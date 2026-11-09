"""WF29 staging: create a Flow Agent and read the staging graph back.

Acceptance: B13 (staging half), IG-AI-06 (staging is not execution).
Every call is offline: a scripted ``FakeTransport``, synthetic ids only.
"""

from __future__ import annotations

import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from agent_studio_support import (  # noqa: E402
    ALLOWED_TOOLS,
    OTHER_TENANT,
    agent_document,
    approval_ref,
    fixture,
    ok,
    paged,
    public_tenant,
    studio_adapter,
    studio_rows,
)

from _public_contract_fakes import FakeTransport, resp  # noqa: E402

from cli_anything.gohighlevel.public.agent_studio import (  # noqa: E402
    DOCUMENTED_ROW_REQUESTS,
    OPERATION_IDS,
    StudioOperationRowMissing,
)


def _graph_with(**overrides):
    graph = {
        "entryNodeId": "node_start",
        "nodes": [
            {"id": "node_start", "type": "start", "tool": "conversation.greet"},
            {"id": "node_lookup", "type": "tool", "tool": "crm.contact.lookup"},
        ],
        "edges": [{"source": "node_start", "target": "node_lookup"}],
        "variables": [{"name": "topic"}],
        "configuration": {"locale": "en-US"},
    }
    graph.update(overrides)
    return graph


class OperationMapInvariants(unittest.TestCase):
    def test_every_modelled_operation_has_a_documented_row_request(self) -> None:
        self.assertEqual(
            sorted(OPERATION_IDS), sorted(DOCUMENTED_ROW_REQUESTS)
        )

    def test_no_deprecated_or_studio_adjacent_endpoint_is_modelled(self) -> None:
        for logical, request in DOCUMENTED_ROW_REQUESTS.items():
            with self.subTest(logical=logical):
                self.assertNotIn("public-api", request["path_template"])
                self.assertNotIn("managed", request["path_template"].lower())

    def test_a_missing_registry_row_fails_loudly(self) -> None:
        rows = studio_rows()
        del rows[OPERATION_IDS["agent.create"]]
        adapter, _public = studio_adapter(FakeTransport(), rows=rows)
        with self.assertRaises(StudioOperationRowMissing) as caught:
            adapter.create_agent(
                tenant=public_tenant(),
                name="Synthetic Flow Agent",
                version=_graph_with(),
                approval=approval_ref(),
                allowed_tools=ALLOWED_TOOLS,
            )
        self.assertEqual(caught.exception.rule, "studio_operation_row_missing")
        self.assertEqual(caught.exception.detail["owner"], "WF00")


class CreateStagingAgent(unittest.TestCase):
    def test_create_reports_the_staging_version_and_unique_name_match(self) -> None:
        document = fixture("staging_agent.json")
        transport = FakeTransport(
            [ok({"id": "agent_synthetic_0001"}), paged(document), paged(document)]
        )
        adapter, _public = studio_adapter(transport)

        result = adapter.create_agent(
            tenant=public_tenant(),
            name="Synthetic Flow Agent",
            version=_graph_with(),
            approval=approval_ref(),
            allowed_tools=ALLOWED_TOOLS,
        )

        self.assertEqual(result.status.value, "ok", result.error)
        studio = result.evidence["agent_studio"]
        self.assertEqual(studio["agent_id"], "agent_synthetic_0001")
        self.assertEqual(studio["staging_version_id"], "ver_synthetic_staging_0001")
        self.assertEqual(studio["status"], "staging")
        self.assertEqual(studio["readback_matched_by"], "name")
        # create + read-back + the shape-tolerant name search, never more
        self.assertEqual(transport.call_count, 3)
        self.assertEqual(transport.requests[0]["method"], "POST")
        sent = transport.requests[0]["body"]
        self.assertEqual(sent["name"], "Synthetic Flow Agent")
        self.assertIn("version", sent)
        self.assertNotIn("nodes", sent, "graph fields must be version-scoped")

    def test_create_without_a_readable_agent_is_unknown_not_ok(self) -> None:
        other = agent_document(name="Some Other Agent")
        transport = FakeTransport(
            [ok({"id": "agent_synthetic_0001"}), paged(other), paged(other)]
        )
        adapter, _public = studio_adapter(transport)

        result = adapter.create_agent(
            tenant=public_tenant(),
            name="Synthetic Flow Agent",
            version=_graph_with(),
            approval=approval_ref(),
            allowed_tools=ALLOWED_TOOLS,
        )

        self.assertEqual(result.status.value, "unknown_outcome")
        self.assertEqual(result.error["rule"], "create_readback_missing")
        self.assertEqual(adapter.pending_count(), 1)

    def test_create_with_an_unreadable_list_is_unknown_not_ok(self) -> None:
        transport = FakeTransport(
            [
                ok({"id": "agent_synthetic_0001"}),
                resp(200, b'{"not":"an envelope"}'),
                resp(200, b'{"not":"an envelope"}'),
            ]
        )
        adapter, _public = studio_adapter(transport)

        result = adapter.create_agent(
            tenant=public_tenant(),
            name="Synthetic Flow Agent",
            version=_graph_with(),
            approval=approval_ref(),
            allowed_tools=ALLOWED_TOOLS,
        )
        self.assertEqual(result.status.value, "unknown_outcome")
        self.assertEqual(result.error["rule"], "create_readback_unreadable")

    def test_two_name_matches_are_ambiguous_never_first(self) -> None:
        document = agent_document()
        transport = FakeTransport(
            [ok({"id": "agent_synthetic_0001"}), paged(document),
             paged(document, document)]
        )
        adapter, _public = studio_adapter(transport)

        result = adapter.create_agent(
            tenant=public_tenant(),
            name="Synthetic Flow Agent",
            version=_graph_with(),
            approval=approval_ref(),
            allowed_tools=ALLOWED_TOOLS,
        )
        self.assertEqual(result.status.value, "unknown_outcome")
        self.assertEqual(result.error["rule"], "create_readback_ambiguous")

    def test_agent_without_a_readable_staging_version_is_not_a_completed_create(
        self,
    ) -> None:
        document = agent_document(staging_id=None, production_id="ver_only_prod")
        transport = FakeTransport(
            [ok({"id": "agent_synthetic_0001"}), paged(document), paged(document)]
        )
        adapter, _public = studio_adapter(transport)

        result = adapter.create_agent(
            tenant=public_tenant(),
            name="Synthetic Flow Agent",
            version=_graph_with(),
            approval=approval_ref(),
            allowed_tools=ALLOWED_TOOLS,
        )
        self.assertEqual(result.status.value, "unknown_outcome")
        self.assertEqual(result.error["rule"], "create_readback_no_staging_version")


class CreateRefusalsBeforeTransport(unittest.TestCase):
    def _create(self, *, version, metadata=None, allowed_tools=ALLOWED_TOOLS):
        transport = FakeTransport()
        adapter, _public = studio_adapter(transport)
        result = adapter.create_agent(
            tenant=public_tenant(),
            name="Synthetic Flow Agent",
            version=version,
            approval=approval_ref(),
            metadata=metadata,
            allowed_tools=allowed_tools,
        )
        return result, transport

    def test_deprecated_top_level_graph_field_is_refused(self) -> None:
        result, transport = self._create(
            version=_graph_with(), metadata={"nodes": [], "description": "x"}
        )
        self.assertEqual(result.status.value, "validation_error")
        self.assertEqual(result.error["rule"], "deprecated_top_level_graph_field")
        self.assertIn("nodes", result.error["fields"])
        self.assertEqual(transport.call_count, 0)

    def test_a_tool_outside_the_allowlist_is_refused(self) -> None:
        graph = _graph_with(
            nodes=[{"id": "node_start", "tool": "unapproved.tool"}],
            edges=[],
            entryNodeId="node_start",
        )
        result, transport = self._create(version=graph)
        self.assertEqual(result.error["rule"], "studio_graph_invalid")
        codes = [item["code"] for item in result.error["graph"]["findings"]]
        self.assertIn("tool_not_allowlisted", codes)
        self.assertEqual(transport.call_count, 0)

    def test_a_graph_declaring_tools_without_an_allowlist_is_refused(self) -> None:
        result, transport = self._create(version=_graph_with(), allowed_tools=None)
        self.assertEqual(result.error["rule"], "studio_graph_invalid")
        codes = [item["code"] for item in result.error["graph"]["findings"]]
        self.assertIn("tool_allowlist_required", codes)
        self.assertEqual(transport.call_count, 0)

    def test_a_dangling_edge_is_refused(self) -> None:
        graph = _graph_with(edges=[{"source": "node_start", "target": "node_ghost"}])
        result, transport = self._create(version=graph)
        codes = [item["code"] for item in result.error["graph"]["findings"]]
        self.assertIn("edge_dangling", codes)
        self.assertEqual(transport.call_count, 0)

    def test_an_unreachable_node_is_refused(self) -> None:
        graph = _graph_with(
            nodes=[
                {"id": "node_start"},
                {"id": "node_mid"},
                {"id": "node_island"},
            ],
            edges=[{"source": "node_start", "target": "node_mid"}],
        )
        result, transport = self._create(version=graph)
        codes = [item["code"] for item in result.error["graph"]["findings"]]
        self.assertIn("unreachable_node", codes)
        self.assertEqual(transport.call_count, 0)

    def test_a_foreign_tenant_resource_id_is_refused(self) -> None:
        graph = _graph_with(
            nodes=[{"id": "node_start", "locationId": OTHER_TENANT}],
            edges=[],
        )
        result, transport = self._create(version=graph)
        codes = [item["code"] for item in result.error["graph"]["findings"]]
        self.assertIn("foreign_tenant_resource", codes)
        self.assertNotIn(OTHER_TENANT, json.dumps(result.error))
        self.assertEqual(transport.call_count, 0)

    def test_a_graph_that_is_not_a_mapping_is_refused(self) -> None:
        result, transport = self._create(version=["not", "a", "graph"])  # type: ignore[arg-type]
        self.assertEqual(result.error["rule"], "studio_graph_invalid")
        self.assertEqual(transport.call_count, 0)


class ReadStagingGraph(unittest.TestCase):
    def test_read_returns_the_document_and_keeps_it_out_of_evidence(self) -> None:
        document = fixture("staging_agent.json")
        transport = FakeTransport([ok(document)])
        adapter, _public = studio_adapter(transport)

        result, payload = adapter.read_agent_document(
            tenant=public_tenant(), agent_id="agent_synthetic_0001"
        )

        self.assertEqual(result.status.value, "ok")
        self.assertEqual(payload, document)
        self.assertNotIn("unknownFutureField", json.dumps(result.evidence))
        self.assertEqual(transport.requests[0]["method"], "GET")
        self.assertIn("agent_synthetic_0001", transport.requests[0]["url"])
        self.assertEqual(
            transport.requests[0]["query"]["locationId"], public_tenant().location_id
        )

    def test_a_denied_read_returns_no_payload(self) -> None:
        transport = FakeTransport()
        adapter, _public = studio_adapter(transport, deny_all=True)

        result, payload = adapter.read_agent_document(
            tenant=public_tenant(), agent_id="agent_synthetic_0001"
        )
        self.assertEqual(result.status.value, "denied")
        self.assertEqual(result.error["rule"], "capability_disabled")
        self.assertIsNone(payload)
        self.assertEqual(transport.call_count, 0)
        self.assertTrue(result.receipt_id.startswith("gxo_res_"))

    def test_an_unbound_capability_probe_denies(self) -> None:
        adapter, _public = studio_adapter(FakeTransport())
        self.assertFalse(adapter.capability("agent.read").enabled)
        self.assertTrue(adapter.capability("agent.read", tenant=public_tenant()).enabled)


if __name__ == "__main__":
    unittest.main()
