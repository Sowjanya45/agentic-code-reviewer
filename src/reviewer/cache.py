"""Content-hash cache so unchanged hunks aren't re-reviewed across re-runs."""
from __future__ import annotations

import json
from pathlib import Path

from .schema import Finding

_DEFAULT_CACHE_PATH = Path("data/cache/review_cache.json")


class ReviewCache:
    def __init__(self, path: Path = _DEFAULT_CACHE_PATH):
        self.path = path
        self._data: dict[str, list[dict]] = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def key(self, content_hash: str, category: str) -> str:
        return f"{content_hash}:{category}"

    def get(self, content_hash: str, category: str) -> list[Finding] | None:
        raw = self._data.get(self.key(content_hash, category))
        if raw is None:
            return None
        return [Finding(**f) for f in raw]

    def set(self, content_hash: str, category: str, findings: list[Finding]) -> None:
        self._data[self.key(content_hash, category)] = [f.model_dump() for f in findings]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2))
