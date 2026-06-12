# 🌱 Sprout — *Your carbon + money second opinion.*

Ask anything in **one smart box** — a single NVIDIA call detects what you need and answers
with **specific, money-grounded output**. Six checks:

- **💰 Savings** — a bill / monthly spend → ranked actions with **₹ + kg saved/yr + payback**.
- **🚆 Trip** — a journey → travel options ranked by **carbon, cost and time**.
- **🛒 Shop** — an order / receipt / cart → footprint + **cheaper-greener swaps**.
- **⚖️ Worth it?** — solar / EV / heat pump → **personalised payback** in ₹, kg and years.
- **🔍 Eco-claim** — a marketing line → **legit / greenwashing** verdict and why.
- **📊 Footprint** — "what's the footprint of X?" → a number + a relatable comparison.

It **auto-detects** the check from what you type (or pick a chip). Commit a money-saving
action and it's banked in a shared **plan** (Google Sheet), so the "₹/year you're on track
to save" compounds — that's the reason to come back.

> Built for **PromptWars** · LLM by **NVIDIA NIM** · **Google** Sheets + Gmail + Calendar.

## The problem

People *want* a lower carbon footprint but trackers fail them: logging is a chore, guilt
repels, the advice is generic ("use less"), and there's no payoff. **Sprout flips it** —
near-zero effort in (paste what you already have), concrete value out (real ₹ saved, a
ranked decision, a verdict), tied to things you do regularly (bills, trips, purchases).

## How it helps — understand · reduce · act

| | How |
|---|---|
| **Understand** | Real inputs (a bill, a trip, a claim) turned into clear numbers — ₹, kg CO₂, payback, time. |
| **Reduce** | Specific, ranked actions and lower-carbon options — never vague advice. |
| **Act & track** | One tap **commits** an action to your plan (Google Sheet); **Calendar** reminder + **Gmail** plan summary keep you moving. |

## Architecture

```
Browser (semantic + ARIA, Tailwind CDN, vanilla JS — one smart input, 6 mode chips)
   │  POST /api/analyze {mode, input}   ·   POST /api/plan {plan, commit}
   ▼
Flask (app.py = create_app factory)  ── one NVIDIA NIM call per question
   │
   ├─ Google Sheet  → savings-plan ledger (₹/yr + kg/yr banked)   [server-side]
   └─ Gmail · Calendar · WhatsApp → plan summary + reminders        [client-side, no OAuth]
```

The backend is a small layered package — each module has one job:

```
app.py              create_app() factory; entry for `gunicorn app:app`
sprout/
  config.py         environment-derived settings
  estimates.py      deterministic offline fallbacks + keyword routing (LLM-free)
  llm.py            NVIDIA NIM call + the unified classify-and-answer router
  ledger.py         savings-plan store (Google Sheet, or in-memory)
  validation.py     request-input guards
  routes.py         HTTP endpoints (Flask blueprint)
  middleware.py     build-id injection + gzip
```

**Resilience:** every endpoint has a deterministic fallback. If NVIDIA or the Sheet is
unreachable, the app still returns a sane result — the demo never dies on stage.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env          # optional: add NVIDIA_API_KEY (works without it via fallback)
python app.py                 # http://localhost:5050
```

## Test & lint (100% coverage gate)

```bash
pytest          # 42 tests, branch coverage gate fails under 100%
ruff check app.py tests/
```

## Deploy to Cloud Run

```bash
cd web
./deploy.sh YOUR_GCP_PROJECT_ID nvapi-YOUR_NVIDIA_KEY
# Optional Sheets ledger:
SHEET_ID=<id> SA_FILE=service-account.json ./deploy.sh PROJECT nvapi-KEY
```

The script enables APIs, stores the key in **Secret Manager**, grants IAM, and deploys
with `--min-instances 1 --cpu-boost` (no cold starts). Always smoke-test after:

```bash
curl -s $URL/healthz
curl -sI --compressed $URL/ | grep -i content-encoding   # → gzip
```

## Google Sheets ledger (optional, ~5 min)

1. [console.cloud.google.com](https://console.cloud.google.com) → enable **Google Sheets API**.
2. Create a **service account**, download its JSON key.
3. Create a Sheet with a tab named **Plan**; share it with the service account's
   `client_email` (Editor).
4. Deploy with `SHEET_ID` + `SA_FILE` as above. Without these, Sprout uses an in-memory
   plan ledger (great for local demos; resets on restart).

## 90-second demo script

1. On **✨ Auto**, paste *"my electricity bill is ₹3,200/month with two ACs"* → **Ask**. Badge shows **Detected: Find savings**; NVIDIA returns ranked actions with ₹/yr + payback.
2. Open a plan (`home-2026`) → tap **Commit ✅** on two actions → the **₹/year counter grows**.
3. Paste *"Mumbai to Pune, 150 km"* → auto-detects **Trip**: *Train 2.3 kg / ₹500* vs *Drive 23 kg*.
4. Paste a grocery order → **Shop**: *2 kg beef = 12 kg → swap to lentils, save 10 kg*.
5. Ask *"is rooftop solar worth it?"* → **Worth it?**: payback ~7 yr, verdict + ₹/yr.
6. Paste a *"100% sustainable"* fast-fashion line → **Greenwashing 🚩** with reasons.
7. Back on the plan: **Add to Calendar 📅** / **Email my plan ✉️** / **Share 🔗** — prefilled Google/WhatsApp, no login. Close: *"one box, a real answer to whatever decision you're facing."*

## Judging-rubric map

| Parameter | Where |
|---|---|
| Problem Alignment | understand (real numbers) / reduce (ranked actions) / act (commit + remind) across 3 everyday jobs |
| Google Services | Sheets (plan ledger) · Gmail (plan email) · Calendar (reminders) — all load-bearing |
| Security | Secret Manager · input length caps · no PII · HTML-escaped output · `.gcloudignore` |
| Testing | `pytest` + `--cov-fail-under=100`, all network mocked (42 tests) |
| Efficiency | gzip middleware · Cache-Control · static caching · 1 LLM call/action · min-instances |
| Accessibility | skip link · semantic landmarks · ARIA live regions · focus rings · ⌘+Enter · AA contrast · reduced-motion |
| Code Quality | type hints · docstrings · named constants · ruff · section banners · GitHub Actions CI |

*Estimates use demo-grade public averages — not for compliance reporting.*
