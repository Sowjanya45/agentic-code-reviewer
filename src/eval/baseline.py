"""Two baselines to compare the agentic reviewer's architecture against:

1. A plain linter (ruff) -- fast, deterministic, no LLM at all.
2. A naive single-prompt LLM review with no chunking and no per-category
   checkers, to isolate the value the chunking + focused-checker
   architecture adds over just pasting a diff into an LLM.
"""
from __future__ import annotations

import json
import subprocess

import git

from reviewer.llm import call_structured
from reviewer.local_diff import changed_files_from_commit
from reviewer.schema import CheckerResult, Finding


def run_ruff_baseline(git_repo: git.Repo, commit_sha: str) -> list[Finding]:
    """Run ruff over each changed file's post-commit content and turn its
    diagnostics into Findings, so results are comparable like-for-like."""
    findings: list[Finding] = []
    for f in changed_files_from_commit(git_repo, commit_sha):
        if not f.full_content:
            continue
        try:
            proc = subprocess.run(
                ["ruff", "check", "--output-format=json", "--stdin-filename", f.filename, "-"],
                input=f.full_content,
                capture_output=True,
                text=True,
                timeout=15,
            )
            diagnostics = json.loads(proc.stdout or "[]")
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            continue
        for d in diagnostics:
            line = d.get("location", {}).get("row", 1)
            findings.append(
                Finding(
                    file=f.filename,
                    line_start=line,
                    line_end=line,
                    category="logic",
                    severity="nit",
                    confidence=0.5,
                    summary=d.get("code") or "ruff",
                    detail=d.get("message", ""),
                )
            )
    return findings


_NAIVE_PROMPT_TEMPLATE = """Review the following code diff for any issues: security
problems, missing/incorrect error handling, missing test coverage, or logic bugs.
Report every issue you find as a structured finding with a file, line range,
category, severity, confidence, summary and detail.

Diff:
```
{diff_text}
```
"""


def naive_single_prompt_review(git_repo: git.Repo, commit_sha: str) -> list[Finding]:
    """One LLM call over the whole commit's diff, no chunking, no per-category
    prompts, no surrounding-function context -- the simplest possible LLM
    reviewer, used to show what the agentic architecture adds."""
    files = changed_files_from_commit(git_repo, commit_sha)
    diff_text = "\n".join(f"--- {f.filename} ---\n{f.patch}" for f in files if f.patch)
    if not diff_text.strip():
        return []
    prompt = _NAIVE_PROMPT_TEMPLATE.format(diff_text=diff_text)
    try:
        result: CheckerResult = call_structured(prompt, CheckerResult)
    except Exception:
        return []
    return result.findings
