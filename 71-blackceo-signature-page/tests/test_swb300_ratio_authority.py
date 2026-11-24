#!/usr/bin/env python3
"""SWB-300 items d1 and d2.

d1: section['layout_aspect_ratio'] read from production-request.json is honoured only when it is a portrait
or square ratio for the mobile viewport AND request.layout_overrides.applied holds a matching row (stage,
section, ratio). A landscape ratio, a bare field with no row, a row for another section, ratio or stage are
all ignored by target_ratio and refused by load_request.
d2: an override entry carrying `negatives` without non-empty `layout` text is refused (it used to be
accepted with the negatives silently dropped).
"""
import copy
import json
import os
import sys
import unittest
from pathlib import Path

os.environ["SKILL71_FIXTURE_RUN"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_layout_overrides import Base, TEXT  # noqa: E402
from test_page_role_thank_you import builder, exe  # noqa: E402
from test_swb290_aspect_override import section  # noqa: E402

MOBILE = "mobile/part-02.png"


class RatioAuthorityTests(Base):
    def built(self, stage="final-mockups", ratio="1:1"):
        return self.build_with(self.put({stage: {"2": {"aspect_ratio": ratio}}}), stage)

    def ratio(self, req, stage="final-mockups", template=MOBILE):
        return exe.target_ratio(stage, template, section(req, "2"), self.run, 2, req)

    def test_a_recorded_portrait_ratio_is_honoured(self):
        self.assertEqual(self.ratio(self.built()), "1:1")
        self.assertIsNone(exe._forced_ratio_refusal(section(self.built(), "2"), self.built()))

    def test_a_landscape_ratio_is_ignored_and_refused(self):
        for stage, template in (("final-mockups", MOBILE), ("mobile-tablet", "section-02.png")):
            req = self.built(stage)
            req = copy.deepcopy(req)
            section(req, "2")["layout_aspect_ratio"]["ratio"] = "16:9"
            for row in req["layout_overrides"]["applied"]:
                row["aspect_ratio"] = "16:9"  # even a matching row cannot legitimise a landscape frame
            self.assertNotEqual(self.ratio(req, stage, template), "16:9", stage)
            self.assertIn("landscape", exe._forced_ratio_refusal(section(req, "2"), req))

    def test_a_field_with_no_matching_row_is_ignored_and_refused(self):
        req = copy.deepcopy(self.built())
        plain = self.ratio(self.build_with(None, "final-mockups"))
        req["layout_overrides"]["applied"] = []
        self.assertEqual(self.ratio(req), plain)
        self.assertIn("no matching row", exe._forced_ratio_refusal(section(req, "2"), req))
        no_block = copy.deepcopy(req)
        del no_block["layout_overrides"]
        self.assertEqual(self.ratio(no_block), plain)

    def test_a_row_for_another_section_ratio_or_stage_does_not_match(self):
        for edit in (lambda r: r["applied"][0].__setitem__("section_id", "3"),
                     lambda r: r["applied"][0].__setitem__("aspect_ratio", "3:4"),
                     lambda r: r.__setitem__("stage", "mobile-tablet")):
            req = copy.deepcopy(self.built())
            edit(req["layout_overrides"])
            self.assertIn("no matching row", exe._forced_ratio_refusal(section(req, "2"), req))

    def test_load_request_refuses_a_landscape_or_unrecorded_field(self):
        for edit, needle in ((lambda d: section(d, "2").__setitem__(
                                  "layout_aspect_ratio", {"stage": "mobile-tablet", "viewport": "mobile", "ratio": "16:9"}),
                              "landscape"),
                             (lambda d: d.pop("layout_overrides", None), "no matching row")):
            req = copy.deepcopy(self.built("mobile-tablet", "3:4"))
            section(req, "2")["layout_aspect_ratio"]["ratio"] = "3:4"
            edit(req)
            (self.run / "production-request.json").write_text(json.dumps(req), encoding="utf-8")
            with self.assertRaises(exe.ExecutorError) as cm:
                exe.load_request(self.run, "production-request.json")
            self.assertIn(needle, str(cm.exception))


class NegativesNeedTextTests(Base):
    def test_negatives_without_layout_text_are_refused(self):
        for entry in ({"negatives": "no stock photos"},
                      {"aspect_ratio": "1:1", "negatives": "no stock photos"},
                      {"aspect_ratio": "1:1", "negatives": "x", "layout": "   "}):
            with self.assertRaises(builder.BuildError, msg=str(entry)) as cm:
                self.build_with(self.put({"mobile-tablet": {"2": entry}}))
            self.assertIn("non-empty `layout`", str(cm.exception))

    def test_negatives_with_layout_text_still_apply(self):
        out = self.build_with(self.put({"mobile-tablet": {"2": {"layout": TEXT, "negatives": "no stock"}}}))
        self.assertIn("NEGATIVES: no stock", section(out, "2")["layout"])


if __name__ == "__main__":
    unittest.main()
