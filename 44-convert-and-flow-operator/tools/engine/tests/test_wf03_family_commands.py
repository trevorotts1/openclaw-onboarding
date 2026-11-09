"""WF03 Pass-2: the 13 proposed families register against the frozen registry.

Every test is offline. The registry rows landed in WF00 (293a79b90), so each
delivered family must
  * own exactly the frozen rows it declares -- no invented operation id, no
    dropped row (IG-ROUTE-06 family registration);
  * refuse a row that is not ``public_direct`` with that row's route class and
    blocker, never substituting a private or authoring rail (route-before-token);
  * send nothing under --dry-run (A01/A06 dry-run discipline);
  * report the one family whose rows still do not exist as PENDING with its
    owner and the change request that asks for the rows -- never a stub.

Run:
    PYTHONPATH="$PWD" python3 -m pytest -q tests/test_wf03_family_commands.py
"""
from __future__ import annotations

import os
import sys
import unittest

import click
from click.testing import CliRunner

_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

from cli_anything.gohighlevel.commands import FAMILIES, _registry  # noqa: E402
from cli_anything.gohighlevel.commands import discover  # noqa: E402
from cli_anything.gohighlevel.public.operations import OPERATIONS  # noqa: E402

#: Families whose frozen rows landed in WF00 and therefore must be delivered.
_DELIVERED = {
    "agency", "agent_studio", "capabilities", "chat_widgets", "community",
    "conversation_ai", "courses", "knowledge_bases", "marketing_quizzes",
    "projects", "voice_ai", "workflow_monitoring",
}

class FamilyRegistrationTest(unittest.TestCase):
    def test_every_delivered_family_matches_the_frozen_registry(self):
        delivered, pending = discover()
        self.assertEqual(set(delivered), _DELIVERED)
        self.assertEqual(set(pending), {"meeting_rooms"})
        for name, module in sorted(delivered.items()):
            with self.subTest(family=name):
                group = module.build()
                self.assertIsInstance(group, click.Group)
                self.assertEqual(group.name, name)
                if name == "capabilities":
                    # No HTTP row belongs to this family; it reads the registry.
                    self.assertEqual(sorted(group.commands),
                                     ["catalog", "gate", "show"])
                    continue
                rows = _registry.rows_for(
                    module.OPERATION_ROOTS, module.EXTRA_OPERATION_IDS
                )
                self.assertTrue(rows, "%s claims no row" % name)
                expected = sorted(_registry.command_name(row.operation_id)
                                  for row in rows)
                self.assertEqual(sorted(group.commands), expected)
                for command in group.commands:
                    operation_id = command.replace("-", ".")
                    self.assertIn(operation_id, OPERATIONS)

    def test_registration_is_idempotent_on_a_real_root_group(self):
        from cli_anything.gohighlevel import commands
        from cli_anything.gohighlevel.commands import apply_families

        # The register set is process-global by design. This test empties it to
        # observe a first registration, then restores it: leaving it populated
        # would make the later import of the root CLI a no-op and hide the
        # families from every other test in this process.
        saved = set(commands._REGISTERED)
        commands._REGISTERED.clear()
        try:
            first = apply_families(click.Group())
            second = apply_families(click.Group())
        finally:
            commands._REGISTERED.clear()
            commands._REGISTERED.update(saved)
        self.assertEqual(sorted(first["applied"]), sorted(_DELIVERED))
        self.assertEqual(second["applied"], [])

    def test_meeting_rooms_is_pending_with_owner_and_the_filed_change_request(self):
        _, pending = discover()
        entry = pending["meeting_rooms"]
        self.assertEqual(entry["owner"], "WF26")
        self.assertIn("no meeting_rooms", entry["reason"])
        self.assertIn("change-requests/2.md", entry["reason"])
        self.assertEqual(FAMILIES["meeting_rooms"], "WF26")

class FamilyRouteDisciplineTest(unittest.TestCase):
    def setUp(self):
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        self.cli = cli
        self.runner = CliRunner()
        self._saved_env = {k: os.environ.get(k) for k in
                           ("GHL_LOCATION_ID", "CAF_DRY_RUN")}
        os.environ.pop("CAF_DRY_RUN", None)

    def tearDown(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_public_row_dry_run_plans_the_frozen_contract_and_sends_nothing(self):
        built: list = []
        real = _registry._adapter
        _registry._adapter = lambda location_id: built.append(location_id)
        try:
            result = self.runner.invoke(
                self.cli,
                ["--dry-run", "--json", "courses", "courses-products-create"],
            )
        finally:
            _registry._adapter = real
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(built, [], "dry-run must not build an adapter")
        payload = __import__("json").loads(result.output)
        row = OPERATIONS["courses.products.create"]
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["operation_id"], "courses.products.create")
        self.assertEqual(payload["method"], row.method)
        self.assertEqual(payload["path_template"], row.path_template)
        self.assertEqual(payload["version"], row.version)
        self.assertTrue(payload["write"])

    def test_non_public_row_refuses_with_its_route_class_and_never_builds(self):
        built: list = []
        real = _registry._adapter
        _registry._adapter = lambda location_id: built.append(location_id)
        try:
            result = self.runner.invoke(
                self.cli,
                ["--location-id", "loc_synthetic_wf03", "knowledge_bases",
                 "knowledge_bases-files-upload"],
            )
        finally:
            _registry._adapter = real
        row = OPERATIONS["knowledge_bases.files.upload"]
        self.assertEqual(row.route_class, "capability_gap")
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("not a public operation", result.output)
        self.assertIn("capability_gap", result.output)
        self.assertIn(row.blocker, result.output)
        self.assertEqual(built, [], "a non-public row must not build an adapter")

    def test_public_row_routes_before_any_token(self):
        """A public family command needs no Firebase token and no private client."""
        import cli_anything.gohighlevel.gohighlevel_cli as mod

        def _boom(*args, **kwargs):  # pragma: no cover - asserted never called
            raise AssertionError("a private client was built on a public path")

        saved = mod._get_internal_client
        mod._get_internal_client = _boom
        for var in ("GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN", "CAF_FIREBASE_REFRESH_TOKEN",
                    "GHL_FIREBASE_REFRESH_TOKEN", "GOHIGHLEVEL_FIREBASE_TOKEN",
                    "GHL_FIREBASE_TOKEN"):
            os.environ.pop(var, None)
        try:
            result = self.runner.invoke(
                self.cli,
                ["--dry-run", "--json", "--location-id", "loc_synthetic_wf03",
                 "voice_ai", "voice-agents-create"],
            )
        finally:
            mod._get_internal_client = saved
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("voice.agents.create", result.output)

class CapabilitiesFamilyTest(unittest.TestCase):
    def setUp(self):
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        self.runner = CliRunner()
        self.cli = cli

    def test_catalog_lists_every_frozen_row(self):
        result = self.runner.invoke(self.cli, ["--json", "capabilities", "catalog"])
        self.assertEqual(result.exit_code, 0, result.output)
        payload = __import__("json").loads(result.output)
        self.assertEqual(payload["rows"], len(OPERATIONS))
        self.assertEqual(sorted(payload["operations"]), sorted(OPERATIONS))

    def test_show_refuses_an_unknown_row_instead_of_inventing_one(self):
        result = self.runner.invoke(
            self.cli, ["capabilities", "show", "meeting_rooms.create"]
        )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("no row", result.output)

    def test_gate_is_default_deny_with_a_named_reason(self):
        result = self.runner.invoke(
            self.cli,
            ["--json", "--location-id", "loc_synthetic_wf03",
             "capabilities", "gate", "voice.agents.create"],
        )
        payload = __import__("json").loads(result.output)
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertFalse(payload["enabled"])
        self.assertTrue(payload["blocked_reason"])

if __name__ == "__main__":
    unittest.main()
