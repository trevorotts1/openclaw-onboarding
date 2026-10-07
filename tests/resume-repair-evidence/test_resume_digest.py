#!/usr/bin/env python3
"""Family A: park mid-run, resume from PARKED.json, identical digest.

Proves (all against live core modules, stdlib only):
  1. mid-run park at both authorities (spend ledger run + state stage),
     spend blocked while parked (RUN_PARKED), stage park needs a reason;
  2. PARKED.json written as an explicit projection (not an authority) that
     carries the intake resume contract fields;
  3. resume: unpark + intake --resume-file PARKED.json -> outcome ok /
     resume-no-changes with digest identical to the pre-park digest
     (three-way: file digest == state_version.expected == state_version.current);
  4. negative control: approval-affecting brief change invalidates resume
     (parked / resume-approval-invalidated, digest differs) -- the identity
     check is live, not vacuous;
  5. cost proof: summary totals never exceed the ceiling, no job is
     re-planned during the parked window.
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L

import state_store as S

RUN = "w4-03-resume"
CEILING = 5000


def check(name, cond, detail=""):
    try:
        L.check(name, cond, detail)
    except AssertionError as exc:
        print(exc, file=sys.stderr)
        L.finish("resume-digest.json", {"failed_check": name})
        raise


tmp = L.mktmp()
try:
    db = os.path.join(tmp, "resume-ledger.db")
    ssdb = os.path.join(tmp, "resume-stages.db")
    brief = os.path.join(L.FIXTURES, "brief.json")

    # --- 1. pre-park intake: record the digest we must see again on resume
    env, rc, err = L.factory("intake", "--brief-file", brief,
                             "--run-id", "pre-park")
    check("intake pre-park rc=ok", rc == L.RC["ok_factory"], rc)
    check("intake pre-park outcome ok",
          env is not None and env["outcome"] == "ok",
          env and env["reason_code"])
    d1 = (env or {}).get("data", {}).get("digest")
    check("digest recorded", bool(d1) and len(d1) == 16, d1)
    summary1 = (env or {}).get("data", {}).get("summary")

    # --- 2. mid-run: ledger job reserved, stage claimed
    e, rc, _ = L.ledger(db, "init_run", "--run", RUN, "--ceiling", CEILING,
                        "--repair-cap", 2)
    check("init_run ok", rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "plan", "--run", RUN, "--key", "music",
                        "--attempt", "m1", "--digest", d1, "--est", 100,
                        "--stage", "music")
    check("plan mid-run ok", rc == 0 and e["outcome"] == "ok", e)
    e, rc, _ = L.ledger(db, "reserve", "--run", RUN, "--key", "music",
                        "--attempt", "m1")
    check("reserve mid-run ok", rc == 0 and e["outcome"] == "ok", e)

    stages = S.Store(ssdb)
    stages.init_run(RUN, ["intake", "music", "video"])
    stages.transition(RUN, "music", "READY", "operator")
    row = stages.claim(RUN, "music", "worker-1")
    check("stage claimed RUNNING", row["state"] == "RUNNING", row["state"])
    try:
        stages.transition(RUN, "music", "PARKED", "worker-1")
        raise AssertionError("PARKED without reason accepted")
    except S.StoreError as exc:
        check("stage PARKED requires reason", exc.code == "MISSING_REASON",
              exc.code)
    row = stages.transition(RUN, "music", "PARKED", "worker-1",
                            reason="MID_RUN_SUSPEND")
    check("stage PARKED with reason", row["state"] == "PARKED", row["state"])
    check("stage owner cleared on PARKED", row["owner"] is None, row["owner"])

    # --- 3. park the spend run (authority record; no PARKED.json reader in tree)
    e, rc, _ = L.ledger(db, "park_run", "--run", RUN, "--reason",
                        "MID_RUN_SUSPEND")
    check("park_run outcome parked",
          e is not None and e["outcome"] == "parked", e)
    check("park_run rc=4", rc == L.RC["parked_ledger"], rc)

    # --- 4. while parked: every spend path rejects RUN_PARKED
    e, rc, _ = L.ledger(db, "can_spend", "--run", RUN, "--est", "1")
    check("can_spend while parked rejected RUN_PARKED",
          rc == L.RC["rejected_ledger"] and e["outcome"] == "rejected"
          and e["reason_code"] == "RUN_PARKED", e)
    e, rc, _ = L.ledger(db, "plan", "--run", RUN, "--key", "video",
                        "--attempt", "v1", "--digest", d1, "--est", "50")
    check("plan while parked rejected RUN_PARKED",
          rc == L.RC["rejected_ledger"] and e["reason_code"] == "RUN_PARKED",
          e)

    # --- 5. cost proof inside the parked window
    e, rc, _ = L.ledger(db, "summary", "--run", RUN)
    ev = e["evidence"]
    check("summary readable while parked", rc == 0 and e["outcome"] == "ok", e)
    check("run_status parked in summary", ev["run_status"] == "parked",
          ev["run_status"])
    check("committed while parked = 100", ev["committed_cost"] == 100, ev)
    check("remaining budget >= 0 while parked",
          ev["remaining_budget"] >= 0, ev["remaining_budget"])
    check("totals <= ceiling while parked",
          ev["actual_cost"] + ev["committed_cost"]
          + ev["unknown_or_reserved_cost"]
          + ev["qc_and_repair_allowance"] <= CEILING, ev)

    # --- 6. PARKED.json: projection of the ledgers + intake resume contract
    parked_doc = {
        "schema": "blackceo.resume-parked-projection/v1",
        "projection": True,
        "authority": "spend ledger runs.status + state_store stage rows; "
                     "this file is a projection, never an authority",
        "unit": "W4-03-U1",
        "run_id": RUN,
        "run_status": "parked",
        "park_reason": "MID_RUN_SUSPEND",
        "stage": {"stage": "music", "state": "PARKED",
                  "reason": "MID_RUN_SUSPEND"},
        "next_stage": "video",
        "outstanding": [],
        # intake resume contract fields:
        "digest": d1,
        "summary": summary1,
    }
    parked_path = os.path.join(L.EVIDENCE, "PARKED.json")
    os.makedirs(L.EVIDENCE, exist_ok=True)
    with open(parked_path, "w", encoding="utf-8") as f:
        json.dump(parked_doc, f, indent=2, sort_keys=True, default=str)
        f.write("\n")
    with open(parked_path, encoding="utf-8") as f:
        back = json.load(f)
    check("PARKED.json written and re-readable",
          back["digest"] == d1 and back["projection"] is True, back["digest"])

    # --- 7. resume: unpark ledger, release stage, replay intake from the file
    e, rc, _ = L.ledger(db, "unpark", "--run", RUN)
    check("unpark ok rc=0", rc == 0 and e["outcome"] == "ok", e)
    row = stages.transition(RUN, "music", "READY", "operator")
    check("stage PARKED -> READY", row["state"] == "READY", row["state"])

    env2, rc2, _ = L.factory("intake", "--brief-file", brief,
                             "--resume-file", parked_path,
                             "--run-id", "resumed")
    d2 = (env2 or {}).get("data", {}).get("digest")
    sv = (env2 or {}).get("state_version", {})
    check("resume intake rc=ok", rc2 == L.RC["ok_factory"], rc2)
    check("resume reason = resume-no-changes",
          env2 is not None and env2["reason_code"] == "resume-no-changes",
          env2 and env2["reason_code"])
    check("resume digest identical to pre-park digest",
          d2 == d1 and d2 == back["digest"], (d1, d2, back["digest"]))
    check("state_version expected == current == pre-park digest",
          sv.get("expected") == d1 and sv.get("current") == d1, sv)
    check("resume did not re-ask questions",
          (env2 or {}).get("data", {}).get("questions") == [],
          (env2 or {}).get("data", {}).get("questions"))
    check("resume keeps next_stage from PARKED.json",
          (env2 or {}).get("data", {}).get("next_stage") == "video",
          (env2 or {}).get("data", {}).get("next_stage"))

    # --- 8. negative control: approval-affecting change must invalidate resume
    with open(brief, encoding="utf-8") as f:
        changed = json.load(f)
    changed["offer"] = "different offer"
    changed_path = os.path.join(tmp, "brief-changed.json")
    with open(changed_path, "w", encoding="utf-8") as f:
        json.dump(changed, f)
    env3, rc3, _ = L.factory("intake", "--brief-file", changed_path,
                             "--resume-file", parked_path,
                             "--run-id", "resume-invalidated")
    d3 = (env3 or {}).get("data", {}).get("digest")
    check("changed brief parks resume (rc=3)",
          rc3 == L.RC["parked_factory"], rc3)
    check("reason = resume-approval-invalidated",
          env3 is not None
          and env3["reason_code"] == "resume-approval-invalidated",
          env3 and env3["reason_code"])
    check("digest differs after approval-affecting change", d3 != d1,
          (d1, d3))
    check("approval_invalidated flagged",
          (env3 or {}).get("data", {}).get("approval_invalidated") is True,
          (env3 or {}).get("data", {}).get("approval_invalidated"))

    # --- 9. cost proof after resume: no spend happened, no job re-planned
    e, rc, _ = L.ledger(db, "summary", "--run", RUN)
    ev = e["evidence"]
    check("run active again", ev["run_status"] == "active",
          ev["run_status"])
    check("no spend during park/resume", ev["actual_cost"] == 0,
          ev["actual_cost"])
    check("remaining unchanged after resume",
          ev["remaining_budget"] == CEILING - 100, ev["remaining_budget"])
    check("totals <= ceiling after resume",
          ev["actual_cost"] + ev["committed_cost"]
          + ev["unknown_or_reserved_cost"]
          + ev["qc_and_repair_allowance"] <= CEILING, ev)
    conn = sqlite3.connect(db)
    n_jobs = conn.execute("SELECT COUNT(*) FROM jobs WHERE run_id=?",
                          (RUN,)).fetchone()[0]
    conn.close()
    check("exactly one job planned (no auto re-plan across park)",
          n_jobs == 1, n_jobs)

    L.finish("resume-digest.json", {
        "pre_park_digest": d1,
        "resume_digest": d2,
        "invalidated_digest": d3,
        "parked_file": parked_path,
        "parked_file_is": "projection of the ledgers; the intake resume "
                          "reader consumes it (no PARKED.json reader exists "
                          "in this tree)",
        "summary_pre": summary1,
        "cost": ev,
    })
finally:
    L.rm_tmp(tmp)
