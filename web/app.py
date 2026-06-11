"""Sprout — a daily climate-habit coach.

Describe your day in one sentence; Sprout itemises your carbon footprint, shows
relatable equivalences and a gauge against a sustainable daily target, then gives
ONE personalised, money-saving swap. A shared "Grove" (Google Sheet) tracks the
streak and compounding savings so people come back.

LLM: NVIDIA NIM (OpenAI-compatible REST). Google services: Sheets (ledger),
Gmail + Calendar (client-side URL-spec dispatch — no OAuth).

The app NEVER hard-depends on the network: if the NVIDIA call or the Sheet is
unavailable, deterministic fallbacks keep every endpoint working (good for a
cold-click demo and for tests).
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

try:  # python-dotenv is dev-only convenience; absent in prod image is fine
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NVIDIA_API_KEY: Final[str] = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_MODEL: Final[str] = os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")
NVIDIA_URL: Final[str] = "https://integrate.api.nvidia.com/v1/chat/completions"

SHEET_ID: Final[str] = os.environ.get("SPROUT_SHEET_ID", "")
MAX_INPUT_CHARS: Final[int] = int(os.environ.get("MAX_INPUT_CHARS", "600"))

# Sustainable per-person daily budget (~6 kg/day ≈ 2.0 t/yr, the 1.5°C target).
DAILY_TARGET_KG: Final[float] = 6.0

# kg CO2e per unit — rough public averages for the offline fallback estimator.
EMISSION_FACTORS: Final[dict[str, tuple[float, str, str]]] = {
    # keyword: (kg per unit, unit-regex group meaning, category)
    "car": (0.17, "km", "transport"),
    "drove": (0.17, "km", "transport"),
    "drive": (0.17, "km", "transport"),
    "uber": (0.17, "km", "transport"),
    "taxi": (0.17, "km", "transport"),
    "bus": (0.10, "km", "transport"),
    "train": (0.04, "km", "transport"),
    "flight": (0.16, "km", "transport"),
    "flew": (0.16, "km", "transport"),
    "beef": (6.0, "meal", "food"),
    "burger": (5.0, "meal", "food"),
    "steak": (6.5, "meal", "food"),
    "lamb": (5.8, "meal", "food"),
    "chicken": (1.8, "meal", "food"),
    "ac": (0.6, "hour", "energy"),
    "heater": (0.7, "hour", "energy"),
    "electricity": (0.42, "kwh", "energy"),
}

# Per-category swap templates for the offline fallback: (tip, kg_saved, money_inr).
SWAP_TEMPLATES: Final[dict[str, tuple[str, float, int]]] = {
    "transport": ("Take the metro or carpool for one trip tomorrow", 3.2, 120),
    "food": ("Swap one beef meal for chicken or veg this week", 4.8, 90),
    "energy": ("Set the AC 2°C higher for 3 hours", 1.4, 60),
    "general": ("Pick one short car trip to replace with a walk or cycle", 2.0, 80),
}

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24  # cache static assets 1 day

# Cache-busts /static on every deploy (file mtime → new ?v= → browser refetches).
BUILD_ID: Final[str] = str(int(Path(__file__).stat().st_mtime))

# In-process Grove store, used when no Google Sheet is configured.
_MEMORY_LEDGER: dict[str, list[dict[str, Any]]] = {}


@app.context_processor
def inject_build_id() -> dict[str, str]:
    """Expose BUILD_ID to templates for cache-busting static asset URLs."""
    return {"build_id": BUILD_ID}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def gauge_status(total_kg: float) -> dict[str, Any]:
    """Classify a daily total against the sustainable target."""
    ratio = total_kg / DAILY_TARGET_KG
    if ratio <= 0.75:
        level, label = "green", "Under your climate budget — nice."
    elif ratio <= 1.25:
        level, label = "amber", "Around the sustainable daily target."
    else:
        level, label = "red", "Over budget — one swap goes a long way."
    return {"level": level, "label": label, "ratio": round(ratio, 2), "target_kg": DAILY_TARGET_KG}


def equivalence(total_kg: float) -> str:
    """Translate kg CO2e into a relatable, human-scale comparison."""
    km = total_kg / 0.17
    charges = total_kg / 0.005
    if km >= 1:
        return f"≈ {km:.0f} km driven in a petrol car"
    return f"≈ {charges:.0f} smartphone charges"


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


def offline_estimate(text: str) -> dict[str, Any]:
    """Deterministic footprint estimate used when the LLM is unavailable."""
    lowered = text.lower()
    by_category: dict[str, dict[str, Any]] = {}
    for keyword, (factor, unit, category) in EMISSION_FACTORS.items():
        if not re.search(rf"\b{re.escape(keyword)}\b", lowered):
            continue
        # Meals are counted once per mention; distances/energy read an adjacent number.
        amount = 1.0 if unit == "meal" else _first_number_near(lowered, keyword)
        kg = round(factor * amount, 2)
        candidate = {"label": keyword, "category": category, "amount": amount, "unit": unit, "kg": kg}
        # Keep only the biggest contributor per category (avoids beef+burger double counting).
        if category not in by_category or kg > by_category[category]["kg"]:
            by_category[category] = candidate
    items = list(by_category.values())
    # Nothing recognised → assume an average day so the UI still shows something.
    if not items:
        items.append(
            {"label": "daily activity", "category": "general", "amount": 1, "unit": "day", "kg": 5.0}
        )
    total = round(sum(i["kg"] for i in items), 2)
    top_category = max(items, key=lambda i: i["kg"])["category"]
    tip, kg_saved, money = SWAP_TEMPLATES.get(top_category, SWAP_TEMPLATES["general"])
    return {
        "items": items,
        "total_kg": total,
        "swap": {"tip": tip, "kg_saved": kg_saved, "money_inr": money, "category": top_category},
        "summary": f"Your day adds up to about {total} kg CO₂e.",
        "source": "offline",
    }


def _first_number_near(text: str, keyword: str) -> float:
    """Find a number adjacent to a keyword (e.g. '20 km' near 'drove'); default 1."""
    idx = text.find(keyword)
    window = text[max(0, idx - 15) : idx + 15]
    match = re.search(r"(\d+(?:\.\d+)?)", window)
    return float(match.group(1)) if match else 1.0


# ---------------------------------------------------------------------------
# NVIDIA NIM (OpenAI-compatible) — one call per user action
# ---------------------------------------------------------------------------

def nvidia_chat(system: str, user: str) -> str:
    """Single chat completion against NVIDIA NIM. Raises on any non-2xx/timeout."""
    resp = requests.post(
        NVIDIA_URL,
        headers={"Authorization": f"Bearer {NVIDIA_API_KEY}", "Accept": "application/json"},
        json={
            "model": NVIDIA_MODEL,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.3,
            "max_tokens": 700,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


_ANALYZE_SYSTEM: Final[str] = (
    "You are a carbon-footprint estimator. Given a person's plain-English description "
    "of their day, return ONLY JSON with this shape: "
    '{"items":[{"label":str,"category":"transport|food|energy|other","amount":number,'
    '"unit":str,"kg":number}],"total_kg":number,'
    '"swap":{"tip":str,"kg_saved":number,"money_inr":number,"category":str},'
    '"summary":str}. The swap must target the largest emission source, be specific and '
    "doable, and include realistic INR money saved. Use kg CO2e."
)


def analyze_day(text: str) -> dict[str, Any]:
    """LLM footprint analysis with a deterministic offline fallback."""
    if not NVIDIA_API_KEY:
        return offline_estimate(text)
    try:
        raw = nvidia_chat(_ANALYZE_SYSTEM, text)
        data = _extract_json(raw)
        # Minimal shape validation; KeyError/TypeError falls through to offline.
        _ = data["items"], data["total_kg"], data["swap"]["tip"]
        data["source"] = "nvidia"
        return data
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return offline_estimate(text)


_WHATIF_SYSTEM: Final[str] = (
    "You estimate the ANNUAL impact of a lifestyle change. Return ONLY JSON: "
    '{"annual_kg":number,"annual_money_inr":number,"trees":number,"note":str}. '
    "trees = annual_kg / 21 (a tree absorbs ~21 kg CO2/yr), rounded to 1 decimal. "
    "Be realistic and encouraging in note."
)


def whatif(change: str) -> dict[str, Any]:
    """Project the annual payoff of a hypothetical change; offline heuristic fallback."""
    if NVIDIA_API_KEY:
        try:
            data = _extract_json(nvidia_chat(_WHATIF_SYSTEM, change))
            _ = data["annual_kg"], data["annual_money_inr"]
            data.setdefault("trees", round(data["annual_kg"] / 21, 1))
            data["source"] = "nvidia"
            return data
        except (requests.RequestException, ValueError, KeyError, TypeError):
            pass
    # Heuristic: scale a per-change weekly saving across the year.
    annual_kg = 180.0
    return {
        "annual_kg": annual_kg,
        "annual_money_inr": 6200,
        "trees": round(annual_kg / 21, 1),
        "note": "A consistent weekly change compounds into real yearly savings.",
        "source": "offline",
    }


# ---------------------------------------------------------------------------
# Grove ledger — Google Sheet when configured, in-memory otherwise
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


def ledger_append(grove: str, member: str, kg_saved: float, money_inr: float) -> None:
    """Append one completed-swap row to the Grove ledger."""
    if sheets_enabled():
        try:
            session = _sheet_session()
            session.post(
                f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/Grove!A1:D1:append",
                params={"valueInputOption": "USER_ENTERED"},
                json={"values": [[grove, member, kg_saved, money_inr]]},
                timeout=15,
            )
            return
        except requests.RequestException:
            pass  # degrade to memory so the demo never breaks
    _MEMORY_LEDGER.setdefault(grove, []).append(
        {"member": member, "kg": kg_saved, "money": money_inr}
    )


def ledger_state(grove: str) -> dict[str, Any]:
    """Aggregate a Grove's forest: members, total kg + money saved, streak proxy."""
    rows: list[dict[str, Any]] = []
    if sheets_enabled():
        try:
            session = _sheet_session()
            resp = session.get(
                f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/Grove!A2:D",
                timeout=15,
            )
            for r in resp.json().get("values", []):
                if len(r) >= 4 and r[0] == grove:
                    rows.append({"member": r[1], "kg": float(r[2]), "money": float(r[3])})
        except (requests.RequestException, ValueError, KeyError):
            rows = _MEMORY_LEDGER.get(grove, [])
    else:
        rows = _MEMORY_LEDGER.get(grove, [])

    members = sorted({r["member"] for r in rows})
    total_kg = round(sum(r["kg"] for r in rows), 2)
    total_money = round(sum(r["money"] for r in rows), 2)
    goal_kg = 50.0 * max(len(members), 1)
    return {
        "grove": grove,
        "members": members,
        "swaps": len(rows),
        "total_kg": total_kg,
        "total_money_inr": total_money,
        "trees": round(total_kg / 21, 1),
        "goal_kg": goal_kg,
        "goal_pct": min(100, round(total_kg / goal_kg * 100)),
        "backend": "sheets" if sheets_enabled() else "memory",
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def clean_input(raw: Any) -> str:
    """Validate and bound free-text input (security guard against oversized payloads)."""
    if not isinstance(raw, str):
        raise ValueError("expected a string")
    text = raw.strip()
    if not text:
        raise ValueError("input is empty")
    if len(text) > MAX_INPUT_CHARS:
        raise ValueError(f"input too long (max {MAX_INPUT_CHARS} chars)")
    return text


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


@app.route("/api/log", methods=["POST"])
def api_log() -> Response:
    """Analyse a described day into an itemised footprint + one personalised swap."""
    payload = request.get_json(silent=True) or {}
    try:
        text = clean_input(payload.get("activity"))
    except ValueError as e:
        return _error(str(e), 400)
    result = analyze_day(text)
    result["gauge"] = gauge_status(result["total_kg"])
    result["equivalence"] = equivalence(result["total_kg"])
    return jsonify(result)


@app.route("/api/whatif", methods=["POST"])
def api_whatif() -> Response:
    """Project the annual ₹ + kg payoff of a hypothetical lifestyle change."""
    payload = request.get_json(silent=True) or {}
    try:
        change = clean_input(payload.get("change"))
    except ValueError as e:
        return _error(str(e), 400)
    return jsonify(whatif(change))


@app.route("/api/grove", methods=["POST"])
def api_grove() -> Response:
    """Grove actions: 'state' reads the forest; 'log' records a completed swap."""
    payload = request.get_json(silent=True) or {}
    try:
        grove = clean_input(payload.get("grove"))
    except ValueError as e:
        return _error(str(e), 400)
    action = payload.get("action", "state")
    if action == "log":
        member = (payload.get("member") or "you").strip()[:40] or "you"
        kg = _as_float(payload.get("kg_saved"), 0.0)
        money = _as_float(payload.get("money_inr"), 0.0)
        ledger_append(grove, member, kg, money)
    return jsonify(ledger_state(grove))


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
