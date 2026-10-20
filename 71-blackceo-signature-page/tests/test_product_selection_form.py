#!/usr/bin/env python3
"""The order page (page_role product_selection) as a third copy form of the one pipeline.

Free: no provider call. Pins that the product-selection form (5 sections, one button per package
card) is accepted by the same section-count check, request builder, wireframe build spec,
composition roles, height floor and Design Board as the landing forms, that nothing landing-only
leaks into it, and that the landing forms behave exactly as before.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand_fixture import give_blackceo_colors  # noqa: E402
import board_fixture as bf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "copy_examples"
PY = sys.executable
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exe = load("stage_executor")
builder = load("build_production_request")
forms = load("copy_forms")
wspec = load("wireframe_spec")
vwire = load("validate_wireframe")
comp = load("composition")
vcopy = load("validate_copy_structure")

IDS = ["1", "2", "3", "4", "5"]
MANUSCRIPT = (FIXTURES / "product-selection-path-b.md").read_text(encoding="utf-8")
SLOTS = {"3": [{"slot_id": f"PKG-{i}", "aspect_ratio": "1:1", "mask": "circle",
                "art_direction": f"package {i} image"} for i in (1, 2, 3)]}
BUTTONS = ["Choose TEST ONLY Essential", "Choose TEST ONLY Professional", "Choose TEST ONLY Elite"]


def stub_request(run, stage="visual-mockup", manuscript=MANUSCRIPT, slots=SLOTS):
    return builder.build(stage, "product-selection", manuscript, slots, {}, [], "STUB-NO-MODEL", "", run)


class FormTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        give_blackceo_colors(self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def test_registry_and_spec(self):
        self.assertEqual(forms.FORMS[:3], ("standard", "long-form", "product-selection"))  # later forms register after these
        spec = forms.load_spec("product-selection")
        self.assertEqual(spec["sequence"], IDS)
        self.assertEqual(spec["page_role"], "product_selection")
        self.assertEqual(forms.form_for_role("product_selection"), "product-selection")
        self.assertIsNone(forms.form_for_role("landing"))
        self.assertEqual(forms.norm("Product Selection"), "product-selection")
        self.assertEqual(exe.SPEC_FILES, forms.SPEC_FILES)

    def test_manuscript_passes_its_own_spec(self):
        units, order, notes = vcopy.parse_manuscript(MANUSCRIPT)
        rep = vcopy.validate(units, order, notes, forms.load_spec("product-selection"))
        self.assertEqual(rep.fails, [])
        self.assertEqual(order, IDS)

    def test_one_package_or_a_button_in_the_wrong_section_fails_the_spec(self):
        spec = forms.load_spec("product-selection")
        one = MANUSCRIPT.split("### Package: TEST ONLY Professional")[0] + "## Section 4:" + MANUSCRIPT.split("## Section 4:", 1)[1]
        units, order, notes = vcopy.parse_manuscript(one)
        self.assertTrue(any("package buttons" in f for f in vcopy.validate(units, order, notes, spec).fails))
        stray = MANUSCRIPT.replace("## Section 5: Questions and trust\n", "## Section 5: Questions and trust\n\n[CTA BUTTON: Buy now]\n")
        units, order, notes = vcopy.parse_manuscript(stray)
        self.assertTrue(any("forbids here" in f for f in vcopy.validate(units, order, notes, spec).fails))

    def test_section_count_accepts_five_and_refuses_twelve_for_this_form(self):
        ok = exe.check_section_count(self.run, {"copy_version": "product-selection",
                                                "sections": [{"section_id": i} for i in IDS]}, paid=True)
        self.assertEqual(ok[:2], ("product-selection", IDS))
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.check_section_count(self.run, {"copy_version": "product-selection", "sections": [
                {"section_id": str(i)} for i in range(1, 13)]})
        self.assertIn("5 canonical", str(ctx.exception))
        with self.assertRaises(exe.ExecutorError):  # and five sections are not a Standard page
            exe.check_section_count(self.run, {"copy_version": "standard",
                                               "sections": [{"section_id": i} for i in IDS]})
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.check_section_count(self.run, {"copy_version": "short-form", "sections": []})
        self.assertIn("product-selection", str(ctx.exception))

    def test_builder_emits_the_five_sections_with_neutral_names_and_one_button_per_card(self):
        request = stub_request(self.run)
        by_id = {s["section_id"]: s for s in request["sections"]}
        self.assertEqual(list(by_id), IDS)
        self.assertEqual([s["section_name"] for s in request["sections"]],
                         ["Bridge headline", "How to choose", "Packages", "Compare", "Questions and trust"])
        self.assertEqual(by_id["3"]["cta_labels"], BUTTONS)
        self.assertIsNone(by_id["3"]["cta"])
        self.assertTrue(all(not by_id[i].get("cta") and "cta_labels" not in by_id[i] for i in "1245"))
        self.assertEqual([by_id[i]["ground"] for i in IDS], ["hero", "light", "dark", "light", "dark"])
        self.assertEqual(by_id["3"]["composition_role"], "selection-packages")
        self.assertEqual(request["metadata"]["canonical_ids"], IDS)

    def test_two_buttons_in_one_landing_section_are_still_refused(self):
        text = (FIXTURES / "standard-path-b.md").read_text(encoding="utf-8")
        text = text.replace("## Section 2:", "[CTA BUTTON: One]\n[CTA BUTTON: Two]\n\n## Section 2:", 1)
        with self.assertRaises(builder.BuildError) as ctx:
            builder.build("visual-mockup", "standard", text, {}, {}, [], "STUB-NO-MODEL", "", self.run)
        self.assertIn("one button per section", str(ctx.exception))

    def test_a_manuscript_for_another_form_is_refused_by_name(self):
        text = (FIXTURES / "standard-path-b.md").read_text(encoding="utf-8")
        with self.assertRaises(builder.BuildError) as ctx:
            builder.build("visual-mockup", "product-selection", text, {}, {}, [], "STUB-NO-MODEL", "", self.run)
        self.assertIn("section count", str(ctx.exception))

    def test_every_section_is_in_the_prompt_band_for_every_stage(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_section_count import design_prose, REAL_MODEL
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup", "final-mockups"):
            request = builder.build(stage, "product-selection", MANUSCRIPT, SLOTS, design_prose(), [],
                                    REAL_MODEL, "", self.run)
            budget = request["metadata"]["char_budget"]
            self.assertGreaterEqual(budget["min_seen"], budget["target"], stage)
            self.assertLessEqual(budget["max_seen"], budget["max"], stage)

    def prompt(self, stage, index, width):
        request = stub_request(self.run, stage)
        request["_brand_block"] = exe.require_brand_colors(self.run)
        request["_hypersat"] = exe.hypersaturation.roles_for_run(self.run)
        section = request["sections"][index - 1]
        return exe.stage_prompt(stage, section, index, width, request, "16:9")

    def test_wireframe_prompt_is_the_annotated_brand_colour_build_spec_for_this_page(self):
        text = self.prompt("desktop-wireframe", 3, 1440)
        for want in ("an order page (package selection)", "FORM: Product Selection", 'exactly "SECTION 3"',
                     'exactly "PACKAGES"', "ORDER PAGE LAYOUT, SECTION 3 (desktop)", "radio group",
                     "none pre-selected", "BRAND COLORS", "never grey line work",
                     'plate 1 labelled "IMAGE 1:1', "one button per package card",
                     '"Choose TEST ONLY Essential" | "Choose TEST ONLY Professional"',
                     "SLOTS PKG-1 1:1 card-overlaps-photo, PKG-2 1:1 card-overlaps-photo"):
            self.assertIn(want, text)
        self.assertNotIn("landing page", text)            # nothing landing-only leaks in
        self.assertNotIn("exactly 7 badges", text)
        self.assertNotIn("FOUNDER LETTER", text)
        mobile = self.prompt("mobile-tablet", 4, 390)
        self.assertIn("ORDER PAGE LAYOUT, SECTION 4 (mobile)", mobile)
        self.assertIn("disclosure", mobile)
        self.assertIn("ORDER PAGE MOBILE", mobile)

    def test_landing_prompts_are_unchanged_by_the_new_form(self):
        self.assertEqual(exe.negative_block("visual-mockup"), exe.negative_block("visual-mockup", steps=True))
        self.assertIn("Do not mis-number the 7 steps", exe.negative_block("final-mockups"))
        self.assertNotIn("7 steps", exe.negative_block("final-mockups", steps=False))
        section = {"section_id": "2", "section_name": "First problem", "copy": "A sentence.", "cta": "Go"}
        block = wspec.prompt_block("desktop-wireframe", section, 2, 12, 1440, {"copy_version": "standard"})
        self.assertIn("for a landing page:", block)
        self.assertIn("STANDARD DESKTOP", block)

    def test_style_references_are_the_drive_files_one_and_four(self):
        request = {"copy_version": "product-selection"}
        self.assertTrue(wspec.reference_urls("desktop-wireframe", request)[0].endswith("chatgpt-wireframe-1.png"))
        self.assertTrue(wspec.reference_urls("mobile-tablet", request)[0].endswith("chatgpt-wireframe-4.png"))
        self.assertEqual(wspec.form_of({"metadata": {"copy_version": "Product Selection"}}), "product-selection")
        with self.assertRaises(wspec.SpecError):
            wspec.reference_urls("desktop-wireframe", {"copy_version": "product-selection",
                                                       "references": ["set-for-life-desktop-wireframe.png"]})

    def test_composition_roles_and_variety(self):
        request = stub_request(self.run)
        resolved = comp.assign_treatments(request["sections"], {})
        self.assertEqual([r["role"] for r in resolved], ["selection-bridge", "selection-guide",
                         "selection-packages", "selection-compare", "selection-trust"])
        self.assertEqual({e["treatment"] for e in resolved[2]["slots"]}, {"card-overlaps-photo"})
        for role in comp.library()["roles"]:
            for tid in [role["default"], *role["alternates"]]:
                self.assertIn(tid, comp.treatments())

    def test_typed_references_come_only_from_this_forms_rows(self):
        def row(i, form):
            return {"id": i, "type": "wireframe", "viewport": "desktop", "form": form, "sections": ["3"],
                    "url": f"https://example.invalid/{i}.png", "traits": []}
        catalog = {"rows": [row("std", "standard"), row("ps", "product-selection")]}
        pick = lambda form: [r["id"] for r in comp.typed_references("desktop-wireframe", "desktop", "3", ["split"], catalog, form)]
        self.assertEqual(pick("product-selection"), ["ps"])
        self.assertEqual(pick("standard"), ["std"])
        self.assertEqual(pick(None), ["std"])

    def test_height_floor_is_the_forms_own_and_labelled_derived(self):
        (self.run / "intake.json").write_text(json.dumps({"copy_version": "product-selection"}))
        self.assertEqual(vwire.height_floor("desktop-wireframe", self.run), 6973)
        self.assertEqual(round(16736 / 12 * 5), 6973)
        self.assertIn("Derived", forms.load_spec("product-selection")["wireframe"]["height_floor_note"])
        (self.run / "intake.json").write_text(json.dumps({"copy_version": "standard"}))
        self.assertEqual(vwire.height_floor("desktop-wireframe", self.run), 16736)
        (self.run / "intake.json").write_text("{}")
        self.assertEqual(vwire.height_floor("desktop-wireframe", self.run), 16736)
        self.assertIsNone(vwire.height_floor("mobile-tablet", self.run))


class PreflightTests(unittest.TestCase):
    """stage_executor --preflight on a request built from the form's own manuscript."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        (self.run / "intake.json").write_text(json.dumps({
            "brand_owner": "blackceo", "brand_file": "assets/brand/blackceo-brand.json",
            "copy_version": "product-selection", "design_style": "B", "test_run": True}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_preflight_for_the_three_stages(self):
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            request = stub_request(self.run, stage)
            (self.run / f"req-{stage}.json").write_text(json.dumps(request))
            proc = subprocess.run([PY, str(SCRIPTS / "stage_executor.py"), str(self.run), "--preflight",
                                   "--stages", stage, "--request", f"req-{stage}.json"],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("PREFLIGHT_SECTIONS copy_version=product-selection sections=5 canonical_ids=1,2,3,4,5",
                          proc.stdout)
            self.assertIn("PREFLIGHT_CTA " + stage + " 3 -> " + " | ".join(BUTTONS), proc.stdout)
            self.assertEqual(proc.stdout.count("PREFLIGHT " + stage), 5 * (2 if stage == "visual-mockup" else 1))
            if stage != "visual-mockup":
                self.assertIn("form=product-selection", proc.stdout)
            else:
                self.assertIn("ground=dark", proc.stdout)

    def test_a_twelve_section_request_is_refused_for_this_form(self):
        request = stub_request(self.run)
        request["sections"] = [{"section_id": str(i), "section_name": str(i), "copy": "A sentence."}
                               for i in range(1, 13)]
        (self.run / "req.json").write_text(json.dumps(request))
        proc = subprocess.run([PY, str(SCRIPTS / "stage_executor.py"), str(self.run), "--preflight",
                               "--stages", "visual-mockup", "--request", "req.json"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAIL: section count", proc.stdout)
        self.assertIn("5 canonical", proc.stdout)

    def test_stub_run_makes_every_stage_folder_with_five_sections(self):
        for stage, files in (("desktop-wireframe", ["section-%02d.png"]), ("mobile-tablet", ["section-%02d.png"]),
                             ("visual-mockup", ["desktop/part-%02d.png", "mobile/part-%02d.png"])):
            request = stub_request(self.run, stage)
            (self.run / f"req-{stage}.json").write_text(json.dumps(request))
            proc = subprocess.run([PY, str(SCRIPTS / "stage_executor.py"), str(self.run), "--stages", stage,
                                   "--request", f"req-{stage}.json"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            for template in files:
                for n in range(1, 6):
                    self.assertTrue((self.run / stage / (template % n)).is_file(), template % n)
        # one long PDF per stage and the overview boards are form-agnostic: they follow the section count
        for stage in ("desktop-wireframe", "visual-mockup"):
            pdf = subprocess.run([PY, str(SCRIPTS / "combine_review_pdf.py"), str(self.run), "--stage", stage,
                                  "--expect", "5"], capture_output=True, text=True)
            self.assertEqual(pdf.returncode, 0, pdf.stdout + pdf.stderr)
            self.assertIn("5 pages", pdf.stdout)
            board = subprocess.run([PY, str(SCRIPTS / "build_overview_board.py"), str(self.run), "--stage", stage,
                                    "--request", f"req-{stage}.json", "--expect", "5"], capture_output=True, text=True)
            self.assertEqual(board.returncode, 0, board.stdout + board.stderr)


class DesignBoardRoleTests(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="ps-board-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.td, ignore_errors=True))

    def test_a_product_selection_run_has_a_product_selection_board(self):
        run = self.td / "run"
        bf.make_run(run, role="landing")  # a run with the board fixture client's brand colours
        (run / "intake.json").write_text(json.dumps({
            "brand_owner": bf.BRAND, "brand_file": "inputs/brand.json", "copy_version": "product-selection"}))
        request = builder.build("visual-mockup", "product-selection", MANUSCRIPT, SLOTS, {}, [], "STUB-NO-MODEL", "", run)
        for i, slot in enumerate(request["sections"][2]["slots"], 1):
            bf.png(run / "inputs" / f"pkg{i}.png")
            slot["file"] = f"inputs/pkg{i}.png"
        board = bf.design_board
        self.assertEqual(board.declared_role(run), "product_selection")  # from the form alone: no launch block
        request["design_board"] = dict(bf.SPEC)
        plan = board.plan(run, request)
        self.assertEqual(plan["role"], "product_selection")
        self.assertIn("icons", plan["expected"]["required_blocks"])
        self.assertNotIn("aesthetic", plan["expected"]["required_blocks"])
        self.assertEqual(len(plan["slots"]), 3)  # one image per package card
        self.assertIn("package", board.ROLE_EMPHASIS["product_selection"])
        # a request that names another role for this run is refused
        request["design_board"]["page_role"] = "landing"
        with self.assertRaises(board.BoardError):
            board.plan(run, request)


if __name__ == "__main__":
    unittest.main()
