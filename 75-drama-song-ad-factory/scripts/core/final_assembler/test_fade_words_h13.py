#!/usr/bin/env python3
"""H13 tests: cross-fades vs words (Part H, Kiesett Stop Stale ad).

stdlib only, zero paid calls, no ffmpeg binary required.

Done when:
  1. a 0.4 s fade into a lip-sync clip whose first word is at 0.25 s is
     shortened so it ends >= 0.1 s before the word (the Stale 1 case);
  2. a first word too early for any fade becomes a cut, never a fade
     over the word;
  3. a late first word keeps the full default fade;
  4. a line with a 0.75 s inner gap passes only when ONE lip-sync
     segment holds the whole line; a cut-away inside the line fails.

Run: python3 core/final_assembler/test_fade_words_h13.py
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


def _lip(first_word_s=None, dur=4.0, **kw):
    s = {"src": "lip.mp4", "dur": dur, "lip_sync": True,
         "lip_sync_line_ids": ["l1"], "transition": "fade"}
    if first_word_s is not None:
        s["first_word_s"] = first_word_s
    s.update(kw)
    return s


BROLL = {"src": "b.mp4", "dur": 4.0}


def test_fade_shrinks_before_first_word():
    p = _plan([BROLL, _lip(0.25)])
    seg = p["segments"][1]
    gap = 0.25 - seg["xfade_dur"]
    check("0.4 s fade shrinks so it ends >= 0.1 s before the word",
          gap >= 0.1 - 1e-6 and seg["xfade_dur"] > 0, "gap %.3f" % gap)
    check("gate passes after the clamp",
          A.check_fade_before_first_word(p) == [])


def test_early_word_becomes_cut():
    p = _plan([BROLL, _lip(0.1)])
    seg = p["segments"][1]
    check("first word at 0.1 s: no fade over the word (cut)",
          seg["xfade_dur"] == 0 and seg["transition"] == "none")


def test_late_word_keeps_default_fade():
    p = _plan([BROLL, _lip(1.0)])
    check("first word at 1.0 s keeps the 0.4 s default fade",
          abs(p["segments"][1]["xfade_dur"] - 0.4) < 0.04)


def test_gate_catches_fade_over_word():
    p = _plan([BROLL, _lip(1.0)])
    p["segments"][1]["first_word_s"] = 0.25     # word moved: stale plan
    check("gate flags a fade that still covers the first word",
          A.check_fade_before_first_word(p) == ["FADE_COVERS_FIRST_WORD"])


# Stale 1: "How long" / "you planning" / "to wait?" with 0.75 s + 1.5 s gaps
WORDS = [{"start_s": 10.0, "end_s": 10.6}, {"start_s": 11.35, "end_s": 12.0},
         {"start_s": 13.5, "end_s": 14.0}]
LINE = [{"line_id": "l1", "start_s": 10.0, "end_s": 14.0, "words": WORDS}]


def test_long_gap_held():
    # one lip-sync segment covers 9.0 .. 15.0 (after 0.4 s fade-in)
    p = _plan([{"src": "a.mp4", "dur": 9.4}, _lip(None, dur=6.4)], LINE)
    check("line with 0.75/1.5 s gaps held on one lip-sync clip passes",
          A.check_long_gap_hold(p) == [])


def test_cutaway_in_gap_fails():
    p = _plan([{"src": "a.mp4", "dur": 9.4},
               _lip(None, dur=2.4),
               {"src": "cut.mp4", "dur": 2.0},
               _lip(None, dur=2.4, src="lip2.mp4")], LINE)
    check("cut-away inside a line with a long gap fails",
          A.check_long_gap_hold(p) == ["LONG_GAP_CUTAWAY"])


def test_short_gaps_ignored():
    short = [{"line_id": "l1", "start_s": 10.0, "end_s": 14.0,
              "words": [{"start_s": 10.0, "end_s": 11.0},
                        {"start_s": 11.3, "end_s": 14.0}]}]
    p = _plan([{"src": "a.mp4", "dur": 9.4},
               _lip(None, dur=2.4),
               {"src": "cut.mp4", "dur": 2.0}], short)
    check("gap under 0.5 s is not policed",
          A.check_long_gap_hold(p) == [])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("FAILED: %s" % FAILS if FAILS else "ALL PASS")
    sys.exit(1 if FAILS else 0)
