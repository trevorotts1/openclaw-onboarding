#!/usr/bin/env python3
"""SPEC C1 tests: the Story Beat Blueprint validator, the A-F record, the pace order.

Run: python3 -m pytest -q scripts/core/method_plan
  or: python3 scripts/core/method_plan/test_method_plan.py

The fixture is method 9.1's complete 90-second example (method 10.2's record
for the same episode). Every negative below starts from that passing fixture
and moves exactly ONE thing, so the reason code that comes back is the code the
acceptance line names -- never a bundle of unrelated failures.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import method_plan.method_plan as MP            # noqa: E402
import music_qc.pace_change as PC               # noqa: E402  the seam consumer

FIXTURE = _HERE / "fixtures" / "blueprint-90s.json"


def _blueprint():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def _method(**over):
    m = {"purpose": "campaign", "platform": None,
         "output_types": ["MASTER_EPISODE", "TRAILER_CLIP", "AD_CLIP"],
         "chosen_length_s": 90,
         "gates": {g: "planned" for g in "ABCDEF"}}
    m.update(over)
    return m


def _codes(report):
    return [e["error"] for e in report["errors"]]


def _cue(blueprint, cue_id):
    for cue in blueprint["music_cues"]:
        if cue["music_cue_id"] == cue_id:
            return cue
    raise AssertionError("fixture has no cue %s" % cue_id)


def _beat(blueprint, beat_id):
    for beat in blueprint["story_beats"]:
        if beat["story_beat_id"] == beat_id:
            return beat
    raise AssertionError("fixture has no beat %s" % beat_id)


# ---- the passing fixture ---------------------------------------------------

def test_fixture_validates():
    """Method 9.1's 90-second example passes every check, with the anchors the
    method's own record (10.2) states for it."""
    report = MP.validate(_blueprint(), _method())
    assert report["outcome"] == "ok", report["errors"]
    assert report["reason_code"] is None
    assert report["purpose"] == "campaign"
    assert report["anchors"] == {"backstory": 0.0, "erm_apex": 22.0,
                                 "hero_shift": 38.0, "breakthrough": 58.0,
                                 "hook": 60.0, "commercial": 72.0}
    assert report["cues"] == ["BASELINE", "PAIN_BUILD", "ERM_DROP", "PAIN_DEEPEN",
                              "HERO_SHIFT", "BREAKTHROUGH", "SOLUTION_HOOK",
                              "COMMERCIAL_CONTINUATION"]
    json.dumps(report)                            # a receipt the factory can write


def test_anchors_are_read_from_the_cues_once():
    """The ERM cue alone moves the ERM anchor: the order check and the pace
    order can never disagree with the record."""
    bp = _blueprint()
    _cue(bp, "ERM_DROP")["start_s"] = 15
    report = MP.validate(bp, _method())
    assert report["anchors"]["erm_apex"] == 15.0
    assert MP.pace_order(bp)["boundary_s"] == 15.0


# ---- the acceptance negatives ---------------------------------------------

def test_hook_before_the_solution_is_introduced_is_unearned():
    bp = _blueprint()
    _cue(bp, "SOLUTION_HOOK")["start_s"] = 30      # before the Hero Shift at 38
    report = MP.validate(bp, _method())
    assert report["outcome"] == "rejected"
    assert report["reason_code"] == "HOOK_UNEARNED", report["errors"]
    assert "HOOK_UNEARNED" in _codes(report)


def test_first_singing_in_baseline_is_refused():
    bp = _blueprint()
    _cue(bp, "BASELINE")["vocal_status"] = "first_sung"
    report = MP.validate(bp, _method())
    assert report["reason_code"] == "SINGING_BEFORE_ERM", report["errors"]
    assert "before the ERM apex" in report["errors"][0]["detail"]


def test_hero_shift_at_the_erm_time_is_not_distinct():
    bp = _blueprint()
    _cue(bp, "HERO_SHIFT")["start_s"] = 22          # the ERM apex
    report = MP.validate(bp, _method())
    assert report["reason_code"] == "HERO_SHIFT_NOT_DISTINCT", report["errors"]
    assert _codes(report) == ["HERO_SHIFT_NOT_DISTINCT"]


def test_lesson_without_memory_hook_is_refused():
    report = MP.validate(_blueprint(), _method(purpose="lesson"))
    assert report["reason_code"] == "CUE_MISSING", report["errors"]
    detail = report["errors"][0]["detail"]
    assert "MEMORY_HOOK" in detail and "RECAP" in detail


def test_testimonial_claim_without_a_source_is_refused():
    bp = _blueprint()
    beat = _beat(bp, "SB-06")
    beat["claim"] = "she got the support she needed"
    beat["claim_source"] = None                     # a claim with no source
    report = MP.validate(bp, _method(purpose="testimonial"))
    assert report["reason_code"] == "CLAIM_UNSOURCED", report["errors"]
    assert "SB-06" in report["errors"][0]["detail"]


def test_testimonial_claim_with_a_source_passes():
    bp = _blueprint()
    beat = _beat(bp, "SB-06")
    beat["claim"] = "she got the support she needed"
    beat["claim_source"] = "testimonial_text, client quote 2026-10-13"
    assert MP.validate(bp, _method(purpose="testimonial"))["outcome"] == "ok"


def test_campaign_beat_without_trailer_value_is_refused():
    bp = _blueprint()
    del _beat(bp, "SB-02")["trailer_value"]
    report = MP.validate(bp, _method())
    assert report["reason_code"] == "TRAILER_VALUE_MISSING", report["errors"]
    assert "SB-02" in report["errors"][0]["detail"]


def test_anchor_order_is_enforced():
    bp = _blueprint()
    _cue(bp, "COMMERCIAL_CONTINUATION")["start_s"] = 50   # before the hook at 60
    report = MP.validate(bp, _method())
    assert report["reason_code"] == "ANCHOR_ORDER", report["errors"]
    assert "backstory < ERM apex < Hero Shift" in report["errors"][0]["detail"]


def test_erm_cue_must_carry_first_sung():
    bp = _blueprint()
    _cue(bp, "ERM_DROP")["vocal_status"] = "sung"
    report = MP.validate(bp, _method())
    assert report["reason_code"] == "ERM_NOT_FIRST_SUNG", report["errors"]


def test_unknown_purpose_fails_closed():
    """No purpose means no lesson / testimonial / campaign gate to apply, so a
    method record that cannot be read is refused, never waved through."""
    for method in (_method(purpose="testimonials"), {}, None):
        report = MP.validate(_blueprint(), method)
        assert report["outcome"] == "rejected", method
        assert report["reason_code"] == "PURPOSE_UNKNOWN", report["errors"]


def test_missing_record_field_is_named():
    bp = _blueprint()
    del _beat(bp, "SB-01")["change"]
    report = MP.validate(bp, _method())
    assert report["reason_code"] == "RECORD_FIELDS_MISSING", report["errors"]
    assert "change" in report["errors"][0]["detail"]

    bp = _blueprint()
    del _cue(bp, "HERO_SHIFT")["transition_method"]
    assert MP.validate(bp, _method())["reason_code"] == "RECORD_FIELDS_MISSING"


def test_blueprint_without_records_is_refused():
    assert MP.validate({}, _method())["reason_code"] == "RECORD_FIELDS_MISSING"
    assert MP.validate(None, _method())["outcome"] == "rejected"


# ---- gates A-F -------------------------------------------------------------

def test_gates_carry_their_evidence_level():
    method = _method(gates={"A": "inspected", "B": "generated", "C": "planned",
                            "D": "planned", "E": "planned", "F": "planned"})
    record = MP.gates(method)
    assert list(record) == ["A", "B", "C", "D", "E", "F"]
    assert record["A"]["evidence_level"] == "inspected"
    assert record["B"]["evidence_level"] == "generated"
    assert record["C"]["evidence_level"] == "planned"
    for key in record:
        assert record[key]["gate"] == key
        assert record[key]["name"] and record[key]["stop"]
        assert record[key]["evidence"]


def test_approval_without_a_recorded_human_answer_reads_planned():
    record = MP.gates(_method(gates={g: "approved" for g in "ABCDEF"}))
    assert all(record[k]["evidence_level"] == "planned" for k in record)
    assert "no recorded human answer" in record["C"]["evidence"]


def test_approval_with_a_recorded_human_answer_stands():
    record = MP.gates(_method(gates={"C": "approved"},
                              approvals={"C": {"answer": "yes", "by": "client"}}))
    assert record["C"]["evidence_level"] == "approved"
    assert "recorded answer" in record["C"]["evidence"]


def test_unreadable_gate_record_never_reads_inspected():
    for value in ("checked", 3, None, ["inspected"]):
        record = MP.gates(_method(gates={"E": value}))
        assert record["E"]["evidence_level"] == "planned", value
    assert all(MP.gates({})[k]["evidence_level"] == "planned" for k in "ABCDEF")


# ---- the pace order --------------------------------------------------------

def test_pace_order_carries_both_seams_at_the_anchors():
    order = MP.pace_order(_blueprint())
    assert order["boundary_s"] == 22.0             # the ERM apex
    assert order["return_boundary_s"] == 38.0      # the Hero Shift
    assert order["boundary_s"] != order["return_boundary_s"]
    assert order["method"] is True
    assert order["drop_anchor"] == "erm_drop" and order["return_anchor"] == "hero_shift"
    assert order["drop"] == "heavier, sparser half-time"
    assert order["return"] == "steadier, more open pace"
    assert order["true_at_beat"] == "the_turn"
    assert "ERM Drop at 22" in order["reason"] and "Hero Shift at 38" in order["reason"]


def test_pace_order_is_a_plan_the_existing_gate_accepts():
    """The seam consumer must take the order as it stands: two anchors, two
    distinct timestamps, no reason for PACE_ANCHOR_MISSING / PACE_SEAM_*."""
    order = MP.pace_order(_blueprint())
    assert PC.check_pace_plan(order) == []
    seams = PC.pace_seams(order)
    assert seams["distinct"] is True and seams["missing"] == []


def test_pace_order_never_invents_a_seam():
    assert MP.pace_order({}) == {}
    assert MP.pace_order(None) == {}
    bp = _blueprint()
    del _cue(bp, "HERO_SHIFT")["start_s"]
    assert MP.pace_order(bp) == {}


def test_true_at_beat_is_the_solution_introduction_or_later():
    """The 60 s golden sheet's lowest_point (conflict C6) can never carry a
    hook earlier than the solution: it reads the_turn instead."""
    assert MP.true_at_beat(_blueprint()) == "the_turn"
    assert MP.true_at_beat({"true_at_beat": "lowest_point"}) == "the_turn"
    assert MP.true_at_beat({"true_at_beat": "hook"}) == "the_turn"
    assert MP.true_at_beat({"true_at_beat": ""}) == "the_turn"
    assert MP.true_at_beat({"true_at_beat": "the_rise"}) == "the_rise"
    assert MP.true_at_beat({}) == "the_turn"
    # the order carries it, so the factory needs one call
    assert MP.pace_order(_blueprint())["true_at_beat"] == "the_turn"


# ---- the production projection (method 10.3-10.4) --------------------------

def _beats():
    import story_arc.story_arc as SA
    return SA.BEATS


def _turns(report):
    return [t["turn"] for t in report["turns"]]


def test_teaching_map_is_the_twelve_production_beats_not_a_second_arc():
    """One row per canonical beat, in the arc module's own order -- the map
    projects onto the twelve, it never adds a beat or a second scheme."""
    rows = MP.teaching_map("campaign")
    assert [r["production_beat"] for r in rows] == list(_beats())
    assert len(rows) == 12
    assert all(r["teaching_function"] and r["cue_id"] for r in rows)
    ranks = [MP._required_cues("campaign").index(r["cue_id"]) for r in rows]
    assert ranks == sorted(ranks)                 # cues never run backwards


def test_lesson_map_swaps_only_the_hook_and_recap():
    lesson = MP.teaching_map("lesson")
    assert lesson[-1]["cue_id"] == "RECAP"
    assert lesson[-2]["cue_id"] == "MEMORY_HOOK"
    assert ([r["cue_id"] for r in lesson[:-2]]
            == [r["cue_id"] for r in MP.teaching_map("campaign")[:-2]])


def test_the_four_turns_record_a_reason_and_an_audible_change():
    turns = MP.musical_turns(_blueprint(), _method())
    assert [t["turn"] for t in turns] == [
        "attention_hook", "first_singing", "hero_shift",
        "solution_signature_hook"]
    for turn in turns:
        assert turn["reason"], turn
        assert turn["audible_change"]["to"], turn
        assert turn["production_beat"] in _beats(), turn
    assert turns[0]["vocal_status"] == "instrumental"      # spoken, not sung
    assert turns[1]["vocal_status"] == "first_sung"        # the ERM Drop
    assert (turns[2]["audible_change"]["rhythm"]
            != turns[1]["audible_change"]["rhythm"])       # a distinct second turn
    assert turns[3]["at_s"] > turns[2]["at_s"]             # hook comes later


def test_validate_records_the_turns():
    report = MP.validate(_blueprint(), _method())
    assert _turns(report) == ["attention_hook", "first_singing", "hero_shift",
                              "solution_signature_hook"]
    json.dumps(report)


def test_attention_hook_must_be_spoken():
    bp = _blueprint()
    _cue(bp, "BASELINE")["lyric_or_dialogue"] = ""
    report = MP.validate(bp, _method())
    assert report["reason_code"] == "ATTENTION_HOOK_NOT_SPOKEN", report["errors"]


def test_attention_hook_must_sound_first():
    bp = _blueprint()
    _cue(bp, "BASELINE")["start_s"] = 2
    _cue(bp, "PAIN_BUILD")["start_s"] = 1
    report = MP.validate(bp, _method())
    assert report["reason_code"] == "ATTENTION_HOOK_NOT_SPOKEN", report["errors"]
    assert "first thing heard" in report["errors"][0]["detail"]


def test_turn_without_a_reason_is_refused():
    bp = _blueprint()
    _cue(bp, "SOLUTION_HOOK")["trigger"] = ""
    _beat(bp, "SB-07")["why_it_belongs"] = ""
    report = MP.validate(bp, _method())
    assert report["reason_code"] == "TURN_REASON_MISSING", report["errors"]
    assert "solution_signature_hook" in report["errors"][0]["detail"]


def test_turn_without_an_audible_change_is_refused():
    bp = _blueprint()
    cue = _cue(bp, "ERM_DROP")
    cue["pace_after"] = cue["rhythmic_change"] = cue["emotional_direction"] = ""
    report = MP.validate(bp, _method())
    assert report["reason_code"] == "TURN_AUDIBLE_CHANGE_MISSING", report["errors"]
    assert "first_singing" in report["errors"][0]["detail"]


def test_hero_shift_must_state_pace_rhythm_and_emotional_direction():
    bp = _blueprint()
    _cue(bp, "HERO_SHIFT")["emotional_direction"] = ""
    report = MP.validate(bp, _method())
    assert report["reason_code"] == "TURN_AUDIBLE_CHANGE_MISSING", report["errors"]
    assert "emotional_direction" in report["errors"][0]["detail"]


def test_hero_shift_that_repeats_the_erm_is_not_distinct():
    bp = _blueprint()
    erm, hero = _cue(bp, "ERM_DROP"), _cue(bp, "HERO_SHIFT")
    for field in ("pace_after", "rhythmic_change", "emotional_direction"):
        hero[field] = erm[field]
    report = MP.validate(bp, _method())
    assert report["reason_code"] == "HERO_SHIFT_NOT_DISTINCT", report["errors"]


def test_shot_seeds_use_the_planner_field_names():
    seeds = MP.shot_seeds(_blueprint(), _method())
    assert len(seeds) == len(_blueprint()["story_beats"])
    assert all(s["story_stage"] in _beats() for s in seeds)
    first = seeds[0]
    assert first["shot_id"] == "SB-01"
    assert first["song_start"] == 0.0 and first["song_end"] == 8.0
    assert first["contract"]["viewer_understanding"] \
        == _beat(_blueprint(), "SB-01")["viewer_understanding"]
    assert "lyric_line_ids" in first["unresolved"]     # the timing map's job
    assert "treatment" in first["unresolved"]          # the planner's choice


def test_shot_seeds_mark_the_turn_cuts_and_the_product_stage():
    seeds = {s["shot_id"]: s for s in MP.shot_seeds(_blueprint(), _method())}
    assert seeds["SB-01"]["beat_cut"] is True          # the spoken attention hook
    assert seeds["SB-03"]["beat_cut"] is True          # the ERM Drop
    assert seeds["SB-05"]["beat_cut"] is True          # the Hero Shift
    assert seeds["SB-07"]["beat_cut"] is True          # the Solution Hook
    assert seeds["SB-02"]["beat_cut"] is False
    assert seeds["SB-01"]["product_visibility"] == "none"
    assert seeds["SB-07"]["product_visibility"] == "featured"


def test_storyboard_cards_carry_what_the_14_1_gate_needs():
    board = MP.storyboard_input(_blueprint(), _method())
    assert board["ready"] is True
    assert len(board["cards"]) == 8
    for card in board["cards"]:
        assert card["story_stage"] and card["viewer_understanding"]
        assert card["contract"]["necessity"]


def test_music_request_carries_the_method_keys():
    request = MP.music_request_input(_blueprint(), _method())
    assert request["true_at_beat"] == "the_turn"
    assert request["hook_plan_seed"] == {"true_at_beat": "the_turn"}
    assert PC.check_pace_plan(request["pace_order"]) == []
    assert [t["turn"] for t in request["turns"]] == _turns(
        MP.validate(_blueprint(), _method()))
    assert MP.music_request_input({}, _method()) == {}   # never invents a seam


def test_production_map_bundles_every_input():
    bundle = MP.production_map(_blueprint(), _method())
    assert sorted(bundle) == ["music_request", "shot_seeds", "storyboard",
                              "teaching_functions", "turns"]
    json.dumps(bundle)


if __name__ == "__main__":
    import traceback

    failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print("ok   %s" % name)
        except Exception:
            failed += 1
            print("FAIL %s" % name)
            traceback.print_exc()
    sys.exit(1 if failed else 0)
