"""media.files.list requires the documented ``type`` query -- GHL-150.

Live evidence, 2026-10-19, tenant ``Mct54Bwi1KlNouGXQcDX``:
``GET /medias/files`` with no ``type`` answers 422
{"message":["type must be a string","type should not be empty"]}; with
``&type=file`` it answers 200 {files,count,traceId}.

These tests pin the pre-transport contract (omission and out-of-set value are
typed refusals with zero transport calls), the dispatch shape (GET, v3,
``type`` + bound ``locationId``), and the checked-in capability record (exactly
the six live-verified operations for the verified tenant, default-deny for
everything else and for any other tenant).  Every test is offline:
``FakeTransport`` records requests and replays scripted responses.
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
    Capability,
    CapabilityGate,
    capability_record_path,
    load_capability_record,
)
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.operations import (  # noqa: E402
    MEDIA_FILE_TYPES,
)
from cli_anything.gohighlevel.public.readback import ReadbackRegistry  # noqa: E402
from cli_anything.gohighlevel.public.result import Status  # noqa: E402
from cli_anything.gohighlevel.public.transport import encode_query  # noqa: E402

MEDIA_OPERATION = "media.files.list"
VERIFIED_TENANT = "Mct54Bwi1KlNouGXQcDX"
PREVIOUS_TENANT = "XCgFTEA1oDvsPnTqqgoB"
VERIFIED_OPERATIONS = frozenset(
    {
        "locations.get",
        "contacts.list",
        "contacts.search",
        "custom_fields.list",
        "pipelines.list",
        "media.files.list",
    }
)


def _enabled_gate(operation_id: str) -> CapabilityGate:
    gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
    gate.enable(
        Capability(
            operation_id=operation_id,
            contract_verified=True,
            adapter_built=True,
            offline_tests_passed=True,
            read_verified=True,
        ),
        write=False,
    )
    return gate


@unittest.skipUnless(REGISTRY_PRESENT, REGISTRY_REASON)
class RequiredQueryTest(unittest.TestCase):
    def adapter(self, transport: FakeTransport) -> PublicGhlAdapter:
        return PublicGhlAdapter(
            auth=fake_auth(),
            operations=FROZEN_OPERATIONS,
            transport=transport,
            capability=_enabled_gate(MEDIA_OPERATION),
            readbacks=ReadbackRegistry(),
        )

    def test_a_the_row_declares_type_as_required_and_closed(self) -> None:
        row = FROZEN_OPERATIONS[MEDIA_OPERATION]
        self.assertEqual(row.method, "GET")
        self.assertEqual(row.path_template, "/medias/files")
        self.assertEqual(row.version, "v3")
        self.assertEqual(row.required_query, ("type",))
        self.assertEqual(dict(row.query_enums), {"type": MEDIA_FILE_TYPES})
        self.assertEqual(
            MEDIA_FILE_TYPES, ("file", "image", "video", "audio", "document")
        )

    def test_b_omitting_type_fails_before_transport(self) -> None:
        transport = FakeTransport([resp(200)])
        adapter = self.adapter(transport)

        with self.assertRaises(ContractViolation) as caught:
            adapter.call(operation_id=MEDIA_OPERATION, tenant=fake_tenant())

        self.assertEqual(caught.exception.rule, "missing_required_query")
        self.assertEqual(caught.exception.detail, {"query": "type"})
        self.assertEqual(transport.call_count, 0)

    def test_c_a_blank_type_is_the_same_typed_refusal(self) -> None:
        transport = FakeTransport([resp(200)])
        adapter = self.adapter(transport)

        with self.assertRaises(ContractViolation) as caught:
            adapter.call(
                operation_id=MEDIA_OPERATION,
                tenant=fake_tenant(),
                query={"type": "   "},
            )

        self.assertEqual(caught.exception.rule, "missing_required_query")
        self.assertEqual(transport.call_count, 0)

    def test_d_type_file_reaches_transport_as_v3_get(self) -> None:
        transport = FakeTransport([resp(200, body=b'{"files":[],"count":0}')])
        adapter = self.adapter(transport)

        result = adapter.call(
            operation_id=MEDIA_OPERATION,
            tenant=fake_tenant(),
            query={"type": "file"},
        )

        self.assertIs(result.status, Status.ok)
        self.assertEqual(transport.call_count, 1)
        sent = transport.last
        self.assertEqual(sent["method"], "GET")
        self.assertEqual(sent["url"], "/medias/files")
        self.assertEqual(sent["version"], "v3")
        self.assertEqual(
            sent["query"],
            {"locationId": SYNTHETIC_TENANT, "type": "file"},
        )
        self.assertEqual(
            encode_query(sent["query"]),
            "locationId=" + SYNTHETIC_TENANT + "&type=file",
        )

    def test_e_an_out_of_set_type_is_refused_before_transport(self) -> None:
        for value in ("spreadsheet", "FILE", "", "file,image"):
            with self.subTest(value=value):
                transport = FakeTransport([resp(200)])
                adapter = self.adapter(transport)
                with self.assertRaises(ContractViolation) as caught:
                    adapter.call(
                        operation_id=MEDIA_OPERATION,
                        tenant=fake_tenant(),
                        query={"type": value},
                    )
                self.assertEqual(
                    caught.exception.rule,
                    "missing_required_query"
                    if not value.strip()
                    else "invalid_query_value",
                )
                self.assertEqual(transport.call_count, 0)

    def test_f_every_documented_type_dispatchable(self) -> None:
        for value in MEDIA_FILE_TYPES:
            with self.subTest(value=value):
                transport = FakeTransport([resp(200)])
                adapter = self.adapter(transport)
                result = adapter.call(
                    operation_id=MEDIA_OPERATION,
                    tenant=fake_tenant(),
                    query={"type": value},
                )
                self.assertIs(result.status, Status.ok)
                self.assertEqual(transport.last["query"]["type"], value)


@unittest.skipUnless(REGISTRY_PRESENT, REGISTRY_REASON)
class CheckedInRecordTest(unittest.TestCase):
    def test_a_exactly_the_six_verified_operations_are_admitted(self) -> None:
        gate = load_capability_record(tenant=VERIFIED_TENANT)

        self.assertEqual(len(gate), len(VERIFIED_OPERATIONS))
        for operation_id in VERIFIED_OPERATIONS:
            with self.subTest(operation_id=operation_id):
                capability = gate.get(operation_id)
                self.assertTrue(capability.enabled)
                self.assertTrue(capability.contract_verified)
                self.assertTrue(capability.adapter_built)
                self.assertTrue(capability.offline_tests_passed)
                self.assertTrue(capability.read_verified)
                self.assertEqual(capability.activation, ACTIVATION_VERIFIED)
                self.assertFalse(capability.provisional)
                self.assertTrue(capability.tenant_verified())

    def test_b_the_record_names_the_verified_tenant_and_evidence_date(self) -> None:
        with open(capability_record_path(), encoding="utf-8") as handle:
            document = json.load(handle)

        self.assertEqual(document["tenant"], VERIFIED_TENANT)
        self.assertEqual(
            set(document["capabilities"]), set(VERIFIED_OPERATIONS)
        )
        self.assertEqual(document["recorded_at"], "2026-10-19")
        self.assertIn("2026-10-19", document["note"])
        self.assertIn(VERIFIED_TENANT, document["note"])

    def test_c_everything_else_is_denied(self) -> None:
        gate = load_capability_record(tenant=VERIFIED_TENANT)

        for operation_id in (
            "contacts.get",
            "contacts.create",
            "custom_fields.get",
            "pipelines.get",
            "media.upload",
            "media.folders.create",
            "users.list",
        ):
            with self.subTest(operation_id=operation_id):
                capability = gate.get(operation_id)
                self.assertFalse(capability.enabled)
                self.assertFalse(capability.read_verified)
                self.assertIsNotNone(capability.activation_blocked)
                self.assertEqual(capability.activation, ACTIVATION_UNVERIFIED)

    def test_d_the_previous_tenant_still_fails_closed(self) -> None:
        transport = FakeTransport([resp(200)])
        adapter = PublicGhlAdapter(
            auth=fake_auth(location_id=PREVIOUS_TENANT),
            operations=FROZEN_OPERATIONS,
            transport=transport,
            readbacks=ReadbackRegistry(),
        )

        result = adapter.call(
            operation_id="contacts.list",
            tenant=fake_tenant(PREVIOUS_TENANT),
            query={"limit": 1},
        )

        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "capability_disabled")
        self.assertTrue(result.evidence["refused_before_transport"])
        self.assertEqual(transport.call_count, 0)

        # The loader itself is empty for the old tenant: the record is bound
        # to one tenant, and a mismatch is default-deny, not a warning.
        self.assertEqual(len(load_capability_record(tenant=PREVIOUS_TENANT)), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
