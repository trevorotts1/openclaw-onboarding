#!/usr/bin/env python3
"""test_world_building_n106.py: places that stay the same (row N-106, 3M).

The location bible with its reference pictures, the prop ledger's one line per
prop per scene, background life, and both states of a place the story changes.

Run: python3 scripts/core/storyboard/test_world_building_n106.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import storyboard.world_building as W                        # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def codes(defects):
    return sorted({d["code"] for d in defects})


# A place with no reference pictures cannot hold one look.
world = {"locations": [{"location_id": "sanctuary"}]}


def test_run():
    check("N-106 a place with no reference pictures is refused",
          codes(W.validate_location_bible(world)) == ["LOCATION_REFERENCE_MISSING"],
          codes(W.validate_location_bible(world)))

    # A place with its reference is clean.
    ok = {"locations": [{"location_id": "sanctuary",
                         "reference_pictures": ["refs/sanctuary-wide.png"]}]}
    check("N-106 a place with its reference passes",
          W.validate_location_bible(ok) == [], W.validate_location_bible(ok))

    # A place the story changes carries both states.
    changed = {"locations": [{"location_id": "home", "changes": True,
                              "reference_pictures": ["refs/home.png"],
                              "states": {"before": ["refs/home-before.png"]}}]}
    check("N-106 a changed place with only one state is refused",
          codes(W.validate_location_bible(changed)) == ["PLACE_STATE_MISSING"],
          codes(W.validate_location_bible(changed)))

    both = {"locations": [{"location_id": "home", "changes": True,
                           "reference_pictures": ["refs/home.png"],
                           "states": {"before": ["refs/a.png"],
                                      "after": ["refs/b.png"]}}]}
    check("N-106 a changed place with both states passes",
          W.validate_location_bible(both) == [], W.validate_location_bible(both))

    # One ledger line per story prop per scene.
    ledger = {"props": [{"prop_id": "letter",
                         "scenes": {"s1": {"place": "table", "state": "unopened",
                                           "holder": "none"}}}]}
    check("N-106 a complete prop ledger line passes",
          W.validate_prop_ledger(ledger, ["s1"]) == [],
          W.validate_prop_ledger(ledger, ["s1"]))
    check("N-106 a prop with no line for its scene is refused",
          codes(W.validate_prop_ledger(ledger, ["s1", "s2"]))
          == ["PROP_LEDGER_INCOMPLETE"],
          codes(W.validate_prop_ledger(ledger, ["s1", "s2"])))
    check("N-106 an empty prop ledger is refused",
          codes(W.validate_prop_ledger({}, [])) == ["PROP_LEDGER_MISSING"],
          codes(W.validate_prop_ledger({}, [])))

    # A place in use names who is there, how many, what they are doing.
    in_use = {"locations": [{"location_id": "sanctuary", "in_use": True,
                             "reference_pictures": ["r.png"]}]}
    check("N-106 a place in use with no background life is refused",
          codes(W.validate_background_life(in_use)) == ["BACKGROUND_LIFE_MISSING"],
          codes(W.validate_background_life(in_use)))

    full = {"locations": [{"location_id": "sanctuary", "crowd_state": "full",
                           "reference_pictures": ["r.png"],
                           "background_life": {"who": "congregation",
                                               "doing": "standing and singing"}}]}
    check("N-106 a full place with no count is refused",
          codes(W.validate_background_life(full)) == ["BACKGROUND_LIFE_MISSING"],
          codes(W.validate_background_life(full)))

    full_ok = {"locations": [{"location_id": "sanctuary", "crowd_state": "full",
                              "reference_pictures": ["r.png"],
                              "background_life": {"who": "congregation",
                                                  "count": 120,
                                                  "doing": "standing and singing"}}]}
    check("N-106 a full place with a count passes",
          W.validate_background_life(full_ok) == [],
          W.validate_background_life(full_ok))

    # The one packet the review reads reports every code together.
    packet = W.validate_world_building({"locations": [{"location_id": "x"}]},
                                       {"props": []}, ["s1"])
    check("N-106 the review packet carries every code",
          not packet["ok"] and "LOCATION_REFERENCE_MISSING" in packet["codes"]
          and "PROP_LEDGER_MISSING" in packet["codes"], packet["codes"])

    assert not FAILS, FAILS


if __name__ == "__main__":
    test_run()
    print()
    print("FAILED: %d" % len(FAILS) if FAILS else "PASS: all checks")
    sys.exit(1 if FAILS else 0)
