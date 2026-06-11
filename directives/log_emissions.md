# Directive: Log Emissions

**Goal:** Given an activity (e.g. "drove 40 km in a petrol car"), estimate its CO2e, append a row to the tracking Google Sheet, and confirm to the user.

## Inputs
- `activity` — one of the known activity keys (see `execution/estimate_emissions.py` builtin table) or a Climatiq `activity_id`.
- `amount` — numeric quantity.
- `unit` — unit matching the activity (kWh, km, kg, l).
- `sheet_id` — target Google Sheet ID. Default lives in `.env` if you add `EMISSIONS_SHEET_ID`.
- Optional `notify_email` — address to send a confirmation to.

## Tools (Layer 3)
- `execution/estimate_emissions.py` — activity → kg CO2e (Climatiq, with offline fallback).
- `execution/update_sheet.py --append` — append the row.
- `execution/send_email.py` — optional confirmation.

## Steps
1. Validate inputs. If `activity`/`unit` aren't in the builtin table and no Climatiq key is set, ask the user to pick a known activity.
2. Run `estimate_emissions.py --activity <a> --amount <n> --unit <u>`. Read `co2e_kg` from the JSON.
3. Append `[date, activity, amount, unit, co2e_kg, source]` to the sheet via `update_sheet.py --append --range "Log!A1"`.
4. If `notify_email` given, send a one-line confirmation with the CO2e figure.
5. Report the kg CO2e and the row that was written.

## Outputs
- One appended row in the tracking sheet (the deliverable).
- Optional confirmation email.
- A short summary back to the caller.

## Edge Cases / Learnings
- `estimate_emissions.py` never hard-fails on API trouble — it degrades to builtin factors. Note the `source` field so the user knows which was used.
- Builtin factors are rough public averages — fine for a demo, not for compliance reporting. Flag this if the user asks about accuracy.
- Dates: pass an explicit ISO date in the row; don't rely on sheet auto-formatting.
