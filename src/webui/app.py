"""Minimal demo UI for the agentic code reviewer.

Not part of the core architecture (the reviewer is a library + CLI) -- this
is a thin Flask wrapper so the pipeline can be demoed visually: pick a known
mined bug commit (or paste any commit SHA from the cloned repo) and see the
reviewer's structured findings, including whether it caught the known bug.

Run with:
    python -m webui.app
"""
from __future__ import annotations

import time
from pathlib import Path

import git
from dotenv import load_dotenv
from flask import Flask, render_template_string, request

load_dotenv()

from eval.matching import bug_is_caught  # noqa: E402
from mining.dataset import load_dataset  # noqa: E402
from reviewer.graph import review_local_commit, review_raw_code  # noqa: E402

REPO_PATH = Path("data/repos/flask")
DATASET_PATH = Path("data/mined/flask.json")

app = Flask(__name__)

PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Agentic Code Reviewer</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, Segoe UI, sans-serif; max-width: 900px;
         margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }
  h1 { font-size: 1.4rem; }
  .subtitle { color: #666; margin-top: -0.5rem; }
  form { background: #f4f4f7; border-radius: 8px; padding: 1rem 1.25rem; margin: 1.5rem 0; }
  label { display: block; font-weight: 600; margin-top: 0.75rem; margin-bottom: 0.25rem; }
  select, input[type=text] { width: 100%; padding: 0.4rem; box-sizing: border-box; }
  button { margin-top: 1rem; padding: 0.5rem 1.2rem; background: #4f46e5; color: white;
           border: none; border-radius: 6px; font-weight: 600; cursor: pointer; }
  .meta { color: #555; font-size: 0.9rem; margin-bottom: 1rem; }
  .finding { border: 1px solid #ddd; border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 0.75rem; }
  .finding.blocker { border-left: 5px solid #dc2626; }
  .finding.warning { border-left: 5px solid #d97706; }
  .finding.nit { border-left: 5px solid #9ca3af; }
  .badge { display: inline-block; font-size: 0.75rem; padding: 0.1rem 0.5rem;
           border-radius: 999px; background: #e5e7eb; margin-left: 0.4rem; }
  .loc { font-family: monospace; color: #555; font-size: 0.85rem; }
  .status-ok { color: #16a34a; font-weight: 600; }
  .status-miss { color: #b45309; font-weight: 600; }
  .error { background: #fee2e2; border: 1px solid #dc2626; border-radius: 8px;
           padding: 1rem; color: #7f1d1d; }
  textarea { width: 100%; box-sizing: border-box; font-family: monospace;
             font-size: 0.85rem; padding: 0.5rem; }
  .divider { text-align: center; color: #999; font-size: 0.85rem; margin: 0.5rem 0; }
</style>
</head>
<body>
  <h1>Agentic Code Reviewer</h1>
  <p class="subtitle">LangGraph + Groq &middot; evaluated against real mined bugs from Flask's history</p>

  <form method="post">
    <input type="hidden" name="mode" value="commit">
    <label for="bug_choice">Pick a known mined bug (Flask history)</label>
    <select name="bug_choice" id="bug_choice">
      <option value="">-- custom commit SHA below --</option>
      {% for b in known_bugs %}
        <option value="{{ b.bug_commit }}" {% if b.bug_commit == selected_sha %}selected{% endif %}>
          {{ b.bug_commit[:8] }} &middot; {{ b.file }} &middot; fixed by "{{ b.fix_summary }}"
        </option>
      {% endfor %}
    </select>

    <label for="commit_sha">...or paste any commit SHA</label>
    <input type="text" name="commit_sha" id="commit_sha" placeholder="e.g. 28d5a4d7..." value="{{ custom_sha or '' }}">

    <button type="submit">Run Review</button>
  </form>

  <p class="divider">&mdash; or &mdash;</p>

  <form method="post">
    <input type="hidden" name="mode" value="paste">
    <label for="raw_filename">Filename (for context only, e.g. language)</label>
    <input type="text" name="raw_filename" id="raw_filename" placeholder="snippet.py" value="{{ raw_filename or 'snippet.py' }}">

    <label for="raw_code">Paste code to review</label>
    <textarea name="raw_code" id="raw_code" rows="12" placeholder="def run_query(user_input):&#10;    return db.execute('SELECT * FROM users WHERE name = ' + user_input)">{{ raw_code or '' }}</textarea>

    <button type="submit">Review Pasted Code</button>
  </form>

  {% if error %}
    <div class="error"><strong>Error:</strong> {{ error }}</div>
  {% endif %}

  {% if report %}
    <div class="meta">
      Reviewed <strong>{{ report.files_reviewed }}</strong> file(s),
      skipped {{ report.files_skipped }}, {{ report.failed_chunks }} chunk(s) failed.
      Took {{ elapsed }}s.
      {% if bug %}
        &middot;
        {% if caught %}
          <span class="status-ok">&#10003; caught the known bug ({{ bug.file }}:{{ bug.line_start }}-{{ bug.line_end }})</span>
        {% else %}
          <span class="status-miss">&#10007; missed the known bug ({{ bug.file }}:{{ bug.line_start }}-{{ bug.line_end }})</span>
        {% endif %}
      {% endif %}
    </div>

    {% if report.failure_reasons %}
      <div class="error">
        <strong>{{ report.failed_chunks }} check(s) failed with:</strong>
        <ul>
          {% for reason in report.failure_reasons %}
            <li>{{ reason }}</li>
          {% endfor %}
        </ul>
      </div>
    {% endif %}

    {% if report.findings %}
      {% for f in report.findings %}
        <div class="finding {{ f.severity }}">
          <div><strong>[{{ f.category }}]</strong> {{ f.summary }}
            <span class="badge">{{ f.severity }}</span>
            <span class="badge">confidence {{ "%.2f"|format(f.confidence) }}</span>
          </div>
          <div class="loc">{{ f.file }}:{{ f.line_start }}-{{ f.line_end }}</div>
          <p>{{ f.detail }}</p>
          {% if f.suggested_fix %}<pre>{{ f.suggested_fix }}</pre>{% endif %}
        </div>
      {% endfor %}
    {% else %}
      <p>No findings.</p>
    {% endif %}
  {% endif %}
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    known_bugs = load_dataset(DATASET_PATH)[:15] if DATASET_PATH.exists() else []
    report = None
    error = None
    elapsed = None
    bug = None
    caught = None
    selected_sha = ""
    custom_sha = ""
    raw_code = ""
    raw_filename = "snippet.py"

    if request.method == "POST":
        mode = request.form.get("mode", "commit")

        if mode == "paste":
            raw_code = request.form.get("raw_code", "")
            raw_filename = request.form.get("raw_filename", "").strip() or "snippet.py"
            if not raw_code.strip():
                error = "Paste some code first."
            else:
                try:
                    start = time.time()
                    report = review_raw_code(raw_code, raw_filename)
                    elapsed = round(time.time() - start, 1)
                except Exception as exc:  # noqa: BLE001 - show the error in the UI, don't crash the demo
                    error = str(exc)
        else:
            selected_sha = request.form.get("bug_choice", "")
            custom_sha = request.form.get("commit_sha", "").strip()
            commit_sha = custom_sha or selected_sha

            if not commit_sha:
                error = "Pick a known bug or paste a commit SHA."
            else:
                try:
                    repo = git.Repo(REPO_PATH)
                    start = time.time()
                    report = review_local_commit(repo, commit_sha)
                    elapsed = round(time.time() - start, 1)
                    bug = next((b for b in known_bugs if b.bug_commit == commit_sha), None)
                    if bug:
                        caught = bug_is_caught(report.findings, bug)
                except Exception as exc:  # noqa: BLE001 - show the error in the UI, don't crash the demo
                    error = str(exc)

    return render_template_string(
        PAGE_TEMPLATE,
        known_bugs=known_bugs,
        report=report,
        error=error,
        elapsed=elapsed,
        bug=bug,
        caught=caught,
        selected_sha=selected_sha,
        custom_sha=custom_sha,
        raw_code=raw_code,
        raw_filename=raw_filename,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
