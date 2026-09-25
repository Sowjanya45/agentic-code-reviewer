"""Render a ReviewReport as Markdown suitable for pasting into a PR comment."""
from __future__ import annotations

from .schema import ReviewReport

_SEVERITY_EMOJI = {"blocker": "\U0001F534", "warning": "\U0001F7E1", "nit": "⚪"}


def to_markdown(report: ReviewReport) -> str:
    lines = [f"## Agentic Code Review — {report.pr_identifier}", ""]
    lines.append(
        f"Reviewed {report.files_reviewed} file(s), skipped {report.files_skipped} "
        f"(size cap), {report.failed_chunks} chunk(s) failed after retries."
    )
    if report.skipped_files:
        lines.append(f"Skipped: {', '.join(report.skipped_files)}")
    lines.append("")

    if not report.findings:
        lines.append("No findings.")
        return "\n".join(lines)

    for f in report.findings:
        emoji = _SEVERITY_EMOJI.get(f.severity, "")
        lines.append(f"### {emoji} [{f.category}] {f.summary}")
        lines.append(f"`{f.file}:{f.line_start}-{f.line_end}` — confidence {f.confidence:.2f}")
        lines.append("")
        lines.append(f.detail)
        if f.suggested_fix:
            lines.append("")
            lines.append("Suggested fix:")
            lines.append(f"```\n{f.suggested_fix}\n```")
        lines.append("")

    return "\n".join(lines)
