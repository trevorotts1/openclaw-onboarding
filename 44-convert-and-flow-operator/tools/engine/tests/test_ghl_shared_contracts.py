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
            "agency.locations.create",
            "courses.products.create",
            "knowledge_bases.files.upload",
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
