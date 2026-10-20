#!/usr/bin/env python3
"""A page type's own canonical sections reach every image stage: the thank-you page.

The thank-you page (page_role thank_you) is not a landing page. Its five sections live in
references/copy-specs/thank-you-v1.json (proposed, pending the owner's approval), read through
scripts/page_role.py, so the pipeline that draws a landing page draws this page the same way:

  - the section-count check accepts exactly the page's 5 sections and refuses a landing-shaped
    12-section request, a short one, and a page role that disagrees with the declared form;
  - the request builder reads the spec, seeds composition role, ground and the one image slot
    (shaped by design style A, B or C), and stamps page_role into the request;
  - the wireframe and mockup prompts carry the page's own structure (a PAGE TYPE STRUCTURE
    block), name it a thank-you page, and never print the landing page's 7-step or landing
    section rules;
  - stage_executor --preflight proves the page free for desktop-wireframe, mobile-tablet and
    visual-mockup and prints page_role, the section count and the blocks present;
  - write_intake, shared_page_service, the stage gate's copy spec, the Design Board and the
    wireframe gate's landing-only height floor all read the same declaration;
  - landing behavior is unchanged (the existing suites pin it).

No paid API is called anywhere in this module.
"""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "copy_examples" / "thank-you-path-b.md"
PY = sys.executable
sys.path.insert(0, str(SCRIPTS))

import page_role  # noqa: E402
import wireframe_spec as w  # noqa: E402
from brand_fixture import give_blackceo_colors  # noqa: E402
from test_section_count import REAL_MODEL, STANDARD, design_prose, sections  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exe = load("stage_executor")
builder = load("build_production_request")
SPEC = json.loads((ROOT / "references" / "copy-specs" / "thank-you-v1.json").read_text(encoding="utf-8"))
IDS = ["1", "2", "3", "4", "5"]
STUB = "STUB-NO-MODEL"


def write_intake(run, **extra):
    data = {"brand_owner": "blackceo", "brand_file": "assets/brand/blackceo-brand.json", **extra}
    (run / "intake.json").write_text(json.dumps(data), encoding="utf-8")


class RunCase(unittest.TestCase):
    """A run dir with the client's brand colours and the fixture manuscript."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / "run"
        (self.run / "copy").mkdir(parents=True)
        (self.run / "copy" / "internal-manuscript.md").write_text(
            FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
        give_blackceo_colors(self.run)
        self.addCleanup(self.tmp.cleanup)

    def build(self, stage="visual-mockup", model=STUB, prose=None, version="thank-you", text=None):
        text = text if text is not None else (self.run / "copy" / "internal-manuscript.md").read_text(
            encoding="utf-8")
        return builder.build(stage, version, text, {}, prose or {}, [], model, "", self.run)

    def preflight(self, stage):
        proc = subprocess.run([PY, str(SCRIPTS / "stage_executor.py"), str(self.run),
                               "--preflight", "--stages", stage], capture_output=True, text=True)
        return proc


class SpecTests(unittest.TestCase):
    def test_the_spec_is_a_copy_spec_of_five_sections_for_the_thank_you_role(self):
        self.assertEqual(SPEC["sequence"], IDS)
        self.assertEqual([s["id"] for s in SPEC["sections"]], IDS)
        self.assertEqual(SPEC["page_role"], "thank_you")
        self.assertEqual(SPEC["copy_version"], "thank-you")
        for entry in SPEC["sections"]:
            self.assertTrue(entry["name"] and entry["framework_name"] and entry["job"], entry["id"])
            self.assertTrue(entry["layout"]["desktop"] and entry["layout"]["mobile"], entry["id"])
            self.assertIn(entry["composition_role"],
                          {r["role"] for r in json.loads(
                              (ROOT / "references" / "composition-treatments.json").read_text())["roles"]})
            self.assertIn(entry["ground"], ("hero", "dark", "light"))

    def test_resolution_by_role_and_version(self):
        self.assertEqual(page_role.spec_for_role("thank_you")["copy_version"], "thank-you")
        for role in ("landing", "product_selection", "checkout", "upsell_1", "downsell_1", "upsell_2"):
            self.assertIsNone(page_role.spec_for_role(role), role)  # no structure yet: legacy path
        self.assertEqual(page_role.copy_versions(), ("standard", "long-form", "thank-you"))
        self.assertIsNone(page_role.load_spec("short-form"))
        self.assertEqual(page_role.spec_ref("thank-you"), "references/copy-specs/thank-you-v1.json")
        self.assertEqual(page_role.spec_ref("standard"), "references/copy-specs/standard-v6.json")
        self.assertEqual(page_role.spec_ref("nope"), "")

    def test_one_image_in_total_and_no_offer_button(self):
        slots = [s for e in SPEC["sections"] for s in e.get("default_slots") or []]
        self.assertEqual(len(slots), SPEC["rules"]["max_images"])
        self.assertEqual(SPEC["rules"]["offer_buttons"], "forbidden")
        self.assertEqual(SPEC["cta_map"]["forbidden_in_sections"], ["2", "4"])
        for sid in SPEC["cta_map"]["forbidden_in_sections"]:
            entry = next(e for e in SPEC["sections"] if e["id"] == sid)
            self.assertEqual(entry["cta"]["standalone"], "forbidden")

    def test_layout_reference_in_skill_82_names_the_same_five_sections(self):
        doc = ROOT.parent / "82-signature-thank-you" / "references" / "wireframe-mockup-layout.md"
        if not doc.is_file():
            self.skipTest("Skill 82 is not in this tree")
        text = doc.read_text(encoding="utf-8")
        for entry in SPEC["sections"]:
            self.assertIn(entry["name"], text, entry["name"])
        self.assertIn("thank-you-v1.json", text)
        self.assertIn("PROPOSED", text)

    def test_copy_structure_validator_reads_the_spec(self):
        def validate(manuscript):
            return subprocess.run(
                [PY, str(SCRIPTS / "validate_copy_structure.py"), str(manuscript),
                 "--spec", str(ROOT / page_role.spec_ref("thank-you"))], capture_output=True, text=True)

        proc = validate(FIXTURE)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("RESULT: PASS", proc.stdout)
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "m.md"
            text = FIXTURE.read_text(encoding="utf-8")
            bad.write_text(text.replace("Own Your Week workbook. Paid.",
                                        "[CTA BUTTON: Buy the bonus]\n\nOwn Your Week workbook. Paid."),
                           encoding="utf-8")
            proc = validate(bad)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("forbids", proc.stdout)  # no button in the order summary
            short = Path(td) / "s.md"
            short.write_text(text.split("## Section 5:")[0], encoding="utf-8")
            proc = validate(short)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("required section 5", proc.stdout)


class SectionCountTests(RunCase):
    def check(self, ids, **request):
        request = dict(request, sections=sections(ids))
        return exe.check_section_count(self.run, request, paid=True)

    def test_five_sections_pass_however_the_role_is_declared(self):
        self.assertEqual(self.check(IDS, page_role="thank_you")[:2], ("thank-you", IDS))
        self.assertEqual(self.check(IDS, copy_version="thank-you")[1], IDS)
        write_intake(self.run, page_role="thank_you")
        self.assertEqual(self.check(IDS)[1], IDS)  # a paid run needs no landing copy_version
        write_intake(self.run, launch={"page_role": "thank_you"})
        self.assertEqual(self.check(IDS)[1], IDS)

    def test_a_landing_shaped_request_for_this_page_is_refused_by_name(self):
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.check(STANDARD, page_role="thank_you")
        message = str(ctx.exception)
        self.assertIn("12 sections", message)
        self.assertIn("5 canonical sections", message)
        self.assertIn("never band-compress", message)

    def test_a_short_request_is_refused_by_name(self):
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.check(IDS[:4], page_role="thank_you")
        self.assertIn("missing ['5']", str(ctx.exception))

    def test_a_role_and_form_that_disagree_are_refused(self):
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.check(STANDARD, page_role="thank_you", copy_version="standard")
        self.assertIn("disagree", str(ctx.exception))
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.check(IDS, page_role="landing", copy_version="thank-you")
        self.assertIn("disagree", str(ctx.exception))

    def test_landing_and_roles_without_a_structure_keep_the_legacy_path(self):
        self.assertEqual(self.check(STANDARD, copy_version="standard")[1], STANDARD)
        self.assertEqual(self.check(STANDARD, copy_version="standard", page_role="product_selection")[1],
                         STANDARD)

    def test_the_copy_source_must_match_the_five_sections(self):
        (self.run / "copy.json").write_text(json.dumps({"sections": [{"id": i} for i in IDS[:4]]}))
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.check(IDS, page_role="thank_you")
        self.assertIn("copy source", str(ctx.exception))


class BuilderTests(RunCase):
    def test_builder_emits_the_five_sections_with_the_spec_names_roles_and_grounds(self):
        request = self.build()
        self.assertEqual([s["section_id"] for s in request["sections"]], IDS)
        self.assertEqual(request["page_role"], "thank_you")
        self.assertEqual(request["copy_version"], "thank-you")
        self.assertEqual(request["metadata"]["page_role"], "thank_you")
        self.assertEqual([s["section_name"] for s in request["sections"]],
                         [e["name"] for e in SPEC["sections"]])
        self.assertEqual([s["composition_role"] for s in request["sections"]],
                         [e["composition_role"] for e in SPEC["sections"]])
        self.assertEqual([s["ground"] for s in request["sections"]], [e["ground"] for e in SPEC["sections"]])
        by_id = {s["section_id"]: s for s in request["sections"]}
        self.assertEqual(by_id["1"]["cta"], "Start here: Own Your Week")
        self.assertIsNone(by_id["2"]["cta"])
        self.assertIsNone(by_id["4"]["cta"])  # no button where the spec forbids one
        self.assertEqual(by_id["5"]["labels"], ["With respect, Marcus Reed"])  # the signature is a label

    def test_one_image_slot_in_total_shaped_by_the_design_style(self):
        shapes = {}
        for style in (None, "A", "B", "C"):
            write_intake(self.run, **({"design_style": style} if style else {}))
            request = self.build()
            slots = [s for sec in request["sections"] for s in sec["slots"]]
            self.assertEqual([s["slot_id"] for s in slots], ["TY-IMG-01"], style)
            shapes[style] = (slots[0].get("shape", "rect"), slots[0]["aspect_ratio"],
                             slots[0].get("treatment"))
        self.assertEqual(shapes, {None: ("rect", "4:3", None), "A": ("rect", "4:3", None),
                                  "B": ("circle", "1:1", "mask-circle"), "C": ("rect", "4:3", None)})

    def test_builder_refuses_a_landing_manuscript_for_this_page_and_the_reverse(self):
        landing = (ROOT / "tests" / "fixtures" / "copy_examples" / "standard-path-b.md").read_text(
            encoding="utf-8")
        with self.assertRaises(builder.BuildError) as ctx:
            self.build(text=landing)
        self.assertIn("5 canonical sections", str(ctx.exception))
        with self.assertRaises(builder.BuildError) as ctx:
            self.build(version="standard")
        self.assertIn("12 canonical sections", str(ctx.exception))
        with self.assertRaises(builder.BuildError):
            self.build(version="short-form")

    def test_the_landing_skeleton_table_never_reaches_this_page(self):
        request = self.build(model=REAL_MODEL, prose=design_prose())
        layouts = " ".join(s["layout"] for s in request["sections"])
        self.assertNotIn("SLOT CANON", layouts)
        for landing_role in ("First problem", "Opening claim", "Founder letter"):
            self.assertNotIn(landing_role, layouts)
        for sid in ("2", "4"):  # a forbidden-button section says so, from the spec
            layout = next(s for s in request["sections"] if s["section_id"] == sid)["layout"]
            self.assertIn("no button", layout)

    def test_every_section_lands_in_the_prompt_band_for_both_mockup_stages(self):
        for stage in ("visual-mockup", "final-mockups"):
            request = self.build(stage=stage, model=REAL_MODEL, prose=design_prose())
            budget = request["metadata"]["char_budget"]
            self.assertGreaterEqual(budget["min_seen"], budget["target"], stage)
            self.assertLessEqual(budget["max_seen"], budget["max"], stage)

    def test_builder_output_passes_a_strict_preflight_prompt_for_prompt(self):
        request = self.build(stage="desktop-wireframe", model=REAL_MODEL, prose=design_prose())
        builder.run_blocks(request, self.run)
        for index, section in enumerate(request["sections"], start=1):
            for _t, width, _h in exe.LAYOUT["desktop-wireframe"]:
                prompt = exe.stage_prompt("desktop-wireframe", section, index, width, request,
                                          "16:9", strict_floor=True)
                self.assertGreaterEqual(len(prompt), 16000)


class PromptTests(RunCase):
    def prompt(self, stage, index, width, request=None):
        request = request or self.build(stage=stage)
        request["_brand_block"] = exe.require_brand_colors(self.run)
        request["_hypersat"] = exe.hypersaturation.roles_for_run(self.run)
        return exe.stage_prompt(stage, request["sections"][index - 1], index, width, request, "16:9")

    def test_every_stage_and_platform_carries_the_pages_own_structure(self):
        for stage, widths in (("desktop-wireframe", (1440,)), ("mobile-tablet", (390,)),
                              ("visual-mockup", (1440, 390)), ("final-mockups", (1440, 390))):
            request = self.build(stage=stage)
            for index in range(1, 6):
                for width in widths:
                    prompt = self.prompt(stage, index, width, request)
                    where = (stage, index, width)
                    self.assertIn("PAGE TYPE STRUCTURE", prompt, where)
                    self.assertIn("this is the thank-you page (5 sections)", prompt, where)
                    self.assertIn("1 image in total and no offer button", prompt, where)
                    if width > 768:
                        self.assertIn("Desktop layout:", prompt, where)
                    else:
                        self.assertIn("Mobile layout:", prompt, where)
                    self.assertNotIn("exactly 7 badges", prompt, where)  # the landing page's 7-step rule
                    self.assertIn("one step label per badge", prompt, where)

    def test_the_wireframe_names_a_thank_you_page_and_never_a_landing_page(self):
        for stage in ("desktop-wireframe", "mobile-tablet"):
            request = self.build(stage=stage)
            width = 390 if stage == "mobile-tablet" else 1440
            first = self.prompt(stage, 1, width, request)
            self.assertIn("annotated build specification for a thank-you page", first)
            self.assertNotIn("build specification for a landing page", first)
            self.assertIn("FORM: Thank-You", first)
            self.assertIn("sheet grammar only", first)  # the reference gives structure, never its sections
            self.assertNotIn("Each pain section", first)
            self.assertNotIn("founder portrait plate", first)
            steps = self.prompt(stage, 4, width, request)
            self.assertIn("between four and six step badges", steps)
            self.assertNotIn("exactly seven step badges", steps)
            for index in (1, 2, 3, 5):
                self.assertNotIn("STEPS —", self.prompt(stage, index, width, request))
        desktop = self.prompt("desktop-wireframe", 3, 1440)
        self.assertIn("THANK-YOU DESKTOP", desktop)
        self.assertIn("exactly one image plate in total", desktop)

    def test_the_wireframe_attaches_the_owner_s_sheet_for_each_platform(self):
        request = self.build()
        request["page_role"] = "thank_you"
        self.assertEqual(w.form_of(request), "thank-you")
        self.assertTrue(w.reference_urls("desktop-wireframe", request)[0].endswith("chatgpt-wireframe-1.png"))
        self.assertTrue(w.reference_urls("mobile-tablet", request)[0].endswith("chatgpt-wireframe-4.png"))
        self.assertEqual(w.reference_urls("visual-mockup", request), [])

    def test_a_landing_request_is_untouched(self):
        landing = {"model": STUB, "copy_version": "standard", "sections": sections(STANDARD),
                   "stage_prompts": {"desktop-wireframe": "{copy}"}}
        landing["_brand_block"] = exe.require_brand_colors(self.run)
        prompt = exe.stage_prompt("desktop-wireframe", landing["sections"][0], 1, 1440, landing, "16:9")
        self.assertNotIn("PAGE TYPE STRUCTURE", prompt)
        self.assertIn("for a landing page", prompt)
        self.assertIn("Do not mis-number the 7 steps", prompt)
        self.assertEqual(w.form_of(landing), "standard")

    def test_page_sections_match_no_landing_reference_sheet(self):
        seen = []
        original = exe.composition.typed_references
        exe.composition.typed_references = lambda stage, platform, sid, used, catalog=None, form=None: seen.append(sid) or []
        try:
            request = self.build()
            resolved = exe.resolve_composition(request["sections"][1], 2, request)
            exe.section_typed_references("desktop-wireframe", 1440, resolved, request["sections"][1])
            landing = {"section_id": "2"}
            exe.section_typed_references("desktop-wireframe", 1440, resolved, landing)
        finally:
            exe.composition.typed_references = original
        self.assertEqual(seen, [None, "2"])  # section 2 here is not landing section 2

    def test_composition_roles_follow_the_page_type_not_the_landing_ids(self):
        request = self.build()
        roles = [r["role"] for r in exe.composition.assign_treatments(request["sections"])]
        self.assertEqual(roles, [e["composition_role"] for e in SPEC["sections"]])
        landing_roles = [exe.composition.section_role(i, "") for i in IDS]
        self.assertNotEqual(roles, landing_roles)  # ids 2, 3, 4 would have been pain sections


class PreflightTests(RunCase):
    def test_free_preflight_for_the_three_image_stages(self):
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            request = self.build(stage=stage)
            (self.run / "production-request.json").write_text(json.dumps(request), encoding="utf-8")
            proc = self.preflight(stage)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            out = proc.stdout
            self.assertRegex(out, r"PREFLIGHT_SECTIONS copy_version=thank-you sections=5 "
                                  r"canonical_ids=1,2,3,4,5 page_role=thank_you ")
            blocks = re.findall(rf"^PREFLIGHT_BLOCKS {stage} \S+ page_role=thank_you blocks=(.+)$", out, re.M)
            self.assertEqual(len(blocks), 5 if stage != "visual-mockup" else 10)
            for line in blocks:
                self.assertIn("PAGE TYPE STRUCTURE", line)
                self.assertIn("COPY", line)
                self.assertIn("BRAND COLORS", line)
            self.assertEqual(out.count("REFUSED"), 0)
            if stage == "visual-mockup":
                self.assertIn("PAGE COLOR SYSTEM", blocks[0])  # hypersaturation is built in
            else:
                self.assertIn("PREFLIGHT_WIREFRAME_REFS", out)
                self.assertIn("form=thank-you", out)

    def test_a_landing_shaped_request_for_this_page_fails_preflight(self):
        request = {"model": STUB, "page_role": "thank_you", "sections": sections(STANDARD)}
        (self.run / "production-request.json").write_text(json.dumps(request), encoding="utf-8")
        proc = self.preflight("visual-mockup")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("FAIL: section count", proc.stdout)
        self.assertIn("5 canonical sections", proc.stdout)

    def test_design_board_and_gate_read_the_same_role_declaration(self):
        board = load("design_board")
        write_intake(self.run, page_role="thank_you", copy_version="thank-you")
        self.assertEqual(board.declared_role(self.run), "thank_you")
        self.assertIn("thank_you", board.ROLE_LABEL)
        gate = load("stage_gate")
        cmd = "python3 scripts/validate_copy_structure.py {run_dir} --spec {copy_spec}"
        resolved, problems = gate.resolve_brand_placeholder(cmd, self.run, "copy", None)
        self.assertEqual(problems, [])
        self.assertIn("references/copy-specs/thank-you-v1.json", resolved)
        write_intake(self.run, copy_version="long-form")
        resolved, _ = gate.resolve_brand_placeholder(cmd, self.run, "copy", None)
        self.assertIn("long-form-v6.json", resolved)
        write_intake(self.run, copy_version="short-form")
        resolved, problems = gate.resolve_brand_placeholder(cmd, self.run, "copy", None)
        self.assertIsNone(resolved)
        self.assertTrue(any("thank-you" in p for p in problems), problems)
        contract = json.loads((ROOT / "references" / "stage-contract.json").read_text(encoding="utf-8"))
        self.assertIn("--spec {copy_spec}", " ".join(contract["stages"]["copy"]["validators"]))
        self.assertIn("thank-you", contract["stages"]["copy"]["copy_selection"]["values"])


class WireframeGateTests(unittest.TestCase):
    """The 16,736 px height floor is the landing standard set's own; a page type asserts none."""

    def run_gate(self, **intake):
        from test_item15_trait_gates import NAVY, GOLD, good_wireframe_run, make_png, run_wireframe, write
        with tempfile.TemporaryDirectory() as td:
            run, _plan = good_wireframe_run(td)
            for n in (1, 2):  # a five-section page is nowhere near a landing page's height
                make_png(run / "desktop-wireframe" / f"section-0{n}.png", 1440, 900, NAVY, chip=GOLD)
            write(run / "intake.json", json.dumps({"brand_owner": "blackceo", **intake}))
            return run_wireframe(run)

    def test_landing_still_fails_a_short_page(self):
        proc = self.run_gate()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("16736px floor", proc.stdout)

    def test_the_thank_you_page_has_no_landing_height_floor(self):
        proc = self.run_gate(page_role="thank_you")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class PipelineTests(RunCase):
    def request_files(self, td, **overrides):
        import test_launch_profile as t
        brand = Path(td) / "brand.json"
        brand.write_text('{"x":1}', encoding="utf-8")
        bh = hashlib.sha256(brand.read_bytes()).hexdigest()
        graph = t.dump(t.graph_doc())
        gh = hashlib.sha256(graph).hexdigest()
        (Path(td) / "graph.json").write_bytes(graph)
        (Path(td) / "launch.json").write_bytes(t.dump(t.launch_doc(gh, brand_ref="brand.json", brand_hash=bh)))
        request = t.request_doc(gh, page_role="thank_you", assigned_skill=82, copy_profile="thank-you",
                                page_id="page-thanks-1", brand_ref="brand.json", brand_hash=bh)
        request.update(overrides)
        (Path(td) / "request.json").write_bytes(t.dump(request))
        return brand

    def service(self, td, version, run_name="svc", **overrides):
        brand = self.request_files(td, **overrides)
        return subprocess.run(
            [PY, str(SCRIPTS / "shared_page_service.py"), "--request", str(Path(td) / "request.json"),
             "--run-dir", str(Path(td) / run_name), "--page-version", version, "--brand-owner", "Acme Owner",
             "--image-cap", "1", "--brand-file", str(brand), "--launch-record", str(Path(td) / "launch.json"),
             "--route-graph", str(Path(td) / "graph.json"), "--pipeline-command", "true"],
            capture_output=True, text=True), Path(td) / run_name

    def test_the_shared_service_admits_the_page_under_its_own_form_only(self):
        with tempfile.TemporaryDirectory() as td:
            proc, run = self.service(td, "thank-you")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            intake = json.loads((run / "intake.json").read_text(encoding="utf-8"))
            self.assertEqual((intake["page_version"], intake["copy_version"], intake["page_role"]),
                             ("thank-you", "thank-you", "thank_you"))
            self.assertEqual(intake["launch"]["copy_profile_mapped"], True)
            self.assertEqual(exe.check_section_count(run, {"sections": sections(IDS)}, paid=True)[1], IDS)
        for version in ("standard", "long-form"):
            with tempfile.TemporaryDirectory() as td:
                proc, run = self.service(td, version)
                self.assertEqual(proc.returncode, 2, proc.stdout)
                self.assertIn("takes --page-version thank-you", proc.stdout)
                self.assertFalse((run / "intake.json").exists())
        with tempfile.TemporaryDirectory() as td:  # and a landing request never takes the page's form
            proc, run = self.service(td, "thank-you", page_role="landing", assigned_skill=71, page_id="page-landing-1",
                                     copy_profile="standard")
            self.assertEqual(proc.returncode, 2, proc.stdout)
            self.assertIn("never forced into another page type", proc.stdout)

    def test_write_intake_records_the_role_and_a_landing_intake_is_unchanged(self):
        run = Path(self.tmp.name) / "intake-run"
        run.mkdir()
        common = [PY, str(SCRIPTS / "write_intake.py"), str(run), "--brand-owner", "Acme", "--image-cap", "1"]
        self.assertEqual(subprocess.run(common + ["--page-version", "thank-you"], capture_output=True).returncode, 0)
        intake = json.loads((run / "intake.json").read_text(encoding="utf-8"))
        self.assertEqual((intake["page_role"], intake["copy_version"]), ("thank_you", "thank-you"))
        landing = Path(self.tmp.name) / "landing-run"
        landing.mkdir()
        subprocess.run([PY, str(SCRIPTS / "write_intake.py"), str(landing), "--brand-owner", "Acme",
                        "--image-cap", "1", "--page-version", "standard", "--copy-version", "standard"],
                       capture_output=True, check=True)
        self.assertNotIn("page_role", json.loads((landing / "intake.json").read_text(encoding="utf-8")))
        for pair in (("thank-you", "standard"), ("standard", "thank-you")):
            mixed = Path(self.tmp.name) / f"mixed-{pair[0]}"
            mixed.mkdir()
            proc = subprocess.run(common[:2] + [str(mixed)] + common[3:] + [
                "--page-version", pair[0], "--copy-version", pair[1]], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2, proc.stdout)
            self.assertIn("disagree", proc.stdout)
            self.assertFalse((mixed / "intake.json").exists())

    def test_run_page_role_stages_drives_the_one_builder_and_the_one_executor(self):
        write_intake(self.run, page_role="thank_you", copy_version="thank-you")
        base = [PY, str(SCRIPTS / "run_page_role_stages.py"), str(self.run), "--model", STUB]
        proc = subprocess.run(base + ["--preflight"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            self.assertIn(f"PREFLIGHT_BLOCKS {stage}", proc.stdout)
        self.assertIn("next: stage_executor.py", proc.stdout)  # the board and final-mockups come after approval
        self.assertNotIn("final-mockups ", proc.stdout.split("next:")[0])
        proc = subprocess.run(base + ["--stages", "mobile-tablet"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        slices = sorted(p.name for p in (self.run / "mobile-tablet").glob("section-*.png"))
        self.assertEqual(slices, [f"section-0{i}.png" for i in range(1, 6)])
        record = json.loads((self.run / "mobile-tablet" / "stage-executor-record.json").read_text())
        self.assertEqual(record["provider"], "stub")

    def test_run_page_role_stages_refuses_a_landing_run(self):
        write_intake(self.run, copy_version="standard")
        proc = subprocess.run([PY, str(SCRIPTS / "run_page_role_stages.py"), str(self.run)],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("landing run is driven by stage_gate.py", proc.stdout)


if __name__ == "__main__":
    unittest.main()
