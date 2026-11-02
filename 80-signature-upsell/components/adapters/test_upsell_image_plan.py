"""UPS-20 / UPS-21 - the upsell image plan and the upsell band layout.

UPS-20: U1 and U2 each get a per-section plan (subject, composition, offer-specific art
direction) that reaches the production request through --slots; none of it is the
section heading, and U1's differs from U2's.
UPS-21: page-structures.json declares upsell_1 / upsell_2 with per-section band tags, the
wireframe spec has a line for every section 1 to 8, and a wireframe slice of every
section carries the tag declared for it.

Run: python3 -m pytest 80-signature-upsell/components/adapters/test_upsell_image_plan.py -q
"""
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ADAPTERS = Path(__file__).resolve().parent
SKILL80 = ADAPTERS.parents[1]
SKILL71 = SKILL80.parent / "71-blackceo-signature-page"
FIX = SKILL80 / "components" / "80-signature-upsell" / "fixtures"
sys.path.insert(0, str(ADAPTERS))
import upsell_image_plan as plan  # noqa: E402

IDS = [str(i) for i in range(1, 9)]
REQ = {"upsell_1": SKILL80 / "examples" / "request-upsell1.example.json",
       "upsell_2": SKILL80 / "examples" / "request-upsell2.example.json"}
COPY = {"upsell_1": FIX / "copy-upsell1-public.valid.json", "upsell_2": FIX / "copy-upsell2-public.valid.json"}
BUNDLE = {"upsell_1": SKILL80 / "examples" / "upsell-result-bundle-upsell1.example.json",
          "upsell_2": SKILL80 / "examples" / "upsell-result-bundle-upsell2-from-downsell1.example.json"}
BIBLE = {"world": "a sunlit home studio", "look": "warm editorial grade", "casting": "adults 35 to 55",
         "avoid": ["gym scenes"]}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_module(name):
    scripts = str(SKILL71 / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(name, SKILL71 / "scripts" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def slots_for(role, bible=None):
    return plan.build_slots(load(REQ[role]), bible)


class ImagePlanTests(unittest.TestCase):
    def test_each_instance_plans_all_eight_sections_with_subject_and_composition(self):
        for role in REQ:
            slots = slots_for(role)
            self.assertEqual(list(slots), IDS)
            for sid, (slot,) in slots.items():
                self.assertEqual(slot["slot_id"], "IMG-%03d" % int(sid))
                self.assertTrue(slot["subject"] and slot["composition"], (role, sid))
                self.assertIn(slot["subject"], slot["art_direction"])
                self.assertIn(slot["composition"], slot["art_direction"])

    def test_art_direction_is_not_the_heading_and_is_not_derived_from_it(self):
        for role in REQ:
            headings = {str(d["number"]): d["heading"] for d in load(COPY[role])["sections"]}
            for sid, (slot,) in slots_for(role).items():
                art = slot["art_direction"].lower()
                self.assertNotEqual(art, headings[sid].lower())
                self.assertNotIn(headings[sid].lower(), art, (role, sid))
                self.assertNotIn("illustrates", art)

    def test_u2_has_its_own_plan_and_every_direction_is_unique(self):
        u1, u2 = slots_for("upsell_1"), slots_for("upsell_2")
        for sid in IDS:
            self.assertNotEqual(u1[sid][0]["art_direction"], u2[sid][0]["art_direction"], sid)
            self.assertNotEqual(u1[sid][0]["subject"], u2[sid][0]["subject"], sid)
            self.assertNotEqual(u1[sid][0]["composition"], u2[sid][0]["composition"], sid)
        for slots in (u1, u2):
            arts = [s[0]["art_direction"] for s in slots.values()]
            self.assertEqual(len(set(arts)), 8)

    def test_plan_is_offer_specific_and_takes_the_visual_bible(self):
        request = load(REQ["upsell_1"])
        slots = plan.build_slots(request, BIBLE)
        name = request["offer"]["display_name"]
        self.assertIn(name, slots["1"][0]["art_direction"])
        self.assertIn(request["offer"]["deliverables"][0], slots["1"][0]["art_direction"])
        self.assertIn(request["offer"]["deliverables"][2], slots["7"][0]["art_direction"])
        for (slot,) in slots.values():
            for word in ("warm editorial grade", "a sunlit home studio", "adults 35 to 55", "gym scenes"):
                self.assertIn(word, slot["art_direction"])
        other = copy.deepcopy(request)
        other["offer"]["display_name"] = "Another Offer"
        self.assertNotEqual(plan.build_slots(other)["1"], slots_for("upsell_1")["1"])

    def test_ratios_come_from_the_declared_layout_and_are_listed_labels(self):
        labels = load(SKILL71 / "references" / "wireframe-build-spec.json")["ratio_labels"]
        layouts = load(SKILL71 / "references" / "page-structures.json")["layouts"]
        for role in REQ:
            for sec in layouts[role]["sections"]:
                (slot,) = slots_for(role)[sec["id"]]
                self.assertEqual((slot["slot_id"], slot["aspect_ratio"]),
                                 (sec["slot"]["slot_id"], sec["slot"]["aspect_ratio"]))
                self.assertIn(slot["aspect_ratio"], labels)

    def test_refuses_an_unknown_instance_and_an_offer_without_a_name(self):
        request = load(REQ["upsell_1"])
        bad = dict(request, instance="landing", page_role="landing")
        with self.assertRaises(plan.PlanError):
            plan.build_slots(bad)
        nameless = copy.deepcopy(request)
        nameless["offer"]["display_name"] = " "
        with self.assertRaises(plan.PlanError):
            plan.build_slots(nameless)

    def test_cli_writes_a_slots_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "slots.json"
            self.assertEqual(plan.main(["--request", str(REQ["upsell_2"]), "--out", str(out)]), 0)
            self.assertEqual(load(out), slots_for("upsell_2"))


@unittest.skipUnless(SKILL71.is_dir(), "Skill 71 is not installed beside Skill 80")
class ProductionRequestTests(unittest.TestCase):
    """The plan reaches the production request through --slots (sections and full build)."""

    @classmethod
    def setUpClass(cls):
        cls.builder = load_module("build_production_request")
        cls.exe = cls.builder.exe
        cls.spec = load(cls.exe.SPEC_DIR / "upsell-v6.json")

    def sections(self, role, slots):
        return self.builder.sections_from_copy_json(load(COPY[role]), load(BUNDLE[role]), self.spec, slots)

    def test_sections_carry_the_plan_not_the_heading_default(self):
        for role in REQ:
            sections = self.sections(role, slots_for(role))
            for s, doc in zip(sections, load(COPY[role])["sections"]):
                art = s["slots"][0]["art_direction"]
                self.assertNotIn("illustrates", art)
                self.assertNotIn(doc["heading"], art)

    def test_u1_and_u2_production_requests_differ_per_section(self):
        sys.path.insert(0, str(SKILL71 / "tests"))
        from brand_fixture import give_blackceo_colors
        arts = {}
        for role in REQ:
            with tempfile.TemporaryDirectory() as tmp:
                give_blackceo_colors(Path(tmp))
                request = self.builder.build("visual-mockup", "upsell", "", slots_for(role), {}, [],
                                             "STUB-NO-MODEL", "", Path(tmp), role,
                                             sections=self.sections(role, slots_for(role)))
            self.assertEqual(request["page_role"], role)
            arts[role] = [s["slots"][0]["art_direction"] for s in request["sections"]]
            headings = [d["heading"] for d in load(COPY[role])["sections"]]
            self.assertEqual(len(arts[role]), 8)
            for art, heading in zip(arts[role], headings):
                self.assertTrue(art and art != heading and heading not in art)
        for a, b in zip(arts["upsell_1"], arts["upsell_2"]):
            self.assertNotEqual(a, b)


@unittest.skipUnless(SKILL71.is_dir(), "Skill 71 is not installed beside Skill 80")
class LayoutTagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_module("build_production_request")
        cls.wf = cls.builder.wireframe_spec
        cls.layouts = load(SKILL71 / "references" / "page-structures.json")["layouts"]
        cls.spec = load(cls.builder.exe.SPEC_DIR / "upsell-v6.json")

    def test_both_roles_declare_eight_sections_with_geometry_and_a_unique_band_tag(self):
        for role in REQ:
            entry = self.layouts[role]
            self.assertEqual(entry["sequence"], IDS)
            self.assertEqual([s["id"] for s in entry["sections"]], IDS)
            tags = [s["layout_tag"] for s in entry["sections"]]
            self.assertEqual(len(set(tags)), 8, "no two bands share a layout tag")
            self.assertTrue(all(s["geometry"] and s["slot"] for s in entry["sections"]))
            self.assertEqual(entry["sequence"], self.spec["sequence"])
        self.assertEqual([s["layout_tag"] for s in self.layouts["upsell_1"]["sections"]],
                         [s["layout_tag"] for s in self.layouts["upsell_2"]["sections"]])

    def test_the_wireframe_spec_covers_every_section_with_its_declared_tag(self):
        lines = self.wf.spec()["page_type_blocks"]["upsell"]
        for role in REQ:
            for sec in self.layouts[role]["sections"]:
                self.assertIn("LAYOUT TAG " + sec["layout_tag"], lines[sec["id"]], (role, sec["id"]))

    def test_a_wireframe_run_of_each_section_matches_a_declared_layout_tag(self):
        for role in REQ:
            sections = self.builder.sections_from_copy_json(load(COPY[role]), load(BUNDLE[role]), self.spec, slots_for(role))
            request = {"copy_version": "upsell", "page_role": role, "sections": sections}
            declared = {s["id"]: s["layout_tag"] for s in self.layouts[role]["sections"]}
            for stage, width in (("desktop-wireframe", 1440), ("mobile-tablet", 390)):
                for i, section in enumerate(sections, 1):
                    prompt = self.wf.prompt_block(stage, section, i, 8, width, request)
                    found = [t for t in declared.values() if "LAYOUT TAG " + t + " " in prompt]
                    self.assertEqual(found, [declared[section["section_id"]]], (role, stage, i))

    def test_each_layout_names_its_80_layout_reference_and_it_lists_every_tag(self):
        ref = "80-signature-upsell/components/80-signature-upsell/references/wireframe-layout.md"
        for role in REQ:
            self.assertEqual(self.layouts[role]["layout_reference"], ref)
            text = (SKILL80.parent / ref).read_text(encoding="utf-8")
            for sec in self.layouts[role]["sections"]:
                self.assertIn(sec["layout_tag"], text, (role, sec["id"]))


if __name__ == "__main__":
    unittest.main()
