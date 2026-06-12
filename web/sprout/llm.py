"""The NVIDIA NIM call and the unified classify-and-answer router.

`analyze()` makes ONE LLM call that both classifies the question into a mode and
returns that mode's structured result, validates the shape, and falls back to a
deterministic offline answer on any failure.
"""
from __future__ import annotations

import json
import re
from typing import Any

import requests

from . import config
from .estimates import MODE_CONFIG, classify_offline


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


def nvidia_chat(system: str, user: str) -> str:
    """Single chat completion against NVIDIA NIM. Raises on any non-2xx/timeout."""
    resp = requests.post(
        config.NVIDIA_URL,
        headers={"Authorization": f"Bearer {config.NVIDIA_API_KEY}", "Accept": "application/json"},
        json={
            "model": config.NVIDIA_MODEL,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
            "max_tokens": 900,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


UNIFIED_SYSTEM = (
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
    if not config.NVIDIA_API_KEY:
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
