#!/usr/bin/env python3
"""T-36 (PBB-651): the journey-templates step goes through the bootstrap engine.

Runs 38-conversational-ai-system/scripts/03-create-journey-templates.sh in a
throwaway MASTER_FILES_DIR and asserts the installer contract:

  * every template and the registry are created, and a receipt is recorded;
  * a foreign file with different bytes is preserved, never overwritten;
  * an identical pre-existing file is adopted, not rewritten;
  * a re-run over a completed tree writes nothing.

Assert-based, stdlib only. Run: python3 -I test_journey_templates_script.py
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL_DIR = HERE.parent.parent.parent          # 38-conversational-ai-system/
SCRIPT = SKILL_DIR / "scripts" / "03-create-journey-templates.sh"
SRC = SKILL_DIR / "templates" / "journey-templates"

TYPES = ("coach", "e-commerce", "saas", "service-provider",
         "course-creator", "real-estate", "consulting", "wellness")


class JourneyTemplatesStep(unittest.TestCase):
    def setUp(self):
        self.master = tempfile.mkdtemp(prefix="t36-journey-")
        self.dst = Path(self.master) / "journey-templates"
        self.addCleanup(shutil.rmtree, self.master, True)

    def run_step(self):
        env = dict(os.environ, MASTER_FILES_DIR=self.master)
        return subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True, text=True, env=env, timeout=120,
        )

    def receipts(self):
        with open(self.dst / ".bootstrap-state.json") as fh:
            return json.load(fh)["receipts"]

    def test_creates_every_template_and_the_registry(self):
        result = self.run_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in TYPES:
            self.assertTrue((self.dst / name / "journey.md").is_file(), name)
        self.assertTrue((self.dst / "registry.md").is_file())
        receipts = self.receipts()
        self.assertEqual(len(receipts), len(TYPES) + 1)
        self.assertEqual(
            {r["outcome"] for r in receipts.values()}, {"created"}
        )
        installed = [ln for ln in result.stdout.splitlines()
                     if ln.startswith("[skill 38] installed ")]
        self.assertEqual(len(installed), len(TYPES) + 1)

    def test_foreign_file_with_different_bytes_is_preserved(self):
        coach = self.dst / "coach"
        coach.mkdir(parents=True)
        hand_edit = coach / "journey.md"
        hand_edit.write_bytes(b"HAND EDITED BY THE CLIENT\n")
        result = self.run_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            hand_edit.read_bytes(), b"HAND EDITED BY THE CLIENT\n"
        )
        self.assertIn("coach/journey.md already exists", result.stdout)
        self.assertNotIn("journey.coach", self.receipts())
        for name in TYPES:
            if name != "coach":
                self.assertTrue((self.dst / name / "journey.md").is_file(), name)

    def test_identical_pre_existing_file_is_adopted_not_rewritten(self):
        coach = self.dst / "coach"
        coach.mkdir(parents=True)
        target = coach / "journey.md"
        shutil.copyfile(SRC / "coach" / "journey.md", target)
        before = target.read_bytes()
        result = self.run_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(self.receipts()["journey.coach"]["outcome"], "adopted")

    def test_rerun_over_a_completed_tree_writes_nothing(self):
        self.assertEqual(self.run_step().returncode, 0)
        state = self.dst / ".bootstrap-state.json"
        before = state.read_bytes()
        tree = sorted(
            (p.relative_to(self.dst).as_posix(), p.read_bytes())
            for p in self.dst.rglob("*") if p.is_file()
        )
        self.assertEqual(self.run_step().returncode, 0)
        self.assertEqual(state.read_bytes(), before)
        after = sorted(
            (p.relative_to(self.dst).as_posix(), p.read_bytes())
            for p in self.dst.rglob("*") if p.is_file()
        )
        self.assertEqual(after, tree)


if __name__ == "__main__":
    unittest.main(verbosity=2)
