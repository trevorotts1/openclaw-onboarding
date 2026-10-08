#!/usr/bin/env python3
"""Part H H1: a lip-sync clip must sit at its line's real Suno start minus
its lead-in (within one frame). Stdlib, no ffmpeg. Run:
python3 core/final_assembler/test_lipsync_placement_h1.py"""
import os
import sys

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CORE)
import final_assembler.assembler as A           # noqa: E402


def _tl(first_dur):
    # filler 0-> (4.0-0.35)=3.65 s, then the lip clip for line L1 (start 4.0)
    return {"schema_version": A.TIMELINE_SCHEMA, "fps": 30, "width": 1920,
            "height": 1080, "song_path": None, "transition": "none",
            "segments": [{"src": "a.mp4", "dur": first_dur},
                         {"src": "lip.mp4", "dur": 2.5, "lip_sync": True,
                          "lip_sync_line_ids": ["L1"], "lip_lead_s": 0.35}],
            "timing": {"sections": [{"section_id": "v", "lyrics": [
                {"line_id": "L1", "start": 4.0, "end": 6.0, "text": "x",
                 "section_id": "v"}]}]}}


def run(first_dur):
    tl = _tl(first_dur)
    return A.validate_lipsync_placement(A.plan_timeline(tl), tl)


assert run(3.65) == 1                      # exact
assert run(3.65 + 1 / 30) == 1             # one frame late still passes
try:
    run(3.65 + 0.2)                        # re-timed by 0.2 s
    raise SystemExit("re-timed clip must fail")
except ValueError as e:
    assert str(e).startswith("LIPSYNC_RETIMED"), e
print("ok: lipsync placement H1")
