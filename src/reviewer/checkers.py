"""Per-category checker prompts and the per-chunk review call."""
from __future__ import annotations

from .cache import ReviewCache
from .llm import call_structured
from .schema import CheckerResult, ChunkReviewOutcome, Hunk

CATEGORIES = ("security", "error_handling", "missing_test", "logic")

_CATEGORY_INSTRUCTIONS = {
    "security": (
        "Look ONLY for security issues: injection (SQL/command/template), "
        "unsafe deserialization, hardcoded secrets/credentials, missing "
        "input validation on untrusted data, path traversal, SSRF, insecure "
        "use of crypto/random, auth/authorization bypass."
    ),
    "error_handling": (
        "Look ONLY for missing or incorrect error handling: unhandled "
        "exceptions on I/O/network/parsing calls, bare except clauses that "
        "swallow errors silently, resources not closed/released on the "
        "error path, error messages that leak internals."
    ),
    "missing_test": (
        "Look ONLY for missing test coverage: new branches, edge cases, or "
        "error paths introduced by this change that don't appear to be "
        "covered by any test in the surrounding context. Do not flag "
        "missing tests for trivial getters/formatting."
    ),
    "logic": (
        "Look ONLY for logic bugs: off-by-one errors, incorrect "
        "conditionals, wrong operator, mutable default arguments, "
        "incorrect handling of None/empty collections."
    ),
}

_PROMPT_TEMPLATE = """You are a focused code reviewer. {instructions}

Only report issues you are reasonably confident about; it is fine to return
no findings. Every finding must cite a specific line range within the
context shown below (not lines outside it).

File: {file}
Context lines {context_start}-{context_end} (line numbers match this file):
```
{context_text}
```

The diff hunk being reviewed (this is what actually changed):
```
{diff_text}
```
"""


def _build_prompt(hunk: Hunk, category: str) -> str:
    return _PROMPT_TEMPLATE.format(
        instructions=_CATEGORY_INSTRUCTIONS[category],
        file=hunk.file,
        context_start=hunk.context_start,
        context_end=hunk.context_end,
        context_text=hunk.context_text,
        diff_text=hunk.diff_text,
    )


def review_chunk(hunk: Hunk, category: str, cache: ReviewCache | None = None) -> ChunkReviewOutcome:
    cache = cache or ReviewCache()
    cached = cache.get(hunk.content_hash, category)
    if cached is not None:
        return ChunkReviewOutcome(hunk=hunk, findings=cached, status="ok")

    prompt = _build_prompt(hunk, category)
    try:
        result: CheckerResult = call_structured(prompt, CheckerResult)
    except Exception as exc:  # noqa: BLE001 - a failing chunk must not crash the run
        return ChunkReviewOutcome(hunk=hunk, findings=[], status="failed", error=str(exc))

    # Clamp findings to this hunk's file; a hallucinated file name would
    # otherwise corrupt aggregation/matching downstream.
    findings = [f for f in result.findings if f.file == hunk.file]
    cache.set(hunk.content_hash, category, findings)
    return ChunkReviewOutcome(hunk=hunk, findings=findings, status="ok")
