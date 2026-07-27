"""Tests for U013 waiver hardening -- duplicates, transcript gate, rejected readability."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, SCRIPTS)


# ---------------------------------------------------------------------------
# load_waivers: duplicate detection
# ---------------------------------------------------------------------------
def test_load_waivers_rejects_duplicates():
    from presentation_job.waivers import load_waivers, WaiverError
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        w = [
            {"rule": "ghl_upload", "source": "intake_field",
             "intake_field": "skip_upload",
             "client_request_quote": "do not upload",
             "captured_at": "2026-01-01T00:00:00Z"},
            {"rule": "ghl_upload", "source": "intake_field",
             "intake_field": "skip_upload",
             "client_request_quote": "skip it",
             "captured_at": "2026-01-02T00:00:00Z"},
        ]
        (base / "waivers.json").write_text(json.dumps(w))
        with pytest.raises(WaiverError, match="two waivers name the same gate"):
            load_waivers(base)


def test_load_waivers_accepts_unique_rules():
    from presentation_job.waivers import load_waivers
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        w = [
            {"rule": "ghl_upload", "source": "intake_field",
             "intake_field": "skip_upload",
             "client_request_quote": "do not upload",
             "captured_at": "2026-01-01T00:00:00Z"},
            {"rule": "script", "source": "intake_field",
             "intake_field": "skip_script",
             "client_request_quote": "skip the script",
             "captured_at": "2026-01-01T00:00:00Z"},
        ]
        (base / "waivers.json").write_text(json.dumps(w))
        result = load_waivers(base)
        assert len(result) == 2


def test_load_waivers_coerces_single_object():
    from presentation_job.waivers import load_waivers
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        w = {"rule": "script", "source": "intake_field",
             "intake_field": "skip_script",
             "client_request_quote": "skip the script",
             "captured_at": "2026-01-01T00:00:00Z"}
        (base / "waivers.json").write_text(json.dumps(w))
        result = load_waivers(base)
        assert isinstance(result, list)
        assert len(result) == 1


def test_load_waivers_returns_empty_on_no_file():
    from presentation_job.waivers import load_waivers
    with tempfile.TemporaryDirectory() as tmp:
        assert load_waivers(Path(tmp)) == []


def test_load_waivers_raises_on_json_error():
    from presentation_job.waivers import load_waivers, WaiverError
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "waivers.json").write_text("{not valid json")
        with pytest.raises(WaiverError, match="unreadable"):
            load_waivers(base)


# ---------------------------------------------------------------------------
# validate_waiver: rule checking
# ---------------------------------------------------------------------------
def test_validate_waiver_unknown_rule():
    from presentation_job.waivers import validate_waiver, WaiverError
    w = {"rule": "nonexistent_gate", "source": "transcript",
         "client_request_quote": "ok",
         "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match="not a waivable gate"):
        validate_waiver(w, Path("/nonexistent"))


def test_validate_waiver_ocr_readback_rejected():
    from presentation_job.waivers import validate_waiver, WaiverError
    w = {"rule": "ocr_readback", "source": "intake_field",
         "intake_field": "whatever",
         "client_request_quote": "skip ocr please",
         "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match="not a waivable gate"):
        validate_waiver(w, Path("/nonexistent"))


def test_validate_waiver_bad_source():
    from presentation_job.waivers import validate_waiver, WaiverError
    w = {"rule": "script", "source": "email",
         "client_request_quote": "ok",
         "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match="source"):
        validate_waiver(w, Path("/nonexistent"))


def test_validate_waiver_short_quote():
    from presentation_job.waivers import validate_waiver, WaiverError
    w = {"rule": "script", "source": "intake_field",
         "intake_field": "f",
         "client_request_quote": "ok",  # 2 chars
         "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match="no client_request_quote"):
        validate_waiver(w, Path("/nonexistent"))


def test_validate_waiver_missing_timestamp():
    from presentation_job.waivers import validate_waiver, WaiverError
    w = {"rule": "script", "source": "intake_field",
         "intake_field": "f",
         "client_request_quote": "yes please"}
    with pytest.raises(WaiverError, match="captured_at"):
        validate_waiver(w, Path("/nonexistent"))


# ---------------------------------------------------------------------------
# validate_waiver: intake_field path
# ---------------------------------------------------------------------------
def test_validate_waiver_intake_field_missing():
    from presentation_job.waivers import validate_waiver, WaiverError
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "working" / "copy").mkdir(parents=True)
        (base / "working" / "copy" / "intake.json").write_text(json.dumps({"other": True}))
        w = {"rule": "script", "source": "intake_field",
             "intake_field": "missing_field",
             "client_request_quote": "skip the script",
             "captured_at": "2026-01-01T00:00:00Z"}
        with pytest.raises(WaiverError, match="not present in intake.json"):
            validate_waiver(w, base)


def test_validate_waiver_intake_field_present():
    from presentation_job.waivers import validate_waiver
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "working" / "copy").mkdir(parents=True)
        (base / "working" / "copy" / "intake.json").write_text(
            json.dumps({"client_ok_script": True}))
        w = {"rule": "script", "source": "intake_field",
             "intake_field": "client_ok_script",
             "client_request_quote": "skip the script",
             "captured_at": "2026-01-01T00:00:00Z"}
        validate_waiver(w, base)  # should not raise


# ---------------------------------------------------------------------------
# transcript path rejection
# ---------------------------------------------------------------------------
def test_transcript_waiver_rejected_by_default():
    from presentation_job.waivers import validate_waiver, WaiverError, TRANSCRIPT_WAIVERS_ACCEPTED
    assert TRANSCRIPT_WAIVERS_ACCEPTED is False
    w = {"rule": "teleprompter", "source": "transcript",
         "client_request_quote": "skip the teleprompter",
         "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match="transcript-sourced waivers are not yet accepted"):
        validate_waiver(w, Path("/nonexistent"))


def test_transcript_waivers_accepted_exists():
    from presentation_job.waivers import TRANSCRIPT_WAIVERS_ACCEPTED
    assert isinstance(TRANSCRIPT_WAIVERS_ACCEPTED, bool)
    assert TRANSCRIPT_WAIVERS_ACCEPTED is False
