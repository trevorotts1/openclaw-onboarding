#!/usr/bin/env python3
"""test_storyboard_failure_contract.py — T0-60 failure contract for Skill 24.

The defect: create_storyboard.py printed "Error: Unknown model ..." to STDOUT,
returned None, and the process exited ZERO having written no file. Any caller
that branches on the exit code — a pipeline stage, a wave gate, a delegating
agent — proceeded believing a storyboard existed.

BOTH DIRECTIONS ARE REQUIRED. A gate observed only failing is as useless as one
observed only passing:

  * unknown model      -> non-zero, error on STDERR, no file written
  * zero-clip duration -> non-zero, error on STDERR, no file written
  * a real request     -> exit 0, both files written, segments > 0  (anti-false-fail)

Hermetic: invokes the script as a subprocess in a temp directory. stdlib only,
no network, no fleet box.

Usage: python3 24-storyboard-writer/test/test_storyboard_failure_contract.py
Exit:  0 = the contract holds; 1 = it does not.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT = Path(os.environ.get("STORYBOARD_SCRIPT", SKILL_DIR / "scripts" / "create_storyboard.py"))
# A model whose clip length is known from scripts/model-database.json.
GOOD_MODEL = "veo-3-1"


def run(cwd, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd), capture_output=True, text=True, timeout=120,
    )


class StoryboardFailureContract(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="storyboard-contract-")
        self.work = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # --- failure direction ---------------------------------------------------

    def test_unknown_model_exits_nonzero_with_stderr_and_no_file(self):
        r = run(self.work, "--duration", "30", "--model", "definitely-not-a-model",
                "--topic", "t", "--output", "sb")
        self.assertNotEqual(r.returncode, 0,
                            "an unknown model must not exit zero; a caller branching on "
                            "the exit code would proceed as if a storyboard existed")
        self.assertIn("AF-STORYBOARD-UNKNOWN-MODEL", r.stderr,
                      "the failure must be NAMED on stderr")
        self.assertNotIn("AF-STORYBOARD-UNKNOWN-MODEL", r.stdout,
                         "the error must not be on stdout, where a success reader picks it up")
        self.assertFalse((self.work / "sb.json").exists())
        self.assertFalse((self.work / "sb.md").exists())

    def test_zero_clip_duration_exits_nonzero_and_writes_nothing(self):
        # duration 0 is the only input that yields a clip count of zero, which
        # previously wrote a storyboard whose segment list was empty.
        r = run(self.work, "--duration", "0", "--model", GOOD_MODEL,
                "--topic", "t", "--output", "sb0")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("AF-STORYBOARD-EMPTY", r.stderr)
        self.assertFalse((self.work / "sb0.json").exists(),
                         "no empty storyboard artifact may be emitted")

    # --- anti-false-fail control --------------------------------------------

    def test_real_request_still_succeeds_with_segments(self):
        r = run(self.work, "--duration", "30", "--model", GOOD_MODEL,
                "--topic", "launch", "--output", "sbok")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.work / "sbok.json"
        self.assertTrue(out.exists())
        doc = json.loads(out.read_text())
        self.assertGreater(len(doc["segments"]), 0)
        self.assertEqual(doc["calculations"]["num_segments"], len(doc["segments"]))
        self.assertTrue((self.work / "sbok.md").exists())

    def test_duration_shorter_than_one_clip_still_produces_one_segment(self):
        # Explicitly pinned so a future "tighten the duration check" change cannot
        # silently start rejecting a legitimate short request.
        r = run(self.work, "--duration", "3", "--model", GOOD_MODEL,
                "--topic", "short", "--output", "sbshort")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = json.loads((self.work / "sbshort.json").read_text())
        self.assertEqual(len(doc["segments"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
