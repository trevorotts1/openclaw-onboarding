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

import hashlib
import json
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


def _choices(choices):
    """Choices as the service stores them: {n: whole number, label: string}.

    A bare label list (``["GO"]``) or a partial object is refused HERE, with a
    named error and no request, so the shipped caller can never publish a shape
    the service will reject after the key was used (ST10B).
    """
    out = []
    for c in choices or ():
        if not isinstance(c, dict):
            raise LedgerError("BAD_CHOICE",
                              "every choice is {n, label}, not %r" % (c,))
        n, label = c.get("n"), c.get("label")
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise LedgerError("BAD_CHOICE", "choice %r needs a whole n >= 1" % (c,))
        if not isinstance(label, str) or not label.strip():
            raise LedgerError("BAD_CHOICE", "choice %r needs a label" % (c,))
        out.append({"n": n, "label": label})
    return out


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
        "choices": _choices(choices),
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


def _item_digest(item):
    """sha256 over the exact presentation the page stored (stage, version,
    question, choices). The decision is bound to these bytes (ST6)."""
    canonical = {"stage": item.get("stage"), "version": item.get("version"),
                 "text": item.get("text"), "choices": item.get("choices") or []}
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def answer_item(base_url, key, order_id, stage, version):
    """The recorded answer as the FULL verified envelope, or None.

    ``answer`` above keeps its legacy scalar return. This is the ST6 contract:
    the caller receives the question, revision, exact presentation digest, the
    client's choice and who/when the service recorded it, so a scalar can never
    stand in for provenance. A tap is only returned when the stored item is at
    the requested stage AND version.
    """
    _require_key(key)
    status, resp = _http("GET", _url(base_url, order_id), key=key)
    if status == 0:
        raise LedgerError("TRANSPORT_UNKNOWN",
                          resp.get("message") or "approval read outcome is unknown")
    if status // 100 != 2 or not resp.get("ok"):
        raise LedgerError("APPROVAL_READ_REFUSED",
                          resp.get("message") or "approval read refused (HTTP %d)" % status)
    wanted = _version(version)
    for item in resp.get("items") or ():
        if item.get("stage") != stage:
            continue
        try:
            stored = int(item.get("version"))
        except (TypeError, ValueError):
            continue
        if stored != wanted:
            continue
        recorded = item.get("answer")
        if not isinstance(recorded, dict):
            return None
        by = recorded.get("by")
        at = recorded.get("at")
        if by not in ("link", "machine") or isinstance(at, bool) or not isinstance(at, int):
            raise LedgerError("BAD_ANSWER",
                              "stored answer carries no verified author/time")
        return {"stage": item.get("stage"), "version": stored,
                "question": item.get("text"), "choices": item.get("choices") or [],
                "value": recorded.get("value"), "by": by, "at": at,
                "created_at": item.get("created_at"),
                "digest": _item_digest(item)}
    return None


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
