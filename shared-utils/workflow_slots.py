#!/usr/bin/env python3
"""Project-local admission ledger; trusted coordinator owns this database.

Usage: python3 workflow_slots.py /absolute/run/slots.sqlite < command.json
Commands: init(coordinator), open(workflow_id), reserve(workflow_id,
reservation_id, role[, route], parent, unit, lease_seconds), start(reservation_id,
fence, agent_id, session_ref), renew(reservation_id, fence, lease_seconds),
check(reservation_id, fence), release(reservation_id, fence, evidence),
close(workflow_id), snapshot(). All commands carry `action` and `coordinator`.
There is NO route allowlist: any non-empty route string is accepted and served.
Omitting `route` falls back to the role's chain in ROUTES (the default, not a
permitted set). Requested-vs-served is recorded at binding and never hidden.
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

# Default chain per role. NOT a permitted set: any route the caller names is
# accepted (A47), so a route outside this map can never be blocked.
ROUTES = {"builder": "deepseek-chain", "reviewer": "sonnet-chain", "merge_operator": "haiku-chain"}
# The harness writes agent-<agent_id>.meta.json (model= the route the agent
# ACTUALLY ran on) under these roots. Two layouts, both observed on this box:
#   <root>/<project-slug>/<session-uuid>/subagents/workflows/<wf-id>/agent-<agent_id>.meta.json
#   <root>/<project-slug>/<session-uuid>/subagents/agent-<agent_id>.meta.json
# The first is a workflow subagent, the second a session subagent. <wf-id> is the
# "wf_..." directory name AND the prefix of that agent's session_ref before '#'
# (session_ref is '<wf-id>#<agent_id>' or '<session-uuid>:<agent_id>'). It is NOT
# this ledger's workflow_id column: those are two different namespaces, observed
# side by side as wf_59f9ce0c-417 vs jev11-w49-a36-repair. Earlier revisions of
# this comment called the directory "<session_ref-prefix>" and sketched the path
# as <slug>/<session>/subagents/workflows/<session_ref-prefix>/; the directory
# really is the harness workflow id and the session segment is a UUID.
#
# The ledger itself sees only the REQUESTED route, so binding is the one moment
# both facts exist. These records are EPHEMERAL: measured on 2026-10-25 the two
# roots held 15,494 then 4,884 agent-*.meta.json files minutes apart as sessions
# were reaped, and every one of 348 archived reservation rows had lost its record.
# So the binding must be resolved and persisted at start(), never re-derived later.
META_ROOTS = (Path.home() / ".claude/projects", Path.home() / ".claude-nine/projects")
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
 terminal_evidence TEXT, agent_id TEXT UNIQUE, renewed REAL,
 served_route TEXT, route_binding TEXT, route_checked REAL
);
"""


def text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise ValueError("invalid " + name)
    return value


def workflow_of(session_ref):
    """The harness workflow id a session_ref binds under, or None for a session agent.

    session_ref is '<wf-id>#<agent_id>' for a workflow subagent and
    '<session-uuid>:<agent_id>' for a session subagent.
    """
    if not isinstance(session_ref, str):
        return None
    head, sep, _ = session_ref.partition("#")
    return head if sep and head.startswith("wf_") else None


def _meta_index(workflow_id=None):
    """agent_id -> meta.json path, for every harness-written binding record in scope.

    Scope is one harness workflow when workflow_id is given (records filed under
    subagents/workflows/<workflow_id>/), else the session-scoped layout only
    (records filed directly under subagents/). A record filed under a different
    workflow is out of scope and is never borrowed, so a fabricated or mismatched
    workflow id resolves to nothing rather than to somebody else's route.
    ponytail: rglobs both roots on every call; cache it if binding ever runs
    per-reservation inside a tight loop.
    """
    expected = ("subagents", "workflows", workflow_id) if workflow_id else ("subagents",)
    depth = len(expected) + 1
    index = {}
    for root in META_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("agent-*.meta.json"):
            if tuple(path.parts[-depth:-1]) != expected:
                continue
            index[path.name[len("agent-"):-len(".meta.json")]] = path
    return index


def served_route(agent_id, workflow_id=None):
    """The route the agent ACTUALLY ran on, read from the harness-written binding record.

    workflow_id scopes the lookup to that one harness workflow; pass
    workflow_of(session_ref). Returns the model name, or None when no in-scope
    record names that agent -- so a substitution can never be manufactured from
    an absent file, and never borrowed from another workflow's record.
    """
    path = _meta_index(workflow_id).get(agent_id)
    if path is None:
        return None
    try:
        model = json.loads(path.read_text()).get("model")
    except (OSError, ValueError):
        return None
    return model if isinstance(model, str) and model.strip() else None


def route_binding(requested, served):
    """Binding verdict for one reservation: requested route vs actually-run route.

    A record we cannot see is UNVERIFIED, never a match -- the absence of a
    witness is not evidence of agreement.
    """
    if served is None:
        return "unverified_no_binding_record"
    return "match" if served == requested else "substitution"


def execute(database, command):
    """Execute one atomic admission/state transition. Return persisted facts only."""
    if not isinstance(command, dict):
        raise ValueError("command must be an object")
    action = command.get("action")
    fields = {
        "init": set(), "open": {"workflow_id"}, "close": {"workflow_id"},
        "reserve": {"workflow_id", "reservation_id", "role", "parent", "unit", "lease_seconds"},
        "start": {"reservation_id", "fence", "agent_id", "session_ref"},
        "renew": {"reservation_id", "fence", "lease_seconds"},
        "check": {"reservation_id", "fence"},
        "release": {"reservation_id", "fence", "evidence"}, "snapshot": set(),
    }
    if not isinstance(action, str) or action not in fields:
        raise ValueError("unknown action")
    # `route` is optional on reserve: absent means the role default (A47).
    optional = {"route"} if action == "reserve" else set()
    base = fields[action] | {"action", "coordinator"}
    if frozenset(command) not in (frozenset(base), frozenset(base | optional)):
        raise ValueError("missing or unknown command fields")
    for key in (fields[action] | {"coordinator"}) - {"lease_seconds", "evidence"}:
        text(command[key], key)
    if command.get("route") is not None:
        text(command["route"], "route")
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
        # A47: ledgers created before route recording exist on disk; add the
        # columns additively so their bound rows survive untouched.
        existing = {r[1] for r in db.execute("PRAGMA table_info(slots)")}
        for column, kind in (("served_route", "TEXT"), ("route_binding", "TEXT"), ("route_checked", "REAL")):
            if column not in existing:
                db.execute(f"ALTER TABLE slots ADD COLUMN {column} {kind}")
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
        substitutions = [dict(r) for r in db.execute(
            "SELECT unit, role, route, served_route, agent_id FROM slots "
            "WHERE route_binding = 'substitution' ORDER BY reserved")]
        rows = [dict(r) for r in db.execute("SELECT * FROM slots ORDER BY reserved")]
        unverified = [r for r in rows if r["agent_id"] is not None and r["route_binding"] != "match"]
        flagged = list(substitutions) + [
            {k: r[k] for k in ("unit", "role", "route", "served_route", "agent_id")} for r in unverified
            if r["route_binding"] == "unverified_no_binding_record"]
        # A zero substitution count means nothing on its own: a row bound before
        # this recording existed has no verdict at all, and cannot be reported as
        # a clean binding. Counted separately so the zero can never be misread.
        unrecorded = sum(1 for r in rows if r["agent_id"] is not None and not r["route_binding"])
        alarm = ""
        if flagged:
            alarm = "!!! ROUTE SUBSTITUTION ALERT - " + "; ".join(
                f"{f['unit']} {f['role']} requested={f['route']} served={f['served_route']}" for f in flagged)
        if unrecorded:
            alarm = (f"!! {unrecorded} bound rows have NO route-binding record "
                     f"(bound before A47 recording); their requested-vs-served route is UNPROVEN, "
                     f"not clean. " + alarm).strip()
        return {
            "workflows": [dict(r) for r in db.execute("SELECT * FROM workflows ORDER BY opened")],
            "slots": rows,
            "active_workflows": db.execute("SELECT count(*) FROM workflows WHERE closed IS NULL").fetchone()[0],
            "reserved_or_live": db.execute("SELECT count(*) FROM slots WHERE ended IS NULL").fetchone()[0],
            "route_substitutions": flagged,
            "route_substitution_count": len(flagged),
            "route_unrecorded_count": unrecorded,
            "route_alarm": alarm,
            "route_evidence": "requested_and_served; served route recorded at binding from the harness binding record"
                              " where present, else explicitly marked unverified",
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
        # A47: route is whatever the caller asked for. Only a MISSING route on a
        # role with no default is an error; no route string is ever rejected.
        route = c.get("route") or ROUTES.get(c["role"])
        if route is None:
            raise ValueError("route required: role has no default route")
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
        db.execute("INSERT INTO slots(reservation_id,workflow_id,role,route,parent,unit,fence,state,reserved,expires)"
                   " VALUES(?,?,?,?,?,?,?,'reserved',?,?)",
                   (c["reservation_id"], c["workflow_id"], c["role"], route, c["parent"], c["unit"], uuid.uuid4().hex, now, now + seconds))
    else:
        row = db.execute("SELECT * FROM slots WHERE reservation_id=?", (c["reservation_id"],)).fetchone()
        if row is None or row["fence"] != c["fence"] or row["ended"] is not None:
            raise ValueError("stale or unknown reservation")
        if action in ("start", "check", "renew") and now >= row["expires"]:
            raise ValueError("lease expired; capacity retained until verified termination")
        if action == "start":
            if row["state"] != "reserved":
                raise ValueError("agent already started")
            # Bind now: the harness record is ephemeral, so this is the one moment
            # the requested route and the actually-run route can be compared.
            served = served_route(c["agent_id"], workflow_of(c["session_ref"]))
            binding = route_binding(row["route"], served)
            db.execute("UPDATE slots SET state='live',started=?,session_ref=?,agent_id=?,served_route=?,route_binding=?,route_checked=? WHERE reservation_id=?",
                       (now, c["session_ref"], c["agent_id"], served, binding, now, c["reservation_id"]))
            if binding == "substitution":
                # Trevor's A47 order: a substitution must not be silent, so it is
                # stated in the command's own result, not merely stored.
                print(f"ROUTE SUBSTITUTION: unit={row['unit']} role={row['role']} "
                      f"requested={row['route']} served={served} agent_id={c['agent_id']}", file=sys.stderr)
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
