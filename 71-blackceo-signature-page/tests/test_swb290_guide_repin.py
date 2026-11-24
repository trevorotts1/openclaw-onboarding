#!/usr/bin/env python3
"""SWB-290 item C: build_hybrid_board.py --refresh-record also re-pins the guide thumbnails.

The guide column's thumbnails are the desktop-wireframe slices. When the wireframe stage is
regenerated (export, record, stitch), the recorded sha256 of every thumbnail is stale and
validate_hybrid_board refuses the board; --refresh-record used to re-pin only the two mockup panels.
It now also verifies the closed wireframe stage against its OWN production record and stitch receipt
(never a claim inside the thumbnail) and re-pins each thumbnail, with `refreshed_from.guide` provenance.

Negative twins (each refuses, leaves the record byte for byte, composes no board): a slice changed after
the stitch, a production record that fails validation, a stitched sheet that is not the stitch of its
slices, a thumbnail naming another slice, a guide section the stage does not have, and an edit of the
guide after the refresh. No paid API is called.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

from PIL import Image  # noqa: E402

import build_hybrid_board as bhb  # noqa: E402
import export_native_slices as ex  # noqa: E402
import test_hybrid_board_refresh as base  # noqa: E402
import test_swb290_wireframe_export as wfx  # noqa: E402
import validate_hybrid_board as vhb  # noqa: E402
import write_production_record as wp  # noqa: E402


class GuideBase(base.RefreshBase):
    def setUp(self):
        super().setUp()
        self.tmp_wf = tempfile.TemporaryDirectory()
        wf_run = wfx.make_wireframe_run(self.tmp_wf.name, natives=wfx.NATIVES[:2])
        req = wf_run / "production-request-desktop-wireframe.json"
        data = json.loads(req.read_text())
        data["sections"] = data["sections"][:2]
        req.write_text(json.dumps(data))
        st = wf_run / "desktop-wireframe"
        ex.run(st, widths={"desktop": wfx.PAGE})
        ok, lines = wp.run(wf_run, stage="desktop-wireframe", ocr=wfx.fake_ocr, ocr_validate=False)
        assert ok, lines
        proc = base.script("stitch_sections.py", st)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        shutil.rmtree(self.run_dir / "desktop-wireframe")
        shutil.copytree(st, self.run_dir / "desktop-wireframe")
        self.wf = self.run_dir / "desktop-wireframe"
        self.stale = [s["sha256"] for s in json.loads(self.before)["guide"]["sections"]]

    def tearDown(self):
        self.tmp_wf.cleanup()
        super().tearDown()


class RepinTests(GuideBase):
    def test_the_old_pins_are_stale_before_the_refresh(self):
        data = json.loads(self.before)
        self.assertTrue(any("does not hash to the recorded sha256" in f
                            for f in vhb.check_board(data, run_dir=self.run_dir)))

    def test_refresh_repins_the_guide_to_the_verified_wireframe_slices(self):
        proc = self.refresh()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        rec = json.loads(self.rec_path.read_text(encoding="utf-8"))
        stitch = json.loads((self.wf / "stitch-receipt.json").read_text())
        want = [s["sha256"] for s in stitch["sections"]]
        self.assertEqual([s["sha256"] for s in rec["guide"]["sections"]], want)
        self.assertNotEqual(want, self.stale)
        for sec in rec["guide"]["sections"]:
            self.assertEqual(sec["sha256"], vhb.sha256(self.run_dir / sec["wireframe_thumbnail"]))
        # everything but the pins is unchanged
        before = json.loads(self.before)["guide"]
        for old, new in zip(before["sections"], rec["guide"]["sections"]):
            self.assertEqual({k: v for k, v in old.items() if k != "sha256"},
                             {k: v for k, v in new.items() if k != "sha256"})
        g = rec["refreshed_from"]["guide"]
        self.assertEqual([r["sha256"] for r in g["prior"]], self.stale)
        self.assertEqual([r["sha256"] for r in g["new"]], want)
        self.assertEqual(g["receipts"]["stitch_receipt"]["path"], "desktop-wireframe/stitch-receipt.json")
        self.assertEqual(g["receipts"]["production_record"]["file_sha256"],
                         vhb.sha256(self.wf / "production-record.json"))
        self.assertEqual(rec["refreshed_from"]["receipt_sha256"], bhb._provenance_hash(rec["refreshed_from"]))
        check = base.script("validate_hybrid_board.py", self.run_dir, "--check-board")
        self.assertEqual(check.returncode, 0, check.stdout)
        receipt = json.loads((self.fm / "hybrid-board-receipt.json").read_text())
        self.assertIn(want[0], [i["sha256"] for i in receipt["inputs"]])

    # ---- negative twins ----
    def test_a_slice_changed_after_the_stitch_is_refused(self):
        Image.new("RGB", (wfx.PAGE, 108), (7, 7, 7)).save(self.wf / "section-01.png")
        self.assert_refused(self.refresh(), "desktop-wireframe")

    def test_a_production_record_that_does_not_pass_is_refused(self):
        self.edit(self.wf / "production-record.json", lambda d: d["sections"][0].__setitem__("width", 999))
        proc = self.refresh()
        self.assert_refused(proc, "the production record does not pass validate_production_record")

    def test_a_stitched_sheet_that_is_not_the_stitch_of_its_slices_is_refused(self):
        sheet = self.wf / "wireframe-full.png"
        im = Image.open(sheet).convert("RGB")
        im.putpixel((0, 0), (250, 1, 1))
        im.save(sheet)
        proc = self.refresh()
        self.assert_refused(proc, "desktop-wireframe")

    def test_a_thumbnail_naming_another_slice_is_refused(self):
        def swap(d):
            d["guide"]["sections"][0]["wireframe_thumbnail"] = "desktop-wireframe/section-02.png"
        self.edit(self.rec_path, swap)
        self.before = self.rec_path.read_bytes()
        self.assert_refused(self.refresh(), "the thumbnail is 'desktop-wireframe/section-02.png' but the closed")

    def test_a_guide_section_the_stage_does_not_have_is_refused(self):
        def bad(d):
            d["guide"]["sections"][1]["section_id"] = "9"
        self.edit(self.rec_path, bad)
        self.before = self.rec_path.read_bytes()
        self.assert_refused(self.refresh(), "has no slice for this section id")

    def test_a_guide_edited_after_the_refresh_is_caught(self):
        self.assertEqual(self.refresh().returncode, 0)
        self.edit(self.rec_path, lambda d: d["guide"]["sections"][0].__setitem__("sha256", "e" * 64))
        proc = base.script("validate_hybrid_board.py", self.run_dir)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("changed after its refresh", proc.stdout)

    def test_a_stitch_receipt_alone_without_its_record_is_refused(self):
        (self.wf / "production-record.json").unlink()
        self.assert_refused(self.refresh(), "the production record")


class NoWireframeEvidenceTests(base.RefreshBase):
    def test_a_run_with_no_wireframe_stage_evidence_keeps_its_guide(self):
        proc = self.refresh()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        rec = json.loads(self.rec_path.read_text(encoding="utf-8"))
        self.assertEqual(rec["guide"], json.loads(self.before)["guide"])
        self.assertNotIn("guide", rec["refreshed_from"])


if __name__ == "__main__":
    unittest.main()
