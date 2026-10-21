#!/usr/bin/env python3
"""Resumable launch progress file: every unit's state, one percentage.

WF-SWARM progress lane. One JSON file per launch (keyed by launch_id), holding
every unit from the approved launch plan (pages, email sequences, text sets,
automations). A stopped run resumes from this file:

- finished units are skipped (never re-dispatched, never re-charged),
- an active unit whose artifact is already on disk is recovered as done by the
  existence check, but only when the artifact is provably non-empty and no live
  execution owner holds the unit (Skill 44 build already happened; no duplicate
  build, no stolen work),
- percentages count terminal units (done or dropped by the client),
- a unit being executed right now is reported as running, never as ready: a
  concurrent resume never claims it as fresh work,
- starting a unit requires execution ownership (a claim with a lease), so two
  resumes cannot both produce side effects for the same unit,
- a stall keeps its partial results and every causal blocker instead of being
  discarded.

The unit expansion is not re-implemented here: ``scheduler/model.py`` is the one
authority for the unit list and the result envelope (failed / blocked / awaiting
facts / dropped / verified success).  A failure returned normally never
satisfies a dependency.

Pure stdlib, no network, no credentials. The file is written atomically so a
crash mid-save leaves the previous progress intact.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
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


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def plan_hash(plan):
    return "sha256:" + hashlib.sha256(_canonical(plan).encode("utf-8")).hexdigest()


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
                "updated_at": stamp,
            }
            for u in units
        },
    }


def default_path(run_dir, launch_id):
    return Path(run_dir) / ("progress-%s.json" % launch_id)


def _fill(unit):
    """Backfill additive fields so an older progress file stays readable."""
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
    out["total"] = len(record["units"])
    out["terminal"] = out["done"] + out["dropped"]
    out["retryable"] = out["failed"]
    out["awaiting_facts"] = sum(
        1 for unit in record["units"].values() if unit.get("missing_facts"))
    out["ready"] = len(ready(record))
    out["empty"] = 1 if not record["units"] else 0
    return out


def percent(record):
    """Percentage of planned units that are terminal (done or dropped)."""
    c = counts(record)
    if not c["total"]:
        return 0.0
    return round(100.0 * c["terminal"] / c["total"], 2)


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
    return {uid for uid, unit in record["units"].items() if unit["state"] in TERMINAL}


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
    """True when the unit's recorded artifact is present and non-empty.

    A zero-byte file is not evidence (L04 receipt rule): it never recovers a
    unit to done.
    """
    path = record["units"][uid].get("artifact")
    if not path:
        return False
    check = exists or (lambda p: Path(p).is_file() and Path(p).stat().st_size > 0)
    try:
        return bool(check(path))
    except (OSError, ValueError):
        return False


def recover_report(record, exists=None, verify=None, now=None):
    """Existence check: an active unit whose artifact is proven is already built.

    ``verify(path, uid) -> (bool, detail)`` lets a receipt validator (L04) be
    injected; the default is exists-and-non-empty.  A unit held by a fresh
    execution lease is skipped, never stolen.  Marks done without dispatching,
    so the run neither pays again nor creates a duplicate build.  A present but
    empty/unverified artifact is recorded as a rejection, never as success.
    """
    now = now or _parse_time(_now())
    result = {"recovered": [], "skipped": [], "rejected": []}
    for uid, unit in record["units"].items():
        if unit["state"] in TERMINAL:
            continue
        if unit["state"] == "running" and _lease_is_fresh(unit, now):
            result["skipped"].append({"unit": uid, "reason": "live execution lease"})
            continue
        path = unit.get("artifact")
        if not path:
            continue
        if verify is not None:
            try:
                ok, detail = verify(path, uid)
            except (OSError, ValueError) as error:
                ok, detail = False, str(error)
        else:
            ok = artifact_exists(record, uid, exists)
            detail = "artifact exists and is non-empty" if ok else "artifact missing or empty"
        if not ok:
            if Path(path).exists():
                kind = "artifact_unverified" if verify is not None else "empty_artifact"
                unit["reason"] = {"kind": kind, "unit": uid, "detail": detail}
                unit["updated_at"] = _now()
                result["rejected"].append({"unit": uid, "detail": detail})
            continue
        unit["state"] = "done"
        unit["note"] = "recovered: %s" % detail
        unit["reason"] = None
        unit["owner"] = None
        unit["lease_expires_at"] = None
        unit["updated_at"] = _now()
        result["recovered"].append(uid)
    return result


def recover(record, exists=None, verify=None, now=None):
    """Backwards-compatible view: the recovered unit ids."""
    return recover_report(record, exists, verify, now)["recovered"]


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
                    "owner": owner, "previous_owner": previous}
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
    return {"claimed": True, "unit": uid, "owner": owner}


def _start_unit(unit, owner, ttl_seconds, now, clock):
    unit["state"] = "running"
    unit["owner"] = owner
    unit["lease_expires_at"] = (now + timedelta(seconds=max(1, int(ttl_seconds)))).isoformat() \
        .replace("+00:00", "Z")
    unit["attempts"] = int(unit.get("attempts") or 0) + 1
    unit["updated_at"] = clock()


def heartbeat(record, uid, owner, ttl_seconds=DEFAULT_LEASE_SECONDS, now=None, clock=_now):
    """Extend a live execution lease. Refuses a different owner."""
    now = now or _parse_time(_now())
    unit = record["units"].get(uid)
    if unit is None:
        raise ProgressError("unknown unit: %s" % uid)
    if unit["state"] != "running" or unit.get("owner") != owner:
        return {"renewed": False, "reason": "not the execution owner", "unit": uid}
    unit["lease_expires_at"] = (now + timedelta(seconds=max(1, int(ttl_seconds)))).isoformat() \
        .replace("+00:00", "Z")
    unit["updated_at"] = clock()
    return {"renewed": True, "unit": uid, "lease_expires_at": unit["lease_expires_at"]}


def release(record, uid, owner, note=None, clock=_now):
    """Give up execution ownership; partial results stay on the unit."""
    unit = record["units"].get(uid)
    if unit is None:
        raise ProgressError("unknown unit: %s" % uid)
    if unit["state"] != "running" or unit.get("owner") != owner:
        return {"released": False, "reason": "not the execution owner", "unit": uid}
    unit["state"] = "pending"
    unit["owner"] = None
    unit["lease_expires_at"] = None
    if note is not None:
        unit["note"] = str(note)
    unit["updated_at"] = clock()
    return {"released": True, "unit": uid}


def complete(record, uid, result, owner=None, artifact=None, clock=_now):
    """Record one runner result envelope under execution ownership.

    Success and drop are side-effect outcomes: they require the same owner that
    claimed the unit.  A normally returned failure is recorded as failed and
    never unlocks dependents.  A terminal unit is never charged again.
    """
    model = _model()
    unit = record["units"].get(uid)
    if unit is None:
        raise ProgressError("unknown unit: %s" % uid)
    envelope = result if isinstance(result, dict) and result.get("status") else \
        model.normalize_result(result)
    status = model.canonical_status(envelope.get("status"))
    if status is None:
        envelope = model.envelope(model.FAILED, detail="unknown result status")
        status = model.FAILED
    if unit["state"] in TERMINAL:
        return False
    if unit["state"] != "running":
        raise ProgressError("unit %s is not running; claim it before completing" % uid)
    if not owner or unit.get("owner") != owner:
        raise ProgressError("unit %s is owned by %r, not %r"
                            % (uid, unit.get("owner"), owner))
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
    if artifact is not None:
        unit["artifact"] = str(artifact)
    elif envelope.get("artifacts"):
        unit["artifact"] = str(envelope["artifacts"][0])
    if envelope.get("detail"):
        unit["note"] = str(envelope["detail"])
    unit["updated_at"] = clock()
    return True


def mark(record, uid, state, artifact=None, charged=None, note=None, clock=_now,
         owner=None):
    """Move one unit's state. A terminal unit is never re-marked.

    ``running`` is refused here: execution ownership comes from ``claim``.
    ``done`` requires the owner that holds the claim.  A failed/blocked unit
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
    if state == "done" and unit["state"] != "running":
        raise ProgressError("state done requires a claim and completion evidence")
    if state != "running":
        unit["owner"] = None
        unit["lease_expires_at"] = None
    unit["state"] = state
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


def complete_atomic(path, uid, result, owner, artifact=None):
    with _locked(path):
        record = load(path)
        changed = complete(record, uid, result, owner=owner, artifact=artifact)
        if changed:
            save(record, path)
        return changed


def recover_atomic(path, exists=None, verify=None):
    with _locked(path):
        record = load(path)
        report = recover_report(record, exists=exists, verify=verify)
        if report["recovered"] or report["rejected"]:
            save(record, path)
        return report


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

    p = sub.add_parser("mark", help="set one unit's state")
    p.add_argument("--file", required=True)
    p.add_argument("--unit", required=True)
    p.add_argument("--state", required=True, choices=STATES)
    p.add_argument("--artifact")
    p.add_argument("--charged", action="store_true")
    p.add_argument("--note")
    p.add_argument("--owner")

    p = sub.add_parser("recover", help="existence check: adopt artifacts already built")
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
            result = model.envelope(args.status, detail=args.detail,
                                    missing_facts=args.missing_fact)
            changed = complete_atomic(args.file, args.unit, result, args.owner,
                                      artifact=args.artifact)
            print(json.dumps({"changed": changed, **summary(load(args.file))},
                             indent=2, sort_keys=True))
            return 0
        if args.cmd == "recover":
            report = recover_atomic(args.file)
            print(json.dumps({**report, **summary(load(args.file))},
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
                 owner=args.owner)
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

        # A verified success unlocks dependents and preserves the paid worker.
        assert claim(record, "landing", "owner-a")["claimed"] is True
        assert complete(record, "landing", model.envelope(
            model.VERIFIED_SUCCESS, artifacts=[str(Path(tmp) / "landing.html")]),
            owner="owner-a") is True
        Path(tmp, "landing.html").write_text("built", encoding="utf-8")
        assert record["units"]["landing"]["state"] == "done"
        assert ready(record) == ["sales", "pre_launch", "doors_open"]

        # Re-marking a finished unit changes nothing and re-charges nothing.
        before = (record["units"]["landing"]["state"],
                  record["units"]["landing"]["attempts"])
        assert mark(record, "landing", "done", charged=True) is False
        assert (record["units"]["landing"]["state"],
                record["units"]["landing"]["attempts"]) == before

        # A crash left "sales" running after its artifact was written.
        assert claim(record, "sales", "owner-c")["claimed"] is True
        mark(record, "sales", "failed", owner="owner-c")  # simulate an old failed row
        record["units"]["sales"]["artifact"] = str(Path(tmp) / "sales.html")
        record["units"]["sales"]["state"] = "running"
        Path(tmp, "sales.html").write_text("built", encoding="utf-8")
        report = recover_report(record)
        assert report["recovered"] == ["sales"], report
        assert record["units"]["sales"]["state"] == "done"
        assert "sales" not in ready(record)

        # A zero-byte artifact never recovers.
        assert claim(record, "doors_open", "owner-d")["claimed"] is True
        mark(record, "doors_open", "failed", owner="owner-d")
        record["units"]["doors_open"]["artifact"] = str(Path(tmp) / "empty.html")
        Path(tmp, "empty.html").write_text("", encoding="utf-8")
        assert recover_report(record)["rejected"][0]["unit"] == "doors_open"
        assert record["units"]["doors_open"]["state"] == "failed"

        mark(record, "pre_launch", "dropped", note="client dropped")
        save(record, path)
        c = counts(record)
        assert c["done"] == 2 and c["dropped"] == 1 and c["failed"] == 1
        assert percent(record) == 60.0
        assert load(path)["percent"] == 60.0
        assert "pre_launch" not in ready(load(path))
        assert load(path)["stall"]["doors_open"]  # causal blocker persisted

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
