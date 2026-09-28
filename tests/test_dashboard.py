from cryptography.fernet import Fernet
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server.auth import auth_bp
from server.dashboard import dashboard_bp
from server.db import Base
from server.models import User


def _make_app_with_user(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    test_sessionmaker = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr("server.db.SessionLocal", test_sessionmaker)

    db = test_sessionmaker()
    user = User(github_id=1, github_login="octocat")
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    return app, user_id


def test_dashboard_redirects_to_login_when_not_authenticated(monkeypatch):
    app, _ = _make_app_with_user(monkeypatch)
    client = app.test_client()

    response = client.get("/dashboard")

    assert response.status_code == 302
    assert response.location.endswith("/login")


def test_dashboard_accessible_when_logged_in(monkeypatch):
    app, user_id = _make_app_with_user(monkeypatch)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert b"octocat" in response.data


def test_saving_groq_key_persists_it(monkeypatch):
    app, user_id = _make_app_with_user(monkeypatch)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    response = client.post("/dashboard", data={"action": "save_groq_key", "groq_key": "gsk_abc123"})

    assert response.status_code == 200
    assert b"Groq key saved" in response.data

    from server.db import SessionLocal

    db = SessionLocal()
    user = db.get(User, user_id)
    assert user.groq_key == "gsk_abc123"
    db.close()
