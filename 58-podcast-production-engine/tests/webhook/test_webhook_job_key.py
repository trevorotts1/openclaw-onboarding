"""Independent check on the job-key module (design/webhook-design.md Section 3.1).

CHECKLIST Part C item 2 (job-key module with collision and divergence tests) and the
QC matrix row "Dedup and claim". The invariants proven here:

  - identical meaning across pipelines collides on the same key (dedup fires),
  - a genuinely changed answer diverges to a new key (a new episode, correctly),
  - volatile transport fields and non-hash canonical extras never affect the key,
  - the key is anchored to the contact and is a stable pd-<contact_id>-<16hex> shape.
"""

from __future__ import annotations

import copy
import re

import pytest

_KEY_SHAPE = re.compile(r"^pd-[A-Za-z0-9_-]+-[0-9a-f]{16}$")
_CONTACT_ID = "C0nTacT12345aBcDe"


def _canon(sut, load_fixture, name, tenant_location_id):
    return sut.map_payload(load_fixture(name), tenant_location_id).canonical


def test_job_key_shape(sut, load_fixture, tenant_location_id):
    canonical = _canon(sut, load_fixture, "convertflow_personal_counterintuitive.json",
                       tenant_location_id)
    key = sut.compute_job_key(canonical)
    assert _KEY_SHAPE.match(key), "unexpected job_key shape: " + key
    assert key.startswith("pd-" + _CONTACT_ID + "-")


def test_job_key_is_deterministic(sut, load_fixture, tenant_location_id):
    canonical = _canon(sut, load_fixture, "convertflow_personal_counterintuitive.json",
                       tenant_location_id)
    assert sut.compute_job_key(copy.deepcopy(canonical)) == sut.compute_job_key(copy.deepcopy(canonical))


def test_all_three_families_collide_on_one_key(sut, load_fixture, tenant_location_id):
    keys = {
        name: sut.compute_job_key(_canon(sut, load_fixture, name, tenant_location_id))
        for name in (
            "convertflow_personal_counterintuitive.json",
            "make_personal_counterintuitive.json",
            "n8n_personal_counterintuitive.json",
        )
    }
    distinct = set(keys.values())
    assert len(distinct) == 1, "families produced different job keys: " + repr(keys)


def test_changed_answer_diverges_to_a_new_key(sut, load_fixture, tenant_location_id):
    base = _canon(sut, load_fixture, "convertflow_personal_counterintuitive.json",
                  tenant_location_id)
    changed = copy.deepcopy(base)
    changed["q3_answer"] = base["q3_answer"] + " And I would do it again."
    base_key = sut.compute_job_key(base)
    changed_key = sut.compute_job_key(changed)
    assert changed_key != base_key
    # still the same person, so the contact anchor is unchanged
    assert changed_key.startswith("pd-" + _CONTACT_ID + "-")


def test_volatile_transport_fields_do_not_change_the_key(sut, load_fixture, tenant_location_id):
    payload = load_fixture("convertflow_personal_counterintuitive.json")
    base_key = sut.compute_job_key(sut.map_payload(payload, tenant_location_id).canonical)
    noisy = copy.deepcopy(payload)
    noisy["webhook_event_id"] = "evt-cf-999999"
    noisy["timestamp"] = "2026-07-06T18:45:12.777Z"
    noisy["retryCount"] = 4
    noisy["delivery_attempt"] = 3
    noisy_key = sut.compute_job_key(sut.map_payload(noisy, tenant_location_id).canonical)
    assert noisy_key == base_key


def test_non_hash_canonical_extras_do_not_change_the_key(sut, load_fixture, tenant_location_id):
    base = _canon(sut, load_fixture, "convertflow_personal_counterintuitive.json",
                  tenant_location_id)
    base_key = sut.compute_job_key(base)
    with_extras = copy.deepcopy(base)
    with_extras["writing_model"] = "glm-5.2"
    with_extras["web_research_tool"] = "Perplexity"
    with_extras["workflow_trigger"] = "04-Podcast is Completed"
    with_extras["retry"] = True
    with_extras["_test"] = True
    assert sut.compute_job_key(with_extras) == base_key


def test_key_is_anchored_to_the_contact(sut, load_fixture, tenant_location_id):
    base = _canon(sut, load_fixture, "convertflow_personal_counterintuitive.json",
                  tenant_location_id)
    other = copy.deepcopy(base)
    other["contact_id"] = "DiFfErEnT9contact"
    base_key = sut.compute_job_key(base)
    other_key = sut.compute_job_key(other)
    assert other_key != base_key
    assert other_key.startswith("pd-DiFfErEnT9contact-")


def test_missing_contact_id_cannot_be_keyed(sut, load_fixture, tenant_location_id):
    base = _canon(sut, load_fixture, "convertflow_personal_counterintuitive.json",
                  tenant_location_id)
    orphan = copy.deepcopy(base)
    orphan.pop("contact_id", None)
    with pytest.raises((ValueError, KeyError)):
        sut.compute_job_key(orphan)
