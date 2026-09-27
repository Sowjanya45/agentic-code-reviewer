import pytest

from reviewer.raw_code import MAX_RAW_CODE_LINES, hunk_from_raw_code


def test_builds_single_hunk_covering_whole_snippet():
    code = "def add(a, b):\n    return a + b\n"
    hunk = hunk_from_raw_code("snippet.py", code)
    assert hunk.file == "snippet.py"
    assert hunk.context_start == 1
    assert hunk.context_end == 2
    assert hunk.context_text == code
    assert "+def add(a, b):" in hunk.diff_text


def test_content_hash_stable_for_identical_code():
    code = "x = 1\n"
    a = hunk_from_raw_code("s.py", code)
    b = hunk_from_raw_code("s.py", code)
    assert a.content_hash == b.content_hash


def test_rejects_oversized_snippet():
    huge_code = "\n".join(f"x{i} = {i}" for i in range(MAX_RAW_CODE_LINES + 1))
    with pytest.raises(ValueError):
        hunk_from_raw_code("s.py", huge_code)
