#!/usr/bin/env python3
"""SWB-290 item B: a wireframe stage can be exported, recorded, stitched and combined.

The stage executor writes wireframe natives flat (`<stage>/section-NN.png`) at whatever size the
provider returns (1024x768, 1536x864 at 1K). No tool wrote the page-width slices or the production
record, so the stitcher and the PDF combiner failed on mixed widths. This module pins the fix:

  - the wireframe request asks the provider for a 2K resolution (the request's input_extra still
    wins, final-mockups requests are unchanged) and every wireframe job names its ratio;
  - export_native_slices.py exports the flat layout (natives kept in <stage>/raw-native, Lanczos
    resize to the page width, receipt with layout flat), never upscaling;
  - write_production_record.py --stage <wireframe stage> writes the one record from evidence only,
    and validate_production_record, stitch_sections and combine_review_pdf all pass on it;
  - negative twins: a native narrower than the page width, a receipt that is not the flat export,
    an executor record that is not the kept native, an OCR garble, a missing ratio, a missing plan.

No paid API is called anywhere in this module.
"""
import hashlib
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

import export_native_slices as ex  # noqa: E402
import stage_executor as exe  # noqa: E402
import validate_production_record as vpr  # noqa: E402
import write_production_record as wp  # noqa: E402

MODEL = "gpt-image-2-6/sunburst-image-to-image"
PAGE = 144  # a tiny page width keeps the images small; the scratch proof runs the real 1440
# (native pixels, requested ratio) per section: the 2K natives are wider than the page
NATIVES = [((288, 216), "4:3"), ((320, 180), "16:9"), ((320, 180), "16:9")]
SECTIONS = [
    {"section_id": "1", "section_name": "Confirmation", "copy": "CONFIRMED\nYou are all set.", "cta": "Start here"},
    {"section_id": "2", "section_name": "Order summary", "copy": "Your payment was received.", "cta": None},
    {"section_id": "3", "section_name": "Access", "copy": "Open your workbook anytime.", "cta": None},
]
OCR = {
    "1": "CONFIRMED You are all set. Start here SECTION 1 CONFIRMATION H1 / 64 px",
    "2": "Your payment was received. SECTION 2 ORDER SUMMARY BEHAVIOR NOTE",
    "3": "Open your workbook anytime. SECTION 3 ACCESS",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fake_ocr(path):
    return OCR[str(int(Path(path).stem.split("-")[1]))]


def make_wireframe_run(tmp, stage="desktop-wireframe", natives=NATIVES, resolution="2K"):
    run = Path(tmp) / "thank_you-run"
    st = run / stage
    (run / "private").mkdir(parents=True)
    st.mkdir(parents=True)
    (run / "private" / "brand.json").write_text("{}", encoding="utf-8")
    (run / "intake.json").write_text(json.dumps({"design_style": "A"}), encoding="utf-8")
    (st / "section-plan.json").write_text("{}", encoding="utf-8")
    images, calls = [], []
    for n, ((w, h), ratio) in enumerate(natives, start=1):
        name = f"section-{n:02d}.png"
        Image.new("RGB", (w, h), (200 + n, 30 * n, 40)).save(st / name)
        key, task = f"key-{n}", f"task{n}"
        images.append({"file": f"{stage}/{name}", "section_id": str(n), "provider": "kie", "model": MODEL,
                       "state": "settled", "actual_pixels": [w, h], "requested_ratio": ratio, "attempt": 1,
                       "task_id": task, "sha256": sha(st / name), "prompt_sha256": "p" * 64,
                       "request_sha256": "r" * 64, "identity": {"key": key, "attempt": 1}})
        calls.append({"file": f"{stage}/{name}", "task_id": task, "status": "done", "state": "settled",
                      "id": f"id{n}"})
        job = run / "image-jobs" / f"{stage}-{name}-1440x760-aaaa{n}"
        (job / "requests").mkdir(parents=True)
        (job / "attempt-001.json").write_text(json.dumps(
            {"identity": {"key": key, "attempt": 1}, "task_id": task, "attempt": 1}), encoding="utf-8")
        inp = {"input_urls": [f"https://example.invalid/{n}.png"]}
        if resolution:
            inp["resolution"] = resolution
        (job / "requests" / "request-a001.json").write_text(json.dumps({"input": inp}), encoding="utf-8")
    (st / "stage-executor-record.json").write_text(json.dumps({"stage": stage, "images": images}), encoding="utf-8")
    (run / "image-spend-ledger.json").write_text(json.dumps({"calls": calls}), encoding="utf-8")
    (run / f"production-request-{stage}.json").write_text(json.dumps({
        "model": MODEL, "sections": SECTIONS,
        "design_board": {"brand_name": "Dr Wall", "footer_taglines": ["Worthiness Gap"]},
    }), encoding="utf-8")
    return run


class ResolutionTests(unittest.TestCase):
    def job(self, stage, ratio="16:9"):
        return {"stage": stage, "prompt": "p", "references": ["https://example.invalid/r.png"],
                "style_refs": [], "ratio": ratio}

    def test_wireframe_stages_ask_for_2k(self):
        for stage in ("desktop-wireframe", "mobile-tablet"):
            self.assertEqual(exe.build_input(self.job(stage), {})["resolution"], "2K", stage)

    def test_the_requests_own_input_extra_wins(self):
        out = exe.build_input(self.job("desktop-wireframe"), {"input_extra": {"resolution": "4K"}})
        self.assertEqual(out["resolution"], "4K")

    def test_other_stages_are_unchanged(self):
        for stage in ("visual-mockup", "final-mockups"):
            self.assertNotIn("resolution", exe.build_input(self.job(stage), {}), stage)
        self.assertEqual(exe.build_input(self.job("final-mockups"), {"input_extra": {"resolution": "4K"}})["resolution"], "4K")

    def test_a_wireframe_job_with_no_ratio_is_refused(self):
        with self.assertRaisesRegex(exe.ExecutorError, "requested ratio must be explicit"):
            exe.build_input(self.job("desktop-wireframe", ratio=""), {})
        self.assertNotIn("aspect_ratio", exe.build_input(self.job("final-mockups", ratio=""), {}))


class FlatExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = make_wireframe_run(self.tmp.name)
        self.st = self.run_dir / "desktop-wireframe"

    def tearDown(self):
        self.tmp.cleanup()

    def export(self, **kw):
        return ex.run(self.st, widths={"desktop": PAGE}, **kw)

    def test_flat_export_keeps_natives_and_exports_to_the_page_width(self):
        natives = {n: sha(self.st / n) for n in ("section-01.png", "section-02.png", "section-03.png")}
        summary, receipt = self.export()
        self.assertEqual(len(summary["export"]), 3)
        for name, digest in natives.items():
            self.assertEqual(sha(self.st / "raw-native" / name), digest)
        sizes = {n: ex.read_dims(self.st / n) for n in natives}
        self.assertEqual(sizes["section-01.png"], (PAGE, 108))   # 4:3
        self.assertEqual(sizes["section-02.png"], (PAGE, 81))    # 16:9
        self.assertEqual(receipt["layout"], "flat")
        self.assertEqual(receipt["stage"], "desktop-wireframe")
        self.assertEqual(receipt["page_widths"], {"desktop": PAGE})
        self.assertEqual(receipt["entries"][0]["native"]["path"], "raw-native/section-01.png")
        self.assertEqual(receipt["entries"][0]["output"]["path"], "section-01.png")
        self.assertEqual(ex.verify_receipt(self.st / "export-receipt.json", self.st), [])

    def test_the_stage_is_inferred_from_the_folder_and_a_second_run_changes_nothing(self):
        self.export()
        before = (self.st / "export-receipt.json").read_bytes()
        summary, _ = self.export()
        self.assertEqual((len(summary["export"]), len(summary["unchanged"])), (0, 3))
        self.assertEqual((self.st / "export-receipt.json").read_bytes(), before)

    def test_mobile_tablet_is_a_mobile_stage(self):
        with tempfile.TemporaryDirectory() as td:
            run = make_wireframe_run(td, stage="mobile-tablet", natives=[((200, 360), "9:16")] * 3)
            _s, receipt = ex.run(run / "mobile-tablet", widths={"mobile": 39})
            self.assertEqual(receipt["page_widths"], {"mobile": 39})
            self.assertEqual(ex.read_dims(run / "mobile-tablet" / "section-01.png"), (39, 70))

    # ---- negative twins ----
    def test_a_native_narrower_than_the_page_is_refused_and_nothing_is_touched(self):
        Image.new("RGB", (100, 75), (1, 1, 1)).save(self.st / "section-02.png")
        before = sha(self.st / "section-01.png")
        with self.assertRaisesRegex(ex.Refused, "narrower than the 144 px page width"):
            self.export()
        self.assertEqual(sha(self.st / "section-01.png"), before)
        self.assertFalse((self.st / "raw-native").exists())

    def test_a_gap_in_the_numbering_is_refused(self):
        (self.st / "section-02.png").unlink()
        with self.assertRaisesRegex(ex.Refused, "gap"):
            self.export()

    def test_a_different_native_already_kept_is_never_overwritten(self):
        (self.st / "raw-native").mkdir()
        Image.new("RGB", (400, 300), (9, 9, 9)).save(self.st / "raw-native" / "section-01.png")
        with self.assertRaisesRegex(ex.Refused, "different native is already kept"):
            self.export()

    def test_a_desktop_stage_refuses_the_mobile_viewport(self):
        with self.assertRaisesRegex(ex.Refused, "is a desktop stage"):
            ex.run(self.st, viewports=("mobile",), widths={"desktop": PAGE})

    def test_the_final_mockups_receipt_keeps_its_shape(self):
        import production_run_fixture as fx
        with tempfile.TemporaryDirectory() as td:
            run = fx.make_run(td)
            _s, receipt = ex.run(run / "final-mockups", widths=fx.WIDTHS)
            self.assertNotIn("layout", receipt)
            self.assertNotIn("stage", receipt)


class WireframeRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = make_wireframe_run(self.tmp.name)
        self.st = self.run_dir / "desktop-wireframe"
        ex.run(self.st, widths={"desktop": PAGE})

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, ocr=fake_ocr, **kw):
        kw.setdefault("ocr_validate", False)
        return wp.run(self.run_dir, stage="desktop-wireframe", ocr=ocr, **kw)

    def record(self):
        return json.loads((self.st / "production-record.json").read_text(encoding="utf-8"))

    def test_record_from_evidence_validates_stitches_and_combines(self):
        ok, lines = self.write()
        self.assertTrue(ok, lines)
        rec = self.record()
        self.assertEqual((rec["artifact"], rec["stage"], rec["page_width"]), ("wireframe", "desktop-wireframe", PAGE))
        s1 = rec["sections"][0]
        self.assertEqual((s1["slice"], s1["width"], s1["height"]), ("section-01.png", PAGE, 108))
        self.assertEqual(s1["generation"]["native_pixels"], "288x216")
        self.assertEqual(s1["generation"]["resolution"], "2K")
        self.assertEqual(s1["generation"]["requested_ratio"], "4:3")
        self.assertEqual(s1["generation"]["layout_reference"], "desktop-wireframe/section-plan.json")
        self.assertEqual(s1["export"]["native_sha256"], sha(self.st / "raw-native" / "section-01.png"))
        self.assertEqual(s1["text_qc"]["garbled_words"], [])
        self.assertEqual(vpr.check_record(rec, base_dir=self.st), [])
        stitch = subprocess.run([sys.executable, str(SCRIPTS / "stitch_sections.py"), str(self.st)],
                                capture_output=True, text=True)
        self.assertEqual(stitch.returncode, 0, stitch.stdout + stitch.stderr)
        self.assertEqual(ex.read_dims(self.st / "wireframe-full.png"), (PAGE, 108 + 81 + 81))
        combine = subprocess.run([sys.executable, str(SCRIPTS / "combine_review_pdf.py"), str(self.run_dir),
                                  "--stage", "desktop-wireframe"], capture_output=True, text=True)
        self.assertEqual(combine.returncode, 0, combine.stdout + combine.stderr)
        self.assertNotIn("different widths", combine.stdout + combine.stderr)

    def test_unexported_natives_make_the_stitcher_fail_the_old_way(self):
        # fail-before: with no export and no record the stitcher has nothing to stitch from
        (self.st / "production-record.json").unlink(missing_ok=True)
        proc = subprocess.run([sys.executable, str(SCRIPTS / "stitch_sections.py"), str(self.st)],
                              capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)

    # ---- negative twins ----
    def test_a_garbled_word_fails_and_leaves_no_record(self):
        ok, lines = self.write(ocr=lambda p: fake_ocr(p).replace("payment", "paymant") if "02" in str(p) else fake_ocr(p))
        self.assertFalse(ok)
        self.assertIn("paymant", "\n".join(lines))
        self.assertFalse((self.st / "production-record.json").exists())
        self.assertFalse((self.st / ".production-record.candidate.json").exists())

    def test_a_word_that_is_not_the_copy_or_an_annotation_is_garbled(self):
        ok, lines = self.write(ocr=lambda p: fake_ocr(p) + " zebra")
        self.assertFalse(ok)
        self.assertIn("zebra", "\n".join(lines))

    def test_allow_text_needs_its_reason_and_authority(self):
        with self.assertRaisesRegex(wp.Refused, "--allow-text needs both"):
            self.write(ocr=lambda p: fake_ocr(p) + " zebra", allow_text=["zebra"])

    def test_an_empty_read_never_passes(self):
        ok, _ = self.write(ocr=lambda p: "")
        self.assertFalse(ok)

    def test_a_final_mockups_receipt_is_not_a_wireframe_receipt(self):
        path = self.st / "export-receipt.json"
        data = json.loads(path.read_text())
        data.pop("layout")
        data["receipt_sha256"] = ex.body_hash(data)
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(wp.Refused, "not the flat export"):
            self.write()

    def test_a_tampered_receipt_is_refused(self):
        path = self.st / "export-receipt.json"
        data = json.loads(path.read_text())
        data["entries"][0]["output"]["width"] = 999
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(wp.Refused, "export receipt does not verify"):
            self.write()

    def test_an_executor_record_that_is_not_the_kept_native_is_refused(self):
        path = self.st / "stage-executor-record.json"
        data = json.loads(path.read_text())
        data["images"][0]["sha256"] = "0" * 64
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(wp.Refused, "not the kept native's"):
            self.write()

    def test_a_missing_requested_ratio_is_refused(self):
        path = self.st / "stage-executor-record.json"
        data = json.loads(path.read_text())
        data["images"][1]["requested_ratio"] = ""
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(wp.Refused, "ratio must be explicit"):
            self.write()

    def test_a_missing_section_plan_is_refused(self):
        (self.st / "section-plan.json").unlink()
        with self.assertRaisesRegex(wp.Refused, "section plan"):
            self.write()

    def test_a_request_section_with_no_slice_is_refused(self):
        req = self.run_dir / "production-request-desktop-wireframe.json"
        data = json.loads(req.read_text())
        data["sections"].append({"section_id": "4", "copy": "More", "cta": None})
        req.write_text(json.dumps(data))
        with self.assertRaisesRegex(wp.Refused, "request names 4 section"):
            self.write()

    def test_an_existing_record_is_never_replaced_without_overwrite(self):
        ok, _ = self.write()
        self.assertTrue(ok)
        with self.assertRaisesRegex(wp.Refused, "already exists"):
            self.write()
        ok, _ = self.write(overwrite=True)
        self.assertTrue(ok)

    def test_the_final_mockups_default_request_name_is_unchanged(self):
        self.assertEqual(wp.DEFAULT_FM_REQUEST, "production-request-final-mockups.json")


if __name__ == "__main__":
    unittest.main()
