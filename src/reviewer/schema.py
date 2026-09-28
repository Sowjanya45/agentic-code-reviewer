"""Structured types shared by the reviewer graph and the evaluation harness."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["security", "error_handling", "missing_test", "logic"]
Severity = Literal["blocker", "warning", "nit"]


class Finding(BaseModel):
    file: str
    line_start: int
    line_end: int
    category: Category
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    detail: str
    suggested_fix: str | None = None

    def overlaps(self, other_file: str, other_start: int, other_end: int) -> bool:
        if self.file != other_file:
            return False
        return self.line_start <= other_end and other_start <= self.line_end


class CheckerResult(BaseModel):
    """Output of a single checker LLM call over a single chunk."""

    findings: list[Finding] = Field(default_factory=list)


class Hunk(BaseModel):
    """A single diff hunk plus the surrounding context used for review."""

    file: str
    hunk_header: str
    diff_text: str
    context_start: int
    context_end: int
    context_text: str
    content_hash: str


class ChunkReviewOutcome(BaseModel):
    hunk: Hunk
    findings: list[Finding] = Field(default_factory=list)
    status: Literal["ok", "failed", "skipped"] = "ok"
    error: str | None = None


class ReviewReport(BaseModel):
    pr_identifier: str
    findings: list[Finding] = Field(default_factory=list)
    files_reviewed: int
    files_skipped: int
    skipped_files: list[str] = Field(default_factory=list)
    failed_chunks: int = 0
    failure_reasons: list[str] = Field(default_factory=list)
