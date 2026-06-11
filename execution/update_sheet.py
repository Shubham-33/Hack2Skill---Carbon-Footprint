"""Write/append values to a Google Sheet.

Usage:
    # Overwrite a range:
    python execution/update_sheet.py --sheet-id <ID> --range "Sheet1!A1" \
        --values '[["Date","kg CO2e"],["2026-06-11","12.4"]]'

    # Append rows after the last row of a range:
    python execution/update_sheet.py --sheet-id <ID> --range "Sheet1!A1" \
        --values '[["2026-06-12","9.1"]]' --append

--values is a JSON 2D array.
"""
from __future__ import annotations

import argparse
import json

from _common import fail, notify_slack, ok
from sheets_client import get_service


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sheet-id", required=True)
    p.add_argument("--range", required=True, dest="rng")
    p.add_argument("--values", required=True, help="JSON 2D array of cell values")
    p.add_argument("--append", action="store_true", help="Append instead of overwrite")
    args = p.parse_args()

    try:
        values = json.loads(args.values)
        if not isinstance(values, list) or not all(isinstance(r, list) for r in values):
            raise ValueError("--values must be a JSON 2D array, e.g. [[\"a\",\"b\"]]")
    except (json.JSONDecodeError, ValueError) as e:
        fail(f"Bad --values: {e}")

    body = {"values": values}
    try:
        sheets = get_service().spreadsheets().values()
        if args.append:
            resp = sheets.append(
                spreadsheetId=args.sheet_id,
                range=args.rng,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            ).execute()
            updated = resp.get("updates", {}).get("updatedCells", 0)
        else:
            resp = sheets.update(
                spreadsheetId=args.sheet_id,
                range=args.rng,
                valueInputOption="USER_ENTERED",
                body=body,
            ).execute()
            updated = resp.get("updatedCells", 0)
    except Exception as e:  # noqa: BLE001
        fail(f"Sheet update failed: {e}", sheet_id=args.sheet_id, range=args.rng)

    notify_slack(f":bar_chart: Updated sheet `{args.sheet_id}` ({updated} cells)")
    ok(updated_cells=updated, range=args.rng, appended=args.append)


if __name__ == "__main__":
    main()
