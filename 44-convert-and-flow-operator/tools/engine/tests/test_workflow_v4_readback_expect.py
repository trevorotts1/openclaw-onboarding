"""V4 write read-back expectations -- GU-004 3.2 (the MAJOR 5 follow-through).

The adapter refuses a write whose read-back carries no ``expect``: an empty
expectation verifies any 2xx, which is zero verification.  Every V4 write now
carries a real one, and this module pins what each expectation proves:

* update / status change -- the read-back returns THIS workflow (the
  documented root ``workflowId``), and for a status change the documented
  ``status`` too.  A DIFFERENT id, or an unreadable read-back, is never ok.
* delete -- the definition read answers 404, which is the documented proof the
  workflow is gone (``evaluate_readback`` answers ``absent`` before the
  expectation runs).  A read-back that still returns the workflow is never ok.
  ``absent`` is the ONE verdict this write accepts, so it is the one verdict
  the adapter's unknown_outcome mapping is overridden for.
* create -- the new name must be present in the list.  The frozen matcher is
  shallow, so the documented list envelopes ({workflows: []}, a bare array)
  read as a mismatch; the shape-tolerant name search (GU-003 WF-05) decides
  there, and it never decides in the create's favour on its own.

Every test is offline on ``FakeTransport``; synthetic identifiers only.
"""

from __future__ import annotations

import copy
import json
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

from cli_anything.gohighlevel.public.adapter import (  # noqa: E402
    ApprovalRef,
    PublicGhlAdapter,
)
from cli_anything.gohighlevel.public.capability import (  # noqa: E402
    Capability,
    CapabilityGate,
)
from cli_anything.gohighlevel.public.operations import OPERATIONS  # noqa: E402
from cli_anything.gohighlevel.public.readback import (  # noqa: E402
    ReadbackRegistry,
    ReadbackStatus,
)
from cli_anything.gohighlevel.public.result import Status  # noqa: E402
from cli_anything.gohighlevel.public.workflow_v4 import WorkflowV4Adapter  # noqa: E402

TENANT = fake_tenant()
WORKFLOW_ID = "wf_synthetic_0001"
OTHER_WORKFLOW_ID = "wf_synthetic_9999"
APPROVAL = ApprovalRef(ref="approval-synthetic-v4")
NEW_NAME = "Synthetic Created Flow"
NEW_ID = "wf_synthetic_0002"

READ = "workflows.definition.read"
UPDATE = "workflows.definition.update"
DELETE = "workflows.definition.delete"
CREATE = "workflows.definition.create"
LIST = "workflows.list"


def _graph(version: int = 3) -> dict:
    return {
        "version": version,
        "name": "Synthetic Readback Flow",
        "source": "synthetic",
        "triggers": [
            {"id": "trg_1", "type": "contact_created", "name": "Created"}
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


def _payload(
    definition: dict,
    status: str = "draft",
    workflow_id: str = WORKFLOW_ID,
) -> dict:
    # GU-003 WF-04: the definition read returns ``workflowId`` at the root --
    # the field the write read-backs assert.
    return {
        "status": status,
        "workflowId": workflow_id,
        "definition": definition,
    }


def _json_response(payload: dict, status: int = 200):
    return resp(status, json.dumps(payload).encode("utf-8"))


def _gate(*operation_ids: str) -> CapabilityGate:
    gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
    for operation_id in operation_ids:
        row = OPERATIONS[operation_id]
        gate.enable(
            Capability(
                operation_id=operation_id,
                contract_verified=True,
                adapter_built=True,
                offline_tests_passed=True,
                read_verified=True,
                canary_verified=True,
            ),
            write=bool(row.write),
        )
    return gate


def _adapter(
    transport: FakeTransport, gate: CapabilityGate | None = None
) -> WorkflowV4Adapter:
    return WorkflowV4Adapter(
        public=PublicGhlAdapter(
            auth=fake_auth(),
            operations=OPERATIONS,
            transport=transport,
            capability=gate,
            readbacks=ReadbackRegistry(),
        )
    )


def _update(adapter: WorkflowV4Adapter, prior: dict, **kwargs):
    return adapter.update_definition(
        tenant=TENANT,
        workflow_id=WORKFLOW_ID,
        intent={"set_fields": {"name": prior["name"]}},
        approval=APPROVAL,
        expected_revision=prior["version"],
        **kwargs,
    )


def _create_body() -> dict:
    return {
        "name": NEW_NAME,
        "source": "synthetic",
        "triggers": [{"id": "trg_1", "type": "contact_created", "name": "Created"}],
        "actions": [{"id": "act_sms", "type": "sms", "name": "A"}],
        "edges": [{"id": "e_1", "from": "trg_1", "to": "act_sms"}],
    }


class UpdateReadbackProvesIdentity(unittest.TestCase):
    """The update read-back must return THIS workflow, never a stand-in."""

    def test_the_expected_id_verifies_the_write(self) -> None:
        # positive control: the expectation is live, and it is satisfiable.
        prior = _graph(version=3)
        after = copy.deepcopy(prior)
        after["version"] = 4

        transport = FakeTransport(
            [
                _json_response(_payload(prior)),
                resp(200, b"{}"),
                _json_response(_payload(after)),  # read-back
                _json_response(_payload(after)),  # verification read
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE))

        result = _update(adapter, prior)

        self.assertIs(result.status, Status.ok, result.error)
        self.assertIs(result.readback.result, ReadbackStatus.verified)
        self.assertEqual(result.evidence["workflow_v4"]["revision_after"], 4)

    def test_a_readback_returning_a_different_workflow_is_not_ok(self) -> None:
        prior = _graph(version=3)
        after = copy.deepcopy(prior)
        after["version"] = 4

        transport = FakeTransport(
            [
                _json_response(_payload(prior)),
                resp(200, b"{}"),
                # the read-back answers with a DIFFERENT workflow's document.
                _json_response(_payload(after, workflow_id=OTHER_WORKFLOW_ID)),
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE))

        result = _update(adapter, prior)

        self.assertIsNot(result.status, Status.ok)
        self.assertIs(result.status, Status.unknown_outcome)
        self.assertIs(result.readback.result, ReadbackStatus.mismatch)
        self.assertEqual(result.error["rule"], "readback_mismatch")
        self.assertEqual(
            [item["method"] for item in transport.requests],
            ["GET", "PUT", "GET"],
            "the mismatch is the write's verdict; the graph is never re-read",
        )

    def test_an_unreadable_readback_is_unknown_outcome(self) -> None:
        prior = _graph(version=3)

        transport = FakeTransport(
            [
                _json_response(_payload(prior)),
                resp(200, b"{}"),
                resp(401, b'{"message":"synthetic"}'),
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE))

        result = _update(adapter, prior)

        self.assertIs(result.status, Status.unknown_outcome)
        self.assertIs(result.readback.result, ReadbackStatus.unreadable)
        self.assertEqual(result.error["rule"], "readback_unreadable")


class DeleteReadbackProvesAbsence(unittest.TestCase):
    """A delete accepts ONE verdict: the workflow is gone."""

    def test_a_404_readback_proves_the_delete_landed(self) -> None:
        prior = _graph(version=3)

        transport = FakeTransport(
            [
                _json_response(_payload(prior)),  # snapshot read
                resp(200, b'{"succeeded":true}'),  # the DELETE
                resp(404, b'{"message":"gone"}'),  # in-write read-back
                resp(404, b'{"message":"gone"}'),  # settle the pending row
                resp(404, b'{"message":"gone"}'),  # follow-up definition read
            ]
        )
        adapter = _adapter(transport, _gate(READ, DELETE))

        result = adapter.delete_workflow(
            tenant=TENANT, workflow_id=WORKFLOW_ID, approval=APPROVAL
        )

        self.assertIs(result.status, Status.ok, result.error)
        self.assertTrue(result.evidence["workflow_v4"]["deleted"])
        self.assertEqual(result.evidence["workflow_v4"]["readback_status"], "absent")
        self.assertEqual(result.evidence["readback"], "absent")
        self.assertEqual(
            [item["method"] for item in transport.requests],
            ["GET", "DELETE", "GET", "GET", "GET"],
            "the delete is never re-issued; every extra call is a read",
        )
        self.assertEqual(
            adapter._public._pending,
            {},
            "a proven delete must not leave the adapter holding a pending write",
        )

    def test_a_readback_that_still_shows_the_workflow_is_unknown_outcome(
        self,
    ) -> None:
        prior = _graph(version=3)

        transport = FakeTransport(
            [
                _json_response(_payload(prior)),  # snapshot read
                resp(200, b'{"succeeded":true}'),  # the DELETE
                # the read-back still returns the workflow: it survived.
                _json_response(_payload(prior)),
                _json_response(_payload(prior)),  # follow-up definition read
            ]
        )
        adapter = _adapter(transport, _gate(READ, DELETE))

        result = adapter.delete_workflow(
            tenant=TENANT, workflow_id=WORKFLOW_ID, approval=APPROVAL
        )

        self.assertIsNot(result.status, Status.ok)
        self.assertIs(result.status, Status.unknown_outcome)
        self.assertEqual(
            result.error["rule"], "delete_readback_still_present"
        )

    def test_a_readback_returning_another_workflow_is_not_a_delete(self) -> None:
        # only `absent` is overridden; a mismatch stands as the adapter says.
        prior = _graph(version=3)

        transport = FakeTransport(
            [
                _json_response(_payload(prior)),
                resp(200, b'{"succeeded":true}'),
                _json_response(_payload(prior, workflow_id=OTHER_WORKFLOW_ID)),
            ]
        )
        adapter = _adapter(transport, _gate(READ, DELETE))

        result = adapter.delete_workflow(
            tenant=TENANT, workflow_id=WORKFLOW_ID, approval=APPROVAL
        )

        self.assertIs(result.status, Status.unknown_outcome)
        self.assertIs(result.readback.result, ReadbackStatus.mismatch)
        self.assertEqual(result.error["rule"], "readback_mismatch")


class CreateReadbackByName(unittest.TestCase):
    """The create read-back expects the new name; the name search decides."""

    def _create(self, adapter: WorkflowV4Adapter):
        return adapter.create_workflow(
            tenant=TENANT,
            definition=_create_body(),
            approval=APPROVAL,
        )

    def test_the_new_name_in_the_list_verifies_the_create(self) -> None:
        # a ``data`` envelope: the shallow matcher can see the rows, so the
        # in-write read-back proves the name itself.
        transport = FakeTransport(
            [
                resp(201, json.dumps({"workflowId": NEW_ID, "status": "draft"}).encode()),
                _json_response(
                    {"data": [{"name": NEW_NAME, "id": NEW_ID, "status": "draft"}]}
                ),
                _json_response({"workflows": [{"name": NEW_NAME, "id": NEW_ID}]}),
            ]
        )
        adapter = _adapter(transport, _gate(CREATE, LIST))

        result = self._create(adapter)

        self.assertIs(result.status, Status.ok, result.error)
        self.assertIs(result.readback.result, ReadbackStatus.verified)
        self.assertEqual(result.evidence["workflow_v4"]["workflow_id"], NEW_ID)
        self.assertEqual(
            result.evidence["workflow_v4"]["readback_matched_by"], "name"
        )

    def test_a_list_envelope_the_matcher_cannot_see_still_finds_the_name(
        self,
    ) -> None:
        # the documented envelope: rows live under ``workflows``, deeper than
        # the frozen matcher reaches, so the in-write read-back mismatches.
        # The name search (GU-003 WF-05) is the shape-tolerant authority and
        # finds the workflow, so the create is ok -- never a false conflict.
        rows = {"workflows": [{"name": NEW_NAME, "id": NEW_ID, "status": "draft"}]}
        transport = FakeTransport(
            [
                resp(201, json.dumps({"workflowId": NEW_ID, "status": "draft"}).encode()),
                _json_response(rows),  # in-write read-back
                _json_response(rows),  # settle the adapter's pending row
                _json_response(rows),  # the name search
            ]
        )
        adapter = _adapter(transport, _gate(CREATE, LIST))

        result = self._create(adapter)

        self.assertIs(result.status, Status.ok, result.error)
        self.assertEqual(result.evidence["workflow_v4"]["workflow_id"], NEW_ID)
        self.assertEqual(
            result.evidence["workflow_v4"]["readback_matched_by"], "name"
        )
        # the shallow verdict is reported, not laundered away.
        self.assertEqual(result.evidence["readback"], "mismatch")
        self.assertEqual(
            adapter._public._pending,
            {},
            "the overridden read-back must not leave a pending write behind",
        )

    def test_a_create_whose_name_never_appears_is_unknown_outcome(self) -> None:
        # the override decides nothing on its own: no name, no success.
        rows = {"workflows": [{"name": "Some Other Flow", "id": "wf_synthetic_0009"}]}
        transport = FakeTransport(
            [
                resp(201, json.dumps({"workflowId": NEW_ID, "status": "draft"}).encode()),
                _json_response(rows),  # in-write read-back: mismatch
                _json_response(rows),  # settle the adapter's pending row
                _json_response(rows),  # the name search: not found
                _json_response({"workflows": []}),  # reconcile re-reads
            ]
        )
        adapter = _adapter(transport, _gate(CREATE, LIST))

        result = self._create(adapter)

        self.assertIs(result.status, Status.unknown_outcome)
        self.assertEqual(result.error["rule"], "create_readback_missing")

        reconciled = adapter.reconcile(result)

        self.assertIs(reconciled.status, Status.not_found)
        self.assertEqual(reconciled.evidence["workflow_v4"]["readback_status"], "absent")


class VacuousReadbackStillRefused(unittest.TestCase):
    """The refusal the fix did NOT touch: an empty expectation, anywhere."""

    def test_an_update_readback_without_an_expectation_is_refused(self) -> None:
        from cli_anything.gohighlevel.public.errors import ContractViolation
        from cli_anything.gohighlevel.public.readback import ReadbackSpec

        prior = _graph(version=3)
        transport = FakeTransport(
            [_json_response(_payload(prior)), resp(200, b"{}"), resp(200, b"{}")]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE))

        with self.assertRaises(ContractViolation) as caught:
            adapter._write(
                UPDATE,
                tenant=TENANT,
                path_params={"workflowId": WORKFLOW_ID},
                body={"version": 3},
                approval=APPROVAL,
                readback=ReadbackSpec(
                    operation_id=READ,
                    target_params={"workflowId": WORKFLOW_ID},
                    expect=None,
                ),
                attempt=1,
                kind="update",
                workflow_id=WORKFLOW_ID,
            )

        self.assertEqual(caught.exception.rule, "readback_vacuous")
        self.assertEqual(transport.call_count, 0)


if __name__ == "__main__":
    unittest.main()
