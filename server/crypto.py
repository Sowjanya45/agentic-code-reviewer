"""Encrypt/decrypt secrets at rest (Groq keys, GitHub OAuth tokens).

Never store these plaintext in the database -- a database dump or a
misconfigured backup would otherwise leak every user's credentials at once.
`ENCRYPTION_KEY` must be a Fernet key; generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    return Fernet(os.environ["ENCRYPTION_KEY"].encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()
