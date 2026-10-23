#!/usr/bin/env python3
"""S75X-W3-U1: the run's RECORDED purpose reaches the story check.

`stage._problems` used to call `story_arc.validate_story(story)` with no
purpose, so a lesson run's `lesson_intro` was refused and a testimonial run's
unsourced claim was never checked. The purpose is read from
`$RUN/control/method.json` and nowhere else -- never guessed from the script's
text -- and it is carried through the first check and every edit re-check.

The presentation stays ONE package with one whole-package approval action
(response `approve both` / `approve`), never a per-scene stop.

Zero paid calls, zero network.
Run: python3 core/script_approval/test_stage_purpose.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, CORE)
from script_approval import approval_events as AE  # noqa: E402
from script_approval import card_answers  # noqa: E402
from script_approval import script_approval as SA  # noqa: E402
from script_approval import stage  # noqa: E402

BEATS = ["ordinary_world", "humiliation", "wound_deepens", "frozen",
         "seeing_it_too", "failed_solutions", "mentor", "product_intro",
         "doubt", "climb", "vindication", "return_cta"]
LESSON_BEATS = BEATS[:7] + ["lesson_intro"] + BEATS[8:]
LYRICS_FIXTURE = os.path.join(CORE, "lyric_writer", "fixtures", "campaign.json")
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Hook 1", "delivery": "sung", "lines": ["I am not sma-a-all"]}]
LYRICS = "\n".join(l for s in SHEET for l in s["lines"])
SCRIPT = {"title": "The Climb", "story": [["The world", ["She runs a small shop."]]],
          "sheet": SHEET, "lyrics": LYRICS}


def story(beats=None, claim=None):
    """A story record; ``claim`` adds a testimonial row for the product beat."""
    doc = {"story_id": "arc-01", "beats": list(beats or BEATS), "product_reveal": 8}
    if claim is not None:
        doc["story_beats"] = [{"story_beat_id": "product_intro", "claim_source": claim}]
    return doc


def run_dir(doc, purpose=None):
    """A run folder with story/lyrics/script and (when given) the recorded purpose."""
    run = tempfile.mkdtemp(prefix="sa-purpose-")
    os.makedirs(os.path.join(run, "creative"))
    os.makedirs(os.path.join(run, "control"))
    with open(os.path.join(run, "creative", "story.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f)
    shutil.copy(LYRICS_FIXTURE, os.path.join(run, "creative", "lyrics.json"))
    with open(os.path.join(run, "creative", "script.json"), "w", encoding="utf-8") as f:
        json.dump(SCRIPT, f)
    if purpose is not None:
        with open(os.path.join(run, "control", "method.json"), "w", encoding="utf-8") as f:
            json.dump({"purpose": purpose}, f)
    card_answers.write(run, [{"id": "script", "n": 1, "text": "", "value": None}],
                       [{"id": "script"}])
    return run


def problems(doc, purpose=None):
    return stage._problems(run_dir(doc, purpose))


# --------------------------------------------------------------------------- #
# 1. each recorded purpose gets its own rules; the others stay base rules
# --------------------------------------------------------------------------- #

def test_lesson_purpose_accepts_lesson_intro_at_beat_eight():
    assert "story: beat-unknown" in " ".join(problems(story(LESSON_BEATS)))
    assert problems(story(LESSON_BEATS), "lesson") == []


def test_testimonial_purpose_requires_a_sourced_claim():
    assert "story: claim-source-missing" in " ".join(problems(story(), "testimonial"))
    assert problems(story(claim="the client's own words"), "testimonial") == []


def test_sales_purposes_keep_the_base_story_rules():
    for purpose in ("campaign", "paid_ad", "short_post"):
        assert problems(story(), purpose) == [], purpose
        assert "story: beat-unknown" in " ".join(problems(story(LESSON_BEATS), purpose)), purpose


# --------------------------------------------------------------------------- #
# 2. the purpose is never guessed: only the recorded, validated value counts
# --------------------------------------------------------------------------- #

def test_purpose_is_never_guessed_from_content_or_an_unknown_value():
    unsourced = story(claim="")                       # testimonial-shaped, no source
    assert problems(unsourced) == []                  # no record: no testimonial rule
    for value in ("sales", "TRAILER", "", 3, None):
        assert problems(unsourced, value) == [], value
    corrupt = run_dir(unsourced)
    with open(os.path.join(corrupt, "control", "method.json"), "w", encoding="utf-8") as f:
        f.write("{not json")
    assert stage._problems(corrupt) == []
    # a recorded, validated purpose is used, and the validator's own folding applies
    assert "story: claim-source-missing" in " ".join(problems(unsourced, "  Testimonial "))


# --------------------------------------------------------------------------- #
# 3. the validated purpose reaches run_stage, its one package, and the re-check
# --------------------------------------------------------------------------- #

def test_run_stage_carries_purpose_into_one_whole_package_once():
    run = run_dir(story(LESSON_BEATS), "lesson")
    delivered = []
    env = stage.run_stage(run, delivered.append)
    assert env["outcome"] == "waiting" and env["reason"] == "script-sent", env
    assert len(delivered) == 1                          # ONE package, not scene by scene
    text = delivered[0]
    for marker in ("THE STORY", "THE SCRIPT", "THE SONG LYRICS", "EARNED SONG HOOK",
                   "ERM DROP", "HERO SHIFT", "CALL TO ACTION", "approve both"):
        assert marker in text, marker
    asks = AE.open_asks(AE.ensure_record(SA.record_for(run)))
    assert len(asks) == 1 and asks[0]["kinds"] == ["script", "lyrics"]   # one action
    # the base rule would have refused the same story without the recorded purpose
    bare = run_dir(story(LESSON_BEATS))
    sent = []
    blocked = stage.run_stage(bare, sent.append)
    assert blocked["outcome"] == "blocked" and "story: beat-unknown" in " ".join(
        blocked["problems"]), blocked
    assert sent == [] and SA.record_for(bare) is None


def test_edit_recheck_still_carries_the_recorded_purpose():
    run = run_dir(story(claim="the client's own words"), "testimonial")
    delivered = []
    assert stage.run_stage(run, delivered.append)["outcome"] == "waiting"
    n = len(delivered)
    # the client's edit lands on disk without the source: the re-check must refuse
    with open(os.path.join(run, "creative", "story.json"), "w", encoding="utf-8") as f:
        json.dump(story(claim=""), f)
    env = stage.run_stage(run, delivered.append, reply="say gate, not door")
    assert env["outcome"] == "blocked", env
    assert "story: claim-source-missing" in " ".join(env["problems"])
    assert len(delivered) == n                          # nothing re-sent
    assert AE.active_approval(AE.ensure_record(SA.record_for(run)), "lyrics") is None


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
