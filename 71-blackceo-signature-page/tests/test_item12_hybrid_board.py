#!/usr/bin/env python3
"""Item 12 (Update Plan): the hybrid board as a standard deliverable at
mockup approval.

Pins:
  (a) the stage contract's final-mockups stage delivers the board
      (hybrid-board.png + its board record), names it the stage's
      approval artifact, and covers it in review; stage order and the
      stage's dependencies are unchanged.
  (b) the SOP mockup stage (Stage 11D) and references/artifact-contracts.md
      define the board: three panels on one sheet (mockup-fidelity
      desktop, mockup-fidelity mobile, section guide column with
      numbered sections, mini wireframe thumbnails, typography specs -
      traits H1/H2 from Item 14), composed deterministically from the
      already-approved artifacts, never a new generation pass, and the
      approval recorded against the board.
  (c) scripts/validate_hybrid_board.py passes a clean record and fails
      by name: a panel whose bytes no longer match the approved
      artifact, a guide that does not match the mockups (H2), and a
      missing typography spec.
  (d) scripts/build_hybrid_board.py composes the board from exactly the
      named artifacts (pixel proof per panel, receipt hashes), the
      composed board passes --check-board, and the composer refuses a
      tampered record, producing no board.
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
CONTRACT = json.loads((ROOT / "references" / "stage-contract.json").read_text(encoding="utf-8"))

DESKTOP_COLOR = (200, 40, 40)
MOBILE_COLOR = (40, 60, 220)
THUMB_COLORS = [(30, 180, 60), (240, 200, 30)]
SECTIONS = [("S01", "Hero"), ("S02", "Offer")]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_run(tmp):
    """Build a synthetic run folder with approved artifacts + a board record."""
    from PIL import Image
    run = Path(tmp)
    fm = run / "final-mockups"
    fm.mkdir(parents=True)
    Image.new("RGB", (80, 120), DESKTOP_COLOR).save(fm / "desktop-full.png")
    Image.new("RGB", (40, 120), MOBILE_COLOR).save(fm / "mobile-full.png")
    dw = run / "desktop-wireframe"
    dw.mkdir(parents=True)
    for i, color in enumerate(THUMB_COLORS, start=1):
        Image.new("RGB", (40, 20), color).save(dw / f"section-{i:02d}.png")
    (dw / "section-plan.json").write_text(json.dumps([
        {"section_id": sid, "copy_block_ids": [], "image_slot_ids": [],
         "reference_traits": []} for sid, _name in SECTIONS]), encoding="utf-8")
    (fm / "production-record.json").write_text(json.dumps({
        "artifact": "mockup", "stage": "final-mockups",
        "sections": [{"section_id": sid} for sid, _name in SECTIONS]}), encoding="utf-8")
    fam = run / "font-action-plan"
    fam.mkdir(parents=True)
    (fam / "font-map.json").write_text("{}", encoding="utf-8")
    record = {
        "board_output": "hybrid-board.png",
        "desktop_panel": {"source": "final-mockups/desktop-full.png",
                          "sha256": sha256(fm / "desktop-full.png")},
        "mobile_panel": {"source": "final-mockups/mobile-full.png",
                         "sha256": sha256(fm / "mobile-full.png")},
        "guide": {
            "typography_source": "font-action-plan/font-map.json",
            "sections": [
                {"number": i, "section_id": sid, "name": name,
                 "wireframe_thumbnail": f"desktop-wireframe/section-{i:02d}.png",
                 "sha256": sha256(dw / f"section-{i:02d}.png"),
                 "type_specs": {"heading": "H1 64px", "body": "Body 18px",
                                "cta": "CTA 20px"}}
                for i, (sid, name) in enumerate(SECTIONS, start=1)
            ],
        },
    }
    (fm / "hybrid-board.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return run


def run_script(script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                          text=True, capture_output=True)


class ContractTest(unittest.TestCase):
    def test_final_mockups_delivers_and_approves_against_the_board(self):
        fm = CONTRACT["stages"]["final-mockups"]
        globs = [a["glob"] for a in fm["artifacts"]]
        self.assertIn("final-mockups/hybrid-board.png", globs)
        self.assertIn("final-mockups/hybrid-board.json", globs)
        self.assertIn("final-mockups/mockup.html", globs)
        self.assertEqual(fm["approval_artifact"], "final-mockups/hybrid-board.png")
        self.assertIn("final-mockups/hybrid-board.png", fm["review_covers"])
        self.assertIn("hybrid board", fm["purpose"].lower())

    def test_stage_shape_unchanged(self):
        self.assertEqual(len(CONTRACT["stage_order"]), 14)
        self.assertEqual(CONTRACT["stages"]["final-mockups"]["depends_on"],
                         ["visual-mockup", "image-map-upload"])

    def test_sop_and_contracts_define_the_board(self):
        stage11 = SOP.split("## Stage 11 -", 1)[1].split("## Stage 12 -", 1)[0].lower()
        for phrase in ("hybrid board", "standard deliverable at mockup approval",
                       "three panels", "section guide",
                       "build_hybrid_board.py", "validate_hybrid_board.py",
                       "never by a new generation pass",
                       "approval is recorded against the board",
                       "approval_artifact"):
            self.assertIn(phrase, stage11, f"Stage 11 board text must pin: {phrase}")
        block = CONTRACTS.split("## Hybrid board", 1)[1].split("## Generation receipt", 1)[0]
        block = " ".join(block.split())
        for phrase in ("hybrid-board.png", "hybrid-board.json", "build_hybrid_board.py",
                       "validate_hybrid_board.py", "hybrid-board-receipt.json",
                       "approval_artifact", "typography_source", "type_specs",
                       "never by a new generation pass"):
            self.assertIn(phrase, block, f"artifact contract must define: {phrase}")


class ValidatorTest(unittest.TestCase):
    def test_clean_record_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            proc = run_script("validate_hybrid_board.py", run)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("PASS", proc.stdout)

    def test_tampered_panel_fails_by_name(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            Image.new("RGB", (80, 120), (1, 2, 3)).save(
                run / "final-mockups" / "desktop-full.png")
            proc = run_script("validate_hybrid_board.py", run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("desktop_panel", proc.stdout)

    def test_guide_mismatch_with_mockups_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            record_path = run / "final-mockups" / "production-record.json"
            record = json.loads(record_path.read_text())
            record["sections"] = list(reversed(record["sections"]))
            record_path.write_text(json.dumps(record), encoding="utf-8")
            proc = run_script("validate_hybrid_board.py", run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("do not match", proc.stdout)

    def test_missing_type_spec_fails_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            record_path = run / "final-mockups" / "hybrid-board.json"
            record = json.loads(record_path.read_text())
            del record["guide"]["sections"][0]["type_specs"]["cta"]
            record_path.write_text(json.dumps(record), encoding="utf-8")
            proc = run_script("validate_hybrid_board.py", run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("type_specs.cta", proc.stdout)


class ComposerTest(unittest.TestCase):
    def test_board_composes_the_three_panels_from_the_named_artifacts(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            proc = run_script("build_hybrid_board.py", run)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            board = run / "final-mockups" / "hybrid-board.png"
            self.assertTrue(board.exists())
            with Image.open(board) as im:
                # Sheet width: margins 2*24 + desktop 720 + gap 24 + guide 400 + gap 24 + mobile 280.
                self.assertEqual(im.size[0], 1496)
                px = im.convert("RGB")
                # Desktop panel origin: (margin, margin + header) = (24, 64).
                self.assertEqual(px.getpixel((30, 70)), DESKTOP_COLOR)
                # Mobile panel origin x: 24 + 720 + 24 + 400 + 24 = 1192.
                self.assertEqual(px.getpixel((1200, 70)), MOBILE_COLOR)
                # Guide column first thumbnail origin x: 24 + 720 + 24 = 768.
                self.assertEqual(px.getpixel((774, 70)), THUMB_COLORS[0])
            receipt = json.loads(
                (run / "final-mockups" / "hybrid-board-receipt.json").read_text())
            self.assertEqual(receipt["output_sha256"], sha256(board))
            self.assertEqual(len(receipt["inputs"]), 4)
            proc = run_script("validate_hybrid_board.py", run, "--check-board")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_composer_refuses_a_tampered_record_and_produces_no_board(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            Image.new("RGB", (40, 20), (9, 9, 9)).save(
                run / "desktop-wireframe" / "section-01.png")
            proc = run_script("build_hybrid_board.py", run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("refusing to compose", proc.stdout)
            self.assertFalse((run / "final-mockups" / "hybrid-board.png").exists(),
                             "a board must never be composed from unapproved bytes")

    def test_composer_refuses_overwrite_without_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            self.assertEqual(run_script("build_hybrid_board.py", run).returncode, 0)
            proc = run_script("build_hybrid_board.py", run)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("already exists", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
