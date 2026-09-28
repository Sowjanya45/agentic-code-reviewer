import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server.db import Base
from server.models import Installation, User


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_groq_key_stored_encrypted_but_reads_back_plain(session):
    user = User(github_id=1, github_login="octocat")
    user.groq_key = "gsk_test_key"
    session.add(user)
    session.commit()

    fetched = session.query(User).filter_by(github_id=1).one()
    assert fetched.groq_key == "gsk_test_key"
    assert fetched._encrypted_groq_key != "gsk_test_key"


def test_oauth_token_stored_encrypted_but_reads_back_plain(session):
    user = User(github_id=2, github_login="hubot")
    user.oauth_token = "gho_test_token"
    session.add(user)
    session.commit()

    fetched = session.query(User).filter_by(github_id=2).one()
    assert fetched.oauth_token == "gho_test_token"
    assert fetched._encrypted_oauth_token != "gho_test_token"


def test_user_with_no_groq_key_yet_returns_none(session):
    user = User(github_id=3, github_login="newbie")
    session.add(user)
    session.commit()

    fetched = session.query(User).filter_by(github_id=3).one()
    assert fetched.groq_key is None


def test_installation_links_to_user(session):
    user = User(github_id=4, github_login="octocat")
    session.add(user)
    session.commit()

    installation = Installation(installation_id=999, account_login="octocat", user_id=user.id)
    session.add(installation)
    session.commit()

    fetched = session.query(Installation).filter_by(installation_id=999).one()
    assert fetched.user.github_login == "octocat"
