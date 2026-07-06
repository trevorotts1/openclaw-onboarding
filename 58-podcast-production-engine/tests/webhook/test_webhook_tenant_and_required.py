"""Tenant isolation and the required-field gate (design/webhook-design.md Section 4.2).

Verification tests T7 (wrong-tenant location_id) and T8 (missing required field).
These prove the layer never writes into another tenant's account and never guesses a
missing required field: it holds the delivery for the operator instead.
"""

from __future__ import annotations

import copy


def _spy():
    calls = []

    def on_accept(job_key, canonical, record):
        calls.append(job_key)
    return calls, on_accept


def test_wrong_tenant_is_quarantined_and_nothing_is_written(
        sut, load_fixture, make_ledger, tenant_location_id):
    ledger = make_ledger()
    calls, on_accept = _spy()

    response = sut.intake(load_fixture("tenant_mismatch.json"), tenant_location_id,
                          ledger, on_accept=on_accept)

    assert response["status"] == "quarantine"
    assert ledger.count() == 0
    assert len(calls) == 0


def test_wrong_tenant_mapping_flags_the_mismatch(sut, load_fixture, tenant_location_id):
    result = sut.map_payload(load_fixture("tenant_mismatch.json"), tenant_location_id)
    assert result.status == "quarantine"
    assert result.tenant_ok is False
    assert any("tenant" in alert.lower() or "mismatch" in alert.lower() for alert in result.alerts)


def test_missing_style_is_held_for_the_operator(
        sut, load_fixture, make_ledger, tenant_location_id):
    ledger = make_ledger()
    calls, on_accept = _spy()

    response = sut.intake(load_fixture("missing_style.json"), tenant_location_id,
                          ledger, on_accept=on_accept)

    assert response["status"] == "accepted-incomplete"
    assert "style" in response["missing"]
    assert response["job"] is not None
    # nothing is produced for an incomplete submission
    assert len(calls) == 0
    # the delivery is persisted as needs_input so the operator can complete it
    record = ledger.read(response["job"])
    assert record["state"] == "needs_input"


def test_missing_style_mapping_names_the_missing_field(sut, load_fixture, tenant_location_id):
    result = sut.map_payload(load_fixture("missing_style.json"), tenant_location_id)
    assert result.status == "accepted-incomplete"
    assert "style" in result.missing
    assert any("missing" in alert.lower() for alert in result.alerts)


def test_interview_missing_host_is_incomplete(sut, load_fixture, tenant_location_id):
    payload = copy.deepcopy(load_fixture("convertflow_interview_provocative.json"))
    del payload["customData"]["podcast_host_name"]
    result = sut.map_payload(payload, tenant_location_id)
    assert result.status == "accepted-incomplete"
    assert "host_name" in result.missing


def test_complete_personal_submission_needs_no_show_or_host(sut, load_fixture, tenant_location_id):
    # Personal mode must NOT require show_name or host_name (Interview-only fields).
    result = sut.map_payload(load_fixture("convertflow_personal_counterintuitive.json"),
                             tenant_location_id)
    assert result.status == "accepted"
    assert "show_name" not in result.missing
    assert "host_name" not in result.missing
