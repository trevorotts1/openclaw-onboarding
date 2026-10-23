#!/usr/bin/env python3
"""multi_run_canary.py — Skill 75 multi-run / two-tenant canary (spec 10.7, 15.1/15.2, A01/A02/A03/A11).

WHAT IT PROVES, against the REAL core modules of the tree under test
(state_store.py + spend_ledger.py imported from the pinned revision's checkout):

  1. TWO synthetic tenants, each with its own SQLite state + spend DB, are fully
     isolated: a claim/transition/payment in tenant A never appears in tenant B;
  2. fair multi-run supervision: two unfinished runs in one tenant both receive
     claim/heartbeat attention — neither starves;
  3. single-writer lease semantics (state_store): an expired lease is reclaimed
     through claim(); a live lease held by another owner is refused (NOT_OWNER);
     the old worker cannot write after reclaim (fenced);
  4. spent-attempt identity (spend_ledger): attempt IDs are atomic and unique
     (no silent a1 fallback), a duplicate attempt is refused (DUPLICATE_ATTEMPT),
     an active logical job refuses a second submission (DUPLICATE_LOGICAL_JOB),
     and a retry is only allowed after a known-failed prior attempt within the
     repair cap;
  5. terminal-state truth (A02): an all-parked, all-failed, empty or MIXED
     terminal run never reports delivered, and no failed/parked stage can be
     promoted to COMPLETE by a wake;
  6. event continuation (A03): an accepted event enqueues ONE durable
     continuation for the same run; a replay adds no second row; after a
     restart the pending work is claimed exactly once with its ORIGINAL
     attempt ordinal, and the event ordinals record enqueue before resume.

SAFETY: the whole canary runs in a Sandbox() scratch dir with the core modules
imported from an explicit --core-root (the pinned checkout). It writes only
temp SQLite files inside the scratch. It NEVER touches a real run, a real box,
a client channel or any paid provider: every "dispatch" is a ledger record, not
an HTTP call. Real-mode receipt names the live channel/provider rows as
BLOCKED_NEEDS_AUTHORIZATION (outside this unit's write surface).

Modes:
  --dry-run  drive the real core modules from the CURRENT checkout (what runs NOW,
             proving the harness works); receipt marks mode=dry-run, claims nothing
  (no flag)  drive the core modules from the PINNED vector checkout (runs AFTER pin)

Exit 0 = all checks pass; 1 = a check failed; 3 = vector not pinned; 2 = tooling.
Stdlib only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canary_common as cc  # noqa: E402

RESULTS = {}

CANONICAL_STAGES = [
    "research", "creative-strategy", "script-lyrics", "music",
    "continuity-bible", "storyboard", "image-keyframes", "video-generation",
    "qc-retakes", "assembly", "final-qc", "delivery",
]


def check(name, ok, detail=""):
    RESULTS[name] = {"ok": bool(ok), "detail": detail}
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                           (" — " + str(detail)[:300]) if detail else ""))
    return ok


def ready(st, run, stage, actor):
    """Move a NOT_STARTED stage to READY so it becomes claimable.

    state_store's claim() only accepts CLAIMABLE states (READY, STALE,
    FAILED_RETRYABLE, RUNNING); NOT_STARTED must take the NOT_STARTED->READY
    edge first. That edge is unowned, so any actor may take it.
    """
    if st.get(run, stage)["state"] == "NOT_STARTED":
        st.transition(run, stage, "READY", actor)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def resolve_core(core_root):
    core = Path(core_root) / "75-drama-song-ad-factory" / "scripts" / "core"
    ss = core / "state_store.py"
    sl = core / "spend_ledger.py"
    if not ss.is_file() or not sl.is_file():
        raise SystemExit("tooling: core modules not found under %s "
                         "(state_store.py=%s spend_ledger.py=%s)"
                         % (core_root, ss.is_file(), sl.is_file()))
    return load_module(ss, "state_store"), load_module(sl, "spend_ledger")


def scenario_tenant_isolation(ss, sl, sb):
    """Two tenants: separate state+spend DBs; actions in one leave no trace in the other."""
    base = Path(sb.env["HOME"]).parent / "tenants"
    dbA, dbB = base / "A" / "state.db", base / "B" / "state.db"
    for d in (dbA.parent, dbB.parent):
        d.mkdir(parents=True, exist_ok=True)

    stA, stB = ss.Store(str(dbA)), ss.Store(str(dbB))
    stA.init_run("runA", CANONICAL_STAGES)
    stB.init_run("runB", CANONICAL_STAGES)
    ready(stA, "runA", "music", "worker-A")
    stA.claim("runA", "music", "worker-A")
    stA.transition("runA", "music", "WAITING_PROVIDER", "worker-A")

    # tenant B untouched
    rowB = stB.get("runB", "music")
    check("tenant-isolation:B.music unaffected by A",
          rowB["state"] == "NOT_STARTED" and rowB["owner"] is None,
          "B.music=%s" % rowB["state"])
    evB = [e for e in stB.events("runB")]
    # events() rows are (stage, kind, detail, at): the actor is the DETAIL.
    check("tenant-isolation:B has no A events",
          not any(e[2] and "worker-A" in str(e[2]) for e in evB),
          "%d events in B" % len(evB))

    # spend DBs are separate files
    sl.init_run(str(base / "A" / "spend.db"), "runA", ceiling=1000)
    sl.init_run(str(base / "B" / "spend.db"), "runB", ceiling=1000)
    plan = sl.plan(str(base / "A" / "spend.db"), "runA", "music.job", "a1",
                   request_digest="d" * 16, estimated_cost=5, stage="music")
    check("tenant-isolation:A spend plan recorded",
          plan["outcome"] == "ok", plan.get("reason_code"))
    probeB = sl.plan(str(base / "B" / "spend.db"), "runA", "music.job", "a1",
                     request_digest="d" * 16, estimated_cost=5, stage="music")
    check("tenant-isolation:B has no A run/ledger",
          probeB["outcome"] in ("error", "rejected"),
          "cross-tenant probe outcome=%s rc=%s" % (probeB["outcome"],
                                                   probeB.get("reason_code")))
    stA.close(); stB.close()


def scenario_fair_supervision(ss, sb):
    """Two unfinished runs both receive claim/heartbeat; neither starves."""
    base = Path(sb.env["HOME"]).parent / "fair"
    base.mkdir(parents=True, exist_ok=True)
    st = ss.Store(str(base / "state.db"))
    st.init_run("runOld", CANONICAL_STAGES)   # older stalled run
    st.init_run("runNew", CANONICAL_STAGES)   # newer approval-waiting run

    def worker(run, owner):
        # each worker opens its own Store connection: a single sqlite connection
        # is bound to the thread that created it, and real workers are separate
        # processes/threads with separate connections to the same DB file.
        wst = ss.Store(str(base / "state.db"))
        for _ in range(3):
            ready(wst, run, "script-lyrics", owner)
            wst.claim(run, "script-lyrics", owner, lease_s=30)
            wst.heartbeat(run, "script-lyrics", owner, lease_s=30)
            time.sleep(0.05)
        wst.close()

    t1 = threading.Thread(target=worker, args=("runOld", "supervisor"))
    t2 = threading.Thread(target=worker, args=("runNew", "supervisor"))
    t1.start(); t2.start(); t1.join(); t2.join()
    o = st.get("runOld", "script-lyrics")
    n = st.get("runNew", "script-lyrics")
    check("fair-supervision:both runs supervised",
          o["owner"] == "supervisor" and n["owner"] == "supervisor",
          "runOld=%s runNew=%s" % (o["state"], n["state"]))
    ev = st.events("runOld") + st.events("runNew")
    check("fair-supervision:claim events on both runs",
          any(e[0] == "script-lyrics" for e in st.events("runOld")) and
          any(e[0] == "script-lyrics" for e in st.events("runNew")),
          "%d total events" % len(ev))
    st.close()


def scenario_lease_single_writer(ss, sb):
    """Expired-lease reclaim through claim(); live lease fenced; old worker can't write."""
    base = Path(sb.env["HOME"]).parent / "lease"
    base.mkdir(parents=True, exist_ok=True)
    st = ss.Store(str(base / "state.db"))
    st.init_run("runL", CANONICAL_STAGES)

    ready(st, "runL", "music", "worker-old")
    st.claim("runL", "music", "worker-old", lease_s=0)  # lease already expired
    # live-lease fence: while lease is live another owner is refused
    ready(st, "runL", "assembly", "worker-old")
    st.claim("runL", "assembly", "worker-old", lease_s=300)
    try:
        st.claim("runL", "assembly", "worker-new")
        fenced = False
        err = "no error"
    except ss.StoreError as e:
        fenced = e.code == "NOT_OWNER"
        err = e.code
    check("lease:fenced live lease (NOT_OWNER)", fenced, err)

    # expired lease reclaimed by a new owner through claim()
    time.sleep(0.05)
    st.claim("runL", "music", "worker-new", lease_s=300)
    row = st.get("runL", "music")
    check("lease:expired lease reclaimed by new owner",
          row["owner"] == "worker-new", "owner=%s" % row["owner"])

    # old worker is fenced after reclaim
    try:
        st.transition("runL", "music", "WAITING_PROVIDER", "worker-old")
        old_fenced = False
        err2 = "no error"
    except ss.StoreError as e:
        old_fenced = e.code in ("NOT_OWNER", "STALE_LEASE")
        err2 = e.code
    check("lease:old worker fenced after reclaim", old_fenced, err2)
    st.close()


def scenario_attempt_identity(sl, sb):
    """Atomic attempt ordinals: no duplicate IDs, no silent a1, retry only after failure."""
    db = str(Path(sb.env["HOME"]).parent / "attempt" / "spend.db")
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    sl.init_run(db, "runP", ceiling=1000, repair_cap=2)

    p1 = sl.plan(db, "runP", "music.job", "a1", request_digest="d1", estimated_cost=5)
    check("attempt:first attempt planned", p1["outcome"] == "ok",
          p1.get("reason_code"))

    dup = sl.plan(db, "runP", "music.job", "a1", request_digest="d1", estimated_cost=5)
    check("attempt:duplicate attempt ID refused",
          dup.get("reason_code") == "DUPLICATE_ATTEMPT", dup.get("reason_code"))

    active = sl.plan(db, "runP", "music.job", "a2", request_digest="d2", estimated_cost=5)
    check("attempt:second submission while active refused",
          active.get("reason_code") == "DUPLICATE_LOGICAL_JOB",
          active.get("reason_code"))

    # retry only allowed after a known-failed prior attempt
    r1 = sl.reserve(db, "runP", "music.job", "a1")
    s1 = sl.mark_submitted(db, "runP", "music.job", "a1", "remote-task-1")
    t1 = sl.mark_terminal(db, "runP", "music.job", "a1", "failed")
    check("attempt:prior attempt marked failed",
          t1.get("outcome") == "ok", t1.get("reason_code"))
    p2 = sl.plan(db, "runP", "music.job", "a2", request_digest="d2",
                 estimated_cost=5, attempt_no=2)
    check("attempt:retry after failure allowed (a2, not silent a1)",
          p2["outcome"] == "ok", p2.get("reason_code"))

    # repair-cap check: the RETRY_NOT_FAILED and DUPLICATE_LOGICAL_JOB guards
    # run first, so give it its own key whose only prior attempt is failed, then
    # request an attempt_no beyond the approved repair cap (2).
    sl.plan(db, "runP", "cap.job", "a1", request_digest="c1", estimated_cost=5)
    sl.reserve(db, "runP", "cap.job", "a1")
    sl.mark_submitted(db, "runP", "cap.job", "a1", "remote-cap-1")
    sl.mark_terminal(db, "runP", "cap.job", "a1", "failed")
    p4 = sl.plan(db, "runP", "cap.job", "a4", request_digest="c4",
                 estimated_cost=5, attempt_no=4)
    check("attempt:retry beyond repair cap refused",
          p4.get("reason_code") == "REPAIR_CAP", p4.get("reason_code"))


def scenario_concurrent_approved_retries(sl, sb):
    """SC-15: N workers race ONE approved retry -> one dispatch, one paid entry.

    The retry is already approved: attempt a1 is known-failed, so a2 is the
    legitimate retry. Every worker calls plan() for a2 at the same instant, and
    the winner alone reserves and submits. Exactly one allocation may commit;
    the ledger's own summary (not a harness counter) reports the dispatches and
    the money, so a broken guard shows up as two calls and double the cost.
    """
    db = str(Path(sb.env["HOME"]).parent / "concurrent" / "spend.db")
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    sl.init_run(db, "runC", ceiling=1000, repair_cap=2)
    sl.plan(db, "runC", "music.job", "a1", request_digest="d1", estimated_cost=5)
    sl.reserve(db, "runC", "music.job", "a1")
    sl.mark_submitted(db, "runC", "music.job", "a1", "remote-c-1")
    sl.mark_terminal(db, "runC", "music.job", "a1", "failed")
    before = sl.summary(db, "runC")["evidence"]["counts"]["number_of_generation_calls"]

    workers, gate = 8, threading.Barrier(8)
    outcomes = []

    def worker(_i):
        try:
            gate.wait(timeout=30)
            out = sl.plan(db, "runC", "music.job", "a2", request_digest="d2",
                          estimated_cost=5, attempt_no=2)
        except Exception as exc:  # noqa: BLE001 - a raise is a refusal to record
            out = {"outcome": "raised", "reason_code": type(exc).__name__}
        if out.get("outcome") == "ok":
            sl.reserve(db, "runC", "music.job", "a2")
            sl.mark_submitted(db, "runC", "music.job", "a2", "remote-c-2")
        outcomes.append(out)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    winners = [o for o in outcomes if o.get("outcome") == "ok"]
    losers = [o for o in outcomes if o.get("outcome") != "ok"]
    check("sc15:exactly-one-dispatch-under-concurrency",
          len(winners) == 1
          and winners[0].get("attempt_id") == "a2"
          and len(outcomes) == workers,
          "%d of %d workers allocated (%s)"
          % (len(winners), len(outcomes),
             [o.get("attempt_id") for o in winners]))
    check("sc15:every-loser-refused-as-duplicate",
          len(losers) == workers - 1
          and all(o.get("reason_code") == "DUPLICATE_ATTEMPT" for o in losers),
          "refusals=%s" % sorted({o.get("reason_code") for o in losers}))

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE run_id=? AND logical_key=?",
            ("runC", "music.job")).fetchone()[0]
        paid = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE run_id=? AND logical_key=? "
            "AND attempt_no=2", ("runC", "music.job")).fetchone()[0]
    finally:
        conn.close()
    check("sc15:one-new-attempt-row-committed",
          rows == 2 and paid == 1,
          "%d job rows for the logical key, %d at attempt 2" % (rows, paid))

    summary = sl.summary(db, "runC")["evidence"]
    after = summary["counts"]["number_of_generation_calls"]
    check("sc15:one-paid-ledger-entry",
          after - before == 1 and summary["committed_cost"] == 5,
          "generation calls %d -> %d, committed cost %s"
          % (before, after, summary["committed_cost"]))

def scenario_terminal_not_delivered(ss, sb):
    """A02: all-parked / all-failed / empty / mixed never report delivered.

    Every terminal shape the acceptance row names is exercised separately: a
    uniform park, a uniform failure, a run with no stages at all, and a MIXED
    run where some stages completed while others did not. In no shape may the
    stage table reach all-COMPLETE, and a wake can never promote a failed or
    parked stage straight to COMPLETE.
    """
    base = Path(sb.env["HOME"]).parent / "terminal"
    base.mkdir(parents=True, exist_ok=True)
    st = ss.Store(str(base / "state.db"))

    # -- all-parked -> must NOT look delivered ----------------------------
    st.init_run("runT", CANONICAL_STAGES)
    for s in CANONICAL_STAGES:
        ready(st, "runT", s, "worker")
        st.claim("runT", s, "worker")
        st.transition("runT", s, "PARKED", "worker", reason="operator park")
    states = [st.get("runT", s)["state"] for s in CANONICAL_STAGES]
    check("terminal:all-parked never delivered",
          all(x == "PARKED" for x in states) and "COMPLETE" not in states,
          "%d stages parked" % len(states))
    try:
        st.transition("runT", "music", "COMPLETE", "worker")
        parked_promoted, perr = False, "no error"
    except ss.StoreError as e:
        parked_promoted, perr = e.code == "ILLEGAL_TRANSITION", e.code
    check("terminal:parked stage cannot be promoted to COMPLETE",
          parked_promoted, perr)

    # -- all-failed -> no COMPLETE, and nothing can be promoted -----------
    st.init_run("runF", CANONICAL_STAGES)
    for s in CANONICAL_STAGES:
        ready(st, "runF", s, "worker")
        st.claim("runF", s, "worker")
        st.transition("runF", s, "FAILED_BLOCKED", "worker", reason="provider refused")
    fstates = [st.get("runF", s)["state"] for s in CANONICAL_STAGES]
    check("terminal:all-failed never delivered",
          all(x == "FAILED_BLOCKED" for x in fstates) and "COMPLETE" not in fstates,
          "%d stages failed" % len(fstates))
    try:
        st.transition("runF", "music", "COMPLETE", "worker")
        promoted, ferr = False, "no error"
    except ss.StoreError as e:
        promoted, ferr = e.code == "ILLEGAL_TRANSITION", e.code
    check("terminal:failed stage cannot be promoted to COMPLETE", promoted, ferr)

    # -- empty run -> no stage exists, so none can be complete ------------
    st.init_run("runE", [])
    missing = 0
    for s in CANONICAL_STAGES:
        try:
            st.get("runE", s)
        except ss.StoreError as e:
            if e.code == "NOT_FOUND":
                missing += 1
    check("terminal:empty run has no complete stages",
          missing == len(CANONICAL_STAGES),
          "%d/%d stages absent" % (missing, len(CANONICAL_STAGES)))
    try:
        st.get("runEMPTY", "music")
        empty_ok, err = False, "no error"
    except ss.StoreError as e:
        empty_ok = e.code == "NOT_FOUND"
        err = e.code
    check("terminal:empty/unknown stage = actionable state error", empty_ok, err)

    # -- mixed -> genuinely mixed, still not all-complete -----------------
    st.init_run("runM", CANONICAL_STAGES)
    half = len(CANONICAL_STAGES) // 2
    for i, s in enumerate(CANONICAL_STAGES):
        ready(st, "runM", s, "worker")
        st.claim("runM", s, "worker")
        if i < half:
            st.transition("runM", s, "COMPLETE", "worker")
        else:
            st.transition("runM", s, "FAILED_BLOCKED", "worker", reason="provider refused")
    mstates = [st.get("runM", s)["state"] for s in CANONICAL_STAGES]
    complete = [x for x in mstates if x == "COMPLETE"]
    check("terminal:mixed run is genuinely mixed",
          len(complete) == half and len(complete) < len(mstates),
          "%d complete, %d not" % (len(complete), len(mstates) - len(complete)))
    check("terminal:mixed never reports all-complete",
          len(complete) != len(CANONICAL_STAGES),
          "complete=%d of %d" % (len(complete), len(CANONICAL_STAGES)))
    try:
        st.transition("runM", CANONICAL_STAGES[half], "COMPLETE", "worker")
        mixed_promoted, merr = False, "no error"
    except ss.StoreError as e:
        mixed_promoted, merr = e.code == "ILLEGAL_TRANSITION", e.code
    check("terminal:mixed failed member cannot be promoted", mixed_promoted, merr)
    st.close()


def scenario_event_continuation(ss, sb):
    """A03: an accepted event continues the SAME run across a restart, with its
    original attempt ordinal, exactly once.

    Enqueue a continuation for one work item, replay the same event (no second
    row), close and reopen the store (a restart), then resume: the pending row
    is claimed once with its original attempt_id, a second resume claims
    nothing, and the event ordinals show enqueue BEFORE resume and carry the
    same identity.
    """
    base = Path(sb.env["HOME"]).parent / "continuation"
    base.mkdir(parents=True, exist_ok=True)
    db = str(base / "state.db")
    digest, attempt = "digest-music-1", "a7"

    st = ss.Store(db)
    st.init_run("runC", CANONICAL_STAGES)
    first = st.enqueue_continuation("runC", "music", "dispatch",
                                    request_digest=digest, attempt_id=attempt)
    row = first.get("continuation") or {}
    check("continuation:event enqueues one pending row",
          first.get("created") is True and row.get("state") == "pending"
          and row.get("attempt_id") == attempt,
          "created=%s state=%s attempt=%s"
          % (first.get("created"), row.get("state"), row.get("attempt_id")))

    replay = st.enqueue_continuation("runC", "music", "dispatch",
                                     request_digest=digest, attempt_id=attempt)
    check("continuation:replayed event adds no second row",
          replay.get("created") is False
          and (replay.get("continuation") or {}).get("id") == row.get("id")
          and (replay.get("continuation") or {}).get("attempt_id") == attempt,
          "created=%s attempt=%s"
          % (replay.get("created"),
             (replay.get("continuation") or {}).get("attempt_id")))
    st.close()

    # -- restart: a brand-new Store over the same file --------------------
    st2 = ss.Store(db)
    pending = st2.scan_pending_continuations("runC")
    check("continuation:restart finds the same pending work",
          len(pending) == 1 and pending[0].get("attempt_id") == attempt
          and pending[0].get("identity") == digest,
          "%d pending attempt=%s" % (len(pending),
                                     pending[0].get("attempt_id") if pending else None))

    claimed = st2.resume_continuations("runC", "worker-restart")
    check("continuation:restart resumes with the original attempt ordinal",
          len(claimed) == 1 and claimed[0].get("attempt_id") == attempt
          and claimed[0].get("state") == "claimed"
          and claimed[0].get("claimed_by") == "worker-restart",
          "%d claimed attempt=%s"
          % (len(claimed), claimed[0].get("attempt_id") if claimed else None))

    again = st2.resume_continuations("runC", "worker-restart")
    check("continuation:second restart claims nothing (exactly once)",
          again == [], "%d claimed on replay" % len(again))

    kinds = [e[1] for e in st2.events("runC")]
    resumes = [e[2] for e in st2.events("runC") if e[1] == "continuation-resume"]
    check("continuation:event ordinals enqueue then resume",
          "continuation-enqueue" in kinds and "continuation-resume" in kinds
          and kinds.index("continuation-enqueue") < kinds.index("continuation-resume"),
          "kinds=%s" % kinds[-4:])
    check("continuation:resume event carries the same identity",
          resumes == [digest], "resume details=%s" % resumes)
    st2.close()


def run(mode, core_root, out, vector_info):
    banner = "multi-run canary %s (real core modules from %s)" % (mode, core_root)
    print(banner)
    with cc.Sandbox() as sb:
        ss, sl = resolve_core(core_root)
        scenario_tenant_isolation(ss, sl, sb)
        scenario_fair_supervision(ss, sb)
        scenario_lease_single_writer(ss, sb)
        scenario_attempt_identity(sl, sb)
        scenario_concurrent_approved_retries(sl, sb)
        scenario_event_continuation(ss, sb)
        scenario_terminal_not_delivered(ss, sb)

        receipt = {
            "schema": "blackceo.skill75.canary.multi-run/v1",
            "unit": "SFR-007",
            "mode": mode,
            "core_root": str(core_root),
            "vector": vector_info,
            "results": RESULTS,
            "sandbox_shim_log": sb.shim_entries(),
            "live_channel_provider_rows": {
                "status": "BLOCKED_NEEDS_AUTHORIZATION",
                "blocker": "authorized live Telegram/OpenClaw-app channel and "
                           "provider acceptance run (spec 15.2 minimal authorized "
                           "run under the existing spending ceiling) is OUTSIDE "
                           "this unit's write surface: no production/client "
                           "writes, no paid jobs, no client-fleet rollout. "
                           "Harnesses are ready; live execution waits for an "
                           "explicit GO and the pinned vector.",
                "claims_now": "none",
            },
            "boundary": ("state_store + spend_ledger driven from the pinned "
                         "checkout in a scratch sandbox; every dispatch is a "
                         "ledger record, never an HTTP call; NO real run, box, "
                         "client channel or paid provider is touched; NO "
                         "acceptance point claimed."),
        }
        cc.write_json(Path(out) / ("multi-run-canary.%s.json" % mode), receipt)

    passed, failed, total = cc.summarize_checks(RESULTS)
    print("%s: %d/%d checks passed%s" % (mode, len(passed), total,
          ("" if not failed else "; FAIL: " + ", ".join(failed))))
    return 0 if not failed else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vector", required=True)
    ap.add_argument("--core-root", default=None,
                    help="checkout whose 75-drama-song-ad-factory core to drive "
                         "(default: the worktree containing this harness)")
    ap.add_argument("--tenants", type=int, default=2)
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)

    core_root = a.core_root or str(Path(__file__).resolve().parents[2])
    v = cc.load_vector(a.vector)
    vector_info = {"pinned": v.get("pinned"),
                   "pinned_at": v.get("pinned_at")}

    if a.dry_run:
        return run("dry-run", core_root, a.out, vector_info)

    ok, reason = cc.require_pinned(v)
    if not ok:
        print("REFUSED (fail-closed): %s" % reason)
        return 3
    vector_info["revisions"] = {k: v["repositories"][k].get("revision")
                               for k in v.get("repositories", {})}
    return run("real", core_root, a.out, vector_info)


if __name__ == "__main__":
    sys.exit(main())
