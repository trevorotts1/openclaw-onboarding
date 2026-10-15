#!/usr/bin/env python3
"""W1-method-song-U2 acceptance: the ERM Drop and the Hero Shift are the two
pace seams of a METHOD run, bound to the Blueprint seconds and written with the
method's own style clauses.

Sources: BUILD-PLAN.md section W1-method-song-U2; METHOD-INTEGRATION.md F5 and
conflicts C3/C4; SPEC.md C3 (Trevor 2026-10-13, decision #5).

What this pins:
  * the two seams of a method order must SIT on the Blueprint ERM apex and Hero
    Shift seconds the order carries -- any other binding is refused with
    PACE_SEAM_NOT_AT_ANCHOR;
  * the anchor names ``erm_drop`` / ``hero_shift`` are approved beside the
    generic ``drop`` / ``return``, and an undeclared name is refused;
  * the FINAL style of a method run carries METHOD_ERM_DROP_CLAUSE and
    METHOD_HERO_SHIFT_CLAUSE, and ``song_contract.check_pace_style`` accepts it;
  * the second seam passes on ANY clear measured change of pace or energy at the
    Hero Shift, in EITHER direction -- it no longer has to return to the opening
    groove -- while the FIRST seam keeps its 30% onset reduction and 3 dB drop;
  * a run with no method block behaves exactly as before.

stdlib only; no network, no spend, no provider call.

Run: python3 -m pytest -q <repo>/75-drama-song-ad-factory/scripts/core/music_qc/test_method_pace.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import music_qc.pace_change as PC           # noqa: E402
import song_contract as SCT                 # noqa: E402
import suno_recipe as R                     # noqa: E402

_SR = getattr(R, "suno_recipe", R)
_SC = getattr(SCT, "song_contract", SCT)

#: The Blueprint seconds of the 60 s example: ERM apex 15.0, Hero Shift 38.0.
ERM_APEX_S, HERO_SHIFT_S = 15.0, 38.0
BASE_STYLE = "smooth r&b melody, female lead, mid tempo"


def method_order(**over):
    """A method pace order as ``method_plan.pace_order(blueprint)`` builds it:
    both anchors named, both seams on the Blueprint seconds, the method clauses
    carried on the order, and the Hero Shift cue's direction copied on."""
    order = {"method": True,
             "drop_anchor": PC.PACE_ANCHOR_ERM_DROP,
             "return_anchor": PC.PACE_ANCHOR_HERO_SHIFT,
             "boundary_s": ERM_APEX_S,
             "return_boundary_s": HERO_SHIFT_S,
             "erm_apex_s": ERM_APEX_S,
             "hero_shift_s": HERO_SHIFT_S,
             "hero_direction": "faster"}
    order.update(over)
    drop, ret = _SR.method_pace_clauses(order)
    order.setdefault("drop", drop)
    order.setdefault("return", ret)
    return order


def old_order(**over):
    """A non-method pace order, exactly the shape the WW-07/WW-23 tests use."""
    order = {"drop": "half-time drop, thin drums",
             "return": "turn and rise back to the groove",
             "boundary_s": 20.0, "return_boundary_s": 60.0}
    order.update(over)
    return order


def style_with(pace_plan):
    """The FINAL style assembled the way music_director assembles it: the base
    brief, then the pace clause LAST."""
    note = _SR.pace_clause(pace_plan)
    return "%s %s" % (str(BASE_STYLE).rstrip(), note) if note else BASE_STYLE


# ---- 1. the two seams sit on the Blueprint seconds -------------------------

def test_method_seams_bound_to_the_blueprint_pass_the_plan_check():
    assert PC.check_pace_plan(method_order()) == []


def test_a_seam_off_the_blueprint_is_refused():
    early = PC.check_pace_plan(method_order(boundary_s=30.0))
    assert any("PACE_SEAM_NOT_AT_ANCHOR" in r for r in early), early
    assert any("ERM apex" in r for r in early), early
    late = PC.check_pace_plan(method_order(return_boundary_s=25.0))
    assert any("PACE_SEAM_NOT_AT_ANCHOR" in r for r in late), late
    assert any("Hero Shift" in r for r in late), late


def test_a_method_order_with_no_blueprint_seconds_is_refused():
    order = method_order()
    del order["erm_apex_s"]
    del order["hero_shift_s"]
    reasons = PC.check_pace_plan(order)
    assert any("PACE_SEAM_NOT_AT_ANCHOR" in r for r in reasons), reasons
    assert any("erm_apex_s" in r and "hero_shift_s" in r for r in reasons), reasons


def test_a_non_numeric_blueprint_second_is_refused():
    reasons = PC.check_pace_plan(method_order(erm_apex_s="soon"))
    assert any("PACE_SEAM_NOT_AT_ANCHOR" in r for r in reasons), reasons


# ---- 2. the anchor names ---------------------------------------------------

def test_erm_drop_and_hero_shift_are_approved_beside_drop_and_return():
    # a method order that names no anchors gets the method's own names
    anchors = PC.pace_anchors({"method": True, "drop": "x", "return": "y"})
    assert anchors["drop_anchor"] == PC.PACE_ANCHOR_ERM_DROP
    assert anchors["return_anchor"] == PC.PACE_ANCHOR_HERO_SHIFT
    # an order that DOES name them keeps them, and is accepted
    named = method_order(drop_anchor="erm_drop", return_anchor="hero_shift")
    assert PC.pace_anchors(named)["drop_anchor"] == "erm_drop"
    assert PC.check_pace_plan(named) == []
    # the generic pair is still approved on a non-method order
    generic = PC.pace_anchors(old_order())
    assert generic["drop_anchor"] == "drop" and generic["return_anchor"] == "return"
    assert PC.check_pace_plan(old_order()) == []


def test_an_unapproved_anchor_name_is_refused():
    reasons = PC.check_pace_plan(method_order(drop_anchor="lowest_point"))
    assert any("PACE_ANCHOR_UNKNOWN" in r for r in reasons), reasons
    assert PC.check_pace_plan(old_order(return_anchor="rise_up")) and \
        any("PACE_ANCHOR_UNKNOWN" in r for r in PC.check_pace_plan(
            old_order(return_anchor="rise_up")))


# ---- 3. the method style carries both clauses ------------------------------

def test_the_method_style_carries_both_clauses_and_the_contract_accepts_it():
    order = method_order()
    style = style_with(order)
    drop, ret = _SR.method_pace_clauses(order)
    assert drop == _SR.METHOD_ERM_DROP_CLAUSE
    assert "the first sung line enters exactly as the groove drops" in style
    assert "when help arrives the music changes pace again, clearly and dramatically" in style
    assert "in the direction this story calls for: faster" in style
    # the two conflicts this unit exists to close: the generic wording is gone
    assert "at the lowest point" not in style
    assert "turn and rise back" not in style
    assert _SC.check_pace_style(style, order) == []


def test_a_method_order_with_no_direction_keeps_the_clause_without_a_placeholder():
    order = method_order(hero_direction=None)
    ret = order["return"]
    assert ret == _SR.METHOD_HERO_SHIFT_CLAUSE
    assert "<" not in ret and "%s" not in ret
    assert _SC.check_pace_style(style_with(order), order) == []


def test_the_method_direction_comes_from_the_blueprint_cue_field():
    order = method_order(hero_direction=None, emotional_direction="bigger")
    assert _SR.method_pace_clauses(order)[1].endswith(": bigger")


# ---- 4. a run with no method block is unchanged ----------------------------

def test_a_non_method_request_is_unchanged():
    order = old_order()
    assert _SR.pace_clause(order) == "%s, %s." % (order["drop"], order["return"])
    assert _SR.pace_clause(None) == ""
    assert PC.check_pace_plan(order) == []
    assert _SC.check_pace_style(style_with(order), order) == []
    # the generic clauses still default when the order names none
    bare = _SR.pace_clause({"boundary_s": 20.0, "return_boundary_s": 60.0})
    assert bare == "%s, %s." % (_SR.PACE_DROP_CLAUSE, _SR.PACE_RETURN_CLAUSE)


def test_a_non_method_order_still_refuses_a_missing_or_reused_seam():
    assert any("PACE_SEAM_MISSING" in r for r in PC.check_pace_plan({"boundary_s": 20.0}))
    reused = PC.check_pace_plan({"boundary_s": 20.0, "return_boundary_s": 20.0})
    assert any("PACE_SEAM_REUSED_BOUNDARY" in r for r in reused), reused
    # a non-method order never asks for Blueprint seconds
    assert not any("PACE_SEAM_NOT_AT_ANCHOR" in r for r in reused)


# ---- 5. the measurement of the second seam ---------------------------------

BEFORE = {"onset_rate_per_s": 3.0, "rms_dbfs": -14.0}
DROP = {"onset_rate_per_s": 1.4, "rms_dbfs": -18.5}      # -53% onsets, -4.5 dB


def test_the_hero_shift_accepts_a_clear_change_in_either_direction():
    # faster and louder than the opening: not a return, and the method accepts it
    up = PC.confirm_pace_change(BEFORE, DROP, {"onset_rate_per_s": 3.6, "rms_dbfs": -8.0},
                                method=True)
    assert up["verdict"] == "PASS", up
    assert up["second_seam_rule"] == "hero_shift_any_clear_change"
    assert up["checks"]["hero_shift_change"] is True
    assert "onset_return" not in up["checks"] and "energy_return" not in up["checks"]
    # slower and quieter than the opening: the other direction
    down = PC.confirm_pace_change(BEFORE, DROP, {"onset_rate_per_s": 1.6, "rms_dbfs": -20.0},
                                  method=True)
    assert down["verdict"] == "PASS", down
    # the SAME evidence is not a return to the groove, so today's rule still FAILs it
    assert PC.confirm_pace_change(BEFORE, DROP,
                                  {"onset_rate_per_s": 3.6, "rms_dbfs": -8.0})["verdict"] == "FAIL"
    assert PC.confirm_pace_change(BEFORE, DROP,
                                  {"onset_rate_per_s": 1.6, "rms_dbfs": -20.0})["verdict"] == "FAIL"


def test_the_hero_shift_still_requires_a_measured_change():
    flat = PC.confirm_pace_change(BEFORE, DROP, dict(BEFORE), method=True)
    assert flat["verdict"] == "FAIL", flat
    assert "hero_shift_change" in flat["failed"], flat
    # a change too small to be clear is still a FAIL
    tiny = PC.confirm_pace_change(BEFORE, DROP,
                                  {"onset_rate_per_s": 3.1, "rms_dbfs": -13.6},
                                  method=True)
    assert tiny["verdict"] == "FAIL" and "hero_shift_change" in tiny["failed"], tiny


def test_the_first_seam_keeps_its_drop_rule_on_a_method_run():
    # no drop at the ERM: refused even though the Hero Shift changes clearly
    nodrop = PC.confirm_pace_change(BEFORE, dict(BEFORE),
                                    {"onset_rate_per_s": 3.6, "rms_dbfs": -8.0},
                                    method=True)
    assert nodrop["verdict"] == "FAIL", nodrop
    assert set(nodrop["failed"]) >= {"onset_reduction", "energy_drop"}, nodrop
    # missing onset or energy evidence is still UNMEASURED, never PASS
    bare = PC.confirm_pace_change({"onset_rate_per_s": 3.0}, BEFORE, BEFORE, method=True)
    assert bare["verdict"] == "UNMEASURED", bare


def test_the_judge_reads_the_method_flag_off_the_order():
    plan = {"pace_change": method_order()}
    pg = PC.judge_plan_pace(plan, BEFORE, DROP, {"onset_rate_per_s": 3.6, "rms_dbfs": -8.0})
    assert pg["verdict"] == "PASS" and pg["applicable"] is True, pg
    assert pg["method"] is True
    assert pg["second_seam_rule"] == "hero_shift_any_clear_change"
    old = PC.judge_plan_pace({"pace_change": old_order()}, BEFORE, DROP, BEFORE)
    assert old["method"] is False
    assert old["second_seam_rule"] == "return_to_opening_groove"
    # no order at all: still not applicable
    assert PC.judge_plan_pace({}, {}, {}, {})["applicable"] is False
