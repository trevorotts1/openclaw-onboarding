#!/usr/bin/env python3
"""test_story_fidelity_fpm6.py: the review demands the story artifacts (F-PM-6).

The location map and the wardrobe ledger are required; one place per shot; and
a chain stays in one place and carries its keyframes and its matched frame.

Run: python3 scripts/core/storyboard_director/test_story_fidelity_fpm6.py
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

def shot(sid, start, **kw):
    base = {"shot_id": sid, "song_start": start, "song_end": start + 4.0,
            "location_id": "church_sanctuary", "location_ids":
            ["church_sanctuary"], "wardrobe_ids": ["choir-robe"]}
    base.update(kw)
    return base

MAP = {"church_sanctuary": {"adjacency": ["narthex"]}}
LEDGER = {"choir-robe": {"accessories": ["stole"]}}

def test_fpm6():
    del FAILS[:]
    # F-PM-6: a place the plan uses with no map entry is an unexplained element.
    out = D.review_story_fidelity(
        [shot("T19", 0.0, location_id="chapel")], location_map=MAP,
        wardrobe_ledger=LEDGER)
    check("F-PM-6 an unlisted place is refused",
          D.UNEXPLAINED_STORY_ELEMENT in out["codes"], out)

    # A wardrobe the plan wears with no ledger entry is an unexplained element.
    out = D.review_story_fidelity(
        [shot("T19", 0.0, wardrobe_ids=["street-coat"])], location_map=MAP,
        wardrobe_ledger=LEDGER)
    check("F-PM-6 an unlisted wardrobe is refused",
          out["codes"] == [D.UNEXPLAINED_STORY_ELEMENT], out)

    # One place per shot: two places in one shot is a multi-place shot.
    out = D.review_story_fidelity(
        [shot("T19", 0.0,
              location_ids=["church_sanctuary", "church_steps"])],
        location_map=MAP, wardrobe_ledger=LEDGER)
    check("F-PM-6 two places in one shot are refused",
          out["codes"] == ["MULTI_PLACE_SHOT"], out)

    # Chain criteria: a chain that moves place mid-chain is not continuous.
    out = D.review_story_fidelity(
        [shot("T19", 0.0, chain_id="aisle-walk", keyframe_ids=["kf1"]),
         shot("T20", 4.0, chain_id="aisle-walk", keyframe_ids=["kf2"],
              location_id="church_steps", location_ids=["church_steps"],
              matched_frame="frame-18")],
        location_map={**MAP, "church_steps": {"adjacency": []}},
        wardrobe_ledger=LEDGER)
    check("F-PM-6 a chain that moves place is refused",
          out["codes"] == ["CHAIN_NOT_CONTINUOUS"], out)

    # A chain with no keyframes and no matched frame is not continuous either.
    out = D.review_story_fidelity(
        [shot("T19", 0.0, chain_id="aisle-walk"),
         shot("T20", 4.0, chain_id="aisle-walk")],
        location_map=MAP, wardrobe_ledger=LEDGER)
    check("F-PM-6 a chain with no keyframes or matched frame is refused",
          out["codes"] == ["CHAIN_NOT_CONTINUOUS"], out)

    # A clean plan with its artifacts passes.
    out = D.review_story_fidelity(
        [shot("T19", 0.0, chain_id="aisle-walk", keyframe_ids=["kf1"]),
         shot("T20", 4.0, chain_id="aisle-walk", keyframe_ids=["kf2"],
              matched_frame="frame-18")],
        location_map=MAP, wardrobe_ledger=LEDGER)
    check("F-PM-6 a explained plan passes", out["outcome"] == "pass", out)

    assert not FAILS, FAILS


if __name__ == "__main__":
    test_fpm6()
    print()
    print("FAILED: %d" % len(FAILS) if FAILS else "PASS: all checks")
    sys.exit(1 if FAILS else 0)
