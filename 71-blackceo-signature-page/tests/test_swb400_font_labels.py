#!/usr/bin/env python3
"""SWB-400 items 3 and 4: the sheet prints the closed font plan's sizes and the W3 plate label.

Trevor's diagnosis (2026-11-24): the printed type sizes came from the house scale ("H1 56-72, H2 48-64, Body
18-20, CTA 18-20") because no request section carried type_specs and nothing read font-action-plan/font-map.json;
and the plate label read "IMAGE 4:3 - warm celebration" where the rubric's W3 wants the slot id, the pixel box, the
ratio and the treatment ("IMG-001 540 x 540 1:1 overlay-light") from the closed image inventory.

  - scripts/font_sizes.py reads the font map's typography records: desktop and tablet for the desktop sheet,
    tablet and mobile for the mobile-tablet sheet; an element the font plan does not size keeps its house range;
  - build_production_request.py copies those sizes into each wireframe section's type_specs (and records the
    source); a run with no font map, and every non-wireframe stage, is unchanged;
  - a page role's slots take the closed inventory's id, treatment and (when it records one) pixel box; a slot that
    disagrees with its entry in ratio or treatment is refused; no inventory yet changes nothing;
  - the plate and SLOT lines print `<id> <w> x <h> <ratio> <treatment>`, the mobile sheet the mobile box.
No paid call is made.
"""
import copy
import json
import os
import re
import sys
import unittest

os.environ["SKILL71_FIXTURE_RUN"] = "1"
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
from test_page_role_thank_you import SPEC, builder, exe, w  # noqa: E402
from test_section_count import REAL_MODEL  # noqa: E402
from test_swb310_floor_and_slot import realistic_prose  # noqa: E402
from test_swb400_section_plan import FONT_MAP, INVENTORY, PlanCase, typography  # noqa: E402
import composition  # noqa: E402
import font_sizes  # noqa: E402

STAGES = (("desktop-wireframe", 1440), ("mobile-tablet", 390))
HOUSE = ("48-64", "56-72", "18-20")


def line(prompt, head):
    return [l for l in prompt.splitlines() if head in l][0]


class FontSizesTests(unittest.TestCase):
    def test_captions_are_the_stages_two_viewports(self):
        self.assertEqual(font_sizes.caption(FONT_MAP, "H1", "desktop-wireframe"), "72 px desktop, 56 px tablet")
        self.assertEqual(font_sizes.caption(FONT_MAP, "H2", "mobile-tablet"), "36 px tablet, 28 px mobile")
        self.assertEqual(font_sizes.caption(FONT_MAP, "CTA", "desktop-wireframe"), "19 px desktop, 18 px tablet")

    def test_an_element_the_font_plan_does_not_size_has_no_caption(self):
        self.assertIsNone(font_sizes.caption(FONT_MAP, "Subhead", "desktop-wireframe"))
        self.assertIsNone(font_sizes.caption(FONT_MAP, "CTA microcopy", "desktop-wireframe"))
        partial = {"typography": [{"element": "body", "sizes": {"desktop": {"px": 21}}}]}
        self.assertIsNone(font_sizes.caption(partial, "Body", "desktop-wireframe"))  # no tablet size: never half a pair
        self.assertIsNone(font_sizes.caption(FONT_MAP, "H2", "visual-mockup"))

    def test_plan_specs_name_the_face_and_refuse_a_missing_record(self):
        specs = font_sizes.plan_specs(FONT_MAP, "desktop-wireframe")
        self.assertEqual(sorted(specs), ["body", "cta", "h1", "h2"])
        self.assertEqual(specs["h1"], "Playfair Display 72px / 1.02 desktop, 56px / 1.02 tablet")
        broken = {"fonts": FONT_MAP["fonts"], "typography": typography()[:2]}
        with self.assertRaises(font_sizes.FontMapError) as cm:
            font_sizes.plan_specs(broken, "desktop-wireframe")
        self.assertIn("body", str(cm.exception))


class RequestTests(PlanCase):
    def built(self, stage, **kw):
        return self.build(stage=stage, model=REAL_MODEL, prose=realistic_prose(), **kw)

    def test_each_wireframe_section_carries_the_font_maps_sizes(self):
        desktop = self.built("desktop-wireframe")
        two = desktop["sections"][1]["type_specs"]
        self.assertEqual(two, {"H2": "44 px desktop, 36 px tablet", "Body": "21 px desktop, 20 px tablet"})
        one = desktop["sections"][0]["type_specs"]
        self.assertEqual(one["H1"], "72 px desktop, 56 px tablet")
        self.assertEqual(one["CTA"], "19 px desktop, 18 px tablet")
        self.assertEqual(one["CTA microcopy"], "12-14 px")  # the font plan sizes no microcopy: the house range stays
        mobile = self.built("mobile-tablet")["sections"][1]["type_specs"]
        self.assertEqual(mobile, {"H2": "36 px tablet, 28 px mobile", "Body": "20 px tablet, 18 px mobile"})
        self.assertEqual(desktop["metadata"]["type_specs_source"], "font-action-plan/font-map.json")

    def test_the_printed_type_specs_are_the_run_sizes_not_the_house_ranges(self):
        for stage, width in STAGES:
            request = self.built(stage)
            request["_brand_block"] = exe.require_brand_colors(self.run)
            request["_hypersat"] = exe.hypersaturation.roles_for_run(self.run)
            for index in range(1, 6):
                prompt = exe.stage_prompt(stage, request["sections"][index - 1], index, width, request, "16:9")
                specs = line(prompt, "INLINE TYPE SPECS")
                for house in HOUSE:
                    self.assertNotIn(house, specs, (stage, index, house))
                self.assertRegex(specs, r"\d+ px (desktop|tablet)", (stage, index))
            two = line(exe.stage_prompt(stage, request["sections"][1], 2, width, request, "16:9"), "INLINE TYPE SPECS")
            self.assertIn("H2 / " + ("44 px desktop, 36 px tablet" if stage == "desktop-wireframe" else "36 px tablet, 28 px mobile"), two)
            self.assertNotIn("SUBHEAD /", two)

    def test_no_font_map_and_other_stages_are_unchanged(self):
        (self.run / "font-action-plan" / "font-map.json").unlink()
        request = self.built("desktop-wireframe")
        self.assertTrue(all("type_specs" not in s for s in request["sections"]))
        self.assertNotIn("type_specs_source", request["metadata"])
        self.put("font-action-plan/font-map.json", FONT_MAP)
        mockup = self.build(stage="visual-mockup")  # the stub model has no prompt floor
        self.assertTrue(all("type_specs" not in s for s in mockup["sections"]))

    def test_an_unreadable_font_map_is_a_named_refusal(self):
        (self.run / "font-action-plan" / "font-map.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(builder.BuildError) as cm:
            self.built("desktop-wireframe")
        self.assertIn("font-map.json", str(cm.exception))


class InventorySlotTests(PlanCase):
    def built(self, stage="desktop-wireframe"):
        return self.build(stage=stage, model=REAL_MODEL, prose=realistic_prose())

    def slot(self, request):
        return request["sections"][0]["slots"][0]

    def test_a_closed_inventory_names_the_slot_and_its_treatment(self):
        request = self.built()
        slot = self.slot(request)
        self.assertEqual((slot["slot_id"], slot["inventory_id"], slot["treatment"]), ("TY-IMG-01", "IMG-001", "overlay-light"))
        self.assertEqual(slot["delivery_px"], {"desktop": [540, 540], "mobile": [342, 342]})  # the spec's box
        self.assertEqual(request["metadata"]["slot_labels_source"], "desktop-wireframe/image-inventory.json")

    def test_the_inventorys_own_pixel_box_wins_over_the_specs(self):
        inventory = copy.deepcopy(INVENTORY)
        inventory["images"][0]["delivery_px"] = {"desktop": [600, 600], "mobile": [300, 300]}
        self.put("desktop-wireframe/image-inventory.json", inventory)
        self.assertEqual(self.slot(self.built())["delivery_px"], {"desktop": [600, 600], "mobile": [300, 300]})

    def test_no_inventory_yet_changes_nothing(self):
        (self.run / "desktop-wireframe" / "image-inventory.json").unlink()
        request = self.built()
        slot = self.slot(request)
        self.assertNotIn("inventory_id", slot)
        self.assertNotIn("treatment", slot)
        self.assertNotIn("slot_labels_source", request["metadata"])

    def test_a_slot_that_disagrees_with_its_inventory_entry_is_refused(self):
        for change, needle in (({"aspect_ratio": "4:3"}, "closed image inventory says 4:3"),
                               ({"treatment": "mask-circle"}, "closed inventory says 'mask-circle'")):
            inventory = copy.deepcopy(INVENTORY)
            inventory["images"][0].update(change)
            self.put("desktop-wireframe/image-inventory.json", inventory)
            if "treatment" in change:  # a request that declares a treatment: the style's own
                with self.assertRaises(builder.BuildError) as cm:
                    builder.apply_inventory(self.with_declared("overlay-light"), self.run)
            else:
                with self.assertRaises(builder.BuildError) as cm:
                    self.built()
            self.assertIn(needle, str(cm.exception))

    def with_declared(self, treatment):
        request = self.build(stage="visual-mockup")  # a request, any stage; the stage does not apply the inventory
        request["sections"][0]["slots"][0]["treatment"] = treatment
        return request

    def test_a_box_that_is_not_the_slots_ratio_is_refused(self):
        request = self.build(stage="visual-mockup")
        for box, needle in (({"desktop": [540, 300], "mobile": [342, 342]}, "is not the slot's ratio"),
                            ({"desktop": [540, 540]}, "delivery_px mobile must be"),
                            ({"desktop": [540.5, 540], "mobile": [342, 342]}, "whole pixels")):
            broken = copy.deepcopy(request)
            broken["sections"][0]["slots"][0]["delivery_px"] = box
            with self.assertRaises(builder.BuildError) as cm:
                builder.check_slot_boxes(broken)
            self.assertIn(needle, str(cm.exception))

    def test_a_landing_request_is_never_matched_to_the_inventory(self):
        request = {"sections": [{"section_id": "1", "slots": [{"slot_id": "TY-IMG-01", "aspect_ratio": "4:3"}]}]}
        self.assertFalse(builder.apply_inventory(request, self.run))  # no page_role: left alone
        self.assertNotIn("inventory_id", request["sections"][0]["slots"][0])


class PlateLabelTests(PlanCase):
    def prompt(self, stage, width, index=1):
        request = self.build(stage=stage, model=REAL_MODEL, prose=realistic_prose())
        request["_brand_block"] = exe.require_brand_colors(self.run)
        request["_hypersat"] = exe.hypersaturation.roles_for_run(self.run)
        return exe.stage_prompt(stage, request["sections"][index - 1], index, width, request, "16:9")

    def test_the_plate_and_slot_lines_print_id_box_ratio_and_treatment(self):
        for (stage, width), box in zip(STAGES, ("540 x 540", "342 x 342")):
            prompt = self.prompt(stage, width)
            label = f"IMG-001 {box} 1:1 overlay-light"
            self.assertIn(f'Print "{label}" as this slot\'s label.', prompt, stage)
            plates = line(prompt, "IMAGE PLATES")
            self.assertIn(f'one plate labelled "{label}"', plates, stage)
            self.assertIn("with the art direction", plates)
            self.assertNotIn("reading IMAGE, the ratio", plates, stage)
            self.assertNotIn('"IMAGE 1:1 -', prompt, stage)
            self.assertEqual(len(re.findall(r"IMG-001 \d+ x \d+", plates)), 1, stage)

    def test_a_run_without_an_inventory_prints_the_spec_slot_with_its_box(self):
        (self.run / "desktop-wireframe" / "image-inventory.json").unlink()
        prompt = self.prompt("desktop-wireframe", 1440)
        self.assertIn('"TY-IMG-01 540 x 540 1:1 overlay-light"', line(prompt, "IMAGE PLATES"))

    def test_a_slot_with_no_box_keeps_the_generic_plate_label(self):
        section = {"section_id": "3", "slots": [{"slot_id": "S3", "aspect_ratio": "4:3", "art_direction": "a quiet desk"}]}
        self.assertFalse(w.labelled_plates(section))
        self.assertEqual(w._plates(section), 'one plate labelled "IMAGE 4:3 - a quiet desk"')

    def test_the_composition_label_prefers_the_inventory_id_and_the_stages_box(self):
        slot = {"slot_id": "TY-IMG-01", "inventory_id": "IMG-001", "aspect_ratio": "1:1",
                "delivery_px": {"desktop": [540, 540], "mobile": [342, 342]}}
        self.assertEqual(composition._label(slot, "split", "desktop-wireframe"), "IMG-001 540 x 540 1:1 split")
        self.assertEqual(composition._label(slot, "split", "mobile-tablet"), "IMG-001 342 x 342 1:1 split")
        self.assertEqual(composition._label({"slot_id": "S1", "aspect_ratio": "4:3"}, "split"), "S1 4:3 split")
        only_desktop = dict(slot, delivery_px={"desktop": [540, 540]})
        self.assertEqual(composition._label(only_desktop, "split", "mobile-tablet"), "IMG-001 540 x 540 1:1 split")


class SpecBoxTests(unittest.TestCase):
    def test_the_spec_states_the_hero_slots_boxes_at_its_own_ratio(self):
        slot = SPEC["sections"][0]["default_slots"][0]
        self.assertEqual(slot["delivery_px"], {"desktop": [540, 540], "mobile": [342, 342]})
        for box in slot["delivery_px"].values():
            self.assertEqual(box[0], box[1])  # 1:1
        self.assertEqual(slot["aspect_ratio"], "1:1")


if __name__ == "__main__":
    unittest.main()
