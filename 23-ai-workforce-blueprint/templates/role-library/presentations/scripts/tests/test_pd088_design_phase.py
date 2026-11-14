#!/usr/bin/env python3
"""test_pd088_design_phase.py — PD-088 (Severe, lane FL17).

The typography step proved a research BRIEF, not typography work: the PF-DESIGN
registry entry was ``_verify_text_artifact("working/research/design-brief-*.md",
50)``, so 50 characters of art direction flipped the typography step to ``done``
with no type system, no design system and no declared weights behind it. The
step now passes only when all three artifacts exist and are valid:

  1. the design brief, >= 200 characters of text;
  2. ``working/typography/type_layout_system.md``, whose declared tokens pass
     ``build_deck.check_font_floor`` (the deterministic numeric floor);
  3. ``working/typography/design_system.json``, an object carrying a non-empty
     ``weight_ladder`` and a non-empty ``archetype_plan``.

Rows (01-BUILD-SPEC.md, section PD-088):

  A1  research brief alone            -> fails, naming type_layout_system.md
      all three present and valid     -> passes
      ``min_body_pt: 12``             -> fails

No network, no model call, no live service.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import phase_verifiers as pv  # noqa: E402

BRIEF_REL = "working/research/design-brief-01.md"
LAYOUT_REL = "working/typography/type_layout_system.md"
SYSTEM_REL = "working/typography/design_system.json"

# Comfortably over the 200-character brief floor: these rows are about WHICH
# artifacts the step demands, not about the floor's exact byte.
BRIEF = (
    "# Design brief\n\n"
    "Audience: owner-operators scaling past their first two hires. Palette: "
    "deep navy ground with warm gold accents, accent held to one word per slide. "
    "Type: one geometric sans family across four weights, hero headlines set "
    "large and loose. Photography: candid, right-third placement, one subject. "
    "Every slide carries one idea and one call to look further.\n"
)

GOOD_TOKENS = (
    "min_body_pt: 24\n"
    "type_scale_steps: 5\n"
    "min_contrast_ratio: 7.0\n"
)

GOOD_SYSTEM = {
    "weight_ladder": {
        "hero": {"font": "Montserrat Black", "role": "hero headlines"},
        "subhead": {"font": "Montserrat ExtraBold", "role": "sub-heads"},
        "label": {"font": "Montserrat Bold", "role": "kicker labels"},
    },
    "archetype_plan": {
        "1": "pure-type hook",
        "2": "teach-one-big-idea",
        "3": "proof stack",
    },
}


def _run_dir(tmp_path: Path, *, brief: str | None = BRIEF,
             tokens: str | None = GOOD_TOKENS,
             system: object = GOOD_SYSTEM) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    for rel, body in ((BRIEF_REL, brief), (LAYOUT_REL, tokens)):
        if body is None:
            continue
        p = run_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    if system is not None:
        p = run_dir / SYSTEM_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(system), encoding="utf-8")
    return run_dir


def test_the_registry_entry_is_the_design_phase_check():
    """The PF-DESIGN step is the new function, not the brief-only factory."""
    assert pv.PHASE_VERIFIERS["PF-DESIGN"] is pv._verify_design_phase


def test_a1_research_brief_alone_fails_naming_the_type_layout_system(tmp_path):
    """A1: a brief with no type system does NOT prove the typography step."""
    run_dir = _run_dir(tmp_path, tokens=None, system=None)
    ok, reasons = pv.PHASE_VERIFIERS["PF-DESIGN"](run_dir)
    assert not ok, "a research brief alone must not pass the typography step"
    assert any("type_layout_system.md" in r for r in reasons), (
        f"the failure must name the missing type system, got reasons={reasons}")
    assert any("design_system.json" in r for r in reasons), (
        f"the failure must name the missing design system, got reasons={reasons}")


def test_a1_all_three_present_and_valid_passes(tmp_path):
    """A1: brief + passing type tokens + design system -> the step passes."""
    run_dir = _run_dir(tmp_path)
    ok, reasons = pv.PHASE_VERIFIERS["PF-DESIGN"](run_dir)
    assert ok, f"all three artifacts present and valid must pass, got reasons={reasons}"


def test_a1_sub_floor_min_body_pt_fails(tmp_path):
    """A1: `min_body_pt: 12` is a declared violation of the font floor."""
    run_dir = _run_dir(tmp_path, tokens=GOOD_TOKENS.replace("min_body_pt: 24",
                                                            "min_body_pt: 12"))
    ok, reasons = pv.PHASE_VERIFIERS["PF-DESIGN"](run_dir)
    assert not ok, "a sub-floor body size must fail the typography step"
    assert any("min_body_pt" in r for r in reasons), (
        f"the failure must name the offending token, got reasons={reasons}")
