#!/usr/bin/env python3
"""v2.9.72 R1: R&B Flow fits, or is refused up front with the length that works.

Before this, a rap style kept its reservation AND its generic sung budget, so
the two missed the style's sung-share floor at 30/45/60 s: plan(60,'rnb-flow')
= sung 53 + rap 40 -> words_fit.preflight SHARE_OFF_TARGET (63.5% vs 72.9%).
Stage 3 then drafted and was refused forever.
"""
import os
import sys

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from length_formula import length_formula as LF       # noqa: E402
from words_fit import words_fit as WF                 # noqa: E402

FAILS = []


def check(label, cond, detail=""):
    if cond:
        print("ok:", label)
    else:
        print("FAIL:", label, detail)
        FAILS.append(label)


def preflight(D, words, style):
    return WF.preflight(D, words.get("sung", 0), words.get("spoken", 0),
                        rap_words=words.get("rap", 0), style=style)


# 1. Every length either FITS or is explicitly flagged, never silently unusable.
for L in (30, 45, 60, 90, 120, 180):
    p = LF.plan(L, style_id="rnb-flow")
    r = preflight(p["delivered_s"], p["words"], "rnb-flow")
    bad = p.get("infeasible")
    check("rnb-flow %d s: outcome ok OR flagged infeasible" % L,
          (r["outcome"] == "ok") != bool(bad),
          "outcome=%s infeasible=%s" % (r["outcome"], bad))
    if bad:
        check("rnb-flow %d s: refusal names the style and a length" % L,
              bad.get("reason_code") == "STYLE_TOO_SHORT_FOR_RAP"
              and isinstance(bad.get("min_length_s"), int)
              and "rnb-flow" in bad.get("message", ""),
              str(bad)[:160])

# 2. The named minimum length really works, and one second less does not.
need = LF.infeasible_length("rnb-flow")
check("minimum length is discovered", isinstance(need, int), repr(need))
check("the minimum length fits", not LF.plan(need, style_id="rnb-flow").get("infeasible"),
      str(LF.plan(need, style_id="rnb-flow").get("infeasible")))
check("one second under the minimum is refused",
      bool(LF.plan(need - 1, style_id="rnb-flow").get("infeasible")))

# 3. The pre-spend path refuses with the same message (no stage-3 loop).
import music_director as MD                          # noqa: E402
txt = "[Intro]\nline one here now\n[Verse]\nline two here now\n"
try:
    MD.build_generate_request(txt, "warm", "t", style_id="rnb-flow", length_s=60,
                              mode="packet", packet_lines=["a b c"], client_text="x")
    check("music_director refuses rnb-flow at 60 s", False, "no exception")
except WF.WordsFitError as e:
    check("music_director refuses rnb-flow at 60 s",
          getattr(e, "code", "") == "STYLE_TOO_SHORT_FOR_RAP" and "70" in str(e), str(e)[:160])

# 4. No style and the two soul styles are byte-identical to v2.9.71.
check("soul-ballad totals unchanged",
      [LF.plan(L, style_id="soul-ballad")["words"]["total"] for L in (30, 45, 60, 90)]
      == [23, 41, 58, 92])
check("soul-rise totals unchanged",
      [LF.plan(L, style_id="soul-rise")["words"]["total"] for L in (30, 45, 60, 90)]
      == [26, 46, 66, 95])
check("no-style totals unchanged",
      [LF.plan(L)["words"]["total"] for L in (30, 45, 60, 90)] == [32, 50, 66, 95])

# 5. The rap floor is still a floor: a feasible length keeps its rap verses.
p = LF.plan(90, style_id="rnb-flow")
check("feasible rnb-flow keeps its rap words", p["words"].get("rap", 0) >= 20,
      str(p["words"]))
check("rap gate still passes on a feasible plan",
      p["rap_gate"]["verdict"] == "PASS", str(p["rap_gate"])[:120])

# 6. An unknown style is not silently given a rap allowance.
check("unknown style has no rap key",
      "rap" not in LF.plan(60, style_id="not-a-style")["words"])

print()
if FAILS:
    print("FAILED: %d checks" % len(FAILS))
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("test_rnbflow_fit_v2972: ALL PASS")
