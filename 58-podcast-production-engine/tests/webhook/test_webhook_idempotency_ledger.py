"""The idempotency proof (CHECKLIST Part C item 3) and the ledger dedup contract.

Design/webhook-design.md Sections 3.2 and 3.3, verification tests T5 and T6.

Proven here, end to end through intake():
  - an identical redelivery yields exactly ONE episode record and a duplicate ack,
  - a one-answer change yields a NEW job (a second record),
  - meaning-based dedup holds ACROSS pipeline families (Convert and Flow then Make.com),
  - volatile-only redeliveries are duplicates,
  - the exclusive-create claim settles a same-submission race,
  - a failed job is not re-run by an upstream retry storm unless operator-sanctioned,
  - a _test-gated delivery is recorded as a test, never as a live episode.

The durable flow trigger (create_flow / run_task) is modelled by an on_accept spy so
the tests can assert it fires exactly once per genuinely new job and never on a duplicate.
"""

from __future__ import annotations

import copy


def _spy():
    calls = []

    def on_accept(job_key, canonical, record):
        calls.append(job_key)
    return calls, on_accept


def test_single_delivery_creates_one_record_and_triggers_one_flow(
        sut, load_fixture, make_ledger, tenant_location_id):
    ledger = make_ledger()
    calls, on_accept = _spy()
    payload = load_fixture("convertflow_personal_counterintuitive.json")

    response = sut.intake(payload, tenant_location_id, ledger, on_accept=on_accept)

    assert response["status"] == "accepted"
    assert ledger.count() == 1
    assert len(calls) == 1
    assert calls[0] == response["job"]


def test_identical_redelivery_is_a_duplicate_with_one_record(
        sut, load_fixture, make_ledger, tenant_location_id):
    ledger = make_ledger()
    calls, on_accept = _spy()
    payload = load_fixture("convertflow_personal_counterintuitive.json")

    first = sut.intake(copy.deepcopy(payload), tenant_location_id, ledger, on_accept=on_accept)
    second = sut.intake(copy.deepcopy(payload), tenant_location_id, ledger, on_accept=on_accept)

    assert first["status"] == "accepted"
    assert second["status"] == "duplicate"
    assert second["job"] == first["job"]
    # exactly one episode record survives the redelivery
    assert ledger.count() == 1
    # no second production run
    assert len(calls) == 1
    # delivery_count incremented to 2
    record = ledger.read(first["job"])
    assert record["attempts"]["delivery_count"] == 2


def test_dedup_holds_across_pipeline_families(
        sut, load_fixture, make_ledger, tenant_location_id):
    # The SAME submission arriving via Convert and Flow and then via Make.com must
    # dedup: same meaning, same job key, one record.
    ledger = make_ledger()
    calls, on_accept = _spy()

    first = sut.intake(load_fixture("convertflow_personal_counterintuitive.json"),
                       tenant_location_id, ledger, on_accept=on_accept)
    second = sut.intake(load_fixture("make_personal_counterintuitive.json"),
                        tenant_location_id, ledger, on_accept=on_accept)

    assert first["status"] == "accepted"
    assert second["status"] == "duplicate"
    assert first["job"] == second["job"]
    assert ledger.count() == 1
    assert len(calls) == 1


def test_one_answer_change_yields_a_new_job(
        sut, load_fixture, make_ledger, tenant_location_id):
    ledger = make_ledger()
    calls, on_accept = _spy()

    original = load_fixture("convertflow_personal_counterintuitive.json")
    changed = copy.deepcopy(original)
    changed["customData"]["q3"] = original["customData"]["q3"] + " And I would do it again."

    first = sut.intake(original, tenant_location_id, ledger, on_accept=on_accept)
    second = sut.intake(changed, tenant_location_id, ledger, on_accept=on_accept)

    assert first["status"] == "accepted"
    assert second["status"] == "accepted"
    assert second["job"] != first["job"]
    # two distinct episode records; two production runs
    assert ledger.count() == 2
    assert len(calls) == 2


def test_volatile_only_redelivery_is_a_duplicate(
        sut, load_fixture, make_ledger, tenant_location_id):
    ledger = make_ledger()
    calls, on_accept = _spy()

    original = load_fixture("convertflow_personal_counterintuitive.json")
    noisy = copy.deepcopy(original)
    noisy["webhook_event_id"] = "evt-cf-777777"
    noisy["timestamp"] = "2026-07-06T19:01:02.003Z"
    noisy["retryCount"] = 5

    first = sut.intake(original, tenant_location_id, ledger, on_accept=on_accept)
    second = sut.intake(noisy, tenant_location_id, ledger, on_accept=on_accept)

    assert first["status"] == "accepted"
    assert second["status"] == "duplicate"
    assert ledger.count() == 1
    assert len(calls) == 1


def test_exclusive_create_claim_settles_a_same_submission_race(
        sut, load_fixture, make_ledger, tenant_location_id):
    # Two deliveries of one submission arriving together: the first claim wins, the
    # second exclusive-create returns None (the filesystem is the lock).
    ledger = make_ledger()
    canonical = sut.map_payload(load_fixture("convertflow_personal_counterintuitive.json"),
                                tenant_location_id).canonical
    job_key = sut.compute_job_key(canonical)

    first = ledger.claim(job_key, canonical)
    second = ledger.claim(job_key, canonical)

    assert first is not None
    assert second is None
    assert ledger.count() == 1


def test_failed_job_is_not_rerun_without_operator_retry(
        sut, load_fixture, make_ledger, tenant_location_id):
    ledger = make_ledger()
    calls, on_accept = _spy()
    payload = load_fixture("convertflow_personal_counterintuitive.json")

    first = sut.intake(payload, tenant_location_id, ledger, on_accept=on_accept)
    ledger.set_state(first["job"], "failed")

    # a plain redelivery after a three-strike failure must not re-run
    redeliver = sut.intake(copy.deepcopy(payload), tenant_location_id, ledger, on_accept=on_accept)
    assert redeliver["status"] == "duplicate"
    assert len(calls) == 1

    # an operator-sanctioned retry (retry: true) re-runs exactly once
    sanctioned = copy.deepcopy(payload)
    sanctioned["customData"]["retry"] = True
    retried = sut.intake(sanctioned, tenant_location_id, ledger, on_accept=on_accept)
    assert retried["status"] == "accepted"
    assert retried["job"] == first["job"]
    assert len(calls) == 2
    assert ledger.count() == 1


def test_test_flag_records_a_test_not_a_live_episode(
        sut, load_fixture, make_ledger, tenant_location_id):
    ledger = make_ledger()
    calls, on_accept = _spy()

    payload = load_fixture("convertflow_personal_counterintuitive.json")
    payload["customData"]["_test"] = True
    test_contact = payload["contact_id"]

    response = sut.intake(payload, tenant_location_id, ledger, on_accept=on_accept,
                          test_contact_id=test_contact)
    assert response["status"] == "accepted"
    record = ledger.read(response["job"])
    assert record["state"] == "test"

    # an identical test redelivery is still a duplicate: no second test record
    again = sut.intake(copy.deepcopy(payload), tenant_location_id, ledger,
                       on_accept=on_accept, test_contact_id=test_contact)
    assert again["status"] == "duplicate"
    assert ledger.count() == 1
