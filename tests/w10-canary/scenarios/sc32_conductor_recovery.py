#!/usr/bin/env python3
"""sc32_conductor_recovery.py — acceptance row SC-32 (S75-W10-U1 scenario matrix).

Condition (SCENARIO-MATRIX.json, row SC-32, verbatim):
    "Conductor crash recovery"

Required result (verbatim):
    "NEGATIVE: after a conductor crash the run resumes from durable state with
     no duplicated stage and no lost ledger entry"

Proves, against the REAL core modules of the tree under test
(state_store.py + spend_ledger.py + job_recovery.py):

  * the durable stage rows of the completed prefix survive the crash byte for
    byte (state + version), and the crashed stage comes back RUNNING with an
    expired lease -- the crash never rewrites the record;
  * after restart the continuation queue holds exactly ONE work item for the
    crashed stage, carrying its ORIGINAL attempt id; re-enqueuing the same work
    item is a replay, not a second stage;
  * the ledger read model is identical before the crash and after the restart
    (same jobs, same committed/unknown buckets, same generation-call count);
  * a verified provider event survives the restart and replaying it is a
    no-op (DUPLICATE_EVENT) -- a durable ledger entry is never lost and never
    doubled;
  * a second attempt for an in-flight logical job is refused
    (DUPLICATE_LOGICAL_JOB);
  * recovery plans POLL for the remote-tracked job and BLOCKED for the
    crash-before-dispatch job -- it NEVER plans a resubmission;
  * the resumed conductor claims the continuation and the expired stage
    exactly once, the already-completed stages are not re-run, and the crashed
    stage reaches COMPLETE exactly once.

Only the provider/transport is a fixture: rows in scratch SQLite files and an
in-process provider event. No network, no paid provider, no live channel, no
graph mutation, no subprocess.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  selftest    re-run the scenario under deliberate fixture defects and REQUIRE
              the named assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc32"
TITLE = "conductor crash recovery (one stage, one ledger entry)"
RUN_ID = "runSC32"
CRASH_STAGE = "video-generation"
PREFIX = ("research", "creative-strategy", "script-lyrics", "music")
MUSIC_KEY = "music.job"
VIDEO_KEY = "video-generation.job"
MUSIC_TASK = "task-music-a1"
EVENT_ID = "evt-music-1"
DIGEST_MUSIC = hashlib.sha256(b"sc32|music|r1").hexdigest()[:16]
DIGEST_VIDEO = hashlib.sha256(b"sc32|video|r1").hexdigest()[:16]

# --------------------------------------------------------------------------
def load_core(core):
    ss = H.load_file(core / "state_store.py", "state_store")
    sl = H.load_file(core / "spend_ledger.py", "spend_ledger")
    jr = H.load_file(core / "job_recovery.py", "job_recovery")
    F = H.load_pkg(core, "intake_preflight.factory")
    return ss, sl, jr, F

def complete_stage(st, stage, actor):
    """Drive one stage NOT_STARTED -> COMPLETE through the real state machine."""
    st.transition(RUN_ID, stage, "READY", actor)
    st.transition(RUN_ID, stage, "RUNNING", actor)
    st.transition(RUN_ID, stage, "QC", actor)
    st.transition(RUN_ID, stage, "COMPLETE", actor)

def stage_snapshot(st, stages):
    return {s: (st.get(RUN_ID, s)["state"], st.get(RUN_ID, s)["version"])
            for s in stages}

def complete_transitions(st, stage):
    return sum(1 for (stg, kind, detail, _at) in st.events(RUN_ID)
               if stg == stage and kind == "transition"
               and str(detail).endswith("->COMPLETE "))

def mutate_databases(state_db, spend_db, muts):
    """Deliberate fixture damage between the crash and the restart."""
    if "drop_continuation" in muts:
        con = sqlite3.connect(state_db)
        try:
            con.execute("DELETE FROM continuations")
            con.commit()
        finally:
            con.close()
    if "drop_ledger_job" in muts:
        con = sqlite3.connect(spend_db)
        try:
            con.execute("DELETE FROM jobs WHERE logical_key=?", (MUSIC_KEY,))
            con.commit()
        finally:
            con.close()

# --------------------------------------------------------------------------
def scenario(core, muts=frozenset()):
    ss, sl, jr, F = load_core(core)
    stages = list(F.CANONICAL_STAGES)
    c = H.Checks(ROW, TITLE)
    print("SC32 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    with H.Scratch() as tmp:
        tmp = Path(tmp)
        state_db = str(tmp / "state.db")
        spend_db = str(tmp / "spend.db")
        st = ss.Store(state_db)
        try:
            st.init_run(RUN_ID, stages)
            sl.init_run(spend_db, RUN_ID, ceiling=10000, repair_cap=2)
            for s in PREFIX:
                complete_stage(st, s, "conductor")

            # music: a real submitted paid job with a remote task id
            sl.plan(spend_db, RUN_ID, MUSIC_KEY, "a1",
                    request_digest=DIGEST_MUSIC, estimated_cost=5,
                    stage="music")
            sl.reserve(spend_db, RUN_ID, MUSIC_KEY, "a1")
            sl.mark_submitted(spend_db, RUN_ID, MUSIC_KEY, "a1", MUSIC_TASK)
            # a verified provider event is a durable ledger entry
            jr.ingest_event(spend_db, RUN_ID, MUSIC_KEY, "a1", EVENT_ID,
                            provider_seq=1, status="progress",
                            payload={"remote_task_id": MUSIC_TASK})

            # the crash stage: a paid job reserved but never dispatched
            sl.plan(spend_db, RUN_ID, VIDEO_KEY, "a1",
                    request_digest=DIGEST_VIDEO, estimated_cost=7,
                    stage=CRASH_STAGE)
            sl.reserve(spend_db, RUN_ID, VIDEO_KEY, "a1")

            # the conductor had queued its next work item before dying
            st.enqueue_continuation(RUN_ID, CRASH_STAGE, "dispatch",
                                    request_digest=DIGEST_VIDEO,
                                    attempt_id="a1")

            before_stages = stage_snapshot(st, stages)
            before_prefix = {s: before_stages[s] for s in PREFIX}
            before_summary = sl.summary(spend_db, RUN_ID)
            before_events = len(st.events(RUN_ID))

            # ---- conductor crash: stage claimed, nothing written after ----
            st.transition(RUN_ID, CRASH_STAGE, "READY", "conductor")
            lease = 60.0 if "live_lease" in muts else 0.1
            st.claim(RUN_ID, CRASH_STAGE, "conductor-crash", lease_s=lease)
            crashed = st.get(RUN_ID, CRASH_STAGE)
        finally:
            st.close()                      # the process dies here

        mutate_databases(state_db, spend_db, muts)
        if "live_lease" not in muts:
            time.sleep(0.15)

        # ---- restart against the same durable files ----------------------
        st = ss.Store(state_db)
        try:
            after_stages = stage_snapshot(st, stages)
            after_prefix = {s: after_stages[s] for s in PREFIX}
            crashed_after = st.get(RUN_ID, CRASH_STAGE)

            c.check("sc32:durable-completed-stages-survive-restart",
                    after_prefix == before_prefix,
                    "changed=%s"
                    % ([s for s in PREFIX
                        if after_prefix.get(s) != before_prefix.get(s)]
                       or "none"))
            c.check("sc32:crash-left-stage-running-with-expired-lease",
                    after_stages[CRASH_STAGE][0] == "RUNNING"
                    and crashed_after["owner"] == "conductor-crash"
                    and (crashed_after["lease_expires"] or 0) < time.time(),
                    "state=%s owner=%s expired=%s"
                    % (after_stages[CRASH_STAGE][0], crashed_after["owner"],
                       (crashed_after["lease_expires"] or 0) < time.time()))

            queue = st.scan_pending_continuations(RUN_ID)
            one = [q for q in queue
                   if q["stage"] == CRASH_STAGE and q["op"] == "dispatch"]
            c.check("sc32:restart-sees-exactly-one-continuation",
                    len(queue) == 1 and len(one) == 1
                    and one[0]["attempt_id"] == "a1",
                    "queue=%d stage_items=%d attempt=%s"
                    % (len(queue), len(one),
                       one[0]["attempt_id"] if one else None))

            replay = st.enqueue_continuation(RUN_ID, CRASH_STAGE, "dispatch",
                                             request_digest=DIGEST_VIDEO,
                                             attempt_id="att-should-not-win")
            queue2 = st.scan_pending_continuations(RUN_ID)
            c.check("sc32:replayed-enqueue-does-not-duplicate-stage",
                    replay.get("created") is False
                    and replay["continuation"]["attempt_id"] == "a1"
                    and len(queue2) == len(queue),
                    "created=%s attempt=%s queue=%d"
                    % (replay.get("created"),
                       replay["continuation"].get("attempt_id"),
                       len(queue2)))

            # ---- recovery plan: poll / block, never resubmit -------------
            plan = jr.recover(spend_db, RUN_ID)
            jobs = (plan.get("evidence") or {}).get("jobs") or []
            by_key = {j.get("logical_key"): j for j in jobs}
            music_job = by_key.get(MUSIC_KEY) or {}
            video_job = by_key.get(VIDEO_KEY) or {}
            c.check("sc32:recovery-plan-never-resubmits",
                    plan.get("outcome") == "ok" and len(jobs) == 2
                    and music_job.get("action") == "POLL"
                    and music_job.get("attempt_id") == "a1"
                    and video_job.get("action") == "BLOCKED"
                    and video_job.get("reason") == "NO_REMOTE_ID"
                    and not any(j.get("action") == "RESUBMIT"
                                for j in jobs),
                    "actions=%s"
                    % {k: v.get("action") for k, v in by_key.items()})

            # ---- the ledger read model lost nothing ---------------------
            after_summary = sl.summary(spend_db, RUN_ID)
            c.check("sc32:ledger-entries-survive-restart",
                    after_summary.get("outcome") == "ok"
                    and after_summary.get("evidence")
                    == before_summary.get("evidence"),
                    "before=%s after=%s"
                    % (str(before_summary.get("evidence"))[:120],
                       str(after_summary.get("evidence"))[:120]))

            replay_event = jr.ingest_event(spend_db, RUN_ID, MUSIC_KEY, "a1",
                                           EVENT_ID, provider_seq=1,
                                           status="progress",
                                           payload={"remote_task_id": MUSIC_TASK})
            after_replay = sl.summary(spend_db, RUN_ID)
            c.check("sc32:ledger-event-replay-is-idempotent",
                    replay_event.get("reason_code") == "DUPLICATE_EVENT"
                    and after_replay.get("evidence")
                    == before_summary.get("evidence"),
                    "reason=%s ledger_unchanged=%s"
                    % (replay_event.get("reason_code"),
                       after_replay.get("evidence")
                       == before_summary.get("evidence")))

            second = sl.plan(spend_db, RUN_ID, MUSIC_KEY, "",
                             request_digest=DIGEST_MUSIC, estimated_cost=5,
                             stage="music")
            c.check("sc32:duplicate-ledger-attempt-refused",
                    second.get("outcome") == "rejected"
                    and second.get("reason_code") == "DUPLICATE_LOGICAL_JOB",
                    "outcome=%s reason=%s"
                    % (second.get("outcome"), second.get("reason_code")))

            # ---- resume: exactly one claim of queue and stage ------------
            claimed = st.resume_continuations(RUN_ID, "conductor-resume")
            claimed_again = st.resume_continuations(RUN_ID, "conductor-resume")
            c.check("sc32:resume-claims-continuation-exactly-once",
                    len(claimed) == 1 and claimed_again == []
                    and claimed[0]["attempt_id"] == "a1",
                    "first=%d second=%d attempt=%s"
                    % (len(claimed), len(claimed_again),
                       claimed[0]["attempt_id"] if claimed else None))

            try:
                st.claim(RUN_ID, CRASH_STAGE, "conductor-resume", lease_s=300)
                took = True
                take_why = "ok"
            except ss.StoreError as exc:
                took, take_why = False, exc.code
            if took:
                try:
                    st.claim(RUN_ID, CRASH_STAGE, "other-worker", lease_s=300)
                    second_took, second_why = True, "ok"
                except ss.StoreError as exc:
                    second_took, second_why = False, exc.code
            else:
                second_took, second_why = False, "not-claimed"
            c.check("sc32:resume-claims-expired-stage-exactly-once",
                    took and not second_took and second_why == "NOT_OWNER",
                    "claimed=%s second=%s reason=%s"
                    % (took, second_took,
                       take_why if not took else second_why))

            if took:
                st.transition(RUN_ID, CRASH_STAGE, "QC", "conductor-resume")
                st.transition(RUN_ID, CRASH_STAGE, "COMPLETE",
                              "conductor-resume")
                resumed_prefix = {s: stage_snapshot(st, stages)[s]
                                  for s in PREFIX}
                c.check("sc32:resume-does-not-repeat-completed-stages",
                        resumed_prefix == before_prefix,
                        "changed=%s"
                        % ([s for s in PREFIX
                            if resumed_prefix.get(s) != before_prefix.get(s)]
                           or "none"))
                c.check("sc32:crash-stage-completes-exactly-once",
                        st.get(RUN_ID, CRASH_STAGE)["state"] == "COMPLETE"
                        and complete_transitions(st, CRASH_STAGE) == 1,
                        "state=%s complete_transitions=%d"
                        % (st.get(RUN_ID, CRASH_STAGE)["state"],
                           complete_transitions(st, CRASH_STAGE)))
            else:
                c.check("sc32:resume-does-not-repeat-completed-stages", False,
                        "not resumed")
                c.check("sc32:crash-stage-completes-exactly-once", False,
                        "not resumed")

            c.check("sc32:events-journal-did-not-shrink",
                    len(st.events(RUN_ID)) >= before_events,
                    "before=%d after=%d"
                    % (before_events, len(st.events(RUN_ID))))
        finally:
            st.close()
    return c

# --------------------------------------------------------------------------
# selftest — deliberate fixture defects must turn the named assertions RED
# --------------------------------------------------------------------------
MUTATIONS = {
    "drop_continuation": [
        "sc32:restart-sees-exactly-one-continuation",
        "sc32:replayed-enqueue-does-not-duplicate-stage",
    ],
    "drop_ledger_job": [
        "sc32:ledger-entries-survive-restart",
        "sc32:ledger-event-replay-is-idempotent",
        "sc32:duplicate-ledger-attempt-refused",
    ],
    "live_lease": [
        "sc32:crash-left-stage-running-with-expired-lease",
        "sc32:resume-claims-expired-stage-exactly-once",
    ],
}

def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and bool(failed)
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good else "DID NOT FAIL AS EXPECTED",
                 failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s" % ("harness fails on all three defects"
                             if ok else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "selftest":
        args = H.add_args(description="sc32 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))
    args = H.add_args(description=__doc__).parse_args(argv)
    return scenario(H.resolve_core(args)).finish(args.out)

if __name__ == "__main__":
    sys.exit(main())
