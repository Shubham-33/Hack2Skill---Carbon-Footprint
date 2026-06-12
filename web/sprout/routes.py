"""HTTP routes, grouped on a Flask blueprint."""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, make_response, render_template, request

from . import config
from .estimates import MODE_CONFIG
from .ledger import ledger_append, ledger_state
from .llm import analyze
from .validation import as_float, clean_input

bp = Blueprint("sprout", __name__)

_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<text y=".9em" font-size="90">🌱</text></svg>'
)


def _error(message: str, status: int) -> Response:
    """Uniform JSON error envelope."""
    resp = jsonify({"ok": False, "error": message})
    resp.status_code = status
    return resp


@bp.route("/")
def index() -> Response:
    """Serve the single-page app with a short cache window."""
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@bp.route("/healthz")
def healthz() -> Response:
    """Liveness probe."""
    return jsonify({"ok": True, "build": config.BUILD_ID})


@bp.route("/favicon.ico")
def favicon() -> Response:
    """Inline 🌱 favicon so browsers don't log a 404 for the missing icon."""
    resp = Response(_FAVICON_SVG, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@bp.route("/api/analyze", methods=["POST"])
def api_analyze() -> Response:
    """Answer a question. 'mode' is an optional routing hint; otherwise Sprout auto-routes."""
    payload = request.get_json(silent=True) or {}
    try:
        text = clean_input(payload.get("input"))
    except ValueError as e:
        return _error(str(e), 400)
    hint = payload.get("mode")
    hint = hint if hint in MODE_CONFIG else None
    return jsonify(analyze(text, hint))


@bp.route("/api/plan", methods=["POST"])
def api_plan() -> Response:
    """Savings plan: 'state' reads the running total; 'commit' banks an action."""
    payload = request.get_json(silent=True) or {}
    try:
        plan = clean_input(payload.get("plan"))
    except ValueError as e:
        return _error(str(e), 400)
    if payload.get("action") == "commit":
        label = (payload.get("label") or "Saving").strip()[:80] or "Saving"
        kg = as_float(payload.get("kg_year"), 0.0)
        inr = as_float(payload.get("inr_year"), 0.0)
        ledger_append(plan, label, kg, inr)
    return jsonify(ledger_state(plan))
