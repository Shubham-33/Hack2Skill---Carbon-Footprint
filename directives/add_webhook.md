# Directive: Add a Webhook

**Goal:** Stand up a new event-driven webhook that maps an incoming HTTP request to a single directive with a scoped set of tools.

## Inputs
- A plain-English description of what the webhook should do ("when X happens, do Y").
- The trigger source (who/what calls the endpoint) and the shape of its JSON payload.
- Which tools the directive needs. Allowed today: `send_email`, `read_sheet`, `update_sheet`.

## Steps
1. **Pick a slug** — short, kebab-case, unique (e.g. `log-emissions`).
2. **Write the directive** — create `directives/<slug>.md` (use this file's structure: Goal, Inputs, Steps, Outputs, Edge Cases). Ask the user before overwriting an existing directive.
3. **Register it** — add an entry under `webhooks` in `execution/webhooks.json`:
   ```json
   "<slug>": {
     "directive": "<slug>.md",
     "description": "...",
     "tools": ["send_email", "update_sheet"]
   }
   ```
   Only list tools the directive actually uses (least privilege).
4. **Deploy** — `modal deploy execution/modal_webhook.py`. Requires the `claude-orchestrator-secrets` Modal secret to exist (ANTHROPIC_API_KEY, SMTP_*, Slack, Google creds).
5. **Test** — POST to the `directive` endpoint with `?slug=<slug>` and a sample payload. Confirm Slack shows the fire/done messages.

## Outputs
- A new `directives/<slug>.md`.
- A new entry in `execution/webhooks.json`.
- A deployed, tested endpoint.

## Edge Cases / Learnings
- **Secrets must exist before deploy.** Create with `modal secret create claude-orchestrator-secrets KEY=value ...`.
- **Tool scoping is enforced by `webhooks.json`, not the directive prose.** If a tool isn't listed, the orchestrator must not use it.
- `modal_webhook.py` ships local `execution/` and `directives/` into the image — redeploy after editing either so the container picks up changes.
- Keep `run_directive()` the only place that talks to the Anthropic SDK; everything else stays deterministic.
