"""A full 7-step funnel gets wireframes and mockups for ALL its downsell pages (SPF030).

legacy_downsell_images.py runs Skill 71's pipeline for every downsell slug of the funnel
size: three stages (desktop wireframe, mobile wireframe, visual mockup), eight sections
each, offline stub provider. Run: python3 test_legacy_downsell_images.py
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent
REPO = SCRIPTS.parents[1]
TOOL = SCRIPTS / "legacy_downsell_images.py"
SKILL71 = REPO / "71-blackceo-signature-page"
BRAND = SKILL71 / "assets" / "brand" / "blackceo-brand.json"
LEDGER = json.loads((SCRIPTS.parent / "examples" / "golden-daybreak" / "copy_ledger.json").read_text())


class LegacyDownsellImagesTests(unittest.TestCase):
    def run_tool(self, ledger, *extra):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        (root / "ledger.json").write_text(json.dumps(ledger))
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--ledger", str(root / "ledger.json"),
             "--skill71-root", str(SKILL71), "--brand-file", str(BRAND),
             "--brand-owner", "blackceo", "--out-dir", str(root / "out"), *extra],
            capture_output=True, text=True)
        return proc, root / "out"

    def test_seven_step_funnel_builds_both_downsell_pages(self):
        proc, out = self.run_tool(LEDGER)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(sorted(report["pages"]), ["downsell", "downsell-2"])
        for slug, page in report["pages"].items():
            self.assertEqual(page["page_role"], "downsell_1")
            self.assertEqual({k: v["images"] for k, v in page["stages"].items()},
                             {"desktop-wireframe": 8, "mobile-tablet": 8, "visual-mockup": 16})
            req = json.loads((out / slug / "production-request-visual-mockup.json").read_text())
            self.assertEqual(len(req["sections"]), 8)
            self.assertEqual(req["decline_action"], {"label": "No thanks"})
        # downsell-2 carries its OWN copy, never downsell's
        d1 = (out / "downsell" / "production-request-visual-mockup.json").read_text()
        d2 = (out / "downsell-2" / "production-request-visual-mockup.json").read_text()
        self.assertIn("Single Day Pass", d2)
        self.assertNotIn("Single Day Pass", d1)
        self.assertTrue((out / "downsell-images-receipt.json").is_file())

    def test_five_step_funnel_builds_only_the_one_downsell(self):
        proc, _ = self.run_tool(dict(LEDGER, funnel_size=5))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(list(json.loads(proc.stdout)["pages"]), ["downsell"])

    def test_three_step_funnel_has_no_downsell_and_says_so(self):
        proc, _ = self.run_tool(dict(LEDGER, funnel_size=3))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["pages"], {})
        self.assertIn("no downsell page", report["note"])

    def test_page_flag_narrows_and_refuses_a_page_outside_the_funnel(self):
        proc, _ = self.run_tool(LEDGER, "--page", "downsell-2")
        self.assertEqual(list(json.loads(proc.stdout)["pages"]), ["downsell-2"])
        proc, _ = self.run_tool(dict(LEDGER, funnel_size=5), "--page", "downsell-2")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("downsell-2", proc.stderr)

    def test_a_page_missing_a_section_is_refused_by_name(self):
        ledger = json.loads(json.dumps(LEDGER))
        page = next(p for p in ledger["pages"] if p["page_type"] == "downsell-2")
        page["sections"] = page["sections"][:7]
        proc, _ = self.run_tool(ledger)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("downsell-2: the copy ledger page must carry sections 1..8", proc.stderr)

    def test_paid_provider_needs_the_owner_flag(self):
        proc, _ = self.run_tool(LEDGER, "--image-provider", "kie")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--allow-paid", proc.stderr)


if __name__ == "__main__":
    unittest.main()
