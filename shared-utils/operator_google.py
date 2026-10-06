#!/usr/bin/env python3
"""
operator_google.py — Gmail + Drive for the OPERATOR's Mac, via the operator's
Google service account with domain-wide delegation (impersonating the operator).

Why not the gws CLI: a bare gws call run headless can wipe its own stored
credentials, and this runs from unattended roll/notify paths. The service
account needs no keyring, no TTY and no gws state at all.

Authorized delegation scopes on that account (anything else answers 403
unauthorized_client): https://www.googleapis.com/auth/drive (FULL; drive.file and
drive.readonly are NOT granted) and https://www.googleapis.com/auth/gmail.send.

Every function returns (ok, detail) and never raises for an unavailable
service; a secret value is never logged or returned.
"""
from __future__ import annotations

import base64
import json
import os
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

SA_PATH = Path(os.environ.get("FLEET_GOOGLE_SA", "~/.openclaw/secrets/gcp-service-account.json")).expanduser()
OPERATOR_EMAIL = os.environ.get("FLEET_OPERATOR_EMAIL", "trevor@blackceo.com")
DRIVE = "https://www.googleapis.com/auth/drive"
GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"


# The operator's Mac is the one machine holding the private fleet boxes file
# (scripts/make-fleet-boxes-file.py). A client box can have a service-account
# file at the same path; it must never be used to mail as the operator.
OPERATOR_MARKER = Path(os.environ.get("FLEET_BOXES_FILE", "~/.openclaw/fleet/boxes.json")).expanduser()


def available() -> bool:
    return SA_PATH.is_file() and OPERATOR_MARKER.is_file()


def _session(scope: str):
    if not SA_PATH.is_file():
        return None, f"no service account at {SA_PATH}"
    try:
        from google.oauth2 import service_account  # type: ignore
        from google.auth.transport.requests import AuthorizedSession  # type: ignore
    except ImportError as e:
        return None, f"google-auth not installed ({e.name})"
    try:
        creds = service_account.Credentials.from_service_account_file(
            str(SA_PATH), scopes=[scope], subject=OPERATOR_EMAIL)
        return AuthorizedSession(creds), ""
    except Exception as e:  # noqa: BLE001
        return None, f"service account unusable: {e.__class__.__name__}"


def send_email(subject: str, body: str, to: str = OPERATOR_EMAIL) -> tuple[bool, str]:
    s, why = _session(GMAIL_SEND)
    if not s:
        return False, why
    msg = EmailMessage()
    msg["To"], msg["From"], msg["Subject"] = to, OPERATOR_EMAIL, subject
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        r = s.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                   json={"raw": raw}, timeout=30)
    except Exception as e:  # noqa: BLE001
        return False, f"gmail send failed: {e.__class__.__name__}"
    return (r.status_code == 200), f"gmail HTTP {r.status_code}"


def _multipart(meta: dict, csv_text: str) -> tuple[bytes, str]:
    boundary = "fleetboxes7a9"
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: text/csv\r\n\r\n"
            f"{csv_text}\r\n--{boundary}--").encode()
    return body, f"multipart/related; boundary={boundary}"


def find_sheet(name: str) -> tuple[Optional[str], str]:
    s, why = _session(DRIVE)
    if not s:
        return None, why
    q = f"name = '{name}' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    r = s.get("https://www.googleapis.com/drive/v3/files", params={"q": q, "fields": "files(id)"}, timeout=30)
    if r.status_code != 200:
        return None, f"drive list HTTP {r.status_code}"
    files = r.json().get("files") or []
    return (files[0]["id"] if files else None), ("found" if files else "not found")


def upsert_sheet(name: str, csv_text: str, file_id: Optional[str] = None) -> tuple[Optional[str], str]:
    """Create (private, in the operator's My Drive) or overwrite the Google Sheet
    `name` from CSV. Overwriting keeps the file id and its (absent) sharing."""
    s, why = _session(DRIVE)
    if not s:
        return None, why
    if not file_id:
        file_id, _ = find_sheet(name)
    if file_id:
        r = s.patch(f"https://www.googleapis.com/upload/drive/v3/files/{file_id}",
                    params={"uploadType": "media"}, data=csv_text.encode(),
                    headers={"Content-Type": "text/csv"}, timeout=60)
    else:
        body, ctype = _multipart({"name": name, "mimeType": "application/vnd.google-apps.spreadsheet"}, csv_text)
        r = s.post("https://www.googleapis.com/upload/drive/v3/files",
                   params={"uploadType": "multipart", "fields": "id"}, data=body,
                   headers={"Content-Type": ctype}, timeout=60)
    if r.status_code != 200:
        return None, f"drive upload HTTP {r.status_code}"
    return r.json().get("id") or file_id, "ok"


def export_sheet_csv(file_id: str) -> tuple[Optional[str], str]:
    s, why = _session(DRIVE)
    if not s:
        return None, why
    r = s.get(f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
              params={"mimeType": "text/csv"}, timeout=60)
    if r.status_code != 200:
        return None, f"drive export HTTP {r.status_code}"
    return r.text, "ok"
