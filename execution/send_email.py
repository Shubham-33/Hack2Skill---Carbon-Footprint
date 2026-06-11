"""Send an email via SMTP.

Usage:
    python execution/send_email.py --to a@b.com --subject "Hi" --body "Text"
    echo "body text" | python execution/send_email.py --to a@b.com --subject "Hi"

Env: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM
"""
from __future__ import annotations

import argparse
import smtplib
import sys
from email.message import EmailMessage

from _common import env, fail, notify_slack, ok


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--to", required=True, help="Comma-separated recipients")
    p.add_argument("--subject", required=True)
    p.add_argument("--body", default=None, help="Body text (or pipe via stdin)")
    p.add_argument("--html", default=None, help="Optional HTML body")
    args = p.parse_args()

    body = args.body if args.body is not None else sys.stdin.read()

    host = env("SMTP_HOST", required=True)
    port = int(env("SMTP_PORT", "587"))
    user = env("SMTP_USER", required=True)
    password = env("SMTP_PASSWORD", required=True)
    sender = env("EMAIL_FROM") or user

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = args.to
    msg["Subject"] = args.subject
    msg.set_content(body)
    if args.html:
        msg.add_alternative(args.html, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
    except Exception as e:  # noqa: BLE001 — surface any SMTP failure to orchestrator
        fail(f"SMTP send failed: {e}", to=args.to)

    notify_slack(f":email: Sent email to {args.to} — _{args.subject}_")
    ok(to=args.to, subject=args.subject)


if __name__ == "__main__":
    main()
