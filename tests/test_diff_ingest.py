from reviewer.diff_ingest import parse_patch_to_hunks

SAMPLE_PATCH = """@@ -10,3 +10,4 @@ def foo():
     a = 1
     b = 2
+    c = 3
     return a + b
@@ -30,2 +31,3 @@ def bar():
     x = 1
+    y = 2
"""


def test_parse_patch_splits_into_two_hunks():
    hunks = parse_patch_to_hunks("pkg/mod.py", SAMPLE_PATCH)
    assert len(hunks) == 2


def test_hunk_line_numbers_track_new_side():
    hunks = parse_patch_to_hunks("pkg/mod.py", SAMPLE_PATCH)
    first, second = hunks
    assert first.context_start == 10
    assert first.context_end == 13  # 10 + len(4) - 1
    assert second.context_start == 31
    assert second.context_end == 33


def test_content_hash_is_stable_for_identical_hunks():
    hunks_a = parse_patch_to_hunks("pkg/mod.py", SAMPLE_PATCH)
    hunks_b = parse_patch_to_hunks("pkg/mod.py", SAMPLE_PATCH)
    assert hunks_a[0].content_hash == hunks_b[0].content_hash


def test_empty_patch_returns_no_hunks():
    assert parse_patch_to_hunks("pkg/mod.py", "") == []
