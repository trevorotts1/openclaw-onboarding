#!/usr/bin/env python3
"""SPF030: the landing role has two page kinds, the signature sales page and the
signature landing (opt-in) page, and both go through the ONE Skill 71 pipeline.

Pins:
  (a) the kinds file: each kind's canonical sequence is the copy spec's own
      sequence for a form the kind allows (sales: Standard 12 or Long-Form 15;
      opt-in: Long-Form 15 only), and an opt-in page on the Standard copy is refused;
  (b) intake records the kind, refuses a kind/copy-form mismatch, and the intake
      gate refuses a production run with no kind (test runs are exempt);
  (c) build_production_request builds a request for each kind from the skill's own
      example copy and records the kind;
  (d) the executor refuses a mismatched kind, fills the kind from intake.json, and
      --preflight prints PREFLIGHT_PAGE and passes for desktop-wireframe,
      mobile-tablet and visual-mockup;
  (e) the wireframe build spec differs by kind: the head names the kind, and the
      closing band (last slice only) is a checkout panel for a sales page and a
      registration strip for an opt-in page; no hex colour, no price; on the
      real copy (the founder letter carries no CTA of its own) the band's button
      reads the page's last given CTA label, that label is in the verbatim copy
      block, and the "no CTA" lines are gone from that slice only;
  (f) the mockup prompt carries the kind line, and the Design Board labels the
      landing role by kind, records it and fails a board of the other kind;
  (g) Skill 71 routes "signature sales page" to itself and Skill 56 declines it.

No paid API is called anywhere in this module.
"""
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
from brand_fixture import give_blackceo_colors  # noqa: E402
import board_fixture as bf  # noqa: E402

ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "copy_examples"
PY = sys.executable
sys.path.insert(0, str(SCRIPTS))
import page_kinds as pk  # noqa: E402
import wireframe_spec as w  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exe = load("stage_executor")
builder = load("build_production_request")
db = bf.design_board

CASES = (("sales", "standard", 12), ("sales", "long-form", 15), ("opt_in", "long-form", 15))
HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def sequence_of(version):
    return json.loads((exe.SPEC_DIR / f"{version}-v6.json").read_text())["sequence"]


def manuscript(version):
    return (FIXTURES / f"{version}-path-b.md").read_text(encoding="utf-8")


def make_request(run, kind, version):
    """The request the skill's own builder writes from its example copy."""
    request = builder.build("visual-mockup", version, manuscript(version), {}, {}, [],
                            "STUB-NO-MODEL", "", run, page_kind=kind)
    (run / "production-request.json").write_text(json.dumps(request), encoding="utf-8")
    return request


class KindTests(unittest.TestCase):
    def test_two_kinds_share_the_landing_role(self):
        self.assertEqual(pk.kind_ids(), ["sales", "opt_in"])
        self.assertEqual(pk.data()["page_role"], "landing")
        schema = json.loads((ROOT / "references" / "page-request.schema.json").read_text())
        self.assertIn(pk.data()["page_role"], schema["properties"]["page_role"]["enum"])

    def test_sequence_is_the_copy_specs_own(self):
        for kind, version, count in CASES:
            seq = pk.sequence(kind, version)
            self.assertEqual(seq, sequence_of(version))
            self.assertEqual(len(seq), count)

    def test_opt_in_needs_long_form(self):
        with self.assertRaises(pk.KindError) as ctx:
            pk.sequence("opt_in", "standard")
        self.assertIn("long-form", str(ctx.exception))
        self.assertEqual(pk.normalize("Opt-In"), "opt_in")
        with self.assertRaises(pk.KindError):
            pk.entry("squeeze")


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def intake(self, *extra, version="long-form"):
        return subprocess.run(
            [PY, str(SCRIPTS / "write_intake.py"), str(self.run), "--page-version", version,
             "--copy-version", version, "--brand-owner", "blackceo", "--image-cap", "1",
             "--test-run", *extra], text=True, capture_output=True)

    def test_kind_is_recorded(self):
        proc = self.intake("--page-kind", "opt_in")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads((self.run / "intake.json").read_text())["page_kind"], "opt_in")

    def test_opt_in_on_standard_copy_is_refused(self):
        proc = self.intake("--page-kind", "opt_in", version="standard")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("long-form", proc.stdout)
        self.assertFalse((self.run / "intake.json").exists())

    def test_no_kind_prints_a_note_and_records_none(self):
        proc = self.intake()
        self.assertEqual(proc.returncode, 0)
        self.assertIn("NOTE page_kind", proc.stdout)
        self.assertNotIn("page_kind", json.loads((self.run / "intake.json").read_text()))

    def test_gate_refuses_a_production_run_without_a_kind(self):
        import stage_gate

        def gate(intake):
            (self.run / "intake.json").write_text(json.dumps(intake))
            return stage_gate.run_builtin("gate:intake_page_kind", [], self.run)

        self.assertIn("no page_kind", gate({"copy_version": "standard"}))
        self.assertIsNone(gate({"copy_version": "standard", "page_kind": "sales"}))
        self.assertIn("long-form", gate({"copy_version": "standard", "page_kind": "opt_in"}))
        self.assertIsNone(gate({"test_run": True}))


class BuilderAndExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        give_blackceo_colors(self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def test_builder_builds_each_kind_from_the_skills_own_copy(self):
        for kind, version, count in CASES:
            request = make_request(self.run, kind, version)
            self.assertEqual(request["page_kind"], kind)
            self.assertEqual(request["metadata"]["page_kind"], kind)
            self.assertEqual(len(request["sections"]), count)
            self.assertEqual([s["section_id"] for s in request["sections"]], pk.sequence(kind, version))

    def test_builder_refuses_opt_in_on_standard_copy(self):
        with self.assertRaises(builder.BuildError) as ctx:
            builder.build("visual-mockup", "standard", manuscript("standard"), {}, {}, [],
                          "STUB-NO-MODEL", "", self.run, page_kind="opt_in")
        self.assertIn("page kind", str(ctx.exception))

    def test_executor_refuses_a_mismatched_kind(self):
        request = {"copy_version": "standard", "page_kind": "opt_in",
                   "sections": [{"section_id": i, "section_name": i, "copy": "A sentence."}
                                for i in sequence_of("standard")]}
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.check_section_count(self.run, request, paid=False)
        self.assertIn("page kind", str(ctx.exception))

    def test_kind_comes_from_intake_when_the_request_is_silent(self):
        make_request(self.run, "sales", "standard")
        request = json.loads((self.run / "production-request.json").read_text())
        request.pop("page_kind")
        request["metadata"].pop("page_kind")
        (self.run / "production-request.json").write_text(json.dumps(request))
        intake = json.loads((self.run / "intake.json").read_text())
        intake["page_kind"] = "sales"
        (self.run / "intake.json").write_text(json.dumps(intake))
        self.assertEqual(exe.load_request(self.run, "production-request.json")["page_kind"], "sales")

    def test_preflight_passes_for_wireframes_and_mockup_of_each_kind(self):
        for kind, version, count in CASES:
            with self.subTest(kind=kind, version=version):
                make_request(self.run, kind, version)
                proc = subprocess.run(
                    [PY, str(SCRIPTS / "stage_executor.py"), str(self.run), "--preflight",
                     "--stages", "desktop-wireframe,mobile-tablet,visual-mockup"],
                    text=True, capture_output=True)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                out = proc.stdout
                self.assertIn(f"PREFLIGHT_PAGE page_role=landing page_kind={kind}", out)
                self.assertIn(f"canonical_sequence_len={count}", out)
                self.assertIn(f"PREFLIGHT_SECTIONS copy_version={version} sections={count}", out)
                for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
                    self.assertEqual(len(re.findall(rf"^PREFLIGHT {stage} ", out, re.M)),
                                     count * (2 if stage == "visual-mockup" else 1), stage)
                self.assertNotIn("REFUSED", out)


def section(sid, name, cta=None):
    return {"section_id": sid, "section_name": name, "copy": "A finished sentence.",
            "cta": cta, "slots": []}


class WireframeAndMockupTests(unittest.TestCase):
    def block(self, kind, stage, index, total, version="long-form"):
        request = {"copy_version": version}
        if kind:
            request["page_kind"] = kind
        return w.prompt_block(stage, section(str(index), "Founder letter", "GET IT"), index, total,
                              1440 if stage == "desktop-wireframe" else 390, request)

    def test_head_and_closing_band_differ_by_kind(self):
        for stage in w.WIREFRAME_STAGES:
            sales = self.block("sales", stage, 15, 15)
            opt_in = self.block("opt_in", stage, 15, 15)
            self.assertIn("SIGNATURE SALES PAGE", sales)
            self.assertIn("checkout call-to-action panel", sales)
            self.assertIn("closing checkout panel", sales)
            self.assertNotIn("OPT-IN", sales)
            self.assertIn("SIGNATURE LANDING (OPT-IN) PAGE", opt_in)
            self.assertIn("registration strip", opt_in)
            self.assertNotIn("closing checkout panel", opt_in)

    def test_closing_band_is_on_the_last_slice_only(self):
        for kind in pk.kind_ids():
            self.assertNotIn("CLOSING BAND", self.block(kind, "desktop-wireframe", 14, 15))
            self.assertIn("CLOSING BAND", self.block(kind, "desktop-wireframe", 15, 15))

    def test_closing_button_label_on_real_copy_for_every_kind_and_stage(self):
        """The founder letter has no CTA in the copy specs, so the closing band reads
        the page's last given CTA; the prompt never says both 'draw a button' and
        'no CTA', and the label is in the verbatim block (the model may print it)."""
        for kind, version, count in CASES:
            with tempfile.TemporaryDirectory() as tmp:
                run = Path(tmp)
                give_blackceo_colors(run)
                make_request(run, kind, version)
                request = exe.load_request(run, "production-request.json")
                request["_brand_block"] = exe.require_brand_colors(run)
                request["_hypersat"] = exe.hypersaturation.roles_for_run(run)
                last = request["sections"][-1]
                self.assertFalse(last.get("cta"), "the copy spec forbids a CTA on the last section")
                label = [x["cta"] for x in request["sections"] if x.get("cta")][-1]
                for stage in (*w.WIREFRAME_STAGES, "visual-mockup"):
                    width = exe.LAYOUT[stage][0][1]
                    with self.subTest(kind=kind, version=version, stage=stage):
                        ratio = exe.target_ratio(stage, exe.LAYOUT[stage][0][0], last, run, count)
                        text = exe.stage_prompt(stage, last, count, width, request, ratio)
                        self.assertIn(f'CLOSING BUTTON LABEL — print exactly: "{label}"', text)
                        self.assertNotIn("this section has no CTA.", text)
                        self.assertNotIn("Draw no button and no CTA strip", text)
                        self.assertNotIn('exactly "No CTA"', text)
                        if stage in w.WIREFRAME_STAGES:
                            self.assertIn(f'carrying one filled primary-colour button reading exactly "{label}"', text)
                            self.assertIn("4. CTA — this section has no CTA of its own", text)
                            self.assertIn("Closing CTA panel", text)
                        else:
                            self.assertIn(f'button reading exactly "{label}"', text)
                text = exe.stage_prompt("desktop-wireframe", request["sections"][5], 6, 1440, request, "3:4")
                self.assertNotIn("CLOSING", text)
                self.assertIn("this section has no CTA.", text)  # a mid-page section without a CTA still says so

    def test_builder_button_line_names_the_closing_label_not_a_forbidden_button(self):
        spec = json.loads((exe.SPEC_DIR / "standard-v6.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            give_blackceo_colors(Path(tmp))
            request = make_request(Path(tmp), "sales", "standard")
        table = builder.skeleton_table()
        sections = request["sections"]
        for kind, expect in (("sales", 'closing panel carries exactly one, labelled "Make Room to Lead"'),
                             (None, "carries no button, no chip")):
            lines = builder.section_fragments("visual-mockup", sections[-1], 12, sections, spec, table, kind)
            self.assertTrue(any(expect in line for line in lines), (kind, [l for l in lines if "BUTTON" in l]))

    def test_closing_label_refuses_a_page_with_no_cta_at_all(self):
        with self.assertRaises(pk.KindError):
            pk.closing_label("sales", {"section_id": "12"}, [{"section_id": "1"}, {"section_id": "12"}], 2, 2)
        self.assertIsNone(pk.closing_label("sales", {"section_id": "1"}, [], 1, 2))
        self.assertIsNone(pk.closing_label(None, {"section_id": "2", "cta": "X"}, [], 2, 2))
        self.assertEqual(pk.closing_label("sales", {"section_id": "2"}, [{"cta": "A."}, {}], 2, 2), "A")

    def test_no_kind_adds_nothing_and_blocks_stay_colourless_and_priceless(self):
        self.assertNotIn("PAGE KIND", self.block(None, "desktop-wireframe", 15, 15))
        for kind in pk.kind_ids():
            text = self.block(kind, "mobile-tablet", 15, 15)
            self.assertFalse(HEX.search(text))
            self.assertIn("no price", text)
            self.assertIn("attached to this request", text)  # structure only, from the one style reference

    def test_every_kind_still_attaches_the_one_style_sheet_for_its_form(self):
        self.assertEqual(w.style_reference("desktop-wireframe", "standard")["name"], "chatgpt-wireframe-1")
        self.assertEqual(w.style_reference("desktop-wireframe", "long-form")["name"], "chatgpt-wireframe-3")

    def test_mockup_prompt_carries_the_kind_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            give_blackceo_colors(run)
            for kind in pk.kind_ids():
                request = {"model": "STUB-NO-MODEL", "page_kind": kind,
                           "stage_prompts": {"visual-mockup": "Draw it.\n{copy}"},
                           "_hypersat": exe.hypersaturation.roles_for_run(run)}
                prompt = exe.stage_prompt("visual-mockup", section("1", "Claim"), 1, 1440, request, "3:4")
                self.assertIn(pk.mockup_line(kind), prompt)
            request.pop("page_kind")
            self.assertNotIn("PAGE KIND", exe.stage_prompt(
                "visual-mockup", section("1", "Claim"), 1, 1440, request, "3:4"))


class DesignBoardTests(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="page-kind-board-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.td, ignore_errors=True))

    def run_for(self, kind):
        run = bf.make_run(self.td / (kind or "none"), "landing")
        if kind:
            intake = json.loads((run / "intake.json").read_text())
            intake["page_kind"] = kind
            (run / "intake.json").write_text(json.dumps(intake))
        return run

    def prompt(self, run):
        request = json.loads((run / "production-request.json").read_text())
        plan = db.plan(run, request)
        return plan, db.compose_prompt(plan, request, run)[0]

    def test_board_label_and_emphasis_follow_the_kind(self):
        for kind in pk.kind_ids():
            label, emphasis = pk.board(kind)
            plan, prompt = self.prompt(self.run_for(kind))
            self.assertEqual(plan["kind"], kind)
            self.assertIn(f"client's {label}.", prompt)
            self.assertIn(emphasis, prompt)
        plan, prompt = self.prompt(self.run_for(None))
        self.assertIsNone(plan["kind"])
        self.assertIn(db.ROLE_LABEL["landing"], prompt)

    def test_record_stores_the_kind_and_a_board_of_the_other_kind_fails(self):
        from unittest import mock
        with mock.patch.object(db, "ocr_text", bf.fake_ocr):
            run = self.run_for("sales")
            bf.seed_board(run)
            self.assertEqual(db.load_record(run)["page_kind"], "sales")
            self.assertEqual(db.validate(run), [])
            intake = json.loads((run / "intake.json").read_text())
            intake["page_kind"] = "opt_in"
            (run / "intake.json").write_text(json.dumps(intake))
            self.assertTrue(any("page kind" in f for f in db.validate(run)))


class RoutingTests(unittest.TestCase):
    REPO = ROOT.parent

    def test_skill_71_owns_the_signature_sales_page_phrases(self):
        entry = json.loads((self.REPO / "23-ai-workforce-blueprint" / "skill-department-map.json").read_text())
        skills = entry["skills"] if isinstance(entry, dict) else entry
        mine = next(s for s in skills if str(s.get("skill")) == "71")
        others = [t for s in skills if str(s.get("skill")) != "71" for t in s.get("intent_triggers", [])]
        for phrase in ("build a signature sales page", "create a signature sales page", "signature sales page"):
            self.assertIn(phrase, mine["intent_triggers"])
            self.assertNotIn(phrase, others)
        self.assertNotIn("and the sales page are produced", mine["description"])

    def test_skill_56_declines_it_in_the_engine_registry(self):
        registry = json.loads((self.REPO / "06-ghl-install-pages" / "funnel-engines" / "registry.json").read_text())
        engine = next(e for e in registry["engines"] if e["id"] == "sales-page-assets")
        self.assertIn("signature sales page", engine["match"]["anti_signals"])


if __name__ == "__main__":
    unittest.main()
