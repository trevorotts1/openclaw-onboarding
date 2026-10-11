#!/usr/bin/env python3
"""Provider-overlap receipts and the three-initial-attempt overlap gate.

TREVOR ORDER 2026-10-11 (WWFIX item 3), implemented exactly, and then repaired
by WW-10 (WW-PREVENT-RECURRENCE-SPEC section 3, Unit U1):

  * the overlap test runs over the THREE INITIAL attempts only -- a regenerated
    variant (for example v3r) never counts as initial overlap evidence;
  * the three attempts must carry EXACTLY THREE DISTINCT initial identities --
    a VARIANT, an ATTEMPT and a TASK id, each one distinct across the three
    receipts. Duplicated or identical receipts FAIL; they never PASS.
  * the common provider-task interval is min(terminal_at) - max(accepted_submit_at),
    compared as INTEGER MICROSECONDS with NO rounding. PASS requires
    >= 1,000,000 microseconds (1.000 s); 0.999 s FAILS.
  * MISSING trustworthy lifecycle evidence is UNAVAILABLE; MALFORMED, REVERSED,
    DUPLICATED or DIGEST-MISMATCHED evidence is FAIL. Both refuse.
  * NO AUTOMATIC PAID REDO: a missing overlap or a missing receipt never buys
    another paid generation. Every already-paid track is preserved; new spend
    requires the owner's explicit authority.

THE LABELLED CLOCK DISTINCTION IS KEPT. A provider lifecycle stamp is only
trustworthy when it is labelled as such:
  * ``accepted_submit_at`` -- the provider's task-id acknowledgement clock,
    written only after a valid task id came back;
  * ``terminal_at`` -- the first terminal provider response, before any
    save / download / separation / judging;
  * ``timestamp_source`` labels the origin. A LOCAL-observed clock, or polling
    or file times, can never prove concurrency and is NEVER backfilled into a
    provider field. A naive (local) timestamp is refused.
An unlabelled or local-only clock is not admissible and makes the gate
UNAVAILABLE -- never a pass.

HONEST SCOPE. This is a CONCURRENCY-EVIDENCE fix. It did not cause the thin rap,
the dead-air intro or the paper arc of the failed run, and on that run's own
timestamps a correct implementation would PASS. It only stops thread counts,
duplicated receipts and post-processing delay from fabricating concurrency.

A receipt also binds what was PAID, so a finished, charged take can never be
reported as unpaid: ``billed_cents`` and ``completed`` ride every receipt, and a
terminal timestamp with ``completed`` True and a non-zero ``billed_cents`` is a
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
#: WW-10: the SAME floor expressed as integer microseconds, so no float rounding
#: can lift 0.999 s to a pass. PASS only at or above this value.
MIN_OVERLAP_US = 1_000_000

#: The number of INITIAL attempts the gate requires.
INITIAL_ATTEMPTS = 3

#: WW-10: the three DISTINCT identities every initial receipt must carry.
DISTINCT_IDENTITY_FIELDS = ("variant_id", "attempt_id", "task_id")

#: WW-10 honest scope marker -- what this fix is and is not.
SCOPE = "CONCURRENCY_EVIDENCE"


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


def _us_delta(a, b):
    """Exact integer microseconds of ``b - a``. No float, no rounding."""
    d = b - a
    return (d.days * 86400 + d.seconds) * 1_000_000 + d.microseconds


def iso_z(value):
    """An aware-UTC timestamp as the canonical receipt string (MICROSECONDS, Z).

    Full microsecond precision is kept on purpose: WW-10 compares integer
    microseconds, so truncating to milliseconds could hide the 999,999 us that
    must FAIL."""
    return _utc(value).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def request_sha256(request):
    """The sha256 of the exact request payload (sorted JSON, stable across runs)."""
    blob = json.dumps(request, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def receipt_sha256(receipt):
    """The digest binding a receipt to its own recorded values.

    The digest covers every field except ``receipt_sha256`` itself, so a receipt
    edited after it was written is DIGEST-MISMATCHED and FAILS the gate."""
    rec = {k: v for k, v in (receipt or {}).items() if k != "receipt_sha256"}
    blob = json.dumps(rec, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def make_receipt(variant_id, request, logical_key, attempt_id, task_id,
                 submitted_at, terminal_at, billed_cents=0, completed=None,
                 initial=None, timestamp_source="provider-task-ack"):
    """One attempt's receipt: variant, request and task ids with both provider
    times, plus what it was billed so a paid take is never read as unpaid.

    ``submitted_at`` is recorded as BOTH the raw submit time and the labelled
    provider ``accepted_submit_at`` (the task-id acknowledgement clock).
    ``initial`` defaults to True for the first three attempts of a variant and
    False for a regenerated attempt; callers may set it explicitly. Both times
    are stored as aware-UTC strings. A ``receipt_sha256`` digest binds the row."""
    if initial is None:
        try:
            initial = int(str(attempt_id).lstrip("aA") or 1) <= INITIAL_ATTEMPTS
        except (TypeError, ValueError):
            initial = False
    done = bool(terminal_at) if completed is None else bool(completed)
    rec = {
        "schema": SCHEMA,
        "variant_id": str(variant_id),
        "request_sha256": request_sha256(request),
        "logical_key": str(logical_key),
        "attempt_id": str(attempt_id),
        "task_id": None if task_id is None else str(task_id),
        "submitted_at": iso_z(submitted_at) if submitted_at else None,
        "accepted_submit_at": iso_z(submitted_at) if submitted_at else None,
        "terminal_at": iso_z(terminal_at) if terminal_at else None,
        "timestamp_source": str(timestamp_source),
        "initial": bool(initial),
        "billed_cents": int(billed_cents or 0),
        "completed": done,
    }
    rec["receipt_sha256"] = receipt_sha256(rec)
    return rec


def initial_attempts(receipts):
    """The INITIAL attempts in ``receipts``; a regenerated attempt never counts."""
    return [r for r in (receipts or []) if isinstance(r, dict) and r.get("initial")]


def _res(status, reason_code, microseconds, detail, **extra):
    out = {"status": status, "reason_code": reason_code,
           "microseconds": microseconds, "detail": detail}
    out.update(extra)
    return out


def _validate(receipts):
    """Classify the initial-provider evidence. One place, one rule set.

    Returns {"status", "reason_code", "microseconds", "detail", ...} where
    status is "OK" (a computable integer-microsecond interval), "UNAVAILABLE"
    (missing trustworthy lifecycle evidence) or "FAIL" (malformed, reversed,
    duplicated or digest-mismatched evidence). Never a silent pass."""
    init = initial_attempts(receipts)
    if len(init) < INITIAL_ATTEMPTS:
        return _res("UNAVAILABLE", "OVERLAP_EVIDENCE_UNAVAILABLE", None,
                    "fewer than %d initial attempts" % INITIAL_ATTEMPTS)
    if len(init) > INITIAL_ATTEMPTS:
        return _res("FAIL", "OVERLAP_TOO_MANY_INITIAL_ATTEMPTS", None,
                    "%d initial attempts, exactly %d are required"
                    % (len(init), INITIAL_ATTEMPTS))
    # distinctness: exactly three DISTINCT initial identities. Each receipt must
    # carry a variant, an attempt and a task id, and the three identities must be
    # pairwise distinct -- so the three task ids are distinct AND no two receipts
    # carry the identical (variant, attempt, task) tuple. Duplicates FAIL.
    for field in DISTINCT_IDENTITY_FIELDS:
        if any(r.get(field) in (None, "") for r in init):
            return _res("UNAVAILABLE", "OVERLAP_EVIDENCE_UNAVAILABLE", None,
                        "an initial attempt has no %s" % field)
    task_ids = [r.get("task_id") for r in init]
    if len(set(task_ids)) != INITIAL_ATTEMPTS:
        return _res("FAIL", "OVERLAP_IDENTITY_DUPLICATE", None,
                    "the three initial attempts do not carry three distinct task ids: %r"
                    % (task_ids,))
    if len({(r.get("variant_id"), r.get("attempt_id"), r.get("task_id"))
            for r in init}) != INITIAL_ATTEMPTS:
        return _res("FAIL", "OVERLAP_IDENTITY_DUPLICATE", None,
                    "two initial receipts carry the identical (variant, attempt, task) identity")
    # every receipt must be internally consistent (digest) if it carries one
    for r in init:
        stored = r.get("receipt_sha256")
        if stored is not None and stored != receipt_sha256(r):
            return _res("FAIL", "OVERLAP_DIGEST_MISMATCH", None,
                        "receipt %r is digest-mismatched (edited after it was written)"
                        % r.get("attempt_id"))
    # trustworthy lifecycle stamps: present, aware, provider-labelled
    starts, ends = [], []
    for r in init:
        if not r.get("terminal_at") or not (r.get("accepted_submit_at")
                                            or r.get("submitted_at")):
            return _res("UNAVAILABLE", "OVERLAP_EVIDENCE_UNAVAILABLE", None,
                        "attempt %r is missing a provider submit/terminal stamp"
                        % r.get("attempt_id"))
        src = str(r.get("timestamp_source") or "")
        if src in ("", "local", "local-observed", "file-time") or src.startswith("local"):
            return _res("UNAVAILABLE", "OVERLAP_CLOCK_NOT_PROVIDER", None,
                        "attempt %r carries only a local clock (%r); local times can "
                        "never prove provider overlap and are never backfilled"
                        % (r.get("attempt_id"), src))
        try:
            s = _utc(r.get("accepted_submit_at") or r.get("submitted_at"))
            t = _utc(r["terminal_at"])
        except OverlapError as e:
            # a NAIVE (timezone-less) stamp is not trustworthy lifecycle evidence
            return _res("UNAVAILABLE", "OVERLAP_CLOCK_NOT_PROVIDER", None,
                        "attempt %r has an unlabelled/local timestamp: %s"
                        % (r.get("attempt_id"), e))
        except (ValueError, TypeError) as e:
            return _res("FAIL", "OVERLAP_EVIDENCE_MALFORMED", None,
                        "attempt %r has a malformed timestamp: %s" % (r.get("attempt_id"), e))
        if t < s:
            return _res("FAIL", "OVERLAP_EVIDENCE_REVERSED", None,
                        "attempt %r terminates (%s) before it was submitted (%s)"
                        % (r.get("attempt_id"), r["terminal_at"], r.get("accepted_submit_at")))
        starts.append(s)
        ends.append(t)
    us = _us_delta(max(starts), min(ends))
    return _res("OK", "OVERLAP_COMPUTED", us,
                "common provider interval %d microseconds over three distinct initial attempts" % us)


def overlap_seconds(receipts, min_s=MIN_OVERLAP_S):
    """(seconds, None) for a computable overlap; (None, reason) otherwise.

    Kept for callers that want a number. WW-10: the value is derived from the
    EXACT integer microseconds the gate compares -- it is never a rounded
    comparison. ``min_s`` is accepted for signature compatibility but the gate
    decides on microseconds (see ``overlap_gate``)."""
    v = _validate(receipts)
    if v["status"] != "OK":
        return None, v["reason_code"]
    return v["microseconds"] / 1_000_000.0, None


def overlap_gate(receipts, min_s=MIN_OVERLAP_S):
    """PASS / FAIL / UNAVAILABLE over the three INITIAL attempts.

    PASS opens approval and delivery; FAIL and UNAVAILABLE both refuse. PASS
    needs >= 1,000,000 microseconds of common overlap across THREE DISTINCT
    initial identities. The result never authorizes a paid redo: ``paid_redo``
    is always False and ``requires_owner_authority`` is always True."""
    v = _validate(receipts)
    us = v["microseconds"]
    if v["status"] == "UNAVAILABLE":
        verdict, reason = "UNAVAILABLE", v["reason_code"]
        detail = ("%s: provider overlap is UNAVAILABLE, never a pass" % v["detail"])
    elif v["status"] == "FAIL":
        verdict, reason = "FAIL", v["reason_code"]
        detail = v["detail"]
    elif us >= MIN_OVERLAP_US:
        verdict, reason = "PASS", "OVERLAP_OK"
        detail = ("three distinct initial attempts overlapped %d microseconds "
                  "(floor %d)" % (us, MIN_OVERLAP_US))
    else:
        verdict, reason = "FAIL", "OVERLAP_BELOW_FLOOR"
        detail = ("the three distinct initial attempts overlapped only %d "
                  "microseconds; the floor is %d" % (us, MIN_OVERLAP_US))
    return {
        "verdict": verdict,
        "reason_code": reason,
        "allowed": verdict == "PASS",
        "overlap_s": None if us is None else us / 1_000_000.0,
        "overlap_us": us,
        "min_overlap_s": MIN_OVERLAP_S,
        "min_overlap_us": MIN_OVERLAP_US,
        "initial_attempts": len(initial_attempts(receipts)),
        "distinct_identities": sorted(
            {r.get("task_id") for r in initial_attempts(receipts)
             if r.get("task_id")}),
        "detail": detail,
        "paid_redo": False,                    # NO AUTOMATIC PAID REDO
        "requires_owner_authority": True,      # new spend needs the owner's word
        "preserve_paid_tracks": True,          # every billed take stays on disk
        "next_action": (
            "Do not re-generate. Preserve the paid tracks and report %s. Any new "
            "spend requires explicit owner authority." % verdict),
        "scope": SCOPE,
        "scope_note": ("a concurrency-evidence fix only: it did not cause the thin "
                       "rap, dead-air intro or paper arc of the failed run"),
        "microseconds_compared_without_rounding": True,
        "source": "WWFIX item 3 + WW-10: three distinct identities, integer "
                  "microseconds, floor 1000000 us",
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
