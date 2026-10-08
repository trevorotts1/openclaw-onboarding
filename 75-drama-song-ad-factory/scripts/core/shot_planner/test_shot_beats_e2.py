#!/usr/bin/env python3
"""E2 tests for the shot planner beat_cut marker (manual Part E E2).

The trunk carries beat_cut as authored marker data, consumed by the
planner (the mark_on_beats helper from the original E2 draft never
shipped — it was dropped in the w5b hand-merge). The marker's real
contract, checked here:

  1. BEAT_CUT_MIN_SHOT_S (1.0 s) applies to beat_cut-marked shots,
     MIN_SHOT_S (1.5 s) to unmarked ones (plan_shot_floor);
  2. a beat_cut boundary refuses to merge across — the short shot
     extends instead (and an unmarked neighbour still merges);
  3. validate_timeline_min_shot applies the same floors on timelines;
  4. the marker rides along through bind_plan untouched.

Fade-default / HARD_CUT_UNMARKED acceptance lives in the sibling
final_assembler/test_transitions_e2.py.

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


def _shot(start, end=None, sid=None, beat_cut=None):
    sh = {"shot_id": sid or "s%s" % start,
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
    if beat_cut is not None:
        sh["beat_cut"] = beat_cut
    return sh


def _dur(sh):
    return sh["song_end"] - sh["song_start"]


# 1. floors: 1.0 s for beat_cut shots, 1.5 s unmarked ------------------------
def test_defaults_and_floors():
    check("MIN_SHOT_S is 1.5", SP.MIN_SHOT_S == 1.5)
    check("BEAT_CUT_MIN_SHOT_S is 1.0", SP.BEAT_CUT_MIN_SHOT_S == 1.0)

    # plan_shot_floor reports only actioned shots; a shot already at or
    # above its floor passes through untouched with no report row.
    bc = _shot(0.0, end=1.2, beat_cut=True)
    out, rep = SP.plan_shot_floor([bc])
    check("beat_cut 1.2s shot passes floor unchanged, no action row",
          _dur(out[0]) == 1.2 and rep == [],
          "got %r %r" % (_dur(out[0]), rep))

    bc_exact = _shot(2.0, end=3.0, beat_cut=True)
    out, rep = SP.plan_shot_floor([bc_exact])
    check("beat_cut shot exactly 1.0s passes unchanged",
          _dur(out[0]) == 1.0 and rep == [],
          "got %r %r" % (_dur(out[0]), rep))

    plain = _shot(0.0, end=1.2)
    out, rep = SP.plan_shot_floor([plain])
    check("unmarked 1.2s shot extends to 1.5s floor",
          abs(_dur(out[0]) - 1.5) < 1e-9 and rep
          and rep[0]["floor_s"] == 1.5 and rep[0]["action"] == "extended",
          "got %r %r" % (_dur(out[0]), rep))

    plain_ok = _shot(4.0, end=5.5)
    out, rep = SP.plan_shot_floor([plain_ok])
    check("unmarked shot exactly 1.5s passes unchanged",
          _dur(out[0]) == 1.5 and rep == [],
          "got %r %r" % (_dur(out[0]), rep))


# 2. beat_cut boundary refuses to merge across -------------------------------
def test_beat_cut_blocks_merge():
    # Control: two adjacent unmarked shots, the second short — they merge.
    ctrl = [_shot(2.0, end=3.0, sid="cA"), _shot(3.0, end=3.9, sid="cB")]
    out, rep = SP.plan_shot_floor([dict(s) for s in ctrl])
    check("control: unmarked short shot merges into neighbour",
          len(out) == 1 and abs(_dur(out[0]) - 1.9) < 1e-9,
          "got %d shots %r" % (len(out), [_dur(s) for s in out]))

    # Same shape with the boundary marked beat_cut: merge is refused, the
    # leading shot extends backwards and the short marked shot extends to
    # its own 1.0 s floor.
    shots = [_shot(2.0, end=3.0, sid="A"), _shot(3.0, end=3.9, sid="B",
                                                  beat_cut=True)]
    out, rep = SP.plan_shot_floor([dict(s) for s in shots])
    by_id = {s["shot_id"]: s for s in out}
    check("beat_cut boundary keeps both shots", len(out) == 2,
          "got %d" % (len(out),))
    check("leading shot extended back to 1.5s",
          abs(_dur(by_id["A"]) - 1.5) < 1e-9 and by_id["A"]["song_start"] == 1.5,
          "got %r %r" % (_dur(by_id["A"]), by_id["A"]))
    check("marked short shot extended to its 1.0s floor",
          abs(_dur(by_id["B"]) - 1.0) < 1e-9,
          "got %r" % (_dur(by_id["B"]),))
    floors = {r["shot_id"]: r["floor_s"] for r in rep}
    check("report floors 1.5 / 1.0",
          floors.get("A") == 1.5 and floors.get("B") == 1.0,
          "got %r" % (floors,))


# 3. validate_timeline_min_shot applies the same floors ----------------------
def test_timeline_min_shot_floors():
    tl = {"segments": [
        {"src": "a.mp4", "dur": 1.2, "beat_cut": True},
        {"src": "b.mp4", "dur": 1.2},
        {"src": "c.mp4", "dur": 1.0, "beat_cut": True},
        {"src": "d.mp4", "dur": 0.99, "beat_cut": True},
        {"src": "e.mp4", "dur": 1.5},
    ]}
    errs = SP.validate_timeline_min_shot(tl)
    check("beat_cut 1.2s and 1.0s segments pass, unmarked 1.2s fails",
          len(errs) == 2 and "segments[1]" in errs[0]
          and "1.50s" in errs[0] and "segments[3]" in errs[1]
          and "1.00s" in errs[1],
          "got %r" % (errs,))


# 4. marker rides through bind_plan untouched ---------------------------------
def test_bind_plan_integration():
    """A beat_cut-marked plan binds like any other; the authored marker
    is not stripped or rewritten."""
    timing = {"song_id": "x", "duration_seconds": 30.0,
              "sections": [{"section_id": "s1", "lyrics": [
                  {"line_id": "L1", "start": 2.0, "end": 4.0, "text": "a"}]}]}
    shots = [_shot(1.9, end=4.5, beat_cut=True)]
    out = SP.bind_plan(shots, timing)
    check("bind_plan passes with marker", out["outcome"] == "ok")
    check("marker survives bind", shots[0]["beat_cut"] is True)


def main():
    for fn in (test_defaults_and_floors, test_beat_cut_blocks_merge,
               test_timeline_min_shot_floors, test_bind_plan_integration):
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