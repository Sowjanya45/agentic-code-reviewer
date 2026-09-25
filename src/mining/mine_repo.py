"""CLI: mine bug-fix pairs from a target OSS repo's history.

Usage:
    python -m mining.mine_repo https://github.com/pallets/flask.git \\
        --clone-dir data/repos/flask --out data/mined/flask.json
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import git

from mining.dataset import save_dataset
from mining.szz import mine_bug_pairs


def clone_or_open(url: str, dest: Path) -> git.Repo:
    if dest.exists() and (dest / ".git").exists():
        logging.info("using existing clone at %s", dest)
        return git.Repo(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    logging.info("cloning %s into %s", url, dest)
    return git.Repo.clone_from(url, dest)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Mine SZZ-style bug-fix pairs from a repo's history.")
    parser.add_argument("repo_url")
    parser.add_argument("--clone-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-fix-commits", type=int, default=200)
    parser.add_argument("--require-issue-ref", action="store_true")
    args = parser.parse_args()

    clone_dir = Path(args.clone_dir)
    repo = clone_or_open(args.repo_url, clone_dir)

    pairs = mine_bug_pairs(
        repo,
        repo_url=args.repo_url,
        repo_local_path=str(clone_dir),
        max_fix_commits=args.max_fix_commits,
        require_issue_ref=args.require_issue_ref,
    )
    logging.info("mined %d bug-fix pairs", len(pairs))

    out_path = Path(args.out)
    save_dataset(pairs, out_path)
    logging.info("saved dataset to %s", out_path)


if __name__ == "__main__":
    main()
