"""Pull a PR's diff via the GitHub API and split it into per-file hunks."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from github import Github

from .schema import Hunk

_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class ChangedFile:
    filename: str
    status: str
    patch: str | None
    full_content: str | None  # new-side file content, None if binary/removed/too large


def fetch_pr_files(repo_full_name: str, pr_number: int, github_token: str) -> list[ChangedFile]:
    """Fetch changed files for a PR, including each file's post-change content."""
    gh = Github(github_token)
    repo = gh.get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)

    changed_files: list[ChangedFile] = []
    for f in pr.get_files():
        content: str | None = None
        if f.status != "removed":
            try:
                blob = repo.get_contents(f.filename, ref=pr.head.sha)
                content = blob.decoded_content.decode("utf-8", errors="replace")
            except Exception:
                content = None
        changed_files.append(
            ChangedFile(filename=f.filename, status=f.status, patch=f.patch, full_content=content)
        )
    return changed_files


def parse_patch_to_hunks(filename: str, patch: str) -> list[Hunk]:
    """Split a unified-diff patch (as returned by the GitHub API) into hunks.

    Line numbers are tracked on the new-file ("+") side, since that's what a
    reviewer comments against.
    """
    if not patch:
        return []

    hunks: list[Hunk] = []
    lines = patch.splitlines()
    i = 0
    while i < len(lines):
        m = _HUNK_HEADER_RE.match(lines[i])
        if not m:
            i += 1
            continue
        new_start = int(m.group(3))
        new_len = int(m.group(4) or "1")
        header = lines[i]
        i += 1
        body_lines = []
        while i < len(lines) and not _HUNK_HEADER_RE.match(lines[i]):
            body_lines.append(lines[i])
            i += 1
        diff_text = "\n".join([header, *body_lines])
        content_hash = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()
        hunks.append(
            Hunk(
                file=filename,
                hunk_header=header,
                diff_text=diff_text,
                context_start=new_start,
                context_end=new_start + max(new_len - 1, 0),
                context_text=diff_text,  # replaced by build_context() once file content is known
                content_hash=content_hash,
            )
        )
    return hunks
