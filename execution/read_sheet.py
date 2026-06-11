"""Read a range from a Google Sheet.

Usage:
    python execution/read_sheet.py --sheet-id <ID> --range "Sheet1!A1:D20"

Prints JSON: {"ok": true, "values": [[...], ...], "rows": N}
"""
from __future__ import annotations

import argparse

from _common import fail, ok
from sheets_client import get_service


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sheet-id", required=True)
    p.add_argument("--range", required=True, dest="rng")
    args = p.parse_args()

    try:
        service = get_service()
        resp = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=args.sheet_id, range=args.rng)
            .execute()
        )
    except Exception as e:  # noqa: BLE001
        fail(f"Sheet read failed: {e}", sheet_id=args.sheet_id, range=args.rng)

    values = resp.get("values", [])
    ok(values=values, rows=len(values), range=args.rng)


if __name__ == "__main__":
    main()
