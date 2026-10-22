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

Paid-attempt identity (directive 8.4, findings D20/D21):
- The LEDGER owns attempt allocation. plan()/allocate_attempt() mint the new
  attempt identity, the monotonically increasing ordinal, and record the
  request digest, retry category and authorization reference in ONE
  transaction that also enforces prior-state and allowance (repair cap)
  checks. The ordinal is derived from persisted history inside that
  transaction; a caller can never bypass the cap by omitting an ordinal or
  passing 1 again. No MAX()+1 outside the transaction, no string-suffix
  identities, and no exception handler that silently falls back to "a1".
- Retry categories are derived from authoritative persisted state:
  `transport_retry` (resubmission of one uncertain submission, after the
  provider lookup that reconciled it), `failed_job_retry` (a confirmed
  failed job), `creative_retake` (new creative take after a SUCCESSFUL
  provider generation; needs its own authorization reference and consumes
  the repair allowance). A provider success that fails creative QC remains
  a successful provider result: record_qc_verdict never flips it.
- An attempt that was ever `unknown` must be reconciled, with provider
  lookup evidence recorded, before ANY resubmission.

Money units and conversion contract (directive 8.4):
- estimated_cost/actual_cost are INTEGER currency subunits (e.g. USD cents).
  est/actual_credits_micro are INTEGER micro-credits (1 credit =
  1_000_000 micro-credits), so fractional provider usage is preserved
  exactly. Floats are refused at the boundary (BAD_MONEY).
- credit_to_subunit_num/den on the run is the explicit rational conversion
  contract (subunits per credit): subunits = floor(micro * num / (1e6*den)),
  and the exact fractional residue is returned, never lost.
- Estimates remain estimates. An unreported actual charge stays in the
  reserved-unknown bucket pending reconciliation; it never becomes an
  asserted actual charge and never vanishes from the allowance math.

Counts derive from persisted rows and acknowledged provider jobs, never
folder counts or returned track counts: billable jobs, provider tracks,
saved artifacts and selected artifacts are reported as distinct numbers.

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
TOOL_VERSION = "1.1.0"
SCHEMA_VERSION = "1.1.0"
COMPATIBLE = {"1.0.0", "1.1.0"}

MICRO_PER_CREDIT = 1000000  # provider credits -> micro-credits (exact integers)

RETRY_CATEGORIES = ("initial", "transport_retry", "failed_job_retry",
                    "creative_retake")
OUTCOME_CLASSES = ("", "rejected_before_submit", "accepted_response_lost",
                   "generated_download_failed", "saved_measurement_failed",
                   "accepted_delivered")

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
  credit_to_subunit_num INTEGER NOT NULL DEFAULT 1,
  credit_to_subunit_den INTEGER NOT NULL DEFAULT 1,
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
  retry_category TEXT NOT NULL DEFAULT '',
  auth_ref TEXT NOT NULL DEFAULT '',
  uncertain INTEGER NOT NULL DEFAULT 0,
  provider_lookup_ref TEXT NOT NULL DEFAULT '',
  outcome_class TEXT NOT NULL DEFAULT '',
  est_credits_micro INTEGER, actual_credits_micro INTEGER,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(logical_key, attempt_id));
CREATE INDEX IF NOT EXISTS idx_jobs_run_state ON jobs(run_id, state);
CREATE INDEX IF NOT EXISTS idx_jobs_digest ON jobs(run_id, request_digest);
CREATE INDEX IF NOT EXISTS idx_jobs_remote ON jobs(run_id, remote_task_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_auth ON jobs(run_id, auth_ref)
  WHERE auth_ref <> '';
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
CREATE TABLE IF NOT EXISTS provider_jobs(
  run_id TEXT NOT NULL, remote_task_id TEXT NOT NULL,
  logical_key TEXT NOT NULL, attempt_id TEXT NOT NULL,
  billable INTEGER NOT NULL DEFAULT 1, credits_micro INTEGER,
  created_at TEXT NOT NULL,
  PRIMARY KEY(run_id, remote_task_id),
  UNIQUE(run_id, logical_key, attempt_id));
CREATE TABLE IF NOT EXISTS tracks(
  run_id TEXT NOT NULL, logical_key TEXT NOT NULL, attempt_id TEXT NOT NULL,
  track_no INTEGER NOT NULL, artifact_path TEXT NOT NULL DEFAULT '',
  sha256 TEXT NOT NULL DEFAULT '', bytes_n INTEGER NOT NULL DEFAULT 0,
  saved INTEGER NOT NULL DEFAULT 0, selected INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  PRIMARY KEY(run_id, logical_key, attempt_id, track_no));
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


def _money_int(name, value):
    """Ledger amounts are exact integers. Floats are refused at the boundary;
    fractional provider usage is expressed in micro-credits instead."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerError(
            "BAD_MONEY: %s must be an integer minor-unit count (use "
            "micro-credits for fractional provider usage)" % name)
    return value


def credits_to_subunits(credits_micro, num, den):
    """Explicit credits -> currency-subunit conversion contract.

    subunits = floor(micro * num / (MICRO_PER_CREDIT * den)); the exact
    fractional residue is returned alongside so fractional usage is never
    lost. (subunits * MICRO_PER_CREDIT * den) + residue == micro * num.
    """
    if isinstance(credits_micro, bool) or not isinstance(credits_micro, int):
        raise LedgerError("BAD_MONEY: credits_micro must be an integer count "
                          "of micro-credits")
    if (isinstance(num, bool) or not isinstance(num, int)
            or isinstance(den, bool) or not isinstance(den, int)
            or num <= 0 or den <= 0):
        raise LedgerError("BAD_CONVERSION_CONTRACT: subunits-per-credit must "
                          "be a positive integer ratio num/den")
    total = credits_micro * num
    per = MICRO_PER_CREDIT * den
    return total // per, total - (total // per) * per


def _mint_attempt_id(run_id, logical_key, ordinal, request_digest,
                     retry_category, auth_ref):
    """Ledger-owned attempt identity: content-derived and ordinal-bound, never
    a string suffix of a prior attempt, never re-minted silently on error."""
    canon = "|".join((run_id, logical_key, str(ordinal), request_digest or "",
                      retry_category or "", auth_ref or ""))
    return "att-%04d-%s" % (
        ordinal, hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12])


def _derive_category(prior, request_digest):
    """Retry category from authoritative persisted state, never caller claims.

    Returns (category, refusal) where refusal is (reason_code, next_action)
    when no new attempt is legitimate.
    """
    if not prior:
        return "initial", None
    terminal = [r for r in prior
                if r[1] in ("succeeded", "failed", "reconciled")]
    if not terminal:
        return None, ("DUPLICATE_LOGICAL_JOB",
                      "an attempt is still in flight; poll it, never resubmit")
    last = terminal[-1]  # rows arrive ordered by attempt_no
    state, final = last[1], last[2]
    if state == "succeeded" or (state == "reconciled" and final == "succeeded"):
        return "creative_retake", None
    # Confirmed-failed path: same uncertain submission is a transport retry.
    if last[3] and last[4] == request_digest:
        return "transport_retry", None
    return "failed_job_retry", None


def _lookup_evidence(conn, run_id, logical_key, attempt_id):
    """True when a provider lookup (or operator evidence receipt) is recorded
    for the attempt that must be reconciled before any resubmission."""
    row = conn.execute(
        "SELECT provider_lookup_ref FROM jobs WHERE logical_key=? AND "
        "attempt_id=?", (logical_key, attempt_id)).fetchone()
    if row and row[0]:
        return True
    rec = conn.execute(
        "SELECT 1 FROM receipts WHERE run_id=? AND logical_key=? AND "
        "attempt_id=? AND (COALESCE(provider_ref,'')<>'' OR "
        "COALESCE(evidence_ref,'')<>'') LIMIT 1",
        (run_id, logical_key, attempt_id)).fetchone()
    return rec is not None


def envelope(command, outcome, reason_code, next_action="", run_id="",
             logical_key="", attempt_id="", evidence=None, state_version=0,
             tool=None):
    return {"schema_version": SCHEMA_VERSION, "tool": tool or TOOL_NAME,
            "tool_version": TOOL_VERSION, "command": command,
            "run_id": run_id, "logical_key": logical_key,
            "attempt_id": attempt_id, "outcome": outcome,
            "reason_code": reason_code, "next_action": next_action,
            "evidence": evidence or {}, "state_version": state_version}


def _migrate_100(conn):
    """1.0.0 -> 1.1.0: additive only. Existing rows are never rewritten."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    for col, decl in (
            ("retry_category", "TEXT NOT NULL DEFAULT ''"),
            ("auth_ref", "TEXT NOT NULL DEFAULT ''"),
            ("uncertain", "INTEGER NOT NULL DEFAULT 0"),
            ("provider_lookup_ref", "TEXT NOT NULL DEFAULT ''"),
            ("outcome_class", "TEXT NOT NULL DEFAULT ''"),
            ("est_credits_micro", "INTEGER"),
            ("actual_credits_micro", "INTEGER")):
        if col not in have:
            conn.execute("ALTER TABLE jobs ADD COLUMN %s %s" % (col, decl))
    have = {r[1] for r in conn.execute("PRAGMA table_info(runs)")}
    for col, decl in (("credit_to_subunit_num", "INTEGER NOT NULL DEFAULT 1"),
                      ("credit_to_subunit_den", "INTEGER NOT NULL DEFAULT 1")):
        if col not in have:
            conn.execute("ALTER TABLE runs ADD COLUMN %s %s" % (col, decl))
    conn.executescript(DDL)  # every object is CREATE IF NOT EXISTS
    conn.execute("UPDATE schema_info SET value=? WHERE key='schema_version'",
                 (SCHEMA_VERSION,))


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
        if row and row[0] == "1.0.0":
            _migrate_100(conn)
            row = (SCHEMA_VERSION,)
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
             repair_cap=2, credit_to_subunit_num=1, credit_to_subunit_den=1):
    """Create DB/run. Idempotent for identical params; never wipes existing.

    credit_to_subunit_num/den records the explicit money conversion contract
    (currency subunits per one provider credit, as an exact integer ratio).
    """
    if ceiling is None or ceiling < 0:
        return envelope("init_run", "rejected", "NO_CEILING",
                        "record a ceiling before any paid submission",
                        run_id=run_id)
    try:
        _money_int("ceiling", ceiling)
        _money_int("qc_allowance", qc_allowance)
        if (isinstance(credit_to_subunit_num, bool)
                or not isinstance(credit_to_subunit_num, int)
                or isinstance(credit_to_subunit_den, bool)
                or not isinstance(credit_to_subunit_den, int)
                or credit_to_subunit_num <= 0 or credit_to_subunit_den <= 0):
            raise LedgerError("BAD_CONVERSION_CONTRACT: subunits-per-credit "
                              "must be a positive integer ratio num/den")
    except LedgerError as e:
        return envelope("init_run", "rejected", str(e).split(":")[0],
                        "record integer minor units and an integer "
                        "num/den conversion contract", run_id=run_id)
    conn = _open(db_path, create=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT ceiling,currency,status,version,credit_to_subunit_num,"
            "credit_to_subunit_den FROM runs WHERE run_id=?",
            (run_id,)).fetchone()
        if row:
            conn.execute("COMMIT")
            same = (row[0] == ceiling and row[1] == currency
                    and row[4] == credit_to_subunit_num
                    and row[5] == credit_to_subunit_den)
            return envelope(
                "init_run", "ok" if same else "rejected",
                "OK" if same else "CEILING_MISMATCH",
                "" if same else "run exists with different ceiling/currency"
                "/money contract", run_id=run_id, state_version=row[3])
        now = _now_iso()
        conn.execute(
            "INSERT INTO runs(run_id,ceiling,currency,qc_allowance,repair_cap,"
            "status,credit_to_subunit_num,credit_to_subunit_den,created_at,"
            "updated_at,version) VALUES(?,?,?,?,?,'active',?,?,?,?,1)",
            (run_id, ceiling, currency, qc_allowance, repair_cap,
             credit_to_subunit_num, credit_to_subunit_den, now, now))
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


def _totals(conn, run_id):
    """(committed, unknown_sum, actual, calls, retry_cost, by_stage, extra).

    Unit contract: estimated_cost/actual_cost are integer currency subunits;
    est/actual_credits_micro are integer micro-credits (fractional provider
    usage preserved exactly). Estimates never become actuals: a job whose
    actual charge is unreported (NULL) stays in the reserved-unknown bucket
    pending reconciliation and keeps counting against the allowance.
    """
    committed, unknown, actual, calls, retry = 0, 0, 0, 0, 0
    c_committed, c_unknown, c_actual, c_retry = 0, 0, 0, 0
    by_stage, by_class, repairs = {}, {}, 0
    for st, est, act, ano, stage, rid, estc, actc, oclass in conn.execute(
            "SELECT state,estimated_cost,actual_cost,attempt_no,stage,"
            "remote_task_id,est_credits_micro,actual_credits_micro,"
            "outcome_class FROM jobs WHERE run_id=?", (run_id,)):
        if st in ("reserved", "submitted"):
            committed += est or 0
            c_committed += estc or 0
        elif st == "planned":
            pass  # reserved nothing yet; surfaced as estimated_cost only
        elif st == "unknown" or act is None:
            # unknown submissions AND any unreported actual charge (including
            # succeeded/failed awaiting reconcile) remain reserved-unknown.
            unknown += est or 0
            c_unknown += estc or 0
        else:
            actual += act
            c_actual += actc or 0
            by_stage[stage or ""] = by_stage.get(stage or "", 0) + act
            if ano and ano > 1:
                retry += act
                c_retry += actc or 0
        if ano and ano > 1:
            repairs += 1
        by_class[oclass or "unclassified"] = by_class.get(
            oclass or "unclassified", 0) + 1
        if rid:
            calls += 1
    credits = {"committed_micro": c_committed,
               "unknown_or_reserved_micro": c_unknown,
               "actual_micro": c_actual, "retry_micro": c_retry}
    return (committed, unknown, actual, calls, retry, by_stage,
            {"credits_micro": credits, "outcomes_by_class": by_class,
             "repairs_used": repairs})


def _counts(conn, run_id):
    """Distinct truth counts from persisted rows, never folder/track counts.

    One multi-track provider job is ONE billable job; its tracks, saved
    artifacts and selected artifacts are counted separately and never as
    extra generation calls.
    """
    gen = set()
    for (rid,) in conn.execute(
            "SELECT remote_task_id FROM jobs WHERE run_id=? AND "
            "remote_task_id<>''", (run_id,)):
        gen.add(rid)
    for (rid,) in conn.execute(
            "SELECT remote_task_id FROM provider_jobs WHERE run_id=?",
            (run_id,)):
        gen.add(rid)
    billable = conn.execute(
        "SELECT COUNT(*) FROM provider_jobs WHERE run_id=? AND billable=1",
        (run_id,)).fetchone()[0]
    legacy = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE run_id=? AND remote_task_id<>'' AND "
        "remote_task_id NOT IN (SELECT remote_task_id FROM provider_jobs "
        "WHERE run_id=?)", (run_id, run_id)).fetchone()[0]
    tracks = conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE run_id=?", (run_id,)).fetchone()[0]
    saved = conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE run_id=? AND saved=1",
        (run_id,)).fetchone()[0]
    selected = conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE run_id=? AND selected=1",
        (run_id,)).fetchone()[0]
    return {"billable_jobs": billable + legacy, "provider_tracks": tracks,
            "saved_artifacts": saved, "selected_artifacts": selected,
            "number_of_generation_calls": len(gen)}


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
        _, ceiling, ccy, qc, repair_cap, status, ver = run
        (committed, unknown, actual, calls, retry, by_stage,
         extra) = _totals(conn, run_id)
        counts = _counts(conn, run_id)
        num, den = conn.execute(
            "SELECT credit_to_subunit_num,credit_to_subunit_den FROM runs "
            "WHERE run_id=?", (run_id,)).fetchone()
        active_est = sum(
            r[0] or 0 for r in conn.execute(
                "SELECT estimated_cost FROM jobs WHERE run_id=? AND state IN"
                " ('planned','reserved','submitted','unknown')", (run_id,)))
        ev = {"estimated_cost": active_est, "committed_cost": committed,
              "actual_cost": actual, "unknown_or_reserved_cost": unknown,
              "qc_and_repair_allowance": qc,
              "provider_cost_by_stage": by_stage,
              "number_of_generation_calls": counts[
                  "number_of_generation_calls"], "retry_cost": retry,
              "remaining_budget": ceiling - (actual + committed + unknown + qc),
              "run_status": status, "currency": ccy,
              "repair_cap": repair_cap,
              "repairs_used": extra["repairs_used"],
              "repairs_remaining": repair_cap - extra["repairs_used"],
              "credits_micro": extra["credits_micro"],
              "outcomes_by_class": extra["outcomes_by_class"],
              "counts": counts,
              "money_contract": {
                  "amounts_unit": "currency_subunit", "currency": ccy,
                  "credits_unit": "micro_credit",
                  "micro_per_credit": MICRO_PER_CREDIT,
                  "credit_to_subunit": {"num": num, "den": den,
                                        "rounding": "floor"},
                  "fractional_usage": "preserved exactly in micro-credits",
                  "estimates": "estimates only; unreported actuals stay "
                               "reserved-unknown"}}
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


def allocate_attempt(db_path, run_id, logical_key, request_digest,
                     retry_category="", auth_ref="", estimated_cost=None,
                     stage="", owner="cli", est_credits_micro=None):
    """Canonical paid-attempt allocation (directive 8.4).

    ONE ledger transaction mints the stable logical job's new attempt ID and
    monotonically increasing ordinal and records the request digest, retry
    category and authorization reference while enforcing prior-state and
    allowance checks. The envelope returns the committed attempt_id; callers
    must use it. There is no exception fallback: allocation either commits or
    refuses visibly, and identities are never string suffixes of a prior
    attempt nor silently re-minted as "a1".
    """
    return _allocate(db_path, "allocate", run_id, logical_key, "",
                     request_digest, estimated_cost, stage, None, owner,
                     retry_category or "", auth_ref or "", est_credits_micro)


def plan(db_path, run_id, logical_key, attempt_id, request_digest,
         estimated_cost=None, stage="", attempt_no=None, owner="cli",
         retry_category="", auth_ref="", est_credits_micro=None):
    """Record a planned job: digest + logical job + attempt identity first.

    Compatible entrypoint for existing callers (kie_dispatch dispatch shape).
    The ordinal is derived from persisted history INSIDE the allocation
    transaction; attempt_no is accepted only when it equals that derived
    ordinal. Omitting an ordinal can never persist ordinal 1 again, passing 1
    again cannot mint a second first attempt (ORDINAL_MISMATCH), and the
    repair cap is enforced from persisted state before anything is written.
    """
    return _allocate(db_path, "plan", run_id, logical_key, attempt_id or "",
                     request_digest, estimated_cost, stage, attempt_no, owner,
                     retry_category or "", auth_ref or "", est_credits_micro)


def _allocate(db_path, cmd, run_id, logical_key, attempt_id, request_digest,
              estimated_cost, stage, attempt_no, owner, retry_category,
              auth_ref, est_credits_micro):
    """The single allocation transaction: identity + ordinal + digest +
    retry category + authorization reference + prior-state and repair-cap
    checks, all committed atomically. No MAX()+1 exists outside this."""
    def refuse(code, action, aid="", ver=0):
        return envelope(cmd, "rejected", code, action, run_id=run_id,
                        logical_key=logical_key,
                        attempt_id=(aid if aid != "" else attempt_id),
                        state_version=ver)
    if not request_digest:
        return refuse("MISSING_DIGEST",
                      "persist the request digest before dispatch")
    try:
        _money_int("estimated_cost", estimated_cost)
        _money_int("est_credits_micro", est_credits_micro)
        if attempt_no is not None and (isinstance(attempt_no, bool)
                                       or not isinstance(attempt_no, int)
                                       or attempt_no < 1):
            raise LedgerError("BAD_ORDINAL: the ordinal is a positive integer")
    except LedgerError as e:
        return refuse(str(e).split(":")[0], str(e))
    if retry_category and retry_category not in RETRY_CATEGORIES:
        return refuse("BAD_RETRY_CATEGORY",
                      "retry category is one of %s" % (RETRY_CATEGORIES,))
    conn = _open(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = _get_run(conn, run_id)
        if not run:
            conn.execute("ROLLBACK")
            return envelope(cmd, "error", "NO_SUCH_RUN", "", run_id=run_id)
        if run[5] != "active":
            conn.execute("ROLLBACK")
            return envelope(cmd, "rejected", "RUN_PARKED",
                            "reconcile or operator unpark", run_id=run_id,
                            logical_key=logical_key, attempt_id=attempt_id,
                            state_version=run[6])
        if attempt_id and _get_job(conn, logical_key, attempt_id):
            conn.execute("ROLLBACK")
            return refuse("DUPLICATE_ATTEMPT",
                          "attempt ID already exists; the ledger mints new "
                          "identities, never reuses one", attempt_id, run[6])
        prior = conn.execute(
            "SELECT attempt_id,state,final_outcome,uncertain,request_digest,"
            "provider_lookup_ref,auth_ref,attempt_no FROM jobs "
            "WHERE run_id=? AND logical_key=? ORDER BY attempt_no",
            (run_id, logical_key)).fetchall()
        repair_cap = run[4]
        derived = (prior[-1][7] if prior else 0) + 1
        claimed = attempt_no
        cap_src = derived if claimed is None else max(derived, claimed)
        if cap_src - 1 > repair_cap:
            conn.execute("ROLLBACK")
            return refuse("REPAIR_CAP",
                          "retry count exceeds approved repair cap %d; this "
                          "attempt would be repair %d"
                          % (repair_cap, cap_src - 1), attempt_id, run[6])
        if claimed is not None and claimed != derived:
            conn.execute("ROLLBACK")
            return refuse("ORDINAL_MISMATCH",
                          "ordinal %d is derived from persisted history; %d "
                          "would break monotonicity" % (derived, claimed),
                          attempt_id, run[6])
        for row in prior:
            if row[1] == "unknown":
                conn.execute("ROLLBACK")
                return refuse("RECONCILE_FIRST",
                              "attempt %s outcome is uncertain; reconcile it "
                              "through provider lookup before any resubmission"
                              % row[0], attempt_id, run[6])
        cat, refusal = _derive_category(prior, request_digest)
        if refusal:
            conn.execute("ROLLBACK")
            return refuse(refusal[0], refusal[1], attempt_id, run[6])
        if retry_category and retry_category != cat:
            conn.execute("ROLLBACK")
            return refuse("RETRY_CATEGORY_MISMATCH",
                          "persisted history makes this a %s; a %s claim "
                          "would falsify the prior outcome"
                          % (cat, retry_category), attempt_id, run[6])
        cat_final = retry_category or cat
        if cat_final in ("transport_retry", "failed_job_retry"):
            if any(r[1] in ("planned", "reserved", "submitted") for r in prior):
                conn.execute("ROLLBACK")
                return refuse("DUPLICATE_LOGICAL_JOB",
                              "logical job already active; poll it, never "
                              "resubmit", attempt_id, run[6])
        if cat_final == "creative_retake" and not auth_ref:
            conn.execute("ROLLBACK")
            return refuse("MISSING_AUTH_REF",
                          "a creative retake consumes repair allowance and "
                          "needs its own authorization reference",
                          attempt_id, run[6])
        if auth_ref:
            dup = conn.execute(
                "SELECT 1 FROM jobs WHERE run_id=? AND auth_ref=?",
                (run_id, auth_ref)).fetchone()
            if dup:
                conn.execute("ROLLBACK")
                return refuse("DUPLICATE_AUTHORIZATION",
                              "authorization %s already funds a committed "
                              "attempt" % auth_ref, attempt_id, run[6])
        for row in prior:
            if row[3] and not _lookup_evidence(conn, run_id, logical_key,
                                               row[0]):
                conn.execute("ROLLBACK")
                return refuse("PROVIDER_LOOKUP_REQUIRED",
                              "uncertain attempt %s needs its provider lookup "
                              "recorded (record_provider_lookup) before any "
                              "resubmission" % row[0], attempt_id, run[6])
        minted = False
        if not attempt_id:
            attempt_id = _mint_attempt_id(run_id, logical_key, derived,
                                          request_digest, cat_final,
                                          auth_ref or "")
            minted = True
        now = _now_iso()
        conn.execute(
            "INSERT INTO jobs(logical_key,attempt_id,run_id,request_digest,"
            "stage,attempt_no,state,estimated_cost,owner,lease_expires,"
            "created_at,updated_at,version,retry_category,auth_ref,uncertain,"
            "est_credits_micro) "
            "VALUES(?,?,?,?,?,?,'planned',?,?,0,?,?,1,?,?,0,?)",
            (logical_key, attempt_id, run_id, request_digest, stage, derived,
             estimated_cost, owner, now, now, cat_final, auth_ref or "",
             est_credits_micro))
        conn.execute("COMMIT")
        return envelope(cmd, "ok", "OK", "reserve before dispatch",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id,
                        evidence={"attempt_no": derived,
                                  "retry_category": cat_final,
                                  "identity_minted_by_ledger": minted,
                                  "repairs_used": derived - 1,
                                  "repair_cap": repair_cap},
                        state_version=1)
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
    """reserved|submitted -> unknown. Retains reservation; never resubmits.

    Marks the attempt uncertain: any resubmission of this logical job needs
    this attempt reconciled through provider lookup first.
    """
    return _mutate(db_path, "mark_unknown", run_id, logical_key, attempt_id,
                   owner, expected_version, ("reserved", "submitted"),
                   "unknown",
                   "reconcile via provider records or operator evidence; "
                   "do not auto-resubmit; park if undeterminable",
                   uncertain=1)


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
              expected_version=0, provider_lookup_ref="",
              actual_credits_micro=None, outcome_class=""):
    """succeeded|failed|unknown -> reconciled. Receipt written first, same txn.

    Money contract: actual_cost is integer currency subunits; when it is not
    reported but actual_credits_micro is, subunits are derived exactly through
    the run's num/den conversion contract (floor, fractional residue never
    lost) and the micro-credit figure is preserved as reported. When NO actual
    is reported the reconcile is refused and the charge stays reserved-unknown
    pending reconciliation -- it is never asserted as zero.

    provider_lookup_ref records the provider lookup that resolved an
    uncertain submission. outcome_class accounts the five outcome classes
    (rejected-before-submit, accepted-but-response-lost,
    generated-but-download-failed, saved-but-measurement-failed,
    accepted-delivered) independently.
    """
    if final_outcome not in ("succeeded", "failed"):
        return envelope("reconcile", "rejected", "BAD_OUTCOME", "",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    if outcome_class not in OUTCOME_CLASSES:
        return envelope("reconcile", "rejected", "BAD_OUTCOME_CLASS",
                        "outcome class is one of %s" % (OUTCOME_CLASSES,),
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    try:
        actual_cost = _money_int("actual_cost", actual_cost)
        actual_credits_micro = _money_int("actual_credits_micro",
                                         actual_credits_micro)
    except LedgerError as e:
        return envelope("reconcile", "rejected", str(e).split(":")[0], str(e),
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    if actual_cost is None and actual_credits_micro is None:
        return envelope("reconcile", "rejected", "UNKNOWN_PRICE",
                        "actual charge unknown; it stays reserved-unknown "
                        "until the provider reports it",
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
        resolved = actual_cost
        residue = 0
        if resolved is None:
            num, den = conn.execute(
                "SELECT credit_to_subunit_num,credit_to_subunit_den FROM runs "
                "WHERE run_id=?", (run_id,)).fetchone()
            resolved, residue = credits_to_subunits(actual_credits_micro,
                                                    num, den)
        now = _now_iso()
        conn.execute(
            "INSERT INTO receipts(run_id,logical_key,attempt_id,amount,currency,"
            "provider_ref,evidence_ref,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (run_id, logical_key, attempt_id, resolved, run[2],
             provider_ref, evidence_ref, now))
        conn.execute(
            "UPDATE jobs SET state='reconciled',final_outcome=?,actual_cost=?,"
            "actual_credits_micro=?,outcome_class=?,provider_lookup_ref="
            "CASE WHEN ?<>'' THEN ? ELSE provider_lookup_ref END,"
            "updated_at=?,version=version+1,owner=? WHERE logical_key=? AND "
            "attempt_id=?", (final_outcome, resolved, actual_credits_micro,
                             outcome_class, provider_lookup_ref,
                             provider_lookup_ref, now, owner or "",
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
                        evidence={"actual_cost": resolved,
                                  "actual_credits_micro": actual_credits_micro,
                                  "credit_residue": residue,
                                  "outcome_class": outcome_class or
                                                   "unclassified"},
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
                   "cancellation preserved receipts; reconcile remote work",
                   uncertain=1)


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


def record_provider_lookup(db_path, run_id, logical_key, attempt_id,
                           lookup_ref, owner="cli"):
    """Record the provider lookup that resolves an uncertain submission.

    Required before any resubmission of a logical job whose attempt was ever
    uncertain (directive 8.4: reconcile uncertain jobs through provider
    lookup before any resubmission).
    """
    if not lookup_ref:
        return envelope("record_provider_lookup", "rejected",
                        "MISSING_LOOKUP_REF",
                        "record the provider lookup reference used to resolve "
                        "the uncertain submission",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    conn = _open(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        job = _get_job(conn, logical_key, attempt_id)
        if not job or job[2] != run_id:
            conn.execute("ROLLBACK")
            return envelope("record_provider_lookup", "error", "NO_SUCH_JOB",
                            "", run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id)
        now = _now_iso()
        conn.execute(
            "UPDATE jobs SET provider_lookup_ref=?,updated_at=?,"
            "version=version+1 WHERE logical_key=? AND attempt_id=?",
            (lookup_ref, now, logical_key, attempt_id))
        try:
            conn.execute(
                "INSERT INTO events(run_id,logical_key,attempt_id,kind,"
                "provider_event_id,provider_seq,status,payload_json,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (run_id, logical_key, attempt_id, "provider_lookup",
                 lookup_ref, 0, "looked_up", "{}", now))
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK")
            return envelope("record_provider_lookup", "ok", "DUPLICATE_LOOKUP",
                            "lookup already recorded", run_id=run_id,
                            logical_key=logical_key, attempt_id=attempt_id)
        ver = conn.execute(
            "SELECT version FROM jobs WHERE logical_key=? AND attempt_id=?",
            (logical_key, attempt_id)).fetchone()[0]
        conn.execute("COMMIT")
        return envelope("record_provider_lookup", "ok", "OK",
                        "uncertain attempt is now reconcilable evidence-wise",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id, state_version=ver)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def record_qc_verdict(db_path, run_id, logical_key, attempt_id, verdict,
                      check_id="", evidence_ref="", owner="cli"):
    """Record a creative QC verdict WITHOUT touching provider accounting.

    A provider success that fails creative QC remains a successful provider
    result: this never flips the terminal state, and a creative retake is
    allocated on top of the successful result (its own identity, its own
    authorization), never by falsifying the prior attempt into a failure.
    """
    if verdict not in ("pass", "fail", "warn"):
        return envelope("record_qc_verdict", "rejected", "BAD_VERDICT",
                        "verdict is pass, fail or warn", run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id)
    conn = _open(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        job = _get_job(conn, logical_key, attempt_id)
        if not job or job[2] != run_id:
            conn.execute("ROLLBACK")
            return envelope("record_qc_verdict", "error", "NO_SUCH_JOB", "",
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id)
        prov = "qc-%s" % hashlib.sha256(
            "|".join((check_id or "verdict", verdict, evidence_ref or ""))
            .encode("utf-8")).hexdigest()[:16]
        now = _now_iso()
        try:
            conn.execute(
                "INSERT INTO events(run_id,logical_key,attempt_id,kind,"
                "provider_event_id,provider_seq,status,payload_json,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (run_id, logical_key, attempt_id, "qc_verdict", prov, 0,
                 verdict,
                 json.dumps({"check_id": check_id, "verdict": verdict,
                             "evidence_ref": evidence_ref},
                            sort_keys=True, separators=(",", ":")), now))
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK")
            return envelope("record_qc_verdict", "ok", "DUPLICATE_VERDICT",
                            "verdict already recorded; nothing changed",
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id)
        conn.execute("COMMIT")
        return envelope("record_qc_verdict", "ok", "OK",
                        "creative verdict recorded; provider result preserved",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id,
                        evidence={"verdict": verdict, "check_id": check_id,
                                  "provider_state": job[6],
                                  "provider_final_outcome": job[7],
                                  "provider_result_preserved": True})
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def record_provider_job(db_path, run_id, logical_key, attempt_id,
                        remote_task_id, billable=1, credits_micro=None,
                        owner="cli"):
    """Register the ONE acknowledged provider job behind one attempt.

    A multi-track provider result stays ONE billable job; its tracks are
    recorded separately (record_track) and never counted as extra generation
    calls. credits_micro is provider-reported usage in micro-credits
    (fractional usage preserved exactly).
    """
    if not remote_task_id:
        return envelope("record_provider_job", "rejected", "MISSING_REMOTE_ID",
                        "the provider job carries its remote task ID",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    try:
        credits_micro = _money_int("credits_micro", credits_micro)
    except LedgerError as e:
        return envelope("record_provider_job", "rejected",
                        str(e).split(":")[0], str(e), run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id)
    if billable not in (0, 1):
        return envelope("record_provider_job", "rejected", "BAD_BILLABLE",
                        "billable is 0 or 1", run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id)
    conn = _open(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        job = _get_job(conn, logical_key, attempt_id)
        if not job or job[2] != run_id:
            conn.execute("ROLLBACK")
            return envelope("record_provider_job", "error", "NO_SUCH_JOB", "",
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id)
        row = conn.execute(
            "SELECT logical_key,attempt_id,billable FROM provider_jobs "
            "WHERE run_id=? AND remote_task_id=?", (run_id, remote_task_id)
        ).fetchone()
        if row:
            conn.execute("ROLLBACK")
            if row[0] == logical_key and row[1] == attempt_id:
                return envelope("record_provider_job", "ok", "OK", "",
                                run_id=run_id, logical_key=logical_key,
                                attempt_id=attempt_id)
            return envelope("record_provider_job", "rejected", "TASK_TAKEN",
                            "remote task %s is already accounted to %s/%s"
                            % (remote_task_id, row[0], row[1]),
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id)
        taken = conn.execute(
            "SELECT remote_task_id FROM provider_jobs WHERE run_id=? AND "
            "logical_key=? AND attempt_id=?",
            (run_id, logical_key, attempt_id)).fetchone()
        if taken:
            conn.execute("ROLLBACK")
            return envelope("record_provider_job", "rejected",
                            "DUPLICATE_PROVIDER_JOB",
                            "attempt already has provider job %s; one "
                            "billable job per attempt" % taken[0],
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id)
        conn.execute(
            "INSERT INTO provider_jobs(run_id,remote_task_id,logical_key,"
            "attempt_id,billable,credits_micro,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (run_id, remote_task_id, logical_key, attempt_id, billable,
             credits_micro, _now_iso()))
        conn.execute("COMMIT")
        return envelope("record_provider_job", "ok", "OK", "", run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id,
                        evidence={"remote_task_id": remote_task_id,
                                  "billable": billable,
                                  "credits_micro": credits_micro})
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def record_track(db_path, run_id, logical_key, attempt_id, track_no,
                 artifact_path="", sha256="", bytes_n=0, saved=1,
                 owner="cli"):
    """Record one provider track (a returned audio take) of an attempt.

    Tracks are counted separately from billable jobs and from saved/selected
    artifacts: one multi-track provider job must never inflate the generation
    call count.
    """
    if isinstance(track_no, bool) or not isinstance(track_no, int) \
            or track_no < 1:
        return envelope("record_track", "rejected", "BAD_TRACK_NO",
                        "track_no is a positive integer", run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id)
    try:
        bytes_n = _money_int("bytes_n", bytes_n) or 0
    except LedgerError as e:
        return envelope("record_track", "rejected", str(e).split(":")[0],
                        str(e), run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    conn = _open(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        job = _get_job(conn, logical_key, attempt_id)
        if not job or job[2] != run_id:
            conn.execute("ROLLBACK")
            return envelope("record_track", "error", "NO_SUCH_JOB", "",
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id)
        conn.execute(
            "INSERT OR REPLACE INTO tracks(run_id,logical_key,attempt_id,"
            "track_no,artifact_path,sha256,bytes_n,saved,selected,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,0,?)",
            (run_id, logical_key, attempt_id, track_no, artifact_path or "",
             sha256 or "", bytes_n, 1 if saved else 0, _now_iso()))
        conn.execute("COMMIT")
        return envelope("record_track", "ok", "OK", "", run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id,
                        evidence={"track_no": track_no,
                                  "saved": bool(saved)})
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def select_track(db_path, run_id, logical_key, attempt_id, track_no,
                 owner="cli"):
    """Mark exactly one recorded track as the selected artifact."""
    conn = _open(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        job = _get_job(conn, logical_key, attempt_id)
        if not job or job[2] != run_id:
            conn.execute("ROLLBACK")
            return envelope("select_track", "error", "NO_SUCH_JOB", "",
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id)
        row = conn.execute(
            "SELECT 1 FROM tracks WHERE run_id=? AND logical_key=? AND "
            "attempt_id=? AND track_no=?",
            (run_id, logical_key, attempt_id, track_no)).fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return envelope("select_track", "rejected", "NO_SUCH_TRACK",
                            "record the track before selecting it",
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id)
        conn.execute(
            "UPDATE tracks SET selected=0 WHERE run_id=? AND logical_key=? "
            "AND attempt_id=?", (run_id, logical_key, attempt_id))
        conn.execute(
            "UPDATE tracks SET selected=1 WHERE run_id=? AND logical_key=? "
            "AND attempt_id=? AND track_no=?",
            (run_id, logical_key, attempt_id, track_no))
        conn.execute("COMMIT")
        return envelope("select_track", "ok", "OK", "", run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id,
                        evidence={"selected_track_no": track_no})
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
    a.add_argument("--credit-num", type=int, default=1)
    a.add_argument("--credit-den", type=int, default=1)

    a = sub.add_parser("plan")
    a.add_argument("--run", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--attempt", required=True)
    a.add_argument("--digest", required=True)
    a.add_argument("--est", type=int, default=None)
    a.add_argument("--stage", default="")
    a.add_argument("--attempt-no", type=int, default=None)
    a.add_argument("--owner", default="cli")
    a.add_argument("--retry-category", default="")
    a.add_argument("--auth-ref", default="")
    a.add_argument("--credits-est-micro", type=int, default=None)

    a = sub.add_parser("allocate")
    a.add_argument("--run", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--digest", required=True)
    a.add_argument("--est", type=int, default=None)
    a.add_argument("--stage", default="")
    a.add_argument("--owner", default="cli")
    a.add_argument("--retry-category", default="")
    a.add_argument("--auth-ref", default="")
    a.add_argument("--credits-est-micro", type=int, default=None)

    a = sub.add_parser("record_provider_lookup")
    a.add_argument("--run", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--attempt", required=True)
    a.add_argument("--lookup-ref", required=True)
    a.add_argument("--owner", default="cli")

    a = sub.add_parser("record_qc_verdict")
    a.add_argument("--run", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--attempt", required=True)
    a.add_argument("--verdict", choices=("pass", "fail", "warn"), required=True)
    a.add_argument("--check-id", default="")
    a.add_argument("--evidence-ref", default="")
    a.add_argument("--owner", default="cli")

    a = sub.add_parser("record_provider_job")
    a.add_argument("--run", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--attempt", required=True)
    a.add_argument("--remote-id", required=True)
    a.add_argument("--billable", type=int, choices=(0, 1), default=1)
    a.add_argument("--credits-micro", type=int, default=None)
    a.add_argument("--owner", default="cli")

    a = sub.add_parser("record_track")
    a.add_argument("--run", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--attempt", required=True)
    a.add_argument("--track-no", type=int, required=True)
    a.add_argument("--artifact-path", default="")
    a.add_argument("--sha", default="")
    a.add_argument("--bytes", type=int, default=0)
    a.add_argument("--saved", type=int, choices=(0, 1), default=1)
    a.add_argument("--owner", default="cli")

    a = sub.add_parser("select_track")
    a.add_argument("--run", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--attempt", required=True)
    a.add_argument("--track-no", type=int, required=True)
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
    a.add_argument("--actual", type=int, default=None)
    a.add_argument("--actual-credits-micro", type=int, default=None)
    a.add_argument("--provider-ref", default="")
    a.add_argument("--evidence-ref", default="")
    a.add_argument("--provider-lookup-ref", default="")
    a.add_argument("--outcome-class", default="")
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
                           ns.qc_allowance, ns.repair_cap,
                           ns.credit_num, ns.credit_den)
        elif ns.cmd == "plan":
            out = plan(ns.db, ns.run, ns.key, ns.attempt, ns.digest, ns.est,
                       ns.stage, ns.attempt_no, ns.owner, ns.retry_category,
                       ns.auth_ref, ns.credits_est_micro)
        elif ns.cmd == "allocate":
            out = allocate_attempt(ns.db, ns.run, ns.key, ns.digest,
                                   ns.retry_category, ns.auth_ref, ns.est,
                                   ns.stage, ns.owner, ns.credits_est_micro)
        elif ns.cmd == "record_provider_lookup":
            out = record_provider_lookup(ns.db, ns.run, ns.key, ns.attempt,
                                         ns.lookup_ref, ns.owner)
        elif ns.cmd == "record_qc_verdict":
            out = record_qc_verdict(ns.db, ns.run, ns.key, ns.attempt,
                                    ns.verdict, ns.check_id, ns.evidence_ref,
                                    ns.owner)
        elif ns.cmd == "record_provider_job":
            out = record_provider_job(ns.db, ns.run, ns.key, ns.attempt,
                                      ns.remote_id, ns.billable,
                                      ns.credits_micro, ns.owner)
        elif ns.cmd == "record_track":
            out = record_track(ns.db, ns.run, ns.key, ns.attempt,
                               ns.track_no, ns.artifact_path, ns.sha,
                               ns.bytes, ns.saved, ns.owner)
        elif ns.cmd == "select_track":
            out = select_track(ns.db, ns.run, ns.key, ns.attempt,
                               ns.track_no, ns.owner)
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
                            ns.owner, ns.expected_version,
                            ns.provider_lookup_ref,
                            ns.actual_credits_micro, ns.outcome_class)
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
