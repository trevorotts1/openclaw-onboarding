"""PD-TEST-082 — AF-PEAK-END must read the artifact contract the producer
actually emits, and P3-ARC must be the place the next drift fails.

THE DEFECT (verified at code level AND against the live artifact).

`build_deck._chk_peak_end` is the AF-PEAK-END doctrine gate (P49): the arc must
declare a deliberate PEAK beat AND a deliberate ending beat, because a flat
ending is remembered as flat. It failed the live arc
(`~/.openclaw/workspace/departments/Presentations/runs/pres-operator-1d269693/
working/copy/arc_allocation.json`) for TWO INDEPENDENT reasons:

  1. THE CONTAINER KEY. The gate read
     `obj.get("slots") or obj.get("allocation") or obj.get("slides") or []`,
     but the live artifact carries its 8 slides under `slide_allocations`. So
     `slots` was `[]`, `tokens` was empty, `blob` was `""`, and every token test
     failed on an artifact that had in fact declared everything. This is the
     same divergence class as PD-TEST-067.

  2. THE EVIDENCE FORM. Even with the container fixed, the token scan reads
     only `arc_section` / `section` / `beat` / `tag` / `type` / `role` plus a
     `tags` list. The live labels are `opening, cost_of_inaction, higher_aim,
     value_anchor, urgency, ability_unblock, decision, trigger` and the live
     move tags are `PRIORITY_STACK ... TRIGGER`; NONE of them matches ANY token
     in PEAK_TAGS or ENDING_TAGS. Yet the same artifact declares both beats
     explicitly and machine-readably: `peak_apex`/`peak_apex_slide`,
     `decision_climax`/`decision_climax_slide`, `ending_beat`/`ending_slide`,
     `flat_ending: false`, and per-slide
     `arc_marks = {"peak": bool, "decision_climax": bool, "ending": bool}`.

THE DECISION PINNED HERE. The gate accepts EITHER form of evidence, and the
doctrine is NOT weakened:

  * PEAK   = a PEAK_TAGS token match (unchanged) OR a positive explicit
             declaration (some slide's `arc_marks.peak` is true, or a non-null
             `peak_apex_slide` / `peak_apex`).
  * ENDING = an ENDING_TAGS token match (unchanged) OR a positive explicit
             declaration (some slide's `arc_marks.ending` is true, or a non-null
             `ending_slide` / `ending_beat`) — AND `flat_ending` must not be
             truthy.
  * `flat_ending: true` FAILS the ending even when `ending_slide` is present.
  * ABSENCE of both forms still FAILS, with the existing message and the
    existing P49 / SOP-NORTHSTAR-00 citation.
  * PEAK_TAGS / ENDING_TAGS membership is DELIBERATELY UNCHANGED.

WHAT ELSE THIS FILE PINS

  A. THE CONTAINER-KEY LOCKSTEP. `build_deck.ARC_SLOT_LIST_KEYS` is asserted
     equal to `presentation_job.arc_slides.SLIDE_LIST_KEYS` whenever that
     module is importable (it is on the PD-TEST-067 branch, not yet on main).
     Two readers of the same artifact shape that drift apart is exactly how
     PD-TEST-067 and PD-TEST-082 both happened.
  B. THE SECOND READER AGREES. `slice1:peak_end` shadow-compares against
     `_chk_peak_end`, and in the default report-only mode the legacy verdict is
     the one RETURNED — so a fix to only one of them would leave the live run
     blocked (or, worse, silently diverging). Both now read ONE evidence dict.
  C. P3-ARC FAILS THE NEXT DRIFT LOUDLY. Its verifier was bare valid-JSON; it
     now asserts the arc's shape where the phase PROMISES it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import build_deck as bd  # noqa: E402
import phase_verifiers as pv  # noqa: E402
import slice1_gate_verifiers as s1  # noqa: E402


# ---------------------------------------------------------------------------
# The live artifact's shape, reproduced verbatim (values copied from run
# pres-operator-1d269693). No token from PEAK_TAGS or ENDING_TAGS appears
# anywhere in it -- asserted below, so the fixture can never silently stop
# proving the token scan fails on it.
# ---------------------------------------------------------------------------
def _live_arc() -> dict:
    return {
        "artifact": "arc_allocation.json",
        "phase": "P3-ARC",
        "deck_slug": "operator-1d269693",
        "slide_count": 8,
        "arc_sections": ["Opening", "Cost of Inaction", "Higher Aim",
                         "Value Anchor", "Urgency", "Ability Unblock",
                         "Decision", "Trigger"],
        "slide_allocations": [
            {"slide_number": 1, "arc_section": "opening",
             "move_tag": "PRIORITY_STACK",
             "arc_marks": {"peak": False, "decision_climax": False, "ending": False}},
            {"slide_number": 2, "arc_section": "cost_of_inaction",
             "move_tag": "COST_OF_INACTION",
             "arc_marks": {"peak": False, "decision_climax": False, "ending": False}},
            {"slide_number": 3, "arc_section": "higher_aim",
             "move_tag": "HIGHER_PRIORITY",
             "arc_marks": {"peak": False, "decision_climax": False, "ending": False}},
            {"slide_number": 4, "arc_section": "value_anchor",
             "move_tag": "VALUE_ANCHOR",
             "arc_marks": {"peak": True, "decision_climax": False, "ending": False}},
            {"slide_number": 5, "arc_section": "urgency",
             "move_tag": "URGENCY_SCARCITY",
             "arc_marks": {"peak": False, "decision_climax": False, "ending": False}},
            {"slide_number": 6, "arc_section": "ability_unblock",
             "move_tag": "ABILITY_UNBLOCK",
             "arc_marks": {"peak": False, "decision_climax": False, "ending": False}},
            {"slide_number": 7, "arc_section": "decision",
             "move_tag": "RERANK_DEMAND",
             "arc_marks": {"peak": False, "decision_climax": True, "ending": False}},
            {"slide_number": 8, "arc_section": "trigger",
             "move_tag": "TRIGGER",
             "arc_marks": {"peak": False, "decision_climax": False, "ending": True}},
        ],
        "peak_apex": {"slide_number": 4, "arc_section": "value_anchor",
                      "move_tag": "VALUE_ANCHOR", "summary": "Anchor value."},
        "peak_apex_slide": 4,
        "decision_climax": {"slide_number": 7, "arc_section": "decision",
                            "move_tag": "RERANK_DEMAND", "summary": "Ask now."},
        "decision_climax_slide": 7,
        "ending_beat": {"slide_number": 8, "arc_section": "trigger",
                        "move_tag": "TRIGGER", "summary": "Fire the trigger."},
        "ending_slide": 8,
        "flat_ending": False,
    }


@pytest.fixture()
def doctrine_run(tmp_path: Path) -> Path:
    """A doctrine-ACTIVE run dir (the switch that engages the AF gates)."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "priority_shift_spec.json").write_text(
        json.dumps({"true_goal": "convert audience priority to owner offer"}))
    return rd


def _write_arc(rd: Path, obj) -> None:
    (rd / "working" / "copy" / "arc_allocation.json").write_text(json.dumps(obj))


def _strip_all_explicit(arc: dict) -> dict:
    """Remove BOTH explicit forms: the top-level declarations AND arc_marks."""
    out = {k: v for k, v in arc.items()
           if k not in ("peak_apex", "peak_apex_slide", "decision_climax",
                        "decision_climax_slide", "ending_beat", "ending_slide",
                        "flat_ending")}
    out["slide_allocations"] = [
        {k: v for k, v in s.items() if k != "arc_marks"}
        for s in arc["slide_allocations"]]
    return out


# ---------------------------------------------------------------------------
# 0. Fixture integrity: the live shape really is invisible to the token scan.
# ---------------------------------------------------------------------------
def test_live_fixture_carries_no_token_from_either_list():
    arc = _live_arc()
    blob = " ".join(
        [str(s["arc_section"]).lower() for s in arc["slide_allocations"]]
        + [str(s["move_tag"]).lower() for s in arc["slide_allocations"]]
        + [str(s).lower() for s in arc["arc_sections"]])
    hits = [t for t in bd.PEAK_TAGS + bd.ENDING_TAGS if t in blob]
    assert hits == [], (
        f"the live-shape fixture now contains {hits} — it no longer proves that "
        "the token scan alone fails on the live artifact")


# ---------------------------------------------------------------------------
# 1. Layer 1 — the container key. `slide_allocations` must be readable, through
#    the SHARED reader PD-TEST-067 introduced (never a private second copy).
# ---------------------------------------------------------------------------
def test_container_key_slide_allocations_is_read():
    arc = _live_arc()
    slots = bd.ARC_SLOTS_FROM_OBJ(arc)
    assert slots is not None, "slide_allocations must be a recognised container"
    assert len(slots) == 8
    # The legacy keys keep working, in the same one reader.
    assert bd.ARC_SLOTS_FROM_OBJ({"slots": [{"slide": 1}]}) == [
        {"slide": 1, "ordinal": 1}]
    assert bd.ARC_SLOTS_FROM_OBJ({"allocation": [1, 2]}) == [
        {"slot": 1, "ordinal": 1, "slide": 1},
        {"slot": 2, "ordinal": 2, "slide": 2}]
    assert bd.ARC_SLOTS_FROM_OBJ({"slides": ["a"]}) == [
        {"slot": "a", "ordinal": 1, "slide": 1}]
    assert bd.ARC_SLOTS_FROM_OBJ([{"slide": 1}]) == [{"slide": 1, "ordinal": 1}]
    assert bd.ARC_SLOTS_FROM_OBJ({"something_else": [1]}) is None


def test_one_shape_reader_shared_with_arc_slides():
    """PD-TEST-067's invariant: ONE reader for the deck's slide-array shape.
    build_deck must ALIAS presentation_job.arc_slides, not re-implement it —
    asserted by IDENTITY (the same object), which no copy can satisfy."""
    from presentation_job import arc_slides
    assert bd.ARC_SLOTS_FROM_OBJ is arc_slides.slots_from_obj, (
        "build_deck has its own container reader again — that divergence IS "
        "PD-TEST-067/082")
    assert bd.ARC_SLOT_LIST_KEYS is arc_slides.SLIDE_LIST_KEYS, (
        "build_deck has its own container-key tuple again")
    # And the live container key is in the shared tuple.
    assert "slide_allocations" in arc_slides.SLIDE_LIST_KEYS


def test_bare_string_slots_still_contribute_tokens():
    """Widening the container reader must not DROP evidence the old scan
    accepted: arc_slides normalises a non-dict entry to {"slot": entry}, and a
    bare list of strings was a FORM 1 token source before PD-TEST-082."""
    ev = bd._arc_peak_end_evidence(["apex", "recap"])
    assert ev["token_peak"] is True, ev
    assert ev["token_ending"] is True, ev
    assert "apex" in ev["blob"] and "recap" in ev["blob"], ev["blob"]


# ---------------------------------------------------------------------------
# 2. Layer 2 + the decision — the live shape PASSES; flat_ending FAILS.
# ---------------------------------------------------------------------------
def test_live_shape_passes(doctrine_run):
    _write_arc(doctrine_run, _live_arc())
    assert bd._chk_peak_end(doctrine_run) == "", (
        "the live arc declares its peak AND its ending explicitly; the gate "
        "must accept the producer's real contract")
    ev = bd._arc_peak_end_evidence(_live_arc())
    assert ev["token_peak"] is False and ev["token_ending"] is False, (
        "sanity: this fixture's PASS must come from the explicit form, never "
        "from a token")
    assert ev["marked_peak"] and ev["marked_ending"]
    assert ev["declared_peak"] and ev["declared_ending"]
    assert ev["peak"] is True and ev["ending"] is True


def test_flat_ending_still_fails(doctrine_run):
    arc = _live_arc()
    arc["flat_ending"] = True
    _write_arc(doctrine_run, arc)
    reason = bd._chk_peak_end(doctrine_run)
    assert reason, "flat_ending: true MUST still fail the ending check"
    assert "no deliberate ending/recap/CTA beat" in reason, reason
    # The doctrine's core is untouched: only the ENDING half fails.
    assert "no PEAK/APEX/WOW beat" not in reason, (
        "flat_ending defeats the ending only — the peak declaration stands")
    # And the slice-side reader must agree, since report-only returns it.
    ok, reasons = s1.get_verifier("slice1:peak_end").run_verifier(doctrine_run)
    assert not ok, "slice1:peak_end accepted a flat ending"
    assert any("no deliberate ending" in r for r in reasons), reasons


def test_flat_ending_defeats_a_token_match_too(doctrine_run):
    """flat_ending is not a tie-breaker on the explicit form only — a flat
    ending is remembered as flat however the ending was declared."""
    _write_arc(doctrine_run, {
        "slide_allocations": [{"slide_number": 3, "arc_section": "recap"},
                              {"slide_number": 4, "arc_section": "apex"}],
        "flat_ending": True})
    reason = bd._chk_peak_end(doctrine_run)
    assert reason and "no deliberate ending/recap/CTA beat" in reason, reason


# ---------------------------------------------------------------------------
# 3. Absence of BOTH forms still fails, with the existing message + citation.
# ---------------------------------------------------------------------------
def test_absence_of_both_forms_fails(doctrine_run):
    _write_arc(doctrine_run, _strip_all_explicit(_live_arc()))
    reason = bd._chk_peak_end(doctrine_run)
    assert reason, "an arc with neither a token nor an explicit declaration fails"
    assert "AF-PEAK-END" in reason
    assert "no PEAK/APEX/WOW beat" in reason
    assert "no deliberate ending/recap/CTA beat" in reason
    assert "P49, SOP-NORTHSTAR-00" in reason
    assert "a flat ending is remembered as flat" in reason


def test_missing_arc_defers(doctrine_run):
    """No arc -> '' (defer); _chk_arc owns absence, not this gate."""
    assert bd._chk_peak_end(doctrine_run) == ""


def test_unparseable_arc_fails(doctrine_run):
    (doctrine_run / "working" / "copy" / "arc_allocation.json").write_text("{oops")
    reason = bd._chk_peak_end(doctrine_run)
    assert reason and "not valid JSON" in reason, reason


def test_no_doctrine_defers(tmp_path):
    """Without doctrine active the gate is silent — unchanged."""
    rd = tmp_path / "nod"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    _write_arc(rd, _strip_all_explicit(_live_arc()))
    assert bd._chk_peak_end(rd) == ""


# ---------------------------------------------------------------------------
# 4. No regression: the legacy token form, and each half independently.
# ---------------------------------------------------------------------------
def test_legacy_token_form_passes(doctrine_run):
    _write_arc(doctrine_run, [
        {"slide": 1, "arc_section": "hook"},
        {"slide": 2, "arc_section": "apex", "beat": "promise-apex"},
        {"slide": 3, "arc_section": "recap"}])
    assert bd._chk_peak_end(doctrine_run) == ""


def test_each_half_fails_independently(doctrine_run):
    """Evidence for ONE beat never satisfies the other."""
    peak_only = _live_arc()
    for k in ("ending_beat", "ending_slide", "flat_ending"):
        peak_only.pop(k, None)
    peak_only["slide_allocations"] = [
        {**{k: v for k, v in s.items() if k != "arc_marks"},
         "arc_marks": {"peak": s["arc_marks"]["peak"]}}
        for s in peak_only["slide_allocations"]]
    _write_arc(doctrine_run, peak_only)
    reason = bd._chk_peak_end(doctrine_run)
    assert reason and "no deliberate ending/recap/CTA beat" in reason, reason
    assert "no PEAK/APEX/WOW beat" not in reason, reason

    ending_only = _live_arc()
    for k in ("peak_apex", "peak_apex_slide", "flat_ending"):
        ending_only.pop(k, None)
    ending_only["slide_allocations"] = [
        {**{k: v for k, v in s.items() if k != "arc_marks"},
         "arc_marks": {"ending": s["arc_marks"]["ending"]}}
        for s in ending_only["slide_allocations"]]
    _write_arc(doctrine_run, ending_only)
    reason = bd._chk_peak_end(doctrine_run)
    assert reason and "no PEAK/APEX/WOW beat" in reason, reason
    assert "no deliberate ending/recap/CTA beat" not in reason, reason


def test_placeholders_are_not_declarations(doctrine_run):
    """A non-null-but-empty placeholder is not a POSITIVE declaration: null,
    false, '', {} and ordinal 0 all leave the beat undeclared."""
    for placeholder in (None, False, "", "   ", {}, 0):
        arc = _strip_all_explicit(_live_arc())
        arc["peak_apex_slide"] = placeholder
        arc["ending_slide"] = placeholder
        _write_arc(doctrine_run, arc)
        reason = bd._chk_peak_end(doctrine_run)
        assert reason, f"placeholder {placeholder!r} must not declare a beat"
        assert "no PEAK/APEX/WOW beat" in reason, (placeholder, reason)


def test_arc_marks_require_a_real_json_true(doctrine_run):
    """arc_marks are the producer's own booleans; a truthy stand-in is a
    producer defect and must not be papered over."""
    arc = _strip_all_explicit(_live_arc())
    arc["slide_allocations"][3]["arc_marks"] = {"peak": 1}
    arc["slide_allocations"][7]["arc_marks"] = {"ending": "true"}
    _write_arc(doctrine_run, arc)
    reason = bd._chk_peak_end(doctrine_run)
    assert reason and "no PEAK/APEX/WOW beat" in reason, reason


# ---------------------------------------------------------------------------
# 5. The two readers agree (PD-TEST-067's "one reader" discipline).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,arc,should_pass", [
    ("live", None, True),
    ("flat_ending", None, False),
    ("no_evidence", None, False),
    ("legacy_tokens", [{"slide": 1, "arc_section": "hook"},
                       {"slide": 2, "arc_section": "apex", "beat": "promise-apex"},
                       {"slide": 3, "arc_section": "recap"}], True),
])
def test_slice_and_preflight_readers_agree(doctrine_run, name, arc, should_pass):
    if arc is None:
        arc = _live_arc()
        if name == "flat_ending":
            arc["flat_ending"] = True
        elif name == "no_evidence":
            arc = _strip_all_explicit(arc)
    _write_arc(doctrine_run, arc)
    legacy_pass = bd._chk_peak_end(doctrine_run) == ""
    ok, reasons = s1.get_verifier("slice1:peak_end").run_verifier(doctrine_run)
    assert legacy_pass is should_pass, (name, "preflight", reasons)
    assert ok is should_pass, (name, "slice1", reasons)


# ---------------------------------------------------------------------------
# 6. P3-ARC asserts the SHAPE where the phase promises it.
# ---------------------------------------------------------------------------
def test_p3_arc_accepts_the_live_shape(doctrine_run):
    _write_arc(doctrine_run, _live_arc())
    ok, reasons = pv.verify("P3-ARC", doctrine_run)
    assert ok, f"the live arc must attest P3-ARC, got {reasons}"


def test_p3_arc_fails_absent_artifact(doctrine_run):
    ok, reasons = pv.verify("P3-ARC", doctrine_run)
    assert not ok, "absence is still a hard FAIL (PRIMARY gate)"
    assert any("not found" in r for r in reasons), reasons


def test_p3_arc_fails_unrecognised_container(doctrine_run):
    """The PD-TEST-067/082 drift class: valid JSON, unconsumable slides."""
    _write_arc(doctrine_run, {"peak_apex_slide": 4, "ending_slide": 8,
                              "my_own_slides": [{"slide": 1}, {"slide": 2}]})
    ok, reasons = pv.verify("P3-ARC", doctrine_run)
    assert not ok, "an arc no reader can consume must not be blessed done"
    # The message is PD-TEST-067's (this gate already existed and is only
    # EXTENDED here, never replaced) — it must still name the readable keys.
    assert any("no slide allocation array this pipeline can read" in r
               for r in reasons), reasons
    assert any("slide_allocations" in r for r in reasons), reasons


def test_p3_arc_fails_empty_slide_array(doctrine_run):
    _write_arc(doctrine_run, {"slide_allocations": [],
                              "peak_apex_slide": 4, "ending_slide": 8})
    ok, reasons = pv.verify("P3-ARC", doctrine_run)
    assert not ok
    assert any("zero slides" in r for r in reasons), reasons


def test_p3_arc_fails_arc_declaring_no_beats(doctrine_run):
    """The producer-side strengthening: an arc that declares NEITHER a token
    NOR an explicit peak/ending now fails AT P3-ARC, loudly, instead of
    starving AF-PEAK-END silently one phase later."""
    _write_arc(doctrine_run, _strip_all_explicit(_live_arc()))
    ok, reasons = pv.verify("P3-ARC", doctrine_run)
    assert not ok, "P3-ARC must require the peak/ending declaration"
    assert any("no PEAK/APEX/WOW beat" in r for r in reasons), reasons
    assert any("no deliberate ending/recap/CTA beat" in r for r in reasons), reasons


def test_p3_arc_fails_flat_ending_with_no_other_evidence(doctrine_run):
    arc = _strip_all_explicit(_live_arc())
    arc["flat_ending"] = True
    _write_arc(doctrine_run, arc)
    ok, reasons = pv.verify("P3-ARC", doctrine_run)
    assert not ok


def test_p3_arc_accepts_the_legacy_token_form(doctrine_run):
    """No regression: the historical shape still attests P3-ARC."""
    _write_arc(doctrine_run, [
        {"slide": 1, "arc_section": "hook"},
        {"slide": 2, "arc_section": "apex", "beat": "promise-apex"},
        {"slide": 3, "arc_section": "recap"}])
    ok, reasons = pv.verify("P3-ARC", doctrine_run)
    assert ok, f"the legacy token form must still attest P3-ARC, got {reasons}"


def test_p3_arc_binding_contract_is_proven():
    """FIX 107: the symbols _verify_arc_allocation calls are in the binding
    contract, so a rename fails loudly at import/preflight."""
    proven = pv.assert_bound()
    for sym in ("build_deck.ARC_SLOT_LIST_KEYS", "build_deck.ARC_SLOTS_FROM_OBJ",
                "build_deck._arc_peak_end_evidence"):
        assert sym in proven, f"{sym} is not in the proven binding contract"


# ---------------------------------------------------------------------------
# 7. OPEN DOCTRINE QUESTION, pinned so it cannot be absorbed silently.
#
# The repo's OWN canonical reference arc declares its peak and ending in NO
# recognised form: its arc_section values are the four Signature-Presentation
# PHASES (Avatar / Signature Story / Transformational Teaching / Purpose
# Pitch), which carry no PEAK_TAGS or ENDING_TAGS token, and it has no
# arc_marks / peak_apex* / ending_* fields. So:
#   * AF-PEAK-END ALREADY failed it at this change's base (the token scan finds
#     nothing) — that is pre-existing, NOT introduced here;
#   * P3-ARC now refuses it one phase earlier, because PD-TEST-082 extended that
#     gate to require the declaration the coordinator asked for.
# This test does not decide the question; it makes the consequence impossible
# to miss, and it is deliberately independent of the 103-slide example so that
# editing the example cannot make the finding disappear.
# ---------------------------------------------------------------------------
def test_canonical_reference_shape_declares_no_beats_finding():
    canonical = {
        "deck_type": "signature", "deck_slug": "golden-quest", "bands": {},
        "slots": [{"slide": i, "phase": "avatar",
                   "arc_section": s, "hook": False, "label_slide": False,
                   "case_study": False}
                  for i, s in enumerate(
                      ["Avatar"] * 11 + ["Signature Story"] * 13
                      + ["Transformational Teaching"] * 36
                      + ["Purpose Pitch"] * 43, start=1)],
    }
    ev = bd._arc_peak_end_evidence(canonical)
    assert ev["token_peak"] is False and ev["marked_peak"] is False \
        and ev["declared_peak"] is False, (
        "the canonical Signature-Presentation arc_section vocabulary is the four "
        "PHASES; if a PEAK tag now matches it, PEAK_TAGS membership changed — "
        "which PD-TEST-082 forbids")
    assert ev["token_ending"] is False and ev["marked_ending"] is False \
        and ev["declared_ending"] is False, (
        "similarly for ENDING_TAGS")
    assert ev["peak"] is False and ev["ending"] is False
    # The four phases are the ENTIRE canonical arc_section vocabulary.
    assert {"Avatar", "Signature Story", "Transformational Teaching",
            "Purpose Pitch"} <= set(
        s["arc_section"] for s in canonical["slots"])
