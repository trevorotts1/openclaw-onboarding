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


# ---------------------------------------------------------------------------
# PD-202 — a closing waiver must be a real request about that gate.
#
# Acceptance: "the" -> rejected for length; a 30-character quote from an
# unlisted field -> rejected naming the field rule; a qualifying quote from a
# listed field -> accepted; ocr_readback -> still rejected. The field map is
# built only from bank questions that offer the client the choice to skip that
# deliverable (teleprompter_declined_reason, speech_script_declined_reason,
# ghl_upload_declined_reason); prompt_floor and qc have none.
# ---------------------------------------------------------------------------
import pytest  # noqa: E402

from presentation_job.waivers import (  # noqa: E402
    WAIVER_INTAKE_FIELDS,
    WAIVER_QUOTE_MIN_CHARS,
    WAIVER_QUOTE_MIN_WORDS,
    WaiverError,
    validate_waiver,
)


def _intake(rd, obj):
    p = rd / "working" / "copy" / "intake.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def _waiver(**over):
    w = {"rule": "teleprompter", "source": "intake_field",
         "intake_field": "teleprompter_declined_reason",
         "client_request_quote": "skip that check for us",
         "captured_at": "2026-01-01T00:00:00Z"}
    w.update(over)
    return w


def test_the_field_map_comes_from_the_bank_and_names_the_decline_questions():
    """Only gates the interview actually asks the client to decline carry a
    field; the craft floors do not (the bank's waiver_field_mapping says so)."""
    assert WAIVER_INTAKE_FIELDS["teleprompter"] == ("teleprompter_declined_reason",)
    assert WAIVER_INTAKE_FIELDS["script"] == ("speech_script_declined_reason",)
    assert WAIVER_INTAKE_FIELDS["ghl_upload"] == ("ghl_upload_declined_reason",)
    assert WAIVER_INTAKE_FIELDS["prompt_floor"] == ()
    assert WAIVER_INTAKE_FIELDS["qc"] == ()
    assert (WAIVER_QUOTE_MIN_CHARS, WAIVER_QUOTE_MIN_WORDS) == (20, 4)


def test_the_waiver_is_rejected_for_length():
    """A stray word is not a request about a gate."""
    rd = _run_dir()
    _intake(rd, {"teleprompter_declined_reason": "the"})
    with pytest.raises(WaiverError) as exc:
        validate_waiver(_waiver(client_request_quote="the"), rd)
    assert "client_request_quote" in str(exc.value)
    assert str(WAIVER_QUOTE_MIN_CHARS) in str(exc.value)


def test_a_20_character_quote_of_three_words_is_still_too_short():
    """Both floors bind: 20+ characters is not enough on its own."""
    rd = _run_dir()
    value = "absolutely-positively-not-thanks"
    _intake(rd, {"teleprompter_declined_reason": value})
    with pytest.raises(WaiverError, match="client_request_quote"):
        validate_waiver(_waiver(client_request_quote=value), rd)


def test_a_30_character_quote_from_an_unlisted_field_is_rejected_naming_the_rule():
    rd = _run_dir()
    _intake(rd, {"special_instructions": "please skip the teleprompter gate"})
    quote = "please skip the teleprompter gate"  # 33 characters, 5 words
    assert len(quote) >= WAIVER_QUOTE_MIN_CHARS and len(quote.split()) >= WAIVER_QUOTE_MIN_WORDS
    with pytest.raises(WaiverError) as exc:
        validate_waiver(_waiver(intake_field="special_instructions",
                                client_request_quote=quote), rd)
    message = str(exc.value)
    assert "not a field that can waive 'teleprompter'" in message, message
    assert "teleprompter_declined_reason" in message, message


def test_a_gate_with_no_decline_question_cannot_be_waived_from_an_intake_field():
    """qc / prompt_floor: the bank offers the client no way to decline them."""
    rd = _run_dir()
    _intake(rd, {"skip_qc": "Please skip the QC check for this run, we are on a deadline."})
    with pytest.raises(WaiverError) as exc:
        validate_waiver(_waiver(rule="qc", intake_field="skip_qc",
                                client_request_quote="skip the QC check for this run"), rd)
    assert "cannot be waived from an intake field" in str(exc.value)


def test_a_qualifying_quote_from_a_listed_field_is_accepted():
    rd = _run_dir()
    _intake(rd, {"teleprompter_declined_reason":
                 "We do not need a teleprompter; skip that check for us."})
    validate_waiver(_waiver(), rd)  # must not raise


def test_an_unparseable_captured_at_is_rejected():
    rd = _run_dir()
    _intake(rd, {"teleprompter_declined_reason": "skip that check for us"})
    with pytest.raises(WaiverError, match="not a date and time"):
        validate_waiver(_waiver(captured_at="last Tuesday"), rd)
    with pytest.raises(WaiverError, match="not a date and time"):
        validate_waiver(_waiver(captured_at="2026-01-01"), rd)  # date, no time


def test_ocr_readback_is_still_rejected():
    rd = _run_dir()
    _intake(rd, {"teleprompter_declined_reason": "skip that check for us"})
    with pytest.raises(WaiverError, match="cannot be waived|not a waivable gate"):
        validate_waiver(_waiver(rule="ocr_readback"), rd)
