#!/usr/bin/env python3
"""scripts/write_production_record.py: a production record from tool evidence only.

Positive: after export_native_slices.py, desktop and mobile records are written,
carry the real dimensions, the generation info from the executor record, the
ledger and the saved requests, cite the export receipt, hold the OCR read-back
of each native, and pass validate_production_record.py (run by the tool itself).
Negative twins: a missing slice, a wrong width, an OCR read that contradicts the
copy (text_qc fails, never a pass), an image that shows too little of its copy,
a request section with no slice, an edited export receipt, an executor record
that is not the kept native, a ledger with no row, and an existing record.
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

import export_native_slices as ex  # noqa: E402
import production_run_fixture as fx  # noqa: E402
import validate_production_record as vpr  # noqa: E402
import write_production_record as wp  # noqa: E402


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = fx.make_run(self.tmp.name)
        self.fm = self.run_dir / "final-mockups"
        ex.run(self.fm, widths=fx.WIDTHS)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, ocr=fx.fake_ocr, **kw):
        kw.setdefault("ocr_validate", False)
        return wp.run(self.run_dir, ocr=ocr, **kw)

    def record(self, vp="desktop"):
        path = self.fm / "production-record.json" if vp == "desktop" else self.fm / vp / "production-record.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_writes_both_records_from_evidence_and_they_validate(self):
        ok, lines = self.write()
        self.assertTrue(ok, lines)
        d, m = self.record(), self.record("mobile")
        self.assertEqual((d["page_width"], m["page_width"]), (144, 39))
        self.assertEqual(d["design_style"], "A")
        s1 = d["sections"][0]
        self.assertEqual((s1["slice"], s1["width"], s1["height"]), ("desktop/part-01.png", 144, 144))
        self.assertEqual(s1["generation"]["native_aspect"], "144x144")
        self.assertEqual(s1["generation"]["native_pixels"], "288x288")
        self.assertEqual(s1["generation"]["task_id"], "taskdesktop1")
        self.assertEqual(s1["generation"]["resolution"], "4K")
        self.assertEqual(s1["generation"]["reference_urls"], ["https://example.invalid/desktop/1.png"])
        self.assertEqual(s1["generation"]["layout_reference"], "desktop-wireframe/section-01.png")
        self.assertEqual(s1["export"]["native_sha256"], fx.sha(self.fm / "raw-native/desktop/part-01.png"))
        self.assertTrue(s1["text_qc"]["checked_at_native_resolution"])
        self.assertEqual(s1["text_qc"]["garbled_words"], [])
        self.assertIn("go to my access page", s1["text_qc"]["readback_text"])
        self.assertEqual(m["sections"][1]["slice"], "part-02.png")
        self.assertEqual(m["sections"][1]["generation"]["layout_reference"], "../mobile-tablet/section-02.png")
        self.assertEqual((m["sections"][1]["width"], m["sections"][1]["height"]), (39, 69))
        for vp, rec in (("desktop", self.fm / "production-record.json"), ("mobile", self.fm / "mobile/production-record.json")):
            self.assertEqual(vpr.check_record(json.loads(rec.read_text()), base_dir=rec.parent), [], vp)
        self.assertTrue((self.fm / "text-qc-readback-desktop.json").is_file())
        self.assertFalse((self.fm / ".production-record.candidate.json").exists())

    # ---- negative twins -------------------------------------------------
    def test_ocr_that_contradicts_the_copy_fails_and_leaves_no_record(self):
        def bad(path):
            text = fx.fake_ocr(path)
            return text.replace("payment", "paymant").replace("receipt", "reciept") if "part-02" in str(path) else text
        ok, lines = self.write(ocr=bad)
        self.assertFalse(ok)
        joined = "\n".join(lines)
        self.assertIn("paymant", joined)
        self.assertFalse((self.fm / "production-record.json").exists())
        self.assertFalse((self.fm / "mobile/production-record.json").exists())

    def test_a_misread_twin_of_a_word_also_read_correctly_is_a_variant_not_a_garble(self):
        def twin(path):
            return fx.fake_ocr(path) + (" paymant" if "part-02" in str(path) else "")
        ok, lines = self.write(ocr=twin)
        self.assertTrue(ok, lines)
        qc = self.record()["sections"][1]["text_qc"]
        self.assertIn("paymant", qc["ocr_variants_of_copy_words"])
        self.assertNotIn("paymant", qc["readback_text"])

    def test_an_image_that_shows_too_little_of_its_copy_fails(self):
        ok, lines = self.write(ocr=lambda p: "payment")
        self.assertFalse(ok)
        self.assertTrue(any("of its copy" in line for line in lines), lines)

    def test_an_empty_read_never_passes(self):
        ok, lines = self.write(ocr=lambda p: "")
        self.assertFalse(ok)
        self.assertFalse((self.fm / "production-record.json").exists())

    def test_missing_slice_is_refused(self):
        (self.fm / "desktop/part-02.png").unlink()
        with self.assertRaisesRegex(wp.Refused, "output file is missing"):
            self.write()

    def test_request_section_with_no_slice_is_refused(self):
        req = self.run_dir / "production-request-final-mockups.json"
        data = json.loads(req.read_text())
        data["sections"].append({"section_id": "3", "copy": "A third section", "cta": None})
        req.write_text(json.dumps(data))
        with self.assertRaisesRegex(wp.Refused, "request names 3 section"):
            self.write()

    def test_extra_slice_the_request_does_not_name_is_refused(self):
        req = self.run_dir / "production-request-final-mockups.json"
        data = json.loads(req.read_text())
        data["sections"] = data["sections"][:1]
        req.write_text(json.dumps(data))
        with self.assertRaisesRegex(wp.Refused, "request names 1 section"):
            self.write()

    def test_wrong_width_slice_is_caught_by_the_receipt(self):
        Image.new("RGB", (200, 200), (1, 1, 1)).save(self.fm / "desktop/part-01.png")
        with self.assertRaisesRegex(wp.Refused, "export receipt does not verify"):
            self.write()

    def test_tampered_receipt_is_refused(self):
        path = self.fm / "export-receipt.json"
        data = json.loads(path.read_text())
        data["entries"][0]["output"]["width"] = 999
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(wp.Refused, "export receipt does not verify"):
            self.write()

    def test_receipt_rehashed_after_tamper_still_fails_on_the_files(self):
        path = self.fm / "export-receipt.json"
        data = json.loads(path.read_text())
        data["entries"][0]["native"]["sha256"] = "0" * 64
        data["receipt_sha256"] = ex.body_hash(data)
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(wp.Refused, "no longer matches the receipt"):
            self.write()

    def test_executor_record_for_a_different_file_is_refused(self):
        path = self.fm / "stage-executor-record.json"
        data = json.loads(path.read_text())
        data["images"][0]["sha256"] = "f" * 64
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(wp.Refused, "not the kept native"):
            self.write()

    def test_missing_ledger_row_is_refused(self):
        path = self.run_dir / "image-spend-ledger.json"
        path.write_text(json.dumps({"calls": []}))
        with self.assertRaisesRegex(wp.Refused, "no done row in image-spend-ledger"):
            self.write()

    def test_a_non_gpt_image_provider_is_refused(self):
        path = self.fm / "stage-executor-record.json"
        data = json.loads(path.read_text())
        data["images"][0]["provider"] = "stub"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(wp.Refused, "not the KIE.ai GPT-image route"):
            self.write()

    def test_generated_ratio_must_equal_the_requested_ratio(self):
        path = self.fm / "stage-executor-record.json"
        data = json.loads(path.read_text())
        data["images"][1]["requested_ratio"] = "1:1"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(wp.Refused, "does not equal the requested ratio"):
            self.write()

    def test_missing_saved_request_means_no_reference_urls_are_invented(self):
        for job in (self.run_dir / "image-jobs").iterdir():
            shutil.rmtree(job)
        with self.assertRaisesRegex(wp.Refused, "no image-jobs attempt carries identity key"):
            self.write()

    def test_an_existing_record_needs_overwrite(self):
        self.assertTrue(self.write()[0])
        with self.assertRaisesRegex(wp.Refused, "already exists"):
            self.write()
        self.assertTrue(self.write(overwrite=True)[0])

    def test_cli_exits_one_on_a_failed_read(self):
        code = wp.main([str(self.run_dir), "--no-ocr-validate"], ocr=lambda p: "nothing legible")
        self.assertEqual(code, 1)
        self.assertEqual(wp.main([str(self.run_dir), "--no-ocr-validate"], ocr=fx.fake_ocr), 0)


@unittest.skipUnless(shutil.which("tesseract"), "tesseract is not installed")
class RealReaderTest(unittest.TestCase):
    """The real design_board.ocr_text reads a native image drawn with the copy."""

    def make(self, tmp, drawn):
        from PIL import ImageDraw, ImageFont
        run = fx.make_run(tmp)
        fm = run / "final-mockups"
        req = run / "production-request-final-mockups.json"
        data = json.loads(req.read_text())
        data["sections"] = [{"section_id": "1", "copy": "Your seat is confirmed", "cta": None}]
        req.write_text(json.dumps(data))
        for vp in ("desktop", "mobile"):
            (fm / vp / "part-02.png").unlink()
            ex_path = fm / "stage-executor-record.json"
            rec = json.loads(ex_path.read_text())
            rec["images"] = [i for i in rec["images"] if not i["file"].endswith("part-02.png")]
            ex_path.write_text(json.dumps(rec))
        for vp, size in (("desktop", (1600, 1600)), ("mobile", (1600, 1600))):
            img = Image.new("RGB", size, "white")
            ImageDraw.Draw(img).text((100, 600), drawn, fill="black", font=ImageFont.load_default(size=150))
            img.save(fm / vp / "part-01.png")
        rec = json.loads((fm / "stage-executor-record.json").read_text())
        for i in rec["images"]:
            i["sha256"] = fx.sha(fm / i["file"].split("/", 1)[1])
            i["actual_pixels"] = [1600, 1600]
            i["requested_ratio"] = "1:1"
        (fm / "stage-executor-record.json").write_text(json.dumps(rec))
        ex.run(fm, widths={"desktop": 800, "mobile": 400})
        return run

    def test_real_ocr_pass_and_a_real_garble_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make(tmp, "Your seat is confirmed")
            ok, lines = wp.run(run, ocr_validate=True)  # the validator's own --ocr read of the exported desktop slice
            self.assertTrue(ok, lines)
            qc = json.loads((run / "final-mockups/production-record.json").read_text())["sections"][0]["text_qc"]
            self.assertIn("confirmed", qc["ocr_text"].lower())
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make(tmp, "Your seat is conflrmqd")
            ok, lines = wp.run(run, ocr_validate=False)
            self.assertFalse(ok, lines)
            self.assertFalse((run / "final-mockups/production-record.json").exists())


if __name__ == "__main__":
    unittest.main()
