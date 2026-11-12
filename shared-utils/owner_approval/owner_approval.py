#!/usr/bin/env python3
"""Owner approval requests through Command Center: the ONE place the path lives.

Why this exists: a write gate (Skill 44 safety_gate.py) needs CAF_APPROVAL_ID, the id of an
approval record that only Command Center can mint, and only when the owner taps Approve on
the page behind a link. An agent that tells the owner "approve it in the Command Center"
with no link strands the owner. This helper gives every skill the same four moves:

    request   register a PENDING request with Command Center (POST), get the owner's link back
    message   print the owner-facing message: plain summary, preview, one-tap link
    status    ask Command Center what happened (GET); once approved, hand back the approval id
    wait      poll status until approved / changes requested / expired / timeout

THE AGENT NEVER MINTS APPROVAL. This script can only ask Command Center to create a pending
request and read the answer. The approval id it hands back is looked up from Command Center;
the write gate still fetches and verifies the record itself, so a made-up id approves nothing.
Chat text ("approved", a thumbs up) is never approval: when the owner says it in chat, the
agent replies with the one-tap link (`message`), it does not proceed.

Environment: MISSION_CONTROL_URL (https, or http on loopback) and MC_API_TOKEN.
State: ~/.openclaw/data/owner-approvals/<request_id>.json (override OWNER_APPROVAL_STATE_DIR).

Exit codes: 0 ok / approved, 2 usage or configuration, 3 pending (status/wait), 4 changes
requested, 5 expired or revoked, 6 Command Center unreachable or refused (fail closed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── The wire contract (change here, nowhere else) ────────────────────────────
REQUEST_PATH = "/api/approval-requests"                    # POST: create a pending request
STATUS_PATH = "/api/approval-requests/{request_id}"        # GET: status + minted approval id
_LOOPBACK = ("localhost", "127.0.0.1", "::1")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,128}$")

# Response field spellings Command Center may use; first present wins.
_F_REQUEST_ID = ("requestId", "request_id", "id")
_F_URL = ("approvalUrl", "approval_url", "deepLink", "deep_link", "url")
_F_APPROVAL_ID = ("approvalId", "approval_id")
_F_STATUS = ("status", "state")

EXIT_OK, EXIT_USAGE, EXIT_PENDING, EXIT_CHANGES, EXIT_EXPIRED, EXIT_CC = 0, 2, 3, 4, 5, 6

_STATUS_MAP = {
    "pending": "pending", "awaiting": "pending", "open": "pending", "requested": "pending",
    "approved": "approved", "granted": "approved",
    "changes_requested": "changes_requested", "changes-requested": "changes_requested",
    "request_changes": "changes_requested", "rejected": "changes_requested",
    "declined": "changes_requested",
    "expired": "expired", "revoked": "expired", "cancelled": "expired", "canceled": "expired",
}


class ApprovalError(RuntimeError):
    """Configuration problem or Command Center failure (always fail closed)."""


def _first(d: dict, names: tuple):
    for n in names:
        if isinstance(d, dict) and d.get(n) not in (None, ""):
            return d[n]
    return None


def _config() -> tuple[str, str]:
    base = os.environ.get("MISSION_CONTROL_URL", "").strip().rstrip("/")
    token = os.environ.get("MC_API_TOKEN", "").strip()
    parts = urllib.parse.urlsplit(base)
    if not (base and token and parts.hostname and (
            parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in _LOOPBACK))):
        raise ApprovalError("Command Center is not configured: set MISSION_CONTROL_URL "
                            "(https, or http on loopback) and MC_API_TOKEN.")
    return base, token


def _call(method: str, path: str, body: dict | None = None) -> dict:
    base, token = _config()
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        timeout = int(os.environ.get("CC_BOARD_TIMEOUT") or 10)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out = json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        raise ApprovalError(f"Command Center answered HTTP {exc.code} for {method} {path}.")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ApprovalError(f"Command Center could not be reached ({type(exc).__name__}).")
    return out if isinstance(out, dict) else {}


def _abs_url(url: str) -> str:
    if url.startswith("/"):
        base, _ = _config()
        return base + url
    return url


# ── State (one small file per request, so reminders and resumes find the link) ─
def _state_dir() -> Path:
    d = Path(os.environ.get("OWNER_APPROVAL_STATE_DIR")
             or Path.home() / ".openclaw" / "data" / "owner-approvals")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_path(request_id: str) -> Path:
    if not _ID_RE.match(request_id or ""):
        raise ApprovalError("request id is missing or malformed.")
    return _state_dir() / f"{request_id}.json"


def _load(request_id: str) -> dict:
    p = _state_path(request_id)
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def _save(rec: dict) -> None:
    p = _state_path(rec["request_id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=2, sort_keys=True))
    os.replace(tmp, p)


def _idem_key(a: dict) -> str:
    raw = "|".join(str(a.get(k, "")) for k in ("kind", "location_id", "action", "object_key", "plan_sha256"))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _find_open(idem: str) -> dict:
    for p in sorted(_state_dir().glob("*.json")):
        try:
            rec = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if rec.get("idem") == idem and rec.get("status") in ("pending", "approved"):
            return rec
    return {}


# ── Operations ───────────────────────────────────────────────────────────────
def request_approval(*, kind: str, location_id: str, action: str, object_key: str,
                     plan_sha256: str, summary: str, preview_text: str = "",
                     preview_url: str = "", skill: str = "", requested_by: str = "agent",
                     expires_in_hours: int = 72) -> dict:
    """Register a pending request (idempotent for the same plan) and return its record."""
    if not (kind and action and plan_sha256 and summary):
        raise ApprovalError("kind, action, plan_sha256 and summary are required.")
    body = {"kind": kind, "location_id": location_id, "action": action,
            "object_key": object_key, "plan_sha256": plan_sha256, "summary": summary,
            "preview_text": preview_text, "preview_url": preview_url, "skill": skill,
            "requested_by": requested_by, "expires_in_hours": expires_in_hours}
    idem = _idem_key(body)
    existing = _find_open(idem)
    if existing:                       # same plan already asked: never create a second request
        existing["reused"] = True
        return existing
    resp = _call("POST", REQUEST_PATH, body)
    rid = _first(resp, _F_REQUEST_ID) or _first(resp.get("request", {}) if isinstance(resp.get("request"), dict) else {}, _F_REQUEST_ID)
    url = _first(resp, _F_URL) or _first(resp.get("request", {}) if isinstance(resp.get("request"), dict) else {}, _F_URL)
    if not rid or not url:
        raise ApprovalError("Command Center did not return a request id and an approval link.")
    rec = {"request_id": str(rid), "approval_url": _abs_url(str(url)), "status": "pending",
           "approval_id": None, "idem": idem, "created_at": _now(), "last_reminded_at": None,
           "summary": summary, "preview_text": preview_text, "preview_url": preview_url,
           "kind": kind, "action": action, "skill": skill}
    _save(rec)
    rec["reused"] = False
    return rec


def check_status(request_id: str) -> dict:
    """Ask Command Center for the current answer; record it; return the state record."""
    rec = _load(request_id) or {"request_id": request_id}
    resp = _call("GET", STATUS_PATH.format(request_id=urllib.parse.quote(request_id, safe="")))
    raw = str(_first(resp, _F_STATUS) or "").strip().lower()
    status = _STATUS_MAP.get(raw)
    if status is None:
        raise ApprovalError(f"Command Center returned an unknown status {raw!r}; treating as not approved.")
    rec.update(request_id=request_id, status=status, checked_at=_now())
    url = _first(resp, _F_URL)
    if url:
        rec["approval_url"] = _abs_url(str(url))
    note = resp.get("note") or resp.get("changes_note") or ""
    if note:
        rec["note"] = str(note)
    aid = _first(resp, _F_APPROVAL_ID)
    if status == "approved":
        if not aid or not re.match(r"^[A-Za-z0-9_-]{8,128}$", str(aid)):
            raise ApprovalError("Status says approved but no usable approval id came back; not proceeding.")
        rec["approval_id"] = str(aid)
    else:
        rec["approval_id"] = None
    _save(rec)
    return rec


def owner_message(rec: dict, *, reminder: bool = False, chat_said_approved: bool = False) -> str:
    """The text the agent sends the owner. It ALWAYS carries the one-tap link."""
    link = rec.get("approval_url") or "(link missing: re-run `request`)"
    lines = []
    if chat_said_approved:
        lines.append("Thank you. To make it official, please tap this one link and press Approve. "
                     "It takes a few seconds, and I will start right after.")
    elif reminder:
        lines.append("A quick reminder: this is still waiting for your OK.")
    else:
        lines.append("I have something ready for your OK.")
    if rec.get("summary"):
        lines += ["", "What will happen:", str(rec["summary"]).strip()]
    if rec.get("preview_text"):
        lines += ["", "Preview:", str(rec["preview_text"]).strip()]
    if rec.get("preview_url"):
        lines += ["", f"Full preview: {rec['preview_url']}"]
    lines += ["", f"Tap to approve (or ask for changes): {link}"]
    return "\n".join(lines)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _emit(rec: dict, args, extra: dict | None = None) -> None:
    out = {k: rec.get(k) for k in ("request_id", "approval_url", "status", "approval_id", "note", "reused")
           if rec.get(k) is not None}
    out.update(extra or {})
    if getattr(args, "shell", False) and rec.get("status") == "approved":
        print(f"export CAF_APPROVAL_ID={rec['approval_id']}")
    else:
        print(json.dumps(out, indent=2))


_EXIT = {"approved": EXIT_OK, "pending": EXIT_PENDING, "changes_requested": EXIT_CHANGES, "expired": EXIT_EXPIRED}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("request", help="register a pending owner approval request")
    for f in ("kind", "action", "plan-sha256", "summary"):
        r.add_argument("--" + f, required=True)
    r.add_argument("--location-id", default=os.environ.get("GHL_LOCATION_ID", ""))
    r.add_argument("--object-key", default="")
    r.add_argument("--preview-text", default="")
    r.add_argument("--preview-file", default="", help="file whose text is the owner preview")
    r.add_argument("--preview-url", default="")
    r.add_argument("--skill", default="")
    r.add_argument("--expires-in-hours", type=int, default=72)
    r.add_argument("--message", action="store_true", help="print the owner message instead of JSON")
    for name in ("message", "status", "wait"):
        if name == "message":
            p = sub.add_parser("message", help="print the owner message with the link")
            p.add_argument("--reminder", action="store_true")
            p.add_argument("--chat-said-approved", action="store_true",
                           help="owner typed 'approved' in chat: answer with the one-tap link")
        else:
            p = sub.add_parser(name)
            p.add_argument("--shell", action="store_true", help="on approval print: export CAF_APPROVAL_ID=...")
            if name == "wait":
                p.add_argument("--timeout", type=int, default=600)
                p.add_argument("--interval", type=int, default=15)
        p.add_argument("--request-id", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "request":
            preview = a.preview_text
            if a.preview_file:
                preview = Path(a.preview_file).read_text(errors="replace")[:6000]
            rec = request_approval(kind=a.kind, location_id=a.location_id, action=a.action,
                                   object_key=a.object_key, plan_sha256=a.plan_sha256,
                                   summary=a.summary, preview_text=preview,
                                   preview_url=a.preview_url, skill=a.skill,
                                   expires_in_hours=a.expires_in_hours)
            if a.message:
                print(owner_message(rec))
            else:
                _emit(rec, a, {"owner_message": owner_message(rec)})
            return EXIT_OK
        if a.cmd == "message":
            rec = _load(a.request_id)
            if not rec.get("approval_url"):
                raise ApprovalError("no saved request with that id; run `request` first.")
            if a.reminder:
                rec["last_reminded_at"] = _now()
                _save(rec)
            print(owner_message(rec, reminder=a.reminder, chat_said_approved=a.chat_said_approved))
            return EXIT_OK
        if a.cmd == "status":
            rec = check_status(a.request_id)
            _emit(rec, a)
            return _EXIT[rec["status"]]
        if a.cmd == "wait":
            deadline = time.monotonic() + a.timeout
            while True:
                rec = check_status(a.request_id)
                if rec["status"] != "pending" or time.monotonic() >= deadline:
                    _emit(rec, a)
                    return _EXIT[rec["status"]]
                time.sleep(max(1, a.interval))
    except ApprovalError as exc:
        print(f"owner_approval: {exc}", file=sys.stderr)
        return EXIT_CC if "Command Center" in str(exc) and "configured" not in str(exc) else EXIT_USAGE
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
