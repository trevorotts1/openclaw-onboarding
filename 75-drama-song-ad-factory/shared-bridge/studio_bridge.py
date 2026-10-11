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
    POST /api/studio/checkin                     header x-ds-key
    POST /api/studio/orders/<id>/state           header x-ds-key  {event}
    POST /api/studio/uploads                     header x-ds-key  {channel, ...}
    POST /api/studio/orders                      header x-ds-key  {title, order_id?}

`event` is one of claim | needs_you | answer | ready | deliver | done.

SECRETS: the presented key is read from env `DS_KEY` only — never argv, never a
file the caller names on the command line, never a log line. Nothing in this
module prints, echoes or receipts a key value.

Exit codes: 0 ok · 1 error · 2 refused · 3 undefined (transport unknown).
Stdlib only: argparse, hashlib, json, os, pathlib, sys, time, urllib.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from studio_claim import ClaimLedger, LedgerError, message_id  # noqa: E402

EXIT = {"ok": 0, "error": 1, "refused": 2, "undefined": 3}

STATUS_EVENTS = ("claim", "needs_you", "answer", "ready", "deliver", "done")

#: U2 schema.sql: upload channels and the plan's 50 MB client cap.
CHANNELS = ("audio", "image", "video")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
HEADER_SNIFF_BYTES = 512

IMAGE_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


# --- key handshake -----------------------------------------------------------

def load_key(env=None):
    """The presented key, from env only. Returns "" when absent (fail closed)."""
    src = os.environ if env is None else env
    return src.get("DS_KEY") or ""


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
    p = pathlib.Path(path)
    if not p.is_file():
        raise LedgerError("NO_FILE", "photo not found: %s" % p.name)
    size = p.stat().st_size
    if size <= 0:
        raise LedgerError("EMPTY_FILE", "photo is empty: %s" % p.name)
    if size > MAX_UPLOAD_BYTES:
        raise LedgerError("TOO_BIG", "%s is %d bytes; cap is %d"
                          % (p.name, size, MAX_UPLOAD_BYTES))
    with p.open("rb") as fh:
        header = fh.read(HEADER_SNIFF_BYTES)
    ctype = sniff_image(header)
    if ctype is None:
        raise LedgerError("UNSUPPORTED_TYPE",
                          "%s is not a recognised photo format" % p.name)
    return {
        "channel": "image",
        "filename": p.name,
        "size_bytes": size,
        "content_type": ctype,
        "header_bytes": len(header),
    }


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
    status, body = _http("POST",
                         args.base_url.rstrip("/") + "/api/studio/orders/%s/state" % args.order,
                         key=key, body={"event": args.event})
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
    s.set_defaults(func=cmd_status)

    d = sub.add_parser("deliver", help="hash and record the finished video")
    d.add_argument("--run-dir", required=True)
    d.add_argument("--order", required=True)
    d.add_argument("--final", required=True)
    d.set_defaults(func=cmd_deliver)

    p = sub.add_parser("photo", help="build the direct-upload request for a photo")
    p.add_argument("--path", required=True)
    p.set_defaults(func=cmd_photo)

    r = sub.add_parser("cleanup-receipt", help="write the owned-run cleanup receipt")
    r.add_argument("--run-dir", required=True)
    r.add_argument("--out", default=None)
    r.add_argument("--apply", action="store_true", help="also remove disposable paths")
    r.set_defaults(func=cmd_cleanup_receipt)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except LedgerError as e:
        _emit({"code": e.code, "message": str(e)})
        return EXIT["refused"]


if __name__ == "__main__":
    sys.exit(main())
