"""Estimate CO2e for an activity.

Tries the Climatiq API if CLIMATIQ_API_KEY is set; otherwise falls back to a
small built-in emission-factor table so the tool always returns a number
(good enough for a hackathon demo / offline runs).

Usage:
    python execution/estimate_emissions.py --activity electricity --amount 100 --unit kWh
    python execution/estimate_emissions.py --activity car_petrol --amount 40 --unit km

Prints JSON: {"ok": true, "co2e_kg": 12.4, "source": "climatiq|builtin", ...}
"""
from __future__ import annotations

import argparse
import os

from _common import fail, ok

# kg CO2e per unit — rough public averages, for offline/demo fallback only.
BUILTIN_FACTORS = {
    ("electricity", "kwh"): 0.42,
    ("natural_gas", "kwh"): 0.18,
    ("car_petrol", "km"): 0.17,
    ("car_diesel", "km"): 0.16,
    ("car_ev", "km"): 0.05,
    ("bus", "km"): 0.10,
    ("train", "km"): 0.04,
    ("flight_short", "km"): 0.16,
    ("flight_long", "km"): 0.15,
    ("beef", "kg"): 27.0,
    ("chicken", "kg"): 6.9,
    ("water", "l"): 0.0003,
}


def from_climatiq(activity: str, amount: float, unit: str):
    import requests

    key = os.environ["CLIMATIQ_API_KEY"]
    # Caller passes a climatiq activity_id directly when using the API path.
    resp = requests.post(
        "https://api.climatiq.io/data/v1/estimate",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "emission_factor": {"activity_id": activity, "data_version": "^6"},
            "parameters": {"energy": amount, "energy_unit": unit},
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["co2e"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--activity", required=True)
    p.add_argument("--amount", required=True, type=float)
    p.add_argument("--unit", required=True)
    args = p.parse_args()

    if os.environ.get("CLIMATIQ_API_KEY"):
        try:
            co2e = from_climatiq(args.activity, args.amount, args.unit)
            ok(co2e_kg=round(co2e, 3), source="climatiq", activity=args.activity)
        except Exception as e:  # noqa: BLE001 — fall through to builtin
            # Don't fail the whole tool on API trouble; degrade gracefully.
            pass

    key = (args.activity.lower(), args.unit.lower())
    factor = BUILTIN_FACTORS.get(key)
    if factor is None:
        fail(
            f"No builtin factor for ({args.activity}, {args.unit}). "
            f"Known: {sorted(BUILTIN_FACTORS)}"
        )
    ok(
        co2e_kg=round(args.amount * factor, 3),
        source="builtin",
        activity=args.activity,
        factor=factor,
    )


if __name__ == "__main__":
    main()
