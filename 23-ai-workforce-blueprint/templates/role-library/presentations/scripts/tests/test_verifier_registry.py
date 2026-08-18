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
    final_qc_verifier,
    get_verifier,
    known_gates,
    priority_shift_verifier,
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


# ---------------------------------------------------------------------------
# SLICE 2 — report-shape-only gates converted to the verifier pattern
# (P-SPEECH-QC via qc_report_verifier("speech"), P-SHIFT-QC via
# priority_shift_verifier(), P-QC-AGGREGATE via final_qc_verifier()).
# Both directions each: a fabricated artifact is REJECTED with the exact
# discrepancy named; a genuine artifact PASSES.
# ---------------------------------------------------------------------------

def _genuine_domain_report(gate, average=9.4):
    """The genuine report shape the manifest's QC domains write (also the shape
    test_presentation_job.py / test_qc_aggregate.py seed for the six domains)."""
    return {
        "gate": gate, "average": average, "pass": average >= 8.5,
        "triggered_autofails": [],
        "qc_independence": {"graded_by": "qc-specialist-independent-reviewer",
                            "independent": True},
    }


def test_slice2_speech_both_directions(tmp_path):
    """P-SPEECH-QC: fabricated speech report (pass:false, wrong gate, no
    independence) rejected naming the discrepancy; genuine passes."""
    spec = qc_report_verifier("speech")
    assert spec.gate == "qc:speech"

    def fabricate(rd):
        write_fixture(rd, "working/qc/speech_qc_report.json",
                      {"gate": "speech", "pass": False, "average": 2.1})

    def genuine(rd):
        write_fixture(rd, "working/qc/speech_qc_report.json",
                      _genuine_domain_report("Phase Speech-QC"))

    rd = _fresh(tmp_path)
    res = both_directions(spec, rd, fabricate=fabricate, genuine=genuine)

    f_ok, f_reasons = res["fabricated"]
    assert not f_ok, "fabricated speech report must be REJECTED"
    joined = "; ".join(f_reasons)
    for needle in ("expected 'Phase Speech-QC'", "below the 8.5", "pass:true",
                   "AF-QC-INDEPENDENCE"):
        assert needle in joined, f"rejection must name {needle!r}: {joined}"

    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine speech report must PASS, got {g_reasons}"


def test_slice2_speech_absent_fails_closed(tmp_path):
    """D10: a P-SPEECH-QC with no report yet fails hard at the phase layer —
    the pre-delivery defer lives in build_deck._chk_speech_qc (path None),
    not here. Once the phase runs, absence is a fail naming the path."""
    spec = qc_report_verifier("speech")
    rd = _fresh(tmp_path)
    ok, reasons = spec.run_verifier(rd)
    assert not ok
    assert any("no input artifact found" in r for r in reasons)
    assert any("speech_qc_report.json" in r for r in reasons)


def test_slice2_priority_shift_both_directions(tmp_path):
    """P-SHIFT-QC: fabricated ledger (pass:true headline over failing rows —
    a rubber stamp) rejected naming the failing items; genuine 14-row all-pass
    ledger passes."""
    spec = priority_shift_verifier()
    assert spec.gate == "qc:priority_shift"

    def fabricate(rd):
        # Headline says pass but the ledger contradicts it.
        write_fixture(rd, "working/qc/priority_shift_report.json", {
            "schema": "priority_shift_report/v1", "gate": "AF-PRIORITY-SHIFT",
            "pass": True,
            "items": [{"item": f"item_{i}", "pass": True, "evidence": "ok"}
                      for i in range(13)]
                     + [{"item": "13_most_vivid_by_the_end", "pass": False,
                         "evidence": "AF-NO-SALIENCE-APEX"}],
        })

    def genuine(rd):
        write_fixture(rd, "working/qc/priority_shift_report.json", {
            "schema": "priority_shift_report/v1", "gate": "AF-PRIORITY-SHIFT",
            "phase": "P-SHIFT-QC (order 7.5)", "pass": True,
            "items": [{"item": f"item_{i}", "pass": True, "evidence": "ok"}
                      for i in range(15)],
            "slides": [{"slide": 1, "pass": True, "verdict": "pass"}],
        })

    rd = _fresh(tmp_path)
    res = both_directions(spec, rd, fabricate=fabricate, genuine=genuine)

    f_ok, f_reasons = res["fabricated"]
    assert not f_ok, "fabricated priority-shift ledger must be REJECTED"
    joined = "; ".join(f_reasons)
    assert "13_most_vivid_by_the_end" in joined, joined

    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine priority-shift ledger must PASS, got {g_reasons}"


def test_slice2_priority_shift_pass_false_flagged(tmp_path):
    spec = priority_shift_verifier()
    rd = _fresh(tmp_path)
    write_fixture(rd, "working/qc/priority_shift_report.json", {
        "schema": "priority_shift_report/v1", "gate": "AF-PRIORITY-SHIFT",
        "pass": False,
        "items": [{"item": "0_attention_is_the_no1_job", "pass": False,
                   "evidence": ""}],
    })
    ok, reasons = spec.run_verifier(rd)
    assert not ok
    joined = "; ".join(reasons)
    assert "pass:true" in joined and "0_attention_is_the_no1_job" in joined, joined


def _seed_six_domains(rd):
    write_fixture(rd, "working/qc/copy_qc_report.json",
                  _genuine_domain_report("Phase 1Q"))
    write_fixture(rd, "working/qc/typography_qc_report.json",
                  _genuine_domain_report("Phase Typography-QC"))
    write_fixture(rd, "working/qc/prompt_qc_report.json",
                  _genuine_domain_report("Phase Prompt-QC"))
    write_fixture(rd, "working/qc/image_qc_report.json",
                  _genuine_domain_report("Phase Image-QC"))
    write_fixture(rd, "working/qc/speech_qc_report.json",
                  _genuine_domain_report("Phase Speech-QC"))
    write_fixture(rd, "working/qc/priority_shift_report.json", {
        "schema": "priority_shift_report/v1", "gate": "AF-PRIORITY-SHIFT",
        "phase": "P-SHIFT-QC (order 7.5)", "pass": True,
        "items": [{"item": f"item_{i}", "pass": True, "evidence": "ok"}
                  for i in range(15)],
    })


def test_slice2_final_qc_both_directions(tmp_path):
    """P-QC-AGGREGATE: the verifier re-measures the REAL artifacts — a
    fabricated aggregate (headline pass over a missing/blocked domain) is
    rejected naming the failing domain; a genuine aggregate over six passing
    domains passes. Fabrication direction: aggregate absent while one domain
    report is missing."""
    spec = final_qc_verifier()
    assert spec.gate == "qc:final"

    def fabricate(rd):
        # Domain reports all present EXCEPT speech — the aggregate's own
        # blocking_reasons names it; the verifier must re-derive that itself.
        _seed_six_domains(rd)
        (rd / "working" / "qc" / "speech_qc_report.json").unlink()
        write_fixture(rd, "working/qc/final_qc_report.json", {
            "schema": "final_qc_report/v1", "generator": "scripts/qc_aggregate.py",
            "threshold": 8.5, "pass": False, "average": None,
            "computed_average": None,
            "blocking_reasons": ["Speech QC (P-SPEECH-QC): missing domain report"],
        })

    def genuine(rd):
        _seed_six_domains(rd)
        write_fixture(rd, "working/qc/final_qc_report.json", {
            "schema": "final_qc_report/v1", "generator": "scripts/qc_aggregate.py",
            "threshold": 8.5, "pass": True, "average": 9.4,
            "computed_average": 9.4,
            "domains": {"copy": {"average": 9.4}, "typography": {"average": 9.4}},
            "per_dimension": {"copy": 9.4, "typography": 9.4,
                              "prompt": 9.4, "image": 9.4, "speech": 9.4,
                              "priority_shift_pass": True},
        })

    rd = _fresh(tmp_path)
    res = both_directions(spec, rd, fabricate=fabricate, genuine=genuine)

    f_ok, f_reasons = res["fabricated"]
    assert not f_ok, "fabricated aggregate must be REJECTED"
    joined = "; ".join(f_reasons)
    for needle in ("qc:final", "qc[speech]", "average is null"):
        assert needle in joined, f"rejection must name {needle!r}: {joined}"

    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine aggregate must PASS, got {g_reasons}"


def test_slice2_final_qc_sub_threshold_domain_blocks(tmp_path):
    """A sub-threshold domain report must block the aggregate even when the
    aggregate's own rows claim a pass — the re-measure, not the headline."""
    spec = final_qc_verifier()
    rd = _fresh(tmp_path)
    _seed_six_domains(rd)
    write_fixture(rd, "working/qc/image_qc_report.json",
                  _genuine_domain_report("Phase Image-QC", 6.0))
    write_fixture(rd, "working/qc/final_qc_report.json", {
        "schema": "final_qc_report/v1", "generator": "scripts/qc_aggregate.py",
        "threshold": 8.5, "pass": True, "average": 9.4,
        "blocking_reasons": [],
    })
    ok, reasons = spec.run_verifier(rd)
    assert not ok
    joined = "; ".join(reasons)
    assert "qc[image]" in joined, joined


def test_slice2_final_qc_absent_fails_closed(tmp_path):
    spec = final_qc_verifier()
    rd = _fresh(tmp_path)
    _seed_six_domains(rd)
    ok, reasons = spec.run_verifier(rd)
    assert not ok
    assert any("no input artifact found" in r for r in reasons)
    assert any("final_qc_report.json" in r for r in reasons)


def test_slice2_phase_verifiers_wired_to_registry(tmp_path):
    """The phase-verifier wiring: PHASE_VERIFIERS entries for P-SPEECH-QC /
    P-SHIFT-QC / P-QC-AGGREGATE must now run the registered verifiers and
    behave identically (fail-closed on absent input, reject fabricated,
    accept genuine)."""
    import phase_verifiers as pv
    rd = _fresh(tmp_path)
    write_fixture(rd, "working/qc/speech_qc_report.json",
                  _genuine_domain_report("Phase Speech-QC"))
    ok, reasons = pv.verify("P-SPEECH-QC", rd)
    assert ok, reasons
    ok, reasons = pv.verify("P-SHIFT-QC", rd)
    assert not ok, "no priority_shift_report.json yet — must fail closed"
    assert any("no input artifact found" in r for r in reasons)
