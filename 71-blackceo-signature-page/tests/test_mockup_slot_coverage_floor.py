#!/usr/bin/env python3
"""Mockups carry every image the page planned.

Pins the three linked repairs behind the "2-3 images in a 12-slot page" defect:
  - every copy spec section that must carry an image declares its slot
    (`default_slots`, derived from the section-image-prompt.md skeleton table)
    and the request builder emits it for a landing spec, not only for a page role;
  - validate_mockup_slots.py runs the reverse pass: every PLANNED slot must
    appear in the rendered mockup, and a miss is an ERROR naming the slot;
  - final-mockups receives the generated, QC'd images (image-generation-qc) as
    references, so the mockup composites the run's real photography.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand_fixture import give_blackceo_colors  # noqa: E402
from test_section_count import REAL_MODEL, design_prose, load  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "copy_examples"
SPECS = ROOT / "references" / "copy-specs"
VALIDATOR = ROOT / "scripts" / "validate_mockup_slots.py"

builder = load("build_production_request")
exe = load("stage_executor")

class SpecSlotTests(unittest.TestCase):
    def spec(self, name):
        return json.loads((SPECS / name).read_text(encoding="utf-8"))

    def test_standard_declares_nine_image_slots(self):
        slots = [s for e in self.spec("standard-v6.json")["sections"] for s in e.get("default_slots") or []]
        self.assertEqual([s["slot_id"] for s in slots],
                         ["IMG-%03d" % n for n in range(1, 10)])

    def test_long_form_declares_twelve_image_slots(self):
        slots = [s for e in self.spec("long-form-v6.json")["sections"] for s in e.get("default_slots") or []]
        self.assertEqual([s["slot_id"] for s in slots],
                         ["IMG-%03d" % n for n in range(1, 13)])

class RequestSlotTests(unittest.TestCase):
    """The builder populates a landing spec's slots: no --slots, no page_role."""

    def build(self, version, manuscript):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run = Path(tmp.name)
        give_blackceo_colors(run)
        text = (FIXTURES / manuscript).read_text(encoding="utf-8")
        return builder.build("visual-mockup", version, text, {}, design_prose(), [],
                             REAL_MODEL, "", run)

    def slots(self, request):
        return {s["section_id"]: [x["slot_id"] for x in s.get("slots") or []]
                for s in request["sections"]}

    def test_long_form_request_carries_twelve_slots(self):
        got = self.slots(self.build("long-form", "long-form-path-b.md"))
        self.assertEqual([s for v in got.values() for s in v],
                         ["IMG-%03d" % n for n in range(1, 13)])
        for sid in ("6", "7", "11"):  # type-only sections: no photo slot
            self.assertEqual(got[sid], [])

class CoverageFloorTests(unittest.TestCase):
    """A mockup that renders 2 of 12 planned slots FAILS and names the 10."""

    def run_dir(self, planned, rendered):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "desktop-wireframe").mkdir()
        (root / "final-mockups").mkdir()
        (root / "image-generation-qc").mkdir()
        (root / "intake.json").write_text(json.dumps({"copy_version": "long-form"}))
        inventory = [{"id": "IMG-%03d" % i, "source": "generated"} for i in planned]
        (root / "desktop-wireframe/image-inventory.json").write_text(
            json.dumps({"images": inventory}))
        sections = [{"section_id": str(i), "slots": [
            {"slot_id": "IMG-%03d" % i, "source": "generated",
             "file": "image-generation-qc/Image-%03d.png" % i}]} for i in rendered]
        (root / "final-mockups/generation-record.json").write_text(
            json.dumps({"stage": "final-mockups", "sections": sections}))
        for i in rendered:
            (root / ("image-generation-qc/Image-%03d.png" % i)).write_bytes(
                b"\x89PNG\r\n\x1a\n" + bytes([i]))
        return root

    def validate(self, root):
        p = subprocess.run([sys.executable, "-I", str(VALIDATOR), str(root)],
                           capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def test_short_mockup_fails_and_names_the_missing_slots(self):
        # The run's own inventory matches the short render: only the spec plan
        # (long-form-v6.json, 12 slots) can catch this, which is the point.
        rc, out = self.validate(self.run_dir(range(3, 13), range(1, 3)))
        self.assertEqual(rc, 1, out)
        for i in range(3, 13):
            self.assertIn("planned image slot IMG-%03d is missing from the rendered page "
                          "(2 of 12 planned slot(s) rendered" % i, out)
        self.assertNotIn("planned image slot IMG-001 is missing", out)

    def test_complete_mockup_passes(self):
        rc, out = self.validate(self.run_dir(range(1, 13), range(1, 13)))
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS: final-mockups mockup gate: all 12 slot(s)", out)

class GeneratedImageRefTests(unittest.TestCase):
    """final-mockups gets the section's generated images; earlier stages do not."""

    def test_generated_images_reach_final_mockups_only(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run = Path(tmp.name)
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            (run / stage / "desktop").mkdir(parents=True)
            (run / stage / "mobile").mkdir(parents=True)
        exe.stub_png(run / "desktop-wireframe/section-01.png", 1440, 810, "d1")
        exe.stub_png(run / "mobile-tablet/section-01.png", 390, 693, "m1")
        exe.stub_png(run / "visual-mockup/desktop/part-01.png", 1440, 2560, "v1")
        (run / "image-generation-qc").mkdir()
        for i in (1, 2):
            (run / ("image-generation-qc/Image-%03d.png" % i)).write_bytes(
                b"\x89PNG\r\n\x1a\n" + bytes([i]))
        (run / "desktop-wireframe/section-plan.json").write_text(json.dumps(
            [{"section_id": "1", "image_slot_ids": ["IMG-001"]},
             {"section_id": "2", "image_slot_ids": ["IMG-002"]}]))
        final = [p.name for p in exe.prior_slices("final-mockups", run, 1, "desktop/part-01.png")]
        self.assertIn("Image-001.png", final)
        self.assertNotIn("Image-002.png", final)  # section 2's photograph, not section 1's
        earlier = [p.name for p in exe.prior_slices("visual-mockup", run, 1, "desktop/part-01.png")]
        self.assertNotIn("Image-001.png", earlier)

    def test_type_only_section_gets_no_generated_images(self):
        # MOCK-001 B8: a section the plan records with an EMPTY image_slot_ids list
        # is type-only (6 persona cards, 7 icon cards, 11 numbered steps) and must
        # receive zero generated files. An empty list must not collapse into
        # "no plan" (which hands the section every generated image).
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run = Path(tmp.name)
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            (run / stage / "desktop").mkdir(parents=True)
            (run / stage / "mobile").mkdir(parents=True)
        exe.stub_png(run / "desktop-wireframe/section-01.png", 1440, 810, "d1")
        exe.stub_png(run / "mobile-tablet/section-01.png", 390, 693, "m1")
        exe.stub_png(run / "visual-mockup/desktop/part-01.png", 1440, 2560, "v1")
        (run / "image-generation-qc").mkdir()
        for i in (1, 2):
            (run / ("image-generation-qc/Image-%03d.png" % i)).write_bytes(
                b"\x89PNG\r\n\x1a\n" + bytes([i]))
        (run / "desktop-wireframe/section-plan.json").write_text(json.dumps(
            [{"section_id": "1", "image_slot_ids": []},
             {"section_id": "2", "image_slot_ids": ["IMG-002"]}]))
        final = [p.name for p in exe.prior_slices("final-mockups", run, 1, "desktop/part-01.png")]
        self.assertNotIn("Image-001.png", final)
        self.assertNotIn("Image-002.png", final)

if __name__ == "__main__":
    unittest.main()
