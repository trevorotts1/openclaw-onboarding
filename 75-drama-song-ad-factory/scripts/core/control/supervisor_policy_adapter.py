#!/usr/bin/env python3
"""S75-T34: supervisor policy adapter — the changed control layer.

The loop-control documents describe recovery in prose. This module turns the
parts that can be decided from observations into enforceable decisions:

  * DETECTION of a missed ready dispatch and of an owned violation, from the
    observed assignment/worker records rather than from a status label;
  * CHECKPOINT PRESERVATION with readback, including an honest record of the
    paths that were deliberately not read because their owner may be writing;
  * an ORDERED STOP: fence (with readback), one exact-owner graceful request
    with a finite deadline, scoped termination only after the deadline is
    ignored and the fingerprint is revalidated, then STOPPED_VERIFIED only on
    process-absent + terminal-ack + write-owner readback + owner counted.
    Replacement is refused until that proof exists;
  * UNKNOWN ownership isolates access and assignment, never kills;
  * RESTART reconciliation that loads the current and previous checkpoint,
    replays newer events and tombstones, preserves counters, and lets a
    successor start read-only until one generation is transferred after
    STOPPED_VERIFIED;
  * ACTIVATION that a document, an open terminal or a heartbeat cannot reach:
    only the installed-controller/startup/owner-generation/state-path/
    operation/failure-injection readback can.

Every host effect is injected. This module starts, signals and inspects no
process, opens no socket, names no credential and uses stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

__all__ = [
    "ACTIVE", "ISOLATED_UNKNOWN_OWNER", "MISSED_READY", "NOT_ACTIVE",
    "OWNED_VIOLATION", "REQUIRED_ACTIVATION_FACETS", "REQUIRED_OPERATIONS",
    "STOPPED_VERIFIED", "STOP_UNVERIFIED", "ControlRefused",
    "ReplacementRefused", "RestartRefused", "StopRefused", "activation_status",
    "assess", "detect_missed_ready", "detect_owned_violation",
    "isolate_unknown_owner", "plan_replacement", "preserve_checkpoint",
    "read_evidence", "reconcile_restart", "stop_verified_offender",
    "transfer_control", "verify_checkpoint", "write_evidence",
]

MISSED_READY = "MISSED_READY"
OWNED_VIOLATION = "OWNED_VIOLATION"
STOPPED_VERIFIED = "STOPPED_VERIFIED"
STOP_UNVERIFIED = "STOP_UNVERIFIED"
ISOLATED_UNKNOWN_OWNER = "ISOLATED_UNKNOWN_OWNER"
ACTIVE = "ACTIVE"
NOT_ACTIVE = "NOT_ACTIVE"

ASSESSMENT_SCHEMA = "s75.control-assessment/v1"
CHECKPOINT_SCHEMA = "s75.control-checkpoint/v1"
STOP_SCHEMA = "s75.control-stop/v1"
REPLACEMENT_SCHEMA = "s75.control-replacement/v1"
ISOLATION_SCHEMA = "s75.control-isolation/v1"
RESTART_SCHEMA = "s75.control-restart/v1"
TRANSFER_SCHEMA = "s75.control-transfer/v1"
ACTIVATION_SCHEMA = "s75.control-activation/v1"

#: A process is owned only when all of these were read back. A name, a cwd or
#: a guessed PID alone is explicitly not an identity.
FINGERPRINT_FIELDS = ("pid", "start_identity", "executable", "cwd", "project")

#: The operations activation must be able to perform through the host.
REQUIRED_OPERATIONS = ("observe", "dispatch", "lease", "fence", "stop",
                       "verify", "terminate", "report")

#: Facets whose readback is required before LOOP ACTIVE.
REQUIRED_ACTIVATION_FACETS = (
    "controller_identity",
    "controller_revision",
    "policy",
    "startup_readback",
    "owner_generation_readback",
    "state_path_proof",
    "supported_operations",
    "failure_injection_receipt",
)

#: Evidence that is real but can never establish ACTIVE on its own.
DISQUALIFIED_EVIDENCE = ("documents", "document", "heartbeat", "heartbeat_utc",
                         "open_terminal", "terminal_open")

POLICY_FIELDS = ("control_interval_seconds", "ready_unassigned_threshold_ticks",
                 "stop_grace_seconds")


class ControlRefused(RuntimeError):
    """A control decision that the supplied observations do not support."""


class StopRefused(ControlRefused):
    """The stop sequence cannot proceed in the required order."""


class ReplacementRefused(ControlRefused):
    """No successor may start: the predecessor proof is not complete."""


class RestartRefused(ControlRefused):
    """Restart/takeover reconciliation cannot proceed safely."""


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _int(value, default=0):
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _fingerprint_problem(worker):
    """Return the fields that prevent this record from being an identity."""
    if not isinstance(worker, dict):
        return list(FINGERPRINT_FIELDS)
    missing = []
    for field in FINGERPRINT_FIELDS:
        value = worker.get(field)
        if field == "pid":
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                missing.append(field)
        elif not _text(value):
            missing.append(field)
    return missing


def detect_missed_ready(assignments, threshold_ticks=2):
    """Assignments that sat ready/unassigned past the policy threshold.

    READY_WITHOUT_DISPATCH is the violation: after ``threshold_ticks`` control
    ticks an undispatched ready assignment has missed its ready dispatch. A
    stored dispatch receipt on the assignment means it is not missed.
    """
    threshold = _int(threshold_ticks, 2)
    if threshold < 1:
        raise ControlRefused("READY_THRESHOLD_MUST_BE_POSITIVE")
    violations = []
    for assignment in assignments or ():
        unit_id = _text(assignment.get("unit_id"))
        if not unit_id:
            raise ControlRefused("ASSIGNMENT_MISSING_UNIT_ID")
        state = _text(assignment.get("state")).upper()
        if state not in ("READY", "QUEUED"):
            continue
        age = _int(assignment.get("ready_age_ticks"), 0)
        if age < threshold:
            continue
        if assignment.get("dispatch_receipt"):
            continue
        violations.append({
            "class": MISSED_READY,
            "unit_id": unit_id,
            "reason": "READY_WITHOUT_DISPATCH",
            "ready_age_ticks": age,
            "threshold_ticks": threshold,
            "attempt_generation": _int(assignment.get("attempt_generation"), 0) or None,
        })
    return sorted(violations, key=lambda row: (row["class"], row["unit_id"], row["reason"]))


def detect_owned_violation(assignment, worker, *, project=None, shared_writers=None):
    """Classify an observed worker against the assignment that claims it.

    ``OWNER_UNKNOWN`` is returned for a missing or incomplete fingerprint: a
    bare PID, a process name or a cwd is not ownership, so no kill decision
    may be derived from it.
    """
    unit_id = _text(assignment.get("unit_id"))
    if not unit_id:
        raise ControlRefused("ASSIGNMENT_MISSING_UNIT_ID")
    expected_project = _text(project) or _text(assignment.get("project"))

    missing = _fingerprint_problem(worker)
    if missing:
        return {
            "status": "OWNER_UNKNOWN",
            "unit_id": unit_id,
            "reason": "NO_FINGERPRINT" if not isinstance(worker, dict) else "INCOMPLETE_FINGERPRINT",
            "missing_fields": missing,
            "violations": [],
        }

    violations = []
    if expected_project and _text(worker.get("project")) != expected_project:
        violations.append({
            "class": OWNED_VIOLATION,
            "unit_id": unit_id,
            "reason": "FOREIGN_PROJECT_WRITER",
            "expected_project": expected_project,
            "observed_project": _text(worker.get("project")),
        })

    expected_lease = _int(assignment.get("lease_generation"), -1)
    observed_lease = _int(worker.get("lease_generation"), -1)
    if expected_lease != observed_lease:
        violations.append({
            "class": OWNED_VIOLATION,
            "unit_id": unit_id,
            "reason": "LEASE_GENERATION_MISMATCH",
            "expected_lease_generation": expected_lease,
            "observed_lease_generation": observed_lease,
        })

    expected_owner = _text(assignment.get("owner"))
    observed_owner = _text(worker.get("owner_id")) or _text(worker.get("owner"))
    if expected_owner and observed_owner and expected_owner != observed_owner:
        violations.append({
            "class": OWNED_VIOLATION,
            "unit_id": unit_id,
            "reason": "OWNER_MISMATCH",
            "expected_owner": expected_owner,
            "observed_owner": observed_owner,
        })

    claimed_paths = set(assignment.get("shared_paths") or ())
    for path in sorted(shared_writers or {}):
        if path not in claimed_paths:
            continue
        owners = sorted({_text(owner) for owner in shared_writers[path] if _text(owner)})
        if len(owners) > 1:
            violations.append({
                "class": OWNED_VIOLATION,
                "unit_id": unit_id,
                "reason": "SHARED_FILE_SECOND_WRITER",
                "shared_path": path,
                "owners": owners,
            })

    violations.sort(key=lambda row: (row["class"], row["unit_id"], row["reason"]))
    return {
        "status": OWNED_VIOLATION if violations else "OWNED_OK",
        "unit_id": unit_id,
        "violations": violations,
        "missing_fields": [],
    }


def assess(assignments, workers=None, *, threshold_ticks=2, project=None,
           shared_writers=None):
    """One deterministic assessment over observed assignments and workers."""
    assignments = list(assignments or ())
    workers = dict(workers or {})
    violations = list(detect_missed_ready(assignments, threshold_ticks))
    unknown = []
    for assignment in assignments:
        unit_id = _text(assignment.get("unit_id"))
        if not unit_id:
            raise ControlRefused("ASSIGNMENT_MISSING_UNIT_ID")
        result = detect_owned_violation(
            assignment, workers.get(unit_id), project=project,
            shared_writers=shared_writers)
        if result["status"] == OWNED_VIOLATION:
            violations.extend(result["violations"])
        elif result["status"] == "OWNER_UNKNOWN":
            unknown.append({
                "unit_id": unit_id,
                "reason": result["reason"],
                "missing_fields": result["missing_fields"],
            })
    violations.sort(key=lambda row: (row["class"], row["unit_id"], row["reason"]))
    unknown.sort(key=lambda row: (row["unit_id"], row["reason"]))
    return {
        "schema": ASSESSMENT_SCHEMA,
        "checked": len(assignments),
        "threshold_ticks": _int(threshold_ticks, 2),
        "violations": violations,
        "unknown_owners": unknown,
        "clean": not violations and not unknown,
    }


def _safe_slot(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text)[:120]


def preserve_checkpoint(assignment, state_dir, *, volatile_paths=(), sequence=None):
    """Write and read back the checkpoint a recovery will rely on.

    Volatile paths are recorded as NOT_READ on purpose: their owner may still
    be writing, and copying them would misrepresent partial content.
    """
    unit_id = _text(assignment.get("unit_id"))
    generation = _int(assignment.get("attempt_generation"), 0)
    if not unit_id or generation < 1:
        raise ControlRefused("CHECKPOINT_NEEDS_UNIT_AND_GENERATION")
    volatile = [{
        "path": _text(path),
        "status": "NOT_READ",
        "reason": "owner may still be writing; not copied and not claimed intact",
    } for path in volatile_paths if _text(path)]
    payload = {
        "schema": CHECKPOINT_SCHEMA,
        "unit_id": unit_id,
        "attempt_generation": generation,
        "project": _text(assignment.get("project")),
        "state": _text(assignment.get("state")),
        "owner": _text(assignment.get("owner")),
        "lease_generation": _int(assignment.get("lease_generation"), -1),
        "scope": assignment.get("scope"),
        "counters": dict(assignment.get("counters") or {}),
        "sequence": _int(sequence if sequence is not None else assignment.get("sequence"), 0),
        "volatile_paths": volatile,
    }
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, _safe_slot("%s.g%d" % (unit_id, generation)) + ".checkpoint.json")
    temporary = path + ".tmp"
    with open(temporary, "wb") as handle:
        handle.write(raw)
    os.replace(temporary, path)
    with open(path, "rb") as handle:
        readback = handle.read()
    if readback != raw:
        raise ControlRefused("CHECKPOINT_READBACK_MISMATCH")
    return {
        "schema": CHECKPOINT_SCHEMA,
        "path": os.path.abspath(path),
        "digest": "sha256:" + hashlib.sha256(readback).hexdigest(),
        "bytes": len(readback),
        "readable": True,
        "unit_id": unit_id,
        "attempt_generation": generation,
        "scope": payload["scope"],
        "counters": payload["counters"],
        "sequence": payload["sequence"],
        "volatile_paths": volatile,
    }


def verify_checkpoint(receipt):
    """Re-read the preserved checkpoint and compare its digest."""
    path = _text((receipt or {}).get("path"))
    expected = _text((receipt or {}).get("digest"))
    if not path or not expected:
        return False
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        return False
    return "sha256:" + hashlib.sha256(raw).hexdigest() == expected


def _stop_result(status, reason, offender, events, terminated, grace_seconds):
    return {
        "schema": STOP_SCHEMA,
        "status": status,
        "reason": reason,
        "offender": dict(offender),
        "events": list(events),
        "terminated": bool(terminated),
        "grace_seconds": grace_seconds,
    }


def stop_verified_offender(offender, effects, *, grace_seconds=60):
    """Fence, request, observe, (scoped terminate), verify — in that order.

    Returns STOP_UNVERIFIED whenever a proof is missing; callers must not
    start a replacement on anything but STOPPED_VERIFIED.
    """
    if not isinstance(offender, dict):
        raise StopRefused("OFFENDER_MISSING_FINGERPRINT")
    missing = _fingerprint_problem(offender)
    if missing:
        raise StopRefused("INCOMPLETE_OFFENDER_FINGERPRINT:" + ",".join(missing))
    if offender.get("shared_service"):
        raise StopRefused("PROTECTED_SHARED_SERVICE")
    grace = _int(grace_seconds, 0)
    if grace < 1:
        raise StopRefused("GRACE_MUST_BE_POSITIVE")

    events = []

    fenced = effects.fence(offender) or {}
    events.append({"step": "FENCE", "fenced": fenced.get("fenced") is True,
                   "readback_verified": fenced.get("readback_verified") is True})
    if not (fenced.get("fenced") is True and fenced.get("readback_verified") is True):
        raise StopRefused("FENCE_UNVERIFIED")

    request = effects.request_stop(offender, grace) or {}
    events.append({"step": "STOP_REQUEST", "ack": request.get("ack") is True,
                   "deadline_seconds": grace})

    observed = effects.observe(offender) or {}
    events.append({"step": "OBSERVE", "running": bool(observed.get("running")),
                   "grace_expired": bool(observed.get("grace_expired"))})

    terminated = False
    if observed.get("running") and observed.get("grace_expired"):
        revalidated = effects.revalidate_fingerprint(offender) or {}
        events.append({"step": "REVALIDATE", "matches": revalidated.get("matches") is True})
        if revalidated.get("matches") is not True:
            return _stop_result(STOP_UNVERIFIED, "FINGERPRINT_CHANGED", offender,
                                events, terminated, grace)
        termination = effects.terminate_scoped(offender) or {}
        targets = termination.get("terminated")
        events.append({"step": "TERMINATE_SCOPED", "targets": list(targets or ())})
        if termination.get("affected_services"):
            raise StopRefused("PROTECTED_SERVICE_TOUCHED")
        if not isinstance(targets, list) or not targets:
            raise StopRefused("TERMINATION_UNPROVEN")
        for target in targets:
            if (_int((target or {}).get("pid"), -1) != offender["pid"]
                    or _text((target or {}).get("start_identity")) != _text(offender.get("start_identity"))):
                raise StopRefused("SCOPE_ESCAPE")
        terminated = True
        observed = effects.observe(offender) or {}
        events.append({"step": "OBSERVE", "running": bool(observed.get("running")),
                       "grace_expired": bool(observed.get("grace_expired"))})

    if observed.get("running"):
        return _stop_result(STOP_UNVERIFIED, "STILL_RUNNING", offender, events,
                            terminated, grace)

    proof = effects.verify_stopped(offender) or {}
    events.append({
        "step": "VERIFY_STOPPED",
        "process_absent": proof.get("process_absent") is True,
        "terminal_ack": proof.get("terminal_ack") is True,
        "write_owner_readback": bool(proof.get("write_owner_readback")),
        "owner_counted": proof.get("owner_counted") is True,
    })
    verified = (
        proof.get("process_absent") is True
        and proof.get("terminal_ack") is True
        and bool(proof.get("write_owner_readback"))
        and proof.get("owner_counted") is True
    )
    if not verified:
        return _stop_result(STOP_UNVERIFIED, "STOP_PROOF_INCOMPLETE", offender,
                            events, terminated, grace)
    return _stop_result(STOPPED_VERIFIED, None, offender, events, terminated, grace)


def plan_replacement(predecessor, successor, *, stop_result, checkpoint):
    """Start exactly one successor, only after verified stop + checkpoint."""
    if not isinstance(stop_result, dict) or stop_result.get("status") != STOPPED_VERIFIED:
        raise ReplacementRefused("PREDECESSOR_NOT_STOPPED_VERIFIED")
    if not isinstance(checkpoint, dict) or checkpoint.get("readable") is not True \
            or not _text(checkpoint.get("digest")):
        raise ReplacementRefused("CHECKPOINT_NOT_PRESERVED")
    if _text(successor.get("unit_id")) != _text(predecessor.get("unit_id")):
        raise ReplacementRefused("UNIT_CHANGED")
    predecessor_generation = _int(predecessor.get("attempt_generation"), 0)
    successor_generation = _int(successor.get("attempt_generation"), 0)
    if successor_generation <= predecessor_generation:
        raise ReplacementRefused("SUCCESSOR_GENERATION_NOT_FRESH")
    if successor.get("exclusive_lease") is not True:
        raise ReplacementRefused("SUCCESSOR_LEASE_NOT_EXCLUSIVE")
    if _text(successor.get("state")).upper() not in ("", "QUEUED", "READY"):
        raise ReplacementRefused("SUCCESSOR_NOT_A_FRESH_START")
    if successor.get("scope") != checkpoint.get("scope"):
        raise ReplacementRefused("SCOPE_CHANGED")
    stopped = stop_result.get("offender") or {}
    predecessor_pid = predecessor.get("pid")
    if predecessor_pid is not None and _int(stopped.get("pid"), -1) != _int(predecessor_pid, -2):
        raise ReplacementRefused("STOP_TARGET_MISMATCH")

    result_successor = dict(successor)
    result_successor.update({
        "state": "DISPATCHED",
        "scope_preserved": True,
        "replaces_attempt_generation": predecessor_generation,
        "predecessor_status": STOPPED_VERIFIED,
    })
    return {
        "schema": REPLACEMENT_SCHEMA,
        "status": "REPLACED",
        "predecessor": {
            "unit_id": _text(predecessor.get("unit_id")),
            "attempt_generation": predecessor_generation,
            "status": STOPPED_VERIFIED,
        },
        "checkpoint_digest": checkpoint.get("digest"),
        "successor": result_successor,
    }


def isolate_unknown_owner(assignment, effects):
    """Fence access and assignment for an unknown owner. Never kill."""
    unit_id = _text(assignment.get("unit_id"))
    if not unit_id:
        raise ControlRefused("ASSIGNMENT_MISSING_UNIT_ID")
    if assignment.get("owner_verified") is True and _text(assignment.get("owner")):
        raise ControlRefused("OWNER_IS_KNOWN")

    result = effects.isolate({
        "unit_id": unit_id,
        "attempt_generation": _int(assignment.get("attempt_generation"), 0) or None,
        "project": _text(assignment.get("project")),
        "scope": assignment.get("scope"),
    }) or {}
    if not (result.get("access_fenced") is True
            and result.get("assignment_fenced") is True
            and result.get("readback_verified") is True):
        raise ControlRefused("ISOLATION_UNVERIFIED")
    if result.get("killed") or result.get("terminated") or result.get("stop_requests"):
        raise ControlRefused("ISOLATION_WAS_DESTRUCTIVE")
    return {
        "schema": ISOLATION_SCHEMA,
        "status": ISOLATED_UNKNOWN_OWNER,
        "unit_id": unit_id,
        "killed": False,
        "owner_counted": True,
        "isolation": {
            "access_fenced": True,
            "assignment_fenced": True,
            "readback_verified": True,
        },
        "uncertainty": "OWNER_UNKNOWN: no kill, access and assignment isolated under control",
    }


def _load_checkpoints(state_dir, unit_id=None):
    if not os.path.isdir(state_dir):
        raise RestartRefused("NO_READABLE_CHECKPOINT")
    loaded = []
    for name in sorted(os.listdir(state_dir)):
        if not name.endswith(".checkpoint.json"):
            continue
        path = os.path.join(state_dir, name)
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict) or payload.get("schema") != CHECKPOINT_SCHEMA:
            continue
        if unit_id and _text(payload.get("unit_id")) != unit_id:
            continue
        payload["_path"] = os.path.abspath(path)
        payload["_digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        loaded.append(payload)
    if not loaded:
        raise RestartRefused("NO_READABLE_CHECKPOINT")
    loaded.sort(key=lambda row: (_text(row.get("unit_id")),
                                 _int(row.get("attempt_generation"), 0)))
    return loaded


def reconcile_restart(state_dir, events=(), *, predecessor_status=None, jobs=(),
                      workers=(), unit_id=None):
    """Load current+previous checkpoint, replay newer events, plan read-only start."""
    loaded = _load_checkpoints(state_dir, unit_id)
    current = loaded[-1]
    previous = loaded[-2] if len(loaded) > 1 else None

    holds = {}
    tombstones = set()
    decisions = []
    applied = []
    skipped = []
    unresolved = []
    for event in sorted(events or (), key=lambda row: _int(row.get("sequence"), 0)):
        sequence = _int(event.get("sequence"), 0)
        kind = _text(event.get("kind")).upper()
        identity = _text(event.get("id")) or "seq-%d" % sequence
        if sequence <= _int(current.get("sequence"), 0):
            skipped.append({"sequence": sequence, "kind": kind, "id": identity})
            continue
        if kind == "HOLD":
            holds[identity] = _text(event.get("status")) or "HELD"
        elif kind == "RELEASE":
            holds.pop(identity, None)
        elif kind == "TOMBSTONE":
            tombstones.add(identity)
        elif kind == "DECISION":
            decisions.append({"id": identity, "decision": event.get("decision")})
        else:
            unresolved.append({"sequence": sequence, "kind": kind, "id": identity,
                               "reason": "UNRECOGNIZED_EVENT_KIND"})
            continue
        applied.append({"sequence": sequence, "kind": kind, "id": identity})

    job_ids = [(_text(job.get("id")) if isinstance(job, dict) else _text(job))
               for job in (jobs or ())]
    job_ids = [job for job in job_ids if job]
    if len(job_ids) > 1:
        raise RestartRefused("DUPLICATE_SUPERVISION_JOB")

    current_lease = _int(current.get("lease_generation"), -1)
    reconciled_workers = []
    unknown_workers = 0
    for worker in workers or ():
        missing = _fingerprint_problem(worker)
        if missing:
            unknown_workers += 1
            reconciled_workers.append({
                "reason": "INCOMPLETE_FINGERPRINT",
                "missing_fields": missing,
                "action": "ISOLATE_NONDESTRUCTIVELY",
            })
            continue
        matching = _int(worker.get("lease_generation"), -2) == current_lease
        reconciled_workers.append({
            "pid": worker.get("pid"),
            "start_identity": _text(worker.get("start_identity")),
            "action": "RETAINED" if matching else "NEEDS_RECONCILIATION",
        })

    transfer_allowed = predecessor_status == STOPPED_VERIFIED
    return {
        "schema": RESTART_SCHEMA,
        "current": {
            "path": current["_path"],
            "digest": current["_digest"],
            "unit_id": _text(current.get("unit_id")),
            "attempt_generation": _int(current.get("attempt_generation"), 0),
            "sequence": _int(current.get("sequence"), 0),
        },
        "previous": None if previous is None else {
            "path": previous["_path"],
            "digest": previous["_digest"],
            "unit_id": _text(previous.get("unit_id")),
            "attempt_generation": _int(previous.get("attempt_generation"), 0),
            "sequence": _int(previous.get("sequence"), 0),
        },
        "events_applied": applied,
        "events_skipped": skipped,
        "holds": dict(sorted(holds.items())),
        "tombstones": sorted(tombstones),
        "decisions": decisions,
        "counters": dict(current.get("counters") or {}),
        "counters_reset": False,
        "volatile_paths": list(current.get("volatile_paths") or ()),
        "jobs": job_ids,
        "job_gap": None if job_ids else "NO_SUPERVISION_JOB_REGISTERED",
        "workers": reconciled_workers,
        "unknown_workers": unknown_workers,
        "unresolved": unresolved,
        "successor_plan": {
            "read_only": True,
            "generation_transfer_allowed": transfer_allowed,
            "requires": "predecessor STOPPED_VERIFIED through the supported fencing/handoff path",
        },
    }


def transfer_control(predecessor, generation, *, predecessor_status, successor):
    """Move exactly one control generation, and only after a verified stop."""
    if predecessor_status != STOPPED_VERIFIED:
        raise RestartRefused("PREDECESSOR_NOT_STOPPED_VERIFIED")
    current_generation = _int(predecessor.get("control_generation"), 0)
    if _int(generation, 0) != current_generation + 1:
        raise RestartRefused("GENERATION_NOT_NEXT")
    if successor.get("control_generation") is not None:
        raise RestartRefused("GENERATION_ALREADY_TRANSFERRED")
    result = dict(successor)
    result.update({
        "control_generation": current_generation + 1,
        "read_only": False,
    })
    return {
        "schema": TRANSFER_SCHEMA,
        "status": "TRANSFERRED",
        "from_generation": current_generation,
        "to_generation": current_generation + 1,
        "successor": result,
    }


def _facet_problem(facet, value):
    if facet == "controller_identity":
        if isinstance(value, dict) and _text(value.get("id")):
            return None
        return "CONTROLLER_IDENTITY_UNREAD"
    if facet == "controller_revision":
        if isinstance(value, int) and not isinstance(value, bool):
            return None
        return None if _text(value) else "CONTROLLER_REVISION_UNREAD"
    if facet == "policy":
        if not isinstance(value, dict):
            return "POLICY_UNREAD"
        gaps = [field for field in POLICY_FIELDS if field not in value]
        if gaps:
            return "POLICY_FIELDS_MISSING:" + ",".join(gaps)
        return None if value.get("readback_verified") is True else "POLICY_READBACK_UNVERIFIED"
    if facet == "startup_readback":
        if isinstance(value, dict) and value.get("readback_verified") is True \
                and (_text(value.get("started_at")) or _int(value.get("started_at"), 0) > 0):
            return None
        return "STARTUP_READBACK_MISSING"
    if facet == "owner_generation_readback":
        if isinstance(value, dict) and value.get("readback_verified") is True \
                and _int(value.get("generation"), 0) >= 1:
            return None
        return "OWNER_GENERATION_READBACK_MISSING"
    if facet == "state_path_proof":
        if isinstance(value, dict) and _text(value.get("path")) \
                and value.get("portable_verified") is True:
            return None
        return "STATE_PATH_UNVERIFIED"
    if facet == "supported_operations":
        if not isinstance(value, (list, tuple)):
            return "SUPPORTED_OPERATIONS_UNREAD"
        gaps = [operation for operation in REQUIRED_OPERATIONS if operation not in value]
        return "CAPABILITY_GAPS:" + ",".join(gaps) if gaps else None
    if facet == "failure_injection_receipt":
        if isinstance(value, dict) and value.get("independent") is True \
                and value.get("detected") is True \
                and _text(value.get("outcome")):
            return None
        return "INDEPENDENT_FAILURE_INJECTION_MISSING"
    return "UNKNOWN_FACET"


def activation_status(readback):
    """ACTIVE only from installed-controller readback; never from prose."""
    readback = dict(readback or {})
    disqualified = sorted(key for key in DISQUALIFIED_EVIDENCE if key in readback)
    problems = {}
    for facet in REQUIRED_ACTIVATION_FACETS:
        problem = _facet_problem(facet, readback.get(facet))
        if problem:
            problems[facet] = problem

    operations = readback.get("supported_operations")
    gaps = []
    if isinstance(operations, (list, tuple)):
        gaps = [operation for operation in REQUIRED_OPERATIONS if operation not in operations]

    only_disqualified = bool(readback) and set(readback).issubset(set(DISQUALIFIED_EVIDENCE))
    if problems:
        return {
            "schema": ACTIVATION_SCHEMA,
            "status": NOT_ACTIVE,
            "reason": "ACTIVATION_PROOF_INCOMPLETE",
            "evidence": "DOCUMENT_HEARTBEAT_ONLY" if only_disqualified else "INCOMPLETE_READBACK",
            "missing": sorted(problems),
            "problems": problems,
            "capability_gaps": gaps,
            "disqualified_evidence": disqualified,
        }
    return {
        "schema": ACTIVATION_SCHEMA,
        "status": ACTIVE,
        "reason": None,
        "evidence": "INSTALLED_CONTROLLER_READBACK",
        "missing": [],
        "problems": {},
        "capability_gaps": [],
        "disqualified_evidence": disqualified,
    }


def write_evidence(path, payload):
    """Atomically write a receipt; return its digest and size."""
    text = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    absolute = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    temporary = absolute + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(temporary, absolute)
    with open(absolute, "rb") as handle:
        raw = handle.read()
    return {
        "path": absolute,
        "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def read_evidence(path):
    try:
        with open(path, "rb") as handle:
            return json.loads(handle.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
