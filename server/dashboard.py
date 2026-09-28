"""Logged-in dashboard: manage your Groq key, and two manual review
actions (paste code, review a PR by number). The PR review uses the
logged-in user's own GitHub OAuth token (from login), not an installation
token -- so it reflects the user's own access, separate from the automatic
webhook-triggered path in webhook.py which acts as the installation."""
from __future__ import annotations

import time

from flask import Blueprint, render_template_string, request, session

from reviewer.graph import review_pr, review_raw_code

from .auth import login_required
from .db import get_session
from .models import User

dashboard_bp = Blueprint("dashboard", __name__)

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
  .account { display: flex; justify-content: space-between; align-items: center;
             background: #eef2ff; border-radius: 8px; padding: 0.75rem 1rem; margin: 1rem 0; }
  form { background: #f4f4f7; border-radius: 8px; padding: 1rem 1.25rem; margin: 1.5rem 0; }
  label { display: block; font-weight: 600; margin-top: 0.75rem; margin-bottom: 0.25rem; }
  input[type=text], input[type=password] { width: 100%; padding: 0.4rem; box-sizing: border-box; }
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
  .success { background: #dcfce7; border: 1px solid #16a34a; border-radius: 8px;
             padding: 0.75rem 1rem; color: #14532d; }
  textarea { width: 100%; box-sizing: border-box; font-family: monospace;
             font-size: 0.85rem; padding: 0.5rem; }
  .divider { text-align: center; color: #999; font-size: 0.85rem; margin: 0.5rem 0; }
</style>
</head>
<body>
  <h1>Agentic Code Reviewer</h1>
  <p class="subtitle">LangGraph + Groq &middot; your account, your Groq key, your reviews</p>

  <div class="account">
    <span>Signed in as <strong>{{ user.github_login }}</strong></span>
    <a href="/logout">Log out</a>
  </div>

  <form method="post">
    <input type="hidden" name="action" value="save_groq_key">
    <label for="groq_key">Groq API key {% if user.groq_key %}(set &mdash; paste a new one to replace it){% endif %}</label>
    <input type="password" name="groq_key" id="groq_key" placeholder="gsk_...">
    <button type="submit">Save Key</button>
  </form>

  {% if groq_key_saved_message %}
    <div class="success">{{ groq_key_saved_message }}</div>
  {% endif %}

  <p class="divider">&mdash; reviews &mdash;</p>

  <form method="post">
    <input type="hidden" name="action" value="review_pr">
    <label for="repo_full_name">Repo (owner/repo)</label>
    <input type="text" name="repo_full_name" id="repo_full_name" placeholder="e.g. pallets/flask" value="{{ repo_full_name or '' }}">

    <label for="pr_number">PR number</label>
    <input type="text" name="pr_number" id="pr_number" placeholder="e.g. 123" value="{{ pr_number or '' }}">

    <button type="submit">Review PR</button>
  </form>

  <p class="divider">&mdash; or &mdash;</p>

  <form method="post">
    <input type="hidden" name="action" value="review_paste">
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


@dashboard_bp.route("/dashboard", methods=["GET", "POST"])
@login_required
def index():
    db = get_session()
    try:
        user = db.get(User, session["user_id"])

        report = None
        error = None
        elapsed = None
        groq_key_saved_message = None
        repo_full_name = ""
        pr_number = ""
        raw_code = ""
        raw_filename = "snippet.py"

        if request.method == "POST":
            action = request.form.get("action")

            if action == "save_groq_key":
                new_key = request.form.get("groq_key", "").strip()
                if new_key:
                    user.groq_key = new_key
                    db.commit()
                    groq_key_saved_message = "Groq key saved."
                else:
                    error = "Enter a Groq API key."

            elif action == "review_paste":
                raw_code = request.form.get("raw_code", "")
                raw_filename = request.form.get("raw_filename", "").strip() or "snippet.py"
                if not user.groq_key:
                    error = "Add your Groq API key first."
                elif not raw_code.strip():
                    error = "Paste some code first."
                else:
                    try:
                        start = time.time()
                        report = review_raw_code(raw_code, user.groq_key, raw_filename)
                        elapsed = round(time.time() - start, 1)
                    except Exception as exc:  # noqa: BLE001 - show the error in the UI
                        error = str(exc)

            elif action == "review_pr":
                repo_full_name = request.form.get("repo_full_name", "").strip()
                pr_number = request.form.get("pr_number", "").strip()
                if not user.groq_key:
                    error = "Add your Groq API key first."
                elif not user.oauth_token:
                    error = "Missing your GitHub access token -- try logging out and back in."
                elif not repo_full_name or not pr_number:
                    error = "Enter both a repo (owner/repo) and a PR number."
                else:
                    try:
                        start = time.time()
                        report = review_pr(repo_full_name, int(pr_number), user.oauth_token, user.groq_key)
                        elapsed = round(time.time() - start, 1)
                    except Exception as exc:  # noqa: BLE001 - show the error in the UI
                        error = str(exc)

        return render_template_string(
            PAGE_TEMPLATE,
            user=user,
            report=report,
            error=error,
            elapsed=elapsed,
            groq_key_saved_message=groq_key_saved_message,
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            raw_code=raw_code,
            raw_filename=raw_filename,
        )
    finally:
        db.close()
