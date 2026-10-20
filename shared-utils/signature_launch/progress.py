#!/usr/bin/env python3
"""Resumable launch progress file: every unit's state, one percentage.

WF-SWARM progress lane. One JSON file per launch (keyed by launch_id), holding
every unit from the approved launch plan (pages, email sequences, text sets,
automations). A stopped run resumes from this file:

- finished units are skipped (never re-dispatched, never re-charged),
- an active unit whose artifact already exists is recovered as done by the
  existence check (Skill 44 build already happened; no duplicate build),
- percentages count terminal units (done or dropped by the client).

Pure stdlib, no network, no credentials. The file is written atomically so a
crash mid-save leaves the previous progress intact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"
KINDS = (
    ("page", "pages"),
    ("email_sequence", "email_sequences"),
    ("text_set", "text_sets"),
    ("automation", "automations"),
)
STATES = ("pending", "running", "done", "failed", "blocked", "dropped")
TERMINAL = ("done", "dropped")


class ProgressError(ValueError):
    """A progress file or launch plan that cannot be trusted. Fail closed."""


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def plan_hash(plan):
    return "sha256:" + hashlib.sha256(_canonical(plan).encode("utf-8")).hexdigest()


def units_from_plan(plan):
    """Ordered [{id, kind, waits_for}] from a launch plan. Fail closed."""
    if not isinstance(plan, dict):
        raise ProgressError("plan must be a JSON object")
    launch_id = str(plan.get("launch_id") or "")
    if not launch_id:
        raise ProgressError("plan has no launch_id")
    units, seen = [], set()
    for kind, key in KINDS:
        rows = plan.get(key)
        if rows is None:
            continue
        if not isinstance(rows, list):
            raise ProgressError("%s must be a list" % key)
        for row in rows:
            uid = str((row or {}).get("id") or "")
            if not uid:
                raise ProgressError("%s has a unit with no id" % key)
            if uid in seen:
                raise ProgressError("duplicate unit id: %s" % uid)
            waits = (row or {}).get("waits_for") or []
            if not isinstance(waits, list):
                raise ProgressError("waits_for on %s must be a list" % uid)
            seen.add(uid)
            units.append({"id": uid, "kind": kind, "waits_for": [str(w) for w in waits]})
    for unit in units:
        unknown = [w for w in unit["waits_for"] if w not in seen]
        if unknown:
            raise ProgressError("unit %s waits_for unknown unit(s): %s"
                                % (unit["id"], ", ".join(unknown)))
    return launch_id, units


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
                "updated_at": stamp,
            }
            for u in units
        },
    }


def default_path(run_dir, launch_id):
    return Path(run_dir) / ("progress-%s.json" % launch_id)


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
        if unit.get("state") not in STATES:
            raise ProgressError("unit %s has unknown state %r" % (uid, unit.get("state")))
        if not isinstance(unit.get("waits_for", []), list):
            raise ProgressError("unit %s waits_for must be a list" % uid)
        unknown = [w for w in unit.get("waits_for") or [] if w not in units]
        if unknown:
            raise ProgressError("unit %s waits_for unknown unit(s): %s"
                                % (uid, ", ".join(map(str, unknown))))
    return record


def load(path):
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProgressError("cannot read progress file %s: %s" % (path, exc))
    return validate(record)


def save(record, path):
    """Atomic write, so an interrupted save never corrupts progress."""
    validate(record)
    record["updated_at"] = _now()
    record["percent"] = percent(record)
    record["counts"] = counts(record)
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
    return out


def percent(record):
    """Percentage of planned units that are terminal (done or dropped)."""
    c = counts(record)
    if not c["total"]:
        return 0.0
    return round(100.0 * c["terminal"] / c["total"], 2)


def ready(record):
    """Units a resumed run should start, in plan order.

    Finished units (done, dropped) are skipped. Units still waiting on an
    unfinished dependency are skipped. Failed/blocked units are retried.
    """
    done = {uid for uid, u in record["units"].items() if u["state"] in TERMINAL}
    out = []
    for uid, unit in record["units"].items():
        if unit["state"] in TERMINAL:
            continue
        if all(w in done for w in unit.get("waits_for") or []):
            out.append(uid)
    return out


def artifact_exists(record, uid, exists=None):
    """True when the unit's recorded artifact is already on disk."""
    path = record["units"][uid].get("artifact")
    if not path:
        return False
    check = exists or (lambda p: Path(p).exists())
    try:
        return bool(check(path))
    except OSError:
        return False


def recover(record, exists=None):
    """Existence check: an active unit whose artifact exists is already built.

    Marks it done without dispatching, so the run neither pays again nor
    creates a duplicate build (Skill 44 existence check). Returns recovered ids.
    """
    recovered = []
    for uid, unit in record["units"].items():
        if unit["state"] in TERMINAL:
            continue
        if artifact_exists(record, uid, exists):
            unit["state"] = "done"
            unit["note"] = "recovered: artifact exists"
            unit["updated_at"] = _now()
            recovered.append(uid)
    return recovered


def mark(record, uid, state, artifact=None, charged=None, note=None, clock=_now):
    """Move one unit's state. Marking a terminal unit done again is a no-op.

    Returns False when the unit was already terminal (nothing re-charged).
    """
    if state not in STATES:
        raise ProgressError("unknown state: %s" % state)
    unit = record["units"].get(uid)
    if unit is None:
        raise ProgressError("unknown unit: %s" % uid)
    if unit["state"] in TERMINAL:
        return False
    if unit["state"] != state:
        unit["attempts"] = int(unit.get("attempts") or 0) + (1 if state == "running" else 0)
    unit["state"] = state
    if artifact is not None:
        unit["artifact"] = str(artifact)
    if charged is not None:
        unit["charged"] = bool(charged)
    if note is not None:
        unit["note"] = str(note)
    unit["updated_at"] = clock()
    return True


def summary(record):
    c = counts(record)
    return {
        "launch_id": record["launch_id"],
        "percent": percent(record),
        "counts": c,
        "ready": ready(record),
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("init", help="create (or keep) the progress file for a plan")
    p.add_argument("--plan", required=True)
    p.add_argument("--file")
    p.add_argument("--run-dir", default=".")
    p.add_argument("--force", action="store_true", help="rewrite an existing file")

    p = sub.add_parser("status", help="percentage and counts")
    p.add_argument("--file", required=True)

    p = sub.add_parser("next", help="units to start or retry on resume")
    p.add_argument("--file", required=True)

    p = sub.add_parser("mark", help="set one unit's state")
    p.add_argument("--file", required=True)
    p.add_argument("--unit", required=True)
    p.add_argument("--state", required=True, choices=STATES)
    p.add_argument("--artifact")
    p.add_argument("--charged", action="store_true")
    p.add_argument("--note")

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
        record = load(args.file)
        if args.cmd == "status":
            print(json.dumps(summary(record), indent=2, sort_keys=True))
            return 0
        if args.cmd == "next":
            print(json.dumps({"ready": ready(record)}, indent=2))
            return 0
        if args.cmd == "mark":
            mark(record, args.unit, args.state, artifact=args.artifact,
                 charged=True if args.charged else None, note=args.note)
            save(record, args.file)
            print(json.dumps(summary(record), indent=2, sort_keys=True))
            return 0
        if args.cmd == "recover":
            found = recover(record)
            save(record, args.file)
            print(json.dumps({"recovered": found, **summary(record)}, indent=2, sort_keys=True))
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
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "progress.json"
        record = new_progress(plan)
        save(record, path)
        assert percent(record) == 0.0
        assert ready(record) == ["landing", "pre_launch"]

        mark(record, "landing", "done", artifact=str(Path(tmp) / "landing.html"))
        Path(tmp, "landing.html").write_text("built", encoding="utf-8")
        save(record, path)
        assert percent(record) == 20.0
        assert ready(record) == ["sales", "pre_launch", "doors_open"]

        # Re-marking a finished unit changes nothing and re-charges nothing.
        before = (record["units"]["landing"]["state"],
                  record["units"]["landing"]["attempts"])
        assert mark(record, "landing", "done", charged=True) is False
        assert (record["units"]["landing"]["state"],
                record["units"]["landing"]["attempts"]) == before

        # A crash left "sales" running after its artifact was written.
        mark(record, "sales", "running", artifact=str(Path(tmp) / "sales.html"))
        Path(tmp, "sales.html").write_text("built", encoding="utf-8")
        assert recover(record) == ["sales"]
        assert record["units"]["sales"]["state"] == "done"
        assert "sales" not in ready(record)

        mark(record, "pre_launch", "dropped", note="client dropped")
        save(record, path)
        assert percent(record) == 60.0
        assert load(path)["percent"] == 60.0

        # A finished unit never comes back on resume.
        assert "pre_launch" not in ready(load(path))

        # init is resume-safe: it returns existing progress, never resets it.
        args = argparse.Namespace(plan=None, file=str(path), run_dir=tmp, force=False)
        plan_file = Path(tmp) / "plan.json"
        plan_file.write_text(json.dumps(plan), encoding="utf-8")
        args.plan = str(plan_file)
        assert _init(args)["percent"] == 60.0


if __name__ == "__main__":
    raise SystemExit(main())
