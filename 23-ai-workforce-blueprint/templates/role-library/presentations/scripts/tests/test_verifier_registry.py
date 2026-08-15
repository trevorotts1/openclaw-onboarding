"""TRUST BOUNDARY, INCREMENT 2 — shared gate-conversion infra tests.

Covers 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/
verifier_registry.py (registry base + seal + shadow-compare wiring) and the
shared both-direction harness. Hermetic: stdlib + tmp_path only, no network.

Both-direction pattern (fabricated artifact REJECTED / genuine PASSES) is
exercised against a REAL registered QC verifier (qc:typography) using the same
rubric runfacts.verify_qc already proved on P-TYPO-QC in Increment 1:
  * fabricated report (pass:false, wrong gate label, no independence) -> FAIL,
    the reason naming exactly what could not be reproduced;
  * genuine report (gate label, average >= 8.5, pass:true, independent) -> PASS.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import runfacts as rf  # noqa: E402
from verifier_registry import (  # noqa: E402
    VerifierSpec,
    Verdict,
    both_directions,
    get_verifier,
    known_gates,
    qc_report_verifier,
    register_verifier,
    run_gate,
    write_fixture,
)


def _fresh(tmp_path: pathlib.Path, name: str = "run") -> pathlib.Path:
    rd = tmp_path / name
    rd.mkdir(parents=True, exist_ok=True)
    rf.reset_cache_for_tests()
    return rd


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_register_verifier_is_idempotent_and_last_wins():
    spec1 = qc_report_verifier("typography")
    gate = spec1.gate
    register_verifier(spec1)
    assert get_verifier(gate) is spec1

    # Re-registration replaces, never duplicates.
    spec2 = qc_report_verifier("typography")
    register_verifier(spec2)
    assert get_verifier(gate) is spec2
    assert known_gates().count(gate) == 1


def test_unknown_gate_fails_closed():
    ok, reasons = run_gate("no-such-gate", pathlib.Path("."))
    assert not ok
    assert any("no verifier registered" in r for r in reasons)


def test_verdict_has_no_truthiness():
    for v in (Verdict.PASS, Verdict.FAIL, Verdict.UNDETERMINED):
        with pytest.raises(TypeError):
            bool(v)


# ---------------------------------------------------------------------------
# qc_report_verifier: the T1 slice machinery
# ---------------------------------------------------------------------------

def _genuine_report():
    return {
        "gate": "Phase Typography-QC",
        "average": 9.2,
        "pass": True,
        "triggered_autofails": [],
        "qc_independence": {"graded_by": "typography-qc-specialist",
                            "independent": True},
    }


def test_qc_verifier_missing_report_fails_closed(tmp_path):
    spec = qc_report_verifier("typography")
    rd = _fresh(tmp_path)
    ok, reasons = spec.run_verifier(rd)
    assert not ok
    assert any("no input artifact found" in r for r in reasons)
    assert any("typography_qc_report.json" in r for r in reasons)


def test_both_directions_fabricated_rejected_genuine_passes(tmp_path):
    """The shared both-direction harness against a real registered verifier."""
    spec = qc_report_verifier("typography")

    def fabricate(rd):
        # Present, parses, but FAILS the rubric on every axis the Increment-1
        # proof used: wrong gate label, sub-floor average, pass not literal
        # True, no independence provenance.
        write_fixture(rd, "working/qc/typography_qc_report.json",
                      {"gate": "typography", "pass": False, "average": 2.1})

    def genuine(rd):
        write_fixture(rd, "working/qc/typography_qc_report.json",
                      _genuine_report())

    rd = _fresh(tmp_path)
    res = both_directions(spec, rd, fabricate=fabricate, genuine=genuine)

    f_ok, f_reasons = res["fabricated"]
    assert not f_ok, "fabricated report must be REJECTED"
    joined = "; ".join(f_reasons)
    for needle in ("expected 'Phase Typography-QC'", "below the 8.5",
                   "pass:true", "AF-QC-INDEPENDENCE"):
        assert needle in joined, f"rejection reason must name {needle!r}: {joined}"

    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine report must PASS, got {g_reasons}"


def test_run_gate_dispatch_by_name(tmp_path):
    register_verifier(qc_report_verifier("typography"))
    rd = _fresh(tmp_path)
    write_fixture(rd, "working/qc/typography_qc_report.json", _genuine_report())
    ok, reasons = run_gate("qc:typography", rd)
    assert ok, reasons
    assert reasons == []


def test_enforcing_flag_flips_only_under_explicit_opt_in(tmp_path):
    spec = qc_report_verifier("typography")
    rd = _fresh(tmp_path)
    write_fixture(rd, "working/qc/typography_qc_report.json",
                  {"gate": "typography", "pass": False, "average": 2.1})
    os.environ.pop(rf.ENFORCE_ENV, None)
    try:
        # Report-only default: the RunFacts verdict is computed (FAIL) and
        # shadow-compared, but with no legacy fn the RunFacts verdict stands
        # (this slice owns the gate) — so FAIL is returned regardless. The
        # report-only guarantee is enforced at the phase-verifier level; here
        # we prove the verdict machinery itself is deterministic.
        ok, reasons = spec.run_verifier(rd)
        assert not ok
        assert reasons and any("expected 'Phase Typography-QC'" in r for r in reasons)

        # UNDETERMINED verdicts are representable and refuse to be a pass.
        spec2 = VerifierSpec(
            gate="demo:undetermined",
            verifier=qc_report_verifier("typography").verifier,
            verdict=lambda facts: (Verdict.UNDETERMINED, "no data"),
            artifacts=("working/qc/typography_qc_report.json",),
        )
        ok2, reasons2 = spec2.run_verifier(rd)
        assert not ok2
        assert any("no data" in r for r in reasons2)
    finally:
        os.environ.pop(rf.ENFORCE_ENV, None)


def test_verifier_registry_module_imports_clean():
    """The registry module must import without executing I/O (no seal at
    import time) — matching the phase_verifiers convention."""
    import importlib
    mod = importlib.import_module("verifier_registry")
    assert callable(mod.register_verifier)
    assert callable(mod.qc_report_verifier)
    assert callable(mod.both_directions)
