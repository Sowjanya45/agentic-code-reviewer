"""Build ChangedFile/Hunk objects from a local git commit instead of a live
GitHub PR -- used by the evaluation harness, which reviews historical
commits rather than open PRs."""
from __future__ import annotations

import git

from .diff_ingest import ChangedFile

SOURCE_EXTENSIONS = (".py",)


def changed_files_from_commit(repo: git.Repo, commit_sha: str) -> list[ChangedFile]:
    """Diff `commit_sha` against its first parent, as if it were a PR."""
    commit = repo.commit(commit_sha)
    if not commit.parents:
        return []
    parent = commit.parents[0]
    diffs = parent.diff(commit, create_patch=True)

    changed: list[ChangedFile] = []
    for d in diffs:
        filename = d.b_path or d.a_path
        if not filename or not filename.endswith(SOURCE_EXTENSIONS):
            continue
        patch_bytes = d.diff
        patch_text = (
            patch_bytes.decode("utf-8", errors="replace") if isinstance(patch_bytes, bytes) else (patch_bytes or "")
        )
        full_content = None
        if d.b_blob is not None:
            try:
                full_content = d.b_blob.data_stream.read().decode("utf-8", errors="replace")
            except Exception:
                full_content = None
        changed.append(
            ChangedFile(filename=filename, status=d.change_type or "modified", patch=patch_text, full_content=full_content)
        )
    return changed
