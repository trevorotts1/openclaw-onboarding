#!/usr/bin/env python3
"""ANN-001: wireframe build annotations must never reach a mockup or the built page.

The defect this module holds shut, in two halves:

  PROMPT. build_production_request.template_for() appended SECTION_TAIL (the
  numbered heading "SECTION 4 of 15: Second problem at 1440px" plus the annotation
  block headings) to EVERY stage, so the final-mockup prompt asked the model to
  draw the production chip and name tab into the client's page. The comment above
  ROLE_NAMES says those labels "are private and must never reach a public mockup";
  the code contradicted it. The wireframe stages still need the heading, so the
  split is SECTION_HEAD (wireframes only) + SECTION_BODY (every stage), with
  SECTION_TAIL kept as their concatenation and the wireframe output byte-identical.

  PAGE. Nothing checked the built page for the leaked annotations afterwards:
  scripts/validate_public_copy.py passed a page carrying a SECTION 4 chip, a
  SECOND PROBLEM tab and a "CTA below the copy" note, because its section-label
  pattern wants a colon after the number and is line-anchored.
  scripts/validate_annotation_leak.py is that guard, registered at the end of the
  final-mockups and responsive-html validator lists.

Fixtures (tests/fixtures/annotation_leak/, one shared production-request.json and
one shared copy/public-copy.md; every page is the existing good page fixture plus
one addition, so the comparison is like-with-like):

  leak/      good page + the annotation block a leaked mockup carries (a SECTION 4
             chip and a SECOND PROBLEM tab, once per platform panel) + a
             "CTA below the copy" note         -> exit 1, all three hits named
  clean/     good page unchanged               -> exit 0
  in_copy/   good page + a real "Second problem" heading, in the copy once -> exit 0
  overflow/  in_copy + a second SECOND PROBLEM tab -> exit 1 (2 on the page, 1 in copy)
  control    the good page fixture itself      -> exit 0

The ALLOW RULE is what separates a headline from a chip: a hit is excused only when
the phrase is in copy/public-copy.md AND the page prints it no more often than the
copy does. That is why in_copy passes and overflow does not.

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
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = HERE / "fixtures" / "annotation_leak"
GOOD_PAGE = HERE / "fixtures" / "page_good" / "index.html"
PY = sys.executable


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


builder = load("build_production_request")
leak = load("validate_annotation_leak")
wireframe_spec = load("wireframe_spec")

# The literal string SECTION_TAIL carried before ANN-001. Both wireframe stages
# must still render exactly this.
OLD_SECTION_TAIL = ("SECTION {section_number} of {section_total}: {section_name} at {width}px\n"
                    "{layout}\nLAYOUT AND COPY:\n{copy}\nIMAGE SLOTS:\n{slots}")
BLOCKS = {"notes": "MEASURED NOTES", "traits": "MEASURED TRAITS", "rules_md": "MEASURED RULES"}


def run_validator(html_path, run_dir=FIXTURES):
    return subprocess.run([PY, str(SCRIPTS / "validate_annotation_leak.py"), str(html_path),
                           "--run-dir", str(run_dir)], text=True, capture_output=True)


class TemplateTests(unittest.TestCase):
    def test_template_wireframe_bytes_unchanged(self):
        """desktop-wireframe and mobile-tablet still render the pre-ANN-001 template."""
        self.assertEqual(builder.SECTION_TAIL, OLD_SECTION_TAIL,
                         "SECTION_TAIL must stay the concatenation it always was")
        self.assertEqual(builder.SECTION_HEAD + builder.SECTION_BODY, OLD_SECTION_TAIL)
        for stage in ("desktop-wireframe", "mobile-tablet"):
            with self.subTest(stage=stage):
                self.assertEqual(builder.template_for(stage, {}),
                                 builder.LEADS[stage] + "\n\n" + OLD_SECTION_TAIL)
                expected = "\n\n".join([
                    builder.LEADS[stage],
                    "LAYOUT NOTES", BLOCKS["notes"],
                    "VISUAL STANDARD TRAITS", BLOCKS["traits"],
                    "DESIGN SYSTEM, MEASURED", BLOCKS["rules_md"],
                    OLD_SECTION_TAIL,
                ])
                self.assertEqual(builder.template_for(stage, BLOCKS), expected)

    def test_template_mockup_has_no_heading(self):
        """Neither mockup stage is asked for the numbered heading or the name tab."""
        body = OLD_SECTION_TAIL.split("\n", 1)[1]
        for stage in builder.MOCKUP_PROMPT_STAGES:
            with self.subTest(stage=stage):
                out = builder.template_for(stage, BLOCKS)
                self.assertNotIn("SECTION {section_number} of", out)
                self.assertTrue(out.endswith(body), out[-120:])
                self.assertIn("LAYOUT AND COPY:", out)
                self.assertIn("IMAGE SLOTS:", out)

    def test_mockup_stage_set_is_the_two_mockup_stages(self):
        self.assertEqual(builder.MOCKUP_PROMPT_STAGES, ("visual-mockup", "final-mockups"))

    def test_final_mockup_lead_calls_the_wireframe_a_layout_reference(self):
        """STEP 2: the annotation sentence, on final-mockups only; the other leads untouched."""
        self.assertIn("annotations and are never drawn", builder.LEADS["final-mockups"])
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            self.assertNotIn("attached wireframe is a layout reference", builder.LEADS[stage])


class ContractTests(unittest.TestCase):
    FINAL = ("python3 scripts/validate_annotation_leak.py "
             "{run_dir}/final-mockups/mockup.html --run-dir {run_dir}")
    RESPONSIVE = ("python3 scripts/validate_annotation_leak.py "
                  "{run_dir}/responsive-html/index.html --run-dir {run_dir}")

    def stages(self):
        return json.loads((ROOT / "references" / "stage-contract.json").read_text(
            encoding="utf-8"))["stages"]

    def test_contract_registers_validator(self):
        stages = self.stages()
        self.assertEqual(stages["final-mockups"]["validators"][-1], self.FINAL)
        self.assertEqual(stages["responsive-html"]["validators"][-1], self.RESPONSIVE)
        for earlier in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            self.assertFalse([v for v in stages[earlier]["validators"]
                              if "validate_annotation_leak" in v], earlier)
        self.assertTrue((SCRIPTS / "validate_annotation_leak.py").is_file())
        carriers = [n for n, s in stages.items()
                    if any("validate_annotation_leak" in v for v in s["validators"])]
        self.assertEqual(sorted(carriers), ["final-mockups", "responsive-html"])


class FixtureTests(unittest.TestCase):
    """The five required fixtures, run as the stage gate runs them."""

    def test_leak_fails_and_names_all_three_hits(self):
        proc = run_validator(FIXTURES / "leak" / "index.html")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("SECTION 4", proc.stdout)          # (e) the numbered chip
        self.assertIn("Second problem", proc.stdout)     # (a) the name tab
        self.assertIn("CTA below the copy", proc.stdout)  # (c) the behaviour note
        for cls in ("(a)", "(c)", "(e)"):
            self.assertIn(cls, proc.stdout)

    def test_clean_passes(self):
        proc = run_validator(FIXTURES / "clean" / "index.html")
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_in_copy_passes(self):
        proc = run_validator(FIXTURES / "in_copy" / "index.html")
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_overflow_fails(self):
        proc = run_validator(FIXTURES / "overflow" / "index.html")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("Second problem", proc.stdout)

    def test_control_is_the_good_page_fixture(self):
        proc = run_validator(GOOD_PAGE)
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_missing_input_is_never_a_pass(self):
        with tempfile.TemporaryDirectory(prefix="ann001-leak-") as tmp:
            proc = run_validator(FIXTURES / "clean" / "index.html", tmp)
            self.assertEqual(proc.returncode, 2, proc.stdout)
        proc = run_validator(FIXTURES / "does-not-exist.html")
        self.assertEqual(proc.returncode, 2, proc.stdout)


class GapTests(unittest.TestCase):
    def test_new_validator_catches_what_validate_public_copy_passes(self):
        """The exact page that currently fools the linter: it returns PASS, we return FAIL."""
        page = FIXTURES / "leak" / "index.html"
        linter = subprocess.run([PY, str(SCRIPTS / "validate_public_copy.py"), str(page)],
                                text=True, capture_output=True)
        self.assertEqual(linter.returncode, 0, linter.stdout)
        self.assertIn("PASS", linter.stdout)
        self.assertEqual(run_validator(page).returncode, 1)

    def test_the_chip_defeats_the_linter_on_its_own(self):
        """A page carrying only the SECTION 4 chip: linter PASS, this validator FAIL."""
        html = GOOD_PAGE.read_text(encoding="utf-8").replace(
            "</body>", '<div class="chip">SECTION 4</div>\n</body>', 1)
        with tempfile.TemporaryDirectory(prefix="ann001-chip-") as tmp:
            page = Path(tmp) / "index.html"
            page.write_text(html, encoding="utf-8")
            linter = subprocess.run([PY, str(SCRIPTS / "validate_public_copy.py"), str(page)],
                                    text=True, capture_output=True)
            self.assertEqual(linter.returncode, 0, linter.stdout)
            proc = run_validator(page)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("(e)", proc.stdout)


class DenylistSourceTests(unittest.TestCase):
    """Each source is derived by import, so a new name joins the check by existing."""

    def sections(self):
        data = json.loads((FIXTURES / "production-request.json").read_text(encoding="utf-8"))
        return data["sections"]

    def test_every_source_class_is_derived(self):
        entries = leak.denylist(self.sections())
        classes = {cls for cls, _phrase in entries}
        self.assertFalse(classes - {"a", "b", "c", "d"})
        self.assertTrue({"a", "c", "d"} <= classes)
        phrases = {phrase for _cls, phrase in entries}
        for value in builder.ROLE_NAMES.values():
            self.assertIn(leak.norm(value), phrases)                       # (a)
        for section in self.sections():                                    # (b)
            self.assertIn(leak.norm(section["section_name"]), phrases)
        for _key, heading in builder.BLOCKS:
            self.assertIn(leak.norm(heading), phrases)                     # (d)
        for heading in ("LAYOUT AND COPY", "IMAGE SLOTS"):
            self.assertIn(heading, phrases)                                # (d)
        for note in leak.NOTE_FALLBACKS:
            self.assertIn(note, phrases)                                   # (c)
        for stage in leak.NOTE_STAGES:                                     # (c) from _note itself
            for section in self.sections():
                produced = wireframe_spec._note(stage, section,
                                                leak.page_kinds.cta_label(section), None, False)
                self.assertIn(leak.norm(produced), phrases)
        self.assertEqual(set(leak.NOTE_STAGES), {"desktop-wireframe", "mobile-tablet"})

    def test_section_names_are_a_live_source(self):
        """A section_name outside ROLE_NAMES (class b) fails a page that prints it."""
        name = "Quietly Distinctive Section Name"
        self.assertNotIn(name, builder.ROLE_NAMES.values())
        with tempfile.TemporaryDirectory(prefix="ann001-section-") as tmp:
            run = Path(tmp)
            (run / "copy").mkdir()
            (run / "copy" / "public-copy.md").write_text("Unrelated public copy.\n", encoding="utf-8")
            (run / "production-request.json").write_text(json.dumps(
                {"sections": [{"section_id": "1", "section_name": name, "copy": "A line."}]}),
                encoding="utf-8")
            page = run / "index.html"
            page.write_text(f"<html><body><h2>{name}</h2></body></html>", encoding="utf-8")
            proc = run_validator(page, run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("(b)", proc.stdout)

    def test_the_allow_rule_governs_the_structural_pattern_too(self):
        """A numbered heading the copy itself prints, once, is excused; twice is not."""
        with tempfile.TemporaryDirectory(prefix="ann001-allow-") as tmp:
            run = Path(tmp)
            (run / "copy").mkdir()
            (run / "production-request.json").write_text(json.dumps(
                {"sections": [{"section_id": "4", "section_name": "Fourth"}]}), encoding="utf-8")
            (run / "copy" / "public-copy.md").write_text("SECTION 4\n", encoding="utf-8")
            once = run / "once.html"
            once.write_text("<html><body><p>SECTION 4</p></body></html>", encoding="utf-8")
            self.assertEqual(run_validator(once, run).returncode, 0)
            twice = run / "twice.html"
            twice.write_text("<html><body><p>SECTION 4</p><p>SECTION 4</p></body></html>",
                             encoding="utf-8")
            proc = run_validator(twice, run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("(e)", proc.stdout)


if __name__ == "__main__":
    unittest.main()
