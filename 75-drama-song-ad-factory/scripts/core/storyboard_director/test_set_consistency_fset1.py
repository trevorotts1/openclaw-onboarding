#!/usr/bin/env python3
"""test_set_consistency_fset1.py: one identifier, one room (row F-SET-1).

The two cases the plan names: two takes sharing one location identifier that
diverge beyond the join threshold (the 2-sanctuary / 3-exterior class) are
refused ``SET_INCONSISTENT``; a render whose geometry contradicts the map
adjacency (the narthex class: door, hall, vestry links) is refused
``MAP_RENDER_MISMATCH``.

Run: python3 scripts/core/storyboard_director/test_set_consistency_fset1.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from storyboard_director import storyboard_director as D      # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        "" if cond else "  <- %r" % (detail,)))
    if not cond:
        FAILS.append(name)

def take(tid, loc="church_sanctuary", rendered=None):
    row = {"take_id": tid, "location_id": loc}
    if rendered is not None:
        row["rendered_adjacency"] = rendered
    return row

def test_fset1():
    del FAILS[:]
    # F-SET-1: two starts under one identifier that do not join are two rooms.
    out = D.review_set_consistency(
        [take("T19"), take("T21")],
        join_scores={("T19", "T21"): 0.41})
    check("F-SET-1 divergent same-identifier takes are refused",
          out["codes"] == ["SET_INCONSISTENT"], out)
    check("F-SET-1 the refusal names the second take",
          out["findings"][0]["take_id"] == "T21", out["findings"])

    # A pair that joins above the threshold is one room and passes.
    out = D.review_set_consistency(
        [take("T19"), take("T21")], join_scores={("T19", "T21"): 0.93})
    check("F-SET-1 a joining pair passes", out["outcome"] == "pass", out)

    # A take measured against its location reference uses the same threshold.
    out = D.review_set_consistency(
        [take("T25")], join_scores={"T25": 0.62})
    check("F-SET-1 a take short of its location reference is refused",
          out["codes"] == ["SET_INCONSISTENT"], out)

    # F-SET-1: the map says sanctuary, narthex, vestry are linked; the render
    # shows a door into the hall that the map does not carry.
    MAP = {"church_sanctuary": {"adjacency": ["narthex", "vestry"]}}
    out = D.review_set_consistency(
        [take("T23", rendered={"north door": "narthex",
                               "east door": "vestry",
                               "side door": "fellowship_hall"})],
        location_map=MAP)
    check("F-SET-1 a render that contradicts the map is refused",
          out["codes"] == ["MAP_RENDER_MISMATCH"], out)

    # The map names a link the render never shows: that is a mismatch too.
    out = D.review_set_consistency(
        [take("T23", rendered={"north door": "narthex"})], location_map=MAP)
    check("F-SET-1 a map link the render never shows is refused",
          out["codes"] == ["MAP_RENDER_MISMATCH"], out)

    # A render that agrees with the map passes.
    out = D.review_set_consistency(
        [take("T23", rendered={"north door": "narthex",
                               "east door": "vestry"})], location_map=MAP)
    check("F-SET-1 a render that agrees with the map passes",
          out["outcome"] == "pass", out)

    assert not FAILS, FAILS


if __name__ == "__main__":
    test_fset1()
    print()
    print("FAILED: %d" % len(FAILS) if FAILS else "PASS: all checks")
    sys.exit(1 if FAILS else 0)
