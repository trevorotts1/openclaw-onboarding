"""Public result envelope -- GU-004 sections 2.1-2.3.

All eight statuses are derived from synthetic transport responses using the
frozen table only.  Required evidence keys are present on every envelope, and
redaction removes tokens, PIT values and approval values from evidence and
from echoed headers.
"""

from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_CONTACT,
    SYNTHETIC_TENANT,
    SYNTHETIC_TOKEN,
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

from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.readback import (  # noqa: E402
    ReadbackRegistry,
    ReadbackStatus,
)
from cli_anything.gohighlevel.public.result import (  # noqa: E402
    REDACTED,
    REQUIRED_EVIDENCE_KEYS,
    OperationResult,
    Status,
    canonical_json,
    redact_headers,
    redact_mapping,
)

_READ_ROW = row(
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

_READ_CASES = (
    ("200", resp(200, b'{"id":"contact_synthetic_0001"}'), Status.ok),
    ("204 no body", resp(204, b""), Status.ok),
    ("400", resp(400, b'{"message":"invalid"}'), Status.validation_error),
    ("401", resp(401, b""), Status.denied),
    ("403", resp(403, b""), Status.denied),
    ("404", resp(404, b""), Status.not_found),
    ("409", resp(409, b""), Status.conflict),
    ("422", resp(422, b""), Status.validation_error),
    ("429", resp(429, b"", {"Retry-After": "1"}), Status.rate_limited),
    ("500", resp(500, b""), Status.unavailable),
    ("503", resp(503, b""), Status.unavailable),
    ("timeout", resp(None, b"", error_kind="timeout"), Status.unavailable),
    ("connection", resp(None, b"", error_kind="connection"), Status.unavailable),
    ("tls", resp(None, b"", error_kind="tls"), Status.unavailable),
    ("dns", resp(None, b"", error_kind="dns"), Status.unavailable),
)

_WRITE_CASES = (
    (
        "2xx verified",
        resp(200, b'{"id":"contact_synthetic_0001"}'),
        resp(200, b'{"id":"contact_synthetic_0001"}'),
        Status.ok,
    ),
    (
        "2xx mismatch",
        resp(200, b'{"id":"contact_synthetic_0001"}'),
        resp(200, b'{"id":"different"}'),
        Status.unknown_outcome,
    ),
    (
        "2xx absent",
        resp(200, b'{"id":"contact_synthetic_0001"}'),
        resp(404, b""),
        Status.unknown_outcome,
    ),
    (
        "2xx unreadable",
        resp(200, b'{"id":"contact_synthetic_0001"}'),
        resp(500, b""),
        Status.unknown_outcome,
    ),
    ("400", resp(400), None, Status.validation_error),
    ("401", resp(401), None, Status.denied),
    ("403", resp(403), None, Status.denied),
    ("404", resp(404), None, Status.not_found),
    ("409", resp(409), None, Status.conflict),
    ("422", resp(422), None, Status.validation_error),
    ("429", resp(429), None, Status.rate_limited),
    ("500", resp(500), None, Status.unknown_outcome),
    ("503", resp(503), None, Status.unknown_outcome),
    ("timeout", resp(None, b"", error_kind="timeout"), None, Status.unknown_outcome),
)


class _EnvelopeCase(unittest.TestCase):
    def _read_adapter(self, response):
        operations = registry(_READ_ROW)
        transport = FakeTransport([response])
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
        )
        return adapter, transport

    def _write_adapter(self, write_response, readback_response):
        operations = registry(_WRITE_ROW, _READ_ROW)
        responses = [write_response]
        if readback_response is not None:
            responses.append(readback_response)
        transport = FakeTransport(responses)
        readbacks = ReadbackRegistry()
        readbacks.register(readback_spec())
        adapter = make_adapter(
            transport,
            operations,
            gate=enabled_gate(list(operations.values())),
            readbacks=readbacks,
        )
        return adapter, transport

    def _read(self, response):
        adapter, _ = self._read_adapter(response)
        return adapter.call(
            operation_id="contacts.get",
            tenant=fake_tenant(),
            path_params={"contactId": SYNTHETIC_CONTACT},
        )

    def _write(self, write_response, readback_response):
        adapter, transport = self._write_adapter(write_response, readback_response)
        result = adapter.call(
            operation_id="contacts.upsert",
            tenant=fake_tenant(),
            body={"email": "a@example.invalid"},
            idempotency_key=issue_key("contacts.upsert"),
            readback=readback_spec(),
        )
        return result, transport


class StatusDerivationTest(_EnvelopeCase):
    def test_read_statuses_match_the_frozen_table(self) -> None:
        for name, response, expected in _READ_CASES:
            with self.subTest(case=name):
                result = self._read(response)
                self.assertIs(result.status, expected)
                self.assertTrue(all(key in result.evidence for key in REQUIRED_EVIDENCE_KEYS))

    def test_write_statuses_match_the_frozen_table(self) -> None:
        for name, write_response, readback_response, expected in _WRITE_CASES:
            with self.subTest(case=name):
                result, _ = self._write(write_response, readback_response)
                self.assertIs(result.status, expected)

    def test_every_status_in_the_enum_is_reachable(self) -> None:
        observed = {expected for _, _, expected in _READ_CASES}
        observed |= {expected for _, _, _, expected in _WRITE_CASES}
        self.assertEqual(observed, set(Status))
        self.assertEqual(len(observed), 8)

    def test_read_transport_error_is_null_http_and_absent_fingerprint(self) -> None:
        result = self._read(resp(None, b"", error_kind="timeout"))
        self.assertIsNone(result.http_status)
        self.assertIsNone(result.response_fingerprint)
        self.assertIsNone(result.evidence["http_status"])
        self.assertIsNone(result.evidence["response_fingerprint"])
        self.assertEqual(result.error["rule"], "transport_timeout")

    def test_write_transport_error_is_unknown_outcome_and_readback_not_performed(self) -> None:
        result, transport = self._write(
            resp(None, b"", error_kind="connection"), None
        )
        self.assertIs(result.status, Status.unknown_outcome)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(result.readback.result, ReadbackStatus.unreadable)
        self.assertEqual(result.readback.detail["reason"], "not_performed")

    def test_write_2xx_verified_has_a_verified_readback(self) -> None:
        result, transport = self._write(
            resp(200, b'{"id":"contact_synthetic_0001"}'),
            resp(200, b'{"id":"contact_synthetic_0001"}'),
        )
        self.assertIs(result.status, Status.ok)
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(transport.requests[1]["method"], "GET")
        self.assertEqual(result.readback.result, ReadbackStatus.verified)
        self.assertEqual(result.evidence["readback"], "verified")

    def test_write_2xx_without_a_verified_readback_is_unknown_outcome(self) -> None:
        for readback_response in (
            resp(200, b'{"id":"different"}'),
            resp(404, b""),
            resp(500, b""),
        ):
            with self.subTest(body=readback_response.body, status=readback_response.status):
                result, _ = self._write(resp(200), readback_response)
                self.assertIs(result.status, Status.unknown_outcome)
                self.assertIsNot(result.readback.result, ReadbackStatus.verified)

    def test_denied_names_a_candidate_scope_and_never_retries(self) -> None:
        scoped = row(
            "contacts.get",
            method="GET",
            path_template="/contacts/{contactId}",
            tenant_binding="path.contactId",
            scopes_candidate=("contacts.readonly",),
        )
        operations = registry(scoped)
        transport = FakeTransport([resp(403, b"")])
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

        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "permission_denied")
        self.assertEqual(result.error["scopes_candidate"], ["contacts.readonly"])
        self.assertIn("candidate", result.error["hint"])
        self.assertEqual(transport.call_count, 1)

    def test_rate_limited_is_never_retried(self) -> None:
        adapter, transport = self._read_adapter(resp(429, b""))
        adapter.call(
            operation_id="contacts.get",
            tenant=fake_tenant(),
            path_params={"contactId": SYNTHETIC_CONTACT},
        )
        self.assertEqual(transport.call_count, 1)


class EvidenceKeysTest(_EnvelopeCase):
    def _all_results(self) -> list[OperationResult]:
        results = [self._read(response) for _, response, _ in _READ_CASES]
        results += [
            self._write(write_response, readback_response)[0]
            for _, write_response, readback_response, _ in _WRITE_CASES
        ]
        return results

    def test_required_evidence_keys_are_always_present(self) -> None:
        for result in self._all_results():
            with self.subTest(status=result.status.value):
                missing = [
                    key for key in REQUIRED_EVIDENCE_KEYS if key not in result.evidence
                ]
                self.assertEqual(missing, [])
                self.assertEqual(result.evidence["operation_id"], result.operation_id)
                self.assertEqual(result.evidence["tenant"], SYNTHETIC_TENANT)
                self.assertEqual(result.evidence["receipt_id"], result.receipt_id)
                self.assertGreaterEqual(result.evidence["attempt"], 1)
                self.assertIsInstance(result.evidence["request_fingerprint"], str)
                self.assertEqual(len(result.evidence["request_fingerprint"]), 64)

    def test_missing_evidence_key_is_a_contract_violation(self) -> None:
        result = self._read(resp(200))
        fields = dict(result.__dict__)
        evidence = dict(fields["evidence"])
        evidence.pop("tenant")
        fields["evidence"] = evidence

        with self.assertRaises(ContractViolation) as caught:
            OperationResult(**fields)  # type: ignore[arg-type]

        self.assertEqual(caught.exception.rule, "evidence_keys_missing")
        self.assertIn("tenant", caught.exception.detail["missing"])

    def test_attempt_below_one_is_a_contract_violation(self) -> None:
        result = self._read(resp(200))
        fields = dict(result.__dict__)
        fields["attempt"] = 0

        with self.assertRaises(ContractViolation) as caught:
            OperationResult(**fields)  # type: ignore[arg-type]

        self.assertEqual(caught.exception.rule, "attempt_invalid")

    def test_receipt_id_has_the_frozen_shape_and_is_unique_per_call(self) -> None:
        import re

        first = self._read(resp(200))
        second = self._read(resp(200))
        pattern = re.compile(r"^gxo_res_[0-9a-f]{12}$")
        self.assertRegex(first.receipt_id, pattern)
        self.assertRegex(second.receipt_id, pattern)
        self.assertNotEqual(first.receipt_id, second.receipt_id)


class RedactionTest(unittest.TestCase):
    def test_sensitive_keys_are_redacted(self) -> None:
        redacted = redact_mapping(
            {
                "Authorization": "Bearer synthetic",
                "token": SYNTHETIC_TOKEN,
                "apiKey": SYNTHETIC_TOKEN,
                "refresh_token": "synthetic-refresh",
                "approval_token": "synthetic-approval",
                "pit": SYNTHETIC_TOKEN,
                "nested": {"private_integration_token": SYNTHETIC_TOKEN},
            }
        )
        self.assertEqual(redacted["Authorization"], REDACTED)
        self.assertEqual(redacted["token"], REDACTED)
        self.assertEqual(redacted["apiKey"], REDACTED)
        self.assertEqual(redacted["refresh_token"], REDACTED)
        self.assertEqual(redacted["approval_token"], REDACTED)
        self.assertEqual(redacted["pit"], REDACTED)
        self.assertEqual(redacted["nested"]["private_integration_token"], REDACTED)
        self.assertNotIn(SYNTHETIC_TOKEN, canonical_json(redacted))

    def test_ids_only_redaction_keeps_the_tenant_and_masks_other_identifiers(self) -> None:
        redacted = redact_mapping(
            {"contactId": SYNTHETIC_CONTACT, "locationId": SYNTHETIC_TENANT},
            redaction="ids-only",
        )
        self.assertEqual(redacted["contactId"], "<id>")
        self.assertEqual(redacted["locationId"], SYNTHETIC_TENANT)

    def test_headers_allowlist_drops_authorization_and_cookies(self) -> None:
        echoed = redact_headers(
            {
                "Authorization": "Bearer synthetic",
                "Cookie": "session=synthetic",
                "Content-Type": "application/json",
                "X-Request-Id": "req_synthetic_1",
            }
        )
        self.assertEqual(
            echoed, {"Content-Type": "application/json", "X-Request-Id": "req_synthetic_1"}
        )

    def test_transport_echoed_headers_never_reach_evidence(self) -> None:
        operations = registry(_READ_ROW)
        transport = FakeTransport(
            [
                resp(
                    200,
                    b'{"id":"contact_synthetic_0001"}',
                    {"Authorization": "Bearer synthetic", "Content-Type": "application/json"},
                )
            ]
        )
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

        echoed = result.evidence["response_headers"]
        self.assertNotIn("Authorization", echoed)
        self.assertEqual(echoed["Content-Type"], "application/json")
        self.assertNotIn("Bearer synthetic", canonical_json(result.evidence))

    def test_adapter_never_writes_the_token_into_the_envelope(self) -> None:
        operations = registry(_READ_ROW)
        transport = FakeTransport([resp(200, b'{"id":"contact_synthetic_0001"}')])
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

        self.assertEqual(result.evidence["auth_source"], "env:GHL_API_KEY")
        self.assertNotIn(SYNTHETIC_TOKEN, canonical_json(result.evidence))
        self.assertNotIn(SYNTHETIC_TOKEN, repr(result))
        self.assertEqual(transport.last["headers"]["Authorization"], "Bearer " + SYNTHETIC_TOKEN)


if __name__ == "__main__":
    unittest.main(verbosity=2)
