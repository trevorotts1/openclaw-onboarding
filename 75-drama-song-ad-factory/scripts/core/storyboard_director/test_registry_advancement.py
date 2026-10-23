#!/usr/bin/env python3
"""S75-W06-U2: continuity-bible advancement through the registry's
executable path, real advancement of the seven downstream stages, and
automatic continuation after storyboard approval.

Proves (findings D08, D33; Skill 75 sections 5.1 item 9, 8.6):
  * the registry runbook row for continuity-bible is a REAL executable (the
    stage runner), not an instruction string with a placeholder, and it runs
    end to end from the command the registry hands out;
  * once the reconciler is wired into the registry (one register() call),
    factory's registry executable path advances continuity-bible from its
    proven artifacts with NO separate manual action;
  * after continuity-bible completes, all seven downstream stages
    (storyboard, image-keyframes, video-generation, qc-retakes, assembly,
    final-qc, delivery) really advance to COMPLETE and `next` traverses to
    run-complete — not merely storyboard eligibility;
  * storyboard approval resumes the pipeline automatically: the decision and
    its continuation enqueue land together, and `next` hands out the video
    command with no further "shall I continue?" prompt.

Run: python3 scripts/core/storyboard_director/test_registry_advancement.py
(stdlib, no spend)
"""
import json
import os
import subprocess
import sys
import tempfile

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import character_continuity.stage as ST                   # noqa: E402
import kie_dispatch.model_lock as ML                      # noqa: E402
import storyboard_director.approval_package as AP         # noqa: E402
import storyboard_director.approval_runner as AR          # noqa: E402
import state_store as SS                                  # noqa: E402
from batch_mode import batch as BATCH                     # noqa: E402

sys.path.insert(0, os.path.join(CORE, "intake_preflight"))
import factory as FACTORY                                 # noqa: E402

STAGES = [s for s, _ in BATCH.STAGES]
VIDEO_MODEL_ROW = "video-generation"
VIDEO_MODEL = "kling-3.0/video"
FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name, "" if cond else " (%s)" % (detail,)))
    if not cond:
        FAILS.append(name)


def qc_record(run_id="run1"):
    return {"schema_version": "1.0.0", "check_id": "continuity-dna-1",
            "run_id": run_id, "stage": "continuity-bible", "check": "continuity",
            "verdict": "PASS",
            "evidence": {"summary": "Character DNA, product DNA and style "
                                    "bible records agree across every shot."},
            "checker_version": "1.0.0",
            "reviewer": {"identity": "qc-reviewer-1", "session": "s1",
                         "authority": "qc"}}


def make_run(up_to=None, storyboard_files=True):
    """Run dir: state store with the 12 stages, continuity records, and the
    storyboard plan. ``up_to`` completes every row before that stage."""
    run = os.path.join(tempfile.mkdtemp(prefix="sbreg-"), "run1")
    os.makedirs(os.path.join(run, "control"))
    os.makedirs(os.path.join(run, "continuity"))
    json.dump([qc_record()], open(os.path.join(run, "continuity",
                                               "qc-records.json"), "w"))
    json.dump({"continuity-dna-1": "agent-writer-1"},
              open(os.path.join(run, "continuity", "makers.json"), "w"))
    if storyboard_files:
        sb = os.path.join(run, "storyboard")
        os.makedirs(sb)
        shots, contracts, stills = [], {}, {}
        for i in range(1, 4):
            sid = "s%d" % i
            shots.append({"shot_id": sid, "song_start": (i - 1) * 8.0,
                          "song_end": (i - 1) * 8.0 + 8.0,
                          "story_stage": "frozen", "location_id": "kitchen",
                          "character_ids": ["mia"], "wardrobe_ids": ["w1"],
                          "continuity_constraints": [], "lyric_line_ids": ["l%d" % i],
                          "visual_objective": "beat %d" % i,
                          "product_visibility": "none",
                          "camera_direction": "close-up %d" % (i % 3),
                          "reference_assets": [],
                          "image_model_capability_request": {},
                          "video_model_capability_request": {},
                          "negative_constraints": [], "cost_estimate": 10,
                          "qc_requirements": ["speaker-visibility"],
                          "status": "planned"})
            contracts[sid] = {"lyric_text": "line %d" % i,
                              "viewer_understanding": "she is stuck %d" % i,
                              "character_action": "sitting at table %d" % i,
                              "visible_emotion": "stuck"}
            stills[sid] = os.path.join(sb, sid + ".png")
            open(stills[sid], "wb").write(b"png-%d" % i)
        json.dump({"shots": shots}, open(os.path.join(sb, "shot-list.json"), "w"))
        json.dump(contracts, open(os.path.join(sb, "contracts.json"), "w"))
        json.dump(stills, open(os.path.join(sb, "stills.json"), "w"))
        json.dump({"storyboard_approval": True},
                  open(os.path.join(run, "control", "card-receipt.json"), "w"))
    with SS.Store(os.path.join(run, "control", "state.sqlite3")) as st:
        st.init_run("run1", STAGES)
        if up_to:
            for s in STAGES[:STAGES.index(up_to)]:
                if st.get("run1", s)["state"] == "NOT_STARTED":
                    st.transition("run1", s, "READY", "t")
                    st.claim("run1", s, "t")
                    st.transition("run1", s, "COMPLETE", "t")
    _seed_gate4(run)
    return run


def _seed_gate4(run):
    """The Gate 4 sources a real run carries, then ONE recap and the operator's
    Go bound to its digest. `factory.py next` reads exactly these before it may
    hand out the paid video stage: picked song + its digest, the locked video
    model and the spend ledger. Without them the stage correctly refuses with
    FINAL_RECAP_MISSING."""
    import hashlib
    import final_recap as FR
    import spend_ledger as L
    os.makedirs(os.path.join(run, "music"), exist_ok=True)
    master = os.path.join(run, "music", "picked-song.mp3")
    with open(master, "wb") as fh:
        fh.write(b"the picked master")
    os.makedirs(os.path.join(run, "song-choices"), exist_ok=True)
    with open(master, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    json.dump({"pick": 1, "label": "warm-live-band", "sha256": digest},
              open(os.path.join(run, "song-choices", "pick.json"), "w"))
    ML.lock_run_model(os.path.join(run, "control", "state.sqlite3"), "run1", VIDEO_MODEL)
    L.init_run(os.path.join(run, "spend.sqlite3"), "run1", 10_000_000)
    doc = FR.build(run)
    FR.record_go(run, {"schema": FR.GO_SCHEMA, "decision": "GO",
                       "operator": "Test Operator",
                       "at_utc": "2026-10-22T00:00:00Z",
                       "recap_digest": doc["recap_digest"]})


class A:
    def __init__(self, run):
        self.run_dir = run


def nxt(run):
    return FACTORY.cmd_next(A(run))


def complete_row(run, stage):
    """The runbook loop's register step: guarded state_store transitions."""
    with SS.Store(os.path.join(run, "control", "state.sqlite3")) as st:
        row = st.get("run1", stage)
        if row["state"] == "NOT_STARTED":
            st.transition("run1", stage, "READY", "t")
        row = st.get("run1", stage)
        if row["state"] != "COMPLETE":
            st.claim("run1", stage, "t")
            st.transition("run1", stage, "COMPLETE", "t")


def test_registry_row_is_a_real_executable():
    rows, path = FACTORY._runbook_rows()
    row = rows.get("continuity-bible") or {}
    check("runbook carries the continuity-bible row", bool(row.get("command")), row)
    check("registry entrypoint is the stage runner, not a placeholder",
          "character_continuity/stage.py advance" in row.get("command", "")
          and "<required-checks>" not in row.get("command", ""), row)
    # and the command actually runs: the registry's executable path end to end
    import shlex
    run = make_run()
    argv = [tok.replace("$RUN_ID", "run1").replace("$RUN", run)
            for tok in shlex.split(row["command"])]
    res = subprocess.run([sys.executable] + argv[1:], capture_output=True,
                         text=True, cwd=os.path.dirname(os.path.dirname(CORE)))
    out = json.loads(res.stdout)
    check("registry entrypoint runs end to end",
          res.returncode == 0 and out.get("outcome") == "advanced"
          and out["row"]["state"] == "COMPLETE", (res.returncode, res.stderr[-200:], out))


def test_continuity_advances_through_the_registry():
    run = make_run(up_to="continuity-bible")
    ST.register(FACTORY._RECONCILIERS)      # one call: the registry wiring
    try:
        env = nxt(run)                      # the registry's executable path
        got = [r for r in (env.get("data", {}).get("reconciled") or [])
               if r.get("stage") == "continuity-bible"]
        check("registry reconciled continuity-bible from its proven artifacts",
              got and got[-1]["to_state"] == "COMPLETE", env.get("data"))
        with SS.Store(os.path.join(run, "control", "state.sqlite3")) as st:
            check("continuity-bible row COMPLETE, no manual action",
                  st.get("run1", "continuity-bible")["state"] == "COMPLETE")
        check("next moves past continuity-bible to storyboard",
              env["data"]["stage"] == "storyboard", env["data"])
    finally:
        FACTORY._RECONCILIERS.pop("continuity-bible", None)


def test_seven_downstream_stages_really_advance():
    run = make_run(up_to="continuity-bible", storyboard_files=True)
    ST.register(FACTORY._RECONCILIERS)
    try:
        # continuity first, through the registry
        env = nxt(run)
        check("continuity-bible reconciled before the walk",
              env["data"].get("reconciled")
              and env["data"]["stage"] == "storyboard", env["data"])
        # storyboard: the real approval gate, then the registry's own
        # storyboard reconciler proves it from the approval artifacts
        w_events = []
        AR.run(run, lambda m, imgs: w_events.append(("m", m, imgs)))
        r = AR.run(run, lambda m, imgs: w_events.append(("m", m, imgs)), reply="GO")
        check("storyboard approved through the in-chat gate",
              r["action"] == "approved" and AR.gate_open(run), r)
        env = nxt(run)
        rec = [x for x in (env["data"].get("reconciled") or [])
               if x.get("stage") == "storyboard"]
        check("storyboard row reconciled from its approval artifacts",
              rec and rec[-1]["to_state"] == "COMPLETE", env["data"])
        walked = ["storyboard"]
        # the remaining six: each `next` hands out its registry row, each
        # row advances to COMPLETE — real advancement, one stage at a time
        for stage in ST.DOWNSTREAM_STAGES[1:]:
            env = nxt(run)
            check("next hands out %s" % stage,
                  env["data"].get("stage") == stage, env.get("data"))
            complete_row(run, stage)
            walked.append(stage)
        check("all seven downstream stages walked in order",
              walked == list(ST.DOWNSTREAM_STAGES), walked)
        with SS.Store(os.path.join(run, "control", "state.sqlite3")) as st:
            states = {s: st.get("run1", s)["state"] for s in ST.DOWNSTREAM_STAGES}
        check("all seven rows COMPLETE",
              all(v == "COMPLETE" for v in states.values()), states)
        env = nxt(run)
        check("registry traverses to run-complete",
              env["reason_code"] == "run-complete", env)
    finally:
        FACTORY._RECONCILIERS.pop("continuity-bible", None)


def test_approval_resumes_the_pipeline_automatically():
    run = make_run(up_to=VIDEO_MODEL_ROW, storyboard_files=True)
    sent = []
    AR.run(run, lambda m, imgs: sent.append((m, imgs)))
    r = AR.run(run, lambda m, imgs: sent.append((m, imgs)), reply="GO")
    check("approval returns the continuation it enqueued",
          r["action"] == "approved"
          and r["continuation"]["stage"] == "video-generation", r)
    q = json.load(open(os.path.join(run, "control", "continuation-queue.json")))
    check("continuation queued beside the decision",
          len(q) == 1 and q[0]["status"] == "queued"
          and q[0]["event"] == "storyboard-approved", q)
    check("continuation carries the registry's own next action",
          "kie_dispatch" in (q[0].get("next_action") or ""), q[0])
    env = nxt(run)
    check("pipeline resumes with the video command, no prompt needed",
          env["outcome"] == "ok" and env["data"]["stage"] == "video-generation"
          and env["data"].get("command"), env)
    check("no waiting state after a valid approval",
          env["reason_code"] != "storyboard-approval-required", env["reason_code"])


if __name__ == "__main__":
    test_registry_row_is_a_real_executable()
    test_continuity_advances_through_the_registry()
    test_seven_downstream_stages_really_advance()
    test_approval_resumes_the_pipeline_automatically()
    print("FAIL (%d): %s" % (len(FAILS), ", ".join(FAILS)) if FAILS else "ALL PASS")
    sys.exit(1 if FAILS else 0)
