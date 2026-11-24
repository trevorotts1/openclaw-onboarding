#!/usr/bin/env python3
"""SWB-310 items a, b and the slot rule of d.

a: the thank-you spec carries enough genuine specification that every section of the desktop-wireframe and
   mobile-tablet requests clears the 16,000-character 80 percent floor with the real model and a design-prose
   file and NO layout-overrides file (it used to refuse section 2 by 397 characters).
b: section 5 is the filled support button, the help email line and the signature line only: no outlined button,
   no manage-purchase button and no behaviour note that names one.
d: stage_executor re-checks a section's slot ratio: a recorded override row never outranks the ratio of a
   non-circle image slot on that section (a circle slot is 1:1 for its mask and never conflicts).
"""
import copy
import json
import os
import sys
import unittest

os.environ["SKILL71_FIXTURE_RUN"] = "1"
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_layout_overrides import Base  # noqa: E402
from test_page_role_thank_you import FIXTURE, SPEC, RunCase, builder, exe  # noqa: E402
from test_section_count import REAL_MODEL, design_prose  # noqa: E402
from test_swb290_aspect_override import section  # noqa: E402

FLOOR = 16000
BANNED = ("real table", "MANAGE PURCHASE", "status chip")
STAGES = (("desktop-wireframe", "desktop"), ("mobile-tablet", "mobile"))
MOBILE = "mobile/part-02.png"


def realistic_prose():
    """The shape and size of a run's dispatched design-prose file (about 4 KB, empty traits)."""
    return {"notes": "PAGE STRUCTURE: thank-you page, 5 sections in this order. DESIGN STYLE A: traditional "
                     "editorial layout with square-cornered rectangles, full-width alternating bands, "
                     "rectangular buttons and hairline rules.",
            "traits": "", "rules_md": design_prose(3300)["rules_md"]}


class PromptFloorTests(RunCase):
    def manuscripts(self):
        full = FIXTURE.read_text(encoding="utf-8")
        # the approved copy of section 5 carries one button, the help email and the sign-off only
        one_button = full.replace("Manage purchase\n\n", "")
        self.assertNotEqual(one_button, full)
        return {"fixture": full, "one-button close": one_button}

    def test_every_section_clears_the_floor_with_no_overrides_file(self):
        for label, text in self.manuscripts().items():
            for stage, viewport in STAGES:
                # builder.build refuses (BuildError "prompt budget") when any section is under the floor
                request = self.build(stage=stage, model=REAL_MODEL, prose=realistic_prose(), text=text)
                self.assertNotIn("layout_overrides", request, (label, stage))
                self.assertEqual(len(request["sections"]), 5)
                for index, entry in enumerate(request["sections"], start=1):
                    spec_section = SPEC["sections"][index - 1]
                    approved = spec_section["layout"][viewport]
                    for _template, width, _height in exe.LAYOUT[stage]:
                        where = (label, stage, index, width)
                        request["_brand_block"] = exe.require_brand_colors(self.run)
                        request["_hypersat"] = exe.hypersaturation.roles_for_run(self.run)
                        prompt = exe.stage_prompt(stage, entry, index, width, request, "16:9", strict_floor=True)
                        self.assertGreaterEqual(len(prompt), FLOOR, where)
                        # the approved design text of the spec reaches the prompt, not filler
                        self.assertIn(approved.split(". ")[0][:60], prompt, where)
                        self.assertIn("Spacing and type:", prompt, where)
                        for banned in BANNED:
                            self.assertNotIn(banned, prompt, where + (banned,))

    def test_the_spec_alone_carries_the_floor_not_repetition(self):
        # a section's layout text holds no repeated 8-word run (the validator's padding screen)
        for entry in SPEC["sections"]:
            for viewport in ("desktop", "mobile"):
                words = entry["layout"][viewport].lower().split()
                grams = [" ".join(words[i:i + 8]) for i in range(len(words) - 7)]
                self.assertEqual(len(grams), len(set(grams)), (entry["id"], viewport))


class SectionFiveTests(RunCase):
    def test_section_five_is_the_support_button_the_help_line_and_the_signature_only(self):
        entry = SPEC["sections"][4]
        blob = json.dumps(entry).lower()
        for gone in ("outlined", "open my access page", "manage purchase", "manage-purchase", "manage the purchase",
                     "secondary"):
            self.assertNotIn(gone, blob, gone)
        for kept in ("filled support button", "only button", "support email address", "signature line"):
            self.assertIn(kept, blob, kept)
        self.assertNotIn("outlined", entry["note"].lower())
        self.assertNotIn("manage", SPEC["cta_map"]["note"].lower())

    def test_the_closing_prompt_names_no_second_button_at_either_width(self):
        for stage, width in (("desktop-wireframe", 1440), ("mobile-tablet", 390)):
            request = self.build(stage=stage)
            request["_brand_block"] = exe.require_brand_colors(self.run)
            request["_hypersat"] = exe.hypersaturation.roles_for_run(self.run)
            close = exe.stage_prompt(stage, request["sections"][4], 5, width, request, "16:9")
            self.assertIn("filled support button", close, stage)
            # the spec's own text for the section: the page-type block and the behavior note line
            block = close.split("PAGE TYPE STRUCTURE", 1)[1].split("\n\n", 1)[0]
            note = [l for l in close.splitlines() if "BEHAVIOR NOTE" in l and "exactly" in l][0]
            for part in (block, note):
                self.assertNotIn("outlined", part, stage)
                self.assertNotIn("carrying the copy's own label and", part, stage)
            self.assertNotIn("Open my access page", close, stage)
            self.assertNotIn("MANAGE PURCHASE", close, stage)


class SlotRatioTests(Base):
    def built(self, ratio="1:1", stage="final-mockups"):
        return self.build_with(self.put({stage: {"2": {"aspect_ratio": ratio}}}), stage)

    def with_slot(self, request, slot):
        request = copy.deepcopy(request)
        section(request, "2")["slots"] = [slot]
        return request

    def ratio(self, request):
        return exe.target_ratio("final-mockups", MOBILE, section(request, "2"), self.run, 2, request)

    def test_an_override_never_outranks_a_conflicting_non_circle_slot(self):
        recorded = self.built()
        self.assertEqual(self.ratio(recorded), "1:1")  # slot-less: the recorded row is honoured
        clash = self.with_slot(recorded, {"slot_id": "TY-IMG-02", "aspect_ratio": "3:4", "art_direction": "x"})
        why = exe._forced_ratio_refusal(section(clash, "2"), clash)
        self.assertIn("slot", why)
        self.assertEqual(self.ratio(clash), "3:4")  # the slot's own ratio governs, not the override
        (self.run / "production-request.json").write_text(json.dumps(clash), encoding="utf-8")
        with self.assertRaises(exe.ExecutorError) as cm:
            exe.load_request(self.run, "production-request.json")
        self.assertIn("slot", str(cm.exception))

    def test_a_matching_auto_or_circle_slot_does_not_conflict(self):
        recorded = self.built()
        for slot in ({"slot_id": "S1", "aspect_ratio": "1:1"},
                     {"slot_id": "S2", "aspect_ratio": "auto"},
                     {"slot_id": "S3", "aspect_ratio": "4:3", "shape": "circle"}):
            req = self.with_slot(recorded, slot)
            self.assertIsNone(exe._forced_ratio_refusal(section(req, "2"), req), slot)
            self.assertEqual(self.ratio(req), "1:1", slot)


if __name__ == "__main__":
    unittest.main()
