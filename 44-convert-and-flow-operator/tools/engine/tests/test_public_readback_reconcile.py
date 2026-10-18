"""Readback and reconciliation -- GU-004 sections 1.3 step 8 and 2.4.

An unreconciled ``unknown_outcome`` blocks every further call with that key.
``reconcile()`` re-reads through the same operation's declared readback row on
the same transport and yields a final status; it never switches operation,
credential class or transport.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_CONTACT,
    FakeTransport,
    enabled_gate,
    fake_tenant,
    issue_key,
    make_adapter,
    readback_spec,
    registry,
    resp,
    row,
)

from cli_anything.gohighlevel.public.errors import (  # noqa: E402
    ContractViolation,
    ReconciliationRequired,
)
from cli_anything.gohighlevel.public.readback import (  # noqa: E402
    ReadbackRegistry,
    ReadbackStatus,
)
from cli_anything.gohighlevel.public.result import Status  # noqa: E402

_WRITE_ROW = row(
    "contacts.upsert",
    method="POST",
    path_template="/contacts/upsert",
    write=True,
    tenant_binding="body.locationId",
)
_READBACK_ROW = row(
    "contacts.get",
    method="GET",
    path_template="/contacts/{contactId}",
    version="v3",
    tenant_binding="path.contactId",
)

_UNKNOWN_WRITE = resp(None, b"", error_kind="timeout")
_VERIFIED_READBACK = resp(200, b'{"id":"contact_synthetic_0001"}')


class _ReconcileCase(unittest.TestCase):
    def setUp(self) -> None:
        self.operations = registry(_WRITE_ROW, _READBACK_ROW)

    def _adapter(self, responses):
        transport = FakeTransport(responses)
        readbacks = ReadbackRegistry()
        readbacks.register(readback_spec())
        adapter = make_adapter(
            transport,
            self.operations,
            gate=enabled_gate(list(self.operations.values())),
            readbacks=readbacks,
        )
        return adapter, transport

    def _write(self, adapter, key, body=None):
        return adapter.call(
            operation_id="contacts.upsert",
            tenant=fake_tenant(),
            body=body if body is not None else {"email": "a@example.invalid"},
            idempotency_key=key,
            readback=readback_spec(),
        )


class UnknownOutcomeBlocksRetryTest(_ReconcileCase):
    def test_retry_with_the_same_key_raises_before_transport(self) -> None:
        key = issue_key("contacts.upsert")
        adapter, transport = self._adapter([_UNKNOWN_WRITE, _VERIFIED_READBACK])

        prior = self._write(adapter, key)
        self.assertIs(prior.status, Status.unknown_outcome)
        self.assertEqual(transport.call_count, 1)

        with self.assertRaises(ReconciliationRequired) as caught:
            self._write(adapter, key)

        self.assertEqual(caught.exception.rule, "reconciliation_required")
        self.assertEqual(caught.exception.detail["receipt_id"], prior.receipt_id)
        self.assertIn("idempotency_key", caught.exception.detail)
        self.assertEqual(transport.call_count, 1)

    def test_a_changed_body_with_the_same_key_is_still_blocked(self) -> None:
        key = issue_key("contacts.upsert")
        adapter, transport = self._adapter([_UNKNOWN_WRITE, _VERIFIED_READBACK])

        self._write(adapter, key)

        with self.assertRaises(ReconciliationRequired):
            self._write(adapter, key, body={"email": "changed@example.invalid"})

        self.assertEqual(transport.call_count, 1)

    def test_a_2xx_write_with_a_mismatched_readback_also_blocks_the_retry(self) -> None:
        key = issue_key("contacts.upsert")
        adapter, transport = self._adapter(
            [resp(200), resp(200, b'{"id":"different"}')]
        )

        prior = self._write(adapter, key)
        self.assertIs(prior.status, Status.unknown_outcome)
        self.assertIs(prior.readback.result, ReadbackStatus.mismatch)

        with self.assertRaises(ReconciliationRequired):
            self._write(adapter, key)

        self.assertEqual(transport.call_count, 2)  # write + its readback only


class ReconcileTest(_ReconcileCase):
    def _unknown(self, responses):
        key = issue_key("contacts.upsert")
        adapter, transport = self._adapter(responses)
        prior = self._write(adapter, key)
        self.assertIs(prior.status, Status.unknown_outcome)
        return adapter, transport, prior

    def test_reconcile_uses_the_readback_operation_on_the_same_transport(self) -> None:
        adapter, transport, prior = self._unknown(
            [_UNKNOWN_WRITE, _VERIFIED_READBACK]
        )

        reconciled = adapter.reconcile(prior)

        self.assertIs(reconciled.status, Status.ok)
        self.assertEqual(transport.call_count, 2)
        request = transport.requests[-1]
        self.assertEqual(request["method"], "GET")
        self.assertEqual(request["url"], "/contacts/" + SYNTHETIC_CONTACT)
        self.assertEqual(request["version"], _READBACK_ROW.version)
        self.assertNotEqual(request["url"], _WRITE_ROW.path_template)
        self.assertIs(adapter._transport, transport)
        self.assertEqual(reconciled.transport, "http")
        self.assertEqual(reconciled.operation_id, _WRITE_ROW.operation_id)
        self.assertEqual(reconciled.evidence["reconciled_from"], prior.receipt_id)
        self.assertEqual(reconciled.version_header, _WRITE_ROW.version)
        self.assertIsNone(reconciled.error)

    def test_reconcile_returns_a_final_status_for_every_readback_outcome(self) -> None:
        cases = (
            ("verified", resp(200, b'{"id":"contact_synthetic_0001"}'), Status.ok),
            ("absent", resp(404, b""), Status.not_found),
            ("mismatch", resp(200, b'{"id":"different"}'), Status.conflict),
            ("unreadable", resp(500, b""), Status.unavailable),
        )
        for name, readback_response, expected in cases:
            with self.subTest(case=name):
                adapter, transport, prior = self._unknown(
                    [_UNKNOWN_WRITE, readback_response]
                )
                reconciled = adapter.reconcile(prior)
                self.assertIs(reconciled.status, expected)
                self.assertEqual(transport.call_count, 2)
                if expected is not Status.ok:
                    self.assertEqual(
                        reconciled.error["rule"], "reconcile_" + reconciled.readback.result.value
                    )

    def test_an_unreadable_reconcile_keeps_the_pending_write(self) -> None:
        adapter, transport, prior = self._unknown([_UNKNOWN_WRITE, resp(500, b"")])

        first = adapter.reconcile(prior)
        self.assertIs(first.status, Status.unavailable)

        transport.responses = [_VERIFIED_READBACK]
        second = adapter.reconcile(prior)

        self.assertIs(second.status, Status.ok)
        self.assertEqual(transport.call_count, 3)

    def test_reconcile_requires_an_unknown_outcome_prior(self) -> None:
        key = issue_key("contacts.upsert")
        adapter, transport = self._adapter(
            [resp(200, b'{"id":"contact_synthetic_0001"}'), _VERIFIED_READBACK]
        )
        ok = adapter.call(
            operation_id="contacts.upsert",
            tenant=fake_tenant(),
            body={"email": "a@example.invalid"},
            idempotency_key=key,
            readback=readback_spec(),
        )
        self.assertIs(ok.status, Status.ok)

        with self.assertRaises(ContractViolation) as caught:
            adapter.reconcile(ok)

        self.assertEqual(caught.exception.rule, "reconcile_requires_unknown_outcome")
        self.assertEqual(transport.call_count, 2)

    def test_reconcile_refuses_a_receipt_it_never_issued(self) -> None:
        adapter, _, prior = self._unknown([_UNKNOWN_WRITE, _VERIFIED_READBACK])
        fabricated = dataclasses.replace(prior, receipt_id="gxo_res_feedfacefeed")

        with self.assertRaises(ContractViolation) as caught:
            adapter.reconcile(fabricated)

        self.assertEqual(caught.exception.rule, "reconcile_unknown_receipt")

    def test_reconcile_never_issues_a_second_write(self) -> None:
        adapter, transport, prior = self._unknown(
            [_UNKNOWN_WRITE, _VERIFIED_READBACK]
        )
        adapter.reconcile(prior)

        methods = [request["method"] for request in transport.requests]
        self.assertEqual(methods, ["POST", "GET"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
