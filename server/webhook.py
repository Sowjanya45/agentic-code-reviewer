"""GitHub webhook receiver: triggers a review when someone comments
something containing "agentic-review" on a PR, across every repo this
GitHub App installation covers -- the automatic counterpart to the
dashboard's manual "Review PR" button.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import threading

from flask import Blueprint, request

from reviewer.github_comment import post_review_comment
from reviewer.graph import review_pr
from reviewer.report import to_markdown

from . import github_app_auth
from .db import get_session
from .models import Installation

webhook_bp = Blueprint("webhook", __name__)


def _verify_signature(payload_body: bytes, signature_header: str | None) -> bool:
    secret = os.environ["GITHUB_WEBHOOK_SECRET"]
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _is_review_trigger_comment(payload: dict) -> bool:
    if payload.get("action") != "created":
        return False
    issue = payload.get("issue", {})
    if "pull_request" not in issue:
        return False  # a plain issue comment, not a PR comment
    commenter = payload.get("comment", {}).get("user", {})
    if commenter.get("type") == "Bot":
        return False  # don't let our own reply (or any bot) retrigger this
    body = payload.get("comment", {}).get("body", "")
    return "agentic-review" in body.lower()


def _run_review_and_post(installation_id: int, repo_full_name: str, pr_number: int) -> None:
    db = get_session()
    try:
        installation = db.query(Installation).filter_by(installation_id=installation_id).one_or_none()
        user = installation.user if installation else None
        groq_key = user.groq_key if user else None
    finally:
        db.close()

    installation_token = github_app_auth.get_installation_token(installation_id)

    if not groq_key:
        post_review_comment(
            repo_full_name,
            pr_number,
            installation_token,
            "## Agentic Code Review\n\nThis account hasn't set up a Groq API key yet. "
            'Log in to the dashboard and add one, then comment "agentic-review" again.',
        )
        return

    try:
        report = review_pr(repo_full_name, pr_number, installation_token, groq_key)
        body = to_markdown(report)
    except Exception as exc:  # noqa: BLE001 - always leave a comment, even on failure
        body = f"## Agentic Code Review\n\nThe review failed to run: `{exc}`"

    post_review_comment(repo_full_name, pr_number, installation_token, body)


def _handle_installation_event(payload: dict) -> None:
    if payload.get("action") not in ("created", "unsuspend"):
        return
    installation_data = payload.get("installation", {})
    installation_id = installation_data.get("id")
    account_login = installation_data.get("account", {}).get("login")
    if not installation_id or not account_login:
        return

    db = get_session()
    try:
        installation = db.query(Installation).filter_by(installation_id=installation_id).one_or_none()
        if installation is None:
            installation = Installation(installation_id=installation_id, account_login=account_login)
            db.add(installation)
        else:
            installation.account_login = account_login
        db.commit()
    finally:
        db.close()


@webhook_bp.route("/webhook", methods=["POST"])
def webhook():
    if not _verify_signature(request.get_data(), request.headers.get("X-Hub-Signature-256")):
        return "Invalid signature", 401

    event = request.headers.get("X-GitHub-Event")
    payload = request.get_json(force=True, silent=True) or {}

    if event == "installation":
        _handle_installation_event(payload)
        return "", 200

    if event == "issue_comment" and _is_review_trigger_comment(payload):
        installation_id = payload["installation"]["id"]
        repo_full_name = payload["repository"]["full_name"]
        pr_number = payload["issue"]["number"]

        # Review calls out to the LLM and can take well over GitHub's webhook
        # response window (~10s), so acknowledge immediately and do the
        # actual work in the background -- otherwise GitHub treats the
        # delivery as failed and retries it, which would double-post.
        thread = threading.Thread(
            target=_run_review_and_post,
            args=(installation_id, repo_full_name, pr_number),
            daemon=True,
        )
        thread.start()

    return "", 200
