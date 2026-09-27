# Agentic Code Reviewer

An AI code reviewer that reviews PR diffs and produces structured findings
(security, error handling, missing tests, logic bugs) — plus an automated
evaluation harness that mines real historical bugs from an open-source
project's git history and measures how many of them the reviewer actually
catches.

Built with **LangGraph** for orchestration and **Groq** (free-tier,
open-source models) for inference.

## Why this exists

Most "AI code review" demos show a model reading a diff and producing
plausible-looking comments, with no way to tell if those comments are
actually catching real bugs. This project instead:

1. Mines real (bug-introducing commit → later bug-fixing commit) pairs from
   an OSS repo's history using a simplified **SZZ algorithm**.
2. Runs the reviewer against each bug-introducing commit's diff, exactly as
   if it were reviewing that PR before the bug was ever found.
3. Automatically checks whether the reviewer's findings land on the actual
   lines that were later fixed — giving a real, reproducible recall/precision
   number instead of "it looked good on the examples I tried."

## Architecture

```
PR diff (GitHub API, or a local git commit for evaluation)
      │
      ▼
[Ingest]              pull changed files, split into per-file diff hunks
      │
      ▼
[Triage]               rank files by risk (auth/payment/security paths first);
                        a size cap on huge PRs drops the lowest-risk files,
                        reported explicitly rather than silently dropped
      │
      ▼
[Context builder]       attach the enclosing function (via tree-sitter for
                        Python; a line-window fallback otherwise) to each hunk
      │
      ▼
[Checkers]  (LangGraph, fanned out per hunk × category via the Send API)
              - security
              - error_handling
              - missing_test
              - logic
            each call retries on rate limits/5xx (Groq's free tier has
            request limits) and is cached by content hash so unchanged
            hunks aren't re-reviewed on re-runs
      │
      ▼
[Aggregate]            dedupe overlapping findings within the same
                        file+category, rank by severity/confidence
      │
      ▼
[Output]               structured JSON + a Markdown summary
```

Structured finding schema (`src/reviewer/schema.py`):

```python
class Finding(BaseModel):
    file: str
    line_start: int
    line_end: int
    category: Literal["security", "error_handling", "missing_test", "logic"]
    severity: Literal["blocker", "warning", "nit"]
    confidence: float
    summary: str
    detail: str
    suggested_fix: str | None
```

## Evaluation methodology (`src/mining`, `src/eval`)

`src/mining/szz.py` implements a simplified SZZ:

1. Find "fixing" commits by commit-message heuristics (`fix`, `fixes #N`, …).
2. For each, find which lines the fix actually removes/changes.
3. `git blame` the pre-fix version of the file to find which earlier commit
   last touched those lines — that's the **bug-introducing commit**.
4. Locate exactly where that content lands in the *introducing* commit's own
   diff (via content matching, not just blame's line numbers, since other
   commits in between shift line numbers) — this is the ground-truth
   location the reviewer needs to flag.

Known simplifications (documented honestly, not hidden): no cross-file
rename tracking, no filtering of purely cosmetic changes, commit-message
keyword matching instead of full issue-tracker cross-referencing, and a
size cap that skips sweeping rewrite commits (they're not realistic "PRs"
and also produce spurious content-match line ranges).

`src/eval/run_eval.py` then:
- Runs the reviewer on every mined bug-introducing commit.
- Matches findings to the known bug location (file + line-range overlap,
  ±3 lines of tolerance).
- Computes recall (bugs caught / total), precision (findings that matched a
  known bug / total findings raised), and average findings per case.
- Runs two baselines for comparison: a plain `ruff` lint pass, and a naive
  single-prompt LLM review with no chunking/context/per-category checkers —
  to quantify what the architecture actually adds.

**Caveat, stated plainly**: precision here undercounts true positives,
since a finding that doesn't match the one *known* mined bug in a commit
might still be a real bug we simply haven't mined evidence for. Treat the
precision number as a lower bound, and spot-check a sample of "extra"
findings before trusting it fully.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY and GITHUB_TOKEN
```

- `GROQ_API_KEY`: free key from https://console.groq.com
- `GITHUB_TOKEN`: a GitHub personal access token with `repo:read`, used to
  pull PR diffs and (for public repos) is optional for cloning during mining

## Usage

**Review a live PR:**
```bash
python -m reviewer.cli owner/repo 123
```

**Mine a bug dataset from a repo's history:**
```bash
python -m mining.mine_repo https://github.com/pallets/flask.git \
    --clone-dir data/repos/flask --out data/mined/flask.json --max-fix-commits 400
```

**Run the evaluation:**
```bash
python -m eval.run_eval --dataset data/mined/flask.json \
    --repo data/repos/flask --out data/eval/flask_results.json
```

**Run tests:**
```bash
pytest
```

## Current status

- [x] Diff ingestion, tree-sitter context building, size-aware triage
- [x] LangGraph checker pipeline (security / error_handling / missing_test / logic)
- [x] Failure handling: per-node retry with backoff (incl. 429 rate limits),
      chunk-level isolation, size cap with explicit skip reporting, content-hash caching
- [x] SZZ-style mining pipeline, validated against a synthetic repo with a
      known planted bug, then run against real Flask history:
      **107 bug-fix pairs mined** from Flask's last 400 fix-like commits
      (`data/mined/flask.json`)
- [x] Evaluation harness + ruff/naive-LLM baselines (code complete)
- [x] End-to-end verified against a real mined bug (`d718ecf6`, Flask's
      `provide_automatic_options` bug): reviewer ran with 0 failed chunks and
      raised 4 findings, two of which correctly overlap the real bug location
- [x] Minimal local demo UI (`src/webui`) to visually run/inspect reviews
- [ ] Full evaluation run across all 107 mined bugs (recall/precision numbers)
      — the pipeline is proven correct on a real case; running the whole
      dataset just takes longer due to Groq free-tier rate limits (see below)

### Notes on getting this actually working

A few non-obvious issues had to be fixed to get real LLM calls working
reliably, worth knowing if you extend this:

- **Groq's free tier enforces a tokens-per-minute (TPM) cap as low as 8000**
  for larger models — a global rate limiter (`reviewer/llm.py`) paces every
  call process-wide, since LangGraph's concurrent fan-out otherwise floods it
  instantly even for a single small review.
- **A change at class scope inside a huge class (e.g. Flask's main `App`
  class) made the tree-sitter context-builder expand to nearly the whole
  file** (1400+ lines, ~14K tokens) because it picked the smallest enclosing
  node, which was the entire class. Fixed with a max-size cap that falls
  back to the line-window instead (`chunking.py`).
- **Forced tool-calling (`with_structured_output`'s default method)
  unreliably fails on this model specifically when the correct answer is "no
  findings"** — it either refuses to call the tool or hallucinates a
  nonexistent one. Switched to `json_mode`, which has no such failure mode,
  at the cost of having to spell out the JSON schema in the prompt manually.
