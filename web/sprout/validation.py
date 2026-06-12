"""Request-input guards shared by the routes."""
from __future__ import annotations

from typing import Any

from . import config


def clean_input(raw: Any) -> str:
    """Validate and bound free-text input (guards against oversized payloads)."""
    if not isinstance(raw, str):
        raise ValueError("expected a string")
    text = raw.strip()
    if not text:
        raise ValueError("input is empty")
    if len(text) > config.MAX_INPUT_CHARS:
        raise ValueError(f"input too long (max {config.MAX_INPUT_CHARS} chars)")
    return text


def as_float(value: Any, default: float) -> float:
    """Coerce a value to float, falling back to default on bad input."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
