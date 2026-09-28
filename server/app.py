"""Flask app factory wiring the auth, dashboard, and webhook blueprints
together. Entry point for Render via `gunicorn server.app:app`.

This is the hosted, multi-tenant product: install the GitHub App once,
log in, add a Groq key, and every repo the installation covers works --
including repos added later. It's separate from `webui/app.py`, which
stays as a single-user local tool driven by a local `.env` file.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask, redirect, url_for

load_dotenv()

from .auth import auth_bp  # noqa: E402
from .dashboard import dashboard_bp  # noqa: E402
from .db import init_db  # noqa: E402
from .webhook import webhook_bp  # noqa: E402


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ["FLASK_SECRET_KEY"]

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(webhook_bp)

    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    init_db()
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
