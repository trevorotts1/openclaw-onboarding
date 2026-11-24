#!/usr/bin/env python3
"""F-LETTER-GATE-HARD: letter gate fail-closed on every Kling/H3 take.

Proves lock 10: frame_text_gate(kling_only=True) rows every non-planned-text
segment (all Kling/H3 takes, not lip-sync only); a lettered take refuses
GARBLED_TEXT_FRAME even with a motion waiver present (letters never
waivable); a stub/extraction outage refuses LETTER_GATE_UNAVAILABLE, never
a silent pass.

stdlib only, zero paid calls, no ffmpeg. Run from core/:
python3 final_assembler/test_letter_gate_hard.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A  # noqa: E402
import final_assembler.frame_text as FT  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _plan(segments):
    return A.plan_timeline({
        "schema_version": A.TIMELINE_SCHEMA, "fps": 30,
        "width": 1920, "height": 1080, "song_path": None,
        "transition": "none", "segments": segments}, ".")


def test_gate_covers_every_take():
    plan = _plan([{"src": "take1.mp4", "dur": 5.0, "model": "kling-x"},
                  {"src": "take2.mp4", "dur": 6.0, "model": "h3"}])
    rows, fail = A.frame_text_gate(plan, kling_only=True)
    clips = [r["clip"] for r in rows if r.get("check") != "onscreen_text"]
    check("every take gets a letter row",
          clips == ["take1.mp4", "take2.mp4"], clips)
    check("stub outage refuses fail-closed, never passes",
          fail is not None
          and fail["reason_code"] == "LETTER_GATE_UNAVAILABLE", fail)


def test_lip_sync_only_mode_unchanged():
    plan = _plan([{"src": "lip.mp4", "dur": 5.0, "lip_sync": True},
                  {"src": "b.mp4", "dur": 6.0}])
    rows, fail = A.frame_text_gate(plan)
    clips = [r["clip"] for r in rows if r.get("check") != "onscreen_text"]
    check("lip-sync-only mode rows lip-sync clips only",
          clips == ["lip.mp4"], clips)
    check("stub lip-sync row still admits (F9 behavior)",
          fail is None, fail)


def test_lettered_take_refuses_despite_waiver():
    FT.register_extractor("letter-hard-texty",
                          lambda paths: ["SALE 50% OFF"] + [None] * (len(paths) - 1))
    plan = _plan([{"src": "take1.mp4", "dur": 5.0, "model": "kling-x"}])
    rows, fail = A.frame_text_gate(plan, kling_only=True,
                                   extractor="letter-hard-texty")
    check("lettered take flags the frame",
          rows and rows[0]["text_frames"] == [0], rows)
    check("lettered take refuses GARBLED_TEXT_FRAME",
          fail is not None and fail["reason_code"] == "GARBLED_TEXT_FRAME",
          fail)
    waiver = {"signed_by": "Trevor", "signature": "x",
              "who": "Trevor", "at": "now", "sites": ["motion"]}
    import never_again as _na
    check("motion waiver itself is valid",
          _na.check_waiver(waiver) is None)
    check("waiver scope stays motion-only (letters never waivable)",
          "motion" in _na.WAIVER_SCOPE
          and "letter" not in " ".join(_na.WAIVER_SCOPE).lower())


def test_extraction_outage_refuses():
    try:
        rows, fail = A.frame_text_gate(
            _plan([{"src": "take1.mp4", "dur": 5.0}]),
            kling_only=True, extractor="letter-hard-no-such-extractor")
    except FT.FrameTextError as exc:
        check("unknown extractor fails closed at the gate",
              exc.code == FT.BAD_EXTRACTOR, exc.code)
        return
    check("unknown extractor fails closed, never passes",
          fail is not None, fail)


if __name__ == "__main__":
    test_gate_covers_every_take()
    test_lip_sync_only_mode_unchanged()
    test_lettered_take_refuses_despite_waiver()
    test_extraction_outage_refuses()
    print("FAILURES: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)
