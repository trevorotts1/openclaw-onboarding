#!/usr/bin/env python3
"""Wiring proof for T-39: `pb_contracts.load_ledger` reaches `compat_guard`.

`compat_guard.py`'s own suite (test_compat_guard.py) proves what the guard
refuses. It cannot prove the guard is *reachable from production*, and a
module nobody calls is the defect T-39 exists to close. This file proves the
call site in `38-conversational-ai-system/tools/pb_contracts.py`:

  * `load_ledger` invokes `compat_guard.assert_compatible` with this build's
    LEDGER_VERSION (a spy: delete the call and this test fails);
  * a ledger written by a NEWER build is refused, and the refusal is CAUSED by
    `compat_guard.NewerThanKnownError` — the `__cause__` chain is the
    discriminator, because the file's pre-wiring branch also raised UsageError
    but with no cause at all;
  * the refusal keeps `pb_contracts`' own exception contract: callers see
    `UsageError`, never a `compat_guard.CompatError` leaking through;
  * controls: a current-version ledger is returned unchanged and a version 1
    ledger still migrates, so the guard is not simply blocking everything;
  * the direct-script path (`python3 -I pb_contracts.py ...`) still resolves
    the sibling module, i.e. the `sys.path` shim is load-bearing on Python
    3.11+ where `-I` implies `-P`.

Run: python3 tools/tests/test_compat_guard_wiring.py
     python3 -m unittest discover -s tools/tests -t tools/tests -p 'test_*.py'
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import compat_guard  # noqa: E402
import pb_contracts  # noqa: E402


class _Ledger(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="t39-wiring-")
        self.dir = Path(self._td.name)
        self.path = self.dir / "ledger.json"

    def tearDown(self):
        self._td.cleanup()

    def write(self, ledger):
        self.path.write_text(json.dumps(ledger), encoding="utf-8")
        return self.path


class TestCallSiteReached(_Ledger):
    def test_load_ledger_calls_assert_compatible_with_known_version(self):
        """The spy: remove the call from load_ledger and this fails."""
        self.write({"version": 2, "actions": {}})
        with mock.patch.object(
            pb_contracts.compat_guard, "assert_compatible", return_value=None
        ) as spy:
            ledger = pb_contracts.load_ledger(str(self.path))
        self.assertEqual(spy.call_count, 1, "load_ledger must call the guard exactly once")
        args, kwargs = spy.call_args
        self.assertEqual(kwargs.get("known_version"), pb_contracts.LEDGER_VERSION)
        self.assertEqual(args[0]["version"], 2, "the guard must see the parsed ledger")
        self.assertEqual(ledger["version"], 2, "the control: a current ledger still loads")

    def test_newer_ledger_refusal_is_caused_by_the_guard(self):
        """Delete the call and __cause__ becomes None: this discriminates."""
        self.write({"version": pb_contracts.LEDGER_VERSION + 1, "actions": {}})
        with self.assertRaises(pb_contracts.UsageError) as ctx:
            pb_contracts.load_ledger(str(self.path))
        cause = ctx.exception.__cause__
        self.assertIsNotNone(cause, "the refusal must be caused by compat_guard, not the legacy branch")
        self.assertIsInstance(cause, compat_guard.NewerThanKnownError)
        self.assertEqual(cause.on_disk, pb_contracts.LEDGER_VERSION + 1)
        self.assertEqual(cause.known, pb_contracts.LEDGER_VERSION)
        self.assertIn("is version %d" % (pb_contracts.LEDGER_VERSION + 1), str(ctx.exception))

    def test_refusal_keeps_the_files_own_exception_contract(self):
        self.write({"version": 9, "actions": {}})
        with self.assertRaises(pb_contracts.UsageError) as ctx:
            pb_contracts.load_ledger(str(self.path))
        self.assertNotIsInstance(
            ctx.exception,
            compat_guard.CompatError,
            "a compat_guard refusal must be wrapped, never raised through",
        )


class TestControls(_Ledger):
    def test_current_version_ledger_is_returned_unchanged(self):
        self.write({"version": pb_contracts.LEDGER_VERSION, "actions": {"k": {"n": 1}}})
        ledger = pb_contracts.load_ledger(str(self.path))
        self.assertEqual(ledger["version"], pb_contracts.LEDGER_VERSION)
        self.assertEqual(ledger["actions"], {"k": {"n": 1}})
        self.assertEqual(ledger["legacy_actions"], {})

    def test_older_ledger_still_migrates(self):
        """The guard must not block an OLDER record: migration still happens."""
        self.write({"version": 1, "actions": {"old::key": {"n": 1}}})
        ledger = pb_contracts.load_ledger(str(self.path))
        self.assertEqual(ledger["version"], pb_contracts.LEDGER_VERSION)
        self.assertEqual(ledger["actions"], {})
        self.assertEqual(ledger["legacy_actions"], {"old::key": {"n": 1}})

    def test_absent_ledger_is_still_defaulted(self):
        ledger = pb_contracts.load_ledger(str(self.dir / "missing.json"))
        self.assertEqual(ledger["version"], pb_contracts.LEDGER_VERSION)


class TestNonIntegerVersion(_Ledger):
    """The guard's `version` must be an int. Loose `==` used to let these pass."""

    def test_boolean_version_is_refused_not_read_as_version_1(self):
        self.write({"version": True, "actions": {"k": {"n": 1}}})
        with self.assertRaises(pb_contracts.UsageError) as ctx:
            pb_contracts.load_ledger(str(self.path))
        self.assertIsInstance(ctx.exception.__cause__, compat_guard.CorruptRecordError)

    def test_float_version_is_refused(self):
        for value in (1.0, 2.0):
            with self.subTest(version=value):
                self.write({"version": value, "actions": {}})
                with self.assertRaises(pb_contracts.UsageError):
                    pb_contracts.load_ledger(str(self.path))


class TestDirectScriptPath(_Ledger):
    def test_isolated_script_execution_still_resolves_the_sibling(self):
        """`python3 -I pb_contracts.py` must find compat_guard (3.11+ strips cwd)."""
        self.write({"version": 9, "actions": {}})
        proc = subprocess.run(
            [
                sys.executable, "-I", str(TOOLS_DIR / "pb_contracts.py"),
                "receipt", "--ledger", str(self.path),
                "--key", "k", "--status", "sent",
            ],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("is version 9", proc.stdout)
        self.assertNotIn("ModuleNotFoundError", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
