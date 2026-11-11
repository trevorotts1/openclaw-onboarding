#!/usr/bin/env python3
"""Harmony issue 40: the pinned external authorities are checked in strict mode, and a drift fails.

Before: `verify.sh` ran `check_authority_pins.py || true`, so four of the seven pins had drifted
(the prompt-length authority both gates obey among them) and nothing went red. The pins file is now
re-stamped to the current blobs, `verify.sh` runs the check with --strict and no `|| true`, and this
test fails when either half is undone.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_authority_pins.py"
PINS = ROOT / "references" / "external-authorities.json"
VERIFY = ROOT / "verify.sh"


def verify_pin_block():
    """The exact authority-pin block of verify.sh: from its `if [ -f ...check_authority_pins.py` line to its `fi`."""
    lines = VERIFY.read_text(encoding="utf-8").splitlines()
    start = [i for i, l in enumerate(lines) if l.startswith("if [") and "check_authority_pins.py" in l]
    assert len(start) == 1, start
    end = next(i for i in range(start[0], len(lines)) if lines[i] == "fi")
    return "\n".join(lines[start[0]:end + 1])


def run_verify_pin_step(pin_path, pin_sha, file_present=True):
    """Run verify.sh's own pin step (verbatim, under its `set -u`) against a one-pin fixture and
    return (verify's exit code, its output). verify.sh exits on `$fail`, so this is that exit code."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "skill"
        (root / "scripts").mkdir(parents=True)
        (root / "references").mkdir()
        shutil.copy(SCRIPT, root / "scripts" / SCRIPT.name)
        target = Path(td) / "shared-utils" / "x.py"
        target.parent.mkdir()
        if file_present:
            target.write_text("print('a')\n", encoding="utf-8")
        (root / "references" / "external-authorities.json").write_text(json.dumps({"authorities": [{
            "name": "fixture", "repo": "fixture", "path": pin_path,
            "blob_sha": pin_sha, "checked_on": "2026-11-10"}]}), encoding="utf-8")
        harness = f'set -u\nROOT="$PIN_TEST_ROOT"\nfail=0\n{verify_pin_block()}\nexit $fail\n'
        proc = subprocess.run(["/bin/bash", "-c", harness], capture_output=True, text=True, cwd=td,
                              env={**os.environ, "PIN_TEST_ROOT": str(root)})
        return proc.returncode, proc.stdout + proc.stderr


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


class AuthorityPinsStrict(unittest.TestCase):
    def test_every_pin_matches_the_repo_in_strict_mode(self):
        proc = run("--strict")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("PIN DRIFT", proc.stdout)
        self.assertNotIn("PIN MISSING", proc.stdout)
        pins = json.loads(PINS.read_text(encoding="utf-8"))["authorities"]
        self.assertEqual(proc.stdout.count("PIN OK"), len(pins), proc.stdout)

    def test_verify_sh_runs_the_check_strict_and_never_swallows_its_exit_code(self):
        calls = [line for line in VERIFY.read_text(encoding="utf-8").splitlines()
                 if line.lstrip().startswith("python3") and "check_authority_pins.py" in line]
        self.assertEqual(len(calls), 1, calls)
        self.assertIn("--strict", calls[0])
        self.assertNotIn("|| true", calls[0])

    def test_a_drifted_pin_still_fails_strict(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            target = repo / "shared-utils" / "x.py"
            target.parent.mkdir(parents=True)
            target.write_text("print('a')\n", encoding="utf-8")
            pins = Path(td) / "pins.json"
            pins.write_text(json.dumps({"authorities": [{
                "name": "fixture", "repo": "fixture", "path": "shared-utils/x.py",
                "blob_sha": "0" * 40, "checked_on": "2026-11-10"}]}), encoding="utf-8")
            proc = run("--pins", pins, "--repo-root", repo, "--strict")
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("PIN DRIFT", proc.stdout)

    def test_a_missing_counterpart_fails_strict_and_only_warns_otherwise(self):
        with tempfile.TemporaryDirectory() as td:
            pins = Path(td) / "pins.json"
            pins.write_text(json.dumps({"authorities": [{
                "name": "fixture", "repo": "fixture", "path": "no/such/authority-file.py",
                "blob_sha": "0" * 40, "checked_on": "2026-11-10"}]}), encoding="utf-8")
            strict = run("--pins", pins, "--repo-root", td, "--strict")
            self.assertEqual(strict.returncode, 1, strict.stdout)
            self.assertIn("PIN MISSING", strict.stdout)
            self.assertIn("1 pinned authority problem", strict.stdout)
            self.assertEqual(run("--pins", pins, "--repo-root", td).returncode, 0)

    def test_verify_sh_goes_red_on_a_drifted_pin(self):
        # Behavior, not text: dropping `|| fail=1`, or swapping it for `|| echo` / `|| :` / `|| true`,
        # or dropping --strict, leaves verify.sh green on drift and fails this.
        code, out = run_verify_pin_step("shared-utils/x.py", "0" * 40)
        self.assertIn("PIN DRIFT", out)
        self.assertNotEqual(code, 0, out)

    def test_verify_sh_goes_red_on_a_missing_pin_counterpart(self):
        code, out = run_verify_pin_step("shared-utils/x.py", "0" * 40, file_present=False)
        self.assertIn("PIN MISSING", out)
        self.assertNotEqual(code, 0, out)

    def test_verify_sh_stays_green_on_a_matching_pin(self):
        # The control for the two tests above: the same harness is green when nothing drifted.
        sha = hashlib.sha1(b"blob 11\0print('a')\n").hexdigest()
        code, out = run_verify_pin_step("shared-utils/x.py", sha)
        self.assertIn("PIN OK", out)
        self.assertEqual(code, 0, out)

    def test_the_docstring_describes_the_strict_gate(self):
        doc = SCRIPT.read_text(encoding="utf-8").split('"""')[1]
        self.assertIn("verify.sh runs this script with --strict", doc)
        self.assertNotIn("without --strict", doc)
        self.assertNotIn("is a WARNING, not a failure", doc)


if __name__ == "__main__":
    unittest.main()
