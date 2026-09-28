"""Post the reviewer's findings back as a comment on the PR that triggered
the review -- used by the comment-triggered GitHub Action."""
from __future__ import annotations

from github import Github


def post_review_comment(repo_full_name: str, pr_number: int, github_token: str, body: str) -> None:
    gh = Github(github_token)
    repo = gh.get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)
    pr.create_issue_comment(body)
