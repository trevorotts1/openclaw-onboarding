"""A 3/5/7-step funnel gets wireframes and mockups for EVERY page it has (SPF030, LANE-49).

legacy_downsell_images.py runs Skill 71's pipeline for every page of the funnel size except the
design-only checkout (named in the receipt): three stages (desktop wireframe, mobile wireframe,
visual mockup), offline stub provider, each page checked against structure/page_types.json.
Run: python3 test_legacy_downsell_images.py
"""
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent
REPO = SCRIPTS.parents[1]
TOOL = SCRIPTS / "legacy_downsell_images.py"
SKILL71 = REPO / "71-blackceo-signature-page"
CHECKOUT_MANUSCRIPT = SKILL71 / "tests" / "fixtures" / "copy_examples" / "checkout-example.md"
BRAND = SKILL71 / "assets" / "brand" / "blackceo-brand.json"
LEDGER = json.loads((SCRIPTS.parent / "examples" / "golden-daybreak" / "copy_ledger.json").read_text())
sys.path.insert(0, str(SKILL71 / "scripts"))
import deliverable_labels  # noqa: E402

# slug -> (page_key, sections): what each page of the 7-step funnel must end with
PAGES = {"main": ("sales", 12), "upsell": ("upsell_1", 8), "downsell": ("downsell_1", 8),
         "upsell-2": ("upsell_2", 8), "downsell-2": ("downsell_2", 8), "thank-you": ("thank_you", 5)}


class LegacyPageImagesTests(unittest.TestCase):
    def run_tool(self, ledger, *extra):
        # Fix plan B2 (unowned requirement G-3): the tool DEFAULTS to the real provider now, so a
        # run that wants the offline stub must ask for it and record the owner approval that
        # permitted it. This suite exercises the stub path end to end.
        if "--image-provider" not in extra:
            extra = (*extra, "--image-provider", "stub", "--stub-approved-by", "fixture-owner-approval")
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

    def test_seven_step_funnel_gets_designs_for_every_page_but_the_design_only_checkout(self):
        proc, out = self.run_tool(LEDGER)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(sorted(report["pages"]), sorted(PAGES))
        self.assertEqual(list(report["not_built"]), ["checkout"])
        for slug, (key, sections) in PAGES.items():
            page = report["pages"][slug]
            self.assertEqual(page["page_key"], key)
            self.assertEqual({k: v["images"] for k, v in page["stages"].items()},
                             {"desktop-wireframe": sections, "mobile-tablet": sections, "visual-mockup": 2 * sections})
            # a stub run is images only: the review PDFs and boards are named as render pending
            self.assertIn("desktop_wireframe_pdf", page["render_pending"])
        self.assertTrue((out / "page-images-receipt.json").is_file())

    def test_each_page_carries_its_own_copy_and_is_labelled_as_itself(self):
        proc, out = self.run_tool(LEDGER)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        want = {"main": "sales_page", "upsell": "upsell_1", "upsell-2": "upsell_2", "downsell": "downsell_1",
                "downsell-2": "downsell_2", "thank-you": "thank_you"}
        for slug, role in want.items():
            self.assertEqual(deliverable_labels.declared_page_role(out / slug), role, slug)

        def request(slug):
            return (out / slug / "production-request-visual-mockup.json").read_text()
        self.assertIn("Single Day Pass", request("downsell-2"))
        self.assertNotIn("Single Day Pass", request("downsell"))
        self.assertIn("Fast Track Sprint", request("upsell"))
        self.assertNotIn("Founders Table Retreat", request("upsell"))
        self.assertIn("Founders Table Retreat", request("upsell-2"))
        self.assertIn("Daybreak Method", request("main"))
        self.assertEqual(json.loads(request("downsell"))["decline_action"], {"label": "No thanks"})

    def test_the_thank_you_page_invents_no_price_or_order_reference(self):
        proc, out = self.run_tool(LEDGER, "--page", "thank-you", "--access-label", "Open My Daybreak")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = (out / "thank-you" / "copy" / "internal-manuscript.md").read_text()
        self.assertIn("The Daybreak Method. Paid.", text)
        self.assertIn("Open My Daybreak", text)
        self.assertNotRegex(text, r"[$]|USD|Order reference")
        self.assertIn("It is official", text)  # TY-1 verbatim
        self.assertIn("Check your email for your receipt", text)  # TY-2 step verbatim

    def test_five_step_funnel_has_one_downsell_and_no_checkout_note(self):
        proc, _ = self.run_tool(dict(LEDGER, funnel_size=5))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(sorted(report["pages"]), ["downsell", "main", "thank-you", "upsell", "upsell-2"])
        self.assertEqual(report["not_built"], {})

    def test_three_step_funnel_builds_main_upsell_and_thank_you(self):
        proc, _ = self.run_tool(dict(LEDGER, funnel_size=3))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(sorted(json.loads(proc.stdout)["pages"]), ["main", "thank-you", "upsell"])

    def test_page_flag_narrows_and_refuses_a_page_outside_the_funnel(self):
        proc, _ = self.run_tool(LEDGER, "--page", "downsell-2")
        self.assertEqual(list(json.loads(proc.stdout)["pages"]), ["downsell-2"])
        proc, _ = self.run_tool(dict(LEDGER, funnel_size=5), "--page", "downsell-2")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("downsell-2", proc.stderr)
        proc, _ = self.run_tool(LEDGER, "--page", "checkout")
        self.assertEqual(proc.returncode, 2)

    def test_a_page_missing_a_section_is_refused_by_name(self):
        for slug, needle in (("downsell-2", "must carry sections 1..8"), ("main", "must carry sections 1..12"),
                             ("upsell", "must carry sections 1..8"), ("thank-you", "TY-1, TY-2, TY-3")):
            ledger = json.loads(json.dumps(LEDGER))
            page = next(p for p in ledger["pages"] if p["page_type"] == slug)
            page["sections"] = page["sections"][:2]
            proc, _ = self.run_tool(ledger, "--page", slug)
            self.assertEqual(proc.returncode, 2, slug)
            self.assertIn(f"{slug}: the copy ledger page {needle}" if slug != "thank-you"
                          else f"{slug}: the copy ledger page must carry sections {needle}", proc.stderr)

    def test_seven_step_checkout_is_drawn_from_the_staged_manuscript(self):
        proc, out = self.run_tool(LEDGER, "--checkout-manuscript", str(CHECKOUT_MANUSCRIPT))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(sorted(report["pages"]), sorted([*PAGES, "checkout"]))
        self.assertEqual(report["not_built"], {})
        page = report["pages"]["checkout"]
        self.assertEqual(page["page_key"], "checkout")
        self.assertEqual({k: v["images"] for k, v in page["stages"].items()},
                         {"desktop-wireframe": 5, "mobile-tablet": 5, "visual-mockup": 10})

    def test_checkout_manuscript_with_card_fields_is_refused(self):
        bad = pathlib.Path(tempfile.mkdtemp()) / "checkout.md"
        bad.write_text(CHECKOUT_MANUSCRIPT.read_text(encoding="utf-8") + "\nCard number field.\n", encoding="utf-8")
        proc, _ = self.run_tool(LEDGER, "--page", "checkout", "--checkout-manuscript", str(bad))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("native checkout form only", proc.stderr)

    def test_without_the_manuscript_the_receipt_says_what_checkout_needs(self):
        proc, _ = self.run_tool(LEDGER, "--page", "main")
        self.assertIn("--checkout-manuscript", json.loads(proc.stdout)["not_built"]["checkout"])

    def test_paid_provider_needs_the_owner_flag(self):
        proc, _ = self.run_tool(LEDGER, "--image-provider", "kie")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--allow-paid", proc.stderr)


class WireframeSlotsetBoundToRequest(unittest.TestCase):
    """AF-FUN-VISUAL-SLOTSET (G-10): the tool writes the wireframe section plan and inventory from the
    page's own production request, after giving every section the funnel structure requires an image
    for a slot. The real tool output goes through the real prover; only final-mockups may remain."""

    run_tool = LegacyPageImagesTests.run_tool

    def check_size(self, size):
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.remove, str(SCRIPTS))
        import prove_sf_build
        proc, out = self.run_tool({**LEDGER, "funnel_size": size})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        run = out.parent / "run"
        run.mkdir()
        out.rename(run / "page-images")
        violations = prove_sf_build.visual_direction_violations(run, size)
        self.assertEqual({code for code, _ in violations}, {"AF-FUN-BUILD-VISUAL"}, violations)
        self.assertTrue(all("final-mockups" in msg for _, msg in violations), violations)
        for plan_file in (run / "page-images").glob("*/desktop-wireframe/section-plan.json"):
            ids = [i for sec in json.loads(plan_file.read_text()) for i in sec["image_slot_ids"]]
            self.assertEqual(len(ids), len(set(ids)), plan_file)  # renumbering kept every id unique
        main = json.loads((run / "page-images" / "main" / "desktop-wireframe" / "section-plan.json").read_text())
        self.assertEqual([len(sec["image_slot_ids"]) for sec in main], [1] * 12)  # 6, 7, 11 are no longer empty

    def test_size_3(self):
        self.check_size(3)

    def test_size_5(self):
        self.check_size(5)

    def test_size_7(self):
        self.check_size(7)


class RecordFinalMockups(unittest.TestCase):
    """G-4 (defect A): --record-final-mockups merges the closed final-mockups records into the receipt, so
    the real P7 prover sees no AF-FUN-BUILD-VISUAL. It draws nothing and spends nothing."""

    run_tool = LegacyPageImagesTests.run_tool

    def setUp(self):
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.remove, str(SCRIPTS))
        import prove_sf_build
        self.build = prove_sf_build
        proc, out = self.run_tool({**LEDGER, "funnel_size": 3})  # stub run: no paid call
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.run_dir = out.parent / "run"
        self.run_dir.mkdir()
        out.rename(self.run_dir / "page-images")
        self.base = self.run_dir / "page-images"
        self.pages = sorted(json.loads((self.base / "page-images-receipt.json").read_text())["pages"])

    def plant(self, skip=(), images=("a.png",)):
        for slug in self.pages:
            if slug not in skip:
                d = self.base / slug / "final-mockups"
                d.mkdir(parents=True, exist_ok=True)
                (d / "stage-executor-record.json").write_text(json.dumps({"images": list(images)}))

    def record(self):
        return subprocess.run([sys.executable, str(TOOL), "--record-final-mockups", "--out-dir", str(self.base)],
                              capture_output=True, text=True)

    def visual(self):
        return [v for v in self.build.visual_direction_violations(self.run_dir, 3) if v[0] == "AF-FUN-BUILD-VISUAL"]

    def test_before_the_mode_the_prover_refuses_and_after_it_passes(self):
        self.plant()
        self.assertTrue(self.visual())  # the control: the records alone do not certify
        proc = self.record()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.visual(), [])

    def test_a_page_without_a_record_exits_2_naming_it_and_leaves_the_receipt_alone(self):
        self.plant(skip=("upsell",))
        before = (self.base / "page-images-receipt.json").read_bytes()
        proc = self.record()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("upsell", proc.stderr)
        self.assertNotIn("main", proc.stderr)
        self.assertEqual((self.base / "page-images-receipt.json").read_bytes(), before)

    def test_a_record_with_no_images_is_refused(self):
        self.plant(images=())
        self.assertEqual(self.record().returncode, 2)

    def test_a_record_changed_after_the_mode_ran_fails_on_the_sha256(self):
        self.plant()
        self.assertEqual(self.record().returncode, 0)
        (self.base / "main" / "final-mockups" / "stage-executor-record.json").write_text('{"images": ["b.png"]}')
        self.assertTrue(any("sha256" in msg for _, msg in self.visual()), self.visual())

    def test_the_mode_needs_no_provider_flag_and_makes_no_subprocess_call(self):
        self.plant()
        spec = importlib.util.spec_from_file_location("legacy_images_record", TOOL)
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        with mock.patch.object(tool.subprocess, "run", side_effect=AssertionError("spawned")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main(["--record-final-mockups", "--out-dir", str(self.base)]), 0)


FAKE_ADAPTER = """#!/usr/bin/env python3
import json, os
print(json.dumps({"state": "success", "data": {"source": "fake", "changed": True, "routes": {
    "Text to Image": os.environ["FAKE_LATEST"] + "-text-to-image",
    "Image to Image": os.environ["FAKE_LATEST"] + "-image-to-image"}}}))
"""


class ImageModelResolvedThroughSkill66(unittest.TestCase):
    """IMG-19: the tool holds no model id; the paid model is Skill 66's default, resolved once per run."""

    def setUp(self):
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.remove, str(SCRIPTS))
        spec = importlib.util.spec_from_file_location("legacy_downsell_images_under_test", TOOL)
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        (self.root / "ledger.json").write_text(json.dumps(LEDGER))

    def run_main(self, *extra):
        """main() with every subprocess stubbed (no paid call); returns (exit code, stderr, argv list)."""
        seen, real = [], subprocess.run

        def fake_run(cmd, **kw):
            if not pathlib.Path(cmd[1]).name.startswith(("build_production_request", "stage_executor")):
                return real(cmd, **kw)  # Skill 66's own call to the Skill 74 adapter is real
            seen.append(list(cmd))
            if "--out" in cmd:  # the real builder writes the request the tool now reads back to bind slots
                (pathlib.Path(kw["cwd"]) / cmd[cmd.index("--out") + 1]).write_text('{"sections": []}')
            return subprocess.CompletedProcess(cmd, 0, "", "")
        err = io.StringIO()
        with mock.patch.object(self.tool.subprocess, "run", fake_run), contextlib.redirect_stderr(err):
            code = self.tool.main(["--ledger", str(self.root / "ledger.json"), "--skill71-root", str(SKILL71),
                                   "--brand-file", str(BRAND), "--brand-owner", "blackceo",
                                   "--out-dir", str(self.root / "out"), "--page", "downsell", *extra])
        return code, err.getvalue(), seen

    def models(self, seen):
        return [c[c.index("--model") + 1] for c in seen if "--model" in c]

    def test_the_source_holds_no_hard_coded_model_id(self):
        self.assertNotIn("gpt-image-2-6/sunburst-image-to-image", TOOL.read_text(encoding="utf-8"))

    def test_changing_the_skill66_default_changes_the_model_in_every_production_request(self):
        adapter = self.root / "kie_live_adapter.py"  # Skill 74 `latest-family`, the way Skill 66 asks it
        adapter.write_text(FAKE_ADAPTER, encoding="utf-8")
        seen_models = []
        for latest in ("gpt-image-8", "gpt-image-9"):
            with mock.patch.dict(os.environ, {"KIE_LIVE_ADAPTER_PATH": str(adapter), "FAKE_LATEST": latest}):
                _, _, seen = self.run_main("--image-provider", "kie", "--allow-paid")
            models = self.models(seen)
            self.assertEqual(models, [f"{latest}-image-to-image"] * 3)  # one build per stage
            seen_models.append(models[0])
        self.assertNotEqual(*seen_models)

    def test_skill66_selector_missing_refuses_and_builds_nothing(self):
        empty = self.root / "no-skill66"
        empty.mkdir()
        source = (REPO / "shared-utils" / "signature_launch" / "image_model.py").read_text(encoding="utf-8")
        broken = self.root / "image_model.py"
        broken.write_text("\n".join(f"SKILL66_ROOT = Path({str(empty)!r})" if ln.startswith("SKILL66_ROOT =") else ln
                                    for ln in source.splitlines()), encoding="utf-8")
        real = importlib.util.spec_from_file_location
        redirect = lambda name, path, *a, **k: real(name, broken if name == "signature_launch_image_model" else path, *a, **k)
        with mock.patch.object(self.tool.importlib.util, "spec_from_file_location", redirect):
            code, err, seen = self.run_main("--image-provider", "kie", "--allow-paid")
        self.assertEqual(code, 2)
        self.assertIn("Skill 66 did not resolve", err)
        self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
