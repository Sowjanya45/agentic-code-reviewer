"""Merge findings from all chunks/checkers: dedupe overlapping findings in
the same file+category, then rank by severity/confidence."""
from __future__ import annotations

from .schema import Finding

_SEVERITY_ORDER = {"blocker": 0, "warning": 1, "nit": 2}


def aggregate_findings(findings: list[Finding]) -> list[Finding]:
    groups: dict[tuple[str, str], list[Finding]] = {}
    for f in findings:
        groups.setdefault((f.file, f.category), []).append(f)

    deduped: list[Finding] = []
    for group in groups.values():
        kept: list[Finding] = []
        for f in sorted(group, key=lambda x: (_SEVERITY_ORDER[x.severity], -x.confidence)):
            if any(k.overlaps(f.file, f.line_start, f.line_end) for k in kept):
                continue
            kept.append(f)
        deduped.extend(kept)

    return sorted(deduped, key=lambda f: (_SEVERITY_ORDER[f.severity], -f.confidence))
