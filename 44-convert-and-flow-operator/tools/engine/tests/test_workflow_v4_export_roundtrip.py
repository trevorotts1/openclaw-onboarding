"""Export -> update round trip, deletion scope, id-less nodes, revision echo.

Four frozen expectations exercised end to end (GU-004 2.4 / 5.7):

* an exported ``{status, definition}`` document fed back to ``workflows update``
  must NOT read as a graph of removals -- the envelope is unwrapped and every
  current node survives the PUT;
* an update whose intent DELETES a node refuses with
  ``deletion_requires_approval`` BEFORE transport unless the approval is
  deletion-scoped;
* an id-less node in the current graph is refused by ``intent_from_definition``
  rather than silently dropped from the present set;
* the CLI echoes the revision it read, so the 422 ``stale_revision`` branch is
  reachable from the shipped verb.

Everything is offline: ``FakeTransport`` records requests and replays scripted
responses.  A V4 snapshot is also shown to restore (Major D).
"""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
from cli_anything.gohighlevel.public.workflow_v4 import WorkflowV4Adapter  # noqa: E402
from cli_anything.gohighlevel.utils.workflow_builder import (  # noqa: E402
    intent_from_definition,
)

TENANT = fake_tenant()
WORKFLOW_ID = "wf_synthetic_0001"
APPROVAL = ApprovalRef(ref="approval-synthetic-v4")
#: The same token, explicitly scoped to deletions.
DELETION_APPROVAL = ApprovalRef(ref="approval-synthetic-v4; scope:deletion")

READ = "workflows.definition.read"
UPDATE = "workflows.definition.update"


def _graph(version: int = 12) -> dict:
    return {
        "version": version,
        "name": "Synthetic Export Flow",
        "source": "synthetic",
        "triggers": [{"id": "trg_1", "type": "contact_created", "name": "Created"}],
        "actions": [
            {"id": "act_a", "type": "sms", "name": "A"},
            {"id": "act_b", "type": "wait", "name": "B"},
        ],
        "edges": [{"id": "e_1", "from": "act_a", "to": "act_b"}],
    }


def _payload(definition: dict, status: str = "draft") -> dict:
    # GU-003 WF-04: the definition read returns ``workflowId`` at the root,
    # and the write read-backs assert it to prove the read returned THIS
    # workflow.  A payload without it is a mismatch, by design.  ``export``
    # writes the {status, definition} envelope only, so a file is built
    # separately where the test feeds one back in.
    return {
        "status": status,
        "workflowId": WORKFLOW_ID,
        "definition": definition,
    }

def _exported_file(definition: dict, status: str = "draft") -> dict:
    """Exactly what ``workflows export`` writes to disk."""
    return {"status": status, "definition": definition}


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


def _ids(nodes) -> list:
    return [node.get("id") for node in nodes]


class ExportedEnvelopeIsNotARemovalPlan(unittest.TestCase):
    """The blocker: feed an export straight back into update."""

    def test_export_round_trip_preserves_every_current_node(self) -> None:
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        prior = _graph(version=12)
        after = copy.deepcopy(prior)
        after["version"] = 13
        exported = _payload(copy.deepcopy(prior))  # what the definition read returns
        on_disk = _exported_file(copy.deepcopy(prior))  # exactly what `export` writes

        transport = FakeTransport(
            [
                _json_response(exported),          # CLI's own definition read
                _json_response(copy.deepcopy(exported)),  # update_definition's read
                resp(200, b"{}"),                  # the PUT
                _json_response(_payload(after)),   # readback
                _json_response(_payload(after)),   # second verification read
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE))

        with tempfile.TemporaryDirectory() as tmp:
            export_path = Path(tmp) / "wf.json"
            export_path.write_text(json.dumps(on_disk), encoding="utf-8")

            with patch(
                "cli_anything.gohighlevel.gohighlevel_cli._get_public_v4",
                return_value=(adapter, "test"),
            ), patch(
                "cli_anything.gohighlevel.utils.workflow_builder.workflow_route",
                return_value=type(
                    "R", (), {"public": True, "as_evidence": lambda self: {}}
                )(),
            ), patch(
                "cli_anything.gohighlevel.utils.snapshot_manager.capture_payload",
                return_value=Path(tmp) / "snap.json",
            ), patch(
                "cli_anything.gohighlevel.utils.workflow_builder.public_approval",
                return_value=APPROVAL,
            ):
                result = CliRunner().invoke(
                    cli,
                    [
                        "--json",
                        "--experimental",
                        "--location-id",
                        TENANT.location_id,
                        "workflows",
                        "update",
                        "--workflow-id",
                        WORKFLOW_ID,
                        "--from-json",
                        str(export_path),
                    ],
                )

        self.assertEqual(result.exit_code, 0, result.output)
        methods = [item["method"] for item in transport.requests]
        self.assertIn("PUT", methods, methods)
        put = transport.requests[methods.index("PUT")]
        self.assertEqual(
            _ids(put["body"]["actions"]),
            ["act_a", "act_b"],
            "feeding an export back must not read the current graph as removals",
        )
        self.assertEqual(_ids(put["body"]["edges"]), ["e_1"])
        self.assertEqual(_ids(put["body"]["triggers"]), ["trg_1"])

    def test_a_really_missing_node_is_still_refused_before_transport(self) -> None:
        prior = _graph(version=12)
        desired = copy.deepcopy(prior)
        desired["actions"] = [prior["actions"][0]]  # act_b genuinely gone

        intent = intent_from_definition(prior, desired)
        self.assertEqual(tuple(intent.remove_actions), ("act_b",))

        transport = FakeTransport([_json_response(_payload(prior))])
        adapter = _adapter(transport, _gate(READ, UPDATE))

        result = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent=intent,
            approval=APPROVAL,
            expected_revision=12,
        )

        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.error["rule"], "deletion_requires_approval")
        self.assertEqual(
            result.error["deletion_requests"],
            [{"kind": "actions", "identity": "act_b"}],
        )
        self.assertTrue(result.evidence["refused_before_transport"])
        self.assertEqual(
            [item["method"] for item in transport.requests],
            ["GET"],
            "the deletion refusal must happen before the PUT",
        )

    def test_a_deletion_scoped_approval_permits_the_removal(self) -> None:
        prior = _graph(version=12)
        desired = copy.deepcopy(prior)
        desired["actions"] = [prior["actions"][0]]
        desired["edges"] = []
        intent = intent_from_definition(prior, desired)

        written = copy.deepcopy(desired)
        written["version"] = 13

        transport = FakeTransport(
            [
                _json_response(_payload(prior)),             # update_definition's read
                resp(200, b"{}"),                            # the PUT
                _json_response(_payload(copy.deepcopy(prior))),  # adapter readback GET
                _json_response(_payload(written)),           # verification read
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE))

        result = adapter.update_definition(
            tenant=TENANT,
            workflow_id=WORKFLOW_ID,
            intent=intent,
            approval=DELETION_APPROVAL,
            expected_revision=12,
        )

        self.assertIs(result.status, Status.ok, result.error)
        methods = [item["method"] for item in transport.requests]
        self.assertIn("PUT", methods)
        put = transport.requests[methods.index("PUT")]
        self.assertEqual(_ids(put["body"]["actions"]), ["act_a"])
        self.assertEqual(put["body"]["edges"], [])


class IdLessCurrentNodeIsRefused(unittest.TestCase):
    def test_intent_from_definition_refuses_an_id_less_current_node(self) -> None:
        current = {
            "version": 3,
            "name": "Idless Flow",
            "actions": [
                {"id": "act_a", "type": "sms", "name": "A"},
                {"type": "wait", "name": "no identity"},
            ],
            "edges": [],
            "triggers": [],
        }

        with self.assertRaises(ContractViolation) as caught:
            intent_from_definition(current, copy.deepcopy(current))
        self.assertEqual(
            caught.exception.rule, "current_node_identity_missing"
        )
        self.assertEqual(caught.exception.detail["kind"], "actions")
        self.assertEqual(caught.exception.detail["count"], 1)

    def test_an_identified_graph_still_builds_an_intent(self) -> None:
        current = _graph(version=12)
        intent = intent_from_definition(current, copy.deepcopy(current))
        self.assertEqual(tuple(intent.remove_actions), ())
        self.assertEqual(len(intent.upsert_actions), 2)


class CliEchoesTheRevisionItRead(unittest.TestCase):
    def test_a_revision_moved_between_the_two_reads_refuses_with_422(self) -> None:
        """The CLI's echo reaches the adapter: a mismatch is a 422, no PUT."""

        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        prior = _graph(version=12)
        moved = copy.deepcopy(prior)
        moved["version"] = 99  # somebody else wrote between the two reads

        transport = FakeTransport(
            [
                _json_response(_payload(prior)),          # CLI read -> echo 12
                _json_response(_payload(moved)),          # update read -> 99
            ]
        )
        adapter = _adapter(transport, _gate(READ, UPDATE))

        with tempfile.TemporaryDirectory() as tmp:
            desired_path = Path(tmp) / "desired.json"
            desired_path.write_text(json.dumps(copy.deepcopy(prior)), encoding="utf-8")

            with patch(
                "cli_anything.gohighlevel.gohighlevel_cli._get_public_v4",
                return_value=(adapter, "test"),
            ), patch(
                "cli_anything.gohighlevel.utils.workflow_builder.workflow_route",
                return_value=type(
                    "R", (), {"public": True, "as_evidence": lambda self: {}}
                )(),
            ), patch(
                "cli_anything.gohighlevel.utils.snapshot_manager.capture_payload",
                return_value=Path(tmp) / "snap.json",
            ), patch(
                "cli_anything.gohighlevel.utils.workflow_builder.public_approval",
                return_value=APPROVAL,
            ):
                result = CliRunner().invoke(
                    cli,
                    [
                        "--json",
                        "--experimental",
                        "--location-id",
                        TENANT.location_id,
                        "workflows",
                        "update",
                        "--workflow-id",
                        WORKFLOW_ID,
                        "--from-json",
                        str(desired_path),
                    ],
                )

        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("stale_revision", result.output)
        self.assertEqual(
            [item["method"] for item in transport.requests],
            ["GET", "GET"],
            "a stale revision must never reach the PUT",
        )

    def test_update_definition_requires_the_revision_keyword(self) -> None:
        transport = FakeTransport()
        adapter = _adapter(transport, _gate(READ, UPDATE))
        with self.assertRaises(ContractViolation) as caught:
            adapter.update_definition(
                tenant=TENANT,
                workflow_id=WORKFLOW_ID,
                intent={"set_fields": {"source": "synthetic"}},
                approval=APPROVAL,
                expected_revision=None,
            )
        self.assertEqual(caught.exception.rule, "expected_revision_required")
        self.assertEqual(transport.call_count, 0)


class V4SnapshotRestores(unittest.TestCase):
    """Major D: the V4 {status, definition} capture must be restorable."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        os.environ["CAF_DATA_DIR"] = self.tmp

    def tearDown(self) -> None:
        os.environ.pop("CAF_DATA_DIR", None)
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_restore_flattens_the_v4_envelope(self) -> None:
        from unittest.mock import MagicMock

        from cli_anything.gohighlevel.utils.snapshot_manager import restore

        snapshot_path = Path(self.tmp) / "snap.json"
        snapshot_path.write_text(
            json.dumps(_payload(_graph(version=7))), encoding="utf-8"
        )

        put_bodies: list = []
        live = {"id": WORKFLOW_ID, "version": 99, "name": "live"}
        client = MagicMock()
        client.location_id = TENANT.location_id

        # snapshot_manager resolves a MagicMock through the legacy .request()
        # path (it is not an InternalAdapter), so the PUT body lands there.
        def request(method, path, body=None, workflow_name="", **kwargs):
            if method == "PUT":
                put_bodies.append(dict(body))
                return {"id": WORKFLOW_ID}
            return dict(live)

        client.request.side_effect = request

        restore(client, WORKFLOW_ID, snapshot_path)

        self.assertEqual(len(put_bodies), 1, put_bodies)
        body = put_bodies[0]
        self.assertEqual(body["name"], "Synthetic Export Flow")
        self.assertEqual(_ids(body["actions"]), ["act_a", "act_b"])
        self.assertEqual(
            body["version"], 99, "the snapshot's historical revision is never replayed"
        )
        self.assertNotIn("definition", body)

    def test_a_v4_envelope_without_a_definition_name_still_fails_loud(self) -> None:
        from unittest.mock import MagicMock

        from cli_anything.gohighlevel.utils.snapshot_manager import restore

        snapshot_path = Path(self.tmp) / "bad.json"
        snapshot_path.write_text(
            json.dumps({"status": "draft", "definition": {"actions": []}}),
            encoding="utf-8",
        )
        client = MagicMock()
        client.location_id = TENANT.location_id
        with self.assertRaises(ValueError):
            restore(client, WORKFLOW_ID, snapshot_path)
        client.get_workflow.assert_not_called()


if __name__ == "__main__":
    unittest.main()