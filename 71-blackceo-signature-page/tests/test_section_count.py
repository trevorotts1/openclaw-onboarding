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
  - a manuscript missing a section makes the builder refuse.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
                               str(self.run), "--preflight"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAIL: section count", proc.stdout)

    def test_short_closing_line_is_copy_but_unfinished_prose_is_not(self):
        ok = {"section_id": "12", "copy": "The letter ends here.\nWith respect, Marcus Reed"}
        self.assertIn("With respect", exe.copy_contract(ok))
        bad = {"section_id": "12",
               "copy": "A short line.\nEvery hire adds cost and management, not only the salary and"}
        with self.assertRaises(exe.ExecutorError):
            exe.copy_contract(bad)


class BuilderTests(unittest.TestCase):
    def build(self, version, text, stage="visual-mockup"):
        return builder.build(stage, version, text, {}, {}, [], "STUB-NO-MODEL", "")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
