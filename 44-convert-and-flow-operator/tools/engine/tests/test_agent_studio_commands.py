"""WF29 command module: the registered CLI exercises the whole lifecycle.

WF03 adds ``studio`` to the main group; this test registers it on a local root
group with the same context shape so the command surface is proven here without
touching ``gohighlevel_cli.py``.  Every call is offline.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import click  # noqa: E402
from click.testing import CliRunner  # noqa: E402

from agent_studio_support import (  # noqa: E402
    ALLOWED_TOOLS,
    agent_document,
    approval_ref,
    execution_response,
    fixture,
    ok,
    public_tenant,
    studio_adapter,
)

from _public_contract_fakes import FakeTransport  # noqa: E402

from cli_anything.gohighlevel import agent_studio_commands  # noqa: E402

STAGING_ID = "ver_synthetic_staging_0001"
PRODUCTION_ID = "ver_synthetic_production_0001"


@click.group()
@click.option("--json", "use_json", is_flag=True)
@click.option("--location-id", "location_id", default=None)
@click.pass_context
def root(ctx, use_json, location_id):
    ctx.ensure_object(dict)
    ctx.obj["json"] = use_json
    ctx.obj["location_id"] = location_id


root.add_command(agent_studio_commands.studio)


class CommandSurface(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()
        self._tmp = tempfile.TemporaryDirectory(prefix="wf29-cmd-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name

    def _file(self, name: str, payload) -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return path

    def _patch(self, adapter):
        return mock.patch.object(
            agent_studio_commands,
            "load_studio_adapter",
            return_value=(adapter, "fake adapter for the command test"),
        )

    def test_the_group_registers_the_documented_verbs(self) -> None:
        self.assertIsInstance(agent_studio_commands.studio, click.Group)
        self.assertEqual(
            sorted(agent_studio_commands.studio.commands),
            ["create", "execute", "promote", "read", "rollback", "session", "update"],
        )

    def test_create_exits_zero_and_prints_the_staging_identity(self) -> None:
        document = fixture("staging_agent.json")
        adapter, _public = studio_adapter(
            FakeTransport(
                [ok({"id": "agent_synthetic_0001"}), ok({"agents": [document]}),
                 ok({"agents": [document]})]
            )
        )
        version_file = self._file("version.json", fixture("staging_agent.json")["versions"][0])
        with self._patch(adapter):
            result = self.runner.invoke(
                root,
                ["--location-id", public_tenant().location_id, "--json",
                 "studio", "create", "--name", "Synthetic Flow Agent",
                 "--version-file", version_file,
                 "--approval-ref", "approval-synthetic-0001",
                 "--allowed-tool", "conversation.greet",
                 "--allowed-tool", "crm.contact.lookup"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status_detail"]["staging_version_id"], STAGING_ID)

    def test_a_disabled_write_exits_one(self) -> None:
        adapter, _public = studio_adapter(FakeTransport(), deny_all=True)
        version_file = self._file("version.json", fixture("staging_agent.json")["versions"][0])
        with self._patch(adapter):
            result = self.runner.invoke(
                root,
                ["--location-id", public_tenant().location_id,
                 "studio", "create", "--name", "Synthetic Flow Agent",
                 "--version-file", version_file],
            )
        self.assertEqual(result.exit_code, 1, result.output)

    def test_an_unknown_outcome_exits_three(self) -> None:
        other = agent_document(name="Some Other Agent")
        adapter, _public = studio_adapter(
            FakeTransport(
                [ok({"id": "agent_synthetic_0001"}), ok({"agents": [other]}),
                 ok({"agents": [other]})]
            )
        )
        version_file = self._file("version.json", fixture("staging_agent.json")["versions"][0])
        with self._patch(adapter):
            result = self.runner.invoke(
                root,
                ["--location-id", public_tenant().location_id,
                 "studio", "create", "--name", "Synthetic Flow Agent",
                 "--version-file", version_file,
                 "--approval-ref", "approval-synthetic-0001",
                 "--allowed-tool", "conversation.greet",
                 "--allowed-tool", "crm.contact.lookup"],
            )
        self.assertEqual(result.exit_code, 3, result.output)
        self.assertIn("OUTCOME UNKNOWN", result.output)

    def test_promote_round_trips_through_the_command(self) -> None:
        document = fixture("staging_agent.json")
        promoted = fixture("promoted_agent.json")
        adapter, _public = studio_adapter(
            FakeTransport(
                [ok(document), ok({"ok": True}), ok(document), ok(promoted)]
            )
        )
        with self._patch(adapter):
            result = self.runner.invoke(
                root,
                ["--location-id", public_tenant().location_id, "--json",
                 "studio", "promote", "--agent-id", "agent_synthetic_0001",
                 "--version-id", STAGING_ID,
                 "--approval-ref", "approval-synthetic-0001"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(
            payload["status_detail"]["previous_active_version_id"], PRODUCTION_ID
        )

    def test_execute_and_session_commands_expose_the_binding(self) -> None:
        document = fixture("staging_agent.json")
        plan = fixture("execution_plan.json")
        adapter, _public = studio_adapter(
            FakeTransport([ok(document), execution_response(), ok(document)])
        )
        payload_file = self._file("payload.json", plan["payload"])
        expect_file = self._file("expect.json", plan["output_expect"])
        with self._patch(adapter):
            executed = self.runner.invoke(
                root,
                ["--location-id", public_tenant().location_id, "--json",
                 "studio", "execute", "--agent-id", "agent_synthetic_0001",
                 "--payload-file", payload_file,
                 "--expect-file", expect_file,
                 "--contact-id", "contact_synthetic_0001",
                 "--thread-id", "thread_synthetic_0001",
                 "--approval-ref", "approval-synthetic-0001"],
            )
            self.assertEqual(executed.exit_code, 0, executed.output)
            bound = self.runner.invoke(
                root,
                ["--location-id", public_tenant().location_id,
                 "studio", "session", "--execution-id", "exec_synthetic_0001"],
            )
        self.assertEqual(bound.exit_code, 0, bound.output)
        session = json.loads(bound.output)
        self.assertEqual(session["location_id"], public_tenant().location_id)
        self.assertEqual(session["contact_id"], "contact_synthetic_0001")
        self.assertEqual(session["thread_id"], "thread_synthetic_0001")

    def test_an_unbound_execution_id_is_an_error(self) -> None:
        adapter, _public = studio_adapter(FakeTransport())
        with self._patch(adapter):
            result = self.runner.invoke(
                root, ["studio", "session", "--execution-id", "exec_absent"]
            )
        self.assertEqual(result.exit_code, 1, result.output)

    def test_a_missing_location_id_is_an_error(self) -> None:
        adapter, _public = studio_adapter(FakeTransport())
        with self._patch(adapter), mock.patch.dict(
            os.environ, {}, clear=False
        ):
            os.environ.pop("GHL_LOCATION_ID", None)
            result = self.runner.invoke(
                root, ["studio", "read", "--agent-id", "agent_synthetic_0001"]
            )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("no location id", result.output)


if __name__ == "__main__":
    unittest.main()
