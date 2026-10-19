#!/usr/bin/env python3
"""One request section per canonical copy section: Standard 12, Long-Form 15.

Pins the section-count contract of scripts/stage_executor.py
(check_section_count) and scripts/build_production_request.py:
  - the builder emits 12 sections for Standard and 15 for Long-Form from the
    guides' own assembled example manuscripts, ids in the spec order;
  - a band-compressed request (6 sections for a 12-section copy) is refused by
    name, in preflight and before any prompt is composed;
  - the request must match its copy source and the run's copy manifest;
  - an undeclared form is allowed only for a free run, never a paid one;
  - the optional 5A/5B/5C expansion is the only other accepted shape;
  - a manuscript missing a section makes the builder refuse;
  - the builder reaches the model's 95 to 100 percent prompt band by genuine
    specification, and refuses a section left under the 80 percent floor;
  - a request under the floor is refused by preflight and by a paid run, never
    waved through with a warning;
  - the truncated-copy guard stays strict (a cut-off last line is refused), and a
    chip label or signature travels as a separate verbatim label;
  - the builder checks its output against the run its manuscript belongs to, not
    the directory it was started in.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand_fixture import give_blackceo_colors  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "copy_examples"
SCRIPTS = ROOT / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    spec.loader.exec_module(mod)
    return mod


exe = load("stage_executor")
builder = load("build_production_request")


def sections(ids):
    return [{"section_id": i, "section_name": i, "copy": "A finished sentence."} for i in ids]


STANDARD = [str(i) for i in range(1, 13)]
LONG = ["1", "2", "2A", "3", "3A", "4", "4A", "5", "6", "7", "8", "9", "10", "11", "12"]


class SectionCountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        give_blackceo_colors(self.run)  # image stages and the builder start from the client's colors

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, version, ids, paid=False, run=None):
        request = {"copy_version": version, "sections": sections(ids)}
        return exe.check_section_count(run or self.run, request, paid)

    def test_canonical_counts_pass(self):
        self.assertEqual(self.check("standard", STANDARD)[1], STANDARD)
        self.assertEqual(self.check("long-form", LONG)[1], LONG)

    def test_lane_style_ids_are_canonicalised(self):
        ids = [f"S{i:02d}" for i in range(1, 13)]
        self.assertEqual(self.check("standard", ids)[1], STANDARD)

    def test_band_compressed_request_is_refused(self):
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.check("standard", [f"S{i:02d}" for i in range(1, 7)])
        message = str(ctx.exception)
        self.assertIn("section count", message)
        self.assertIn("6 sections", message)
        self.assertIn("12 canonical", message)
        self.assertIn("never band-compress", message)

    def test_standard_request_for_long_form_is_refused(self):
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.check("long-form", STANDARD)
        self.assertIn("missing ['2A', '3A', '4A']", str(ctx.exception))

    def test_five_a_b_c_expansion_is_the_only_other_shape(self):
        expanded = LONG[:7] + ["5A", "5B", "5C"] + LONG[8:]
        self.assertEqual(len(self.check("long-form", expanded)[1]), 17)
        with self.assertRaises(exe.ExecutorError):
            self.check("long-form", LONG[:7] + ["5A", "5B"] + LONG[8:])

    def test_unknown_form_is_refused(self):
        with self.assertRaises(exe.ExecutorError):
            self.check("short-form", STANDARD)

    def test_undeclared_form_is_free_only(self):
        request = {"sections": sections(["hero"])}
        self.assertIsNone(exe.check_section_count(self.run, request, paid=False))
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.check_section_count(self.run, request, paid=True)
        self.assertIn("copy_version", str(ctx.exception))

    def test_form_comes_from_intake_when_the_request_is_silent(self):
        (self.run / "intake.json").write_text(json.dumps({"copy_version": "standard"}))
        with self.assertRaises(exe.ExecutorError):
            exe.check_section_count(self.run, {"sections": sections(["1", "2"])}, False)

    def test_request_must_match_copy_source_and_manifest(self):
        source = {"sections": [{"id": f"S{i:02d}"} for i in range(1, 12)]}
        (self.run / "copy.json").write_text(json.dumps(source))
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.check("standard", STANDARD)
        self.assertIn("copy source", str(ctx.exception))
        (self.run / "copy.json").unlink()
        (self.run / "copy").mkdir()
        (self.run / "copy" / "copy-manifest.json").write_text(
            json.dumps({"sections": STANDARD[:-1]}))
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.check("standard", STANDARD)
        self.assertIn("copy manifest", str(ctx.exception))

    def test_load_request_refuses_and_preflight_exits_1(self):
        request = {"model": "STUB-NO-MODEL", "copy_version": "standard",
                   "sections": sections([f"S{i:02d}" for i in range(1, 7)])}
        (self.run / "production-request.json").write_text(json.dumps(request))
        with self.assertRaises(exe.ExecutorError):
            exe.load_request(self.run, "production-request.json")
        proc = subprocess.run([sys.executable, str(SCRIPTS / "stage_executor.py"),
                               str(self.run), "--preflight", "--stages", "visual-mockup"],
                              capture_output=True, text=True)  # final-mockups would stop first at the unapproved design board
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAIL: section count", proc.stdout)

    def test_truncated_last_line_is_refused_even_when_short(self):
        for copy in ("Founders lose ten hours a week to busywork.\nThe three steps that",
                     "Line one is fine.\nAnd then we will show you how to",
                     "Every hire adds cost and management, not only the salary and"):
            with self.assertRaises(exe.ExecutorError) as ctx:
                exe.copy_contract({"section_id": "12", "copy": copy})
            self.assertIn("mid-sentence", str(ctx.exception))

    def test_signature_and_chip_labels_are_verbatim_labels_not_prose(self):
        section = {"section_id": "12", "copy": "The letter ends here.",
                   "labels": ["With respect, Marcus Reed"]}
        block = exe.copy_contract(section)
        self.assertIn('LABELS', block)
        self.assertIn('"With respect, Marcus Reed"', block)
        long_label = {"section_id": "12", "copy": "The letter ends here.",
                      "labels": ["Every hire adds cost and management, not only the salary"]}
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.copy_contract(long_label)
        self.assertIn("label", str(ctx.exception))

    def test_multi_paragraph_copy_prints_once(self):
        copy = "First paragraph here.\n\nSecond paragraph here."
        request = {"model": "STUB-NO-MODEL", "stage_prompts": {"visual-mockup": "Draw it.\n{copy}"},
                   "_hypersat": exe.hypersaturation.roles_for_run(self.run)}
        prompt = exe.stage_prompt("visual-mockup", {"section_id": "1", "copy": copy}, 1, 1440, request, "3:4")
        self.assertEqual(prompt.count("Second paragraph here."), 1)

    def test_under_floor_is_refused_when_strict_and_warned_otherwise(self):
        request = {"model": "gpt-image-2-5-sunburst", "stage_prompts": {"visual-mockup": "{copy}"},
                   "_hypersat": exe.hypersaturation.roles_for_run(self.run)}
        section = {"section_id": "1", "copy": "A finished sentence."}
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.stage_prompt("visual-mockup", section, 1, 1440, request, "3:4", strict_floor=True)
        self.assertIn("below the 16000-char floor", str(ctx.exception))
        self.assertTrue(exe.stage_prompt("visual-mockup", section, 1, 1440, request, "3:4"))

    def test_preflight_exits_1_on_a_prompt_under_the_floor(self):
        request = {"model": "gpt-image-2-5-sunburst", "copy_version": "standard",
                   "stage_prompts": {"visual-mockup": "{copy}"},
                   "sections": sections([str(i) for i in range(1, 13)])}
        (self.run / "production-request.json").write_text(json.dumps(request))
        proc = subprocess.run([sys.executable, str(SCRIPTS / "stage_executor.py"), str(self.run),
                               "--preflight", "--stages", "visual-mockup"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("REFUSED: prompt budget", proc.stdout)
        self.assertIn("PREFLIGHT_SECTIONS", proc.stdout)


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        give_blackceo_colors(self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, version, text, stage="visual-mockup"):
        return builder.build(stage, version, text, {}, {}, [], "STUB-NO-MODEL", "", self.run)

    def test_builder_emits_one_section_per_canonical_section(self):
        for version, ids in (("standard", STANDARD), ("long-form", LONG)):
            text = (FIXTURES / f"{version}-path-b.md").read_text(encoding="utf-8")
            request = self.build(version, text)
            self.assertEqual([s["section_id"] for s in request["sections"]], ids)
            self.assertEqual(request["metadata"]["section_count"], len(ids))
            self.assertEqual(request["copy_version"], version)
            self.assertTrue(all(s["copy"] for s in request["sections"]))

    def test_builder_carries_each_sections_cta_and_no_private_label(self):
        text = (FIXTURES / "long-form-path-b.md").read_text(encoding="utf-8")
        request = self.build("long-form", text)
        by_id = {s["section_id"]: s for s in request["sections"]}
        self.assertTrue(by_id["1"]["cta"])
        self.assertIsNone(by_id["2"]["cta"])
        self.assertTrue(by_id["2A"]["cta"])
        names = " ".join(s["section_name"] for s in request["sections"])
        self.assertNotIn("Big Bold", names)

    def test_builder_refuses_a_manuscript_missing_a_section(self):
        text = (FIXTURES / "long-form-path-b.md").read_text(encoding="utf-8")
        head, rest = text.split("## Section 2A:", 1)
        tail = rest.split("## Section 3:", 1)[1]
        with self.assertRaises(builder.BuildError) as ctx:
            self.build("long-form", head + "## Section 3:" + tail)
        self.assertIn("missing ['2A']", str(ctx.exception))


REAL_MODEL = "gpt-image-2-5-sunburst-image-to-image"


def design_prose(chars=14500):
    """Unique pseudo-sentences standing in for a run's measured design system
    (a varied vocabulary, so the validator's padding screens have nothing to flag).
    14500 is the size of a real measured system; the builder's own top-up is finite."""
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


class BandTests(unittest.TestCase):
    """The builder lands every section in the 95 to 100 percent band, or refuses."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        give_blackceo_colors(self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, version, prose, stage="visual-mockup", slots=None):
        text = (FIXTURES / f"{version}-path-b.md").read_text(encoding="utf-8")
        return builder.build(stage, version, text, slots or {}, prose, [], REAL_MODEL, "", self.run)

    def test_every_section_is_in_band_for_both_forms_and_both_mockup_stages(self):
        for version in ("standard", "long-form"):
            for stage in ("visual-mockup", "final-mockups"):
                request = self.build(version, design_prose(), stage)
                budget = request["metadata"]["char_budget"]
                self.assertGreaterEqual(budget["min_seen"], budget["target"], (version, stage))
                self.assertLessEqual(budget["max_seen"], budget["max"], (version, stage))

    def test_builder_output_passes_a_strict_preflight_prompt_for_prompt(self):
        request = self.build("long-form", design_prose())
        builder.run_blocks(request, self.run)  # the executor re-resolves the run's palette, as load_request does
        for index, section in enumerate(request["sections"], start=1):
            for _t, width, _h in exe.LAYOUT["visual-mockup"]:
                prompt = exe.stage_prompt("visual-mockup", section, index, width, request,
                                          "3:4", strict_floor=True)
                self.assertGreaterEqual(len(prompt), 16000)

    def test_no_design_prose_means_a_named_refusal_not_a_short_prompt(self):
        with self.assertRaises(builder.BuildError) as ctx:
            self.build("standard", {})
        self.assertIn("below the 16000-char floor", str(ctx.exception))
        self.assertIn("--design-prose", str(ctx.exception))

    def test_private_framework_labels_never_reach_a_prompt(self):
        request = self.build("long-form", design_prose())
        layouts = " ".join(s["layout"] for s in request["sections"])
        for bad in ("Big Bold", "framework", "5A", "2A", "CTA BUTTON"):
            self.assertNotIn(bad, layouts)
        self.assertNotRegex(layouts, r"(?i)\b(pain|solution) \d")
        self.assertIn("Answer the first cost in place", layouts)
        prose = design_prose()
        # the table leads: a block too big for the budget is trimmed from its tail
        prose["rules_md"] = "| Pain 01 | 394 | 525 | 132 |\n| Pain 02 | 526 | 649 | 124 |\n" + prose["rules_md"]
        template = self.build("long-form", prose)["stage_prompts"]["visual-mockup"]
        self.assertNotRegex(template, r"(?i)\bpain \d")
        self.assertIn("| the first cost | 394", template)

    def test_slot_canon_only_where_the_run_plans_slots(self):
        bare = " ".join(s["layout"] for s in self.build("standard", design_prose())["sections"])
        self.assertNotIn("SLOT CANON", bare)
        slots = {"2": [{"slot_id": "hero", "aspect_ratio": "16:9", "art_direction": "x"}]}
        planned = self.build("standard", design_prose(), slots=slots)["sections"]
        self.assertIn("SLOT CANON", planned[1]["layout"])
        self.assertEqual(sum("SLOT CANON" in s["layout"] for s in planned), 1)

    def test_signature_is_a_label_and_the_founder_letter_still_builds(self):
        request = self.build("standard", design_prose())
        last = request["sections"][-1]
        self.assertEqual(last["labels"], ["With respect, Marcus Reed"])
        self.assertTrue(last["copy"].endswith("."))


class RunDirTests(unittest.TestCase):
    """The self-check reads the run the manuscript belongs to, not the working directory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / "run"
        (self.run / "copy").mkdir(parents=True)
        (self.run / "copy" / "internal-manuscript.md").write_text(
            (FIXTURES / "standard-path-b.md").read_text(encoding="utf-8"), encoding="utf-8")
        give_blackceo_colors(self.run)
        self.elsewhere = Path(self.tmp.name) / "elsewhere"
        self.elsewhere.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "build_production_request.py"),
             "--copy-version", "standard", "--manuscript", str(self.run / "copy" / "internal-manuscript.md"),
             "--stage", "visual-mockup", "--model", "STUB-NO-MODEL",
             "--out", str(self.run / "production-request.json"), *extra],
            capture_output=True, text=True, cwd=self.elsewhere)

    def test_manifest_of_the_run_is_checked_from_any_working_directory(self):
        (self.run / "copy" / "copy-manifest.json").write_text(json.dumps({"sections": STANDARD[:-1]}))
        proc = self.cli()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("copy manifest", proc.stdout)

    def test_matching_manifest_is_reported_as_checked(self):
        (self.run / "copy" / "copy-manifest.json").write_text(json.dumps({"sections": STANDARD}))
        proc = self.cli()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("CHECKED", proc.stdout)
        self.assertIn("against=copy manifest", proc.stdout)

    def test_a_manifest_in_the_working_directory_is_never_read(self):
        (self.elsewhere / "copy").mkdir()
        (self.elsewhere / "copy" / "copy-manifest.json").write_text(json.dumps({"sections": ["1"]}))
        proc = self.cli()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("copy manifest absent", proc.stdout)

    def test_run_dir_flag_overrides_the_default(self):
        other = Path(self.tmp.name) / "other-run"
        (other / "copy").mkdir(parents=True)
        give_blackceo_colors(other)
        (other / "copy" / "copy-manifest.json").write_text(json.dumps({"sections": STANDARD[:3]}))
        proc = self.cli("--run-dir", str(other))
        self.assertEqual(proc.returncode, 1, proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
