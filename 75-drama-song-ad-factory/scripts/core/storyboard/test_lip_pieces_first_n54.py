#!/usr/bin/env python3
"""test_lip_pieces_first_n54.py: lip pieces first, no short story shot (N-54).

Run: python3 scripts/core/storyboard/test_lip_pieces_first_n54.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import storyboard.story_checks as C                          # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def lip(sid, a, b):
    return {"shot_id": sid, "song_start": a, "song_end": b, "route": "omnihuman"}


def story(sid, a, b):
    return {"shot_id": sid, "song_start": a, "song_end": b,
            "route": "h3_start_end"}


def codes(rows):
    return sorted({f["code"] for f in C.check_lip_pieces_first(rows)})


# A story shot laid over a lip-sync piece is the squeeze 3.4a forbids.
squeezed = [lip("L1", 40.0, 48.0), story("S1", 42.0, 46.0)]


def test_run():
    check("N-54 a story shot inside a lip window is refused",
          codes(squeezed) == ["LIP_PIECES_NOT_FIRST"], codes(squeezed))

    # A story shot laid after the pieces is clean.
    clean = [lip("L1", 40.0, 48.0), story("S1", 48.0, 52.0)]
    check("N-54 adjacent story shots pass", codes(clean) == [], codes(clean))

    # A story shot under 2.5 seconds is refused.
    short = [story("S1", 10.0, 12.0)]
    check("N-54 a story shot under 2.5 s is refused",
          codes(short) == ["SHOT_TOO_SHORT"], codes(short))

    # A lip-sync piece under 2.5 s is not a story shot and is not refused here.
    short_lip = [lip("L1", 10.0, 12.0)]
    check("N-54 a short lip piece is not a short story shot",
          codes(short_lip) == [], codes(short_lip))

    # The explicit flag is still honoured.
    flagged = [story("S1", 60.0, 66.0), dict(story("S2", 66.0, 72.0),
                                             under_lip_window=True)]
    check("N-54 the explicit flag still refuses",
          codes(flagged) == ["LIP_PIECES_NOT_FIRST"], codes(flagged))

    assert not FAILS, FAILS


if __name__ == "__main__":
    test_run()
    print()
    print("FAILED: %d" % len(FAILS) if FAILS else "PASS: all checks")
    sys.exit(1 if FAILS else 0)
