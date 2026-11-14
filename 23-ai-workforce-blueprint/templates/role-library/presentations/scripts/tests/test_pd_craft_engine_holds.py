#!/usr/bin/env python3
"""PD-310 — where the human-only craft rules run, the engine hook, and the
three defers that must fail closed.

Three things this file proves, all against the real module (no model call, no
network, no live service):

1. THE ENGINE HOOK. `craft_judgement.engine_attestation_reasons` hands both
   existing blockers (human verdicts, warning holds) to the phase-verifier path
   behind `PRESENTATION_CRAFT_ENGINE_HOLDS`, DEFAULT-OFF. Switch off: "" for
   every phase, so nothing changes. Switch on: a missing verdict file returns a
   reason starting `OPERATOR-REVIEW:` (PD-206's operator-channel prefix).
2. THE MISSING INSTRUMENT. The three enforced checks used to DEFER (pass) when
   `slide_craft` was unavailable, which read as "fail-closed" while passing. They
   now FAIL with a named reason unless `phase_verifiers._degraded_allowed` says
   this is an explicit test/CI context — the engine's own degraded-pass contract.
3. Nothing here asserts a pass about the unit itself; QC runs the acceptance
   rows. Standard library + pytest only; no suite, server or service is started.
"""

import json
import os
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent

import sys  # noqa: E402

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import craft_judgement as cj  # noqa: E402

DEGRADED_ENV = "PRESENTATION_ALLOW_DEGRADED_VERIFIERS"
DEGRADED_SIGNALS = (DEGRADED_ENV, "CI", "OPENCLAW_TEST")


def _run_dir(tmp_path):
    """A minimal run: two slides, one of which fires AF-AUD-1 (a "Speaker:"
    tag), plus the intake and arc the checks read."""
    rd = tmp_path / "run"
    copy_dir = rd / "working" / "copy"
    copy_dir.mkdir(parents=True)
    (rd / "working" / "qc").mkdir(parents=True)
    (copy_dir / "slides.json").write_text(json.dumps([
        {"slide": 1, "copy": ["REAL REVENUE GROWTH", "Speaker: stay right here"]},
        {"slide": 2, "copy": ["SAME HEADLINE THAT FITS"]},
    ]), encoding="utf-8")
    (copy_dir / "intake.json").write_text(
        json.dumps({"deck_type": "webinar", "hook": "Small steps still cross big rooms"}),
        encoding="utf-8")
    (copy_dir / "arc_allocation.json").write_text(json.dumps({"slots": [
        {"slide": 1, "arc_section": "BUILDUP"},
        {"slide": 2, "arc_section": "BUILDUP"},
    ]}), encoding="utf-8")
    return rd


def _no_degraded_signal(monkeypatch):
    """A production-shaped context: none of the three degraded-pass signals."""
    for name in DEGRADED_SIGNALS:
        monkeypatch.delenv(name, raising=False)


# ── 1. the engine hook ────────────────────────────────────────────────────

def test_switch_off_changes_nothing(tmp_path, monkeypatch):
    rd = _run_dir(tmp_path)
    monkeypatch.delenv(cj.ENGINE_HOLDS_ENV, raising=False)
    for phase in sorted(cj.ENGINE_HOLD_PHASES) + ["P-TYPO-QC"]:
        assert cj.engine_attestation_reasons(rd, phase) == "", (
            "switch off must leave the engine path exactly as it was")


def test_switch_on_missing_verdict_file_is_an_operator_review(tmp_path, monkeypatch):
    rd = _run_dir(tmp_path)
    monkeypatch.setenv(cj.ENGINE_HOLDS_ENV, "1")
    reason = cj.engine_attestation_reasons(rd, "P-PROMPT-QC")
    assert reason.startswith("OPERATOR-REVIEW:"), reason
    assert "AF-OBI-HUMAN-VERDICT" in reason, reason
    assert "human_craft_verdicts.json" in reason, (
        "the reason must name the file a person records the verdict in")


def test_switch_on_warning_hold_is_an_operator_review(tmp_path, monkeypatch):
    rd = _run_dir(tmp_path)
    monkeypatch.setenv(cj.ENGINE_HOLDS_ENV, "1")
    reason = cj.engine_attestation_reasons(rd, "P1Q-COPY-QC")
    assert reason.startswith("OPERATOR-REVIEW:"), reason
    assert "AF-WARNING-HOLD" in reason and "AF-AUD-1" in reason, reason


def test_switch_on_leaves_an_unrelated_phase_clear(tmp_path, monkeypatch):
    rd = _run_dir(tmp_path)
    monkeypatch.setenv(cj.ENGINE_HOLDS_ENV, "1")
    assert cj.engine_attestation_reasons(rd, "P-TYPO-QC") == ""


def test_switch_accepts_only_an_explicit_on(tmp_path):
    """The switch is DEFAULT-OFF: "0", "false", garbage and unset all leave it
    off; only 1/true/on/yes turn it on."""
    rd = _run_dir(tmp_path)
    old = os.environ.get(cj.ENGINE_HOLDS_ENV)
    try:
        for value, expected_off in (("0", True), ("false", True), ("", True),
                                    ("garbage", True), ("1", False),
                                    ("true", False)):
            os.environ[cj.ENGINE_HOLDS_ENV] = value
            got = cj.engine_attestation_reasons(rd, "P-PROMPT-QC")
            assert (got == "") is expected_off, (
                f"switch value {value!r} gave {got!r}")
    finally:
        if old is None:
            os.environ.pop(cj.ENGINE_HOLDS_ENV, None)
        else:
            os.environ[cj.ENGINE_HOLDS_ENV] = old


# ── 2. the three defers fail closed on a missing instrument ───────────────

def _without_reader(monkeypatch):
    """Simulate slide_craft being unimportable, the way the module's own FIX 17
    guard leaves it."""
    monkeypatch.setattr(cj, "_SLIDES", None)
    monkeypatch.setattr(cj, "_INTAKE", None)
    monkeypatch.setattr(cj, "_WRITE_PROVENANCE", None)


def test_hook_footer_defer_fails_closed_without_the_reader(tmp_path, monkeypatch):
    rd = _run_dir(tmp_path)
    _no_degraded_signal(monkeypatch)
    _without_reader(monkeypatch)
    reason = cj.check_hook_footer(rd)
    assert reason.startswith("AF-HOOK-2"), reason
    assert "unavailable" in reason and "fail-closed" in reason, reason


def test_hook_signature_quote_defer_fails_closed_without_the_reader(tmp_path, monkeypatch):
    rd = _run_dir(tmp_path)
    _no_degraded_signal(monkeypatch)
    _without_reader(monkeypatch)
    reason = cj.check_hook_signature_quote(rd)
    assert reason.startswith("AF-HOOK-7"), reason
    assert "fail-closed" in reason, reason


def test_comparison_rows_defer_fails_closed_without_the_reader(tmp_path, monkeypatch):
    rd = _run_dir(tmp_path)
    _no_degraded_signal(monkeypatch)
    _without_reader(monkeypatch)
    reason = cj.check_comparison_rows(rd)
    assert reason.startswith("AF-OBI-6"), reason
    assert "fail-closed" in reason, reason


def test_every_defer_still_defers_in_an_explicit_degraded_context(tmp_path, monkeypatch):
    """The one context where the old defer survives: the engine's own test/CI
    marker, read through phase_verifiers._degraded_allowed."""
    rd = _run_dir(tmp_path)
    _no_degraded_signal(monkeypatch)
    monkeypatch.setenv(DEGRADED_ENV, "1")
    _without_reader(monkeypatch)
    assert cj.check_hook_footer(rd) == ""
    assert cj.check_hook_signature_quote(rd) == ""
    assert cj.check_comparison_rows(rd) == ""
