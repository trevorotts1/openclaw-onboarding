#!/usr/bin/env python3
"""Update Plan Item 19: supplied-asset size check at intake.

Fixtures: the 150x150 founder photo against the 470x500 founder-letter
slot flags UNDERSIZED with both sizes printed; a supplied asset at or
above its slot size passes with its measurement recorded; recorded
dimensions match the files' measured bytes; an UNDERSIZED verdict never
blocks intake, prints as a named line at intake, in REPORT warnings, and
is carried for placing stages' evidence.
"""
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import stage_gate  # noqa: E402
import write_intake  # noqa: E402

PY = sys.executable


def jpeg_bytes(width, height):
    """Minimal JPEG carrying a SOF0 segment with the given dimensions."""
    sof = struct.pack(">H", 8 + 3 * 3) + bytes([8]) + struct.pack(">HH", height, width)
    sof += bytes([3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1])
    return b"\xff\xd8" + b"\xff\xc0" + sof + b"\xff\xd9"


def png_bytes(width, height):
    ihdr = struct.pack(">II", width, height) + bytes([8, 2, 0, 0, 0])
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr
            + b"\x00\x00\x00\x00")


FOUNDER_DECL = {"id": "IMG-012", "source": "supplied-founder-photo",
                "file": "founder.jpg", "slot_ratio": "47:50",
                "slot_layout_width_px": 235}


class SuppliedSizeCheckTests(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="item19-"))
        (self.td / "founder.jpg").write_bytes(jpeg_bytes(150, 150))
        (self.td / "logo.png").write_bytes(png_bytes(1200, 1000))

    def run_intake(self, declarations, extra=()):
        decl_path = self.td / "supplied.json"
        decl_path.write_text(json.dumps(declarations), encoding="utf-8")
        proc = subprocess.run(
            [PY, str(SCRIPTS / "write_intake.py"), str(self.td),
             "--page-version", "standard", "--brand-owner", "test",
             "--image-cap", "12", "--supplied-assets", str(decl_path), *extra],
            text=True, capture_output=True)
        return proc

    def test_dimensions_measured_from_bytes(self):
        self.assertEqual(write_intake.image_pixel_dimensions(self.td / "founder.jpg"),
                         (150, 150))
        self.assertEqual(write_intake.image_pixel_dimensions(self.td / "logo.png"),
                         (1200, 1000))

    def test_founder_photo_undersized_with_shortfall(self):
        records, problems = write_intake.supplied_size_check_records(
            [FOUNDER_DECL], self.td)
        self.assertEqual(problems, [])
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["asset_px"], {"width": 150, "height": 150})
        # layout 235 wide at 47:50, rendered at DISPLAY_DENSITY_FACTOR 2
        self.assertEqual(rec["slot_px"], {"width": 470, "height": 500})
        self.assertEqual(rec["verdict"], "UNDERSIZED")
        self.assertEqual(rec["shortfall_px"], {"width": 320, "height": 350})
        line = write_intake.supplied_size_line(rec)
        self.assertIn("IMG-012", line)
        self.assertIn("150x150", line)
        self.assertIn("470x500", line)
        self.assertIn("UNDERSIZED", line)

    def test_asset_at_or_above_slot_passes(self):
        decl = {"id": "IMG-001", "source": "supplied-logo", "file": "logo.png",
                "slot_ratio": "47:50", "slot_layout_width_px": 235}
        records, problems = write_intake.supplied_size_check_records([decl], self.td)
        self.assertEqual(problems, [])
        self.assertEqual(records[0]["verdict"], "OK")
        self.assertEqual(records[0]["asset_px"], {"width": 1200, "height": 1000})
        self.assertNotIn("shortfall_px", records[0])

    def test_explicit_slot_px_and_exact_fit(self):
        decl = {"id": "IMG-012", "source": "supplied-founder-photo",
                "file": "founder.jpg", "slot_px": {"width": 150, "height": 150}}
        records, problems = write_intake.supplied_size_check_records([decl], self.td)
        self.assertEqual(problems, [])
        self.assertEqual(records[0]["verdict"], "OK")

    def test_section_plan_fills_ratio_and_width(self):
        plan = [{"section_id": "12", "image_slot_ids": ["IMG-012"],
                 "slot_aspect_ratios": {"IMG-012": "47:50"},
                 "slot_layout_widths": {"IMG-012": 235}}]
        plan_path = self.td / "section-plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        decl = {"id": "IMG-012", "source": "supplied-founder-photo",
                "file": "founder.jpg"}
        records, problems = write_intake.supplied_size_check_records(
            [decl], self.td, write_intake.section_plan_index(plan_path))
        self.assertEqual(problems, [])
        self.assertEqual(records[0]["slot_px"], {"width": 470, "height": 500})
        self.assertEqual(records[0]["verdict"], "UNDERSIZED")

    def test_intake_records_verdict_and_never_blocks(self):
        proc = self.run_intake([FOUNDER_DECL])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("SUPPLIED ASSET SIZE IMG-012", proc.stdout)
        self.assertIn("UNDERSIZED", proc.stdout)
        intake = json.loads((self.td / "intake.json").read_text(encoding="utf-8"))
        checks = intake["supplied_asset_size_checks"]
        self.assertEqual(checks[0]["verdict"], "UNDERSIZED")
        self.assertEqual(checks[0]["asset_px"], {"width": 150, "height": 150})
        self.assertEqual(checks[0]["slot_px"], {"width": 470, "height": 500})

    def test_unmeasurable_asset_is_invalid_input(self):
        decl = {"id": "IMG-009", "source": "supplied-photo",
                "file": "missing.jpg", "slot_px": {"width": 10, "height": 10}}
        proc = self.run_intake([decl])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("IMG-009", proc.stdout)

    def test_gate_flag_lines_and_report_warnings(self):
        proc = self.run_intake([FOUNDER_DECL,
                                {"id": "IMG-001", "source": "supplied-logo",
                                 "file": "logo.png",
                                 "slot_px": {"width": 100, "height": 100}}])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        lines = stage_gate.supplied_size_flag_lines(self.td)
        self.assertEqual(len(lines), 1)
        self.assertIn("IMG-012", lines[0])
        self.assertIn("150x150", lines[0])
        self.assertIn("470x500", lines[0])
        self.assertIn("UNDERSIZED", lines[0])
        warnings = stage_gate.collect_warnings(self.td, {})
        self.assertTrue(any("IMG-012" in w and "UNDERSIZED" in w for w in warnings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
