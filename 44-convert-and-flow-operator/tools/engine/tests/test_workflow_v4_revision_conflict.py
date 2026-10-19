"""V4 revision discipline and conflict semantics -- GU-004 2.4 and 5.7.

Frozen expectations (section 6.2 and GU-003 WF-04 .. WF-09):

* a stale ``expected_revision`` refuses with 422 and writes nothing;
* a missing revision refuses; a non-integer opaque revision is carried
  unchanged (never parsed, coerced, incremented or synthesised);
* a published workflow refuses with 409 and is never auto-unpublished;
* a status change advances the revision, so the next write must be preceded
  by a fresh definition read carrying the new opaque revision;
* a write timeout is ``unknown_outcome``: a retry is refused until
  ``reconcile`` re-reads the affected graph, and reconcile never retries the
  write.

The synthetic graphs in the W02 fixture are read from disk when present; the
non-integer revision case is built inline because the fixture records the
older rejection expectation.
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
from cli_anything.gohighlevel.public.errors import (  # noqa: E402
    ReconciliationRequired,
)
from cli_anything.gohighlevel.public.operations import OPERATIONS  # noqa: E402
from cli_anything.gohighlevel.public.readback import ReadbackRegistry  # noqa: E402
from cli_anything.gohighlevel.public.result import Status  # noqa: E402
from cli_anything.gohighlevel.public.workflow_v4 import WorkflowV4Adapter  # noqa: E402
from cli_anything.gohighlevel.public.workflow_v4_intent import (  # noqa: E402
    apply_intent,
    carry_revision,
    extract_revision,
    revision_equals,
)

TENANT = fake_tenant()
WORKFLOW_ID = "wf_synthetic_0001"
APPROVAL = ApprovalRef(ref="approval-synthetic-v4")

READ = "workflows.definition.read"
UPDATE = "workflows.definition.update"
STATUS = "workflows.status.publish"


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


def _graph(version=3, name="Synthetic Conflict Flow") -> dict:
    return {
        "version": version,
        "name": name,
        "source": "synthetic",
        "triggers": [
            {"id": "trg_1", "type": "contact_created", "name": "Contact Created"}
        ],
        "actions": [
            {
                "id": "act_sms",
                "type": "sms",
                "name": "Send SMS",
                "message": "SYNTHETIC_MESSAGE_PLACEHOLDER",
            }
        ],
        "edges": [{"id": "e_1", "from": "trg_1", "to": "act_sms"}],
    }


def _payload(definition: dict, status: str = "draft") -> dict:
    # GU-003 WF-04: the definition read returns ``workflowId`` at the root,
    # and the write read-backs assert it to prove the read returned THIS
    # workflow.  A payload without it is a mismatch, by design.
    return {
        "status": status,
        "workflowId": WORKFLOW_ID,
        "definition": definition,
    }


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


class RevisionRefusal(unittest.TestCase):
    def test_stale_revision_is_422_and_writes_nothing(self) -> None:
        case = _CASES.get("stale_revision_conflict")
        if case is None:
            prior = _graph(version=12)
            stale_revision = 11
        else:
            prior = copy.deepcopy(case["prior"])
            stale_revision = case["request"]["version"]

        transport = FakeTransport([_json_response(_payload(prior))])
        adapter = _adapter(transport, _gate(READ, UPDATE))

        result = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"source": "synthetic"}},
            approval=APPROVAL,
            expected_revision=stale_revision,
        )

        self.assertIs(result.status, Status.validation_error)
        self.assertEqual(result.error["rule"], "stale_revision")
        self.assertEqual(result.error["documented_http_status"], 422)
        self.assertEqual(result.operation_id, UPDATE)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual([item["method"] for item in transport.requests], ["GET"])

    def test_missing_revision_is_refused_before_any_write(self) -> None:
        prior = _graph(version=12)
        del prior["version"]
        transport = FakeTransport([_json_response(_payload(prior))])
        adapter = _adapter(transport, _gate(READ, UPDATE))

        result = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"source": "synthetic"}},
            approval=APPROVAL,
            expected_revision=12,
        )

        self.assertIs(result.status, Status.validation_error)
        self.assertEqual(result.error["rule"], "revision_missing")
        self.assertEqual(result.error["documented_http_status"], 422)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual([item["method"] for item in transport.requests], ["GET"])

    def test_non_integer_opaque_revision_is_carried_unchanged(self) -> None:
        prior = _graph(version="rev-2026-10.3")
        after = copy.deepcopy(prior)
        after["version"] = "rev-2026-10.4"

        transport = FakeTransport(
            [
                _json_response(_payload(prior)),
                resp(200, b"{}"),
                _json_response(_payload(prior)),
                _json_response(_payload(after)),
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE))

        result = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"name": prior["name"]}},
            approval=APPROVAL,
            expected_revision="rev-2026-10.3",
        )

        self.assertIs(result.status, Status.ok, result.error)
        definition_write = transport.requests[1]
        self.assertEqual(definition_write["method"], "PUT")
        self.assertEqual(definition_write["body"]["version"], "rev-2026-10.3")
        self.assertIsInstance(definition_write["body"]["version"], str)
        self.assertEqual(
            result.evidence["workflow_v4"]["revision_before"], "rev-2026-10.3"
        )

        # The intent module is the authority for the echo: no parsing, no
        # coercion between 3, 3.0 and "3".
        self.assertEqual(extract_revision(prior), "rev-2026-10.3")
        self.assertEqual(
            carry_revision(prior, "rev-2026-10.3")["version"], "rev-2026-10.3"
        )
        self.assertFalse(revision_equals(3, "3"))
        self.assertFalse(revision_equals(3, 3.0))
        self.assertTrue(revision_equals("3", "3"))

    def test_published_workflow_is_409_with_no_auto_unpublish(self) -> None:
        case = _CASES.get("published_workflow_conflict")
        if case is None:
            prior = _graph(version=12)
            status = "published"
        else:
            prior = copy.deepcopy(case["prior"])
            status = prior.get("status", "published")

        transport = FakeTransport([_json_response(_payload(prior, status))])
        adapter = _adapter(transport, _gate(READ, UPDATE, STATUS))

        result = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"name": "Synthetic Changed Flow"}},
            approval=APPROVAL,
            expected_revision=12,
        )

        self.assertIs(result.status, Status.conflict)
        self.assertEqual(result.error["rule"], "workflow_published")
        self.assertEqual(result.error["documented_http_status"], 409)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(
            [item["method"] for item in transport.requests],
            ["GET"],
            "a published workflow must not be touched, least of all unpublished",
        )
        self.assertFalse(
            any("/status" in item["url"] for item in transport.requests)
        )

    def test_remote_409_on_the_definition_write_is_not_auto_unpublished(self) -> None:
        prior = _graph(version=12)
        transport = FakeTransport(
            [
                _json_response(_payload(prior)),
                resp(409, b'{"message":"workflow is published"}'),
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE, STATUS))

        result = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"name": prior["name"]}},
            approval=APPROVAL,
            expected_revision=12,
        )

        self.assertIs(result.status, Status.conflict)
        self.assertEqual(result.error["rule"], "conflict")
        self.assertEqual(
            [item["method"] for item in transport.requests], ["GET", "PUT"]
        )
        self.assertFalse(
            any("/status" in item["url"] for item in transport.requests),
            "409 must surface; unpublish is a separate authorization",
        )

    def test_status_change_revision_bump_forces_a_fresh_read_before_write(self) -> None:
        published = _graph(version=12, name="Synthetic Published Flow")
        fresh = copy.deepcopy(published)
        fresh["version"] = 13
        after = copy.deepcopy(fresh)
        after["version"] = 14

        transport = FakeTransport(
            [
                _json_response(_payload(published, "published")),
                resp(200, b"{}"),
                _json_response(_payload(published, "draft")),
                _json_response(_payload(published, "draft")),
                _json_response(_payload(fresh, "draft")),
                resp(200, b"{}"),
                _json_response(_payload(fresh, "draft")),
                _json_response(_payload(after, "draft")),
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE, STATUS))

        result = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent={"set_fields": {"name": fresh["name"]}},
            approval=APPROVAL,
            expected_revision=12,
            allow_draft_transition=True,
            draft_transition_approval=APPROVAL,
        )

        self.assertIs(result.status, Status.ok, result.error)
        self.assertEqual(
            [item["method"] for item in transport.requests],
            ["GET", "PUT", "GET", "GET", "GET", "PUT", "GET", "GET"],
        )
        self.assertTrue(transport.requests[1]["url"].endswith("/status"))
        self.assertEqual(transport.requests[1]["body"], {"status": "draft"})
        definition_write = transport.requests[5]
        self.assertTrue(definition_write["url"].endswith("/definition"))
        self.assertEqual(
            definition_write["body"]["version"],
            13,
            "the write must carry the revision read AFTER the status change",
        )
        self.assertNotEqual(definition_write["body"]["version"], 12)
        self.assertTrue(
            result.evidence["workflow_v4"]["draft_transition_performed"]
        )
        self.assertFalse(result.evidence["workflow_v4"]["publish_authorized"])

    def test_draft_transition_without_its_own_approval_is_refused(self) -> None:
        prior = _graph(version=12)
        transport = FakeTransport([_json_response(_payload(prior, "published"))])
        adapter = _adapter(transport, _gate(READ, UPDATE, STATUS))

        from cli_anything.gohighlevel.public.errors import ContractViolation

        with self.assertRaises(ContractViolation) as caught:
            adapter.update_definition(
                tenant=TENANT,
                workflow_id=WORKFLOW_ID,
                intent={"set_fields": {"name": prior["name"]}},
                approval=APPROVAL,
                expected_revision=12,
                allow_draft_transition=True,
                draft_transition_approval=None,
            )
        self.assertEqual(
            caught.exception.rule, "draft_transition_approval_required"
        )
        self.assertEqual(transport.call_count, 1)


class UnknownOutcomeReconciliation(unittest.TestCase):
    def _timeout_scenario(self):
        prior = _graph(version=3)
        proposed = apply_intent(prior, {"set_fields": {"name": prior["name"]}})
        settled = copy.deepcopy(proposed)
        settled["version"] = 4
        return prior, proposed, settled

    def test_timeout_is_unknown_outcome_and_blocks_retry_until_reconcile(self) -> None:
        prior, proposed, settled = self._timeout_scenario()
        transport = FakeTransport(
            [
                _json_response(_payload(prior)),
                resp(None, b"", error_kind="timeout"),
                _json_response(_payload(settled)),
                _json_response(_payload(settled)),
                _json_response(_payload(prior)),
                resp(200, b"{}"),
                _json_response(_payload(settled)),
                _json_response(_payload(settled)),
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE))
        intent = {"set_fields": {"name": prior["name"]}}

        first = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent=intent,
            approval=APPROVAL,
            expected_revision=3,
        )

        self.assertIs(first.status, Status.unknown_outcome)
        self.assertEqual(first.error["rule"], "transport_timeout")
        self.assertEqual(first.operation_id, UPDATE)
        self.assertRegex(first.receipt_id, r"^gxo_res_[0-9a-f]{12}$")
        self.assertEqual(transport.call_count, 2)

        with self.assertRaises(ReconciliationRequired) as caught:
            adapter.update_definition(
                tenant=TENANT,
                workflow_id=WORKFLOW_ID,
                intent=intent,
                approval=APPROVAL,
                expected_revision=3,
            )
        self.assertEqual(caught.exception.rule, "reconciliation_required")
        self.assertEqual(
            caught.exception.detail["rule"], "workflow_write_unreconciled"
        )
        self.assertEqual(
            transport.call_count,
            2,
            "a retry must not reach transport before reconcile",
        )

        reconciled = adapter.reconcile(first)

        self.assertIs(reconciled.status, Status.ok, reconciled.error)
        self.assertEqual(transport.call_count, 4)
        self.assertEqual(
            [item["method"] for item in transport.requests[2:]],
            ["GET", "GET"],
            "reconcile re-reads; it never replays the write",
        )
        self.assertEqual(reconciled.evidence["reconciled_from"], first.receipt_id)

        retried = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent=intent,
            approval=APPROVAL,
            expected_revision=3,
        )
        self.assertIs(retried.status, Status.ok, retried.error)
        self.assertEqual(transport.call_count, 8)

    def test_reconcile_cannot_be_replayed_after_it_settles(self) -> None:
        prior, _proposed, settled = self._timeout_scenario()
        transport = FakeTransport(
            [
                _json_response(_payload(prior)),
                resp(None, b"", error_kind="timeout"),
                _json_response(_payload(settled)),
                _json_response(_payload(settled)),
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE))
        intent = {"set_fields": {"name": prior["name"]}}
        first = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent=intent,
            approval=APPROVAL,
            expected_revision=3,
        )
        self.assertIs(first.status, Status.unknown_outcome)
        settled_result = adapter.reconcile(first)
        self.assertIs(settled_result.status, Status.ok)

        from cli_anything.gohighlevel.public.errors import ContractViolation

        with self.assertRaises(ContractViolation) as caught:
            adapter.reconcile(first)
        self.assertEqual(caught.exception.rule, "reconcile_unknown_receipt")


if __name__ == "__main__":
    unittest.main()
