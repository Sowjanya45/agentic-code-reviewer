from pathlib import Path

from reviewer.cache import ReviewCache
from reviewer.schema import Finding


def _finding() -> Finding:
    return Finding(
        file="a.py", line_start=1, line_end=2, category="security",
        severity="warning", confidence=0.5, summary="s", detail="d",
    )


def test_set_then_get_roundtrips(tmp_path: Path):
    cache = ReviewCache(path=tmp_path / "cache.json")
    cache.set("hash1", "security", [_finding()])
    result = cache.get("hash1", "security")
    assert result is not None
    assert result[0].summary == "s"


def test_miss_returns_none(tmp_path: Path):
    cache = ReviewCache(path=tmp_path / "cache.json")
    assert cache.get("nope", "security") is None


def test_persists_across_instances(tmp_path: Path):
    path = tmp_path / "cache.json"
    cache1 = ReviewCache(path=path)
    cache1.set("hash1", "security", [_finding()])
    cache1.save()

    cache2 = ReviewCache(path=path)
    assert cache2.get("hash1", "security") is not None


def test_different_category_is_a_separate_cache_entry(tmp_path: Path):
    cache = ReviewCache(path=tmp_path / "cache.json")
    cache.set("hash1", "security", [_finding()])
    assert cache.get("hash1", "logic") is None
