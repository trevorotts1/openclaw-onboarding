#!/usr/bin/env python3
"""agnes_plan tests (BUILD-PLAN W1-agnes-core-U4).

Run: python3 -m pytest -q scripts/core/agnes_plan
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import agnes_plan as AP  # noqa: E402


def _refuses(fn, *args):
    """The code fn() refused with, or an AssertionError if it did not refuse."""
    try:
        fn(*args)
    except AP.PlanError as exc:
        return exc.code
    raise AssertionError("%r did not refuse %r" % (fn.__name__, (args,)))


# --- segments: fixed 10-second windows over the delivered length (SPEC A5.1)
def test_segment_counts():
    for d, n in ((28, 3), (88, 9), (58, 6), (298, 30), (30, 3), (10, 1), (1, 1)):
        segs = AP.segments(d)
        assert len(segs) == n, (d, len(segs), n)
        assert [s["index"] for s in segs] == list(range(1, n + 1))
        assert segs[0]["start_s"] == 0
        assert segs[-1]["end_s"] == d
        assert segs[-1]["start_s"] == (n - 1) * AP.SEGMENT_S
        for i in range(n - 1):
            assert segs[i]["end_s"] == segs[i + 1]["start_s"], segs
        assert all(s["end_s"] - s["start_s"] <= AP.SEGMENT_S for s in segs)
        assert all(s["end_s"] - s["start_s"] > 0 for s in segs)


def test_segment_counts_match_the_spec_examples():
    # SPEC A5.1: 90 s chosen -> D = 88 -> 9 clips; 30 -> 3; 60 -> 6; 5 min -> 30.
    assert len(AP.segments(88)) == 9
    assert len(AP.segments(28)) == 3
    assert len(AP.segments(58)) == 6
    assert len(AP.segments(298)) == 30


def test_length_cap_refuses_past_five_minutes():
    for d in (418, 300, 299):
        assert _refuses(AP.segments, d) == "AGNES_LENGTH_CAP", d
    for bad in (0, -5, "298", None, True):
        assert _refuses(AP.segments, bad) == "AGNES_PLAN_INPUT", bad


# --- lip-sync cutaways land on the segment that covers them (SPEC A5.1)
def test_cutaway_maps_onto_its_segment():
    segs = AP.segments(88)
    rows = AP.lipsync_cutaways(segs, [{"start_s": 23.0, "duration_s": 4.5}])
    assert rows == [{"start_s": 23.0, "end_s": 27.5, "segment_index": 3}], rows


def test_cutaway_edges_and_order():
    segs = AP.segments(88)
    rows = AP.lipsync_cutaways(segs, [
        {"start_s": 0.0, "end_s": 3.0},
        {"start_s": 19.999, "duration_s": 4.5},
        {"start_s": 20.0, "end_s": 24.5},
        {"start_s": 87.5, "duration_s": 0.5},
    ])
    assert [r["segment_index"] for r in rows] == [1, 2, 3, 9], rows
    assert abs(rows[1]["end_s"] - 24.499) < 1e-9, rows[1]


def test_cutaway_refuses_what_it_cannot_map():
    segs = AP.segments(88)
    assert _refuses(AP.lipsync_cutaways, [], [{"start_s": 0, "end_s": 1}])
    assert _refuses(AP.lipsync_cutaways, segs, [{"start_s": 120.0, "duration_s": 1}])
    assert _refuses(AP.lipsync_cutaways, segs, [{"duration_s": 1}])
    assert _refuses(AP.lipsync_cutaways, segs, [{"start_s": 5.0, "end_s": 1.0}])


# --- quota need (SPEC A5.2/A5.3)
def test_need_one_shape_and_both_shapes():
    segs = AP.segments(298)
    one = AP.need(segs, ["cartoon"])
    assert one == {"video_seconds": 300, "images": 30,
                   "allowance_seconds": 360}, one
    both = AP.need(segs, ["drawn", "real"])
    assert both["video_seconds"] == 600 and both["images"] == 60, both
    assert both["allowance_seconds"] == 720, both


def test_need_for_a_90_second_card_is_90_seconds():
    # U7 prints "Agnes video time: about N of your 500 seconds today" from this.
    assert AP.need(AP.segments(88), ["cartoon"])["video_seconds"] == 90
    assert AP.need(AP.segments(88), ["cartoon"])["allowance_seconds"] == 108
    # A bare clip count is accepted too.
    assert AP.need(9, ["cartoon"])["video_seconds"] == 90


# --- the segment prompt (trial A structure)
FIXTURE = {
    "story_beats": [
        {"story_beat_id": "BASELINE", "start_s": 0.0, "end_s": 5.0,
         "development": "she opens the laptop and starts the same old routine",
         "change": "she settles into the tired routine that never works",
         "intended_emotion": "weary recognition"},
        {"story_beat_id": "PAIN_BUILD", "start_s": 5.0, "end_s": 10.0,
         "development": "the routine fails again in front of her",
         "change": "she pushes back from the desk, hands flat on it",
         "intended_emotion": "rising frustration"},
    ],
}
BIBLES = {
    "character": "Maya, 34, curly dark hair, yellow jacket over a white tee, "
                 "jeans, white sneakers; open, tired, determined.",
    "style": "2D hand-painted cartoon, bold outline, flat warm palette of "
             "mustard, teal and cream, soft painterly shading.",
}


def test_video_prompt_carries_ten_per_second_rows_and_the_no_text_block():
    segs = AP.segments(30)
    prompt, count = AP.video_prompt(segs[0], FIXTURE, BIBLES)
    assert count == len(prompt) and count > 0
    rows = [ln for ln in prompt.splitlines() if ln.startswith("second ")]
    assert len(rows) == 10, len(rows)
    assert AP.NO_TEXT_BLOCK in prompt
    for channel in AP.CHANNELS:
        assert "%s:" % channel in rows[0], channel
    # the second-by-second direction comes from the blueprint's own beats
    assert "[BASELINE]" in rows[0] and "[BASELINE]" in rows[4]
    assert "[PAIN_BUILD]" in rows[5] and "[PAIN_BUILD]" in rows[9]
    assert "she pushes back from the desk" in rows[5]
    assert "rising frustration" in prompt
    for heading in ("CHARACTER BIBLE", "STYLE BIBLE", "FRAMING", "SETTING",
                    "PHYSICS", "CONTINUITY", "TEXT BAN", "PALETTE",
                    "EXPRESSION LIBRARY", "SELF-CHECK BEFORE FINISHING"):
        assert heading in prompt, heading


def test_video_prompt_trims_the_last_segment_rows():
    segs = AP.segments(28)
    prompt, _ = AP.video_prompt(segs[2], FIXTURE, BIBLES)
    rows = [ln for ln in prompt.splitlines() if ln.startswith("second ")]
    assert len(rows) == 8, len(rows)   # 20-28 s


def test_video_prompt_refuses_what_it_cannot_build():
    segs = AP.segments(30)
    assert _refuses(AP.video_prompt, segs[0], {"story_beats": []}, BIBLES)
    assert _refuses(AP.video_prompt, segs[0], FIXTURE, {"character": "x"})
    assert _refuses(AP.video_prompt, segs[0], FIXTURE, "not a bible")
    assert _refuses(AP.video_prompt, {"start_s": 0.0}, FIXTURE, BIBLES)


# --- the lip-sync close-up (SPEC A7)
def test_closeup_prompt_has_the_no_teeth_rule():
    p = AP.closeup_prompt("A tired mother in her thirties, curly brown hair")
    assert "no teeth" in p
    assert AP.NO_TEXT_BLOCK in p
    assert "front-facing" in p and "three-quarter" in p
    assert "never profile" in p
    assert "no shadow across the mouth" in p
    assert "nothing over the mouth" in p
    assert p.startswith("A tired mother in her thirties, curly brown hair")
    assert _refuses(AP.closeup_prompt, "   ")
    assert _refuses(AP.closeup_prompt, None)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("agnes_plan self-check: all passed")
