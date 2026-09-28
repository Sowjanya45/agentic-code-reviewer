"""Minimal demo UI for the agentic code reviewer.

Not part of the core architecture (the reviewer is a library, a CLI, and a
GitHub Action) -- this is a thin Flask wrapper for two ways to try it
interactively: review a live GitHub PR by number, or paste a code snippet
directly.

Run with:
    python -m webui.app
"""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from flask import Flask, render_template_string, request

load_dotenv()

from reviewer.graph import review_pr, review_raw_code  # noqa: E402

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
  input[type=text] { width: 100%; padding: 0.4rem; box-sizing: border-box; }
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
  .error { background: #fee2e2; border: 1px solid #dc2626; border-radius: 8px;
           padding: 1rem; color: #7f1d1d; }
  textarea { width: 100%; box-sizing: border-box; font-family: monospace;
             font-size: 0.85rem; padding: 0.5rem; }
  .divider { text-align: center; color: #999; font-size: 0.85rem; margin: 0.5rem 0; }
</style>
</head>
<body>
  <h1>Agentic Code Reviewer</h1>
  <p class="subtitle">LangGraph + Groq &middot; review a live PR, or paste a snippet directly</p>

  <form method="post">
    <input type="hidden" name="mode" value="pr">
    <label for="repo_full_name">Repo (owner/repo)</label>
    <input type="text" name="repo_full_name" id="repo_full_name" placeholder="e.g. pallets/flask" value="{{ repo_full_name or '' }}">

    <label for="pr_number">PR number</label>
    <input type="text" name="pr_number" id="pr_number" placeholder="e.g. 123" value="{{ pr_number or '' }}">

    <button type="submit">Review PR</button>
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
    report = None
    error = None
    elapsed = None
    repo_full_name = ""
    pr_number = ""
    raw_code = ""
    raw_filename = "snippet.py"

    if request.method == "POST":
        mode = request.form.get("mode", "pr")

        groq_api_key = os.environ.get("GROQ_API_KEY")

        if mode == "paste":
            raw_code = request.form.get("raw_code", "")
            raw_filename = request.form.get("raw_filename", "").strip() or "snippet.py"
            if not raw_code.strip():
                error = "Paste some code first."
            elif not groq_api_key:
                error = "GROQ_API_KEY is not set in .env."
            else:
                try:
                    start = time.time()
                    report = review_raw_code(raw_code, groq_api_key, raw_filename)
                    elapsed = round(time.time() - start, 1)
                except Exception as exc:  # noqa: BLE001 - show the error in the UI, don't crash the demo
                    error = str(exc)
        else:
            repo_full_name = request.form.get("repo_full_name", "").strip()
            pr_number = request.form.get("pr_number", "").strip()
            github_token = os.environ.get("GITHUB_TOKEN")

            if not repo_full_name or not pr_number:
                error = "Enter both a repo (owner/repo) and a PR number."
            elif not github_token:
                error = "GITHUB_TOKEN is not set in .env -- required to fetch a live PR."
            elif not groq_api_key:
                error = "GROQ_API_KEY is not set in .env."
            else:
                try:
                    start = time.time()
                    report = review_pr(repo_full_name, int(pr_number), github_token, groq_api_key)
                    elapsed = round(time.time() - start, 1)
                except Exception as exc:  # noqa: BLE001 - show the error in the UI, don't crash the demo
                    error = str(exc)

    return render_template_string(
        PAGE_TEMPLATE,
        report=report,
        error=error,
        elapsed=elapsed,
        repo_full_name=repo_full_name,
        pr_number=pr_number,
        raw_code=raw_code,
        raw_filename=raw_filename,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
