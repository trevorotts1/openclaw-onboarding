#!/usr/bin/env python3
"""PAR003 tests: two assembler fixes that existed only in the 999 copy.

stdlib only, zero paid calls, no ffmpeg binary required.

  1. plan_timeline carries a segment's "hold" flag into the plan, so the
     H3 per-segment duplicate gate (fps_conform.segment_dup_report) can
     exempt a deliberate still; without it every hold failed the gate.
  2. h5_gates turns a malformed timeline line (missing start_s) into the
     loud TIMELINE_BAD_LINES receipt instead of a raw KeyError.

Run: python3 core/final_assembler/test_assembler_parity_par003.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A       # noqa: E402

FAILS = []
FPS = 30


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _plan(segs, lines=None):
    tl = {"schema_version": A.TIMELINE_SCHEMA, "fps": FPS, "width": 1920,
          "height": 1080, "song_path": None, "segments": segs,
          "transition_duration": 0.4}
    if lines is not None:
        tl["lines"] = lines
    return A.plan_timeline(tl, ".")


def test_hold_flag_reaches_plan():
    p = _plan([{"src": "a.mp4", "dur": 4.0},
               {"src": "still.mp4", "dur": 4.0, "hold": True}])
    check("hold true rides the plan", p["segments"][1]["hold"] is True)
    check("hold defaults false", p["segments"][0]["hold"] is False)


def test_bad_line_is_loud_not_a_crash():
    p = _plan([{"src": "a.mp4", "dur": 4.0, "shows_line_ids": ["l1"]}])
    p["lines"] = [{"line_id": "l1", "end_s": 4.0}]          # no start_s
    fail, _ev = A.h5_gates(p)
    check("TIMELINE_BAD_LINES receipt",
          fail is not None and fail["reason_code"] == "TIMELINE_BAD_LINES",
          str(fail))


if __name__ == "__main__":
    test_hold_flag_reaches_plan()
    test_bad_line_is_loud_not_a_crash()
    if FAILS:
        print("FAILED: %s" % ", ".join(FAILS))
        sys.exit(1)
    print("all ok")
