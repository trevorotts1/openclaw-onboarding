#!/usr/bin/env python3
"""Family B: one repair cycle budgeted, repair <= repair_cap.

Proves (stdlib only, live core modules):
  1. spend ledger: run with --repair-cap 1 grants exactly one retry
     (attempt_no 2), rejects attempt_no 3 with REPAIR_CAP (rc 5), rejects a
     retry of a non-failed attempt with RETRY_NOT_FAILED (rc 5);
  2. the cap is read from the run row, not hardcoded: a default-cap-2 run
     grants two retries and rejects the third;
  3. retake_manager: profile-sourced cap 1 parks the second retake with
     REPAIR_CAP_EXHAUSTED; default cap 2 parks the third; every granted
     attempt stays <= repair_cap, counters come from durable history;
  4. music_director.plan_repair: with repair_cap 1, failed sections beyond
     the cap park instead of extending;
  5. cost proof: receipts sum == summary actual cost, retry_cost equals the
     retry-attempt spend, totals <= ceiling.
"""
import json
import os
import sqlite3
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L

import music_director as M

RETKE = os.path.join(L.CORE, "retake_manager", "retake_manager.py")
ACCEPTANCE_PROFILE = os.path.join(L.CORE, "acceptance-profile.json")
CAP1_PROFILE = os.path.join(L.FIXTURES, "profile-repair-cap-1.json")
CEILING = 5000


def check(name, cond, detail=""):
    try:
        L.check(name, cond, detail)
    except AssertionError as exc:
        print(exc, file=sys.stderr)
        L.finish("repair-budget.json", {"failed_check": name})
        raise


def run_retake(request, profile=None):
    args = [sys.executable, RETKE, "--request", request]
    if profile:
        args += ["--profile", profile]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=60)
    return json.loads(proc.stdout), proc.returncode


def cycle(db, run, key, attempt_id, attempt_no, outcome, actual, remote):
    """plan -> reserve -> submitted -> terminal -> reconcile (full paid cycle)."""
    e, rc, _ = L.ledger(db, "plan", "--run", run, "--key", key,
                        "--attempt", attempt_id, "--digest",
                        "digest-%s-%d" % (key, attempt_no),
                        "--est", actual, "--attempt-no", attempt_no)
    if e["outcome"] != "ok":
        return e, rc
    e, rc, _ = L.ledger(db, "reserve", "--run", run, "--key", key,
                        "--attempt", attempt_id)
    if e["outcome"] != "ok":
        return e, rc
    e, rc, _ = L.ledger(db, "mark_submitted", "--run", run, "--key", key,
                        "--attempt", attempt_id, "--remote-id", remote)
    if e["outcome"] != "ok":
        return e, rc
    e, rc, _ = L.ledger(db, "mark_terminal", "--run", run, "--key", key,
                        "--attempt", attempt_id, "--outcome", outcome)
    if e["outcome"] != "ok":
        return e, rc
    e, rc, _ = L.ledger(db, "reconcile", "--run", run, "--key", key,
                        "--attempt", attempt_id, "--final", outcome,
                        "--actual", actual,
                        "--provider-ref", "provider:%s" % remote,
                        "--evidence-ref", "receipt:%s" % attempt_id)
    return e, rc


tmp = L.mktmp()
try:
    db = os.path.join(tmp, "repair-ledger.db")
    RUN1 = "w4-03-repair-cap1"
    RUN2 = "w4-03-repair-cap2"

    # --- 1. run row carries the budget: one repair cycle
    e, rc, _ = L.ledger(db, "init_run", "--run", RUN1, "--ceiling", CEILING,
                        "--repair-cap", 1)
    check("init_run cap1 ok", rc == 0 and e["outcome"] == "ok", e)
    conn = sqlite3.connect(db)
    cap1 = conn.execute("SELECT repair_cap FROM runs WHERE run_id=?",
                        (RUN1,)).fetchone()[0]
    conn.close()
    check("runs.repair_cap == 1", cap1 == 1, cap1)

    granted = []
    e, rc = cycle(db, RUN1, "key1", "a1", 1, "failed", 100, "t-a1")
    check("attempt 1 (original) completes", rc == 0 and e["outcome"] == "ok",
          e)
    e, rc = cycle(db, RUN1, "key1", "a2", 2, "failed", 100, "t-a2")
    check("attempt 2 (the budgeted repair) completes",
          rc == 0 and e["outcome"] == "ok", e)
    if rc == 0 and e["outcome"] == "ok":
        granted.append(2)
    e, rc, _ = L.ledger(db, "plan", "--run", RUN1, "--key", "key1",
                        "--attempt", "a3", "--digest", "digest-key1-3",
                        "--est", 100, "--attempt-no", 3)
    check("attempt 3 rejected REPAIR_CAP rc=5",
          rc == L.RC["rejected_ledger"] and e["outcome"] == "rejected"
          and e["reason_code"] == "REPAIR_CAP", e)
    check("repair granted == 1 <= repair_cap(1)",
          len(granted) == 1 and len(granted) <= cap1, (granted, cap1))
    check("REPAIR_CAP message names the cap",
          "exceeds approved repair cap" in e["next_action"], e["next_action"])

    # retry of a non-failed attempt is refused
    e, rc = cycle(db, RUN1, "key2", "b1", 1, "succeeded", 40, "t-b1")
    check("succeeded attempt completes", rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "plan", "--run", RUN1, "--key", "key2",
                        "--attempt", "b2", "--digest", "digest-key2-2",
                        "--est", 40, "--attempt-no", 2)
    check("retry of non-failed attempt rejected RETRY_NOT_FAILED rc=5",
          rc == L.RC["rejected_ledger"] and e["reason_code"] == "RETRY_NOT_FAILED",
          e)

    # --- 2. cap is read from the run (default 2), not hardcoded
    e, rc, _ = L.ledger(db, "init_run", "--run", RUN2, "--ceiling", CEILING)
    check("init_run default ok", rc == 0 and e["outcome"] == "ok", e)
    conn = sqlite3.connect(db)
    cap2 = conn.execute("SELECT repair_cap FROM runs WHERE run_id=?",
                        (RUN2,)).fetchone()[0]
    conn.close()
    check("default runs.repair_cap == 2", cap2 == 2, cap2)
    granted2 = []
    for n, outcome, actual in ((1, "failed", 100), (2, "failed", 100),
                               (3, "failed", 100)):
        e, rc = cycle(db, RUN2, "key3", "c%d" % n, n, outcome, actual,
                      "t-c%d" % n)
        ok = rc == 0 and e["outcome"] == "ok"
        check("cap2 attempt %d completes" % n, ok, e)
        if ok and n > 1:
            granted2.append(n)
    e, rc, _ = L.ledger(db, "plan", "--run", RUN2, "--key", "key3",
                        "--attempt", "c4", "--digest", "digest-key3-4",
                        "--est", 100, "--attempt-no", 4)
    check("cap2 attempt 4 rejected REPAIR_CAP rc=5",
          rc == L.RC["rejected_ledger"] and e["reason_code"] == "REPAIR_CAP",
          e)
    check("cap2 repairs granted == 2 <= repair_cap(2)",
          len(granted2) == 2 and len(granted2) <= cap2, (granted2, cap2))

    # --- 3. cost proof: receipts == actual, retry cost tracked, <= ceiling
    e, rc, _ = L.ledger(db, "summary", "--run", RUN1)
    ev1 = e["evidence"]
    conn = sqlite3.connect(db)
    receipts = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(amount),0) FROM receipts WHERE run_id=?",
        (RUN1,)).fetchone()
    conn.close()
    check("receipts written for every reconcile", receipts[0] == 3,
          receipts[0])
    check("receipts sum == summary actual_cost",
          receipts[1] == ev1["actual_cost"], (receipts[1], ev1["actual_cost"]))
    check("retry_cost == spend of retry attempts", ev1["retry_cost"] == 100,
          ev1["retry_cost"])
    check("remaining budget >= 0", ev1["remaining_budget"] >= 0,
          ev1["remaining_budget"])
    check("totals <= ceiling",
          ev1["actual_cost"] + ev1["committed_cost"]
          + ev1["unknown_or_reserved_cost"]
          + ev1["qc_and_repair_allowance"] <= CEILING, ev1)

    # --- 4. retake_manager: durable-history cap, profile + default sources
    req_path = os.path.join(tmp, "retake-request.json")

    def retake(history, profile=None):
        req = {"failed_artifact_id": "shot-1", "check": "music_qc",
               "shots": ["shot-1"], "dependents": {}, "accepted": [],
               "artifact_states": {"shot-1": "FAIL"},
               "attempt_history": history}
        with open(req_path, "w", encoding="utf-8") as f:
            json.dump(req, f)
        return run_retake(req_path, profile)

    p, rc = retake([], CAP1_PROFILE)
    check("cap1 profile: first retake ok", p["outcome"] == "ok", p)
    check("cap1 profile: cap source profile and cap 1",
          p.get("repair_cap") == 1 and p.get("repair_cap_source") == "profile",
          (p.get("repair_cap"), p.get("repair_cap_source")))
    check("cap1 profile: attempt_no <= repair_cap",
          p["attempts"][0]["attempt_no"] <= p["repair_cap"], p["attempts"])

    p, rc = retake([{"artifact_id": "shot-1"}], CAP1_PROFILE)
    check("cap1 profile: second retake parked REPAIR_CAP_EXHAUSTED rc=4",
          p["outcome"] == "parked" and p["code"] == "REPAIR_CAP_EXHAUSTED"
          and rc == 4, (p, rc))
    check("cap1 profile: counters show 1 >= cap 1",
          p["attempt_counts"]["shot-1"] >= p["repair_cap"],
          p["attempt_counts"])

    p, rc = retake([], ACCEPTANCE_PROFILE)
    check("default profile: first retake ok", p["outcome"] == "ok", p)
    check("default profile: cap 2 from default",
          p.get("repair_cap") == 2 and p.get("repair_cap_source") == "default",
          (p.get("repair_cap"), p.get("repair_cap_source")))

    p, rc = retake([{"artifact_id": "shot-1"}], ACCEPTANCE_PROFILE)
    check("default profile: second retake ok (1 prior < cap 2)",
          p["outcome"] == "ok", p)
    check("default profile: attempt_no == 2 <= cap 2",
          p["attempts"][0]["attempt_no"] == 2
          and p["attempts"][0]["attempt_no"] <= p["repair_cap"],
          p["attempts"])

    p, rc = retake([{"artifact_id": "shot-1"}, {"artifact_id": "shot-1"}],
                   ACCEPTANCE_PROFILE)
    check("default profile: third retake parked REPAIR_CAP_EXHAUSTED rc=4",
          p["outcome"] == "parked" and p["code"] == "REPAIR_CAP_EXHAUSTED"
          and rc == 4, (p, rc))

    # --- 5. music_director: one extend, the rest park
    actions = M.plan_repair(
        [{"section_id": "s%d" % i, "verdict": "FAIL"} for i in range(3)],
        repair_cap=1)
    extends = [a for a in actions if a["action"] == "extend"]
    parks = [a for a in actions if a["action"] == "park"]
    check("plan_repair grants <= repair_cap extends",
          len(extends) <= 1 and len(extends) == 1, actions)
    check("plan_repair parks the overflow sections", len(parks) == 2,
          actions)

    L.finish("repair-budget.json", {
        "run1": {"repair_cap": cap1, "repairs_granted": len(granted),
                 "summary": ev1, "receipts": list(receipts)},
        "run2": {"repair_cap": cap2, "repairs_granted": len(granted2)},
        "retake_manager": "cap1 profile parks 2nd retake; default cap 2 "
                          "parks 3rd; every granted attempt <= repair_cap",
        "plan_repair": {"repair_cap": 1, "extends": len(extends),
                        "parks": len(parks)},
    })
finally:
    L.rm_tmp(tmp)
