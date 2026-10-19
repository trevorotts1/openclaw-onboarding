#!/usr/bin/env python3
"""Acceptance tests for scripts/stage_executor.py (the generation wire).

The executor is the command the shared page service's --pipeline-command
seam was always meant to receive. These tests pin the wire, not the art:

  (a) a stub run produces the four image stages' files at the contract
      widths, and one stage-executor-record.json per stage;
  (b) the executor writes no gate receipt, no private/ directory and no
      REPORT.md, so it can never close a stage;
  (c) stub mode composes nothing and calls no network;
  (d) the paid route refuses without --allow-paid and without KIE_API_KEY;
  (e) one --item run writes the delivered name Image-NN.png and a record.

No paid API is called anywhere in this module.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board_fixture as bf  # noqa: E402  (SPF021: every image stage needs an approved design board)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "stage_executor.py"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand_fixture import give_blackceo_colors  # noqa: E402

spec = importlib.util.spec_from_file_location("stage_executor", SCRIPT)
exe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exe)

REQUEST = {
    "model": "STUB-NO-MODEL",
    "sections": [
        {"section_id": "hero", "section_name": "Hero", "copy": "New copy one.",
         "slots": [{"slot_id": "IMG-001", "aspect_ratio": "16:9",
                    "art_direction": "Window light."}]},
        {"section_id": "proof", "section_name": "Proof", "copy": "New copy two.",
         "slots": [{"slot_id": "IMG-002", "aspect_ratio": "4:3",
                    "art_direction": "Desk detail."}]},
    ],
}


class StageExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()
        bf.make_run(self.run_dir, base_request=REQUEST)  # writes production-request.json

    def approve_board(self):
        """final-mockups needs the page's approved Design Board, made after its images exist."""
        for i in (1, 2):
            bf.png(self.run_dir / "image-generation-qc" / f"Image-00{i}.png", (40 * i, 90, 140))
        bf.seed_real_board(self.run_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def execute(self, *extra):
        proc = subprocess.run([sys.executable, str(SCRIPT), str(self.run_dir), *extra],
                              capture_output=True, text=True, env=bf.subprocess_env())
        return proc

    @bf.needs_ocr
    def test_stub_writes_four_stages_and_no_receipts(self):
        self.approve_board()
        proc = self.execute("--provider", "stub")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        expected = {
            "desktop-wireframe": ["section-01.png", "section-02.png"],
            "mobile-tablet": ["section-01.png", "section-02.png"],
            "visual-mockup": ["desktop/part-01.png", "mobile/part-01.png",
                              "desktop/part-02.png", "mobile/part-02.png"],
            "final-mockups": ["desktop/part-01.png", "mobile/part-01.png",
                              "desktop/part-02.png", "mobile/part-02.png"],
        }
        for stage, files in expected.items():
            for rel in files:
                self.assertTrue((self.run_dir / stage / rel).is_file(), f"{stage}/{rel}")
            record = json.loads((self.run_dir / stage / exe.RECORD).read_text(encoding="utf-8"))
            self.assertEqual(record["provider"], "stub")
            self.assertEqual(len(record["images"]), len(files))
            self.assertIn("not a gate receipt", record["note"])
            for image in record["images"]:
                self.assertEqual(len(image["sha256"]), 64)
        self.assertFalse((self.run_dir / "private").exists())
        self.assertFalse((self.run_dir / "REPORT.md").exists())
        self.assertFalse(list(self.run_dir.rglob("*receipt*.json")))
        self.assertFalse(list(self.run_dir.rglob("generation-record.json")))

    def test_stub_widths(self):
        from PIL import Image
        proc = self.execute("--provider", "stub", "--stages", "desktop-wireframe,mobile-tablet")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(Image.open(self.run_dir / "desktop-wireframe/section-01.png").size[0], 1440)
        self.assertEqual(Image.open(self.run_dir / "mobile-tablet/section-01.png").size[0], 390)

    def test_paid_route_refuses(self):
        proc = self.execute("--provider", "kie", "--stages", "desktop-wireframe")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--allow-paid", proc.stdout)
        env = bf.subprocess_env()
        env.pop("KIE_API_KEY", None)
        proc = subprocess.run([sys.executable, str(SCRIPT), str(self.run_dir),
                               "--provider", "kie", "--allow-paid", "--stages", "desktop-wireframe"],
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("KIE_API_KEY", proc.stdout)
        self.assertFalse((self.run_dir / "desktop-wireframe").exists())

    def test_item_mode_writes_delivered_name(self):
        (self.run_dir / "image-inventory-prompts").mkdir()
        (self.run_dir / "image-inventory-prompts" / "IMG-007.txt").write_text(
            "Prompt for the seventh image.", encoding="utf-8")
        proc = self.execute("--stage", "image-generation-qc", "--item", "IMG-007",
                            "--provider", "stub")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((self.run_dir / "image-generation-qc/Image-07.png").is_file())
        record = json.loads((self.run_dir / "image-generation-qc" / exe.RECORD)
                            .read_text(encoding="utf-8"))
        self.assertEqual(record["items"][0]["item"], "IMG-007")


if __name__ == "__main__":
    unittest.main(verbosity=2)
