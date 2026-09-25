from reviewer.chunking import build_context
from reviewer.schema import Hunk

SOURCE = '''\
import os


def unrelated():
    pass


def target_function(x):
    if x > 0:
        return x
    return -x


class Foo:
    def method(self):
        return 1
'''


def _make_hunk(start: int, end: int) -> Hunk:
    return Hunk(
        file="mod.py",
        hunk_header="@@ -1,1 +1,1 @@",
        diff_text="+ return x",
        context_start=start,
        context_end=end,
        context_text="",
        content_hash="abc123",
    )


def test_expands_to_enclosing_function():
    # line 9 is `if x > 0:` inside target_function (lines 8-11)
    hunk = _make_hunk(9, 9)
    expanded = build_context(hunk, SOURCE)
    assert expanded.context_start == 8
    assert expanded.context_end == 11
    assert "target_function" in expanded.context_text


def test_falls_back_to_line_window_for_non_python():
    hunk = Hunk(
        file="mod.js",
        hunk_header="@@ -1,1 +1,1 @@",
        diff_text="+ return x",
        context_start=5,
        context_end=5,
        context_text="",
        content_hash="abc123",
    )
    js_source = "\n".join(f"line{i}" for i in range(1, 30))
    expanded = build_context(hunk, js_source)
    assert expanded.context_start < 5
    assert expanded.context_end > 5


def test_no_content_returns_hunk_unchanged():
    hunk = _make_hunk(9, 9)
    expanded = build_context(hunk, None)
    assert expanded is hunk
