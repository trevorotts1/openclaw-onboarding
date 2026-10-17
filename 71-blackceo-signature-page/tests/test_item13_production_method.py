#!/usr/bin/env python3
"""Item 13 (Update Plan): the pinned wireframe/mockup production method.

Pins:
  (a) the SOP wireframe stage (Stage 4D), the mobile stage, and the mockup
      stage (Stage 11C) state the fixed method: per-section generation via
      the KIE.ai GPT-image route with the model resolved from the registry
      at build time, the approved wireframe section as the mockup section's
      layout reference, the visual bible as style input, native aspect,
      the deterministic stitcher and PDF combiner, and native-resolution
      text QC with regeneration of any garbled section before stitching.
  (b) references/artifact-contracts.md defines the production-record.json
      build record (generation inputs, native-aspect output, text-QC leg).
  (c) scripts/validate_production_record.py catches a deliberately garbled
      section (the QC-leg record requirement), including a record that
      falsely claims a pass, and refuses a section with no QC record.
  (d) scripts/stitch_sections.py assembles the sections in record order
      and refuses to stitch a garbled section (no output is produced).
  (e) scripts/combine_review_pdf.py, fed a manifest in record order,
      produces the combined PDF with the same page order.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SOP = (ROOT / "references" /
       "BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md").read_text(encoding="utf-8")
CONTRACTS = (ROOT / "references" / "artifact-contracts.md").read_text(encoding="utf-8")

WIDTH = 40
SECTIONS = [
    ("S01", (220, 30, 30), 10, "Build your desktop command center"),
    ("S02", (30, 180, 60), 20, "Every section in its place"),
    ("S03", (40, 60, 220), 30, "Ship the full page today"),
]


def make_stage(tmp, garbled=None, drop_qc=False, lie_clean=False, attempts=None):
    """Build a synthetic stage folder: slices + production-record.json."""
    from PIL import Image
    stage = Path(tmp)
    records = []
    for idx, (sid, color, height, copy_text) in enumerate(SECTIONS, start=1):
        name = f"section-{idx:02d}.png"
        Image.new("RGB", (WIDTH, height), color).save(stage / name)
        readback = copy_text
        garbled_words = []
        if garbled == sid:
            readback = copy_text.replace("desktop", "desktor").replace("Desktop", "Desktor")
            if readback == copy_text:  # S02/S03 fallback garble
                readback = copy_text + " desktor"
            garbled_words = [] if lie_clean else ["desktor"]
        section = {
            "section_id": sid,
            "slice": name,
            "width": WIDTH,
            "height": height,
            "generation": {
                "route": "kie-gpt-image",
                "model_id": "resolved-at-build-time-fixture",
                "model_source": "latest-family",
                "layout_reference": f"approved wireframe section {sid}",
                "style_input": "visual-mockup/page-visual-bible.json",
                "native_aspect": f"{WIDTH}x{height}",
            },
        }
        if not drop_qc:
            section["text_qc"] = {
                "checked_at_native_resolution": True,
                "expected_text": copy_text,
                "readback_text": readback,
                "garbled_words": garbled_words,
                "verdict": "pass",
                "attempts": (attempts or {}).get(sid, 1),
            }
        records.append(section)
    record = {
        "artifact": "mockup",
        "stage": "final-mockups",
        "page_width": WIDTH,
        "stitched_output": "wireframe-full.png",
        "pdf_output": "wireframe.pdf",
        "sections": records,
    }
    (stage / "production-record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return stage


def run(script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                          text=True, capture_output=True)


class MethodTextTest(unittest.TestCase):
    def test_sop_stage4d_pins_the_method(self):
        stage4 = SOP.split("## Stage 4 -", 1)[1].split("## Stage 5 -", 1)[0].lower()
        for phrase in ("production method (pinned; update plan item 13)",
                       "per section", "kie.ai gpt-image",
                       "resolved from the model registry at build time",
                       "visual bible", "style input", "native aspect",
                       "stitch_sections.py", "combine_review_pdf.py",
                       "native resolution", "garbled",
                       "regenerated before stitching",
                       "production-record.json", "validate_production_record.py"):
            self.assertIn(phrase, stage4, f"Stage 4 method text must pin: {phrase}")

    def test_sop_mockup_stage_applies_the_method(self):
        stage11 = SOP.split("## Stage 11 -", 1)[1].split("## Stage 12 -", 1)[0].lower()
        for phrase in ("production method for the mockup sections",
                       "approved wireframe section slice", "layout reference",
                       "visual bible", "native aspect", "garbled",
                       "stitch_sections.py", "production-record.json"):
            self.assertIn(phrase, stage11, f"Stage 11 method text must pin: {phrase}")
        stage5 = SOP.split("## Stage 5 -", 1)[1].split("## Stage 6 -", 1)[0].lower()
        self.assertIn("pinned production method", stage5)
        stage6 = SOP.split("## Stage 6 -", 1)[1].split("## Stage 7 -", 1)[0].lower()
        self.assertIn("style input", stage6)

    def test_contract_defines_the_build_record(self):
        block = CONTRACTS.split("## Production method and per-section build record", 1)[1]
        block = " ".join(block.split("## Generation receipt", 1)[0].split())
        for phrase in ("production-record.json", "kie-gpt-image", "model_source",
                       "layout_reference", "style_input", "native_aspect",
                       "checked_at_native_resolution", "garbled_words", "attempts",
                       "stitch_sections.py", "combine_review_pdf.py",
                       "never accepted into the combined artifact"):
            self.assertIn(phrase, block, f"artifact contract must define: {phrase}")


class ProductionRecordQCTest(unittest.TestCase):
    def test_clean_record_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = make_stage(tmp)
            proc = run("validate_production_record.py", stage / "production-record.json")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("PASS", proc.stdout)

    def test_garbled_section_is_caught_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = make_stage(tmp, garbled="S01")
            proc = run("validate_production_record.py", stage / "production-record.json")
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("S01", proc.stdout)
            self.assertIn("desktor", proc.stdout.lower())

    def test_lying_record_is_caught_by_recomputation(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = make_stage(tmp, garbled="S01", lie_clean=True)
            proc = run("validate_production_record.py", stage / "production-record.json")
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("desktor", proc.stdout.lower())

    def test_missing_qc_record_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = make_stage(tmp, drop_qc=True)
            proc = run("validate_production_record.py", stage / "production-record.json")
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("text_qc record is required", proc.stdout)

    def test_native_aspect_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = make_stage(tmp)
            record = json.loads((stage / "production-record.json").read_text())
            record["sections"][1]["height"] = 999
            record["sections"][1]["generation"]["native_aspect"] = f"{WIDTH}x999"
            (stage / "production-record.json").write_text(json.dumps(record), encoding="utf-8")
            proc = run("validate_production_record.py", stage / "production-record.json")
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("S02", proc.stdout)

    def test_regenerated_section_passes_with_attempts_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = make_stage(tmp, attempts={"S01": 2})
            proc = run("validate_production_record.py", stage / "production-record.json")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class StitcherTest(unittest.TestCase):
    def test_stitcher_assembles_sections_in_order(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            stage = make_stage(tmp)
            proc = run("stitch_sections.py", stage)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            out = stage / "wireframe-full.png"
            self.assertTrue(out.exists())
            with Image.open(out) as im:
                self.assertEqual(im.size, (WIDTH, 60))
                px = im.convert("RGB")
                self.assertEqual(px.getpixel((5, 5)), SECTIONS[0][1])
                self.assertEqual(px.getpixel((5, 15)), SECTIONS[1][1])
                self.assertEqual(px.getpixel((5, 45)), SECTIONS[2][1])
            receipt = json.loads((stage / "stitch-receipt.json").read_text())
            self.assertEqual([s["section_id"] for s in receipt["sections"]],
                             [s[0] for s in SECTIONS])
            first = stage / "section-01.png"
            self.assertEqual(receipt["sections"][0]["sha256"],
                             hashlib.sha256(first.read_bytes()).hexdigest())
            self.assertEqual(receipt["output_sha256"],
                             hashlib.sha256(out.read_bytes()).hexdigest())

    def test_stitcher_refuses_a_garbled_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = make_stage(tmp, garbled="S02")
            proc = run("stitch_sections.py", stage)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("garbled", proc.stdout.lower())
            self.assertFalse((stage / "wireframe-full.png").exists(),
                             "a garbled section must never be stitched into the combined artifact")


class CombinerTest(unittest.TestCase):
    def test_combiner_produces_the_pdf_in_record_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = make_stage(tmp)
            manifest = {
                "category": "desktop-mockups",
                "output": "wireframe.pdf",
                "pages": [{"path": f"section-{i:02d}.png", "label": sid}
                          for i, (sid, *_rest) in enumerate(SECTIONS, start=1)],
            }
            (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            proc = run("combine_review_pdf.py", stage / "manifest.json")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((stage / "wireframe.pdf").exists())
            receipt = json.loads((stage / "wireframe.pdf.manifest.json").read_text())
            self.assertEqual(receipt["page_count"], len(SECTIONS))
            self.assertEqual([p["label"] for p in receipt["pages"]],
                             [s[0] for s in SECTIONS])


if __name__ == "__main__":
    unittest.main(verbosity=2)
