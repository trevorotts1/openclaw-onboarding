#!/usr/bin/env python3
"""test_choir_lipsync_n07.py: N-07 choir energy comes before the close piece.

Run: python3 scripts/core/storyboard/test_choir_lipsync_n07.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import choir_lipsync as C  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


WIDE = {"shot_id": "T18", "route": "minimax-h3/reference-to-video",
        "shot_size": "wide", "camera_move": "slow push in",
        "location_id": "choir_loft"}
CLOSE = {"shot_id": "T19", "speaker": "choir", "lip_sync": True,
         "location_id": "choir_loft"}


def test_wide_nine_picture_lead_in_passes():
    check("N07-1 a wider nine-picture shot before the choir piece passes",
          C.check_choir_lead_in([WIDE, CLOSE]) == [])


def test_choir_piece_without_lead_in_is_refused():
    prev = {"shot_id": "T18", "route": "h3_start_end", "shot_size": "close",
            "location_id": "choir_loft"}
    findings = C.check_choir_lead_in([prev, CLOSE])
    check("N07-2 a close shot before the choir piece is refused",
          [f["code"] for f in findings] == [C.CHOIR_LEAD_IN_MISSING], findings)
    check("N07-3 a choir piece with nothing before it is refused",
          [f["code"] for f in C.check_choir_lead_in([CLOSE])]
          == [C.CHOIR_LEAD_IN_MISSING])


def test_non_choir_pieces_are_unaffected():
    lead = {"shot_id": "T01", "speaker": "lead", "lip_sync": True}
    check("N07-4 a lead lip-sync piece needs no choir lead-in",
          C.check_choir_lead_in([lead]) == [])


def test_run():
    test_wide_nine_picture_lead_in_passes()
    test_choir_piece_without_lead_in_is_refused()
    test_non_choir_pieces_are_unaffected()


if __name__ == "__main__":
    test_run()
    print("\n%s" % ("PASS 4/4" if not FAILS else "FAIL: %s" % ", ".join(FAILS)))
    sys.exit(1 if FAILS else 0)
