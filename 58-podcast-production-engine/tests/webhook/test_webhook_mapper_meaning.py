"""Independent check on the deterministic mapper: mapping is by MEANING, not name.

Covers design/webhook-design.md Section 4 and CHECKLIST Part C item 2 (deterministic
mapper with fixture unit tests for the Convert and Flow, Make.com, and n8n families).

The three family fixtures carry ONE submission with identical meaning but different
field spellings, casing, nesting, and whitespace, plus different volatile transport
fields. A correct mapper collapses all three to the same canonical hash fields.
"""

from __future__ import annotations

import copy
import json
import os

from spec_reference.job_key import HASH_FIELDS

_HERE = os.path.dirname(os.path.abspath(__file__))
_FAMILIES = [
    "convertflow_personal_counterintuitive.json",
    "make_personal_counterintuitive.json",
    "n8n_personal_counterintuitive.json",
]


def _project(canonical):
    return {k: v for k, v in canonical.items() if k in HASH_FIELDS}


def _expected():
    path = os.path.join(_HERE, "fixtures", "expected", "canonical_personal_counterintuitive.json")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def test_every_family_is_accepted(sut, load_fixture, tenant_location_id):
    for name in _FAMILIES:
        result = sut.map_payload(load_fixture(name), tenant_location_id)
        assert result.status == "accepted", name + " should map to accepted, got " + result.status
        assert result.tenant_ok is True


def test_every_family_matches_the_expected_canonical(sut, load_fixture, tenant_location_id):
    expected = _expected()
    for name in _FAMILIES:
        result = sut.map_payload(load_fixture(name), tenant_location_id)
        assert _project(result.canonical) == expected, name + " canonical hash fields diverged"


def test_all_families_produce_identical_hash_fields(sut, load_fixture, tenant_location_id):
    projections = []
    for name in _FAMILIES:
        result = sut.map_payload(load_fixture(name), tenant_location_id)
        projections.append(_project(result.canonical))
    first = projections[0]
    for other in projections[1:]:
        assert other == first, "families disagree on canonical hash fields"


def test_convertflow_full_canonical_equals_expected(sut, load_fixture, tenant_location_id):
    # The Convert and Flow fixture carries no extra fields, so its full canonical
    # equals the expected hash-field set exactly (no stray keys leak in).
    result = sut.map_payload(load_fixture("convertflow_personal_counterintuitive.json"),
                             tenant_location_id)
    assert result.canonical == _expected()


def test_container_flattening_reads_nested_contact_id(sut, load_fixture, tenant_location_id):
    # n8n nests the contact under body.contact; a bare id there must become contact_id.
    result = sut.map_payload(load_fixture("n8n_personal_counterintuitive.json"), tenant_location_id)
    assert result.canonical.get("contact_id") == "C0nTacT12345aBcDe"
    assert result.canonical.get("first_name") == "Maria"


def test_whitespace_is_normalized(sut, load_fixture, tenant_location_id):
    # n8n answer_1 carries leading, trailing, and internal double spaces.
    result = sut.map_payload(load_fixture("n8n_personal_counterintuitive.json"), tenant_location_id)
    assert result.canonical["q1_answer"] == "The harder I pushed for control, the less I actually had."


def test_enum_forms_are_normalized(sut, load_fixture, tenant_location_id):
    # Make sends S2.1-Pro, Full, Clean; the mapper lowercases enum values.
    result = sut.map_payload(load_fixture("make_personal_counterintuitive.json"), tenant_location_id)
    assert result.canonical["tts_model"] == "s2.1-pro"
    assert result.canonical["episode_type"] == "full"
    assert result.canonical["explicit"] == "clean"
    assert result.canonical["mode"] == "personal_podcast_style"
    assert result.canonical["style"] == "counter_intuitive"


def test_unknown_fields_never_enter_the_canonical_record(sut, load_fixture, tenant_location_id):
    # Volatile transport keys (event ids, timestamps, signatures) are unmapped and
    # must not appear as canonical fields.
    for name in _FAMILIES:
        result = sut.map_payload(load_fixture(name), tenant_location_id)
        for stray in ("webhook_event_id", "executionId", "eventId", "signature", "timestamp"):
            assert stray not in result.canonical


def test_mapping_is_deterministic(sut, load_fixture, tenant_location_id):
    payload = load_fixture("convertflow_personal_counterintuitive.json")
    first = sut.map_payload(copy.deepcopy(payload), tenant_location_id).canonical
    second = sut.map_payload(copy.deepcopy(payload), tenant_location_id).canonical
    assert first == second


def test_interview_fixture_requires_and_finds_show_and_host(sut, load_fixture, tenant_location_id):
    result = sut.map_payload(load_fixture("convertflow_interview_provocative.json"),
                             tenant_location_id)
    assert result.status == "accepted"
    assert result.canonical["mode"] == "interview_style_podcast"
    assert result.canonical["style"] == "provocative"
    assert result.canonical["show_name"] == "The Unfiltered Founder"
    assert result.canonical["host_name"] == "Dana Whitfield"


def test_value_shape_rejects_implausible_values(sut, load_fixture, tenant_location_id):
    payload = load_fixture("convertflow_personal_counterintuitive.json")
    bad = copy.deepcopy(payload)
    bad["customData"]["podcast_mode"] = "totally unrelated words"
    bad["customData"]["podcast_survey_writing_style"] = "not a real style"
    bad["contact_id"] = "maria@example.com"
    bad["customData"]["date_for_release"] = "sometime next quarter"
    result = sut.map_payload(bad, tenant_location_id)
    # Invalid enum and id and date values are dropped, never guessed.
    assert "mode" not in result.canonical
    assert "style" not in result.canonical
    assert "contact_id" not in result.canonical
    assert "publish_timestamp" not in result.canonical
    # With required anchors missing, the delivery is held for the operator.
    assert result.status == "accepted-incomplete"
