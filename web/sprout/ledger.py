"""The savings-plan ledger.

Banks committed actions to a Google Sheet when one is configured; otherwise keeps
them in memory. Both reads and writes degrade to memory on any Sheets error so the
demo never breaks.
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests

from . import config

# In-process ledger, used when no Google Sheet is configured (or as a fallback).
_MEMORY_LEDGER: dict[str, list[dict[str, Any]]] = {}


def sheets_enabled() -> bool:
    """True when a Sheet is configured and service-account creds are present."""
    return bool(config.SHEET_ID) and bool(
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
                f"https://sheets.googleapis.com/v4/spreadsheets/{config.SHEET_ID}/values/Plan!A1:D1:append",
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
                f"https://sheets.googleapis.com/v4/spreadsheets/{config.SHEET_ID}/values/Plan!A2:D",
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
