#!/usr/bin/env python3
"""Spend ledger: transactional pre-submit reservations, no-double-spend guard.

Directive sections 18 + 24.4. Stdlib only (sqlite3, argparse, json, hashlib,
os, sqlite3, sys, time, datetime). One authoritative per-run SQLite store;
JSON manifests are projections, never authorities.

States: planned -> reserved -> submitted -> succeeded|failed -> reconciled,
with `unknown` retaining the reservation when acceptance is uncertain.
Cancellation preserves receipts (active -> unknown, reconcile later).

Fail-closed rules:
- Corrupt/incompatible DB stops spending, never becomes a fresh empty run
  (Skill 48 lesson: corrupt load() must not yield an empty spendable ledger).
- Unknown prices require a decision before dispatch (estimated_cost=None blocks).
- BEFORE remote task IDs exist, recovery only BLOCKS; never auto-resubmits.
- Double reserve serialized with BEGIN IMMEDIATE + active-key uniqueness.
- Budget violation parks the run instead of continuing.

Money is integer minor units (cents/credits); no floats.
Every command returns the stable JSON envelope; exit codes documented in
EXIT below. Outcomes (ok/waiting/parked/rejected/error) are execution
outcomes, separate from QC verdicts.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

TOOL_NAME = "spend_ledger"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"
COMPATIBLE = {"1.0.0"}

STATES = ("planned", "reserved", "submitted", "unknown",
          "succeeded", "failed", "reconciled")
ACTIVE = ("planned", "reserved", "submitted", "unknown")
EXIT = {"ok": 0, "waiting": 3, "parked": 4, "rejected": 5, "error": 1}

DDL = """
CREATE TABLE IF NOT EXISTS schema_info(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY, ceiling INTEGER NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD', qc_allowance INTEGER NOT NULL DEFAULT 0,
  repair_cap INTEGER NOT NULL DEFAULT 2, status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS jobs(
  logical_key TEXT NOT NULL, attempt_id TEXT NOT NULL,
  run_id TEXT NOT NULL REFERENCES runs(run_id), request_digest TEXT NOT NULL,
  stage TEXT NOT NULL DEFAULT '', attempt_no INTEGER NOT NULL DEFAULT 1,
  state TEXT NOT NULL CHECK(state IN
    ('planned','reserved','submitted','unknown','succeeded','failed','reconciled')),
  final_outcome TEXT, remote_task_id TEXT,
  estimated_cost INTEGER, actual_cost INTEGER,
  owner TEXT NOT NULL DEFAULT '', lease_expires INTEGER NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(logical_key, attempt_id));
CREATE INDEX IF NOT EXISTS idx_jobs_run_state ON jobs(run_id, state);
CREATE INDEX IF NOT EXISTS idx_jobs_digest ON jobs(run_id, request_digest);
CREATE INDEX IF NOT EXISTS idx_jobs_remote ON jobs(run_id, remote_task_id);
CREATE TABLE IF NOT EXISTS receipts(
  receipt_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
  logical_key TEXT NOT NULL, attempt_id TEXT NOT NULL, amount INTEGER NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD', provider_ref TEXT, evidence_ref TEXT,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(
  event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
  logical_key TEXT NOT NULL, attempt_id TEXT NOT NULL, kind TEXT NOT NULL,
  provider_event_id TEXT NOT NULL, provider_seq INTEGER NOT NULL DEFAULT 0,
  status TEXT, payload_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
  UNIQUE(run_id, logical_key, attempt_id, provider_event_id));
CREATE TABLE IF NOT EXISTS results(
  run_id TEXT NOT NULL, logical_key TEXT NOT NULL, attempt_id TEXT NOT NULL,
  artifact_path TEXT NOT NULL, sha256 TEXT, bytes_n INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  PRIMARY KEY(run_id, logical_key, attempt_id));
"""


class LedgerError(Exception):
    """Base; carries machine reason code."""


class CorruptStateError(LedgerError):
    pass


class IncompatibleStateError(LedgerError):
    pass


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest_request(obj):
    """Canonical sha256 of a request payload (persist before dispatch)."""
    canon = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def envelope(command, outcome, reason_code, next_action="", run_id="",
             logical_key="", attempt_id="", evidence=None, state_version=0,
             tool=None):
    return {"schema_version": SCHEMA_VERSION, "tool": tool or TOOL_NAME,
            "tool_version": TOOL_VERSION, "command": command,
            "run_id": run_id, "logical_key": logical_key,
            "attempt_id": attempt_id, "outcome": outcome,
            "reason_code": reason_code, "next_action": next_action,
            "evidence": evidence or {}, "state_version": state_version}


def _open(db_path, create=False):
    """Open verified DB. Never auto-creates over an existing file."""
    exists = os.path.exists(db_path)
    if not exists and not create:
        raise LedgerError("NO_DB")
    try:
        conn = sqlite3.connect(db_path, timeout=10, isolation_level=None,
                               check_same_thread=False)
    except sqlite3.Error as e:
        raise CorruptStateError("CORRUPT_STATE: open failed: %s" % e)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        if not exists and create:
            conn.executescript(DDL)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "INSERT INTO schema_info(key,value) VALUES('schema_version',?)",
                (SCHEMA_VERSION,))
        row = conn.execute(
            "SELECT value FROM schema_info WHERE key='schema_version'").fetchone()
    except sqlite3.DatabaseError as e:
        conn.close()
        raise CorruptStateError("CORRUPT_STATE: %s" % e)
    except sqlite3.Error as e:
        conn.close()
        raise IncompatibleStateError("INCOMPATIBLE_STATE: %s" % e)
    if not row or row[0] not in COMPATIBLE:
        conn.close()
        raise IncompatibleStateError(
            "INCOMPATIBLE_STATE: schema=%s" % (row[0] if row else None))
    return conn


def init_run(db_path, run_id, ceiling, currency="USD", qc_allowance=0,
             repair_cap=2):
    """Create DB/run. Idempotent for identical params; never wipes existing."""
    if ceiling is None or ceiling < 0:
        return envelope("init_run", "rejected", "NO_CEILING",
                        "record a ceiling before any paid submission",
                        run_id=run_id)
    conn = _open(db_path, create=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT ceiling,currency,status,version FROM runs WHERE run_id=?",
            (run_id,)).fetchone()
        if row:
            conn.execute("COMMIT")
            same = (row[0] == ceiling and row[1] == currency)
            return envelope(
                "init_run", "ok" if same else "rejected",
                "OK" if same else "CEILING_MISMATCH",
                "" if same else "run exists with different ceiling",
                run_id=run_id, state_version=row[3])
        now = _now_iso()
        conn.execute(
            "INSERT INTO runs(run_id,ceiling,currency,qc_allowance,repair_cap,"
            "status,created_at,updated_at,version) VALUES(?,?,?,?,?,'active',?,?,1)",
            (run_id, ceiling, currency, qc_allowance, repair_cap, now, now))
        conn.execute("COMMIT")
        return envelope("init_run", "ok", "OK", "", run_id=run_id,
                        state_version=1)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def _get_run(conn, run_id):
    return conn.execute(
        "SELECT run_id,ceiling,currency,qc_allowance,repair_cap,status,version"
        " FROM runs WHERE run_id=?", (run_id,)).fetchone()


def _get_job(conn, logical_key, attempt_id):
    return conn.execute(
        "SELECT logical_key,attempt_id,run_id,request_digest,stage,attempt_no,"
        "state,final_outcome,remote_task_id,estimated_cost,actual_cost,owner,"
        "lease_expires,last_seq,version FROM jobs "
        "WHERE logical_key=? AND attempt_id=?",
        (logical_key, attempt_id)).fetchone()


def _active_for_key(conn, run_id, logical_key):
    q = ("SELECT attempt_id,state FROM jobs WHERE run_id=? AND logical_key=?"
         " AND state IN ('planned','reserved','submitted','unknown')")
    return conn.execute(q, (run_id, logical_key)).fetchall()


def _totals(conn, run_id):
    """(committed, unknown_sum, actual, calls, retry_cost, by_stage)."""
    committed, unknown, actual, calls, retry = 0, 0, 0, 0, 0
    by_stage = {}
    for st, est, act, ano, stage, rid in conn.execute(
            "SELECT state,estimated_cost,actual_cost,attempt_no,stage,"
            "remote_task_id FROM jobs WHERE run_id=?", (run_id,)):
        if st in ("reserved", "submitted"):
            committed += est or 0
        if st == "unknown":
            unknown += est or 0
        if st == "reconciled" and act:
            actual += act
            by_stage[stage or ""] = by_stage.get(stage or "", 0) + act
            if ano and ano > 1:
                retry += act
        if rid:
            calls += 1
    return committed, unknown, actual, calls, retry, by_stage


def summary(db_path, run_id):
    """Directive 18 cost ledger read model. Read-only; never spends."""
    try:
        conn = _open(db_path)
    except LedgerError as e:
        return envelope("summary", "error", str(e).split(":")[0],
                        "enter verified recovery; spending stopped",
                        run_id=run_id)
    try:
        run = _get_run(conn, run_id)
        if not run:
            return envelope("summary", "error", "NO_SUCH_RUN", "", run_id=run_id)
        _, ceiling, ccy, qc, _, status, ver = run
        committed, unknown, actual, calls, retry, by_stage = _totals(conn, run_id)
        active_est = sum(
            r[0] or 0 for r in conn.execute(
                "SELECT estimated_cost FROM jobs WHERE run_id=? AND state IN"
                " ('planned','reserved','submitted','unknown')", (run_id,)))
        ev = {"estimated_cost": active_est, "committed_cost": committed,
              "actual_cost": actual, "unknown_or_reserved_cost": unknown,
              "qc_and_repair_allowance": qc,
              "provider_cost_by_stage": by_stage,
              "number_of_generation_calls": calls, "retry_cost": retry,
              "remaining_budget": ceiling - (actual + committed + unknown + qc),
              "run_status": status, "currency": ccy}
        return envelope("summary", "ok", "OK", "", run_id=run_id, evidence=ev,
                        state_version=ver)
    finally:
        conn.close()


def can_spend(db_path, run_id, estimated_cost):
    """Pre-dispatch gate. False on corrupt/parked/no-ceiling/unknown-price."""
    if estimated_cost is None:
        return envelope("can_spend", "rejected", "UNKNOWN_PRICE",
                        "unknown prices require a decision before dispatch",
                        run_id=run_id)
    s = summary(db_path, run_id)
    if s["outcome"] == "error":
        code = s["reason_code"]
        note = ("spending stopped; verified recovery required"
                if code in ("CORRUPT_STATE", "INCOMPATIBLE_STATE")
                else "unknown run; plan against a recorded run")
        return envelope("can_spend", "rejected", code, note,
                        run_id=run_id)
    if s["evidence"]["run_status"] != "active":
        return envelope("can_spend", "rejected", "RUN_PARKED",
                        "run parked; reconcile or operator unpark",
                        run_id=run_id)
    if estimated_cost > s["evidence"]["remaining_budget"]:
        return envelope("can_spend", "rejected", "BUDGET_EXCEEDED",
                        "budget violation parks the run instead of continuing",
                        run_id=run_id)
    return envelope("can_spend", "ok", "OK", "", run_id=run_id,
                    evidence=s["evidence"],
                    state_version=s["state_version"])


def _park_locked(conn, run_id, reason):
    now = _now_iso()
    conn.execute("UPDATE runs SET status='parked',updated_at=?,version=version+1"
                 " WHERE run_id=?", (now, run_id))
    return reason


def plan(db_path, run_id, logical_key, attempt_id, request_digest,
         estimated_cost=None, stage="", attempt_no=1, owner="cli"):
    """Record a planned job: digest + logical key + attempt persisted first."""
    if not request_digest:
        return envelope("plan", "rejected", "MISSING_DIGEST",
                        "persist the request digest before dispatch",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    conn = _open(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = _get_run(conn, run_id)
        if not run:
            conn.execute("ROLLBACK")
            return envelope("plan", "error", "NO_SUCH_RUN", "",
                            run_id=run_id)
        if run[5] != "active":
            conn.execute("ROLLBACK")
            return envelope("plan", "rejected", "RUN_PARKED",
                            "reconcile or operator unpark", run_id=run_id,
                            logical_key=logical_key, attempt_id=attempt_id,
                            state_version=run[6])
        if _get_job(conn, logical_key, attempt_id):
            conn.execute("ROLLBACK")
            return envelope("plan", "rejected", "DUPLICATE_ATTEMPT",
                            "attempt ID already exists; use a new attempt ID",
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id)
        act = _active_for_key(conn, run_id, logical_key)
        if act:
            conn.execute("ROLLBACK")
            return envelope(
                "plan", "rejected", "DUPLICATE_LOGICAL_JOB",
                "logical job already active as %s; poll it, never resubmit"
                % act[0][0], run_id=run_id, logical_key=logical_key,
                attempt_id=attempt_id, state_version=run[6])
        if attempt_no > 1:
            prior = conn.execute(
                "SELECT state,final_outcome FROM jobs WHERE run_id=? AND "
                "logical_key=? ORDER BY attempt_no DESC LIMIT 1",
                (run_id, logical_key)).fetchone()
            ok_retry = prior and (prior[0] == "failed" or (
                prior[0] == "reconciled" and prior[1] == "failed"))
            if not ok_retry:
                conn.execute("ROLLBACK")
                return envelope(
                    "plan", "rejected", "RETRY_NOT_FAILED",
                    "retry only known failed artifacts; prior attempt not failed",
                    run_id=run_id, logical_key=logical_key,
                    attempt_id=attempt_id, state_version=run[6])
            if attempt_no - 1 > run[4]:
                conn.execute("ROLLBACK")
                return envelope("plan", "rejected", "REPAIR_CAP",
                                "retry count exceeds approved repair cap",
                                run_id=run_id, logical_key=logical_key,
                                attempt_id=attempt_id, state_version=run[6])
        now = _now_iso()
        conn.execute(
            "INSERT INTO jobs(logical_key,attempt_id,run_id,request_digest,stage,"
            "attempt_no,state,estimated_cost,owner,lease_expires,created_at,"
            "updated_at,version) VALUES(?,?,?,?,?,?,'planned',?,?,0,?,?,1)",
            (logical_key, attempt_id, run_id, request_digest, stage,
             attempt_no, estimated_cost, owner, now, now))
        conn.execute("COMMIT")
        return envelope("plan", "ok", "OK", "reserve before dispatch",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id, state_version=1)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def _mutate(db_path, cmd, run_id, logical_key, attempt_id, owner,
            expected_version, allowed, new_state, next_action, **sets):
    """Generic guarded transition: lease + expected-version + allowed-from."""
    conn = _open(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = _get_run(conn, run_id)
        if not run:
            conn.execute("ROLLBACK")
            return envelope(cmd, "error", "NO_SUCH_RUN", "", run_id=run_id)
        if run[5] != "active" and cmd != "unpark":
            conn.execute("ROLLBACK")
            return envelope(cmd, "rejected", "RUN_PARKED",
                            "reconcile or operator unpark", run_id=run_id,
                            logical_key=logical_key, attempt_id=attempt_id,
                            state_version=run[6])
        job = _get_job(conn, logical_key, attempt_id)
        if not job:
            conn.execute("ROLLBACK")
            return envelope(cmd, "error", "NO_SUCH_JOB",
                            "unknown run/request/task/attempt", run_id=run_id,
                            logical_key=logical_key, attempt_id=attempt_id)
        now_s, me = int(time.time()), owner or ""
        if job[11] and job[11] != me and job[12] > now_s:
            conn.execute("ROLLBACK")
            return envelope(cmd, "waiting", "LEASE_HELD",
                            "owner %s holds lease; stale worker must not overwrite"
                            % job[11], run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id, state_version=job[14])
        if expected_version and expected_version != job[14]:
            conn.execute("ROLLBACK")
            return envelope(cmd, "rejected", "STALE_VERSION",
                            "reread current version %d" % job[14],
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id, state_version=job[14])
        if job[6] not in allowed:
            conn.execute("ROLLBACK")
            return envelope(cmd, "rejected", "BAD_TRANSITION",
                            "state %s cannot %s" % (job[6], cmd),
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id, state_version=job[14])
        assigns = ["state=?", "updated_at=?", "version=version+1",
                   "owner=?", "lease_expires=?"]
        vals = [new_state, _now_iso(), me, now_s + 300]
        for k, v in sets.items():
            assigns.append("%s=?" % k)
            vals.append(v)
        vals.extend([logical_key, attempt_id])
        conn.execute("UPDATE jobs SET %s WHERE logical_key=? AND attempt_id=?"
                     % ",".join(assigns), vals)
        ver = conn.execute(
            "SELECT version FROM jobs WHERE logical_key=? AND attempt_id=?",
            (logical_key, attempt_id)).fetchone()[0]
        conn.execute("COMMIT")
        return envelope(cmd, "ok", "OK", next_action, run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id,
                        state_version=ver)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def reserve(db_path, run_id, logical_key, attempt_id, owner="cli",
            expected_version=0, lease_seconds=300):
    """planned -> reserved. Enforces ceiling; parks run on violation."""
    gate = can_spend(
        db_path, run_id,
        (_get_est(db_path, run_id, logical_key, attempt_id)))
    if gate["outcome"] == "rejected" and gate["reason_code"] in (
            "BUDGET_EXCEEDED", "UNKNOWN_PRICE"):
        conn = _open(db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            _park_locked(conn, run_id, gate["reason_code"])
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()
        gate["outcome"] = "parked"
        return gate
    if gate["outcome"] == "rejected":
        return gate
    out = _mutate(db_path, "reserve", run_id, logical_key, attempt_id, owner,
                  expected_version, ("planned",), "reserved",
                  "dispatch only against this reservation")
    return out


def _get_est(db_path, run_id, logical_key, attempt_id):
    try:
        conn = _open(db_path)
    except LedgerError:
        return 0
    try:
        r = conn.execute("SELECT estimated_cost FROM jobs WHERE logical_key=?"
                         " AND attempt_id=?", (logical_key, attempt_id)).fetchone()
        return r[0] if r else 0
    finally:
        conn.close()


def mark_submitted(db_path, run_id, logical_key, attempt_id, remote_task_id,
                   owner="cli", expected_version=0):
    """reserved -> submitted. Remote task ID persisted immediately."""
    if not remote_task_id:
        return envelope("mark_submitted", "rejected", "MISSING_REMOTE_ID",
                        "persist remote task IDs immediately when available",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    return _mutate(db_path, "mark_submitted", run_id, logical_key, attempt_id,
                   owner, expected_version, ("reserved",), "submitted",
                   "poll this job; polling is distinct from resubmitting",
                   remote_task_id=remote_task_id)


def mark_unknown(db_path, run_id, logical_key, attempt_id, owner="cli",
                 expected_version=0):
    """reserved|submitted -> unknown. Retains reservation; never resubmits."""
    return _mutate(db_path, "mark_unknown", run_id, logical_key, attempt_id,
                   owner, expected_version, ("reserved", "submitted"),
                   "unknown",
                   "reconcile via provider records or operator evidence; "
                   "do not auto-resubmit; park if undeterminable")


def mark_terminal(db_path, run_id, logical_key, attempt_id, outcome,
                  owner="cli", expected_version=0):
    """submitted|unknown -> succeeded|failed. Requires remote acceptance first."""
    if outcome not in ("succeeded", "failed"):
        return envelope("mark_terminal", "rejected", "BAD_OUTCOME",
                        "outcome is succeeded or failed", run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id)
    return _mutate(db_path, "mark_terminal", run_id, logical_key, attempt_id,
                   owner, expected_version, ("submitted", "unknown"), outcome,
                   "persist receipt then reconcile")


def reconcile(db_path, run_id, logical_key, attempt_id, final_outcome,
              actual_cost, provider_ref="", evidence_ref="", owner="cli",
              expected_version=0):
    """succeeded|failed|unknown -> reconciled. Receipt written first, same txn."""
    if final_outcome not in ("succeeded", "failed"):
        return envelope("reconcile", "rejected", "BAD_OUTCOME", "",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    if actual_cost is None:
        return envelope("reconcile", "rejected", "UNKNOWN_PRICE",
                        "actual charge unknown; park until determined",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    conn = _open(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = _get_run(conn, run_id)
        if not run:
            conn.execute("ROLLBACK")
            return envelope("reconcile", "error", "NO_SUCH_RUN", "",
                            run_id=run_id)
        job = _get_job(conn, logical_key, attempt_id)
        if not job:
            conn.execute("ROLLBACK")
            return envelope("reconcile", "error", "NO_SUCH_JOB", "",
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id)
        if job[6] not in ("succeeded", "failed", "unknown"):
            conn.execute("ROLLBACK")
            return envelope("reconcile", "rejected", "BAD_TRANSITION",
                            "state %s cannot reconcile" % job[6],
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id, state_version=job[14])
        if expected_version and expected_version != job[14]:
            conn.execute("ROLLBACK")
            return envelope("reconcile", "rejected", "STALE_VERSION",
                            "reread current version %d" % job[14],
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id, state_version=job[14])
        now = _now_iso()
        conn.execute(
            "INSERT INTO receipts(run_id,logical_key,attempt_id,amount,currency,"
            "provider_ref,evidence_ref,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (run_id, logical_key, attempt_id, actual_cost, run[2],
             provider_ref, evidence_ref, now))
        conn.execute(
            "UPDATE jobs SET state='reconciled',final_outcome=?,actual_cost=?,"
            "updated_at=?,version=version+1,owner=? WHERE logical_key=? AND "
            "attempt_id=?", (final_outcome, actual_cost, now, owner or "",
                             logical_key, attempt_id))
        ver = conn.execute(
            "SELECT version FROM jobs WHERE logical_key=? AND attempt_id=?",
            (logical_key, attempt_id)).fetchone()[0]
        conn.execute("COMMIT")
        s = summary(db_path, run_id)
        if s["evidence"].get("remaining_budget", 0) < 0:
            c2 = _open(db_path)
            try:
                c2.execute("BEGIN IMMEDIATE")
                _park_locked(c2, run_id, "BUDGET_EXCEEDED")
                c2.execute("COMMIT")
            finally:
                c2.close()
            return envelope("reconcile", "parked", "BUDGET_EXCEEDED",
                            "settled charges exceeded ceiling; run parked",
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id, state_version=ver)
        return envelope("reconcile", "ok", "OK", "", run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id,
                        state_version=ver)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def cancel(db_path, run_id, logical_key, attempt_id, owner="cli",
           expected_version=0):
    """Active -> unknown. Preserves receipts; remote work reconciled later."""
    job_state = None
    try:
        conn = _open(db_path)
        try:
            r = conn.execute("SELECT state FROM jobs WHERE logical_key=? AND "
                             "attempt_id=?", (logical_key, attempt_id)).fetchone()
            job_state = r[0] if r else None
        finally:
            conn.close()
    except LedgerError as e:
        return envelope("cancel", "error", str(e).split(":")[0], "",
                        run_id=run_id)
    if job_state in ("succeeded", "failed", "reconciled"):
        return envelope("cancel", "rejected", "BAD_TRANSITION",
                        "terminal job %s keeps its receipts" % job_state,
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    if job_state == "unknown":
        return envelope("cancel", "ok", "ALREADY_UNKNOWN",
                        "already in cancel-safe state; reconcile remote work",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    return _mutate(db_path, "cancel", run_id, logical_key, attempt_id, owner,
                   expected_version, ("planned", "reserved", "submitted"),
                   "unknown",
                   "cancellation preserved receipts; reconcile remote work")


def park_run(db_path, run_id, reason="OPERATOR_PARK"):
    conn = _open(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _park_locked(conn, run_id, reason)
        conn.execute("COMMIT")
        return envelope("park_run", "parked", reason,
                        "resume from last incomplete stage", run_id=run_id)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def unpark(db_path, run_id):
    conn = _open(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = _get_run(conn, run_id)
        if not run:
            conn.execute("ROLLBACK")
            return envelope("unpark", "error", "NO_SUCH_RUN", "",
                            run_id=run_id)
        now = _now_iso()
        conn.execute("UPDATE runs SET status='active',updated_at=?,"
                     "version=version+1 WHERE run_id=?", (now, run_id))
        conn.execute("COMMIT")
        return envelope("unpark", "ok", "OK", "", run_id=run_id,
                        state_version=run[6] + 1)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def _cli():
    p = argparse.ArgumentParser(prog="spend_ledger",
                                description="Transactional spend ledger")
    p.add_argument("--db", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("init_run")
    a.add_argument("--run", required=True)
    a.add_argument("--ceiling", type=int, required=True)
    a.add_argument("--currency", default="USD")
    a.add_argument("--qc-allowance", type=int, default=0)
    a.add_argument("--repair-cap", type=int, default=2)

    a = sub.add_parser("plan")
    a.add_argument("--run", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--attempt", required=True)
    a.add_argument("--digest", required=True)
    a.add_argument("--est", type=int, default=None)
    a.add_argument("--stage", default="")
    a.add_argument("--attempt-no", type=int, default=1)
    a.add_argument("--owner", default="cli")

    for name in ("reserve", "mark_unknown", "cancel"):
        a = sub.add_parser(name)
        a.add_argument("--run", required=True)
        a.add_argument("--key", required=True)
        a.add_argument("--attempt", required=True)
        a.add_argument("--owner", default="cli")
        a.add_argument("--expected-version", type=int, default=0)

    a = sub.add_parser("mark_submitted")
    a.add_argument("--run", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--attempt", required=True)
    a.add_argument("--remote-id", required=True)
    a.add_argument("--owner", default="cli")
    a.add_argument("--expected-version", type=int, default=0)

    a = sub.add_parser("mark_terminal")
    a.add_argument("--run", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--attempt", required=True)
    a.add_argument("--outcome", choices=("succeeded", "failed"), required=True)
    a.add_argument("--owner", default="cli")
    a.add_argument("--expected-version", type=int, default=0)

    a = sub.add_parser("reconcile")
    a.add_argument("--run", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--attempt", required=True)
    a.add_argument("--final", choices=("succeeded", "failed"), required=True)
    a.add_argument("--actual", type=int, required=True)
    a.add_argument("--provider-ref", default="")
    a.add_argument("--evidence-ref", default="")
    a.add_argument("--owner", default="cli")
    a.add_argument("--expected-version", type=int, default=0)

    a = sub.add_parser("summary")
    a.add_argument("--run", required=True)

    a = sub.add_parser("can_spend")
    a.add_argument("--run", required=True)
    a.add_argument("--est", type=int, default=None)

    a = sub.add_parser("park_run")
    a.add_argument("--run", required=True)
    a.add_argument("--reason", default="OPERATOR_PARK")

    a = sub.add_parser("unpark")
    a.add_argument("--run", required=True)

    ns = p.parse_args()
    try:
        if ns.cmd == "init_run":
            out = init_run(ns.db, ns.run, ns.ceiling, ns.currency,
                           ns.qc_allowance, ns.repair_cap)
        elif ns.cmd == "plan":
            out = plan(ns.db, ns.run, ns.key, ns.attempt, ns.digest, ns.est,
                       ns.stage, ns.attempt_no, ns.owner)
        elif ns.cmd == "reserve":
            out = reserve(ns.db, ns.run, ns.key, ns.attempt, ns.owner,
                          ns.expected_version)
        elif ns.cmd == "mark_submitted":
            out = mark_submitted(ns.db, ns.run, ns.key, ns.attempt,
                                 ns.remote_id, ns.owner, ns.expected_version)
        elif ns.cmd == "mark_unknown":
            out = mark_unknown(ns.db, ns.run, ns.key, ns.attempt, ns.owner,
                               ns.expected_version)
        elif ns.cmd == "cancel":
            out = cancel(ns.db, ns.run, ns.key, ns.attempt, ns.owner,
                         ns.expected_version)
        elif ns.cmd == "mark_terminal":
            out = mark_terminal(ns.db, ns.run, ns.key, ns.attempt, ns.outcome,
                                ns.owner, ns.expected_version)
        elif ns.cmd == "reconcile":
            out = reconcile(ns.db, ns.run, ns.key, ns.attempt, ns.final,
                            ns.actual, ns.provider_ref, ns.evidence_ref,
                            ns.owner, ns.expected_version)
        elif ns.cmd == "summary":
            out = summary(ns.db, ns.run)
        elif ns.cmd == "can_spend":
            out = can_spend(ns.db, ns.run, ns.est)
        elif ns.cmd == "park_run":
            out = park_run(ns.db, ns.run, ns.reason)
        elif ns.cmd == "unpark":
            out = unpark(ns.db, ns.run)
    except (CorruptStateError, IncompatibleStateError) as e:
        out = envelope(ns.cmd, "error", str(e).split(":")[0],
                       "spending stopped; verified recovery required")
    except LedgerError as e:
        out = envelope(ns.cmd, "error", str(e), "")
    print(json.dumps(out, indent=2))
    sys.exit(EXIT[out["outcome"]])


if __name__ == "__main__":
    _cli()
