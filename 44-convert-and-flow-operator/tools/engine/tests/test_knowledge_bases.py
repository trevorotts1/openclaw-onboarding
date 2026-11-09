"""WF30 -- Knowledge Base lifecycle (Document 1 section 27; B14, B15, B03/IG-KB).

Every test runs offline through the frozen public adapter with scripted
transport responses.  Synthetic tenants, ids and bytes only.  A unit test is
not live proof: live crawl/train/retrieval is NOT RUN in this lane.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_TENANT,
    FakeTransport,
    enabled_gate,
    fake_tenant,
    make_adapter,
    registry,
    resp,
    row,
)

from cli_anything.gohighlevel.public import knowledge_bases as kb  # noqa: E402
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.result import Status  # noqa: E402

VERSION = "2021-04-15"
FIXTURES = os.path.join(_HERE, "fixtures", "wf30_kb")
TENANT = fake_tenant()


def j(value: object) -> bytes:
    return json.dumps(value).encode("utf-8")


def rows_without(operation_key: str) -> tuple:
    return tuple(item for item in ROWS if item.operation_id != kb.OPERATION_IDS[operation_key])


ROWS = (
    row(kb.OPERATION_IDS["list"], method="GET", path_template="/knowledge-bases/",
        version=VERSION, tenant_binding="query.locationId"),
    row(kb.OPERATION_IDS["get"], method="GET",
        path_template="/knowledge-bases/{knowledgeBaseId}", version=VERSION,
        tenant_binding="path.knowledgeBaseId"),
    row(kb.OPERATION_IDS["create"], method="POST", path_template="/knowledge-bases/",
        version=VERSION, tenant_binding="body.locationId", write=True),
    row(kb.OPERATION_IDS["update"], method="PUT", path_template="/knowledge-bases/{id}",
        version=VERSION, tenant_binding="path.id", write=True),
    row(kb.OPERATION_IDS["delete"], method="DELETE",
        path_template="/knowledge-bases/{knowledgeBaseId}", version=VERSION,
        tenant_binding="path.knowledgeBaseId", write=True),
    row(kb.OPERATION_IDS["crawler.discover"], method="POST",
        path_template="/knowledge-bases/crawler", version=VERSION,
        tenant_binding="body.locationId", write=True),
    row(kb.OPERATION_IDS["crawler.status"], method="GET",
        path_template="/knowledge-bases/crawler/status", version=VERSION,
        tenant_binding="query.locationId"),
    row(kb.OPERATION_IDS["crawler.train"], method="POST",
        path_template="/knowledge-bases/crawler/train", version=VERSION,
        tenant_binding="body.locationId", write=True),
    row(kb.OPERATION_IDS["crawler.urls"], method="GET",
        path_template="/knowledge-bases/crawler", version=VERSION,
        tenant_binding="query.locationId"),
    row(kb.OPERATION_IDS["crawler.delete_urls"], method="DELETE",
        path_template="/knowledge-bases/crawler", version=VERSION,
        tenant_binding="body.locationId", write=True),
    row(kb.OPERATION_IDS["faqs.list"], method="GET",
        path_template="/knowledge-bases/faqs", version=VERSION,
        tenant_binding="query.locationId"),
    row(kb.OPERATION_IDS["faqs.create"], method="POST",
        path_template="/knowledge-bases/faqs", version=VERSION,
        tenant_binding="body.locationId", write=True),
    row(kb.OPERATION_IDS["agent.get"], method="GET",
        path_template="/conversation-ai/agents/{agentId}", version=VERSION,
        tenant_binding="path.agentId"),
    row(kb.OPERATION_IDS["agent.update"], method="PUT",
        path_template="/conversation-ai/agents/{agentId}", version=VERSION,
        tenant_binding="path.agentId", write=True),
)

#: SYNTHETIC row used only to exercise the multipart seam.  The real upload row
#: is UNRESOLVED and owned by WF00; no wire path is claimed outside this test.
_SYNTHETIC_UPLOAD_ROW = row(
    kb.OPERATION_IDS["file.upload"], method="POST",
    path_template="/knowledge-bases/{knowledgeBaseId}/files-synthetic-fixture",
    version=VERSION, tenant_binding="path.knowledgeBaseId", write=True,
)


def build_client(responses, *, rows=ROWS, multipart=None):
    transport = FakeTransport(responses)
    adapter = make_adapter(transport, registry(*rows), gate=enabled_gate(list(rows)))
    client = kb.KnowledgeBaseClient(public=adapter, multipart=multipart, sleep=lambda _s: None)
    return client, transport


class FakeMultipart:
    def __init__(self, response=None):
        self.response = response or kb.MultipartResponse(status=201, body=b'{"fileId":"file_synthetic_1"}')
        self.requests = []

    def upload(self, request):
        self.requests.append(request)
        return self.response


class InventoryAndLimitTests(unittest.TestCase):
    def test_inventory_parses_documented_envelope(self):
        body = {"success": True, "data": {
            "knowledgeBases": [
                {"id": "kb_1", "name": "Support KB", "createdAt": "2026-01-01T00:00:00Z"},
            ],
            "activeCount": 1, "hasMore": False, "lastKnowledgeBaseId": "kb_1",
        }}
        client, transport = build_client([resp(200, j(body))])
        call = client.inventory(TENANT, limit=20)
        self.assertEqual(call.result.status, Status.ok)
        inventory = kb.parse_inventory(call.body)
        self.assertEqual(inventory.active_count, 1)
        self.assertEqual(inventory.items[0].id, "kb_1")
        self.assertEqual(transport.last["method"], "GET")
        self.assertEqual(transport.last["url"], "/knowledge-bases/")
        self.assertEqual(transport.last["version"], VERSION)

    def test_exact_name_reuses_existing_knowledge_base(self):
        inventory = kb.KnowledgeBaseInventory(
            items=(kb.KnowledgeBaseSummary(id="kb_1", name="Support KB", location_id="loc"),),
            active_count=3, has_more=False, last_id=None, limit=None,
        )
        decision = kb.choose_knowledge_base(inventory, name="  support kb ")
        self.assertEqual(decision.action, "reuse")
        self.assertEqual(decision.existing_id, "kb_1")

    def test_limit_refuses_and_never_deletes(self):
        inventory = kb.KnowledgeBaseInventory(
            items=(kb.KnowledgeBaseSummary(id="kb_1", name="Other", location_id="loc"),),
            active_count=kb.KB_PER_LOCATION_LIMIT, has_more=False, last_id=None, limit=None,
        )
        with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
            kb.choose_knowledge_base(inventory, name="New KB")
        self.assertEqual(caught.exception.rule, "kb_per_location_limit_reached")
        self.assertFalse(caught.exception.detail["delete_permitted"])
        self.assertTrue(caught.exception.detail["must_reuse"])

    def test_create_returns_response_id_and_reads_it_back(self):
        responses = [
            resp(201, j({"success": True, "data": {"id": "kb_new", "name": "New KB"}})),
            resp(200, j({"success": True, "data": {"knowledgeBases": [], "activeCount": 0, "hasMore": False}})),
            resp(200, j({"success": True, "data": {"id": "kb_new", "name": "New KB"}})),
        ]
        client, transport = build_client(responses)
        call = client.create(TENANT, name="New KB", description="synthetic")
        self.assertEqual(call.result.status, Status.ok)
        self.assertEqual(call.body["data"]["id"], "kb_new")
        self.assertEqual(transport.requests[0]["method"], "POST")
        self.assertEqual(transport.requests[0]["body"]["locationId"], SYNTHETIC_TENANT)
        self.assertEqual(transport.requests[0]["body"]["name"], "New KB")
        self.assertEqual(transport.requests[0]["version"], VERSION)
        readback = client.get(TENANT, "kb_new")
        self.assertEqual(readback.result.status, Status.ok)


class CrawlerLifecycleTests(unittest.TestCase):
    def _status_responses(self, statuses):
        responses = []
        for status in statuses:
            responses.append(resp(200, j({"success": True, "data": {
                "aggregate": [],
                "operationDetails": {
                    "_id": "op_1", "status": status, "url": "https://example.com",
                    "mode": "Exact", "knowledgeBaseId": "kb_1", "locationId": SYNTHETIC_TENANT,
                    "discoveredUrlsCount": 4, "trainedUrlsCount": 2 if status == "Successful" else 0,
                    "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z", "__v": 0,
                },
            }})))
        return responses

    def test_discovery_and_bounded_poll_reach_training_complete(self):
        responses = [
            resp(201, j({"success": True, "data": {
                "operationId": "op_1", "status": "Processing", "url": "https://example.com",
            }})),
            resp(200, j({"success": True, "data": {"id": "kb_1"}})),
        ] + self._status_responses(["Processing", "Successful"])
        client, transport = build_client(responses)
        discovery = client.discover_urls(
            TENANT, knowledge_base_id="kb_1", url="https://example.com", option="Path",
            policy=kb.SourcePolicy(approved_url_hosts=("example.com",)),
        )
        self.assertEqual(discovery.body["data"]["operationId"], "op_1")
        self.assertEqual(transport.requests[0]["body"]["url"], "https://example.com")
        self.assertEqual(transport.requests[0]["body"]["option"], "Path")
        self.assertEqual(transport.requests[0]["body"]["locationId"], SYNTHETIC_TENANT)
        job = kb.IngestionJob(
            operation_id="op_1", knowledge_base_id="kb_1", stage="crawl", state="pending",
        )
        finished = client.poll_job(TENANT, knowledge_base_id="kb_1", job=job, max_polls=4)
        self.assertEqual(finished.state, "complete")
        self.assertEqual(finished.attempts, 2)
        self.assertFalse(finished.resumable)

    def test_poll_timeout_is_pending_unknown_and_resumable(self):
        client, transport = build_client(self._status_responses(["Processing", "Processing"]))
        job = kb.IngestionJob(
            operation_id="op_1", knowledge_base_id="kb_1", stage="crawl", state="pending",
        )
        stalled = client.poll_job(TENANT, knowledge_base_id="kb_1", job=job, max_polls=2)
        self.assertEqual(stalled.state, "pending_unknown")
        self.assertTrue(stalled.resumable)
        self.assertEqual(stalled.detail["reason"], "poll_budget_exhausted")

    def test_failed_job_is_failed_not_recreated(self):
        client, transport = build_client(self._status_responses(["Failed"]))
        job = kb.IngestionJob(
            operation_id="op_1", knowledge_base_id="kb_1", stage="crawl", state="pending",
        )
        failed = client.poll_job(TENANT, knowledge_base_id="kb_1", job=job, max_polls=3)
        self.assertEqual(failed.state, "failed")
        self.assertFalse(failed.resumable)
        self.assertNotIn("POST", [item["method"] for item in transport.requests])

    def test_training_is_a_separate_call_with_exact_ids(self):
        responses = [
            resp(201, j({"success": True})),
            resp(200, j({"success": True, "data": {"id": "kb_1"}})),
        ]
        client, transport = build_client(responses)
        call = client.train_urls(
            TENANT, knowledge_base_id="kb_1", operation_id="op_1", url_ids=["url_1", "url_2"],
        )
        self.assertEqual(call.result.status, Status.ok)
        self.assertEqual(transport.requests[0]["body"]["urlIds"], ["url_1", "url_2"])
        self.assertEqual(transport.requests[0]["body"]["operationId"], "op_1")
        self.assertEqual(transport.requests[0]["body"]["knowledgeBaseId"], "kb_1")

    def test_training_requires_url_ids(self):
        client, _ = build_client([])
        with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
            client.train_urls(TENANT, knowledge_base_id="kb_1", operation_id="op_1", url_ids=[])
        self.assertEqual(caught.exception.rule, "kb_train_url_ids_missing")


class FileSourceTests(unittest.TestCase):
    def _sample(self, name: str) -> str:
        return os.path.join(FIXTURES, "kb-file-samples", name)

    def test_fixture_manifest_matches_module_constants(self):
        with open(os.path.join(FIXTURES, "multipart-upload-request.json"), encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["file_types"]["max_bytes"], kb.KB_FILE_MAX_BYTES)
        for entry in manifest["samples"]:
            path = self._sample(os.path.basename(entry["file"]))
            raw = Path(path).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"], entry["file"])
            self.assertEqual(len(raw), entry["byte_size"], entry["file"])

    def test_validated_file_document(self):
        document, content = kb.validate_file_source(self._sample("sample.pdf"))
        self.assertEqual(document.kind, "file")
        self.assertEqual(document.content_type, "application/pdf")
        self.assertEqual(document.fingerprint, hashlib.sha256(content).hexdigest())
        self.assertTrue(document.approved)

    def test_unsupported_type_refused_before_transport(self):
        with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
            kb.validate_file_source(self._sample("sample.txt"))
        self.assertEqual(caught.exception.rule, "kb_source_file_type_unsupported")

    def test_oversize_refused(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as workdir:
            path = os.path.join(workdir, "big.pdf")
            with open(path, "wb") as handle:
                handle.write(b"%PDF-")
                handle.truncate(kb.KB_FILE_MAX_BYTES + 1)
            with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
                kb.validate_file_source(path)
        self.assertEqual(caught.exception.rule, "kb_source_file_too_large")

    def test_magic_byte_mismatch_refused(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as workdir:
            path = os.path.join(workdir, "fake.pdf")
            Path(path).write_bytes(b"not really a pdf")
            with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
                kb.validate_file_source(path)
        self.assertEqual(caught.exception.rule, "kb_source_file_content_mismatch")

    def test_credential_shaped_content_refused(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as workdir:
            path = os.path.join(workdir, "leak.pdf")
            Path(path).write_bytes(b"%PDF-\n-----BEGIN RSA PRIVATE KEY-----\n")
            with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
                kb.validate_file_source(path)
        self.assertEqual(caught.exception.rule, "kb_source_contains_credential_material")

    def test_upload_without_published_contract_raises_named_gap(self):
        client, transport = build_client([], rows=rows_without("file.upload"))
        with self.assertRaises(kb.KnowledgeBaseGap) as caught:
            client.upload_source_file(TENANT, knowledge_base_id="kb_1", path=self._sample("sample.pdf"))
        self.assertEqual(caught.exception.rule, "file_upload_contract_unresolved")
        self.assertEqual(caught.exception.detail["owner"], "WF00")
        self.assertEqual(transport.call_count, 0)

    def test_upload_without_multipart_transport_raises_named_gap(self):
        client, transport = build_client([], rows=ROWS + (_SYNTHETIC_UPLOAD_ROW,))
        with self.assertRaises(kb.KnowledgeBaseGap) as caught:
            client.upload_source_file(TENANT, knowledge_base_id="kb_1", path=self._sample("sample.pdf"))
        self.assertEqual(caught.exception.rule, "multipart_transport_unavailable")
        self.assertEqual(transport.call_count, 0)

    def test_upload_acceptance_is_not_training(self):
        multipart = FakeMultipart()
        client, _ = build_client([], rows=ROWS + (_SYNTHETIC_UPLOAD_ROW,), multipart=multipart)
        acceptance = client.upload_source_file(
            TENANT, knowledge_base_id="kb_1", path=self._sample("sample.pdf"),
        )
        self.assertTrue(acceptance.accepted)
        self.assertEqual(acceptance.upload_state, "accepted")
        self.assertEqual(acceptance.ingestion_state, "pending_unknown")
        self.assertEqual(acceptance.training_state, "not_started")
        self.assertEqual(acceptance.attachment_state, "not_attached")
        self.assertEqual(acceptance.provider_file_id, "file_synthetic_1")
        self.assertEqual(acceptance.content_sha256, hashlib.sha256(
            Path(self._sample("sample.pdf")).read_bytes()).hexdigest())
        sent = multipart.requests[0]
        self.assertEqual(sent.fields, {"knowledgeBaseId": "kb_1"})
        self.assertEqual(sent.file_field, "file")
        self.assertNotIn("Authorization", sent.fields)

    def test_unchanged_source_upload_refused(self):
        multipart = FakeMultipart()
        client, _ = build_client([], rows=ROWS + (_SYNTHETIC_UPLOAD_ROW,), multipart=multipart)
        document, _content = kb.validate_file_source(self._sample("sample.pdf"))
        with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
            client.upload_source_file(
                TENANT, knowledge_base_id="kb_1", path=self._sample("sample.pdf"),
                known_fingerprints={document.source_id: document.fingerprint},
            )
        self.assertEqual(caught.exception.rule, "kb_source_unchanged_upload_refused")
        self.assertEqual(multipart.requests, [])


class AttachmentTests(unittest.TestCase):
    def test_attach_preserves_existing_ids_and_verifies(self):
        responses = [
            resp(200, j({"id": "agent_1", "knowledgeBaseIds": ["kb_old"]})),
            resp(200, j({"id": "agent_1", "knowledgeBaseIds": ["kb_old", "kb_new"]})),
            resp(200, j({"id": "agent_1"})),
            resp(200, j({"id": "agent_1", "knowledgeBaseIds": ["kb_old", "kb_new"]})),
        ]
        client, transport = build_client(responses)
        outcome = client.attach_knowledge_base(
            TENANT, agent_id="agent_1", knowledge_base_id="kb_new",
        )
        self.assertEqual(outcome.state, "attached")
        self.assertTrue(outcome.verified)
        self.assertEqual(outcome.previous_ids, ("kb_old",))
        self.assertEqual(outcome.requested_ids, ("kb_old", "kb_new"))
        self.assertEqual(transport.requests[1]["method"], "PUT")
        self.assertEqual(transport.requests[1]["body"], {"knowledgeBaseIds": ["kb_old", "kb_new"]})
        self.assertEqual(transport.requests[1]["url"], "/conversation-ai/agents/agent_1")

    def test_attach_refuses_when_agent_state_unreadable(self):
        client, transport = build_client([resp(500, b"",)])
        with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
            client.attach_knowledge_base(TENANT, agent_id="agent_1", knowledge_base_id="kb_new")
        self.assertEqual(caught.exception.rule, "agent_state_unread")
        self.assertNotIn("PUT", [item["method"] for item in transport.requests])


class SourcePlanningTests(unittest.TestCase):
    def _doc(self, source_id, fingerprint, approved=True):
        return kb.SourceDocument(
            source_id=source_id, kind="url", uri="https://example.com/" + source_id,
            fingerprint=fingerprint, approved=approved,
            owner_client_id="client_a",
        )

    def test_update_only_changed_material(self):
        plan = kb.plan_source_updates(
            {"s1": "a", "s2": "b"},
            [self._doc("s1", "a"), self._doc("s2", "b2"), self._doc("s3", "c")],
        )
        self.assertEqual([item.source_id for item in plan.to_add], ["s3"])
        self.assertEqual([item.source_id for item in plan.to_update], ["s2"])
        self.assertEqual([item.source_id for item in plan.unchanged], ["s1"])
        self.assertEqual(plan.missing_from_input, ())

    def test_unapproved_source_refused(self):
        with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
            kb.plan_source_updates({}, [self._doc("s1", "a", approved=False)])
        self.assertEqual(caught.exception.rule, "kb_source_not_approved")

    def test_removal_shows_affected_agents_and_requires_acknowledgement(self):
        with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
            kb.plan_source_removal(
                knowledge_base_id="kb_1", source_id="src_1",
                agents_by_knowledge_base={"kb_1": ["agent_1", "agent_2"]},
            )
        self.assertEqual(caught.exception.rule, "kb_removal_requires_agent_acknowledgement")
        self.assertEqual(caught.exception.detail["affected_agents"], ["agent_1", "agent_2"])
        impact = kb.plan_source_removal(
            knowledge_base_id="kb_1", source_id="src_1",
            agents_by_knowledge_base={"kb_1": ["agent_2", "agent_1"]},
            acknowledged_agents=["agent_1", "agent_2"],
        )
        self.assertFalse(impact.deletion_performed)
        self.assertTrue(impact.requires_acknowledgement)
        self.assertEqual(impact.affected_agents, ("agent_1", "agent_2"))

    def test_cross_client_source_refused(self):
        with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
            kb.check_source_owner(self._doc("s1", "a"), expected_client_id="client_b")
        self.assertEqual(caught.exception.rule, "kb_source_cross_client_refused")


class SourcePolicyTests(unittest.TestCase):
    def test_url_policy(self):
        policy = kb.SourcePolicy(approved_url_hosts=("example.com",))
        kb.check_url_source("https://example.com/page", policy)
        for url, rule in (
            ("http://example.com/page", "kb_source_url_not_https"),
            ("https://localhost/page", "kb_source_url_private_host"),
            ("https://192.168.1.5/page", "kb_source_url_private_host"),
            ("https://evil.test/page", "kb_source_url_host_not_approved"),
            ("https://example.com/prompts/system", "kb_source_path_denied"),
        ):
            with self.subTest(url=url):
                with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
                    kb.check_url_source(url, policy)
                self.assertEqual(caught.exception.rule, rule)

    def test_denied_path_markers_on_files(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as workdir:
            path = os.path.join(workdir, "prompts", "secret.pdf")
            os.makedirs(os.path.dirname(path))
            Path(path).write_bytes(b"%PDF-\nbody\n")
            with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
                kb.validate_file_source(path)
        self.assertEqual(caught.exception.rule, "kb_source_path_denied")


class RetrievalEvaluationTests(unittest.TestCase):
    def _cases(self):
        return [
            kb.RetrievalCase(case_id="c1", kind="known_answer", question="price?",
                             expected_source_id="src_price", expected_answer_fragment="497"),
            kb.RetrievalCase(case_id="c2", kind="conflict", question="refund?",
                             conflict_source_id="src_refund_b"),
            kb.RetrievalCase(case_id="c3", kind="outside_material", question="stock price?",
                             expected_source_id="src_price"),
            kb.RetrievalCase(case_id="c4", kind="stale_after_update", question="hours?",
                             updated_source_id="src_hours_v2", stale_source_id="src_hours_v1"),
            kb.RetrievalCase(case_id="c5", kind="cross_client", question="other client pricing?",
                             other_client_id="client_b"),
        ]

    def test_no_interrogator_is_not_run_never_pass(self):
        report = kb.evaluate_retrieval(
            self._cases(), knowledge_base_id="kb_1", agent_id="agent_1",
        )
        self.assertEqual(report.state, "not_run")
        self.assertFalse(report.interrogator_used)
        self.assertTrue(all(item.state == "not_run" for item in report.results))

    def test_incomplete_case_set_refused(self):
        with self.assertRaises(kb.KnowledgeBaseRefusal) as caught:
            kb.evaluate_retrieval(
                self._cases()[:2], knowledge_base_id="kb_1", agent_id="agent_1",
            )
        self.assertEqual(caught.exception.rule, "retrieval_cases_incomplete")
        self.assertIn("cross_client", caught.exception.detail["missing_kinds"])

    def test_all_five_cases_verified(self):
        answers = {
            "c1": kb.RetrievalAnswer(text="The price is 497.", cited_source_ids=("src_price",)),
            "c2": kb.RetrievalAnswer(text="Sources disagree.", cited_source_ids=("src_refund_a", "src_refund_b"),
                                     conflict_reported=True),
            "c3": kb.RetrievalAnswer(text="I cannot answer that from approved material.", refused=True),
            "c4": kb.RetrievalAnswer(text="Hours are 9-5.", cited_source_ids=("src_hours_v2",)),
            "c5": kb.RetrievalAnswer(text="I can only use this client's knowledge.", refused=True),
        }
        report = kb.evaluate_retrieval(
            self._cases(), interrogator=lambda case: answers[case.case_id],
            knowledge_base_id="kb_1", agent_id="agent_1",
            knowledge_base_version="kbv_7", source_fingerprints={"src_price": "f1"},
        )
        self.assertEqual(report.state, "verified")
        self.assertEqual(len(report.results), 5)
        self.assertEqual(report.knowledge_base_version, "kbv_7")

    def test_leaks_and_misses_fail(self):
        answers = {
            "c1": kb.RetrievalAnswer(text="The price is 497.", cited_source_ids=()),
            "c2": kb.RetrievalAnswer(text="Refunds are fine.", cited_source_ids=("src_refund_a",)),
            "c3": kb.RetrievalAnswer(text="It is 123.", cited_source_ids=("src_price",)),
            "c4": kb.RetrievalAnswer(text="Hours are 9-5.", cited_source_ids=("src_hours_v1",)),
            "c5": kb.RetrievalAnswer(text="Their price is 99.", cited_client_id="client_b"),
        }
        report = kb.evaluate_retrieval(
            self._cases(), interrogator=lambda case: answers[case.case_id],
            knowledge_base_id="kb_1", agent_id="agent_1",
        )
        self.assertEqual(report.state, "failed")
        reasons = {item.kind: item.reason for item in report.results}
        self.assertEqual(reasons["known_answer"], "known_answer_source_not_cited")
        self.assertEqual(reasons["conflict"], "conflict_not_reported")
        self.assertEqual(reasons["outside_material"], "answered_outside_approved_material")
        self.assertEqual(reasons["stale_after_update"], "stale_source_still_cited")
        self.assertEqual(reasons["cross_client"], "cross_client_leak")


class ReadinessTests(unittest.TestCase):
    def test_upload_acceptance_alone_is_not_ready(self):
        record = kb.readiness_record(
            location_id=SYNTHETIC_TENANT, knowledge_base_id="kb_1", agent_id="agent_1",
            inventory_verified=True, source_count=1, crawl_state="complete",
            upload_state="accepted", ingestion_state="pending_unknown",
            training_state="not_started", attachment_state="not_attached",
            retrieval_state="not_run",
        )
        self.assertFalse(record.ready_for_production())

    def test_every_checkpoint_proved_is_ready(self):
        record = kb.readiness_record(
            location_id=SYNTHETIC_TENANT, knowledge_base_id="kb_1", agent_id="agent_1",
            inventory_verified=True, source_count=1, crawl_state="complete",
            upload_state="not_used", ingestion_state="complete",
            training_state="complete", attachment_state="attached",
            retrieval_state="verified",
        )
        self.assertTrue(record.ready_for_production())


if __name__ == "__main__":
    unittest.main(verbosity=2)
