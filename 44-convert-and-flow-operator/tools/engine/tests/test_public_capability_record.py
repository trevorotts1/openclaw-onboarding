"""Checked-in capability record -- GHL-140.

The adapter used to consult an empty in-memory gate, so every representative
probe stopped before transport with ``capability_disabled``.  These tests pin
the replacement contract:

* a versioned, checked-in record plus the loader the adapter calls;
* default-deny for anything the record does not name;
* ``enabled=True`` still requires evidence (the __post_init__ invariant);
* an enabled record never claims a verified tenant: activation stays
  ``UNVERIFIED`` until a real 200 is observed, and the receipt says so;
* the three representative operations and ``locations.get`` reach transport;
* deleting a record entry flips the operation back to ``capability_disabled``.

Every test is offline: ``FakeTransport`` records requests, no socket opens.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    FROZEN_OPERATIONS,
    REGISTRY_PRESENT,
    REGISTRY_REASON,
    SYNTHETIC_TENANT,
    FakeTransport,
    fake_auth,
    fake_tenant,
    resp,
)

from cli_anything.gohighlevel.public.adapter import PublicGhlAdapter  # noqa: E402
from cli_anything.gohighlevel.public.capability import (  # noqa: E402
    ACTIVATION_UNVERIFIED,
    ACTIVATION_VERIFIED,
    CAPABILITY_RECORD_VERSION,
    Capability,
    CapabilityGate,
    capability_record_path,
    load_capability_record,
)
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.readback import ReadbackRegistry  # noqa: E402
from cli_anything.gohighlevel.public.result import Status  # noqa: E402

REPRESENTATIVE = ("contacts.list", "contacts.search", "custom_fields.list")
LOCATION_OPERATION = "locations.get"
CHECKED_IN_TENANT = "XCgFTEA1oDvsPnTqqgoB"


def _capability_row(**overrides: object) -> dict[str, object]:
    """Offline evidence complete, tenant read explicitly unproven."""

    row: dict[str, object] = {
        "contract_verified": True,
        "adapter_built": True,
        "offline_tests_passed": True,
        "read_verified": True,
        "canary_verified": False,
        "enabled": True,
        "activation": ACTIVATION_VERIFIED,
        "provisional": False,
    }
    row.update(overrides)
    return row


def _record(*operation_ids: str, tenant: str = SYNTHETIC_TENANT, **overrides: object):
    return {
        "record_version": CAPABILITY_RECORD_VERSION,
        "tenant": tenant,
        "capabilities": {
            operation_id: _capability_row(**overrides)
            for operation_id in operation_ids
        },
    }


class _RecordCase(unittest.TestCase):
    """Writes temporary records under the lane-prefixed temp prefix."""

    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp(prefix="ghl-140-", dir="/tmp")

    def tearDown(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)

    def write_record(self, document: object, name: str = "record.json") -> str:
        path = os.path.join(self._dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(document, handle)
        return path

    def adapter(self, path: str, transport: FakeTransport) -> PublicGhlAdapter:
        return PublicGhlAdapter(
            auth=fake_auth(),
            operations=FROZEN_OPERATIONS,
            transport=transport,
            capability_record=path,
            readbacks=ReadbackRegistry(),
        )


@unittest.skipUnless(REGISTRY_PRESENT, REGISTRY_REASON)
class RecordLoaderTest(_RecordCase):
    def test_a_missing_record_is_default_deny(self) -> None:
        transport = FakeTransport([resp(200)])
        adapter = self.adapter(os.path.join(self._dir, "absent.json"), transport)

        result = adapter.call(
            operation_id="contacts.search",
            tenant=fake_tenant(),
            body={"filters": []},
        )

        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "capability_disabled")
        self.assertTrue(result.evidence["refused_before_transport"])
        self.assertEqual(transport.call_count, 0)

    def test_the_record_version_is_enforced(self) -> None:
        document = _record("contacts.search")
        document["record_version"] = CAPABILITY_RECORD_VERSION + 1
        gate = load_capability_record(
            tenant=SYNTHETIC_TENANT, path=self.write_record(document)
        )
        self.assertEqual(len(gate), 0)
        self.assertFalse(gate.get("contacts.search").enabled)

    def test_a_tenant_mismatch_is_default_deny(self) -> None:
        path = self.write_record(_record("contacts.search", tenant="loc_other"))
        gate = load_capability_record(tenant=SYNTHETIC_TENANT, path=path)
        self.assertEqual(len(gate), 0)
        self.assertFalse(gate.get("contacts.search").enabled)

    def test_an_empty_capability_table_is_default_deny(self) -> None:
        document = _record()
        path = self.write_record(document)
        self.assertEqual(
            len(load_capability_record(tenant=SYNTHETIC_TENANT, path=path)), 0
        )

    def test_a_row_without_evidence_fails_the_whole_record(self) -> None:
        document = _record("contacts.search", "custom_fields.list")
        document["capabilities"]["custom_fields.list"] = {
            "contract_verified": True,
            "offline_tests_passed": True,
            "enabled": True,
            "provisional": True,
        }
        gate = load_capability_record(
            tenant=SYNTHETIC_TENANT, path=self.write_record(document)
        )
        self.assertEqual(len(gate), 0)
        self.assertFalse(gate.get("contacts.search").enabled)

    def test_an_unknown_row_field_is_refused(self) -> None:
        document = _record("contacts.search")
        document["capabilities"]["contacts.search"]["scope"] = "contacts.readonly"
        gate = load_capability_record(
            tenant=SYNTHETIC_TENANT, path=self.write_record(document)
        )
        self.assertEqual(len(gate), 0)

    def test_a_non_object_row_is_refused(self) -> None:
        document = _record("contacts.search")
        document["capabilities"]["contacts.search"] = ["enabled"]
        gate = load_capability_record(
            tenant=SYNTHETIC_TENANT, path=self.write_record(document)
        )
        self.assertEqual(len(gate), 0)


class CapabilityEvidenceInvariantTest(unittest.TestCase):
    def test_enabled_with_no_evidence_is_impossible(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            Capability(
                operation_id="contacts.search", enabled=True, provisional=True
            )
        self.assertEqual(caught.exception.rule, "enabled_without_evidence")

    def test_provisional_still_needs_every_offline_flag(self) -> None:
        for missing in (
            "contract_verified",
            "adapter_built",
            "offline_tests_passed",
        ):
            evidence = _capability_row()
            evidence.pop(missing)
            with self.subTest(missing=missing):
                with self.assertRaises(ContractViolation) as caught:
                    Capability(operation_id="contacts.search", **evidence)
                self.assertEqual(
                    caught.exception.rule, "enabled_without_evidence"
                )

    def test_a_verified_read_is_the_enabling_state(self) -> None:
        capability = Capability(
            operation_id="contacts.search", **_capability_row()
        )
        self.assertTrue(capability.enabled)
        self.assertTrue(capability.evidence_ok())
        self.assertFalse(capability.write_ready())
        self.assertTrue(capability.tenant_verified())
        self.assertEqual(capability.activation, ACTIVATION_VERIFIED)

    def test_provisional_without_a_verified_read_is_denied(self) -> None:
        # GU-004 3.2 rule 2, literally: there is no offline-only escape.
        with self.assertRaises(ContractViolation) as caught:
            Capability(
                operation_id="contacts.search",
                **_capability_row(
                    provisional=True,
                    read_verified=False,
                    activation=ACTIVATION_UNVERIFIED,
                ),
            )
        self.assertEqual(caught.exception.rule, "enabled_without_evidence")

    def test_verified_activation_demands_a_verified_read(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            Capability(
                operation_id="contacts.search",
                **_capability_row(
                    provisional=False,
                    read_verified=False,
                    activation=ACTIVATION_VERIFIED,
                ),
            )
        self.assertEqual(
            caught.exception.rule, "capability_verified_without_read"
        )

    def test_provisional_never_coexists_with_a_verified_read_or_canary(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            Capability(
                operation_id="contacts.search",
                **_capability_row(provisional=True, read_verified=True),
            )
        self.assertEqual(
            caught.exception.rule, "provisional_with_read_verified"
        )
        with self.assertRaises(ContractViolation) as caught:
            Capability(
                operation_id="contacts.search",
                **_capability_row(
                    provisional=True,
                    read_verified=False,
                    canary_verified=True,
                    activation=ACTIVATION_UNVERIFIED,
                ),
            )
        self.assertEqual(caught.exception.rule, "provisional_with_canary")

    def test_a_verified_read_is_the_only_state_that_claims_the_tenant(self) -> None:
        capability = Capability(
            operation_id="contacts.search",
            **_capability_row(
                provisional=False,
                read_verified=True,
                activation=ACTIVATION_VERIFIED,
            ),
        )
        self.assertTrue(capability.enabled)
        self.assertTrue(capability.evidence_ok())
        self.assertTrue(capability.tenant_verified())

    def test_a_provisional_row_cannot_be_placed_as_a_write_candidate(self) -> None:
        capability = Capability(
            operation_id="contacts.search", **_capability_row()
        )
        gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
        with self.assertRaises(ContractViolation) as caught:
            gate.put(capability, write=True)
        self.assertEqual(caught.exception.rule, "capability_canary_missing")


@unittest.skipUnless(REGISTRY_PRESENT, REGISTRY_REASON)
class AdapterReachesTransportTest(_RecordCase):
    def test_the_three_representative_operations_reach_transport(self) -> None:
        cases = {
            "contacts.list": {
                "method": "GET",
                "path": "/contacts/",
                "version": "2021-07-28",
                "path_params": None,
            },
            "contacts.search": {
                "method": "POST",
                "path": "/contacts/search",
                "version": "v3",
                "path_params": None,
            },
            "custom_fields.list": {
                "method": "GET",
                "path": "/locations/" + SYNTHETIC_TENANT + "/customFields",
                "version": "v3",
                "path_params": {"locationId": SYNTHETIC_TENANT},
            },
        }
        path = self.write_record(_record(*REPRESENTATIVE))

        for operation_id, expected in cases.items():
            with self.subTest(operation_id=operation_id):
                transport = FakeTransport([resp(200)])
                adapter = self.adapter(path, transport)

                result = adapter.call(
                    operation_id=operation_id,
                    tenant=fake_tenant(),
                    path_params=expected["path_params"],
                    body={"filters": []}
                    if operation_id == "contacts.search"
                    else None,
                )

                self.assertIs(result.status, Status.ok)
                self.assertEqual(transport.call_count, 1)
                sent = transport.last
                self.assertEqual(sent["method"], expected["method"])
                self.assertEqual(sent["url"], expected["path"])
                self.assertEqual(sent["version"], expected["version"])

    def test_locations_get_is_dispatchable(self) -> None:
        path = self.write_record(_record(LOCATION_OPERATION))
        transport = FakeTransport([resp(200)])
        adapter = self.adapter(path, transport)

        result = adapter.call(
            operation_id=LOCATION_OPERATION,
            tenant=fake_tenant(),
            path_params={"locationId": SYNTHETIC_TENANT},
        )

        self.assertIs(result.status, Status.ok)
        self.assertEqual(transport.call_count, 1)
        sent = transport.last
        self.assertEqual(sent["method"], "GET")
        self.assertEqual(sent["url"], "/locations/" + SYNTHETIC_TENANT)
        self.assertEqual(sent["version"], "2021-07-28")

    def test_the_receipt_surfaces_the_verified_read(self) -> None:
        path = self.write_record(_record("contacts.search"))
        transport = FakeTransport([resp(200)])
        adapter = self.adapter(path, transport)

        result = adapter.call(
            operation_id="contacts.search",
            tenant=fake_tenant(),
            body={"filters": []},
        )

        self.assertIs(result.status, Status.ok)
        self.assertEqual(
            result.evidence["capability"],
            {
                "operation_id": "contacts.search",
                "enabled": True,
                "activation": ACTIVATION_VERIFIED,
                "tenant_verified": True,
                "provisional": False,
                "observed_http_status": 200,
            },
        )

    def test_a_verified_record_is_the_only_one_that_reports_the_tenant(self) -> None:
        path = self.write_record(
            _record(
                "contacts.search",
                provisional=False,
                read_verified=True,
                activation=ACTIVATION_VERIFIED,
            )
        )
        transport = FakeTransport([resp(200)])
        adapter = self.adapter(path, transport)

        result = adapter.call(
            operation_id="contacts.search",
            tenant=fake_tenant(),
            body={"filters": []},
        )

        self.assertTrue(result.evidence["capability"]["tenant_verified"])
        self.assertEqual(
            result.evidence["capability"]["activation"], ACTIVATION_VERIFIED
        )

    def test_a_403_is_never_reported_as_success_or_verified(self) -> None:
        path = self.write_record(_record("contacts.search"))
        transport = FakeTransport([resp(403, body=b'{"message":"Forbidden"}')])
        adapter = self.adapter(path, transport)

        result = adapter.call(
            operation_id="contacts.search",
            tenant=fake_tenant(),
            body={"filters": []},
        )

        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "permission_denied")
        self.assertIn("contacts.readonly", result.error["scopes_candidate"])
        self.assertEqual(
            result.evidence["capability"]["activation"], ACTIVATION_UNVERIFIED
        )
        self.assertFalse(result.evidence["capability"]["tenant_verified"])

    def test_deleting_the_record_entry_flips_back_to_capability_disabled(self) -> None:
        path = self.write_record(_record("contacts.search"))
        reached = FakeTransport([resp(200)])
        adapter = self.adapter(path, reached)
        first = adapter.call(
            operation_id="contacts.search",
            tenant=fake_tenant(),
            body={"filters": []},
        )
        self.assertIs(first.status, Status.ok)
        self.assertEqual(reached.call_count, 1)

        # Negative control: the same call with the entry removed.
        blocked_path = self.write_record(_record(), name="negative.json")
        blocked = FakeTransport([resp(200)])
        adapter = self.adapter(blocked_path, blocked)
        second = adapter.call(
            operation_id="contacts.search",
            tenant=fake_tenant(),
            body={"filters": []},
        )

        self.assertIs(second.status, Status.denied)
        self.assertEqual(second.error["rule"], "capability_disabled")
        self.assertTrue(second.evidence["refused_before_transport"])
        self.assertEqual(blocked.call_count, 0)


@unittest.skipUnless(REGISTRY_PRESENT, REGISTRY_REASON)
class RegistryRowTest(unittest.TestCase):
    def test_locations_get_carries_its_own_documented_contract(self) -> None:
        self.assertIn(LOCATION_OPERATION, FROZEN_OPERATIONS)
        row = FROZEN_OPERATIONS[LOCATION_OPERATION]
        self.assertEqual(row.method, "GET")
        self.assertEqual(row.path_template, "/locations/{locationId}")
        self.assertEqual(row.version, "2021-07-28")
        self.assertEqual(row.tenant_binding, "path.locationId")
        self.assertEqual(row.scopes_candidate, ("locations.readonly",))
        self.assertFalse(row.write)
        self.assertEqual(row.documented_level, "D")

    def test_representative_rows_carry_their_documented_scopes(self) -> None:
        expected = {
            "contacts.list": ("contacts.readonly",),
            "contacts.search": ("contacts.readonly",),
            "custom_fields.list": ("locations/customFields.readonly",),
        }
        for operation_id, scopes in expected.items():
            with self.subTest(operation_id=operation_id):
                self.assertEqual(
                    FROZEN_OPERATIONS[operation_id].scopes_candidate, scopes
                )

    def test_no_version_is_applied_globally(self) -> None:
        versions = {
            FROZEN_OPERATIONS[operation_id].version
            for operation_id in (LOCATION_OPERATION, *REPRESENTATIVE)
        }
        self.assertEqual(versions, {"2021-07-28", "v3"})

    def test_the_checked_in_record_declares_rows_without_admitting_them(self) -> None:
        # GU-004 3.2 rule 2 is literal: no real 200 has been observed for this
        # tenant, so the checked-in record MUST NOT enable anything. It exists
        # so the loader and the operation rows are testable.
        gate = load_capability_record(tenant=CHECKED_IN_TENANT)
        for operation_id in (LOCATION_OPERATION, *REPRESENTATIVE):
            with self.subTest(operation_id=operation_id):
                capability = gate.get(operation_id)
                self.assertFalse(capability.enabled)
                self.assertFalse(capability.read_verified)
                self.assertFalse(capability.tenant_verified())
                self.assertFalse(capability.evidence_ok())
        # Default-deny is untouched for everything else.
        self.assertFalse(gate.get("contacts.get").enabled)
        self.assertIsNotNone(gate.get("contacts.get").activation_blocked)
        self.assertTrue(capability_record_path().is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
