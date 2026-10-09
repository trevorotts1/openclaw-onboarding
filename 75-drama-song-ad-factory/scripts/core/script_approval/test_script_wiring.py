#!/usr/bin/env python3
"""SCRIPT APPROVAL wiring, end to end: card answer -> `factory.py next` -> paused run ->
client reply -> music. Delivery is a mocked sink (or a fake `openclaw` on PATH); the music
submit is the kie_dispatch fake Skill 74. No network, no paid call.
Run: python3 core/script_approval/test_script_wiring.py
"""
import argparse
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for p in (CORE, os.path.join(CORE, "kie_dispatch"), os.path.join(CORE, "intake_preflight")):
    sys.path.insert(0, p)
from choice_card.intake_card import intake_card as IC  # noqa: E402
import factory as F  # noqa: E402
import script_approval as SA  # noqa: E402
import test_kie_dispatch as TK  # noqa: E402

N = len(IC.QUESTIONS)
SHEET = [{"tag": "Intro", "lines": ["One closed door."]},
         {"tag": "Hook 1", "lines": ["I am not sma-a-all", "I ne-ever wa-a-as"]}]
STAGES = ("research", "creative-strategy", "script-lyrics", "music", "continuity-bible", "storyboard",
          "image-keyframes", "video-generation", "qc-retakes", "assembly", "final-qc", "delivery")
SAMPLES = os.path.join(CORE, "story_arc", "fixtures", "valid.json"), \
    os.path.join(CORE, "lyric_writer", "fixtures", "campaign.json")


def lyrics_of(sheet):
    return "\n".join(l for s in sheet for l in s["lines"])


def ones():
    """One reply per question: option 1, or a dollar amount for the spend question."""
    return ["$25" if q["id"] == "spend" else "1" for q in IC.QUESTIONS]


def make_run(yes=True):
    run = tempfile.mkdtemp(prefix="sa-wire-")
    os.makedirs(os.path.join(run, "control"))
    os.makedirs(os.path.join(run, "creative"))
    with sqlite3.connect(os.path.join(run, "control", "state.sqlite3")) as con:
        con.execute("CREATE TABLE stages(run_id TEXT, stage TEXT, state TEXT)")
        for s in STAGES:
            con.execute("INSERT INTO stages VALUES('R',?,?)",
                        (s, "COMPLETE" if STAGES.index(s) < 3 else "NOT_STARTED"))
    shutil.copy(SAMPLES[0], os.path.join(run, "creative", "story.json"))
    shutil.copy(SAMPLES[1], os.path.join(run, "creative", "lyrics.json"))
    answers = IC.conversation(ones()[:-1] + ["1" if yes else "2"])["answers"]
    json.dump(answers, open(os.path.join(run, "card-answers.json"), "w"))
    write_script(run, SHEET)
    return run


def write_script(run, sheet):
    json.dump({"title": "The Climb", "story": [["The world", ["She runs a small shop."]]],
               "sheet": sheet, "lyrics": lyrics_of(sheet)},
              open(os.path.join(run, "creative", "script.json"), "w"))


def next_(run, target=""):
    return F.cmd_next(argparse.Namespace(run_dir=run, target=target))


def reply(run, text, target=""):
    return F.cmd_script_reply(argparse.Namespace(run_dir=run, reply=text, target=target))


def music(run, lyrics):
    """The mocked music submit: a real dispatch against the fake Skill 74. -> (envelope, calls)."""
    req = {"model": "m", "input": {"prompt": "p" * 200}, "lyrics": lyrics, "run_dir": run}
    env, db, fake, tmp = TK.run_case(TK.BASE_SCRIPT, "sa-wire", model="suno-music-v6", request=req)
    return env, fake.calls


def test_yes_pauses_then_approve_continues():
    run = make_run()
    env = next_(run)
    assert env["outcome"] == "waiting" and env["reason_code"] == "SCRIPT_AWAITING_APPROVAL", env
    assert "command" not in env["data"]                              # no music command handed out
    sent = env["data"]["delivered"]
    assert sent and "THE SONG LYRICS" in "\n".join(sent) and "One closed door." in "\n".join(sent)
    rec = SA.record_for(run)
    assert rec["status"] == "pending" and rec["sent"] is True
    refused, calls = music(run, lyrics_of(SHEET))                    # the song cannot start; gate found the record itself
    assert refused["reason_code"] == SA.REASON and calls == [], refused
    assert reply(run, "approve")["outcome"] == "ok"
    go = next_(run)
    assert go["outcome"] == "ok" and go["data"]["stage"] == "music", go
    started, calls = music(run, lyrics_of(SHEET))
    assert started.get("reason_code") != SA.REASON and calls, started   # now the submit goes through


def test_resume_keeps_pause_and_does_not_resend():
    run = make_run()
    first = next_(run)["data"]["delivered"]
    again = next_(run)
    assert again["outcome"] == "waiting" and again["data"]["delivered"] == [], again
    assert SA.record_for(run)["sent"] is True and first


def test_edit_resends_and_old_approval_does_not_carry():
    run = make_run()
    next_(run)
    gate = [dict(s, lines=[l.replace("door", "gate") for l in s["lines"]]) for s in SHEET]
    write_script(run, gate)                                          # the agent applies the client's edit
    env = reply(run, "say gate, not door")
    assert env["outcome"] == "waiting" and "One closed gate." in "\n".join(env["data"]["delivered"]), env
    assert "door" not in "\n".join(env["data"]["delivered"])
    refused, calls = music(run, lyrics_of(gate))
    assert refused["reason_code"] == SA.REASON and calls == []
    reply(run, "approve")
    refused, calls = music(run, lyrics_of(SHEET))                    # approved the gate text, not the door text
    assert refused["reason_code"] == SA.REASON and calls == []


def test_no_path_unchanged():
    run = make_run(yes=False)
    env = next_(run)
    assert env["outcome"] == "ok" and env["data"]["stage"] == "music", env
    assert SA.record_for(run) is None and not os.path.exists(os.path.join(run, "creative", "script-approval.json"))
    started, calls = music(run, lyrics_of(SHEET))
    assert started.get("reason_code") != SA.REASON and calls


def test_failed_checks_send_nothing():
    run = make_run()
    os.remove(os.path.join(run, "creative", "story.json"))
    env = next_(run)
    assert env["outcome"] == "rejected" and SA.record_for(run) is None, env


def test_run_takes_finds_the_record_from_run_dir():
    import length_formula as LF
    import song_dispatch as SD
    import suno_recipe as R
    sys.path.insert(0, os.path.join(CORE, "suno_recipe"))
    run = make_run()
    next_(run)                                                       # pending record on disk, nothing handed in
    hook = ["I am not sma-a-all", "I ne-ever wa-a-as"]
    sheet = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
             {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
             {"tag": "Verse", "delivery": "sung", "lines": ["One seed of truth made me stro-o-ong,"]},
             {"tag": "Hook 1", "delivery": "sung", "lines": hook},
             {"tag": "Hook 2", "delivery": "sung", "lines": hook},
             {"tag": "Hook 3", "delivery": "sung", "lines": hook},
             {"tag": "Outro", "delivery": "spoken",
              "lines": ["She Found Power in the Climb. Get the book. Link below."]}]
    req = R.build_request("soul-ballad", sheet, "I am not small. I never was. One seed of truth made me strong. "
                          "She Found Power in the Climb.", "T", 58, hook_plan={"true_at_beat": "the_world"})
    calls = []
    try:
        SD.run_takes(req, LF.plan(60, (15, 20)), lambda rq: calls.append(1) or [], lambda t: {},
                     lambda t, r: None, "", "", run_dir=run, kie=lambda fn, label, generation=False: fn())
    except SD.DispatchError as e:
        assert SA.REASON in str(e)
    else:
        raise AssertionError("generation ran before approval")
    assert calls == []


def _fake_openclaw(ok=True):
    d = tempfile.mkdtemp(prefix="sa-bin-")
    log = os.path.join(d, "log")
    exe = os.path.join(d, "openclaw")
    open(exe, "w").write('#!/bin/sh\nprintf "%%s\\n" "$*" >> %s\n%s\n' % (log, "exit 0" if ok else "exit 1"))
    os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
    return d, log


def test_delivery_uses_openclaw_send_and_failure_resends_on_resume():
    run = make_run()
    bad, badlog = _fake_openclaw(ok=False)
    old = os.environ["PATH"]
    try:
        os.environ["PATH"] = bad + os.pathsep + old
        env = next_(run, target="555")
        assert env["outcome"] == "error", env                       # not delivered: not claimed as sent
        assert SA.record_for(run)["sent"] is False
        good, goodlog = _fake_openclaw(ok=True)
        os.environ["PATH"] = good + os.pathsep + old
        env = next_(run, target="555")                              # resume: re-sends because it never went out
        assert env["outcome"] == "waiting"
        line = open(goodlog).read()
        assert "message send --channel telegram --target 555 --message" in line and "THE SONG LYRICS" in line
        assert SA.record_for(run)["sent"] is True
        n = open(goodlog).read().count("message send")
        next_(run, target="555")
        assert open(goodlog).read().count("message send") == n      # no duplicate after a real send
    finally:
        os.environ["PATH"] = old


def confirm_card(run, script_answer):
    """Drive the REAL card (factory.py card --step --run-dir) to a confirmed recap."""
    os.remove(os.path.join(run, "card-answers.json"))
    replies = ones()[:-1] + [script_answer] + ["yes"]
    args = ["card", "--step", "--run-dir", run] + [x for r in replies for x in ("--reply", r)]
    assert F.main(args) == 0


def test_confirmed_recap_writes_answers_yes_pauses():
    run = make_run()
    confirm_card(run, "1")
    rows = json.load(open(os.path.join(run, "card-answers.json")))
    assert [r["id"] for r in rows] == [q["id"] for q in IC.QUESTIONS]
    env = next_(run)
    assert env["outcome"] == "waiting" and env["reason_code"] == "SCRIPT_AWAITING_APPROVAL", env
    assert "THE SONG LYRICS" in "\n".join(env["data"]["delivered"])


def test_confirmed_recap_no_goes_to_music():
    run = make_run()
    confirm_card(run, "2")
    env = next_(run)
    assert env["outcome"] == "ok" and env["data"]["stage"] == "music", env


def test_unconfirmed_recap_writes_nothing():
    run = make_run()
    os.remove(os.path.join(run, "card-answers.json"))
    args = ["card", "--step", "--run-dir", run] + [x for r in ones() for x in ("--reply", r)]
    F.main(args)
    assert not os.path.exists(os.path.join(run, "card-answers.json"))


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print("ALL PASS" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
