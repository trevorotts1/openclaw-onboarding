#!/usr/bin/env python3
"""write_production_record.py --allow-text must carry its reason and authority (SWB-119).

Positive: with --allow-text, --allow-reason and --allow-authority the record's text_qc
holds an `allowed_text` object (the exact words that section shows and its copy lacks, the
whole allow list, the reason, the authority) and validate_production_record.py passes it.
Negative twins: allow-text without a reason, without an authority, a blank reason, a reason
with no allow-text, a tampered record (reason removed, a word the image never showed, a word
that is the section's own copy, the object not an object), and no override recorded when
none was used. Nothing is loosened: an un-allowed extra word is still a garble.
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

import export_native_slices as ex  # noqa: E402
import production_run_fixture as fx  # noqa: E402
import validate_production_record as vpr  # noqa: E402
import write_production_record as wp  # noqa: E402

REASON = "tesseract reads the footer ornament as gem and the page carries no such word"
AUTHORITY = "Trevor, owner, 2026-11-24"


def noisy_ocr(path):
    text = fx.fake_ocr(path)
    return text + " gem roe" if "part-01" in str(path) else text


class AllowTextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = fx.make_run(self.tmp.name)
        self.fm = self.run_dir / "final-mockups"
        ex.run(self.fm, widths=fx.WIDTHS)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, ocr=noisy_ocr, **kw):
        kw.setdefault("ocr_validate", False)
        return wp.run(self.run_dir, ocr=ocr, **kw)

    def record(self, vp="desktop"):
        path = self.fm / "production-record.json" if vp == "desktop" else self.fm / vp / "production-record.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_the_unallowed_extra_words_still_fail(self):
        ok, lines = self.write()
        self.assertFalse(ok)
        self.assertIn("gem", "\n".join(lines))
        self.assertFalse((self.fm / "production-record.json").exists())

    def test_allow_text_with_reason_and_authority_records_all_of_it(self):
        ok, lines = self.write(allow_text=["gem", "roe", "unused"], allow_reason=REASON, allow_authority=AUTHORITY)
        self.assertTrue(ok, lines)
        for vp in ("desktop", "mobile"):
            rec = self.record(vp)
            first = rec["sections"][0]["text_qc"]["allowed_text"]
            self.assertEqual(first["words"], ["gem", "roe"])
            self.assertEqual(first["allow_list"], ["gem", "roe", "unused"])
            self.assertEqual((first["reason"], first["authority"]), (REASON, AUTHORITY))
            second = rec["sections"][1]["text_qc"]["allowed_text"]
            self.assertEqual(second["words"], [])
            self.assertEqual((second["reason"], second["authority"]), (REASON, AUTHORITY))
            self.assertEqual(vpr.check_record(rec, base_dir=self.fm / "mobile" if vp == "mobile" else self.fm), [])

    def test_allow_text_without_a_reason_is_refused_and_writes_nothing(self):
        with self.assertRaisesRegex(wp.Refused, "allow-reason"):
            self.write(allow_text=["gem"], allow_authority=AUTHORITY)
        self.assertFalse((self.fm / "production-record.json").exists())

    def test_allow_text_without_an_authority_is_refused(self):
        with self.assertRaisesRegex(wp.Refused, "allow-authority"):
            self.write(allow_text=["gem"], allow_reason=REASON)

    def test_a_blank_reason_is_refused(self):
        with self.assertRaisesRegex(wp.Refused, "allow-reason"):
            self.write(allow_text=["gem"], allow_reason="   ", allow_authority=AUTHORITY)

    def test_a_reason_with_no_allow_text_is_refused(self):
        with self.assertRaisesRegex(wp.Refused, "no --allow-text"):
            self.write(ocr=fx.fake_ocr, allow_reason=REASON, allow_authority=AUTHORITY)

    def test_no_override_means_no_allowed_text_object(self):
        ok, lines = self.write(ocr=fx.fake_ocr)
        self.assertTrue(ok, lines)
        for section in self.record()["sections"]:
            self.assertNotIn("allowed_text", section["text_qc"])

    def test_cli_exit_codes(self):
        base = [str(self.run_dir), "--no-ocr-validate", "--allow-text", "gem", "--allow-text", "roe"]
        self.assertEqual(wp.main(base, ocr=noisy_ocr), 1)
        self.assertFalse((self.fm / "production-record.json").exists())
        self.assertEqual(wp.main(base + ["--allow-reason", REASON, "--allow-authority", AUTHORITY], ocr=noisy_ocr), 0)
        self.assertEqual(self.record()["sections"][0]["text_qc"]["allowed_text"]["authority"], AUTHORITY)


class ValidatorTwinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        run = fx.make_run(self.tmp.name)
        self.fm = run / "final-mockups"
        ex.run(self.fm, widths=fx.WIDTHS)
        ok, lines = wp.run(run, ocr=noisy_ocr, ocr_validate=False, allow_text=["gem", "roe"],
                           allow_reason=REASON, allow_authority=AUTHORITY)
        assert ok, lines
        self.rec = json.loads((self.fm / "production-record.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.tmp.cleanup()

    def failures(self, mutate):
        rec = copy.deepcopy(self.rec)
        mutate(rec["sections"][0]["text_qc"]["allowed_text"], rec["sections"][0]["text_qc"])
        return vpr.check_record(rec, base_dir=self.fm)

    def test_untouched_record_passes(self):
        self.assertEqual(vpr.check_record(self.rec, base_dir=self.fm), [])

    def test_removed_reason_fails(self):
        self.assertTrue(any("allowed_text.reason" in f for f in self.failures(lambda a, q: a.pop("reason"))))

    def test_blank_authority_fails(self):
        self.assertTrue(any("allowed_text.authority" in f
                            for f in self.failures(lambda a, q: a.__setitem__("authority", " "))))

    def test_a_word_the_image_never_showed_fails(self):
        def m(a, q):
            a["words"].append("ghost")
            a["allow_list"].append("ghost")
        self.assertTrue(any("not in the recorded read" in f for f in self.failures(m)))

    def test_a_word_outside_the_allow_list_fails(self):
        self.assertTrue(any("own allow_list" in f for f in self.failures(lambda a, q: a["words"].append("seat"))))

    def test_a_word_of_the_copy_is_no_allowance(self):
        def m(a, q):
            a["words"].append("seat")
            a["allow_list"].append("seat")
        self.assertTrue(any("word of the section's copy" in f for f in self.failures(m)))

    def test_an_empty_allow_list_fails(self):
        def m(a, q):
            a["words"] = []
            a["allow_list"] = []
        self.assertTrue(any("allow_list is empty" in f for f in self.failures(m)))

    def test_allowed_text_that_is_not_an_object_fails(self):
        rec = copy.deepcopy(self.rec)
        rec["sections"][0]["text_qc"]["allowed_text"] = "gem"
        self.assertTrue(any("must be an object" in f for f in vpr.check_record(rec, base_dir=self.fm)))

    def test_an_allowance_does_not_hide_a_garble(self):
        def m(a, q):
            q["readback_text"] += " zzqx"
        self.assertTrue(any("zzqx" in f for f in self.failures(m)))


if __name__ == "__main__":
    unittest.main()
