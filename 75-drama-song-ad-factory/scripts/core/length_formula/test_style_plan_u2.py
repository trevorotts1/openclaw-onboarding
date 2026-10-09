#!/usr/bin/env python3
"""FU-U2 (plan unit U2): style-aware length plan and words fit.

Proves, behaviourally:
  (a) plan(150, style_id="rnb-flow")["words"] carries a rap key above 0
      (before this unit: TypeError -- plan() had no style_id at all);
  (b) build_generate_request(..., style_id="rnb-flow", length_s=148) on the
      One-Check sheet raises WordsFitError AT R&B RATES (before: judged at
      Soul Ballad rates, because the style never reached words_fit);
  (c) music_styles._length_key(120) is accepted (before: UNKNOWN_LENGTH),
      and the card menu (words_fit.CARD_LENGTHS_S) offers 120;
  (d) a rap section in a soul-ballad sheet is refused.
REGRESSION: Soul Ballad and Soul Rise plans stay BYTE-IDENTICAL to the base
tree (the L=60 BSW result: 65 words, sha256 recorded below).

Run: python3 core/length_formula/test_style_plan_u2.py
stdlib only, no network, no spend.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

import length_formula as LF             # noqa: E402
import music_styles as MS               # noqa: E402
import suno_recipe as R                 # noqa: E402
import words_fit as W                   # noqa: E402

FIXTURE = os.path.join(CORE, "suno_recipe", "fixtures", "one-check-lyrics.txt")

#: The base-tree digests (FU-U1 tree), computed BEFORE this unit's change:
#:   json.dumps(plan, sort_keys=True) with the FU-U13 product_connection key
#:   removed (a sibling unit's key, not this unit's output).
# MGB013: L150/L300 are main's digests (the fixed CTA cap was retired 2026-10-09);
# L60 and L60_bsw are unchanged from the FU-U1 tree.
BASE_SHA = {
    "L60": "05d36d4066c5fec710d1ec61f91a5a2345f2007848dc8bc7912e03a0776b3d4d",
    "L60_bsw": "e890c4a29922a9253cd8f293f4005fef9b29e4fc801e03d8f5688d2ee4373721",
    "L150": "e938e6a3f2b2ce46e3f796d25852218d1cc3ad858253d4fe60cfe46e8633e628",
    "L300": "40f5cbe5290b764bfe5c9d324355260c2d358ef9e19f228fbce58ae50e6d16d5",
}

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def load_fixture():
    with open(FIXTURE, encoding="utf-8") as fh:
        return fh.read()


def canon(plan):
    """The plan as the base tree emitted it: FU-U13's key is not this unit's."""
    return json.dumps({k: v for k, v in plan.items() if k != "product_connection"},
                      sort_keys=True)


def test_a_rap_budget_in_the_plan():
    try:
        p = LF.plan(150, style_id="rnb-flow")
    except TypeError as exc:
        check("(a) plan() takes style_id", False, str(exc))
        return
    check("(a) rnb-flow plan carries a rap key", "rap" in p["words"],
          repr(sorted(p["words"])))
    check("(a) the rap budget is above 0", p["words"].get("rap", 0) > 0,
          repr(p["words"]))
    check("(a) the plan reports rap seconds", p.get("rap_s", 0) > 0, repr(p.get("rap_s")))
    check("(a) the word total adds up",
          p["words"]["total"] == p["words"]["spoken"] + p["words"]["sung"]
          + p["words"]["rap"], repr(p["words"]))
    # The plan reaches the ad's own spoken-style target by construction
    # (rap counts as spoken-style delivery): no caps-bind note.
    check("(a) the rap plan reaches the requested share",
          p["spoken_share_pct_planned"] >= p["spoken_share_pct_requested"] - 1.0,
          (p["spoken_share_pct_planned"], p["spoken_share_pct_requested"]))


def test_b_gate_judged_at_rnb_rates():
    sheet = load_fixture()
    try:
        fit = W.preflight_sheet(148, sheet, style="rnb-flow")
    except Exception as exc:                        # noqa: BLE001
        check("(b) words_fit reads the One-Check sheet", False,
              "%s: %s" % (type(exc).__name__, exc))
        return
    check("(b) the R&B rates are the ones applied",
          fit["rates"] == W.STYLE_RATES.get("rnb-flow") and fit["rates"]["sung"] == 1.9,
          repr(fit["rates"]))
    # The gate itself: build_generate_request must raise WordsFitError, and
    # the payload it carries must be the R&B-rate arithmetic.
    import music_director
    try:
        music_director.build_generate_request(
            sheet, "x", "T", style_id="rnb-flow", length_s=148, client_text="")
    except W.WordsFitError as exc:
        check("(b) build_generate_request raises WordsFitError", True)
        check("(b) the refusal is the R&B-rate plan (134.8s, SHARE_OFF_TARGET)",
              fit["reason_code"] == "SHARE_OFF_TARGET"
              and abs(fit["plan_s"] - 134.758) < 0.01,
              "%s %r" % (fit["reason_code"], fit["plan_s"]))
    except Exception as exc:                        # noqa: BLE001
        check("(b) build_generate_request raises WordsFitError",
              False, "%s: %s" % (type(exc).__name__, str(exc)[:200]))
    else:
        check("(b) build_generate_request raises WordsFitError", False, "no raise")
    # Control: the same numbers at BALLAD rates give a different plan length,
    # so the assertion above really discriminates the two rate tables.
    ballad = W.preflight_sheet(148, sheet, style="soul-ballad")
    check("(b) ballad rates give a different plan (the check discriminates)",
          ballad["plan_s"] > fit["plan_s"] and ballad["rates"] != fit["rates"],
          "%r vs %r" % (ballad["plan_s"], fit["plan_s"]))


def test_c_120_is_offered():
    try:
        secs = MS.music_styles._length_key(120)
    except Exception as exc:                        # noqa: BLE001
        check("(c) _length_key(120) is accepted", False,
              "%s: %s" % (type(exc).__name__, exc))
        secs = None
    check("(c) _length_key(120) is accepted", secs == 120, repr(secs))
    check("(c) the card menu offers 120", 120 in W.CARD_LENGTHS_S,
          repr(W.CARD_LENGTHS_S))
    check("(c) one copy: CARD_LENGTHS_S is music_styles.OFFERED_LENGTHS_S",
          W.CARD_LENGTHS_S == getattr(MS, "OFFERED_LENGTHS_S", None)
          == (60, 90, 120, 180, 300, 600),
          repr((W.CARD_LENGTHS_S, getattr(MS, "OFFERED_LENGTHS_S", None))))
    try:
        alias = MS.music_styles._length_key("2min")
    except Exception:                               # noqa: BLE001
        alias = None
    check("(c) the 2-minute alias resolves", alias == 120, repr(alias))


def test_d_rap_refused_outside_the_rap_style():
    sheet = R.parse_lyrics(load_fixture())
    client = "Girl, I got you. You need to register for the Girl, I Got You Masterclass."
    errs = R.check_lyric_sheet(sheet, client, 148, style_id="soul-ballad")
    check("(d) a rap section in a soul-ballad sheet is refused",
          any("rap" in e for e in errs), repr(errs[:2]))
    risen = R.check_lyric_sheet(sheet, client, 148, style_id="soul-rise")
    check("(d) soul-rise refuses rap too",
          any("rap" in e for e in risen), repr(risen[:2]))


def test_regression_soul_plans_are_byte_identical():
    for name, plan in (("L60", LF.plan(60)),
                       ("L60_bsw", LF.plan(60, (15, 20))),
                       ("L150", LF.plan(150)),
                       ("L300", LF.plan(300))):
        got = hashlib.sha256(canon(plan).encode()).hexdigest()
        check("regression %s is byte-identical to the base tree" % name,
              got == BASE_SHA[name], "%s vs %s" % (got[:16], BASE_SHA[name][:16]))
        check("regression %s adds no rap key" % name, "rap" not in plan["words"],
              repr(sorted(plan["words"])))
    for name, kwargs in (("L60_soulballad", {"style_id": "soul-ballad"}),
                         ("L60_soulrise", {"style_id": "soul-rise"})):
        try:
            plan = LF.plan(60, **kwargs)
        except TypeError as exc:
            check("regression %s is byte-identical to the base tree" % name,
                  False, str(exc))
            continue
        got = hashlib.sha256(canon(plan).encode()).hexdigest()
        check("regression %s is byte-identical to the base tree" % name,
              got == BASE_SHA["L60"], "%s vs %s" % (got[:16], BASE_SHA["L60"][:16]))
        check("regression %s adds no rap key" % name, "rap" not in plan["words"],
              repr(sorted(plan["words"])))
    # The acceptance number: the L=60 BSW result is 65 words.
    check("regression: L=60 BSW is the measured 65 words",
          LF.plan(60, (15, 20))["words"]["total"] == 65,
          repr(LF.plan(60, (15, 20))["words"]))


def main():
    test_a_rap_budget_in_the_plan()
    test_b_gate_judged_at_rnb_rates()
    test_c_120_is_offered()
    test_d_rap_refused_outside_the_rap_style()
    test_regression_soul_plans_are_byte_identical()
    print()
    if FAILS:
        print("FAILED: %d" % len(FAILS))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
