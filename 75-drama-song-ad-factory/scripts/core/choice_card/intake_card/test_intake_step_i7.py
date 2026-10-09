#!/usr/bin/env python3
"""I7 test: the intake is a one-question-per-turn conversation.

Transcript: every bot turn holds exactly ONE question, a one-sentence why,
numbered options one per line, the RECOMMENDED one marked and explained; the
last turn is a recap that waits for a yes.

Run: python3 core/choice_card/intake_card/test_intake_step_i7.py
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import intake_card as IC  # noqa: E402

N = len(IC.QUESTIONS)
#: AI MODELS + four picks, then an explicit dollar amount for the spend question (no amount = no spend)
OK = ["1"] * 5 + ["$25"] + ["1"] * (N - 6)


def _transcript(replies):
    """Bot turn before each reply, plus the final turn."""
    return [IC.conversation(replies[:i])["message"] for i in range(len(replies) + 1)]


def test_transcript_one_question_per_turn_with_options_and_recommendation():
    turns = _transcript(OK)
    for i, t in enumerate(turns[:N], 1):
        assert t.count("Question ") == 1 and t.startswith("Question %d of %d - " % (i, N)), t
        lines = t.split("\n")
        assert lines[1].endswith(".") and lines[2] == ""              # one-sentence why
        opts = [l for l in lines if re.match(r"^\d+\. ", l)]
        assert len(opts) == len(IC.QUESTIONS[i - 1]["options"])
        if IC.QUESTIONS[i - 1]["recommended"] is None:                # unpriced spend: no recommendation
            assert not any(IC.REC in l for l in opts) and t.endswith("like $25.")
            continue
        assert sum(IC.REC in l for l in opts) == 1                    # one RECOMMENDED
        assert re.search(r"I recommend option \d+ \(.+\) because .+\.", t)
        assert t.endswith('say "recommended".')


def test_recap_then_yes_finishes():
    turns = _transcript(OK)
    recap = turns[N]
    assert recap.startswith("Here is what you picked:") and "Question " not in recap
    assert len([l for l in recap.split("\n") if re.match(r"^\d+\. ", l)]) == N
    assert not IC.conversation(OK)["done"]
    done = IC.conversation(OK + ["yes"])
    assert done["done"] and done["message"].startswith("Locked in")


def test_recommended_bad_answer_and_spend_amount():
    st = IC.conversation(["recommended", "9"])
    assert st["message"].startswith("Sorry, I did not catch that. Question 2 of")
    assert len(st["answers"]) == 1
    a = IC.conversation(["1"] * 5 + ["$25", "2"])["answers"]
    assert a[5]["value"] == "25" and a[6]["n"] == 2


def test_change_one_line_returns_to_recap():
    base = OK
    st = IC.conversation(base + ["3"])                 # change line 3
    assert st["message"].startswith("Question 3 of")
    st = IC.conversation(base + ["3", "2"])
    assert st["answers"][2]["n"] == 2 and st["message"].startswith("Here is what you picked:")


def test_cli_step_prints_next_message_raw_and_json():
    s = os.path.join(HERE, "intake_card.py")
    out = subprocess.run([sys.executable, s, "--step", "--reply", "1"],
                         capture_output=True, text=True).stdout
    assert out == IC.conversation(["1"])["message"] + "\n" and "\\n" not in out
    js = json.loads(subprocess.run([sys.executable, s, "--step", "--format", "openclaw-json",
                                    "--target", "9", "--reply", "1"],
                                   capture_output=True, text=True).stdout)
    assert js["send"][-3] == "9" and "\n" in js["send"][-1] and js["done"] is False


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
