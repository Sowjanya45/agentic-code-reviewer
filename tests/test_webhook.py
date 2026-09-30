import hashlib
import hmac
import json

from cryptography.fernet import Fernet
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server.db import Base
from server.models import Installation, User
from server.webhook import _is_review_trigger_comment, _run_review_and_post, webhook_bp


def _make_app(monkeypatch, secret="test-secret"):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    test_sessionmaker = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr("server.db.SessionLocal", test_sessionmaker)

    app = Flask(__name__)
    app.register_blueprint(webhook_bp)
    return app, test_sessionmaker


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_rejects_missing_signature(monkeypatch):
    app, _ = _make_app(monkeypatch)
    client = app.test_client()

    response = client.post("/webhook", json={"action": "created"})

    assert response.status_code == 401


def test_rejects_wrong_signature(monkeypatch):
    app, _ = _make_app(monkeypatch)
    client = app.test_client()
    body = json.dumps({"action": "created"}).encode()

    response = client.post(
        "/webhook",
        data=body,
        headers={"X-Hub-Signature-256": "sha256=wrong", "X-GitHub-Event": "issue_comment"},
        content_type="application/json",
    )

    assert response.status_code == 401


def test_accepts_correctly_signed_payload(monkeypatch):
    app, _ = _make_app(monkeypatch)
    client = app.test_client()
    body = json.dumps({"action": "closed", "issue": {}}).encode()

    response = client.post(
        "/webhook",
        data=body,
        headers={"X-Hub-Signature-256": _sign(body, "test-secret"), "X-GitHub-Event": "issue_comment"},
        content_type="application/json",
    )

    assert response.status_code == 200


def test_installation_created_event_records_installation(monkeypatch):
    app, Session = _make_app(monkeypatch)
    client = app.test_client()
    payload = {"action": "created", "installation": {"id": 555, "account": {"login": "octocat"}}}
    body = json.dumps(payload).encode()

    response = client.post(
        "/webhook",
        data=body,
        headers={"X-Hub-Signature-256": _sign(body, "test-secret"), "X-GitHub-Event": "installation"},
        content_type="application/json",
    )

    assert response.status_code == 200
    db = Session()
    installation = db.query(Installation).filter_by(installation_id=555).one()
    assert installation.account_login == "octocat"
    db.close()


def test_trigger_detects_agentic_review_comment_on_a_pr_from_a_human():
    payload = {
        "action": "created",
        "issue": {"pull_request": {}},
        "comment": {"user": {"type": "User"}, "body": "can you run an agentic-review on this?"},
    }
    assert _is_review_trigger_comment(payload)


def test_trigger_is_case_insensitive():
    payload = {
        "action": "created",
        "issue": {"pull_request": {}},
        "comment": {"user": {"type": "User"}, "body": "Agentic-Review please"},
    }
    assert _is_review_trigger_comment(payload)


def test_trigger_ignores_plain_word_review_without_the_full_phrase():
    # The whole point of the "agentic-review" phrase is to avoid false
    # triggers from ordinary PR chatter that just happens to say "review".
    payload = {
        "action": "created",
        "issue": {"pull_request": {}},
        "comment": {"user": {"type": "User"}, "body": "great work, review looks good!"},
    }
    assert not _is_review_trigger_comment(payload)


def test_trigger_ignores_comment_without_review_keyword():
    payload = {
        "action": "created",
        "issue": {"pull_request": {}},
        "comment": {"user": {"type": "User"}, "body": "nice work!"},
    }
    assert not _is_review_trigger_comment(payload)


def test_trigger_ignores_comment_on_plain_issue_not_pr():
    payload = {
        "action": "created",
        "issue": {},
        "comment": {"user": {"type": "User"}, "body": "agentic-review please"},
    }
    assert not _is_review_trigger_comment(payload)


def test_trigger_ignores_bot_comments_to_avoid_self_retrigger():
    payload = {
        "action": "created",
        "issue": {"pull_request": {}},
        "comment": {"user": {"type": "Bot"}, "body": "## Agentic Code Review\n\nagentic-review complete"},
    }
    assert not _is_review_trigger_comment(payload)


def test_run_review_and_post_without_groq_key_asks_user_to_set_one_up(monkeypatch, mocker):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr("server.db.SessionLocal", Session)

    db = Session()
    user = User(github_id=1, github_login="octocat")  # no groq_key set
    db.add(user)
    db.commit()
    installation = Installation(installation_id=777, account_login="octocat", user_id=user.id)
    db.add(installation)
    db.commit()
    db.close()

    mocker.patch("server.webhook.github_app_auth.get_installation_token", return_value="ghs_token")
    mock_post = mocker.patch("server.webhook.post_review_comment")
    mock_review = mocker.patch("server.webhook.review_pr")

    _run_review_and_post(777, "owner/repo", 5)

    mock_review.assert_not_called()
    mock_post.assert_called_once()
    args = mock_post.call_args[0]
    assert args[0] == "owner/repo"
    assert args[1] == 5
    assert args[2] == "ghs_token"
    assert "Groq API key" in args[3]


def test_run_review_and_post_with_groq_key_runs_review(monkeypatch, mocker):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr("server.db.SessionLocal", Session)

    db = Session()
    user = User(github_id=2, github_login="octocat")
    user.groq_key = "gsk_test"
    db.add(user)
    db.commit()
    installation = Installation(installation_id=888, account_login="octocat", user_id=user.id)
    db.add(installation)
    db.commit()
    db.close()

    mocker.patch("server.webhook.github_app_auth.get_installation_token", return_value="ghs_token")
    mock_post = mocker.patch("server.webhook.post_review_comment")
    fake_report = mocker.Mock()
    mock_review = mocker.patch("server.webhook.review_pr", return_value=fake_report)
    mocker.patch("server.webhook.to_markdown", return_value="## rendered report")

    _run_review_and_post(888, "owner/repo", 9)

    mock_review.assert_called_once_with("owner/repo", 9, "ghs_token", "gsk_test")
    mock_post.assert_called_once_with("owner/repo", 9, "ghs_token", "## rendered report")
