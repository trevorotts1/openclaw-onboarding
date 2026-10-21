#!/usr/bin/env python3
"""Heartbeat (skill75 v2.9.77): run_watch.py proves each thing the keepalive
must do, on synthetic runs only -- no network, no provider, no real clock.

Proves, behaviourally (stdlib only, real state_store + real spend_ledger
fixtures in a temp dir):
  1. a normal stage update reads the current stage, its state, the elapsed
     minutes and a plain-English message (music -> "your ad's music is being
     created");
  2. every pending decision is surfaced with its question and options: intake
     outstanding, an approval gate waiting on the client, a song pick offering
     its labelled versions (and NOT surfaced once pick.json exists), and a cost
     fork still on the safe default "wait" (a later "proceed" for the same fork
     supersedes it);
  3. a stall is detected when the current stage has made no progress for 30
     minutes, and when its lease has run out -- with HEARTBEAT_STALLED named and
     the exact factory.py recovery command PRINTED (never run);
  4. the 3-hour cap is anchored on the run's own start: expired, the wrap-up
     message, HEARTBEAT_EXPIRED named, --interval-check exits 10; a COMPLETE
     run says so and also stops the loop without an expiry failure;
  5. an unreadable state store is loud (HEARTBEAT_STATE_UNREADABLE), never a
     silent pass, and exits 1;
  6. the watcher never mutates the run: the state store, spend ledger,
     fork-decisions.json and run-state.json are byte-identical afterwards.

Run: python3 scripts/core/heartbeat/test_run_watch.py
"""
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(HERE))

import run_watch as RW              # noqa: E402  (unit under test)
import spend_ledger as SL           # noqa: E402  (the real 3h anchor)
import state_store as SS            # noqa: E402  (the real state schema)

FS = []


def check(name, cond, detail=""):
    print("%s %s%s" % ("ok" if cond else "FAIL", name,
                       (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FS.append(name)


#: the twelve stage ids (batch_mode/batch.py:112-125) the run carries.
STAGES = ("research", "creative-strategy", "script-lyrics", "music",
          "continuity-bible", "storyboard", "image-keyframes",
          "video-generation", "qc-retakes", "assembly", "final-qc", "delivery")

NOW = 1800000000.0          # fixed "now" for every judgement below


def iso(epoch):
    import datetime
    return datetime.datetime.fromtimestamp(
        epoch, datetime.timezone.utc).isoformat(timespec="seconds")


def make_run(tmp, name, base_ago_s=95 * 60, ledger=True):
    """A run folder with the REAL state store and the REAL spend ledger."""
    run = Path(tmp) / name
    (run / "control").mkdir(parents=True)
    with SS.Store(run / "control" / "state.sqlite3") as st:
        st.init_run(name, STAGES)
    if ledger:
        SL.init_run(str(run / "spend.sqlite3"), name, ceiling=10000)
        con = sqlite3.connect(str(run / "spend.sqlite3"))
        con.execute("UPDATE runs SET created_at=? WHERE run_id=?",
                    (iso(NOW - base_ago_s), name))
        con.commit()
        con.close()
    _age_all(run, name, NOW - base_ago_s)
    return run


def _age_all(run, run_id, stamp):
    con = sqlite3.connect(str(run / "control" / "state.sqlite3"))
    con.execute("UPDATE stages SET updated_at=? WHERE run_id=?", (stamp, run_id))
    con.commit()
    con.close()


def set_stage(run, run_id, stage, state, age_s=0, lease_in=None, owner=None,
              reason=None):
    con = sqlite3.connect(str(run / "control" / "state.sqlite3"))
    con.execute(
        "UPDATE stages SET state=?, owner=?, lease_expires=?, reason=?,"
        " updated_at=? WHERE run_id=? AND stage=?",
        (state, owner, (NOW + lease_in) if lease_in is not None else None,
         reason, NOW - age_s, run_id, stage))
    con.commit()
    con.close()


def write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def decisions_of(env, kind):
    return [d for d in env["decisions_pending"] if d["kind"] == kind]


def tree_digest(run):
    out = {}
    for p in sorted(run.rglob("*")):
        if not p.is_file() or p.suffix in (".db-shm", ".db-wal"):
            continue
        if p.name.endswith(("-shm", "-wal")):
            continue
        out[str(p.relative_to(run))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def main():
    tmp = tempfile.mkdtemp(prefix="runwatch-")

    # 1. a normal stage update ------------------------------------------------
    run = make_run(tmp, "run1")
    for s in ("research", "creative-strategy", "script-lyrics"):
        set_stage(run, "run1", s, "COMPLETE", age_s=45 * 60)
    set_stage(run, "run1", "music", "RUNNING", age_s=5 * 60, lease_in=300,
              owner="worker-1")
    env = RW.build(run, now=NOW)
    check("1: current stage is music", env["stage"] == "music", env["stage"])
    check("1: state is RUNNING", env["stage_state"] == "RUNNING")
    check("1: elapsed minutes read off the run's own start",
          env["elapsed_minutes"] == 95, env["elapsed_minutes"])
    check("1: completed stages counted", env["completed_stages"] == 3,
          env["completed_stages"])
    check("1: nothing pending on a healthy run",
          env["decisions_pending"] == [], env["decisions_pending"])
    check("1: not stalled, not expired",
          env["stalled"] is False and env["expired"] is False)
    check("1: no loud code on a healthy run", env["loud"] == [], env["loud"])
    check("1: plain-English stage phrase",
          "your ad's music is being created" in env["message_for_client"],
          env["message_for_client"])
    check("1: message carries the progress count",
          "3 of 12 steps are finished" in env["message_for_client"])

    # 2. every pending decision in front of the client ------------------------
    run = make_run(tmp, "run2")
    for s in ("research", "creative-strategy", "script-lyrics", "music",
              "continuity-bible"):
        set_stage(run, "run2", s, "COMPLETE", age_s=30 * 60)
    set_stage(run, "run2", "storyboard", "WAITING_APPROVAL", age_s=10 * 60)
    write_json(run / "control" / "run-state.json", {
        "outstanding": ["Should the second character be a man or a woman?",
                        {"id": "city", "question": "Which city is this set in?",
                         "options": ["Atlanta", "Houston"]}],
    })
    write_json(run / "control" / "fork-decisions.json", {"forks": [
        {"fork_id": "redo", "decision": "wait", "label": "Redo the opening shot",
         "cost_minor": 1500},
        {"fork_id": "redo", "decision": "proceed", "label": "Redo the opening shot",
         "cost_minor": 1500},
        {"fork_id": "more-clips", "decision": "wait",
         "label": "Make four more clips", "cost_minor": 2500,
         "reason": "cost 2500 over the remaining balance 100"},
    ]})
    env = RW.build(run, now=NOW)
    intake = decisions_of(env, "intake")
    approvals = decisions_of(env, "approval")
    forks = decisions_of(env, "fork")
    check("2: intake outstanding surfaced (2)", len(intake) == 2, intake)
    check("2: intake options carried",
          any(d["options"] == ["Atlanta", "Houston"] for d in intake), intake)
    check("2: storyboard approval surfaced", len(approvals) == 1, approvals)
    check("2: approval offers Approve / change",
          approvals and approvals[0]["options"] == ["Approve them", "Change one shot"],
          approvals)
    check("2: only the latest wait fork is surfaced (superseded skipped)",
          len(forks) == 1 and forks[0]["id"] == "more-clips", forks)
    check("2: fork question names its own label and cost",
          forks and "Make four more clips" in forks[0]["question"]
          and "$25.00" in forks[0]["question"], forks)
    msg = env["message_for_client"]
    check("2: every question is in the client message",
          all(d["question"] in msg for d in env["decisions_pending"]), msg)
    check("2: a client wait is not a stall", env["stalled"] is False)
    check("2: no failure code just because a client owes an answer",
          env["loud"] == [], env["loud"])

    # 2b. the song pick offers its labelled versions, then disappears answered
    run = make_run(tmp, "run2b")
    for s in ("research", "creative-strategy", "script-lyrics"):
        set_stage(run, "run2b", s, "COMPLETE", age_s=40 * 60)
    set_stage(run, "run2b", "music", "WAITING_APPROVAL", age_s=8 * 60)
    write_json(run / "song-choices" / "state.json", {"required": True, "offered": {
        "1": {"label": "1 - Slow Soul (strings)", "file": "a.mp3", "duration": 61},
        "2": {"label": "2 - Upbeat Pop (drums)", "file": "b.mp3", "duration": 62},
    }})
    env = RW.build(run, now=NOW)
    pick = decisions_of(env, "approval")
    check("2b: song pick surfaced with its labelled versions",
          len(pick) == 1 and pick[0]["id"] == "song-pick"
          and "1 - Slow Soul (strings)" in pick[0]["options"], pick)
    write_json(run / "song-choices" / "pick.json", {"pick": 2, "label": "2 - Upbeat Pop (drums)"})
    env = RW.build(run, now=NOW)
    check("2b: an answered song pick is not surfaced again",
          decisions_of(env, "approval") == [], env["decisions_pending"])

    # 3. stall detection ------------------------------------------------------
    run = make_run(tmp, "run3")
    for s in ("research", "creative-strategy"):
        set_stage(run, "run3", s, "COMPLETE", age_s=60 * 60)
    set_stage(run, "run3", "script-lyrics", "RUNNING", age_s=45 * 60,
              lease_in=600, owner="worker-2")
    before = tree_digest(run)
    env = RW.build(run, now=NOW)
    check("3: a 45-minute silence on the current stage is a stall",
          env["stalled"] is True, str(env))
    check("3: HEARTBEAT_STALLED is named",
          "HEARTBEAT_STALLED" in env["loud"], env["loud"])
    check("3: the recovery command is the factory's own next",
          "factory.py next --run-dir" in env["recovery_command"],
          env["recovery_command"])
    check("3: the client hears it plainly, no codes",
          "I hit a problem with the script and lyrics step" in env["message_for_client"]
          and "HEARTBEAT" not in env["message_for_client"],
          env["message_for_client"])
    check("3: a stall is not an expiry", env["expired"] is False)

    # lease ran out while the row looked fresh -> still a stall
    run = make_run(tmp, "run3b")
    set_stage(run, "run3b", "research", "COMPLETE", age_s=20 * 60)
    set_stage(run, "run3b", "creative-strategy", "RUNNING", age_s=0,
              lease_in=-60, owner="worker-3")
    env = RW.build(run, now=NOW)
    check("3b: an expired lease is a stall even on a fresh row",
          env["stalled"] is True and "HEARTBEAT_STALLED" in env["loud"], str(env))

    # a STALE row is a stall, with its recorded reason
    run = make_run(tmp, "run3c")
    set_stage(run, "run3c", "research", "STALE", age_s=0,
              reason="upstream brief changed")
    env = RW.build(run, now=NOW)
    check("3c: a STALE row is a stall naming its reason",
          env["stalled"] is True and "upstream brief changed" in env["stall_detail"],
          env["stall_detail"])

    # 4. the 3-hour cap -------------------------------------------------------
    run = make_run(tmp, "run4", base_ago_s=185 * 60)
    for s in ("research", "creative-strategy", "script-lyrics", "music",
              "continuity-bible", "storyboard", "image-keyframes",
              "video-generation", "qc-retakes", "assembly"):
        set_stage(run, "run4", s, "COMPLETE", age_s=185 * 60)
    set_stage(run, "run4", "final-qc", "RUNNING", age_s=2 * 60, lease_in=300,
              owner="worker-4")
    env = RW.build(run, now=NOW)
    check("4: 185 minutes is past the 3-hour cap", env["expired"] is True)
    check("4: HEARTBEAT_EXPIRED is named", "HEARTBEAT_EXPIRED" in env["loud"],
          env["loud"])
    check("4: the client gets the final wrap-up",
          "Time's up for this round" in env["message_for_client"]
          and "10 of 12 steps are finished" in env["message_for_client"],
          env["message_for_client"])
    check("4: the loop is told to stop", env["loop_should_stop"] is True)
    rc = RW.main(["--run-dir", str(run), "--interval-check", "--now", str(NOW)])
    check("4: --interval-check exits 10 on expiry", rc == 10, rc)
    rc = RW.main(["--run-dir", str(run), "--now", str(NOW)])
    check("4: a plain read still exits 0", rc == 0, rc)

    # a cap is a cap, not a deadline: a COMPLETE run is done, never "expired"
    run = make_run(tmp, "run4b", base_ago_s=190 * 60)
    for s in STAGES:
        set_stage(run, "run4b", s, "COMPLETE", age_s=20 * 60)
    env = RW.build(run, now=NOW)
    check("4b: a COMPLETE run is not expired",
          env["expired"] is False and env["stage_state"] == "COMPLETE", str(env))
    check("4b: no failure code on a finished run", env["loud"] == [], env["loud"])
    check("4b: the client is told it is finished",
          "Your video is finished" in env["message_for_client"],
          env["message_for_client"])
    check("4b: the loop stops on COMPLETE too", env["loop_should_stop"] is True)

    # 5. an unreadable run is loud, never a silent pass ----------------------
    empty = Path(tmp) / "run5"
    (empty / "control").mkdir(parents=True)
    env = RW.build(empty, now=NOW)
    check("5: HEARTBEAT_STATE_UNREADABLE is named",
          env["loud"] == ["HEARTBEAT_STATE_UNREADABLE"], env["loud"])
    check("5: an unreadable run still has a client message",
          bool(env["message_for_client"]) and "couldn't read" in env["message_for_client"],
          env["message_for_client"])
    rc = RW.main(["--run-dir", str(empty), "--now", str(NOW)])
    check("5: an unreadable state exits 1", rc == 1, rc)
    rc = RW.main(["--run-dir", str(Path(tmp) / "does-not-exist"), "--now", str(NOW)])
    check("5: a missing run folder is loud too", rc == 1, rc)

    # 6. the watcher never mutates the run -----------------------------------
    check("3: the run's own files are byte-identical after a look",
          before == tree_digest(Path(tmp) / "run3"), "run3 changed")
    run6 = make_run(tmp, "run6")
    set_stage(run6, "run6", "research", "RUNNING", age_s=40 * 60, lease_in=300,
              owner="worker-6")
    write_json(run6 / "control" / "fork-decisions.json",
               {"forks": [{"fork_id": "f", "decision": "wait", "label": "q"}]})
    write_json(run6 / "control" / "run-state.json", {"outstanding": ["q?"]})
    snap = tree_digest(run6)
    RW.build(run6, now=NOW)
    RW.main(["--run-dir", str(run6), "--interval-check", "--now", str(NOW)])
    check("6: state, ledger, forks and run-state unchanged",
          snap == tree_digest(run6),
          sorted(set(snap) ^ set(tree_digest(run6))))

    print()
    if FS:
        print("%d FAILED: %s" % (len(FS), ", ".join(FS)))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
