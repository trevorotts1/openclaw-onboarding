#!/usr/bin/env python3
"""SWB-290 item D: a validated, design-only aspect_ratio in the layout-overrides section entry.

Sections 2 and 3 of the thank-you page have no image slot, so the mobile frame of those sections fell to
the stage default and left most of the frame blank. <run>/dispatch/layout-overrides.json may now carry
{"<stage>": {"<section id>": {"aspect_ratio": "1:1"}}} (with or without `layout` text):

  - only a ratio from stage_executor.RATIO_ENUM, portrait or square (the mobile frame), for a stage that
    draws a mobile slice, and only for a section with no slot unless the value equals the slot's ratio;
  - recorded in the layout_overrides provenance row, honoured by stage_executor.target_ratio for that
    stage, that section and the MOBILE viewport only; the desktop frame never moves;
  - an absent key leaves every request and every ratio byte for byte as before.
No paid call is made.
"""
import json
import os
import sys
import unittest
from pathlib import Path

os.environ["SKILL71_FIXTURE_RUN"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_layout_overrides import Base, TEXT, RunnerTests  # noqa: E402
from test_page_role_thank_you import builder, exe  # noqa: E402


def section(request, sid):
    return next(s for s in request["sections"] if str(s["section_id"]) == sid)


class AppliedTests(Base):
    def test_a_ratio_only_entry_is_recorded_and_appends_no_text(self):
        plain = self.build_with(None, "final-mockups")
        path = self.put({"final-mockups": {"2": {"aspect_ratio": "1:1"}}})
        out = self.build_with(path, "final-mockups")
        block = out["layout_overrides"]
        self.assertEqual(block["applied"], [{"section_id": "2", "appended_text": "", "aspect_ratio": "1:1",
                                             "viewport": "mobile"}])
        self.assertEqual(section(out, "2").get("layout", ""), section(plain, "2").get("layout", ""))
        self.assertEqual(section(out, "2")["layout_aspect_ratio"],
                         {"stage": "final-mockups", "viewport": "mobile", "ratio": "1:1"})
        for sid in ("1", "3", "4", "5"):
            self.assertNotIn("layout_aspect_ratio", section(out, sid))

    def test_a_ratio_with_layout_text_does_both(self):
        path = self.put({"mobile-tablet": {"3": {"layout": TEXT, "aspect_ratio": "3:4"}}})
        out = self.build_with(path)
        self.assertIn(TEXT, section(out, "3")["layout"])
        self.assertEqual(out["layout_overrides"]["applied"][0]["aspect_ratio"], "3:4")

    def test_the_executor_honours_it_for_that_stage_section_and_the_mobile_viewport_only(self):
        for stage, mobile, desktop in (("final-mockups", "mobile/part-02.png", "desktop/part-02.png"),
                                       ("visual-mockup", "mobile/part-02.png", "desktop/part-02.png")):
            plain = section(self.build_with(None, stage), "2")
            before_m = exe.target_ratio(stage, mobile, plain, self.run, 2)
            before_d = exe.target_ratio(stage, desktop, plain, self.run, 2)
            path = self.put({stage: {"2": {"aspect_ratio": "1:1"}}})
            sec = section(self.build_with(path, stage), "2")
            self.assertEqual(exe.target_ratio(stage, mobile, sec, self.run, 2), "1:1", stage)
            self.assertEqual(exe.target_ratio(stage, desktop, sec, self.run, 2), before_d, stage)
            self.assertNotEqual(before_m, "1:1", "the fixture must show a real change")
            other = "visual-mockup" if stage == "final-mockups" else "final-mockups"
            self.assertEqual(exe.target_ratio(other, mobile, sec, self.run, 2),
                             exe.target_ratio(other, mobile, plain, self.run, 2), "another stage is untouched")

    def test_mobile_tablet_is_a_mobile_stage(self):
        plain = section(self.build_with(None), "2")
        before = exe.target_ratio("mobile-tablet", "section-02.png", plain, self.run, 2)
        sec = section(self.build_with(self.put({"mobile-tablet": {"2": {"aspect_ratio": "3:4"}}})), "2")
        self.assertEqual(exe.target_ratio("mobile-tablet", "section-02.png", sec, self.run, 2), "3:4")
        self.assertEqual(before, "9:16")

    def test_an_absent_key_changes_nothing_byte_for_byte(self):
        plain = self.build_with(None, "final-mockups")
        path = self.put({"final-mockups": {"2": {"layout": TEXT}}})
        out = self.build_with(path, "final-mockups")
        self.assertNotIn("layout_aspect_ratio", json.dumps(out))
        self.assertEqual(out["layout_overrides"]["applied"], [{"section_id": "2", "appended_text": TEXT}])
        for sec in out["sections"]:
            self.assertEqual(exe.target_ratio("final-mockups", "mobile/part-01.png", sec, self.run, 1),
                             exe.target_ratio("final-mockups", "mobile/part-01.png",
                                              section(plain, str(sec["section_id"])), self.run, 1))

    def test_the_section_that_has_a_slot_keeps_it_unless_the_value_is_the_slots(self):
        portrait = {"section_id": "9", "slots": [{"slot_id": "A", "aspect_ratio": "3:4"}]}
        builder._check_aspect_override("final-mockups", "9", "3:4", portrait)  # equal: accepted
        with self.assertRaisesRegex(builder.BuildError, "image slot ratio '3:4'"):
            builder._check_aspect_override("final-mockups", "9", "1:1", portrait)
        auto = {"section_id": "9", "slots": [{"slot_id": "A", "aspect_ratio": "auto"}]}
        builder._check_aspect_override("final-mockups", "9", "1:1", auto)
        circle = {"section_id": "9", "slots": [{"slot_id": "A", "aspect_ratio": "1:1", "shape": "circle"}]}
        builder._check_aspect_override("final-mockups", "9", "3:4", circle)


class RefusalTests(Base):
    def refuses(self, doc, needle, stage="mobile-tablet"):
        path = self.put(doc)
        with self.assertRaises(builder.BuildError) as cm:
            self.build_with(path, stage)
        self.assertIn(needle, str(cm.exception))

    def test_a_landscape_ratio_is_refused(self):
        for r in ("16:9", "4:3", "3:2", "21:9", "9:8"):
            self.refuses({"mobile-tablet": {"2": {"aspect_ratio": r}}}, "landscape")

    def test_an_unknown_or_malformed_ratio_is_refused(self):
        for r in ("5:7", "1:2", "auto", "", "3/4", 0.75, None, ["1:1"]):
            self.refuses({"mobile-tablet": {"2": {"aspect_ratio": r}}}, "must be one of")

    def test_a_section_with_a_slot_is_refused_unless_the_ratio_equals_the_slots(self):
        # thank-you section 1 carries the 4:3 celebration slot: a portrait override differs from it
        self.refuses({"mobile-tablet": {"1": {"aspect_ratio": "3:4"}}}, "image slot ratio")

    def test_the_desktop_wireframe_stage_has_no_mobile_slice(self):
        self.refuses({"desktop-wireframe": {"2": {"aspect_ratio": "1:1"}}}, "mobile slice", "desktop-wireframe")

    def test_other_keys_are_still_refused_beside_the_ratio(self):
        self.refuses({"mobile-tablet": {"2": {"aspect_ratio": "1:1", "copy": "x"}}}, "copy")

    def test_a_layout_text_entry_still_needs_text(self):
        self.refuses({"mobile-tablet": {"2": {"layout": "  ", "aspect_ratio": "1:1"}}}, "non-empty")
        self.refuses({"mobile-tablet": {"2": {"negatives": "x"}}}, "non-empty")

    def test_an_unknown_section_is_still_refused(self):
        self.refuses({"mobile-tablet": {"9": {"aspect_ratio": "1:1"}}}, "unknown section")


class RunnerAspectTests(RunnerTests):
    def test_the_preflight_prints_the_aspect_override(self):
        self.put({"mobile-tablet": {"2": {"aspect_ratio": "1:1"}}})
        proc = self.runner("--preflight", "--stages", "mobile-tablet")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("LAYOUT-OVERRIDE-ASPECT section 2: 1:1 (mobile)", proc.stdout)
        request = json.loads((self.run / "production-request.json").read_text())
        self.assertEqual(request["layout_overrides"]["applied"][0]["aspect_ratio"], "1:1")


# the inherited runner tests are covered by test_layout_overrides; run only the new one here
for _name in [n for n in dir(RunnerAspectTests) if n.startswith("test_") and n != "test_the_preflight_prints_the_aspect_override"]:
    setattr(RunnerAspectTests, _name, None)

if __name__ == "__main__":
    unittest.main()
