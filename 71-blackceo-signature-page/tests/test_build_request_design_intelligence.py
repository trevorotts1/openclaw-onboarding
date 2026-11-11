#!/usr/bin/env python3
"""scripts/build_production_request.py reads Skill 45 (fix spec M4, issues 8 and 39).

Every build reads the design library's prompt bands, negative-prompting rules and funnel page
rules and writes private/receipts/design-intelligence.json. A style card the intake (or
--style-card-id) names has its LONG tier embedded VERBATIM as a BRAND STYLE block that is never
trimmed. A missing library or an unregistered card refuses by name (AF-DI-ABSENT) and writes
nothing. Skill 45 is only read.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand_fixture import give_blackceo_colors  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "copy_examples"
SCRIPTS = ROOT / "scripts"
DI_PATH = ROOT.parent / "shared-utils" / "signature_launch" / "design_intelligence.py"

CARD_ID = "FN-TEST-001"
# literal braces on purpose: they must survive the executor's str.format (a {WORD} variable is its own refusal)
CARD_TIER = 'Bold gold funnel style {"palette": "gold"}, hero left, headline room right. Do not place text over any face.'


def load_di():
    import importlib.util
    spec = importlib.util.spec_from_file_location("signature_launch_design_intelligence", DI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


di = load_di()


class BuildRequestDesignIntelligence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.run = base / "run"
        (self.run / "copy").mkdir(parents=True)
        (self.run / "copy" / "internal-manuscript.md").write_text(
            (FIXTURES / "standard-path-b.md").read_text(encoding="utf-8"), encoding="utf-8")
        give_blackceo_colors(self.run)
        self.lib = base / "library"
        (self.lib / "_system").mkdir(parents=True)
        (self.lib / "funnel-page-designs").mkdir()
        (self.lib / "INDEX.md").write_text(
            "| Sig # | ID | Style Name | One-Line Summary | Status | Ver | Date | File Path |\n|---|---|---|---|---|---|---|---|\n"
            f"| 1 | {CARD_ID} | T | s | production | v1.0 | 2026-11-10 | funnel-page-designs/FN-TEST-001.md |\n"
            "| 2 | FN-TEST-002 | V | s | production | v1.0 | 2026-11-10 | funnel-page-designs/FN-TEST-002.md |\n",
            encoding="utf-8")
        (self.lib / "funnel-page-designs" / "FN-TEST-002.md").write_text(
            "# FN-TEST-002\n\n### LONG (<=19,000 chars)\n```\nGold style for {SUBJECT} with room for {HEADLINE_TEXT}.\n```\n",
            encoding="utf-8")
        (self.lib / "funnel-page-designs" / "FN-TEST-001.md").write_text(
            f"# {CARD_ID}\n\n### LONG (<=19,000 chars)\n```\n{CARD_TIER}\n```\n", encoding="utf-8")
        (self.lib / "funnel-page-designs" / "_RULES.md").write_text("# rules\n", encoding="utf-8")
        (self.lib / "_system" / "prompt-bands.json").write_text('{"version": 3, "bands": {}}', encoding="utf-8")
        (self.lib / "_system" / "NEGATIVE-PROMPTING-SOP.md").write_text("# negative\n", encoding="utf-8")
        self.out = self.run / "production-request.json"

    def cli(self, *extra, library=None, stage="visual-mockup", model="STUB-NO-MODEL"):
        env = {**os.environ, "DIU_LIBRARY_DIR": str(library or self.lib)}
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "build_production_request.py"),
             "--copy-version", "standard", "--manuscript", str(self.run / "copy" / "internal-manuscript.md"),
             "--stage", stage, "--model", model, "--out", str(self.out), *extra],
            capture_output=True, text=True, env=env, cwd=self.tmp.name)

    def receipt(self):
        return json.loads((self.run / di.RECEIPT_REL).read_text(encoding="utf-8"))

    def test_every_build_writes_a_receipt_that_matches_the_library(self):
        proc = self.cli()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("DESIGN-INTELLIGENCE receipt=private/receipts/design-intelligence.json card=none", proc.stdout)
        receipt = self.receipt()
        self.assertIsNone(receipt["card_id"])
        self.assertEqual(di.verify_receipt(receipt, self.lib), [])
        request = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertNotIn("BRAND STYLE", request["stage_prompts"]["visual-mockup"])
        self.assertNotIn("style_card", request["metadata"])

    def test_style_card_long_tier_is_embedded_verbatim_and_receipted(self):
        proc = self.cli("--style-card-id", CARD_ID)
        # rc 0 also proves the braces in the card survive the executor's str.format
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        request = json.loads(self.out.read_text(encoding="utf-8"))
        template = request["stage_prompts"]["visual-mockup"]
        self.assertIn("BRAND STYLE (design library style card, LONG tier, verbatim)", template)
        self.assertIn(CARD_TIER.replace("{", "{{").replace("}", "}}"), template)
        self.assertEqual(request["metadata"]["style_card"]["id"], CARD_ID)
        self.assertEqual(request["metadata"]["style_card"]["sha256"], self.receipt()["card_sha256"])
        self.assertEqual(self.receipt()["card_id"], CARD_ID)
        self.assertEqual(di.verify_receipt(self.receipt(), self.lib), [])

    def test_all_four_stages_carry_the_card_verbatim(self):
        # ruling WP-12-2: desktop-wireframe, mobile-tablet, visual-mockup and final-mockups all carry the card
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup", "final-mockups"):
            with self.subTest(stage=stage):
                proc = self.cli("--style-card-id", CARD_ID, stage=stage)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                template = json.loads(self.out.read_text(encoding="utf-8"))["stage_prompts"][stage]
                self.assertIn("BRAND STYLE (design library style card, LONG tier, verbatim)", template)
                self.assertIn(CARD_TIER.replace("{", "{{").replace("}", "}}"), template)

    def test_a_card_too_large_for_the_model_budget_is_refused_never_trimmed(self):
        card = self.lib / "funnel-page-designs" / "FN-TEST-001.md"
        card.write_text(f"# {CARD_ID}\n\n### LONG (<=19,000 chars)\n```\n{'Gold style. ' * 5000}\n```\n", encoding="utf-8")
        proc = self.cli("--style-card-id", CARD_ID, model="gpt-image-2")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("REFUSED", proc.stdout)
        self.assertFalse(self.out.exists(), "an oversized card must refuse, not write a trimmed request")
        self.assertFalse((self.run / di.RECEIPT_REL).exists())

    def test_the_card_comes_from_the_intake_when_no_flag_is_given(self):
        intake_path = self.run / "intake.json"  # give_blackceo_colors wrote the brand pointer here: keep it
        intake = json.loads(intake_path.read_text(encoding="utf-8")) if intake_path.is_file() else {}
        intake["style_card_id"] = CARD_ID
        intake_path.write_text(json.dumps(intake), encoding="utf-8")
        proc = self.cli()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.receipt()["card_id"], CARD_ID)
        self.assertIn(CARD_TIER.replace("{", "{{").replace("}", "}}"),
                      json.loads(self.out.read_text())["stage_prompts"]["visual-mockup"])

    def test_an_unregistered_card_refuses_by_name_and_writes_nothing(self):
        proc = self.cli("--style-card-id", "FN-NOPE-404")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("REFUSED: AF-DI-ABSENT", proc.stdout)
        self.assertFalse(self.out.exists())
        self.assertFalse((self.run / di.RECEIPT_REL).exists())

    def test_a_card_with_unfilled_template_variables_is_refused_by_name(self):
        proc = self.cli("--style-card-id", "FN-TEST-002")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("FN-TEST-002", proc.stdout)
        self.assertIn("{HEADLINE_TEXT}, {SUBJECT}", proc.stdout)
        self.assertFalse(self.out.exists())
        self.assertFalse((self.run / di.RECEIPT_REL).exists())

    def test_a_missing_library_refuses_every_build_even_without_a_card(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        proc = self.cli(library=empty)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("AF-DI-ABSENT", proc.stdout)
        self.assertFalse(self.out.exists())
        self.assertFalse((self.run / di.RECEIPT_REL).exists())

    def test_a_missing_rules_file_refuses_by_name(self):
        (self.lib / "_system" / "NEGATIVE-PROMPTING-SOP.md").unlink()
        proc = self.cli()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("NEGATIVE-PROMPTING-SOP.md", proc.stdout)


if __name__ == "__main__":
    unittest.main()
