#!/usr/bin/env python3
"""ghl_publish_approval.py - publish authorization for Skill 6 (S06-06).

A page may go live only when ALL of these hold:

  1. ``approval`` is an approval_ref (a plain id string) that resolves to a
     record in the Launcher's approval store. A free string such as "yes" or
     "live", a bare boolean, or an in-memory dict is never authority: the
     record is READ from the store (this module never writes it - the Launcher's
     human-approval step is the only writer).
  2. The record names ``allowed_write_target == "approved_live_publication"``
     (an ``approved_test_location`` record authorizes test-location writes only)
     and ``test_only`` is False.
  3. The record names the target ``location_id`` and lists the ``page_ids`` it
     covers; this page's id and this run's location must both match.
  4. The record is not revoked and not expired.
  5. ``ghl_gate`` has passed for this page (a live PASS verdict over the run's
     evidence root, with this page's own row PASS). Verification comes BEFORE
     publication, never after.

Store: a directory of ``<approval_ref>.json`` files named by the environment
variable ``LAUNCH_APPROVAL_STORE`` (or passed as ``store_dir``). Unset or
missing -> refuse. Fail closed everywhere.

ponytail: provenance of the record (a human reply carrying the plan-hash
prefix, verified by a service the AI session cannot write) is the Launcher /
approval-record service's job (U-approval-02); this module trusts only what
the store returns and checks scope, target, test_only, revocation and expiry.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

STORE_ENV = "LAUNCH_APPROVAL_STORE"
LIVE_TARGET = "approved_live_publication"

# An approval_ref is a plain file-safe id: no path separators, no traversal.
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ID_CLEAN_RE = re.compile(r"[^A-Za-z0-9_-]")


class PublishApprovalError(RuntimeError):
    """Raised when a publish (or a live write) lacks a valid approval record."""


def _norm_id(value) -> str:
    return _ID_CLEAN_RE.sub("", str(value or "").strip()).lower()


def read_record(approval_ref, store_dir: str | None = None) -> dict | None:
    """READ-ONLY lookup of ``approval_ref`` in the launch approval store.
    Returns the record dict, or None for anything that is not a resolvable ref
    (a bool, a dict, "yes", a traversal attempt, no store, no file, bad JSON)."""
    if not isinstance(approval_ref, str) or not _REF_RE.match(approval_ref):
        return None
    store = (store_dir or os.environ.get(STORE_ENV) or "").strip()
    if not store:
        return None
    path = os.path.join(store, approval_ref + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) else None


def _expired(expires_at, now: float) -> bool:
    if expires_at in (None, ""):
        return False
    try:
        if isinstance(expires_at, (int, float)) and not isinstance(expires_at, bool):
            return float(expires_at) <= now
        dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp() <= now
    except (TypeError, ValueError):
        return True  # an unreadable expiry is not "no expiry": fail closed


def record_refusals(record: dict | None, approval_ref, *, location_id,
                    page_id=None, now: float | None = None) -> list[str]:
    """Reasons ``record`` does not authorize live publication (empty = it does).
    ``page_id=None`` skips the page-id check (a location-wide live write such as
    a media push); a page publish always passes its page id."""
    if not isinstance(record, dict):
        return [f"no approval record resolves for approval_ref {approval_ref!r} "
                f"in the launch approval store ({STORE_ENV})"]
    now = time.time() if now is None else now
    why: list[str] = []
    if record.get("approval_ref") != approval_ref:
        why.append("record approval_ref does not match the ref it was read by")
    if record.get("allowed_write_target") != LIVE_TARGET:
        why.append(f"allowed_write_target is {record.get('allowed_write_target')!r}, "
                   f"not {LIVE_TARGET!r}")
    if record.get("test_only") is not False:
        why.append("record is test_only (or does not state test_only: false)")
    if record.get("revoked"):
        why.append("record is revoked")
    if _expired(record.get("expires_at"), now):
        why.append("record is expired")
    rec_loc = _norm_id(record.get("location_id"))
    if not rec_loc or rec_loc != _norm_id(location_id):
        why.append("record does not name this target location_id")
    if page_id is not None:
        pages = record.get("page_ids")
        if not isinstance(pages, list) or str(page_id) not in {str(p) for p in pages}:
            why.append(f"record page_ids does not name page {page_id!r}")
    return why


def gate_refusals(evidence_root, page_id) -> list[str]:
    """Reasons ``ghl_gate`` has NOT passed for ``page_id`` (empty = passed):
    a live PASS verdict over the evidence root AND this page's raw row PASS."""
    if not evidence_root or not os.path.isdir(str(evidence_root)):
        return ["ghl_gate has not passed: no evidence_root (verification must "
                "run and pass BEFORE publication)"]
    import ghl_gate  # lazy: ghl_gate -> ghl_verify -> ghl_builder -> this module
    import ghl_verify
    rc = ghl_gate.require_pass(str(evidence_root))
    if rc != 0:
        return [f"ghl_gate did not pass for the run (exit {rc})"]
    try:
        with open(os.path.join(str(evidence_root), ghl_verify.RAW_REL),
                  encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return ["ghl_gate raw verify log is unreadable"]
    rows = [r for r in raw if isinstance(r, dict) and str(r.get("page_id")) == str(page_id)]
    if not rows or not all(r.get("PASS") is True for r in rows):
        return [f"ghl_gate has no passing row for page {page_id!r}"]
    return []


def publish_refusals(approval, *, location_id, page_id, evidence_root=None,
                     store_dir: str | None = None, now: float | None = None) -> list[str]:
    """Every reason this page may NOT be published live (empty = may publish)."""
    if not location_id or not page_id:
        return ["publish needs the target location_id and page_id"]
    record = read_record(approval, store_dir)
    why = record_refusals(record, approval, location_id=location_id,
                          page_id=page_id, now=now)
    if why:
        return why  # no point reading evidence for an unapproved page
    return gate_refusals(evidence_root, page_id)


def require_publish(approval, *, location_id, page_id, evidence_root=None,
                    store_dir: str | None = None) -> dict:
    """Return the approval record, or raise ``PublishApprovalError``."""
    why = publish_refusals(approval, location_id=location_id, page_id=page_id,
                           evidence_root=evidence_root, store_dir=store_dir)
    if why:
        raise PublishApprovalError("REFUSE publish: " + "; ".join(why))
    return read_record(approval, store_dir) or {}


def require_live_write(approval, *, location_id, store_dir: str | None = None) -> dict:
    """Same record, for a live write that is not one page's publish (the
    graphics media push). Checks everything except page ids and the page gate."""
    record = read_record(approval, store_dir)
    why = record_refusals(record, approval, location_id=location_id, page_id=None)
    if why:
        raise PublishApprovalError("REFUSE live write: " + "; ".join(why))
    return record or {}
