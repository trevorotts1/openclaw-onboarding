#!/usr/bin/env python3
"""test_opening_n05.py: the opening passage (row N-05, section 3.2).

Run: python3 scripts/core/storyboard/test_opening_n05.py
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


def row(**kw):
    base = {"shot_id": "T1", "song_start": 1.0, "song_end": 9.0,
            "route": "omnihuman", "speaker": "ava", "lipsync_label": "lead"}
    base.update(kw)
    return base


def codes(rows, **kw):
    return sorted({f["code"] for f in C.check_opening(rows, **kw)})


# A lead passage starting by second 3 and holding 8 seconds passes.


def test_run():
    check("N-05 a proper opening passage passes", codes([row()]) == [], codes([row()]))

    # A passage that starts after second 3 is refused.
    late = [row(song_start=5.0, song_end=13.0)]
    check("N-05 a late first line is refused",
          codes(late) == ["OPENING_PASSAGE_MISSING"], codes(late))

    # Under 8 seconds inside the first 15 is refused.
    short = [row(song_start=1.0, song_end=6.0)]
    check("N-05 a short opening passage is refused",
          codes(short) == ["OPENING_PASSAGE_MISSING"], codes(short))

    # The passage must be the LEAD's: a choir-labelled early piece does not count.
    choir = [row(lipsync_label="choir")]
    check("N-05 a choir piece is not the lead's opening",
          codes(choir) == ["OPENING_PASSAGE_MISSING"], codes(choir))

    # lead_id resolves a named lead when the row carries no label.
    unnamed = [{"shot_id": "T1", "song_start": 1.0, "song_end": 9.0,
                "route": "omnihuman", "speaker": "ava"}]
    check("N-05 lead_id names the lead",
          codes(unnamed, lead_id="ava") == [], codes(unnamed, lead_id="ava"))
    other = [{"shot_id": "T1", "song_start": 1.0, "song_end": 9.0,
              "route": "omnihuman", "speaker": "ben"}]
    check("N-05 another singer is not the lead",
          codes(other, lead_id="ava") == ["OPENING_PASSAGE_MISSING"],
          codes(other, lead_id="ava"))

    # The passage is measured only inside the first 15 seconds.
    over = [row(song_start=1.0, song_end=30.0)]
    check("N-05 seconds are counted only inside the first 15 s",
          codes(over) == [], codes(over) or "would need 8s inside 15s")

    assert not FAILS, FAILS


if __name__ == "__main__":
    test_run()
    print()
    print("FAILED: %d" % len(FAILS) if FAILS else "PASS: all checks")
    sys.exit(1 if FAILS else 0)
