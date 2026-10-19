#!/usr/bin/env python3
"""Contract tests for the generation wire's prompt and geometry repairs.

Pins the four source-level repairs:
  - verbatim copy goes first, exactly once, with the exact CTA label;
  - provenance (local paths, reference filenames, reference raster px)
    never reaches the model;
  - copy padded with style prose, or cut mid-sentence, is refused
    before a paid call;
  - each job sees only its own section's earlier slices, and the
    requested ratio is the pixel-mate's, not one 3:4 for every part.
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stage_executor", ROOT / "scripts/stage_executor.py")
exe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exe)

SECTION = {
    "section_id": "S01", "section_name": "Hero",
    "copy": "You’re doing every job. CTA: SAVE MY SEAT.",
    "slots": [{"slot_id": "IMG-001", "aspect_ratio": "3:4",
               "art_direction": "Founder at a desk."}],
}
LEAKY = ("Styled mockup section {section_number} {section_name} at {width}px ratio {ratio}. "
         "File: /Users/blackceomacmini/ref/chatgpt-mockup-4.png. Pixels: 724 × 2172. "
         "SHA-256: deadbeef. Raster: 724 × 2172. {copy} {slots}")
REQUEST = {"model": "gpt-image-2-5-sunburst-image-to-image",
           "style": "warm editorial", "stage_prompts": {"visual-mockup": LEAKY}}


class PromptContractTests(unittest.TestCase):
    def test_copy_first_once_and_provenance_removed(self):
        prompt = exe.stage_prompt("visual-mockup", SECTION, 1, 1440, REQUEST, "3:4")
        self.assertTrue(prompt.startswith("VERBATIM COPY"), prompt[:80])
        self.assertEqual(prompt.count("You’re doing every job."), 1)
        self.assertIn('CTA LABEL — print exactly: "SAVE MY SEAT"', prompt)
        for leak in ("/Users/", "chatgpt-mockup-4", "724", "2172", "SHA-256"):
            self.assertNotIn(leak, prompt)
        self.assertIn("FRAME CONTRACT", prompt)
        self.assertIn("no blank bands", prompt)

    def test_style_padding_inside_copy_is_refused(self):
        section = dict(SECTION, copy=SECTION["copy"] + " Preserve the measured band order.")
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.stage_prompt("visual-mockup", section, 1, 1440, REQUEST, "3:4")
        self.assertIn("style padding", str(ctx.exception))

    def test_mid_sentence_copy_is_refused(self):
        for tail in ("The leads, the follow-up, the invoices,", "Every hire adds cost and management, not"):
            with self.assertRaises(exe.ExecutorError) as ctx:
                exe.stage_prompt("visual-mockup", dict(SECTION, copy=tail), 1, 1440, REQUEST, "3:4")
            self.assertIn("ends mid-sentence", str(ctx.exception))

    def test_nearest_offered_ratio(self):
        self.assertEqual(exe.nearest_ratio(1024, 3072), "9:16")
        self.assertEqual(exe.nearest_ratio(1672, 941), "16:9")
        self.assertEqual(exe.nearest_ratio(1440, 1920), "3:4")
        self.assertEqual(exe.nearest_ratio(390, 520), "3:4")

    def test_only_same_index_slices_are_attached(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
                (run / stage / "desktop").mkdir(parents=True)
                (run / stage / "mobile").mkdir(parents=True)
            exe.stub_png(run / "desktop-wireframe/section-01.png", 1440, 810, "d1")
            exe.stub_png(run / "desktop-wireframe/section-02.png", 1440, 810, "d2")
            exe.stub_png(run / "mobile-tablet/section-01.png", 390, 693, "m1")
            exe.stub_png(run / "visual-mockup/desktop/part-01.png", 1440, 2560, "v1")
            refs = exe.prior_slices("visual-mockup", run, 1, "desktop/part-01.png")
            self.assertEqual(len(refs), 2)
            self.assertTrue(all("01" in p.name for p in refs))
            ratio = exe.target_ratio("visual-mockup", "desktop/part-01.png",
                                     SECTION, run, 1)
            self.assertEqual(ratio, "16:9")

    def test_png_size_reads_ihdr(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "slice.png"
            exe.stub_png(out, 390, 520, "size")
            self.assertEqual(exe.png_size(out), (390, 520))


if __name__ == "__main__":
    unittest.main(verbosity=2)
