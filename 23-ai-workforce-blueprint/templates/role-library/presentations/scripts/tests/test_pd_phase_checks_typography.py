#!/usr/bin/env python3
"""test_pd_phase_checks_typography.py — PD-075 (Moderate, lane FL17).

The Typography-QC step (``P-TYPO-QC``) proved only that
``working/qc/typography_qc_report.json`` existed, was non-empty and parsed
(``_verify_json_artifact`` with no required keys). A report that explicitly said
``pass: false`` — the live rubber stamp the RunFacts increment was built around —
still flipped the step to done.

After the fix the legacy half of the shadow-wired entry is
``_verify_qc_report("working/qc/typography_qc_report.json", "_chk_typography_qc",
"AF-TYPOGRAPHY-QC")`` — build_deck's real report-shape + teeth gate — and the
``_shadow_qc_verifier`` wrapper is kept around it.

Rows (01-BUILD-SPEC.md, section PD-075 — A1):

  A1a  ``pass: false`` report (shape otherwise valid)  -> fails
  A1b  a valid passing report                          -> passes

No network, no model call, no live service.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import phase_verifiers as pv  # noqa: E402

REPORT_REL = "working/qc/typography_qc_report.json"

# A report whose shape is valid in every respect except `pass` — so a failure
# can only come from the pass verdict, never from a malformed fixture.
def _report(pass_value: bool) -> dict:
    return {
        "gate": "Phase Typography-QC",
        "average": 9.1,
        "pass": pass_value,
        "triggered_autofails": [],
        "qc_independence": {
            "graded_by": "qc-specialist-typography-presentations",
            "independent": True,
            "builder": "typography-architect",
            "self_graded": False,
        },
    }

def _run_dir(tmp_path: Path, report: dict) -> Path:
    run_dir = tmp_path / "run"
    p = run_dir / REPORT_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report), encoding="utf-8")
    return run_dir

def test_a1a_pass_false_report_fails_the_typography_step(tmp_path):
    """A1: the report says pass:false — the step must refuse it."""
    run_dir = _run_dir(tmp_path, _report(False))
    ok, reasons = pv.verify("P-TYPO-QC", run_dir)
    assert not ok, "a report that says pass:false must NOT pass the step"
    joined = "; ".join(reasons)
    assert "AF-TYPOGRAPHY-QC" in joined, (
        f"the failure must cite the typography QC code, got {reasons}")

def test_a1b_valid_passing_report_passes_the_typography_step(tmp_path):
    """A1: the known-good control — a real passing report still passes."""
    run_dir = _run_dir(tmp_path, _report(True))
    ok, reasons = pv.verify("P-TYPO-QC", run_dir)
    assert ok, f"a valid passing report must pass, got reasons={reasons}"
    assert reasons == [], f"the passing path must carry no reasons, got {reasons}"

def test_the_registration_is_the_qc_report_gate_inside_the_shadow_wrapper():
    """The change itself: real report gate, still shadow-wired, still the one
    checked path PD-061's parity walk reads."""
    fn = pv.PHASE_VERIFIERS["P-TYPO-QC"]
    # The shadow wrapper is the only thing that copies artifact_pattern onto
    # the returned callable; its presence proves P-TYPO-QC is still wrapped.
    assert getattr(fn, "artifact_pattern", None) == REPORT_REL, (
        "P-TYPO-QC must stay behind the shadow wrapper, which carries the "
        "checked report path")
    # And the wrapped legacy callable is the QC-report gate built by
    # _verify_qc_report, not the existence-only _verify_json_artifact factory.
    legacy = [c.cell_contents for c in (fn.__closure__ or ())
              if callable(c.cell_contents) and c.cell_contents is not fn]
    assert any(getattr(f, "__qualname__", "").startswith("_verify_qc_report.")
               for f in legacy), (
        "the legacy half must be a _verify_qc_report verifier")
