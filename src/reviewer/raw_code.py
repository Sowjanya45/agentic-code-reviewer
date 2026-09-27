"""Build a single Hunk from raw pasted code, so the same reviewer pipeline
(checkers, aggregation, failure handling) can review a snippet the user
pastes directly, not just a PR diff or a historical commit."""
from __future__ import annotations

import hashlib

from .schema import Hunk

MAX_RAW_CODE_LINES = 500


def hunk_from_raw_code(filename: str, code: str) -> Hunk:
    """Treat the whole snippet as a single addition hunk -- the context IS
    the pasted code, so no separate context-expansion step is needed."""
    lines = code.splitlines() or [""]
    if len(lines) > MAX_RAW_CODE_LINES:
        raise ValueError(
            f"Pasted code has {len(lines)} lines, over the {MAX_RAW_CODE_LINES}-line "
            "limit for a single review. Paste a smaller snippet."
        )

    header = f"@@ -0,0 +1,{len(lines)} @@"
    diff_text = "\n".join([header, *(f"+{line}" for line in lines)])
    content_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()

    return Hunk(
        file=filename,
        hunk_header=header,
        diff_text=diff_text,
        context_start=1,
        context_end=len(lines),
        context_text=code,
        content_hash=content_hash,
    )
