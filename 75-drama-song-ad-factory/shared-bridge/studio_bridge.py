#!/usr/bin/env python3
"""U5 — the shared studio bridge (one file for OpenClaw boxes and Claude Code).

Reuses the mint/renew/sync shape of `intake-miniapp/bridge/intake_bridge.py`
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
    POST /api/studio/checkin                     header x-ds-key
    GET  /api/studio/orders/<id>                 header x-ds-key
    POST /api/studio/orders/<id>/state           header x-ds-key  {event}
    POST /api/studio/uploads                     header x-ds-key  {channel, ...}
    POST /api/studio/orders                      header x-ds-key  {title, order_id?}

`event` is one of claim | needs_you | answer | ready | deliver | done.

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
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from studio_claim import ClaimLedger, LedgerError, message_id  # noqa: E402

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
    """`~/.drama-studio` for the SAME env the caller passed (SPEC §2)."""
    src = _env_of(env)
    home = (src.get("HOME") or "").strip() or str(pathlib.Path.home())
    return pathlib.Path(home) / ".drama-studio"


def state_dir(env=None):
    """The state folder: `$DRAMA_STUDIO_STATE` when set, else `~/.drama-studio`."""
    src = _env_of(env)
    given = (src.get("DRAMA_STUDIO_STATE") or "").strip()
    return pathlib.Path(given).expanduser() if given else _home_state(env)


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

def _emit(obj):
    print(json.dumps(obj, indent=2, sort_keys=True))


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


def cmd_enroll(args):
    """Register this box ONCE; the key comes back once and is written 0600."""
    env = os.environ
    if load_key(env):
        _emit({"code": "ALREADY_ENROLLED",
               "message": "a machine key already exists; refusing to replace it"})
        return EXIT["refused"]
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


def cmd_poll(args):
    """Check in, claim one waiting order, replay it, print one JSON line."""
    key = load_key()
    if not key:
        _emit({"code": "NO_KEY", "message": "no machine key; run enroll first"})
        return EXIT["refused"]
    base = resolve_base_url(args.base_url)
    if not base:
        _emit({"code": "NO_BASE_URL",
               "message": "no studio address; pass --base-url or run enroll"})
        return EXIT["refused"]

    status, out = _http("POST", base + "/api/studio/checkin", key=key, body={})
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

    with ClaimLedger(args.db or str(state_dir() / "studio.db")) as led:
        won = led.claim_order(order_id, BRIDGE_OWNER)
    if not won:
        return EXIT["ok"]                       # another run holds it: no output

    status, out = _http("POST", base + "/api/studio/orders/%s/state" % order_id,
                        key=key, body={"event": "claim"})
    if status // 100 != 2 or not out.get("ok"):
        return _refusal(out, status, "claim")
    status, out = _http("GET", base + "/api/studio/orders/%s" % order_id, key=key)
    if status // 100 != 2 or not out.get("ok"):
        return _refusal(out, status, "order fetch")
    order = out.get("order") or {}
    title = str(order.get("title") or title)
    client_id = str(order.get("client_id") or "")

    run_dir = pathlib.Path(args.runs).expanduser() / order_id
    control = run_dir / "control"
    control.mkdir(parents=True, exist_ok=True)
    # The run dir knows WHERE the studio is; it never holds the key.
    (control / "studio-order.json").write_text(
        json.dumps({"order_id": order_id, "client_id": client_id,
                    "title": title, "base_url": base}, sort_keys=True) + "\n",
        encoding="utf-8")

    code, factory = _replay(args.skill_root, run_dir, order.get("replies") or [])
    if code != EXIT["ok"]:
        return code
    _board_epic(args.skill_root, order_id, title)
    print(json.dumps({"order_id": order_id, "run_dir": str(run_dir),
                      "next": "%s %s next --run-dir %s"
                              % (sys.executable, factory, run_dir)},
                     sort_keys=True))
    return EXIT["ok"]


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
    en.set_defaults(func=cmd_enroll)

    li = sub.add_parser("link", help="print the client's personal link; --new rotates it")
    li.add_argument("--new", action="store_true", help="mint a fresh link; the old one stops working")
    li.add_argument("--base-url", default=None)
    li.set_defaults(func=cmd_link)

    po = sub.add_parser("poll", help="check in, claim one order, replay it, print one JSON line")
    po.add_argument("--skill-root", required=True, help="skill 75 root R")
    po.add_argument("--runs", required=True, help="runs directory D; the order becomes D/<order_id>")
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
