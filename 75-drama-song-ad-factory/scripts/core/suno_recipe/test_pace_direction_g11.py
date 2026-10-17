#!/usr/bin/env python3
"""G11 (2026-10-17): the approved pace direction is an ABSENCE, not a texture.

Run: python3 core/suno_recipe/test_pace_direction_g11.py     (or pytest, no fixtures)

WHY THIS EXISTS. Every stem ever measured kept its drums and RAISED its energy
under the old wording -- 36 historical stems plus the 12 of the a2 round, whose
onsets were flat or RISING while the energy rose (1.760 -> 1.760/s at +3.48 dB,
1.886 -> 1.886/s at +7.91 dB, 2.011 -> 1.634/s at +0.47 dB, 1.383 -> 2.263/s at
+1.41 dB, 2.263 -> 2.766/s at +2.63 dB, 1.760 -> 2.891/s at +2.29 dB), against a
gate that demands a 3 dB energy DROP and a 30% onset REDUCTION. "half-time with
thin, sparse drums" asks Suno for a thinner sound and it keeps playing;
"the drums and bass cut out entirely for four seconds" asks it to stop. The
RETURN is named the same way -- an intensity, not a mood.

This file proves the change on the REAL assembled payload, never on a string
constant in isolation: the approved 48 s sheet, the three variants the client
actually chooses between (intimate-piano / warm-live-band / cinematic-strings),
serialized by song_choices.build_requests -- the same builder a dispatch runs.
No provider call, no spend, no network.

The run that motivated this carries its OWN ``drop`` / ``return`` inside its
``pace_plan``, and ``suno_recipe.pace_clause`` reads those BEFORE the defaults
(``drop = pace_plan.get("drop") or PACE_DROP_CLAUSE``). A repo default change
alone would never have reached that run, so both paths are proved here: the
plan-carrying-the-clauses path AND the default path.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "intake_preflight"))

from song_choices import song_choices as SC                     # noqa: E402
from suno_recipe import suno_recipe as R                         # noqa: E402
import song_contract as _SC                                      # noqa: E402
import music_qc.pace_change as PC                                 # noqa: E402

_SCM = getattr(_SC, "song_contract", _SC)      # the module, not the package

#: The wording this unit installs. Kept as literals ON PURPOSE: asserting the
#: module against its own constants would prove nothing.
STRONG_DROP = "at the lowest point the drums and bass cut out entirely for four seconds"
STRONG_RETURN = "then the drums slam back in at double intensity"
#: The retired wording, pinned so a regression is caught by substring, not by
#: a reviewer's memory.
WEAK_DROP = "at the lowest point the groove drops to half-time with thin, sparse drums"
WEAK_RETURN = "then it turns and rises back to the full groove"

#: The approved sheet: a real 48 s run's sheet and pace plan, brand token
#: replaced (the fixture's own note). The fixture's rendered lyrics hash to
#: aacc7dbf... because of that replacement; the unredacted run's lyrics hash to
#: 8c7a8d12..., the same sheet. 48 s, seams 16 s / 40 s, hook true at
#: pain_deepens. No sheet is invented here.
_FIXTURE = os.path.join(CORE, "sung_hook", "fixtures", "gala-48s-approved.json")
SHEET_ID = "soul-ballad"
LENGTH_S = 48
TRUE_AT_BEAT = "pain_deepens"
#: The fixture carries no client text and the recipe refuses an UNMEASURED
#: own-words hook, so the client line is stated here -- it is the sheet's own
#: hook words plus its own outro copy, nothing invented.
CLIENT = ("The night of legacy and light, in emerald and light. "
          "Reserve by October 27. examplegala2026 dot com.")
VARIANTS = ("intimate-piano", "warm-live-band", "cinematic-strings")

_CACHE = {}


def _sheet():
    return R.parse_lyrics(json.load(open(_FIXTURE, encoding="utf-8"))["sheet_text"])


def _approved_plan():
    """The run's own pace order: reason + BOTH seams, exactly as approved."""
    plan = dict(json.load(open(_FIXTURE, encoding="utf-8"))["pace_plan"])
    assert plan["boundary_s"] == 16.0 and plan["return_boundary_s"] == 40.0, plan
    return plan


def _builds(key, pace_plan):
    """{variant id: serialized input.style} for the three real variants.

    One build per key: song_choices.build_requests is the dispatch path and is
    not cheap, and every assertion below must judge the SAME payload.
    """
    if key not in _CACHE:
        out = SC.build_requests(SHEET_ID, _sheet(), CLIENT, "Gala", LENGTH_S,
                                hook_plan={"true_at_beat": TRUE_AT_BEAT},
                                pace_plan=pace_plan)
        _CACHE[key] = [(v["id"], r) for v, r in out]
    return _CACHE[key]


def _styles(key, pace_plan):
    return {vid: r["input"]["style"] for vid, r in _builds(key, pace_plan)}


# ---- 1. the constants themselves -------------------------------------------

def test_the_default_clauses_are_the_stronger_wording():
    assert R.PACE_DROP_CLAUSE == STRONG_DROP, R.PACE_DROP_CLAUSE
    assert R.PACE_RETURN_CLAUSE == STRONG_RETURN, R.PACE_RETURN_CLAUSE
    assert WEAK_DROP not in R.PACE_DROP_CLAUSE and WEAK_RETURN not in R.PACE_RETURN_CLAUSE
    # the return still comes after the drop, in order, in the rendered clause
    note = R.pace_clause({"boundary_s": 16.0, "return_boundary_s": 40.0})
    assert note == "%s, %s." % (STRONG_DROP, STRONG_RETURN), note
    assert R.pace_clause(None) == ""


def test_no_pace_plan_still_means_no_clause():
    """The change is an INSTRUCTION change, never a new mandatory clause. Only
    the ABSENCE of a plan suppresses the clause; a plan that names its seams
    but carries no wording of its own is the default path."""
    assert R.pace_clause(None) == ""
    assert R.pace_clause({}) == ""
    assert R.pace_clause({"reason": "no seams named"}) == \
        "%s, %s." % (STRONG_DROP, STRONG_RETURN)


# ---- 2. the three serialized provider styles -------------------------------

def test_the_run_own_pace_plan_carries_both_phrases():
    """THE OVERRIDE PATH. A run whose pace_plan carries its own drop/return
    never reads the repo defaults, so the wording the run carries is what
    reaches Suno. Stamped from the constants here, exactly as a regenerated
    pace plan would carry it."""
    plan = _approved_plan()
    plan["drop"], plan["return"] = R.PACE_DROP_CLAUSE, R.PACE_RETURN_CLAUSE
    for vid, style in _styles("carried", plan).items():
        assert STRONG_DROP in style, (vid, style[-200:])
        assert STRONG_RETURN in style, (vid, style[-200:])
        assert WEAK_DROP not in style and WEAK_RETURN not in style, vid


def test_a_pace_plan_with_no_clauses_falls_back_to_the_defaults():
    """THE DEFAULT PATH. Same run, drop/return stripped: the defaults are what
    the provider gets, so they must be the strong wording too."""
    plan = _approved_plan()
    plan.pop("drop", None)
    plan.pop("return", None)
    for vid, style in _styles("default", plan).items():
        assert STRONG_DROP in style and STRONG_RETURN in style, (vid, style[-200:])
        assert WEAK_DROP not in style and WEAK_RETURN not in style, vid


def test_all_three_serialized_styles_stay_under_the_cap():
    """Measured on the FINAL payload after every append (the pace clause is
    LAST, and an over-cap append refuses rather than truncating). The report
    line is the number the next reader needs."""
    plan = _approved_plan()
    plan["drop"], plan["return"] = R.PACE_DROP_CLAUSE, R.PACE_RETURN_CLAUSE
    lens = {vid: len(style) for vid, style in _styles("carried", plan).items()}
    assert set(lens) == set(VARIANTS), lens
    for vid in VARIANTS:
        assert lens[vid] < R.SUNO_STYLE_FIELD_MAX, (vid, lens[vid])
    print("  G11 serialized input.style lengths (cap %d): %s"
          % (R.SUNO_STYLE_FIELD_MAX,
             ", ".join("%s=%d" % (v, lens[v]) for v in VARIANTS)))


def test_the_contract_gate_accepts_every_style_it_now_ships():
    """The wording is an instruction, not a bypass: the pace anchor gate must
    still find both directions IN ORDER in what we send."""
    plan = _approved_plan()
    plan["drop"], plan["return"] = R.PACE_DROP_CLAUSE, R.PACE_RETURN_CLAUSE
    for vid, style in _styles("carried", plan).items():
        assert _SCM.check_pace_style(style, plan) == [], \
            (vid, _SCM.check_pace_style(style, plan))
        # the clause is LAST, after the ending and the variant's arrangement
        assert style.rstrip().rstrip(".").endswith(STRONG_RETURN), (vid, style[-200:])
    # NEGATIVE CONTROL: the gate still refuses a style carrying only ONE of the
    # two directions -- a stronger clause must not widen what passes.
    one_way = _styles("carried", plan)[VARIANTS[0]].replace(STRONG_RETURN, "")
    assert one_way != _styles("carried", plan)[VARIANTS[0]]
    assert any("PACE_DIRECTION_MISSING" in r
               for r in _SCM.check_pace_style(one_way, plan))


# ---- 3. nothing but the instruction moved ----------------------------------

def test_no_gate_threshold_moved():
    """G11 changes WHAT we ask for, never WHAT WE REQUIRE. Every number the
    pace gate judges by is pinned here so a drift fails loudly."""
    assert PC.PACE_ONSET_REDUCTION == 0.30, PC.PACE_ONSET_REDUCTION
    assert PC.PACE_ENERGY_DROP_DB == 3.0, PC.PACE_ENERGY_DROP_DB
    assert PC.PACE_RETURN_DB == 3.0, PC.PACE_RETURN_DB
    assert PC.PACE_SEAM_COUNT == 2, PC.PACE_SEAM_COUNT
    assert PC.PACE_SEAM_KEYS == ("boundary_s", "return_boundary_s")
    assert R.SUNO_STYLE_FIELD_MAX == 1000, R.SUNO_STYLE_FIELD_MAX
    assert R.MIN_HOOK_REPEATS == 2 and R.FIRST_SING_TARGET == 0.15
    assert R.ACCEPT_PTS == 5 and R.FLAG_PTS == 10


def test_the_method_clauses_are_deliberately_untouched():
    """No METHOD stem has ever been measured, so the method lane carries no
    evidence of the same failure; and the Hero Shift must stay
    direction-agnostic (C4 / Trevor 2026-10-13 decision #5), which a fixed
    intensity would contradict. Pinned so the no-change is a decision on
    record, not an oversight nobody can see."""
    assert R.METHOD_ERM_DROP_CLAUSE == ("the first sung line enters exactly as the "
                                        "groove drops to a heavier, sparser half-time feel")
    assert R.METHOD_HERO_SHIFT_CLAUSE == ("when help arrives the music changes pace "
                                          "again, clearly and dramatically, in the "
                                          "direction this story calls for")


def test_the_sheet_this_unit_judges_is_the_approved_one():
    """The measurement above is only worth as much as the sheet it stands on."""
    lyrics = R.render_lyrics(_sheet(), SHEET_ID)
    assert hashlib.sha256(lyrics.encode()).hexdigest().startswith("aacc7dbf")
    sections = [s["tag"] for s in _sheet()]
    assert sections == ["Intro", "Vocalise", "Verse 1", "Hook 1", "Verse 2",
                        "Hook 2", "Outro"], sections


def _report():
    """The three serialized provider styles, verbatim, on the override path."""
    plan = _approved_plan()
    plan["drop"], plan["return"] = R.PACE_DROP_CLAUSE, R.PACE_RETURN_CLAUSE
    for vid, style in _styles("carried", plan).items():
        print("  input.style [%s] (%d chars)\n    %s" % (vid, len(style), style))


def main():
    fails = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print("  ok   %s" % name)
        except Exception as e:                      # noqa: BLE001 - self-check
            fails += 1
            print("  FAIL %s: %s: %s" % (name, type(e).__name__, e))
    if not fails:
        _report()
    print("G11 pace direction: %s" % ("PASS" if not fails else "FAIL (%d)" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
