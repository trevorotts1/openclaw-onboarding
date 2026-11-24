#!/usr/bin/env python3
"""build_hybrid_board.py --refresh-record re-pins the board record to the current stitches (SWB-119).

Positive: after export, production records and both stitches, a record pinned to older panels
is re-pinned to the current desktop and mobile stitches (paths from the stitch receipts), carries
refreshed_from provenance, passes validate_hybrid_board, and the board is composed.
Negative twins (each refuses, leaves the record byte for byte and composes no board): a panel
not equal to its stitch receipt (desktop, mobile), a slice changed after the export, a stitch
whose inputs are not the export receipt's, a missing production record, a missing stitch or
export receipt, a tampered production record, a stale record citing another export receipt,
and an existing board without --overwrite. The no-flag behaviour is unchanged.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SCRIPTS))

from PIL import Image  # noqa: E402

import build_hybrid_board as bhb  # noqa: E402
import export_native_slices as ex  # noqa: E402
import production_run_fixture as fx  # noqa: E402
import validate_hybrid_board as vhb  # noqa: E402
import write_production_record as wp  # noqa: E402


def script(name, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)], text=True, capture_output=True)


class RefreshBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = fx.make_run(self.tmp.name)
        self.fm = self.run_dir / "final-mockups"
        ex.run(self.fm, widths=fx.WIDTHS)
        ok, lines = wp.run(self.run_dir, ocr=fx.fake_ocr, ocr_validate=False)
        assert ok, lines
        for stage in (self.fm, self.fm / "mobile"):
            proc = script("stitch_sections.py", stage)
            assert proc.returncode == 0, proc.stdout + proc.stderr
        (self.run_dir / "font-action-plan").mkdir()
        (self.run_dir / "font-action-plan" / "font-map.json").write_text("{}", encoding="utf-8")
        # the stale Nov-23 style record: pinned to files that are not the current stitches
        Image.new("RGB", (50, 60), (1, 2, 3)).save(self.fm / "mockup-full-mobile.png")
        self.rec_path = self.fm / "hybrid-board.json"
        self.rec_path.write_text(json.dumps({
            "board_output": "hybrid-board.png",
            "desktop_panel": {"source": "final-mockups/mockup-full.png", "sha256": "a" * 64},
            "mobile_panel": {"source": "final-mockups/mockup-full-mobile.png", "sha256": "b" * 64},
            "guide": {"typography_source": "font-action-plan/font-map.json", "sections": [
                {"number": i, "section_id": str(i), "name": f"Section {i}",
                 "wireframe_thumbnail": f"desktop-wireframe/section-{i:02d}.png",
                 "sha256": vhb.sha256(self.run_dir / "desktop-wireframe" / f"section-{i:02d}.png"),
                 "type_specs": {"heading": "H 64", "body": "B 18", "cta": "C 20"}} for i in (1, 2)]},
        }, indent=2), encoding="utf-8")
        self.before = self.rec_path.read_bytes()

    def tearDown(self):
        self.tmp.cleanup()

    def refresh(self, *extra):
        return script("build_hybrid_board.py", self.run_dir, "--refresh-record", *extra)

    def assert_refused(self, proc, phrase):
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("nothing was written", proc.stdout)
        self.assertIn(phrase, proc.stdout)
        self.assertEqual(self.rec_path.read_bytes(), self.before, "the record must be left untouched")
        self.assertFalse((self.fm / "hybrid-board.png").exists())

    def edit(self, path, fn):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        fn(data)
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


class PositiveTests(RefreshBase):
    def test_no_flag_still_refuses_the_stale_record(self):
        proc = script("build_hybrid_board.py", self.run_dir)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("refusing to compose", proc.stdout)
        self.assertEqual(self.rec_path.read_bytes(), self.before)

    def test_refresh_repins_to_the_current_stitches_and_composes(self):
        proc = self.refresh()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        rec = json.loads(self.rec_path.read_text(encoding="utf-8"))
        self.assertEqual(rec["desktop_panel"], {"source": "final-mockups/mockup-full.png",
                                                "sha256": vhb.sha256(self.fm / "mockup-full.png")})
        self.assertEqual(rec["mobile_panel"], {"source": "final-mockups/mobile/mockup-full-mobile.png",
                                               "sha256": vhb.sha256(self.fm / "mobile" / "mockup-full-mobile.png")})
        stitch = json.loads((self.fm / "mobile" / "stitch-receipt.json").read_text())
        self.assertEqual(rec["mobile_panel"]["sha256"], stitch["output_sha256"])
        prov = rec["refreshed_from"]
        self.assertEqual(prov["prior"]["desktop_panel"]["sha256"], "a" * 64)
        self.assertEqual(prov["prior"]["mobile_panel"]["source"], "final-mockups/mockup-full-mobile.png")
        self.assertEqual(prov["new"]["mobile_panel"], rec["mobile_panel"])
        self.assertEqual(prov["receipts"]["export"]["receipt_sha256"],
                         json.loads((self.fm / "export-receipt.json").read_text())["receipt_sha256"])
        self.assertEqual(prov["receipts"]["mobile"]["stitch_receipt"]["path"], "final-mockups/mobile/stitch-receipt.json")
        self.assertEqual(prov["receipt_sha256"], bhb._provenance_hash(prov))
        self.assertEqual(rec["guide"], json.loads(self.before)["guide"])
        check = script("validate_hybrid_board.py", self.run_dir, "--check-board")
        self.assertEqual(check.returncode, 0, check.stdout)
        receipt = json.loads((self.fm / "hybrid-board-receipt.json").read_text())
        self.assertIn(rec["mobile_panel"]["sha256"], [i["sha256"] for i in receipt["inputs"]])

    def test_an_existing_board_needs_overwrite_and_the_record_is_not_rewritten(self):
        self.assertEqual(self.refresh().returncode, 0)
        first = self.rec_path.read_bytes()
        proc = self.refresh()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Use --overwrite", proc.stdout)
        self.assertEqual(self.rec_path.read_bytes(), first)
        self.assertEqual(self.refresh("--overwrite").returncode, 0)

    def test_provenance_edit_is_caught_by_the_validator(self):
        self.assertEqual(self.refresh().returncode, 0)
        self.edit(self.rec_path, lambda d: d["refreshed_from"]["prior"]["desktop_panel"].__setitem__("sha256", "c" * 64))
        proc = script("validate_hybrid_board.py", self.run_dir)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("provenance was edited", proc.stdout)

    def test_a_record_changed_after_its_refresh_is_caught(self):
        self.assertEqual(self.refresh().returncode, 0)
        self.edit(self.rec_path, lambda d: d["desktop_panel"].__setitem__("sha256", "d" * 64))
        proc = script("validate_hybrid_board.py", self.run_dir)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("changed after its refresh", proc.stdout)


class NegativeTests(RefreshBase):
    def test_desktop_panel_not_equal_to_its_stitch_receipt(self):
        Image.new("RGB", (144, 10), (9, 9, 9)).save(self.fm / "mockup-full.png")
        self.assert_refused(self.refresh(), "desktop: the panel file")

    def test_mobile_panel_not_equal_to_its_stitch_receipt(self):
        Image.new("RGB", (39, 10), (9, 9, 9)).save(self.fm / "mobile" / "mockup-full-mobile.png")
        self.assert_refused(self.refresh(), "mobile: the panel file")

    def test_a_slice_changed_after_the_export(self):
        Image.new("RGB", (144, 144), (7, 7, 7)).save(self.fm / "desktop" / "part-01.png")
        self.assert_refused(self.refresh(), "export receipt does not verify")

    def test_stitch_inputs_that_are_not_the_stitch_receipts(self):
        self.edit(self.fm / "stitch-receipt.json", lambda d: d["sections"][0].__setitem__("sha256", "e" * 64))
        self.assert_refused(self.refresh(), "stitched from other slices")

    def test_stitch_inputs_that_are_not_the_export_receipts(self):
        # the export receipt is internally consistent (its own hash recomputed) but holds other bytes
        # for the slice than the stitch used; the file-level re-verify is bypassed to isolate the row check
        def swap(d):
            d["entries"][0]["output"]["sha256"] = "f" * 64
            d["receipt_sha256"] = ex.body_hash(d)
        self.edit(self.fm / "export-receipt.json", swap)
        real = ex.verify_receipt
        ex.verify_receipt = lambda *a, **k: []
        try:
            failures, new = bhb.refresh_record(self.run_dir, "hybrid-board.json")
        finally:
            ex.verify_receipt = real
        self.assertIsNone(new)
        self.assertTrue(any("not the slice the export receipt holds" in f for f in failures), failures)

    def test_a_tampered_export_receipt_is_refused(self):
        self.edit(self.fm / "export-receipt.json", lambda d: d["entries"][0]["output"].__setitem__("sha256", "f" * 64))
        self.assert_refused(self.refresh(), "export receipt does not verify")

    def test_missing_export_receipt(self):
        (self.fm / "export-receipt.json").unlink()
        self.assert_refused(self.refresh(), "export receipt does not verify")

    def test_missing_desktop_production_record(self):
        (self.fm / "production-record.json").unlink()
        self.assert_refused(self.refresh(), "desktop: the production record")

    def test_missing_mobile_production_record(self):
        (self.fm / "mobile" / "production-record.json").unlink()
        self.assert_refused(self.refresh(), "mobile: the production record")

    def test_a_tampered_production_record_is_refused(self):
        self.edit(self.fm / "mobile" / "production-record.json",
                  lambda d: d["sections"][0].__setitem__("width", 999))
        self.assert_refused(self.refresh(), "does not pass validate_production_record")

    def test_a_production_record_citing_another_export_receipt_is_stale(self):
        self.edit(self.fm / "production-record.json",
                  lambda d: d["sections"][1]["export"].__setitem__("receipt_sha256", "0" * 64))
        self.assert_refused(self.refresh(), "the record is stale")

    def test_missing_stitch_receipt(self):
        (self.fm / "mobile" / "stitch-receipt.json").unlink()
        self.assert_refused(self.refresh(), "mobile: the stitch receipt")

    def test_stitch_receipt_naming_another_output(self):
        self.edit(self.fm / "stitch-receipt.json", lambda d: d.__setitem__("stitched_output", "other.png"))
        self.assert_refused(self.refresh(), "stitch receipt names")

    def test_a_stale_stitch_receipt_listing_fewer_sections(self):
        self.edit(self.fm / "stitch-receipt.json", lambda d: d["sections"].pop())
        self.assert_refused(self.refresh(), "stitch receipt lists")

    def test_a_guide_that_does_not_match_is_refused(self):
        self.edit(self.rec_path, lambda d: d["guide"]["sections"][0].__setitem__("sha256", "9" * 64))
        self.before = self.rec_path.read_bytes()
        self.assert_refused(self.refresh(), "refreshed record does not pass validate_hybrid_board")


if __name__ == "__main__":
    unittest.main()
