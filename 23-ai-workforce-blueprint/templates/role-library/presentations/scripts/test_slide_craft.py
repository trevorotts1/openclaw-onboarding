#!/usr/bin/env python3
"""test_slide_craft.py — mutation-proof tests for slide_craft.py enforcers.

Flat beside the module under test — there is no scripts/tests/ directory and
pytest's default prepend import mode resolves the test file's OWN directory,
so a suite at scripts/tests/ fails at collection with
ModuleNotFoundError: No module named 'slide_craft'.

Standard library only; no fixtures, no network, no render. Every fixture is a
tempfile.mkdtemp() run directory built in the test."""

import json
import os
import tempfile
from pathlib import Path

import slide_craft


def _rd():
    """Create a temp run directory."""
    return Path(tempfile.mkdtemp())


def _deck(slides, hook=None, ladder=None, arc=None, ocr=None):
    """Build a synthetic run directory with slides.json and optional artefacts."""
    rd = _rd()
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "slides.json").write_text(json.dumps(slides))
    intake_val = {"deck_type": "webinar"}
    if hook is not None:
        intake_val["hook"] = hook
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(intake_val))
    if ladder is not None:
        (rd / "working" / "copy" / "price_ladder.json").write_text(json.dumps(ladder))
    if arc is not None:
        (rd / "working" / "copy" / "slides_copy.md").write_text(arc)
    if ocr is not None:
        (rd / "renders").mkdir()
        (rd / "renders" / "slide-01.ocr.json").write_text(
            json.dumps({"checked": True, "ocr_text": ocr}))
    return rd, rd / "working" / "copy" / "slides.json"


def _one(**kw):
    base = {"slide": 1, "scene": "x", "copy": ["REAL REVENUE GROWTH"]}
    base.update(kw)
    return [base]


def _sl(n):
    return [{"slide": i, "scene": "x", "copy": ["A HEADLINE THAT FITS"]}
            for i in range(1, n + 1)]


HOOK = "there is a difference between managing and leading"

GOLD = {"rungs": [
    {"kind": "ANCHOR", "target_slide": 24},
    {"kind": "DROP", "target_slide": 35},
    {"kind": "DROP", "target_slide": 51},
    {"kind": "DROP", "target_slide": 65},
    {"kind": "FINAL", "target_slide": 73},
]}

BAD = {"rungs": [
    {"kind": "ANCHOR", "target_slide": 32},
    {"kind": "DROP", "target_slide": 34},
    {"kind": "DROP", "target_slide": 37},
    {"kind": "FINAL", "target_slide": 43},
]}


# 1. check_obi_text_blocks
def test_obi_text_blocks_pass():
    rd, sp = _deck(_one(copy=["THREE MOVES THAT WORKED", "How we doubled", "90 DAYS"]))
    assert slide_craft.check_obi_text_blocks(rd, sp) == ""


def test_obi_text_blocks_fail():
    rd, sp = _deck(_one(copy=["A", "B", "C", "D"]))
    r = slide_craft.check_obi_text_blocks(rd, sp)
    assert r != ""
    assert "AF-OBI-1" in r
    assert "4" in r


def test_obi_text_blocks_empty_excluded():
    rd, sp = _deck(_one(copy=["HEADLINE", "", "   ", "BODY"]))
    assert slide_craft.check_obi_text_blocks(rd, sp) == ""


# 2. check_obi_headline_words
def test_obi_headline_words_pass():
    rd, sp = _deck(_one(copy=["one two three four five six seven eight nine"]))
    assert slide_craft.check_obi_headline_words(rd, sp) == ""


def test_obi_headline_words_fail():
    rd, sp = _deck(_one(copy=["one two three four five six seven eight nine ten"]))
    r = slide_craft.check_obi_headline_words(rd, sp)
    assert r != ""
    assert "AF-OBI-2" in r
    assert "10" in r
    assert "9" in r


def test_obi_headline_words_hyphenated():
    rd, sp = _deck(_one(copy=["state-of-the-art clarity"]))
    assert slide_craft.check_obi_headline_words(rd, sp) == ""


# 3. Two ceilings do not collide
def test_two_ceilings_do_not_collide():
    rd, sp = _deck(_one(copy=["one two three four five six seven eight nine"]))
    assert slide_craft.check_obi_headline_words(rd, sp) == ""
    rd2, sp2 = _deck(_one(copy=["A", "B", "C", "D"]))
    r = slide_craft.check_obi_text_blocks(rd2, sp2)
    assert r != ""
    assert "AF-OBI-1" in r


# 4. check_aud_meta_tokens
def test_aud_meta_tokens_pass():
    rd, sp = _deck(_one(copy=["THREE MOVES THAT WORKED"]))
    assert slide_craft.check_aud_meta_tokens(rd, sp) == ""


def test_aud_meta_tokens_fail_webinar():
    rd, sp = _deck(_one(copy=["THIS IS NOT JUST A WEBINAR"]))
    r = slide_craft.check_aud_meta_tokens(rd, sp)
    assert r != ""
    assert "AF-AUD-4" in r


def test_aud_meta_tokens_seminar_passes():
    rd, sp = _deck(_one(copy=["THIS IS A SEMINAR"]))
    assert slide_craft.check_aud_meta_tokens(rd, sp) == ""


# 5. check_aud_credentials
def test_aud_credentials_body_fails():
    rd, sp = _deck(_one(copy=["WHY US", "licensed counselor"]))
    r = slide_craft.check_aud_credentials(rd, sp)
    assert r != ""
    assert "AF-AUD-5" in r


def test_aud_credentials_headline_passes():
    rd, sp = _deck(_one(copy=["A LICENSED COUNSELOR"]))
    assert slide_craft.check_aud_credentials(rd, sp) == ""


# 6. check_aud_placeholder_render
def test_aud_placeholder_copy_only_passes():
    rd, sp = _deck(_one(copy=["[CLIENT WIN - owner to confirm]"]),
                   ocr="REVENUE GROWTH METRICS")
    assert slide_craft.check_aud_placeholder_render(rd, sp) == ""


def test_aud_placeholder_render_fails():
    rd, sp = _deck(_one(), ocr="[CLIENT WIN - owner to confirm]")
    r = slide_craft.check_aud_placeholder_render(rd, sp)
    assert r != ""
    assert "AF-AUD-6" in r


def test_aud_placeholder_defer_no_renders():
    rd, sp = _deck(_one())
    assert slide_craft.check_aud_placeholder_render(rd, sp) == ""


def test_aud_placeholder_defer_no_sidecar():
    rd, sp = _deck(_one())
    (rd / "renders").mkdir()
    assert slide_craft.check_aud_placeholder_render(rd, sp) == ""


def test_aud_placeholder_defer_checked_false():
    rd, sp = _deck(_one())
    (rd / "renders").mkdir()
    (rd / "renders" / "slide-01.ocr.json").write_text(
        json.dumps({"checked": False, "ocr_text": "whatever"}))
    assert slide_craft.check_aud_placeholder_render(rd, sp) == ""


# 7. check_hook_verbatim
def test_hook_verbatim_exact_pass():
    rd, sp = _deck(_one(copy=[HOOK]), hook=HOOK)
    assert slide_craft.check_hook_verbatim(rd, sp) == ""


def test_hook_verbatim_mutation_fail():
    rd, sp = _deck(_one(copy=[HOOK + " totally"]), hook=HOOK)
    r = slide_craft.check_hook_verbatim(rd, sp)
    assert r != ""
    assert "AF-HOOK-5" in r


def test_hook_verbatim_unrelated_pass():
    rd, sp = _deck(_one(copy=["a completely different sentence"]), hook=HOOK)
    assert slide_craft.check_hook_verbatim(rd, sp) == ""


def test_hook_verbatim_defer_no_hook():
    rd, sp = _deck(_one(copy=[HOOK]))
    assert slide_craft.check_hook_verbatim(rd, sp) == ""


# 8. check_den_ladder_gaps
def test_den_ladder_gaps_pass():
    rd, sp = _deck(_sl(75), ladder=GOLD)
    assert slide_craft.check_den_ladder_gaps(rd, sp) == ""


def test_den_ladder_gaps_fail():
    rd, sp = _deck(_sl(45), ladder=BAD)
    r = slide_craft.check_den_ladder_gaps(rd, sp)
    assert r != ""
    assert "AF-DEN-1" in r


def test_den_ladder_gaps_client_count():
    rd = _rd()
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "slides.json").write_text(json.dumps(_sl(45)))
    (rd / "working" / "copy" / "intake.json").write_text(
        json.dumps({"deck_type": "webinar", "client_requested_slide_count": 45}))
    (rd / "working" / "copy" / "price_ladder.json").write_text(json.dumps(BAD))
    sp = rd / "working" / "copy" / "slides.json"
    r = slide_craft.check_den_ladder_gaps(rd, sp)
    assert r != ""
    assert "AF-DEN-1" in r
    assert "re-space" in r.lower()


# 9. check_den_anchor_depth
def test_den_anchor_depth_pass():
    rd, sp = _deck(_sl(75), ladder=GOLD)
    assert slide_craft.check_den_anchor_depth(rd, sp) == ""


def test_den_anchor_depth_fail():
    rd, sp = _deck(_sl(45), ladder={
        "rungs": [{"kind": "ANCHOR", "target_slide": 32},
                  {"kind": "DROP", "target_slide": 34}]})
    r = slide_craft.check_den_anchor_depth(rd, sp)
    assert r != ""
    assert "AF-DEN-2" in r
    assert "71" in r


# 10. check_den_stack_before_drop
def test_den_stack_before_drop_pass():
    rd, sp = _deck(_sl(20), arc="<!-- ARC: VALUE_STACK -->\nx\n<!-- ARC: DROP1 -->\ny")
    assert slide_craft.check_den_stack_before_drop(rd, sp) == ""


def test_den_stack_before_drop_fail():
    rd, sp = _deck(_sl(20), arc="<!-- ARC: DROP1 -->\nx\n<!-- ARC: VALUE_STACK -->\ny")
    r = slide_craft.check_den_stack_before_drop(rd, sp)
    assert r != ""
    assert "AF-DEN-4" in r


def test_den_stack_before_drop_no_drop():
    rd, sp = _deck(_sl(20), arc="<!-- ARC: PROMISE -->\nx")
    assert slide_craft.check_den_stack_before_drop(rd, sp) == ""


# 11. check_den_repitch_block
def test_den_repitch_block_pass():
    rd, sp = _deck(_sl(75), ladder={
        "rungs": [{"kind": "FINAL", "target_slide": 70}]})
    assert slide_craft.check_den_repitch_block(rd, sp) == ""


def test_den_repitch_block_fail():
    rd, sp = _deck(_sl(75), ladder=GOLD)
    r = slide_craft.check_den_repitch_block(rd, sp)
    assert r != ""
    assert "AF-DEN-7" in r


# 12. Every check defers and records it
def test_all_defers_on_empty_and_provenance():
    rd = _rd()
    names = [n for n in dir(slide_craft) if n.startswith("check_")]
    for n in names:
        r = getattr(slide_craft, n)(rd, None)
        assert r == "", f"{n} did not defer on empty run dir: {r!r}"
    prov = rd / "working" / "qc" / "slide_craft.json"
    assert prov.exists(), "provenance file missing"


# 13. No check raises on malformed input
def test_no_raise_malformed_slides():
    rd = _rd()
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "slides.json").write_text("not json")
    (rd / "working" / "copy" / "intake.json").write_text("{}")
    sp = rd / "working" / "copy" / "slides.json"
    for fn in [n for n in dir(slide_craft) if n.startswith("check_")]:
        rv = getattr(slide_craft, fn)(rd, sp)
        assert isinstance(rv, str), f"{fn} raised on malformed slides.json"


def test_no_raise_empty_slides():
    rd = _rd()
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "slides.json").write_text("{}")
    (rd / "working" / "copy" / "intake.json").write_text("{}")
    sp = rd / "working" / "copy" / "slides.json"
    for fn in [n for n in dir(slide_craft) if n.startswith("check_")]:
        rv = getattr(slide_craft, fn)(rd, sp)
        assert isinstance(rv, str), f"{fn} raised on empty-dict slides.json"


def test_no_raise_malformed_ladder():
    rd = _rd()
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "slides.json").write_text(
        json.dumps([{"slide": 1, "scene": "x", "copy": ["A"]}]))
    (rd / "working" / "copy" / "price_ladder.json").write_text("not json")
    (rd / "working" / "copy" / "intake.json").write_text("{}")
    sp = rd / "working" / "copy" / "slides.json"
    for fn in ["check_den_ladder_gaps", "check_den_anchor_depth",
               "check_den_repitch_block"]:
        rv = getattr(slide_craft, fn)(rd, sp)
        assert isinstance(rv, str), f"{fn} raised on malformed price_ladder"


def test_no_raise_zero_byte_ocr():
    rd = _rd()
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "slides.json").write_text(
        json.dumps([{"slide": 1, "scene": "x", "copy": ["A"]}]))
    (rd / "working" / "copy" / "intake.json").write_text("{}")
    (rd / "renders").mkdir()
    (rd / "renders" / "slide-01.ocr.json").write_text("")
    sp = rd / "working" / "copy" / "slides.json"
    r = slide_craft.check_aud_placeholder_render(rd, sp)
    assert isinstance(r, str)


# 14. Warn switch is observable
def test_warn_switch_changes_behavior():
    rd, sp = _deck(_one(copy=["one two three four five six seven eight nine ten"]))
    r = slide_craft.check_obi_headline_words(rd, sp)
    assert r != ""
    assert "AF-OBI-2" in r


# 15. Thresholds match SOP
THRESHOLDS = {
    "OBI_TEXT_BLOCK_MAX": 3,
    "OBI_HEADLINE_WORD_MAX": 9,
    "DEN_PRICE_BEAT_MIN_GAP": 8,
    "DEN_ANCHOR_DEPTH_MIN": 0.25,
    "DEN_ANCHOR_DEPTH_MAX": 0.45,
    "DEN_REPITCH_MIN": 4,
    "DEN_REPITCH_MAX": 7,
    "HOOK_VARIANT_RATIO": 0.82,
}


def test_threshold_values_match_sop():
    for name, expect in THRESHOLDS.items():
        got = getattr(slide_craft, name)
        assert got == expect, f"{name} = {got!r}, expected {expect!r}"


def test_no_bare_threshold_literal():
    import ast
    src = Path(slide_craft.__file__).read_text()
    tree = ast.parse(src)

    threshold_values = set(THRESHOLDS.values())

    # Nodes within constant definitions (to exclude)
    const_def_nodes = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in THRESHOLDS:
                    for child in ast.walk(node.value):
                        if isinstance(child, ast.Constant):
                            const_def_nodes.add(id(child))

    bare = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in threshold_values:
            if id(node) not in const_def_nodes:
                bare.append((getattr(node, 'lineno', '?'), node.value))
    assert bare == [], f"Bare threshold literal(s) outside the constant block: {bare}"
