#!/usr/bin/env python3
"""Job recovery: verified callbacks/polls in, never a resubmission out.

Directive sections 18 + 24.4. Stdlib only. Consumes verified relay/poll
results; correlates run/request/task/attempt IDs; dedupes and applies
out-of-order events by provider_seq; persists downloaded results; recovers
existing jobs without automatically repeating uncertain submissions.

Authority rules:
- Callbacks never create jobs (NO_SUCH_JOB) and never dispatch (DB rows are
  never re-dispatched). Unknown acceptance -> park, per section 18.
- Verified provider events are authoritative input, not worker claims, so
  ingest does not take worker leases; cross-process safety comes from
  BEGIN IMMEDIATE + UNIQUE(provider_event_id) + provider_seq ordering.
- recover() opens the DB read-only (mode=ro): the plan it returns provably
  writes nothing.
- BEFORE remote task IDs exist, recovery only BLOCKS; it never auto-resubmits
  (crash-before-dispatch vs crash-after-accept are indistinguishable locally,
  so both wait for provider records or operator evidence).
"""
import argparse
import json
import os
import sqlite3
import sys

import spend_ledger as L
from functools import partial as _partial

TOOL_NAME = "job_recovery"
TOOL_VERSION = "1.0.0"
_env = _partial(L.envelope, tool=TOOL_NAME)
TERMINAL = ("succeeded", "failed")
PROGRESS = ("accepted", "progress", "in_progress", "pending")


def _open_ro(db_path):
    """Read-only open with schema check. Raises LedgerError like L._open."""
    if not os.path.exists(db_path):
        raise L.LedgerError("NO_DB")
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True,
                               timeout=10, check_same_thread=False)
    except sqlite3.Error as e:
        raise L.CorruptStateError("CORRUPT_STATE: open failed: %s" % e)
    try:
        row = conn.execute("SELECT value FROM schema_info "
                           "WHERE key='schema_version'").fetchone()
    except sqlite3.DatabaseError as e:
        conn.close()
        raise L.CorruptStateError("CORRUPT_STATE: %s" % e)
    except sqlite3.Error as e:
        conn.close()
        raise L.IncompatibleStateError("INCOMPATIBLE_STATE: %s" % e)
    if not row or row[0] not in L.COMPATIBLE:
        conn.close()
        raise L.IncompatibleStateError(
            "INCOMPATIBLE_STATE: schema=%s" % (row[0] if row else None))
    return conn


def _task_id_from(payload):
    if isinstance(payload, dict):
        for k in ("remote_task_id", "task_id", "provider_task_id"):
            if payload.get(k):
                return str(payload[k])
    return ""


def ingest_event(db_path, run_id, logical_key, attempt_id, provider_event_id,
                 provider_seq=0, status="progress", payload=None,
                 artifact_path="", artifact_sha="", artifact_bytes=0):
    """Apply one verified provider event. Idempotent on provider_event_id."""
    payload = payload or {}
    try:
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=True)
    except (TypeError, ValueError):
        return _env("ingest_event", "rejected", "BAD_PAYLOAD",
                          "payload must be JSON-serializable", run_id=run_id,
                          logical_key=logical_key, attempt_id=attempt_id)
    conn = L._open(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        job = L._get_job(conn, logical_key, attempt_id)
        if not job or job[2] != run_id:
            conn.execute("ROLLBACK")
            return _env("ingest_event", "error", "NO_SUCH_JOB",
                              "callbacks never create jobs; unknown "
                              "run/request/task/attempt", run_id=run_id,
                              logical_key=logical_key, attempt_id=attempt_id)
        state, remote, last_seq, ver = job[6], job[8] or "", job[13], job[14]
        if state in ("reconciled",):
            conn.execute("ROLLBACK")
            return _env("ingest_event", "rejected", "ALREADY_RECONCILED",
                              "terminal accounting closed; reconcile, never replay",
                              run_id=run_id, logical_key=logical_key,
                              attempt_id=attempt_id, state_version=ver)
        try:
            conn.execute(
                "INSERT INTO events(run_id,logical_key,attempt_id,kind,"
                "provider_event_id,provider_seq,status,payload_json,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (run_id, logical_key, attempt_id, "provider", provider_event_id,
                 provider_seq, status, payload_json, L._now_iso()))
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK")
            return _env("ingest_event", "ok", "DUPLICATE_EVENT",
                              "event already applied; no state change",
                              run_id=run_id, logical_key=logical_key,
                              attempt_id=attempt_id, state_version=ver)
        if provider_seq <= last_seq:
            conn.execute("COMMIT")
            return _env("ingest_event", "ok", "STALE_SEQ",
                              "older than applied seq %d; recorded, not applied"
                              % last_seq, run_id=run_id, logical_key=logical_key,
                              attempt_id=attempt_id, state_version=ver)
        ev_task = _task_id_from(payload)
        if remote and ev_task and ev_task != remote:
            conn.execute("ROLLBACK")
            return _env("ingest_event", "rejected", "TASK_MISMATCH",
                              "event task %s != recorded %s" % (ev_task, remote),
                              run_id=run_id, logical_key=logical_key,
                              attempt_id=attempt_id, state_version=ver)
        now = L._now_iso()
        if not remote and ev_task:
            remote = ev_task
        new_state, note = state, "recorded"
        if status in TERMINAL:
            if state in ("planned", "reserved", "submitted", "unknown"):
                # Terminal callback proves remote acceptance (covers
                # crash-after-accept-before-persist) and completion at once.
                new_state = status
                note = ("terminal event applied from %s; persist receipt, "
                        "then reconcile" % state)
            else:
                conn.execute("ROLLBACK")
                return _env("ingest_event", "rejected", "BAD_TRANSITION",
                                  "state %s cannot take terminal event" % state,
                                  run_id=run_id, logical_key=logical_key,
                                  attempt_id=attempt_id, state_version=ver)
        elif state == "planned" and remote:
            # Progress with a task ID proves acceptance the DB missed.
            new_state = "submitted"
            note = "acceptance recovered from provider event; polling, not resubmitting"
        elif state == "reserved" and remote:
            new_state = "submitted"
            note = "acceptance recovered from provider event; polling, not resubmitting"
        conn.execute("UPDATE jobs SET state=?,remote_task_id=?,last_seq=?,"
                     "updated_at=?,version=version+1 "
                     "WHERE logical_key=? AND attempt_id=?",
                     (new_state, remote, provider_seq, now,
                      logical_key, attempt_id))
        if artifact_path:
            conn.execute("INSERT OR REPLACE INTO results(run_id,logical_key,"
                         "attempt_id,artifact_path,sha256,bytes_n,created_at)"
                         " VALUES(?,?,?,?,?,?,?)",
                         (run_id, logical_key, attempt_id, artifact_path,
                          artifact_sha, artifact_bytes, now))
        ver = conn.execute("SELECT version FROM jobs WHERE logical_key=? AND "
                           "attempt_id=?", (logical_key, attempt_id)).fetchone()[0]
        conn.execute("COMMIT")
        return _env("ingest_event", "ok", "OK", note, run_id=run_id,
                          logical_key=logical_key, attempt_id=attempt_id,
                          evidence={"state": new_state,
                                    "remote_task_id": remote},
                          state_version=ver)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def record_result(db_path, run_id, logical_key, attempt_id, artifact_path,
                  artifact_sha="", artifact_bytes=0):
    """Persist a downloaded provider result against an existing job."""
    conn = L._open(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        job = L._get_job(conn, logical_key, attempt_id)
        if not job or job[2] != run_id:
            conn.execute("ROLLBACK")
            return _env("record_result", "error", "NO_SUCH_JOB", "",
                              run_id=run_id, logical_key=logical_key,
                              attempt_id=attempt_id)
        conn.execute("INSERT OR REPLACE INTO results(run_id,logical_key,"
                     "attempt_id,artifact_path,sha256,bytes_n,created_at)"
                     " VALUES(?,?,?,?,?,?,?)",
                     (run_id, logical_key, attempt_id, artifact_path,
                      artifact_sha, artifact_bytes, L._now_iso()))
        conn.execute("COMMIT")
        return _env("record_result", "ok", "OK", "", run_id=run_id,
                          logical_key=logical_key, attempt_id=attempt_id,
                          state_version=job[14])
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def recover(db_path, run_id):
    """Read-only recovery plan. Writes nothing (mode=ro); never resubmits."""
    try:
        conn = _open_ro(db_path)
    except L.LedgerError as e:
        return _env("recover", "error", str(e).split(":")[0],
                          "enter verified recovery; spending stopped",
                          run_id=run_id)
    try:
        run = conn.execute("SELECT status,version FROM runs WHERE run_id=?",
                           (run_id,)).fetchone()
        if not run:
            return _env("recover", "error", "NO_SUCH_RUN", "",
                              run_id=run_id)
        plan = []
        for key, att, state, remote, est, seq in conn.execute(
                "SELECT logical_key,attempt_id,state,remote_task_id,"
                "estimated_cost,last_seq FROM jobs WHERE run_id=? AND state IN"
                " ('planned','reserved','submitted','unknown') "
                "ORDER BY logical_key,attempt_no", (run_id,)):
            if not remote:
                # Crash-before-dispatch and crash-after-accept look identical
                # locally: BLOCK, reconcile via provider records or operator.
                plan.append({"logical_key": key, "attempt_id": att,
                             "state": state, "action": "BLOCKED",
                             "reason": "NO_REMOTE_ID",
                             "next": "reconcile via provider records or operator "
                                     "evidence; never auto-resubmit"})
            elif state == "unknown":
                plan.append({"logical_key": key, "attempt_id": att,
                             "state": state, "action": "RECONCILE",
                             "reason": "UNCERTAIN_ACCEPTANCE",
                             "next": "poll task %s or operator evidence; park if "
                                     "undeterminable" % remote})
            else:
                plan.append({"logical_key": key, "attempt_id": att,
                             "state": state, "action": "POLL",
                             "reason": "REMOTE_TRACKED",
                             "next": "poll task %s; polling is distinct from "
                                     "resubmitting" % remote})
        return _env("recover", "ok", "OK",
                          "resume from last incomplete stage; no job re-dispatched",
                          run_id=run_id, evidence={"jobs": plan},
                          state_version=run[1])
    finally:
        conn.close()


def _cli():
    p = argparse.ArgumentParser(prog="job_recovery",
                                description="Job recovery without resubmission")
    p.add_argument("--db", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ingest_event")
    a.add_argument("--run", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--attempt", required=True)
    a.add_argument("--event-id", required=True)
    a.add_argument("--seq", type=int, default=0)
    a.add_argument("--status", default="progress")
    a.add_argument("--payload", default="{}")
    a.add_argument("--artifact", default="")
    a.add_argument("--sha", default="")
    a.add_argument("--bytes", type=int, default=0)

    a = sub.add_parser("record_result")
    a.add_argument("--run", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--attempt", required=True)
    a.add_argument("--artifact", required=True)
    a.add_argument("--sha", default="")
    a.add_argument("--bytes", type=int, default=0)

    a = sub.add_parser("recover")
    a.add_argument("--run", required=True)

    ns = p.parse_args()
    try:
        if ns.cmd == "ingest_event":
            try:
                payload = json.loads(ns.payload)
            except json.JSONDecodeError:
                out = _env("ingest_event", "rejected", "BAD_PAYLOAD",
                           "payload must be JSON", run_id=ns.run,
                           logical_key=ns.key, attempt_id=ns.attempt)
                print(json.dumps(out, indent=2))
                sys.exit(L.EXIT[out["outcome"]])
            out = ingest_event(ns.db, ns.run, ns.key, ns.attempt, ns.event_id,
                               ns.seq, ns.status, payload,
                               ns.artifact, ns.sha, ns.bytes)
        elif ns.cmd == "record_result":
            out = record_result(ns.db, ns.run, ns.key, ns.attempt, ns.artifact,
                                ns.sha, ns.bytes)
        elif ns.cmd == "recover":
            out = recover(ns.db, ns.run)
    except (L.CorruptStateError, L.IncompatibleStateError) as e:
        out = _env(ns.cmd, "error", str(e).split(":")[0],
                         "spending stopped; verified recovery required")
    except L.LedgerError as e:
        out = _env(ns.cmd, "error", str(e), "")
    print(json.dumps(out, indent=2))
    sys.exit(L.EXIT[out["outcome"]])


if __name__ == "__main__":
    _cli()
