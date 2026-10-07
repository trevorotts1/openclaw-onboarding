#!/usr/bin/env python3
"""Family C: unknown-submission reconciliation evidence, never auto-resubmit.

Proves (stdlib only, live core modules):
  1. recover() is read-only (byte-identical DB across the call) and returns a
     per-job plan: no remote id -> BLOCKED/NO_REMOTE_ID ("never
     auto-resubmit"), unknown with remote id -> RECONCILE/UNCERTAIN_ACCEPTANCE,
     remote-tracked -> POLL/REMOTE_TRACKED;
  2. no auto-resubmit: a new plan for an active unknown key is rejected
     DUPLICATE_LOGICAL_JOB, and callbacks never create jobs (NO_SUCH_JOB);
  3. reconcile evidence: provider event applies once (idempotent
     DUPLICATE_EVENT, stale STALE_SEQ, TASK_MISMATCH refused), receipt is
     written before the job reconciles, reservations clear only after
     reconciliation, receipts sum == summary actual cost;
  4. unknown price parks the run before dispatch (UNKNOWN_PRICE, rc 4),
     spend stays blocked (RUN_PARKED) until operator unpark;
  5. cost proof: totals <= ceiling at every step.
"""
import hashlib
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L

RUN = "w4-03-unknown"
RUN_PRICE = "w4-03-unknown-price"
CEILING = 5000


def check(name, cond, detail=""):
    try:
        L.check(name, cond, detail)
    except AssertionError as exc:
        print(exc, file=sys.stderr)
        L.finish("unknown-reconcile.json", {"failed_check": name})
        raise


def db_state(db):
    """(sha256, size, mtime_ns) of the main DB, plus WAL emptiness.

    The main file is the transactional store: any write by a "read-only"
    call would move these. SQLite also creates -shm/-wal sidecars on open;
    those count only as 'no pending transaction' (WAL length 0), since a
    read-only connection creates the empty sidecars just by opening.
    """
    st = os.stat(db)
    wal = db + "-wal"
    wal_size = os.path.getsize(wal) if os.path.exists(wal) else 0
    h = hashlib.sha256()
    with open(db, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest(), st.st_size, st.st_mtime_ns, wal_size


def job_snapshot(db, run_id):
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT logical_key, attempt_id, state, remote_task_id, version "
        "FROM jobs WHERE run_id=? ORDER BY logical_key, attempt_id",
        (run_id,)).fetchall()
    conn.close()
    return rows


tmp = L.mktmp()
try:
    db = os.path.join(tmp, "unknown-ledger.db")
    e, rc, _ = L.ledger(db, "init_run", "--run", RUN, "--ceiling", CEILING)
    check("init_run ok", rc == 0 and e["outcome"] == "ok", e)

    # --- A: crash before dispatch (planned/reserved, no remote id ever)
    e, rc, _ = L.ledger(db, "plan", "--run", RUN, "--key",
                        "crash-before-dispatch", "--attempt", "a1",
                        "--digest", "d-a1", "--est", 50, "--stage", "music")
    check("plan A ok", rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "reserve", "--run", RUN, "--key",
                        "crash-before-dispatch", "--attempt", "a1")
    check("reserve A ok", rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "mark_unknown", "--run", RUN, "--key",
                        "crash-before-dispatch", "--attempt", "a1")
    check("mark_unknown A ok (reservation retained)",
          rc == 0 and e["outcome"] == "ok", e)

    # --- B: submitted then acceptance uncertain
    e, rc, _ = L.ledger(db, "plan", "--run", RUN, "--key", "uncertain-accept",
                        "--attempt", "b1", "--digest", "d-b1", "--est", 60,
                        "--stage", "video")
    check("plan B ok", rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "reserve", "--run", RUN, "--key",
                        "uncertain-accept", "--attempt", "b1")
    check("reserve B ok", rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "mark_submitted", "--run", RUN, "--key",
                        "uncertain-accept", "--attempt", "b1",
                        "--remote-id", "task-77")
    check("mark_submitted B ok", rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "mark_unknown", "--run", RUN, "--key",
                        "uncertain-accept", "--attempt", "b1")
    check("mark_unknown B ok", rc == 0 and e["outcome"] == "ok", e)

    # --- C: remote-tracked control (POLL, not parked)
    e, rc, _ = L.ledger(db, "plan", "--run", RUN, "--key", "remote-tracked",
                        "--attempt", "c1", "--digest", "d-c1", "--est", 70,
                        "--stage", "video")
    check("plan C ok", rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "reserve", "--run", RUN, "--key", "remote-tracked",
                        "--attempt", "c1")
    check("reserve C ok", rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "mark_submitted", "--run", RUN, "--key",
                        "remote-tracked", "--attempt", "c1",
                        "--remote-id", "task-88")
    check("mark_submitted C ok", rc == 0 and e["outcome"] == "ok", e)

    # --- cost proof before recovery: reservations visible, under ceiling
    e, rc, _ = L.ledger(db, "summary", "--run", RUN)
    ev0 = e["evidence"]
    check("unknown_or_reserved covers A+B", ev0["unknown_or_reserved_cost"]
          == 110, ev0["unknown_or_reserved_cost"])
    check("committed covers C", ev0["committed_cost"] == 70,
          ev0["committed_cost"])
    check("totals <= ceiling before recovery",
          ev0["actual_cost"] + ev0["committed_cost"]
          + ev0["unknown_or_reserved_cost"]
          + ev0["qc_and_repair_allowance"] <= CEILING, ev0)

    # --- recover(): read-only proof + plan
    before = db_state(db)
    snap_before = job_snapshot(db, RUN)
    env, rc, err = L.recover(db, RUN)
    after = db_state(db)
    snap_after = job_snapshot(db, RUN)
    check("recover rc=0 / outcome ok", rc == 0 and env["outcome"] == "ok", env)
    check("recover left the main DB byte-identical (sha/size/mtime)",
          before == after, (before, after))
    check("recover wrote no pending transaction (WAL empty)",
          after[3] == 0, after[3])
    check("recover changed no job row", snap_before == snap_after,
          (snap_before, snap_after))
    full_plan = env["evidence"]["jobs"]
    jobs = {j["logical_key"]: j for j in env["evidence"]["jobs"]}
    check("recover plans all 3 open jobs", len(jobs) == 3, list(jobs))
    check("no-remote-id job BLOCKED / NO_REMOTE_ID",
          jobs["crash-before-dispatch"]["action"] == "BLOCKED"
          and jobs["crash-before-dispatch"]["reason"] == "NO_REMOTE_ID",
          jobs["crash-before-dispatch"])
    check("BLOCKED plan refuses auto-resubmit",
          "never auto-resubmit" in jobs["crash-before-dispatch"]["next"],
          jobs["crash-before-dispatch"]["next"])
    check("unknown+remote job RECONCILE / UNCERTAIN_ACCEPTANCE",
          jobs["uncertain-accept"]["action"] == "RECONCILE"
          and jobs["uncertain-accept"]["reason"] == "UNCERTAIN_ACCEPTANCE",
          jobs["uncertain-accept"])
    check("remote-tracked job POLL / REMOTE_TRACKED",
          jobs["remote-tracked"]["action"] == "POLL"
          and jobs["remote-tracked"]["reason"] == "REMOTE_TRACKED",
          jobs["remote-tracked"])

    # --- no auto-resubmit of the active unknown key
    e, rc, _ = L.ledger(db, "plan", "--run", RUN, "--key",
                        "crash-before-dispatch", "--attempt", "a2",
                        "--digest", "d-a2", "--est", 50, "--attempt-no", 2)
    check("re-plan of active unknown key rejected DUPLICATE_LOGICAL_JOB rc=5",
          rc == L.RC["rejected_ledger"]
          and e["reason_code"] == "DUPLICATE_LOGICAL_JOB", e)
    check("reject message forbids resubmit",
          "never resubmit" in e["next_action"], e["next_action"])

    # --- callbacks never create jobs
    e, rc, _ = L.recover(db, RUN)  # still read-only, sanity
    env2, rc2, _ = L.run_py(
        L.RECOVERY, "--db", db, "ingest_event", "--run", RUN, "--key",
        "ghost-key", "--attempt", "g1", "--event-id", "ev-ghost",
        "--seq", "1", "--status", "succeeded", "--payload", "{}")
    check("callback for unknown job rejected NO_SUCH_JOB rc=1",
          rc2 == 1 and env2["reason_code"] == "NO_SUCH_JOB", (rc2, env2))

    # --- reconcile B from verified provider evidence
    env2, rc2, _ = L.run_py(
        L.RECOVERY, "--db", db, "ingest_event", "--run", RUN, "--key",
        "uncertain-accept", "--attempt", "b1", "--event-id", "ev-b1",
        "--seq", "1", "--status", "succeeded",
        "--payload", '{"remote_task_id": "task-77"}')
    check("terminal provider event applied",
          rc2 == 0 and env2["reason_code"] == "OK"
          and env2["evidence"]["state"] == "succeeded", (rc2, env2))
    env2, rc2, _ = L.run_py(
        L.RECOVERY, "--db", db, "ingest_event", "--run", RUN, "--key",
        "uncertain-accept", "--attempt", "b1", "--event-id", "ev-b1",
        "--seq", "1", "--status", "succeeded",
        "--payload", '{"remote_task_id": "task-77"}')
    check("duplicate event idempotent (DUPLICATE_EVENT)",
          env2["reason_code"] == "DUPLICATE_EVENT", env2)
    env2, rc2, _ = L.run_py(
        L.RECOVERY, "--db", db, "ingest_event", "--run", RUN, "--key",
        "uncertain-accept", "--attempt", "b1", "--event-id", "ev-b0",
        "--seq", "1", "--status", "progress", "--payload", "{}")
    check("older seq recorded not applied (STALE_SEQ)",
          env2["reason_code"] == "STALE_SEQ", env2)
    env2, rc2, _ = L.run_py(
        L.RECOVERY, "--db", db, "ingest_event", "--run", RUN, "--key",
        "uncertain-accept", "--attempt", "b1", "--event-id", "ev-b9",
        "--seq", "2", "--status", "progress",
        "--payload", '{"remote_task_id": "task-OTHER"}')
    check("task-id mismatch refused (TASK_MISMATCH)",
          rc2 == L.RC["rejected_ledger"]
          and env2["reason_code"] == "TASK_MISMATCH", (rc2, env2))

    # downloaded artifact persisted against the existing job
    artifact = os.path.join(tmp, "result-b1.json")
    with open(artifact, "w", encoding="utf-8") as f:
        json.dump({"job": "uncertain-accept", "state": "succeeded"}, f)
    sha = L.sha256_file(artifact)
    env2, rc2, _ = L.run_py(
        L.RECOVERY, "--db", db, "record_result", "--run", RUN, "--key",
        "uncertain-accept", "--attempt", "b1", "--artifact", artifact,
        "--sha", sha, "--bytes", str(os.path.getsize(artifact)))
    check("record_result ok", rc2 == 0 and env2["outcome"] == "ok", env2)

    e, rc, _ = L.ledger(db, "reconcile", "--run", RUN, "--key",
                        "uncertain-accept", "--attempt", "b1",
                        "--final", "succeeded", "--actual", 60,
                        "--provider-ref", "task-77",
                        "--evidence-ref", "event:ev-b1")
    check("reconcile B ok", rc == 0 and e["outcome"] == "ok", e)

    # --- reconcile A from operator evidence (charge never happened)
    e, rc, _ = L.ledger(db, "mark_terminal", "--run", RUN, "--key",
                        "crash-before-dispatch", "--attempt", "a1",
                        "--outcome", "failed")
    check("mark_terminal A ok", rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "reconcile", "--run", RUN, "--key",
                        "crash-before-dispatch", "--attempt", "a1",
                        "--final", "failed", "--actual", 0,
                        "--evidence-ref", "operator:no-dispatch-charge")
    check("reconcile A ok on operator evidence",
          rc == 0 and e["outcome"] == "ok", e)

    # --- after reconcile: reservations cleared, receipts exact
    e, rc, _ = L.ledger(db, "summary", "--run", RUN)
    ev1 = e["evidence"]
    check("unknown_or_reserved cleared after reconcile",
          ev1["unknown_or_reserved_cost"] == 0,
          ev1["unknown_or_reserved_cost"])
    check("actual cost == reconciled charge", ev1["actual_cost"] == 60,
          ev1["actual_cost"])
    check("run still active (only C outstanding)",
          ev1["run_status"] == "active", ev1["run_status"])
    conn = sqlite3.connect(db)
    receipts = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(amount),0) FROM receipts WHERE run_id=?",
        (RUN,)).fetchone()
    rows = conn.execute(
        "SELECT logical_key, state, final_outcome, actual_cost FROM jobs "
        "WHERE run_id=? ORDER BY logical_key", (RUN,)).fetchall()
    conn.close()
    state_by_key = {r[0]: (r[1], r[2], r[3]) for r in rows}
    check("one receipt per reconciled job, sum 60 (A zero-charge + B)",
          receipts[0] == 2 and receipts[1] == 60, receipts)
    check("receipts sum == summary actual_cost",
          receipts[1] == ev1["actual_cost"], (receipts[1], ev1["actual_cost"]))
    check("A and B reconciled, C still submitted",
          state_by_key["crash-before-dispatch"][0] == "reconciled"
          and state_by_key["uncertain-accept"][0] == "reconciled"
          and state_by_key["remote-tracked"][0] == "submitted",
          state_by_key)
    check("totals <= ceiling after reconcile",
          ev1["actual_cost"] + ev1["committed_cost"]
          + ev1["unknown_or_reserved_cost"]
          + ev1["qc_and_repair_allowance"] <= CEILING, ev1)

    # --- unknown price parks before dispatch (separate run)
    e, rc, _ = L.ledger(db, "init_run", "--run", RUN_PRICE,
                        "--ceiling", CEILING)
    check("init_run price run ok", rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "plan", "--run", RUN_PRICE, "--key",
                        "priceless", "--attempt", "p1", "--digest", "d-p1",
                        "--stage", "music")
    check("plan with unknown price accepted into ledger",
          rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "reserve", "--run", RUN_PRICE, "--key",
                        "priceless", "--attempt", "p1")
    check("reserve with unknown price parks run rc=4 UNKNOWN_PRICE",
          rc == L.RC["parked_ledger"] and e["outcome"] == "parked"
          and e["reason_code"] == "UNKNOWN_PRICE", (rc, e))
    e, rc, _ = L.ledger(db, "summary", "--run", RUN_PRICE)
    check("price run status parked", e["evidence"]["run_status"] == "parked",
          e["evidence"]["run_status"])
    e, rc, _ = L.ledger(db, "plan", "--run", RUN_PRICE, "--key", "other",
                        "--attempt", "o1", "--digest", "d-o1")
    check("plan while price-parked rejected RUN_PARKED rc=5",
          rc == L.RC["rejected_ledger"] and e["reason_code"] == "RUN_PARKED",
          e)
    e, rc, _ = L.ledger(db, "unpark", "--run", RUN_PRICE)
    check("operator unpark ok", rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "can_spend", "--run", RUN_PRICE, "--est", 1)
    check("spend gate open again after unpark",
          rc == 0 and e["outcome"] == "ok", e)

    # --- final recover: only C remains, still POLL (poll, not resubmit)
    env, rc, _ = L.recover(db, RUN)
    remaining = env["evidence"]["jobs"]
    check("final recover lists only the remote-tracked job",
          len(remaining) == 1 and remaining[0]["logical_key"] == "remote-tracked",
          remaining)
    check("final action is POLL (polling != resubmitting)",
          remaining[0]["action"] == "POLL", remaining[0])

    L.finish("unknown-reconcile.json", {
        "recover_plan": full_plan,
        "recover_plan_final": env["evidence"]["jobs"],
        "recover_readonly_db_state": {"sha256": before[0], "size": before[1],
                                      "mtime_ns": before[2],
                                      "wal_size_after": after[3]},
        "summary_before": ev0,
        "summary_after": ev1,
        "receipts": list(receipts),
        "job_rows": [list(r) for r in rows],
        "unknown_price_park": "reserve with est=None parked the run "
                              "(UNKNOWN_PRICE, rc 4); plan/spend blocked "
                              "RUN_PARKED until unpark",
    })
finally:
    L.rm_tmp(tmp)
