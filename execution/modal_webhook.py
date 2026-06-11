"""Modal app exposing the orchestrator as event-driven webhooks.

Each webhook slug (see webhooks.json) maps to exactly one directive with a
scoped set of tools. Incoming requests are handed to Claude as the orchestrator,
which reads the directive and calls only the allowed execution tools.

Do not modify this file unless necessary — add behavior via directives + webhooks.json.

Deploy:   modal deploy execution/modal_webhook.py
Endpoints (after deploy, names follow your Modal workspace):
    .../list-webhooks            -> GET, lists configured webhooks
    .../directive?slug=<slug>    -> POST, executes the directive for <slug>
    .../test-email               -> POST {"to": "..."} sends a test email
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import modal

ROOT = Path(__file__).parent
WEBHOOKS_PATH = ROOT / "webhooks.json"

image = (
    modal.Image.debian_slim()
    .pip_install(
        "anthropic>=0.40.0",
        "requests>=2.31.0",
        "google-api-python-client>=2.100.0",
        "google-auth>=2.23.0",
        "python-dotenv>=1.0.0",
    )
    .add_local_dir(str(ROOT), remote_path="/root/execution")
    .add_local_dir(str(ROOT.parent / "directives"), remote_path="/root/directives")
)

app = modal.App("claude-orchestrator")

# Secrets are configured in the Modal dashboard (or `modal secret create`).
secrets = [modal.Secret.from_name("claude-orchestrator-secrets")]


def _load_webhooks() -> dict:
    return json.loads(WEBHOOKS_PATH.read_text())["webhooks"]


def _slack(text: str) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    try:
        import requests

        requests.post(url, json={"text": text}, timeout=5)
    except Exception:
        pass


@app.function(image=image, secrets=secrets)
@modal.fastapi_endpoint(method="GET")
def list_webhooks():
    return {"webhooks": _load_webhooks()}


@app.function(image=image, secrets=secrets)
@modal.fastapi_endpoint(method="POST")
def directive(slug: str, payload: dict | None = None):
    """Run the directive bound to `slug` with the incoming payload.

    The orchestration loop (reading the directive + tool-calling Claude) lives in
    run_directive(); kept separate so it is unit-testable without Modal.
    """
    webhooks = _load_webhooks()
    if slug not in webhooks:
        return {"ok": False, "error": f"Unknown slug: {slug}", "known": list(webhooks)}

    cfg = webhooks[slug]
    _slack(f":zap: Webhook `{slug}` fired → directive `{cfg['directive']}`")
    result = run_directive(cfg, payload or {})
    _slack(f":white_check_mark: Webhook `{slug}` done")
    return {"ok": True, "slug": slug, "result": result}


@app.function(image=image, secrets=secrets)
@modal.fastapi_endpoint(method="POST")
def test_email(to: str):
    import subprocess

    r = subprocess.run(
        ["python", "/root/execution/send_email.py", "--to", to,
         "--subject", "Orchestrator test", "--body", "It works."],
        capture_output=True, text=True,
    )
    return {"ok": r.returncode == 0, "stdout": r.stdout, "stderr": r.stderr}


def run_directive(cfg: dict, payload: dict) -> dict:
    """Hand the directive + payload to Claude as orchestrator, with scoped tools.

    This is intentionally a thin stub: wire it to the Anthropic SDK with the
    directive text as context and only `cfg['tools']` exposed. Returns whatever
    structured result the run produces. Build this out when you deploy.
    """
    directive_path = Path("/root/directives") / cfg["directive"]
    directive_text = directive_path.read_text() if directive_path.exists() else ""
    return {
        "directive": cfg["directive"],
        "allowed_tools": cfg["tools"],
        "payload": payload,
        "directive_loaded": bool(directive_text),
        "note": "Wire run_directive() to the Anthropic SDK to execute for real.",
    }
