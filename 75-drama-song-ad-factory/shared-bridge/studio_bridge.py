#!/usr/bin/env python3
"""U5 — the shared studio bridge (one file for OpenClaw boxes and Claude Code).

Reuses the mint/renew/sync shape of `intake/interview-app/bridge/intake_bridge.py`
and the durable-outbox shape of `scripts/core/cc_sync.py`. It is NOT a new
framework, scheduler, dashboard or management app.

What it is: the box-side half of the drama studio. The box holds the client's
presented key, claims ONE order at a time (never two runs on one order), refuses
replayed messages, hands photos to storage without routing bytes through the
worker, reports status, delivers, and leaves an owned-run cleanup receipt.

It speaks the U2 service contract verbatim (branch unit/U2, head 8f344a1d):

    GET  /api/studio/health
    POST /api/studio/enroll                      {enrollment_secret, label?}   no key
    POST /api/studio/link                        header x-ds-key  {rotate}
    POST /api/studio/checkin                     header x-ds-key  {agnes_remembered, agnes_progress?}
    GET  /api/studio/orders/<id>                 header x-ds-key
    POST /api/studio/orders/<id>/state           header x-ds-key  {event, reason?}
    POST /api/studio/uploads                     header x-ds-key  {channel, ...}
    POST /api/studio/orders                      header x-ds-key  {title, order_id?}

`event` is one of claim | needs_you | answer | ready | deliver | done | cancel.
The check-in carries the client's remembered Agnes answer and, while a run's
Agnes job is active, that run's small progress record (SPEC A11) - neither is a
secret, and the key never rides on either.

SECRETS: the presented key comes from env `DS_KEY` first, else the state
folder's `machine.key` (SPEC §2/§6) — never argv, never a file the caller names
on the command line, never a log line. Nothing in this module prints, echoes or
receipts a key value.

Exit codes: 0 ok · 1 error · 2 refused · 3 undefined (transport unknown, or an
approval not answered yet) · 4 halted (a replay that waits on the client).
Stdlib only: argparse, hashlib, json, os, pathlib, re, subprocess, sys, time,
urllib.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from studio_claim import (ClaimLedger, LedgerError, message_id,  # noqa: E402
                          STEPS, STEP_CLAIMED, STEP_ORDER_FETCHED,
                          STEP_MATERIALIZED, STEP_WAKE_QUEUED,
                          STEP_EXECUTION_ACCEPTED)

EXIT = {"ok": 0, "error": 1, "refused": 2, "undefined": 3, "halted": 4}

STATUS_EVENTS = ("claim", "needs_you", "answer", "ready", "deliver", "done")

#: The studio's own TERMINAL order states (service/src/lifecycle.js
#: TERMINAL_STATES). `cancel` is one of the contract's state events
#: (`POST /api/studio/orders/<id>/state`), it is allowed while the order waits
#: or sits at an approval stop before paid production, and once reached the
#: state never moves again. A terminal order is never materialized and never
#: woken: its local claim is released instead of resumed (ITEM 29 step 4).
TERMINAL_ORDER_STATES = ("done", "cancelled", "expired")

#: The claim ledger's owner row: one box = one claimant, whatever the process.
BRIDGE_OWNER = "studio-bridge"
#: The one inbox line the service prints (service/src/inbox.js:61).
INBOX_LINE = re.compile(r'^DRAMA_ORDER\s+(\S+)\s+"(.*)"$')
APPROVAL_STAGES = ("script", "song", "storyboard")
DELIVERY_KINDS = ("ghl", "r2")
#: An order id becomes a run directory name: one path segment, never a walk.
ORDER_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")

# The studio sits behind Cloudflare, which refuses Python's default User-Agent
# ("Python-urllib/3.x") with HTTP 403 "error code: 1010". Every request from this
# module therefore carries this ONE explicit User-Agent. Keep it identical in
# studio_bridge.py, studio.py and studio_check.py; prove/prove_user_agent.py
# asserts all three strings are equal before it drives a request.
STUDIO_USER_AGENT = "drama-studio-client/2.7.48 (+https://studio.zerohumanworkforce.com)"

#: Same per-channel caps and extensions as service/src/uploads.js.
CHANNELS = ("audio", "image", "video")
MAX_UPLOAD_BYTES = {"image": 25 * 1024 * 1024, "audio": 25 * 1024 * 1024,
                    "video": 200 * 1024 * 1024}
#: What an object is FOR, which picks its folder. `intake` is everything a
#: client or the studio sends in; `r2_fallback` is the studio's own 7-day copy of
#: a finished video (decision 5), which lives under clients/<id>/video/.
UPLOAD_KINDS = ("intake", "r2_fallback")
UPLOAD_SEGMENT = {"intake": "intake", "r2_fallback": "video"}
UPLOAD_TYPES = {
    "jpg": ("image", "image/jpeg"), "jpeg": ("image", "image/jpeg"),
    "png": ("image", "image/png"), "heic": ("image", "image/heic"),
    "webp": ("image", "image/webp"), "mp3": ("audio", "audio/mpeg"),
    "m4a": ("audio", "audio/mp4"), "wav": ("audio", "audio/wav"),
    "ogg": ("audio", "audio/ogg"), "mp4": ("video", "video/mp4"),
    "mov": ("video", "video/quicktime"), "webm": ("video", "video/webm"),
}
STUDIO_BASE_URL = "https://studio.zerohumanworkforce.com"
HEADER_SNIFF_BYTES = 512

IMAGE_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


# --- key handshake -----------------------------------------------------------

def _env_of(env):
    return os.environ if env is None else env


def _home_state(env=None):
    """`~/.drama-studio` for the SAME env the caller passed (SPEC §2).

    Kept exactly as it always was: the legacy fallback rung for a key written
    before the platform contract existed (see `load_key`).
    """
    src = _env_of(env)
    home = (src.get("HOME") or "").strip() or str(pathlib.Path.home())
    return pathlib.Path(home) / ".drama-studio"


def _contract_state(env=None):
    """THE persistent state root — the one contract for every reader (D24).

    macOS and Hostinger keep state under HOME (`/Users/<u>/.drama-studio`,
    `/data/.drama-studio`). Contabo's HOME is the ephemeral container layer, so
    its persistent root is `/home/node/.openclaw/.drama-studio` — exactly what
    timer-artifacts/run-timer.sh enforces and install-timer.sh stores into.
    Enrolment, installer, bridge, poller and wake helper must all meet here.
    """
    src = _env_of(env)
    home = (src.get("HOME") or "").strip() or str(pathlib.Path.home())
    if home.rstrip("/") == "/home/node":
        return pathlib.Path("/home/node/.openclaw/.drama-studio")
    return pathlib.Path(home) / ".drama-studio"


def state_dir(env=None):
    """The state folder: `$DRAMA_STUDIO_STATE` when set, else the contract root."""
    src = _env_of(env)
    given = (src.get("DRAMA_STUDIO_STATE") or "").strip()
    return pathlib.Path(given).expanduser() if given else _contract_state(env)


def read_private(path):
    """The one stripped line of a state file, or "". Never logged, never raised."""
    try:
        p = pathlib.Path(path)
        return p.read_text(encoding="utf-8").strip() if p.is_file() else ""
    except OSError:
        return ""


def write_private(path, text, *, mode=0o600, folder_mode=0o700):
    """Write a state file 0600 in a 0700 folder (SPEC §2). The value is never echoed."""
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p.parent, folder_mode)
    except OSError:  # a folder this process cannot chmod still holds the file
        pass
    p.write_text(text, encoding="utf-8")
    os.chmod(p, mode)
    return p


def load_key(env=None):
    """The presented key: env `DS_KEY`, else `machine.key`, else home (SPEC §6).

    Returns "" when absent (fail closed). The value is never printed.
    """
    src = _env_of(env)
    key = (src.get("DS_KEY") or "").strip()
    if key:
        return key
    for folder in (state_dir(env), _home_state(env)):
        found = read_private(folder / "machine.key")
        if found:
            return found
    return ""


def resolve_base_url(base_url=None, env=None):
    """The studio API base: `--base-url` → `machine.url` → `studio.url` (SPEC §2)."""
    if base_url and base_url.strip():
        return base_url.strip().rstrip("/")
    found = read_private(state_dir(env) / "machine.url")
    if not found:
        found = read_private(_home_state(env) / "studio.url")
    return found.rstrip("/")


def key_headers(key):
    """The key always travels in the `x-ds-key` header, never a query string."""
    return {"x-ds-key": key}


def handshake(base_url, key, *, timeout=20):
    """Prove the key is accepted. Returns (ok, summary) — summary holds no key."""
    if not key:
        return False, {"code": "NO_KEY", "message": "DS_KEY not set in env"}
    status, body = _http("POST", base_url.rstrip("/") + "/api/studio/checkin",
                         key=key, body={}, timeout=timeout)
    if status != 200 or not body.get("ok"):
        return False, {"code": body.get("code") or "HTTP_%d" % status,
                       "message": body.get("message") or "check-in refused"}
    return True, {"ok": True, "line": body.get("line")}


# --- HTTP --------------------------------------------------------------------

def _http(method, url, *, key=None, body=None, timeout=20):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("content-type", "application/json")
    req.add_header("User-Agent", STUDIO_USER_AGENT)
    if key:
        for h, v in key_headers(key).items():
            req.add_header(h, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"error": raw[:200]}
    except (urllib.error.URLError, TimeoutError) as e:
        # Could not tell whether the server saw it: UNKNOWN, never "failed".
        return 0, {"code": "TRANSPORT_UNKNOWN", "message": str(e)[:200]}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is never followed: the bytes come from the address asked for."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# --- photo handling ----------------------------------------------------------

def sniff_image(header):
    """The image content type of a file header, or None. No library needed."""
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
        return "image/webp"
    if len(header) >= 12 and header[4:8] == b"ftyp" and header[8:12] in (
            b"heic", b"heix", b"hevc", b"mif1"):
        return "image/heic"
    for magic, ctype in IMAGE_MAGIC:
        if header.startswith(magic):
            return ctype
    return None


def photo_request(path):
    """Build the /api/studio/uploads body for a photo, or refuse.

    The bytes never pass through this function's caller into the worker: the
    worker returns a presigned PUT and the phone uploads DIRECT (U2 README).
    Refusals are loud and non-zero — an unsupported or oversized file is named,
    never silently downgraded.
    """
    return upload_request(path, channel="image")


def upload_request(path, channel=None, upload_kind=None):
    """Build the service request, checking file bytes, extension and channel cap."""
    p = pathlib.Path(path)
    if not p.is_file():
        raise LedgerError("NO_FILE", "photo not found: %s" % p.name)
    if upload_kind is not None and upload_kind not in UPLOAD_KINDS:
        raise LedgerError("UNSUPPORTED_KIND",
                          "upload_kind must be intake or r2_fallback")
    size = p.stat().st_size
    if size <= 0:
        raise LedgerError("EMPTY_FILE", "photo is empty: %s" % p.name)
    ext = p.suffix.lower().lstrip(".")
    kind = UPLOAD_TYPES.get(ext)
    if kind is None or (channel is not None and channel != kind[0]
                        and not (ext == "webm" and channel == "audio")):
        raise LedgerError("UNSUPPORTED_TYPE", "file format is not accepted for this channel")
    channel = channel or kind[0]
    ctype = "audio/webm" if ext == "webm" and channel == "audio" else kind[1]
    cap = MAX_UPLOAD_BYTES[channel]
    if size > cap:
        raise LedgerError("TOO_BIG", "%s is %d bytes; cap is %d"
                          % (p.name, size, cap))
    with p.open("rb") as fh:
        header = fh.read(HEADER_SNIFF_BYTES)
    signatures = {"png": (b"\x89PNG",), "jpg": (b"\xff\xd8\xff",),
                  "jpeg": (b"\xff\xd8\xff",), "webp": (b"RIFF",),
                  "wav": (b"RIFF",), "ogg": (b"OggS",),
                  "webm": (b"\x1a\x45\xdf\xa3",),
                  "mp3": (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")}
    matches = (header[4:8] == b"ftyp" if ext in ("heic", "m4a", "mov", "mp4")
               else any(header.startswith(sig) for sig in signatures.get(ext, ())))
    if len(header) < 4 or not matches:
        raise LedgerError("UNSUPPORTED_TYPE",
                          "%s is not a recognised photo format" % p.name)
    body = {
        "channel": channel,
        "filename": p.name,
        "size_bytes": size,
        "content_type": ctype,
        "header_bytes": list(header[:16]),
    }
    if upload_kind is not None:
        body["upload_kind"] = upload_kind
    return body


def _put_file(url, file_handle, content_type, size, *, timeout=120):
    """Stream file bytes directly to R2; no presented key is forwarded."""
    req = urllib.request.Request(url, data=file_handle, method="PUT",
                                 headers={"Content-Type": content_type,
                                          "Content-Length": str(size),
                                          "User-Agent": STUDIO_USER_AGENT})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def upload_file(path, *, channel=None, upload_kind=None, env=None, post=None, put=None):
    """POST metadata then PUT bytes. Returns identifiers only, never a signed URL."""
    key = load_key(env)
    if not key:
        raise LedgerError("NO_KEY", "DS_KEY not set in env")
    body = upload_request(path, channel, upload_kind)
    base = (resolve_base_url(None, env) or STUDIO_BASE_URL).rstrip("/")
    status, result = (post or _http)("POST", base + "/api/studio/uploads",
                                    key=key, body=body)
    if status == 0:
        raise LedgerError("TRANSPORT_UNKNOWN", "upload request outcome is unknown")
    if status != 201 or not result.get("ok"):
        raise LedgerError("UPLOAD_REFUSED", "upload request refused (HTTP %d)" % status)
    upload = result.get("upload") or {}
    object_path = result.get("object_path", "")
    upload_id = result.get("upload_id", "")
    parts = urllib.parse.urlsplit(upload.get("url", ""))
    # Validate the destination before sending any file bytes; no redirects.
    expected_segment = UPLOAD_SEGMENT[upload_kind or "intake"]
    segments = parts.path.split("/")
    bucket = segments[1] if len(segments) > 1 else ""
    if (parts.scheme != "https" or parts.username or parts.password or parts.port
            or not re.fullmatch(r"[a-f0-9]{32}\.r2\.cloudflarestorage\.com", parts.hostname or "")
            or not re.fullmatch(r"clients/c-[a-f0-9]{32}/" + expected_segment
                                + r"/u_[a-f0-9]{24}\.[a-z0-9]+", object_path)
            or not bucket
            or parts.path != "/" + bucket + "/" + object_path
            or upload_id != object_path.rsplit("/", 1)[-1].split(".")[0]
            or upload.get("content_type") != body["content_type"]):
        raise LedgerError("UPLOAD_RESPONSE_INVALID", "storage upload response is invalid")
    with pathlib.Path(path).open("rb") as fh:
        if (os.fstat(fh.fileno()).st_size != body["size_bytes"]
                or list(fh.read(16)) != body["header_bytes"]):
            raise LedgerError("FILE_CHANGED", "file changed before upload")
        fh.seek(0)
        put_status = (put or _put_file)(upload["url"], fh, upload["content_type"], body["size_bytes"])
    if put_status == 0:
        raise LedgerError("TRANSPORT_UNKNOWN", "storage upload outcome is unknown")
    if put_status // 100 != 2:
        raise LedgerError("UPLOAD_PUT_REFUSED", "storage upload refused (HTTP %d)" % put_status)
    return {"upload_id": upload_id, "object_path": object_path}


def upload_fallback_video(path, **options):
    """The production writer for the R2 fallback copy of a finished video.

    The copy lands under `clients/<id>/video/` (the studio's own 7-day object,
    decision 5) instead of `intake/`. It is the same uploader, not a second
    control service: the module still only answers "which link may be handed
    over", and this only decides where the studio's own copy is stored.
    """
    return upload_file(path, channel="video", upload_kind="r2_fallback", **options)


# --- delivery ----------------------------------------------------------------

def delivery_record(run_dir, order_id, final_path):
    """The delivery record for the finished video, or refuse when it is absent.

    A delivery that cannot name a real, hashed file is never posted.
    """
    fp = pathlib.Path(final_path)
    if not fp.is_file():
        raise LedgerError("NO_FINAL_MEDIA", "final media not found: %s" % fp.name)
    digest = _sha256_file(fp)
    return {
        "order_id": order_id,
        "run_dir": str(run_dir),
        "path": str(fp),
        "bytes": fp.stat().st_size,
        "sha256": digest,
    }


def _sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


# --- owned-run cleanup receipt ----------------------------------------------

#: Run-owned disposable trees (plan 3.10/§3.11): unreferenced source downloads,
#: failed renders, rejected alternatives, extraction trees, disposable copies.
DISPOSABLE_DIRS = ("extraction", "extraction_trees", "source_downloads",
                   "failed", "failed_renders", "rejected", "alternatives",
                   "rejected_alternatives", "disposable_copies", "tmp")
#: Never removed here: final media, and the small receipts a completed run keeps.
PROTECTED_DIRS = ("receipts", "intake", "replay", "approval", "approvals",
                  "spend", "characters", "final", "delivery")


def cleanup_plan(run_dir):
    """Classify a run dir into run-owned disposable paths and protected ones."""
    root = pathlib.Path(run_dir).resolve()
    if not root.is_dir():
        raise LedgerError("NO_RUN_DIR", "run dir not found: %s" % root.name)
    disposable, protected = [], []
    for child in sorted(root.iterdir()):
        bucket = disposable if _is_disposable(child.name) else protected
        bucket.append({"name": child.name, "dir": child.is_dir()})
    return {"run_dir": str(root), "disposable": disposable, "protected": protected}


def _is_disposable(name):
    if name in PROTECTED_DIRS:
        return False
    if name in DISPOSABLE_DIRS:
        return True
    return name.endswith(".tmp") or name.endswith(".partial")


def write_cleanup_receipt(run_dir, out_path=None):
    """Write the owned-run cleanup receipt. Deletes nothing — plan it, then commit."""
    plan = cleanup_plan(run_dir)
    receipt = {"kind": "owned-run-cleanup-receipt", "run_dir": plan["run_dir"],
               "disposable": plan["disposable"], "protected": plan["protected"],
               "removed": [], "protected_left": [d["name"] for d in plan["protected"]]}
    out = pathlib.Path(out_path) if out_path else pathlib.Path(plan["run_dir"]) / "owned-run-cleanup-receipt.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt["receipt_path"] = str(out)
    return receipt


def apply_cleanup(receipt, run_dir):
    """Remove ONLY the receipt's disposable entries, inside the run dir."""
    root = pathlib.Path(run_dir).resolve()
    removed = []
    for entry in receipt.get("disposable", []):
        target = (root / entry["name"]).resolve()
        if root not in target.parents:  # never escape the run dir
            continue
        if not target.exists():
            continue
        if target.is_dir():
            import shutil
            shutil.rmtree(target)
        else:
            target.unlink()
        removed.append(entry["name"])
    receipt["removed"] = removed
    return receipt


# --- board (quiet) -----------------------------------------------------------

class Board:
    """The studio board, quiet by construction.

    One emit per (run, message) — the ledger's UNIQUE guard means a re-emit is a
    refusal, so a retry loop can never duplicate a card. `sender` is any
    callable, so this stays testable and does not hard-bind cc_sync.
    """

    def __init__(self, ledger, sender):
        self.ledger = ledger
        self.sender = sender
        self.emitted = []

    def emit(self, run_id, order_id, stage, payload):
        mid = message_id(order_id, stage, payload.get("seq", 0))
        if not self.ledger.record_message(run_id, mid, kind=stage):
            return False  # already emitted: stay quiet, do not send twice
        self.sender(run_id, order_id, stage, payload)
        self.emitted.append(mid)
        return True


# --- CLI ---------------------------------------------------------------------

#: Capability-bearing links (a studio URL whose fragment/query carries a key)
#: never appear in routine diagnostics. A deliberate client handoff prints the
#: link through `link` / wake_agent.sh's message — the authorized delivery
#: route — and never through `_emit`.
CAPABILITY_LINK = re.compile(
    r"https?://[^\s\"']*(?:[#?&][^\s\"']*(?:key|token|k)=)[^\s\"']*", re.I)


def redact_links(value):
    """Scrub capability-bearing links out of any diagnostic structure."""
    if isinstance(value, str):
        return CAPABILITY_LINK.sub("[redacted-link]", value)
    if isinstance(value, dict):
        return {k: redact_links(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_links(v) for v in value]
    return value


def _emit(obj):
    print(json.dumps(redact_links(obj), indent=2, sort_keys=True))


def cmd_handshake(args):
    ok, summary = handshake(args.base_url, load_key())
    _emit(summary)
    return EXIT["ok"] if ok else EXIT["refused"]


def cmd_claim(args):
    with ClaimLedger(args.db) as led:
        if led.claim_order(args.order, args.owner):
            st = led.order_state(args.order) or {}
            _emit({"order_id": args.order, "owner": args.owner, "won": True,
                   "fence": st.get("fence"),
                   "claim_token": st.get("claim_token"),
                   "state": st.get("state")})
            return EXIT["ok"]
    _emit({"order_id": args.order, "won": False,
           "code": "ALREADY_CLAIMED",
           "message": "another run holds this order"})
    return EXIT["refused"]


def cmd_notice(args):
    with ClaimLedger(args.db) as led:
        notice = led.notice_gate(args.order, reminder_after_s=args.reminder_after_s)
    if notice is None:
        _emit({"order_id": args.order, "notice": None})
        return EXIT["ok"]
    _emit({"order_id": args.order, "notice": notice})
    return EXIT["ok"]


def cmd_lease(args):
    with ClaimLedger(args.db) as led:
        won = led.lease_acquire(args.name, args.owner, ttl_s=args.ttl)
        holder = led.lease_holder(args.name)
    _emit({"name": args.name, "owner": args.owner, "won": won, "holder": holder})
    return EXIT["ok"] if won else EXIT["refused"]


def cmd_status(args):
    key = load_key()
    if not key:
        _emit({"code": "NO_KEY", "message": "DS_KEY not set in env"})
        return EXIT["refused"]
    body = {"event": args.event}
    if bool(args.delivery_url) != bool(args.delivery_kind):
        _emit({"code": "AF-DS-DELIVERY-KIND",
               "message": "--delivery-url and --delivery-kind go together"})
        return EXIT["refused"]
    if args.delivery_url:
        body["delivery"] = {"url": args.delivery_url, "kind": args.delivery_kind}
    status, body = _http("POST",
                         args.base_url.rstrip("/") + "/api/studio/orders/%s/state" % args.order,
                         key=key, body=body)
    if status == 0:
        _emit({"code": "TRANSPORT_UNKNOWN", "message": body.get("message", "")})
        return EXIT["undefined"]
    if status // 100 != 2 or not body.get("ok"):
        _emit({"code": body.get("code") or "HTTP_%d" % status,
               "message": body.get("message") or "status refused"})
        return EXIT["refused"]
    _emit({"ok": True, "order": body.get("order", {})})
    return EXIT["ok"]


def cmd_deliver(args):
    try:
        record = delivery_record(args.run_dir, args.order, args.final)
    except LedgerError as e:
        _emit({"code": e.code, "message": str(e)})
        return EXIT["refused"]
    _emit(record)
    return EXIT["ok"]


def cmd_photo(args):
    try:
        body = photo_request(args.path)
    except LedgerError as e:
        _emit({"code": e.code, "message": str(e)})
        return EXIT["refused"]
    _emit(body)
    return EXIT["ok"]


def cmd_upload(args):
    try:
        _emit(upload_file(args.path, channel=args.channel,
                          upload_kind=args.upload_kind))
        return EXIT["ok"]
    except LedgerError as exc:
        _emit({"code": exc.code, "message": str(exc)})
        return EXIT["undefined"] if exc.code == "TRANSPORT_UNKNOWN" else EXIT["refused"]


def cmd_cleanup_receipt(args):
    try:
        receipt = write_cleanup_receipt(args.run_dir, args.out)
        if args.apply:
            receipt = apply_cleanup(receipt, args.run_dir)
    except LedgerError as e:
        _emit({"code": e.code, "message": str(e)})
        return EXIT["refused"]
    _emit(receipt)
    return EXIT["ok"]


# --- enroll / link (SPEC §6) -------------------------------------------------

def _refusal(out, status, what):
    if status == 0:
        _emit({"code": "TRANSPORT_UNKNOWN", "message": out.get("message", "")})
        return EXIT["undefined"]
    _emit({"code": out.get("code") or "HTTP_%d" % status,
           "message": out.get("message") or ("%s refused" % what)})
    return EXIT["refused"]


#: A state file's required mode on platforms that enforce POSIX permissions.
PRIVATE_FILE_MODE = 0o600
PRIVATE_DIR_MODE = 0o700


def _legacy_state(env=None):
    """The pre-contract home root when it is a STRAY OF THIS BOX — else None.

    Only the Contabo shape has a real split (contract root moved under
    /home/node/.openclaw while old writes sit in the ephemeral home leaf), so
    only there may a stranded key be adopted. An explicit DRAMA_STUDIO_STATE
    that is not the contract root is a DIFFERENT installation: never raided
    for identity, never merged.
    """
    root = state_dir(env)
    legacy = _home_state(env)
    if root == _contract_state(env) and root != legacy:
        return legacy
    return None


def _receipt(env=None, *, base_url=None):
    """Validate the COMPLETE enrolment receipt locally — no network (D24).

    Key presence alone is not readiness: the receipt is the pair (key, url)
    in ONE consistent state root with private permissions. `stray_key` is a
    valid identity stranded in the legacy home root (a pre-contract write on
    the one platform where the root moved); recovery adopts it, never
    re-enrols and never discards it.
    """
    root = state_dir(env)
    legacy = _legacy_state(env)
    key_path = root / "machine.key"
    url_path = root / "machine.url"
    stray_key = None
    if legacy is not None and not read_private(key_path):
        if read_private(legacy / "machine.key"):
            stray_key = legacy / "machine.key"
    has_key = bool(read_private(key_path)) or bool(stray_key)
    has_url = bool(read_private(url_path))
    key_mode = _mode_of(key_path)
    perms_ok = (key_mode is None or key_mode == PRIVATE_FILE_MODE) and (
        not stray_key)
    return {"state_root": str(root), "has_key": has_key, "has_url": has_url,
            "stray_key": str(stray_key) if stray_key else None,
            "key_permissions": ("0%o" % key_mode) if key_mode is not None else None,
            "complete": bool(has_key and has_url and perms_ok and not stray_key),
            "base_url": (base_url or "").strip() or None}


def _mode_of(path):
    try:
        return pathlib.Path(path).stat().st_mode & 0o777
    except OSError:
        return None


def _recover_receipt(env=None, *, base_url=None):
    """Complete an interrupted enrolment WITHOUT a second identity (D24).

    A key-only record (crash between the two writes), a stranded legacy-root
    key, or an over-open mode is repaired in place: the valid key is adopted
    or preserved, the missing machine.url is written from the configured
    address, and modes are tightened. No HTTP call happens here — a recovery
    must never mint a duplicate identity.
    """
    root = state_dir(env)
    legacy = _legacy_state(env)
    recovered = []
    if legacy is not None:
        stray = legacy / "machine.key"
        if not read_private(root / "machine.key") and read_private(stray):
            for name in ("machine.key", "machine.url"):
                src = legacy / name
                if read_private(src):
                    write_private(root / name, read_private(src) + "\n")
                    try:
                        src.unlink()
                    except OSError:
                        pass
                    recovered.append("adopted %s from %s" % (name, legacy))
    if not read_private(root / "machine.key"):
        return None, recovered  # nothing to recover: no identity at all
    if not read_private(root / "machine.url"):
        base = (base_url or "").strip() or resolve_base_url(None, env) or STUDIO_BASE_URL
        write_private(root / "machine.url", base.rstrip("/") + "\n")
        recovered.append("machine.url restored")
    for name in ("machine.key", "machine.url", "client.url"):
        p = root / name
        if p.is_file() and _mode_of(p) != PRIVATE_FILE_MODE:
            try:
                os.chmod(p, PRIVATE_FILE_MODE)
            except OSError:
                pass
            recovered.append("%s permissions tightened" % name)
    return root / "machine.key", recovered


def cmd_enroll(args):
    """Register this box ONCE; the key comes back once and is written 0600.

    A valid key is never replaced and never re-minted: a key-only or
    interrupted record is RECOVERED locally (`--resume`, also the default for
    an existing key) instead of contacting the studio again, so no duplicate
    identity can be created.
    """
    env = os.environ
    if load_key(env):
        rec = _receipt(env, base_url=args.base_url)
        if rec["complete"] and not args.resume:
            _emit({"code": "ALREADY_ENROLLED",
                   "message": "a machine key already exists; refusing to replace it"})
            return EXIT["refused"]
        key_path, recovered = _recover_receipt(env, base_url=args.base_url)
        if key_path is None:
            # An identity exists in a fallback root but none in this one:
            # never mint a second identity; --resume reconciles quietly.
            if args.resume:
                _emit({"ok": True, "already_enrolled": True, "recovered": False,
                       "changes": recovered})
                return EXIT["ok"]
            _emit({"code": "ALREADY_ENROLLED",
                   "message": "a machine key already exists; refusing to replace it"})
            return EXIT["refused"]
        rec = _receipt(env, base_url=args.base_url)
        _emit({"ok": True, "recovered": bool(recovered),
               "already_enrolled": rec["complete"] and not recovered,
               "changes": recovered, "machine_key": str(key_path),
               "machine_url": str(state_dir(env) / "machine.url")})
        return EXIT["ok"]
    secret = (env.get("DS_ENROLLMENT_SECRET") or "").strip()
    if not secret:
        _emit({"code": "NO_ENROLLMENT_SECRET",
               "message": "DS_ENROLLMENT_SECRET not set in env"})
        return EXIT["refused"]
    base = resolve_base_url(args.base_url, env) or STUDIO_BASE_URL
    body = {"enrollment_secret": secret}
    if args.label:
        body["label"] = args.label
    status, out = _http("POST", base + "/api/studio/enroll", body=body)
    if status // 100 != 2 or not out.get("ok") or not out.get("key"):
        return _refusal(out, status, "enroll")
    folder = state_dir(env)
    # key first, then url: a crash between the two leaves a key-only record,
    # which the next pass recovers in place (never re-enrols).
    write_private(folder / "machine.key", str(out["key"]).strip() + "\n")
    write_private(folder / "machine.url", base + "\n")
    _emit({"ok": True, "client_id": out.get("client_id"), "base_url": base,
           "machine_key": str(folder / "machine.key"),
           "machine_url": str(folder / "machine.url")})
    return EXIT["ok"]


def cmd_link(args):
    """Print the client's personal link; `--new` rotates it and saves `client.url`."""
    key = load_key()
    if not key:
        _emit({"code": "NO_KEY", "message": "no machine key; run enroll first"})
        return EXIT["refused"]
    base = resolve_base_url(args.base_url) or STUDIO_BASE_URL
    stored_path = state_dir() / "client.url"
    stored = read_private(stored_path)
    if stored and not args.new:
        print(stored)
        return EXIT["ok"]
    status, out = _http("POST", base + "/api/studio/link", key=key,
                        body={"rotate": bool(args.new)})
    link = str(out.get("link") or "").strip()
    if status // 100 != 2 or not out.get("ok") or not link:
        if out.get("exists"):
            # The active link's secret is not recoverable, only re-minted.
            _emit({"code": "LINK_UNAVAILABLE",
                   "message": "an active link exists but its value is not stored "
                              "here; run link --new to mint a fresh one"})
            return EXIT["refused"]
        return _refusal(out, status, "link")
    write_private(stored_path, link + "\n")
    print(link)
    return EXIT["ok"]


# --- optional Studio capability (SPEC 9.3, D24) ------------------------------
#
# The optional intake capability is modelled EXPLICITLY in the installation
# state (the persistent state root's capability.json) as one of
# disabled | needs-enrollment | ready | degraded. Chat intake never needs it;
# an idle optional poller reads `capability --gate` and stays quiet instead of
# failing every tick or auto-enrolling a chat-only user to silence logs.

CAPABILITY_STATES = ("disabled", "needs-enrollment", "ready", "degraded")
#: `capability --gate` exit: 0 = ready (poll), 10 = skip quietly.
GATE_READY, GATE_SKIP = 0, 10
#: Transitional delivery to the timer is one line per TRANSITION, never per tick.
CAPABILITY_FILE = "capability.json"


def _capability_path(env=None):
    return state_dir(env) / CAPABILITY_FILE


def cmd_state_dir(args):
    """Print the persistent state root — the ONE contract (D24) in one place.

    Shell callers (enroll-on-install.sh) resolve through this command instead
    of restating the platform rule and drifting from the bridge.
    """
    print(str(state_dir()))
    return EXIT["ok"]


def _read_capability(env=None):
    try:
        raw = _capability_path(env).read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_capability(record, env=None):
    p = _capability_path(env)
    write_private(p, json.dumps(record, indent=2, sort_keys=True) + "\n")
    return p


def _record_capability(state, env=None, *, now=None, error=None, note=None):
    """Merge one observation into capability.json (the installation state).

    `last_attempt_at` moves on every observation, `last_success_at` only on a
    proven-ready check. An error carries its own `at`; a reader marks it
    STALE once `last_success_at` passes it — old log tails are then never
    reported as new failures.
    """
    ts = time.time() if now is None else now
    rec = _read_capability(env)
    rec["capability"] = state
    rec["updated_at"] = ts
    rec["last_attempt_at"] = ts
    if state == "ready":
        rec["last_success_at"] = ts
        rec.pop("last_error", None)
    elif error:
        rec["last_error"] = {"at": ts, "code": str(error.get("code") or "ERROR"),
                             "message": str(error.get("message") or "")[:200]}
    if note:
        rec["last_note"] = str(note)[:200]
    try:
        _write_capability(rec, env)
    except OSError:
        pass  # a read-only state root must never break the caller's flow
    return rec


def _capability_view(rec, *, now=None):
    """The record as routine diagnostics see it: no link value, staleness set."""
    ts = time.time() if now is None else now
    out = {k: v for k, v in rec.items() if k != "last_error"}
    err = rec.get("last_error")
    if isinstance(err, dict):
        out["last_error"] = dict(err)
        out["last_error"]["stale"] = bool(
            rec.get("last_success_at") and
            float(err.get("at") or 0) <= float(rec.get("last_success_at") or 0))
    out["link_present"] = bool(read_private(state_dir() / "client.url"))
    return out


def _capability_state(env=None, *, base_url=None, probe=None, recover=False):
    """Compute the live capability state from observed facts — never logs.

    disabled         no key and no enrolment intent (a chat-only install)
    needs-enrollment no key, but the operator injected an enrolment secret
    ready            the complete receipt validates and the handshake answers
    degraded         a key exists but the receipt is incomplete/unhealthy
                     (recoverable in place; never re-enrols, never drops key)
    """
    if recover:
        _recover_receipt(env, base_url=base_url)
    rec = _receipt(env, base_url=base_url)
    saved = _read_capability(env)
    if not rec["has_key"]:
        state = "needs-enrollment" if saved.get("intent") == "needs-enrollment" \
            else "disabled"
        return state, None
    if not rec["complete"]:
        return "degraded", {"code": "RECEIPT_INCOMPLETE",
                            "message": "key present but the enrolment receipt is "
                                       "incomplete (key=%s url=%s root-consistent=%s)"
                                       % (rec["has_key"], rec["has_url"],
                                          not rec["stray_key"])}
    probe = handshake if probe is None else probe
    ok, summary = probe(base_url or resolve_base_url(None, env) or STUDIO_BASE_URL,
                        load_key(env))
    if ok:
        return "ready", None
    return "degraded", {"code": str(summary.get("code") or "HANDSHAKE_REFUSED"),
                        "message": str(summary.get("message") or "handshake refused")}


def cmd_capability(args):
    """Model the optional Studio capability in the installation state (D24)."""
    env = os.environ
    now = time.time()
    if args.record:
        if args.record not in CAPABILITY_STATES:
            _emit({"code": "BAD_CAPABILITY", "message": args.record})
            return EXIT["refused"]
        saved = _read_capability(env)
        if load_key(env) or saved.get("capability") in ("ready", "degraded"):
            # an observed enrolment is never downgraded by an install pass
            _emit({"ok": True, "capability": saved.get("capability") or "present",
                   "kept": True})
            return EXIT["ok"]
        rec = _record_capability(args.record, env, now=now)
        if args.record == "needs-enrollment":
            rec = _read_capability(env)
            rec["intent"] = "needs-enrollment"
            _write_capability(rec, env)
        elif args.record == "disabled":
            rec = _read_capability(env)
            rec.setdefault("intent", "disabled")
            _write_capability(rec, env)
        _emit({"ok": True, "capability": args.record})
        return EXIT["ok"]
    # live evaluation
    prev = _read_capability(env).get("capability")
    state, err = _capability_state(env, base_url=args.base_url,
                                   probe=None if not args.no_network else
                                   (lambda _b, _k: (True, {"ok": True})),
                                   recover=args.repair)
    _record_capability(state, env, now=now, error=err)
    view = _capability_view(_read_capability(env), now=now)
    if args.gate:
        if state != prev:
            # ONE transition line, to stderr; silence on every later tick.
            sys.stderr.write("drama-studio: capability %s -> %s%s\n"
                             % (prev or "unset", state,
                                (" (%s)" % err["code"]) if err else ""))
        return GATE_READY if state == "ready" else GATE_SKIP
    _emit(view)
    return EXIT["ok"] if state == "ready" else EXIT["refused"]


# --- poll (SPEC §6) ----------------------------------------------------------

def _board_epic(skill_root, order_id, title):
    """One epic card when `CC_WORKSPACE` is set; a silent skip when it is not."""
    if not (os.environ.get("CC_WORKSPACE") or "").strip():
        return
    core = str(pathlib.Path(skill_root) / "scripts" / "core")
    if core not in sys.path:
        sys.path.insert(0, core)
    try:
        from cc_sync import Outbox  # noqa: PLC0415
        from batch_mode.batch import STAGES  # noqa: PLC0415
        out = Outbox(run_id=order_id)
        out.enqueue_create(job_id=order_id, show_name=title,
                           stages=[{"slug": s[0]} for s in STAGES],
                           workspace=out.workspace,
                           department="video",
                           title_prefix="Drama Song Ad")
        out.flush()
    except Exception as exc:  # noqa: BLE001 - a down board never stops the order
        sys.stderr.write("studio_bridge: board card not created: %s\n" % exc)


#: The card's own step line: the one place its question count is written out
#: (`intake_card.render_step`). A recap, a waiting answer or a locked-in run
#: prints no step line at all.
QUESTION_LINE = re.compile(r"Question (\d+) of (\d+)")

#: A new-page reply: "<n>. <option text>" (S75-059). The card parses a NUMBER,
#: so the number is what it receives - the text after it is checked first.
NUMBERED_REPLY = re.compile(r"^\s*(\d+)\s*\.\s*(.+?)\s*$")

#: The durable halt record for a replay (S75-106). While it exists the order
#: waits on the client and `_replay` runs NO turn, so one refused order can never
#: loop a card turn on every poll.
REPLAY_HALTED_FILE = "replay-halted.json"

#: The client's own sentence for a halted replay. One plain line per cause; the
#: machine code is the operator's, on stderr, never the client's.
HALT_SECOND_SENTENCE = ("One of your answers did not match the choices. "
                        "Open your order and tap Continue to fix it.")
HALT_SENTENCES = {
    "testimonial-permission-pending":
        "Your order is paused until you have your client's OK to use their "
        "story. Open your order and tap Continue when you have it.",
    "INVALID_OPTION": HALT_SECOND_SENTENCE,
    "INTAKE_REPLAY_MISMATCH": HALT_SECOND_SENTENCE,
}
HALT_DEFAULT = ("Your studio is not ready to start this order. We have been "
                "told. You do not need to do anything.")


def _skill_core(skill_root):
    """`<skill 75>/scripts/core` on `sys.path`, so the bridge reads the skill's
    own modules instead of carrying a second copy of any of them."""
    core = str(pathlib.Path(skill_root).expanduser() / "scripts" / "core")
    if core not in sys.path:
        sys.path.insert(0, core)
    return core


# --- the Agnes records on the check-in (SPEC A2, A11) ------------------------

def remembered_agnes(skill_root, client_dir):
    """The client's remembered Agnes answer: "yes", "no" or "unknown" (SPEC A2).

    Read through `agnes_access`, the one module that owns
    `<client data folder>/agnes.json` - never a second reader of that file. A
    skill copy that has no such module yet reads "unknown", which is exactly what
    the card and the studio page show for a client who has not answered, so the
    two can never disagree with this. Only the stored answer leaves here: never a
    key, never a plan, never the file itself.
    """
    _skill_core(skill_root)
    try:
        from agnes_access import agnes_access as AG  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - a copy without the module still checks in
        return "unknown"
    try:
        answer = AG.remembered(client_dir)
    except (OSError, TypeError, ValueError):
        return "unknown"
    return answer if answer in ("yes", "no") else "unknown"


def active_agnes_progress(runs_root):
    """The run under `runs_root` still making Agnes clips, and its
    `control/agnes-progress.json` (SPEC A11).

    That record is the small one `agnes_quota.progress` writes - clips done and
    total, in flight, waiting reason, ETA, updated time - no secret and no key on
    it. Returns None while no run has an unfinished job, so the ordinary
    check-in still carries its one field and no more.
    """
    try:
        runs = [p for p in pathlib.Path(runs_root).expanduser().iterdir()
                if p.is_dir() and ORDER_ID.fullmatch(p.name)]
    except OSError:
        return None
    picked, picked_at = None, -1.0
    for run in runs:
        path = run / "control" / "agnes-progress.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            seen = path.stat().st_mtime
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        total, done = record.get("clips_total"), record.get("clips_done")
        if not isinstance(total, int) or not isinstance(done, int) or done >= total:
            continue                      # finished, or not a progress record
        if seen > picked_at:
            picked, picked_at = (run.name, record), seen
    if picked is None:
        return None
    order_id, record = picked
    return dict(record, order_id=order_id)


def checkin_body(skill_root, runs_root, client_dir=None):
    """The check-in body (SPEC A11): the remembered Agnes answer, and the active
    run's progress record while its Agnes job is still running."""
    body = {"agnes_remembered": remembered_agnes(skill_root, client_dir)}
    progress = active_agnes_progress(runs_root)
    if progress is not None:
        body["agnes_progress"] = progress
    return body


# --- the replay guard (SPEC B1) ----------------------------------------------

def _card_replay(skill_root, replies, client_dir=None):
    """The card's own reading of these replies - the ONE judge (SPEC B1).

    Drops the trailing recap confirmation the studio page appends
    (`mini-app/ui/studio.js:470`), replays the rest through the card's own
    `conversation`, and returns `(accepted question ids, questions asked, done)`.
    `questions` is the "Question N of M" total the card is on, or None when it
    reached its recap, a waiting answer or a locked-in run (it completed what it
    asked) - so no step line and no count to refuse against. None when the
    installed card has no purpose flow to judge against, and None on any card
    fault: a claim never dies on this import.
    """
    _skill_core(skill_root)
    try:
        from choice_card.intake_card import intake_card as IC  # noqa: PLC0415
        if getattr(IC, "_shaped", None) is None:
            return None
        if "purpose_flow" not in inspect.signature(IC.conversation).parameters:
            return None
        given = [str(r) for r in replies]
        if given and given[-1].strip().lower() in \
                tuple(getattr(IC, "_YES", ()) or ("yes",)):
            given = given[:-1]           # the recap confirmation is not an answer
        if not given:
            return None
        state = IC.conversation(given, client_dir=client_dir, purpose_flow=True)
    except Exception:  # noqa: BLE001 - never stop a claim on a card import
        return None
    ids = [str(a.get("id") or "") for a in (state.get("answers") or [])]
    found = QUESTION_LINE.search(str(state.get("message") or ""))
    questions = int(found.group(2)) if found else None
    return ids, questions, bool(state.get("done"))


def _question_mismatch(skill_root, replies, client_dir=None):
    """`(answers the card accepted, questions it asked)` when the replies cannot
    complete the question list, else None.

    The card rebuilds that list from these replies with `_shaped`
    (SPEC B1) - the same rebuild the studio page's `shows_when` screens were
    built from - so a set the card cannot finish means the phone showed a
    different list than this card asks. Replaying anyway would answer one screen
    with another screen's number: a shifted run, which is what this refuses.

    The card is the judge, never a list this bridge re-derives (its shape can
    differ from a second `_shaped` call over `QUESTIONS`, and counting against a
    re-derived list refuses orders the card itself completed). A step line with
    fewer accepted answers than questions means the card ran out, or a reply did
    not fit and the rest shifted: that is the refusal, and those are the two
    counts named back. Extra replies past a complete list are absorbed by the
    card itself (a "change line N" or a recap), never a mismatch here.

    None when the installed card has no purpose flow to count against, and None
    on any card fault: a claim never dies on this import.
    """
    replay = _card_replay(skill_root, replies, client_dir)
    if replay is None:
        return None
    ids, questions, done = replay
    if done or questions is None or questions <= 0 or len(ids) >= questions:
        return None
    return len(ids), questions


def _reply_id_mismatch(skill_root, reply_ids, replies, client_dir=None):
    """The page's screen ids against the ids the card itself asks, in order.

    Every answer travels with the id of the screen it was given on (S75-106
    step 5). A page that numbered its screens differently would replay one
    screen's answer onto another question, so the card's own ids judge it. The
    page's trailing recap confirmation carries its own id and is not a card
    question: one extra trailing id is allowed, and only the card's own
    positions are compared. None when the page sent no ids (an old page - the
    count check rules), when the card cannot judge, or when the ids agree.
    """
    if not isinstance(reply_ids, (list, tuple)) or not reply_ids:
        return None
    replay = _card_replay(skill_root, replies, client_dir)
    if replay is None:
        return None
    ids = replay[0]
    page = [str(x) for x in reply_ids]
    if len(page) not in (len(ids), len(ids) + 1) or page[:len(ids)] != ids:
        return page, ids
    return None


def _option_slot(q):
    """True when a screen offers a slot for the client's own words.

    An option whose detail opens "reply with" is a box, not a label - the page's
    own rule (`studio.js:isFreeTextOption`) - so the text after its number is
    the client's answer, never a choice to be judged.
    """
    for opt in q.get("options") or []:
        detail = (opt[1] if isinstance(opt, (tuple, list)) and len(opt) > 1
                  else "")
        if str(detail or "").strip().lower().startswith("reply with"):
            return True
    return False


def _plain_replies(skill_root, replies, client_dir=None):
    """The page's replies as the card reads them, and the first text mismatch.

    A new page sends each choice reply as "<n>. <option text>" (S75-059). The
    card parses a NUMBER, so a choice reply is reduced to its number - after
    the text after the number is checked against the box card's own option for
    that screen, case-insensitive and trimmed. A typed brief answer is never
    numbered and never reduced: the page sends it as the client wrote it.

    Returns `(replies_for_the_card, mismatch)`. `mismatch` is
    `(position, question_id, page_text, card_text)` at the first screen whose
    text the card does not ask - the caller halts the order with the second
    sentence instead of replaying one screen's answer onto another question. A
    page with no numbered reply (an old page) is returned unchanged, and so is
    any list when the installed card cannot judge: a claim never dies on this.
    """
    given = [str(r) for r in (replies or [])]
    if not any(NUMBERED_REPLY.match(r) for r in given):
        return given, None
    _skill_core(skill_root)
    try:
        from choice_card.intake_card import intake_card as IC  # noqa: PLC0415
        if getattr(IC, "_shaped", None) is None:
            return given, None
        if "purpose_flow" not in inspect.signature(IC.conversation).parameters:
            return given, None
        plain, accepted = [], []
        for at, reply in enumerate(given):
            qs = IC._shaped(IC.QUESTIONS, accepted, client_dir)
            if len(accepted) >= len(qs):
                plain.append(reply)         # past the last question: the recap
                continue
            q = qs[len(accepted)]
            found = NUMBERED_REPLY.match(reply)
            if q.get("free_text"):          # a typed brief answer: as written
                plain.append(reply)
                answer = IC._parse(reply, q)
            elif found is None:             # an old page: a bare number, amount
                plain.append(reply)
                answer = IC._parse(reply, q)
            else:
                n, text = int(found.group(1)), found.group(2).strip()
                opts = q.get("options") or []
                card_text = (str(opts[n - 1][0]).strip()
                             if 1 <= n <= len(opts) else None)
                if (card_text is not None
                        and text.casefold() == card_text.casefold()):
                    plain.append(str(n))
                    answer = IC._parse(str(n), q)
                elif _option_slot(q):
                    # a box for the client's own words: the number carried the
                    # answer, so the text is what the card reads
                    plain.append(text)
                    answer = IC._parse(text, q)
                else:
                    return given, (at, str(q.get("id") or ""), text, card_text)
            if isinstance(answer, dict) and "error" not in answer:
                accepted.append(answer)
    except Exception:  # noqa: BLE001 - never stop a claim on a card import
        return given, None
    return plain, None


def _refuse_mismatch(base, key, order_id, mismatch):
    """Refuse a replay whose reply count cannot complete the question list.

    The order is NOT cancelled. It is claimed, so the studio's own lifecycle
    (`mini-app/service/src/lifecycle.js`: `in_production -> needs_you`) accepts
    a `needs_you` event, and the client sees one plain card asking for a second
    look instead of a dead order. This is the OLD-PAGE fallback (an order with no
    `reply_ids`); `cmd_poll` releases the claim after this refusal, so the box
    checks in and can see other orders - a refused order never blocks it - and
    the run never starts shifted.

    The reply posted to the service is the client's sentence only; the two
    counts travel to the operator on stderr, and in the JSON line on stdout.
    A claim post that was itself refused leaves the order `waiting`, where
    `needs_you` is not a legal move: the studio answers 409, which is accepted
    and logged here - a refused state post never becomes a failed poll.
    """
    given, questions = mismatch
    reason = ("REPLAY_QUESTION_MISMATCH: %d replies cannot complete the %d "
              "questions of this card" % (given, questions))
    status, out = _http("POST",
                        base.rstrip("/") + "/api/studio/orders/%s/state" % order_id,
                        key=key,
                        body={"event": "needs_you",
                              "reason": "A few of your answers need a second "
                                        "look. Open your studio page and tap "
                                        "Continue."})
    posted = bool(status and status // 100 == 2 and out.get("ok"))
    sys.stderr.write("studio_bridge: %s - order %s; needs_you %s%s\n"
                     % (reason, order_id, "posted" if posted else "refused",
                        "" if posted else " (HTTP %s %s)" % (
                            status, (out.get("code") or out.get("message")
                                     or "")[:200])))
    _emit({"code": "REPLAY_QUESTION_MISMATCH", "message": reason,
           "order_id": order_id, "replies": given, "questions": questions,
           "needs_you_posted": posted})
    return EXIT["refused"]


def _halt_sentence(code):
    """The client's sentence for a halt code; the code itself is the operator's."""
    return HALT_SENTENCES.get(str(code or ""), HALT_DEFAULT)


def _write_halted(run_dir, turn, state, fallback_code):
    """Write the durable halt record (S75-106) and return it.

    `{turn, question_id, reason_code, at}` - the reason code and the question id
    read from the card's own `--format session-json` answer, never invented here.
    """
    state = state if isinstance(state, dict) else {}
    record = {"turn": turn,
              "question_id": state.get("question_id"),
              "reason_code": (str(state.get("reason_code") or "").strip()
                              or fallback_code),
              "at": time.time()}
    control = pathlib.Path(run_dir) / "control"
    control.mkdir(parents=True, exist_ok=True)
    (control / REPLAY_HALTED_FILE).write_text(
        json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    return record


def _read_halted(run_dir):
    """The run's durable halt record, or None when there is none."""
    try:
        record = json.loads(
            (pathlib.Path(run_dir) / "control" / REPLAY_HALTED_FILE)
            .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def _halt_order(led, base, key, order_id, record):
    """One halted order waits on the client, in words, and the box moves on.

    Posts `needs_you` with the client's own sentence - a 409 is expected when
    the order never left `waiting` (its claim post was refused) and is accepted
    and logged, never a failed poll - writes the `replay_halted` receipt, and
    RELEASES the local claim so the next poll checks in and can see other
    orders: one refused order never blocks the box. The machine code goes to
    stderr for the operator, never to the client.
    """
    code = str(record.get("reason_code") or "REPLAY_HALTED")
    status, out = _http("POST",
                        base.rstrip("/") + "/api/studio/orders/%s/state" % order_id,
                        key=key,
                        body={"event": "needs_you",
                              "reason": _halt_sentence(code)})
    posted = bool(status and status // 100 == 2 and out.get("ok"))
    sys.stderr.write("studio_bridge: order %s halted (%s); needs_you %s%s\n"
                     % (order_id, code, "posted" if posted else "refused",
                        "" if posted else " (HTTP %s %s)" % (
                            status, (out.get("code") or out.get("message")
                                     or "")[:200])))
    led.write_receipt(order_id, "replay_halted", record)
    led.release_order(order_id, BRIDGE_OWNER)
    # Nothing on stdout: this is not a wake line. The timer hands every stdout
    # line to the wake script, which would report a line it cannot wake as a
    # failed wake - a false failure for an order that is simply waiting on its
    # client. The code and the order id are on stderr; the receipt and the halt
    # record both outlive the claim.
    return EXIT["ok"]


def _journaled_turns(session_path):
    """How many card turns the run's intake session has already journaled.

    0 when the session does not exist yet (a fresh run). A session that exists
    but cannot be read answers None: an unknown history must never restart a
    replay at the wrong turn, so the replay fails closed instead.
    """
    try:
        state = json.loads(session_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 0
    except (OSError, ValueError) as exc:
        _emit({"code": "REPLAY_SESSION_UNREADABLE", "message": str(exc)[:300]})
        return None
    events = state.get("events") if isinstance(state, dict) else None
    return len(events) if isinstance(events, list) else 0


def _session_state(proc):
    """A turn's `--format session-json` answer, or None when it printed none."""
    try:
        state = json.loads(proc.stdout)
    except (ValueError, TypeError):
        return None
    return state if isinstance(state, dict) else None


def _session_done(run_dir, state):
    """The session's own completion: True, False, or None when it cannot tell.

    The last turn's session-json is the first answer; the run's stored session
    (`control/intake-session.json`) answers for a card copy that prints text.
    None when neither exists - a skill copy with no durable session has no
    `done` to read, and an absent record is never a proven false.
    """
    if isinstance(state, dict) and isinstance(state.get("done"), bool):
        return state["done"]
    try:
        stored = json.loads((pathlib.Path(run_dir) / "control"
                             / "intake-session.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(stored, dict) and isinstance(stored.get("done"), bool):
        return stored["done"]
    return None


def _replay(skill_root, run_dir, replies):
    """Hand every reply back to the card, one turn per answer, in order.

    The card takes at most ONE new reply per turn: a fresh session refuses any
    reply before its question is presented (QUESTION_NOT_PRESENTED), and a turn
    carrying more than one new reply is refused (ONE_REPLY_AT_A_TIME). So the
    bridge primes the pending question with a no-reply turn, then plays the
    answers back as GROWING REPLAY PREFIXES: turn i carries replies[:i+1], and
    the session's own replay absorption (an already-journaled prefix replays as
    INTAKE_REPLAYED, a divergent one as INTAKE_REPLAY_MISMATCH) reduces each
    turn to its one new answer. Starting past the turns the session already
    journaled resumes an interrupted order without re-answering, and a shifted
    list still fails closed at the session's own prefix check. argv lists, never
    a shell.

    A turn that exits non-zero writes `control/replay-halted.json`
    `{turn, question_id, reason_code, at}` - the reason code read from the card's
    `--format session-json` answer - and the replay answers `halted`; while that
    file exists the replay answers `halted` WITHOUT running a turn, so one
    refused order never loops a card turn on every poll. It never answers ok for
    a session whose `done` is false: after the last turn the session's own
    completion is required.
    """
    run_dir = pathlib.Path(run_dir)
    control = run_dir / "control"
    if (control / REPLAY_HALTED_FILE).is_file():
        return EXIT["halted"], None      # already halted: run no turn
    factory = (pathlib.Path(skill_root).expanduser() / "scripts" / "core"
               / "intake_preflight" / "factory.py")
    if not factory.is_file():
        _emit({"code": "NO_FACTORY",
               "message": "factory.py not found under %s" % skill_root})
        return EXIT["refused"], factory
    base = [sys.executable, str(factory), "card", "--step",
            "--format", "session-json", "--run-dir", str(run_dir)]

    def _halt(turn, state, fallback):
        record = _write_halted(run_dir, turn, state, fallback)
        # stderr only: stdout is the wake line, and a halt has none to wake.
        sys.stderr.write("studio_bridge: replay halted at turn %s (%s)\n"
                         % (record["turn"], record["reason_code"]))
        return EXIT["halted"], factory

    def _turn(extra, turn):
        argv = list(base)
        for reply in extra:
            argv.extend(["--reply", str(reply)])
        try:
            done = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=600, cwd=str(skill_root))
        except (OSError, subprocess.SubprocessError) as exc:
            _emit({"code": "REPLAY_FAILED", "message": str(exc)[:300]})
            return EXIT["error"], factory
        state = _session_state(done)
        if done.returncode != 0:
            return _halt(turn, state, "INTAKE_TURN_REFUSED")
        return state or {}

    result = _turn((), 0)                # prime: the first question is presented
    if isinstance(result, tuple):
        return result
    state = result
    try:
        start = _journaled_turns(control / "intake-session.json")
        if start is None:
            return EXIT["error"], factory
        for i in range(start, len(replies)):
            result = _turn(replies[:i + 1], i + 1)
            if isinstance(result, tuple):
                return result
            state = result
    except (OSError, subprocess.SubprocessError) as exc:
        _emit({"code": "REPLAY_FAILED", "message": str(exc)[:300]})
        return EXIT["error"], factory
    if _session_done(run_dir, state) is False:
        return _halt(len(replies), state, "INTAKE_NOT_CONFIRMED")
    return EXIT["ok"], factory


def _ensure_run_state(skill_root, run_dir, order_id):
    """The run's state authority, created through the ONE writer (`state_store`).

    poll claims the order and replays the card, so the run folder exists and
    holds the client's answers; the very next command the agent is told to run
    (`factory.py next`) reads `control/state.sqlite3` (factory.py:501) and
    answers `state-file-missing` when it is not there. So poll creates it here,
    with the SAME `state_store.Store` INSTRUCTIONS step 5 writes through -- never
    a second writer, never a hand-written sqlite file. `init_run` is
    INSERT-OR-IGNORE, so a run already initialised stays untouched.

    Returns the stage list on success, or None when the store exists but
    refused the write (the poll then fails loudly instead of printing a `next`
    that cannot work). A skill copy with no store at all -- a test stub, a
    partial install -- warns on stderr and returns `[]`: the order still reaches
    the agent, who can run intake properly.
    """
    _skill_core(skill_root)
    try:
        from state_store import Store  # noqa: PLC0415
        from batch_mode.batch import STAGES  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 - a store-less copy still runs
        sys.stderr.write("studio_bridge: this skill copy has no state store "
                         "(%s); the run has no state authority yet\n"
                         % str(exc)[:200])
        return []
    db = pathlib.Path(run_dir) / "control" / "state.sqlite3"
    stages = [str(s[0]) for s in STAGES]
    try:
        with Store(db) as store:
            store.init_run(order_id, stages)
    except Exception as exc:  # noqa: BLE001 - a refused write fails the claim
        _emit({"code": "RUN_STATE_FAILED",
               "message": "could not create the run state through state_store:"
                          " %s" % str(exc)[:300],
               "path": str(db)})
        return None
    return stages

def _advance_claim(led, order_id, owner, fence, step, now=None,
                   stale_code="STALE_CLAIM"):
    """Move the claim one step, FENCED, and treat an already-recorded step as
    success (a resumed poll reconciles, it does not re-run). A fence from a
    taken-over claim is a named refusal and the caller must stop."""
    st = led.order_state(order_id)
    if st is None:
        _emit({"order_id": order_id, "code": stale_code,
               "message": "no live claim for this order"})
        return False
    if fence is not None and int(st.get("fence") or -1) != int(fence):
        _emit({"order_id": order_id, "code": stale_code,
               "message": "claim was taken over before %s" % step})
        return False
    cur = st.get("step") or STEP_CLAIMED
    if cur in STEPS and STEPS.index(step) <= STEPS.index(cur):
        return True                 # already recorded: idempotent resume
    if led.advance_step(order_id, owner, step, now=now, fence=fence):
        return True
    _emit({"order_id": order_id, "code": stale_code,
           "message": "claim was taken over before %s" % step})
    return False


def _terminal_state(order):
    """The studio's terminal state for this order, or None when it may run.

    The service projects `state` onto every order payload it returns
    (service/src/index.js: GET /api/studio/orders/<id> answers `project(...)`,
    and `project` sets `state` from `resolveOrderState`), so a cancellation is
    ON THE WIRE: `{"event": "cancel"}` moves a waiting or approval-stop order to
    `cancelled`, which is terminal (lifecycle.js TERMINAL_STATES).

    A payload with no usable `state` is NOT terminal. Recovery must never be
    blocked by a field an older service or a stub did not send: unknown is
    "keep resuming", which is exactly the pre-existing ST1 behaviour.
    """
    if not isinstance(order, dict):
        return None
    state = str(order.get("state") or "").strip().lower()
    return state if state in TERMINAL_ORDER_STATES else None


def _drop_terminal(led, order_id, state, via):
    """Carry the studio's terminal state: resume nothing, release the claim.

    No wake line is printed (a cancelled order must never start a run, a paid
    job or a client notice), and the local claim row is deleted so the startup
    scan stops offering this order. The receipt outlives the row, so the fact
    stays auditable after the claim is gone.
    """
    led.write_receipt(order_id, "remote_terminal", {"state": state, "via": via})
    led.release_order(order_id, BRIDGE_OWNER)
    return EXIT["ok"]


def _refresh_stored_line(led, order_id):
    """Re-point a stored poll line at the claim that is live now.

    The claim commit (studio_claim) and the `poll_line` receipt below are TWO
    SQLite commits. A process killed between them leaves the line frozen on the
    old fence and the old claim token. The refusal in `cmd_poll` must not leave
    it that way: every later poll would present the stale token, be refused,
    and report success — the line would stay wedged until the lease expired and
    a takeover rewrote it. Refreshing the line to the live claim keeps the
    receipt true, so the next poll resumes. Nothing is printed, the exit-code
    contract is unchanged, and only OUR OWN live claim is written: a line that
    already matches it is left alone, and another owner's claim is never
    recorded as ours.
    """
    st = led.order_state(order_id) or {}
    if not st or st.get("owner") != BRIDGE_OWNER:
        return False
    stored = next((r["payload"] for r in reversed(led.receipts(order_id))
                   if r["kind"] == "poll_line"), None)
    if not stored or stored.get("fence") == st.get("fence"):
        return False
    line = dict(stored)
    line["fence"] = st.get("fence")
    line["claim_token"] = st.get("claim_token")
    led.write_receipt(order_id, "poll_line", line)
    return True


# --- the order's uploaded files (S75-075) -----------------------------------

#: The uploads read route (U-Z08): raw bytes for a box-held key, and
#: `AF-DS-UP-NOT-ARRIVED` when the object never reached storage.
UPLOAD_FILE_ROUTE = "/api/studio/uploads/%s/file"
#: An upload id becomes one path segment, never a walk.
UPLOAD_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
#: content type -> (extension, channel). The extension names the saved file and
#: the channel picks the cap from `MAX_UPLOAD_BYTES`.
UPLOAD_FILE_TYPES = {
    "image/jpeg": ("jpg", "image"), "image/png": ("png", "image"),
    "image/heic": ("heic", "image"), "image/heic-sequence": ("heic", "image"),
    "image/webp": ("webp", "image"), "audio/mpeg": ("mp3", "audio"),
    "audio/mp4": ("m4a", "audio"), "audio/wav": ("wav", "audio"),
    "audio/x-wav": ("wav", "audio"), "audio/ogg": ("ogg", "audio"),
    "audio/webm": ("webm", "audio"), "video/mp4": ("mp4", "video"),
    "video/quicktime": ("mov", "video"), "video/webm": ("webm", "video"),
}
FILENAME_HEADER = re.compile(r'filename\s*=\s*"?([^";]+)"?', re.I)


def _upload_target(upload_id, content_type, disposition):
    """(file name, size cap) for one download.

    The extension comes from the service's own file name when it sends one,
    else from the bytes' content type. An unknown type keeps the largest cap
    the table holds and a `.bin` name: the file is never dropped for its name.
    """
    ctype = (content_type or "").split(";")[0].strip().lower()
    ext, channel = UPLOAD_FILE_TYPES.get(ctype, ("bin", "video"))
    named = FILENAME_HEADER.search(disposition or "")
    if named:
        suffix = pathlib.PurePosixPath(named.group(1).strip()).name
        suffix = suffix.rsplit(".", 1)[-1].lower() if "." in suffix else ""
        if suffix in UPLOAD_TYPES:
            ext = suffix
    return upload_id + "." + ext, MAX_UPLOAD_BYTES[channel]


def _fetch_uploads(base, key, order, run_dir, *, timeout=120):
    """Download each `upload_ids` file into `<run>/intake/uploads/<id>.<ext>`.

    Runs before the intake replay, so the photos and voice notes the client's
    answers talk about are already in the run. Returns `(records, warnings)`:
    the records are what `control/studio-order.json` keeps, the warnings are
    plain lines on the wake output. A file that is missing, refused or over
    its cap is ONE warning line - never a refusal, never a failed order.
    """
    upload_ids = order.get("upload_ids") if isinstance(order, dict) else None
    if not isinstance(upload_ids, list) or not upload_ids:
        return [], []
    folder = pathlib.Path(run_dir) / "intake" / "uploads"
    records, warnings = [], []
    opener = urllib.request.build_opener(_NoRedirect())
    for raw_id in upload_ids:
        upload_id = str(raw_id or "").strip()
        if not UPLOAD_ID.fullmatch(upload_id):
            warnings.append("An uploaded file could not be fetched (bad reference).")
            continue
        req = urllib.request.Request(
            base.rstrip("/") + UPLOAD_FILE_ROUTE % upload_id, method="GET")
        req.add_header("content-type", "application/json")
        req.add_header("User-Agent", STUDIO_USER_AGENT)
        for h, v in key_headers(key).items():
            req.add_header(h, v)
        try:
            with opener.open(req, timeout=timeout) as resp:
                name, cap = _upload_target(
                    upload_id, resp.headers.get("content-type"),
                    resp.headers.get("content-disposition"))
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / name
                digest = hashlib.sha256()
                written = 0
                too_big = False
                with target.open("wb") as fh:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > cap:
                            too_big = True
                            break
                        fh.write(chunk)
                        digest.update(chunk)
                if too_big:
                    target.unlink(missing_ok=True)
                    warnings.append("An uploaded file (%s) is larger than the "
                                    "studio accepts; it was not kept." % upload_id)
                    continue
        except urllib.error.HTTPError as exc:
            try:
                exc.read()          # drain the body: a clean close, no half-read
            except OSError:
                pass
            if exc.code == 404:
                warnings.append("An uploaded file (%s) has not reached the "
                                "studio yet; the run continues without it."
                                % upload_id)
            else:
                warnings.append("An uploaded file (%s) could not be fetched "
                                "(HTTP %s); the run continues without it."
                                % (upload_id, exc.code))
            continue
        except (urllib.error.URLError, TimeoutError, OSError):
            warnings.append("An uploaded file (%s) could not be reached; the "
                            "run continues without it." % upload_id)
            continue
        records.append({"upload_id": upload_id, "path": str(target),
                        "bytes": written, "sha256": digest.hexdigest()})
    return records, warnings


def cmd_poll(args):
    """Check in, claim one waiting order, replay it, print one JSON line.

    Durable claim/wake (SPEC 9.4, D35): the claim ledger records the steps
    claimed -> order-fetched -> materialized -> wake-queued ->
    execution-accepted. A local claim survives a failed fetch or wake and is
    RESUMED by the next poll under the same order (a same-owner re-claim is a
    resume; a live other owner is the only refusal). A repeated poll
    RECONCILES the recorded steps instead of returning quiet success, and a
    wake request stays pending — the line is re-emitted — until the supported
    runtime acknowledgement (wake --ack) arrives. Execution-accepted is final:
    later polls stay silent, so no duplicate campaign or paid job can start.

    A resume carries the studio's CURRENT order state: a terminal order
    (`cancelled`, `done`, `expired`) is never materialized, woken or re-emitted,
    and its local claim is released with a `remote_terminal` receipt on the
    ledger (ITEM 29 step 4).
    """
    key = load_key()
    if not key:
        _emit({"code": "NO_KEY", "message": "no machine key; run enroll first"})
        return EXIT["refused"]
    base = resolve_base_url(args.base_url)
    if not base:
        _emit({"code": "NO_BASE_URL",
               "message": "no studio address; pass --base-url or run enroll"})
        return EXIT["refused"]

    db = os.path.abspath(args.db or str(state_dir() / "studio.db"))
    with ClaimLedger(db) as led:
        # Check-in on EVERY poll, before unfinished claims are looked at
        # (S75-106 step 3): the studio learns this box is alive even while a
        # local claim sits unfinished, so one refused order can never keep the
        # box from checking in. Its inbox line is used only when nothing is
        # pending.
        status, out = _http("POST", base + "/api/studio/checkin", key=key,
                            body=checkin_body(args.skill_root, args.runs,
                                              args.client_dir))
        if status // 100 != 2 or not out.get("ok"):
            return _refusal(out, status, "check-in")
        line = out.get("line")
        # Startup recovery BEFORE relying on the waiting inbox (SPEC 9.4, D35):
        # a claim event can take an order out of that inbox while its local
        # handoff is unfinished, so a crashed claim is found here, not lost.
        pending = led.unfinished_orders(BRIDGE_OWNER)
        resume_token = None
        resume_fence = None
        from_recovery = bool(pending)
        if pending:
            # A stored poll line carries the claim token AND fence this owner
            # proved with last time: present both back so the ledger can tell a
            # crash-resume apart from a second live materializer.
            order_id, title = pending[0], ""
            for rec in reversed(led.receipts(order_id)):
                if rec.get("kind") == "poll_line":
                    line = rec.get("payload") or {}
                    resume_token = line.get("claim_token")
                    resume_fence = line.get("fence")
                    break
        else:
            if not line:
                return EXIT["ok"]               # nothing waiting: no output at all
            found = INBOX_LINE.match(str(line))
            if not found:
                _emit({"code": "BAD_INBOX_LINE", "message": str(line)[:200]})
                return EXIT["refused"]
            order_id, title = found.group(1), found.group(2)
            if not ORDER_ID.fullmatch(order_id):
                _emit({"code": "BAD_ORDER_ID",
                       "message": "refusing order id %r" % order_id[:64]})
                return EXIT["refused"]

        won = led.claim_order(order_id, BRIDGE_OWNER,
                              resume_token=resume_token,
                              resume_fence=resume_fence)
        if not won:
            # Refused: a live holder keeps it. A refused RESUME, though, must
            # not leave the stored line stale (see `_refresh_stored_line`);
            # refresh first, then keep the silent success.
            _refresh_stored_line(led, order_id)
            return EXIT["ok"]                   # a live holder keeps it
        recs = led.receipts(order_id)
        st = led.order_state(order_id) or {}
        fence = st.get("fence")
        stored_line = next((r["payload"] for r in reversed(recs)
                            if r["kind"] == "poll_line"), None)
        if stored_line is not None and stored_line.get("fence") != fence:
            # A resume advances the fence, so refresh the stored line NOW — in
            # the same ledger step as the claim — or a crash before
            # materialization finishes would leave a line the next poll is
            # refused on.
            refreshed = dict(stored_line)
            refreshed["fence"] = fence
            refreshed["claim_token"] = st.get("claim_token")
            led.write_receipt(order_id, "poll_line", refreshed)
            stored_line = refreshed
        if st.get("step") == STEP_EXECUTION_ACCEPTED:
            return EXIT["ok"]   # acknowledged: silent, no duplicate campaign
        kinds = {r["kind"] for r in recs}
        stored_order = next((r["payload"].get("order") for r in reversed(recs)
                             if r["kind"] == "order_fetched"), None)

        # Carry the studio's CURRENT state into the resume (ITEM 29 step 4).
        # The stored order was fetched before the crash; the client can cancel
        # while the claim sits unfinished, and a cancelled order leaves the
        # waiting inbox, so nothing else here would ever notice. Re-read the
        # order and honour a terminal state: no wake line, no run, no paid job,
        # the claim released. A failed re-read resumes the stored claim as
        # before (a transient GET must never wedge a recovery; the next poll
        # retries it).
        if from_recovery:
            status, out = _http("GET", base + "/api/studio/orders/%s" % order_id,
                                key=key)
            if status // 100 == 2 and out.get("ok"):
                order_now = out.get("order")
                led.record_order_state(
                    order_id,
                    order_now.get("state") if isinstance(order_now, dict) else None,
                    owner=BRIDGE_OWNER, fence=fence)
                closed = _terminal_state(order_now)
                if closed:
                    return _drop_terminal(led, order_id, closed, "resume")
            else:
                # The re-read failed: the last state the studio gave us is
                # still on the claim row, and a TERMINAL one stops the resume
                # just the same (a terminal order never moves again). The
                # claim is not wedged by an unreachable service.
                closed = _terminal_state({"state": st.get("state")})
                if closed:
                    return _drop_terminal(led, order_id, closed, "recorded")

        # Claim event: sent once. A repeat poll after a crash must never
        # re-post a claim the studio could reject as its own replay (D35).
        if "claim_event" not in kinds:
            status, out = _http("POST", base + "/api/studio/orders/%s/state" % order_id,
                                key=key, body={"event": "claim"})
            posted = status // 100 == 2 and bool(out.get("ok"))
            led.write_receipt(order_id, "claim_event", {
                "posted": posted,
                "code": None if posted else (out.get("code") or "HTTP_%d" % status)})
            # A refused claim POST is NOT fatal while the order still fetches:
            # repeated polls reconcile existing state (9.4).

        order = stored_order
        if order is None:
            status, out = _http("GET", base + "/api/studio/orders/%s" % order_id, key=key)
            if status // 100 != 2 or not out.get("ok"):
                # The claim stays at its step and the NEXT poll resumes this
                # fetch under the same order — never a silent
                # claimed-and-forgotten state.
                return _refusal(out, status, "order fetch")
            order = out.get("order") or {}
            # Keep the ledger's order state current on the studio's terms: this
            # is the one place the bridge sees a freshly fetched order, so the
            # claim row's `state` records what the studio said (lifecycle.js
            # STATES vocabulary), not the bridge's own handoff step.
            led.record_order_state(order_id, order.get("state"),
                                   owner=BRIDGE_OWNER, fence=fence)
            # The order can be cancelled between the check-in line and this
            # fetch; the fetched payload already carries that state, so it is
            # honoured here too — nothing is materialized for a closed order.
            closed = _terminal_state(order)
            if closed:
                return _drop_terminal(led, order_id, closed, "fetch")
            led.write_receipt(order_id, "order_fetched", {"order": order})
        if not _advance_claim(led, order_id, BRIDGE_OWNER, fence,
                              STEP_ORDER_FETCHED):
            return EXIT["refused"]
        title = str(order.get("title") or title)
        client_id = str(order.get("client_id") or "")

        # Absolute, always: the poll line's `next` is meant to be run as printed,
        # from wherever the agent happens to be (a relative --runs would otherwise
        # print a relative run_dir and a next that resolves somewhere else).
        run_dir = (pathlib.Path(args.runs).expanduser() / order_id).resolve()

        # Each answer travels with the text of the option the client picked
        # (S75-059): a page whose option list was reordered would replay a
        # different choice than the one shown. The text after the number is
        # compared with the box card's own option for that screen, and the
        # reply the card receives is its number - a typed brief answer passes
        # through exactly as written.
        replies, text_mismatch = _plain_replies(args.skill_root,
                                                order.get("replies") or [],
                                                args.client_dir)
        if text_mismatch is not None:
            at, question_id, page_text, card_text = text_mismatch
            sys.stderr.write(
                "studio_bridge: order %s reply %d says %r; the card asks %r\n"
                % (order_id, at + 1, page_text[:120],
                   (card_text or "")[:120]))
            record = _write_halted(
                run_dir, 0,
                {"question_id": question_id or None,
                 "reason_code": "INVALID_OPTION"},
                "INVALID_OPTION")
            return _halt_order(led, base, key, order_id, record)

        # Each answer travels with the id of the screen it was given on (S75-106
        # step 5). A page that numbered its screens differently would replay one
        # screen's answer onto another question, so the card's own ids are
        # compared first: a difference waits on the client (`halted`), never a
        # shifted run.
        ids_mismatch = _reply_id_mismatch(args.skill_root, order.get("reply_ids"),
                                          replies, args.client_dir)
        if ids_mismatch is not None:
            page_ids, asked_ids = ids_mismatch
            at = next((i for i in range(min(len(page_ids), len(asked_ids)))
                       if page_ids[i] != asked_ids[i]), len(asked_ids))
            record = _write_halted(
                run_dir, 0,
                {"question_id": asked_ids[at] if at < len(asked_ids) else None,
                 "reason_code": "INTAKE_REPLAY_MISMATCH"},
                "INTAKE_REPLAY_MISMATCH")
            return _halt_order(led, base, key, order_id, record)

        # An old page carries no reply ids and no option text: a reply count
        # that cannot complete the card's question list still replays shifted
        # answers, so the order waits on the client (`needs_you`, never
        # cancelled) and nothing is written (SPEC B1). The claim is released so
        # a refused order never blocks the box, exactly as a halted one does not.
        mismatch = _question_mismatch(args.skill_root, replies, args.client_dir)
        if mismatch is not None:
            code = _refuse_mismatch(base, key, order_id, mismatch)
            led.release_order(order_id, BRIDGE_OWNER)
            return code
        out_line = stored_line
        upload_warnings = []
        if out_line is None:
            control = run_dir / "control"
            control.mkdir(parents=True, exist_ok=True)
            # (S75-075) The client's uploaded files land in the run BEFORE the
            # intake replay: the card's photos answer is about files that must
            # already be there. A file the studio cannot hand over is one
            # warning line on this wake, never a refusal - the order still runs.
            uploads, upload_warnings = _fetch_uploads(base, key, order, run_dir)
            order_record = {"order_id": order_id, "client_id": client_id,
                            "title": title, "base_url": base}
            if uploads:
                order_record["uploads"] = uploads
            # The run dir knows WHERE the studio is; it never holds the key.
            (control / "studio-order.json").write_text(
                json.dumps(order_record, sort_keys=True) + "\n",
                encoding="utf-8")

            # The run's state authority, at claim time, so the very next command works.
            if _ensure_run_state(args.skill_root, run_dir, order_id) is None:
                return EXIT["error"]

            code, factory = _replay(args.skill_root, run_dir, replies)
            if code == EXIT["halted"]:
                # The order waits on the client: needs_you, the halt receipt and
                # the claim released - no wake line and no run for it, and the
                # box is free for the next order.
                return _halt_order(led, base, key, order_id,
                                   _read_halted(run_dir)
                                   or {"reason_code": "REPLAY_HALTED"})
            if code != EXIT["ok"]:
                return code
            _board_epic(args.skill_root, order_id, title)
            out_line = {"order_id": order_id, "run_dir": str(run_dir),
                        "next": "%s %s next --run-dir %s"
                                % (sys.executable, factory, run_dir),
                        "db": db, "fence": fence,
                        "claim_token": st.get("claim_token")}
            if upload_warnings:
                out_line["upload_warnings"] = upload_warnings
            if not _advance_claim(led, order_id, BRIDGE_OWNER, fence,
                                  STEP_MATERIALIZED):
                return EXIT["refused"]
        else:
            # A resumed poll carries the CURRENT claim's fence, never the one
            # frozen in the receipt: the line handed to the wake must match the
            # claim that is live now.
            out_line = dict(out_line)
        out_line["fence"] = fence
        out_line["claim_token"] = st.get("claim_token")
        if stored_line is None or stored_line.get("fence") != fence:
            # First materialization, or a takeover since the line was frozen:
            # refresh the recorded line so a direct acknowledgement (no
            # explicit --fence) is checked against the live claim.
            led.write_receipt(order_id, "poll_line", out_line)
        # Materialized but not yet acknowledged: re-emit the SAME line so the
        # wake request persists and is retried (a quiet success here is the
        # claimed-and-forgotten state this repair exists to remove).
        print(json.dumps(out_line, sort_keys=True))
        return EXIT["ok"]


# --- durable wake handoff (SPEC 9.4, D35) ------------------------------------

#: A wake turn must finish inside this lease or a later tick may re-wake.
WAKE_LEASE_TTL_S = 600.0


def _wake_fence(led, order_id, explicit):
    """The fence a wake step must present.

    Explicit `--fence` (from the poll line) wins. A legacy direct caller that
    passed no fence falls back to the fence frozen on the latest poll line, so
    an acknowledgement recorded after a takeover is still refused. ``None``
    (no line, no explicit fence) keeps the pre-repair behaviour for old callers.
    """
    if explicit is not None:
        return int(explicit)
    for rec in reversed(led.receipts(order_id)):
        if rec.get("kind") == "poll_line":
            value = (rec.get("payload") or {}).get("fence")
            return int(value) if value is not None else None
    return None


def cmd_wake(args):
    """Record the wake handoff steps on the claim ledger (D35).

    --queued  the wake request is in flight; a concurrent wake for the same
              order is refused (lease), so a turn is never started twice.
    --ack     the supported runtime acknowledged the turn: the claim moves to
              execution-accepted and every later poll stays silent.
    --fail    the wake failed for a NAMED reason. The step does not move: the
              request stays queued and the next poll retries it under the same
              order. Failures are never converted into silent success.
    """
    db = os.path.abspath(args.db or str(state_dir() / "studio.db"))
    now = time.time()
    lease_owner = "%s@%s" % (BRIDGE_OWNER, os.getpid())
    with ClaimLedger(db) as led:
        st = led.order_state(args.order)
        owner = st["owner"] if st else BRIDGE_OWNER
        fence = _wake_fence(led, args.order, getattr(args, "fence", None))
        if args.queued:
            won = led.lease_acquire("wake:" + args.order, lease_owner,
                                    ttl_s=WAKE_LEASE_TTL_S, now=now)
            if not won:
                _emit({"order_id": args.order, "in_flight": True,
                       "message": "a wake for this order is already in flight"})
                return EXIT["ok"]
            if not _advance_claim(led, args.order, owner, fence,
                                  STEP_WAKE_QUEUED, now=now):
                led.lease_clear("wake:" + args.order)
                return EXIT["refused"]
            led.write_receipt(args.order, "wake_queued",
                              {"pid": os.getpid()}, now=now)
            _emit({"order_id": args.order, "queued": True})
            return EXIT["ok"]
        if args.ack:
            if not _advance_claim(led, args.order, owner, fence,
                                  STEP_EXECUTION_ACCEPTED, now=now,
                                  stale_code="STALE_ACK"):
                return EXIT["refused"]
            led.write_receipt(args.order, "execution_accepted",
                              {"pid": os.getpid()}, now=now)
            led.lease_clear("wake:" + args.order)
            _emit({"order_id": args.order, "execution_accepted": True})
            return EXIT["ok"]
        if args.fail:
            if fence is not None and st is not None \
                    and int(st.get("fence") or -1) != int(fence):
                _emit({"order_id": args.order, "wake_failed": False,
                       "code": "STALE_FAIL",
                       "message": "failure carries a stale fence"})
                return EXIT["refused"]
            led.write_receipt(args.order, "wake_failed",
                              {"reason": args.reason or "UNNAMED",
                               "pid": os.getpid()}, now=now)
            led.lease_clear("wake:" + args.order)
            _emit({"order_id": args.order, "wake_failed": args.reason or "UNNAMED",
                   "retryable": True})
            return EXIT["ok"]
    _emit({"code": "BAD_WAKE", "message": "use --queued, --ack or --fail"})
    return EXIT["refused"]


# --- approvals (U2 owns approvals_bridge) ------------------------------------

def _bridge_call(name, base, key, args, *extra):
    """Call `approvals_bridge.<name>(base, key, order, stage, version, *extra)`.

    Imported lazily: U2 lands the module separately, and the rest of this
    bridge must keep working without it.
    """
    try:
        import approvals_bridge  # noqa: PLC0415
    except ImportError as exc:
        _emit({"code": "NO_APPROVALS_BRIDGE", "message": str(exc)[:300]})
        return EXIT["error"], None
    fn = getattr(approvals_bridge, name, None)
    if fn is None:
        _emit({"code": "NO_APPROVALS_BRIDGE",
               "message": "approvals_bridge has no %r" % name})
        return EXIT["error"], None
    try:
        return EXIT["ok"], fn(base, key, args.order, args.stage, args.version, *extra)
    except Exception as exc:  # noqa: BLE001 - a refusal keeps its own code
        _emit({"code": getattr(exc, "code", "APPROVAL_FAILED"),
               "message": str(exc)[:300]})
        return EXIT["error"], None


def cmd_publish_approval(args):
    key, base = load_key(), resolve_base_url(args.base_url)
    if not key:
        _emit({"code": "NO_KEY", "message": "no machine key; run enroll first"})
        return EXIT["refused"]
    if not base:
        _emit({"code": "NO_BASE_URL", "message": "no studio address; pass --base-url"})
        return EXIT["refused"]
    try:
        text = pathlib.Path(args.text_file).expanduser().read_text(encoding="utf-8")
    except OSError as exc:
        _emit({"code": "NO_TEXT_FILE", "message": str(exc)[:300]})
        return EXIT["refused"]
    choices = [{"n": i + 1, "label": str(label)}
               for i, label in enumerate(args.choice or [])]
    # `files`: local paths approvals_bridge PUTs to their presigned URLs.
    code, item = _bridge_call("publish", base, key, args, text, choices,
                              list(args.file or []))
    if code != EXIT["ok"]:
        return code
    _emit(item if isinstance(item, dict) else {"item": item})
    return code


def cmd_approval_answer(args):
    key, base = load_key(), resolve_base_url(args.base_url)
    if not key:
        _emit({"code": "NO_KEY", "message": "no machine key; run enroll first"})
        return EXIT["refused"]
    if not base:
        _emit({"code": "NO_BASE_URL", "message": "no studio address; pass --base-url"})
        return EXIT["refused"]
    code, value = _bridge_call("answer", base, key, args)
    if code != EXIT["ok"]:
        return code
    if value is None:
        return EXIT["undefined"]                # not answered yet (exit 3)
    print(value if isinstance(value, str) else json.dumps(value, sort_keys=True))
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("handshake", help="prove the presented key is accepted")
    h.add_argument("--base-url", required=True)
    h.set_defaults(func=cmd_handshake)

    c = sub.add_parser("claim", help="claim ONE order; the loser exits non-zero")
    c.add_argument("--db", required=True)
    c.add_argument("--order", required=True)
    c.add_argument("--owner", required=True)
    c.set_defaults(func=cmd_claim)

    n = sub.add_parser("notice", help="one nudge, one reminder, then silence")
    n.add_argument("--db", required=True)
    n.add_argument("--order", required=True)
    n.add_argument("--reminder-after-s", type=float, default=86400.0)
    n.set_defaults(func=cmd_notice)

    l = sub.add_parser("lease", help="take a Windows-safe lease; a live holder refuses")
    l.add_argument("--db", required=True)
    l.add_argument("--name", required=True)
    l.add_argument("--owner", required=True)
    l.add_argument("--ttl", type=float, default=120.0)
    l.set_defaults(func=cmd_lease)

    s = sub.add_parser("status", help="post an order state event")
    s.add_argument("--base-url", required=True)
    s.add_argument("--order", required=True)
    s.add_argument("--event", required=True, choices=STATUS_EVENTS)
    s.add_argument("--delivery-url", default=None,
                   help="with --event deliver: the finished video's link")
    s.add_argument("--delivery-kind", default=None, choices=DELIVERY_KINDS)
    s.set_defaults(func=cmd_status)

    d = sub.add_parser("deliver", help="hash and record the finished video")
    d.add_argument("--run-dir", required=True)
    d.add_argument("--order", required=True)
    d.add_argument("--final", required=True)
    d.set_defaults(func=cmd_deliver)

    p = sub.add_parser("photo", help="build the direct-upload request for a photo")
    p.add_argument("--path", required=True)
    p.set_defaults(func=cmd_photo)

    u = sub.add_parser("upload", help="send a photo, audio or video directly to storage")
    u.add_argument("path")
    u.add_argument("--channel", choices=CHANNELS)
    u.add_argument("--upload-kind", choices=UPLOAD_KINDS,
                   help="intake (default), or r2_fallback for the studio's own "
                        "7-day copy, which is stored under clients/<id>/video/")
    u.set_defaults(func=cmd_upload)

    r = sub.add_parser("cleanup-receipt", help="write the owned-run cleanup receipt")
    r.add_argument("--run-dir", required=True)
    r.add_argument("--out", default=None)
    r.add_argument("--apply", action="store_true", help="also remove disposable paths")
    r.set_defaults(func=cmd_cleanup_receipt)

    en = sub.add_parser("enroll", help="register this box once; writes machine.key + machine.url")
    en.add_argument("--base-url", default=None, help="default: stored address, else the studio")
    en.add_argument("--label", default=None, help="computer/box name stored with the key")
    en.add_argument("--resume", action="store_true",
                    help="with an existing key: complete/recover the receipt locally "
                         "(never contacts the studio; never re-enrols)")
    en.set_defaults(func=cmd_enroll)

    cap = sub.add_parser("capability",
                         help="model the optional Studio capability in the install state")
    cap.add_argument("--gate", action="store_true",
                     help="exit 0 = ready to poll, 10 = skip quietly; one line per "
                          "transition only (the idle optional poller reads this)")
    cap.add_argument("--record", default=None, choices=CAPABILITY_STATES,
                     help="install-time intent (disabled | needs-enrollment); an "
                          "observed enrolment is never downgraded")
    cap.add_argument("--repair", action="store_true",
                     help="recover an interrupted/key-only receipt in place first")
    cap.add_argument("--no-network", action="store_true",
                     help="receipt-only check; the handshake is not probed")
    cap.add_argument("--base-url", default=None)
    cap.set_defaults(func=cmd_capability)

    wk = sub.add_parser("wake", help="record the durable wake handoff on the claim ledger")
    wk.add_argument("--order", required=True)
    wk.add_argument("--db", default=None, help="claim ledger (default: <state folder>/studio.db)")
    wk.add_argument("--queued", action="store_true", help="wake request in flight")
    wk.add_argument("--ack", action="store_true", help="runtime acknowledged the turn")
    wk.add_argument("--fail", action="store_true", help="wake failed; the request stays queued")
    wk.add_argument("--reason", default=None, help="with --fail: the named failure code")
    wk.add_argument("--fence", type=int, default=None,
                    help="the poll line's fence: a stale fence is refused")
    wk.set_defaults(func=cmd_wake)

    sd = sub.add_parser("state-dir", help="print the persistent state root (one contract)")
    sd.set_defaults(func=cmd_state_dir)

    li = sub.add_parser("link", help="print the client's personal link; --new rotates it")
    li.add_argument("--new", action="store_true", help="mint a fresh link; the old one stops working")
    li.add_argument("--base-url", default=None)
    li.set_defaults(func=cmd_link)

    po = sub.add_parser("poll", help="check in, claim one order, replay it, print one JSON line")
    po.add_argument("--skill-root", required=True, help="skill 75 root R")
    po.add_argument("--runs", required=True, help="runs directory D; the order becomes D/<order_id>")
    po.add_argument("--client-dir", default="",
                    help="the client data folder holding agnes.json; empty reads the "
                         "remembered Agnes answer as unknown (SPEC A2)")
    po.add_argument("--base-url", default=None)
    po.add_argument("--db", default=None, help="claim ledger (default: <state folder>/studio.db)")
    po.set_defaults(func=cmd_poll)

    pa = sub.add_parser("publish-approval", help="post an approval item and PUT its files")
    pa.add_argument("--order", required=True)
    pa.add_argument("--stage", required=True, choices=APPROVAL_STAGES)
    pa.add_argument("--version", required=True, type=int)
    pa.add_argument("--text-file", required=True)
    pa.add_argument("--choice", action="append", default=[], help="choice label (repeat)")
    pa.add_argument("--file", action="append", default=[], help="local file to PUT (repeat)")
    pa.add_argument("--base-url", default=None)
    pa.set_defaults(func=cmd_publish_approval)

    aa = sub.add_parser("approval-answer", help="print the client's answer, or nothing")
    aa.add_argument("--order", required=True)
    aa.add_argument("--stage", required=True, choices=APPROVAL_STAGES)
    aa.add_argument("--version", required=True, type=int)
    aa.add_argument("--base-url", default=None)
    aa.set_defaults(func=cmd_approval_answer)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except LedgerError as e:
        _emit({"code": e.code, "message": str(e)})
        return EXIT["refused"]


if __name__ == "__main__":
    sys.exit(main())
