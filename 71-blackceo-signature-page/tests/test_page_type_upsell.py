#!/usr/bin/env python3
"""The upsell page type (Skill 80, page roles upsell_1 and upsell_2) goes through Skill 71's
own pipeline: an eight-section copy form, a per-form wireframe layout reference, the page
role in the Design Board, and wireframes and mockups with desktop and mobile review PDFs.

Pins:
  - the section-count check accepts the eight upsell sections and refuses 12, 7 and 9;
  - form_of / style_reference know the upsell form and its two Drive style references;
  - the builder turns Skill 80's validated copy plus its result bundle into 8 request
    sections (a CTA, the exact terms line and the decline link on every one) and refuses a
    bundle with no terms, or a copy with a missing section;
  - wireframe prompts carry the page type's build-spec lines (CTA stack, order-confirmed
    strip, what band, reasons band) in the client's colours;
  - mockup prompts carry the same lines through the section layout, plus the hypersaturated
    colour blocks and the design style;
  - the free preflight passes for desktop-wireframe, mobile-tablet and visual-mockup;
  - the Design Board resolves the upsell page role from the run;
  - eight stub images per platform combine into desktop and mobile review PDFs;
  - the launch context maps the upsell copy profile to copy_version upsell;
  - the page-type runner refuses a role that disagrees with its bundle.
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
from board_fixture import SPEC, make_run, png  # noqa: E402
from brand_fixture import give_blackceo_colors  # noqa: E402
import test_section_count as tsc  # noqa: E402

ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
SKILL80 = ROOT.parent / "80-signature-upsell"
FIX80 = SKILL80 / "components/80-signature-upsell/fixtures"
COPY_1 = FIX80 / "copy-upsell1-public.valid.json"
COPY_2 = FIX80 / "copy-upsell2-public.valid.json"
BUNDLE_1 = SKILL80 / "examples/upsell-result-bundle-upsell1.example.json"
BUNDLE_2 = SKILL80 / "examples/upsell-result-bundle-upsell2-from-downsell1.example.json"
PROFILE = SKILL80 / "components/80-signature-upsell/profiles/upsell-profile.json"
STAGES = ("desktop-wireframe", "mobile-tablet", "visual-mockup")
exe, builder = tsc.exe, tsc.builder
wf = builder.wireframe_spec
UPSELL = [str(i) for i in range(1, 9)]
needs_skill80 = unittest.skipUnless(COPY_1.is_file() and BUNDLE_1.is_file(),
                                    "Skill 80 is not installed beside Skill 71")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cli(script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                          capture_output=True, text=True)


def upsell_request(stage, run, copy=COPY_1, bundle=BUNDLE_1):
    spec = load(exe.SPEC_DIR / "upsell-v6.json")
    sections = builder.sections_from_copy_json(load(copy), load(bundle), spec, {})
    return builder.build(stage, "upsell", "", {}, {}, [], "STUB-NO-MODEL", "", run, sections=sections)


class SpecTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        give_blackceo_colors(self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, ids):
        request = {"copy_version": "upsell", "sections": tsc.sections(ids)}
        return exe.check_section_count(self.run, request, True)

    def test_eight_sections_pass_and_other_counts_are_refused(self):
        self.assertEqual(self.check(UPSELL)[1], UPSELL)
        for ids in (tsc.STANDARD, UPSELL[:7], UPSELL + ["9"]):
            with self.assertRaises(exe.ExecutorError) as ctx:
                self.check(ids)
            self.assertIn("8 canonical", str(ctx.exception))
            self.assertIn("never band-compress", str(ctx.exception))

    def test_spec_names_both_page_roles_and_pins_the_skill_80_profile(self):
        spec = load(exe.SPEC_DIR / "upsell-v6.json")
        self.assertEqual(spec["page_roles"], ["upsell_1", "upsell_2"])
        self.assertEqual(spec["sequence"], UPSELL)
        self.assertEqual(spec["cta_map"]["forbidden_in_sections"], [])
        if PROFILE.is_file():
            self.assertEqual(spec["source"]["sha256"], hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
                             "the upsell profile changed: re-check upsell-v6.json against it")
            self.assertEqual(len(load(PROFILE)["sections"]), len(spec["sections"]))

    def test_form_and_style_references(self):
        self.assertEqual(wf.form_of({"copy_version": "upsell"}, strict=True), "upsell")
        desktop = wf.style_reference("desktop-wireframe", "upsell")
        mobile = wf.style_reference("mobile-tablet", "upsell")
        self.assertEqual((desktop["name"], mobile["name"]), ("chatgpt-wireframe-1", "chatgpt-wireframe-4"))
        self.assertIn("UPSELL MOBILE", mobile["extra_rule"])

    def test_launch_context_maps_the_upsell_copy_profile(self):
        import launch_context
        self.assertEqual(launch_context.COPY_PROFILE_VERSION["signature-upsell-eight-section"], "upsell")
        self.assertEqual(launch_context.COPY_PROFILE_VERSION["standard"], "standard")


@needs_skill80
class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        give_blackceo_colors(self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def test_eight_sections_each_with_cta_terms_and_decline(self):
        request = upsell_request("visual-mockup", self.run)
        terms = load(BUNDLE_1)["page_plan"]["disclosure"]["text"]
        sections = request["sections"]
        self.assertEqual([s["section_id"] for s in sections], UPSELL)
        self.assertEqual(request["copy_version"], "upsell")
        for s in sections:
            self.assertTrue(s["cta"], s["section_id"])
            self.assertEqual(s["copy"].splitlines()[-1], terms, s["section_id"])
            self.assertEqual(s["decline"], "No thanks - continue without this extra")
            self.assertTrue(s["slots"], "one planned image slot per section")
        self.assertIn("Your original purchase is confirmed", sections[0]["copy"])
        reasons = [l for l in sections[7]["copy"].splitlines() if l[:3] in [f"{n}. " for n in range(1, 8)]]
        self.assertEqual(len(reasons), 7, "seven numbered reasons")
        names = " ".join(s["section_name"] for s in sections)
        self.assertNotIn("Big Bold", names)
        self.assertNotIn("benefit", names.lower())

    def test_upsell_2_builds_the_same_shape_with_its_own_terms(self):
        if not (COPY_2.is_file() and BUNDLE_2.is_file()):
            self.skipTest("upsell 2 fixtures absent")
        request = upsell_request("desktop-wireframe", self.run, COPY_2, BUNDLE_2)
        self.assertEqual(len(request["sections"]), 8)
        self.assertIn("USD 47.00 today", request["sections"][0]["terms"])
        self.assertEqual(len(request["sections"][0]["ack"]), 2, "both entry-path acknowledgements")

    def test_refuses_a_bundle_without_terms_and_a_copy_with_a_missing_section(self):
        spec = load(exe.SPEC_DIR / "upsell-v6.json")
        bundle = load(BUNDLE_1)
        bundle["page_plan"]["disclosure"].pop("text")
        with self.assertRaises(builder.BuildError) as ctx:
            builder.sections_from_copy_json(load(COPY_1), bundle, spec, {})
        self.assertIn("disclosure.text", str(ctx.exception))
        copy = load(COPY_1)
        copy["sections"].pop(2)
        with self.assertRaises(builder.BuildError) as ctx:
            builder.sections_from_copy_json(copy, load(BUNDLE_1), spec, {})
        self.assertIn("missing ['3']", str(ctx.exception))
        copy = load(COPY_1)
        copy["sections"][4]["cta"] = None
        with self.assertRaises(builder.BuildError) as ctx:
            builder.sections_from_copy_json(copy, load(BUNDLE_1), spec, {})
        self.assertIn("CTA in every section", str(ctx.exception))

    def prompts(self, stage, width):
        request = upsell_request(stage, self.run)
        request["_brand_block"] = exe.require_brand_colors(self.run)
        request["_hypersat"] = exe.hypersaturation.roles_for_run(self.run)
        exe.resolve_design_style(self.run, request)
        return request, {i: exe.stage_prompt(stage, s, i, width, request, "3:2")
                         for i, s in enumerate(request["sections"], 1)}

    def test_wireframe_prompts_carry_the_page_type_lines_in_client_colours(self):
        for stage, width in (("desktop-wireframe", 1440), ("mobile-tablet", 390)):
            request, prompts = self.prompts(stage, width)
            terms = request["sections"][0]["terms"]
            for i, prompt in prompts.items():
                self.assertIn("UPSELL CTA STACK", prompt, i)
                self.assertIn(terms, prompt, i)
                self.assertIn("No thanks - continue without this extra", prompt, i)
                self.assertIn("BRAND COLORS", prompt, i)
                self.assertIn("a filled primary-colour", prompt, i)
                self.assertIn("never colourless", prompt, i)
            self.assertIn("ORDER-CONFIRMED STRIP", prompts[1])
            self.assertIn("WHO BAND", prompts[6])
            self.assertIn("WHAT BAND", prompts[7])
            self.assertIn("REASONS BAND", prompts[8])
            self.assertIn('"SECTION 8"', prompts[8])
            self.assertNotIn("ORDER-CONFIRMED STRIP", prompts[2])
        self.assertIn("UPSELL DESKTOP", self.prompts("desktop-wireframe", 1440)[1][1])
        self.assertIn("UPSELL MOBILE", self.prompts("mobile-tablet", 390)[1][1])

    def test_mockup_prompts_carry_the_page_type_lines_colour_system_and_style(self):
        _request, prompts = self.prompts("visual-mockup", 1440)
        for needle in ("UPSELL CTA STACK", "PAGE COLOR SYSTEM", "circle"):
            self.assertIn(needle, prompts[7])
        self.assertIn("WHAT BAND", prompts[7])
        self.assertIn("REASONS BAND", prompts[8])

    def test_composition_varies_across_the_eight_sections(self):
        request = upsell_request("visual-mockup", self.run)
        treatments = [r["slots"][0]["treatment"] for r in exe.composition.assign_treatments(
            request["sections"], exe.request_cues(request))]
        self.assertEqual(len(treatments), 8)
        self.assertGreaterEqual(len(set(treatments)), 5)
        self.assertTrue(all(a == "split" or a != b for a, b in zip(treatments, treatments[1:])))

    def test_every_section_lands_in_the_prompt_band_with_design_prose(self):
        spec = load(exe.SPEC_DIR / "upsell-v6.json")
        for stage in ("desktop-wireframe", "visual-mockup"):
            sections = builder.sections_from_copy_json(load(COPY_1), load(BUNDLE_1), spec, {})
            request = builder.build(stage, "upsell", "", {}, tsc.design_prose(), [],
                                    tsc.REAL_MODEL, "", self.run, sections=sections)
            budget = request["metadata"]["char_budget"]
            self.assertGreaterEqual(budget["min_seen"], budget["target"], stage)
            self.assertLessEqual(budget["max_seen"], budget["max"], stage)


@needs_skill80
class RunTests(unittest.TestCase):
    """A run folder the way the wrapper stages it: copy source, intake, page role."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        (self.run / "copy.json").write_text(COPY_1.read_text(encoding="utf-8"), encoding="utf-8")
        (self.run / "page-request.json").write_text(json.dumps({"page_role": "upsell_1"}))
        (self.run / "intake.json").write_text(json.dumps(
            {"brand_owner": "blackceo", "brand_file": "assets/brand/blackceo-brand.json",
             "copy_version": "upsell", "design_style": "B", "design_style_source": "client_choice"}))

    def tearDown(self):
        self.tmp.cleanup()

    def build_all(self):
        for stage in STAGES:
            proc = cli("build_production_request.py", "--copy-version", "upsell", "--copy-json",
                       COPY_1, "--bundle", BUNDLE_1, "--stage", stage, "--out",
                       self.run / f"production-request-{stage}.json", "--run-dir", self.run,
                       "--model", "STUB-NO-MODEL")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_free_preflight_for_the_three_stages(self):
        self.build_all()
        for stage in STAGES:
            proc = cli("stage_executor.py", self.run, "--preflight", "--stages", stage,
                       "--request", f"production-request-{stage}.json")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("PREFLIGHT_SECTIONS copy_version=upsell sections=8 "
                          "canonical_ids=1,2,3,4,5,6,7,8", proc.stdout)
            self.assertNotIn("REFUSED", proc.stdout)
            if stage != "visual-mockup":
                self.assertIn("form=upsell", proc.stdout)
                self.assertIn("chatgpt-wireframe", proc.stdout)

    def test_section_count_checks_the_request_against_the_skill_80_copy(self):
        self.build_all()
        copy = load(self.run / "copy.json")
        copy["sections"].pop()
        (self.run / "copy.json").write_text(json.dumps(copy))
        proc = cli("stage_executor.py", self.run, "--preflight", "--stages", "desktop-wireframe",
                   "--request", "production-request-desktop-wireframe.json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("copy source", proc.stdout)

    def test_design_board_resolves_the_upsell_page_role(self):
        request = upsell_request("visual-mockup", self.run)
        board_run = self.run / "board"
        for section in request["sections"]:
            for slot in section["slots"]:
                slot["file"] = f"inputs/{section['section_id']}-{slot['slot_id']}.png"
                png(board_run / slot["file"])
        make_run(board_run, role="upsell_1", base_request=request)
        proc = cli("stage_executor.py", board_run, "--preflight", "--stages", "design-board")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PREFLIGHT design-board upsell_1", proc.stdout)
        self.assertIn("slots=8", proc.stdout)
        # a board for another role than the run's is refused by name
        wrong = json.loads((board_run / "production-request.json").read_text())
        wrong["design_board"]["page_role"] = "thank_you"
        (board_run / "production-request.json").write_text(json.dumps(wrong))
        proc = cli("stage_executor.py", board_run, "--preflight", "--stages", "design-board")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("differs from the run's declared page role", proc.stdout)

    def test_eight_stub_sections_per_platform_combine_into_review_pdfs(self):
        self.build_all()
        proc = cli("stage_executor.py", self.run, "--stages", "visual-mockup",
                   "--request", "production-request-visual-mockup.json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(len(list((self.run / "visual-mockup" / "desktop").glob("part-*.png"))), 8)
        self.assertEqual(len(list((self.run / "visual-mockup" / "mobile").glob("part-*.png"))), 8)
        proc = cli("combine_review_pdf.py", self.run, "--stage", "visual-mockup", "--expect", 8)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        pdfs = sorted(p.name for p in (self.run / "review-pdfs").glob("*.pdf"))
        # the clear-labels names: page role, device and kind in every review PDF name
        self.assertEqual(pdfs, ["upsell-1_DESKTOP_MOCKUPS-VISUAL.pdf", "upsell-1_MOBILE_MOCKUPS-VISUAL.pdf"])

    def test_the_runner_refuses_a_role_that_disagrees_with_its_bundle(self):
        request = self.run / "req.json"
        request.write_text(json.dumps({"page_role": "upsell_2"}))
        common = ["--copy-json", COPY_1, "--bundle", BUNDLE_1, "--request", request,
                  "--launch-record", request, "--route-graph", request, "--brand-file", request,
                  "--brand-owner", "x", "--image-cap", 1, "--run-dir", self.run / "out"]
        proc = cli("run_page_type.py", "--copy-version", "upsell", *common)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("both must agree", proc.stdout)
        self.assertFalse((self.run / "out").exists())
        proc = cli("run_page_type.py", "--copy-version", "standard", *common)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not a page type", proc.stdout)


if __name__ == "__main__":
    unittest.main()
