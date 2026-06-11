"""Proof harness for the safety gate — U1-engine-debrand FIX 4.

Verifies that BOTH dry-run interfaces (--dry-run flag and CAF_DRY_RUN env var)
are inert: they print [DRY RUN] and never open a socket to *.leadconnectorhq.com.

Run with:
    python -m pytest tests/test_safety_gate.py -v

Or standalone:
    python tests/test_safety_gate.py

PASS = Safety gate is working. FAIL (non-zero) = live CRM write was attempted.
"""
from __future__ import annotations

import importlib
import os
import socket
import sys
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock

# Ensure the engine root (1 level up from this file) is on sys.path
# so `cli_anything` can be imported regardless of CWD.
_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)


# ---------------------------------------------------------------------------
# Network guard — any connect to leadconnectorhq.com is a hard FAIL
# ---------------------------------------------------------------------------

_BLOCKED_HOST = "leadconnectorhq.com"
_original_connect = socket.socket.connect


def _guarded_connect(self, address):
    if isinstance(address, tuple):
        host = address[0]
        if _BLOCKED_HOST in str(host):
            raise AssertionError(
                f"SAFETY GATE FAILURE: attempt to connect to live CRM host {host!r}. "
                "DRY RUN did not intercept the write."
            )
    return _original_connect(self, address)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_safety_gate():
    """Re-import safety_gate so module-level state is reset between tests."""
    mod_name = "cli_anything.gohighlevel.utils.safety_gate"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDryRunFlagPath(unittest.TestCase):
    """--dry-run flag sets CAF_DRY_RUN AFTER import; gate must still intercept."""

    def setUp(self):
        # Simulate what the CLI callback does: set env AFTER module would have loaded
        os.environ.pop("CAF_DRY_RUN", None)
        self.sg = _fresh_safety_gate()
        # Now set the env var (simulates click callback ordering)
        os.environ["CAF_DRY_RUN"] = "true"
        # Install network guard
        socket.socket.connect = _guarded_connect

    def tearDown(self):
        os.environ.pop("CAF_DRY_RUN", None)
        socket.socket.connect = _original_connect

    def test_dry_run_flag_prints_dry_run_and_exits(self):
        """check_write must exit(0) and print [DRY RUN] — never reach network."""
        captured = StringIO()
        with patch("sys.stdout", captured):
            with self.assertRaises(SystemExit) as cm:
                self.sg.check_write(
                    method="POST",
                    url="https://services.leadconnectorhq.com/contacts/",
                    payload={"email": "a@b.com"},
                    location_id="GOODLOC",
                )
        self.assertEqual(cm.exception.code, 0, "DRY RUN must exit with code 0")
        output = captured.getvalue()
        self.assertIn("[DRY RUN]", output, "DRY RUN banner must be printed")

    def test_dry_run_flag_no_socket_connect(self):
        """No socket.connect call must be made in dry-run mode."""
        connect_calls = []

        def recording_guard(self_, address):
            if isinstance(address, tuple) and _BLOCKED_HOST in str(address[0]):
                connect_calls.append(address)
                raise AssertionError(f"Live CRM connect attempted: {address}")
            return _original_connect(self_, address)

        socket.socket.connect = recording_guard
        try:
            with patch("sys.stdout", StringIO()):
                try:
                    self.sg.check_write(
                        method="POST",
                        url="https://services.leadconnectorhq.com/contacts/",
                        payload={"email": "a@b.com"},
                        location_id="GOODLOC",
                    )
                except SystemExit:
                    pass
        finally:
            socket.socket.connect = _original_connect

        self.assertEqual(connect_calls, [], "No CRM socket connect must occur in DRY RUN")


class TestDryRunEnvPath(unittest.TestCase):
    """CAF_DRY_RUN=true set before import; gate must intercept."""

    def setUp(self):
        os.environ["CAF_DRY_RUN"] = "true"
        self.sg = _fresh_safety_gate()
        socket.socket.connect = _guarded_connect

    def tearDown(self):
        os.environ.pop("CAF_DRY_RUN", None)
        socket.socket.connect = _original_connect

    def test_env_var_dry_run_prints_and_exits(self):
        """CAF_DRY_RUN=true env path must print [DRY RUN] and exit(0)."""
        captured = StringIO()
        with patch("sys.stdout", captured):
            with self.assertRaises(SystemExit) as cm:
                self.sg.check_write(
                    method="POST",
                    url="https://services.leadconnectorhq.com/contacts/",
                    payload={"email": "a@b.com"},
                    location_id="GOODLOC",
                )
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("[DRY RUN]", captured.getvalue())


class TestWhitelistFailClosed(unittest.TestCase):
    """Empty whitelist must refuse all writes — even without dry-run."""

    def setUp(self):
        os.environ.pop("CAF_DRY_RUN", None)
        os.environ.pop("CAF_ALLOWED_LOCATION_IDS", None)
        os.environ.pop("CAF_APPROVAL_TOKEN", None)
        self.sg = _fresh_safety_gate()
        socket.socket.connect = _guarded_connect

    def tearDown(self):
        os.environ.pop("CAF_DRY_RUN", None)
        os.environ.pop("CAF_ALLOWED_LOCATION_IDS", None)
        os.environ.pop("CAF_APPROVAL_TOKEN", None)
        socket.socket.connect = _original_connect

    def test_empty_whitelist_raises_safety_refused(self):
        with self.assertRaises(self.sg.SafetyRefused):
            self.sg.check_write(
                method="POST",
                url="https://services.leadconnectorhq.com/contacts/",
                payload={},
                location_id="ANY_LOC",
            )


class TestWhitelistEnforced(unittest.TestCase):
    """Unlisted location must be refused."""

    def setUp(self):
        os.environ.pop("CAF_DRY_RUN", None)
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "ALLOWED_LOC"
        os.environ.pop("CAF_APPROVAL_TOKEN", None)
        self.sg = _fresh_safety_gate()
        socket.socket.connect = _guarded_connect

    def tearDown(self):
        os.environ.pop("CAF_DRY_RUN", None)
        os.environ.pop("CAF_ALLOWED_LOCATION_IDS", None)
        os.environ.pop("CAF_APPROVAL_TOKEN", None)
        socket.socket.connect = _original_connect

    def test_unlisted_location_refused(self):
        with self.assertRaises(self.sg.SafetyRefused):
            self.sg.check_write(
                method="POST",
                url="https://services.leadconnectorhq.com/contacts/",
                payload={},
                location_id="WRONG_LOC",
            )

    def test_listed_location_with_approval_passes(self):
        os.environ["CAF_APPROVAL_TOKEN"] = "test-token"
        # Should raise SafetyRefused only when location is not in list
        # With correct location and token, no exception should be raised
        try:
            self.sg.check_write(
                method="POST",
                url="https://services.leadconnectorhq.com/contacts/",
                payload={},
                location_id="ALLOWED_LOC",
            )
        except self.sg.SafetyRefused:
            self.fail("SafetyRefused raised for whitelisted location with approval token")
        finally:
            os.environ.pop("CAF_APPROVAL_TOKEN", None)


class TestZHCStandingApproval(unittest.TestCase):
    """ZHC-prefixed workflow names must pass approval without a token."""

    def setUp(self):
        os.environ.pop("CAF_DRY_RUN", None)
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "ZHC_LOC"
        os.environ.pop("CAF_APPROVAL_TOKEN", None)
        self.sg = _fresh_safety_gate()
        socket.socket.connect = _guarded_connect

    def tearDown(self):
        os.environ.pop("CAF_DRY_RUN", None)
        os.environ.pop("CAF_ALLOWED_LOCATION_IDS", None)
        socket.socket.connect = _original_connect

    def test_zhc_prefix_passes(self):
        try:
            self.sg.check_write(
                method="POST",
                url="https://services.leadconnectorhq.com/contacts/",
                payload={},
                location_id="ZHC_LOC",
                workflow_name="ZHC-onboarding",
            )
        except self.sg.SafetyRefused:
            self.fail("ZHC-prefixed workflow_name must receive standing approval")

    def test_empty_workflow_name_refused_without_token(self):
        with self.assertRaises(self.sg.SafetyRefused):
            self.sg.check_write(
                method="POST",
                url="https://services.leadconnectorhq.com/contacts/",
                payload={},
                location_id="ZHC_LOC",
                workflow_name="",
            )


class TestDraftOnlyFlag(unittest.TestCase):
    """draft_only_active_flag() must respect CAF_DRAFT_ONLY at call time."""

    def setUp(self):
        os.environ.pop("CAF_DRAFT_ONLY", None)
        self.sg = _fresh_safety_gate()

    def tearDown(self):
        os.environ.pop("CAF_DRAFT_ONLY", None)

    def test_default_is_draft_only(self):
        """No env var: default is True → active flag returns False."""
        self.assertFalse(self.sg.draft_only_active_flag())

    def test_explicit_true_returns_inactive(self):
        os.environ["CAF_DRAFT_ONLY"] = "true"
        self.assertFalse(self.sg.draft_only_active_flag())

    def test_false_returns_active(self):
        os.environ["CAF_DRAFT_ONLY"] = "false"
        self.assertTrue(self.sg.draft_only_active_flag())


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestDryRunFlagPath,
        TestDryRunEnvPath,
        TestWhitelistFailClosed,
        TestWhitelistEnforced,
        TestZHCStandingApproval,
        TestDraftOnlyFlag,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
