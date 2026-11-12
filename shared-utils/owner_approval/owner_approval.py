#!/usr/bin/env python3
"""Owner approval requests: the ONE path every approval kind goes through.

Why this exists: a write gate (Skill 44 safety_gate.py) needs CAF_APPROVAL_ID, the id of an
approval record that only Command Center can mint. The owner can say yes in THREE places and
any one of them works: (1) a reply in the chat they are already using (Telegram or the OpenClaw
chat app), (2) a button in Telegram, (3) the one-tap link to Command Center. The agent delivers
the review material INTO the chat (the copy text inline, wireframe / mockup images or a PDF
attached) so the owner never has to leave the conversation to see what they are approving.

    request        register a PENDING request with Command Center (POST), get the owner's link back
    message        print the owner-facing message: plain summary, preview inline, three ways to approve
    deliver        send that message (and the attachments) into the owner's chat through the gateway
    chat-decision  the owner answered in chat: hand Command Center the inbound message reference
    status         ask Command Center what happened (GET); once approved, hand back the approval id
    wait           poll status until approved / changes requested / expired / timeout
    pending        list the requests still waiting on the owner (local state, no network)

THE AGENT NEVER MINTS APPROVAL. A chat reply becomes a record only because `chat-decision` gives
Command Center the reference of the real inbound message; Command Center checks that the message
really came from the owner and mints the record itself. This script cannot create an approval and
the agent's own text is never one. The approval id it hands back is looked up from Command Center
(and re-read with a GET after a chat decision); the write gate still fetches and verifies the
record itself, so a made-up id approves nothing. Something already approved is never asked again.

Every approval message carries "Code: <first 6 characters of the request id>" so a chat reply binds
to the right request when more than one is waiting.

Environment: MISSION_CONTROL_URL (https, or http on loopback) and MC_API_TOKEN.
State: ~/.openclaw/data/owner-approvals/<request_id>.json (override OWNER_APPROVAL_STATE_DIR).
Gateway send command: `openclaw` (override OWNER_APPROVAL_SEND_CMD); Telegram target from
--target or OWNER_APPROVAL_TELEGRAM_TARGET.

Exit codes: 0 ok / approved, 2 usage or configuration, 3 pending (status/wait), 4 changes
requested, 5 expired or revoked, 6 Command Center unreachable or refused (fail closed),
7 Command Center refused a chat decision with a reason (relay it plainly, re-send the link).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── The wire contract (change here, nowhere else) ────────────────────────────
REQUEST_PATH = "/api/approval-requests"                    # POST: create a pending request
STATUS_PATH = "/api/approval-requests/{request_id}"        # GET: status, short_code, approve_by, minted approval id
CHAT_DECISION_PATH = "/api/approval-requests/{request_id}/chat-decision"  # POST: owner answered in chat
_LOOPBACK = ("localhost", "127.0.0.1", "::1")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,128}$")

# Response field spellings Command Center may use; first present wins.
_F_REQUEST_ID = ("request_id", "requestId", "id")
_F_URL = ("approval_url", "approvalUrl", "path")
_F_APPROVAL_ID = ("approval_id", "approvalId")
_F_STATUS = ("status", "state")

EXIT_OK, EXIT_USAGE, EXIT_PENDING, EXIT_CHANGES, EXIT_EXPIRED, EXIT_CC = 0, 2, 3, 4, 5, 6
EXIT_REFUSED = 7

#: Every approval kind Command Center mints. Each one travels the same request / deliver /
#: chat-decision / wait path; none implies another.
KINDS = ("plan_build", "paid_asset_budget", "publish", "automation_write", "design_board",
         "pin_rotation", "stub_render")
CHANNELS = ("telegram", "webchat")
DECISIONS = ("approve", "changes")
_TEXT_SUFFIXES = (".txt", ".md", ".markdown", ".json", ".csv", ".html", ".htm")
_MEDIA_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf")
_REF_RE = re.compile(r"^(telegram|webchat):[^:\s]{1,128}:[^:\s]{1,128}$")
PREVIEW_INLINE_LIMIT = 6000

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


class ApprovalHTTPError(ApprovalError):
    """Command Center answered with an HTTP error; keeps the status and the stated reason."""

    def __init__(self, message: str, code: int, reason: str = ""):
        super().__init__(message)
        self.code = code
        self.reason = reason


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
        reason = ""
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace") or "{}")
            if isinstance(payload, dict):
                reason = str(payload.get("reason") or payload.get("error") or payload.get("message") or "")[:500]
        except (OSError, ValueError):
            pass
        raise ApprovalHTTPError(f"Command Center answered HTTP {exc.code} for {method} {path}.",
                                exc.code, reason)
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


# ── Preview material (copy inline, images and PDFs attached) ─────────────────
def collect_preview(files: list) -> tuple[str, list]:
    """Split --preview-file paths into inline text and attachments (images / PDF).

    Text-like files (.txt .md .json .html ...) are read and shown inline in the chat; images and
    PDFs are attached with the message. Anything else is refused by name so a review item is never
    silently left out of what the owner sees.
    """
    texts, attachments = [], []
    for raw in files or []:
        path = Path(str(raw)).expanduser()
        if not path.is_file():
            raise ApprovalError(f"preview file {str(raw)[:80]!r} does not exist.")
        suffix = path.suffix.lower()
        if suffix in _MEDIA_SUFFIXES:
            attachments.append(str(path.resolve()))
        elif suffix in _TEXT_SUFFIXES or suffix == "":
            texts.append(path.read_text(errors="replace").strip())
        else:
            raise ApprovalError(f"preview file {path.name!r} is not text, an image or a PDF; "
                                "convert it so the owner can see it in chat.")
    return "\n\n".join(t for t in texts if t)[:PREVIEW_INLINE_LIMIT], attachments


def short_code(request_id: str) -> str:
    """The code that binds a chat reply to one request: first six characters of the request id."""
    return str(request_id)[:6]


# ── Operations ───────────────────────────────────────────────────────────────
def request_approval(*, kind: str, location_id: str, action: str, object_key: str,
                     plan_sha256: str, summary: str, preview_text: str = "",
                     preview_url: str = "", skill: str = "", requested_by: str = "agent",
                     title: str = "", valid_until: str = "", owner_hours: int = 0,
                     attachments: list | None = None) -> dict:
    """Register a pending request (idempotent for the same plan) and return its record."""
    if not (kind and action and plan_sha256 and summary):
        raise ApprovalError("kind, action, plan_sha256 and summary are required.")
    if kind not in KINDS:
        raise ApprovalError(f"unknown approval kind {kind!r}; use one of {', '.join(KINDS)}.")
    pv = {}
    if preview_text:
        pv["text"] = preview_text
    if preview_url:
        pv["links"] = [{"label": "Full preview", "url": preview_url}]
    body = {"kind": kind, "location_id": location_id, "action": action,
            "object_key": object_key, "plan_sha256": plan_sha256,
            "title": (title or summary)[:200], "summary": summary[:4000],
            "requested_by": requested_by}
    if pv:
        body["preview"] = pv
    if valid_until:
        body["valid_until"] = valid_until
    if owner_hours:
        body["expires_at"] = (datetime.now(timezone.utc) + timedelta(hours=owner_hours)).isoformat(timespec="seconds")
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
           "approval_id": None, "idem": idem, "location_id": location_id, "object_key": object_key,
           "plan_sha256": plan_sha256, "created_at": _now(), "last_reminded_at": None,
           "summary": summary, "preview_text": preview_text, "preview_url": preview_url,
           "attachments": list(attachments or []), "short_code": short_code(str(rid)),
           "kind": kind, "action": action, "skill": skill}
    _save(rec)
    rec["reused"] = False
    return rec


def check_status(request_id: str) -> dict:
    """Ask Command Center for the current answer; record it; return the state record."""
    rec = _load(request_id) or {"request_id": request_id}
    resp = _call("GET", STATUS_PATH.format(request_id=urllib.parse.quote(request_id, safe="")))
    return _absorb(rec, request_id, resp)


def _absorb(rec: dict, request_id: str, resp: dict) -> dict:
    """Fold a Command Center answer into the state record. Approval needs a usable approval id."""
    raw = str(_first(resp, _F_STATUS) or "").strip().lower()
    status = _STATUS_MAP.get(raw)
    if status is None:
        raise ApprovalError(f"Command Center returned an unknown status {raw!r}; treating as not approved.")
    rec.update(request_id=request_id, status=status, checked_at=_now())
    url = _first(resp, _F_URL)
    if url:
        rec["approval_url"] = _abs_url(str(url))
    if resp.get("short_code"):
        rec["short_code"] = str(resp["short_code"])
    if resp.get("approve_by"):
        rec["approve_by"] = str(resp["approve_by"])
    note = resp.get("decision_note") or resp.get("note") or ""
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


def chat_decision(request_id: str, *, decision: str, channel: str, source_message_ref: str,
                  note: str = "") -> dict:
    """The owner answered in chat. Give Command Center the inbound message reference; it verifies
    the real owner message itself and mints (or refuses) the record. The agent supplies no approval.

    source_message_ref is "<channel>:<chat_or_session_id>:<message_id>" of the INBOUND message.
    Raises ApprovalHTTPError on a refusal (403 / 409) so the caller can relay the reason.
    """
    if decision not in DECISIONS:
        raise ApprovalError(f"decision must be one of {', '.join(DECISIONS)}.")
    if channel not in CHANNELS:
        raise ApprovalError(f"channel must be one of {', '.join(CHANNELS)}.")
    m = _REF_RE.match(source_message_ref or "")
    if not m or m.group(1) != channel:
        raise ApprovalError("source message reference must look like <channel>:<chat_or_session_id>:<message_id> "
                            "and match --channel; it is the owner's real inbound message, never made up.")
    rec = _load(request_id) or {"request_id": request_id}
    if rec.get("status") == "approved" and rec.get("approval_id"):
        rec["already_approved"] = True            # never ask, or record, something already approved
        return rec
    body = {"decision": decision, "channel": channel, "source_message_ref": source_message_ref}
    if note:
        body["note"] = note[:2000]
    resp = _call("POST", CHAT_DECISION_PATH.format(request_id=urllib.parse.quote(request_id, safe="")), body)
    raw = str(_first(resp, _F_STATUS) or "").strip().lower()
    mapped = _STATUS_MAP.get(raw)
    if decision == "approve" and mapped != "approved":
        raise ApprovalError(f"Command Center answered {raw!r} to an approval; treating as not approved.")
    if mapped == "approved":
        # Trust nothing but Command Center's own record: read it back before handing out an id.
        rec = check_status(request_id)
        if rec["status"] != "approved":
            raise ApprovalError("Command Center did not confirm the approval on read-back; not proceeding.")
        return rec
    if note:
        rec["note"] = note
    rec = _absorb(rec, request_id, dict(resp, status=raw or "changes_requested"))
    return rec


def _ways_to_approve(rec: dict) -> list:
    code = rec.get("short_code") or short_code(rec.get("request_id", ""))
    link = rec.get("approval_url") or "(link missing: re-run `request`)"
    return [
        "Three ways to answer. Any one of them works:",
        f'1. Reply right here: "approve" (or "yes"), or "changes: <what to change>".',
        "2. Tap the Approve or Ask for changes button under this message (Telegram).",
        f"3. Open Command Center: {link}",
        "",
        f"Code: {code}",
    ]


def owner_message(rec: dict, *, reminder: bool = False, chat_said_approved: bool = False,
                  refusal: str = "") -> str:
    """The text the agent sends the owner: the material inline, three ways to answer, the code."""
    lines = []
    if refusal:
        lines.append("I could not record your reply yet. " + refusal.strip())
        lines.append("You can still answer with the button or the link below, or reply again.")
    elif chat_said_approved:
        lines.append("Thank you. I need Command Center to confirm your reply first. "
                     "Please use the button or the link below and it takes a few seconds.")
    elif reminder:
        lines.append("A quick reminder: this is still waiting for your OK.")
    else:
        lines.append("I have something ready for your OK.")
    if rec.get("summary"):
        lines += ["", "What will happen:", str(rec["summary"]).strip()]
    if rec.get("preview_text"):
        lines += ["", "Preview:", str(rec["preview_text"]).strip()]
    atts = [Path(a).name for a in rec.get("attachments") or []]
    if atts:
        lines += ["", "Attached for you to look at: " + ", ".join(atts)]
    if rec.get("preview_url"):
        lines += ["", f"Full preview: {rec['preview_url']}"]
    lines += [""] + _ways_to_approve(rec)
    return "\n".join(lines)


def chat_buttons(rec: dict) -> dict:
    """Telegram button presentation: the tap comes back as an ordinary inbound owner message."""
    code = rec.get("short_code") or short_code(rec.get("request_id", ""))
    return {"buttons": [{"label": "Approve", "value": f"approve {code}"},
                        {"label": "Ask for changes", "value": f"changes {code}:"}]}


def send_command(rec: dict, *, channel: str, target: str, account: str = "", buttons: bool = True,
                 reminder: bool = False, dry_run: bool = False) -> list:
    """The gateway send command that puts the review material in the owner's chat.

    Telegram goes out through `openclaw message send` with the attachments as --media. The OpenClaw
    chat app is the conversation the agent is already in, so webchat has no send command: the agent
    posts owner_message(...) and attaches the listed files in its own reply (returns []).
    """
    if channel != "telegram":
        return []
    if not target:
        raise ApprovalError("telegram delivery needs --target (the owner's chat id) or OWNER_APPROVAL_TELEGRAM_TARGET.")
    cmd = shlex.split(os.environ.get("OWNER_APPROVAL_SEND_CMD", "openclaw")) + [
        "message", "send", "--channel", "telegram", "--target", target,
        "--message", owner_message(rec, reminder=reminder)]
    if account:
        cmd += ["--account", account]
    for media in rec.get("attachments") or []:
        cmd += ["--media", media]
    if buttons:
        cmd += ["--presentation", json.dumps(chat_buttons(rec))]
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def deliver(rec: dict, *, channel: str, target: str = "", account: str = "", reminder: bool = False,
            dry_run: bool = False) -> dict:
    """Send the approval message into the owner's chat. Returns {delivered, command?, text, attachments}."""
    target = target or os.environ.get("OWNER_APPROVAL_TELEGRAM_TARGET", "")
    text = owner_message(rec, reminder=reminder)
    out = {"channel": channel, "text": text, "attachments": list(rec.get("attachments") or [])}
    cmd = send_command(rec, channel=channel, target=target, account=account, reminder=reminder, dry_run=dry_run)
    if not cmd:
        out.update(delivered=False, note="webchat: post this text and attach the listed files in your reply.")
        return out
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if res.returncode != 0 and "--presentation" in cmd:        # buttons unsupported here: send without them
        cmd = send_command(rec, channel=channel, target=target, account=account, buttons=False,
                           reminder=reminder, dry_run=dry_run)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        out["buttons"] = False
    if res.returncode != 0:
        raise ApprovalError("the chat message could not be sent (the gateway refused it); "
                            "tell the owner plainly and send the Command Center link in your reply.")
    out.update(delivered=True, dry_run=dry_run)
    if rec.get("request_id"):
        rec["delivered_at"] = _now()
        _save({k: v for k, v in rec.items() if k not in ("reused", "already_approved")})
    return out


def list_pending() -> list:
    rows = []
    for p in sorted(_state_dir().glob("*.json")):
        try:
            rec = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if rec.get("status") == "pending":
            rows.append({k: rec.get(k) for k in ("request_id", "short_code", "kind", "summary", "created_at")})
    return rows


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _emit(rec: dict, args, extra: dict | None = None) -> None:
    out = {k: rec.get(k) for k in ("request_id", "short_code", "approval_url", "status", "approval_id",
                                   "note", "reused", "already_approved") if rec.get(k) is not None}
    out.update(extra or {})
    if getattr(args, "shell", False) and rec.get("status") == "approved":
        # Bind the gate to exactly what was registered (the gate compares these to the record).
        for var, key in (("CAF_APPROVAL_ID", "approval_id"), ("CAF_WRITE_ACTION", "action"),
                         ("CAF_OBJECT_KEY", "object_key"), ("CAF_PLAN_SHA256", "plan_sha256")):
            if rec.get(key) is not None:
                print(f"export {var}={shlex.quote(str(rec[key]))}")
    else:
        print(json.dumps(out, indent=2))


_EXIT = {"approved": EXIT_OK, "pending": EXIT_PENDING, "changes_requested": EXIT_CHANGES, "expired": EXIT_EXPIRED}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("request", help="register a pending owner approval request")
    r.add_argument("--kind", required=True, choices=KINDS)
    for f in ("action", "plan-sha256", "summary"):
        r.add_argument("--" + f, required=True)
    r.add_argument("--location-id", default=os.environ.get("GHL_LOCATION_ID", ""))
    r.add_argument("--object-key", default="")
    r.add_argument("--preview-text", default="")
    r.add_argument("--preview-file", action="append", default=[],
                   help="repeatable: a text file is shown inline in chat; an image or PDF is attached")
    r.add_argument("--preview-url", default="")
    r.add_argument("--skill", default="")
    r.add_argument("--title", default="")
    r.add_argument("--valid-until", default="", help="ISO end of the window being approved (e.g. end of the week)")
    r.add_argument("--owner-hours", type=int, default=0, help="hours the owner has to answer (default: server 7d)")
    r.add_argument("--message", action="store_true", help="print the owner message instead of JSON")
    r.add_argument("--deliver", choices=CHANNELS, default="",
                   help="also put the message (and attachments) in the owner's chat now")
    r.add_argument("--target", default="", help="telegram chat id for --deliver telegram")
    for name in ("message", "deliver", "chat-decision", "status", "wait"):
        p = sub.add_parser(name)
        if name == "message":
            p.add_argument("--reminder", action="store_true")
            p.add_argument("--chat-said-approved", action="store_true",
                           help="fallback only: a chat decision could not be recorded, send the button / link wording")
        elif name == "deliver":
            p.add_argument("--channel", choices=CHANNELS, required=True)
            p.add_argument("--target", default="")
            p.add_argument("--account", default="")
            p.add_argument("--reminder", action="store_true")
            p.add_argument("--dry-run", action="store_true", help="build the send but do not deliver")
        elif name == "chat-decision":
            p.add_argument("--decision", choices=DECISIONS, required=True)
            p.add_argument("--channel", choices=CHANNELS, required=True)
            p.add_argument("--source-message-ref", required=True,
                           help="<channel>:<chat_or_session_id>:<message_id> of the owner's inbound message")
            p.add_argument("--note", default="", help="what the owner wants changed, in their words")
            p.add_argument("--shell", action="store_true", help="on approval print: export CAF_APPROVAL_ID=...")
        else:
            p.add_argument("--shell", action="store_true", help="on approval print: export CAF_APPROVAL_ID=...")
            if name == "wait":
                p.add_argument("--timeout", type=int, default=600)
                p.add_argument("--interval", type=int, default=15)
        p.add_argument("--request-id", required=True)
    sub.add_parser("pending", help="list requests still waiting on the owner (no network)")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "pending":
            print(json.dumps(list_pending(), indent=2))
            return EXIT_OK
        if a.cmd == "request":
            preview, attachments = collect_preview(a.preview_file)
            preview = "\n\n".join(x for x in (a.preview_text, preview) if x)[:PREVIEW_INLINE_LIMIT]
            rec = request_approval(kind=a.kind, location_id=a.location_id, action=a.action,
                                   object_key=a.object_key, plan_sha256=a.plan_sha256,
                                   summary=a.summary, preview_text=preview,
                                   preview_url=a.preview_url, skill=a.skill, title=a.title,
                                   valid_until=a.valid_until, owner_hours=a.owner_hours,
                                   attachments=attachments)
            extra = {}
            if a.deliver:
                extra["delivery"] = deliver(rec, channel=a.deliver, target=a.target)
            if a.message:
                print(owner_message(rec))
            else:
                _emit(rec, a, {"owner_message": owner_message(rec), **extra})
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
        if a.cmd == "deliver":
            rec = _load(a.request_id)
            if not rec.get("approval_url"):
                raise ApprovalError("no saved request with that id; run `request` first.")
            if rec.get("status") == "approved":
                raise ApprovalError("this was already approved; nothing to send, do not ask again.")
            res = deliver(rec, channel=a.channel, target=a.target, account=a.account,
                          reminder=a.reminder, dry_run=a.dry_run)
            print(json.dumps(res, indent=2))
            return EXIT_OK
        if a.cmd == "chat-decision":
            try:
                rec = chat_decision(a.request_id, decision=a.decision, channel=a.channel,
                                    source_message_ref=a.source_message_ref, note=a.note)
            except ApprovalHTTPError as exc:
                if exc.code in (403, 409):
                    saved = _load(a.request_id)
                    reason = exc.reason or "Command Center could not match that reply to you."
                    print(json.dumps({"request_id": a.request_id, "status": "refused", "reason": reason,
                                      "owner_message": owner_message(saved, refusal=reason) if saved else reason},
                                     indent=2))
                    return EXIT_REFUSED
                raise
            _emit(rec, a)
            return _EXIT[rec["status"]]
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
