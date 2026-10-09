#!/usr/bin/env python3
"""FU-INTRO-MESSAGE tests: the one-time intro before question 1.

Run: python3 core/choice_card/intake_card/test_intro_message.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
FACTORY = os.path.join(CORE, "intake_preflight", "factory.py")
sys.path.insert(0, CORE)
from choice_card.intake_card import intake_card as IC  # noqa: E402
from choice_card.intake_card import intro as INTRO  # noqa: E402

EXPECTED = (
    "Turn your offer into a music video people actually feel.\n\n"
    "Answer a few quick questions, and we handle the rest:\n"
    "- Write the story and script, with the song lyrics woven in\n"
    "- Create your characters (or bring back ones you've saved)\n"
    "- Compose an original song in the music style you choose\n"
    "- Create every image and build the storyboard, shot by shot\n"
    "- Make the video shots and lip-sync the singers\n"
    "- Edit it all together with captions and your call to action\n\n"
    "You approve the script, pick your favorite of 3 song versions, and sign off "
    "on the storyboard before any video is made. Longer videos also come with "
    "60- and 90-second clips for social media.\n\n"
    "Before we start: if your video uses KIE.ai or OpenRouter models, top up your "
    "credits there first so your video doesn't stop halfway.\n\n"
    "Let's start - just a few quick questions."
)


def card(*extra):
    r = subprocess.run([sys.executable, FACTORY, "card", "--step", *extra],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.rstrip("\n")


def _state():
    return os.path.join(tempfile.mkdtemp(), "run-state.json")


def test_text_matches_exact_wording():
    assert INTRO.INTRO == EXPECTED


def test_intro_once_then_question_one_on_new_interactive_run():
    st = _state()
    first = card("--run-state-file", st)
    assert first == EXPECTED                       # intro, its own message
    assert "Question 1" not in first
    second = card("--run-state-file", st)          # next message is question 1
    assert second.startswith("Question 1 of ") and second == IC.conversation([])["message"]
    assert json.load(open(st))["intro_shown"] is True


def test_not_shown_on_resume_or_recap():
    st = _state()
    json.dump({"intro_shown": True, "keep": 1}, open(st, "w"))
    assert card("--run-state-file", st).startswith("Question 1 of ")   # resume
    n = len(IC.QUESTIONS)
    assert "Here is what you picked" in card("--run-state-file", st, *["--reply", "1"] * n)
    assert json.load(open(st))["keep"] == 1                            # state kept


def test_not_shown_once_replies_exist():
    st = _state()                                  # fresh file, but client already replied
    assert card("--run-state-file", st, "--reply", "1").startswith("Question 2 of ")
    assert not os.path.exists(st)


def test_batch_and_cli_only_paths_unchanged():
    assert card() == IC.conversation([])["message"]                    # no run-state flag
    full = subprocess.run([sys.executable, FACTORY, "card"], capture_output=True, text=True).stdout
    assert full.rstrip("\n") == IC.render_card()
    assert "Turn your offer" not in full


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    print("%d failed" % fails)
    raise SystemExit(1 if fails else 0)
