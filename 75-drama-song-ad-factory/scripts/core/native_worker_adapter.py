#!/usr/bin/env python3
"""Skill75 native worker record adapter (candidate, unapplied).

Honest boundary, separate from any repair-run supervisor/watchdog:
  * It observes the real Workflow host records (journal.jsonl + agent-*.meta.json)
    and persists exact start/result/route identities.
  * It plans a dependency-ready, owned-path-disjoint worker frontier.
  * It never launches, steers, pauses, cancels, reconciles or resumes a native
    worker. Those verbs return typed UNAVAILABLE_EXTERNAL: there is no supported
    external harness control endpoint. No executable stub is fabricated.
  * It never changes guards, settings, providers, routes or credentials.

Supported input (demonstrated by real records under the selected runtime profile):
    <run-dir>/journal.jsonl
        {"type":"launched"}
        {"type":"started","key":K,"agentId":A,"label":L,"phase":P}
        {"type":"result","key":K,"agentId":A,"result":R}
    <run-dir>/agent-A.meta.json
        {"agentType":"workflow-subagent","description":D,"workflowPhase":P,
         "spawnDepth":1,"requestShape":"foreground","requestNonInteractive":false,
         "model":M}

Served route is stored only from an explicit route map supplied by the caller.
Absent evidence is UNAVAILABLE_SERVED_ROUTE, never inferred from the requested model.

CLI:
    python3 -I native_worker_adapter.py --run-dir PATH [--served-routes JSON]
        [--units JSON] [--capacity JSON] [--out PATH]
    any of --launch --steer --pause --cancel --reconcile --resume
        -> typed UNAVAILABLE_EXTERNAL, exit 4, zero writes.

Exit: 0 supported observation; 2 record invalid/unavailable; 4 control unavailable;
      5 config/input error.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pathlib
import posixpath
import sys

SCHEMA = "skill75.native-worker-records/v1"
FRONTIER_SCHEMA = "skill75.native-worker-frontier/v1"
UNAVAILABLE_CONTROL = "UNAVAILABLE_EXTERNAL"
RESOLVED_STATES = {"resolved", "complete", "completed", "finalized", "committed",
                   "applied", "done", "closed"}
ACTIVE_STATES = {"running", "started", "in_progress", "claimed", "active"}
CONTROL_VERBS = ("launch", "steer", "pause", "cancel", "reconcile", "resume")


class RecordError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return default, "missing: %s" % path
    except (OSError, ValueError) as exc:
        return default, "unreadable: %s (%s)" % (path, exc)


def capabilities():
    unavailable = ("%s: no supported external harness control endpoint; owner stop "
                   "and host records remain read-only" % UNAVAILABLE_CONTROL)
    return {
        "observe_host_records": "SUPPORTED_READ_ONLY",
        "persist_worker_records": "SUPPORTED_EXPLICIT_OUTPUT",
        "frontier_plan": "SUPPORTED_PURE",
        "launch": unavailable,
        "steer": unavailable,
        "pause": unavailable,
        "cancel": unavailable,
        "reconcile": unavailable,
        "resume": unavailable,
        "settings_provider_mutation": "NOT_SUPPORTED",
    }


def _served(served_routes, run_id, agent_id):
    if not isinstance(served_routes, dict):
        return None, "no explicit route map"
    flat = served_routes.get("%s/%s" % (run_id, agent_id))
    if isinstance(flat, str) and flat.strip():
        return flat.strip(), "route-map-flat"
    runs = served_routes.get("runs")
    if isinstance(runs, dict):
        run = runs.get(run_id)
        if isinstance(run, dict):
            agents = run.get("agents")
            if isinstance(agents, dict):
                got = agents.get(agent_id)
                if isinstance(got, str) and got.strip():
                    return got.strip(), "route-map-runs"
    return None, "no served-route record for this agent"


def read_run(run_dir, served_routes=None):
    """Read one real Workflow run directory. Read-only; no host process contact."""
    run_dir = pathlib.Path(run_dir)
    run_id = run_dir.name
    journal = run_dir / "journal.jsonl"
    if not run_dir.is_dir():
        raise RecordError("UNAVAILABLE_RECORD", "run directory missing: %s" % run_dir)
    if not journal.is_file():
        raise RecordError("UNAVAILABLE_RECORD", "journal missing: %s" % journal)
    try:
        journal_sha = sha256_file(journal)
        lines = journal.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise RecordError("UNAVAILABLE_RECORD", "journal unreadable: %s" % exc)

    launched = 0
    started = collections.OrderedDict()
    results = {}
    unknown = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError as exc:
            raise RecordError("INVALID_RECORD", "journal line %d: %s" % (number, exc))
        if not isinstance(event, dict):
            raise RecordError("INVALID_RECORD", "journal line %d is not an object" % number)
        kind = event.get("type")
        if kind == "launched":
            launched += 1
            continue
        if kind == "started":
            key, agent = event.get("key"), event.get("agentId")
            if not isinstance(key, str) or not key or not isinstance(agent, str) or not agent:
                raise RecordError("INVALID_RECORD", "started line %d lacks key/agentId" % number)
            if key in started:
                raise RecordError("INVALID_RECORD", "duplicate started key: %s" % key)
            if any(row["agentId"] == agent for row in started.values()):
                raise RecordError("INVALID_RECORD", "duplicate started agentId: %s" % agent)
            started[key] = {"key": key, "agentId": agent,
                            "label": event.get("label"), "phase": event.get("phase")}
            continue
        if kind == "result":
            key, agent = event.get("key"), event.get("agentId")
            if key not in started:
                raise RecordError("INVALID_RECORD", "result without started key: %r" % key)
            if agent != started[key]["agentId"]:
                raise RecordError("INVALID_RECORD", "result agent mismatch for key: %s" % key)
            if key in results:
                raise RecordError("INVALID_RECORD", "duplicate result key: %s" % key)
            text = event.get("result")
            if not isinstance(text, str) or not text.strip():
                raise RecordError("INVALID_RECORD", "empty/non-string result for %s" % key)
            results[key] = text
            continue
        unknown.append(str(kind))

    records = []
    for key, row in started.items():
        agent = row["agentId"]
        meta_path = run_dir / ("agent-%s.meta.json" % agent)
        meta, meta_err = load_json(meta_path, {})
        if not isinstance(meta, dict):
            meta, meta_err = {}, "meta is not an object: %s" % meta_path
        requested = meta.get("model")
        requested = requested.strip() if isinstance(requested, str) and requested.strip() else None
        served, served_src = _served(served_routes, run_id, agent)
        text = results.get(key)
        records.append({
            "run_id": run_id,
            "agent_id": agent,
            "label": row.get("label"),
            "phase": row.get("phase"),
            "spawn_depth": meta.get("spawnDepth"),
            "request_shape": meta.get("requestShape"),
            "agent_type": meta.get("agentType"),
            "route": {
                "requested_model": requested,
                "requested_status": "RECORDED" if requested else "UNAVAILABLE_REQUESTED_ROUTE",
                "served_model": served,
                "served_status": "RECORDED" if served else "UNAVAILABLE_SERVED_ROUTE",
                "served_source": served_src,
                "evidence": str(meta_path) if not meta_err else None,
                "meta_error": meta_err,
            },
            "start": {
                "event": "started", "key": key,
                "journal": str(journal), "journal_sha256": journal_sha,
            },
            "result": {
                "event": "result", "key": key,
                "nonempty": bool(text),
                "chars": len(text) if text else 0,
                "sha256": sha256_bytes(text.encode("utf-8")) if text else None,
                "text": text,
            },
        })

    if not started:
        state = "UNAVAILABLE_RECORD"
    elif len(results) == len(started):
        state = "COMPLETE"
    else:
        state = "PARTIAL"
    return {
        "schema": SCHEMA,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "journal": str(journal),
        "journal_sha256": journal_sha,
        "state": state,
        "launched_events": launched,
        "started_count": len(started),
        "result_count": len(results),
        "unknown_event_types": sorted(set(unknown)),
        "capabilities": capabilities(),
        "workers": records,
    }


def _owned(unit):
    raw = unit.get("owned_paths") or []
    if not isinstance(raw, list) or any(not isinstance(p, str) or not p.strip() for p in raw):
        raise RecordError("INVALID_UNIT", "owned_paths must be non-empty strings")
    out = []
    for path in raw:
        norm = posixpath.normpath(path.strip().replace("\\", "/")).strip("/")
        if norm and norm != ".":
            out.append(norm)
    return tuple(sorted(set(out)))


def _overlaps(left, right):
    for a in left:
        for b in right:
            if a == b or a.startswith(b + "/") or b.startswith(a + "/"):
                return True
    return False


def worker_frontier(units, capacity=None):
    """Dependency-ready, owned-path-disjoint selection. Pure; no I/O, no launches.

    A path is either equal to or nested under another owned path = collision.
    Active units already holding a path exclude a new unit that would overlap.
    """
    if not isinstance(units, list):
        raise RecordError("INVALID_UNIT", "units must be a list")
    rows = []
    seen = set()
    for unit in units:
        if not isinstance(unit, dict):
            raise RecordError("INVALID_UNIT", "unit is not an object")
        uid = unit.get("unit") or unit.get("id")
        if not isinstance(uid, str) or not uid.strip():
            raise RecordError("INVALID_UNIT", "unit id missing")
        uid = uid.strip()
        if uid in seen:
            raise RecordError("INVALID_UNIT", "duplicate unit id: %s" % uid)
        seen.add(uid)
        deps = unit.get("depends_on") or []
        if not isinstance(deps, list) or any(not isinstance(d, str) for d in deps):
            raise RecordError("INVALID_UNIT", "depends_on must be strings for %s" % uid)
        rows.append({"unit": uid, "state": str(unit.get("state") or "").lower(),
                     "depends_on": list(deps), "owned_paths": _owned(unit)})

    active = [r for r in rows if r["state"] in ACTIVE_STATES]
    collisions = []
    for i, left in enumerate(active):
        for right in active[i + 1:]:
            if _overlaps(left["owned_paths"], right["owned_paths"]):
                collisions.append({"units": [left["unit"], right["unit"]],
                                   "reason": "PATH_COLLISION_ACTIVE"})
    resolved = {r["unit"] for r in rows if r["state"] in RESOLVED_STATES}

    selected, excluded = [], []
    for row in sorted(rows, key=lambda r: r["unit"]):
        uid = row["unit"]
        if row["state"] != "ready":
            excluded.append({"unit": uid, "reason": "WAIT_STATE", "state": row["state"]})
            continue
        wait = [d for d in row["depends_on"] if d not in resolved]
        if wait:
            excluded.append({"unit": uid, "reason": "WAIT_DEP", "depends_on": wait})
            continue
        clash_active = next((a for a in active
                             if _overlaps(row["owned_paths"], a["owned_paths"])), None)
        if clash_active is not None:
            excluded.append({"unit": uid, "reason": "PATH_COLLISION_ACTIVE",
                             "with": clash_active["unit"]})
            continue
        clash = next((s for s in selected
                      if _overlaps(row["owned_paths"], s["owned_paths"])), None)
        if clash is not None:
            excluded.append({"unit": uid, "reason": "PATH_COLLISION_SELECTED",
                             "with": clash["unit"]})
            continue
        if capacity is not None and len(selected) >= int(capacity):
            excluded.append({"unit": uid, "reason": "CAPACITY"})
            continue
        selected.append({"unit": uid, "owned_paths": list(row["owned_paths"])})

    return {
        "schema": FRONTIER_SCHEMA,
        "capacity": capacity,
        "selected": selected,
        "excluded": excluded,
        "collisions": collisions,
        "rule": "ready + dependencies resolved + owned paths disjoint; no launch",
    }


def persist(payload, out_path):
    """Write the caller's explicit output path atomically. Creates parent only."""
    path = pathlib.Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return str(path)


def _capacity_from(path):
    if not path:
        return None
    data, err = load_json(path, None)
    if err or data is None:
        raise RecordError("INVALID_CAPACITY", err or "empty capacity file")
    if isinstance(data, int) and not isinstance(data, bool) and data > 0:
        return data
    if isinstance(data, dict):
        for key in ("max_agents_per_workflow", "max_total_agents", "agents", "capacity"):
            value = data.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return value
    raise RecordError("INVALID_CAPACITY", "no positive integer capacity in %s" % path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Skill75 native worker record adapter")
    ap.add_argument("--run-dir")
    ap.add_argument("--served-routes")
    ap.add_argument("--units")
    ap.add_argument("--capacity")
    ap.add_argument("--out")
    for verb in CONTROL_VERBS:
        ap.add_argument("--" + verb, action="store_true")
    args = ap.parse_args(argv)

    requested = [verb for verb in CONTROL_VERBS if getattr(args, verb)]
    if requested:
        print(json.dumps({
            "schema": SCHEMA, "requested": requested,
            "status": UNAVAILABLE_CONTROL,
            "reason": "no supported external harness control endpoint; record observation only",
            "writes": [],
        }, sort_keys=True))
        return 4

    records = frontier = None
    status = 0
    try:
        if args.run_dir:
            served, served_err = (load_json(args.served_routes, {})
                                  if args.served_routes else (None, None))
            if served_err:
                raise RecordError("INVALID_ROUTE_MAP", served_err)
            records = read_run(args.run_dir, served)
            if records["state"] != "COMPLETE":
                status = 2
        if args.units:
            units, units_err = load_json(args.units, None)
            if units_err or units is None:
                raise RecordError("INVALID_UNIT", units_err or "empty units file")
            frontier = worker_frontier(units, _capacity_from(args.capacity))
        if not args.run_dir and not args.units:
            raise RecordError("INVALID_INPUT", "supply --run-dir and/or --units")
    except RecordError as exc:
        print(json.dumps({"schema": SCHEMA, "status": exc.code, "reason": exc.message,
                          "writes": []}, sort_keys=True))
        return 5

    payload = {"schema": SCHEMA, "records": records, "frontier": frontier}
    if args.out:
        payload["writes"] = [persist(payload, args.out)]
    print(json.dumps(payload, indent=1, sort_keys=True))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
