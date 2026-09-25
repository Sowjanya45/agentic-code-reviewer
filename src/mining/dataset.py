"""Storage for mined (bug-introducing commit, fixing commit) pairs."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class BugPair(BaseModel):
    repo: str  # local clone path, for reproducibility recorded alongside repo_url
    repo_url: str
    fix_commit: str
    fix_summary: str
    bug_commit: str
    file: str
    line_start: int
    line_end: int
    matched_lines: int
    issue_ref: str | None = None


def save_dataset(pairs: list[BugPair], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([p.model_dump() for p in pairs], indent=2))


def load_dataset(path: Path) -> list[BugPair]:
    data = json.loads(path.read_text())
    return [BugPair(**d) for d in data]
