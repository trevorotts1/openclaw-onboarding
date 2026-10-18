"""Public adapter contract -- GU-004 sections 1.2-1.5 and 2.4.

Proves, entirely offline:

* there is no global version default anywhere in the public package, and the
  package imports nothing from ``utils/ghl_client.py`` (freeze rule 7.3);
* the ``Version`` header for a call equals that operation row's literal, and a
  second operation sends its own literal;
* tenant and auth-kind refusals happen before transport;
* a write without a readback plan never reaches transport;
* approval is required exactly where the row says so.
"""

from __future__ import annotations

import os
import re
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    FROZEN_OPERATIONS,
    REGISTRY_PRESENT,
    REGISTRY_REASON,
    SYNTHETIC_APPROVAL,
    SYNTHETIC_CONTACT,
    SYNTHETIC_OTHER_TENANT,
    SYNTHETIC_TENANT,
    FakeTransport,
    RecordingOpener,
    StubResponse,
    approval,
    enabled_gate,
    fake_auth,
    fake_tenant,
    issue_key,
    make_adapter,
    readback_spec,
    registry,
    resp,
    row,
)

from cli_anything.gohighlevel.public.adapter import ApprovalRef  # noqa: E402
from cli_anything.gohighlevel.public.auth import AuthKind  # noqa: E402
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.readback import ReadbackRegistry  # noqa: E402
from cli_anything.gohighlevel.public.result import Status  # noqa: E402
from cli_anything.gohighlevel.public.transport import RequestsTransport  # noqa: E402

_ENGINE_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
_PUBLIC_DIR = os.path.join(
    _ENGINE_ROOT, "cli_anything", "gohighlevel", "public"
)

_READ_ROW = row(
    "contacts.get",
    method="GET",
    path_template="/contacts/{contactId}",
    tenant_binding="path.contactId",
)
_READBACK_ROW = row(
    "contacts.get",
    method="GET",
    path_template="/contacts/{contactId}",
    tenant_binding="path.contactId",
)
_WRITE_ROW = row(
    "contacts.upsert",
    method="POST",
    path_template="/contacts/upsert",
    write=True,
    tenant_binding="body.locationId",
)


def _public_sources() -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    for name in sorted(os.listdir(_PUBLIC_DIR)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(_PUBLIC_DIR, name), encoding="utf-8") as handle:
            sources.append((name, handle.read()))
    return sources


class NoGlobalVersionDefaultTest(unittest.TestCase):
    def test_package_source_has_no_prefix_map_or_default_version(self) -> None:
        sources = _public_sources()
        self.assertTrue(sources, "public package source must be readable")
        for name, text in sources:
            self.assertNotIn("VERSION_MAP", text, f"{name} must not carry a prefix map")
            self.assertNotIn(
                "DEFAULT_VERSION", text, f"{name} must not carry a default version"
            )

    def test_no_module_level_version_literal(self) -> None:
        # A module-level constant whose *name* carries VERSION and whose value
        # is a version literal is the forbidden global default (freeze 1.3
        # step 3).  Date constants such as DOC_FETCH_DATE are not versions.
        literal = re.compile(
            r"^[A-Z][A-Z0-9_]*VERSION[A-Z0-9_]*\s*=\s*['\"]"
            r"(?:v\d+|legacy|\d{4}-\d{2}-\d{2})['\"]",
            re.MULTILINE,
        )
        for name, text in _public_sources():
            match = literal.search(text)
            self.assertIsNone(
                match,
                f"{name} declares a module-level version constant: {match.group(0) if match else ''}",
            )

    def test_public_package_does_not_import_ghl_client(self) -> None:
        for name, text in _public_sources():
            self.assertNotIn(
                "ghl_client", text, f"{name} must not reference utils/ghl_client.py"
            )

    def test_package_exports_exactly_the_frozen_surface(self) -> None:
        import cli_anything.gohighlevel.public as public

        self.assertEqual(
            list(public.__all__),
            ["PublicGhlAdapter", "OperationResult", "Capability"],
        )


class PerOperationVersionHeaderTest(unittest.TestCase):
    def _adapter(self, operations, transport):
        return make_adapter(
            transport, operations, gate=enabled_gate(list(operations.values()))
        )

    def test_each_operation_sends_its_own_row_version(self) -> None:
        contacts = row(
            "contacts.get",
            method="GET",
            path_template="/contacts/{contactId}",
            version="v3",
            tenant_binding="path.contactId",
        )
        products = row(
            "products.list",
            method="GET",
            path_template="/products/",
            version="2021-07-28",
            version_alternates=("v3",),
            tenant_binding="query.locationId",
        )
        operations = registry(contacts, products)
        transport = FakeTransport([resp(200), resp(200)])
        adapter = self._adapter(operations, transport)
        tenant = fake_tenant()

        first = adapter.call(
            operation_id="contacts.get",
            tenant=tenant,
            path_params={"contactId": SYNTHETIC_CONTACT},
        )
        second = adapter.call(operation_id="products.list", tenant=tenant)

        self.assertEqual(transport.requests[0]["version"], "v3")
        self.assertEqual(transport.requests[1]["version"], "2021-07-28")
        self.assertEqual(first.version_header, "v3")
        self.assertEqual(second.version_header, "2021-07-28")
        self.assertEqual(first.evidence["version_header"], "v3")
        self.assertEqual(second.evidence["version_header"], "2021-07-28")

    def test_version_alternates_never_become_the_header(self) -> None:
        products = row(
            "products.list",
            method="GET",
            path_template="/products/",
            version="v3",
            version_alternates=("2021-07-28",),
            tenant_binding="query.locationId",
        )
        operations = registry(products)
        transport = FakeTransport([resp(200)])
        adapter = self._adapter(operations, transport)

        adapter.call(operation_id="products.list", tenant=fake_tenant())

        self.assertEqual(transport.last["version"], "v3")
        self.assertNotIn(transport.last["version"], products.version_alternates)

    def test_row_with_no_version_sends_no_version(self) -> None:
        mcp = row(
            "mcp.list_locations",
            method="POST",
            path_template="/mcp",
            version=None,
            route_class="official_mcp",
        )
        operations = registry(mcp)
        transport = FakeTransport([resp(200)])
        adapter = self._adapter(operations, transport)

        result = adapter.call(operation_id="mcp.list_locations", tenant=fake_tenant())

        self.assertIsNone(transport.last["version"])
        self.assertIsNone(result.version_header)
        self.assertIsNone(result.evidence["version_header"])

    def test_request_object_carries_the_row_version_and_no_smuggled_one(self) -> None:
        contacts = row(
            "contacts.get",
            method="GET",
            path_template="/contacts/{contactId}",
            version="2021-07-28",
            tenant_binding="path.contactId",
        )
        operations = registry(contacts)
        opener = RecordingOpener(StubResponse())
        transport = RequestsTransport(
            base_url="https://example.invalid", opener=opener
        )
        adapter = make_adapter(
            transport,  # type: ignore[arg-type]
            operations,
            gate=enabled_gate(list(operations.values())),
        )

        adapter.call(
            operation_id="contacts.get",
            tenant=fake_tenant(),
            path_params={"contactId": SYNTHETIC_CONTACT},
        )

        built = opener.last
        self.assertEqual(built.headers["Version"], "2021-07-28")

    def test_transport_drops_a_caller_supplied_version_header(self) -> None:
        opener = RecordingOpener(StubResponse())
        transport = RequestsTransport(
            base_url="https://example.invalid", opener=opener
        )

        transport.request(
            method="GET",
            url="/contacts/x",
            version="v3",
            headers={"Version": "2021-07-28", "Authorization": "Bearer synthetic"},
            query=None,
            body=None,
            timeout_s=1.0,
        )

        self.assertEqual(opener.last.headers["Version"], "v3")


class RefusalBeforeTransportTest(unittest.TestCase):
    def test_auth_kind_not_allowed(self) -> None:
        operations = registry(_READ_ROW)
        transport = FakeTransport([resp(200)])
        adapter = make_adapter(
            transport,
            operations,
            auth=fake_auth(kind=AuthKind.oauth),
            gate=enabled_gate(list(operations.values())),
        )

        result = adapter.call(
            operation_id="contacts.get",
            tenant=fake_tenant(),
            path_params={"contactId": SYNTHETIC_CONTACT},
        )

        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "auth_kind_not_allowed")
        self.assertTrue(result.evidence["refused_before_transport"])
        self.assertEqual(transport.call_count, 0)

    def test_tenant_mismatch_under_location_pit(self) -> None:
        operations = registry(_READ_ROW)
        transport = FakeTransport([resp(200)])
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
        )

        result = adapter.call(
            operation_id="contacts.get",
            tenant=fake_tenant(SYNTHETIC_OTHER_TENANT),
            path_params={"contactId": SYNTHETIC_CONTACT},
        )

        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "tenant_mismatch")
        self.assertEqual(transport.call_count, 0)

    def test_path_tenant_binding_mismatch(self) -> None:
        located = row(
            "custom_fields.list",
            method="GET",
            path_template="/locations/{locationId}/customFields",
            tenant_binding="path.locationId",
        )
        operations = registry(located)
        transport = FakeTransport([resp(200)])
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
        )

        result = adapter.call(
            operation_id="custom_fields.list",
            tenant=fake_tenant(),
            path_params={"locationId": SYNTHETIC_OTHER_TENANT},
        )

        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "tenant_mismatch")
        self.assertEqual(transport.call_count, 0)

    def test_body_tenant_binding_refuses_a_conflicting_location(self) -> None:
        operations = registry(_WRITE_ROW)
        transport = FakeTransport([resp(200), resp(200)])
        readbacks = ReadbackRegistry()
        readbacks.register(readback_spec())
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
            readbacks=readbacks,
        )

        result = adapter.call(
            operation_id="contacts.upsert",
            tenant=fake_tenant(),
            body={"locationId": SYNTHETIC_OTHER_TENANT, "email": "a@example.invalid"},
            idempotency_key=issue_key("contacts.upsert"),
            readback=readback_spec(),
        )

        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "tenant_mismatch")
        self.assertEqual(transport.call_count, 0)

    def test_body_tenant_binding_is_injected_once(self) -> None:
        operations = registry(_WRITE_ROW, _READBACK_ROW)
        transport = FakeTransport([resp(200), resp(200, b'{"id":"contact_synthetic_0001"}')])
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
        )

        result = adapter.call(
            operation_id="contacts.upsert",
            tenant=fake_tenant(),
            body={"email": "a@example.invalid"},
            idempotency_key=issue_key("contacts.upsert"),
            readback=readback_spec(),
        )

        self.assertIs(result.status, Status.ok)
        self.assertEqual(transport.requests[0]["body"]["locationId"], SYNTHETIC_TENANT)

    def test_unknown_operation_id_never_reaches_transport(self) -> None:
        operations = registry(_READ_ROW)
        transport = FakeTransport([resp(200)])
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
        )

        with self.assertRaises(ContractViolation) as caught:
            adapter.call(operation_id="contacts.not_a_row", tenant=fake_tenant())

        self.assertEqual(caught.exception.rule, "unknown_operation_id")
        self.assertEqual(transport.call_count, 0)

    def test_path_param_mismatch_never_reaches_transport(self) -> None:
        operations = registry(_READ_ROW)
        transport = FakeTransport([resp(200)])
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
        )

        with self.assertRaises(ContractViolation) as caught:
            adapter.call(
                operation_id="contacts.get",
                tenant=fake_tenant(),
                path_params={"contactId": SYNTHETIC_CONTACT, "extra": "x"},
            )

        self.assertEqual(caught.exception.rule, "path_params_mismatch")
        self.assertEqual(transport.call_count, 0)


class ReadbackRequiredBeforeTransportTest(unittest.TestCase):
    def test_write_without_a_readback_plan_is_refused(self) -> None:
        operations = registry(_WRITE_ROW, _READBACK_ROW)
        transport = FakeTransport([resp(200), resp(200)])
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
            readbacks=ReadbackRegistry(),
        )

        with self.assertRaises(ContractViolation) as caught:
            adapter.call(
                operation_id="contacts.upsert",
                tenant=fake_tenant(),
                body={"email": "a@example.invalid"},
                idempotency_key=issue_key("contacts.upsert"),
            )

        self.assertEqual(caught.exception.rule, "readback_required")
        self.assertEqual(transport.call_count, 0)

    def test_a_read_may_not_carry_a_readback(self) -> None:
        operations = registry(_READ_ROW, _READBACK_ROW)
        transport = FakeTransport([resp(200)])
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
        )

        with self.assertRaises(ContractViolation) as caught:
            adapter.call(
                operation_id="contacts.get",
                tenant=fake_tenant(),
                path_params={"contactId": SYNTHETIC_CONTACT},
                readback=readback_spec(),
            )

        self.assertEqual(caught.exception.rule, "readback_not_allowed_for_read")
        self.assertEqual(transport.call_count, 0)

    def test_write_requires_an_idempotency_key(self) -> None:
        operations = registry(_WRITE_ROW, _READBACK_ROW)
        transport = FakeTransport([resp(200), resp(200)])
        readbacks = ReadbackRegistry()
        readbacks.register(readback_spec())
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
            readbacks=readbacks,
        )

        with self.assertRaises(ContractViolation) as caught:
            adapter.call(
                operation_id="contacts.upsert",
                tenant=fake_tenant(),
                body={"email": "a@example.invalid"},
                readback=readback_spec(),
            )

        self.assertEqual(caught.exception.rule, "idempotency_key_required")
        self.assertEqual(transport.call_count, 0)


class ApprovalRequiredTest(unittest.TestCase):
    def _adapter(self):
        approved = row(
            "contacts.delete",
            method="DELETE",
            path_template="/contacts/{contactId}",
            write=True,
            approval_required=True,
            tenant_binding="path.contactId",
        )
        operations = registry(approved, _READBACK_ROW)
        transport = FakeTransport([resp(200), resp(200, b'{"id":"contact_synthetic_0001"}')])
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
        )
        return adapter, transport

    def test_missing_approval_is_refused_before_transport(self) -> None:
        adapter, transport = self._adapter()

        with self.assertRaises(ContractViolation) as caught:
            adapter.call(
                operation_id="contacts.delete",
                tenant=fake_tenant(),
                path_params={"contactId": SYNTHETIC_CONTACT},
                idempotency_key=issue_key("contacts.delete"),
                readback=readback_spec(),
            )

        self.assertEqual(caught.exception.rule, "approval_required")
        self.assertEqual(transport.call_count, 0)

    def test_approval_is_recorded_by_kind_and_never_by_value(self) -> None:
        adapter, transport = self._adapter()

        result = adapter.call(
            operation_id="contacts.delete",
            tenant=fake_tenant(),
            path_params={"contactId": SYNTHETIC_CONTACT},
            idempotency_key=issue_key("contacts.delete"),
            approval=approval(),
            readback=readback_spec(),
        )

        self.assertIs(result.status, Status.ok)
        self.assertEqual(transport.call_count, 2)  # write + readback
        self.assertEqual(result.evidence["approval"], {"present": True, "kind": "approval_record"})
        self.assertNotIn(SYNTHETIC_APPROVAL, repr(result.evidence))
        self.assertNotIn(SYNTHETIC_APPROVAL, repr(result.error))

    def test_an_empty_approval_reference_is_refused(self) -> None:
        adapter, transport = self._adapter()

        with self.assertRaises(ContractViolation):
            adapter.call(
                operation_id="contacts.delete",
                tenant=fake_tenant(),
                path_params={"contactId": SYNTHETIC_CONTACT},
                idempotency_key=issue_key("contacts.delete"),
                approval=ApprovalRef(ref="   "),
                readback=readback_spec(),
            )

        self.assertEqual(transport.call_count, 0)

    def test_rows_without_approval_need_none(self) -> None:
        operations = registry(_READ_ROW)
        transport = FakeTransport([resp(200)])
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
        )

        result = adapter.call(
            operation_id="contacts.get",
            tenant=fake_tenant(),
            path_params={"contactId": SYNTHETIC_CONTACT},
        )

        self.assertIs(result.status, Status.ok)


@unittest.skipUnless(REGISTRY_PRESENT, REGISTRY_REASON)
class FrozenRegistryConformanceTest(unittest.TestCase):
    """Runs against the real ``OPERATIONS`` registry once W04 lands it."""

    def test_registry_is_populated_and_rows_are_frozen_shape(self) -> None:
        self.assertTrue(FROZEN_OPERATIONS)
        required = (
            "operation_id",
            "method",
            "path_template",
            "version",
            "version_alternates",
            "documented_level",
            "route_class",
            "auth_kinds",
            "tenant_binding",
            "write",
            "approval_required",
            "scopes_candidate",
            "doc_url",
            "doc_fetch_date",
            "blocker",
        )
        for operation_id, frozen in FROZEN_OPERATIONS.items():
            for field_name in required:
                self.assertTrue(
                    hasattr(frozen, field_name),
                    f"{operation_id} row missing frozen field {field_name}",
                )

    def test_every_read_row_sends_its_own_version(self) -> None:
        known_bindings = {
            "body.locationId",
            "query.locationId",
            "path.locationId",
            "body.altId+altType=location",
            "query.altId+altType",
            "implicit-pit",
            "none",
        }
        reads = [
            frozen
            for frozen in FROZEN_OPERATIONS.values()
            if not frozen.write
            and frozen.route_class in ("public_direct", "official_mcp")
            and frozen.tenant_binding in known_bindings
            and str(frozen.method).upper()
            in {"GET", "POST", "PUT", "DELETE", "PATCH"}
            and str(frozen.path_template).startswith("/")
            and AuthKind.location_pit in tuple(frozen.auth_kinds)
        ]
        self.assertTrue(reads, "registry must contain at least one public read row")
        gate = enabled_gate(reads)
        transport = FakeTransport()

        for frozen in reads:
            params = {
                name: (SYNTHETIC_TENANT if name == "locationId" else "synthetic_value")
                for name in re.findall(r"\{([^{}]+)\}", frozen.path_template)
            }
            transport.responses = [resp(200)]
            adapter = make_adapter(
                transport,
                FROZEN_OPERATIONS,
                gate=gate,
                max_attempts=1,
            )
            with self.subTest(operation_id=frozen.operation_id):
                result = adapter.call(
                    operation_id=frozen.operation_id,
                    tenant=fake_tenant(),
                    path_params=params or None,
                )
                self.assertEqual(transport.last["version"], frozen.version)
                self.assertEqual(result.version_header, frozen.version)


if __name__ == "__main__":
    unittest.main(verbosity=2)
