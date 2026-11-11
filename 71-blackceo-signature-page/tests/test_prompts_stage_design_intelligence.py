#!/usr/bin/env python3
"""Skill 45 consumption at the prompts stage (fix spec M4, issues 8 and 39).

image-inventory-prompts cannot close unless the run read Skill 45: the receipt at
private/receipts/design-intelligence.json (written by scripts/build_production_request.py, or by
shared-utils/signature_launch/design_intelligence.py) must exist, must be re-hashable against the
live design library, and must name the style card the intake asks for. The stage_gate close hook
(design_intelligence_problems) runs beside the existing style-selection hook.

Fail-before / pass-after: before this change the same close passed with no receipt at all.

The run folders are the real-contract image chain tests/test_stage_gate.py already builds.
"""
import json
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_stage_gate as tsg  # noqa: E402  (its chain builder is the real-contract fixture)

STAGE = "image-inventory-prompts"
RECEIPT = Path("private") / "receipts" / "design-intelligence.json"
CARD_ID = "FN-TEST-001"
CARD_TIER = "Bold gold funnel style, hero left, headline room right. Do not place text over any face."
INDEX_ROW = (f"| 1 | {CARD_ID} | Test | a test card | production | v1.0 | 2026-11-10 | "
             "funnel-page-designs/FN-TEST-001.md |\n")


class PromptsStageDesignIntelligence(unittest.TestCase):
    def setUp(self):
        self.factory = tsg.StageGateTest("test_e_close_image_inventory_prompts_real_validator")
        self.factory.setUp()
        self.addCleanup(self.factory.tearDown)
        self.td = self.factory.td
        self.di = tsg.stage_gate._design_intelligence()

    def chain(self, name="run"):
        run = self.td / name
        env, gate = self.factory.build_image_stage_chain(run, tsg.fitted_good_prompt())
        tsg.put_receipt(run, STAGE, author="prompt-writer", reviewer="prompt-reviewer",
                        scores={"fidelity": 9},
                        extra={"validator_files": [f"{STAGE}/IMG-001.txt", f"{STAGE}/IMG-002.txt"]})
        return run, env, gate

    def library_copy(self):
        """A private copy of the real Skill 45 library, with one extra registered funnel card."""
        lib = self.td / "library"
        shutil.copytree(self.di.library_root(), lib)
        index = (lib / "INDEX.md").read_text(encoding="utf-8")
        marker = "| - | - | *(empty - awaiting first funnel/landing/website style card)* | | | | | |\n"
        self.assertIn(marker, index, "the funnel table of INDEX.md changed shape")
        (lib / "INDEX.md").write_text(index.replace(marker, INDEX_ROW), encoding="utf-8")
        (lib / "funnel-page-designs" / "FN-TEST-001.md").write_text(
            f"# {CARD_ID}\n\n### LONG (<=19,000 chars)\n```\n{CARD_TIER}\n```\n", encoding="utf-8")
        return lib

    def test_close_refuses_without_the_receipt(self):
        run, env, gate = self.chain()
        (run / RECEIPT).unlink()
        proc = gate("close", str(run), STAGE, expect=1, env=env)
        out = proc.stdout + proc.stderr
        self.assertIn("AF-DI-ABSENT", out)
        self.assertIn("design-intelligence receipt", out)
        state = json.loads((run / "private" / "state.json").read_text())
        self.assertNotEqual(state["stages"].get(STAGE, {}).get("status"), "closed")

    def test_close_passes_with_the_receipt(self):
        run, env, gate = self.chain()
        self.assertTrue((run / RECEIPT).is_file())
        gate("close", str(run), STAGE, expect=0, env=env)
        state = json.loads((run / "private" / "state.json").read_text())
        self.assertEqual(state["stages"][STAGE]["status"], "closed")

    def test_close_refuses_a_hand_written_receipt(self):
        run, env, gate = self.chain()
        (run / RECEIPT).write_text(json.dumps({
            "schema": self.di.RECEIPT_SCHEMA, "card_id": None, "card_sha256": None,
            "prompt_bands_sha256": "0" * 64, "negative_prompting_sha256": "1" * 64,
            "page_rules_category": "funnel-page-designs", "page_rules_sha256": "2" * 64}), encoding="utf-8")
        proc = gate("close", str(run), STAGE, expect=1, env=env)
        self.assertIn("does not match the design library now", proc.stdout + proc.stderr)

    def test_close_refuses_a_receipt_older_than_the_library(self):
        lib = self.library_copy()
        run, env, gate = self.chain()
        env = {**env, "DIU_LIBRARY_DIR": str(lib)}
        self.di.write_receipt(run, None, root=lib)
        (lib / "funnel-page-designs" / "_RULES.md").write_text("# rules\nchanged after the prompts\n", encoding="utf-8")
        proc = gate("close", str(run), STAGE, expect=1, env=env)
        out = proc.stdout + proc.stderr
        self.assertIn("page_rules_sha256", out)
        self.assertIn("redo them", out)

    def test_intake_style_card_must_be_the_card_the_receipt_names(self):
        lib = self.library_copy()
        run, env, gate = self.chain()
        env = {**env, "DIU_LIBRARY_DIR": str(lib)}
        intake = json.loads((run / "intake.json").read_text(encoding="utf-8"))
        intake["style_card_id"] = CARD_ID
        (run / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
        self.di.write_receipt(run, None, root=lib)  # built without the card the intake asks for
        proc = gate("close", str(run), STAGE, expect=1, env=env)
        self.assertIn(f"asks for style card '{CARD_ID}'", proc.stdout + proc.stderr)
        self.di.write_receipt(run, CARD_ID, root=lib)  # rebuilt with it
        gate("close", str(run), STAGE, expect=0, env=env)

    def test_close_refuses_when_the_skill_45_reader_cannot_be_loaded(self):
        run, _env, _gate = self.chain()
        self.assertEqual(tsg.stage_gate.design_intelligence_problems(run), [])  # control: reader loads, receipt current
        with mock.patch.object(tsg.stage_gate, "_design_intelligence", side_effect=ImportError("gone")):
            problems = tsg.stage_gate.design_intelligence_problems(run)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("AF-DI-ABSENT", problems[0])
        self.assertIn("cannot be loaded", problems[0])

    def test_the_stage_contract_reads_the_four_skill_45_paths(self):
        reads = " ".join(tsg.stage_gate.STAGES[STAGE]["reads"])
        for path in ("_system/prompt-bands.json", "_system/NEGATIVE-PROMPTING-SOP.md",
                     "funnel-page-designs/_RULES.md", "library/INDEX.md"):
            self.assertIn(path, reads)


if __name__ == "__main__":
    unittest.main()
