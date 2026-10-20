#!/usr/bin/env python3
"""A page role with its own section sequence (checkout, references/copy-specs/roles/checkout.json).

Pins the role-spec seam of scripts/stage_executor.py (check_section_count), scripts/
build_production_request.py (--page-role), scripts/composition.py (composition_role) and
scripts/wireframe_spec.py (the page type layout block):
  - a 5-section checkout request passes; a 12-section (landing) request on a checkout run is
    refused by name; a 5-section request on a landing run is still refused (landing unchanged);
  - the role comes from the request, else from the run's page-request.json;
  - the builder makes the 5-section request from a checkout manuscript, with the role's slots,
    grounds, composition roles and layout, and refuses a button in the wrong section;
  - treatments vary between sections and never repeat a non-split one next door;
  - the Design Board accepts the declared slots for the checkout role;
  - the section order is the reading order of Skill 79's QC-STATES.md;
  - the wireframe prompt carries the checkout layout and none of the landing-only wording;
  - preflight composes all three stages with the checkout page's own structure (no provider call).
"""
import importlib.util
import json
import re
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
FIXTURE = ROOT / "tests" / "fixtures" / "copy_examples" / "checkout-example.md"
QC_STATES = ROOT.parent / "79-signature-order-form" / "references" / "components" / "QC-STATES.md"
REAL_MODEL = "gpt-image-2-5-sunburst-image-to-image"
CHECKOUT = ["1", "2", "3", "4", "5"]
STANDARD = [str(i) for i in range(1, 13)]


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    spec.loader.exec_module(mod)
    return mod


exe = load("stage_executor")
builder = load("build_production_request")
comp = load("composition")
role_spec = load("role_spec")


def design_prose(chars=14500):
    """The same stand-in for a measured design system test_section_count uses."""
    syllables = ["ba", "ke", "lo", "mi", "su", "ta", "ve", "zo", "ri", "na"]
    words = [a + b + c + d for a in syllables for b in syllables for c in syllables for d in syllables]
    text, state = [], 7
    while sum(len(t) + 1 for t in text) < chars:
        sentence = []
        for _ in range(12):
            state = (state * 1103515245 + 12345) % 2147483648
            sentence.append(words[state % len(words)])
        text.append(" ".join(sentence) + ".")
    return {"rules_md": "\n".join(text)}


def sections(ids):
    return [{"section_id": i, "section_name": i, "copy": "A finished sentence."} for i in ids]


class RunCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        give_blackceo_colors(self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, stage="visual-mockup", text=None, slots=None, prose=None):
        text = FIXTURE.read_text(encoding="utf-8") if text is None else text
        return builder.build(stage, None, text, slots or {}, design_prose() if prose is None else prose,
                             [], REAL_MODEL, "", self.run, "checkout")


class SectionCountTests(RunCase):
    def check(self, role, ids, version=None):
        request = {"sections": sections(ids)}
        if role:
            request["page_role"] = role
        if version:
            request["copy_version"] = version
        return exe.check_section_count(self.run, request, paid=True)

    def test_five_section_checkout_passes_even_paid_and_without_a_copy_version(self):
        version, ids, _ = self.check("checkout", CHECKOUT)
        self.assertEqual((version, ids), ("standard", CHECKOUT))  # the form label defaults from the spec

    def test_twelve_section_request_on_a_checkout_run_is_refused(self):
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.check("checkout", STANDARD, "standard")
        message = str(ctx.exception)
        self.assertIn("12 sections", message)
        self.assertIn("checkout page has 5 canonical sections", message)
        self.assertIn("never band-compress", message)

    def test_a_short_checkout_request_is_refused_by_name(self):
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.check("checkout", CHECKOUT[:4])
        self.assertIn("missing ['5']", str(ctx.exception))

    def test_landing_is_unchanged(self):
        self.assertEqual(self.check("landing", STANDARD, "standard")[1], STANDARD)
        self.assertEqual(self.check(None, STANDARD, "standard")[1], STANDARD)
        with self.assertRaises(exe.ExecutorError) as ctx:  # five sections are not a landing page
            self.check("landing", CHECKOUT, "standard")
        self.assertIn("12 canonical", str(ctx.exception))
        with self.assertRaises(exe.ExecutorError):  # and a landing page still needs its form when paid
            self.check("landing", STANDARD)

    def test_unknown_form_label_is_refused_for_a_role_page_too(self):
        with self.assertRaises(exe.ExecutorError):
            self.check("checkout", CHECKOUT, "short-form")

    def test_role_comes_from_the_runs_page_request_when_the_request_is_silent(self):
        (self.run / "page-request.json").write_text(json.dumps({"page_role": "checkout"}))
        request = {"sections": sections(CHECKOUT)}
        self.assertEqual(exe.check_section_count(self.run, request, paid=True)[1], CHECKOUT)
        with self.assertRaises(exe.ExecutorError):
            exe.check_section_count(self.run, {"sections": sections(STANDARD)}, paid=True)

    def test_every_role_spec_is_well_formed(self):
        for path in sorted((ROOT / "references" / "copy-specs" / "roles").glob("*.json")):
            spec = role_spec.load(path.stem)
            self.assertEqual(spec["sequence"], [s["id"] for s in spec["sections"]], path.name)
            for s in spec["sections"]:
                for key in ("name", "job", "composition_role", "ground", "slots", "desktop", "mobile",
                            "behavior_notes"):
                    self.assertIn(key, s, f"{path.name} section {s['id']}")
            self.assertTrue(any(s["slots"] for s in spec["sections"]), "the Design Board needs a slot")


class BuilderTests(RunCase):
    def test_builder_makes_the_five_section_request_with_the_roles_structure(self):
        request = self.build()
        self.assertEqual([s["section_id"] for s in request["sections"]], CHECKOUT)
        self.assertEqual(request["page_role"], "checkout")
        self.assertEqual(request["metadata"]["page_role"], "checkout")
        self.assertEqual(request["metadata"]["section_count"], 5)
        self.assertNotIn("_role_spec", request)
        by_id = {s["section_id"]: s for s in request["sections"]}
        self.assertEqual([by_id[i]["section_name"] for i in CHECKOUT],
                         ["Offer or selected package", "Offer details and price", "Order bump",
                          "Guarantee and terms", "Secure checkout"])
        self.assertEqual(by_id["5"]["cta"], "Complete my order")
        self.assertTrue(all(by_id[i]["cta"] is None for i in "1234"))
        self.assertEqual([len(by_id[i]["slots"]) for i in CHECKOUT], [1, 0, 0, 1, 0])
        self.assertEqual({s["ground"] for s in request["sections"]} - {"light", "hero"}, set())
        self.assertIn("DESKTOP LAYOUT", by_id["1"]["layout"])
        self.assertIn("MOBILE LAYOUT", by_id["1"]["layout"])

    def test_caller_slots_replace_the_roles_default_slots(self):
        slot = {"slot_id": "X-1", "aspect_ratio": "1:1", "art_direction": "a custom plate"}
        request = self.build(slots={"1": [slot], "2": [], "4": []})
        by_id = {s["section_id"]: s for s in request["sections"]}
        self.assertEqual(by_id["1"]["slots"], [slot])
        self.assertEqual(by_id["4"]["slots"], [])

    def test_builder_refuses_a_button_where_the_spec_forbids_one(self):
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "## Section 3: Order bump\n", "## Section 3: Order bump\n\n[CTA BUTTON: Add it]\n")
        with self.assertRaises(builder.BuildError) as ctx:
            self.build(text=text)
        self.assertIn("section 3", str(ctx.exception))

    def test_builder_refuses_a_checkout_manuscript_without_its_button(self):
        text = re.sub(r"\[CTA BUTTON:[^\]]*\]", "", FIXTURE.read_text(encoding="utf-8"))
        with self.assertRaises(builder.BuildError) as ctx:
            self.build(text=text)
        self.assertIn("section 5", str(ctx.exception))

    def test_builder_refuses_the_landing_manuscript_shape_for_a_checkout(self):
        text = (ROOT / "tests" / "fixtures" / "copy_examples" / "standard-path-b.md").read_text(encoding="utf-8")
        with self.assertRaises(builder.BuildError) as ctx:
            self.build(text=text)
        self.assertIn("5 canonical sections", str(ctx.exception))

    def test_landing_builds_are_untouched(self):
        text = (ROOT / "tests" / "fixtures" / "copy_examples" / "standard-path-b.md").read_text(encoding="utf-8")
        request = builder.build("visual-mockup", "standard", text, {}, {}, [], "STUB-NO-MODEL", "", self.run)
        self.assertEqual([s["section_id"] for s in request["sections"]], STANDARD)
        self.assertNotIn("page_role", request)
        self.assertNotIn("composition_role", request["sections"][0])
        with self.assertRaises(builder.BuildError):  # landing still needs its form
            builder.build("visual-mockup", None, text, {}, {}, [], "STUB-NO-MODEL", "", self.run)

    def test_every_stage_lands_in_the_prompt_band(self):
        for stage in exe.STAGES:
            budget = self.build(stage)["metadata"]["char_budget"]
            self.assertGreaterEqual(budget["min_seen"], budget["target"], stage)
            self.assertLessEqual(budget["max_seen"], budget["max"], stage)


class CompositionTests(RunCase):
    def test_treatments_vary_and_never_repeat_a_non_split_one_next_door(self):
        request = self.build()
        resolved = comp.assign_treatments(request["sections"])
        self.assertEqual([r["role"] for r in resolved],
                         ["offer-explainer", "price-summary", "order-bump", "guarantee", "checkout-form"])
        primary = [next((e["treatment"] for e in r["slots"]), None) for r in resolved]
        self.assertTrue(all(primary), primary)
        self.assertGreaterEqual(len(set(primary)), 3, primary)
        for a, b in zip(primary, primary[1:]):
            self.assertTrue(a == "split" or a != b, primary)

    def test_a_landing_section_id_does_not_give_a_checkout_section_a_landing_role(self):
        bare = [{"section_id": i, "section_name": "x", "copy": "c"} for i in CHECKOUT]
        self.assertEqual(comp.section_role("1", "Offer or selected package"), "hero")  # the id wins by number
        self.assertEqual(comp.assign_treatments(self.build()["sections"])[0]["role"], "offer-explainer")
        self.assertEqual(comp.assign_treatments(bare)[0]["role"], "hero")  # why composition_role matters

    def test_role_names_alone_also_resolve_when_no_composition_role_is_carried(self):
        for sid, name, role in (("x1", "Offer or selected package", "offer-explainer"),
                                ("x2", "Offer details and price", "price-summary"),
                                ("x3", "Order bump", "order-bump"), ("x4", "Guarantee and terms", "guarantee"),
                                ("x5", "Secure checkout", "checkout-form")):
            self.assertEqual(comp.section_role(sid, name), role)


class BoardTests(RunCase):
    def test_design_board_accepts_the_declared_slots_for_the_checkout_role(self):
        request = self.build()
        run = self.run / "board"
        for section in request["sections"]:
            for slot in section["slots"]:
                bf.png(run / "inputs" / f"{slot['slot_id']}.png")
                slot["file"] = f"inputs/{slot['slot_id']}.png"
        bf.make_run(run, "checkout", base_request=request)
        plan = bf.design_board.plan(run, json.loads((run / "production-request.json").read_text()))
        self.assertEqual(plan["role"], "checkout")
        self.assertEqual(len(plan["slots"]), 2)


class ReadingOrderTests(unittest.TestCase):
    @unittest.skipUnless(QC_STATES.is_file(), "Skill 79 is not beside Skill 71 in this tree")
    def test_section_order_is_skill_79s_reading_order(self):
        text = QC_STATES.read_text(encoding="utf-8")
        item = re.search(r"- Reading order:(.*?)in both modes", text, re.S).group(1)  # the bullet wraps lines
        order = [" ".join(p.split()).lower() for p in item.split(",")][:5]
        keys = ["explanation", "offer details", "bump", "guarantee", "native slot"]
        self.assertEqual([next(k for k in keys if k in p) for p in order], keys)
        names = [s["name"].lower() for s in role_spec.load("checkout")["sections"]]
        want = ["offer or selected package", "offer details and price", "order bump",
                "guarantee and terms", "secure checkout"]
        self.assertEqual(names, want)


class PromptTests(RunCase):
    def prompt(self, stage, index, width):
        request = self.build(stage)
        request["_role_spec"] = role_spec.load("checkout")
        builder.run_blocks(request, self.run)
        return exe.stage_prompt(stage, request["sections"][index - 1], index, width, request, "4:3")

    def test_wireframe_prompt_carries_the_checkout_layout_and_no_landing_only_wording(self):
        for stage, width in (("desktop-wireframe", 1440), ("mobile-tablet", 390)):
            prompt = self.prompt(stage, 5, width)
            self.assertIn("PAGE TYPE LAYOUT, checkout page", prompt)
            self.assertIn("NATIVE CHECKOUT FORM", prompt)
            self.assertIn("for a checkout page", prompt)
            self.assertIn("CHECKOUT DESKTOP" if width > 400 else "MOBILE", prompt)
            for landing_only in ("for a landing page", "Each pain section", "fills the dark authority bands",
                                 "alternate between the light and the dark"):
                self.assertNotIn(landing_only, prompt, stage)
            self.assertIn("Complete my order", prompt)

    def test_the_form_is_never_drawn_as_card_fields(self):
        prompt = self.prompt("visual-mockup", 5, 1440)
        self.assertIn("no card, expiry or security-code fields", prompt)
        self.assertNotRegex(prompt, r"(?i)card number|cvc|cvv")


class PreflightTests(RunCase):
    def test_preflight_composes_all_three_stages_on_the_checkout_structure(self):
        (self.run / "page-request.json").write_text(json.dumps({"page_role": "checkout"}))
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            name = f"production-request-{stage}.json"
            request = self.build(stage)
            (self.run / name).write_text(json.dumps(request))
            proc = subprocess.run([sys.executable, str(SCRIPTS / "stage_executor.py"), str(self.run),
                                   "--stages", stage, "--request", name, "--preflight"],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("sections=5 canonical_ids=1,2,3,4,5", proc.stdout)
            platforms = 2 if stage == "visual-mockup" else 1
            self.assertEqual(len(re.findall(r"^PREFLIGHT \S+ \S+ ratio=", proc.stdout, re.M)), 5 * platforms)
            self.assertNotIn("REFUSED", proc.stdout)


if __name__ == "__main__":
    unittest.main()
