# Carbon Footprint

> ## 🌱 The hackathon app lives in **[`web/`](web/)** — see **[web/README.md](web/README.md)**.
> **Sprout** is a daily climate-habit coach (NVIDIA NIM + Google Sheets/Gmail/Calendar),
> deployed to Cloud Run. That's the PromptWars submission. The 3-layer scaffold below is
> the supporting automation system.

---

## 3-Layer Agent System

A directive-driven agent system that separates **intent** (Markdown SOPs) from
**decision-making** (the LLM orchestrator) from **execution** (deterministic
Python). See [CLAUDE.md](CLAUDE.md) for the full operating contract.

## Layout

```
CLAUDE.md / AGENTS.md / GEMINI.md   Agent instructions (mirrored)
directives/                          Layer 1 — SOPs in Markdown
  add_webhook.md                     How to add a new webhook
  log_emissions.md                   Estimate CO2e → append to sheet
execution/                           Layer 3 — deterministic tools
  _common.py                         env / JSON result / Slack helpers
  send_email.py                      SMTP send
  read_sheet.py  update_sheet.py     Google Sheets I/O
  sheets_client.py                   Shared Sheets auth
  estimate_emissions.py             Activity → kg CO2e (Climatiq + offline fallback)
  webhooks.json                      slug → directive + scoped tools
  modal_webhook.py                   Modal app exposing webhooks
.tmp/                                Intermediates (gitignored)
.env.example                         Copy to .env and fill in
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in your keys
```

## Try a tool (offline, no keys needed)

```bash
cd execution
python estimate_emissions.py --activity car_petrol --amount 40 --unit km
# -> {"ok": true, "co2e_kg": 6.8, "source": "builtin", ...}
```

## Run a directive (orchestrator path)

Tell your agent: *"Log emissions: 40 km in a petrol car, sheet `<ID>`."*
It reads [directives/log_emissions.md](directives/log_emissions.md) and calls the
execution scripts in order.

## Webhooks

To add one, see [directives/add_webhook.md](directives/add_webhook.md). Deploy with
`modal deploy execution/modal_webhook.py` (requires the `claude-orchestrator-secrets`
Modal secret).

## Notes

- Built-in emission factors are rough public averages — demo-grade, not for compliance.
- Use the latest capable Claude model (currently Opus 4.8) when building.
