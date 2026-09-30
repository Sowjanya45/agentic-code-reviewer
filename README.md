# Agentic Code Reviewer

An AI code reviewer that produces structured findings (security, error
handling, missing tests, logic bugs) from a code change — via a live GitHub
PR, a comment on that PR ("agentic-review"), or a pasted snippet.

Built with **LangGraph** for orchestration and **Groq** (free-tier,
open-source models) for inference.

## Ways to use it

1. **Hosted multi-tenant server** (`server/`) — install a GitHub App once on
   your account, log in, add your own Groq key, and it works on *every*
   repo the installation covers — including repos added later. Comment
   anything containing "agentic-review" on any PR in any of those repos
   and it reviews and replies automatically; or use the logged-in
   dashboard to manually review a PR by number or paste a snippet. This is
   the "real product" version — see **The hosted server** section below.
2. **Comment-triggered GitHub Action** (`.github/workflows/pr-review-bot.yml`)
   — the lightweight, single-repo alternative: comment "agentic-review" on
   a PR in *this* repo and a GitHub Action reviews it. No server, no
   GitHub App, no login — just add one repo secret. Doesn't extend to
   other repos without copying the workflow file into each one (that's
   exactly what the hosted server exists to avoid).
3. **Local web UI** (`webui/`) — a small local Flask app, single-user,
   driven by a local `.env` — review a live PR by number, or paste a
   snippet directly.
4. **CLI** — `python -m reviewer.cli owner/repo 123` for a one-off review
   from the terminal.

All four go through the exact same reviewer pipeline (`src/reviewer/`).

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
When someone comments on a PR and the comment contains "agentic-review"
(case-insensitive), it:

1. Checks the comment is actually on a PR (not a plain issue), and that the
   commenter isn't the bot itself (so its own reply doesn't retrigger it
   in a loop).
2. Checks out the repo, installs dependencies.
3. Runs `scripts/pr_comment_bot.py`, which reviews the PR via the same
   `review_pr()` used by the CLI/web UI, and posts the findings back as a
   PR comment via the GitHub API.

**Setup**: add `GROQ_API_KEY` as a repository secret (Settings → Secrets and
variables → Actions). No GitHub token needs adding — the Action uses the
repo's automatically-provided `secrets.GITHUB_TOKEN`, scoped to read the PR
and post comments.

## The hosted server (`server/`)

A GitHub App + Flask server, meant to be deployed once (e.g. on Render) and
then work across every repo it's installed on, for every user who installs
it — not just this one repo.

```
Browser                        Server (Flask)                    GitHub
   │  Install the App  ────────────┼─────────────────────────────────▶│
   │                               │◀── installation + OAuth code ────│
   │                        /github/callback: exchange code for a    │
   │                        user access token, create/update User,   │
   │                        link installation_id to that user        │
   │                               │                                  │
   │  Paste Groq key on dashboard  │                                  │
   │        (encrypted at rest) ───▶  stored in Postgres/SQLite      │
   │                               │                                  │
(later) comment "agentic-review"   │                                  │
on ANY installed repo              │◀──── issue_comment webhook ──────│
                                    │                                  │
                              /webhook: verify signature, look up     │
                              the installation's user + Groq key,     │
                              mint a short-lived installation token,  │
                              run review_pr(), post the findings  ────▶ comment
```

Two GitHub tokens are in play, both landing on the same `review_pr()`:
- **Dashboard's manual "Review PR" button** uses the logged-in user's own
  OAuth token (from login) — reflects their own GitHub access.
- **Automatic webhook-triggered review** uses a short-lived installation
  token, minted on demand via `server/github_app_auth.py` (PyGithub's
  built-in GitHub App auth) — works across every repo the installation
  covers, no personal token involved.

Server pieces: `server/models.py` (SQLAlchemy `User`/`Installation`,
Groq key and OAuth token stored via `server/crypto.py`'s Fernet
encryption — never plaintext in the DB), `server/auth.py` ("Sign in with
GitHub" OAuth login), `server/dashboard.py` (the two manual actions),
`server/webhook.py` (the automatic path — runs the review in a background
thread since it can exceed GitHub's ~10s webhook response window),
`server/app.py` (wires it all together; entry point for
`gunicorn server.app:app`).

### Setting it up

1. **Create the GitHub App** at github.com/settings/apps/new:
   - Callback URL / Webhook URL: point at placeholders for now (e.g.
     `https://example.com/github/callback`) — you'll come back and fix
     these to your real Render URL after the first deploy.
   - Enable **"Request user authorization (OAuth) during installation."**
   - Permissions: **Pull requests** (Read & Write), **Issues** (Read),
     **Contents** (Read). Subscribe to webhook events: **Issue comment**,
     **Installation**.
   - "Where can this GitHub App be installed": start with **"Only on this
     account."**
   - Generate a **private key** (downloads a `.pem`) and a **client
     secret**; note the **App ID** and **Client ID**.
2. **Deploy to Render**: new Web Service from this repo (start command
   `gunicorn server.app:app` with `PYTHONPATH=src`, per the `Procfile`),
   add the free Postgres add-on (sets `DATABASE_URL` automatically), and
   set the remaining env vars from `.env.example`'s hosted-server section
   (`GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY` — paste the `.pem` contents
   — `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_CLIENT_SECRET`,
   `GITHUB_WEBHOOK_SECRET`, `ENCRYPTION_KEY`, `FLASK_SECRET_KEY`).
3. Go back to the GitHub App settings and swap the placeholder Callback/
   Webhook URLs for the real `https://<your-app>.onrender.com/...` ones.
4. Install the App on your account, log in, paste a Groq key on the
   dashboard, then test: comment "agentic-review" on a PR in any repo the
   app covers.

**Local dev**: omit `DATABASE_URL` to use a local SQLite file
(`server_dev.db`) automatically. Run with
`PYTHONPATH=src FLASK_SECRET_KEY=dev ENCRYPTION_KEY=... python -m server.app`.
The webhook path needs a real GitHub App to test against; the OAuth
login and dashboard paths work fully locally once `GITHUB_APP_CLIENT_ID`/
`_SECRET` are set (register a dev instance of the App with
`http://127.0.0.1:5000/github/callback` as its callback URL).

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
- [x] Per-user Groq API keys (the LLM client/rate-limiter are keyed per
      key, not a single global) -- required for the multi-tenant server
- [x] Pasted-code review mode, reusing the same pipeline
- [x] Comment-triggered GitHub Action (single-repo) + PR-comment posting
- [x] Local web UI for live PR review and pasted-code review
- [x] Hosted multi-tenant server: GitHub App OAuth login, encrypted-at-rest
      per-user Groq keys, a dashboard with manual review actions, and a
      webhook handler for automatic comment-triggered reviews across every
      installed repo -- unit-tested (44 tests) with the webhook signature
      verification, trigger detection, and installation-token flow all
      exercised against real signed payloads
- [x] End-to-end verified against real Groq API calls on the CLI/Action/
      webui path (see commit history for the specific bugs found and fixed
      getting there: a token-budget blowup on class-scope changes, and
      unreliable forced tool-calling on empty results, fixed by switching
      to `json_mode`)
- [ ] The hosted server's webhook path is unit-tested but not yet verified
      against a real deployed GitHub App + Render instance (needs the
      manual GitHub App creation + Render deployment steps above, which
      only the repo owner can do)
