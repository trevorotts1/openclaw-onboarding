"""Blocker and major regressions -- GU-004 sections 1.3, 2.4, 3.2-3.3.

One regression per reviewer-constructed defect:

* BLOCKER 1 -- a caller readback spec must never point at a WRITE row, and a
  write row's declared plan pins the spec, so reconcile() can never re-issue
  the write (the reviewer observed ``["POST", "POST"]``).
* BLOCKER 2 -- any transport exception (``http.client.IncompleteRead``,
  ``HTTPException``, ``ValueError``, ...) maps to a normal receipt instead of
  escaping ``call()`` with no receipt and no pending record.
* BLOCKER 3 -- a write-capable capability without canary evidence is refused
  both in ``CapabilityGate.put()`` and by the adapter's ``write_ready()`` gate.
* MAJOR 4 -- a gate (or capability record) bound to one tenant never
  authorizes a call for another.
* MAJOR 5 -- a write readback spec with no ``expect`` is refused outright: a
  2xx that verifies nothing must not report ``ok``.

Every test is offline on a fake Transport; synthetic identifiers only.
"""

from __future__ import annotations

import http.client
import os
import re
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_CONTACT,
    SYNTHETIC_OTHER_TENANT,
    SYNTHETIC_TENANT,
    FakeTransport,
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

from cli_anything.gohighlevel.public.capability import (  # noqa: E402
    Capability,
    CapabilityGate,
)
from cli_anything.gohighlevel.public.errors import (  # noqa: E402
    ContractViolation,
    ReconciliationRequired,
)
from cli_anything.gohighlevel.public.readback import (  # noqa: E402
    ReadbackRegistry,
    ReadbackSpec,
)
from cli_anything.gohighlevel.public.result import Status  # noqa: E402

_WRITE_ROW = row(
    "contacts.upsert",
    method="POST",
    path_template="/contacts/upsert",
    write=True,
    tenant_binding="body.locationId",
)
_READ_ROW = row(
    "contacts.get",
    method="GET",
    path_template="/contacts/{contactId}",
    tenant_binding="path.contactId",
)
_OTHER_READ_ROW = row(
    "products.list",
    method="GET",
    path_template="/products/",
    tenant_binding="query.locationId",
)


class _RaisingTransport:
    """Transport stand-in that raises instead of returning a response."""

    def __init__(self, exception: BaseException) -> None:
        self._exception = exception
        self.requests: list[dict[str, object]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        version: str | None,
        headers: dict[str, str],
        query: object,
        body: object,
        timeout_s: float,
    ) -> object:
        self.requests.append({"method": method, "url": url})
        raise self._exception

    @property
    def call_count(self) -> int:
        return len(self.requests)


class Blocker1ReadbackTargetsWriteTest(unittest.TestCase):
    """A caller spec may only re-READ; never the write itself."""

    def _adapter(self, transport, *, readbacks=None):
        operations = registry(_WRITE_ROW, _READ_ROW, _OTHER_READ_ROW)
        return make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
            readbacks=readbacks if readbacks is not None else ReadbackRegistry(),
        )

    def test_a_spec_pointing_at_the_write_row_is_refused_before_transport(
        self,
    ) -> None:
        transport = FakeTransport([resp(200), resp(200)])
        adapter = self._adapter(transport)
        write_spec = ReadbackSpec(
            operation_id="contacts.upsert",
            expect={"id": SYNTHETIC_CONTACT},
        )

        with self.assertRaises(ContractViolation) as caught:
            adapter.call(
                operation_id="contacts.upsert",
                tenant=fake_tenant(),
                body={"email": "a@example.invalid"},
                idempotency_key=issue_key("contacts.upsert"),
                readback=write_spec,
            )

        self.assertEqual(caught.exception.rule, "readback_invalid")
        self.assertEqual(
            caught.exception.detail["reason"], "readback_targets_a_write"
        )
        self.assertEqual(transport.call_count, 0)

    def test_a_write_row_plan_pins_the_spec_to_the_same_read(self) -> None:
        # The write row declares its plan (contacts.get); a caller spec that
        # names a different read row is a plan mismatch, refused outright.
        readbacks = ReadbackRegistry()
        readbacks.register(readback_spec(), operation_id="contacts.upsert")
        transport = FakeTransport([resp(200), resp(200)])
        adapter = self._adapter(transport, readbacks=readbacks)
        other_spec = ReadbackSpec(
            operation_id="products.list",
            expect={"ok": True},
        )

        with self.assertRaises(ContractViolation) as caught:
            adapter.call(
                operation_id="contacts.upsert",
                tenant=fake_tenant(),
                body={"email": "a@example.invalid"},
                idempotency_key=issue_key("contacts.upsert"),
                readback=other_spec,
            )

        self.assertEqual(caught.exception.rule, "readback_plan_mismatch")
        self.assertEqual(caught.exception.detail["plan"], "contacts.get")
        self.assertEqual(caught.exception.detail["call"], "products.list")
        self.assertEqual(transport.call_count, 0)

    def test_reconcile_never_reissues_the_write_request(self) -> None:
        # The reviewer's construction: a spec that resolves to the write row
        # made reconcile() POST twice.  Now the write is refused at the spec
        # gate, so no receipt, no pending row, and zero transport traffic.
        transport = FakeTransport([resp(200)])
        adapter = self._adapter(transport)
        write_spec = ReadbackSpec(
            operation_id="contacts.upsert",
            expect={"id": SYNTHETIC_CONTACT},
        )

        with self.assertRaises(ContractViolation):
            adapter.call(
                operation_id="contacts.upsert",
                tenant=fake_tenant(),
                body={"email": "a@example.invalid"},
                idempotency_key=issue_key("contacts.upsert"),
                readback=write_spec,
            )

        methods = [request["method"] for request in transport.requests]
        self.assertEqual(methods, [])
        self.assertEqual(adapter._pending, {})


class Blocker2TransportExceptionTest(unittest.TestCase):
    """An unclassified transport failure still produces a normal receipt."""

    def _write_adapter(self, transport):
        operations = registry(_WRITE_ROW, _READ_ROW)
        readbacks = ReadbackRegistry()
        readbacks.register(readback_spec())
        return make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
            readbacks=readbacks,
        )

    def test_incomplete_read_on_a_write_is_unknown_outcome_with_a_receipt(
        self,
    ) -> None:
        transport = _RaisingTransport(http.client.IncompleteRead(b""))
        adapter = self._write_adapter(transport)
        key = issue_key("contacts.upsert")

        result = adapter.call(
            operation_id="contacts.upsert",
            tenant=fake_tenant(),
            body={"email": "a@example.invalid"},
            idempotency_key=key,
            readback=readback_spec(),
        )

        self.assertIs(result.status, Status.unknown_outcome)
        self.assertRegex(result.receipt_id, re.compile(r"^gxo_res_[0-9a-f]{12}$"))
        self.assertEqual(result.error["rule"], "transport_unknown")
        self.assertEqual(result.evidence["transport_exception"], "IncompleteRead")
        self.assertIsNone(result.http_status)
        self.assertIsNone(result.response_fingerprint)

        # the same key then retries -- and is blocked instead of re-firing.
        with self.assertRaises(ReconciliationRequired) as caught:
            adapter.call(
                operation_id="contacts.upsert",
                tenant=fake_tenant(),
                body={"email": "a@example.invalid"},
                idempotency_key=key,
                readback=readback_spec(),
            )
        self.assertEqual(caught.exception.detail["receipt_id"], result.receipt_id)
        self.assertEqual(transport.call_count, 1)

    def test_a_bare_value_error_on_a_read_is_unavailable_with_a_receipt(
        self,
    ) -> None:
        transport = _RaisingTransport(ValueError("synthetic parse failure"))
        operations = registry(_READ_ROW)
        adapter = make_adapter(
            transport, operations, gate=enabled_gate(list(operations.values()))
        )

        result = adapter.call(
            operation_id="contacts.get",
            tenant=fake_tenant(),
            path_params={"contactId": SYNTHETIC_CONTACT},
        )

        self.assertIs(result.status, Status.unavailable)
        self.assertRegex(result.receipt_id, re.compile(r"^gxo_res_[0-9a-f]{12}$"))
        self.assertEqual(result.error["rule"], "transport_unknown")
        self.assertEqual(result.evidence["transport_exception"], "ValueError")

    def test_an_exception_during_the_readback_is_unreadable_not_a_crash(
        self,
    ) -> None:
        operations = registry(_WRITE_ROW, _READ_ROW)
        readbacks = ReadbackRegistry()
        readbacks.register(readback_spec())
        # the write succeeds, then the read-back transport blows up.
        transport = FakeTransport([resp(200, b'{"id":"contact_synthetic_0001"}')])

        class _ExplodeOnSecond:
            def __init__(self) -> None:
                self._inner = transport
                self.calls = 0

            def request(self, **kwargs):
                self.calls += 1
                if self.calls > 1:
                    raise http.client.HTTPException("synthetic")
                return self._inner.request(**kwargs)

        exploder = _ExplodeOnSecond()
        adapter = make_adapter(
            exploder,  # type: ignore[arg-type]
            operations,
            gate=enabled_gate(list(operations.values())),
            readbacks=readbacks,
        )

        result = adapter.call(
            operation_id="contacts.upsert",
            tenant=fake_tenant(),
            body={"email": "a@example.invalid"},
            idempotency_key=issue_key("contacts.upsert"),
            readback=readback_spec(),
        )

        self.assertIs(result.status, Status.unknown_outcome)
        self.assertEqual(result.readback.result.value, "unreadable")
        self.assertRegex(result.receipt_id, re.compile(r"^gxo_res_[0-9a-f]{12}$"))


class Blocker3CanaryGateTest(unittest.TestCase):
    """Canary evidence is enforced in put() and by the adapter's write gate."""

    def test_put_refuses_a_write_capable_row_without_the_canary(self) -> None:
        gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
        no_canary = Capability(
            operation_id="contacts.upsert",
            contract_verified=True,
            adapter_built=True,
            offline_tests_passed=True,
            read_verified=True,
            canary_verified=False,
            enabled=True,
        )

        with self.assertRaises(ContractViolation) as caught:
            gate.put(no_canary, write=True)

        self.assertEqual(caught.exception.rule, "capability_canary_missing")
        self.assertFalse(gate.get("contacts.upsert").enabled)

    def test_put_refuses_a_disabled_write_row_without_the_canary(self) -> None:
        # registration itself is gated: the row may not sit in the gate as a
        # write candidate before enable() ever runs.
        gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
        no_canary = Capability(
            operation_id="contacts.upsert",
            contract_verified=True,
            adapter_built=True,
            offline_tests_passed=True,
            read_verified=True,
            canary_verified=False,
            enabled=False,
        )

        with self.assertRaises(ContractViolation) as caught:
            gate.put(no_canary, write=True)

        self.assertEqual(caught.exception.rule, "capability_canary_missing")
        self.assertNotIn("contacts.upsert", gate._capabilities)

    def test_the_adapter_gates_a_write_on_write_ready_not_on_enabled(self) -> None:
        # enabled=True with complete evidence but no canary: legal for a read,
        # refused for a write even though the row sits in the gate as enabled.
        gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
        gate.put(
            Capability(
                operation_id="contacts.upsert",
                contract_verified=True,
                adapter_built=True,
                offline_tests_passed=True,
                read_verified=True,
                canary_verified=False,
                enabled=True,
            )
        )
        self.assertTrue(gate.get("contacts.upsert").enabled)

        operations = registry(_WRITE_ROW, _READ_ROW)
        readbacks = ReadbackRegistry()
        readbacks.register(readback_spec())
        transport = FakeTransport([resp(200), resp(200)])
        adapter = make_adapter(
            transport, operations, gate=gate, readbacks=readbacks
        )

        result = adapter.call(
            operation_id="contacts.upsert",
            tenant=fake_tenant(),
            body={"email": "a@example.invalid"},
            idempotency_key=issue_key("contacts.upsert"),
            readback=readback_spec(),
        )

        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "capability_disabled")
        self.assertTrue(result.evidence["refused_before_transport"])
        self.assertEqual(transport.call_count, 0)

    def test_the_same_canary_less_row_still_serves_a_read(self) -> None:
        gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
        gate.enable(
            Capability(
                operation_id="contacts.get",
                contract_verified=True,
                adapter_built=True,
                offline_tests_passed=True,
                read_verified=True,
                canary_verified=False,
            ),
            write=False,
        )
        self.assertTrue(gate.get("contacts.get").enabled)
        self.assertFalse(gate.get("contacts.get").write_ready())

        operations = registry(_READ_ROW)
        transport = FakeTransport([resp(200)])
        adapter = make_adapter(transport, operations, gate=gate)

        result = adapter.call(
            operation_id="contacts.get",
            tenant=fake_tenant(),
            path_params={"contactId": SYNTHETIC_CONTACT},
        )

        self.assertIs(result.status, Status.ok)
        self.assertEqual(transport.call_count, 1)


class Major4CapabilityTenantTest(unittest.TestCase):
    """A gate authorized for one tenant never authorizes another."""

    def test_a_gate_bound_to_another_tenant_is_refused_before_transport(
        self,
    ) -> None:
        operations = registry(_READ_ROW)
        # auth and call agree on loc_B; the gate is bound to loc_A.
        gate = enabled_gate(list(operations.values()), tenant=SYNTHETIC_TENANT)
        transport = FakeTransport([resp(200)])
        adapter = make_adapter(
            transport,
            operations,
            auth=fake_auth(location_id=SYNTHETIC_OTHER_TENANT),
            gate=gate,
        )

        result = adapter.call(
            operation_id="contacts.get",
            tenant=fake_tenant(SYNTHETIC_OTHER_TENANT),
            path_params={"contactId": SYNTHETIC_CONTACT},
        )

        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "capability_tenant_mismatch")
        self.assertTrue(result.evidence["refused_before_transport"])
        self.assertEqual(transport.call_count, 0)

    def test_a_capability_record_carrying_another_tenant_is_refused(self) -> None:
        # the gate itself matches the call tenant, but the record was
        # authorized for a different one.
        gate = CapabilityGate(tenant=SYNTHETIC_OTHER_TENANT)
        gate.put(
            Capability(
                operation_id="contacts.get",
                contract_verified=True,
                adapter_built=True,
                offline_tests_passed=True,
                read_verified=True,
                enabled=True,
                tenant=SYNTHETIC_TENANT,
            )
        )
        operations = registry(_READ_ROW)
        transport = FakeTransport([resp(200)])
        adapter = make_adapter(
            transport,
            operations,
            auth=fake_auth(location_id=SYNTHETIC_OTHER_TENANT),
            gate=gate,
        )

        result = adapter.call(
            operation_id="contacts.get",
            tenant=fake_tenant(SYNTHETIC_OTHER_TENANT),
            path_params={"contactId": SYNTHETIC_CONTACT},
        )

        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "capability_tenant_mismatch")
        self.assertEqual(transport.call_count, 0)

    def test_a_matching_tenant_still_reaches_transport(self) -> None:
        operations = registry(_READ_ROW)
        gate = enabled_gate(list(operations.values()), tenant=SYNTHETIC_TENANT)
        transport = FakeTransport([resp(200)])
        adapter = make_adapter(transport, operations, gate=gate)

        result = adapter.call(
            operation_id="contacts.get",
            tenant=fake_tenant(),
            path_params={"contactId": SYNTHETIC_CONTACT},
        )

        self.assertIs(result.status, Status.ok)
        self.assertEqual(transport.call_count, 1)


class Major5VacuousReadbackTest(unittest.TestCase):
    """A spec with no expectation proves nothing, so no write may run."""

    def test_a_caller_spec_without_expect_is_refused_before_transport(
        self,
    ) -> None:
        operations = registry(_WRITE_ROW, _READ_ROW)
        transport = FakeTransport([resp(200), resp(200)])
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
            readbacks=ReadbackRegistry(),
        )
        vacuous = ReadbackSpec(
            operation_id="contacts.get",
            target_params={"contactId": SYNTHETIC_CONTACT},
            expect=None,
        )

        with self.assertRaises(ContractViolation) as caught:
            adapter.call(
                operation_id="contacts.upsert",
                tenant=fake_tenant(),
                body={"email": "a@example.invalid"},
                idempotency_key=issue_key("contacts.upsert"),
                readback=vacuous,
            )

        self.assertEqual(caught.exception.rule, "readback_vacuous")
        self.assertEqual(transport.call_count, 0)

    def test_an_empty_expect_mapping_is_also_vacuous(self) -> None:
        operations = registry(_WRITE_ROW, _READ_ROW)
        transport = FakeTransport([resp(200), resp(200)])
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
            readbacks=ReadbackRegistry(),
        )
        vacuous = ReadbackSpec(
            operation_id="contacts.get",
            target_params={"contactId": SYNTHETIC_CONTACT},
            expect={},
        )

        with self.assertRaises(ContractViolation) as caught:
            adapter.call(
                operation_id="contacts.upsert",
                tenant=fake_tenant(),
                body={"email": "a@example.invalid"},
                idempotency_key=issue_key("contacts.upsert"),
                readback=vacuous,
            )

        self.assertEqual(caught.exception.rule, "readback_vacuous")
        self.assertEqual(transport.call_count, 0)

    def test_a_vacuous_plan_on_the_write_row_is_refused_too(self) -> None:
        # the plan comes from the registry, not the caller -- it carries no
        # expect either, and must be refused the same way.
        readbacks = ReadbackRegistry()
        readbacks.register(
            ReadbackSpec(
                operation_id="contacts.get",
                target_params={"contactId": SYNTHETIC_CONTACT},
                expect=None,
            ),
            operation_id="contacts.upsert",
        )
        operations = registry(_WRITE_ROW, _READ_ROW)
        transport = FakeTransport([resp(200), resp(200)])
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
                idempotency_key=issue_key("contacts.upsert"),
            )

        self.assertEqual(caught.exception.rule, "readback_vacuous")
        self.assertEqual(transport.call_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)