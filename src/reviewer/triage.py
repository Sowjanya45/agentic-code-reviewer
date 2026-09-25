"""Risk-based ranking of changed files, used to decide what gets reviewed
when a PR is too large to review in full."""
from __future__ import annotations

from .diff_ingest import ChangedFile

MAX_FILES_DEFAULT = 40

_HIGH_RISK_PATTERNS = (
    "auth", "login", "session", "token", "password", "secret", "crypto",
    "payment", "billing", "checkout", "permission", "access", "security",
)
_LOW_RISK_PATTERNS = (
    "docs/", "readme", "changelog", ".md", "test_", "_test.py", "/tests/",
    "example", "sample",
)


def _risk_score(filename: str) -> int:
    lower = filename.lower()
    if any(p in lower for p in _HIGH_RISK_PATTERNS):
        return 2
    if any(p in lower for p in _LOW_RISK_PATTERNS):
        return 0
    return 1


def rank_files_by_risk(files: list[ChangedFile]) -> list[ChangedFile]:
    """Highest-risk files first, so a size cap drops the least important ones."""
    return sorted(files, key=lambda f: _risk_score(f.filename), reverse=True)
