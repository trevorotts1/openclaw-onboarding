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
approval not answered yet).
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
                          STEP_CLAIMED, STEP_ORDER_FETCHED, STEP_MATERIALIZED,
                          STEP_WAKE_QUEUED, STEP_EXECUTION_ACCEPTED)

EXIT = {"ok": 0, "error": 1, "refused": 2, "undefined": 3}

STATUS_EVENTS = ("claim", "needs_you", "answer", "ready", "deliver", "done")

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


def upload_request(path, channel=None):
    """Build the service request, checking file bytes, extension and channel cap."""
    p = pathlib.Path(path)
    if not p.is_file():
        raise LedgerError("NO_FILE", "photo not found: %s" % p.name)
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
    return {
        "channel": channel,
        "filename": p.name,
        "size_bytes": size,
        "content_type": ctype,
        "header_bytes": list(header[:16]),
    }


def _put_file(url, file_handle, content_type, size, *, timeout=120):
    """Stream file bytes directly to R2; no presented key is forwarded."""
    req = urllib.request.Request(url, data=file_handle, method="PUT",
                                 headers={"Content-Type": content_type,
                                          "Content-Length": str(size),
                                          "User-Agent": STUDIO_USER_AGENT})
    # A redirect must never forward the file to another destination.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def upload_file(path, *, channel=None, env=None, post=None, put=None):
    """POST metadata then PUT bytes. Returns identifiers only, never a signed URL."""
    key = load_key(env)
    if not key:
        raise LedgerError("NO_KEY", "DS_KEY not set in env")
    body = upload_request(path, channel)
    status, result = (post or _http)("POST", STUDIO_BASE_URL + "/api/studio/uploads",
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
    import re
    if (parts.scheme != "https" or parts.username or parts.password or parts.port
            or not re.fullmatch(r"[a-f0-9]{32}\.r2\.cloudflarestorage\.com", parts.hostname or "")
            or not re.fullmatch(r"clients/c-[a-f0-9]{32}/intake/u_[a-f0-9]{24}\.[a-z0-9]+", object_path)
            or parts.path != "/zhw-drama-studio/" + object_path
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
            _emit({"order_id": args.order, "owner": args.owner, "won": True})
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
        _emit(upload_file(args.path, channel=args.channel))
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
        out = Outbox()
        out.enqueue_create(job_id=order_id, show_name=title,
                           stages=[{"slug": s[0]} for s in STAGES],
                           workspace=out.workspace)
        out.flush()
    except Exception:  # noqa: BLE001 - a down board never stops the order
        pass


#: The card's own step line: the one place its question count is written out
#: (`intake_card.render_step`). A recap, a waiting answer or a locked-in run
#: prints no step line at all.
QUESTION_LINE = re.compile(r"Question (\d+) of (\d+)")


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
    re-derived list refuses orders the card itself completed). The test: drop the
    trailing recap confirmation the studio page appends
    (`mini-app/ui/studio.js:470`), replay the rest, and read the card's own
    "Question N of M" step line. No step line means the card reached its recap,
    its waiting answer or a locked-in run - it completed whatever it asked. A
    step line with fewer accepted answers than questions means it ran out, or a
    reply did not fit and the rest shifted: that is the refusal, and those are
    the two counts named back. Extra replies past a complete list are absorbed by
    the card itself (a "change line N" or a recap), never a mismatch here.

    None when the installed card has no purpose flow to count against, and None
    on any card fault: a claim never dies on this import. The guard stays inert
    until the card that defines the shaped list ships (O-card-wiring).
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
    if state.get("done"):
        return None                                    # the card locked these in
    found = QUESTION_LINE.search(str(state.get("message") or ""))
    if not found:
        return None                                    # the card reached its recap
    questions = int(found.group(2))
    accepted = len(state.get("answers") or [])
    if questions <= 0 or accepted >= questions:
        return None
    return accepted, questions


def _refuse_mismatch(base, key, order_id, mismatch):
    """Refuse a replay whose reply count cannot complete the question list, and
    cancel the order with that reason on it: the run never starts shifted."""
    given, questions = mismatch
    reason = ("REPLAY_QUESTION_MISMATCH: %d replies cannot complete the %d "
              "questions of this card" % (given, questions))
    status, out = _http("POST",
                        base.rstrip("/") + "/api/studio/orders/%s/state" % order_id,
                        key=key, body={"event": "cancel", "reason": reason})
    cancelled = bool(status and status // 100 == 2 and out.get("ok"))
    _emit({"code": "REPLAY_QUESTION_MISMATCH", "message": reason,
           "order_id": order_id, "replies": given, "questions": questions,
           "cancelled": cancelled})
    return EXIT["refused"]


def _replay(skill_root, run_dir, replies):
    """Hand every reply back to the card, in order. argv list, never a shell."""
    factory = (pathlib.Path(skill_root).expanduser() / "scripts" / "core"
               / "intake_preflight" / "factory.py")
    if not factory.is_file():
        _emit({"code": "NO_FACTORY",
               "message": "factory.py not found under %s" % skill_root})
        return EXIT["refused"], factory
    argv = [sys.executable, str(factory), "card", "--step", "--format", "text",
            "--run-dir", str(run_dir)]
    for reply in replies:
        argv.extend(["--reply", str(reply)])
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=600, cwd=str(skill_root))
    except (OSError, subprocess.SubprocessError) as exc:
        _emit({"code": "REPLAY_FAILED", "message": str(exc)[:300]})
        return EXIT["error"], factory
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-300:]
        _emit({"code": "REPLAY_FAILED", "message": tail})
        return EXIT["error"], factory
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

    status, out = _http("POST", base + "/api/studio/checkin", key=key,
                        body=checkin_body(args.skill_root, args.runs, args.client_dir))
    if status // 100 != 2 or not out.get("ok"):
        return _refusal(out, status, "check-in")
    line = out.get("line")
    if not line:
        return EXIT["ok"]                       # nothing waiting: no output at all
    found = INBOX_LINE.match(str(line))
    if not found:
        _emit({"code": "BAD_INBOX_LINE", "message": str(line)[:200]})
        return EXIT["refused"]
    order_id, title = found.group(1), found.group(2)
    if not ORDER_ID.fullmatch(order_id):
        _emit({"code": "BAD_ORDER_ID", "message": "refusing order id %r" % order_id[:64]})
        return EXIT["refused"]

    db = os.path.abspath(args.db or str(state_dir() / "studio.db"))
    with ClaimLedger(db) as led:
        won = led.claim_order(order_id, BRIDGE_OWNER)
        if not won:
            return EXIT["ok"]                   # a live OTHER owner holds it
        recs = led.receipts(order_id)
        st = led.order_state(order_id) or {}
        if st.get("step") == STEP_EXECUTION_ACCEPTED:
            return EXIT["ok"]   # acknowledged: silent, no duplicate campaign
        kinds = {r["kind"] for r in recs}
        stored_order = next((r["payload"].get("order") for r in reversed(recs)
                             if r["kind"] == "order_fetched"), None)
        stored_line = next((r["payload"] for r in reversed(recs)
                            if r["kind"] == "poll_line"), None)

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
            led.write_receipt(order_id, "order_fetched", {"order": order})
        led.advance_step(order_id, BRIDGE_OWNER, STEP_ORDER_FETCHED)
        title = str(order.get("title") or title)
        client_id = str(order.get("client_id") or "")

        # Before the run folder exists at all: a reply count that cannot complete
        # the card's question list replays shifted answers, so the order is
        # cancelled with that reason instead and nothing is written (SPEC B1).
        mismatch = _question_mismatch(args.skill_root, order.get("replies") or [],
                                      args.client_dir)
        if mismatch is not None:
            return _refuse_mismatch(base, key, order_id, mismatch)

        # Absolute, always: the poll line's `next` is meant to be run as printed,
        # from wherever the agent happens to be (a relative --runs would otherwise
        # print a relative run_dir and a next that resolves somewhere else).
        run_dir = (pathlib.Path(args.runs).expanduser() / order_id).resolve()
        out_line = stored_line
        if out_line is None:
            control = run_dir / "control"
            control.mkdir(parents=True, exist_ok=True)
            # The run dir knows WHERE the studio is; it never holds the key.
            (control / "studio-order.json").write_text(
                json.dumps({"order_id": order_id, "client_id": client_id,
                            "title": title, "base_url": base}, sort_keys=True) + "\n",
                encoding="utf-8")

            # The run's state authority, at claim time, so the very next command works.
            if _ensure_run_state(args.skill_root, run_dir, order_id) is None:
                return EXIT["error"]

            code, factory = _replay(args.skill_root, run_dir, order.get("replies") or [])
            if code != EXIT["ok"]:
                return code
            _board_epic(args.skill_root, order_id, title)
            out_line = {"order_id": order_id, "run_dir": str(run_dir),
                        "next": "%s %s next --run-dir %s"
                                % (sys.executable, factory, run_dir),
                        "db": db}
            led.write_receipt(order_id, "poll_line", out_line)
            led.advance_step(order_id, BRIDGE_OWNER, STEP_MATERIALIZED)
        # Materialized but not yet acknowledged: re-emit the SAME line so the
        # wake request persists and is retried (a quiet success here is the
        # claimed-and-forgotten state this repair exists to remove).
        print(json.dumps(out_line, sort_keys=True))
        return EXIT["ok"]


# --- durable wake handoff (SPEC 9.4, D35) ------------------------------------

#: A wake turn must finish inside this lease or a later tick may re-wake.
WAKE_LEASE_TTL_S = 600.0


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
        if args.queued:
            won = led.lease_acquire("wake:" + args.order, lease_owner,
                                    ttl_s=WAKE_LEASE_TTL_S, now=now)
            if not won:
                _emit({"order_id": args.order, "in_flight": True,
                       "message": "a wake for this order is already in flight"})
                return EXIT["ok"]
            led.advance_step(args.order, owner, STEP_WAKE_QUEUED, now=now)
            led.write_receipt(args.order, "wake_queued",
                              {"pid": os.getpid()}, now=now)
            _emit({"order_id": args.order, "queued": True})
            return EXIT["ok"]
        if args.ack:
            led.advance_step(args.order, owner, STEP_EXECUTION_ACCEPTED, now=now)
            led.write_receipt(args.order, "execution_accepted",
                              {"pid": os.getpid()}, now=now)
            led.lease_clear("wake:" + args.order)
            _emit({"order_id": args.order, "execution_accepted": True})
            return EXIT["ok"]
        if args.fail:
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
