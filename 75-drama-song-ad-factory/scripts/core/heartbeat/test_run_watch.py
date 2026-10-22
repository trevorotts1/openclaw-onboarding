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
  3. a stall is detected when the current stage has made no durable event for
     30 minutes, and when its lease has run out -- with HEARTBEAT_STALLED named
     and the exact factory.py recovery command PRINTED (never run) when the
     actuator is not separately authorized;
  4. the supervision cap is anchored on the run's own start: expired and
     HEARTBEAT_EXPIRED named, but supervision never self-terminates --
     --interval-check keeps looping (exit 0) on an unfinished run however long
     it runs; only a verified COMPLETE run stops the loop (exit 10);
  5. an unreadable state store is loud (HEARTBEAT_STATE_UNREADABLE), never a
     silent pass, and exits 1;
  6. the observer never mutates the run: the state store, spend ledger,
     fork-decisions.json and run-state.json are byte-identical afterwards;
  7. a four-hour unfinished run stays supervised: evidence-based recovery runs
     under separate authorization (or a named legitimate wait is reported),
     never false success, never self-termination;
  8. the recovery actuator is fenced: monotonic generation claims with
     revocation-before-replacement, stale tokens rejected AND quarantined at
     the write, evidence, state and provider-dispatch boundaries, execution
     only through the supported native control (factory.py next), no provider
     dispatch, and creative/PASS-record actions refused (roles stay distinct);
  9. watchdog clocks advance only from durable events: copied/touched decision
     files and file mtime never reset them, and a durable event outranks a
     fresh state stamp.

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


def tree_digest_skip(run, skip_prefix):
    """tree_digest, minus paths under skip_prefix (the actuator's own ledger)."""
    return {k: v for k, v in tree_digest(run).items()
            if not k.startswith(skip_prefix)}


def add_event(run, run_id, stage, at, kind="progress"):
    """A durable event row -- the ONLY thing that advances a watchdog clock."""
    con = sqlite3.connect(str(run / "control" / "state.sqlite3"))
    con.execute("INSERT INTO events(id, run_id, stage, kind, detail, at)"
                " VALUES(?,?,?,?,?,?)",
                (hashlib.sha256(("%s|%s|%g|%s" % (run_id, stage, at, kind))
                                .encode()).hexdigest(),
                 run_id, stage, kind, "", float(at)))
    con.commit()
    con.close()


def write_auth(run, by="operator", scope=("resume",), run_id=None):
    """The SEPARATE written authorization the actuator needs (never self-made)."""
    write_json(run / "control" / "recovery-authorization.json",
               {"authorized": True, "scope": list(scope), "by": by,
                "run_id": run_id or run.name})


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

    # 4. the supervision cap escalates, it never stops supervision ----------
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
    check("4: the client gets honest progress, no stopping story",
          "10 of 12 steps are finished" in env["message_for_client"]
          and "Time's up for this round" not in env["message_for_client"]
          and "staying with it" in env["message_for_client"],
          env["message_for_client"])
    check("4: the cap never stops supervision",
          env["loop_should_stop"] is False and env["supervising"] is True)
    rc = RW.main(["--run-dir", str(run), "--interval-check", "--now", str(NOW)])
    check("4: --interval-check keeps looping past the cap", rc == 0, rc)
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
    check("4b: only verified completion stops the loop",
          env["loop_should_stop"] is True and env["supervising"] is False)
    rc = RW.main(["--run-dir", str(run), "--interval-check", "--now", str(NOW)])
    check("4b: --interval-check exits 10 on verified completion", rc == 10, rc)

    # 4c. an explicit user cancellation is the one other legitimate stop ----
    run = make_run(tmp, "run4c", base_ago_s=240 * 60)
    set_stage(run, "run4c", "research", "RUNNING", age_s=40 * 60, lease_in=300,
              owner="worker-4c")
    write_json(run / "control" / "run-state.json", {"canceled": True})
    env = RW.build(run, now=NOW)
    check("4c: a recorded user cancellation stops the loop, honestly",
          env["canceled"] is True and env["loop_should_stop"] is True
          and "You asked us to stop this run" in env["message_for_client"],
          env["message_for_client"])

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

    # 7. a four-hour unfinished run keeps supervised -------------------------
    calls = []

    def runner(argv):
        calls.append(list(argv))
        return {"returncode": 0, "stdout_sha256": "0" * 64, "stderr_tail": ""}

    run = make_run(tmp, "run7", base_ago_s=240 * 60)
    for s in ("research", "creative-strategy", "script-lyrics"):
        set_stage(run, "run7", s, "COMPLETE", age_s=240 * 60)
    set_stage(run, "run7", "music", "RUNNING", age_s=45 * 60, lease_in=300,
              owner="worker-7")
    write_auth(run)
    before = tree_digest_skip(run, "control/recovery/")
    env = RW.build(run, now=NOW, recovery_act=True, runner=runner)
    check("7: 240 minutes is past the cap", env["expired"] is True)
    check("7: supervision never self-terminates",
          env["loop_should_stop"] is False and env["supervising"] is True, str(env))
    check("7: the stalled run got evidence-based recovery",
          bool(env["recovery"]) and env["recovery"]["acted"] is True
          and "factory.py" in env["recovery"]["control"]["argv"][1],
          str(env.get("recovery")))
    check("7: recovery executed the supported native control exactly once",
          len(calls) == 1 and calls[0][2] == "next"
          and calls[0][4] == str(run), calls)
    check("7: the recovery claim carries a generation and token",
          env["recovery"]["claim"]["generation"] >= 1
          and len(env["recovery"]["claim"]["token"]) == 32,
          str(env["recovery"].get("claim")))
    check("7: no false success on an unfinished run",
          "Your video is finished" not in env["message_for_client"]
          and env["stage_state"] != "COMPLETE", env["message_for_client"])
    check("7: the run's own files are untouched outside the fence ledger",
          before == tree_digest_skip(run, "control/recovery/"),
          sorted(set(before) ^ set(tree_digest_skip(run, "control/recovery/"))))
    rc = RW.main(["--run-dir", str(run), "--interval-check", "--now", str(NOW)])
    check("7: --interval-check keeps looping at four hours", rc == 0, rc)

    # 7b. four hours parked on the client is a NAMED legitimate wait --------
    run = make_run(tmp, "run7b", base_ago_s=240 * 60)
    set_stage(run, "run7b", "research", "COMPLETE", age_s=240 * 60)
    set_stage(run, "run7b", "creative-strategy", "WAITING_APPROVAL",
              age_s=200 * 60)
    env = RW.build(run, now=NOW)
    check("7b: a client wait is named, not a stall",
          env["stalled"] is False and bool(env["wait"])
          and env["wait"]["kind"] == "client-approval", str(env.get("wait")))
    check("7b: four hours waiting on the client keeps supervision alive",
          env["loop_should_stop"] is False and env["supervising"] is True)
    check("7b: never false success while waiting",
          "Your video is finished" not in env["message_for_client"],
          env["message_for_client"])

    # 8. the recovery actuator is fenced ------------------------------------
    run = make_run(tmp, "run8")
    write_auth(run)
    fence = RW.RecoveryFence(run / "control" / "recovery" / "fence.json")
    c1 = fence.claim("first worker", now=NOW - 30)
    c2 = fence.claim("replacement worker", now=NOW - 20)
    c3 = fence.claim("second replacement", now=NOW - 10)
    check("8: claim generations are monotonic",
          (c1["generation"], c2["generation"], c3["generation"]) == (1, 2, 3),
          (c1["generation"], c2["generation"], c3["generation"]))
    doc = json.loads((run / "control" / "recovery" / "fence.json").read_text())
    first = doc["claims"][0]
    check("8: the old token is revoked before the replacement may write",
          first["status"] == "revoked"
          and first["revoked_for_generation"] == c2["generation"]
          and first["revoked_at"] <= doc["claims"][1]["claimed_at"], first)
    stale = [fence.guard(b, c1["token"], now=NOW) for b in RW.FENCE_BOUNDARIES]
    check("8: a stale token is rejected at every fenced boundary",
          len(stale) == 4 and all(not ok for ok, _ in stale), stale)
    doc = json.loads((run / "control" / "recovery" / "fence.json").read_text())
    check("8: stale results are quarantined at all four boundaries",
          sorted(q["boundary"] for q in doc["quarantine"]
                 if q["token"] == c1["token"]) == sorted(RW.FENCE_BOUNDARIES),
          doc["quarantine"])
    ok, detail = fence.guard("state", c3["token"], now=NOW)
    check("8: the current token passes its boundary", ok is True, detail)

    calls = []

    def runner(argv):
        calls.append(list(argv))
        return {"returncode": 0, "stdout_sha256": "0" * 64, "stderr_tail": ""}

    rec = RW.actuate_recovery(run, reason="stalled", action="resume", now=NOW,
                              runner=runner)
    check("8: the actuator executes the supported native control",
          rec["acted"] is True and len(calls) == 1
          and "factory.py" in calls[0][1] and calls[0][2] == "next"
          and calls[0][4] == str(run), calls)
    check("8: one claim cleared every fenced boundary",
          sorted(s["boundary"] for s in rec["steps"]) == sorted(RW.FENCE_BOUNDARIES)
          and all(s["ok"] for s in rec["steps"]), rec["steps"])
    check("8: provider dispatch is refused, never attempted",
          rec["provider_dispatch"]["attempted"] is False
          and rec["provider_dispatch"]["refused"]
          == "RECOVERY_NO_PROVIDER_DISPATCH", rec["provider_dispatch"])
    check("8: evidence records loaded source hashes",
          set(rec.get("evidence", {}).get("loaded_source_hashes", {}))
          == {"run_watch.py", "factory.py"}, rec.get("evidence"))
    rec = RW.actuate_recovery(run, reason="x", action="write-pass", now=NOW,
                              runner=runner)
    check("8: manufacturing a PASS record is refused (reviewer is a real role)",
          rec["acted"] is False
          and rec["refused"]["code"] == "RECOVERY_ACTION_REFUSED", rec)
    rec = RW.actuate_recovery(run, reason="x", action="author-creative", now=NOW,
                              runner=runner)
    check("8: authoring creative output is refused (builder is a real role)",
          rec["acted"] is False
          and rec["refused"]["code"] == "RECOVERY_ACTION_REFUSED", rec)
    check("8: refused actions ran no control", len(calls) == 1, calls)

    run2 = make_run(tmp, "run8b")
    calls2 = []

    def runner2(argv):
        calls2.append(list(argv))
        return {"returncode": 0, "stdout_sha256": "0" * 64, "stderr_tail": ""}

    rec = RW.actuate_recovery(run2, reason="stall", now=NOW, runner=runner2)
    check("8: without the separate written authorization the actuator refuses",
          rec["acted"] is False
          and rec["refused"]["code"] == "RECOVERY_NOT_AUTHORIZED", rec)
    check("8: nothing ran and no fence was created when unauthorized",
          calls2 == [] and not (run2 / "control" / "recovery").exists(),
          (calls2, sorted(p.name for p in (run2 / "control").iterdir())))

    # 9. watchdog clocks advance only from durable events -------------------
    run = make_run(tmp, "run9")
    set_stage(run, "run9", "research", "RUNNING", age_s=45 * 60, lease_in=3600,
              owner="worker-9")
    env = RW.build(run, now=NOW)
    check("9: 45 minutes of work silence is a stall", env["stalled"] is True,
          str(env["stall_detail"]))
    check("9: the activity clock names its source",
          env["activity"]["source"] in ("state-stamp-anchor", "durable-event"),
          str(env["activity"]))
    # copied/touched decision files are not activity: fresh mtimes change nothing
    write_json(run / "control" / "run-state.json", {"outstanding": []})
    write_json(run / "control" / "fork-decisions.json",
               {"forks": [{"fork_id": "f", "decision": "proceed"}]})
    write_json(run / "control" / "copied-decision.json", {"note": "a fresh copy"})
    for p in ("run-state.json", "fork-decisions.json", "copied-decision.json"):
        os.utime(str(run / "control" / p), (NOW, NOW))
    env = RW.build(run, now=NOW)
    check("9: copied/touched decision files never reset the watchdog clock",
          env["stalled"] is True, str(env["stall_detail"]))
    add_event(run, "run9", "research", NOW - 5 * 60, kind="worker-heartbeat")
    env = RW.build(run, now=NOW)
    check("9: a durable event advances the clock and clears the stall",
          env["stalled"] is False
          and env["activity"]["source"] == "durable-event", str(env))
    run = make_run(tmp, "run9b")
    set_stage(run, "run9b", "research", "RUNNING", age_s=0, lease_in=3600,
              owner="worker-9b")
    add_event(run, "run9b", "research", NOW - 2 * RW.STALL_AFTER_S,
              kind="progress")
    env = RW.build(run, now=NOW)
    check("9b: only durable events advance the clock (a fresh state stamp does not)",
          env["stalled"] is True and env["activity"]["source"] == "durable-event",
          str(env))

    # 10. a WAL state db with no sidecars is readable ------------------------
    run10 = make_run(tmp, "run10")
    set_stage(run10, "run10", "music", "RUNNING", age_s=60, lease_in=300,
              owner="worker-10")
    db10 = run10 / "control" / "state.sqlite3"
    con = sqlite3.connect(str(db10))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    for side in ("-wal", "-shm"):
        sidep = Path(str(db10) + side)
        if sidep.exists():
            sidep.unlink()
    env = RW.build(run10, now=NOW)
    check("10: WAL db without sidecars reads, not HEARTBEAT_STATE_UNREADABLE",
          "HEARTBEAT_STATE_UNREADABLE" not in env["loud"], env["loud"])
    check("10: the stage table still reads through the private-copy fallback",
          env["stage"] == "research", env["stage"])

    # 11. a delivered run is never "stalled" just because time passed --------
    run11 = make_run(tmp, "run11")
    for s in STAGES:
        set_stage(run11, "run11", s, "COMPLETE", age_s=1000 * 60)
    env = RW.build(run11, now=NOW)
    check("11: a COMPLETE stage never counts as a stall",
          env["stalled"] is False, env.get("stall_detail"))
    check("11: no HEARTBEAT_STALLED on a delivered run",
          "HEARTBEAT_STALLED" not in env["loud"], env["loud"])
    check("11: the delivered run still stops the loop",
          env["loop_should_stop"] is True)


    # 12. a client wait past the cap is not an expiry ------------------------
    run12 = make_run(tmp, "run12", base_ago_s=6 * 60 * 60)
    for s in ("research", "creative-strategy", "script-lyrics", "music",
              "continuity-bible", "storyboard", "image-keyframes"):
        set_stage(run12, "run12", s, "COMPLETE", age_s=6 * 60 * 60)
    set_stage(run12, "run12", "video-generation", "WAITING_APPROVAL",
              age_s=30 * 60)
    env = RW.build(run12, now=NOW)
    check("12: a run parked on the client is not expired",
          env["expired"] is False, env.get("expired"))
    check("12: no HEARTBEAT_EXPIRED while the client owes the answer",
          "HEARTBEAT_EXPIRED" not in env["loud"], env["loud"])
    check("12: the client is told it is waiting on them",
          (env.get("wait") or {}).get("kind", "").startswith("client"),
          env.get("wait"))


    print()
    if FS:
        print("%d FAILED: %s" % (len(FS), ", ".join(FS)))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
