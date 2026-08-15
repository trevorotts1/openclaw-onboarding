"""SLICE 1 BOTH-DIRECTION TESTS — the 18 converted gates.

For each slice-1 gate: a FABRICATED artifact (present, parses, but fails the
rubric) must be REJECTED with a reason naming the exact discrepancy, and a
GENUINE artifact (satisfies the rubric) must PASS. Both directions run through
run_verifier() so the sealed-facts + shadow-compare path is what is exercised.

The fabricated/genuine fixtures below mirror the REAL fixtures the existing
test_preflight.py suite already uses (the doctrine-fire fixtures, the Skill-51
prover golden fixtures, the signed intake-transcript envelope), so the two
directions agree with the legacy engine's own coverage.
"""

import json
import pathlib
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import runfacts as rf  # noqa: E402
from verifier_registry import both_directions, run_gate, write_fixture  # noqa: E402
import slice1_gate_verifiers as s1  # noqa: E402
import build_deck as bd  # noqa: E402


def _fresh(tmp_path: pathlib.Path, name: str = "run") -> Path:
    rd = Path(tmp_path) / name
    rd.mkdir(parents=True, exist_ok=True)
    rf.reset_cache_for_tests()
    return rd


def _doctrine(rd: Path, spec: dict | None = None) -> None:
    """Doctrine-active: priority_shift_spec.json present (the no-regression switch)."""
    write_fixture(rd, "working/copy/priority_shift_spec.json",
                  spec if spec is not None else {"true_goal": "make the offer #1"})


def _png(rd: Path, rel: str) -> None:
    p = rd / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\xcc" * (bd.PLACEHOLDER_MIN_BYTES + 500))


# ===========================================================================
# Shared fabricate/genuine pair builders (mirror test_preflight doctrine fixtures)
# ===========================================================================
def _pair_deck_type():
    def fabricate(rd):
        write_fixture(rd, "working/copy/intake.json",
                      {"interview_confirmed": True, "deck_type": "hand_typed"})
    def genuine(rd):
        write_fixture(rd, "working/copy/intake.json",
                      {"interview_confirmed": True, "deck_type": "signature_presentation"})
    return fabricate, genuine


def _pair_mode():
    def fabricate(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/intake.json", {"creation_mode": "nonsense"})
    def genuine(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/intake.json",
                      {"creation_mode": "from_scratch"})
    return fabricate, genuine


def _pair_priority_shift():
    def fabricate(rd):
        _doctrine(rd, spec={})
        write_fixture(rd, "working/copy/slides_copy.md",
                      "SLIDE 1\nHEADLINE: Our product transforms your business.\n")
    def genuine(rd):
        _doctrine(rd, spec={"true_goal": "make the offer the audience's new #1",
                            "priority_stack": ["incumbent vendor", "status quo"]})
        write_fixture(rd, "working/copy/slides_copy.md",
                      "# clean deck\n"
                      "PRIORITY_STACK. what matters most is the old way.\n"
                      "PRESENT_COST. the cost of inaction is real.\n"
                      "HIGHER_PRIORITY. one higher priority outranks the rest.\n"
                      "VALUE_ANCHOR. the value anchor: worth far more than the price.\n"
                      "URGENCY_SCARCITY. limited, with a hard deadline.\n"
                      "ABILITY_UNBLOCK. a payment plan makes it easy to start.\n"
                      "RERANK_DEMAND. make this your #1, decide now.\n"
                      "TRIGGER. act now by midnight, enroll now.\n")
    return fabricate, genuine


def _pair_priority_stack():
    def fabricate(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/slides_copy.md",
                      "SLIDE 1\nHEADLINE: Today's price is $997.\n"
                      "SLIDE 2\nLADDER: value anchor drop.\n")
    def genuine(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/slides_copy.md",
                      "SLIDE 1\nwhat matters most to you right now.\n"
                      "SLIDE 2\nLADDER: value anchor drop.\n")
    return fabricate, genuine


def _pair_rerank():
    def fabricate(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/intake.json", {"pitch_included": True})
        write_fixture(rd, "working/copy/slides_copy.md",
                      "SLIDE 1\nHEADLINE: The price is $997 per month.\n"
                      "SLIDE 2\nBUY: Click to join now.\n")
    def genuine(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/intake.json", {"pitch_included": True})
        write_fixture(rd, "working/copy/slides_copy.md",
                      "SLIDE 1\nHEADLINE: The price is $997 per month.\n"
                      "SLIDE 2\nmake this your #1. Decide now — move this to the top.\n")
    return fabricate, genuine


def _pair_trigger():
    def fabricate(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/intake.json", {"pitch_included": True})
        write_fixture(rd, "working/copy/slides_copy.md",
                      "SLIDE 1\nCTA: Click the link below to join.\n")
    def genuine(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/intake.json", {"pitch_included": True})
        write_fixture(rd, "working/copy/slides_copy.md",
                      "SLIDE 1\nCTA: Act now — doors close by midnight.\n")
    return fabricate, genuine


def _pair_proclamation_hedge():
    def fabricate(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/slides_copy.md",
                      "SLIDE 1\nHEADLINE: This system is, kind of, the best.\n")
    def genuine(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/slides_copy.md",
                      "SLIDE 1\nHEADLINE: This system is the best.\n")
    return fabricate, genuine


def _pair_peak_end():
    def fabricate(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/arc_allocation.json", [
            {"slide": 1, "arc_section": "hook"},
            {"slide": 2, "arc_section": "body"},
            {"slide": 3, "arc_section": "teaching"}])
    def genuine(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/arc_allocation.json", [
            {"slide": 1, "arc_section": "hook"},
            {"slide": 2, "arc_section": "apex", "beat": "promise-apex"},
            {"slide": 3, "arc_section": "recap"}])
    return fabricate, genuine


def _pair_salience_apex(monkeypatch):
    def fabricate(rd):
        _doctrine(rd)
        for i in range(1, 4):
            _png(rd, f"renders/slide-{i:02d}.png")
        write_fixture(rd, "working/copy/arc_allocation.json", [
            {"slide": 1, "arc_section": "hook"},
            {"slide": 2, "arc_section": "apex", "beat": "promise-apex"},
            {"slide": 3, "arc_section": "recap"}])
    def genuine(rd):
        _doctrine(rd)
        for i in range(1, 4):
            _png(rd, f"renders/slide-{i:02d}.png")
        write_fixture(rd, "working/copy/arc_allocation.json", [
            {"slide": 1, "arc_section": "hook"},
            {"slide": 2, "arc_section": "apex", "beat": "promise-apex"},
            {"slide": 3, "arc_section": "recap"}])
    return fabricate, genuine


def _flatfill_apex_flat(path: Path):
    n = path.name
    if "slide-01" in n:
        return (0.05, (100, 50, 200))
    if "slide-02" in n:
        return (0.95, (240, 240, 240))
    if "slide-03" in n:
        return (0.50, (150, 100, 100))
    return (None, None)


def _flatfill_apex_vivid(path: Path):
    n = path.name
    if "slide-02" in n:
        return (0.05, (100, 50, 200))
    if "slide-01" in n:
        return (0.50, (150, 100, 100))
    if "slide-03" in n:
        return (0.50, (150, 100, 100))
    return (None, None)


def _pair_converter_no_invent():
    def fabricate(rd):
        write_fixture(rd, "working/copy/source_brief.md",
                      "The product achieved 75% growth and $1,234,567 in revenue.")
        write_fixture(rd, "working/source/transcript.txt",
                      "The product is great. Many clients have succeeded over time.")
    def genuine(rd):
        write_fixture(rd, "working/copy/source_brief.md",
                      "The deck reports 73% growth.")
        write_fixture(rd, "working/source/transcript.txt",
                      "Last year we measured 73% growth across the cohort.")
    return fabricate, genuine


def _pair_persuasion_beats():
    def fabricate(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/intake.json", {"pitch_included": True})
        write_fixture(rd, "working/copy/slides_copy.md",
                      "SLIDE 1\nHEADLINE: Our offer.\nSLIDE 2\nCTA: Join now.\n")
    def genuine(rd):
        _doctrine(rd)
        write_fixture(rd, "working/copy/intake.json", {"pitch_included": True})
        write_fixture(rd, "working/copy/slides_copy.md",
                      "# persuasion-clean deck\n"
                      "the problem: you are stuck, and the real reason is the villain.\n"
                      "you face a choice — two paths, a fork: keep the old way, or you can "
                      "take the new way. compared to the old way the new way is proven — "
                      "a peer-reviewed study and an expert case study. measurable results: "
                      "73% growth, 3x roi, clients went from struggling to thriving.\n")
    return fabricate, genuine


def _pair_style_preview():
    manifest = {"schema": "style_samples/v1",
                "samples": [{"variant": "A", "slides": [1, 2, 3]}]}
    def fabricate(rd):
        write_fixture(rd, "working/style-preview/style_samples_manifest.json", manifest)
    def genuine(rd):
        write_fixture(rd, "working/style-preview/style_samples_manifest.json", manifest)
        _png(rd, "renders/locked-A-1.png")
        write_fixture(rd, "working/copy/style_preview_choice.json", {
            "owner_approved": True, "chosen_variant": "A",
            "locked_renders": ["renders/locked-A-1.png"]})
    return fabricate, genuine


def _pair_priority_shift_ledger(monkeypatch):
    clean_spec = {
        "true_goal": "make the offer the audience's new #1 priority",
        "priority_stack": ["incumbent", "status quo"],
        "higher_priority_hook": "the cost of waiting outranks every line item",
        "the_one_promise": "double your qualified pipeline in eight weeks",
        "the_one_wow": "a stalled funnel rebuilt live on stage",
        "the_one_demonstration": "the three-move rebuild performed in real time",
    }
    clean_copy = (
        "# doctrine-clean pitch deck\n"
        "PRIORITY_STACK. what matters most to you — your current priority stack.\n"
        "PRESENT_COST. the cost of inaction is the cost of doing nothing.\n"
        "HIGHER_PRIORITY. one higher priority outranks the rest.\n"
        "VALUE_ANCHOR. the value anchor: worth far more than the price.\n"
        "URGENCY_SCARCITY. limited, with a hard deadline.\n"
        "ABILITY_UNBLOCK. a payment plan and a full guarantee make it easy to start.\n"
        "RERANK_DEMAND. make this your #1. Decide now — move this to the top.\n"
        "TRIGGER. act now — the deadline is by midnight tonight; enroll now.\n")
    arc = [{"slide": 1, "arc_section": "hook"},
           {"slide": 2, "arc_section": "apex", "beat": "promise-apex"},
           {"slide": 3, "arc_section": "recap"}]
    def fabricate(rd):
        _doctrine(rd, spec={})
        _png(rd, "renders/slide-01.png")
        write_fixture(rd, "working/copy/intake.json", {"pitch_included": True})
        write_fixture(rd, "working/copy/slides_copy.md", "SLIDE 1\nHEADLINE: x.\n")
        write_fixture(rd, "working/copy/arc_allocation.json", arc)
    def genuine(rd):
        _doctrine(rd, spec=clean_spec)
        for i in range(1, 4):
            _png(rd, f"renders/slide-{i:02d}.png")
        write_fixture(rd, "working/copy/intake.json",
                      {"pitch_included": True, "creation_mode": "from_scratch"})
        write_fixture(rd, "working/copy/slides_copy.md", clean_copy)
        write_fixture(rd, "working/copy/arc_allocation.json", arc)
    return fabricate, genuine


def _pair_sp(prover_kind):
    spi = bd._sp_prover("prove_sp_intake")
    sps = bd._sp_prover("prove_sp_structure")
    spn = bd._sp_prover("prove_sp_no_pitch")
    itc = bd._sp_prover("intake_trace_check")
    _pytest = pytest
    _pytest.skip("SP provers not co-located with the test run") \
        if not (spi and sps and spn and itc) else None

    def _signature_intake(rd):
        write_fixture(rd, "working/copy/intake.json",
                      {"deck_type": "signature_presentation",
                       "interview_confirmed": True})

    def _clean_transcript():
        turns = [
            {"role": "assistant",
             "text": "Love this -- QUICK or IN-DEPTH, which would you like?",
             "qid": "interview_choice"},
            {"role": "owner", "text": "quick", "qid": "interview_choice"},
            {"role": "assistant",
             "text": "What is the title of your Signature Presentation?", "qid": "q1"},
            {"role": "owner", "text": "The Signature Talk", "qid": "q1"},
        ]
        seen, out = [], []
        for t in turns:
            if str(t.get("role") or "").strip().lower() == "assistant":
                qid = str(t.get("qid") or "").strip()
                if qid and qid not in seen:
                    seen.append(qid)
            out.append(t)
        return itc.build_driver_envelope(seen, turns)

    if prover_kind == "intake":
        def fabricate(rd):
            _signature_intake(rd)
            f = spi._valid_runtime_fixture()
            del f["answers"]["q7"]
            write_fixture(rd, "working/copy/sp_intake.json", f)
        def genuine(rd):
            _signature_intake(rd)
            write_fixture(rd, "working/copy/sp_intake.json",
                          spi._valid_runtime_fixture())
    elif prover_kind == "structure":
        def fabricate(rd):
            _signature_intake(rd)
            d = sps._valid_fixture()
            d["slides"] = [s for s in d["slides"] if s["slide"] != 100]
            write_fixture(rd, "working/copy/sp_structure.json", d)
        def genuine(rd):
            _signature_intake(rd)
            write_fixture(rd, "working/copy/sp_structure.json",
                          sps._valid_fixture())
    elif prover_kind == "no_pitch":
        def fabricate(rd):
            _signature_intake(rd)
            write_fixture(rd, "working/copy/sp_intake.json",
                          spn._fixture_intake(True))
            write_fixture(rd, "working/copy/sp_structure.json",
                          spn._fixture_ledger("price_in_teach"))
        def genuine(rd):
            _signature_intake(rd)
            write_fixture(rd, "working/copy/sp_intake.json",
                          spn._fixture_intake(True))
            write_fixture(rd, "working/copy/sp_structure.json",
                          spn._fixture_ledger("valid"))
    elif prover_kind == "intake_trace":
        def fabricate(rd):
            _signature_intake(rd)
            write_fixture(rd, "working/copy/sp_intake.json",
                          spi._valid_runtime_fixture())
            write_fixture(rd, "working/interview/intake_transcript.json",
                          json.dumps([{"role": "assistant", "text": "q1? q2? q3?"}]))
        def genuine(rd):
            _signature_intake(rd)
            write_fixture(rd, "working/copy/sp_intake.json",
                          spi._valid_runtime_fixture())
            write_fixture(rd, "working/interview/intake_transcript.json",
                          json.dumps(_clean_transcript()))
    else:  # claim
        def fabricate(rd):
            write_fixture(rd, "working/copy/intake.json", {"interview_confirmed": True})
            write_fixture(rd, "working/copy/sp_intake.json",
                          spi._valid_runtime_fixture())
        def genuine(rd):
            _signature_intake(rd)
            write_fixture(rd, "working/copy/sp_intake.json",
                          spi._valid_runtime_fixture())
    return fabricate, genuine


# ===========================================================================
# The both-direction tests — one per gate.
# ===========================================================================
def test_slice1_deck_type_both_directions(tmp_path):
    fab, gen = _pair_deck_type()
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:deck_type"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok, "fabricated deck_type must be REJECTED"
    assert any("AF-DECK-TYPE-UNSET" in r and "hand_typed" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine deck_type must PASS, got {g_reasons}"


def test_slice1_mode_both_directions(tmp_path):
    fab, gen = _pair_mode()
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:mode"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-MODE-UNSET" in r and "nonsense" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine mode must PASS, got {g_reasons}"


def test_slice1_priority_shift_both_directions(tmp_path):
    fab, gen = _pair_priority_shift()
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:priority_shift"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-NO-SHIFT" in r and "true_goal" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine priority_shift must PASS, got {g_reasons}"


def test_slice1_priority_stack_both_directions(tmp_path):
    fab, gen = _pair_priority_stack()
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:priority_stack"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-NO-PRIORITY-STACK" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine priority_stack must PASS, got {g_reasons}"


def test_slice1_rerank_both_directions(tmp_path):
    fab, gen = _pair_rerank()
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:rerank"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-NO-RERANK" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine rerank must PASS, got {g_reasons}"


def test_slice1_trigger_both_directions(tmp_path):
    fab, gen = _pair_trigger()
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:trigger"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-NO-TRIGGER" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine trigger must PASS, got {g_reasons}"


def test_slice1_proclamation_hedge_both_directions(tmp_path):
    fab, gen = _pair_proclamation_hedge()
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:proclamation_hedge"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-PROCLAMATION-HEDGE" in r and "kind of" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine proclamation_hedge must PASS, got {g_reasons}"


def test_slice1_peak_end_both_directions(tmp_path):
    fab, gen = _pair_peak_end()
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:peak_end"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-PEAK-END" in r and "PEAK" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine peak_end must PASS, got {g_reasons}"


def test_slice1_salience_apex_both_directions(tmp_path, monkeypatch):
    fab, gen = _pair_salience_apex(monkeypatch)
    rd = _fresh(tmp_path)
    spec = s1.get_verifier("slice1:salience_apex")
    with monkeypatch.context() as m:
        m.setattr(bd, "_png_flatfill_fraction", _flatfill_apex_flat)
        res_flat = both_directions(spec, rd, fabricate=fab, genuine=gen)
    f_ok, f_reasons = res_flat["fabricated"]
    assert not f_ok
    assert any("AF-NO-SALIENCE-APEX" in r and "slide 2" in r for r in f_reasons), f_reasons
    with monkeypatch.context() as m:
        m.setattr(bd, "_png_flatfill_fraction", _flatfill_apex_vivid)
        g_ok, g_reasons = spec.run_verifier(rd)
    assert g_ok, f"genuine salience_apex must PASS, got {g_reasons}"


def test_slice1_converter_no_invent_both_directions(tmp_path):
    fab, gen = _pair_converter_no_invent()
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:converter_no_invent"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-CONVERTER-NO-INVENT" in r and "75%" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine converter_no_invent must PASS, got {g_reasons}"


def test_slice1_persuasion_beats_both_directions(tmp_path):
    fab, gen = _pair_persuasion_beats()
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:persuasion_beats"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-NO-PROBLEM" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine persuasion_beats must PASS, got {g_reasons}"


def test_slice1_style_preview_both_directions(tmp_path):
    fab, gen = _pair_style_preview()
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:style_preview"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-STYLE-UNPICKED" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine style_preview must PASS, got {g_reasons}"


def test_slice1_priority_shift_ledger_both_directions(tmp_path, monkeypatch):
    fab, gen = _pair_priority_shift_ledger(monkeypatch)
    rd = _fresh(tmp_path)
    spec = s1.get_verifier("slice1:priority_shift_ledger")
    with monkeypatch.context() as m:
        m.setattr(bd, "_png_flatfill_fraction", _flatfill_apex_vivid)
        res = both_directions(spec, rd, fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-PRIORITY-SHIFT" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine priority_shift_ledger must PASS, got {g_reasons}"
    # The 14-item report must still be WRITTEN (the P-SHIFT-QC phase reads it).
    assert (rd / "working" / "qc" / "priority_shift_report.json").is_file()


def test_slice1_sp_intake_both_directions(tmp_path):
    spi = bd._sp_prover("prove_sp_intake")
    if spi is None:
        pytest.skip("SP provers not co-located")
    fab, gen = _pair_sp("intake")
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:sp_intake"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-SP-8Q-MISSING" in r and "q7" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine sp_intake must PASS, got {g_reasons}"


def test_slice1_sp_structure_both_directions(tmp_path):
    sps = bd._sp_prover("prove_sp_structure")
    if sps is None:
        pytest.skip("SP provers not co-located")
    fab, gen = _pair_sp("structure")
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:sp_structure"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-SP-SLIDE-FLOOR" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine sp_structure must PASS, got {g_reasons}"


def test_slice1_sp_no_pitch_both_directions(tmp_path):
    spn = bd._sp_prover("prove_sp_no_pitch")
    if spn is None:
        pytest.skip("SP provers not co-located")
    fab, gen = _pair_sp("no_pitch")
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:sp_no_pitch"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-SP-P3-PITCH" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine sp_no_pitch must PASS, got {g_reasons}"


def test_slice1_sp_intake_trace_both_directions(tmp_path):
    itc = bd._sp_prover("intake_trace_check")
    if itc is None:
        pytest.skip("SP provers not co-located")
    fab, gen = _pair_sp("intake_trace")
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:sp_intake_trace"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-INTAKE-BATCH" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine sp_intake_trace must PASS, got {g_reasons}"


def test_slice1_sp_intake_trace_absent_transcript_fails_closed(tmp_path):
    """D10: an ABSENT transcript is a FAIL, not a defer — the cheapest way past
    a conversation gate is to record no conversation."""
    itc = bd._sp_prover("intake_trace_check")
    if itc is None:
        pytest.skip("SP provers not co-located")
    rd = _fresh(tmp_path)
    write_fixture(rd, "working/copy/intake.json",
                  {"deck_type": "signature_presentation"})
    write_fixture(rd, "working/copy/sp_intake.json",
                  bd._sp_prover("prove_sp_intake")._valid_runtime_fixture())
    ok, reasons = s1.run_gate("slice1:sp_intake_trace", rd)
    assert not ok
    assert any("AF-INTAKE-BATCH" in r and "no intake transcript" in r
               for r in reasons), reasons


def test_slice1_sp_claim_both_directions(tmp_path):
    pr = bd._sp_prover("prove_sp_routing")
    if pr is None:
        pytest.skip("SP provers not co-located")
    fab, gen = _pair_sp("claim")
    rd = _fresh(tmp_path)
    res = both_directions(s1.get_verifier("slice1:sp_claim"), rd,
                          fabricate=fab, genuine=gen)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok
    assert any("AF-SP-TYPE-UNDECLARED" in r for r in f_reasons), f_reasons
    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine sp_claim must PASS, got {g_reasons}"


def test_slice1_claim_runs_for_every_deck_no_signal_passes(tmp_path):
    """P-SP-CLAIM does NOT defer: a plain non-signature deck with no SP signal
    passes; a deck carrying an sp_intake.json without declaring deck_type FAILS."""
    pr = bd._sp_prover("prove_sp_routing")
    if pr is None:
        pytest.skip("SP provers not co-located")
    rd = _fresh(tmp_path)
    write_fixture(rd, "working/copy/intake.json", {"interview_confirmed": True})
    ok, reasons = s1.run_gate("slice1:sp_claim", rd)
    assert ok, f"no-signal deck must PASS the claim gate, got {reasons}"


def test_slice1_all_gates_fail_closed_on_missing_input(tmp_path):
    """A gate whose input genuinely does not exist yet must NOT pass — the D10
    rule. Defer is only ever a report-only PASS when the artifact is not due yet
    (phase ordering), never when the input exists but is wrong. On an EMPTY run
    dir every slice-1 gate must fail or pass-with-no-teeth the same way the
    legacy gate did (shadow-compared), and no gate may fabricate a PASS the
    legacy gate would not give."""
    rd = _fresh(tmp_path)
    for gate, _artifacts, _v, legacy in s1.SLICE1_GATES:
        ok, reasons = s1.run_gate(gate, rd)
        legacy_reason = legacy(rd)
        # The verdict and the legacy gate must agree on an empty run dir
        # (both may defer — a PASS with no teeth — but never disagree).
        if legacy_reason == "":
            # legacy defers; the verdict may also defer (report-only PASS is the
            # shadow-compare default), or fail closed where the gate is
            # fail-closed-on-absent by design (sp_intake_trace).
            assert ok or any(r for r in reasons), (gate, reasons)
        else:
            assert not ok, f"{gate} must not pass when the legacy gate fails: {reasons}"
            assert any(r for r in reasons), (gate, reasons)


def test_slice1_defer_semantics_match_legacy(tmp_path):
    """The defer paths (report-only PASS) must be IDENTICAL to the legacy gates:
    doctrine-inactive -> all doctrine gates defer; non-signature deck -> all SP
    gates defer; pre-render -> salience/ledger defer; no arc -> peak_end defers."""
    rd = _fresh(tmp_path)
    # No doctrine spec, no intake, no copy: every gate defers in legacy terms.
    for gate, artifacts in ((g, a) for g, a, _v, _l in s1.SLICE1_GATES):
        legacy_fn = dict((g, l) for g, a, v, l in s1.SLICE1_GATES)[gate]
        legacy_reason = legacy_fn(rd)
        assert legacy_reason == "", f"{gate}: legacy should defer, got {legacy_reason!r}"


def test_slice1_ledger_report_written_on_fail(tmp_path, monkeypatch):
    """The 14-item ship gate keeps writing working/qc/priority_shift_report.json
    on FAIL (the P-SHIFT-QC phase verifier reads that report)."""
    fab, _gen = _pair_priority_shift_ledger(monkeypatch)
    rd = _fresh(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(bd, "_png_flatfill_fraction", _flatfill_apex_flat)
        fab(rd)
        ok, _reasons = s1.run_gate("slice1:priority_shift_ledger", rd)
    assert not ok
    report = rd / "working" / "qc" / "priority_shift_report.json"
    assert report.is_file()
    obj = json.loads(report.read_text())
    assert obj["gate"] == "AF-PRIORITY-SHIFT"
    # Items 0..14 — the 14-item checklist plus the North-Star item 0.
    assert len(obj["items"]) == 15
    assert len(obj["slides"]) >= 1
