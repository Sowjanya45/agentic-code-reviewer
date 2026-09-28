"""GitHub OAuth login ("Sign in with GitHub") via this GitHub App's own
client id/secret. A GitHub App can act as an OAuth App for user login,
separate from the installation access tokens used for automated reviews
(see github_app_auth.py) -- this is the user's *own* identity/token, used
for the dashboard's manual review actions.
"""
from __future__ import annotations

import os
import secrets
from functools import wraps

import requests
from flask import Blueprint, redirect, request, session, url_for

from .db import get_session
from .models import Installation, User

auth_bp = Blueprint("auth", __name__)

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


@auth_bp.route("/login")
def login():
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    params = {
        "client_id": os.environ["GITHUB_APP_CLIENT_ID"],
        "redirect_uri": url_for("auth.callback", _external=True),
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return redirect(f"{GITHUB_AUTHORIZE_URL}?{query}")


@auth_bp.route("/github/callback")
def callback():
    if request.args.get("state") != session.pop("oauth_state", None):
        return "Invalid OAuth state.", 400

    code = request.args.get("code")
    if not code:
        return "Missing authorization code.", 400

    token_response = requests.post(
        GITHUB_TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": os.environ["GITHUB_APP_CLIENT_ID"],
            "client_secret": os.environ["GITHUB_APP_CLIENT_SECRET"],
            "code": code,
        },
        timeout=15,
    )
    token_response.raise_for_status()
    access_token = token_response.json().get("access_token")
    if not access_token:
        return "GitHub did not return an access token.", 400

    profile_response = requests.get(
        GITHUB_USER_URL,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        timeout=15,
    )
    profile_response.raise_for_status()
    profile = profile_response.json()

    db = get_session()
    try:
        user = db.query(User).filter_by(github_id=profile["id"]).one_or_none()
        if user is None:
            user = User(github_id=profile["id"], github_login=profile["login"])
            db.add(user)
        else:
            user.github_login = profile["login"]
        user.oauth_token = access_token
        db.commit()
        db.refresh(user)

        # If this callback followed an "Install App" click (App has "Request
        # user authorization during installation" enabled), GitHub includes
        # installation_id here -- link it to the user who just logged in.
        installation_id = request.args.get("installation_id")
        if installation_id:
            installation = (
                db.query(Installation).filter_by(installation_id=int(installation_id)).one_or_none()
            )
            if installation is None:
                installation = Installation(
                    installation_id=int(installation_id), account_login=profile["login"]
                )
                db.add(installation)
            installation.user_id = user.id
            db.commit()

        session["user_id"] = user.id
    finally:
        db.close()

    return redirect(url_for("dashboard.index"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
