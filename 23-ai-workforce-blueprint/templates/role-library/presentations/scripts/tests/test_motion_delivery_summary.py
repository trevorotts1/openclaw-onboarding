#!/usr/bin/env python3
"""test_motion_delivery_summary.py -- FIX-PLAN Item 34 residual R4:
the one-line motion summary on the delivery path (B14 Section 5.4
tail).

B34-R4HUNT verified no counterpart exists on the base: no code read
the landed motion.json and formatted a one-line summary. What R4
builds is (a) presentation_job.motion.motion_summary_line, derived
from the LANDED record shape (election object; slides[] keyed by
slide number; statuses embedded / validated / degraded /
produced_late_not_embedded; MOTION_* values in reason_code; slot
letters derived through motion.slot_for_slide, never stored spec
vocabulary), and (b) the P8.15-MOTION verifier surfacing that line
as a PASS NOTE, the shape _verify_upsell_vsl_build uses for its
defer/waived PASS. Motion deliberately adds NO top-level deliverable:
nothing here touches DELIVERABLE_AUDIT_SPEC or the curated delivery
folder (the B34-R4HUNT binding constraint).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import pytest  # noqa: E402

from presentation_job import motion as pm  # noqa: E402
from test_mg036_motion_integration import media  # noqa: E402,F401


def _record(slides, elected=True):
    return {"election": {"field": "want_motion_graphics",
                         "value": "yes" if elected else "no",
                         "elected": elected,
                         "source": "intake_capture"},
            "slides": slides}


def test_summary_not_elected():
    assert pm.motion_summary_line(_record([], elected=False)) == \
        "Motion: not elected; deck complete on static slides"


def test_summary_all_embedded():
    rec = _record([
        {"slide": 1, "status": "embedded", "slot": "A"},
        {"slide": 9, "status": "embedded", "slot": "B"}])
    assert pm.motion_summary_line(rec) == \
        "Motion: 2 of 2 pieces embedded"


def test_summary_mixed_with_degraded_slot_b():
    rec = _record([
        {"slide": 1, "status": "embedded", "slot": "A"},
        {"slide": 9, "status": "degraded", "slot": "B",
         "reason_code": "MOTION_QC_FAILED"}])
    assert pm.motion_summary_line(rec) == (
        "Motion: 1 of 2 pieces embedded; slot B degraded "
        "(MOTION_QC_FAILED); deck complete on static slides")


def test_summary_derives_slot_letter_when_record_stores_none():
    # A slide degraded before the slot judgment carries no stored
    # slot; the letter is derived through slot_for_slide from the
    # slide number and the run's arc tags, as the seam derives it.
    rec = _record([
        {"slide": 1, "status": "embedded"},
        {"slide": 9, "status": "degraded",
         "reason_code": "MOTION_PACKAGE_MISSING"}])
    line = pm.motion_summary_line(rec, {9: "section divider"})
    assert "slot B degraded (MOTION_PACKAGE_MISSING)" in line, line
    rec_a = _record([
        {"slide": 1, "status": "degraded",
         "reason_code": "MOTION_SLOT_EXCLUDED_HOOK"}])
    assert pm.motion_summary_line(rec_a).startswith(
        "Motion: 0 of 1 pieces embedded; slot A degraded "
        "(MOTION_SLOT_EXCLUDED_HOOK)")


def test_summary_late_piece_wording():
    rec = _record([
        {"slide": 1, "status": "embedded", "slot": "A"},
        {"slide": 9, "status": "produced_late_not_embedded",
         "slot": "B"}])
    line = pm.motion_summary_line(rec)
    assert "slot B produced late, not embedded" in line, line
    assert line.endswith("deck complete on static slides")


def test_summary_elected_with_no_pieces():
    assert pm.motion_summary_line(_record([])) == (
        "Motion: 0 of 0 pieces embedded; deck complete on static "
        "slides")


# ---------------------------------------------------------------------------
# The verifier surface: the P8.15-MOTION PASS carries the line as a
# NOTE (the VSL PASS-with-NOTE shape).
# ---------------------------------------------------------------------------

def test_verifier_pass_carries_the_summary_note(media, tmp_path):
    pytest.importorskip("pptx")
    import build_deck
    import motion_phase
    import phase_verifiers
    from test_mg036_motion_integration import build_run, _slides_of
    run_dir = build_run(tmp_path, media)
    _r, motion_media = build_deck.plan_motion_media(
        run_dir, _slides_of(run_dir))
    deck = tmp_path / "deck.pptx"
    rendered = [{"slide": n,
                 "file": str(run_dir / "renders" / f"slide-{n:02d}.png")}
                for n in (1, 2, 3)]
    build_deck.assemble_pptx(rendered, deck, motion_media=motion_media)
    build_deck.finalize_motion_record(run_dir, deck)
    import shutil
    shutil.copy2(deck, run_dir / "fixture-FINAL.pptx")
    assert motion_phase.run(run_dir) == motion_phase.EXIT_OK
    ok, reasons = phase_verifiers.verify("P8.15-MOTION", run_dir)
    assert ok, reasons
    notes = [r for r in reasons if r.startswith("NOTE: P8.15-MOTION ")]
    assert len(notes) == 1, reasons
    assert notes[0] == ("NOTE: P8.15-MOTION Motion: 1 of 1 pieces "
                        "embedded"), notes
