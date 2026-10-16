#!/usr/bin/env python3
"""W1-method-story-U2: method anchors on the twelve beats, and the hook-from
beat for a method run (Trevor 2026-10-13: the build toward the hook may start
once the solution has been introduced, never before it).

Covers: METHOD_ANCHORS covers exactly the twelve beats with the method's cue
names (ERM apex at the end of wound_deepens, no beat mapped to ERM_DROP), the
existing BEAT_TO_TIMING map is untouched, method_true_at_beat() answers
``the_turn`` at every length (the 60 s golden sheet's ``lowest_point`` moves
there), a lesson accepts ``lesson_intro`` for beat 8, a testimonial refuses a
product beat with no ``claim_source``, and a record validated with no purpose
behaves exactly as before.

Run: python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/story_arc/test_method_anchors.py
stdlib only, no network, no spend.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # scripts/core/story_arc
CORE = HERE.parent                              # scripts/core
sys.path.insert(0, str(CORE))

import story_arc.story_arc as SA                 # noqa: E402

#: The method's required music cues (method section 10.3 / SPEC C1).
CUES = ("BASELINE", "PAIN_BUILD", "ERM_DROP", "PAIN_DEEPEN", "HERO_SHIFT",
        "BREAKTHROUGH", "SOLUTION_HOOK", "COMMERCIAL_CONTINUATION")

#: W1-method-story-U2 "How", verbatim: beat -> cue.
WANT_ANCHORS = {
    "ordinary_world": "BASELINE",
    "humiliation": "PAIN_BUILD",
    "wound_deepens": "PAIN_BUILD",
    "frozen": "PAIN_DEEPEN",
    "seeing_it_too": "PAIN_DEEPEN",
    "failed_solutions": "PAIN_DEEPEN",
    "mentor": "HERO_SHIFT",
    "product_intro": "HERO_SHIFT",
    "doubt": "BREAKTHROUGH",
    "climb": "BREAKTHROUGH",
    "vindication": "SOLUTION_HOOK",
    "return_cta": "COMMERCIAL_CONTINUATION",
}

#: The mapping as it was before this unit: nothing existing moved.
WANT_TIMING = {
    "ordinary_world": "hook",
    "humiliation": "the_world",
    "wound_deepens": "villain_arrives",
    "frozen": "pain_deepens",
    "seeing_it_too": "lowest_point",
    "failed_solutions": "the_turn",
    "mentor": "the_turn",
    "product_intro": "the_turn",
    "doubt": "the_rise",
    "climb": "the_rise",
    "vindication": "the_rise",
    "return_cta": "call_to_action",
}


def _story(**over):
    story = {"story_id": "demo-arc-01", "beats": list(SA.BEATS), "product_reveal": 8}
    story.update(over)
    return story


def _lesson_story():
    beats = list(SA.BEATS)
    beats[7] = SA.LESSON_INTRO
    return _story(beats=beats)


def _claim(beat="product_intro", source="she cleared the card in ninety days"):
    return [{"story_beat_id": beat, "claim_source": source}]


def test_anchors_cover_the_twelve_beats():
    assert list(SA.METHOD_ANCHORS) == list(SA.BEATS)
    assert SA.METHOD_ANCHORS == WANT_ANCHORS, SA.METHOD_ANCHORS


def test_anchor_cues_are_the_methods_cues_and_carry_no_erm_drop():
    assert set(SA.METHOD_ANCHORS.values()) <= set(CUES)
    # The ERM apex is not a beat: no beat is anchored to ERM_DROP.
    assert "ERM_DROP" not in SA.METHOD_ANCHORS.values()
    assert SA.METHOD_ERM_APEX == {"beat": "wound_deepens", "position": "end"}


def test_existing_beat_to_timing_is_untouched():
    assert SA.BEAT_TO_TIMING == WANT_TIMING
    assert list(SA.BEATS) == ["ordinary_world", "humiliation", "wound_deepens", "frozen",
                              "seeing_it_too", "failed_solutions", "mentor", "product_intro",
                              "doubt", "climb", "vindication", "return_cta"]


def test_method_true_at_beat_is_the_turn_at_every_length():
    for length in (None, 30, 60, 90, 180, 300, 600):
        got = SA.method_true_at_beat(length)
        assert got == "the_turn", (length, got)
    # the 60 s golden sheet's lowest_point hook moves to the_turn
    assert SA.method_true_at_beat(60) != "lowest_point"
    assert SA.method_true_at_beat() in SA.TIMING_STAGES
    assert SA.METHOD_TRUE_AT_BEAT == "the_turn"


def test_method_purposes_are_the_five_spec_purposes():
    assert SA.METHOD_PURPOSES == ("campaign", "testimonial", "lesson", "paid_ad", "short_post")


def test_base_story_unchanged_with_and_without_a_purpose():
    valid = SA.load_fixture("valid.json")
    assert SA.validate_story(valid)["outcome"] == "ok"
    assert SA.validate_story(valid, purpose="campaign")["outcome"] == "ok"
    for name, want in (("missing-ordinary_world.json", "beat-missing"),
                       ("duplicate.json", "beat-duplicate"),
                       ("reordered.json", "beat-order"),
                       ("reveal-early.json", "reveal-early")):
        for purpose in (None, "campaign"):
            r = SA.validate_story(SA.load_fixture(name), purpose=purpose)
            assert (r["outcome"], r["reason_code"]) == ("rejected", want), (name, purpose, r)


def test_lesson_accepts_lesson_intro_for_beat_8():
    r = SA.validate_story(_lesson_story(), purpose="lesson")
    assert (r["outcome"], r["reason_code"]) == ("ok", "story-valid"), r
    assert r["beats"][7] == "lesson_intro"          # accepted, never renamed
    # the plain beat still validates for a lesson: accepted, not required
    assert SA.validate_story(_story(), purpose="lesson")["outcome"] == "ok"
    # without a purpose the base contract is untouched: beat-unknown
    r = SA.validate_story(_lesson_story())
    assert (r["outcome"], r["reason_code"]) == ("rejected", "beat-unknown"), r


def test_lesson_intro_off_beat_8_is_refused():
    beats = list(SA.BEATS)
    beats[3] = SA.LESSON_INTRO                      # frozen's slot, product_intro still at 8
    r = SA.validate_story(_story(beats=beats), purpose="lesson")
    assert r["outcome"] == "rejected", r
    assert r["reason_code"] in ("beat-duplicate", "beat-order"), r


def test_testimonial_requires_a_claim_source_on_the_product_beat():
    assert SA.validate_story(_story(story_beats=_claim()), purpose="testimonial")["outcome"] == "ok"
    # no claim record at all -> refused, CLAIM_UNSOURCED
    r = SA.validate_story(_story(), purpose="testimonial")
    assert (r["outcome"], r["reason_code"]) == ("rejected", "claim-source-missing"), r
    assert "CLAIM_UNSOURCED" in r["errors"][0]["detail"], r
    # an empty source is no source
    r = SA.validate_story(_story(story_beats=_claim(source="   ")), purpose="testimonial")
    assert r["reason_code"] == "claim-source-missing", r
    # the rule is off for every other purpose and for no purpose
    assert SA.validate_story(_story(), purpose="campaign")["outcome"] == "ok"
    assert SA.validate_story(_story())["outcome"] == "ok"
    # purpose is matched as written by the card
    assert SA.validate_story(_story(), purpose=" Testimonial ")["outcome"] == "rejected"


def test_existing_fixture_selftest_still_passes():
    assert SA.selftest() == 0                      # valid passes, every defect rejects
