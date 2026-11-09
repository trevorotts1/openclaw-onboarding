"""WF01 typed multipart transport, refusal-before-transport and resumability.

Covers: B03 (transport side), IG-ROUTE-08, A07's no-rail-switch half.

Every byte-level test injects an opener stub: urllib never opens a socket, and
no real credential or asset host is contacted.
"""

from __future__ import annotations

import hashlib
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_TENANT,
    FakeTransport,
    fake_auth,
    fake_tenant,
    resp,
)

from cli_anything.gohighlevel.public.adapter import PublicGhlAdapter  # noqa: E402
from cli_anything.gohighlevel.public.capability import (  # noqa: E402
    ACTIVATION_VERIFIED,
    Capability,
    CapabilityGate,
)
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.idempotency import IdempotencyKey  # noqa: E402
from cli_anything.gohighlevel.public.readback import ReadbackSpec  # noqa: E402
from cli_anything.gohighlevel.public.result import Status  # noqa: E402
from cli_anything.gohighlevel.public.transport import (  # noqa: E402
    JSON_MEDIA_TYPE,
    MULTIPART_MEDIA_TYPE,
    MultipartFile,
    MultipartOutcome,
    MultipartRequest,
    RequestsTransport,
    _RefuseRedirects,
    resolve_request_media_type,
)

UPLOAD_ROW = {
    "operation_id": "kb.files.upload",
    "method": "POST",
    "path_template": "/knowledge-bases/{id}/files",
    "version": "v3",
    "write": True,
    "approval_required": False,
    "route_class": "public_direct",
    "auth_kinds": (fake_auth().kind,),
    "tenant_binding": "none",
    "scopes_candidate": ("knowledge_bases.write",),
    "doc_url": "https://example.invalid/doc",
    "doc_fetch_date": "2026-10-18",
    "request_media_type": MULTIPART_MEDIA_TYPE,
}
READ_ROW = {
    "operation_id": "kb.files.get",
    "method": "GET",
    "path_template": "/knowledge-bases/{id}/files/{fileId}",
    "version": "v3",
    "write": False,
    "route_class": "public_direct",
    "auth_kinds": (fake_auth().kind,),
    "tenant_binding": "none",
}


def upload_file(content: bytes = b"hello,bytes", **overrides: object) -> MultipartFile:
    payload = {
        "field_name": "file",
        "filename": "notes.txt",
        "content_type": "text/plain",
        "content": content,
    }
    payload.update(overrides)
    return MultipartFile(**payload)


class RecordingOpener:
    """Captures the urllib Request; never opens a socket."""

    def __init__(self, response: object | None = None) -> None:
        self.requests: list[object] = []
        self._response = response

    def __call__(self, request, timeout=None):  # noqa: ANN001 - urllib shape
        self.requests.append(request)
        return self._response if self._response is not None else _Stub()


class _Stub:
    def __init__(self, body: bytes = b'{"ok":true}', status: int = 200) -> None:
        self._body = body
        self._status = status
        self.headers = {"Content-Type": "application/json"}

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self._status

    def __enter__(self) -> "_Stub":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class MediaTypeResolutionTests(unittest.TestCase):
    def test_absent_declaration_is_the_frozen_json_behaviour(self) -> None:
        self.assertEqual(resolve_request_media_type({"method": "GET"}), JSON_MEDIA_TYPE)

    def test_multipart_declaration_is_typed(self) -> None:
        self.assertEqual(
            resolve_request_media_type({"request_media_type": "multipart/form-data; boundary=x"}),
            MULTIPART_MEDIA_TYPE,
        )

    def test_unknown_declaration_is_refused_not_sent_as_json(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            resolve_request_media_type({"request_media_type": "application/x-msgpack"})
        self.assertEqual(caught.exception.rule, "request_media_type_unsupported")


class MultipartValidationTests(unittest.TestCase):
    def test_disallowed_type_is_refused_before_transport(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            upload_file(content_type="application/x-plot")
        self.assertEqual(caught.exception.rule, "multipart_type_refused")

    def test_header_injection_in_filename_is_refused(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            upload_file(filename="a\r\nX-Evil: 1")
        self.assertEqual(caught.exception.rule, "multipart_header_injection")

    def test_empty_file_is_refused(self) -> None:
        with self.assertRaises(ContractViolation):
            upload_file(content=b"")

    def test_credential_never_travels_as_a_multipart_field(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            MultipartRequest(files=(upload_file(),), fields={"Authorization": "Bearer x"})
        self.assertEqual(caught.exception.rule, "multipart_credential_field")

    def test_over_budget_is_refused_before_any_byte_leaves(self) -> None:
        opener = RecordingOpener()
        transport = RequestsTransport(opener=opener)
        with self.assertRaises(ContractViolation) as caught:
            transport.request_multipart(
                method="POST",
                url="/kb/{id}/files",
                version="v3",
                headers={"Authorization": "Bearer synthetic"},
                query=None,
                payload=MultipartRequest(files=(upload_file(b"0123456789"),)),
                timeout_s=5.0,
                max_bytes=4,
            )
        self.assertEqual(caught.exception.rule, "multipart_oversize")
        self.assertEqual(opener.requests, [])

    def test_cross_host_absolute_url_is_refused(self) -> None:
        opener = RecordingOpener()
        transport = RequestsTransport(opener=opener)
        with self.assertRaises(ContractViolation) as caught:
            transport.request_multipart(
                method="POST",
                url="https://assets.example.invalid/upload",
                version="v3",
                headers={"Authorization": "Bearer synthetic"},
                query=None,
                payload=MultipartRequest(files=(upload_file(),)),
                timeout_s=5.0,
            )
        self.assertEqual(caught.exception.rule, "asset_host_refused")
        self.assertEqual(opener.requests, [])

    def test_plain_http_is_refused(self) -> None:
        transport = RequestsTransport(opener=RecordingOpener())
        with self.assertRaises(ContractViolation):
            transport.request_multipart(
                method="POST",
                url="http://services.leadconnectorhq.com/upload",
                version="v3",
                headers={},
                query=None,
                payload=MultipartRequest(files=(upload_file(),)),
                timeout_s=5.0,
            )

    def test_redirect_handler_refuses_every_redirect(self) -> None:
        handler = _RefuseRedirects()
        self.assertIsNone(
            handler.redirect_request(None, None, 302, "Found", {}, "https://evil.invalid/")
        )


class MultipartWireTests(unittest.TestCase):
    def test_library_built_boundary_body_and_hashes(self) -> None:
        opener = RecordingOpener()
        transport = RequestsTransport(opener=opener)
        payload = MultipartRequest(
            files=(upload_file(b"col1,col2\n1,2\n"),),
            fields={"name": "lesson-one"},
        )
        outcome = transport.request_multipart(
            method="POST",
            url="/knowledge-bases/{id}/files",
            version="v3",
            headers={"Authorization": "Bearer synthetic-token-value"},
            query={"locationId": SYNTHETIC_TENANT},
            payload=payload,
            timeout_s=5.0,
        )
        self.assertIsInstance(outcome, MultipartOutcome)
        self.assertEqual(outcome.response.status, 200)
        request = opener.requests[0]
        content_type = request.headers.get("Content-type") or request.headers.get("Content-Type")
        self.assertIn("multipart/form-data; boundary=----ghlboundary", content_type)
        boundary = content_type.split("boundary=", 1)[1]
        body = request.data
        self.assertTrue(body.startswith(b"--" + boundary.encode()))
        self.assertTrue(body.rstrip().endswith(b"--"))
        self.assertIn(b'name="file"; filename="notes.txt"', body)
        self.assertIn(b"Content-Type: text/plain", body)
        self.assertIn(b"col1,col2", body)
        self.assertIn(b"lesson-one", body)
        # The credential travels in the header only; never inside the body.
        self.assertNotIn(b"synthetic-token-value", body)
        # The Version header is the row's, and the actual bytes were hashed.
        self.assertEqual(request.headers.get("Version"), "v3")
        self.assertEqual(outcome.evidence["body_sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(outcome.evidence["files"][0]["sha256"], hashlib.sha256(b"col1,col2\n1,2\n").hexdigest())
        self.assertTrue(outcome.evidence["boundary_library_built"])
        self.assertFalse(outcome.evidence["redirects_followed"])
        self.assertIn("locationId", request.full_url)


class FakeMultipartTransport:
    """Adapter-level fake: records both rails, replays scripted responses."""

    def __init__(self, responses: list | None = None) -> None:
        self.responses = list(responses or [])
        self.json_requests: list[dict] = []
        self.multipart_requests: list[dict] = []

    def request(self, **kwargs):  # noqa: ANN003
        self.json_requests.append(kwargs)
        if self.responses:
            return self.responses.pop(0)
        return resp(200, b'{"ok":true}')

    def request_multipart(self, *, payload, **kwargs):  # noqa: ANN001
        self.multipart_requests.append({"payload": payload, **kwargs})
        response = self.responses.pop(0) if self.responses else resp(200)
        evidence = dict(payload.evidence())
        evidence["body_sha256"] = "0" * 64
        return MultipartOutcome(response=response, evidence=evidence)


def admitted_adapter(transport, *, operations, **kwargs) -> PublicGhlAdapter:
    capability = Capability(
        operation_id="kb.files.upload",
        contract_verified=True,
        adapter_built=True,
        offline_tests_passed=True,
        read_verified=True,
        canary_verified=True,
        enabled=True,
        tenant=SYNTHETIC_TENANT,
        activation=ACTIVATION_VERIFIED,
    )
    return PublicGhlAdapter(
        auth=fake_auth(),
        operations=operations,
        transport=transport,
        capability=CapabilityGate({"kb.files.upload": capability}, tenant=SYNTHETIC_TENANT),
        **kwargs,
    )


class AdapterMultipartTests(unittest.TestCase):
    def test_json_row_refuses_a_multipart_payload(self) -> None:
        adapter = PublicGhlAdapter(
            auth=fake_auth(),
            operations={READ_ROW["operation_id"]: READ_ROW},
            transport=FakeMultipartTransport(),
            capability=CapabilityGate(tenant=SYNTHETIC_TENANT),
        )
        with self.assertRaises(ContractViolation) as caught:
            adapter.call(
                operation_id="kb.files.get",
                tenant=fake_tenant(),
                path_params={"id": "kb1", "fileId": "f1"},
                multipart=MultipartRequest(files=(upload_file(),)),
            )
        self.assertEqual(caught.exception.rule, "multipart_not_allowed_for_json")

    def test_multipart_row_without_a_typed_payload_refuses_with_zero_calls(self) -> None:
        transport = FakeMultipartTransport()
        adapter = admitted_adapter(
            transport, operations={UPLOAD_ROW["operation_id"]: UPLOAD_ROW}
        )
        result = adapter.call(
            operation_id="kb.files.upload",
            tenant=fake_tenant(),
            path_params={"id": "kb1"},
            idempotency_key=str(IdempotencyKey.issue("kb.files.upload")),
        )
        self.assertEqual(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "multipart_payload_required")
        self.assertTrue(result.evidence["refused_before_transport"])
        self.assertEqual(transport.multipart_requests, [])
        self.assertEqual(transport.json_requests, [])

    def test_unimplemented_multipart_transport_refuses_before_sending(self) -> None:
        transport = FakeTransport()
        adapter = admitted_adapter(
            transport, operations={UPLOAD_ROW["operation_id"]: UPLOAD_ROW}
        )
        result = adapter.call(
            operation_id="kb.files.upload",
            tenant=fake_tenant(),
            path_params={"id": "kb1"},
            idempotency_key=str(IdempotencyKey.issue("kb.files.upload")),
            multipart=MultipartRequest(files=(upload_file(),)),
        )
        self.assertEqual(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "multipart_transport_unimplemented")
        self.assertEqual(transport.call_count, 0)

    def test_multipart_write_transmits_and_records_redacted_evidence(self) -> None:
        transport = FakeMultipartTransport([resp(200), resp(200, b'{"id":"f1"}')])
        adapter = admitted_adapter(
            transport,
            operations={
                UPLOAD_ROW["operation_id"]: UPLOAD_ROW,
                READ_ROW["operation_id"]: READ_ROW,
            },
        )
        key = IdempotencyKey.issue("kb.files.upload")
        result = adapter.call(
            operation_id="kb.files.upload",
            tenant=fake_tenant(),
            path_params={"id": "kb1"},
            idempotency_key=str(key),
            multipart=MultipartRequest(files=(upload_file(),)),
            readback=ReadbackSpec(
                operation_id="kb.files.get",
                target_params={"id": "kb1", "fileId": "f1"},
                expect={"id": "f1"},
            ),
        )
        self.assertEqual(result.status, Status.ok, result.error)
        self.assertEqual(len(transport.multipart_requests), 1)
        self.assertEqual(transport.json_requests[0]["method"], "GET")  # readback only
        self.assertEqual(result.evidence["request_media_type"], MULTIPART_MEDIA_TYPE)
        self.assertEqual(result.evidence["multipart_request"]["file_count"], 1)
        self.assertEqual(result.evidence["multipart_request"]["files"][0]["sha256"], hashlib.sha256(b"hello,bytes").hexdigest())
        # Bytes never appear in the receipt.
        self.assertNotIn("hello,bytes", str(dict(result.evidence)))

    def test_ambiguous_upload_blocks_a_repeat_on_any_rail(self) -> None:
        transport = FakeMultipartTransport([resp(status=None, body=b"", error_kind="timeout")])
        adapter = admitted_adapter(
            transport,
            operations={
                UPLOAD_ROW["operation_id"]: UPLOAD_ROW,
                READ_ROW["operation_id"]: READ_ROW,
            },
        )
        first = adapter.call(
            operation_id="kb.files.upload",
            tenant=fake_tenant(),
            path_params={"id": "kb1"},
            idempotency_key=str(IdempotencyKey.issue("kb.files.upload")),
            multipart=MultipartRequest(files=(upload_file(),)),
            readback=ReadbackSpec(
                operation_id="kb.files.get",
                target_params={"id": "kb1", "fileId": "f1"},
                expect={"id": "f1"},
            ),
        )
        self.assertEqual(first.status, Status.unknown_outcome)
        second = adapter.call(
            operation_id="kb.files.upload",
            tenant=fake_tenant(),
            path_params={"id": "kb1"},
            idempotency_key=str(IdempotencyKey.issue("kb.files.upload")),
            multipart=MultipartRequest(files=(upload_file(),)),
            readback=ReadbackSpec(
                operation_id="kb.files.get",
                target_params={"id": "kb1", "fileId": "f1"},
                expect={"id": "f1"},
            ),
        )
        self.assertEqual(second.status, Status.denied)
        self.assertEqual(second.error["rule"], "unreconciled_intent_exists")
        self.assertEqual(len(transport.multipart_requests), 1)

    def test_old_json_callers_keep_the_json_rail(self) -> None:
        transport = FakeMultipartTransport([resp(200)])
        read_capability = Capability(
            operation_id="kb.files.get",
            contract_verified=True,
            adapter_built=True,
            offline_tests_passed=True,
            read_verified=True,
            enabled=True,
            tenant=SYNTHETIC_TENANT,
            activation=ACTIVATION_VERIFIED,
        )
        adapter = PublicGhlAdapter(
            auth=fake_auth(),
            operations={READ_ROW["operation_id"]: READ_ROW},
            transport=transport,
            capability=CapabilityGate(
                {"kb.files.get": read_capability}, tenant=SYNTHETIC_TENANT
            ),
        )
        result = adapter.call(
            operation_id="kb.files.get",
            tenant=fake_tenant(),
            path_params={"id": "kb1", "fileId": "f1"},
        )
        self.assertEqual(result.evidence["request_media_type"], JSON_MEDIA_TYPE)
        self.assertEqual(transport.multipart_requests, [])


if __name__ == "__main__":
    unittest.main()
