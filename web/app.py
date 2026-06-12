"""Sprout — your carbon + money second opinion.

Ask anything in one box; a single NVIDIA call classifies it and answers with specific,
money-grounded output across six checks (savings, trip, claim, shop, worth, lookup).
Commit a saving and it banks into a shared plan (Google Sheet); the ₹/yr on track to
save compounds — the reason to come back.

This module is the entry point: it assembles the Flask app from the `sprout` package
(config · estimates · llm · ledger · validation · routes · middleware). Run with
`gunicorn app:app` (see Procfile). Every path has a deterministic offline fallback, so
a network/LLM hiccup never breaks the demo.
"""
from __future__ import annotations

import os

from flask import Flask

from sprout import middleware
from sprout.routes import bp


def create_app() -> Flask:
    """Build and configure the Sprout Flask application."""
    app = Flask(__name__)
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24  # cache static assets 1 day
    app.register_blueprint(bp)
    middleware.register(app)
    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=False)
