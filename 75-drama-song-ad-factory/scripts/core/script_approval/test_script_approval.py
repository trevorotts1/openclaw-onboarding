#!/usr/bin/env python3
"""SCRIPT APPROVAL tests: the card question, the script message, the pause, the edit loop.

Zero paid calls: the music submit is a mock that records calls.
Run: python3 core/script_approval/test_script_approval.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "kie_dispatch"))
sys.path.insert(0, os.path.join(CORE, "suno_recipe"))
from choice_card.intake_card import intake_card as IC  # noqa: E402
import length_formula as LF  # noqa: E402
import script_approval as SA  # noqa: E402
import song_dispatch as SD  # noqa: E402
import suno_recipe as R  # noqa: E402

N = len(IC.QUESTIONS)
TITLE = "The Climb"
STORY = [("The world", ["She runs a small shop.", "Nobody knows her name."]),
         ("The turn", ["One seed of truth changes it."])]
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
         {"tag": "Outro", "delivery": "spoken", "lines": ["Get the book. Link below."]},
         {"tag": "End", "delivery": None, "lines": []}]
LYRICS = "\n".join(l for s in SHEET for l in s["lines"])


CLIENT = "I am not small. I never was. One seed of truth made me strong. She Found Power in the Climb."
RSHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
          {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
          {"tag": "Verse", "delivery": "sung", "lines": ["One seed of truth made me stro-o-ong,"]},
          {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
          {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
          {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
          {"tag": "Outro", "delivery": "spoken",
           "lines": ["She Found Power in the Climb. Get the book. Link below."]}]


def _edit(reply, story, sheet):
    sheet = [dict(s, lines=[l.replace("door", "gate") for l in s["lines"]]) for s in sheet]
    return story, sheet, "\n".join(l for s in sheet for l in s["lines"])


def test_question_renders_last_with_right_count_and_text():
    q = IC.QUESTIONS[-1]
    assert q["label"] == "SCRIPT APPROVAL" and q["id"] == "script"
    text = IC.render_card().split("\n\n")[N - 1]
    assert text == ("Question %d of %d - SCRIPT APPROVAL\n"
                    "Do you want to read and approve the script - your story and the song lyrics - "
                    "before the song is made?\n"
                    "1. Yes, show me first - Nothing is generated until you say go. (RECOMMENDED)\n"
                    "2. No, just make it - I start as soon as the card is approved." % (N, N))
    assert "Question %d of %d - " % (1, N) in IC.render_card()


def test_recap_and_change_by_number():
    base = ["$25" if q["id"] == "spend" else "1" for q in IC.QUESTIONS]   # spend takes a dollar amount
    recap = IC.conversation(base)["message"]
    assert "%d. Script Approval: Yes, show me first" % N in recap
    st = IC.conversation(base + [str(N)])                      # change the last line
    assert st["message"].startswith("Question %d of %d - SCRIPT APPROVAL" % (N, N))
    st = IC.conversation(base + [str(N), "2"])
    assert st["answers"][-1]["n"] == 2 and "Script Approval: No, just make it" in st["message"]
    assert SA.wants_approval(IC.conversation(base)["answers"], IC.QUESTIONS) is True
    assert SA.wants_approval(st["answers"], IC.QUESTIONS) is False


def test_script_message_shape():
    m = SA.render_script(TITLE, STORY, SHEET)
    assert m.index("THE STORY") < m.index("THE SONG LYRICS") < m.index('Reply "approve"')
    assert "THE WORLD\nShe runs a small shop." in m and "[Hook 1]\nI am not sma-a-all" in m
    assert "[End]" not in m and "*" not in m and "#" not in m


def _req_and_plan():
    plan = LF.plan(60, (15, 20))
    return R.build_request("soul-ballad", RSHEET, CLIENT, "T", 58, hook_plan={"true_at_beat": "the_world"}), plan


def _run(rec, calls):
    req, plan = _req_and_plan()
    return SD.run_takes(req, plan, lambda rq: calls.append(1) or [], lambda t: {}, lambda t, r: None,
                        "", "", script_approval=rec, kie=lambda fn, label, generation=False: fn()), req


def test_yes_pauses_before_any_music_submit_and_sends_script():
    run = tempfile.mkdtemp()
    req, _ = _req_and_plan()
    msgs = SA.request_approval(run, TITLE, STORY, SHEET, req["lyrics"])
    assert msgs and "THE SONG LYRICS" in "\n".join(msgs)
    rec = SA.record_for(run)
    assert rec["required"] and rec["status"] == "pending"
    calls = []
    try:
        _run(rec, calls)
    except SD.DispatchError as e:
        assert SA.REASON in str(e)
    else:
        raise AssertionError("generation ran before approval")
    assert calls == []                                          # the music submit mock was never called
    # missing record on a run that required it is the caller's pending record: a record
    # that is required but empty of approval fails closed too
    assert SA.check_script_approval({"required": True}, req["lyrics"])


def test_dispatch_path_refuses_pending_and_allows_approved_and_unasked():
    import test_kie_dispatch as TK
    base = {"model": "m", "input": {"prompt": "p" * 200}, "lyrics": "la la"}
    pending = {"required": True, "status": "pending", "lyrics_sha": SA.lyrics_sha("la la")}
    env, db, fake, tmp = TK.run_case(TK.BASE_SCRIPT, "sa-pend", model="suno-music-v6",
                                     request=dict(base, script_approval=pending))
    assert env.get("reason_code") == SA.REASON and fake.calls == [], env
    ok = dict(pending, status="approved")
    env, db, fake, tmp = TK.run_case(TK.BASE_SCRIPT, "sa-ok", model="suno-music-v6",
                                     request=dict(base, script_approval=ok))
    assert env.get("reason_code") != SA.REASON
    env, db, fake, tmp = TK.run_case(TK.BASE_SCRIPT, "sa-none", model="suno-music-v6", request=base)
    assert env.get("reason_code") != SA.REASON                  # No path: as today
    env, db, fake, tmp = TK.run_case(TK.BASE_SCRIPT, "sa-img", request=dict(base, script_approval=pending))
    assert env.get("reason_code") != SA.REASON                  # only music is held


def test_approve_continues_and_edit_changes_script_and_resends():
    run = tempfile.mkdtemp()
    SA.request_approval(run, TITLE, STORY, SHEET, LYRICS)
    r = SA.handle_reply(run, "say gate, not door", TITLE, STORY, SHEET, LYRICS, _edit, lambda s, h: [])
    assert r["status"] == "pending" and r["messages"] and "One closed gate." in "\n".join(r["messages"])
    assert "door" not in "\n".join(r["messages"])
    old = SA.record_for(run)
    assert old["status"] == "pending" and old["lyrics_sha"] == SA.lyrics_sha(r["lyrics"])
    # a failed re-check sends nothing and stays paused
    bad = SA.handle_reply(run, "break it", TITLE, STORY, SHEET, LYRICS, _edit, lambda s, h: ["too long"])
    assert bad["messages"] == [] and bad["problems"] == ["too long"] and SA.record_for(run)["status"] == "pending"
    # approve unlocks the gate for the approved lyrics, and only for them
    ok = SA.handle_reply(run, "approve", TITLE, STORY, SHEET, r["lyrics"], _edit, lambda s, h: [])
    assert ok["status"] == "approved"
    rec = SA.record_for(run)
    assert SA.check_script_approval(rec, r["lyrics"]) is None
    assert SA.check_script_approval(rec, r["lyrics"] + " changed") is not None   # edited after approval


def test_no_path_unchanged():
    assert SA.check_script_approval(None, "x") is None
    assert SA.check_script_approval({"required": False}, "x") is None
    calls = []
    out, _ = _run(None, calls)
    assert calls and out["verdict"] == "FAIL"                  # ran the loop as today (mock returns no takes)


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
