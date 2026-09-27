"""Attach surrounding-function context to a hunk instead of a raw diff snippet.

Uses tree-sitter to find the enclosing function/class for Python files; falls
back to a fixed line-window expansion for any file tree-sitter can't parse
(other languages, syntax errors, etc.) so the reviewer never fails outright
just because context-building couldn't do the fancy thing.
"""
from __future__ import annotations

from .schema import Hunk

_FALLBACK_WINDOW = 15  # lines of context above/below when tree-sitter can't help
_MAX_ENCLOSING_LINES = 120  # a match this large is a class/module, not a
                            # focused function -- fall back instead of
                            # sending a near-whole-file prompt to the LLM

_PY_LANGUAGE = None


def _get_python_language():
    global _PY_LANGUAGE
    if _PY_LANGUAGE is not None:
        return _PY_LANGUAGE
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language

        _PY_LANGUAGE = Language(tspython.language())
    except Exception:
        _PY_LANGUAGE = False
    return _PY_LANGUAGE


def _enclosing_python_range(source: str, line_start: int, line_end: int) -> tuple[int, int] | None:
    """Return 1-indexed (start, end) lines of the innermost function/class
    enclosing the given range, or None if tree-sitter is unavailable or the
    source doesn't parse.
    """
    language = _get_python_language()
    if not language:
        return None
    try:
        from tree_sitter import Parser

        parser = Parser(language)
        tree = parser.parse(source.encode("utf-8"))
    except Exception:
        return None

    target_start = line_start - 1  # tree-sitter rows are 0-indexed
    target_end = line_end - 1

    best: tuple[int, int] | None = None
    best_span = None

    def visit(node):
        nonlocal best, best_span
        if node.type in ("function_definition", "class_definition"):
            node_start = node.start_point[0]
            node_end = node.end_point[0]
            if node_start <= target_start and node_end >= target_end:
                span = node_end - node_start
                if best_span is None or span < best_span:
                    best = (node_start + 1, node_end + 1)
                    best_span = span
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return best


def build_context(hunk: Hunk, full_content: str | None) -> Hunk:
    """Return a copy of `hunk` with `context_text`/`context_start`/`context_end`
    expanded to cover the enclosing function where possible, else a fixed
    line window around the hunk.
    """
    if not full_content:
        return hunk

    lines = full_content.splitlines()
    total_lines = len(lines)

    enclosing = None
    if hunk.file.endswith(".py"):
        enclosing = _enclosing_python_range(full_content, hunk.context_start, hunk.context_end)
        if enclosing and (enclosing[1] - enclosing[0] + 1) > _MAX_ENCLOSING_LINES:
            enclosing = None  # e.g. a change at class scope in a huge class

    if enclosing:
        ctx_start, ctx_end = enclosing
    else:
        ctx_start = max(1, hunk.context_start - _FALLBACK_WINDOW)
        ctx_end = min(total_lines, hunk.context_end + _FALLBACK_WINDOW)

    context_text = "\n".join(lines[ctx_start - 1 : ctx_end])

    return hunk.model_copy(
        update={
            "context_start": ctx_start,
            "context_end": ctx_end,
            "context_text": context_text,
        }
    )
