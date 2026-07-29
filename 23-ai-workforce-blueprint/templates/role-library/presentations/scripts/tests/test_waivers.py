"""U013 waiver tests."""
import json, sys, pathlib, tempfile, pytest
SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
from presentation_job.waivers import WaiverError, load_waivers, validate_waiver, TRANSCRIPT_WAIVERS_ACCEPTED, GATE_KEYS, NON_WAIVABLE_GATES

def _rd(): return pathlib.Path(tempfile.mkdtemp())
def _wj(rd, rel, obj):
    p = rd / rel; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8"); return p

def test_transcript_waivers_defaults_false():
    assert TRANSCRIPT_WAIVERS_ACCEPTED is False

def test_ocr_readback_unwaivable():
    rd = _rd(); _wj(rd, "working/copy/intake.json", {"skip_ocr": True})
    w = {"rule": "ocr_readback", "source": "intake_field", "intake_field": "skip_ocr",
         "client_request_quote": "we do not need the readback", "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match="cannot be waived|not a waivable gate"):
        validate_waiver(w, rd)

def test_short_quote_rejected():
    rd = _rd(); _wj(rd, "working/copy/intake.json", {"f": True})
    w = {"rule": "teleprompter", "source": "intake_field", "intake_field": "f",
         "client_request_quote": "a", "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match="(?i)no client_request_quote"):
        validate_waiver(w, rd)

def test_missing_rule_rejected():
    rd = _rd(); _wj(rd, "working/copy/intake.json", {"f": True})
    w = {"rule": "not_a_gate", "source": "intake_field", "intake_field": "f",
         "client_request_quote": "yes sir", "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match="(?i)not a waivable gate"):
        validate_waiver(w, rd)

def test_duplicate_waivers_exit():
    rd = _rd(); _wj(rd, "waivers.json", [
        {"rule": "qc", "source": "intake_field", "intake_field": "f1",
         "client_request_quote": "skip", "captured_at": "2026-01-01T00:00:00Z"},
        {"rule": "qc", "source": "intake_field", "intake_field": "f2",
         "client_request_quote": "skip again", "captured_at": "2026-01-01T00:00:01Z"}])
    with pytest.raises(WaiverError, match="(?i)two waivers"):
        load_waivers(rd)

def test_valid_intake_waiver():
    rd = _rd(); _wj(rd, "working/copy/intake.json", {"no_teleprompter": True})
    w = {"rule": "teleprompter", "source": "intake_field", "intake_field": "no_teleprompter",
         "client_request_quote": "I waive the teleprompter quality check.", "captured_at": "2026-01-01T00:00:00Z"}
    validate_waiver(w, rd)

def test_missing_intake_field_rejected():
    rd = _rd(); _wj(rd, "working/copy/intake.json", {})
    w = {"rule": "teleprompter", "source": "intake_field", "intake_field": "no_tp",
         "client_request_quote": "please skip", "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match="not present"):
        validate_waiver(w, rd)

def test_no_source_rejected():
    rd = _rd()
    w = {"rule": "teleprompter", "source": "email",
         "client_request_quote": "yes", "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match="(?i)source"):
        validate_waiver(w, rd)

def test_transcript_rejected_when_disabled():
    assert TRANSCRIPT_WAIVERS_ACCEPTED is False
    rd = _rd()
    _wj(rd, "working/interview/intake_transcript.json", [{"role": "owner", "text": "I want to skip the teleprompter check."}])
    w = {"rule": "teleprompter", "source": "transcript",
         "client_request_quote": "I want to skip the teleprompter check.", "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match=r"(?i)TRANSCRIPT_WAIVERS_ACCEPTED"):
        validate_waiver(w, rd)

def test_missing_captured_at_rejected():
    rd = _rd(); _wj(rd, "working/copy/intake.json", {"f": True})
    w = {"rule": "teleprompter", "source": "intake_field", "intake_field": "f",
         "client_request_quote": "yes sir"}
    with pytest.raises(WaiverError, match="(?i)captured_at"):
        validate_waiver(w, rd)

def test_non_dict_waiver_element_rejected():
    # U013 fix-list item 5: load_waivers must reject a non-dict element in
    # waivers.json with a clean WaiverError instead of silently skipping it
    # (a bare string/number element used to slip through the old `if isinstance(w, dict):`
    # guard, which only validated dicts and ignored everything else).
    rd = _rd(); _wj(rd, "waivers.json", ["not-a-waiver-object"])
    with pytest.raises(WaiverError, match="(?i)expected an object"):
        load_waivers(rd)
