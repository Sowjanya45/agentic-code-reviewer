# Agentic Code Reviewer

An AI code reviewer that produces structured findings (security, error
handling, missing tests, logic bugs) from a code change — via a live GitHub
PR, a comment on that PR ("please review this"), or a pasted snippet.

Built with **LangGraph** for orchestration and **Groq** (free-tier,
open-source models) for inference.

## Three ways to use it

1. **Comment-triggered PR review** — comment anything containing the word
   "review" (e.g. "can you please review this PR?") on a pull request in a
   repo with the included GitHub Action set up, and it reviews the PR and
   replies with its findings as a comment. No server or hosting needed —
   it runs entirely as a GitHub Action.
2. **Web UI** — a small local Flask app to review a live PR by number, or
   paste a code snippet directly, and see structured findings in the browser.
3. **CLI** — `python -m reviewer.cli owner/repo 123` for a one-off review
   from the terminal.

All three go through the exact same reviewer pipeline.

## Architecture

```
PR diff (GitHub API) or pasted code
      │
      ▼
[Ingest]              pull changed files, split into per-file diff hunks
                       (pasted code becomes one synthetic "addition" hunk)
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
[Output]               structured JSON + a Markdown summary (posted as a
                       PR comment, or rendered in the web UI)
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

## The comment-triggered GitHub Action

`.github/workflows/pr-review-bot.yml` listens for `issue_comment` events.
When someone comments on a PR and the comment contains the word "review"
(case-insensitive), it:

1. Checks the comment is actually on a PR (not a plain issue), and that the
   commenter isn't the bot itself (so its own reply, which also contains
   the word "review", doesn't retrigger it in a loop).
2. Checks out the repo, installs dependencies.
3. Runs `scripts/pr_comment_bot.py`, which reviews the PR via the same
   `review_pr()` used by the CLI/web UI, and posts the findings back as a
   PR comment via the GitHub API.

**Setup**: add `GROQ_API_KEY` as a repository secret (Settings → Secrets and
variables → Actions). No GitHub token needs adding — the Action uses the
repo's automatically-provided `secrets.GITHUB_TOKEN`, scoped to read the PR
and post comments.

## Failure handling

- **Per-node retry with backoff** on LLM/API errors, including a global
  rate limiter (Groq's free tier has a strict tokens-per-minute cap that
  the checker fan-out would otherwise blow through instantly).
- **Chunk-level isolation**: one failing check doesn't abort the review —
  partial results are returned along with the actual failure reason
  (surfaced in both the web UI and the PR comment), not hidden behind a
  silent "no findings."
- **Size-aware triage** for huge PRs, and a context-size cap so a change at
  class scope inside a large class doesn't expand to the whole file and
  blow the token budget.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env   # fill in GROQ_API_KEY and GITHUB_TOKEN
```

- `GROQ_API_KEY`: free key from https://console.groq.com
- `GITHUB_TOKEN`: a GitHub personal access token with `repo:read`, needed
  by the CLI/web UI to fetch a live PR's diff (the GitHub Action doesn't
  need this — it uses the repo's own token automatically)

## Usage

**Review a live PR (CLI):**
```bash
PYTHONPATH=src python -m reviewer.cli owner/repo 123
```

**Web UI** (review a PR by number, or paste code):
```bash
PYTHONPATH=src python -m webui.app
```
then open http://127.0.0.1:5000

**Tests:**
```bash
pytest
```

## Current status

- [x] Diff ingestion, tree-sitter context building, size-aware triage
- [x] LangGraph checker pipeline (security / error_handling / missing_test / logic)
- [x] Failure handling: per-node retry with backoff (incl. 429 rate limits),
      chunk-level isolation, size cap, content-hash caching, failure
      reasons surfaced instead of hidden
- [x] Pasted-code review mode, reusing the same pipeline
- [x] Comment-triggered GitHub Action + PR-comment posting
- [x] Web UI for live PR review and pasted-code review
- [x] End-to-end verified against real Groq API calls (see commit history
      for the specific bugs found and fixed getting there: a token-budget
      blowup on class-scope changes, and unreliable forced tool-calling on
      empty results, fixed by switching to `json_mode`)
