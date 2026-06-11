"""Google Sheets client shared by read_sheet.py and update_sheet.py.

Auth: a service-account JSON whose path is in GOOGLE_SERVICE_ACCOUNT_JSON
(defaults to credentials.json). Share the target sheet with the service
account's client_email.
"""
from __future__ import annotations

import os

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "credentials.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Service account file not found: {path}. "
            "Set GOOGLE_SERVICE_ACCOUNT_JSON or place credentials.json at repo root."
        )
    creds = Credentials.from_service_account_file(path, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)
