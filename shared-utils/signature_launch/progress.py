#!/usr/bin/env python3
"""Resumable launch progress file: every unit's state, one percentage.

WF-SWARM progress lane. One JSON file per launch (keyed by launch_id), holding
every unit from the approved launch plan (pages, email sequences, text sets,
automations). A stopped run resumes from this file:

- finished units are skipped (never re-dispatched, never re-charged),
- a crashed run is recovered ONLY from current admission evidence for the exact
  unit (shared-utils/signature_launch/admission.py): a nonempty file, an exit
  code or a declared status never completes a unit,
- percentages count DELIVERED work (verified done) against the approved plan's
  units; a client-dropped, skipped, stale or superseded unit stays in the
  denominator and contributes zero,
- a unit being executed right now is reported as running, never as ready: a
  concurrent resume never claims it as fresh work,
- starting a unit requires execution ownership (a claim with a lease), so two
  resumes cannot both produce side effects for the same unit,
- a completion/release names the attempt it owns, so a late worker cannot
  complete or release a newer attempt,
- a stall keeps its partial results and every causal blocker instead of being
  discarded.

The unit expansion is not re-implemented here: ``scheduler/model.py`` is the one
authority for the unit list and the result envelope (failed / blocked / awaiting
facts / dropped / verified success).  A failure returned normally never
satisfies a dependency, and a normal return value never becomes success.

Pure stdlib, no network, no credentials. The file is written atomically so a
crash mid-save leaves the previous progress intact.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"
STATES = ("pending", "running", "done", "failed", "blocked", "dropped")
TERMINAL = ("done", "dropped")
DEFAULT_LEASE_SECONDS = 900

_HERE = Path(__file__).resolve().parent
_MODEL = None
_ADMISSION = None


class ProgressError(ValueError):
    """A progress file or launch plan that cannot be trusted. Fail closed."""


def _model():
    """Load the authoritative expansion/envelope module (scheduler/model.py)."""
    global _MODEL
    if _MODEL is None:
        path = _HERE / "scheduler" / "model.py"
        spec = importlib.util.spec_from_file_location(
            "signature_launch_scheduler_model", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODEL = module
    return _MODEL


def _admission():
    """Load the one admission/completion service (admission.py)."""
    global _ADMISSION
    if _ADMISSION is None:
        spec = importlib.util.spec_from_file_location(
            "signature_launch_admission", _HERE / "admission.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _ADMISSION = module
    return _ADMISSION


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def plan_hash(plan):
    """The one plan hash (admission.py owns the canonical definition)."""
    return _admission().plan_hash(plan)


def units_from_plan(plan):
    """Ordered [{id, kind, waits_for, ...}] from the authoritative expansion."""
    try:
        expanded = _model().expand_plan(plan)
    except _model().ExpansionError as error:
        raise ProgressError(str(error))
    units = [{
        "id": unit["id"],
        "kind": unit["kind"],
        "lane": unit["lane"],
        "waits_for": list(unit["waits_for"]),
        "family": unit.get("family"),
    } for unit in expanded["units"]]
    return expanded["launch_id"], units


def new_progress(plan, clock=_now):
    """A fresh progress record for an approved plan, every unit pending."""
    launch_id, units = units_from_plan(plan)
    stamp = clock()
    return {
        "schema_version": SCHEMA_VERSION,
        "launch_id": launch_id,
        "plan_hash": plan_hash(plan),
        # The required unit set is persisted at init so the delivered
        # denominator can never shrink by editing the ``units`` dict.
        "required_units": [u["id"] for u in units],
        "created_at": stamp,
        "updated_at": stamp,
        "units": {
            u["id"]: {
                "kind": u["kind"],
                "waits_for": u["waits_for"],
                "state": "pending",
                "attempts": 0,
                "charged": False,
                "artifact": None,
                "note": None,
                "reason": None,
                "missing_facts": [],
                "owner": None,
                "lease_expires_at": None,
                "result": None,
                "verified": False,
                "stale": False,
                "superseded": False,
                "skipped": False,
                "review_required": False,
                "review": None,
                "evidence_digest": None,
                "content_checked": False,
                "revision": 1,
                "updated_at": stamp,
            }
            for u in units
        },
    }


def default_path(run_dir, launch_id):
    return Path(run_dir) / ("progress-%s.json" % launch_id)


def _fill(unit):
    """Backfill additive fields so an older progress file stays readable.

    A legacy ``done`` row is backfilled ``verified: False``: an unsupported
    completion claim is preserved and reported as unverified, never promoted.
    """
    unit.setdefault("waits_for", [])
    unit.setdefault("attempts", 0)
    unit.setdefault("charged", False)
    unit.setdefault("artifact", None)
    unit.setdefault("note", None)
    unit.setdefault("reason", None)
    unit.setdefault("missing_facts", [])
    unit.setdefault("owner", None)
    unit.setdefault("lease_expires_at", None)
    unit.setdefault("result", None)
    unit.setdefault("verified", False)
    unit.setdefault("stale", False)
    unit.setdefault("superseded", False)
    unit.setdefault("skipped", False)
    unit.setdefault("review_required", False)
    unit.setdefault("review", None)
    unit.setdefault("evidence_digest", None)
    unit.setdefault("content_checked", False)
    unit.setdefault("revision", 1)
    return unit


def validate(record):
    """Structural checks on a loaded record. Fail closed."""
    if not isinstance(record, dict):
        raise ProgressError("progress must be a JSON object")
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ProgressError("unsupported progress schema_version: %r"
                            % record.get("schema_version"))
    if not str(record.get("launch_id") or ""):
        raise ProgressError("progress has no launch_id")
    units = record.get("units")
    if not isinstance(units, dict):
        raise ProgressError("progress has no units object")
    for uid, unit in units.items():
        if not isinstance(unit, dict):
            raise ProgressError("unit %s is not an object" % uid)
        _fill(unit)
        if unit.get("state") not in STATES:
            raise ProgressError("unit %s has unknown state %r" % (uid, unit.get("state")))
        if not isinstance(unit.get("waits_for", []), list):
            raise ProgressError("unit %s waits_for must be a list" % uid)
        unknown = [w for w in unit.get("waits_for") or [] if w not in units]
        if unknown:
            raise ProgressError("unit %s waits_for unknown unit(s): %s"
                                % (uid, ", ".join(map(str, unknown))))
        if not isinstance(unit.get("missing_facts"), list):
            raise ProgressError("unit %s missing_facts must be a list" % uid)
        if unit.get("reason") is not None and not isinstance(unit.get("reason"), dict):
            raise ProgressError("unit %s reason must be an object or null" % uid)
        if unit.get("lease_expires_at") is not None and _parse_time(
                unit.get("lease_expires_at")) is None:
            raise ProgressError("unit %s lease_expires_at is not a timestamp" % uid)
    return record


def load(path):
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProgressError("cannot read progress file %s: %s" % (path, exc))
    return validate(record)


def save(record, path, clock=_now):
    """Atomic write, so an interrupted save never corrupts progress."""
    validate(record)
    record["updated_at"] = clock()
    record["percent"] = percent(record)
    record["counts"] = counts(record)
    record["empty"] = not record["units"]
    record["stall"] = stall_report(record)["units"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".progress-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return record


def counts(record):
    out = {state: 0 for state in STATES}
    for unit in record["units"].values():
        out[unit["state"]] += 1
    view = _admission().delivered(record)
    out["total"] = len(record["units"])
    out["terminal"] = out["done"] + out["dropped"]
    out["retryable"] = out["failed"]
    out["awaiting_facts"] = sum(
        1 for unit in record["units"].values() if unit.get("missing_facts"))
    out["ready"] = len(ready(record))
    out["empty"] = 1 if not record["units"] else 0
    # Delivered work and every excluded category (one denominator, one rule).
    out["delivered"] = view["delivered"]
    out["unverified_done"] = len(view["excluded"]["unverified_done"])
    out["stale"] = len(view["excluded"]["stale"])
    out["superseded"] = len(view["excluded"]["superseded"])
    out["skipped"] = len(view["excluded"]["skipped"])
    return out


def percent(record):
    """Percentage of the approved plan's units that are DELIVERED.

    Delivered means verified done.  A dropped/skipped/stale/superseded unit
    stays in the denominator and contributes zero, and a legacy ``done`` claim
    with no verified evidence counts as unverified, not as delivered.
    """
    return _admission().delivered(record)["percent"]


def _parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _lease_is_fresh(unit, now):
    expires = _parse_time(unit.get("lease_expires_at"))
    if expires is None:
        return False
    return expires > now


def _resolved(record):
    """Unit ids that unlock dependents: verified done, or client dropped.

    A ``done`` row whose ``verified`` is not True is NOT resolved (D3).  It
    used to unlock dependents and let ``claim`` start them, while
    ``model.satisfies_dependency`` and ``admission.admit_entry`` both refused
    the same row.
    """
    return {uid for uid, unit in record["units"].items()
            if unit["state"] == "dropped"
            or (unit["state"] == "done" and unit.get("verified") is True)}


def _dependencies_met(unit, resolved):
    return all(dependency in resolved for dependency in unit.get("waits_for") or [])


def _startable(record, uid, unit, resolved, now):
    """Why a unit may not start, or None when it may. Running is not startable."""
    if unit["state"] in TERMINAL:
        return "terminal"
    if unit["state"] == "running":
        return "running"
    if unit.get("missing_facts"):
        return "awaiting_facts"
    if unit["state"] == "blocked":
        return "blocked"
    if not _dependencies_met(unit, resolved):
        return "dependency"
    if unit["state"] not in ("pending", "failed"):
        return unit["state"]
    return None


def ready(record, now=None):
    """Units a resumed run should start now, in plan order.

    Excludes: terminal units, units with a fresh execution lease (running),
    units awaiting facts, blocked units (an operator must clear the cause),
    and units whose dependencies are not terminal.  A failed unit IS ready:
    retry is deliberate, once, and reported under ``retry``.
    """
    now = now or _parse_time(_now())
    resolved = _resolved(record)
    return [uid for uid, unit in record["units"].items()
            if _startable(record, uid, unit, resolved, now) is None]


def ready_to_start(record, now=None):
    """Separate ready-to-start from running, retry, awaiting and blocked."""
    now = now or _parse_time(_now())
    resolved = _resolved(record)
    view = {"fresh": [], "retry": [], "running": [], "stale_running": [],
            "awaiting_facts": [], "blocked": [], "terminal": []}
    for uid, unit in record["units"].items():
        reason = _startable(record, uid, unit, resolved, now)
        if reason is None:
            view["retry" if unit["state"] == "failed" else "fresh"].append(uid)
        elif reason == "running":
            (view["running"] if _lease_is_fresh(unit, now)
             else view["stale_running"]).append(uid)
        elif reason == "awaiting_facts":
            view["awaiting_facts"].append(uid)
        elif reason == "terminal":
            view["terminal"].append(uid)
        elif reason == "dependency":
            view["blocked"].append(uid)
        else:
            view["blocked"].append(uid)
    view["ready"] = view["fresh"] + view["retry"]
    return view


def artifact_exists(record, uid, exists=None):
    """Whether the unit's recorded artifact path is present and non-empty.

    This is a filesystem FACT, never completion evidence.  ``recover`` uses it
    only to say "an artifact exists but nothing proves it"; it can no longer
    complete a unit.
    """
    path = record["units"][uid].get("artifact")
    if not path:
        return False
    check = exists or (lambda p: Path(p).is_file() and Path(p).stat().st_size > 0)
    try:
        return bool(check(path))
    except (OSError, ValueError):
        return False


def recover_report(record, exists=None, verify=None, evidence=None, now=None):
    """Reconcile CURRENT admission evidence for the exact unit.

    ``evidence`` is a mapping ``{unit_id: evidence}`` or a callable
    ``(unit_id) -> evidence`` built with ``admission.evidence``.  Only a
    verified evidence object with the current output hashes, the current input
    hashes and (where required) a successful independent review completes a
    unit.

    A nonempty file no longer completes anything.  A legacy ``verify(path, uid)
    -> (bool, detail)`` callback is still run for its detail, but a True return
    alone is not completion: bytes on disk do not prove the unit's inputs,
    attempt or review.  A unit held by a fresh execution lease is skipped,
    never stolen.
    """
    now = now or _parse_time(_now())
    admission = _admission()
    result = {"recovered": [], "skipped": [], "rejected": []}
    for uid, unit in record["units"].items():
        if unit["state"] in TERMINAL:
            continue
        if unit["state"] == "running" and _lease_is_fresh(unit, now):
            result["skipped"].append({"unit": uid, "reason": "live execution lease"})
            continue
        candidate = evidence(uid) if callable(evidence) else (evidence or {}).get(uid)
        legacy_detail = None
        if candidate is None and verify is not None and unit.get("artifact"):
            try:
                ok, legacy_detail = verify(unit["artifact"], uid)
            except (OSError, ValueError) as error:
                ok, legacy_detail = False, str(error)
            if not ok:
                _reject(unit, uid, "artifact_unverified", legacy_detail)
                result["rejected"].append({"unit": uid, "detail": legacy_detail})
                continue
        if candidate is None:
            if artifact_exists(record, uid, exists) or unit.get("artifact"):
                detail = ("bytes exist but no current admission evidence completes "
                          "this unit" if legacy_detail is None else
                          "bytes verify but a byte check alone is not admission "
                          "evidence (%s)" % legacy_detail)
                _reject(unit, uid, "no_evidence", detail)
                result["rejected"].append({"unit": uid, "detail": detail})
            continue
        if not isinstance(candidate, dict) or candidate.get("unit") != uid:
            detail = "evidence does not name unit %s" % uid
            _reject(unit, uid, "evidence_refused", detail)
            result["rejected"].append({"unit": uid, "detail": detail})
            continue
        checked = admission.verify_evidence(candidate, unit=uid,
                                            plan_hash=record.get("plan_hash"))
        if not checked["ok"]:
            detail = "; ".join(checked["reasons"]) or "evidence refused"
            _reject(unit, uid, "evidence_refused", detail)
            result["rejected"].append({"unit": uid, "detail": detail})
            continue
        unit["state"] = "done"
        unit["verified"] = True
        unit["stale"] = False
        unit["superseded"] = False
        unit["content_checked"] = bool(checked["content_checked"])
        unit["evidence_digest"] = checked["artifact_set_hash"]
        unit["review"] = ({"ok": True} if checked["reviewed"]
                          else (candidate.get("review") or None))
        unit["artifact"] = None
        for entry in checked["artifacts"]:
            if entry.get("path"):
                unit["artifact"] = entry["path"]
                break
        unit["note"] = "recovered from admission evidence"
        unit["reason"] = None
        unit["owner"] = None
        unit["lease_expires_at"] = None
        unit["updated_at"] = _now()
        result["recovered"].append(uid)
    return result


def _reject(unit, uid, kind, detail):
    unit["reason"] = {"kind": kind, "unit": uid, "detail": detail}
    unit["updated_at"] = _now()


def recover(record, exists=None, verify=None, evidence=None, now=None):
    """Backwards-compatible view: the recovered unit ids."""
    return recover_report(record, exists, verify, evidence, now)["recovered"]


def claim(record, uid, owner, ttl_seconds=DEFAULT_LEASE_SECONDS, now=None, clock=_now):
    """Take execution ownership of one unit. Returns the claim decision.

    Refuses a terminal unit, a unit already running under a fresh lease, a unit
    awaiting facts, and a unit whose dependencies are not terminal.  An expired
    lease may be reclaimed and the previous owner is recorded.  A legacy
    ``running`` unit with no lease is NOT claimed: it must be released or
    recovered explicitly, so a concurrent resume can never steal it.
    """
    owner = str(owner or "").strip()
    if not owner:
        raise ProgressError("claim requires a non-empty owner")
    now = now or _parse_time(_now())
    unit = record["units"].get(uid)
    if unit is None:
        raise ProgressError("unknown unit: %s" % uid)
    if unit["state"] in TERMINAL:
        return {"claimed": False, "reason": "terminal", "unit": uid}
    if unit["state"] == "running":
        if unit.get("owner") == owner and _lease_is_fresh(unit, now):
            return {"claimed": True, "renewed": True, "unit": uid, "owner": owner}
        if not _lease_is_fresh(unit, now):
            if unit.get("owner") is None:
                return {"claimed": False, "reason": "running without a lease; "
                        "release or recover it explicitly", "unit": uid}
            previous = unit.get("owner")
            _start_unit(unit, owner, ttl_seconds, now, clock)
            return {"claimed": True, "reclaimed": True, "unit": uid,
                    "owner": owner, "previous_owner": previous,
                    "attempt": int(unit["attempts"])}
        return {"claimed": False, "reason": "held by %s" % unit.get("owner"),
                "unit": uid}
    if unit.get("missing_facts"):
        return {"claimed": False, "reason": "awaiting facts: %s"
                % ", ".join(unit["missing_facts"]), "unit": uid}
    resolved = _resolved(record)
    missing = [dependency for dependency in unit.get("waits_for") or []
               if dependency not in resolved]
    if missing:
        return {"claimed": False, "reason": "dependencies unresolved: %s"
                % ", ".join(missing), "unit": uid}
    if unit["state"] == "blocked":
        return {"claimed": False, "reason": "blocked: %s"
                % ((unit.get("reason") or {}).get("detail") or "cause not cleared"),
                "unit": uid}
    _start_unit(unit, owner, ttl_seconds, now, clock)
    return {"claimed": True, "unit": uid, "owner": owner,
            "attempt": int(unit["attempts"])}


def _start_unit(unit, owner, ttl_seconds, now, clock):
    unit["state"] = "running"
    unit["owner"] = owner
    unit["lease_expires_at"] = (now + timedelta(seconds=max(1, int(ttl_seconds)))).isoformat() \
        .replace("+00:00", "Z")
    unit["attempts"] = int(unit.get("attempts") or 0) + 1
    unit["updated_at"] = clock()


def heartbeat(record, uid, owner, ttl_seconds=DEFAULT_LEASE_SECONDS, now=None,
              clock=_now, attempt=None):
    """Extend a live execution lease. Refuses a different owner or attempt."""
    now = now or _parse_time(_now())
    unit = record["units"].get(uid)
    if unit is None:
        raise ProgressError("unknown unit: %s" % uid)
    if unit["state"] != "running" or unit.get("owner") != owner:
        return {"renewed": False, "reason": "not the execution owner", "unit": uid}
    if attempt is not None and int(attempt) != int(unit.get("attempts") or 0):
        return {"renewed": False, "unit": uid,
                "reason": "attempt %s is not current (%s)"
                          % (attempt, unit.get("attempts"))}
    unit["lease_expires_at"] = (now + timedelta(seconds=max(1, int(ttl_seconds)))).isoformat() \
        .replace("+00:00", "Z")
    unit["updated_at"] = clock()
    return {"renewed": True, "unit": uid, "lease_expires_at": unit["lease_expires_at"]}


def release(record, uid, owner, note=None, clock=_now, attempt=None):
    """Give up execution ownership; partial results stay on the unit.

    A late worker (an older attempt) cannot release a newer worker's unit.
    """
    unit = record["units"].get(uid)
    if unit is None:
        raise ProgressError("unknown unit: %s" % uid)
    if unit["state"] != "running" or unit.get("owner") != owner:
        return {"released": False, "reason": "not the execution owner", "unit": uid}
    if attempt is not None and int(attempt) != int(unit.get("attempts") or 0):
        return {"released": False, "unit": uid,
                "reason": "attempt %s is not current (%s)"
                          % (attempt, unit.get("attempts"))}
    unit["state"] = "pending"
    unit["owner"] = None
    unit["lease_expires_at"] = None
    if note is not None:
        unit["note"] = str(note)
    unit["updated_at"] = clock()
    return {"released": True, "unit": uid}


def complete(record, uid, result, owner=None, artifact=None, clock=_now, attempt=None):
    """Record one runner result envelope under execution ownership.

    ``result`` is ALWAYS re-normalised through ``scheduler/model.py``, so a
    declared ``{"status": "verified_success"}`` and every ordinary return value
    (``None``, a truthy object, a completed subprocess) are recorded as failed
    unless they carry admission evidence.  Success and drop are side-effect
    outcomes: they require the same owner and attempt that claimed the unit,
    so a late worker cannot complete a newer attempt.  A terminal unit is never
    charged again.
    """
    model = _model()
    admission = _admission()
    unit = record["units"].get(uid)
    if unit is None:
        raise ProgressError("unknown unit: %s" % uid)
    if unit["state"] in TERMINAL:
        return False
    if unit["state"] != "running":
        raise ProgressError("unit %s is not running; claim it before completing" % uid)
    if not owner or unit.get("owner") != owner:
        raise ProgressError("unit %s is owned by %r, not %r"
                            % (uid, unit.get("owner"), owner))
    if attempt is not None and int(attempt) != int(unit.get("attempts") or 0):
        raise ProgressError("unit %s attempt %s is not current (%s); a late worker "
                            "cannot complete a newer attempt"
                            % (uid, attempt, unit.get("attempts")))
    envelope = model.normalize_result(result)
    status = model.canonical_status(envelope.get("status"))
    if status is None:
        envelope = model.envelope(model.FAILED, detail="unknown result status")
        status = model.FAILED
    # The evidence must belong to THIS unit under THIS plan's hash (D1/D2).
    # normalize_result validated it structurally; this binds it to the record.
    if status == model.VERIFIED_SUCCESS:
        recheck = admission.verify_evidence(envelope.get("evidence"), unit=uid,
                                            plan_hash=record.get("plan_hash"))
        if not recheck["ok"]:
            envelope = model.envelope(model.FAILED, detail=(
                "completion evidence does not belong to unit %s under the "
                "current plan: %s" % (uid, "; ".join(recheck["reasons"]) or "refused")))
            status = model.FAILED
    unit["state"] = model.PERSISTED_STATE[status]
    unit["owner"] = None
    unit["lease_expires_at"] = None
    unit["result"] = envelope
    unit["missing_facts"] = list(envelope.get("missing_facts") or [])
    unit["reason"] = {
        "kind": status,
        "detail": envelope.get("detail"),
        "blocker": envelope.get("blocker"),
    }
    checked = envelope.get("evidence_checked") or {}
    unit["verified"] = status == model.VERIFIED_SUCCESS and envelope.get("verified") is True
    unit["content_checked"] = bool(checked.get("content_checked"))
    unit["evidence_digest"] = checked.get("artifact_set_hash")
    if status == model.VERIFIED_SUCCESS:
        unit["stale"] = False
        unit["superseded"] = False
        unit["review"] = ((envelope.get("evidence") or {}).get("review")
                          if isinstance(envelope.get("evidence"), dict) else None)
    else:
        unit["verified"] = False
    if artifact is not None:
        unit["artifact"] = str(artifact)
    elif envelope.get("artifacts"):
        unit["artifact"] = str(envelope["artifacts"][0])
    if envelope.get("detail"):
        unit["note"] = str(envelope["detail"])
    unit["updated_at"] = clock()
    return True


def mark(record, uid, state, artifact=None, charged=None, note=None, clock=_now,
         owner=None, evidence=None, attempt=None):
    """Move one unit's state. A terminal unit is never re-marked.

    ``running`` is refused here: execution ownership comes from ``claim``.
    ``done`` requires the owner and attempt that hold the claim AND a verified
    admission evidence object; a declared state is not evidence, so
    ``mark(..., "done")`` without evidence fails closed.  A failed/blocked unit
    stays retryable exactly as the envelope defines it.
    """
    if state not in STATES:
        raise ProgressError("unknown state: %s" % state)
    unit = record["units"].get(uid)
    if unit is None:
        raise ProgressError("unknown unit: %s" % uid)
    if unit["state"] in TERMINAL:
        return False
    if state == "running":
        raise ProgressError("state running requires claim(owner, ttl)")
    if unit["state"] == "running" and unit.get("owner") != owner:
        raise ProgressError("unit %s is owned by %r; wrong owner %r"
                            % (uid, unit.get("owner"), owner))
    if attempt is not None and unit["state"] == "running" \
            and int(attempt) != int(unit.get("attempts") or 0):
        raise ProgressError("unit %s attempt %s is not current (%s)"
                            % (uid, attempt, unit.get("attempts")))
    checked = None
    if state == "done":
        if unit["state"] != "running":
            raise ProgressError("state done requires a claim and completion evidence")
        checked = _admission().verify_evidence(evidence, unit=uid,
                                               plan_hash=record.get("plan_hash"))
        if not checked["ok"]:
            raise ProgressError("state done requires verified admission evidence: %s"
                                % ("; ".join(checked["reasons"]) or "none supplied"))
    if state != "running":
        unit["owner"] = None
        unit["lease_expires_at"] = None
    unit["state"] = state
    unit["verified"] = state == "done" and checked is not None and checked["ok"]
    if unit["verified"]:
        unit["stale"] = False
        unit["superseded"] = False
        unit["content_checked"] = bool(checked["content_checked"])
        unit["evidence_digest"] = checked["artifact_set_hash"]
    if artifact is not None:
        unit["artifact"] = str(artifact)
    if charged is not None:
        unit["charged"] = bool(charged)
    if note is not None:
        unit["note"] = str(note)
    unit["updated_at"] = clock()
    return True


def stall_report(record):
    """Every non-terminal unit with its causal blockers, derived and persisted."""
    model = _model()
    by_id = {uid: {"id": uid, "waits_for": unit.get("waits_for") or []}
             for uid, unit in record["units"].items()}
    resolved = _resolved(record)
    detail = {}
    for uid, unit in record["units"].items():
        if unit["state"] in TERMINAL:
            continue
        blockers = []
        if unit["state"] == "running":
            blockers.append({"unit": uid, "state": "running", "kind": "executing",
                             "detail": unit.get("owner")})
        if unit.get("missing_facts"):
            blockers.append({"unit": uid, "state": unit["state"], "kind": "awaiting_fact",
                             "detail": ", ".join(unit["missing_facts"])})
        reason = unit.get("reason") or {}
        if reason.get("kind") in ("failed", "blocked", "awaiting_facts", "empty_artifact"):
            blockers.append({"unit": uid, "state": unit["state"], "kind": reason.get("kind"),
                             "detail": reason.get("detail")})
        if unit["state"] != "running":
            blockers.extend(model.causal_blockers(uid, by_id, resolved))
        if blockers:
            detail[uid] = blockers
    return {"units": detail, "blocked": sorted(detail)}


def summary(record):
    view = ready_to_start(record)
    return {
        "launch_id": record["launch_id"],
        "empty": not record["units"],
        "percent": percent(record),
        "counts": counts(record),
        "delivered": _admission().delivered(record),
        "ready": view["ready"],
        "fresh": view["fresh"],
        "retry": view["retry"],
        "running": view["running"],
        "awaiting_facts": view["awaiting_facts"],
        "blocked": view["blocked"],
        "stall": stall_report(record)["units"],
    }


def _init(args):
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    record = new_progress(plan)
    path = Path(args.file) if args.file else default_path(args.run_dir, record["launch_id"])
    if path.exists() and not args.force:
        # Resume rather than reset: a second init never zeroes real progress.
        existing = load(path)
        if existing.get("plan_hash") != record["plan_hash"]:
            raise ProgressError("progress exists for a different plan: %s" % path)
        return summary(existing)
    save(record, path)
    return summary(record)


@contextlib.contextmanager
def _locked(path):
    """Cross-process lock so claim/complete/recover are atomic on one file."""
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+")
    try:
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass  # single-host fallback: still atomic replace, no cross-process lock
        yield
    finally:
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        handle.close()


def claim_atomic(path, uid, owner, ttl_seconds=DEFAULT_LEASE_SECONDS):
    with _locked(path):
        record = load(path)
        decision = claim(record, uid, owner, ttl_seconds)
        if decision.get("claimed"):
            save(record, path)
        return decision


def complete_atomic(path, uid, result, owner, artifact=None, attempt=None):
    with _locked(path):
        record = load(path)
        changed = complete(record, uid, result, owner=owner, artifact=artifact,
                           attempt=attempt)
        if changed:
            save(record, path)
        return changed


def recover_atomic(path, exists=None, verify=None, evidence=None):
    with _locked(path):
        record = load(path)
        report = recover_report(record, exists=exists, verify=verify,
                                evidence=evidence)
        if report["recovered"] or report["rejected"]:
            save(record, path)
        return report


def admit_atomic(path, uid, owner, ttl_seconds=DEFAULT_LEASE_SECONDS,
                 clock=_now, revalidate_stale=True):
    """Governed entry admission, atomic under the existing file lock."""
    admission = _admission()
    with _locked(path):
        record = load(path)
        decision = admission.admit_entry(record, uid, owner,
                                         ttl_seconds=ttl_seconds, clock=clock,
                                         revalidate_stale=revalidate_stale)
        if decision.get("admitted"):
            save(record, path)
        return decision


def invalidate_atomic(path, units, kind, detail=None):
    """Targeted invalidation with downstream cascade, atomic under the lock."""
    with _locked(path):
        record = load(path)
        report = _admission().invalidate(record, units, kind=kind, detail=detail)
        if report["invalidated"]:
            save(record, path)
        return report


def _read_evidence(path):
    """Optional evidence JSON for the CLI (never invented when absent)."""
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("init", help="create (or keep) the progress file for a plan")
    p.add_argument("--plan", required=True)
    p.add_argument("--file")
    p.add_argument("--run-dir", default=".")
    p.add_argument("--force", action="store_true", help="rewrite an existing file")

    p = sub.add_parser("status", help="percentage, counts and ready/running view")
    p.add_argument("--file", required=True)

    p = sub.add_parser("next", help="units to start or retry on resume")
    p.add_argument("--file", required=True)

    p = sub.add_parser("ready", help="fresh/retry/running/awaiting/blocked sets")
    p.add_argument("--file", required=True)

    p = sub.add_parser("stall", help="causal blockers per unfinished unit")
    p.add_argument("--file", required=True)

    p = sub.add_parser("claim", help="take execution ownership of one unit")
    p.add_argument("--file", required=True)
    p.add_argument("--unit", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--ttl", type=int, default=DEFAULT_LEASE_SECONDS)

    p = sub.add_parser("heartbeat", help="extend an execution lease")
    p.add_argument("--file", required=True)
    p.add_argument("--unit", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--ttl", type=int, default=DEFAULT_LEASE_SECONDS)

    p = sub.add_parser("release", help="give up execution ownership")
    p.add_argument("--file", required=True)
    p.add_argument("--unit", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--note")

    p = sub.add_parser("complete", help="record one result envelope under ownership")
    p.add_argument("--file", required=True)
    p.add_argument("--unit", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--detail")
    p.add_argument("--artifact")
    p.add_argument("--missing-fact", action="append", default=[])
    p.add_argument("--evidence", help="admission evidence JSON file "
                                      "(required by verified_success)")

    p = sub.add_parser("mark", help="set one unit's state")
    p.add_argument("--file", required=True)
    p.add_argument("--unit", required=True)
    p.add_argument("--state", required=True, choices=STATES)
    p.add_argument("--artifact")
    p.add_argument("--charged", action="store_true")
    p.add_argument("--note")
    p.add_argument("--owner")
    p.add_argument("--evidence", help="admission evidence JSON file (required by done)")

    p = sub.add_parser("recover", help="reconcile current admission evidence")
    p.add_argument("--file", required=True)
    p.add_argument("--evidence", help="{unit: evidence} JSON file")

    p = sub.add_parser("admit", help="governed entry admission for one unit")
    p.add_argument("--file", required=True)
    p.add_argument("--unit", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--ttl", type=int, default=DEFAULT_LEASE_SECONDS)

    p = sub.add_parser("invalidate", help="invalidate a unit and its downstream work")
    p.add_argument("--file", required=True)
    p.add_argument("--unit", action="append", required=True)
    p.add_argument("--kind", required=True)
    p.add_argument("--detail")

    p = sub.add_parser("done-standard", help="derived done export (not an authority)")
    p.add_argument("--file", required=True)

    args = ap.parse_args(argv)
    if args.self_test:
        self_test()
        print("progress self-test: PASS")
        return 0
    if not args.cmd:
        ap.print_help()
        return 2
    try:
        if args.cmd == "init":
            print(json.dumps(_init(args), indent=2, sort_keys=True))
            return 0
        if args.cmd == "claim":
            print(json.dumps(claim_atomic(args.file, args.unit, args.owner, args.ttl),
                             indent=2, sort_keys=True))
            return 0
        if args.cmd == "complete":
            model = _model()
            envelope = model.envelope(args.status, detail=args.detail,
                                      missing_facts=args.missing_fact,
                                      evidence=_read_evidence(args.evidence))
            changed = complete_atomic(args.file, args.unit, envelope, args.owner,
                                      artifact=args.artifact)
            print(json.dumps({"changed": changed, **summary(load(args.file))},
                             indent=2, sort_keys=True))
            return 0
        if args.cmd == "recover":
            report = recover_atomic(args.file, evidence=_read_evidence(args.evidence))
            print(json.dumps({**report, **summary(load(args.file))},
                             indent=2, sort_keys=True))
            return 0
        if args.cmd == "admit":
            print(json.dumps(admit_atomic(args.file, args.unit, args.owner, args.ttl),
                             indent=2, sort_keys=True))
            return 0
        if args.cmd == "invalidate":
            print(json.dumps(invalidate_atomic(args.file, args.unit, args.kind,
                                               args.detail),
                             indent=2, sort_keys=True))
            return 0
        if args.cmd == "done-standard":
            print(json.dumps(_admission().done_standard(load(args.file)),
                             indent=2, sort_keys=True))
            return 0
        record = load(args.file)
        if args.cmd == "status":
            print(json.dumps(summary(record), indent=2, sort_keys=True))
            return 0
        if args.cmd == "next":
            print(json.dumps({"ready": ready(record)}, indent=2))
            return 0
        if args.cmd == "ready":
            print(json.dumps(ready_to_start(record), indent=2))
            return 0
        if args.cmd == "stall":
            print(json.dumps(stall_report(record), indent=2, sort_keys=True))
            return 0
        if args.cmd == "heartbeat":
            print(json.dumps(heartbeat(record, args.unit, args.owner, args.ttl),
                             indent=2, sort_keys=True))
            save(record, args.file)
            return 0
        if args.cmd == "release":
            decision = release(record, args.unit, args.owner, args.note)
            save(record, args.file)
            print(json.dumps(decision, indent=2, sort_keys=True))
            return 0
        if args.cmd == "mark":
            mark(record, args.unit, args.state, artifact=args.artifact,
                 charged=True if args.charged else None, note=args.note,
                 owner=args.owner, evidence=_read_evidence(args.evidence))
            save(record, args.file)
            print(json.dumps(summary(record), indent=2, sort_keys=True))
            return 0
    except (OSError, ValueError, ProgressError) as exc:
        print("progress: %s" % exc, file=sys.stderr)
        return 2
    return 2


def self_test():
    plan = {
        "launch_id": "selftest-launch",
        "pages": [
            {"id": "landing", "waits_for": []},
            {"id": "sales", "waits_for": ["landing"]},
        ],
        "email_sequences": [{"id": "pre_launch", "waits_for": []}],
        "text_sets": [{"id": "doors_open", "waits_for": ["landing"]}],
        "automations": [{"id": "opt_in", "waits_for": ["pre_launch"]}],
    }
    model = _model()
    admission = _admission()
    ph = plan_hash(plan)

    def ev(uid, target="artifact-%s.html" % "x"):
        return admission.evidence(uid, ph, [admission.artifact(target,
                                                               sha256="b" * 64)],
                                  inputs={"plan": ph})

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "progress.json"
        record = new_progress(plan)
        save(record, path)
        assert percent(record) == 0.0
        assert ready(record) == ["landing", "pre_launch"]

        # Execution ownership is required before any side effect.
        assert claim(record, "landing", "owner-a")["claimed"] is True
        assert record["units"]["landing"]["state"] == "running"
        assert "landing" not in ready(record)
        assert "landing" in ready_to_start(record)["running"]
        assert claim(record, "landing", "owner-b")["claimed"] is False

        # A failure returned normally persists as failed and satisfies nothing.
        assert complete(record, "landing", {"status": "failed", "detail": "boom"},
                        owner="owner-a") is True
        assert record["units"]["landing"]["state"] == "failed"
        assert model.satisfies_dependency({"status": "failed"}) is False
        assert "sales" not in ready(record)          # dependency not satisfied
        assert "landing" in ready(record)            # retry is allowed, deliberately
        assert "landing" in ready_to_start(record)["retry"]

        # A normal return (None) is not verified success.
        assert claim(record, "landing", "owner-a")["claimed"] is True
        assert complete(record, "landing", None, owner="owner-a") is True
        unit = record["units"]["landing"]
        assert unit["state"] == "failed" and unit["verified"] is False, unit
        assert "no admission evidence" in (unit["reason"]["detail"] or "")

        # A declared status is not evidence either.
        assert claim(record, "landing", "owner-a")["claimed"] is True
        assert complete(record, "landing",
                        {"status": "verified_success", "verified": True},
                        owner="owner-a") is True
        unit = record["units"]["landing"]
        assert unit["state"] == "failed" and unit["verified"] is False, unit

        # Real evidence completes and unlocks dependents.
        assert claim(record, "landing", "owner-a")["claimed"] is True
        assert complete(record, "landing",
                        model.envelope(model.VERIFIED_SUCCESS,
                                       evidence=ev("landing")),
                        owner="owner-a") is True
        unit = record["units"]["landing"]
        assert unit["state"] == "done" and unit["verified"] is True
        assert unit["evidence_digest"].startswith("sha256:")
        assert ready(record) == ["sales", "pre_launch", "doors_open"]

        # Re-marking a finished unit changes nothing and re-charges nothing.
        before = (record["units"]["landing"]["state"],
                  record["units"]["landing"]["attempts"])
        assert mark(record, "landing", "done", charged=True) is False
        assert (record["units"]["landing"]["state"],
                record["units"]["landing"]["attempts"]) == before

        # A late worker (older attempt) cannot complete a newer worker's unit.
        assert claim(record, "sales", "owner-c")["claimed"] is True
        assert release(record, "sales", "owner-c")["released"] is True
        assert claim(record, "sales", "owner-c")["attempt"] == 2
        try:
            complete(record, "sales", model.envelope(model.VERIFIED_SUCCESS,
                                                     evidence=ev("sales")),
                     owner="owner-c", attempt=1)
            raise AssertionError("a late attempt completed a newer unit")
        except ProgressError:
            pass
        assert complete(record, "sales",
                        model.envelope(model.VERIFIED_SUCCESS, evidence=ev("sales")),
                        owner="owner-c", attempt=2) is True
        assert record["units"]["sales"]["verified"] is True

        assert claim(record, "doors_open", "owner-d")["claimed"] is True
        assert complete(record, "doors_open",
                        model.envelope(model.VERIFIED_SUCCESS, evidence=ev("doors_open")),
                        owner="owner-d") is True
        mark(record, "pre_launch", "dropped", note="client dropped")

        # Delivered = verified done. A dropped unit stays in the denominator
        # and contributes zero (the old rule counted it and reported 80.0).
        c = counts(record)
        assert c["done"] == 3 and c["dropped"] == 1 and c["delivered"] == 3
        assert c["unverified_done"] == 0 and c["terminal"] == 4
        assert percent(record) == 60.0, percent(record)

        # --- recovery: a nonempty file alone never completes a unit ---------
        rec2 = new_progress(plan)
        assert claim(rec2, "landing", "owner-e")["claimed"] is True
        assert release(rec2, "landing", "owner-e")["released"] is True
        artifact = Path(tmp) / "landing.html"
        artifact.write_text("built", encoding="utf-8")
        rec2["units"]["landing"]["artifact"] = str(artifact)
        report = recover_report(rec2)
        assert report["recovered"] == [], report
        assert report["rejected"][0]["unit"] == "landing"
        assert rec2["units"]["landing"]["state"] == "pending"
        assert rec2["units"]["landing"]["reason"]["kind"] == "no_evidence"

        # The same bytes DO recover when current admission evidence names them.
        report = recover_report(rec2, evidence={"landing": ev("landing")})
        assert report["recovered"] == ["landing"], report
        assert rec2["units"]["landing"]["state"] == "done"
        assert rec2["units"]["landing"]["verified"] is True

        save(record, path)
        assert load(path)["percent"] == 60.0
        assert "pre_launch" not in ready(load(path))

        # init is resume-safe: it returns existing progress, never resets it.
        args = argparse.Namespace(plan=None, file=str(path), run_dir=tmp, force=False)
        plan_file = Path(tmp) / "plan.json"
        plan_file.write_text(json.dumps(plan), encoding="utf-8")
        args.plan = str(plan_file)
        assert _init(args)["percent"] == 60.0

        # An empty plan is explicitly empty, never a fake 100%.
        empty = new_progress({"launch_id": "empty-launch"})
        assert empty["units"] == {}
        assert percent(empty) == 0.0
        assert ready(empty) == []
        assert ready_to_start(empty)["ready"] == []


if __name__ == "__main__":
    raise SystemExit(main())
