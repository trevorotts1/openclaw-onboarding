#!/usr/bin/env python3
"""Provider-overlap receipts and the three-initial-attempt overlap gate.

TREVOR ORDER 2026-10-11 (WWFIX item 3), implemented exactly:
  * the overlap test runs over the THREE INITIAL attempts only -- a regenerated
    variant (for example v3r) never counts as initial overlap evidence;
  * the common provider-task interval is min(terminal_at) - max(submitted_at);
  * PASS requires >= 1.000 s; 0.999 s, zero and negative FAIL, never PASS;
  * a value that cannot be computed because the evidence is absent is
    UNAVAILABLE and is NEVER reported as a pass;
  * NO AUTOMATIC PAID REDO: a missing overlap or a missing receipt never buys
    another paid generation. Every already-paid track is preserved; new spend
    requires the owner's explicit authority.

Every timestamp in a receipt is AWARE UTC. A naive (local) timestamp is
refused: pool launch times and `_wall_clock_s` are LOCAL dispatch clocks and
can never establish provider overlap.

A receipt also binds what was PAID, so a finished, charged take can never be
reported as unpaid: `billed_cents` and `completed` ride every receipt, and a
terminal timestamp with `completed` True and a non-zero `billed_cents` is a
paid, completed take.

stdlib only; no network, no spend.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

TOOL_NAME = "song_choices.overlap"
SCHEMA = "blackceo.song-overlap-receipt/v1"

#: NEW ACCEPTANCE RULE (WWFIX 2026-10-11): the three INITIAL attempts must share
#: a common provider interval of at least this many seconds. It is a rule set by
#: the fix, not a measured limit of the failed run -- that run's provider overlap
#: was UNAVAILABLE (its envelopes carried no submitted/terminal timestamps).
MIN_OVERLAP_S = 1.0

#: The number of INITIAL attempts the gate requires.
INITIAL_ATTEMPTS = 3


class OverlapError(ValueError):
    """A loud refusal: approval or delivery stops when the overlap is not PASS."""


def _utc(value):
    """Aware-UTC datetime from an ISO-8601 string or a datetime. Naive refused."""
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise OverlapError(
            "timestamp %r carries no timezone; LOCAL clocks can never prove "
            "provider overlap (aware UTC is required)" % (value,))
    return dt.astimezone(timezone.utc)


def iso_z(value):
    """An aware-UTC timestamp as the canonical receipt string (milliseconds, Z)."""
    return _utc(value).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def request_sha256(request):
    """The sha256 of the exact request payload (sorted JSON, stable across runs)."""
    blob = json.dumps(request, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def make_receipt(variant_id, request, logical_key, attempt_id, task_id,
                 submitted_at, terminal_at, billed_cents=0, completed=None,
                 initial=None):
    """One attempt's receipt: variant, request and task ids with both provider
    times, plus what it was billed so a paid take is never read as unpaid.

    ``initial`` defaults to True for the first three attempts of a variant and
    False for a regenerated attempt; callers may set it explicitly. Both times
    are stored as aware-UTC strings."""
    if initial is None:
        try:
            initial = int(str(attempt_id).lstrip("aA") or 1) <= INITIAL_ATTEMPTS
        except (TypeError, ValueError):
            initial = False
    done = bool(terminal_at) if completed is None else bool(completed)
    return {
        "schema": SCHEMA,
        "variant_id": str(variant_id),
        "request_sha256": request_sha256(request),
        "logical_key": str(logical_key),
        "attempt_id": str(attempt_id),
        "task_id": None if task_id is None else str(task_id),
        "submitted_at": iso_z(submitted_at) if submitted_at else None,
        "terminal_at": iso_z(terminal_at) if terminal_at else None,
        "initial": bool(initial),
        "billed_cents": int(billed_cents or 0),
        "completed": done,
    }


def initial_attempts(receipts):
    """The INITIAL attempts in ``receipts``; a regenerated attempt never counts."""
    return [r for r in (receipts or []) if isinstance(r, dict) and r.get("initial")]


def overlap_seconds(receipts):
    """(seconds, None) for a computable overlap; (None, "UNAVAILABLE") without it.

    The common provider interval over the three INITIAL attempts is
    min(terminal_at) - max(submitted_at). Fewer than three initial attempts,
    a missing task id, or a missing/malformed/naive timestamp is UNAVAILABLE.
    A negative or zero interval is a real number and stays computable (it FAILS
    the gate); only absent or unusable evidence is UNAVAILABLE."""
    init = initial_attempts(receipts)
    if len(init) < INITIAL_ATTEMPTS:
        return None, "UNAVAILABLE"
    start, end = [], []
    for r in init:
        if not r.get("task_id") or not r.get("submitted_at") or not r.get("terminal_at"):
            return None, "UNAVAILABLE"
        try:
            s, t = _utc(r["submitted_at"]), _utc(r["terminal_at"])
        except (OverlapError, ValueError, TypeError):
            return None, "UNAVAILABLE"
        start.append(s)
        end.append(t)
    return round((min(end) - max(start)).total_seconds(), 3), None


def overlap_gate(receipts, min_s=MIN_OVERLAP_S):
    """PASS / FAIL / UNAVAILABLE over the three INITIAL attempts.

    PASS opens approval and delivery; FAIL and UNAVAILABLE both refuse. The
    result never authorizes a paid redo: ``paid_redo`` is always False and
    ``requires_owner_authority`` is always True."""
    seconds, status = overlap_seconds(receipts)
    if seconds is None:
        verdict, reason = "UNAVAILABLE", "OVERLAP_EVIDENCE_UNAVAILABLE"
        detail = ("no submitted/terminal provider timestamps for three initial "
                  "attempts: provider overlap is UNAVAILABLE, never a pass")
    elif seconds >= min_s:
        verdict, reason = "PASS", "OVERLAP_OK"
        detail = "three initial attempts overlapped %.3f s (floor %.3f s)" % (seconds, min_s)
    else:
        verdict, reason = "FAIL", "OVERLAP_BELOW_FLOOR"
        detail = ("the three initial attempts overlapped only %.3f s; the floor "
                  "is %.3f s" % (seconds, min_s))
    return {
        "verdict": verdict,
        "reason_code": reason,
        "allowed": verdict == "PASS",
        "overlap_s": seconds,
        "min_overlap_s": min_s,
        "initial_attempts": len(initial_attempts(receipts)),
        "detail": detail,
        "paid_redo": False,                    # NO AUTOMATIC PAID REDO
        "requires_owner_authority": True,      # new spend needs the owner's word
        "preserve_paid_tracks": True,          # every billed take stays on disk
        "next_action": (
            "Do not re-generate. Preserve the paid tracks and report %s. Any new "
            "spend requires explicit owner authority." % verdict),
        "source": "TREVOR ORDER 2026-10-11 (WWFIX item 3): overlap >= 1.000 s",
    }


def assert_overlap(receipts, min_s=MIN_OVERLAP_S):
    """Raise unless the three INITIAL attempts overlapped at least ``min_s``.
    Returns the gate result when it PASSes."""
    gate = overlap_gate(receipts, min_s)
    if not gate["allowed"]:
        raise OverlapError("%s: %s" % (gate["reason_code"], gate["detail"]))
    return gate


def receipts_from_results(results):
    """Every overlap receipt carried by generate_choices' results, in order."""
    out = []
    for r in results or []:
        out += [x for x in (r.get("overlap_receipts") or []) if isinstance(x, dict)]
    return out
