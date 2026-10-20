#!/usr/bin/env python3
"""A non-landing page role has its own canonical section structure (SPF030, downsell_1).

Pins references/page-structures.json and its three consumers:
  - scripts/stage_executor.py check_section_count reads the page role (request page_role, else the
    run's page-request.json) and checks the downsell's eight sections instead of the landing's
    twelve; the landing page keeps its behaviour;
  - scripts/wireframe_spec.py draws the downsell's own bands (reassurance band, decline button,
    two equal columns, the seven-row list) and none of the landing's step or founder-letter lines;
  - scripts/build_production_request.py builds the eight-section request from the role's own page
    copy (Skill 81's page object) and refuses a page that does not match the structure;
  - scripts/design_board.py already reads the role from the run: downsell_1 resolves from
    page-request.json.
Zero provider calls.
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

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SKILL81 = ROOT.parent / "81-signature-downsell"
PAGE_FIXTURE = SKILL81 / "fixtures" / "valid-downsell-page.json"
STRUCTURES = json.loads((ROOT / "references" / "page-structures.json").read_text(encoding="utf-8"))
DOWNSELL = STRUCTURES["roles"]["downsell_1"]
IDS = [str(i) for i in range(1, 9)]


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    spec.loader.exec_module(mod)
    return mod


exe = load("stage_executor")
builder = load("build_production_request")
wf = load("wireframe_spec")
board = load("design_board")


def sections(ids):
    return [{"section_id": i, "section_name": i, "copy": "A finished sentence."} for i in ids]


def page_doc():
    return json.loads(PAGE_FIXTURE.read_text(encoding="utf-8"))


class StructureFileTests(unittest.TestCase):
    def test_eight_sections_in_order_with_a_button_in_each(self):
        self.assertEqual(DOWNSELL["sequence"], IDS)
        self.assertEqual([s["id"] for s in DOWNSELL["sections"]], IDS)
        self.assertEqual(DOWNSELL["cta_map"]["required_in_sections"], IDS)
        self.assertEqual(DOWNSELL["cta_map"]["forbidden_in_sections"], [])

    @unittest.skipUnless(SKILL81.is_dir(), "Skill 81 is not installed beside Skill 71")
    def test_order_matches_skill_81_page_schema(self):
        schema = json.loads((SKILL81 / "schemas" / "downsell-page.schema.json").read_text(encoding="utf-8"))
        roles = [item["properties"]["role"]["const"] for item in schema["properties"]["sections"]["prefixItems"]]
        self.assertEqual([s["page_role"] for s in DOWNSELL["sections"]], roles)

    def test_every_default_slot_ratio_is_a_listed_label_and_treatment_is_known(self):
        labels = wf.spec()["ratio_labels"]
        treatments = {t["id"] for t in json.loads(
            (ROOT / "references" / "composition-treatments.json").read_text(encoding="utf-8"))["treatments"]}
        for sec in DOWNSELL["sections"]:
            for slot in sec["slots"]:
                self.assertIn(slot["aspect_ratio"], labels)
                self.assertIn(slot["treatment"], treatments)

    def test_the_three_problem_bands_do_not_share_one_geometry(self):
        geo = [DOWNSELL["sections"][i]["layout"] for i in (1, 2, 3)]
        self.assertEqual(len(set(geo)), 3)
        treat = [DOWNSELL["sections"][i]["slots"][0]["treatment"] for i in (1, 2, 3)]
        self.assertEqual(len(set(treat)), 3)


class SectionCountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        give_blackceo_colors(self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, ids, **extra):
        return exe.check_section_count(self.run, {"sections": sections(ids), **extra}, paid=True)

    def test_downsell_request_with_eight_sections_passes_a_paid_check(self):
        version, ids, _ = self.check(IDS, page_role="downsell_1")
        self.assertEqual((version, ids), ("downsell", IDS))

    def test_downsell_request_with_the_landings_twelve_is_refused_by_name(self):
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.check([str(i) for i in range(1, 13)], page_role="downsell_1")
        self.assertIn("Downsell page (downsell_1) has 8 canonical sections", str(ctx.exception))
        self.assertIn("unexpected", str(ctx.exception))

    def test_seven_sections_are_refused_naming_the_missing_one(self):
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.check(IDS[:7], page_role="downsell_1")
        self.assertIn("missing ['8']", str(ctx.exception))

    def test_role_comes_from_the_runs_page_request_when_the_request_does_not_say(self):
        (self.run / "page-request.json").write_text(json.dumps({"page_role": "downsell_1"}))
        self.assertEqual(self.check(IDS)[1], IDS)
        with self.assertRaises(exe.ExecutorError):
            self.check([str(i) for i in range(1, 13)])

    def test_role_in_metadata_counts(self):
        self.assertEqual(self.check(IDS, metadata={"page_role": "downsell_1"})[1], IDS)

    def test_landing_is_unchanged(self):
        standard = [str(i) for i in range(1, 13)]
        self.assertEqual(self.check(standard, copy_version="standard")[1], standard)
        self.assertEqual(self.check(standard, copy_version="standard", page_role="landing")[1], standard)
        with self.assertRaises(exe.ExecutorError):  # eight sections are still a band-compressed landing
            self.check(IDS, copy_version="standard")

    def test_a_role_without_an_entry_keeps_the_landing_rule(self):
        standard = [str(i) for i in range(1, 13)]
        self.assertIsNone(exe.page_structure("no_such_role"))
        self.assertEqual(self.check(standard, copy_version="standard", page_role="no_such_role")[1], standard)

    def test_intake_standard_version_does_not_override_the_role(self):
        # shared_page_service passes --page-version standard for every role
        (self.run / "intake.json").write_text(json.dumps(
            {"brand_owner": "blackceo", "brand_file": "assets/brand/blackceo-brand.json",
             "copy_version": "standard"}))
        self.assertEqual(self.check(IDS, page_role="downsell_1")[0], "downsell")


class WireframeTests(unittest.TestCase):
    def request(self, **extra):
        return {"page_role": "downsell_1", "decline_action": {"label": "No thanks, continue with my current order"},
                **extra}

    def block(self, stage, tag, cta="Claim the offer", request=None):
        width = 390 if stage == "mobile-tablet" else 1440
        section = {"section_id": tag, "section_name": DOWNSELL["sections"][int(tag) - 1]["name"],
                   "cta": cta, "slots": []}
        return wf.prompt_block(stage, section, int(tag), 8, width, request or self.request())

    def test_sheet_form_is_the_profiles_never_inferred_from_eight_sections(self):
        self.assertEqual(wf.form_of({"page_role": "downsell_1", "sections": sections(IDS)}, strict=True), "standard")

    def test_first_band_has_the_reassurance_band_and_the_decline_button(self):
        for stage in wf.WIREFRAME_STAGES:
            text = self.block(stage, "1")
            self.assertIn("REASSURANCE BAND / ORIGINAL ORDER CONFIRMED", text)
            self.assertIn('"No thanks, continue with my current order"', text)
            self.assertIn("MONEY TERMS / BODY SIZE", text)
            self.assertIn("Downsell page", text)
            self.assertIn('reading exactly "SECTION 1"', text)

    def test_section_seven_is_two_equal_columns_and_eight_is_the_seven_row_list(self):
        seven = self.block("desktop-wireframe", "7")
        self.assertIn("INCLUDED and NOT INCLUDED", seven)
        self.assertIn("same visual weight", seven)
        eight = self.block("desktop-wireframe", "8")
        self.assertIn("WHEN TIME RUNS OUT", eight)
        self.assertIn("exactly seven rows", eight)
        self.assertIn("clearly unlike section 7", eight)
        mobile_eight = self.block("mobile-tablet", "8")
        self.assertIn("numeral circles 1 to 7 once each in order", mobile_eight)

    def test_mobile_is_one_column_with_the_standard_phone_reference(self):
        text = self.block("mobile-tablet", "2")
        self.assertIn("single-column phone stack", text)
        self.assertIn("chatgpt-wireframe-4", wf.style_reference("mobile-tablet", "standard")["name"])

    def test_no_landing_band_lines_leak_into_the_downsell(self):
        for tag in IDS:
            for stage in wf.WIREFRAME_STAGES:
                text = self.block(stage, tag)
                self.assertNotIn("STANDARD DESKTOP —", text)
                self.assertNotIn("FOUNDER LETTER", text)
                self.assertNotIn("STEPS — exactly seven step badges", text)
                self.assertNotIn("landing page", text)

    def test_brand_colour_grammar_still_applies(self):
        text = self.block("desktop-wireframe", "3")
        for needle in ("SECTION CHIP AND NAME TAB", "INLINE TYPE SPECS", "IMAGE PLATES", "BRAND COLORS",
                       "never grey line work"):
            self.assertIn(needle.lower() if needle == "never grey line work" else needle,
                          text.lower() if needle == "never grey line work" else text)

    def test_a_downsell_band_without_a_decline_label_is_refused(self):
        with self.assertRaises(wf.SpecError) as ctx:
            self.block("desktop-wireframe", "1", request={"page_role": "downsell_1"})
        self.assertIn("decline", str(ctx.exception))

    def test_landing_block_is_unchanged_by_the_profile_code(self):
        section = {"section_id": "11", "section_name": "Steps", "cta": "Go", "slots": []}
        text = wf.prompt_block("desktop-wireframe", section, 11, 12, 1440, {"copy_version": "standard"})
        self.assertIn("STEPS — exactly seven step badges", text)
        self.assertIn("landing page", text)
        self.assertNotIn("DOWNSELL", text)


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        give_blackceo_colors(self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, doc=None, stage="visual-mockup", slots=None):
        return builder.build(stage, None, "", slots or {}, {}, [], "STUB-NO-MODEL", "", self.run,
                             structure=DOWNSELL, page_doc=doc or page_doc())

    def test_builds_eight_sections_with_the_role_and_the_decline_label(self):
        request = self.build()
        self.assertEqual([s["section_id"] for s in request["sections"]], IDS)
        self.assertEqual(request["page_role"], "downsell_1")
        self.assertEqual(request["copy_version"], "downsell")
        self.assertEqual(request["metadata"]["section_count"], 8)
        self.assertEqual(request["decline_action"]["label"], "No thanks, continue with my current order")
        for section in request["sections"]:
            self.assertTrue(section["cta"])
            self.assertEqual(section["labels"], [request["decline_action"]["label"]])
        self.assertEqual([s["section_name"] for s in request["sections"]],
                         [s["name"] for s in DOWNSELL["sections"]])

    def test_framework_role_labels_are_not_public_copy(self):
        request = self.build()
        text = json.dumps(request["sections"])
        self.assertNotIn("Big Bold", text)
        self.assertEqual(request["metadata"]["dropped_role_label_headings"], IDS[:7])
        eight = request["sections"][7]["copy"].splitlines()
        self.assertEqual(eight[0], "When Time Runs Out")

    def test_section_eight_carries_exactly_seven_numbered_lines(self):
        copy = self.build()["sections"][7]["copy"].splitlines()
        self.assertEqual([l[:3] for l in copy if l[:1].isdigit()],
                         [f"{n}. " for n in range(1, 8)])
        self.assertTrue(all(l[-1] == "." for l in copy if l[:1].isdigit()))

    def test_default_slots_come_from_the_structure_and_slots_file_wins(self):
        request = self.build()
        self.assertEqual(request["sections"][0]["slots"][0]["treatment"], "split")
        self.assertEqual(request["sections"][7]["slots"], [])
        custom = {"1": [{"slot_id": "mine", "aspect_ratio": "16:9", "art_direction": "x"}]}
        self.assertEqual(self.build(slots=custom)["sections"][0]["slots"][0]["slot_id"], "mine")

    def test_refuses_a_page_with_the_wrong_roles(self):
        doc = page_doc()
        doc["page"]["sections"].pop()
        with self.assertRaises(builder.BuildError) as ctx:
            self.build(doc)
        self.assertIn("section count", str(ctx.exception))

    def test_refuses_a_page_with_no_decline_label(self):
        doc = page_doc()
        del doc["page"]["decline_action"]
        with self.assertRaises(builder.BuildError) as ctx:
            self.build(doc)
        self.assertIn("decline", str(ctx.exception))

    def test_refuses_a_section_with_no_button_label(self):
        doc = page_doc()
        doc["page"]["sections"][2]["cta"]["label"] = ""
        with self.assertRaises(builder.BuildError) as ctx:
            self.build(doc)
        self.assertIn("section 3", str(ctx.exception))

    def test_each_stage_builds_and_the_request_passes_the_executors_own_check(self):
        for stage in exe.STAGES:
            request = self.build(stage=stage)
            self.assertEqual(request["metadata"]["stage"], stage)
            self.assertEqual(exe.check_section_count(self.run, request, paid=True)[1], IDS)

    def test_page_layout_reaches_the_mockup_prompt_and_the_landing_skeleton_does_not(self):
        request = self.build(stage="visual-mockup")
        request["_brand_block"] = exe.require_brand_colors(self.run)
        request["_hypersat"] = exe.hypersaturation.roles_for_run(self.run)
        prompt = exe.stage_prompt("visual-mockup", request["sections"][6], 7, 1440, request, "3:2")
        self.assertIn("Two equal columns side by side", prompt)
        self.assertNotIn("SLOT CANON", prompt)

    def test_cli_page_role_needs_page_copy_and_is_exclusive_with_the_landing_flags(self):
        proc = subprocess.run([sys.executable, str(SCRIPTS / "build_production_request.py"),
                               "--page-role", "downsell_1", "--stage", "visual-mockup",
                               "--out", str(self.run / "x.json")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        proc = subprocess.run([sys.executable, str(SCRIPTS / "build_production_request.py"),
                               "--page-role", "no_such_role", "--page-copy", str(PAGE_FIXTURE),
                               "--stage", "visual-mockup", "--model", "STUB-NO-MODEL",
                               "--run-dir", str(self.run), "--out", str(self.run / "x.json")],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no entry in", proc.stdout)


class PreflightTests(unittest.TestCase):
    """The free proof: build the request from Skill 81's own example page and preflight three stages."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        give_blackceo_colors(self.run)
        (self.run / "page-request.json").write_text(json.dumps({"page_role": "downsell_1"}))

    def tearDown(self):
        self.tmp.cleanup()

    def build_file(self, stage):
        proc = subprocess.run([sys.executable, str(SCRIPTS / "build_production_request.py"),
                               "--page-role", "downsell_1", "--page-copy", str(PAGE_FIXTURE),
                               "--stage", stage, "--model", "STUB-NO-MODEL", "--run-dir", str(self.run),
                               "--out", str(self.run / f"production-request-{stage}.json")],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def preflight(self, stage):
        self.build_file(stage)
        return subprocess.run([sys.executable, str(SCRIPTS / "stage_executor.py"), str(self.run), "--preflight",
                               "--stages", stage, "--request", f"production-request-{stage}.json"],
                              capture_output=True, text=True)

    def test_three_stages_preflight_clean_with_eight_sections_and_the_role(self):
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            proc = self.preflight(stage)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("PREFLIGHT_SECTIONS copy_version=downsell sections=8 "
                          "canonical_ids=1,2,3,4,5,6,7,8 page_role=downsell_1", proc.stdout)
            self.assertNotIn("REFUSED", proc.stdout)
            self.assertEqual(proc.stdout.count("PREFLIGHT_CTA"), 8)
            if stage == "visual-mockup":
                self.assertEqual(proc.stdout.count("PREFLIGHT_HYPERSAT"), 16)
            else:
                self.assertEqual(proc.stdout.count("PREFLIGHT_WIREFRAME_REFS"), 8)
                self.assertIn("form=standard", proc.stdout)

    def test_the_downsell_request_is_refused_as_a_landing_when_the_role_is_lost(self):
        self.build_file("desktop-wireframe")
        path = self.run / "production-request-desktop-wireframe.json"
        request = json.loads(path.read_text())
        del request["page_role"]
        del request["metadata"]["page_role"]
        request["copy_version"] = "standard"
        path.write_text(json.dumps(request))
        (self.run / "page-request.json").unlink()
        proc = subprocess.run([sys.executable, str(SCRIPTS / "stage_executor.py"), str(self.run), "--preflight",
                               "--stages", "desktop-wireframe", "--request", path.name],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("section count", proc.stdout)


class DesignBoardRoleTests(unittest.TestCase):
    def test_downsell_role_resolves_from_the_runs_page_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            self.assertEqual(board.declared_role(run), "landing")
            (run / "page-request.json").write_text(json.dumps({"page_role": "downsell_1"}))
            self.assertEqual(board.declared_role(run), "downsell_1")
            self.assertEqual(exe.page_role_for(run, {}), "downsell_1")
            self.assertEqual(exe.page_role_for(run, {"page_role": "landing"}), "landing")
        self.assertIn("downsell_1", board.ROLE_LABEL)
        self.assertIn("downsell_1", board.ROLE_EMPHASIS)


if __name__ == "__main__":
    unittest.main()
