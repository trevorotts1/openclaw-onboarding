#!/usr/bin/env python3
"""scripts/export_native_slices.py: page-width export that keeps every native.

Positive: the export is Lanczos at the page width with the aspect kept, the
native is kept byte for byte with its sha256, the receipt names inputs, outputs,
sizes, hashes and method, and a second run changes nothing.
Negative twins: an unreadable or zero-size input, a missing slice number, a
native narrower than the page width, a different native already kept, a slice
that is not the export of its kept native, and an edited receipt.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

from PIL import Image  # noqa: E402

import export_native_slices as ex  # noqa: E402
import production_run_fixture as fx  # noqa: E402

W = {"desktop": fx.WIDTHS["desktop"], "mobile": fx.WIDTHS["mobile"]}


def run_export(fm, **kw):
    return ex.run(fm, widths=W, **kw)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = fx.make_run(self.tmp.name)
        self.fm = self.run_dir / "final-mockups"

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_keeps_natives_and_writes_a_verifiable_receipt(self):
        natives = {p: fx.sha(self.fm / p) for p in ("desktop/part-01.png", "desktop/part-02.png",
                                                     "mobile/part-01.png", "mobile/part-02.png")}
        summary, receipt = run_export(self.fm)
        self.assertEqual(len(summary["export"]), 4)
        for rel, digest in natives.items():
            self.assertEqual(fx.sha(self.fm / "raw-native" / rel), digest, "native kept byte for byte")
        sizes = {rel: ex.read_dims(self.fm / rel) for rel in natives}
        self.assertEqual(sizes["desktop/part-01.png"], (144, 144))
        self.assertEqual(sizes["desktop/part-02.png"], (144, 81))     # 3840x2160 shape -> 1440x810
        self.assertEqual(sizes["mobile/part-02.png"], (39, 69))       # 2160x3840 shape -> 390x693
        self.assertEqual(receipt["entries"][0]["native"]["sha256"], natives["desktop/part-01.png"])
        self.assertIn("Lanczos", receipt["method"])
        self.assertEqual(ex.verify_receipt(self.fm / "export-receipt.json", self.fm), [])

    def test_second_run_is_idempotent(self):
        run_export(self.fm)
        before = (self.fm / "export-receipt.json").read_bytes()
        outs = {p.name + p.parent.name: fx.sha(p) for p in self.fm.glob("*/part-*.png") if "raw-native" not in str(p)}
        summary, _ = run_export(self.fm)
        self.assertEqual(len(summary["unchanged"]), 4)
        self.assertEqual(summary["export"], [])
        self.assertEqual(before, (self.fm / "export-receipt.json").read_bytes())
        again = {p.name + p.parent.name: fx.sha(p) for p in self.fm.glob("*/part-*.png") if "raw-native" not in str(p)}
        self.assertEqual(outs, again)

    def test_dry_run_changes_nothing(self):
        before = fx.sha(self.fm / "desktop/part-01.png")
        summary, receipt = run_export(self.fm, dry_run=True)
        self.assertEqual(len(summary["export"]), 4)
        self.assertIsNone(receipt)
        self.assertEqual(before, fx.sha(self.fm / "desktop/part-01.png"))
        self.assertFalse((self.fm / "raw-native").exists())

    # ---- negative twins -------------------------------------------------
    def test_zero_size_input_is_refused_and_nothing_is_touched(self):
        (self.fm / "mobile/part-02.png").write_bytes(b"")
        before = fx.sha(self.fm / "desktop/part-01.png")
        with self.assertRaisesRegex(ex.Refused, "zero-size"):
            run_export(self.fm)
        self.assertEqual(before, fx.sha(self.fm / "desktop/part-01.png"))
        self.assertFalse((self.fm / "raw-native").exists())

    def test_unreadable_input_is_refused(self):
        (self.fm / "desktop/part-02.png").write_bytes(b"not an image at all")
        with self.assertRaisesRegex(ex.Refused, "not a readable image"):
            run_export(self.fm)

    def test_missing_slice_number_is_refused(self):
        (self.fm / "desktop/part-01.png").unlink()
        with self.assertRaisesRegex(ex.Refused, "gap or does not start at 01"):
            run_export(self.fm)

    def test_native_narrower_than_the_page_width_is_refused(self):
        Image.new("RGB", (100, 100), (1, 2, 3)).save(self.fm / "desktop/part-01.png")
        with self.assertRaisesRegex(ex.Refused, "never upscales"):
            run_export(self.fm)

    def test_a_different_native_already_kept_is_never_overwritten(self):
        kept = self.fm / "raw-native/desktop"
        kept.mkdir(parents=True)
        Image.new("RGB", (288, 288), (7, 7, 7)).save(kept / "part-01.png")
        stale = fx.sha(kept / "part-01.png")
        with self.assertRaisesRegex(ex.Refused, "natives are never overwritten"):
            run_export(self.fm)
        self.assertEqual(stale, fx.sha(kept / "part-01.png"))

    def test_an_already_exported_slice_with_no_kept_native_is_refused(self):
        Image.new("RGB", (144, 144), (5, 5, 5)).save(self.fm / "desktop/part-01.png")
        with self.assertRaisesRegex(ex.Refused, "no native is kept"):
            run_export(self.fm)

    def test_a_slice_that_is_not_the_export_of_its_native_is_refused(self):
        run_export(self.fm)
        Image.new("RGB", (144, 144), (250, 0, 0)).save(self.fm / "desktop/part-01.png")
        (self.fm / "export-receipt.json").unlink()
        with self.assertRaisesRegex(ex.Refused, "not the 144 px export"):
            run_export(self.fm)

    def test_an_edited_receipt_fails_verification(self):
        run_export(self.fm)
        path = self.fm / "export-receipt.json"
        data = json.loads(path.read_text())
        data["entries"][0]["native"]["sha256"] = "0" * 64
        path.write_text(json.dumps(data))
        out = ex.verify_receipt(path, self.fm)
        self.assertTrue(out and "edited" in out[0])

    def test_an_edited_output_fails_verification(self):
        run_export(self.fm)
        Image.new("RGB", (144, 144), (1, 1, 1)).save(self.fm / "desktop/part-01.png")
        out = ex.verify_receipt(self.fm / "export-receipt.json", self.fm)
        self.assertTrue(any("no longer matches" in line for line in out))

    def test_cli_exit_codes(self):
        self.assertEqual(ex.main([str(self.fm), "--desktop-width", "144", "--mobile-width", "39"]), 0)
        (self.fm / "desktop/part-01.png").write_bytes(b"")
        self.assertEqual(ex.main([str(self.fm), "--desktop-width", "144", "--mobile-width", "39"]), 1)


if __name__ == "__main__":
    unittest.main()
