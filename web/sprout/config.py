"""Runtime configuration — all environment-derived settings live here.

Values that tests override (keys, sheet id, limits) are plain module attributes so
they can be monkeypatched; truly constant values are annotated Final.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Final

try:  # python-dotenv is a dev convenience; its absence in prod is fine
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# --- NVIDIA NIM (OpenAI-compatible) ---
NVIDIA_API_KEY: str = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_MODEL: str = os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
NVIDIA_URL: Final[str] = "https://integrate.api.nvidia.com/v1/chat/completions"

# --- Google Sheets ledger ---
SHEET_ID: str = os.environ.get("SPROUT_SHEET_ID", "")

# --- App ---
MAX_INPUT_CHARS: int = int(os.environ.get("MAX_INPUT_CHARS", "600"))

# Cache-busts /static on every deploy (file mtime → new ?v= → browser refetches).
BUILD_ID: Final[str] = str(int(Path(__file__).stat().st_mtime))

# kg CO2e and ₹ per km — public averages, used by the offline trip fallback.
TRIP_FACTORS: Final[list[tuple[str, float, float, str]]] = [
    ("Cycle", 0.0, 0.0, "Zero emissions, free, good for short hops"),
    ("Train", 0.04, 1.2, "Low carbon and usually cheapest for distance"),
    ("Bus", 0.10, 1.5, "Low carbon, flexible routes"),
    ("Car", 0.17, 8.0, "Convenient but the priciest per km"),
]
