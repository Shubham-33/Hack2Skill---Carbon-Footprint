"""Sprout — your carbon + money second opinion.

Ask anything in one box; a single NVIDIA call classifies it and answers with specific,
money-grounded output. Six checks:

  • savings  — a bill / monthly spend → ranked actions with ₹ + kg saved/yr + payback
  • trip     — a journey → travel options ranked by carbon, cost and time
  • claim    — an "eco-friendly" marketing claim → legit / greenwashing verdict + why
  • shop     — an order / receipt / cart → footprint + cheaper-greener swaps
  • worth    — "is solar / an EV / a heat pump worth it?" → personalised payback
  • lookup   — "what's the footprint of X?" → a number + a relatable comparison

Commit a money-saving action and it's banked in a shared plan (Google Sheet), so the
"₹/year you're on track to save" compounds — that's the reason to come back.

LLM: NVIDIA NIM (OpenAI-compatible REST). Google services: Sheets (ledger), plus
Gmail + Calendar via client-side URL-spec (no OAuth).

Every path has a deterministic offline fallback, so a network/LLM hiccup never breaks
the demo (and tests run without a key).
"""
from __future__ import annotations

import gzip
import json
import os
import re
from pathlib import Path
from typing import Any, Final

import requests
from flask import Flask, Response, jsonify, make_response, render_template, request

try:  # python-dotenv is a dev convenience; its absence in prod is fine
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NVIDIA_API_KEY: Final[str] = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_MODEL: Final[str] = os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
NVIDIA_URL: Final[str] = "https://integrate.api.nvidia.com/v1/chat/completions"

SHEET_ID: Final[str] = os.environ.get("SPROUT_SHEET_ID", "")
MAX_INPUT_CHARS: Final[int] = int(os.environ.get("MAX_INPUT_CHARS", "600"))

# kg CO2e per km — public averages, used by the offline trip fallback.
TRIP_FACTORS: Final[list[tuple[str, float, float, str]]] = [
    # (mode, kg/km, ₹/km, note)
    ("Cycle", 0.0, 0.0, "Zero emissions, free, good for short hops"),
    ("Train", 0.04, 1.2, "Low carbon and usually cheapest for distance"),
    ("Bus", 0.10, 1.5, "Low carbon, flexible routes"),
    ("Car", 0.17, 8.0, "Convenient but the priciest per km"),
]

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24  # cache static assets 1 day

# Cache-busts /static on every deploy (file mtime → new ?v= → browser refetches).
BUILD_ID: Final[str] = str(int(Path(__file__).stat().st_mtime))

# In-process savings ledger, used when no Google Sheet is configured.
_MEMORY_LEDGER: dict[str, list[dict[str, Any]]] = {}


@app.context_processor
def inject_build_id() -> dict[str, str]:
    """Expose BUILD_ID to templates for cache-busting static asset URLs."""
    return {"build_id": BUILD_ID}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Any:
    """Parse JSON from an LLM reply, tolerating ```json fences and stray prose."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return json.loads(cleaned[start : end + 1])


def _find_money(text: str) -> float:
    """Pull the first rupee-ish amount from text (e.g. '₹3200', 'rs 3,200'); else 0."""
    match = re.search(r"(?:₹|rs\.?\s*)?(\d[\d,]*)", text.lower())
    if not match:
        return 0.0
    return float(match.group(1).replace(",", ""))


def _first_number(text: str) -> float | None:
    """First standalone number in text, or None."""
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# Offline fallbacks (deterministic; safety net + test path)
# ---------------------------------------------------------------------------

def offline_savings(text: str) -> dict[str, Any]:
    """Generic-but-structured savings list when the LLM is unavailable."""
    actions = [
        {"action": "Set AC to 24°C instead of 18°C", "saves_inr_year": 3600,
         "saves_kg_year": 210, "effort": "easy", "payback": "immediate"},
        {"action": "Switch your 5 most-used bulbs to LED", "saves_inr_year": 900,
         "saves_kg_year": 60, "effort": "easy", "payback": "~2 months"},
        {"action": "Add a smart power strip to cut standby draw", "saves_inr_year": 1200,
         "saves_kg_year": 80, "effort": "medium", "payback": "~3 months"},
    ]
    return {
        "summary": f"Spotted ₹{sum(a['saves_inr_year'] for a in actions)}/yr in easy savings.",
        "monthly_spend_inr": _find_money(text),
        "annual_kg": sum(a["saves_kg_year"] for a in actions),
        "actions": actions,
    }


def offline_trip(text: str) -> dict[str, Any]:
    """Estimate travel options for a trip using built-in per-km factors."""
    dist = _first_number(text) or 10.0
    options = [
        {
            "mode": mode,
            "kg": round(kg * dist, 1),
            "cost_inr": round(cost * dist),
            "time": f"~{round(dist / 20, 1)} h" if mode != "Cycle" else f"~{round(dist / 12, 1)} h",
            "note": note,
        }
        for mode, kg, cost, note in TRIP_FACTORS
    ]
    best = min(options, key=lambda o: (o["kg"], o["cost_inr"]))["mode"]
    return {"from": "Start", "to": "Destination", "distance_km": dist, "options": options, "best": best}


def offline_claim(text: str) -> dict[str, Any]:
    """Cautious default verdict when the LLM is unavailable."""
    return {
        "claim": text[:120],
        "verdict": "mixed",
        "confidence": 0.5,
        "reasons": [
            "The claim lacks a named third-party certification.",
            "No lifecycle data is given to back it up.",
        ],
        "tip": "Look for a specific certification (Energy Star, FSC, etc.) and real numbers.",
    }


def offline_shop(text: str) -> dict[str, Any]:
    """Generic order breakdown with greener swaps when the LLM is unavailable."""
    items = [
        {"item": "Highest-impact item in your order", "kg": 3.2,
         "swap": "Pick a local or less-packaged alternative", "saves_kg": 1.1},
        {"item": "A packaged / imported item", "kg": 1.5,
         "swap": "Buy in bulk to cut packaging", "saves_kg": 0.4},
    ]
    return {
        "summary": f"About {round(sum(i['kg'] for i in items), 1)} kg CO₂e in this order.",
        "total_kg": round(sum(i["kg"] for i in items), 1),
        "items": items,
        "total_saves_kg": round(sum(i["saves_kg"] for i in items), 1),
    }


def offline_worth(text: str) -> dict[str, Any]:
    """Generic payback estimate when the LLM is unavailable."""
    return {
        "item": "This upgrade",
        "upfront_inr": 120000,
        "saves_inr_year": 24000,
        "saves_kg_year": 1500,
        "payback_years": 5.0,
        "verdict": "borderline",
        "note": "Worth it if you'll keep it 5+ years; check for local subsidies that shorten payback.",
    }


def offline_lookup(text: str) -> dict[str, Any]:
    """Rough footprint figure when the LLM is unavailable."""
    return {
        "thing": text[:60],
        "kg": 5.0,
        "unit": "per item",
        "equivalent": "≈ 29 km driven in a petrol car",
        "context": "A rough average — give a specific quantity for a sharper number.",
    }


# Ordered keyword routing for the offline path (the LLM classifies when available).
_CLASSIFY_RULES: Final[list[tuple[str, tuple[str, ...]]]] = [
    ("worth", ("worth", "solar", " ev", "electric vehicle", "heat pump", "induction")),
    ("shop", ("receipt", "order", "cart", "grocery", "bought")),
    ("claim", ("greenwash", "eco-friendly", "sustainable", "carbon neutral", "claim")),
    ("savings", ("bill", "electricity", "spend", "saving")),
    ("trip", (" to ", "travel", "commute", "flight", "train", "drive")),
]


def classify_offline(text: str) -> str:
    """Pick a mode from keywords when the LLM can't classify; default to lookup."""
    lowered = text.lower()
    for mode, keywords in _CLASSIFY_RULES:
        if any(k in lowered for k in keywords):
            return mode
    return "lookup"


# ---------------------------------------------------------------------------
# NVIDIA NIM (OpenAI-compatible) — one call per question
# ---------------------------------------------------------------------------

def nvidia_chat(system: str, user: str) -> str:
    """Single chat completion against NVIDIA NIM. Raises on any non-2xx/timeout."""
    resp = requests.post(
        NVIDIA_URL,
        headers={"Authorization": f"Bearer {NVIDIA_API_KEY}", "Accept": "application/json"},
        json={
            "model": NVIDIA_MODEL,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
            "max_tokens": 900,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# mode → (required result key, offline fallback). The LLM (or classify_offline) picks
# the mode; the required key validates the LLM returned the right shape.
MODE_CONFIG: Final[dict[str, dict[str, Any]]] = {
    "savings": {"required": "actions", "offline": offline_savings},
    "trip": {"required": "options", "offline": offline_trip},
    "claim": {"required": "verdict", "offline": offline_claim},
    "shop": {"required": "items", "offline": offline_shop},
    "worth": {"required": "payback_years", "offline": offline_worth},
    "lookup": {"required": "kg", "offline": offline_lookup},
}

UNIFIED_SYSTEM: Final[str] = (
    "You are Sprout, a carbon + money assistant. Classify the user's question into exactly "
    "ONE mode and answer it. Return ONLY JSON: {\"mode\": one of "
    "[savings,trip,claim,shop,worth,lookup], \"result\": {...}} where result matches the "
    "chosen mode's schema:\n"
    "- savings (lower a bill/spending): {summary, monthly_spend_inr, annual_kg, "
    "actions:[{action, saves_inr_year, saves_kg_year, effort:easy|medium|hard, payback}]} "
    "— 3-5 specific actions ranked by money saved.\n"
    "- trip (how to travel A→B): {from, to, distance_km, "
    "options:[{mode, kg, cost_inr, time, note}], best}.\n"
    "- claim (is an eco-claim real): {claim, verdict:legit|mixed|greenwashing, confidence, "
    "reasons:[...], tip}.\n"
    "- shop (footprint of an order/receipt/cart): {summary, total_kg, "
    "items:[{item, kg, swap, saves_kg}], total_saves_kg}.\n"
    "- worth (is solar/EV/heat pump/etc worth it): {item, upfront_inr, saves_inr_year, "
    "saves_kg_year, payback_years, verdict:'worth it'|borderline|'not yet', note}.\n"
    "- lookup (quick footprint of X): {thing, kg, unit, equivalent, context}.\n"
    "If the user gives a Preferred mode, use it. Money in INR. Be specific and realistic; "
    "never give vague advice."
)


def _route_offline(text: str, hint: str | None) -> dict[str, Any]:
    """Build an offline envelope, honouring an explicit hint or classifying by keyword."""
    mode = hint if hint in MODE_CONFIG else classify_offline(text)
    return {"mode": mode, "result": MODE_CONFIG[mode]["offline"](text), "source": "offline"}


def analyze(text: str, hint: str | None = None) -> dict[str, Any]:
    """Classify + answer via one NVIDIA call, falling back to deterministic offline output.

    Returns an envelope: {"mode": str, "result": {...}, "source": "nvidia"|"offline"}.
    """
    if not NVIDIA_API_KEY:
        return _route_offline(text, hint)
    user = f"Preferred mode: {hint}\n\n{text}" if hint else text
    try:
        data = _extract_json(nvidia_chat(UNIFIED_SYSTEM, user))
        mode = data["mode"]
        if mode not in MODE_CONFIG:
            raise ValueError(f"bad mode: {mode}")
        result = data["result"]
        if MODE_CONFIG[mode]["required"] not in result:
            raise KeyError(MODE_CONFIG[mode]["required"])
        return {"mode": mode, "result": result, "source": "nvidia"}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return _route_offline(text, hint)


# ---------------------------------------------------------------------------
# Savings ledger — Google Sheet when configured, in-memory otherwise
# ---------------------------------------------------------------------------

def sheets_enabled() -> bool:
    """True when a Sheet is configured and service-account creds are present."""
    return bool(SHEET_ID) and bool(
        os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT")
        or os.path.exists(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "credentials.json"))
    )


def _sheet_session():  # pragma: no cover - thin google-auth wrapper, mocked in tests
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    blob = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT")
    if blob:
        creds = service_account.Credentials.from_service_account_info(json.loads(blob), scopes=scopes)
    else:
        path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "credentials.json")
        creds = service_account.Credentials.from_service_account_file(path, scopes=scopes)
    return AuthorizedSession(creds)


def ledger_append(plan: str, action: str, kg_year: float, inr_year: float) -> None:
    """Bank a committed savings action for a plan (shared code)."""
    if sheets_enabled():
        try:
            session = _sheet_session()
            session.post(
                f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/Plan!A1:D1:append",
                params={"valueInputOption": "USER_ENTERED"},
                json={"values": [[plan, action, kg_year, inr_year]]},
                timeout=15,
            )
            return
        except requests.RequestException:
            pass  # degrade to memory so the demo never breaks
    _MEMORY_LEDGER.setdefault(plan, []).append(
        {"action": action, "kg": kg_year, "inr": inr_year}
    )


def ledger_state(plan: str) -> dict[str, Any]:
    """Aggregate a plan: committed actions, total ₹/yr and kg/yr on track to save."""
    rows: list[dict[str, Any]] = []
    if sheets_enabled():
        try:
            session = _sheet_session()
            resp = session.get(
                f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/Plan!A2:D",
                timeout=15,
            )
            for r in resp.json().get("values", []):
                if len(r) >= 4 and r[0] == plan:
                    rows.append({"action": r[1], "kg": float(r[2]), "inr": float(r[3])})
        except (requests.RequestException, ValueError, KeyError):
            rows = _MEMORY_LEDGER.get(plan, [])
    else:
        rows = _MEMORY_LEDGER.get(plan, [])

    return {
        "plan": plan,
        "actions": [r["action"] for r in rows],
        "count": len(rows),
        "total_kg_year": round(sum(r["kg"] for r in rows), 1),
        "total_inr_year": round(sum(r["inr"] for r in rows)),
        "trees": round(sum(r["kg"] for r in rows) / 21, 1),
        "backend": "sheets" if sheets_enabled() else "memory",
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def clean_input(raw: Any) -> str:
    """Validate and bound free-text input (guards against oversized payloads)."""
    if not isinstance(raw, str):
        raise ValueError("expected a string")
    text = raw.strip()
    if not text:
        raise ValueError("input is empty")
    if len(text) > MAX_INPUT_CHARS:
        raise ValueError(f"input too long (max {MAX_INPUT_CHARS} chars)")
    return text


def _as_float(value: Any, default: float) -> float:
    """Coerce a value to float, falling back to default on bad input."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _error(message: str, status: int) -> Response:
    resp = jsonify({"ok": False, "error": message})
    resp.status_code = status
    return resp


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index() -> Response:
    """Serve the single-page app with a short cache window."""
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@app.route("/healthz")
def healthz() -> Response:
    """Liveness probe."""
    return jsonify({"ok": True, "build": BUILD_ID})


@app.route("/api/analyze", methods=["POST"])
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


@app.route("/api/plan", methods=["POST"])
def api_plan() -> Response:
    """Savings plan: 'state' reads the running total; 'commit' banks an action."""
    payload = request.get_json(silent=True) or {}
    try:
        plan = clean_input(payload.get("plan"))
    except ValueError as e:
        return _error(str(e), 400)
    if payload.get("action") == "commit":
        label = (payload.get("label") or "Saving").strip()[:80] or "Saving"
        kg = _as_float(payload.get("kg_year"), 0.0)
        inr = _as_float(payload.get("inr_year"), 0.0)
        ledger_append(plan, label, kg, inr)
    return jsonify(ledger_state(plan))


# ---------------------------------------------------------------------------
# Efficiency middleware
# ---------------------------------------------------------------------------

@app.after_request
def gzip_response(response: Response) -> Response:
    """Gzip eligible text responses (stdlib only) to cut bytes on the wire."""
    accept = request.headers.get("Accept-Encoding") or ""
    if (
        response.direct_passthrough
        or not (200 <= response.status_code < 300)
        or response.headers.get("Content-Encoding")
        or "gzip" not in accept
        or (response.content_length is not None and response.content_length < 500)
    ):
        return response
    data = gzip.compress(response.get_data(), compresslevel=6)
    response.set_data(data)
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = str(len(data))
    response.headers["Vary"] = "Accept-Encoding"
    return response


if __name__ == "__main__":  # pragma: no cover
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=False)
