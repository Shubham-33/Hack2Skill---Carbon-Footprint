"""Sprout — a carbon + money second-opinion assistant.

Layered for clarity:

  config      — environment-derived settings
  estimates   — deterministic offline fallbacks + keyword routing (LLM-free)
  llm         — the NVIDIA NIM call and the unified classify-and-answer router
  ledger      — the savings-plan store (Google Sheet, or in-memory)
  validation  — request-input guards
  routes      — HTTP endpoints (Flask blueprint)
  middleware  — cross-cutting concerns (build-id injection, gzip)

`app.py` wires these together into a Flask app via `create_app()`.
"""
