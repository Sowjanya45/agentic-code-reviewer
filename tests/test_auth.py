from cryptography.fernet import Fernet
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server.auth import auth_bp
from server.dashboard import dashboard_bp
from server.db import Base
from server.models import User


def _make_app(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("GITHUB_APP_CLIENT_ID", "client123")
    monkeypatch.setenv("GITHUB_APP_CLIENT_SECRET", "secret456")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    test_sessionmaker = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr("server.db.SessionLocal", test_sessionmaker)

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    return app


def test_login_redirects_to_github_with_client_id_and_state(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()

    response = client.get("/login")

    assert response.status_code == 302
    assert "client_id=client123" in response.location
    assert "state=" in response.location


def test_callback_rejects_mismatched_state(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()

    client.get("/login")  # sets session['oauth_state']
    response = client.get("/github/callback?code=abc&state=wrong-state")

    assert response.status_code == 400


def test_callback_creates_user_and_redirects_to_dashboard(monkeypatch, mocker):
    app = _make_app(monkeypatch)
    client = app.test_client()

    login_resp = client.get("/login")
    state = login_resp.location.split("state=")[1]

    token_resp = mocker.Mock()
    token_resp.json.return_value = {"access_token": "gho_test_token"}
    token_resp.raise_for_status.return_value = None

    profile_resp = mocker.Mock()
    profile_resp.json.return_value = {"id": 42, "login": "octocat"}
    profile_resp.raise_for_status.return_value = None

    mocker.patch("server.auth.requests.post", return_value=token_resp)
    mocker.patch("server.auth.requests.get", return_value=profile_resp)

    response = client.get(f"/github/callback?code=abc123&state={state}")

    assert response.status_code == 302
    assert response.location.endswith("/dashboard")

    from server.db import SessionLocal

    db = SessionLocal()
    user = db.query(User).filter_by(github_id=42).one()
    assert user.github_login == "octocat"
    assert user.oauth_token == "gho_test_token"
    db.close()
