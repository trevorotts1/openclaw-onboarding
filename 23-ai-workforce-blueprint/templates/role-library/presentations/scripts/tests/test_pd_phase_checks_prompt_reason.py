#!/usr/bin/env python3
"""test_pd_phase_checks_prompt_reason.py — PD-072 (Moderate, lane FL17).

``phase_verifiers._verify_prompt`` built each failure reason from
``d.get('detail', '')``. The deficiency record produced by
``build_deck.check_prompt_qc_deterministic`` has no ``detail`` key — its keys are
``code`` / ``severity`` / ``measured`` / ``required`` / ``intelligence`` /
``fix`` — so every reason reached the engine's regenerate order and the client's
pause message as ``AF-PROMPT-FLOOR slide-3: AF-P1 — `` with nothing after the
dash.

After the fix the reason is built from the record's own fields, so a too-short
prompt names the measured character count and the words to add.

Rows (PASS4-ENGINE.md, section PD-072 — A1):

  A1a  a stubbed too-short deficiency (``measured`` + ``fix``) -> the reason
       carries the measured character count and the ADD text
  A1b  the real measurer on a real too-short prompt file -> same, end to end

No network, no model call, no live service.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import phase_verifiers as pv  # noqa: E402

SHORT_PROMPT = "way too thin to be a real slide prompt"

# The real deficiency shape from build_deck._pdef — no "detail" key anywhere.
def _deficiency_record(text: str) -> dict:
    n = len(text)
    return {
        "pass": False,
        "slides": {
            3: {
                "char_count": n,
                "excellence": 0.01,
                "deficiencies": [
                    {
                        "code": "AF-P1",
                        "severity": "fatal",
                        "measured": f"{n} chars",
                        "required": "inside the rule 12 band",
                        "intelligence": "Length",
                        "fix": (f"prompt is {n} chars, below the 80 percent floor: ADD at "
                                f"least 15962 chars of genuine specification. Re-author "
                                f"with real specificity; do NOT pad."),
                    }
                ],
            }
        },
        "deck_deficiencies": [],
        "deficiencies": [],
    }

def _assert_reason_carries_the_fix(reasons, text: str) -> None:
    joined = "; ".join(reasons)
    assert not reasons[0].endswith("— "), (
        f"the reason must not end at the empty dash, got {reasons}")
    assert f"{len(text)} chars" in joined, (
        f"the reason must name the measured character count {len(text)}, got {reasons}")
    assert "ADD at least" in joined, (
        f"the reason must name the words to add, got {reasons}")

def test_a1a_stubbed_too_short_deficiency_puts_the_fix_in_the_reason(tmp_path, monkeypatch):
    """A1: the record's measured/fix text reaches the reason (hermetic)."""
    record = _deficiency_record(SHORT_PROMPT)
    monkeypatch.setattr(pv, "_bd_fn", lambda name: (lambda run_dir: record))

    ok, reasons = pv._verify_prompt(tmp_path)

    assert not ok, "a failing measurer verdict must not pass the prompt step"
    assert reasons, "a failing verdict must carry at least one reason"
    _assert_reason_carries_the_fix(reasons, SHORT_PROMPT)
    assert "slide-3" in reasons[0], f"the reason must name the slide, got {reasons}"

def test_a1b_real_measurer_on_a_too_short_prompt_names_the_count_and_the_add(tmp_path):
    """A1: end to end through build_deck's real deterministic prompt measurer."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "copy").mkdir(parents=True)
    (run_dir / "working" / "prompts").mkdir(parents=True)
    (run_dir / "working" / "copy" / "slides.json").write_text(
        json.dumps({"slides": [{"slide": 1, "arc_section": "opening"}]}),
        encoding="utf-8")
    (run_dir / "working" / "prompts" / "slide-01.txt").write_text(
        SHORT_PROMPT, encoding="utf-8")

    ok, reasons = pv._verify_prompt(run_dir)

    assert not ok, f"a too-short prompt must fail the prompt step, got {reasons}"
    _assert_reason_carries_the_fix(reasons, SHORT_PROMPT)
