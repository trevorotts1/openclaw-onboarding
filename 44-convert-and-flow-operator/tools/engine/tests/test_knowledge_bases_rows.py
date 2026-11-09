"""WF30 -- knowledge-base rows must resolve through the REAL operation registry.

This is the row-resolution test.  It is the one test that reads
``public/operations.py`` itself rather than a synthetic row table, so a green
run here is the only evidence that the KB surface is wired to the frozen
registry instead of a fixture.

The sixteen ids below are the operations the KB lifecycle calls that were
absent before WF00 CP04.  The seventeenth (``knowledge_bases.sources.upload``)
is deliberately a GAP row: the vendor publishes no file-source upload
operation, so it must stay ``UNKNOWN``/``feature_gap`` and is never given an
invented route.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    FakeTransport,
    RecordingOpener,
    StubResponse,
    enabled_gate,
    fake_tenant,
    make_adapter,
    registry,
    row,
)

from cli_anything.gohighlevel.public import knowledge_bases as kb  # noqa: E402
from cli_anything.gohighlevel.public.operations import (  # noqa: E402
    OPERATIONS,
    SUPPORTED_VERSIONS,
    UNKNOWN,
)
from cli_anything.gohighlevel.public.transport import RequestsTransport  # noqa: E402

#: The sixteen KB-lifecycle operations that were missing before WF00 CP04.
PREVIOUSLY_MISSING = (
    "knowledge_bases.list",
    "knowledge_bases.get",
    "knowledge_bases.create",
    "knowledge_bases.update",
    "knowledge_bases.delete",
    "knowledge_bases.crawler.discover",
    "knowledge_bases.crawler.status",
    "knowledge_bases.crawler.train",
    "knowledge_bases.crawler.urls",
    "knowledge_bases.crawler.delete_urls",
    "knowledge_bases.faqs.list",
    "knowledge_bases.faqs.create",
    "knowledge_bases.faqs.update",
    "knowledge_bases.faqs.delete",
    "conversation_ai.agents.get",
    "conversation_ai.agents.update",
)

UPLOAD_ID = "knowledge_bases.sources.upload"
FIXTURES = os.path.join(_HERE, "fixtures", "wf30_kb")
TENANT = fake_tenant()
VERSION = "2021-04-15"

class RegistryResolutionTests(unittest.TestCase):
    def test_registry_is_the_cp04_206_row_contract(self):
        # CP04 evidence: 206 rows, 206 distinct.
        self.assertEqual(len(OPERATIONS), 206)
        self.assertEqual(len({row.operation_id for row in OPERATIONS.values()}), 206)

    def test_all_sixteen_previously_missing_ids_resolve(self):
        missing = [op for op in PREVIOUSLY_MISSING if op not in OPERATIONS]
        self.assertEqual(missing, [], f"still absent: {missing}")

    def test_every_operation_id_the_kb_module_calls_resolves(self):
        missing = sorted(
            op for op in kb.OPERATION_IDS.values() if op not in OPERATIONS
        )
        self.assertEqual(missing, [], f"KB module references absent rows: {missing}")

    def test_resolved_rows_carry_a_real_wire_contract(self):
        for operation_id in PREVIOUSLY_MISSING:
            with self.subTest(operation_id=operation_id):
                frozen = OPERATIONS[operation_id]
                self.assertIn(frozen.method.upper(), {"GET", "POST", "PUT", "PATCH", "DELETE"})
                self.assertTrue(frozen.path_template.startswith("/"))
                self.assertNotEqual(frozen.path_template, UNKNOWN)
                self.assertIsNotNone(frozen.version)
                self.assertIn(frozen.version, SUPPORTED_VERSIONS)
                self.assertEqual(frozen.resolved_availability, "public")
                self.assertIsNotNone(frozen.doc_url)
                self.assertIsNotNone(frozen.doc_fetch_date)

    def test_version_literals_are_per_row_never_a_global_default(self):
        # A KB row must not inherit a Version from another family.
        versions = {OPERATIONS[op].version for op in PREVIOUSLY_MISSING}
        self.assertEqual(versions, {VERSION})

class UploadGapRowTests(unittest.TestCase):
    def test_upload_row_is_a_named_gap_not_an_invented_route(self):
        frozen = OPERATIONS[UPLOAD_ID]
        self.assertEqual(frozen.path_template, UNKNOWN)
        self.assertEqual(frozen.version, None)
        self.assertEqual(frozen.resolved_availability, "feature_gap")
        self.assertEqual(frozen.blocker, "B-NO-CONTRACT")
        self.assertEqual(frozen.route_class, "capability_gap")
        self.assertEqual(frozen.request_media_type, "multipart/form-data")
        self.assertTrue(frozen.write)
        self.assertTrue(frozen.unresolved_fields)

    def test_upload_refuses_against_the_real_registry_and_names_the_blocker(self):
        transport = FakeTransport()
        adapter = make_adapter(transport, OPERATIONS, gate=enabled_gate(tuple(OPERATIONS.values())))
        client = kb.KnowledgeBaseClient(public=adapter, sleep=lambda _s: None)
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as workdir:
            source = Path(workdir) / "sample.pdf"
            source.write_bytes(Path(FIXTURES, "kb-file-samples", "sample.pdf").read_bytes())
            with self.assertRaises(kb.KnowledgeBaseGap) as caught:
                client.upload_source_file(TENANT, knowledge_base_id="kb_1", path=source)
        self.assertEqual(caught.exception.rule, "file_upload_contract_unresolved")
        self.assertEqual(caught.exception.detail["blocker"], "B-NO-CONTRACT")
        self.assertEqual(caught.exception.detail["availability"], "feature_gap")
        self.assertEqual(transport.call_count, 0)

class MultipartSeamTests(unittest.TestCase):
    def test_kb_client_auto_binds_the_real_multipart_seam(self):
        # WF01's transport is present on this branch; the client must wire it
        # rather than refuse with multipart_transport_unavailable.
        transport = RequestsTransport(opener=RecordingOpener())
        adapter = make_adapter(FakeTransport(), OPERATIONS, gate=enabled_gate(tuple(OPERATIONS.values())))
        adapter._transport = transport
        client = kb.KnowledgeBaseClient(public=adapter, sleep=lambda _s: None)
        self.assertIsInstance(client._multipart, kb.TransportMultipartSeam)

    def test_documented_row_upload_travels_as_real_multipart(self):
        documented = row(
            kb.OPERATION_IDS["file.upload"],
            method="POST",
            path_template="/knowledge-bases/{knowledgeBaseId}/files",
            version=VERSION,
            route_class="public_direct",
            tenant_binding="path.knowledgeBaseId",
            write=True,
        )
        rows = (documented,)
        opener = RecordingOpener(StubResponse(status=201, body=b'{"fileId":"file_1"}'))
        transport = RequestsTransport(opener=opener)
        adapter = make_adapter(FakeTransport(), registry(*rows), gate=enabled_gate(rows))
        adapter._transport = transport
        client = kb.KnowledgeBaseClient(public=adapter, sleep=lambda _s: None)
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as workdir:
            source = Path(workdir) / "sample.pdf"
            source.write_bytes(Path(FIXTURES, "kb-file-samples", "sample.pdf").read_bytes())
            acceptance = client.upload_source_file(
                TENANT, knowledge_base_id="kb_1", path=source
            )
        self.assertTrue(acceptance.accepted)
        self.assertEqual(acceptance.http_status, 201)
        self.assertEqual(acceptance.provider_file_id, "file_1")
        sent = opener.last
        self.assertEqual(sent.get_method(), "POST")
        self.assertTrue(sent.full_url.endswith("/knowledge-bases/kb_1/files"))
        content_type = sent.get_header("Content-type")
        self.assertTrue(content_type.startswith("multipart/form-data; boundary="))
        body = sent.data
        self.assertIn(b'name="knowledgeBaseId"', body)
        self.assertIn(b'name="file"; filename="sample.pdf"', body)
        self.assertIn(b"Content-Type: application/pdf", body)
        self.assertIn(b"%PDF-", body)
        # The credential never travels as a form field.
        self.assertNotIn(b"authorization", body.lower())

if __name__ == "__main__":
    unittest.main()
