"""Shared helpers for execution-layer scripts.

Keep this thin: env loading, Slack notification, and a tiny result envelope so
every tool prints structured JSON the orchestrator can parse.
"""
from __future__ import annotations

import json
import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional at runtime
    pass


def env(key: str, default: str | None = None, required: bool = False) -> str | None:
    val = os.environ.get(key, default)
    if required and not val:
        fail(f"Missing required env var: {key}")
    return val


def emit(ok: bool, **fields) -> None:
    """Print a single-line JSON result and exit. The orchestrator reads stdout."""
    print(json.dumps({"ok": ok, **fields}))
    sys.exit(0 if ok else 1)


def ok(**fields) -> None:
    emit(True, **fields)


def fail(message: str, **fields) -> None:
    emit(False, error=message, **fields)


def notify_slack(text: str) -> None:
    """Best-effort Slack stream. Never raises — notification must not break a tool."""
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    try:
        import requests

        requests.post(url, json={"text": text}, timeout=5)
    except Exception:
        pass
