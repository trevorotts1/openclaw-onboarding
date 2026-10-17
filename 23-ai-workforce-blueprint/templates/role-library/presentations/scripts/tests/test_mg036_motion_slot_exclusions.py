#!/usr/bin/env python3
"""test_mg036_motion_slot_exclusions.py -- Item 34 (FIX-PLAN) R5: the
exclusion half of spec T4, for the R3 slot-exclusion enforcement.

The mg036 suite (test_mg036_motion_integration.py, UNMODIFIED) pins the
slot rule's positive form and the cap. This sibling pins the doctrine
exclusions readiness R3 builds INSIDE build_deck.py's single validator:
a motion declaration on a doctrine-barred slide degrades with its own
named code instead of embedding, the slot letter stays on the entry
(the slide IS a nominal slot; it is doctrine-barred, which is a
different fact from MOTION_SLOT_INVALID), and the exclusion is logged
in the motion record entry. The codes (presentation_job/motion.py):
MOTION_SLOT_EXCLUDED_HOOK, MOTION_SLOT_EXCLUDED_PRICE,
MOTION_SLOT_EXCLUDED_OFFER_CTA, MOTION_SLOT_EXCLUDED_PROOF, all
per-slide judgments inside the validator. No adjacency code exists
in the ported delta; see the X5 note.

Cases (build/B34-TESTPLAN.md Section 6, reconciled at assembly prep
with the contribution lineage's suite of the same name; the union is
recorded in build/B34-ITEM34.md):
  X1 hook slide 1 (arc_allocation hook flag, read through the same
     _load_slide_arc_tags loader plan_motion_media already calls);
  X2 price-carrying divider, in both canonical price forms: a currency
     amount in the approved copy, and the FINAL_PRICE literal;
  X3 offer/CTA arc slide (divider-shaped slide inside the offer arc);
  X4 proof/guarantee slide (guarantee sentence in the approved copy);
  X5 adjacency: PINNED AS LANDED BEHAVIOR, with the conflict named.
     Spec 3.2 bars two consecutive filled slots, but the unmodified
     mg036 cap case (test_plan_enforces_b14_cap) asserts
     set(motion_media) == {1, 2}: adjacent slides 1 and 2 are its two
     kept pieces, and that suite must pass UNMODIFIED. The two cannot
     both hold in plan_motion_media. This file therefore pins the
     landed behavior (both validate) and the stream record carries
     the doctrine conflict for a coordinator ruling. An earlier draft
     of this file asserted the spec-form degrade; it was replaced at
     assembly prep for exactly this reason, recorded, not silently.

Fixture builders are imported from the mg036 suite (house
sibling-import style), so staged packages are byte-for-byte the
governed fixture shape. Where a case changes a slide's approved copy,
the package storyboard is made to cover that copy, so the copy
inventory authenticates and ONLY the exclusion can degrade the slide
(check-order independent). Pre-change, X1 to X4 VALIDATE (the mg036
happy-path and slot-B tests are the standing proof), so every
assertion in them fails on the pre-R3 tree for exactly the missing
enforcement.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import pytest  # noqa: E402

import build_deck  # noqa: E402
from presentation_job import motion as pm  # noqa: E402

from test_mg036_motion_integration import (  # noqa: E402
    COPY_LINES,
    SPEECH,
    _deck_parts,
    _outcome_for,
    _rendered_list,
    _slides_of,
    build_run,
    media,
    needs_media,
)

PRICE_COPY = "Yours today for $497"
GUARANTEE_COPY = "Backed by our 90-day guarantee"


def _write_arc(run_dir: Path, slides: list) -> None:
    (run_dir / "working" / "copy" / "arc_allocation.json").write_text(
        json.dumps({"slides": slides}), encoding="utf-8")


def _set_copy(run_dir: Path, slide_no: int, copy_lines: list) -> list:
    slides = _slides_of(run_dir)
    for slide in slides:
        if slide["slide"] == slide_no:
            slide["copy"] = list(copy_lines)
    (run_dir / "working" / "copy" / "slides.json").write_text(
        json.dumps(slides), encoding="utf-8")
    return slides


def _assert_excluded(record, motion_media, run_dir, slide_no, code,
                     slot, cause_word):
    """The shared exclusion contract (B34-TESTPLAN Section 6)."""
    entry = _outcome_for(record, slide_no)
    assert entry["status"] == "degraded", entry
    assert entry["reason_code"] == code, entry
    assert entry["reason_code"] != pm.MOTION_SLOT_INVALID, entry
    assert entry["slot"] == slot, entry
    assert "_embed" not in entry, entry
    assert slide_no not in motion_media, motion_media
    assert cause_word in (entry.get("detail") or "").lower(), entry
    on_disk = json.loads(
        (run_dir / "working" / "checkpoints" / "motion.json")
        .read_text(encoding="utf-8"))
    disk_entry = _outcome_for(on_disk, slide_no)
    assert disk_entry["reason_code"] == code, disk_entry
    assert cause_word in (disk_entry.get("detail") or "").lower(), \
        disk_entry


@needs_media
def test_x1_hook_slide_1_degrades_never_embeds(media, tmp_path):
    run_dir = build_run(tmp_path, media, motion_slides=(1,))
    _write_arc(run_dir, [{"slide": 1, "hook": True}])
    record, motion_media = build_deck.plan_motion_media(
        run_dir, _slides_of(run_dir))
    _assert_excluded(record, motion_media, run_dir, 1,
                     pm.MOTION_SLOT_EXCLUDED_HOOK, "A", "hook")
    assert motion_media == {}

    # Direct-validate arm: the same judgment inside the one validator,
    # with the arc blob the plan path itself loads.
    blob = build_deck._load_slide_arc_tags(run_dir)[1]
    assert "hook" in blob
    outcome = build_deck.validate_motion_slide_artifacts(
        run_dir, 1, _slides_of(run_dir)[0]["media"],
        election=pm.election_for_run(run_dir),
        arc_tag_blob=blob, copy_lines=list(COPY_LINES))
    assert outcome["status"] == "degraded", outcome
    assert outcome["reason_code"] == pm.MOTION_SLOT_EXCLUDED_HOOK, \
        outcome
    assert "_embed" not in outcome, outcome

    # Assemble arm: the plan's map carries nothing for the slide, so
    # the delivered deck carries no MOTION media part. (The rendered
    # slide stills are ppt/media parts too, by deck anatomy; the
    # landed mg036 suite filters to the motion extensions for
    # exactly this reason, and this arm does the same.)
    pytest.importorskip("pptx")
    deck = tmp_path / "deck.pptx"
    build_deck.assemble_pptx(_rendered_list(run_dir), deck,
                             speech_chunks=SPEECH,
                             motion_media=motion_media)
    parts = _deck_parts(deck)
    media_parts = [n for n in parts if n.startswith("ppt/media/")
                   and n.lower().endswith((".mp4", ".mov", ".m4v",
                                           ".webm"))]
    assert media_parts == [], media_parts


@needs_media
def test_x2_price_carrying_divider_degrades(media, tmp_path):
    # The package storyboard covers the price copy, so the copy
    # inventory authenticates: only the exclusion can degrade it.
    run_dir = build_run(
        tmp_path, media, motion_slides=(3,), arc_dividers=(3,),
        package_overrides={"package": {
            "storyboard_strings": ["Section Three", PRICE_COPY]}})
    slides = _set_copy(run_dir, 3, ["Section Three", PRICE_COPY])
    record, motion_media = build_deck.plan_motion_media(run_dir, slides)
    _assert_excluded(record, motion_media, run_dir, 3,
                     pm.MOTION_SLOT_EXCLUDED_PRICE, "B", "price")

    outcome = build_deck.validate_motion_slide_artifacts(
        run_dir, 3, slides[2]["media"],
        election=pm.election_for_run(run_dir),
        arc_tag_blob="section divider",
        copy_lines=["Section Three", PRICE_COPY])
    assert outcome["status"] == "degraded", outcome
    assert outcome["reason_code"] == pm.MOTION_SLOT_EXCLUDED_PRICE, \
        outcome


@needs_media
def test_x2_final_price_literal_divider_degrades(media, tmp_path):
    run_dir = build_run(
        tmp_path, media, motion_slides=(3,), arc_dividers=(3,),
        package_overrides={"package": {
            "storyboard_strings": ["Section Three", "FINAL_PRICE"]}})
    slides = _set_copy(run_dir, 3, ["Section Three", "FINAL_PRICE"])
    record, motion_media = build_deck.plan_motion_media(run_dir, slides)
    _assert_excluded(record, motion_media, run_dir, 3,
                     pm.MOTION_SLOT_EXCLUDED_PRICE, "B", "price")

    outcome = build_deck.validate_motion_slide_artifacts(
        run_dir, 3, slides[2]["media"],
        election=pm.election_for_run(run_dir),
        arc_tag_blob="section divider",
        copy_lines=["Section Three", "FINAL_PRICE"])
    assert outcome["status"] == "degraded", outcome
    assert outcome["reason_code"] == pm.MOTION_SLOT_EXCLUDED_PRICE, \
        outcome


@needs_media
def test_x3_offer_arc_divider_degrades(media, tmp_path):
    run_dir = build_run(
        tmp_path, media, motion_slides=(3,),
        package_overrides={"package": {
            "storyboard_strings": ["Slide 3 headline",
                                   "Slide 3 support"]}})
    _write_arc(run_dir, [{"slide": 3, "arc_section": "offer",
                          "tag": "divider"}])
    record, motion_media = build_deck.plan_motion_media(
        run_dir, _slides_of(run_dir))
    entry = _outcome_for(record, 3)
    assert entry["status"] == "degraded", entry
    assert entry["reason_code"] == pm.MOTION_SLOT_EXCLUDED_OFFER_CTA, \
        entry
    assert entry["slot"] == "B", entry
    assert 3 not in motion_media, motion_media
    detail = (entry.get("detail") or "").lower()
    assert "offer" in detail or "cta" in detail, entry


@needs_media
def test_x4_guarantee_copy_divider_degrades(media, tmp_path):
    run_dir = build_run(
        tmp_path, media, motion_slides=(3,), arc_dividers=(3,),
        package_overrides={"package": {
            "storyboard_strings": ["Section Three", GUARANTEE_COPY]}})
    slides = _set_copy(run_dir, 3, ["Section Three", GUARANTEE_COPY])
    record, motion_media = build_deck.plan_motion_media(run_dir, slides)
    _assert_excluded(record, motion_media, run_dir, 3,
                     pm.MOTION_SLOT_EXCLUDED_PROOF, "B", "guarantee")


@needs_media
def test_x5_adjacency_follows_the_landed_cap_behavior(media, tmp_path):
    """The recorded conflict, pinned as landed behavior: B14 Section
    3.2 bars two consecutive filled slots, but the unmodified mg036
    cap case keeps adjacent slides 1 and 2 as its two pieces
    (set(motion_media) == {1, 2}). Until a coordinator ruling
    reconciles them, the merged suite governs and this pair
    validates. If this test ever fails because an adjacency degrade
    landed in plan_motion_media, the mg036 cap case must have been
    reconciled in the same change."""
    all_copy = list(COPY_LINES) + [
        "Slide 2 headline", "Slide 2 support",
        "Slide 3 headline", "Slide 3 support"]
    run_dir = build_run(
        tmp_path, media, motion_slides=(1, 2), arc_dividers=(2,),
        package_overrides={"package": {
            "storyboard_strings": all_copy,
            "essential_text": list(COPY_LINES)}})
    record, motion_media = build_deck.plan_motion_media(
        run_dir, _slides_of(run_dir))
    assert set(motion_media) == {1, 2}
    assert _outcome_for(record, 1)["status"] == "validated"
    assert _outcome_for(record, 2)["status"] == "validated"
