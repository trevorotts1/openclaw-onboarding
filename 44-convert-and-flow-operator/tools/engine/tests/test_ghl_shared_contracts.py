"""WF00 shared operation-contract and schema suite (registry side).

Covers the WF00 acceptance ids without inventing a second registry:

* A18  -- Skill 29 current claims match the executable registry and source
          evidence: every registry row exports one contract document, and the
          corpus is internally coherent (no duplicate ids, no v4 literal, no
          global version default).
* B01  -- Shared registry / inventory / router / Skill 6 bridge agree: the
          registry is the single authority and every exported contract is valid
          against ``operation-contract.schema.json``.
* IG-ROUTE-06 -- registry, capability map and contract documents describe the
                 same operation and route.
* IG-ROUTE-07 -- per-operation versions, widget schema versions, workflow
                 revisions and agent version ids remain distinct.
* IG-WF-01     -- production workflow rows reflect verified V3 contracts; no
                 obsolete staging v4 request escapes.
* IG-AUTH-03   -- a successful read never enables the corresponding
                 create/update/publish operation.

Every test is offline.  No token, account, network or live call is involved.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from cli_anything.gohighlevel.public.operations import (  # noqa: E402
    OPERATIONS,
    RECEIPT_OUTCOMES,
    contract_documents,
    capability_map,
)

_ROOT = Path(__file__).resolve().parents[4]
_CONTRACTS = _ROOT / "shared-utils" / "ghl" / "contracts"


def _load_contracts_module():
    spec = importlib.util.spec_from_file_location(
        "ghl_shared_contracts_validate", _CONTRACTS / "validate.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - broken install
        raise AssertionError(f"cannot load {_CONTRACTS / 'validate.py'}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONTRACTS = _load_contracts_module()

_WORKFLOW_FAMILY = {
    "workflows.step_types.list",
    "workflows.definition.validate",
    "workflows.search",
    "workflows.definition.create",
    "workflows.definition.read",
    "workflows.definition.update",
    "workflows.status.publish",
    "workflows.definition.delete",
    "workflows.logs.list",
    "workflows.logs",
    "workflows.logs.aggregate",
}

_DOCUMENTED_WRITE_KEYS = {
    "workflows.definition.create",
    "workflows.definition.update",
    "workflows.status.publish",
    "workflows.definition.delete",
}


def _fixtures(kind: str) -> list[Path]:
    directory = _CONTRACTS / "fixtures" / kind
    return sorted(directory.glob("*.json"))


def _contract_name_for(path: Path) -> str:
    prefix = path.name.split(".")[0]
    mapping = {
        "operation-contract": "operation-contract",
        "capability-record": "capability-record.v2",
        "hybrid-operation-receipt": "hybrid-operation-receipt.v1",
        "course-build-plan": "course-build-plan.v1",
        "course-asset-manifest": "course-asset-manifest.v1",
        "learning-association": "learning-association.v1",
        "course-delivery-receipt": "course-delivery-receipt.v1",
    }
    if prefix not in mapping:
        raise AssertionError(f"fixture {path.name} has no contract mapping")
    return mapping[prefix]


class RegistryContractDocumentsTest(unittest.TestCase):
    """A18 / B01 / IG-ROUTE-06 -- one authority, one exported shape."""

    def test_every_registry_row_exports_one_valid_contract_document(self) -> None:
        documents = contract_documents()
        self.assertEqual(len(documents), len(OPERATIONS))
        seen: set[str] = set()
        for document in documents:
            operation_id = document["operation_id"]
            with self.subTest(operation_id=operation_id):
                self.assertNotIn(operation_id, seen, "duplicate contract document")
                seen.add(operation_id)
                CONTRACTS.validate("operation-contract", document)
        self.assertEqual(seen, set(OPERATIONS))

    def test_contract_documents_agree_with_the_registry_rows(self) -> None:
        by_id = {document["operation_id"]: document for document in contract_documents()}
        for operation_id, row in OPERATIONS.items():
            with self.subTest(operation_id=operation_id):
                document = by_id[operation_id]
                self.assertEqual(document["method"], row.method)
                self.assertEqual(document["path_template"], row.path_template)
                self.assertEqual(document["version"], row.version)
                self.assertEqual(document["effect"], row.resolved_effect)
                self.assertEqual(document["approval_class"], row.resolved_approval_class)
                self.assertEqual(
                    document["identity_placement"], row.identity_placement
                )
                self.assertEqual(document["token_class"], row.token_class)
                self.assertEqual(
                    document["implementation"], row.implementation
                )

    def test_capability_map_describes_the_same_operations_and_routes(self) -> None:
        expected_transports = {
            "public_rest": ["api"],
            "official_mcp": ["mcp"],
            "skill44_private": ["api"],
            "skill06_browser": ["browser"],
            "unresolved": [],
            "excluded": [],
        }
        mapping = capability_map()
        self.assertEqual(set(mapping), set(OPERATIONS))
        for operation_id, row in OPERATIONS.items():
            entry = mapping[operation_id]
            with self.subTest(operation_id=operation_id):
                self.assertEqual(entry["routeClass"], row.route_class)
                self.assertEqual(entry["implementation"], row.implementation)
                self.assertEqual(entry["effect"], row.resolved_effect)
                self.assertEqual(
                    entry["transports"], expected_transports[row.implementation]
                )
                self.assertNotIn("enabled", entry, "the registry carries no enablement")

    def test_no_registry_row_carries_enablement(self) -> None:
        # IG-AUTH-03 / freeze 3.2 rule 5: enablement belongs to the capability
        # gate per (operation_id, tenant).  A row that could enable itself would
        # let one read activate a write.
        from dataclasses import fields

        names = {field.name for field in fields(type(next(iter(OPERATIONS.values()))))}
        self.assertNotIn("enabled", names)
        self.assertNotIn("enabled", json.dumps(list(capability_map().values())))

    def test_read_and_write_rows_are_separate_operations(self) -> None:
        read_ids = {
            "workflows.definition.read",
            "workflows.step_types.list",
            "workflows.logs.list",
        }
        write_ids = _DOCUMENTED_WRITE_KEYS
        self.assertTrue(read_ids.isdisjoint(write_ids))
        for operation_id in read_ids:
            self.assertFalse(OPERATIONS[operation_id].write, operation_id)
        for operation_id in write_ids:
            self.assertTrue(OPERATIONS[operation_id].write, operation_id)


class WorkflowReFreezeTest(unittest.TestCase):
    """IG-WF-01 -- production v3 rows, effect not inferred from the verb."""

    def test_workflow_family_is_production_v3(self) -> None:
        for operation_id in _WORKFLOW_FAMILY:
            row = OPERATIONS[operation_id]
            with self.subTest(operation_id=operation_id):
                self.assertEqual(row.version, "v3", operation_id)
                self.assertEqual(row.documented_level, "D", operation_id)
                self.assertEqual(row.route_class, "public_direct", operation_id)

    def test_no_row_carries_the_obsolete_staging_literal(self) -> None:
        offenders = [
            operation_id
            for operation_id, row in OPERATIONS.items()
            if row.version == "v4"
        ]
        self.assertEqual(offenders, [])

    def test_search_is_a_read_and_validation_is_a_non_persisting_write(self) -> None:
        search = OPERATIONS["workflows.search"]
        self.assertEqual(search.method, "POST")
        self.assertEqual(search.resolved_effect, "read")
        self.assertFalse(search.write)
        self.assertFalse(search.consumes_write_quota)

        validate = OPERATIONS["workflows.definition.validate"]
        self.assertEqual(validate.method, "POST")
        self.assertEqual(validate.resolved_effect, "non_persisting_write")
        self.assertFalse(validate.write)
        self.assertTrue(validate.consumes_write_quota)
        self.assertEqual(validate.resolved_approval_class, "none")

    def test_workflow_scopes_are_the_five_independent_permissions(self) -> None:
        self.assertEqual(
            OPERATIONS["workflows.step_types.list"].scopes_candidate,
            ("workflows.readonly",),
        )
        self.assertEqual(
            OPERATIONS["workflows.definition.validate"].scopes_candidate,
            ("workflows.write",),
        )
        self.assertEqual(
            OPERATIONS["workflows.search"].scopes_candidate,
            ("workflows.readonly",),
        )
        self.assertEqual(
            OPERATIONS["workflows.definition.read"].scopes_candidate,
            ("workflows.readonly",),
        )
        self.assertEqual(
            OPERATIONS["workflows.definition.create"].scopes_candidate,
            ("workflows.write",),
        )
        self.assertEqual(
            OPERATIONS["workflows.definition.update"].scopes_candidate,
            ("workflows.write",),
        )
        self.assertEqual(
            OPERATIONS["workflows.status.publish"].scopes_candidate,
            ("workflows.publish",),
        )
        self.assertEqual(
            OPERATIONS["workflows.definition.delete"].scopes_candidate,
            ("workflows.delete",),
        )
        for operation_id in ("workflows.logs.list", "workflows.logs.aggregate"):
            self.assertEqual(
                OPERATIONS[operation_id].scopes_candidate, ("workflows.logs",)
            )

    def test_workflow_writes_keep_their_approval_class(self) -> None:
        for operation_id in _DOCUMENTED_WRITE_KEYS:
            row = OPERATIONS[operation_id]
            with self.subTest(operation_id=operation_id):
                self.assertTrue(row.approval_required, operation_id)
                self.assertIn(
                    row.resolved_approval_class, ("approval", "destructive")
                )
        self.assertEqual(
            OPERATIONS["workflows.definition.delete"].resolved_approval_class,
            "destructive",
        )
        self.assertEqual(
            OPERATIONS["workflows.definition.read"].resolved_approval_class, "none"
        )

    def test_workflow_rows_never_claim_tenant_activation(self) -> None:
        for operation_id in _WORKFLOW_FAMILY:
            row = OPERATIONS[operation_id]
            with self.subTest(operation_id=operation_id):
                self.assertEqual(row.resolved_availability, "private_beta")
                self.assertEqual(row.blocker, "B-WORKFLOW-BETA")

    def test_documentation_provenance_is_not_fabricated(self) -> None:
        # Section 34.1: a citation to inherited evidence is not a fresh live
        # test.  A row recorded from the specification must say so, and its
        # retrieval date must be the date that evidence was captured.
        for operation_id in (
            "workflows.definition.read",
            "workflows.definition.create",
            "workflows.definition.update",
            "workflows.status.publish",
            "workflows.definition.delete",
        ):
            row = OPERATIONS[operation_id]
            with self.subTest(operation_id=operation_id):
                self.assertEqual(row.doc_evidence, "reopened_2026-11-07")
                self.assertEqual(row.doc_fetch_date, "2026-11-07")

        for operation_id in (
            "workflows.step_types.list",
            "workflows.definition.validate",
            "workflows.search",
            "locations.create",
            "courses.products.create",
            "knowledge_bases.sources.upload",
        ):
            row = OPERATIONS[operation_id]
            with self.subTest(operation_id=operation_id):
                self.assertEqual(row.doc_evidence, "revision3_spec")
                if row.doc_url is None:
                    self.assertIsNone(row.doc_fetch_date)
                else:
                    self.assertEqual(row.doc_fetch_date, "2026-11-08")

    def test_every_row_has_a_documentation_evidence_basis(self) -> None:
        for operation_id, row in OPERATIONS.items():
            with self.subTest(operation_id=operation_id):
                self.assertIn(row.doc_evidence, {"frozen", "reopened_2026-11-07",
                                                 "reopened_2026-11-08",
                                                 "revision3_spec", "none"})
                self.assertEqual(row.doc_fetch_date is None, row.doc_url is None)


class VersionAndIdentityDistinctionsTest(unittest.TestCase):
    """IG-ROUTE-07 -- versions and typed identities stay distinct."""

    def test_per_operation_versions_are_not_globally_rewritten(self) -> None:
        versions = {row.version for row in OPERATIONS.values() if row.version}
        self.assertIn("v3", versions)
        self.assertIn("2021-07-28", versions)
        self.assertGreater(len(versions), 1)
        # A known per-row literal is not replaced by the workflow family's.
        self.assertEqual(OPERATIONS["social.accounts.list"].version, "2021-07-28")
        self.assertIn("v3", OPERATIONS["social.accounts.list"].version_alternates)
        self.assertEqual(OPERATIONS["workflows.definition.read"].version, "v3")

    def test_widget_config_version_is_not_the_wire_version(self) -> None:
        schema = CONTRACTS.load_schema("hybrid-operation-receipt.v1")
        widget = schema["$defs"]["sub_results"]["properties"]["chat_widget"]
        names = set(widget["properties"])
        self.assertIn("config_version", names)
        self.assertNotIn("version", names)
        self.assertIn("chat_widget_id", names)

    def test_studio_version_and_execution_ids_are_typed(self) -> None:
        schema = CONTRACTS.load_schema("operation-contract")
        typed = set(schema["$defs"]["typed_id_name"]["enum"])
        for name in (
            "studio_agent_id",
            "studio_version_id",
            "studio_execution_id",
            "knowledge_base_id",
            "knowledge_source_id",
            "chat_widget_id",
            "meeting_room_ref",
            "host_user_id",
            "projects_space_id",
            "projects_list_id",
            "projects_task_id",
            "voice_agent_id",
            "conversation_agent_id",
        ):
            self.assertIn(name, typed)
        for legacy in (
            "company_id",
            "location_id",
            "agency_company_id",
            "commerce_product_id",
            "course_product_id",
            "course_lesson_id",
            "community_group_id",
            "community_group_slug",
            "social_account_id",
            "member_contact_id",
            "workflow_id",
            "run_id",
        ):
            self.assertIn(legacy, typed)

    def test_course_and_commerce_ids_are_never_conflated(self) -> None:
        schema = CONTRACTS.load_schema("operation-contract")
        typed = set(schema["$defs"]["typed_id_name"]["enum"])
        self.assertIn("course_product_id", typed)
        self.assertIn("commerce_product_id", typed)
        self.assertNotEqual("course_product_id", "commerce_product_id")
        for operation_id, row in OPERATIONS.items():
            if not operation_id.startswith("courses."):
                continue
            with self.subTest(operation_id=operation_id):
                self.assertTrue(
                    row.path_template.startswith("/courses")
                    or row.path_template == "UNKNOWN",
                    row.path_template,
                )


class SharedVocabularyTest(unittest.TestCase):
    """Outcomes and sub-results live in the one envelope."""

    def test_outcome_vocabulary_is_shared_and_complete(self) -> None:
        expected = {
            "planned",
            "submitted",
            "processing",
            "verified",
            "failed",
            "blocked",
            "unknown_outcome",
            "not_requested",
        }
        self.assertEqual(set(RECEIPT_OUTCOMES), expected)
        receipt = CONTRACTS.load_schema("hybrid-operation-receipt.v1")
        self.assertEqual(set(receipt["$defs"]["outcome"]["enum"]), expected)
        delivery = CONTRACTS.load_schema("course-delivery-receipt.v1")
        self.assertEqual(
            set(delivery["properties"]["outcome"]["enum"]), expected
        )

    def test_unknown_outcome_is_representable(self) -> None:
        # The outcome vocabulary belongs to the two receipt contracts; the
        # capability record models availability, not an operation outcome.
        for name in ("hybrid-operation-receipt.v1", "course-delivery-receipt.v1"):
            with self.subTest(contract=name):
                text = json.dumps(CONTRACTS.load_schema(name))
                self.assertIn("unknown_outcome", text)

    def test_meeting_ai_kb_widget_projects_share_the_receipt_envelope(self) -> None:
        schema = CONTRACTS.load_schema("hybrid-operation-receipt.v1")
        sub_results = schema["$defs"]["sub_results"]
        self.assertEqual(
            set(sub_results["properties"]),
            {
                "meeting_room",
                "voice_ai",
                "conversation_ai",
                "studio",
                "knowledge_base",
                "chat_widget",
                "projects",
            },
        )
        self.assertFalse(sub_results.get("additionalProperties", True))

    def test_legacy_conversion_is_versioned_and_additive(self) -> None:
        receipt = CONTRACTS.load_schema("hybrid-operation-receipt.v1")
        conversion = receipt["$defs"]["legacy_conversion"]
        self.assertEqual(conversion["properties"]["grants_widened"], {"const": False})
        instance = json.loads(
            (_CONTRACTS / "fixtures" / "valid" / "hybrid-operation-receipt.v1.json").read_text(
                encoding="utf-8"
            )
        )
        instance["legacy_conversion"] = {
            "from_schema_version": "0.9.0",
            "converted": True,
            "grants_widened": False,
            "notes": ["strict old launch binding wrapped, not rewritten in place"],
        }
        before = json.dumps(instance, sort_keys=True)
        CONTRACTS.validate("hybrid-operation-receipt.v1", instance)
        self.assertEqual(json.dumps(instance, sort_keys=True), before)

        instance["legacy_conversion"]["grants_widened"] = True
        with self.assertRaises(CONTRACTS.ContractError):
            CONTRACTS.validate("hybrid-operation-receipt.v1", instance)


class ChangeRequestReconciliationTest(unittest.TestCase):
    """WF00-CP03: every consumer-requested row is frozen with its exact id.

    Each assertion is the consumer's published interface, not a new registry.
    """

    def test_wf05_public_location_create_uses_the_agency_binding(self) -> None:
        row = OPERATIONS["locations.create"]
        self.assertEqual((row.method, row.path_template), ("POST", "/locations"))
        self.assertEqual(row.version, "2021-07-28")
        # WF05's typed adapter writes the agency companyId itself; the generic
        # adapter must not inject a location, so the row records binding "none"
        # and names the body.companyId rule in identity_detail (WF05 CR allows
        # exactly this representation).
        self.assertEqual(row.tenant_binding, "none")
        self.assertIn("body.companyId", row.identity_detail or "")
        self.assertEqual(row.identity_placement, "none")
        self.assertEqual(row.token_class, "agency_pit")
        self.assertEqual(row.scopes_candidate, ("locations.write",))
        self.assertEqual(row.readback_plan, "locations.get")
        self.assertTrue(row.write)
        self.assertEqual(row.resolved_availability, "tenant_restricted")

    def test_wf06_course_family_ids_and_effects_are_exact(self) -> None:
        expected = {
            "courses.products.create": ("POST", "/courses/products", True),
            "courses.products.get": ("GET", "UNKNOWN", False),
            "courses.categories.create": ("POST", "UNKNOWN", True),
            "courses.lessons.create": ("POST", "UNKNOWN", True),
            "courses.imports.submit": (
                "POST", "/courses/courses-exporter/public/import", True),
            "courses.enrollments.create": ("POST", "/courses/enrollments", True),
            "courses.product_enrollments.list": ("GET", "UNKNOWN", False),
            "courses.offers.create": ("POST", "UNKNOWN", True),
            "courses.offers.revoke": ("DELETE", "UNKNOWN", True),
            "courses.quizzes.create": (
                "POST",
                "/courses/products/{productId}/lessons/{lessonId}/quiz", True),
            "courses.quizzes.questions.upsert": (
                "PUT",
                "/courses/products/{productId}/quizzes/{quizId}/questions", True),
        }
        for operation_id, (method, path, write) in expected.items():
            row = OPERATIONS[operation_id]
            with self.subTest(operation_id=operation_id):
                self.assertEqual((row.method, row.path_template), (method, path))
                self.assertEqual(row.write, write)
                if path == "UNKNOWN":
                    self.assertEqual(row.route_class, "capability_gap")
                    self.assertIsNone(row.doc_url)
                else:
                    self.assertIn("courses.write", row.scopes_candidate)
        # A literal the evidence did not settle is never asserted.
        self.assertIsNone(OPERATIONS["courses.products.create"].version)
        self.assertEqual(
            OPERATIONS["courses.products.create"].version_state, "unverified")
        self.assertIn("version",
                      OPERATIONS["courses.products.create"].unresolved_fields)
        # The vendor spec settled the import literal; no CRUD default inherited.
        self.assertEqual(OPERATIONS["courses.imports.submit"].version, "2021-07-28")
        self.assertEqual(
            OPERATIONS["courses.imports.submit"].doc_evidence,
            "reopened_2026-11-08",
        )

    def test_wf10_community_ids_and_versions_are_exact(self) -> None:
        members = OPERATIONS["social.community.users.list"]
        self.assertEqual(
            members.path_template,
            "/social-media-posting/{locationId}/community/accounts/"
            "{accountId}/users",
        )
        self.assertEqual(members.version, "2021-07-28")
        self.assertIn("v3", members.version_alternates)
        self.assertEqual(members.scopes_candidate,
                         ("socialplanner/oauth.readonly",))
        self.assertEqual(members.doc_url,
                         "https://raw.githubusercontent.com/GoHighLevel/"
                         "highlevel-api-docs/main/apps/social-media-posting.json")
        validate_membership = OPERATIONS["social.community.group_users.validate"]
        self.assertEqual(validate_membership.scopes_candidate,
                         ("socialplanner/account.readonly",))
        self.assertEqual(
            validate_membership.path_template,
            "/social-media-posting/{locationId}/community/groups/{groupId}/"
            "users/{contactId}/validate",
        )
        comment = OPERATIONS["social.comments.community.create"]
        self.assertEqual(comment.tenant_binding, "query.locationId")
        self.assertEqual(comment.version, "v3")
        self.assertEqual(comment.scopes_candidate,
                         ("socialplanner/comments.write",))
        self.assertEqual(comment.readback_plan, "social.comments.list")

    def test_wf24_funnel_version_is_a_label_not_a_claim(self) -> None:
        for operation_id, path, required in (
            ("funnels.list", "/funnels/funnel/list",
             ("locationId", "offset", "limit")),
            ("funnels.pages.list", "/funnels/page",
             ("locationId", "funnelId", "limit", "offset")),
            ("funnels.pages.count", "/funnels/page/count",
             ("locationId", "funnelId")),
        ):
            row = OPERATIONS[operation_id]
            with self.subTest(operation_id=operation_id):
                self.assertEqual(row.path_template, path)
                self.assertEqual(row.version, "2023-02-21")
                self.assertEqual(row.version_state, "unverified")
                self.assertEqual(row.required_query, required)
                self.assertIn("version.header", row.unresolved_fields)
                self.assertIn("scopes", row.unresolved_fields)

    def test_wf25_monitoring_rows_publish_the_wire_names(self) -> None:
        canonical = OPERATIONS["workflows.logs.list"]
        alias = OPERATIONS["workflows.logs"]
        aggregate = OPERATIONS["workflows.logs.aggregate"]
        for row in (canonical, alias):
            self.assertEqual((row.method, row.path_template),
                             ("GET", "/workflows/{workflowId}/logs"))
            self.assertEqual(row.pagination, "cursor")
            self.assertEqual(row.scopes_candidate, ("workflows.logs",))
            self.assertIn("startDate", row.documented_query)
            self.assertIn("referenceId", row.documented_query)
            self.assertIn("referenceCreatedAt", row.documented_query)
            self.assertIn("limit", [name for name, _ in row.query_constraints])
        self.assertIn("groupBy", aggregate.documented_query)
        self.assertIn("timezone", aggregate.documented_query)
        limits = dict(aggregate.query_constraints)
        self.assertIn("1000", limits["limit"])
        self.assertIn("5000", limits["limit"])

    def test_wf27_wf28_wf29_native_rows_are_additive_and_default_deny(self) -> None:
        expected = {
            "voiceAi.agents.list": ("GET", "/voice-ai/agents", False),
            "voiceAi.agents.get": ("GET", "/voice-ai/agents/{agentId}", False),
            "voiceAi.agents.create": ("POST", "/voice-ai/agents", True),
            "voiceAi.agents.update": ("PATCH", "/voice-ai/agents/{agentId}", True),
            "voiceAi.actions.get": ("GET", "/voice-ai/actions/{actionId}", False),
            "voiceAi.actions.create": ("POST", "/voice-ai/actions", True),
            "voiceAi.actions.update": ("PUT", "/voice-ai/actions/{actionId}", True),
            "voiceAi.calls.list": ("GET", "/voice-ai/dashboard/call-logs", False),
            "voiceAi.calls.get": ("GET",
                                  "/voice-ai/dashboard/call-logs/{callId}", False),
            "conversation_ai.agents.list": (
                "GET", "/conversation-ai/agents/search", False),
            "conversation_ai.agents.get": (
                "GET", "/conversation-ai/agents/{agentId}", False),
            "conversation_ai.agents.create": (
                "POST", "/conversation-ai/agents", True),
            "conversation_ai.agents.update": (
                "PUT", "/conversation-ai/agents/{agentId}", True),
            "agentStudio.agents.list": ("GET", "/agent-studio/agent", False),
            "agentStudio.agents.create": ("POST", "/agent-studio/agent", True),
            "agentStudio.agents.read": (
                "GET", "/agent-studio/agent/{agentId}", False),
            "agentStudio.agents.metadata.update": (
                "PATCH", "/agent-studio/agent/{agentId}", True),
            "agentStudio.versions.update": (
                "PATCH", "/agent-studio/agent/versions/{versionId}", True),
            "agentStudio.versions.promote": (
                "POST", "/agent-studio/agent/versions/{versionId}/publish", True),
            "agentStudio.agents.execute": (
                "POST", "/agent-studio/agent/{agentId}/execute", True),
        }
        for operation_id, (method, path, write) in expected.items():
            row = OPERATIONS[operation_id]
            with self.subTest(operation_id=operation_id):
                self.assertEqual((row.method, row.path_template), (method, path))
                self.assertEqual(row.write, write)
                self.assertEqual(row.version, "2021-04-15")
                self.assertFalse(hasattr(row, "enabled"))

    def test_wf30_knowledge_base_family_and_multipart_gap(self) -> None:
        expected = {
            "knowledge_bases.list": ("GET", "/knowledge-bases/", False),
            "knowledge_bases.get": (
                "GET", "/knowledge-bases/{knowledgeBaseId}", False),
            "knowledge_bases.create": ("POST", "/knowledge-bases/", True),
            "knowledge_bases.update": ("PUT", "/knowledge-bases/{id}", True),
            "knowledge_bases.delete": (
                "DELETE", "/knowledge-bases/{knowledgeBaseId}", True),
            "knowledge_bases.crawler.discover": (
                "POST", "/knowledge-bases/crawler", True),
            "knowledge_bases.crawler.status": (
                "GET", "/knowledge-bases/crawler/status", False),
            "knowledge_bases.crawler.train": (
                "POST", "/knowledge-bases/crawler/train", True),
            "knowledge_bases.crawler.urls": (
                "GET", "/knowledge-bases/crawler", False),
            "knowledge_bases.crawler.delete_urls": (
                "DELETE", "/knowledge-bases/crawler", True),
            "knowledge_bases.faqs.list": ("GET", "/knowledge-bases/faqs", False),
            "knowledge_bases.faqs.create": ("POST", "/knowledge-bases/faqs", True),
            "knowledge_bases.faqs.update": (
                "PUT", "/knowledge-bases/faqs/{id}", True),
            "knowledge_bases.faqs.delete": (
                "DELETE", "/knowledge-bases/faqs/{id}", True),
        }
        for operation_id, (method, path, write) in expected.items():
            row = OPERATIONS[operation_id]
            with self.subTest(operation_id=operation_id):
                self.assertEqual((row.method, row.path_template), (method, path))
                self.assertEqual(row.write, write)
                self.assertEqual(row.version, "2021-04-15")
        gap = OPERATIONS["knowledge_bases.sources.upload"]
        self.assertEqual(gap.route_class, "capability_gap")
        self.assertEqual(gap.request_media_type, "multipart/form-data")
        self.assertEqual(gap.blocker, "B-NO-CONTRACT")
        self.assertIsNone(gap.doc_url)
        self.assertEqual(gap.path_template, "UNKNOWN")

    def test_wf30_conversation_agent_attachment_rows_exist(self) -> None:
        for operation_id in ("conversation_ai.agents.get",
                             "conversation_ai.agents.update"):
            self.assertIn(operation_id, OPERATIONS)
        self.assertEqual(OPERATIONS["conversation_ai.agents.update"].method, "PUT")
        self.assertEqual(
            OPERATIONS["conversation_ai.agents.update"].readback_plan,
            "conversation_ai.agents.get",
        )

    def test_wf31_widget_rows_preserve_the_numeric_config_version(self) -> None:
        expected = {
            "chat_widgets.list": ("GET", "/chat-widget/list", False),
            "chat_widgets.get": (
                "GET", "/chat-widget/data/{locationId}/{id}", False),
            "chat_widgets.create": ("POST", "/chat-widget/", True),
            "chat_widgets.update": (
                "PUT", "/chat-widget/data/{locationId}/{id}", True),
            "chat_widgets.patch": (
                "PATCH", "/chat-widget/data/{locationId}/{id}", True),
            "chat_widgets.delete": (
                "DELETE", "/chat-widget/{locationId}/{id}", True),
            "chat_widgets.clone": ("POST", "/chat-widget/clone", True),
            "chat_widgets.public_config": (
                "GET", "/chat-widget/public/config/{id}", False),
        }
        for operation_id, (method, path, write) in expected.items():
            row = OPERATIONS[operation_id]
            with self.subTest(operation_id=operation_id):
                self.assertEqual((row.method, row.path_template), (method, path))
                self.assertEqual(row.write, write)
                self.assertEqual(row.version, "v3")
        row = OPERATIONS["chat_widgets.public_config"]
        self.assertEqual(row.version, "v3")
        self.assertNotEqual(row.version, "2")
        self.assertIn("version", row.documented_query)
        self.assertEqual(row.identity_placement, "path")

    def test_no_two_rows_share_a_route_except_the_declared_logs_alias(self) -> None:
        seen: dict[tuple[str, str], str] = {}
        for operation_id, row in OPERATIONS.items():
            if row.method in ("MCP", "UNKNOWN") or row.path_template == "UNKNOWN":
                continue
            key = (row.method, row.path_template)
            if key in seen:
                pair = frozenset({seen[key], operation_id})
                allowed = {
                    frozenset({"workflows.logs.list", "workflows.logs"}),
                    frozenset({
                        "conversations.messages.send",
                        "conversations.messages.send_in_conversation",
                    }),
                    frozenset({
                        "workflows.private.save",
                        "workflows.private.publish",
                    }),
                }
                self.assertIn(
                    pair, allowed,
                    f"undeclared duplicate route {key}: {sorted(pair)}",
                )
            else:
                seen[key] = operation_id


class FixturePackTest(unittest.TestCase):
    """The frozen fixtures are loadable and each invalid case is rejected."""

    def test_valid_fixtures_validate(self) -> None:
        fixtures = _fixtures("valid")
        self.assertTrue(fixtures, "the valid fixture pack must not be empty")
        covered: set[str] = set()
        for path in fixtures:
            contract = _contract_name_for(path)
            covered.add(contract)
            with self.subTest(fixture=path.name):
                CONTRACTS.validate_file(contract, path)
        self.assertEqual(covered, set(CONTRACTS.SCHEMA_FILES))

    def test_invalid_fixtures_are_rejected(self) -> None:
        fixtures = _fixtures("invalid")
        self.assertTrue(fixtures, "the invalid fixture pack must not be empty")
        for path in fixtures:
            contract = _contract_name_for(path)
            with self.subTest(fixture=path.name):
                with self.assertRaises(CONTRACTS.ContractError):
                    CONTRACTS.validate_file(contract, path)

    def test_every_schema_declares_its_semantic_constraints(self) -> None:
        for name in CONTRACTS.SCHEMA_FILES:
            with self.subTest(contract=name):
                schema = CONTRACTS.load_schema(name)
                self.assertIn("x-semantic-constraints", schema)
                self.assertTrue(schema["x-semantic-constraints"])


class CourseContractTest(unittest.TestCase):
    """Plan, asset, association and delivery shapes stay separate."""

    def test_duplicate_titles_with_distinct_keys_are_allowed(self) -> None:
        plan = json.loads(
            (_CONTRACTS / "fixtures" / "valid" / "course-build-plan.v1.json").read_text(
                encoding="utf-8"
            )
        )
        titles = [lesson["title"] for lesson in plan["modules"][0]["lessons"]]
        self.assertEqual(titles[0], titles[1])
        CONTRACTS.validate("course-build-plan.v1", plan)

    def test_draft_only_plan_cannot_publish_a_module(self) -> None:
        plan = json.loads(
            (_CONTRACTS / "fixtures" / "valid" / "course-build-plan.v1.json").read_text(
                encoding="utf-8"
            )
        )
        plan["modules"][0]["visibility"] = "published"
        with self.assertRaises(CONTRACTS.ContractError):
            CONTRACTS.validate("course-build-plan.v1", plan)

    def test_learning_association_detach_is_not_a_course_delete(self) -> None:
        plan = json.loads(
            (
                _CONTRACTS / "fixtures" / "valid" / "learning-association.v1.json"
            ).read_text(encoding="utf-8")
        )
        plan["operation"] = "detach"
        CONTRACTS.validate("learning-association.v1", plan)
        self.assertEqual(plan["operation"], "detach")
        text = json.dumps(CONTRACTS.load_schema("learning-association.v1"))
        self.assertIn("never calls course delete", text)

    def test_media_proof_fields_are_separate(self) -> None:
        manifest = json.loads(
            (
                _CONTRACTS / "fixtures" / "valid" / "course-asset-manifest.v1.json"
            ).read_text(encoding="utf-8")
        )
        proof = manifest["proof"]
        self.assertEqual(
            set(proof),
            {
                "asset_persisted",
                "native_content_ready",
                "lesson_association_verified",
                "learner_render_verified",
            },
        )
        manifest["proof"]["learner_render_verified"] = True
        with self.assertRaises(CONTRACTS.ContractError):
            CONTRACTS.validate("course-asset-manifest.v1", manifest)


class CapabilityRecordV2Test(unittest.TestCase):
    """Separate facts, and a v1 translation that never widens a grant."""

    def test_valid_record_separates_every_dimension(self) -> None:
        path = _CONTRACTS / "fixtures" / "valid" / "capability-record.v2.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        CONTRACTS.validate("capability-record.v2", record)
        capability = record["capabilities"]["workflows.step_types.list"]
        for field in (
            "documented",
            "adapter_built",
            "offline_tests_passed",
            "availability",
            "scope_state",
            "read_probe",
            "write_canary",
            "enabled",
        ):
            self.assertIn(field, capability)
        self.assertFalse(capability["enabled"])

    def test_v1_translation_is_recorded_and_grants_are_not_widened(self) -> None:
        record = json.loads(
            (_CONTRACTS / "fixtures" / "valid" / "capability-record.v2.json").read_text(
                encoding="utf-8"
            )
        )
        record["legacy_conversion"] = {
            "from_record_version": 1,
            "source_path": "state/ghl-public-capabilities.v1.json",
            "source_sha256": "a" * 64,
            "converted_at": "2026-11-08T12:00:00Z",
            "grants_widened": False,
            "notes": ["read_verified mapped to read_probe.state=passed"],
        }
        CONTRACTS.validate("capability-record.v2", record)
        record["legacy_conversion"]["grants_widened"] = True
        with self.assertRaises(CONTRACTS.ContractError):
            CONTRACTS.validate("capability-record.v2", record)

    def test_enabled_requires_the_offline_evidence_facts(self) -> None:
        record = json.loads(
            (_CONTRACTS / "fixtures" / "valid" / "capability-record.v2.json").read_text(
                encoding="utf-8"
            )
        )
        capability = record["capabilities"]["workflows.step_types.list"]
        capability["enabled"] = True
        capability["availability"] = "unknown"
        with self.assertRaises(CONTRACTS.ContractError):
            CONTRACTS.validate("capability-record.v2", record)


if __name__ == "__main__":
    unittest.main(verbosity=2)
