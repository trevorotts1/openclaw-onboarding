#!/usr/bin/env python3
"""U2 — box-side approvals: publish an item to the studio page, read the tap.

Two functions, one per direction of the approval gate (SPEC.md §4):

    publish(base_url, key, order_id, stage, version, text, choices, files)
        POST the item to /api/studio/orders/<id>/approvals, then PUT every
        file to its presigned URL (streamed from disk) and return the item.

    answer(base_url, key, order_id, stage, version)
        GET the same list and return the recorded answer value, or None
        when nothing has been answered yet.

Both raise `LedgerError` (never a bare exception) when the service refuses or
the transport outcome is unknown, so the caller can tell "not answered yet"
from "could not ask".

SECRETS: the presented key travels only in the `x-ds-key` header. Nothing here
prints, logs or returns it, and presigned URLs are never printed either.

Stdlib only, and no second HTTP client: this imports studio_bridge's request
helper and its one explicit User-Agent (Cloudflare refuses Python's default).
"""
from __future__ import annotations

import mimetypes
import os
import pathlib
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from studio_bridge import (  # noqa: E402,F401  (STUDIO_USER_AGENT is re-exported
    STUDIO_USER_AGENT,        # so the checks can prove it is the SAME constant)
    _http,
    _put_file,
)
from studio_claim import LedgerError  # noqa: E402

STAGES = ("script", "song", "storyboard")

# The only content types this bridge will ever PUT to a client page: a .json,
# .log or .py handed to the publisher is refused HERE, locally, before any
# request and before the key is used (SPEC §4: approvals carry media only).
PUBLISHABLE_PREFIXES = ("image/", "audio/", "video/")
PUBLISHABLE_TYPES = ("application/pdf",)


def _publishable(ctype):
    return ctype.startswith(PUBLISHABLE_PREFIXES) or ctype in PUBLISHABLE_TYPES


def _url(base_url, order_id):
    oid = urllib.parse.quote(str(order_id), safe="")
    return base_url.rstrip("/") + "/api/studio/orders/%s/approvals" % oid


def _require_key(key):
    if not key:
        raise LedgerError("NO_KEY", "DS_KEY not set in env")


def _version(value):
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise LedgerError("BAD_VERSION", "version must be a whole number")
    if v < 1:
        raise LedgerError("BAD_VERSION", "version must be a whole number")
    return v


def _file_spec(entry):
    """One file to publish: a path on disk, or {path, name, content_type}.

    Only image/*, audio/*, video/* and application/pdf are publishable;
    anything else raises locally, with no request and no key involved.
    """
    if isinstance(entry, dict):
        path = entry.get("path") or ""
        name = entry.get("name") or os.path.basename(str(path))
        ctype = entry.get("content_type")
    else:
        path, name, ctype = str(entry), os.path.basename(str(entry)), None
    p = pathlib.Path(path)
    if not p.is_file():
        raise LedgerError("NO_FILE", "approval file not found: %s" % name)
    ctype = ctype or mimetypes.guess_type(name)[0]
    if not ctype:
        raise LedgerError("UNSUPPORTED_FILE", "unknown file type: %s" % name)
    if not _publishable(ctype):
        raise LedgerError("BAD_FILE_TYPE",
                          "refusing to publish %s: content type %s is not "
                          "image, audio, video or pdf" % (name, ctype))
    return {"path": p, "name": name, "content_type": ctype,
            "bytes": p.stat().st_size}


def publish(base_url, key, order_id, stage, version, text, choices, files):
    """Post one approval item, then PUT each of its files to storage."""
    _require_key(key)
    if stage not in STAGES:
        raise LedgerError("BAD_STAGE", "stage must be script, song or storyboard")
    specs = [_file_spec(f) for f in (files or ())]
    body = {
        "stage": stage,
        "version": _version(version),
        "text": text,
        "choices": list(choices or ()),
        "files": [{"name": s["name"], "content_type": s["content_type"],
                   "bytes": s["bytes"]} for s in specs],
    }
    status, resp = _http("POST", _url(base_url, order_id), key=key, body=body)
    if status == 0:
        raise LedgerError("TRANSPORT_UNKNOWN",
                          resp.get("message") or "approval publish outcome is unknown")
    if status // 100 != 2 or not resp.get("ok"):
        raise LedgerError("APPROVAL_PUBLISH_REFUSED",
                          resp.get("message") or "approval publish refused (HTTP %d)" % status)
    uploads = {u.get("name"): u for u in (resp.get("uploads") or ())}
    for s in specs:
        url = (uploads.get(s["name"]) or {}).get("url")
        if not url:
            raise LedgerError("APPROVAL_UPLOAD_MISSING",
                              "no upload url returned for %s" % s["name"])
        with s["path"].open("rb") as fh:
            put_status = _put_file(url, fh, s["content_type"], s["bytes"])
        if put_status == 0:
            raise LedgerError("TRANSPORT_UNKNOWN",
                              "storage upload outcome is unknown: %s" % s["name"])
        if put_status // 100 != 2:
            raise LedgerError("APPROVAL_PUT_REFUSED",
                              "storage refused %s (HTTP %d)" % (s["name"], put_status))
    return resp.get("item") or {}


def answer(base_url, key, order_id, stage, version):
    """The recorded answer for this stage+version, or None when unanswered."""
    _require_key(key)
    status, resp = _http("GET", _url(base_url, order_id), key=key)
    if status == 0:
        raise LedgerError("TRANSPORT_UNKNOWN",
                          resp.get("message") or "approval read outcome is unknown")
    if status // 100 != 2 or not resp.get("ok"):
        raise LedgerError("APPROVAL_READ_REFUSED",
                          resp.get("message") or "approval read refused (HTTP %d)" % status)
    for item in resp.get("items") or ():
        if item.get("stage") != stage or str(item.get("version")) != str(version):
            continue
        recorded = item.get("answer")
        if isinstance(recorded, dict):
            return recorded.get("value")
        return None
    return None
