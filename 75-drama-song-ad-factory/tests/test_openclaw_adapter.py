#!/usr/bin/env python3
"""W3-02-U6: openclaw_adapter.py is a pure passthrough.

Proves, behaviourally:
  * the adapter shells the shared entrypoint with an ARGUMENT ARRAY
    (shell metacharacters in an argument are data, never executed),
  * stdout and the exit code are relayed byte-for-byte and code-for-code,
  * a failed shared guard (error/rejected) is NOT bypassed, masked or
    rewritten by the adapter,
  * a missing entrypoint fails closed (exit 1, no fabricated envelope).

Run: python3 tests/test_openclaw_adapter.py   (also pytest-collectable).
stdlib only.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ADAPTER = SKILL / "scripts" / "openclaw_adapter.py"
FACTORY = SKILL / "scripts" / "core" / "intake_preflight" / "factory.py"

SCHEMA_VERSION = "blackceo.intake-preflight/envelope/v1"
RUN_ID = "w3-02-u6-run"  # fixed so adapter/direct runs are byte-comparable

COMPLETE_BRIEF = {
    "offer": "Drama-song factory adapter test offer",
    "audience": "busy parents",
    "action": "visit the link",
    "website": "example.com",  # I1: intake asks for the exact address otherwise
    "budget_minor": 100,
    "budget_currency": "USD",
    "placement": "vertical-feed",  # stated, else intake asks the placement question (exit 2)
}


def _run(target, args, cwd=None):
    return subprocess.run(
        [sys.executable, str(target)] + list(args),
        capture_output=True, text=True, cwd=cwd,
    )


def adapter(args, cwd=None):
    return _run(ADAPTER, args, cwd=cwd)


def direct(args, cwd=None):
    return _run(FACTORY, args, cwd=cwd)


class OpenclawAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dsa-u6-")
        self.work = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _brief_file(self, brief):
        p = self.work / "brief.json"
        p.write_text(json.dumps(brief), encoding="utf-8")
        return p

    def envelope(self, proc):
        self.assertTrue(proc.stdout.strip(), msg=proc.stderr)
        return json.loads(proc.stdout)

    def test_ok_envelope_relayed_byte_for_byte(self):
        args = ["intake", "--run-id", RUN_ID,
                "--brief-file", str(self._brief_file(COMPLETE_BRIEF))]
        a, d = adapter(args), direct(args)
        self.assertEqual(a.returncode, 0)
        self.assertEqual(a.returncode, d.returncode)
        self.assertEqual(a.stdout, d.stdout)
        env = self.envelope(a)
        self.assertEqual(env["schema_version"], SCHEMA_VERSION)
        self.assertEqual(env["command"], "intake")
        self.assertEqual(env["outcome"], "ok")
        self.assertEqual(env["reason_code"], "complete-brief-zero-questions")

    def test_failed_guard_error_not_bypassed(self):
        # tool-unavailable -> outcome error, exit 1 (core EXIT map).
        args = ["preflight", "--run-id", RUN_ID, "--root", str(self.work),
                "--require-tool", "dsa-u6-tool-that-does-not-exist"]
        a, d = adapter(args), direct(args)
        self.assertEqual(d.returncode, 1)
        self.assertEqual(a.returncode, d.returncode)
        self.assertNotEqual(a.returncode, 0)
        self.assertEqual(a.stdout, d.stdout)
        env = self.envelope(a)
        self.assertEqual(env["outcome"], "error")
        self.assertEqual(env["reason_code"], "tool-unavailable")

    def test_rejected_guard_not_bypassed(self):
        # unknown delivery profile -> outcome rejected, exit 4.
        args = ["preflight", "--run-id", RUN_ID, "--root", str(self.work),
                "--profile", "bogus-profile-w3-02-u6"]
        a, d = adapter(args), direct(args)
        self.assertEqual(d.returncode, 4)
        self.assertEqual(a.returncode, d.returncode)
        self.assertEqual(a.stdout, d.stdout)
        env = self.envelope(a)
        self.assertEqual(env["outcome"], "rejected")
        self.assertEqual(env["reason_code"], "delivery-profile-unknown")

    def test_argument_array_never_a_shell(self):
        marker = self.work / "shell-was-used"
        hostile = "x; touch %s $(touch %s) `touch %s`" % (
            marker, marker, marker)
        brief = dict(COMPLETE_BRIEF, offer=hostile)
        args = ["intake", "--run-id", RUN_ID, "--brief", json.dumps(brief)]
        a, d = adapter(args, cwd=str(self.work)), direct(args, cwd=str(self.work))
        self.assertFalse(marker.exists(),
                         msg="adapter executed an argument through a shell")
        self.assertEqual(a.returncode, d.returncode)
        self.assertEqual(a.stdout, d.stdout)
        env = self.envelope(a)
        self.assertEqual(env["outcome"], "ok")
        # hostile text stayed data: it is echoed in the summary offer.
        self.assertEqual(env["data"]["summary"]["offer"], hostile)

    def test_missing_entrypoint_fails_closed(self):
        lone = self.work / "scripts"
        lone.mkdir()
        shutil.copy(ADAPTER, lone / "openclaw_adapter.py")
        proc = subprocess.run(
            [sys.executable, str(lone / "openclaw_adapter.py"), "intake"],
            capture_output=True, text=True, cwd=str(self.work),
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "", msg="no fabricated success envelope")
        self.assertIn("entrypoint missing", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
