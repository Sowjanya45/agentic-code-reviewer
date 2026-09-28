"""SQLAlchemy models. Secrets (Groq key, GitHub OAuth token) are stored
encrypted (see crypto.py) and exposed via plain-text properties so callers
never have to think about encryption at the call site."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import crypto
from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    github_login: Mapped[str] = mapped_column(String(255), nullable=False)
    _encrypted_oauth_token: Mapped[str | None] = mapped_column("encrypted_oauth_token", Text, nullable=True)
    _encrypted_groq_key: Mapped[str | None] = mapped_column("encrypted_groq_key", Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    installations: Mapped[list["Installation"]] = relationship(back_populates="user")

    @property
    def oauth_token(self) -> str | None:
        return crypto.decrypt(self._encrypted_oauth_token) if self._encrypted_oauth_token else None

    @oauth_token.setter
    def oauth_token(self, value: str) -> None:
        self._encrypted_oauth_token = crypto.encrypt(value)

    @property
    def groq_key(self) -> str | None:
        return crypto.decrypt(self._encrypted_groq_key) if self._encrypted_groq_key else None

    @groq_key.setter
    def groq_key(self, value: str) -> None:
        self._encrypted_groq_key = crypto.encrypt(value)


class Installation(Base):
    __tablename__ = "installations"

    id: Mapped[int] = mapped_column(primary_key=True)
    installation_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped[User | None] = relationship(back_populates="installations")
