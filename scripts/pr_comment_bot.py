"""Entry point for the GitHub Action: review the PR that was commented on
and post the findings back as a PR comment.

Reads everything it needs from environment variables set by the workflow
(.github/workflows/pr-review-bot.yml) -- there is no CLI to invoke this by
hand outside that context.
"""
from __future__ import annotations

import os
import sys

from reviewer.github_comment import post_review_comment
from reviewer.graph import review_pr
from reviewer.report import to_markdown


def main() -> None:
    repo_full_name = os.environ["REPO_FULL_NAME"]
    pr_number = int(os.environ["PR_NUMBER"])
    github_token = os.environ["GITHUB_TOKEN"]

    try:
        report = review_pr(repo_full_name, pr_number, github_token)
        body = to_markdown(report)
    except Exception as exc:  # noqa: BLE001 - always leave a comment, even on failure
        body = f"## Agentic Code Review\n\nThe review failed to run: `{exc}`"
        post_review_comment(repo_full_name, pr_number, github_token, body)
        print(f"Review failed: {exc}", file=sys.stderr)
        raise

    post_review_comment(repo_full_name, pr_number, github_token, body)
    print(f"Posted review comment on {repo_full_name}#{pr_number}")


if __name__ == "__main__":
    main()
