#!/usr/bin/env python3
"""SWB-400 item 1: the thank-you order summary prints ONE heading (the closed export's), each sentence once.

Trevor's diagnosis (2026-11-24): section 2 printed the grammar's name tab ORDER SUMMARY (legitimate) and also a
big display headline repeating the item sentence, because the closed heading `What you purchased`
(copy/public-copy.md `## What you purchased`) never reached the VERBATIM COPY block, the spec layout named no
heading words, and the request guessed the first line to be a headline (H2 / SUBHEAD in the type specs).

  - the spec's section 2 carries copy_heading, line_roles [H2, Body, Body] and a dated later_decisions note;
  - the request builder puts the closed heading first in the section's copy (the section carries it, with its
    source) and stamps the declared line roles; section 1 and the others are unchanged;
  - the section 2 desktop and mobile wireframe prompts start the VERBATIM COPY with `What you purchased`, hold
    each sentence exactly once, no SUBHEAD, and the words ORDER SUMMARY only in the grammar name tab;
  - the colour paragraph of section 2 spends no accent fill (the other sections keep the house wording);
  - negative twins: no export falls back to the section name and says so; a heading count that does not pair
    with the sequence refuses; a bad line_roles refuses; a section without line_roles is guessed as before.
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
from test_page_role_thank_you import FIXTURE, SPEC, RunCase, builder, exe, w  # noqa: E402
from test_section_count import REAL_MODEL  # noqa: E402
from test_swb310_floor_and_slot import realistic_prose  # noqa: E402

ITEM = "The Worthiness Gap: Black Friday Intensive."
PAYMENT = "Your payment has been received and your receipt is in your email."
HEADING = "What you purchased"
HEADINGS = ["Your order is confirmed", HEADING, "Your access", "What happens next", "Help with your order"]
STAGES = (("desktop-wireframe", 1440), ("mobile-tablet", 390))


def public_copy(headings=HEADINGS):
    return "# Thank you\n\n" + "\n\n---\n\n".join(f"## {h}\n\nBody of {h}." for h in headings) + "\n"


def manuscript():
    """The thank-you fixture with section 2 holding the closed run's two approved lines."""
    text = FIXTURE.read_text(encoding="utf-8")
    start = text.index("## Section 2: Order summary")
    end = text.index("## Section 3: Access")
    return text[:start] + f"## Section 2: Order summary\n\n{ITEM}\n\n{PAYMENT}\n\n---\n\n" + text[end:]


def section2(request):
    return next(s for s in request["sections"] if s["section_id"] == "2")


class HeadingCase(RunCase):
    def setUp(self):
        super().setUp()
        (self.run / "copy" / "internal-manuscript.md").write_text(manuscript(), encoding="utf-8")
        (self.run / "copy" / "public-copy.md").write_text(public_copy(), encoding="utf-8")

    def built(self, stage="desktop-wireframe"):
        return self.build(stage=stage, model=REAL_MODEL, prose=realistic_prose())

    def prompt(self, stage, width, request=None, index=2):
        request = request or self.built(stage)
        request["_brand_block"] = exe.require_brand_colors(self.run)
        request["_hypersat"] = exe.hypersaturation.roles_for_run(self.run)
        return exe.stage_prompt(stage, request["sections"][index - 1], index, width, request, "16:9")


class SpecTests(unittest.TestCase):
    def test_section_two_declares_the_heading_the_roles_and_the_colour(self):
        entry = SPEC["sections"][1]
        self.assertIs(entry["copy_heading"], True)
        self.assertEqual(entry["line_roles"], ["H2", "Body", "Body"])
        self.assertNotIn("second line of the headline", entry["wireframe_colour"])
        self.assertIn("chip only", entry["wireframe_colour"])
        for viewport in ("desktop", "mobile"):
            self.assertIn("first line of the copy block", entry["layout"][viewport])
            self.assertNotIn("A section heading", entry["layout"][viewport])
        decisions = SPEC["structure_approval"]["later_decisions"]
        note = next(d for d in decisions if d["decision"] == "order_summary_heading_is_the_closed_heading")
        self.assertEqual(note["date"], "2026-11-24")
        self.assertIn("What you purchased", note["basis"])

    def test_no_other_section_declares_a_heading_or_roles(self):
        for entry in SPEC["sections"]:
            if entry["id"] != "2":
                for key in ("copy_heading", "line_roles", "wireframe_colour"):
                    self.assertNotIn(key, entry, (entry["id"], key))


class BuilderTests(HeadingCase):
    def test_the_closed_heading_is_the_first_line_of_the_section_copy(self):
        entry = section2(self.built())
        self.assertEqual(entry["copy"], f"{HEADING}\n{ITEM}\n{PAYMENT}")
        self.assertEqual(entry["copy_heading"], HEADING)
        self.assertEqual(entry["copy_heading_source"], "copy/public-copy.md")
        self.assertEqual(entry["line_roles"], ["H2", "Body", "Body"])

    def test_other_sections_are_untouched(self):
        request = self.built()
        for entry in request["sections"]:
            if entry["section_id"] != "2":
                for key in ("copy_heading", "line_roles", "copy_heading_source"):
                    self.assertNotIn(key, entry, (entry["section_id"], key))
        self.assertTrue(request["sections"][0]["copy"].startswith("CONFIRMED"), request["sections"][0]["copy"][:40])

    def test_no_export_falls_back_to_the_section_name_and_says_so(self):
        (self.run / "copy" / "public-copy.md").unlink()
        entry = section2(self.built())
        self.assertEqual(entry["copy"].splitlines()[0], "Order summary")
        self.assertIn("no copy/public-copy.md", entry["copy_heading_source"])

    def test_an_export_whose_heading_count_does_not_pair_refuses(self):
        (self.run / "copy" / "public-copy.md").write_text(public_copy(HEADINGS[:4]), encoding="utf-8")
        with self.assertRaises(builder.BuildError) as cm:
            self.built()
        self.assertIn("cannot be paired", str(cm.exception))

    def test_a_bad_line_roles_refuses_by_name(self):
        spec = copy.deepcopy(SPEC)
        spec["sections"][1]["line_roles"] = ["H2", "Banner"]
        for bad in (["H2", "Banner"], [], "H2"):
            spec["sections"][1]["line_roles"] = bad
            with self.assertRaises(builder.BuildError, msg=repr(bad)) as cm:
                builder.sections_from_manuscript(manuscript(), spec, {}, None, None, dict(zip("12345", HEADINGS)))
            self.assertIn("line_roles", str(cm.exception))

    def test_a_section_without_line_roles_is_guessed_as_before(self):
        # section 1: a one-word chip, a long bold line and a button: H1 then Body, never a declared role
        self.assertEqual(w._type_elements({"section_id": "1", "copy": "CONFIRMED\nYou are all set and the seat is yours."}),
                         ["H1", "Subhead"])
        self.assertEqual(builder.line_role("CONFIRMED", True), "headline")
        self.assertEqual(builder.line_role("A longer line that is more than twelve words long, said plainly and "
                                           "in full so it counts as body copy.", False), "body")

    def test_declared_roles_drive_the_type_elements_and_the_line_role(self):
        sec = {"section_id": "2", "copy": f"{HEADING}\n{ITEM}\n{PAYMENT}", "line_roles": ["H2", "Body", "Body"]}
        self.assertEqual(w._type_elements(sec), ["H2", "Body"])
        self.assertEqual([builder.line_role("x", i == 0, r) for i, r in enumerate(sec["line_roles"])],
                         ["heading", "body", "body"])
        # a line the spec did not name is Body, never a guessed Subhead
        sec["copy"] += "\nOne more short line."
        self.assertEqual(w._type_elements(sec), ["H2", "Body"])


class PromptTests(HeadingCase):
    def test_section_two_prompts_print_the_heading_once_and_each_sentence_once(self):
        for stage, width in STAGES:
            prompt = self.prompt(stage, width)
            where = (stage, width)
            block = prompt.split("VERBATIM COPY", 1)[1].split("\n\n", 1)[0].splitlines()
            self.assertEqual(block[1:4], [HEADING, ITEM, PAYMENT], where)
            for sentence in (ITEM, PAYMENT):
                self.assertEqual(prompt.count(sentence), 1, where + (sentence,))
            self.assertEqual(prompt.count(HEADING), 1, where)  # the line plan names the heading, never quotes it
            self.assertNotIn("SUBHEAD /", prompt.upper(), where)  # the sheet grammar's own "never add a subhead" stays

    def test_the_words_order_summary_print_only_in_the_grammar_name_tab(self):
        for stage, width in STAGES:
            prompt = self.prompt(stage, width)
            self.assertEqual(len(re.findall("ORDER SUMMARY", prompt)), 1, stage)
            tab = [l for l in prompt.splitlines() if "ORDER SUMMARY" in l][0]
            self.assertIn('name tab reading exactly "ORDER SUMMARY"', tab, stage)

    def test_the_type_specs_read_h2_and_body_and_no_subhead(self):
        for stage, width in STAGES:
            line = [l for l in self.prompt(stage, width).splitlines() if "INLINE TYPE SPECS" in l][0]
            self.assertIn("H2 /", line, stage)
            self.assertIn("BODY /", line, stage)
            self.assertNotIn("SUBHEAD", line, stage)
            self.assertNotIn("H1 /", line, stage)

    def test_the_line_plan_makes_the_heading_the_heading_not_the_headline(self):
        prompt = self.prompt("desktop-wireframe", 1440)
        self.assertIn("COPY ANATOMY: 1 x heading, 2 x body", prompt)
        self.assertIn("1 heading (3 words)", prompt)
        self.assertNotIn("x headline", prompt)
        self.assertNotIn("two-tone statement-turn", prompt.split("TYPE ROLES:", 1)[1].split("\n", 1)[0])

    def test_section_two_spends_no_accent_fill_and_the_others_keep_the_house_colour_wording(self):
        for stage, width in STAGES:
            request = self.built(stage)
            two = self.prompt(stage, width, request, 2)
            one = self.prompt(stage, width, request, 1)
            self.assertIn("primary colour fills the section chip only", two, stage)
            self.assertNotIn("the second line of the headline", two, stage)
            self.assertIn("the second line of the headline", one, stage)
            self.assertNotIn("section chip only", one, stage)

    def test_the_floor_of_the_prompt_still_holds_with_the_heading_line(self):
        for stage, width in STAGES:
            request = self.built(stage)  # builder.build refuses when any section is under the floor
            for index in range(1, 6):
                self.assertGreaterEqual(len(self.prompt(stage, width, request, index)), 16000, (stage, index))
                self.assertNotIn("layout_overrides", request)


if __name__ == "__main__":
    unittest.main()
