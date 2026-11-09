"""WF03 CLI integration: route-before-token, lazy private client, registration.

Every test is offline. ``FakeV4`` records the adapter calls the CLI makes and
replays scripted results; ``_get_internal_client`` is patched so any private
client construction on a public path is a hard failure.

Acceptance ids covered here:
  A01           -- public workflow path runs with Firebase absent
  A06           -- a published workflow is never silently set to draft; a stale
                   revision is never replayed (the fresh read supplies it)
  IG-ROUTE-06   -- the route is chosen before a token; --experimental is
                   route-aware; --dry-run makes no mutating call; each delivered
                   family command module registers exactly once

Run:
    PYTHONPATH="$PWD" python3 -m pytest -q tests/test_wf03_cli_routing.py
"""
from __future__ import annotations

import copy
import json
import os
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

from cli_anything.gohighlevel.public.result import Status  # noqa: E402

LOC = "loc_synthetic_wf03"

_FIREBASE_VARS = (
    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
    "CAF_FIREBASE_REFRESH_TOKEN",
    "GHL_FIREBASE_REFRESH_TOKEN",
    "GOHIGHLEVEL_FIREBASE_TOKEN",
    "GHL_FIREBASE_TOKEN",
)


class _Result:
    """Minimal OperationResult stand-in with the frozen ``status``/``receipt``."""

    def __init__(self, status=Status.ok, receipt_id="gxo_res_wf03001", error=None,
                 evidence=None):
        self.status = status
        self.receipt_id = receipt_id
        self.error = error
        self.evidence = evidence or {}


class _Cap:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.activation_blocked = None if enabled else object()


class FakeV4:
    """Records every adapter call; capability is scripted per test."""

    def __init__(self, *, enabled=True, definition=None, status_value="published",
                 update_status=Status.ok):
        self.enabled = enabled
        self.definition = definition if definition is not None else {
            "version": "rev-7",
            "actions": [
                {"id": "step-1", "name": "Welcome",
                 "attributes": {"subject": "Hello", "body": "<p>Hello there friend</p>"}},
            ],
            "triggers": [{"id": "trig-1", "type": "contact_tag"}],
        }
        self.status_value = status_value
        self.update_status = update_status
        self.calls: list[tuple] = []

    def capability(self, operation, *, tenant=None):
        self.calls.append(("capability", operation, tenant))
        return _Cap(self.enabled)

    def read_definition_document(self, *, tenant, workflow_id, attempt=1):
        self.calls.append(("read_definition_document", workflow_id))
        return _Result(Status.ok), {"definition": copy.deepcopy(self.definition)}

    def read_status(self, *, tenant, workflow_id, attempt=1):
        self.calls.append(("read_status", workflow_id))
        return _Result(Status.ok, evidence={"workflow_v4": {"status": self.status_value}})

    def update_definition(self, **kwargs):
        self.calls.append(("update_definition", kwargs))
        return _Result(self.update_status)

    def set_status(self, **kwargs):
        self.calls.append(("set_status", kwargs))
        return _Result(Status.ok)

    def create_workflow(self, **kwargs):
        self.calls.append(("create_workflow", kwargs))
        return _Result(Status.ok)

    def names(self):
        return [call[0] for call in self.calls]


class _Base(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in self._env_keys()}
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["GHL_LOCATION_ID"] = LOC
        os.environ["GHL_API_KEY"] = "synthetic-pit"
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = LOC
        os.environ["CAF_APPROVAL_TOKEN"] = "synthetic-approval"
        os.environ["CAF_DATA_DIR"] = self._tmp.name
        os.environ.pop("CAF_DRY_RUN", None)
        for var in _FIREBASE_VARS:
            os.environ.pop(var, None)

    def tearDown(self):
        for var in _FIREBASE_VARS:
            os.environ.pop(var, None)
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    @staticmethod
    def _env_keys():
        return ("GHL_LOCATION_ID", "GHL_API_KEY", "CAF_ALLOWED_LOCATION_IDS",
                "CAF_APPROVAL_TOKEN", "CAF_DATA_DIR", "CAF_DRY_RUN")

    def _run(self, args, fake, *, private_calls=None):
        """Invoke the CLI with the public adapter faked and private use trapped."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel import gohighlevel_cli as cli_mod

        build_private = private_calls if private_calls is not None else []
        original = cli_mod._get_internal_client

        def _trap(*a, **kw):
            build_private.append(a)
            return original(*a, **kw)

        with patch(
            "cli_anything.gohighlevel.utils.workflow_builder.load_public_v4",
            return_value=(fake, "synthetic fake adapter; gate scripted by the test"),
        ), patch.object(cli_mod, "_get_internal_client", side_effect=_trap):
            result = CliRunner().invoke(cli_mod.cli, args)
        return result, build_private

    def _write_json(self, payload):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", dir=self._tmp.name, delete=False
        )
        with handle as fh:
            json.dump(payload, fh)
        return handle.name


class A01PublicPathWithoutFirebase(_Base):
    """A01 (CLI side): the public path never needs a Firebase token."""

    def test_a01_public_get_needs_no_private_client(self):
        fake = FakeV4()
        result, private_calls = self._run(
            ["--json", "workflows", "get", "--workflow-id", "wf-1"], fake
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(private_calls, [], "_get_internal_client was built on a public read")
        self.assertIn("read_definition_document", fake.names())

    def test_a01_public_status_read_uses_public_adapter(self):
        fake = FakeV4(status_value="published")
        result, private_calls = self._run(
            ["--json", "workflows", "status", "--workflow-id", "wf-1"], fake
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(private_calls, [])
        payload = json.loads(result.output)
        self.assertEqual(payload["status"], "published")
        self.assertEqual(payload["route"], "public_v4")

    def test_a01_public_update_reaches_adapter_without_private_client(self):
        fake = FakeV4()
        path = self._write_json(dict(fake.definition))
        result, private_calls = self._run(
            ["--json", "workflows", "update", "--workflow-id", "wf-1",
             "--from-json", path],
            fake,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(private_calls, [])
        self.assertIn("update_definition", fake.names())

    def test_a01_public_publish_does_not_require_experimental(self):
        fake = FakeV4()
        result, private_calls = self._run(
            ["--json", "workflows", "publish", "--workflow-id", "wf-1"], fake
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(private_calls, [])
        call = next(c for c in fake.calls if c[0] == "set_status")[1]
        self.assertEqual(call["status"], "published")

    def test_a01_public_get_leaves_firebase_env_absent(self):
        fake = FakeV4()
        result, _ = self._run(["--json", "workflows", "get", "--workflow-id", "wf-1"], fake)
        self.assertEqual(result.exit_code, 0, result.output)
        for var in _FIREBASE_VARS:
            self.assertFalse(os.environ.get(var), "test must run with Firebase unset")


class A06NoSilentDraftOrStaleRevision(_Base):
    """A06 (CLI side): publish is explicit; update carries the fresh revision."""

    def test_a06_update_passes_the_freshly_read_revision(self):
        fake = FakeV4()
        path = self._write_json(dict(fake.definition))
        result, _ = self._run(
            ["--json", "workflows", "update", "--workflow-id", "wf-1",
             "--from-json", path],
            fake,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        call = next(c for c in fake.calls if c[0] == "update_definition")[1]
        self.assertEqual(call["expected_revision"], "rev-7")
        self.assertIs(call["allow_deletions"], False)

    def test_a06_publish_never_sends_draft(self):
        fake = FakeV4()
        result, _ = self._run(["workflows", "publish", "--workflow-id", "wf-1"], fake)
        self.assertEqual(result.exit_code, 0, result.output)
        statuses = [c[1]["status"] for c in fake.calls if c[0] == "set_status"]
        self.assertEqual(statuses, ["published"])
        self.assertNotIn("draft", statuses)

    def test_a06_unpublish_is_the_only_draft_path(self):
        fake = FakeV4()
        result, _ = self._run(["workflows", "unpublish", "--workflow-id", "wf-1"], fake)
        self.assertEqual(result.exit_code, 0, result.output)
        statuses = [c[1]["status"] for c in fake.calls if c[0] == "set_status"]
        self.assertEqual(statuses, ["draft"])

    def test_a06_update_refuses_when_current_definition_is_unreadable(self):
        class _Unreadable(FakeV4):
            def read_definition_document(self, *, tenant, workflow_id, attempt=1):
                self.calls.append(("read_definition_document", workflow_id))
                return _Result(Status.blocked, error="no definition"), None

        fake = _Unreadable()
        path = self._write_json({"version": "rev-7", "actions": []})
        result, _ = self._run(
            ["workflows", "update", "--workflow-id", "wf-1", "--from-json", path], fake
        )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertNotIn("update_definition", fake.names())


class IGRoute06RouteBeforeToken(_Base):
    """IG-ROUTE-06: private routes keep the gate and build the client only after it."""

    def test_ig_route_06_private_update_requires_experimental(self):
        fake = FakeV4(enabled=False)
        path = self._write_json({"version": "rev-7", "actions": []})
        private_calls: list = []
        result, _ = self._run(
            ["workflows", "update", "--workflow-id", "wf-1", "--from-json", path],
            fake, private_calls=private_calls,
        )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("--experimental", result.output)
        self.assertEqual(private_calls, [], "client built before the route gate fired")
        self.assertNotIn("update_definition", fake.names())

    def test_ig_route_06_private_route_builds_client_only_after_gate(self):
        fake = FakeV4(enabled=False)
        path = self._write_json({"version": "rev-7", "actions": []})
        private_calls: list = []
        result, _ = self._run(
            ["--experimental", "workflows", "update", "--workflow-id", "wf-1",
             "--from-json", path],
            fake, private_calls=private_calls,
        )
        # With --experimental the gate passes and the client is finally needed.
        self.assertEqual(len(private_calls), 1, result.output)
        self.assertNotIn("update_definition", fake.names())

    def test_ig_route_06_legacy_experimental_flag_still_works_on_public(self):
        fake = FakeV4()
        result, _ = self._run(
            ["--experimental", "--json", "workflows", "get", "--workflow-id", "wf-1"],
            fake,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("read_definition_document", fake.names())

    def test_ig_route_06_public_publish_is_not_mutating_under_dry_run(self):
        fake = FakeV4()
        result, _ = self._run(
            ["--dry-run", "--json", "workflows", "publish", "--workflow-id", "wf-1"],
            fake,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        # The local capability read is a gate lookup, not a call; nothing writes.
        self.assertEqual(
            [c for c in fake.names() if c != "capability"], [],
            "dry-run must not call a mutating adapter method",
        )
        payload = json.loads(result.output)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["body"], {"status": "published"})

    def test_ig_route_06_public_update_is_not_mutating_under_dry_run(self):
        fake = FakeV4()
        path = self._write_json(dict(fake.definition))
        result, _ = self._run(
            ["--dry-run", "--json", "workflows", "update", "--workflow-id", "wf-1",
             "--from-json", path],
            fake,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertNotIn("update_definition", fake.names())

    def test_ig_route_06_private_status_change_refuses_without_substitute(self):
        fake = FakeV4(enabled=False)
        result, _ = self._run(
            ["--experimental", "workflows", "publish", "--workflow-id", "wf-1"], fake
        )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("no private status rail", result.output)
        self.assertNotIn("set_status", fake.names())


class IGRegistrationAndAliases(_Base):
    """IG-ROUTE-06: each delivered family module registers exactly once."""

    def _fake_module(self, name, counter):
        module = types.ModuleType("cli_anything.gohighlevel.commands." + name)

        def register(cli):
            counter.append(name)

        module.register = register
        sys.modules[module.__name__] = module
        self.addCleanup(sys.modules.pop, module.__name__, None)
        return module

    def test_ig_route_06_family_registers_exactly_once(self):
        import click

        from cli_anything.gohighlevel import commands

        counter: list = []
        self._fake_module("projects", counter)
        # apply_families takes the ROOT CLICK GROUP (that is the contract), so
        # the throwaway roots here are real groups; the process register set is
        # restored afterwards so neighbouring tests see the import-time state.
        saved = set(commands._REGISTERED)
        commands._REGISTERED.discard("projects")
        try:
            first = commands.apply_families(click.Group())
            second = commands.apply_families(click.Group())
        finally:
            commands._REGISTERED.clear()
            commands._REGISTERED.update(saved)
        self.assertIn("projects", first["applied"])
        self.assertNotIn("projects", second["applied"])
        self.assertEqual(counter, ["projects"])

    def test_ig_route_06_undelivered_families_are_pending_not_stubs(self):
        from cli_anything.gohighlevel import commands

        delivered, pending = commands.discover()
        # WF00 (293a79b90) landed the frozen rows, so the courses family is a
        # real delivered module now. The family that still has NO frozen row is
        # the one that must be pending with its owner and a named reason.
        self.assertIn("courses", delivered)
        self.assertNotIn("courses", pending)
        self.assertIn("meeting_rooms", pending)
        self.assertEqual(pending["meeting_rooms"]["owner"], "WF26")
        self.assertIn("no meeting_rooms", pending["meeting_rooms"]["reason"])

    def test_ig_route_06_every_frozen_row_family_is_delivered(self):
        """Only a family with zero frozen rows may stay pending."""
        from cli_anything.gohighlevel import commands

        delivered, pending = commands.discover()
        self.assertEqual(sorted(delivered), sorted(set(commands.FAMILIES) - set(pending)))
        for name in delivered:
            module = delivered[name]
            self.assertTrue(callable(getattr(module, "register", None)), name)
        self.assertEqual(sorted(pending), ["meeting_rooms"])

    def test_ig_route_06_cli_exposes_the_three_console_aliases(self):
        import setuptools

        captured: dict = {}
        real_setup = setuptools.setup
        setuptools.setup = lambda **kwargs: captured.update(kwargs)
        try:
            runpy.run_path(os.path.join(_ENGINE_ROOT, "setup.py"), run_name="__main__")
        finally:
            setuptools.setup = real_setup
        scripts = [
            entry.split("=", 1)[0].strip()
            for entry in captured["entry_points"]["console_scripts"]
        ]
        self.assertEqual(sorted(scripts), ["caf", "convertandflow", "ghl"])


if __name__ == "__main__":
    unittest.main()
