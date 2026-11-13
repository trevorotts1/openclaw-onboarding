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

#: The card a plain replay asks: the new card, numbered over the screens it
#: actually ASKS (S75-006: the defaulted tail -- video model, shape, photos --
#: rides on the recap and is never a turn of its own).
Q = [q for q in IC.QUESTIONS if not q.get("defaulted")]
N = len(Q)
#: The typed brief answers for the ask list, the nine production picks and the
#: dollar amount for the spend question.
OK = IC.example_replies(IC.QUESTIONS)


def _transcript(replies):
    """Bot turn before each reply, plus the final turn."""
    return [IC.conversation(replies[:i])["message"] for i in range(len(replies) + 1)]


def test_transcript_one_question_per_turn_with_options_and_recommendation():
    turns = _transcript(OK)
    for i, t in enumerate(turns[:N], 1):
        assert t.count("Question ") == 1 and t.startswith("Question %d of %d - " % (i, N)), t
        lines = t.split("\n")
        q = Q[i - 1]
        if "body" in q:                  # CHECKPOINTS carries its own exact wording
            assert lines[1:] == q["body"], t
            continue
        if q.get("free_text"):           # the address follow-up carries no why line
            assert t.endswith(IC.FREE_TEXT_HINT) and not lines[2].startswith("1. "), t
            continue
        assert lines[1].endswith(".") and lines[2] == ""              # one-sentence why
        opts = [l for l in lines if re.match(r"^\d+\. ", l)]
        assert len(opts) == len(q["options"])
        if q["recommended"] is None:                                 # unpriced spend: no recommendation
            assert not any(IC.REC in l for l in opts) and t.endswith("like $25.")
            continue
        assert sum(IC.REC in l for l in opts) == 1                   # one RECOMMENDED
        assert re.search(r"I recommend option \d+ \(.+\) because .+\.", t)
        assert t.endswith('say "recommended".')


def test_recap_then_yes_finishes():
    turns = _transcript(OK)
    recap = turns[N]
    assert recap.startswith("Here is what you picked:") and "Question " not in recap
    # one numbered line per asked answer, plus the three defaulted recap lines
    lines = [l for l in recap.split("\n") if re.match(r"^\d+\. ", l)]
    assert len(lines) == len(IC.QUESTIONS), recap
    assert not IC.conversation(OK)["done"]
    done = IC.conversation(OK + ["yes"])
    assert done["done"] and done["message"].startswith("Locked in")


def test_recommended_bad_answer_and_spend_amount():
    # "recommended" is not an answer a typed brief question can take.
    st = IC.conversation(["recommended"])
    assert st["message"].startswith("Sorry, I did not catch that. Question 1 of")
    assert st["answers"] == []
    # On a choice question it still means "take the recommended one".
    models_at = [q["id"] for q in Q].index("models")
    st = IC.conversation(OK[:models_at] + ["recommended", "9"])
    assert st["message"].startswith("Sorry, I did not catch that. Question %d of" % (models_at + 2))
    assert len(st["answers"]) == models_at + 1
    spend_at = [q["id"] for q in Q].index("spend")
    a = IC.conversation(OK[:spend_at] + ["$25"])["answers"]
    assert a[spend_at]["value"] == "25"
    # the VIDEO MODEL is a recap line since S75-006: its own number asks the
    # full question, and the client's pick replaces the line's default.
    model_line = len(Q) + 1                     # first defaulted line
    st = IC.conversation(OK + [str(model_line)])
    assert "Which video model should make your shots?" in st["message"], st["message"]
    st = IC.conversation(OK + [str(model_line), "2"])
    assert st["message"].startswith("Here is what you picked:")
    assert "Video model: " in st["message"] and "(default" not in st["message"].split("Video model:", 1)[1].split("\n")[0]


def test_change_one_line_returns_to_recap():
    base = OK
    music_at = [q["id"] for q in Q].index("music") + 1   # a numbered line to change
    st = IC.conversation(base + [str(music_at)])
    assert st["message"].startswith("Question %d of" % music_at)
    st = IC.conversation(base + [str(music_at), "3"])
    assert st["answers"][music_at - 1]["n"] == 3 and st["message"].startswith("Here is what you picked:")


def test_a_typed_brief_answer_is_stored_verbatim():
    # the OFFER screen on its own: the first typed question of the new card
    offer = [IC._offer_q()]
    st = IC.conversation(["My 6-week Confident Speaker program"], offer)
    assert st["answers"][0] == {"n": 1, "text": "My 6-week Confident Speaker program",
                                "value": "My 6-week Confident Speaker program", "id": "offer"}
    # a bare "1" or a bare "yes" is never somebody's offer
    assert IC.conversation(["1"], offer)["answers"] == []
    assert IC.conversation(["yes"], offer)["answers"] == []


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
