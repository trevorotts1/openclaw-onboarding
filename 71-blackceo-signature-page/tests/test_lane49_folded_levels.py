#!/usr/bin/env python3
"""LANE-49: a sales page that folds N levels into itself (journey_mode folded_levels, no selection
page) closes on an N-card levels panel, on the wireframes, with every card's button leading to
checkout; and a second downsell is labelled Downsell 2 on every file it makes.

No provider is called anywhere in this module.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import deliverable_labels as labels  # noqa: E402
import page_kinds as pk  # noqa: E402
import wireframe_spec as w  # noqa: E402


def slice_block(kind, index, total, **request_extra):
    request = {"copy_version": "long-form", "page_kind": kind, **request_extra}
    section = {"section_id": str(index), "section_name": "Founder letter", "copy": "A finished sentence.",
               "cta": "GET IT", "slots": []}
    return w.prompt_block("desktop-wireframe", section, index, total, 1440, request)


class FoldedLevelsTests(unittest.TestCase):
    def test_sales_page_closes_on_a_three_card_levels_panel(self):
        last = slice_block("sales", 15, 15, folded_levels=3)
        self.assertIn("exactly 3 level cards", last)
        self.assertIn("one card per level", last)
        self.assertNotIn("one full-width closing checkout panel", last)

    def test_levels_panel_is_on_the_last_slice_only(self):
        self.assertNotIn("level cards", slice_block("sales", 14, 15, folded_levels=3))

    def test_without_levels_the_sales_page_is_byte_for_byte_unchanged(self):
        plain = slice_block("sales", 15, 15)
        self.assertEqual(plain, slice_block("sales", 15, 15, folded_levels=None))
        self.assertEqual(plain, slice_block("sales", 15, 15, folded_levels=1))
        self.assertIn("closing checkout panel", plain)

    def test_an_opt_in_page_never_shows_levels(self):
        self.assertEqual(slice_block("opt_in", 15, 15), slice_block("opt_in", 15, 15, folded_levels=3))

    def test_a_bad_level_count_is_refused(self):
        with self.assertRaises(pk.KindError):
            pk.wireframe_lines("sales", "Long-Form", 15, 15, "GET IT", levels="three")

    def test_mockup_line_carries_the_levels_panel(self):
        self.assertIn("exactly 3 level cards", pk.mockup_line("sales", "GET IT", levels=3))
        self.assertNotIn("level cards", pk.mockup_line("sales", "GET IT"))


class SecondDownsellLabelTests(unittest.TestCase):
    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        Path(self.run_dir, "page-request.json").write_text('{"page_role": "downsell_1"}', encoding="utf-8")
        os.environ.pop("SIGNATURE_ROLE_INSTANCE", None)

    def tearDown(self):
        os.environ.pop("SIGNATURE_ROLE_INSTANCE", None)

    def test_a_downsell_run_is_downsell_1_unless_it_is_the_second_instance(self):
        self.assertEqual(labels.declared_page_role(self.run_dir), "downsell_1")
        os.environ["SIGNATURE_ROLE_INSTANCE"] = "downsell_2"
        self.assertEqual(labels.declared_page_role(self.run_dir), "downsell_2")
        self.assertEqual(labels.title_band("downsell_2", "mobile", "visual-mockup", 8),
                         "DOWNSELL 2 · MOBILE MOCKUP · 8 SECTIONS")

    def test_an_instance_of_another_family_is_ignored(self):
        os.environ["SIGNATURE_ROLE_INSTANCE"] = "upsell_2"
        self.assertEqual(labels.declared_page_role(self.run_dir), "downsell_1")


if __name__ == "__main__":
    unittest.main()
