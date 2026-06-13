# 🌱 Sprout — your carbon + money second opinion

[![CI](https://github.com/Shubham-33/Hack2Skill---Carbon-Footprint/actions/workflows/ci.yml/badge.svg)](https://github.com/Shubham-33/Hack2Skill---Carbon-Footprint/actions)
![coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
![type-checked](https://img.shields.io/badge/mypy-clean-blue)

Ask anything in **one box** — a bill, a trip, a product, an eco-claim, an order, or
*"is solar worth it?"* — and a single NVIDIA NIM call detects what you need and answers
with **specific, money-grounded output**. Built for **PromptWars / Hack2Skill**.

🔗 **Live:** https://sprout-h2izdenmlq-uc.a.run.app
📦 **The app lives in [`web/`](web/)** — see **[web/README.md](web/README.md)** for full docs.

## The problem

People want a lower carbon footprint but trackers fail them: logging is a chore, guilt
repels, the advice is generic, and there's no payoff. **Sprout flips it** — near-zero
effort in (paste what you already have), concrete value out (real ₹ saved, a ranked
decision, a verdict), tied to things you do regularly (bills, trips, purchases).

## Six checks, one smart input

| Check | You paste | You get |
|---|---|---|
| 💰 Savings | a bill / monthly spend | ranked actions with ₹ + kg saved/yr + payback |
| 🚆 Trip | a journey | travel options ranked by carbon, cost, time |
| 🛒 Shop | an order / receipt | footprint + cheaper-greener swaps |
| ⚖️ Worth it? | solar / EV / heat pump | personalised payback in ₹, kg, years |
| 🔍 Eco-claim | a marketing line | legit / greenwashing verdict + why |
| 📊 Footprint | "footprint of X?" | a number + a relatable comparison |

Commit a saving and it banks into a shared **plan** (Google Sheet); the ₹/yr on track to
save compounds — the reason to come back. Distribution via Gmail / Calendar / WhatsApp
URL-specs (no OAuth).

## Tech

- **Backend:** Python / Flask, a layered [`sprout`](web/sprout/) package (config · estimates ·
  llm · ledger · validation · routes · middleware) assembled by a `create_app()` factory.
- **LLM:** NVIDIA NIM (`llama-3.3-70b-instruct`, OpenAI-compatible REST) — one call per
  question, with a deterministic offline fallback so it never dies on stage.
- **Google:** Sheets (ledger) + Gmail + Calendar.
- **Quality:** 100% test coverage gate, `ruff` + `mypy` clean, GitHub Actions CI, gzip +
  Secret Manager, WCAG-AA accessibility. Deployed to Cloud Run.

## Quick start

```bash
cd web
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env          # optional: add NVIDIA_API_KEY (works without it via fallback)
python app.py                 # http://localhost:5050
pytest                        # 58 tests, 100% coverage gate
```

Full run / test / deploy instructions: **[web/README.md](web/README.md)**.

## License

[MIT](LICENSE)
