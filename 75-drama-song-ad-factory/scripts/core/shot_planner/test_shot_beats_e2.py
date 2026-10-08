#!/usr/bin/env python3
"""E2 tests for the shot planner on-beat marker (manual Part E E2).

stdlib only. Run: python3 core/shot_planner/test_shot_beats_e2.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import shot_planner.shot_planner as SP     # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _shot(start, end=None, sid=None):
    return {"shot_id": sid or "s%s" % start,
            "song_start": start,
            "song_end": end if end is not None else start + 2.0,
            "lyric_line_ids": ["L1"],
            "story_stage": "act-1", "visual_objective": "show pain",
            "character_ids": ["c1"], "wardrobe_ids": ["w1"],
            "location_id": "kitchen", "product_visibility": "background",
            "camera_direction": "slow push",
            "reference_assets": [], "image_model_capability_request":
            {"capabilities": ["text-to-image"]},
            "video_model_capability_request": {"capabilities": ["text-to-video"]},
            "continuity_constraints": [], "negative_constraints": [],
            "cost_estimate": 0, "qc_requirements": [], "status": "planned"}


def test_line_starts_are_beats():
    """Timing map without beats/bpm: lyric line starts are the anchors."""
    timing = {"song_id": "x", "duration_seconds": 30.0,
              "sections": [{"section_id": "s1", "lyrics": [
                  {"line_id": "L1", "start": 4.0, "end": 6.0, "text": "a"},
                  {"line_id": "L2", "start": 8.0, "end": 10.0, "text": "b"}]}]}
    plan = [_shot(3.9), _shot(8.05), _shot(6.0)]
    out = SP.mark_on_beats(plan, timing)
    check("0.1s off line start -> beat_cut true",
          out[0]["beat_cut"] is True
          and out[0]["beat_cut_delta_s"] <= SP.BEAT_TOLERANCE_S,
          "got %r" % (out[0],))
    check("0.05s off line start -> beat_cut true", out[1]["beat_cut"] is True)
    check(">0.25s from any line start -> beat_cut false",
          out[2]["beat_cut"] is False, "got %r" % (out[2],))


def test_explicit_beats_list():
    timing = {"song_id": "x", "duration_seconds": 20.0,
              "beats": [0.0, 0.5, 1.0, 1.5, 2.0],
              "sections": [{"section_id": "s1", "lyrics": [
                  {"line_id": "L1", "start": 3.0, "end": 5.0, "text": "a"}]}]}
    out = SP.mark_on_beats([_shot(1.45), _shot(0.8)], timing)
    check("explicit beats: 1.45 within 0.25 of 1.5 -> true",
          out[0]["beat_cut"] is True)
    check("explicit beats: 0.8 nearest beat 0.5/1.0 delta 0.2 -> true",
          out[1]["beat_cut"] is True and out[1]["beat_cut_delta_s"] == 0.2,
          "got %r" % (out[1],))
    out2 = SP.mark_on_beats([_shot(1.87)], timing)
    check("explicit beats: 1.87 nearest 2.0 delta 0.13 -> true",
          out2[0]["beat_cut"] is True)
    out3 = SP.mark_on_beats([_shot(2.3)], timing)
    check("explicit beats: 2.3 nearest 2.0 or 2.5 -> 0.3 away false",
          out3[0]["beat_cut"] is False, "got %r" % (out3[0],))


def test_bpm_grid():
    timing = {"song_id": "x", "duration_seconds": 20.0, "bpm": 120,
              "sections": [{"section_id": "s1", "lyrics": [
                  {"line_id": "L1", "start": 3.0, "end": 5.0, "text": "a"}]}]}
    # 120 bpm -> beat every 0.5 s from 0
    out = SP.mark_on_beats([_shot(1.99), _shot(2.3)], timing)
    check("bpm grid: 1.99 near 2.0 -> true", out[0]["beat_cut"] is True)
    check("bpm grid: 2.3 nearest 2.5 delta 0.2 -> true",
          out[1]["beat_cut"] is True, "got %r" % (out[1],))


def test_bind_plan_integration():
    """bind_plan output + marked shots carry the marker through QC."""
    timing = {"song_id": "x", "duration_seconds": 30.0,
              "sections": [{"section_id": "s1", "lyrics": [
                  {"line_id": "L1", "start": 2.0, "end": 4.0, "text": "a"}]}]}
    shots = [_shot(1.9, end=4.5)]
    SP.mark_on_beats(shots, timing)
    out = SP.bind_plan(shots, timing)
    check("bind_plan passes with marker", out["outcome"] == "ok")
    check("marker survives bind", shots[0]["beat_cut"] is True)


def main():
    for fn in (test_line_starts_are_beats, test_explicit_beats_list,
               test_bpm_grid, test_bind_plan_integration):
        try:
            fn()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % getattr(fn, "__name__", "test"), False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all E2 shot-beat checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())