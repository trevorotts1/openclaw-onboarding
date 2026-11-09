"""WF01 capability evidence v2, exact failure classification and route decision.

Covers: A02, A03, A07, IG-AUTH-01..05, IG-ROUTE-01..05, IG-ROUTE-10.

The four fixtures under ``fixtures/wf01-cp01/`` are the frozen WF01-CP01
examples (public-enabled, beta-disabled, authorization-denied,
unknown-outcome).  Every test is offline: synthetic tenants, no socket.
"""

from __future__ import annotations

import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_TENANT,
    FakeTransport,
    Row,
    fake_auth,
    fake_tenant,
    registry,
    resp,
)

from cli_anything.gohighlevel.public.adapter import PublicGhlAdapter  # noqa: E402
from cli_anything.gohighlevel.public.capability import (  # noqa: E402
    ACTIVATION_VERIFIED,
    ACTIVATION_UNVERIFIED,
    CAPABILITY_RECORD_VERSION,
    CAPABILITY_RECORD_VERSION_V2,
    CanaryAdmission,
    Capability,
    CapabilityCache,
    CapabilityGate,
    CapabilityRecordV2,
    classify_failure,
    decide_route,
    load_capability_records_v2,
    resolve_capability,
    translate_capability_document,
)
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.result import Status  # noqa: E402

FIXTURES = os.path.join(_HERE, "fixtures", "wf01-cp01")


def fixture(name: str) -> dict:
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as handle:
        return json.load(handle)


def record_from(document: dict) -> CapabilityRecordV2:
    return CapabilityRecordV2(**document["record"])


class FrozenFixtureTests(unittest.TestCase):
    """The four WF01-CP01 fixtures, driven through the frozen interface."""

    def test_public_enabled_resolves_allow_and_public_rest(self) -> None:
        case = fixture("public_enabled")
        record = record_from(case)
        resolution = resolve_capability(
            record=record,
            tenant=record.location_id,
            operation_id=record.operation_id,
            write=case["resolve"]["write"],
            route_class=case["resolve"]["route_class"],
        )
        self.assertEqual(resolution.decision, case["expect"]["decision"])
        decision = decide_route(resolution=resolution, caller="cli_worker")
        self.assertEqual(decision.route, case["expect"]["route"])
        self.assertFalse(decision.must_reconcile)
        # A read never admits the corresponding write (IG-AUTH-03).
        write_resolution = resolve_capability(
            record=record,
            tenant=record.location_id,
            operation_id=record.operation_id,
            write=True,
        )
        self.assertEqual(write_resolution.decision, case["expect"]["write_decision"])
        self.assertFalse(record.write_admitted())

    def test_beta_disabled_classifies_and_selects_private_fallback(self) -> None:
        case = fixture("beta_disabled")
        failure = classify_failure(
            http_status=case["http_status"], body=case["body"], write=True
        )
        self.assertEqual(failure.kind, case["expect"]["classification"])
        self.assertTrue(failure.fallback_allowed)
        record = record_from(case)
        resolution = resolve_capability(
            record=record, tenant=record.location_id, operation_id=record.operation_id
        )
        self.assertEqual(resolution.decision, case["expect"]["resolve_decision"])
        decision = decide_route(resolution=resolution, failure=failure)
        self.assertEqual(decision.route, case["expect"]["route"])
        self.assertEqual(
            decision.evidence["failure_classification"]["provider_code"],
            "WORKFLOW_API_NOT_ENABLED_FOR_LOCATION",
        )

    def test_authorization_denied_is_never_a_fallback(self) -> None:
        case = fixture("authorization_denied")
        failure = classify_failure(
            http_status=case["http_status"], body=case["body"], write=True
        )
        self.assertEqual(failure.kind, case["expect"]["classification"])
        self.assertFalse(failure.fallback_allowed)
        record = record_from(case)
        resolution = resolve_capability(
            record=record, tenant=record.location_id, operation_id=record.operation_id,
            write=True,
        )
        decision = decide_route(resolution=resolution, failure=failure)
        self.assertEqual(decision.route, case["expect"]["route"])
        # The record itself is bound to a missing scope: still deny, still no route.
        self.assertEqual(resolution.decision, case["expect"]["resolve_decision"])

    def test_unknown_outcome_reconciles_without_rail_switch(self) -> None:
        case = fixture("unknown_outcome")
        failure = classify_failure(
            http_status=None,
            transport_error=case["transport_error"],
            write=case["write"],
        )
        self.assertEqual(failure.kind, case["expect"]["classification"])
        record = record_from(case)
        resolution = resolve_capability(
            record=record, tenant=record.location_id, operation_id=record.operation_id,
            write=True,
        )
        self.assertEqual(resolution.decision, case["expect"]["resolve_decision"])
        decision = decide_route(resolution=resolution, failure=failure)
        self.assertEqual(decision.route, case["expect"]["route"])
        self.assertEqual(decision.must_reconcile, case["expect"]["must_reconcile"])


class ClassificationTests(unittest.TestCase):
    """IG-AUTH-05: missing scopes and vendor feature-disabled errors stay apart."""

    def test_beta_is_not_a_bad_token(self) -> None:
        beta = classify_failure(
            http_status=403,
            body=b'{"code":"WORKFLOW_API_NOT_ENABLED_FOR_LOCATION"}',
        )
        unauthorized = classify_failure(http_status=401, body=b"{}")
        self.assertEqual(beta.kind, "beta_not_enabled")
        self.assertEqual(unauthorized.kind, "unauthorized")
        self.assertNotEqual(beta.kind, unauthorized.kind)

    def test_scope_and_role_are_distinct_from_beta(self) -> None:
        scope = classify_failure(
            http_status=403, body=b'{"message":"insufficient scope: contacts.write"}'
        )
        role = classify_failure(
            http_status=403, body=b'{"message":"the user role may not do this"}'
        )
        generic = classify_failure(http_status=403, body=b"{}")
        self.assertEqual(scope.kind, "missing_scope")
        self.assertEqual(role.kind, "wrong_role")
        self.assertEqual(generic.kind, "forbidden")
        for item in (scope, role, generic):
            self.assertFalse(item.fallback_allowed)

    def test_no_secret_or_body_echoed_in_classification(self) -> None:
        failure = classify_failure(
            http_status=403,
            body=b'{"message":"denied","authorization":"Bearer synthetic-secret-value"}',
        )
        blob = json.dumps(failure.as_evidence())
        self.assertNotIn("synthetic-secret-value", blob)


class RecordTranslationTests(unittest.TestCase):
    """v1 -> v2 translation: never widens a grant."""

    def _document(self, **row: object) -> dict:
        base = {
            "contract_verified": True,
            "adapter_built": True,
            "offline_tests_passed": True,
            "read_verified": True,
            "canary_verified": False,
            "enabled": True,
            "activation": ACTIVATION_VERIFIED,
        }
        base.update(row)
        return {
            "record_version": CAPABILITY_RECORD_VERSION,
            "tenant": SYNTHETIC_TENANT,
            "capabilities": {"contacts.list": base},
        }

    def test_enabled_v1_row_translates_enabled_read(self) -> None:
        rows = translate_capability_document(
            self._document(), tenant=SYNTHETIC_TENANT, contract_revision="rev1"
        )
        record = rows["contacts.list"]
        self.assertEqual(record.record_version, CAPABILITY_RECORD_VERSION_V2)
        self.assertTrue(record.enabled)
        self.assertTrue(record.read_admitted())
        self.assertFalse(record.write_admitted())
        # Dimensions v1 never measured stay unknown, never "available".
        self.assertEqual(record.availability, "unknown")
        self.assertEqual(record.scope_state, "unverified")

    def test_v1_row_without_evidence_translates_disabled(self) -> None:
        rows = translate_capability_document(
            self._document(read_verified=False), tenant=SYNTHETIC_TENANT
        )
        record = rows["contacts.list"]
        self.assertFalse(record.enabled)
        self.assertFalse(record.read_admitted())

    def test_v1_blocked_row_stays_disabled(self) -> None:
        document = self._document()
        document["capabilities"]["contacts.list"]["activation_blocked"] = {
            "reason": "r",
            "owner": "o",
            "unblock": "u",
        }
        rows = translate_capability_document(document, tenant=SYNTHETIC_TENANT)
        self.assertFalse(rows["contacts.list"].enabled)

    def test_v2_loader_accepts_v1_file_and_refuses_other_tenant(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "record.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self._document(), handle)
            loaded = load_capability_records_v2(tenant=SYNTHETIC_TENANT, path=path)
            self.assertIn("contacts.list", loaded)
            self.assertEqual(
                load_capability_records_v2(tenant="loc_other", path=path), {}
            )

    def test_unknown_record_version_fails_closed(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "record.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"record_version": 99, "tenant": SYNTHETIC_TENANT}, handle)
            self.assertEqual(
                load_capability_records_v2(tenant=SYNTHETIC_TENANT, path=path), {}
            )


class CacheTests(unittest.TestCase):
    """Configurable bounded cache with rotation/schema invalidation (IG-AUTH-04)."""

    def _record(self, **overrides: object) -> CapabilityRecordV2:
        payload = {
            "location_id": SYNTHETIC_TENANT,
            "operation_id": "contacts.list",
            "contract_revision": "rev1",
            "credential_fingerprint": "cred-one",
            "effective_grant_fingerprint": "grant-one",
            "documented": True,
            "adapter_built": True,
            "offline_tests_passed": True,
            "read_probe": {"state": "passed", "receipt_id": "r"},
            "enabled": True,
        }
        payload.update(overrides)
        return CapabilityRecordV2(**payload)

    def test_ttl_expiry(self) -> None:
        cache = CapabilityCache(ttl_s=10, max_entries=4)
        cache.put(self._record(), now=0.0)
        self.assertIsNotNone(cache.get(SYNTHETIC_TENANT, "contacts.list", now=5.0))
        self.assertIsNone(cache.get(SYNTHETIC_TENANT, "contacts.list", now=11.0))

    def test_credential_rotation_invalidates_only_its_entries(self) -> None:
        cache = CapabilityCache(ttl_s=60, max_entries=4)
        cache.put(self._record(), now=0.0)
        cache.put(
            self._record(operation_id="contacts.get", credential_fingerprint="cred-two"),
            now=0.0,
        )
        cache.put(
            self._record(operation_id="contacts.search", credential_fingerprint="cred-one"),
            now=0.0,
        )
        # A lookup bound to the new credential must not reuse cred-one evidence.
        self.assertIsNone(
            cache.get(
                SYNTHETIC_TENANT,
                "contacts.list",
                now=1.0,
                credential_fingerprint="cred-two",
            )
        )
        self.assertIsNotNone(cache.get(SYNTHETIC_TENANT, "contacts.get", now=1.0))
        dropped = cache.invalidate_credential(
            tenant=SYNTHETIC_TENANT, credential_fingerprint="cred-two"
        )
        # Only cred-two's row goes; cred-one evidence for another operation stays.
        self.assertEqual(dropped, 1)
        self.assertEqual(len(cache), 1)
        self.assertIsNotNone(cache.get(SYNTHETIC_TENANT, "contacts.search", now=2.0))

    def test_contract_hash_change_drops_only_that_revision(self) -> None:
        cache = CapabilityCache(ttl_s=60, max_entries=4)
        cache.put(self._record(), now=0.0)
        self.assertEqual(
            cache.invalidate_contract(tenant=SYNTHETIC_TENANT, contract_revision="rev2"),
            0,
        )
        self.assertEqual(
            cache.invalidate_contract(tenant=SYNTHETIC_TENANT, contract_revision="rev1"),
            1,
        )

    def test_invalidated_entry_is_not_served(self) -> None:
        cache = CapabilityCache(ttl_s=60, max_entries=4)
        cache.put(self._record(), now=0.0)
        cache.invalidate(
            tenant=SYNTHETIC_TENANT, operation_id="contacts.list", reason="rotation"
        )
        self.assertIsNone(cache.get(SYNTHETIC_TENANT, "contacts.list", now=1.0))

    def test_cache_is_bounded(self) -> None:
        cache = CapabilityCache(ttl_s=60, max_entries=2)
        cache.put(self._record(), now=0.0)
        cache.put(self._record(operation_id="b"), now=0.0)
        cache.put(self._record(operation_id="c"), now=0.0)
        self.assertEqual(len(cache), 2)


class IdentityBindingTests(unittest.TestCase):
    """IG-AUTH-01/02 and the pre-network refusals."""

    def test_location_principal_mismatch_refused_before_network(self) -> None:
        case = fixture("public_enabled")
        record = record_from(case)
        resolution = resolve_capability(
            record=record,
            tenant="loc_other",
            operation_id=record.operation_id,
        )
        self.assertEqual(resolution.decision, "deny")
        self.assertEqual(resolution.reason, "location_principal_mismatch")

    def test_credential_classes_cannot_be_substituted(self) -> None:
        from cli_anything.gohighlevel.public.auth import AuthKind, resolve_auth

        with self.assertRaises(ContractViolation) as caught:
            resolve_auth(kind="agency_pit", env={})
        self.assertEqual(caught.exception.rule, "agency_auth_unmapped")

        # The adapter refuses a credential class its row does not allow, before
        # transport: a Firebase token never stands in for a location PIT.
        adapter = PublicGhlAdapter(
            auth=fake_auth(kind=AuthKind.firebase_internal),
            operations=registry(
                Row("contacts.list", method="GET", path_template="/contacts/")
            ),
            transport=FakeTransport(),
            capability=CapabilityGate(tenant=SYNTHETIC_TENANT),
        )
        result = adapter.call(
            operation_id="contacts.list", tenant=fake_tenant(), query={"locationId": SYNTHETIC_TENANT}
        )
        self.assertEqual(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "auth_kind_not_allowed")
        self.assertTrue(result.evidence["refused_before_transport"])

    def test_read_evidence_never_enables_a_write(self) -> None:
        record = CapabilityRecordV2(
            location_id=SYNTHETIC_TENANT,
            operation_id="contacts.create",
            contract_revision="rev1",
            documented=True,
            adapter_built=True,
            offline_tests_passed=True,
            read_probe={"state": "passed", "receipt_id": "r"},
            enabled=True,
        )
        self.assertTrue(record.read_admitted())
        self.assertFalse(record.write_admitted())
        resolution = resolve_capability(
            record=record, tenant=SYNTHETIC_TENANT, operation_id="contacts.create", write=True
        )
        self.assertEqual(resolution.decision, "canary_required")
        self.assertEqual(resolution.reason, "write_canary_absent")


class CanaryAdmissionTests(unittest.TestCase):
    """First canary is possible without enabling every operation globally."""

    def _record(self, **overrides: object) -> CapabilityRecordV2:
        payload = {
            "location_id": SYNTHETIC_TENANT,
            "operation_id": "workflows.definition.create",
            "contract_revision": "rev1",
            "credential_fingerprint": "cred-one",
            "documented": True,
            "adapter_built": True,
            "offline_tests_passed": True,
            "read_probe": {"state": "passed", "receipt_id": "r"},
            "enabled": True,
        }
        payload.update(overrides)
        return CapabilityRecordV2(**payload)

    def test_admits_one_bounded_canary(self) -> None:
        admission = CanaryAdmission(
            operation_id="workflows.definition.create",
            tenant=SYNTHETIC_TENANT,
            authorized_by="operator",
            contract_revision="rev1",
            credential_fingerprint="cred-one",
        )
        admitted, reason = admission.admit(self._record())
        self.assertTrue(admitted, reason)
        with self.assertRaises(ContractViolation):
            CanaryAdmission(
                operation_id="workflows.definition.create",
                tenant=SYNTHETIC_TENANT,
                authorized_by="operator",
                contract_revision="rev1",
                max_attempts=5,
            )

    def test_refuses_blocked_or_mismatched_records(self) -> None:
        admission = CanaryAdmission(
            operation_id="workflows.definition.create",
            tenant=SYNTHETIC_TENANT,
            authorized_by="operator",
            contract_revision="rev1",
        )
        self.assertEqual(
            admission.admit(self._record(contract_revision="rev2"))[1],
            "contract_revision_mismatch",
        )
        self.assertEqual(
            admission.admit(
                self._record(scope_state="missing_scope", enabled=False)
            )[1],
            "missing_scope",
        )
        self.assertEqual(
            admission.admit(
                self._record(availability="beta_not_enabled", enabled=False)
            )[1],
            "beta_not_enabled",
        )
        self.assertEqual(admission.admit(None)[1], "capability_record_absent")

    def test_successful_canary_is_evidence_not_global_enablement(self) -> None:
        record = self._record()
        proven = record.with_canary(state="passed", receipt_id="gxo_res_canary")
        self.assertTrue(proven.write_admitted())
        self.assertFalse(record.write_admitted())


class GateIntegrationTests(unittest.TestCase):
    """The v1 gate still refuses a write without canary evidence."""

    def test_v2_to_gate_never_widens(self) -> None:
        record = CapabilityRecordV2(
            location_id=SYNTHETIC_TENANT,
            operation_id="contacts.create",
            contract_revision="rev1",
            documented=True,
            adapter_built=True,
            offline_tests_passed=True,
            read_probe={"state": "passed", "receipt_id": "r"},
            enabled=True,
        )
        capability = record.to_gate_capability()
        self.assertTrue(capability.enabled)
        self.assertFalse(capability.canary_verified)
        self.assertEqual(capability.activation, ACTIVATION_VERIFIED)
        gate = CapabilityGate({"contacts.create": capability}, tenant=SYNTHETIC_TENANT)
        self.assertFalse(gate.get("contacts.create").write_ready())

    def test_unproven_read_stays_unverified(self) -> None:
        record = CapabilityRecordV2(
            location_id=SYNTHETIC_TENANT,
            operation_id="contacts.list",
            contract_revision="rev1",
            documented=True,
            adapter_built=True,
            offline_tests_passed=True,
            enabled=True,
        )
        capability = record.to_gate_capability()
        self.assertFalse(capability.enabled)
        self.assertEqual(capability.activation, ACTIVATION_UNVERIFIED)


if __name__ == "__main__":
    unittest.main()
