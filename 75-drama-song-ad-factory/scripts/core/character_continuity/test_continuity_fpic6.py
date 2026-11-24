#!/usr/bin/env python3
"""test_continuity_fpic6.py: the wardrobe and location walk across shots (F-PIC-6).

The robe shot is the proven case: a character changes wardrobe mid-scene with
no ledger entry, and the cross-shot check refuses ``WARDROBE_BREAK``. A place
that changes inside one scene without a moving transition refuses
``LOCATION_BREAK``.

Run: python3 scripts/core/character_continuity/test_continuity_fpic6.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import character_continuity.continuity as C      # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        "" if cond else "  <- %r" % (detail,)))
    if not cond:
        FAILS.append(name)

def shot(sid, start, **kw):
    base = {"shot_id": sid, "song_start": start, "song_end": start + 4.0,
            "scene_id": "S1", "character_ids": ["denise"],
            "wardrobe_ids": ["choir-robe"], "location_id": "church_sanctuary"}
    base.update(kw)
    return base

LEDGER = {"choir-robe": {"accessories": ["stole"]},
          "street-coat": {"accessories": []}}

def test_fpic6():
    del FAILS[:]
    # F-PIC-6: the robe comes off mid-scene with no ledger entry for the new one.
    out = C.check_cross_shot_continuity(
        [shot("T19", 0.0),
         shot("T20", 4.0, wardrobe_ids=["street-coat"])],
        wardrobe_ledger={"choir-robe": {"accessories": ["stole"]}})
    check("F-PIC-6 a wardrobe change mid-scene with no ledger entry is refused",
          out["codes"] == ["WARDROBE_BREAK"], out)

    # The same change with a ledger entry is a planned costume change.
    out = C.check_cross_shot_continuity(
        [shot("T19", 0.0), shot("T20", 4.0, wardrobe_ids=["street-coat"])],
        wardrobe_ledger=LEDGER)
    check("F-PIC-6 a ledgered wardrobe passes", out["outcome"] == "pass", out)

    # A scene that moves place without a moving transition is a location break.
    out = C.check_cross_shot_continuity(
        [shot("T21", 8.0),
         shot("T22", 12.0, location_id="church_steps")],
        wardrobe_ledger=LEDGER)
    check("F-PIC-6 a place change mid-scene is refused",
          out["codes"] == ["LOCATION_BREAK"], out)

    # A declared moving transition carries the audience to the new place.
    out = C.check_cross_shot_continuity(
        [shot("T21", 8.0),
         shot("T22", 12.0, location_id="church_steps",
              transition="location_change")],
        wardrobe_ledger=LEDGER)
    check("F-PIC-6 a declared moving transition passes",
          out["outcome"] == "pass", out)

    # Wardrobe and place both hold across the whole scene: nothing is refused.
    out = C.check_cross_shot_continuity(
        [shot("T23", 16.0), shot("T24", 20.0), shot("T25", 24.0)],
        wardrobe_ledger=LEDGER)
    check("F-PIC-6 a steady scene passes", out["outcome"] == "pass", out)

    assert not FAILS, FAILS


if __name__ == "__main__":
    test_fpic6()
    print()
    print("FAILED: %d" % len(FAILS) if FAILS else "PASS: all checks")
    sys.exit(1 if FAILS else 0)
