#!/usr/bin/env python3
"""Fix plan B8 / G-11 (review 3097, defect C): request-level references never carry the
client's GENERATED images.

`--references` puts the generated images on the final-mockups request (G-11), but a
request-level reference rides into every job and is labelled "structure only". They must
reach a job only through prior_slices, per section: a section whose plan holds no image
(image_slot_ids []) gets neither Image-001.png nor Image-002.png in input_urls, and the
structure-only reference text names neither. No network, no paid call.
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stage_executor", ROOT / "scripts" / "stage_executor.py")
exe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exe)

STYLE = "https://example.test/library/structure-example.png"


class RequestReferencesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / "run"
        wf = self.run / "desktop-wireframe"
        wf.mkdir(parents=True)
        (wf / "section-plan.json").write_text(json.dumps([
            {"section_id": "hero", "image_slot_ids": ["IMG-001"]},
            {"section_id": "steps", "image_slot_ids": []}]), encoding="utf-8")
        self.generated = []
        for n in (1, 2):
            p = self.run / "image-generation-qc" / f"Image-00{n}.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"\x89PNG\r\n\x1a\n")
            self.generated.append(str(p))
        mapped = self.run / "image-map-upload" / "Image-001.png"
        mapped.parent.mkdir(parents=True)
        mapped.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.request = {"references": [STYLE, *self.generated, str(mapped)],
                        "reference_roles": ["wireframe"]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_generated_images_are_dropped_and_the_style_reference_stays(self):
        self.assertEqual(exe.request_references(self.request), [STYLE])
        self.assertEqual(exe.request_references({}), [])

    def test_type_only_section_job_gets_no_generated_image(self):
        for index, want_generated in ((1, True), (2, False)):
            section = {"section_id": "x", "slots": [{"slot_id": "IMG-001"}] if want_generated else []}
            refs = exe.prior_slices("final-mockups", self.run, index, "desktop/part-{n:02d}.png", section)
            job = {"prompt": "p", "references": [str(r) for r in refs]}
            urls = exe.build_input(job, self.request)["input_urls"]
            self.assertIn(STYLE, urls)
            joined = "\n".join(urls)
            if want_generated:
                self.assertIn("Image-001.png", joined)  # per-section path (prior_slices) still delivers it
                self.assertNotIn("Image-002.png", joined)
            else:
                self.assertNotIn("Image-001.png", joined, urls)
                self.assertNotIn("Image-002.png", joined, urls)

    def test_structure_only_text_names_no_generated_image(self):
        from reference_use import reference_block  # noqa: PLC0415  (scripts/ is on sys.path via the module load)
        block = reference_block(exe.request_references(self.request), self.request["reference_roles"])
        self.assertIn("REFERENCE IMAGE", block)
        self.assertIn("The first attached image is a REFERENCE IMAGE", block)  # one reference, not four
        self.assertNotIn("Image-00", block)

    def test_bleed_check_never_reads_a_generated_image(self):
        class Kie:
            name = "kie"
        seen = []
        original = exe.reference_use.check
        exe.reference_use.check = lambda out, refs, palette: seen.append(list(refs)) or {"status": "PASS"}
        try:
            exe.reference_bleed(Path("x.png"), self.request, Kie())
        finally:
            exe.reference_use.check = original
        self.assertEqual(seen, [[STYLE]])


if __name__ == "__main__":
    unittest.main()
