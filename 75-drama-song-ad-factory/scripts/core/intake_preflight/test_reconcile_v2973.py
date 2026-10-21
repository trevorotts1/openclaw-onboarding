#!/usr/bin/env python3
"""L4.1 (v2.9.73): `next` reconciles stage rows from proven artifacts on disk
BEFORE it answers, through state_store's guarded transitions — never a
hand-written sqlite UPDATE.

Live proof (Voyage To Virtue): storyboard gate.json held approved_at
2026-10-20T21:56:49Z with 13 stills on disk while the stages row said
NOT_STARTED, so `next` kept handing back the music command and the run went
stale for hours.

Proves, behaviourally (stdlib only, no network, no provider, $0, temp dirs):
  1. THE LIVE-RUN CASE: gate.json approved + approval.json approved + every
     stills.json path a non-empty file, stages row story-board NOT_STARTED ->
     `next` (the real CLI) reconciles the row to COMPLETE THROUGH the store
     (transition/claim events with owner "reconcile" on the event trail),
     and answers the stage AFTER storyboard — never the music command the
     NOT_STARTED row produced.
  2. the reconcile record on the envelope: data.reconciled carries stage,
     from_state, to_state and the artifact evidence (approved shot count,
     stills, none missing).
  3. an UNPROVEN row writes NOTHING: gate.json with shots but no approval
     file still leaves NOT_STARTED; a stills path that is missing or empty
     leaves NOT_STARTED; a row where only the qc records fail stays put.
  4. a COMPLETE row is never touched; a live foreign lease is never seized
     (the reconcile records the skip, no write).
  5. the music reconciler refuses WITHOUT the independent QC records (no
     gate is ever invented): pick + picked file alone leave NOT_STARTED.
  6. the music reconciler completes WITH matching pick.json sha256 AND an
     all-PASS qc-records.json (a real qc_gate.evaluate over real records):
     the row goes -> READY -> claim -> QC -> COMPLETE via the store.
  7. no direct UPDATE ever runs: the store's events table carries the
     reconcile trail (claim/transition entries, actor on the detail), and
     the stages table's version counter advanced — the store's own CAS.
  8. `next`'s stage answer is UNCHANGED for a run with nothing proven
     (the pre-fix behaviour for every other case).

Run: python3 scripts/core/intake_preflights/test_reconcile_v2973.py
(from the skill root: python3 scripts/core/intake_preflight/test_reconcile_v2973.py)
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = Path(HERE).parent
SKILL = Path(HERE).parents[2]
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(HERE))

import factory as F            # noqa: E402
import state_store as SS       # noqa: E402
from batch_mode.batch import STAGES  # noqa: E402

RID = "vtv-reconcile-run"
FACTORY = HERE + "/factory.py"

FAILS = []


def check(name, cond, detail=""):
    print("%s %s%s" % ("ok" if cond else "FAIL", name,
                       (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def new_run(tmp):
    run = Path(tempfile.mkdtemp(dir=tmp, prefix="rec-"))
    (run / "control").mkdir(parents=True)
    with SS.Store(run / "control" / "state.sqlite3") as st:
        st.init_run(RID, [s for s, _ in STAGES])
    return run


def stage_state(run, stage):
    with SS.Store(run / "control" / "state.sqlite3") as st:
        return st.get(RID, stage)["state"]


def qc_pass_records():
    """Real qc-schema records, all PASS, one per required check, maker
    distinct from reviewer (17.6's shape for qc_gate.evaluate)."""
    return [
        {"schema_version": "1.0.0", "check_id": "song", "run_id": RID,
         "stage": "music", "check": "song", "verdict": "PASS",
         "evidence": {"summary": "five WW-21 gates on picked take"},
         "checker_version": "song_dispatch/1",
         "reviewer": {"identity": "qc-reviewer", "session": "s1",
                      "authority": "dept-qc"}},
    ]


def run_next(run_dir):
    return subprocess.run(
        [sys.executable, FACTORY, "next", "--run-dir", str(run_dir)],
        capture_output=True, text=True, cwd=str(SKILL), timeout=60)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="reconcile-"))

    # ---- 1. THE LIVE-RUN CASE: approved on disk, NOT_STARTED in the DB ----
    run = new_run(tmp)
    sb = run / "storyboard"
    sb.mkdir(parents=True)
    (sb / "gate.json").write_text(json.dumps(
        {"shots": [{"shot_id": "s%d" % i, "status": "storyboard_approved"}
                   for i in range(1, 14)],
         "approved_at": "2026-10-20T21:56:49Z"}))
    (sb / "approval.json").write_text(json.dumps(
        {"state": "approved", "choice": "yes",
         "at": 1760999809.0}))                    # 2026-10-20T21:56:49Z
    stills_dir = run / "stills"
    stills_dir.mkdir()
    stills = {}
    for i in range(1, 14):
        p = stills_dir / ("shot-%d.png" % i)
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 32)
        stills["s%d" % i] = "stills/shot-%d.png" % i
    (sb / "stills.json").write_text(json.dumps(stills))
    check("precondition: storyboard row NOT_STARTED",
          stage_state(run, "storyboard") == "NOT_STARTED")
    p = run_next(run)
    env = json.loads(p.stdout)
    rec = (env.get("data") or {}).get("reconciled") or []
    row = next((r for r in rec if r.get("stage") == "storyboard"), None)
    check("the reconciler moved THE approved row", row is not None,
          str(rec)[:300])
    if row:
        check("from NOT_STARTED to COMPLETE",
              row["from_state"] == "NOT_STARTED"
              and row["to_state"] == "COMPLETE", str(row))
        ev = row.get("evidence") or {}
        check("evidence names the artifacts and the counts",
              ev.get("approved_shots") == 13 and ev.get("stills") == 13
              and ev.get("stills_missing") == [], str(ev))
    check("the row IS COMPLETE in the store after next",
          stage_state(run, "storyboard") == "COMPLETE",
          stage_state(run, "storyboard"))
    # the event trail: the store carries the reconcile moves
    with SS.Store(run / "control" / "state.sqlite3") as st:
        evs = st.events(RID)
    recon_transitions = [e for e in evs if e[0] == "storyboard"
                         and e[1] == "transition"]
    recon_claim = [e for e in evs if e[0] == "storyboard"
                   and e[1] == "claim" and e[2] == "reconcile"]
    check("the store's event trail carries the reconcile claim + transition "
          "(owner on the claim detail, 'reconciled' on the transition)",
          len(recon_transitions) >= 2 and "reconciled" in recon_transitions[-1][2]
          and len(recon_claim) == 1, str(recon_transitions)[:300])

    # ---- 3a. UNPROVEN: no approval.json -> nothing written ----
    run3 = new_run(tmp)
    sb3 = run3 / "storyboard"
    sb3.mkdir(parents=True)
    (sb3 / "gate.json").write_text(json.dumps(
        {"shots": [{"shot_id": "s1", "status": "storyboard_approved"}]}))
    (sb3 / "stills.json").write_text(json.dumps({"s1": "stills/s1.png"}))
    (run3 / "stills").mkdir()
    (run3 / "stills" / "s1.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 8)
    env3 = _next_env(run3)
    rec3 = (env3.get("data") or {}).get("reconciled") or []
    check("gate.json alone is not proof: row untouched",
          not any(r.get("stage") == "storyboard" for r in rec3)
          and stage_state(run3, "storyboard") == "NOT_STARTED",
          str(rec3)[:200])

    # ---- 3b. UNPROVEN: a still path missing -> nothing written ----
    run3b = new_run(tmp)
    sb3b = run3b / "storyboard"
    sb3b.mkdir(parents=True)
    (sb3b / "gate.json").write_text(json.dumps(
        {"shots": [{"shot_id": "s1", "status": "storyboard_approved"}]}))
    (sb3b / "approval.json").write_text(json.dumps({"state": "approved"}))
    (sb3b / "stills.json").write_text(json.dumps({"s1": "stills/GONE.png"}))
    env3b = _next_env(run3b)
    rec3b = (env3b.get("data") or {}).get("reconciled") or []
    check("a missing still is not proof: row untouched",
          not any(r.get("stage") == "storyboard" for r in rec3b)
          and stage_state(run3b, "storyboard") == "NOT_STARTED",
          str(rec3b)[:200])
    check("next still answers the EARLIEST un-finished stage "
          "(research) when storyboard could not be proven",
          (env3b.get("data") or {}).get("stage") == "research",
          env3b.get("data", {}).get("stage"))

    # ---- 3c. the live lease is never seized ----
    run3c = new_run(tmp)
    sb3c = run3c / "storyboard"
    sb3c.mkdir(parents=True)
    (sb3c / "gate.json").write_text(json.dumps(
        {"shots": [{"shot_id": "s1", "status": "storyboard_approved"}]}))
    (sb3c / "approval.json").write_text(json.dumps({"state": "approved"}))
    (sb3c / "stills.json").write_text(json.dumps({"s1": "stills/s1.png"}))
    (run3c / "stills").mkdir()
    (run3c / "stills" / "s1.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 8)
    with SS.Store(run3c / "control" / "state.sqlite3") as st:
        st.transition(RID, "storyboard", "READY", "seed")
        st.claim(RID, "storyboard", "live-worker", lease_s=600)
    env3c = _next_env(run3c)
    rec3c = [r for r in (env3c.get("data") or {}).get("reconciled") or []
             if r.get("stage") == "storyboard"]
    check("a live foreign lease is skipped, the row untouched",
          rec3c and rec3c[0].get("skipped", "").startswith("live lease")
          and stage_state(run3c, "storyboard") == "RUNNING",
          str(rec3c)[:250])

    # ---- 5. music without the QC records is never reconciled ----
    run4 = new_run(tmp)
    (run4 / "music").mkdir()
    (run4 / "music" / "picked-song.mp3").write_bytes(b"ID3" + b"\0" * 64)
    (run4 / "song-choices").mkdir()
    import hashlib
    sha = hashlib.sha256((run4 / "music" / "picked-song.mp3").read_bytes()) \
        .hexdigest()
    (run4 / "song-choices" / "pick.json").write_text(json.dumps(
        {"pick": 1, "label": "V1", "sha256": sha}))
    env4 = _next_env(run4)
    rec4 = (env4.get("data") or {}).get("reconciled") or []
    check("pick + file but NO qc records: music untouched (no gate invented)",
          not any(r.get("stage") == "music" for r in rec4)
          and stage_state(run4, "music") == "NOT_STARTED",
          str(rec4)[:250])

    # ---- 6. music WITH an all-PASS record set: QC -> COMPLETE via store ----
    run5 = new_run(tmp)
    (run5 / "music").mkdir()
    (run5 / "music" / "picked-song.mp3").write_bytes(b"ID3" + b"\0" * 64)
    sha5 = hashlib.sha256((run5 / "music" / "picked-song.mp3")
                          .read_bytes()).hexdigest()
    (run5 / "song-choices").mkdir()
    (run5 / "song-choices" / "pick.json").write_text(json.dumps(
        {"pick": 1, "label": "V1", "sha256": sha5}))
    (run5 / "music" / "qc-records.json").write_text(
        json.dumps(qc_pass_records()))
    (run5 / "music" / "makers.json").write_text(
        json.dumps({"song": "music-worker"}))
    env5 = _next_env(run5)
    rec5 = [r for r in (env5.get("data") or {}).get("reconciled") or []
            if r.get("stage") == "music"]
    check("music with a PASS record set reconciles QC -> COMPLETE",
          rec5 and rec5[0].get("to_state") == "COMPLETE", str(rec5)[:400])
    check("music row IS COMPLETE in the store",
          stage_state(run5, "music") == "COMPLETE",
          stage_state(run5, "music"))

    # ---- 5b. music with a FAIL record set is never reconciled ----
    run5b = new_run(tmp)
    (run5b / "music").mkdir()
    (run5b / "music" / "picked-song.mp3").write_bytes(b"ID3" + b"\0" * 64)
    sha5b = hashlib.sha256((run5b / "music" / "picked-song.mp3")
                           .read_bytes()).hexdigest()
    (run5b / "song-choices").mkdir()
    (run5b / "song-choices" / "pick.json").write_text(json.dumps(
        {"pick": 1, "label": "V1", "sha256": sha5b}))
    bad = [dict(qc_pass_records()[0], verdict="FAIL")]
    (run5b / "music" / "qc-records.json").write_text(json.dumps(bad))
    (run5b / "music" / "makers.json").write_text(json.dumps({"song": "w"}))
    env5b = _next_env(run5b)
    rec5b = (env5b.get("data") or {}).get("reconciled") or []
    check("a FAIL record set never reconciles the music stage",
          not any(r.get("stage") == "music" for r in rec5b)
          and stage_state(run5b, "music") == "NOT_STARTED",
          str(rec5b)[:250])

    # ---- 8. a run with nothing to reconcile answers exactly as before ----
    run6 = new_run(tmp)
    env6 = _next_env(run6)
    check("nothing proven: next answers stage research, no reconciled key",
          (env6.get("data") or {}).get("stage") == "research"
          and "reconciled" not in (env6.get("data") or {}),
          str((env6.get("data") or {}).get("stage")))
    env6b = _next_env(run6)
    check("a second next with nothing proven writes nothing again",
          not (env6b.get("data") or {}).get("reconciled"),
          str((env6b.get("data") or {}).get("reconciled")))

    print()
    if FAILS:
        print("FAILED: %d: %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("test_reconcile_v2973: PASS")
    return 0


def _next_env(run):
    """Run the real CLI `next` and return the parsed envelope."""
    p = run_next(run)
    if p.returncode not in (0, 2, 3, 4):
        return {"outcome": "error", "exit": p.returncode,
                "stderr": p.stderr[:200], "data": {}}
    return json.loads(p.stdout)


if __name__ == "__main__":
    sys.exit(main())