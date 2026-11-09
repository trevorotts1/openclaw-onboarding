"""Production-contract (v3) workflow adapter, exercised on an explicit fixture.

The registry rows for the newer workflow surfaces belong to WF00 and are not on
main yet.  This module does NOT invent them in production code: it declares the
Document 1 section 6.2 contract as an explicit fixture registry and injects it
into ``PublicGhlAdapter(operations=...)``.  The production path stays fail-loud
(``WorkflowRowMissing`` names WF00 / WF00-CP01), which is asserted here too.

Every test is offline on ``FakeTransport``; synthetic identifiers only.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    FakeTransport,
    Row,
    fake_tenant,
    make_adapter,
    registry,
    resp,
)

from cli_anything.gohighlevel.public.adapter import ApprovalRef  # noqa: E402
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.result import Status  # noqa: E402
from cli_anything.gohighlevel.public.workflow_v4 import (  # noqa: E402
    UPDATE_OPERATION,
    WorkflowRowMissing,
    WorkflowV4Adapter,
    validate_operation_map,
)

TENANT = fake_tenant()
WORKFLOW_ID = "wf_synthetic_0001"
NEW_ID = "wf_synthetic_0002"
APPROVAL = ApprovalRef(ref="approval-synthetic-v4")
DELETION_APPROVAL = ApprovalRef(ref="approval-synthetic-v4; scope:deletion")
PUBLISH_APPROVAL = ApprovalRef(ref="approval-synthetic-v4; scope:publication")


def _rows(*, version: str = "v3") -> dict:
    """Document 1 section 6.2 rows, declared explicitly as a fixture."""

    return registry(
        Row("workflows.definition.read", method="GET",
            path_template="/workflows/{workflowId}/definition", version=version,
            tenant_binding="query.locationId"),
        Row("workflows.list", method="GET", path_template="/workflows/",
            version=version, tenant_binding="query.locationId"),
        Row("workflows.definition.create", method="POST", path_template="/workflows/",
            version=version, tenant_binding="query.locationId", write=True,
            approval_required=True),
        Row("workflows.definition.update", method="PUT",
            path_template="/workflows/{workflowId}/definition", version=version,
            tenant_binding="query.locationId", write=True, approval_required=True),
        Row("workflows.status.publish", method="PUT",
            path_template="/workflows/{workflowId}/status", version=version,
            tenant_binding="query.locationId", write=True, approval_required=True),
        Row("workflows.definition.delete", method="DELETE",
            path_template="/workflows/{workflowId}", version=version,
            tenant_binding="query.locationId", write=True, approval_required=True),
        Row("workflows.step_types.list", method="GET",
            path_template="/workflows/step-types", version=version,
            tenant_binding="query.locationId"),
        Row("workflows.definition.validate", method="POST",
            path_template="/workflows/definition/validate", version=version,
            tenant_binding="query.locationId"),
        Row("workflows.search", method="POST", path_template="/workflows/search",
            version=version, tenant_binding="query.locationId"),
        Row("workflows.logs.list", method="GET",
            path_template="/workflows/{workflowId}/logs", version=version,
            tenant_binding="query.locationId"),
        Row("workflows.logs.aggregate", method="GET",
            path_template="/workflows/{workflowId}/logs/aggregate", version=version,
            tenant_binding="query.locationId"),
    )


def _gate(rows: dict, *operation_ids: str):
    from _public_contract_fakes import enabled_gate

    return enabled_gate([rows[item] for item in operation_ids], tenant=TENANT.location_id)


def _adapter(transport: FakeTransport, rows: dict, gate, operations=None):
    public = make_adapter(transport, operations if operations is not None else rows,
                          gate=gate)
    return WorkflowV4Adapter(public=public)


def _graph(version=3, name="Synthetic V3 Flow") -> dict:
    return {
        "version": version,
        "name": name,
        "source": "synthetic",
        "triggers": [{"id": "trg_1", "type": "contact_created"}],
        "actions": [
            {"id": "act_sms", "type": "sms", "name": "A",
             "message": "SYNTHETIC_MESSAGE_PLACEHOLDER"},
            {"id": "act_unknown", "type": "synthetic_unknown_supported",
             "config": {"k": "SYNTHETIC_VALUE"}},
        ],
        "edges": [{"id": "e_1", "from": "trg_1", "to": "act_sms"}],
        "settings": {"syntheticUnknownSetting": True},
    }


def _payload(definition, status="draft", workflow_id=WORKFLOW_ID) -> dict:
    return {"status": status, "workflowId": workflow_id, "definition": definition}


def _json(payload, status=200):
    return resp(status, json.dumps(payload).encode("utf-8"))


class VersionNeutralRegistry(unittest.TestCase):
    def test_every_request_carries_the_row_version(self) -> None:
        rows = _rows(version="v3")
        prior = _graph()
        after = copy.deepcopy(prior)
        after["version"] = 4
        transport = FakeTransport([
            _json(_payload(prior)),
            resp(200, b"{}"),
            _json(_payload(after)),
            _json(_payload(after)),
        ])
        adapter = _adapter(transport, rows, _gate(rows, "workflows.definition.read",
                                                  "workflows.definition.update"))
        result = adapter.update_definition(
            tenant=TENANT, workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"name": prior["name"]}},
            approval=APPROVAL, expected_revision=3,
        )
        self.assertIs(result.status, Status.ok, result.error)
        self.assertEqual({item["version"] for item in transport.requests}, {"v3"})

    def test_missing_row_fails_loud_and_names_the_owner(self) -> None:
        rows = _rows()
        transport = FakeTransport()
        from cli_anything.gohighlevel.public.operations import OPERATIONS

        adapter = _adapter(transport, rows, None, operations=OPERATIONS)
        with self.assertRaises(WorkflowRowMissing) as caught:
            adapter.discovered_step_types(tenant=TENANT)
        self.assertEqual(caught.exception.rule, "workflow_operation_row_missing")
        self.assertEqual(caught.exception.detail["owner"], "WF00")
        self.assertEqual(caught.exception.detail["checkpoint"], "WF00-CP01")
        self.assertEqual(transport.call_count, 0)

    def test_missing_rows_are_reported_not_silently_dropped(self) -> None:
        from cli_anything.gohighlevel.public.operations import OPERATIONS

        missing = validate_operation_map(OPERATIONS)
        self.assertIn("workflows.definition.validate", missing)
        self.assertIn("workflows.step_types.list", missing)
        self.assertIn("workflows.search", missing)


class PublicWithoutFirebase(unittest.TestCase):
    """A01 (adapter side): the public module has no private rail in it."""

    def test_the_adapter_module_carries_no_private_transport(self) -> None:
        source = (
            Path(__file__).resolve().parent.parent
            / "cli_anything" / "gohighlevel" / "public" / "workflow_v4.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "ghl_internal_client",
            "firebase",
            "chrome_extension",
            "from .internal",
            "import requests",
        ):
            self.assertNotIn(forbidden, source, forbidden)


class StepTypeDiscovery(unittest.TestCase):
    """IG-WF-03: page through every step type and collect asset references."""

    def test_all_pages_are_read_and_the_continuation_is_carried_verbatim(self) -> None:
        rows = _rows()
        transport = FakeTransport([
            _json({"stepTypes": [
                {"type": "sms", "assetReferences": [{"field": "mediaId"}]}
            ], "nextCursor": "opaque-token-1"}),
            _json({"stepTypes": [{"type": "email"}, {"type": "wait"}],
                   "nextCursor": None}),
        ])
        adapter = _adapter(transport, rows,
                           _gate(rows, "workflows.step_types.list"))
        result, evidence = adapter.discovered_step_types(tenant=TENANT)

        self.assertIs(result.status, Status.ok, result.error)
        self.assertEqual(evidence["count"], 3)
        self.assertTrue(evidence["complete"])
        self.assertEqual(evidence["pages"], 2)
        self.assertEqual(evidence["asset_reference_count"], 1)
        second_query = transport.requests[1]["query"] or {}
        self.assertEqual(second_query.get("nextCursor"), "opaque-token-1")
        self.assertIn("wait", evidence["step_types"])

    def test_an_uncarryable_continuation_never_claims_completeness(self) -> None:
        rows = _rows()
        transport = FakeTransport([
            _json({"stepTypes": [{"type": "sms"}],
                   "meta": {"nextCursor": "nested-token"}}),
        ])
        adapter = _adapter(transport, rows,
                           _gate(rows, "workflows.step_types.list"))
        _result, evidence = adapter.discovered_step_types(tenant=TENANT)
        self.assertFalse(evidence["complete"])
        self.assertEqual(evidence["unresolved"]["reason"],
                         "continuation_shape_unresolved")


class Validator(unittest.TestCase):
    """A04 / IG-WF-04: a 200 with valid:false is a failure."""

    def _adapter(self, responses):
        rows = _rows()
        transport = FakeTransport(responses)
        return _adapter(transport, rows,
                        _gate(rows, "workflows.definition.validate")), transport

    def test_http_200_with_valid_false_fails(self) -> None:
        adapter, transport = self._adapter([
            _json({"valid": False, "errors": [{"code": "action_invalid"}]})
        ])
        result = adapter.validate_definition(tenant=TENANT, definition=_graph())
        self.assertIs(result.status, Status.validation_error)
        self.assertEqual(result.error["rule"], "validation_failed")
        self.assertEqual(transport.call_count, 1)

    def test_unknown_action_noop_warning_fails(self) -> None:
        adapter, _transport = self._adapter([
            _json({"valid": True, "warnings": [
                {"code": "unknown_action_converted_to_note"}
            ]})
        ])
        result = adapter.validate_definition(tenant=TENANT, definition=_graph())
        self.assertIs(result.status, Status.validation_error)
        self.assertEqual(result.error["rule"], "unknown_action_noop_warning")

    def test_missing_valid_field_is_not_success(self) -> None:
        adapter, _transport = self._adapter([_json({"warnings": []})])
        result = adapter.validate_definition(tenant=TENANT, definition=_graph())
        self.assertIs(result.status, Status.unavailable)
        self.assertEqual(result.error["rule"], "validation_result_missing")

    def test_builder_only_field_omission_is_refused(self) -> None:
        step_types = {
            "sms": {
                "type": "sms",
                "requiredEnforcement": "builder-only",
                "fields": [{"name": "message", "required": True}],
            }
        }
        definition = copy.deepcopy(_graph())
        del definition["actions"][0]["message"]
        adapter, _transport = self._adapter([_json({"valid": True})])
        result = adapter.validate_definition(
            tenant=TENANT, definition=definition, step_types=step_types
        )
        self.assertIs(result.status, Status.validation_error)
        self.assertEqual(result.error["rule"], "builder_only_field_missing")


class CompleteReplacement(unittest.TestCase):
    """A05 / IG-WF-05: unknown nodes, edges and settings survive the PUT."""

    def test_complete_graph_is_written_and_read_back_unchanged(self) -> None:
        rows = _rows()
        prior = _graph()
        after = copy.deepcopy(prior)
        after["version"] = 4
        after["name"] = "Renamed"
        transport = FakeTransport([
            _json(_payload(prior)),
            resp(200, b"{}"),
            _json(_payload(after)),
            _json(_payload(after)),
        ])
        adapter = _adapter(transport, rows, _gate(rows, "workflows.definition.read",
                                                  "workflows.definition.update"))
        result = adapter.update_definition(
            tenant=TENANT, workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"name": "Renamed"}},
            approval=APPROVAL, expected_revision=3,
        )
        self.assertIs(result.status, Status.ok, result.error)
        body = transport.requests[1]["body"]
        self.assertEqual(body["actions"], prior["actions"])
        self.assertEqual(body["edges"], prior["edges"])
        self.assertEqual(body["triggers"], prior["triggers"])
        self.assertEqual(body["settings"], prior["settings"])
        self.assertEqual(body["version"], 3)

    def test_fractional_opaque_revision_is_never_coerced(self) -> None:
        rows = _rows()
        prior = _graph(version=3.25)
        after = copy.deepcopy(prior)
        after["version"] = 3.5
        transport = FakeTransport([
            _json(_payload(prior)),
            resp(200, b"{}"),
            _json(_payload(after)),
            _json(_payload(after)),
        ])
        adapter = _adapter(transport, rows, _gate(rows, "workflows.definition.read",
                                                  "workflows.definition.update"))
        result = adapter.update_definition(
            tenant=TENANT, workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"name": prior["name"]}},
            approval=APPROVAL, expected_revision=3.25,
        )
        self.assertIs(result.status, Status.ok, result.error)
        written = transport.requests[1]["body"]["version"]
        self.assertEqual(written, 3.25)
        self.assertIsInstance(written, float)

    def test_unapproved_deletion_is_refused_before_transport(self) -> None:
        rows = _rows()
        prior = _graph()
        transport = FakeTransport([_json(_payload(prior))])
        adapter = _adapter(transport, rows, _gate(rows, "workflows.definition.read",
                                                  "workflows.definition.update"))
        result = adapter.update_definition(
            tenant=TENANT, workflow_id=WORKFLOW_ID,
            intent={"remove_actions": ["act_unknown"]},
            approval=APPROVAL, expected_revision=3,
        )
        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "deletion_requires_approval")
        self.assertEqual([item["method"] for item in transport.requests], ["GET"])

    def test_provider_step_ids_are_captured_after_create(self) -> None:
        rows = _rows()
        authored = {
            "name": "Synthetic Created",
            "actions": [{"id": "act_authored", "type": "sms"}],
            "triggers": [], "edges": [],
        }
        returned = {
            "version": 1,
            "name": "Synthetic Created",
            "actions": [{"id": "act_provider", "type": "sms"}],
            "triggers": [], "edges": [],
        }
        transport = FakeTransport([
            resp(201, json.dumps({"workflowId": NEW_ID, "status": "draft"}).encode()),
            _json({"data": [{"name": "Synthetic Created", "id": NEW_ID}]}),
            _json({"workflows": [{"name": "Synthetic Created", "id": NEW_ID}]}),
            _json(_payload(returned, workflow_id=NEW_ID)),
        ])
        adapter = _adapter(transport, rows, _gate(
            rows, "workflows.definition.create", "workflows.list",
            "workflows.definition.read"))
        result = adapter.create_workflow(
            tenant=TENANT, definition=authored, approval=APPROVAL
        )
        self.assertIs(result.status, Status.ok, result.error)
        evidence = result.evidence["workflow_v4"]
        self.assertEqual(evidence["workflow_id"], NEW_ID)
        self.assertEqual(evidence["provider_step_id_map"],
                         {"act_authored": "act_provider"})
        self.assertEqual(evidence["provider_step_id_map_status"], "mapped")
        self.assertNotIn("version", transport.requests[0]["body"])


class RevisionAndPublication(unittest.TestCase):
    """A06 / IG-WF-06..08."""

    def test_published_workflow_is_not_silently_drafted(self) -> None:
        rows = _rows()
        prior = _graph()
        transport = FakeTransport([_json(_payload(prior, "published"))])
        adapter = _adapter(transport, rows, _gate(
            rows, "workflows.definition.read", "workflows.definition.update",
            "workflows.status.publish"))
        result = adapter.update_definition(
            tenant=TENANT, workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"name": "x"}},
            approval=APPROVAL, expected_revision=3,
        )
        self.assertIs(result.status, Status.conflict)
        self.assertEqual(result.error["rule"], "workflow_published")
        self.assertFalse(any("/status" in item["url"] for item in transport.requests))

    def test_remote_stale_revision_rereads_and_reapplies_once(self) -> None:
        rows = _rows()
        prior = _graph(version=3)
        fresh = copy.deepcopy(prior)
        fresh["version"] = 4
        fresh["name"] = "Renamed"
        after = copy.deepcopy(fresh)
        after["version"] = 5
        transport = FakeTransport([
            _json(_payload(prior)),                                  # first read
            resp(422, b'{"code":"stale_revision","message":"revision moved"}'),
            _json(_payload(fresh)),                                  # realign read
            resp(200, b"{}"),                                        # second PUT
            _json(_payload(after)),                                  # read-back
            _json(_payload(after)),                                  # verification
        ])
        adapter = _adapter(transport, rows, _gate(
            rows, "workflows.definition.read", "workflows.definition.update"))
        result = adapter.update_definition(
            tenant=TENANT, workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"name": "Renamed"}},
            approval=APPROVAL, expected_revision=3,
        )
        self.assertIs(result.status, Status.ok, result.error)
        self.assertEqual(
            [item["method"] for item in transport.requests],
            ["GET", "PUT", "GET", "PUT", "GET", "GET"],
        )
        self.assertEqual(transport.requests[3]["body"]["version"], 4)
        self.assertTrue(result.evidence["workflow_v4"]["revision_realigned"])
        self.assertEqual(result.evidence["workflow_v4"]["realign_reads"], 1)

    def test_generic_422_is_not_blindly_retried(self) -> None:
        rows = _rows()
        prior = _graph(version=3)
        transport = FakeTransport([
            _json(_payload(prior)),
            resp(422, b'{"code":"validation_error","message":"bad field"}'),
        ])
        adapter = _adapter(transport, rows, _gate(
            rows, "workflows.definition.read", "workflows.definition.update"))
        result = adapter.update_definition(
            tenant=TENANT, workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"name": "Renamed"}},
            approval=APPROVAL, expected_revision=3,
        )
        self.assertIs(result.status, Status.validation_error)
        self.assertEqual([item["method"] for item in transport.requests], ["GET", "PUT"])

    def test_authorized_draft_transition_is_followed_by_a_fresh_read(self) -> None:
        rows = _rows()
        published = _graph(version=12)
        fresh = copy.deepcopy(published)
        fresh["version"] = 13
        after = copy.deepcopy(fresh)
        after["version"] = 14
        transport = FakeTransport([
            _json(_payload(published, "published")),
            resp(200, b"{}"),                       # status -> draft
            _json(_payload(published, "draft")),    # status read-back
            _json(_payload(published, "draft")),    # post-transition fresh read
            _json(_payload(fresh, "draft")),        # update's own read
            resp(200, b"{}"),                       # definition PUT
            _json(_payload(fresh, "draft")),        # in-write read-back
            _json(_payload(after, "draft")),        # verification
        ])
        adapter = _adapter(transport, rows, _gate(
            rows, "workflows.definition.read", "workflows.definition.update",
            "workflows.status.publish"))
        result = adapter.update_definition(
            tenant=TENANT, workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"name": fresh["name"]}},
            approval=APPROVAL, expected_revision=12,
            allow_draft_transition=True, draft_transition_approval=APPROVAL,
        )
        self.assertIs(result.status, Status.ok, result.error)
        self.assertEqual(transport.requests[1]["body"], {"status": "draft"})
        self.assertEqual(transport.requests[5]["body"]["version"], 13)
        self.assertTrue(result.evidence["workflow_v4"]["draft_transition_performed"])

    def test_publish_needs_a_publication_scoped_approval(self) -> None:
        rows = _rows()
        transport = FakeTransport()
        adapter = _adapter(transport, rows,
                           _gate(rows, "workflows.status.publish"))
        denied = adapter.publish_workflow(
            tenant=TENANT, workflow_id=WORKFLOW_ID, approval=APPROVAL
        )
        self.assertIs(denied.status, Status.denied)
        self.assertEqual(denied.error["rule"],
                         "publish_approval_not_publication_scoped")
        self.assertEqual(transport.call_count, 0)


class DestructiveOperations(unittest.TestCase):
    def test_delete_requires_a_deletion_scoped_approval(self) -> None:
        rows = _rows()
        transport = FakeTransport()
        adapter = _adapter(transport, rows,
                           _gate(rows, "workflows.definition.delete"))
        result = adapter.delete_workflow(
            tenant=TENANT, workflow_id=WORKFLOW_ID, approval=APPROVAL
        )
        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"],
                         "delete_requires_destructive_approval")
        self.assertEqual(result.error["bound_workflow_id"], WORKFLOW_ID)
        self.assertEqual(transport.call_count, 0)

    def test_restore_uses_the_update_contract_with_the_current_revision(self) -> None:
        """IG-WF-12: no restore endpoint; snapshot recovery is an update."""

        rows = _rows()
        live = _graph(version=21)
        after = copy.deepcopy(live)
        after["version"] = 22
        snapshot = {"status": "draft", "definition": _graph(version=7)}
        transport = FakeTransport([
            _json(_payload(live)),          # restore's fresh read
            _json(_payload(live)),          # update's own read
            resp(200, b"{}"),               # PUT
            _json(_payload(after)),         # in-write read-back
            _json(_payload(after)),         # verification
        ])
        adapter = _adapter(transport, rows, _gate(
            rows, "workflows.definition.read", "workflows.definition.update"))
        result = adapter.restore_workflow(
            tenant=TENANT, workflow_id=WORKFLOW_ID, snapshot=snapshot,
            approval=APPROVAL,
        )
        self.assertIs(result.status, Status.ok, result.error)
        self.assertEqual(transport.requests[2]["body"]["version"], 21)
        self.assertFalse(any("restore" in item["url"]
                             for item in transport.requests))
        restore = result.evidence["workflow_v4"]["restore"]
        self.assertEqual(restore["mode"], "approved_update_from_snapshot")
        self.assertFalse(restore["replayed_snapshot_revision"])


class FolderHandling(unittest.TestCase):
    def test_folder_name_and_path_are_mutually_exclusive(self) -> None:
        rows = _rows()
        transport = FakeTransport()
        adapter = _adapter(transport, rows,
                           _gate(rows, "workflows.definition.create"))
        with self.assertRaises(ContractViolation) as caught:
            adapter.create_workflow(
                tenant=TENANT, definition={"name": "Synthetic"},
                approval=APPROVAL,
                folder={"folderName": "A", "folderPath": "A/B"},
            )
        self.assertEqual(caught.exception.rule,
                         "folder_name_and_path_exclusive")
        self.assertEqual(transport.call_count, 0)

    def test_folder_depth_limit_is_enforced_when_supplied(self) -> None:
        rows = _rows()
        transport = FakeTransport()
        adapter = _adapter(transport, rows,
                           _gate(rows, "workflows.definition.create"))
        with self.assertRaises(ContractViolation) as caught:
            adapter.create_workflow(
                tenant=TENANT, definition={"name": "Synthetic"},
                approval=APPROVAL, folder={"folderPath": "A/B/C/D"},
                folder_path_max_depth=3,
            )
        self.assertEqual(caught.exception.rule, "folder_path_depth_exceeded")
        self.assertEqual(transport.call_count, 0)

    def test_create_folder_if_missing_must_be_boolean(self) -> None:
        rows = _rows()
        transport = FakeTransport()
        adapter = _adapter(transport, rows,
                           _gate(rows, "workflows.definition.create"))
        with self.assertRaises(ContractViolation) as caught:
            adapter.create_workflow(
                tenant=TENANT, definition={"name": "Synthetic"},
                approval=APPROVAL,
                folder={"folderPath": "A", "createFolderIfMissing": "yes"},
            )
        self.assertEqual(caught.exception.rule,
                         "create_folder_if_missing_invalid")
        self.assertEqual(transport.call_count, 0)


class SearchIsARead(unittest.TestCase):
    def test_search_carries_no_write_classification(self) -> None:
        rows = _rows()
        transport = FakeTransport([_json({"workflows": []})])
        adapter = _adapter(transport, rows, _gate(rows, "workflows.search"))
        result = adapter.search_workflows(
            tenant=TENANT, body={"query": "Synthetic"}
        )
        self.assertIs(result.status, Status.ok, result.error)
        evidence = result.evidence["workflow_v4"]
        self.assertTrue(evidence["read_operation"])
        self.assertTrue(evidence["consumes_write_quota"])
        self.assertIsNone(transport.requests[0]["headers"].get("Idempotency-Key"))


class MonitoringDelegation(unittest.TestCase):
    def test_logs_facade_never_implements_a_second_reader(self) -> None:
        spec = importlib.util.find_spec(
            "cli_anything.gohighlevel.public.workflow_monitoring"
        )
        if spec is not None:
            self.skipTest("WF25 workflow_monitoring has landed; delegated path")
        rows = _rows()
        transport = FakeTransport()
        adapter = _adapter(transport, rows, _gate(
            rows, "workflows.logs.list", "workflows.logs.aggregate"))
        listed = adapter.list_logs(
            tenant=TENANT, workflow_id=WORKFLOW_ID,
            query={"startTime": "2026-11-01", "endTime": "2026-11-02"},
        )
        aggregated = adapter.aggregate_logs(
            tenant=TENANT, workflow_id=WORKFLOW_ID
        )
        for result in (listed, aggregated):
            self.assertIs(result.status, Status.unavailable)
            self.assertEqual(result.error["rule"],
                             "workflow_monitoring_module_missing")
            self.assertEqual(result.error["owner"], "WF25")
        self.assertEqual(transport.call_count, 0)


class ValidationSurfaceAndGaps(unittest.TestCase):
    def test_validation_read_remains_a_named_gap(self) -> None:
        rows = _rows()
        transport = FakeTransport()
        adapter = _adapter(transport, rows, None)
        with self.assertRaises(ContractViolation) as caught:
            adapter.read_validation(tenant=TENANT, workflow_id=WORKFLOW_ID)
        self.assertEqual(
            caught.exception.rule,
            "workflow_validation_read_has_no_documented_operation",
        )
        self.assertEqual(transport.call_count, 0)

    def test_capability_for_a_missing_row_is_deny_not_a_crash(self) -> None:
        rows = _rows()
        transport = FakeTransport()
        from cli_anything.gohighlevel.public.operations import OPERATIONS

        adapter = _adapter(transport, rows, None, operations=OPERATIONS)
        capability = adapter.capability("step_types.list", tenant=TENANT)
        self.assertFalse(capability.enabled)
        self.assertIsNotNone(capability.activation_blocked)
        self.assertEqual(capability.activation_blocked.owner, "WF00")


if __name__ == "__main__":
    unittest.main()
