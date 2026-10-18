"""V4 full-graph preservation -- GU-004 2.4 and 5.7 (GU-003 WF-04 .. WF-08).

Frozen expectations (section 6.2):

* untouched actions, edges and triggers survive the complete-replacement write
  verbatim, including a node type the documented set does not know but the
  contract supports;
* steps absent from a proposed graph are DETECTED as deletion requests -- the
  contract says omission deletes, so detection must exist before any apply;
* ``apply_intent`` never drops a node silently: only an explicit identity in
  ``remove_*`` removes, and an unknown removal target is refused;
* restore has no documented operation, so a restore is a fresh approved
  update that reads the current revision first -- never a stale-wire replay.

The W02 synthetic graphs are read from disk at their worktree path; nothing is
copied into this repository.  Cases the fixture does not carry are built
inline.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path

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

from cli_anything.gohighlevel.public.adapter import (  # noqa: E402
    ApprovalRef,
    PublicGhlAdapter,
)
from cli_anything.gohighlevel.public.capability import (  # noqa: E402
    Capability,
    CapabilityGate,
)
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.operations import OPERATIONS  # noqa: E402
from cli_anything.gohighlevel.public.readback import ReadbackRegistry  # noqa: E402
from cli_anything.gohighlevel.public.result import Status  # noqa: E402
from cli_anything.gohighlevel.public.workflow_v4 import (  # noqa: E402
    WorkflowGap,
    WorkflowV4Adapter,
)
from cli_anything.gohighlevel.public.workflow_v4_intent import (  # noqa: E402
    ADDED,
    REMOVED,
    UNTOUCHED,
    apply_intent,
    diff_definition,
)

TENANT = fake_tenant()
WORKFLOW_ID = "wf_synthetic_0001"
APPROVAL = ApprovalRef(ref="approval-synthetic-v4")

READ = "workflows.definition.read"
UPDATE = "workflows.definition.update"


def _fixture_path() -> Path | None:
    override = os.environ.get("GHL_WORKFLOW_V4_GRAPHS")
    if override and os.path.isfile(override):
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        if parent.name != "worktrees":
            continue
        candidate = (
            parent
            / "W02-fixtures"
            / "tests"
            / "fixtures"
            / "ghl_compat"
            / "workflow_v4_graphs.json"
        )
        if candidate.is_file():
            return candidate
    return None


def _fixture_cases() -> dict[str, dict]:
    path = _fixture_path()
    if path is None:
        return {}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return {graph["case_id"]: graph for graph in data["graphs"]}


_CASES = _fixture_cases()


def _payload(definition: dict, status: str = "draft") -> dict:
    return {"status": status, "definition": definition}


def _json_response(payload: dict, status: int = 200):
    return resp(status, json.dumps(payload).encode("utf-8"))


def _gate(*operation_ids: str) -> CapabilityGate:
    gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
    for operation_id in operation_ids:
        row = OPERATIONS[operation_id]
        capability = Capability(
            operation_id=operation_id,
            contract_verified=True,
            adapter_built=True,
            offline_tests_passed=True,
            read_verified=True,
            canary_verified=True,
        )
        gate.enable(capability, write=bool(row.write))
    return gate


def _adapter(
    transport: FakeTransport, gate: CapabilityGate | None = None
) -> WorkflowV4Adapter:
    public = PublicGhlAdapter(
        auth=fake_auth(),
        operations=OPERATIONS,
        transport=transport,
        capability=gate,
        readbacks=ReadbackRegistry(),
    )
    return WorkflowV4Adapter(public=public)


def _node(nodes: list[dict], identity: str) -> dict:
    for node in nodes:
        if node.get("id") == identity:
            return node
    raise AssertionError(f"node {identity!r} absent from {nodes!r}")


class FixtureGraphPreservation(unittest.TestCase):
    def test_untouched_nodes_survive_the_complete_replacement_write(self) -> None:
        case = _CASES.get("simple_linear_update")
        if case is None:
            self.skipTest("W02 workflow_v4_graphs.json fixture not present")
        prior = copy.deepcopy(case["prior"])
        request = copy.deepcopy(case["request"])
        after = copy.deepcopy(request)
        after["version"] = 4

        transport = FakeTransport(
            [
                _json_response(_payload(prior)),
                resp(200, b"{}"),
                _json_response(_payload(after)),
                _json_response(_payload(after)),
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE))
        changed_action = _node(request["actions"], "act_wait")

        result = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent={"upsert_actions": [changed_action]},
            approval=APPROVAL,
            expected_revision=prior["version"],
        )

        self.assertIs(result.status, Status.ok, result.error)
        self.assertEqual(
            transport.requests[1]["body"],
            request,
            "the PUT body is the complete preserved graph, not a patch",
        )
        counts = result.evidence["workflow_v4"]["readback_diff"]["counts"]
        self.assertEqual(counts["untouched_actions"], 3)
        self.assertEqual(counts["untouched_edges"], 3)
        self.assertEqual(counts["untouched_triggers"], 1)
        self.assertEqual(counts["changed_actions"], 0)
        self.assertEqual(counts["removed_actions"], 0)

    def test_unknown_but_supported_node_survives_verbatim(self) -> None:
        case = _CASES.get("branch_with_unknown_but_supported_node")
        if case is None:
            self.skipTest("W02 workflow_v4_graphs.json fixture not present")
        prior = copy.deepcopy(case["prior"])
        request = copy.deepcopy(case["request"])
        after = copy.deepcopy(request)
        after["version"] = 6

        unknown_before = _node(prior["actions"], "act_unknown_synthetic")
        unknown_after = _node(request["actions"], "act_unknown_synthetic")
        self.assertEqual(unknown_before, unknown_after)
        self.assertEqual(
            unknown_before["type"], "synthetic_unknown_supported_node_type"
        )

        transport = FakeTransport(
            [
                _json_response(_payload(prior)),
                resp(200, b"{}"),
                _json_response(_payload(after)),
                _json_response(_payload(after)),
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE))

        result = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent={"upsert_actions": [_node(request["actions"], "act_sms_no")]},
            approval=APPROVAL,
            expected_revision=prior["version"],
        )

        self.assertIs(result.status, Status.ok, result.error)
        body = transport.requests[1]["body"]
        self.assertEqual(_node(body["actions"], "act_unknown_synthetic"), unknown_before)
        self.assertEqual(_node(body["edges"], "e_4"), _node(prior["edges"], "e_4"))
        self.assertEqual(body["triggers"], prior["triggers"])
        self.assertEqual(
            [node["id"] for node in body["actions"]],
            [node["id"] for node in prior["actions"]],
            "no node is added, removed or reordered by an unrelated update",
        )

        diff = diff_definition(prior, request)
        self.assertEqual(diff.added_actions(), ())
        self.assertEqual(diff.removed_actions(), ())
        self.assertEqual(
            [node.identity for node in diff.changed_actions()], ["act_sms_no"]
        )
        self.assertIn(
            "act_unknown_synthetic",
            [node.identity for node in diff.untouched_actions()],
        )
        self.assertFalse(diff.content_is_empty())

    def test_omitted_step_is_detected_as_a_deletion_request(self) -> None:
        case = _CASES.get("omitted_step_deletion_detected")
        if case is None:
            self.skipTest("W02 workflow_v4_graphs.json fixture not present")
        prior = copy.deepcopy(case["prior"])
        request = copy.deepcopy(case["request"])

        transport = FakeTransport()
        diff = diff_definition(prior, request)

        self.assertTrue(diff.has_deletions)
        self.assertEqual(
            {(node.kind, node.identity) for node in diff.deletion_requests()},
            {
                ("actions", "act_wait"),
                ("edges", "e_2"),
                ("edges", "e_3"),
            },
        )
        self.assertEqual(
            [node.identity for node in diff.added_edges()], ["e_5"]
        )
        self.assertEqual(diff.changed_actions(), ())
        self.assertFalse(diff.content_is_empty())
        self.assertEqual(
            transport.call_count,
            0,
            "detection happens before any apply; nothing was written",
        )


class IntentNeverDropsAStep(unittest.TestCase):
    def _graph(self) -> dict:
        return {
            "version": 7,
            "name": "Synthetic Preservation Flow",
            "source": "synthetic",
            "triggerRelation": {"trg_1": ["e_1"]},
            "settings": {"timezone": "UTC", "syntheticUnknownSetting": True},
            "triggers": [
                {"id": "trg_1", "type": "contact_created", "name": "Created"}
            ],
            "actions": [
                {"id": "act_a", "type": "sms", "name": "A"},
                {"id": "act_b", "type": "wait", "name": "B"},
                {
                    "id": "act_unknown",
                    "type": "synthetic_unknown_supported_node_type",
                    "config": {"synthetic_key": "SYNTHETIC_VALUE"},
                },
            ],
            "edges": [
                {"id": "e_1", "from": "trg_1", "to": "act_a"},
                {"id": "e_2", "from": "act_a", "to": "act_b"},
                {"id": "e_3", "from": "act_b", "to": "act_unknown"},
            ],
        }

    def test_no_upsert_and_no_removal_keeps_every_node_verbatim(self) -> None:
        graph = self._graph()
        proposed = apply_intent(graph, {"set_fields": {"name": graph["name"]}})

        for kind in ("actions", "edges", "triggers"):
            self.assertEqual(proposed[kind], graph[kind])
        self.assertEqual(proposed["triggerRelation"], graph["triggerRelation"])
        self.assertEqual(proposed["settings"], graph["settings"])
        self.assertEqual(proposed["version"], 7)
        self.assertFalse(diff_definition(graph, proposed).has_deletions)

    def test_only_an_explicit_identity_removes_a_node(self) -> None:
        graph = self._graph()
        proposed = apply_intent(graph, {"remove_actions": ["act_b"]})

        self.assertEqual(
            [node["id"] for node in proposed["actions"]],
            ["act_a", "act_unknown"],
        )
        self.assertEqual(proposed["edges"], graph["edges"])
        diff = diff_definition(graph, proposed)
        self.assertEqual(
            [node.identity for node in diff.removed_actions()], ["act_b"]
        )

    def test_removing_an_unknown_identity_is_refused(self) -> None:
        graph = self._graph()
        with self.assertRaises(ContractViolation) as caught:
            apply_intent(graph, {"remove_actions": ["act_absent"]})
        self.assertEqual(caught.exception.rule, "removal_target_unknown")

    def test_upsert_into_a_complete_graph_keeps_every_other_node(self) -> None:
        graph = self._graph()
        updated = dict(_node(graph["actions"], "act_a"))
        updated["name"] = "A changed"
        proposed = apply_intent(graph, {"upsert_actions": [updated]})

        self.assertEqual(
            [node["id"] for node in proposed["actions"]],
            ["act_a", "act_b", "act_unknown"],
        )
        self.assertEqual(_node(proposed["actions"], "act_unknown"),
                         _node(graph["actions"], "act_unknown"))
        self.assertEqual(proposed["edges"], graph["edges"])
        self.assertEqual(proposed["triggers"], graph["triggers"])

    def test_unknown_keys_are_not_treated_as_nodes(self) -> None:
        graph = self._graph()
        graph["vendorExtension"] = {
            "actions": [{"id": "not_a_step", "type": "opaque"}]
        }
        proposed = apply_intent(graph, {"set_fields": {"source": "synthetic"}})
        self.assertEqual(proposed["vendorExtension"], graph["vendorExtension"])
        self.assertEqual(len(proposed["actions"]), 3)

    def test_id_less_node_is_matched_by_content_never_by_guess(self) -> None:
        current = {
            "version": 2,
            "actions": [{"type": "sms", "name": "A"}],
            "edges": [],
            "triggers": [],
        }
        proposed_same = {
            "version": 2,
            "actions": [{"type": "sms", "name": "A"}],
            "edges": [],
            "triggers": [],
        }
        proposed_changed = {
            "version": 2,
            "actions": [{"type": "sms", "name": "B"}],
            "edges": [],
            "triggers": [],
        }

        same = diff_definition(current, proposed_same)
        self.assertEqual(len(same.untouched_actions()), 1)
        self.assertEqual(same.added_actions(), ())
        self.assertEqual(same.removed_actions(), ())

        changed = diff_definition(current, proposed_changed)
        self.assertEqual(changed.changed_actions(), ())
        self.assertEqual(len(changed.removed_actions()), 1)
        self.assertEqual(len(changed.added_actions()), 1)
        self.assertEqual(changed.removed_actions()[0].status, REMOVED)
        self.assertEqual(changed.added_actions()[0].status, ADDED)
        self.assertEqual(same.untouched_actions()[0].status, UNTOUCHED)

        with self.assertRaises(ContractViolation) as caught:
            apply_intent(current, {"upsert_actions": [{"type": "sms", "name": "C"}]})
        self.assertEqual(
            caught.exception.rule, "intent_node_identity_missing"
        )


class RestoreReadsFreshRevision(unittest.TestCase):
    def test_restore_without_a_documented_operation_is_a_named_gap(self) -> None:
        transport = FakeTransport()
        adapter = _adapter(transport, _gate(READ, UPDATE))
        with self.assertRaises(WorkflowGap) as caught:
            adapter.restore_workflow(
                tenant=TENANT, workflow_id=WORKFLOW_ID
            )
        self.assertEqual(
            caught.exception.rule, "workflow_restore_has_no_documented_operation"
        )
        self.assertIn("fresh approved update", caught.exception.detail["unblock"])
        self.assertEqual(transport.call_count, 0)

    def test_restore_as_update_reads_the_current_revision_before_writing(self) -> None:
        prior = {
            "version": 21,
            "name": "Synthetic Restore Flow",
            "source": "synthetic",
            "settings": {"restored": False},
            "triggers": [
                {"id": "trg_1", "type": "contact_created", "name": "Created"}
            ],
            "actions": [{"id": "act_a", "type": "sms", "name": "A"}],
            "edges": [{"id": "e_1", "from": "trg_1", "to": "act_a"}],
        }
        after = copy.deepcopy(prior)
        after["version"] = 22
        after["settings"] = {"restored": True}

        transport = FakeTransport(
            [
                _json_response(_payload(prior)),
                resp(200, b"{}"),
                _json_response(_payload(after)),
                _json_response(_payload(after)),
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE))

        result = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"settings": {"restored": True}}},
            approval=APPROVAL,
            expected_revision=21,
        )

        self.assertIs(result.status, Status.ok, result.error)
        self.assertEqual(
            [item["method"] for item in transport.requests], ["GET", "PUT", "GET", "GET"]
        )
        self.assertEqual(transport.requests[1]["body"]["version"], 21)
        self.assertFalse(
            any("restore" in item["url"] for item in transport.requests),
            "restore has no endpoint; it must be a fresh update",
        )

    def test_restore_with_a_stale_revision_writes_nothing(self) -> None:
        prior = {
            "version": 21,
            "name": "Synthetic Restore Flow",
            "source": "synthetic",
            "actions": [],
            "edges": [],
            "triggers": [],
        }
        transport = FakeTransport([_json_response(_payload(prior))])
        adapter = _adapter(transport, _gate(READ, UPDATE))

        result = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"name": prior["name"]}},
            approval=APPROVAL,
            expected_revision=20,
        )

        self.assertIs(result.status, Status.validation_error)
        self.assertEqual(result.error["rule"], "stale_revision")
        self.assertEqual(transport.call_count, 1)
        self.assertEqual([item["method"] for item in transport.requests], ["GET"])

    def test_diff_flags_the_removal_but_apply_requires_an_explicit_identity(self) -> None:
        prior = {
            "version": 5,
            "actions": [
                {"id": "act_a", "type": "sms", "name": "A"},
                {"id": "act_b", "type": "wait", "name": "B"},
            ],
            "edges": [{"id": "e_1", "from": "act_a", "to": "act_b"}],
            "triggers": [],
        }
        omitted = copy.deepcopy(prior)
        omitted["actions"] = [prior["actions"][0]]
        omitted["edges"] = []

        diff = diff_definition(prior, omitted)
        self.assertTrue(diff.has_deletions)
        self.assertEqual(
            {node.identity for node in diff.deletion_requests()},
            {"act_b", "e_1"},
        )

        proposed = apply_intent(prior, {"set_fields": {"name": "same"}})
        self.assertEqual(len(proposed["actions"]), 2)
        self.assertEqual(len(proposed["edges"]), 1)


if __name__ == "__main__":
    unittest.main()
