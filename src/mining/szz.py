"""Simplified SZZ-style bug mining.

Given a fixing commit (identified by commit-message heuristics), find the
earlier commit that introduced the lines the fix removes/changes, via git
blame on the pre-fix file plus content matching against the introducing
commit's own diff (so line numbers are correct in the introducing commit's
*own* diff, not just wherever blame happens to point in a later revision).

This is intentionally a simplified variant of SZZ (no move/rename tracking
across files, no filtering of purely cosmetic changes, no B-SZZ blank-line
skipping) -- good enough to build a real, reproducible evaluation dataset
for a student project, not a research-grade implementation.
"""
from __future__ import annotations

import logging
import re

import git

from mining.dataset import BugPair

logger = logging.getLogger(__name__)

_FIX_RE = re.compile(r"\bfix(e[sd]|ing)?\b", re.IGNORECASE)
_ISSUE_RE = re.compile(r"#(\d+)")
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_IRRELEVANT_PATH_MARKERS = ("test", "docs/", "examples/", "changelog", ".md", ".rst")
_MAX_BUG_COMMIT_SIZE = 400  # insertions + deletions, across the whole commit


def _is_relevant_file(path: str) -> bool:
    if not path.endswith(".py"):
        return False
    lower = path.lower()
    return not any(marker in lower for marker in _IRRELEVANT_PATH_MARKERS)


def find_fixing_commits(
    repo: git.Repo,
    max_fix_commits: int = 200,
    require_issue_ref: bool = False,
    max_commits_scanned: int = 5000,
) -> list[tuple[git.Commit, str | None]]:
    fixing: list[tuple[git.Commit, str | None]] = []
    for scanned, commit in enumerate(repo.iter_commits("HEAD")):
        if scanned >= max_commits_scanned or len(fixing) >= max_fix_commits:
            break
        if len(commit.parents) != 1:
            continue  # skip merge commits and the initial commit
        if not _FIX_RE.search(commit.summary):
            continue
        issue_match = _ISSUE_RE.search(commit.message)
        if require_issue_ref and not issue_match:
            continue
        fixing.append((commit, issue_match.group(1) if issue_match else None))
    return fixing


def _parse_hunk_line_changes(patch_text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return (removed, added), each a list of (line_number, content)."""
    removed: list[tuple[int, str]] = []
    added: list[tuple[int, str]] = []
    old_no = new_no = None
    for line in patch_text.splitlines():
        m = _HUNK_RE.match(line)
        if m:
            old_no = int(m.group(1))
            new_no = int(m.group(3))
            continue
        if old_no is None:
            continue  # still in the diff --git/index/---/+++ preamble
        if line.startswith("-"):
            removed.append((old_no, line[1:]))
            old_no += 1
        elif line.startswith("+"):
            added.append((new_no, line[1:]))
            new_no += 1
        elif line.startswith("\\"):
            continue  # "\ No newline at end of file"
        else:
            old_no += 1
            new_no += 1
    return removed, added


def _diff_text_for_file(commit: git.Commit, parent: git.Commit, filename: str) -> str | None:
    for d in parent.diff(commit, create_patch=True):
        if (d.b_path or d.a_path) == filename:
            patch_bytes = d.diff
            return patch_bytes.decode("utf-8", errors="replace") if isinstance(patch_bytes, bytes) else patch_bytes
    return None


def _blame_line_owners(repo: git.Repo, rev: str, file_path: str) -> dict[int, str]:
    try:
        blame_result = repo.blame(rev, file_path)
    except git.GitCommandError:
        return {}
    if not blame_result:
        return {}
    line_to_commit: dict[int, str] = {}
    line_no = 1
    for commit, lines in blame_result:
        for _ in lines:
            line_to_commit[line_no] = commit.hexsha
            line_no += 1
    return line_to_commit


_MIN_CONTENT_LEN = 6  # skip trivial/common lines ("pass", "", "return") that
                       # would spuriously match many unrelated locations
_MAX_PLAUSIBLE_SPAN = 60  # a genuine single bug rarely spans more lines than
                          # this; a wider match means the content wasn't
                          # actually distinctive, so treat it as unreliable


def _locate_lines_in_introducing_commit(
    repo: git.Repo, bug_commit: git.Commit, filename: str, target_contents: list[str]
) -> tuple[int, int, int]:
    """Find where `target_contents` land in `bug_commit`'s own diff (new-side
    line numbers), so downstream findings can be matched against the diff
    the reviewer will actually see when reviewing bug_commit."""
    if not bug_commit.parents:
        return (0, 0, 0)
    parent = bug_commit.parents[0]
    patch_text = _diff_text_for_file(bug_commit, parent, filename)
    if not patch_text:
        return (0, 0, 0)
    _, added = _parse_hunk_line_changes(patch_text)
    target_set = {c.strip() for c in target_contents if len(c.strip()) >= _MIN_CONTENT_LEN}
    if not target_set:
        return (0, 0, 0)
    matched = [line_no for line_no, content in added if content.strip() in target_set]
    if matched and (max(matched) - min(matched)) > _MAX_PLAUSIBLE_SPAN:
        return (0, 0, 0)
    if not matched:
        return (0, 0, 0)
    return (min(matched), max(matched), len(matched))


def mine_bug_pairs(
    repo: git.Repo,
    repo_url: str,
    repo_local_path: str,
    max_fix_commits: int = 200,
    require_issue_ref: bool = False,
) -> list[BugPair]:
    fixing_commits = find_fixing_commits(repo, max_fix_commits=max_fix_commits, require_issue_ref=require_issue_ref)
    logger.info("found %d candidate fixing commits", len(fixing_commits))

    consolidated: dict[tuple[str, str], dict] = {}

    for fix_commit, issue_ref in fixing_commits:
        parent = fix_commit.parents[0]
        try:
            diffs = parent.diff(fix_commit, create_patch=True)
        except git.GitCommandError:
            continue

        for d in diffs:
            filename = d.b_path or d.a_path
            if not filename or not _is_relevant_file(filename):
                continue
            patch_bytes = d.diff
            patch_text = patch_bytes.decode("utf-8", errors="replace") if isinstance(patch_bytes, bytes) else (patch_bytes or "")
            removed, _ = _parse_hunk_line_changes(patch_text)
            if not removed:
                continue  # pure addition, nothing to blame back to a bug

            blame_map = _blame_line_owners(repo, parent.hexsha, filename)
            if not blame_map:
                continue

            by_bug_commit: dict[str, list[str]] = {}
            for old_line_no, content in removed:
                bug_sha = blame_map.get(old_line_no)
                if not bug_sha or bug_sha == fix_commit.hexsha:
                    continue
                by_bug_commit.setdefault(bug_sha, []).append(content)

            for bug_sha, contents in by_bug_commit.items():
                bug_commit = repo.commit(bug_sha)
                if len(bug_commit.parents) != 1:
                    continue  # skip merges and the repo's initial commit
                if bug_commit.stats.total["lines"] > _MAX_BUG_COMMIT_SIZE:
                    continue  # a sweeping rewrite isn't a realistic "PR" to
                    # evaluate a reviewer against, and inflates content-match
                    # false positives (common short lines recur across it)
                line_start, line_end, matched = _locate_lines_in_introducing_commit(
                    repo, bug_commit, filename, contents
                )
                if matched == 0:
                    continue

                key = (bug_sha, filename)
                existing = consolidated.get(key)
                if existing:
                    existing["line_start"] = min(existing["line_start"], line_start)
                    existing["line_end"] = max(existing["line_end"], line_end)
                    existing["matched_lines"] += matched
                else:
                    consolidated[key] = {
                        "fix_commit": fix_commit.hexsha,
                        "fix_summary": fix_commit.summary,
                        "bug_commit": bug_sha,
                        "file": filename,
                        "line_start": line_start,
                        "line_end": line_end,
                        "matched_lines": matched,
                        "issue_ref": issue_ref,
                    }

    return [
        BugPair(repo=repo_local_path, repo_url=repo_url, **fields) for fields in consolidated.values()
    ]
