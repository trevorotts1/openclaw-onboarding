"""PD unit tests for lane FL26 (client waivers and the closing gates).

Change under test here is PD-317b: `presentation_job.gates.Gates._qc_gate`
must read the closing quality report's own VERDICT, not only a number. The
report producer is `qc_aggregate.py` (phase P-QC-AGGREGATE), whose report dict
carries `"schema": "final_qc_report/v1"` and `"pass": <overall_pass>` beside
`"average"` (qc_aggregate.aggregate, the report dict it writes).

Acceptance rows: A1 (number at/above threshold + pass true + schema -> pass),
A2 (same number, pass false -> fail naming `pass`), A3 (no schema -> fail
naming it), plus the below-threshold control A4 relies on.

PD-202 (waiver rules) adds its own cases to this same lane-owned file.
"""
import json
import pathlib
import sys
import tempfile

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job.gates import (  # noqa: E402
    QC_PASS_THRESHOLD,
    QC_REPORT_SCHEMA,
    Gates,
)


def _run_dir():
    return pathlib.Path(tempfile.mkdtemp())


def _report(rd, obj):
    p = rd / "working" / "qc" / "final_qc_report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def test_schema_constant_matches_the_roll_up():
    """The gate's schema string must be the one qc_aggregate writes; a copy that
    drifts silently would reject every genuine report."""
    assert QC_REPORT_SCHEMA == "final_qc_report/v1"


def test_a1_passing_number_with_pass_true_and_schema_passes():
    rd = _run_dir()
    _report(rd, {"schema": QC_REPORT_SCHEMA, "pass": True,
                 "average": QC_PASS_THRESHOLD})
    g = Gates(rd, {})._qc_gate()
    assert g["state"] == "pass", g
    assert g["warn_only"] is False
    assert g["score"] == QC_PASS_THRESHOLD


def test_a2_passing_number_with_pass_false_fails_naming_pass():
    rd = _run_dir()
    _report(rd, {"schema": QC_REPORT_SCHEMA, "pass": False, "average": 9.4})
    g = Gates(rd, {})._qc_gate()
    assert g["state"] == "fail", g
    assert g["warn_only"] is False
    assert "'pass'" in g["reason"], g["reason"]
    assert "9.4" not in g["reason"] or "verdict" in g["reason"]


def test_a3_missing_schema_fails_naming_it():
    rd = _run_dir()
    _report(rd, {"pass": True, "average": 9.4})
    g = Gates(rd, {})._qc_gate()
    assert g["state"] == "fail", g
    assert g["warn_only"] is False
    assert "schema" in g["reason"], g["reason"]


def test_wrong_schema_string_also_fails():
    rd = _run_dir()
    _report(rd, {"schema": "some_other_report/v9", "pass": True, "average": 9.4})
    g = Gates(rd, {})._qc_gate()
    assert g["state"] == "fail", g
    assert "schema" in g["reason"], g["reason"]


def test_below_threshold_still_fails_with_a_full_verdict():
    rd = _run_dir()
    _report(rd, {"schema": QC_REPORT_SCHEMA, "pass": True, "average": 7.9})
    g = Gates(rd, {})._qc_gate()
    assert g["state"] == "fail", g
    assert "7.9" in g["reason"], g["reason"]


def test_verdict_failure_still_surfaces_aggregator_blocking_reasons():
    rd = _run_dir()
    _report(rd, {"schema": QC_REPORT_SCHEMA, "pass": False, "average": 9.4,
                 "blocking_reasons": ["Speech QC (P-SPEECH-QC): missing domain report"]})
    g = Gates(rd, {})._qc_gate()
    assert g["state"] == "fail", g
    assert "'pass'" in g["reason"], g["reason"]
    assert "P-SPEECH-QC" in g["reason"], g["reason"]
