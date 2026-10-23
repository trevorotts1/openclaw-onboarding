#!/usr/bin/env python3
"""sc38_user_cancellation.py — acceptance row SC-38.

Condition (SCENARIO-MATRIX.json, row SC-38, verbatim):
    "User cancellation"

Required result (verbatim):
    "NEGATIVE: a cancelled run performs no further paid work and no delivery;
     terminal state is cancelled, not delivered"

The runner drives the REAL supervision module of the tree under test
(``scripts/core/heartbeat/run_watch.py``) against a run folder built from the
REAL ``state_store`` and ``spend_ledger`` in a scratch dir. Cancellation is
recorded the way the runbook records it: ``control/run-state.json`` with
``{"canceled": true}``. No network, no provider, no channel, no delivery
producer.

A supplied ``--core-root`` is AUTHORITATIVE: if it does not hold
``state_store.py`` the runner exits 2 naming the path (``_harness`` never falls
back to another installed copy).

Modes:
  (no flag)   run the scenario and print one assertion line per check
  selftest    re-run under deliberate defects and REQUIRE the named assertions
              to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc38"
TITLE = "user cancellation: no further paid work, no delivery, terminal cancelled"

STAGES = ("research", "creative-strategy", "script-lyrics", "music",
          "continuity-bible", "storyboard", "image-keyframes",
          "video-generation", "qc-retakes", "assembly", "final-qc", "delivery")
NOW = time.time()
RUN = "runSC38"
LEDGER_TABLES = ("jobs", "receipts", "events", "provider_jobs", "results")

# --------------------------------------------------------------------------
# run folder fixtures — real state store + real spend ledger
# --------------------------------------------------------------------------
def make_run(tmp, name, started_ago_s=20 * 60):
    run = Path(tmp) / name
    (run / "control").mkdir(parents=True)
    return run

def init_state(core, run, name):
    ss = H.load_file(core / "state_store.py", "state_store")
    st = ss.Store(run / "control" / "state.sqlite3")
    st.init_run(name, STAGES)
    st.transition(name, "research", "READY", "worker-setup")
    st.claim(name, "research", "worker-setup", lease_s=300)
    st.transition(name, "research", "COMPLETE", "worker-setup")
    st.transition(name, "creative-strategy", "READY", "worker-setup")
    st.claim(name, "creative-strategy", "worker-setup", lease_s=300)
    st.close()

def init_ledger(core, run, name, started_ago_s=20 * 60):
    sl = H.load_file(core / "spend_ledger.py", "spend_ledger")
    db = str(run / "spend.sqlite3")
    sl.init_run(db, name, ceiling=10000)
    con = sqlite3.connect(db)
    con.execute("UPDATE runs SET created_at=? WHERE run_id=?",
                (time.strftime("%Y-%m-%dT%H:%M:%SZ",
                               time.gmtime(NOW - started_ago_s)), name))
    con.commit()
    con.close()
    return sl, db

def record_one_paid_job(sl, db, name):
    """A real submitted paid job, so the spend instrument has something to see."""
    out = [
        sl.plan(db, name, "music.job", "a1",
                request_digest=hashlib.sha256(b"music-a1").hexdigest()[:16],
                estimated_cost=5, stage="music"),
        sl.reserve(db, name, "music.job", "a1"),
    ]
    out.append(sl.mark_submitted(db, name, "music.job", "a1",
                                 "fixture-task-music-a1"))
    return [row.get("outcome") for row in out]

def set_running(run, name, lease_in=300, age_s=0):
    con = sqlite3.connect(str(run / "control" / "state.sqlite3"))
    con.execute(
        "UPDATE stages SET state='RUNNING', owner='worker-setup',"
        " lease_expires=?, updated_at=? WHERE run_id=? AND stage=?",
        (NOW + lease_in, NOW - age_s, name, "creative-strategy"))
    con.commit()
    con.close()

def write_auth(run, name):
    H.write_json(run / "control" / "recovery-authorization.json",
                 {"authorized": True, "scope": ["resume"], "by": "operator",
                  "run_id": name})

def ledger_snapshot(db):
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    try:
        counts = {t: con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                  for t in LEDGER_TABLES}
        run_status = con.execute("SELECT status FROM runs").fetchone()[0]
        spent = con.execute(
            "SELECT COALESCE(SUM(actual_cost), 0) FROM jobs").fetchone()[0]
    finally:
        con.close()
    return {"counts": counts, "run_status": run_status, "actual_cost": spent}

def state_snapshot(run):
    con = sqlite3.connect("file:%s?mode=ro"
                          % (run / "control" / "state.sqlite3"), uri=True)
    try:
        rows = con.execute(
            "SELECT stage, state, version, owner, lease_expires, reason"
            " FROM stages ORDER BY stage").fetchall()
    finally:
        con.close()
    return {r[0]: tuple(r[1:]) for r in rows}

def tree_digest(root):
    root = Path(root)
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    return out

def tick(RW, run, now):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return RW.main(["--run-dir", str(run), "--interval-check",
                        "--now", str(now)])

# --------------------------------------------------------------------------
# the scenario
# --------------------------------------------------------------------------
def scenario(core, muts=frozenset()):
    RW = H.load_file(core / "heartbeat" / "run_watch.py", "sc38_run_watch")
    if "cancel_ignored" in muts:
        RW.explicit_cancellation = lambda run_dir: False
    if "delivers_anyway" in muts:
        real_message = RW.client_message

        def finished_anyway(run_id, row, decisions, stalled, stall_detail,
                            expired, complete, elapsed_minutes, done, total,
                            max_hours, canceled=False):
            if canceled:
                return ("Your video is finished. All %d steps are done, and the "
                        "finished file is in your delivery folder." % total)
            return real_message(run_id, row, decisions, stalled, stall_detail,
                                expired, complete, elapsed_minutes, done, total,
                                max_hours, canceled=canceled)
        RW.client_message = finished_anyway

    c = H.Checks(ROW, TITLE)
    print("SC38 %s — core %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    with H.Scratch() as tmp:
        tmp = Path(tmp)
        run = make_run(tmp, RUN)
        init_state(core, run, RUN)
        sl, db = init_ledger(core, run, RUN)
        outcomes = record_one_paid_job(sl, db, RUN)
        set_running(run, RUN, lease_in=300, age_s=5 * 60)
        H.write_json(run / "control" / "run-state.json", {"outline": "live"})

        before_ledger = ledger_snapshot(db)
        c.check("sc38:paid-work-exists-before-cancel",
                outcomes == ["ok", "ok", "ok"]
                and before_ledger["counts"]["jobs"] == 1,
                "outcomes=%s jobs=%d receipts=%d submitted=%d"
                % (outcomes, before_ledger["counts"]["jobs"],
                   before_ledger["counts"]["receipts"],
                   before_ledger["counts"]["provider_jobs"]))

        env_before = RW.build(run, now=NOW)
        rc_before = tick(RW, run, NOW)
        c.check("sc38:driver-keeps-working-before-cancel",
                rc_before == 0 and env_before["canceled"] is False
                and env_before["loop_should_stop"] is False
                and env_before["supervising"] is True,
                "rc=%s canceled=%s loop_should_stop=%s supervising=%s"
                % (rc_before, env_before["canceled"],
                   env_before["loop_should_stop"], env_before["supervising"]))

        # ---- the user cancels ------------------------------------------
        H.write_json(run / "control" / "run-state.json", {"canceled": True})
        read_back = RW.explicit_cancellation(run)
        typed = Path(tmp) / "typed"
        H.write_json(typed / "control" / "run-state.json", {"canceled": "true"})
        stray = Path(tmp) / "stray"
        H.write_json(stray / "run-state.json", {"canceled": True})
        c.check("sc38:cancellation-record-is-read-as-content",
                read_back is True
                and RW.explicit_cancellation(typed) is False
                and RW.explicit_cancellation(stray) is False,
                "control_record=%s string_value=%s stray_path=%s"
                % (read_back, RW.explicit_cancellation(typed),
                   RW.explicit_cancellation(stray)))

        pre_state = state_snapshot(run)
        pre_ledger = ledger_snapshot(db)
        pre_tree = tree_digest(run)
        if "spends_after_cancel" in muts:
            sl.plan(db, RUN, "image.job", "a1",
                    request_digest=hashlib.sha256(b"late").hexdigest()[:16],
                    estimated_cost=5, stage="image-keyframes")

        env_after = RW.build(run, now=NOW)
        rc_after = tick(RW, run, NOW)
        post_ledger = ledger_snapshot(db)
        post_state = state_snapshot(run)
        post_tree = tree_digest(run)

        c.check("sc38:loop-stops-on-cancel",
                rc_after == 10 and env_after["canceled"] is True
                and env_after["loop_should_stop"] is True
                and env_after["supervising"] is False,
                "rc=%s canceled=%s loop_should_stop=%s supervising=%s"
                % (rc_after, env_after["canceled"],
                   env_after["loop_should_stop"], env_after["supervising"]))

        # Watcher/no-spend path only: the ledger itself still accepts
        # plan/reserve/submit after cancellation, so this is conductor-side.
        c.check("sc38:no-further-paid-work",
                pre_ledger == post_ledger,
                "before=%s after=%s"
                % (pre_ledger["counts"], post_ledger["counts"]))
        c.check("sc38:no-stage-advance-or-new-claim",
                pre_state == post_state,
                "changed=%s"
                % (sorted(s for s in pre_state
                          if pre_state[s] != post_state.get(s)) or "none"))

        receipt = env_after["message_for_client"]
        delivery_state = post_state.get("delivery", ("<absent>",))[0]
        receipts_on_disk = sorted(str(p.relative_to(run))
                                  for p in run.rglob("delivery-receipt.json"))
        c.check("sc38:terminal-state-is-cancelled-not-delivered",
                env_after["canceled"] is True
                and env_after["stage_state"] != "COMPLETE"
                and delivery_state != "COMPLETE"
                and "You asked us to stop this run" in receipt
                and "Your video is finished" not in receipt
                and not receipts_on_disk,
                "canceled=%s stage_state=%s delivery=%s delivery_receipts=%s"
                " message=%r"
                % (env_after["canceled"], env_after["stage_state"],
                   delivery_state, receipts_on_disk or "none", receipt[:120]))

        changed_files = sorted(k for k in set(pre_tree) | set(post_tree)
                               if pre_tree.get(k) != post_tree.get(k))
        c.check("sc38:watcher-does-not-write-to-the-run",
                pre_tree == post_tree,
                "changed_files=%s" % (changed_files or "none"))

        # ---- a cancelled stalled run never actuates recovery ------------
        stalled = make_run(tmp, "runSC38-stalled")
        init_state(core, stalled, "runSC38-stalled")
        init_ledger(core, stalled, "runSC38-stalled", started_ago_s=240 * 60)
        set_running(stalled, "runSC38-stalled", lease_in=-60, age_s=40 * 60)
        write_auth(stalled, "runSC38-stalled")
        calls = []

        def runner(argv):
            calls.append(list(argv))
            return {"returncode": 0, "stdout_sha256": "0" * 64,
                    "stderr_tail": ""}

        # known-good control: the SAME fixture without the cancel record DOES
        # actuate recovery, so a "no recovery" result is not vacuous.
        env_control = RW.build(stalled, now=NOW, recovery_act=True,
                               runner=runner)
        c.check("sc38:control-stalled-run-without-cancel-actuates-recovery",
                bool(env_control["recovery"])
                and env_control["recovery"]["acted"] is True
                and len(calls) == 1,
                "stalled=%s canceled=%s acted=%s runner_calls=%d"
                % (env_control["stalled"], env_control["canceled"],
                   bool(env_control["recovery"])
                   and env_control["recovery"]["acted"], len(calls)))

        H.write_json(stalled / "control" / "run-state.json", {"canceled": True})
        calls.clear()
        env_cancel = RW.build(stalled, now=NOW, recovery_act=True,
                              runner=runner)
        c.check("sc38:cancelled-run-never-actuates-recovery",
                env_cancel["canceled"] is True
                and env_cancel["recovery"] is None and not calls,
                "canceled=%s stalled=%s recovery=%s runner_calls=%d"
                % (env_cancel["canceled"], env_cancel["stalled"],
                   env_cancel["recovery"], len(calls)))
    return c

# --------------------------------------------------------------------------
# selftest — prove the harness turns RED under deliberate defects
# --------------------------------------------------------------------------
MUTATIONS = {
    "cancel_ignored": [
        "sc38:cancellation-record-is-read-as-content",
        "sc38:loop-stops-on-cancel",
        "sc38:terminal-state-is-cancelled-not-delivered",
        "sc38:cancelled-run-never-actuates-recovery",
    ],
    "spends_after_cancel": [
        "sc38:no-further-paid-work",
    ],
    "delivers_anyway": [
        "sc38:terminal-state-is-cancelled-not-delivered",
    ],
}

def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and len(failed) >= 1
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good else "DID NOT FAIL AS EXPECTED",
                 failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s"
          % ("harness fails on every injected defect" if ok
             else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "selftest":
        args = H.add_args(description="sc38 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))

    ap = H.add_args(description=__doc__)
    args = ap.parse_args(argv)
    core = H.resolve_core(args)
    result = scenario(core)
    if args.out:
        return result.finish(Path(args.out) / "receipts")
    return result.finish()

if __name__ == "__main__":
    sys.exit(main())
