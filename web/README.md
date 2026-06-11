# 🌱 Sprout — *Describe your day. See your footprint. Shrink it.*

A daily climate-habit coach. Tell Sprout about your day in one sentence; it itemises
your carbon footprint, compares it to a sustainable daily target, and gives you **one
personalised, money-saving swap**. A shared **Grove** (family/team) tracks your streak
and compounding savings — so you actually come back.

> Built for **PromptWars** · LLM by **NVIDIA NIM** · **Google** Sheets + Gmail + Calendar.

## The problem

Most people *want* a smaller carbon footprint but can't act on it because:

- **Tracking is a chore.** Logging via dropdowns dies after 3 days.
- **Guilt repels.** "You emitted 12 kg 😞" makes people close the app.
- **No reason to return.** A static number you've already seen.

Carbon trackers have notoriously bad retention. **Sprout flips the model:** the daily
action is *receiving* one small swap (a reward), not *entering* data (a chore) — and the
swap is framed around **money saved**, with lower carbon as the happy side effect.

## How it helps — understand · track · reduce

| | How |
|---|---|
| **Understand** | One-sentence input → itemised kg CO₂e + relatable equivalences + a gauge vs. a 6 kg/day sustainable target. A **What-if** simulator shows the *annual* ₹ + kg payoff of bigger changes. |
| **Track** | A shared **Grove** ledger (Google Sheet) banks every completed swap — streak, trees' worth, and ₹ saved compound visibly. |
| **Reduce** | Exactly **one** personalised swap targeting your biggest source, with kg + ₹ saved. One tap adds it to **Google Calendar**; a weekly **Gmail** digest brings the Grove back. |

## Architecture

```
Browser (semantic + ARIA, Tailwind CDN, vanilla JS)
   │  POST /api/log · /api/whatif · /api/grove
   ▼
Flask app.py  ── one NVIDIA NIM call per action (structured JSON, offline fallback)
   │
   ├─ Google Sheet  → Grove ledger (streak / savings)            [server-side]
   └─ Gmail · Calendar · WhatsApp → share + reminders via URL-spec [client-side, no OAuth]
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
pytest          # 46 tests, branch coverage gate fails under 100%
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
3. Create a Sheet with a tab named **Grove**; share it with the service account's
   `client_email` (Editor).
4. Deploy with `SHEET_ID` + `SA_FILE` as above. Without these, Sprout uses an in-memory
   Grove (great for local demos; resets on restart).

## 90-second demo script

1. Click **Load sample day** → **Analyse my day**.
2. NVIDIA itemises 4 activities; the **gauge flips red**, Sprout shrinks to a seedling.
3. Read the **one swap** ("Swap a beef meal → save 4.8 kg + ₹90").
4. Drag a **What-if** preset → "Bike to work 2×/week → ~180 kg + ₹6,200/yr".
5. **Join a Grove** (`sprout-otter-42`) → tap **Did it ✅** → the forest grows, ₹ counter ticks.
6. **Add reminder 📅** opens Google Calendar; **Email digest ✉️** opens Gmail — prefilled, no login.
7. Close on the Grove: *"social accountability is why people come back."*

## Judging-rubric map

| Parameter | Where |
|---|---|
| Problem Alignment | understand / track / reduce above; sharp single-action loop |
| Google Services | Sheets (ledger) · Gmail (digest) · Calendar (reminders) — all load-bearing |
| Security | Secret Manager · input length caps · no PII · `.gcloudignore` |
| Testing | `pytest` + `--cov-fail-under=100`, all network mocked (46 tests) |
| Efficiency | gzip middleware · Cache-Control · static caching · 1 LLM call/action · min-instances |
| Accessibility | skip link · semantic landmarks · ARIA live regions · focus rings · ⌘+Enter · AA contrast · reduced-motion |
| Code Quality | type hints · docstrings · named constants · ruff · section banners · GitHub Actions CI |

*Estimates use demo-grade public averages — not for compliance reporting.*
