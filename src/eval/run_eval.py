"""Run the agentic reviewer (and baselines) over the mined bug dataset and
compute recall/precision, saving a reproducible results file.

Usage:
    python -m eval.run_eval --dataset data/mined/flask.json \\
        --repo data/repos/flask --out data/eval/flask_results.json
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import git

from eval.baseline import naive_single_prompt_review, run_ruff_baseline
from eval.matching import bug_is_caught, count_matching_findings
from mining.dataset import BugPair, load_dataset
from reviewer.graph import review_local_commit
from reviewer.schema import Finding

logger = logging.getLogger(__name__)


def _evaluate_one(bug: BugPair, findings: list[Finding]) -> dict:
    return {
        "bug_commit": bug.bug_commit,
        "file": bug.file,
        "caught": bug_is_caught(findings, bug),
        "total_findings": len(findings),
        "matching_findings": count_matching_findings(findings, bug),
    }


def _summarize(cases: list[dict]) -> dict:
    n = len(cases)
    if n == 0:
        return {"n": 0}
    caught = sum(1 for c in cases if c["caught"])
    total_findings = sum(c["total_findings"] for c in cases)
    matching_findings = sum(c["matching_findings"] for c in cases)
    return {
        "n": n,
        "recall": caught / n,
        "avg_findings_per_case": total_findings / n,
        "precision": (matching_findings / total_findings) if total_findings else 0.0,
    }


def run_evaluation(
    dataset_path: Path, repo_local_path: str, max_pairs: int | None, run_baselines: bool
) -> dict:
    pairs = load_dataset(dataset_path)
    if max_pairs:
        pairs = pairs[:max_pairs]
    repo = git.Repo(repo_local_path)

    per_case: list[dict] = []
    ruff_cases: list[dict] = []
    naive_cases: list[dict] = []

    for i, bug in enumerate(pairs):
        logger.info("[%d/%d] reviewing %s (%s)", i + 1, len(pairs), bug.bug_commit[:8], bug.file)
        report = review_local_commit(repo, bug.bug_commit)
        per_case.append(_evaluate_one(bug, report.findings))

        if run_baselines:
            ruff_cases.append(_evaluate_one(bug, run_ruff_baseline(repo, bug.bug_commit)))
            naive_cases.append(_evaluate_one(bug, naive_single_prompt_review(repo, bug.bug_commit)))

    result = {
        "dataset": str(dataset_path),
        "n_cases": len(pairs),
        "agentic_reviewer": _summarize(per_case),
        "cases": per_case,
    }
    if run_baselines:
        result["baseline_ruff"] = _summarize(ruff_cases)
        result["baseline_naive_llm"] = _summarize(naive_cases)

    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Evaluate the reviewer against a mined bug dataset.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--repo", required=True, help="local path to the cloned target repo")
    parser.add_argument("--max-pairs", type=int, default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--skip-baselines", action="store_true")
    args = parser.parse_args()

    result = run_evaluation(
        Path(args.dataset), args.repo, args.max_pairs, run_baselines=not args.skip_baselines
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    logging.info("wrote results to %s", out_path)
    logging.info("agentic reviewer: %s", result["agentic_reviewer"])
    if not args.skip_baselines:
        logging.info("baseline ruff: %s", result["baseline_ruff"])
        logging.info("baseline naive llm: %s", result["baseline_naive_llm"])


if __name__ == "__main__":
    main()
