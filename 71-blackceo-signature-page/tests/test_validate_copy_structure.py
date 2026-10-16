#!/usr/bin/env python3
"""Tests for validate_copy_structure.py (FIX-PLAN Item 18, as amended).

The fixture tests are the contract from Amendment 6 / Item 18: the counting
implementation must reproduce the guides' OWN published counts for their
measured examples. If a fixture test fails, the counter or the spec is
wrong; the fixtures (transcribed from the guide texts) must not be adjusted
to fit the counter. Discrepancies are reported with evidence.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
FIX = SKILL / "tests" / "fixtures" / "copy_examples"
SPECS = SKILL / "references" / "copy-specs"
VALIDATOR = SKILL / "scripts" / "validate_copy_structure.py"

_spec = importlib.util.spec_from_file_location("validate_copy_structure",
                                               VALIDATOR)
vcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vcs)


def load_json(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def run_cli(manuscript_text, spec_name):
    with tempfile.TemporaryDirectory() as tmp:
        md = Path(tmp) / "internal-manuscript.md"
        md.write_text(manuscript_text, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(VALIDATOR), str(md),
             "--spec", str(SPECS / spec_name)],
            capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr


class FixtureCountsTest(unittest.TestCase):
    """The guides' published counts, reproduced by the validator's counter."""

    def test_lesson_examples_reproduce_published_counts(self):
        checked = 0
        for fixture in ("standard-lessons.json", "long-form-lessons.json"):
            data = load_json(fixture)
            for section, by_path in data["examples"].items():
                for path_letter, ex in by_path.items():
                    units, _ = vcs.units_from_markdown(ex["copy_markdown"])
                    words = vcs.count_words(units)
                    self.assertEqual(
                        words, ex["published_words"],
                        f"{fixture} Section {section} path {path_letter}: "
                        f"counter says {words} words, the guide publishes "
                        f"{ex['published_words']} (guide line "
                        f"{ex['guide_line']})")
                    if ex.get("published_chars") is not None:
                        chars = vcs.count_chars(units)
                        self.assertEqual(
                            chars, ex["published_chars"],
                            f"{fixture} Section {section} path {path_letter}: "
                            f"counter says {chars} chars, the guide publishes "
                            f"{ex['published_chars']}")
                    checked += 1
        self.assertEqual(checked, 81)  # 36 Standard + 45 Long-Form examples

    def test_path_b_section_counts_match_measured_tables(self):
        expected = load_json("expected-counts.json")
        for version, fixture, spec_name in (
                ("standard", "standard-path-b.md", "standard-v6.json"),
                ("long-form", "long-form-path-b.md", "long-form-v6.json")):
            spec = vcs.load_spec(str(SPECS / spec_name))
            text = (FIX / fixture).read_text(encoding="utf-8")
            units, order, notes = vcs.parse_manuscript(text)
            by_section = {}
            for u in units:
                by_section.setdefault(u.section, []).append(u)
            published = expected[version]["paths"]["B"]["sections_words"]
            for sid, want in published.items():
                got = vcs.count_words(by_section.get(sid, []))
                self.assertEqual(
                    got, want,
                    f"{version} path B Section {sid}: counter says {got} "
                    f"words, the guide's measured table publishes {want}")
            if version == "standard":
                for sid, want in expected["standard"][
                        "path_b_section_chars"].items():
                    got = vcs.count_chars(by_section[sid])
                    self.assertEqual(
                        got, want,
                        f"standard path B Section {sid}: counter says {got} "
                        f"chars, the guide's note publishes {want}")


class AssembledExamplesPassTest(unittest.TestCase):
    """Each guide's own assembled path B manuscript must pass its own spec."""

    def test_standard_path_b_passes(self):
        text = (FIX / "standard-path-b.md").read_text(encoding="utf-8")
        code, out = run_cli(text, "standard-v6.json")
        self.assertEqual(code, 0, out)
        self.assertIn("RESULT: PASS", out)
        self.assertNotIn("FAIL:", out)

    def test_long_form_path_b_passes(self):
        text = (FIX / "long-form-path-b.md").read_text(encoding="utf-8")
        code, out = run_cli(text, "long-form-v6.json")
        self.assertEqual(code, 0, out)
        self.assertIn("RESULT: PASS", out)
        self.assertNotIn("FAIL:", out)


class CtaMapTest(unittest.TestCase):
    def test_path_b_cta_positions_match_the_maps(self):
        for fixture, want in (
                ("standard-path-b.md", ["1", "2", "3", "4", "5", "10"]),
                ("long-form-path-b.md", ["1", "2A", "4A", "5", "7", "9", "11"])):
            units, _o, _n = vcs.parse_manuscript(
                (FIX / fixture).read_text(encoding="utf-8"))
            got = sorted({u.section for u in units
                          if u.kind == "cta_button"},
                         key=lambda s: (len(s), s))
            self.assertEqual(sorted(got, key=lambda s: (int(''.join(
                c for c in s if c.isdigit())), s)),
                sorted(want, key=lambda s: (int(''.join(
                    c for c in s if c.isdigit())), s)),
                f"{fixture}: CTA buttons in {got}, the map says {want}")

    def test_forbidden_cta_in_long_form_section_2_fails(self):
        text = (FIX / "long-form-path-b.md").read_text(encoding="utf-8")
        marker = "## Section 2A:"
        injected = ("[CTA BUTTON: Book the Working Session]\n\n" + marker)
        self.assertIn(marker, text)
        code, out = run_cli(text.replace(marker, injected, 1),
                            "long-form-v6.json")
        self.assertEqual(code, 1)
        self.assertIn("CTA map", out)
        self.assertIn("Section 2", out)

    def test_missing_section_fails(self):
        text = (FIX / "long-form-path-b.md").read_text(encoding="utf-8")
        start = text.index("## Section 8:")
        end = text.index("## Section 9:")
        code, out = run_cli(text[:start] + text[end:], "long-form-v6.json")
        self.assertEqual(code, 1)
        self.assertIn("required section 8", out)

    def test_extra_section_fails_in_standard(self):
        text = (FIX / "standard-path-b.md").read_text(encoding="utf-8")
        text += ("\n## Section 13: The Extra Bit\n\n"
                 "A section the framework never declared.\n")
        code, out = run_cli(text, "standard-v6.json")
        self.assertEqual(code, 1)
        self.assertIn("Section 13", out)


class StepCharBandTest(unittest.TestCase):
    PADDED_STEP = ("Create your private workspace, invite your whole "
                   "leadership team, and connect every tool your business "
                   "already uses each day")  # 124 characters

    def _s11_doc(self, first_step):
        steps = [first_step] + [
            f"Complete onboarding action number {i} with the team today"
            for i in range(2, 8)]
        body = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
        return ("## Section 11: The Big How To\n\n"
                "Follow these steps to begin.\n\n" + body + "\n")

    def test_standard_step_over_116_chars_fails(self):
        spec = vcs.load_spec(str(SPECS / "standard-v6.json"))
        units, order, notes = vcs.parse_manuscript(
            self._s11_doc(self.PADDED_STEP))
        rep = vcs.validate(units, order, notes, spec)
        step_fails = [f for f in rep.fails if "Step 1" in f and "chars" in f]
        self.assertTrue(step_fails,
                        f"expected a Step 1 character failure, got: {rep.fails}")

    def test_standard_step_bands_do_not_leak_into_long_form(self):
        spec = vcs.load_spec(str(SPECS / "long-form-v6.json"))
        units, order, notes = vcs.parse_manuscript(
            self._s11_doc(self.PADDED_STEP))
        rep = vcs.validate(units, order, notes, spec)
        step_fails = [f for f in rep.fails if "Step" in f]
        self.assertEqual(step_fails, [],
                         f"long-form must never char-check steps: {step_fails}")


class ContainmentTest(unittest.TestCase):
    def test_child_id_as_top_level_section_fails(self):
        spec = vcs.load_spec(str(SPECS / "standard-v6.json"))
        doc = ("## Section 5A: Recognition and reason\n\n"
               "That is why this work exists for your team.\n")
        units, order, notes = vcs.parse_manuscript(doc)
        rep = vcs.validate(units, order, notes, spec)
        self.assertTrue(any("child" in f for f in rep.fails), rep.fails)

    def test_long_form_section7_expanded_band_accepted(self):
        spec = vcs.load_spec(str(SPECS / "long-form-v6.json"))
        card = ("**Working Session Card:** " + " ".join(
            ["guided", "practice", "with", "your", "team", "on", "real",
             "work", "from", "your", "own", "pipeline", "and", "calendar",
             "so", "every", "idea", "becomes", "a", "repeatable", "habit",
             "you", "can", "run", "without", "help", "every", "single",
             "week"] * 2))
        cards = "\n".join(f"- {card}" for _ in range(6))
        doc = ("## Section 7: The Big Bold What\n\n"
               "Here is everything included in the program for your team.\n\n"
               + cards + "\n")
        units, order, notes = vcs.parse_manuscript(doc)
        rep = vcs.validate(units, order, notes, spec)
        self.assertEqual(rep.counts["7"].get("band"), "expanded_six_card",
                         rep.counts)
        self.assertFalse(any("neither declared band" in w for w in rep.warns),
                         rep.warns)


if __name__ == "__main__":
    unittest.main()
