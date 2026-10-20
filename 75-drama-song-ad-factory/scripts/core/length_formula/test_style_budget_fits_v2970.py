#!/usr/bin/env python3
"""v2.9.70: a named non-rap style's plan budget passes the gate that judges it.

Before: plan(60, style_id="soul-ballad") gave 66 words that words_fit.preflight
priced at 65.7 s against a 58 s card -> WORDS_DO_NOT_FIT, so stage 3 could
never pass (Laya Kelley 9 h, Jennifer Allen 54/136 min agents).
Run: python3 core/length_formula/test_style_budget_fits_v2970.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import length_formula as LF   # noqa: E402
import suno_recipe as R       # noqa: E402
import words_fit as WF        # noqa: E402

for style in ("soul-ballad", "soul-rise"):
    for L in (30, 45, 60, 90, 120, 180):
        p = LF.plan(L, style_id=style)
        w = p["words"]
        fit = WF.preflight(p["delivered_s"], w["sung"], w["spoken"], style=style)
        assert fit["outcome"] == "ok", (style, L, fit["reason_code"], w)
        assert w["total"] == w["sung"] + w["spoken"], (style, L, w)
        assert w["opener_max"] <= w["spoken"], (style, L, w)
        base = LF.plan(L)["words"]
        assert all(w[k] <= base[k] for k in ("total", "spoken", "sung")), (style, L, w, base)

# no style / unknown style: the plan is untouched (BASE_SHA pins live in test_style_plan_u2)
assert LF.plan(60) == LF.plan(60, style_id=None) == LF.plan(60, style_id="no-such-style")

# suno_recipe.check_lyric_sheet's budget row is a DRAFTING tolerance (10% + 2)
# around the UNCAPPED plan -- the same number it used before v2.9.70. The cap
# belongs to the fit gate (words_fit.preflight), never to this row: pricing the
# row off the cap refused a real approved 48 s sheet (58 words against 52.6)
# and broke sung_hook/test_three_walls.py,
# song_dispatch/test_remaining_defects_r1_r2_r4.py and
# suno_recipe/test_pace_direction_g11.py. So the row keeps its old ceiling here
# AND the capped plan still has to fit words_fit (the loop above proves that).
cap = LF.plan(60, style_id="soul-ballad")["words"]["total"]
draft = LF.plan(60)["words"]["total"]
assert cap < draft, (cap, draft)
hook = {"tag": "Hook", "delivery": "sung", "lines": ["I rise again"]}
sheet = [{"tag": "Verse 1", "delivery": "sung", "lines": ["I walk the road"] * 16},
         hook, dict(hook), dict(hook)]
total = R.sheet_words(sheet)
assert total > cap * 1.1 + 2, (total, cap)
budget = [e for e in R.check_lyric_sheet(sheet, "I rise again", 58, style_id="soul-ballad")
          if "budget" in e]
if total <= draft * 1.1 + 2:
    assert budget == [], budget          # inside the drafting tolerance: no row
else:
    assert budget == ["%d words, the 58 s budget is %d" % (total, draft)], budget
# ... and the gate that decides FIT is words_fit, which the capped plan passes.
w = LF.plan(60, style_id="soul-ballad")["words"]
assert WF.preflight(LF.plan(60, style_id="soul-ballad")["delivered_s"],
                    w["sung"], w["spoken"], style="soul-ballad")["outcome"] == "ok"
print("test_style_budget_fits_v2970: PASS")
