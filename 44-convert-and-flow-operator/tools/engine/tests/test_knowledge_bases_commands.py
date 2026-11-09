"""WF30 -- KB command surface (registration-ready for WF03).

The command module is exercised through click's runner with synthetic
adapters.  Registration itself is a WF03 change request; these tests prove the
surface a registration line would expose.
"""

from __future__ import annotations

import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from click.testing import CliRunner  # noqa: E402

from _public_contract_fakes import FakeTransport, enabled_gate, make_adapter, registry, resp, row  # noqa: E402

from cli_anything.gohighlevel import kb_commands  # noqa: E402
from cli_anything.gohighlevel.public import knowledge_bases as kb  # noqa: E402
from cli_anything.gohighlevel.public.auth import TenantBinding  # noqa: E402

VERSION = "2021-04-15"
TENANT = TenantBinding(location_id="loc_synthetic_0001", source="test")
FIXTURES = os.path.join(_HERE, "fixtures", "wf30_kb")

ROWS = (
    row(kb.OPERATION_IDS["list"], method="GET", path_template="/knowledge-bases/",
        version=VERSION, tenant_binding="query.locationId"),
    row(kb.OPERATION_IDS["get"], method="GET",
        path_template="/knowledge-bases/{knowledgeBaseId}", version=VERSION,
        tenant_binding="path.knowledgeBaseId"),
    row(kb.OPERATION_IDS["agent.get"], method="GET",
        path_template="/conversation-ai/agents/{agentId}", version=VERSION,
        tenant_binding="path.agentId"),
    row(kb.OPERATION_IDS["agent.update"], method="PUT",
        path_template="/conversation-ai/agents/{agentId}", version=VERSION,
        tenant_binding="path.agentId", write=True),
)


def j(value):
    return json.dumps(value).encode("utf-8")


def client_with(responses, rows=ROWS):
    transport = FakeTransport(responses)
    adapter = make_adapter(transport, registry(*rows), gate=enabled_gate(list(rows)))
    return kb.KnowledgeBaseClient(public=adapter, sleep=lambda _s: None)


def wired_group(client):
    return kb_commands.build_kb_group(
        adapter_factory=lambda: client,
        tenant_factory=lambda: TENANT,
    )


class WiringTests(unittest.TestCase):
    def test_unwired_group_refuses_clearly(self):
        result = CliRunner().invoke(kb_commands.kb, ["inventory"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("not wired", result.output)

    def test_group_name_and_commands(self):
        group = wired_group(client_with([]))
        self.assertEqual(group.name, "kb")
        self.assertEqual(
            sorted(group.commands),
            sorted(["inventory", "create", "discover", "status", "train",
                    "upload", "attach", "detach", "evaluate"]),
        )


class CommandTests(unittest.TestCase):
    def test_inventory_success_prints_json(self):
        client = client_with([resp(200, j({"success": True, "data": {
            "knowledgeBases": [{"id": "kb_1", "name": "Support"}],
            "activeCount": 1, "hasMore": False,
        }}))])
        result = CliRunner().invoke(wired_group(client), ["inventory"])
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["body"]["data"]["knowledgeBases"][0]["id"], "kb_1")

    def test_inventory_failure_exits_nonzero(self):
        client = client_with([resp(403, b"{}")])
        result = CliRunner().invoke(wired_group(client), ["inventory"])
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(json.loads(result.output)["status"], "denied")

    def test_upload_gap_exits_two_with_named_rule(self):
        client = client_with([])
        path = os.path.join(FIXTURES, "kb-file-samples", "sample.pdf")
        result = CliRunner().invoke(wired_group(client), ["upload", "--kb-id", "kb_1", "--file", path])
        self.assertEqual(result.exit_code, 2)
        payload = json.loads(result.output)
        self.assertEqual(payload["rule"], "file_upload_contract_unresolved")

    def test_attach_reports_verified_state(self):
        client = client_with([
            resp(200, j({"id": "agent_1", "knowledgeBaseIds": ["kb_old"]})),
            resp(200, j({"id": "agent_1", "knowledgeBaseIds": ["kb_old", "kb_new"]})),
            resp(200, j({"id": "agent_1"})),
            resp(200, j({"id": "agent_1", "knowledgeBaseIds": ["kb_old", "kb_new"]})),
        ])
        result = CliRunner().invoke(
            wired_group(client), ["attach", "--agent-id", "agent_1", "--kb-id", "kb_new"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["state"], "attached")
        self.assertTrue(payload["verified"])

    def test_evaluate_without_interrogator_is_not_run(self):
        cases = [
            {"case_id": "c1", "kind": "known_answer", "question": "q"},
            {"case_id": "c2", "kind": "conflict", "question": "q"},
            {"case_id": "c3", "kind": "outside_material", "question": "q"},
            {"case_id": "c4", "kind": "stale_after_update", "question": "q"},
            {"case_id": "c5", "kind": "cross_client", "question": "q"},
        ]
        path = os.path.join(os.environ["TMPDIR"], "wf30-retrieval-cases.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(cases, handle)
        result = CliRunner().invoke(
            wired_group(client_with([])),
            ["evaluate", "--cases", path, "--kb-id", "kb_1", "--agent-id", "agent_1"],
        )
        self.assertEqual(result.exit_code, 1)
        payload = json.loads(result.output)
        self.assertEqual(payload["state"], "not_run")
        self.assertFalse(payload["interrogator_used"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
