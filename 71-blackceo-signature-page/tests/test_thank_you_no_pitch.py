"""AF-71-THANK-YOU-PITCH: a thank-you page is not drawn from a manuscript that pitches.

run_page_role_stages.py scans the manuscript with Skill 82's semantic_scan.py before its first
stage and refuses on any FLAG line; a clean scan writes private/receipts/no-pitch-scan.json
(zero findings, manuscript sha), and the copy stage will not close for a thank_you run without it.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import no_pitch_scan  # noqa: E402
import stage_gate  # noqa: E402
from test_page_role_thank_you import FIXTURE, PY, STUB, RunCase, write_intake  # noqa: E402

PITCH = "One more thing — add it for $47 before this page closes."
RUNNER = SCRIPTS / "run_page_role_stages.py"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class RunnerTests(RunCase):
    def setUp(self):
        super().setUp()
        write_intake(self.run, page_role="thank_you", copy_version="thank-you")
        self.receipt = self.run / "private" / "receipts" / "no-pitch-scan.json"

    def run_runner(self, *extra, manuscript=None):
        cmd = [PY, str(RUNNER), str(self.run), "--model", STUB, "--preflight", *extra]
        if manuscript:
            cmd += ["--manuscript", str(manuscript)]
        return subprocess.run(cmd, capture_output=True, text=True)

    def pitched(self):
        path = Path(self.tmp.name) / "pitched.md"
        path.write_text(FIXTURE.read_text(encoding="utf-8") + "\n" + PITCH + "\n", encoding="utf-8")
        return path

    def test_a_pitched_manuscript_is_refused_before_any_stage(self):
        proc = self.run_runner(manuscript=self.pitched())
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("AF-71-THANK-YOU-PITCH", proc.stdout)
        self.assertIn("one_more_thing", proc.stdout)
        self.assertFalse((self.run / "production-request.json").exists())  # no stage started
        self.assertFalse(self.receipt.exists())

    def test_the_fixture_manuscript_passes_and_leaves_a_zero_finding_receipt(self):
        proc = self.run_runner()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(data["findings"], 0)
        self.assertEqual(data["manuscript_sha256"], sha(self.run / "copy" / "internal-manuscript.md"))

    def test_a_refusal_removes_a_receipt_left_by_an_earlier_clean_run(self):
        self.assertEqual(self.run_runner().returncode, 0)
        self.assertTrue(self.receipt.is_file())
        self.assertEqual(self.run_runner(manuscript=self.pitched()).returncode, 1)
        self.assertFalse(self.receipt.exists())

    def test_the_flag_names_the_scanner_and_a_missing_scanner_refuses(self):
        proc = self.run_runner("--no-pitch-scan", str(Path(self.tmp.name) / "absent.py"))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("AF-71-THANK-YOU-PITCH", proc.stdout)
        self.assertFalse(self.receipt.exists())

    def test_a_scanner_that_errors_is_a_refusal_not_a_pass(self):
        broken = Path(self.tmp.name) / "broken_scan.py"
        broken.write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
        proc = self.run_runner("--no-pitch-scan", str(broken))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertFalse(self.receipt.exists())


class CopyCloseTests(RunCase):
    """The copy stage's gate row: no receipt, no close; a landing run is not asked for one."""

    def failure(self):
        return stage_gate.run_one_validator(["gate:no_pitch_receipt"], self.run)

    def test_the_copy_stage_carries_the_gate_row(self):
        copy = stage_gate.STAGES["copy"]
        self.assertTrue(any(v.startswith("gate:no_pitch_receipt") for v in copy["validators"]))
        self.assertIn("gate:no_pitch_receipt", stage_gate.GATE_BUILTINS)

    def test_a_thank_you_run_without_a_receipt_cannot_close_copy(self):
        write_intake(self.run, page_role="thank_you", copy_version="thank-you")
        self.assertIn("AF-71-THANK-YOU-PITCH", self.failure() or "")

    def test_a_clean_receipt_closes_and_an_edit_after_the_scan_reopens(self):
        write_intake(self.run, page_role="thank_you", copy_version="thank-you")
        proc = subprocess.run([PY, str(SCRIPTS / "no_pitch_scan.py"), str(self.run)],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIsNone(self.failure())
        manuscript = self.run / "copy" / "internal-manuscript.md"
        manuscript.write_text(manuscript.read_text(encoding="utf-8") + "\n" + PITCH + "\n", encoding="utf-8")
        self.assertIn("changed since", self.failure() or "")

    def test_a_clean_receipt_does_not_close_once_the_manuscript_is_deleted(self):
        write_intake(self.run, page_role="thank_you", copy_version="thank-you")
        proc = subprocess.run([PY, str(SCRIPTS / "no_pitch_scan.py"), str(self.run)],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        (self.run / "copy" / "internal-manuscript.md").unlink()
        self.assertIn("changed since", no_pitch_scan.receipt_failure(self.run) or "")

    def test_a_receipt_with_findings_never_closes(self):
        write_intake(self.run, page_role="thank_you", copy_version="thank-you")
        receipt = self.run / "private" / "receipts" / "no-pitch-scan.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps({
            "findings": 1, "manuscript_sha256": sha(self.run / "copy" / "internal-manuscript.md")}),
            encoding="utf-8")
        self.assertIn("AF-71-THANK-YOU-PITCH", self.failure() or "")

    def test_a_landing_run_is_not_asked_for_a_receipt(self):
        write_intake(self.run, copy_version="standard")
        self.assertIsNone(self.failure())


class ModuleTests(unittest.TestCase):
    def test_the_default_scanner_is_skill_82s(self):
        scanner = no_pitch_scan.default_scanner()
        self.assertIsNotNone(scanner)
        self.assertEqual(scanner.name, "semantic_scan.py")
        self.assertEqual(scanner.parent.parent.name, "82-signature-thank-you")


if __name__ == "__main__":
    unittest.main()
