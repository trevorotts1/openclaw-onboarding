#!/usr/bin/env python3
"""Project-local admission ledger; trusted coordinator owns this database.

Usage: python3 workflow_slots.py /absolute/run/slots.sqlite < command.json
Commands: init(coordinator), open(workflow_id), reserve(workflow_id,
reservation_id, role, route, parent, unit, lease_seconds), start(reservation_id,
fence, agent_id, session_ref), renew(reservation_id, fence, lease_seconds),
check(reservation_id, fence), release(reservation_id, fence, evidence),
close(workflow_id), snapshot(). All commands carry `action` and `coordinator`.
Initialize once with trusted root identity; only that coordinator may mutate.
Reservation IDs exist before launch; actual agent/session IDs bind after spawn.

Reserve BEFORE launch. A failed/unknown launch retains its reservation. Expiry
fences start/check, never reclaims capacity. Release requires coordinator-verified
terminal evidence; this ledger does not pretend to inspect remote processes.
For an unstarted reservation, evidence kind=launch_cancelled confirms launch was
never sent. Otherwise kind=session_terminal must match its bound session_ref.
Both require verified=true and a nonempty reference. Do not expose this CLI to
workers or untrusted requests. Host guard remains owner of native visibility.
"""
import json
import math
import sqlite3
import sys
import time
import uuid
from contextlib import closing
from pathlib import Path

ROUTES = {"builder": "opus-chain", "reviewer": "sonnet-chain", "merge_operator": "haiku-chain"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS coordinator (id INTEGER PRIMARY KEY CHECK(id=1), identity TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workflows (
 workflow_id TEXT PRIMARY KEY, opened REAL NOT NULL, closed REAL
);
CREATE TABLE IF NOT EXISTS slots (
 reservation_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL REFERENCES workflows,
 role TEXT NOT NULL, route TEXT NOT NULL, parent TEXT NOT NULL, unit TEXT NOT NULL,
 fence TEXT NOT NULL, state TEXT NOT NULL, reserved REAL NOT NULL,
 expires REAL NOT NULL, started REAL, ended REAL, session_ref TEXT UNIQUE,
 terminal_evidence TEXT, agent_id TEXT UNIQUE, renewed REAL
);
"""


def text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise ValueError("invalid " + name)
    return value


def execute(database, command):
    """Execute one atomic admission/state transition. Return persisted facts only."""
    if not isinstance(command, dict):
        raise ValueError("command must be an object")
    action = command.get("action")
    fields = {
        "init": set(), "open": {"workflow_id"}, "close": {"workflow_id"},
        "reserve": {"workflow_id", "reservation_id", "role", "route", "parent", "unit", "lease_seconds"},
        "start": {"reservation_id", "fence", "agent_id", "session_ref"},
        "renew": {"reservation_id", "fence", "lease_seconds"},
        "check": {"reservation_id", "fence"},
        "release": {"reservation_id", "fence", "evidence"}, "snapshot": set(),
    }
    if not isinstance(action, str) or action not in fields:
        raise ValueError("unknown action")
    if set(command) != fields[action] | {"action", "coordinator"}:
        raise ValueError("missing or unknown command fields")
    for key in (fields[action] | {"coordinator"}) - {"lease_seconds", "evidence"}:
        text(command[key], key)
    if "lease_seconds" in command:
        seconds = command["lease_seconds"]
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 < seconds <= 86400:
            raise ValueError("invalid lease_seconds")
    path = Path(database)
    if not path.is_absolute():
        raise ValueError("database must be absolute")
    # ponytail: one local SQLite file per project; distributed runners need a shared transactional service.
    with closing(sqlite3.connect(path, timeout=10, isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        try:
            result = transition(db, command)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise


def transition(db, c):
    action, now = c["action"], time.time()
    owner = db.execute("SELECT identity FROM coordinator WHERE id=1").fetchone()
    if action == "init" and owner is None:
        db.execute("INSERT INTO coordinator VALUES(1,?)", (c["coordinator"],))
        return {"coordinator": c["coordinator"]}
    if owner is None or owner[0] != c["coordinator"]:
        raise ValueError("trusted coordinator required")
    if action == "init":
        return {"coordinator": owner[0]}
    if action == "snapshot":
        return {
            "workflows": [dict(r) for r in db.execute("SELECT * FROM workflows ORDER BY opened")],
            "slots": [dict(r) for r in db.execute("SELECT * FROM slots ORDER BY reserved")],
            "active_workflows": db.execute("SELECT count(*) FROM workflows WHERE closed IS NULL").fetchone()[0],
            "reserved_or_live": db.execute("SELECT count(*) FROM slots WHERE ended IS NULL").fetchone()[0],
            "route_evidence": "requested_only; verify served route from harness/router receipts",
            "native_visibility": "UNVERIFIED",
        }
    if action == "open":
        existing = db.execute("SELECT * FROM workflows WHERE workflow_id=?", (c["workflow_id"],)).fetchone()
        if existing:
            if existing["closed"] is not None:
                raise ValueError("workflow ID retired; use a new ID")
            return dict(existing)
        if db.execute("SELECT count(*) FROM workflows WHERE closed IS NULL").fetchone()[0] >= 10:
            raise ValueError("workflow limit")
        db.execute("INSERT INTO workflows VALUES(?,?,NULL)", (c["workflow_id"], now))
        return {"workflow_id": c["workflow_id"], "opened": now, "closed": None}
    if action == "close":
        if db.execute("SELECT 1 FROM slots WHERE workflow_id=? AND ended IS NULL", (c["workflow_id"],)).fetchone():
            raise ValueError("workflow still has reserved/live agents")
        if db.execute("UPDATE workflows SET closed=? WHERE workflow_id=? AND closed IS NULL", (now, c["workflow_id"])).rowcount != 1:
            raise ValueError("workflow not active")
        return {"workflow_id": c["workflow_id"], "closed": now}
    if action == "reserve":
        if ROUTES.get(c["role"]) != c["route"]:
            raise ValueError("role/route mismatch")
        seconds = c["lease_seconds"]
        if c["parent"] != owner[0]:
            raise ValueError("nested reservation prohibited")
        if not db.execute("SELECT 1 FROM workflows WHERE workflow_id=? AND closed IS NULL", (c["workflow_id"],)).fetchone():
            raise ValueError("workflow not active")
        if db.execute("SELECT 1 FROM slots WHERE reservation_id=?", (c["reservation_id"],)).fetchone():
            raise ValueError("agent ID already reserved; reconcile rather than respawn")
        if db.execute("SELECT count(*) FROM slots WHERE ended IS NULL").fetchone()[0] >= 100:
            raise ValueError("global agent limit")
        if db.execute("SELECT count(*) FROM slots WHERE workflow_id=? AND ended IS NULL", (c["workflow_id"],)).fetchone()[0] >= 10:
            raise ValueError("workflow agent limit")
        db.execute("INSERT INTO slots VALUES(?,?,?,?,?,?,?,'reserved',?,?,NULL,NULL,NULL,NULL,NULL,NULL)",
                   (c["reservation_id"], c["workflow_id"], c["role"], c["route"], c["parent"], c["unit"], uuid.uuid4().hex, now, now + seconds))
    else:
        row = db.execute("SELECT * FROM slots WHERE reservation_id=?", (c["reservation_id"],)).fetchone()
        if row is None or row["fence"] != c["fence"] or row["ended"] is not None:
            raise ValueError("stale or unknown reservation")
        if action in ("start", "check", "renew") and now >= row["expires"]:
            raise ValueError("lease expired; capacity retained until verified termination")
        if action == "start":
            if row["state"] != "reserved":
                raise ValueError("agent already started")
            db.execute("UPDATE slots SET state='live',started=?,session_ref=?,agent_id=? WHERE reservation_id=?", (now, c["session_ref"], c["agent_id"], c["reservation_id"]))
        elif action == "renew":
            db.execute("UPDATE slots SET expires=?,renewed=? WHERE reservation_id=?", (max(row["expires"], now + c["lease_seconds"]), now, c["reservation_id"]))
        elif action == "release":
            e = c["evidence"]
            if not isinstance(e, dict) or e.get("verified") is not True:
                raise ValueError("verified terminal evidence required")
            text(e.get("reference"), "terminal evidence reference")
            if row["session_ref"] is None:
                if e.get("kind") != "launch_cancelled":
                    raise ValueError("confirm launch never sent before cancelling reservation")
            elif e.get("kind") != "session_terminal" or e.get("session_ref") != row["session_ref"] or e.get("status") not in ("completed", "failed", "cancelled"):
                raise ValueError("terminal evidence does not match bound session")
            db.execute("UPDATE slots SET state='released',ended=?,fence=?,terminal_evidence=? WHERE reservation_id=?", (now, uuid.uuid4().hex, json.dumps(e, sort_keys=True), c["reservation_id"]))
    return dict(db.execute("SELECT * FROM slots WHERE reservation_id=?", (c["reservation_id"],)).fetchone())


def main():
    try:
        if len(sys.argv) != 2:
            raise ValueError("usage: workflow_slots.py /absolute/run/slots.sqlite < command.json")
        result = execute(sys.argv[1], json.load(sys.stdin))
        print(json.dumps({"ok": True, "result": result}, allow_nan=False))
        return 0
    except (ValueError, TypeError, sqlite3.Error, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
