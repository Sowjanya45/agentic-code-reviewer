"""Database engine/session setup. Uses DATABASE_URL if set (Render's free
Postgres add-on provides this automatically); falls back to a local SQLite
file for development so the server runs without any DB setup."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///server_dev.db")
    # Render (and some other hosts) give postgres:// URLs, but SQLAlchemy's
    # psycopg2 driver wants the postgresql:// scheme.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


engine = create_engine(_database_url(), future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    from . import models  # noqa: F401 - ensures models are registered on Base

    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()
