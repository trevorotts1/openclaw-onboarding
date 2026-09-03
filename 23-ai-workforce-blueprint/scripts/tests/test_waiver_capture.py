"""Unit tests for U026 — waiver-form-field consent capture.

Tests _build_waiver_records in isolation and through the driver's public
interfaces.  Also covers auto_skip_all_conditionals integration for the
new question pairs.
"""
import json
import pathlib
import sys
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Import the driver as a module
# ---------------------------------------------------------------------------
_DRV = pathlib.Path(__file__).resolve().parent.parent / "deck-intake-turngate.py"
_mod = {}

with open(_DRV) as f:
    code = compile(f.read(), str(_DRV), "exec")
exec(code, _mod)  # nosec — test harness, no untrusted input

_build_waiver_records = _mod["_build_waiver_records"]
_auto_skip_all_conditionals = _mod["auto_skip_all_conditionals"]
_merge_intake_json = _mod["merge_intake_json"]

# ---------------------------------------------------------------------------
# Fixture: load the questions file once
# ---------------------------------------------------------------------------
_QFILE = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "templates" / "role-library" / "presentations" / "intake"
    / "deck-intake-questions.json"
)


@pytest.fixture(scope="module")
def qdata():
    with open(_QFILE) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# _build_waiver_records — unit tests
# ---------------------------------------------------------------------------

def test_no_waiver_when_toggle_not_validated(qdata):
    """A toggle that hasn't been validated yields no record."""
    led = {"entries": {
        "want_teleprompter": {"validated": False, "normalized": "no", "answer": "no"},
        "teleprompter_declined_reason": {"validated": True, "answer": "I hate teleprompters"},
    }}
    recs = _build_waiver_records(qdata, led)
    assert recs == []


def test_no_waiver_when_toggle_is_yes(qdata):
    """Accepting a gate is not a waiver."""
    led = {"entries": {
        "want_teleprompter": {"validated": True, "normalized": "yes", "answer": "yes"},
        "teleprompter_declined_reason": {"validated": True, "answer": "because"},
    }}
    recs = _build_waiver_records(qdata, led)
    assert recs == []


def test_no_waiver_when_reason_not_validated(qdata):
    """A reason that is not validated yields no record — gate stays enforced."""
    led = {"entries": {
        "want_teleprompter": {"validated": True, "normalized": "no", "answer": "no"},
        "teleprompter_declined_reason": {"validated": False, "answer": "maybe"},
    }}
    recs = _build_waiver_records(qdata, led)
    assert recs == []


def test_no_waiver_when_reason_empty(qdata):
    """An empty string reason is not consent."""
    led = {"entries": {
        "want_teleprompter": {"validated": True, "normalized": "no", "answer": "no"},
        "teleprompter_declined_reason": {"validated": True, "answer": ""},
    }}
    recs = _build_waiver_records(qdata, led)
    assert recs == []


def test_no_waiver_when_reason_whitespace_only(qdata):
    """A whitespace-only reason is not consent — .strip() must remove it."""
    led = {"entries": {
        "want_teleprompter": {"validated": True, "normalized": "no", "answer": "no"},
        "teleprompter_declined_reason": {"validated": True, "answer": "   "},
    }}
    recs = _build_waiver_records(qdata, led)
    assert recs == []


def test_no_waiver_when_reason_skipped(qdata):
    """U026 cardinal rule: a skipped entry is NEVER consent, even when
    validated=True and answer='(not applicable)' — the pattern
    auto_skip_conditionals writes."""
    led = {"entries": {
        "want_teleprompter": {"validated": True, "normalized": "no", "answer": "no"},
        "teleprompter_declined_reason": {
            "validated": True,
            "skipped": True,
            "answer": "(not applicable)",
        },
    }}
    recs = _build_waiver_records(qdata, led)
    assert recs == [], f"skipped entry leaked a waiver: {recs}"


def test_waiver_emitted_when_decline_with_quote(qdata):
    """Happy path: validated no + validated non-empty quote = one waiver record."""
    led = {"entries": {
        "want_teleprompter": {"validated": True, "normalized": "no", "answer": "no"},
        "teleprompter_declined_reason": {
            "validated": True,
            "validated_at": "2026-07-25T10:00:00Z",
            "answer": "  I read from paper, always have  ",
            "asked_at": "2026-07-25T09:55:00Z",
        },
    }}
    recs = _build_waiver_records(qdata, led)
    assert len(recs) == 1
    r = recs[0]
    assert r["rule"] == "teleprompter"
    assert r["source"] == "intake_field"
    assert r["client_request_quote"] == "I read from paper, always have"
    assert r["intake_field"] == "teleprompter_declined_reason"
    assert r["captured_at"] == "2026-07-25T10:00:00Z"
    assert r["captured_from"] == "deck-intake-turngate.py"


def test_captured_at_falls_back_to_asked_at(qdata):
    """When validated_at is absent, captured_at uses asked_at."""
    led = {"entries": {
        "want_teleprompter": {"validated": True, "normalized": "no", "answer": "no"},
        "teleprompter_declined_reason": {
            "validated": True,
            "asked_at": "2026-07-25T09:55:00Z",
            "answer": "no thanks",
        },
    }}
    recs = _build_waiver_records(qdata, led)
    assert len(recs) == 1
    assert recs[0]["captured_at"] == "2026-07-25T09:55:00Z"


def test_captured_at_falls_back_to_now(qdata):
    """When neither validated_at nor asked_at is present, _now() is the fallback."""
    led = {"entries": {
        "want_teleprompter": {"validated": True, "normalized": "no", "answer": "no"},
        "teleprompter_declined_reason": {
            "validated": True,
            "answer": "no thanks",
        },
    }}
    recs = _build_waiver_records(qdata, led)
    assert len(recs) == 1
    assert "T" in recs[0]["captured_at"]


def test_normalized_supersedes_answer_for_toggle(qdata):
    """normalized is preferred over raw answer for toggle comparison."""
    led = {"entries": {
        "want_teleprompter": {
            "validated": True,
            "normalized": "no",
            "answer": "nah, I'm good",
        },
        "teleprompter_declined_reason": {
            "validated": True,
            "answer": "prefer slides only",
        },
    }}
    recs = _build_waiver_records(qdata, led)
    assert len(recs) == 1


def test_multiple_waivers_simultaneously(qdata):
    """Two different gates declined yields two records."""
    led = {"entries": {
        "want_teleprompter": {"validated": True, "normalized": "no", "answer": "no"},
        "teleprompter_declined_reason": {
            "validated": True,
            "answer": "no prompter needed",
        },
        "want_ghl_upload": {"validated": True, "normalized": "no", "answer": "no"},
        "ghl_upload_declined_reason": {
            "validated": True,
            "answer": "using google drive instead",
        },
        "want_speech_script": {"validated": True, "normalized": "yes", "answer": "yes"},
    }}
    recs = _build_waiver_records(qdata, led)
    assert len(recs) == 2
    rules = {r["rule"] for r in recs}
    assert rules == {"teleprompter", "ghl_upload"}


# ---------------------------------------------------------------------------
# Integration: auto_skip_all_conditionals with new pairs
# ---------------------------------------------------------------------------

def test_auto_skip_reason_when_toggle_is_yes(qdata):
    """When the toggle answer is 'yes', the reason is auto-skipped."""
    led = {"entries": {
        "want_teleprompter": {"validated": True, "normalized": "yes", "answer": "yes"},
    }}
    _auto_skip_all_conditionals(qdata, led)
    reason = led["entries"].get("teleprompter_declined_reason", {})
    assert reason.get("skipped") is True
    assert reason.get("validated") is True


def test_auto_skip_does_not_skip_reason_when_toggle_is_no(qdata):
    """When the toggle answer is 'no', the reason is NOT auto-skipped."""
    led = {"entries": {
        "want_teleprompter": {"validated": True, "normalized": "no", "answer": "no"},
    }}
    _auto_skip_all_conditionals(qdata, led)
    reason = led["entries"].get("teleprompter_declined_reason", {})
    assert not reason.get("skipped")
    assert not reason.get("validated")


def test_auto_skip_does_not_skip_reason_when_toggle_not_answered(qdata):
    """When the toggle hasn't been answered, the reason is left pending."""
    led = {"entries": {}}
    _auto_skip_all_conditionals(qdata, led)
    reason = led["entries"].get("teleprompter_declined_reason", {})
    assert not reason.get("skipped")


def test_all_four_pairs_skip_on_yes(qdata):
    """Each of the four toggles, when 'yes', auto-skips its reason."""
    pairs = [
        ("want_teleprompter", "teleprompter_declined_reason"),
        ("want_speech_script", "speech_script_declined_reason"),
        ("want_ghl_upload", "ghl_upload_declined_reason"),
        ("want_audio_deliverable", "audio_declined_reason"),
    ]
    for toggle_id, reason_id in pairs:
        led = {"entries": {
            toggle_id: {"validated": True, "normalized": "yes", "answer": "yes"},
        }}
        _auto_skip_all_conditionals(qdata, led)
        reason = led["entries"].get(reason_id, {})
        assert reason.get("skipped") is True, f"{reason_id} not skipped for {toggle_id}=yes"
        assert reason.get("validated") is True


def test_all_four_pairs_not_skipped_on_no(qdata):
    """Each of the four toggles, when 'no', does NOT skip its reason."""
    pairs = [
        ("want_teleprompter", "teleprompter_declined_reason"),
        ("want_speech_script", "speech_script_declined_reason"),
        ("want_ghl_upload", "ghl_upload_declined_reason"),
        ("want_audio_deliverable", "audio_declined_reason"),
    ]
    for toggle_id, reason_id in pairs:
        led = {"entries": {
            toggle_id: {"validated": True, "normalized": "no", "answer": "no"},
        }}
        _auto_skip_all_conditionals(qdata, led)
        reason = led["entries"].get(reason_id, {})
        assert not reason.get("skipped"), f"{reason_id} skipped for {toggle_id}=no"
        assert not reason.get("validated"), f"{reason_id} validated for {toggle_id}=no"


# ---------------------------------------------------------------------------
# Schema conformance
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"rule", "source", "client_request_quote", "intake_field",
                   "captured_at", "captured_from"}


def test_waiver_record_has_exact_schema_keys(qdata):
    """Every waiver record carries exactly the six schema keys."""
    led = {"entries": {
        "want_teleprompter": {"validated": True, "normalized": "no", "answer": "no"},
        "teleprompter_declined_reason": {
            "validated": True,
            "answer": "no prompter",
        },
    }}
    recs = _build_waiver_records(qdata, led)
    assert len(recs) == 1
    assert set(recs[0].keys()) == REQUIRED_FIELDS


def test_source_is_always_intake_field(qdata):
    """Every waiver record from this unit has source='intake_field'."""
    led = {"entries": {
        "want_teleprompter": {"validated": True, "normalized": "no", "answer": "no"},
        "teleprompter_declined_reason": {
            "validated": True,
            "answer": "no prompter",
        },
    }}
    recs = _build_waiver_records(qdata, led)
    assert all(r["source"] == "intake_field" for r in recs)


# ---------------------------------------------------------------------------
# merge_intake_json: waiver write surface
# ---------------------------------------------------------------------------

def test_merge_waivers_preserves_existing_keys():
    """merge_intake_json preserves keys not in updates when merging waivers."""
    run_dir = pathlib.Path(tempfile.mkdtemp())
    (run_dir / "working" / "copy").mkdir(parents=True)
    first = run_dir / "working" / "copy" / "intake.json"
    first.write_text(json.dumps({"deck_type": "webinar", "existing_key": "value"}))
    _merge_intake_json(run_dir, {"waivers": [{"rule": "teleprompter"}]})
    obj = json.loads((run_dir / "working" / "copy" / "intake.json").read_text())
    assert obj["deck_type"] == "webinar"
    assert obj["existing_key"] == "value"
    assert "waivers" in obj
    assert len(obj["waivers"]) == 1


def test_merge_waivers_creates_file_when_absent():
    """merge_intake_json creates the intake.json when it doesn't exist."""
    run_dir = pathlib.Path(tempfile.mkdtemp())
    _merge_intake_json(run_dir, {"waivers": [{"rule": "teleprompter"}]})
    obj = json.loads((run_dir / "working" / "copy" / "intake.json").read_text())
    assert "waivers" in obj


# ---------------------------------------------------------------------------
# Anti-self-authoring — the unit's reason to exist
# ---------------------------------------------------------------------------

def test_anti_self_authoring_all_attack_vectors():
    """Every agent-authored waiver path must produce ZERO records."""
    qdata = json.loads(_QFILE.read_text())
    attacks = {
        "toggle no, reason invented by assistant (unvalidated)": {
            "want_teleprompter": {"validated": True, "normalized": "no", "answer": "no"},
            "teleprompter_declined_reason": {"validated": False, "answer": "client said they do not need it"},
        },
        "toggle unvalidated, reason validated": {
            "want_teleprompter": {"validated": False, "answer": "no"},
            "teleprompter_declined_reason": {"validated": True, "answer": "no thanks"},
        },
        "toggle skipped entirely, reason validated": {
            "teleprompter_declined_reason": {"validated": True, "answer": "no thanks"},
        },
        "reason skipped flag set (auto_skip pattern)": {
            "want_teleprompter": {"validated": True, "normalized": "no", "answer": "no"},
            "teleprompter_declined_reason": {
                "validated": True,
                "skipped": True,
                "answer": "(not applicable)",
            },
        },
    }
    for label, entries in attacks.items():
        recs = _build_waiver_records(qdata, {"entries": entries})
        assert recs == [], f"LEAK: '{label}' produced {len(recs)} records"
