#!/usr/bin/env python3
"""N-121 (3M.4): the world-continuity check on the rows.

Crowd state to within its range, choir headcount, the room's set pieces, and
the story clock's light. A MAJOR finding fails the plan.

Run: python3 scripts/core/storyboard/test_story_checks_n121.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import storyboard.story_checks as C                    # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        "" if cond else "  <- %r" % (detail,)))
    if not cond:
        FAILS.append(name)

def codes(rows):
    return sorted({r["code"] for r in rows})

WORLD = {"places": {"sanctuary": {
    "crowd_states": {"service": {"min": 100, "max": 140}},
    "choir": {"count": 12},
    "set_pieces": ["cross", "loft"],
    "clock": {"morning": "warm"},
}}}

def row(**kw):
    base = {"shot_id": "S1", "location_id": "sanctuary", "crowd_state": "service",
            "crowd_count": 120, "choir_count": 12, "light": "warm",
            "time_of_day": "morning", "set_pieces": ["cross", "loft"],
            "shows_whole_place": True}
    base.update(kw)
    return base

def test_clean():
    check("N-121 a matching row passes", C.check_world([row()], WORLD) == [])

def test_crowd():
    check("N-121 an empty room in a full scene refuses CROWD_MISMATCH",
          codes(C.check_world([row(crowd_count=3)], WORLD)) == ["CROWD_MISMATCH"])
    check("N-121 a full room passes",
          C.check_world([row(crowd_count=125)], WORLD) == [])

def test_choir_set_clock():
    check("N-121 a choir of 3 where 12 stand refuses CHOIR_COUNT_MISMATCH",
          codes(C.check_world([row(choir_count=3)], WORLD)) == ["CHOIR_COUNT_MISMATCH"])
    check("N-121 a whole-place shot missing its set pieces refuses SET_PIECE_MISSING",
          codes(C.check_world([row(set_pieces=["cross"])], WORLD)) == ["SET_PIECE_MISSING"])
    check("N-121 a morning scene lit cold refuses LIGHT_OFF_CLOCK",
          codes(C.check_world([row(light="cold")], WORLD)) == ["LIGHT_OFF_CLOCK"])

def test_canonical_shape():
    # The World Bible record carries locations as a LIST of rows
    # (world_bible/world.schema.json). The check must read that shape too, or
    # it fails open and every N-121 code is unreachable on a real run.
    canonical = {"locations": [dict(WORLD["places"]["sanctuary"],
                                    location_id="sanctuary")]}
    check("N-121 the canonical list-shaped world is read, not skipped",
          codes(C.check_world([row(crowd_count=3)], canonical)) == ["CROWD_MISMATCH"],
          C.check_world([row(crowd_count=3)], canonical))
    check("N-121 the canonical list-shaped world passes a matching row",
          C.check_world([row()], canonical) == [],
          C.check_world([row()], canonical))

def test_run():
    test_clean()
    test_crowd()
    test_choir_set_clock()
    test_canonical_shape()

if __name__ == "__main__":
    test_run()
    print("\n%s" % ("PASS" if not FAILS else "FAIL: %s" % ", ".join(FAILS)))
    sys.exit(1 if FAILS else 0)
