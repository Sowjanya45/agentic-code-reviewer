"""CLI entry point: review a real PR end to end.

Usage:
    python -m reviewer.cli owner/repo 123
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from .graph import review_pr
from .report import to_markdown
from .triage import MAX_FILES_DEFAULT


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run the agentic code reviewer on a PR.")
    parser.add_argument("repo", help="owner/repo")
    parser.add_argument("pr_number", type=int)
    parser.add_argument("--max-files", type=int, default=MAX_FILES_DEFAULT)
    args = parser.parse_args()

    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("GITHUB_TOKEN is not set (see .env.example).", file=sys.stderr)
        sys.exit(1)
    if not os.environ.get("GROQ_API_KEY"):
        print("GROQ_API_KEY is not set (see .env.example).", file=sys.stderr)
        sys.exit(1)

    report = review_pr(args.repo, args.pr_number, github_token, max_files=args.max_files)
    print(to_markdown(report))


if __name__ == "__main__":
    main()
