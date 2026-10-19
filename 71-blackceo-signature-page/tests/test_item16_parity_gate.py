#!/usr/bin/env python3
"""Item 16 (Update Plan): approved mockup as the responsive-html stage's
design source of truth, with the side-by-side parity check as required
gate evidence.

Pins:
  (a) the responsive-html contract artifacts require the parity sheets
      at BOTH widths and the drift table (compare-report.json), not a
      single generic compare image;
  (b) the stage contract records the source-of-truth rule and the
      parity close requirement in its purpose;
  (c) stage_gate.check_parity_evidence: complete evidence with drift
      status "pass" returns no failures; a missing sheet at either
      width, a missing report, an unreadable report, and drift statuses
      fail / skipped-no-html / unavailable-playwright each block by
      name, with the report's named drift lines carried through;
  (d) the SOP Stage 12 text states the source-of-truth rule and the
      parity close requirement;
  (e) references/html-qc-rubric.md criterion 4 carries the required
      close evidence;
  (f) references/artifact-contracts.md carries the parity evidence
      contract naming all three records;
  (g) blast radius: stage IDs and stage order unchanged; the
      responsive-html validators and review requirement unchanged.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "references" / "stage-contract.json").read_text(encoding="utf-8"))
STAGES = CONTRACT["stages"]
sys.path.insert(0, str(ROOT / "scripts"))
import stage_gate  # noqa: E402


def globs(stage):
    return [a["glob"] for a in STAGES[stage]["artifacts"]]


def make_run(report=None, sheets=(1440, 390), report_text=None):
    td = tempfile.TemporaryDirectory()
    run_dir = Path(td.name)
    compare = run_dir / "responsive-html" / "compare"
    compare.mkdir(parents=True)
    for width in sheets:
        (compare / f"compare-{width}-01.png").write_bytes(b"\x89PNG")
    if report_text is not None:
        (compare / "compare-report.json").write_text(report_text, encoding="utf-8")
    elif report is not None:
        (compare / "compare-report.json").write_text(json.dumps(report), encoding="utf-8")
    return td, run_dir


def pass_report():
    return {"tool": "compare_sheet.py",
            "drift": {"status": "pass",
                      "widths": {"1440": {"failures": [], "table": []},
                                 "390": {"failures": [], "table": []}}}}


class ContractPins(unittest.TestCase):
    def test_artifacts_require_both_parity_sheets_and_drift_table(self):
        g = globs("responsive-html")
        self.assertIn("responsive-html/compare/compare-1440-*.png", g)
        self.assertIn("responsive-html/compare/compare-390-*.png", g)
        self.assertIn("responsive-html/compare/compare-report.json", g)
        self.assertNotIn("responsive-html/compare/*.png", g,
                         "the generic single-image glob must not stand: "
                         "one width's sheet is not parity evidence")

    def test_purpose_records_source_of_truth_and_close_requirement(self):
        purpose = STAGES["responsive-html"].get("purpose", "")
        self.assertIn("source of truth", purpose)
        self.assertIn("1440 and 390", purpose)
        self.assertIn("compare-report.json", purpose)
        self.assertIn("block close", purpose)

    def test_stage_list_and_validators_unchanged(self):
        self.assertEqual(CONTRACT["stage_order"], [
            "intake", "copy", "font-action-plan",
            "desktop-wireframe", "mobile-tablet", "visual-mockup", "image-inventory-prompts",
            "image-generation-qc", "image-map-upload", "design-board", "final-mockups",
            "responsive-html", "ghl-install-test", "publish-verify",
            "automation-wiring"])
        spec = STAGES["responsive-html"]
        self.assertEqual(spec["depends_on"], ["final-mockups"])
        self.assertTrue(spec["review_required"])
        self.assertIn("python3 scripts/compare_sheet.py {run_dir}",
                      spec["validators"])


class ParityEvidenceHook(unittest.TestCase):
    def test_pass_evidence_returns_no_failures(self):
        td, run_dir = make_run(report=pass_report())
        with td:
            self.assertEqual(stage_gate.check_parity_evidence(run_dir), [])

    def test_missing_sheet_at_one_width_blocks_by_name(self):
        td, run_dir = make_run(report=pass_report(), sheets=(1440,))
        with td:
            failures = stage_gate.check_parity_evidence(run_dir)
            self.assertTrue(any("390" in f and "parity" in f for f in failures),
                            failures)

    def test_missing_report_blocks_by_name(self):
        td, run_dir = make_run(report=None)
        with td:
            failures = stage_gate.check_parity_evidence(run_dir)
            self.assertTrue(any("compare-report.json" in f for f in failures),
                            failures)

    def test_unreadable_report_blocks(self):
        td, run_dir = make_run(report_text="{not json")
        with td:
            failures = stage_gate.check_parity_evidence(run_dir)
            self.assertTrue(any("unreadable" in f for f in failures), failures)

    def test_drift_fail_blocks_and_carries_named_lines(self):
        report = pass_report()
        report["drift"]["status"] = "fail"
        report["drift"]["widths"]["1440"]["failures"] = [
            "DRIFT: section count differs: mockup has 12 sections, page has 11"]
        td, run_dir = make_run(report=report)
        with td:
            failures = stage_gate.check_parity_evidence(run_dir)
            self.assertTrue(any("'fail'" in f for f in failures), failures)
            self.assertTrue(any("section count differs" in f for f in failures),
                            failures)

    def test_skipped_and_unavailable_statuses_block(self):
        for status in ("skipped-no-html", "unavailable-playwright"):
            report = pass_report()
            report["drift"]["status"] = status
            td, run_dir = make_run(report=report)
            with td:
                failures = stage_gate.check_parity_evidence(run_dir)
                self.assertTrue(failures, status)
                self.assertTrue(any(status in f for f in failures), failures)


class TextPins(unittest.TestCase):
    def test_sop_stage_12_states_the_rule(self):
        sop = (ROOT / "references" /
               "BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md"
               ).read_text(encoding="utf-8")
        stage12 = sop.split("## Stage 12")[1].split("## Stage 13")[0]
        self.assertIn("design source of truth", stage12)
        self.assertIn("Parity evidence (required to close", stage12)
        self.assertIn("compare-report.json", stage12)
        self.assertIn("at 1440 and at 390", stage12)

    def test_rubric_criterion_4_requires_the_evidence(self):
        rubric = (ROOT / "references" / "html-qc-rubric.md").read_text(encoding="utf-8")
        self.assertIn("Required close evidence (Update Plan Item 16)", rubric)
        self.assertIn("check_parity_evidence", rubric)

    def test_artifact_contracts_carry_the_parity_contract(self):
        text = (ROOT / "references" / "artifact-contracts.md").read_text(encoding="utf-8")
        self.assertIn("## Parity evidence (stage `responsive-html`; Update Plan Item 16)", text)
        self.assertIn("compare-1440-*.png", text)
        self.assertIn("compare-390-*.png", text)
        self.assertIn("compare-report.json", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
