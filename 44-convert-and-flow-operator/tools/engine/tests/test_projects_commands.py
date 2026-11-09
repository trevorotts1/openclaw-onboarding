"""Projects command module (WF32) -- registration and offline failure modes.

No live host, no credentials, no real catalog.  WF03 registers the group; these
tests prove the module is registrable and that it fails closed without a
discovery document.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

import click
from click.testing import CliRunner

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from cli_anything.gohighlevel.public import projects as pj  # noqa: E402
from cli_anything.gohighlevel.public import projects_commands as pc  # noqa: E402


def root_group() -> click.Group:
    @click.group()
    def root():
        pass

    return pc.register(root)


class RegistrationTests(unittest.TestCase):
    def test_register_adds_projects_group(self):
        root = root_group()
        self.assertIn("projects", root.commands)
        names = set(root.commands["projects"].commands)
        for expected in (
            "availability",
            "space-create",
            "space-list",
            "list-create",
            "statuses",
            "task-create",
            "subtask-create",
            "task-list",
            "add-task-to-list",
            "comment-add",
            "recurrence-set",
            "members",
            "member-remove",
            "list-delete",
            "space-delete",
        ):
            self.assertIn(expected, names)


class AvailabilityCommandTests(unittest.TestCase):
    def test_reports_both_dimensions_independently(self):
        result = CliRunner().invoke(
            root_group(),
            [
                "projects",
                "availability",
                "--ui-state", "available",
                "--ui-source", "labs_capture",
                "--api-state", "unknown",
                "--api-source", "api_probe_not_run",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["ui_labs"]["state"], "available")
        self.assertEqual(payload["api_beta"]["state"], "unknown")
        self.assertTrue(payload["independent"])

    def test_requiring_api_beta_exits_3(self):
        result = CliRunner().invoke(
            root_group(),
            ["projects", "availability", "--ui-state", "available", "--require", "api"],
        )
        self.assertEqual(result.exit_code, 3, result.output)
        self.assertIn("projects_feature_unavailable", result.output)


class FailClosedTests(unittest.TestCase):
    def test_service_command_without_catalog_exits_2(self):
        result = CliRunner().invoke(root_group(), ["projects", "space-list"])
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("refusing to invent endpoints", result.output)

    def test_fixture_catalog_refused_without_flag(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"evidence": "fixture", "operations": {}}, handle)
            path = handle.name
        try:
            result = CliRunner().invoke(
                root_group(), ["projects", "--catalog", path, "space-list"]
            )
        finally:
            os.unlink(path)
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("fixture catalog refused", result.output)

    def test_incomplete_fixture_with_opt_in_exits_3(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"evidence": "fixture", "operations": {"x.y": {}}}, handle)
            path = handle.name
        try:
            result = CliRunner().invoke(
                root_group(),
                ["projects", "--catalog", path, "--allow-fixture", "space-list"],
            )
        finally:
            os.unlink(path)
        self.assertEqual(result.exit_code, 3, result.output)
        self.assertIn("projects_discovery_incomplete", result.output)


class ServiceFactoryTests(unittest.TestCase):
    def tearDown(self):
        pc.set_service_factory(None)

    def test_injected_service_marks_fixture_output(self):
        class StubService:
            fixture = True

            def list_spaces(self, **_kwargs):
                return pj.Page(
                    operation_id=pj.SPACE_LIST,
                    records=({"id": "s1"},),
                    pages=1,
                    tokens=(),
                )

        pc.set_service_factory(lambda **_kwargs: StubService())
        result = CliRunner().invoke(root_group(), ["projects", "space-list"])
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertTrue(payload["fixture"])
        self.assertEqual(payload["records"], [{"id": "s1"}])


if __name__ == "__main__":
    unittest.main()
