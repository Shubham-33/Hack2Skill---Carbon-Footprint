"""Deterministic offline estimates and keyword routing.

These run when the LLM is unavailable (no key, network error, bad response) so every
endpoint always returns a sane answer — the demo never dies, and tests need no network.
`MODE_CONFIG` is the registry the LLM router and the offline path both key off.
"""
from __future__ import annotations

import re
from typing import Any, Final

from . import config


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


def offline_savings(text: str) -> dict[str, Any]:
    """Generic-but-structured savings list when the LLM is unavailable."""
    actions: list[dict[str, Any]] = [
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
        for mode, kg, cost, note in config.TRIP_FACTORS
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
    items: list[dict[str, Any]] = [
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
