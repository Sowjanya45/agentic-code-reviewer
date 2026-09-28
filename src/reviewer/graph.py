"""LangGraph wiring: ingest -> fan out to per-hunk/per-category checkers ->
aggregate. Uses LangGraph's Send API for the dynamic fan-out since the
number of hunks isn't known until the PR is fetched."""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from .aggregator import aggregate_findings
from .cache import ReviewCache
from .checkers import CATEGORIES, review_chunk
from .chunking import build_context
from .diff_ingest import fetch_pr_files, parse_patch_to_hunks
from .raw_code import hunk_from_raw_code
from .schema import ChunkReviewOutcome, Hunk, ReviewReport
from .triage import MAX_FILES_DEFAULT, rank_files_by_risk


class GraphState(TypedDict, total=False):
    mode: str  # "github_pr" or "raw_code"
    pr_identifier: str  # human-readable label for the report
    repo_full_name: str
    pr_number: int
    github_token: str
    raw_code: str  # only for mode == "raw_code"
    raw_filename: str
    max_files: int
    hunks: list[Hunk]
    skipped_files: list[str]
    outcomes: Annotated[list[ChunkReviewOutcome], operator.add]
    report: ReviewReport


class CheckerInput(TypedDict):
    hunk: Hunk
    category: str


def ingest_node(state: GraphState) -> dict:
    if state["mode"] == "raw_code":
        # the pasted snippet IS the context -- no file to fetch, no risk
        # triage over multiple files, no surrounding-function expansion
        hunk = hunk_from_raw_code(state.get("raw_filename") or "pasted_code.py", state["raw_code"])
        return {"hunks": [hunk], "skipped_files": []}

    files = fetch_pr_files(state["repo_full_name"], state["pr_number"], state["github_token"])
    ranked = rank_files_by_risk(files)
    max_files = state.get("max_files") or MAX_FILES_DEFAULT
    kept, skipped = ranked[:max_files], ranked[max_files:]

    hunks: list[Hunk] = []
    for f in kept:
        for raw_hunk in parse_patch_to_hunks(f.filename, f.patch or ""):
            hunks.append(build_context(raw_hunk, f.full_content))

    return {"hunks": hunks, "skipped_files": [f.filename for f in skipped]}


def fan_out_to_checkers(state: GraphState):
    if not state["hunks"]:
        return "aggregate"
    return [
        Send("checker_node", {"hunk": hunk, "category": category})
        for hunk in state["hunks"]
        for category in CATEGORIES
    ]


def checker_node(state: CheckerInput) -> dict:
    cache = ReviewCache()
    outcome = review_chunk(state["hunk"], state["category"], cache=cache)
    cache.save()
    return {"outcomes": [outcome]}


def aggregate_node(state: GraphState) -> dict:
    outcomes = state.get("outcomes", [])
    all_findings = [f for o in outcomes for f in o.findings]
    deduped = aggregate_findings(all_findings)

    failed_chunks = sum(1 for o in outcomes if o.status == "failed")
    files_reviewed = len({o.hunk.file for o in outcomes})
    # dedupe identical error strings -- the same root cause (e.g. a bad API
    # key) usually fails every chunk with the same message
    failure_reasons = list(dict.fromkeys(o.error for o in outcomes if o.status == "failed" and o.error))

    report = ReviewReport(
        pr_identifier=state["pr_identifier"],
        findings=deduped,
        files_reviewed=files_reviewed,
        files_skipped=len(state.get("skipped_files", [])),
        skipped_files=state.get("skipped_files", []),
        failed_chunks=failed_chunks,
        failure_reasons=failure_reasons,
    )
    return {"report": report}


def build_graph():
    graph = StateGraph(GraphState)
    graph.add_node("ingest", ingest_node)
    graph.add_node("checker_node", checker_node)
    graph.add_node("aggregate", aggregate_node)

    graph.set_entry_point("ingest")
    graph.add_conditional_edges("ingest", fan_out_to_checkers, ["checker_node", "aggregate"])
    graph.add_edge("checker_node", "aggregate")
    graph.add_edge("aggregate", END)

    return graph.compile()


def review_pr(repo_full_name: str, pr_number: int, github_token: str, max_files: int = MAX_FILES_DEFAULT) -> ReviewReport:
    app = build_graph()
    final_state = app.invoke(
        {
            "mode": "github_pr",
            "pr_identifier": f"{repo_full_name}#{pr_number}",
            "repo_full_name": repo_full_name,
            "pr_number": pr_number,
            "github_token": github_token,
            "max_files": max_files,
        }
    )
    return final_state["report"]


def review_raw_code(code: str, filename: str = "pasted_code.py") -> ReviewReport:
    """Review a pasted code snippet directly, through the same checker/
    aggregation/failure-handling pipeline as a PR."""
    app = build_graph()
    final_state = app.invoke(
        {
            "mode": "raw_code",
            "pr_identifier": f"pasted:{filename}",
            "raw_code": code,
            "raw_filename": filename,
        }
    )
    return final_state["report"]
