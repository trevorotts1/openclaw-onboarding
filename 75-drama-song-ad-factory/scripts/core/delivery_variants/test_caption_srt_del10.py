"""DEL-10 tests: the delivery folder ships a valid caption file (.srt).

Fixture: ``fixtures/caption_srt_del10.json`` — a generic sample sheet, the
measured word timings the pipeline records, the cue windows those produce,
and a golden SRT whose exact bytes are asserted. The structure checks are
written here independently of the writer, so a broken builder cannot pass
its own parse. Stdlib only, zero network, zero spend, no ffmpeg.

Run: python3 scripts/core/delivery_variants/test_caption_srt_del10.py
"""
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from delivery_variants import caption_srt as cs  # noqa: E402
import caption_timing  # noqa: E402  the pipeline's caption/timing source

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "caption_srt_del10.json"
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))

_TS = re.compile(
    r"^\d{2,}:[0-5]\d:[0-5]\d,\d{3} --> \d{2,}:[0-5]\d:[0-5]\d,\d{3}$")


def _ms(stamp):
    """'00:00:02,750' -> 2.75 seconds (read by the test's own parser)."""
    hh, mm, rest = stamp.split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


def pipeline_cues():
    """The cues the run already produces: approved sheet + measured timing."""
    return caption_timing.captions(DATA["sheet"], DATA["timing"])


class ExportWritesValidSrt(unittest.TestCase):
    """The run's delivery folder ends up with one valid, numbered .srt."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="del10-"))
        self.delivery = self.tmp / "delivery"
        self.cues, self.receipt = pipeline_cues()
        self.exported = cs.export_captions_srt(str(self.delivery), self.cues)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pipeline_fixture_yields_the_expected_cues(self):
        self.assertTrue(self.receipt.get("ok"), self.receipt)
        got = [(c["text"], round(c["start"], 3), round(c["end"], 3))
               for c in self.cues]
        want = [(c["text"], c["start"], c["end"])
                for c in DATA["expected_cues"]]
        self.assertEqual(got, want)

    def test_file_is_the_numbered_package_name(self):
        self.assertTrue(self.exported["ok"], self.exported)
        self.assertEqual(self.exported["file"], "10 - Captions.srt")
        path = self.delivery / "10 - Captions.srt"
        self.assertTrue(path.is_file())
        self.assertGreater(path.stat().st_size, 0)

    def test_receipt_is_honest(self):
        self.assertEqual(self.exported["timing"], "measured")
        self.assertEqual(self.exported["cue_count"], len(self.cues))
        self.assertEqual(self.exported["reason_code"], None)
        self.assertRegex(self.exported["sha256"], r"^[0-9a-f]{64}$")

    def test_structure_validated_independently_of_the_writer(self):
        """Indexes, timestamps and bodies re-checked by THIS test's parser."""
        text = (self.delivery / "10 - Captions.srt").read_text(
            encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        blocks = re.split(r"(?:\r?\n){2,}", text.strip("\r\n"))
        self.assertEqual(len(blocks), len(DATA["expected_cues"]))
        prev_start = None
        for i, block in enumerate(blocks, 1):
            lines = block.split("\n")
            self.assertGreaterEqual(len(lines), 3, block)
            self.assertEqual(lines[0], str(i))
            self.assertRegex(lines[1], _TS)
            start, end = (_ms(p) for p in lines[1].split(" --> "))
            self.assertLessEqual(start, end)
            if prev_start is not None:
                self.assertGreaterEqual(start, prev_start)
            self.assertTrue("\n".join(lines[2:]).strip())
            want = DATA["expected_cues"][i - 1]
            self.assertAlmostEqual(start, want["start"], delta=0.001)
            self.assertAlmostEqual(end, want["end"], delta=0.001)
            prev_start = start

    def test_text_is_the_sheet_word_for_word(self):
        """The cue bodies ARE the approved sheet's lines, in order."""
        text = (self.delivery / "10 - Captions.srt").read_text(
            encoding="utf-8")
        bodies = [ln for ln in text.strip("\n").split("\n")
                  if ln and not ln.isdigit() and " --> " not in ln]
        self.assertEqual(bodies, DATA["sheet"])

    def test_gate_passes_on_a_clean_export(self):
        self.assertEqual(cs.check_captions_srt(str(self.delivery)),
                         ("PASS", "10 - Captions.srt carries 3 valid cues"))


class GoldenBytes(unittest.TestCase):
    """Exact SRT format: index, comma milliseconds, blank line, newline."""

    def test_export_matches_the_golden_file_byte_for_byte(self):
        tmp = Path(tempfile.mkdtemp(prefix="del10-"))
        try:
            delivery = tmp / "delivery"
            receipt = cs.export_captions_srt(str(delivery),
                                             DATA["golden"]["cues"])
            self.assertTrue(receipt["ok"], receipt)
            raw = (delivery / "10 - Captions.srt").read_bytes()
            self.assertEqual(raw.decode("utf-8"), DATA["golden"]["srt"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class FailClosed(unittest.TestCase):
    """No measured cues, no file: an empty clock is never invented."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="del10-"))
        self.delivery = self.tmp / "delivery"
        self.name = "10 - Captions.srt"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def assertRefused(self, receipt, code):
        self.assertFalse(receipt["ok"], receipt)
        self.assertEqual(receipt["reason_code"], code, receipt)
        self.assertEqual(receipt["timing"], "unavailable")
        self.assertFalse((self.delivery / self.name).exists())
        self.assertEqual(sorted(p.name for p in self.delivery.glob("*.srt"))
                         if self.delivery.exists() else [], [])

    def test_no_cues_refused(self):
        self.assertRefused(cs.export_captions_srt(str(self.delivery), []),
                           cs.NO_CUES)

    def test_cues_must_be_a_list(self):
        for bad in (None, "cues", {"text": "x"}, 7):
            self.assertRefused(
                cs.export_captions_srt(str(self.delivery), bad), cs.BAD_INPUT)

    def test_bad_delivery_dir_refused(self):
        for bad in ("", None, "   "):
            r = cs.export_captions_srt(bad, DATA["golden"]["cues"])
            self.assertFalse(r["ok"], r)
            self.assertEqual(r["reason_code"], cs.BAD_INPUT)

    def test_window_that_ends_before_it_starts_refused(self):
        self.assertRefused(
            cs.export_captions_srt(str(self.delivery),
                                   [{"text": "x", "start": 2.0, "end": 1.0}]),
            cs.BAD_CUES)

    def test_cue_without_text_refused(self):
        self.assertRefused(
            cs.export_captions_srt(str(self.delivery),
                                   [{"text": "  ", "start": 0.0, "end": 1.0}]),
            cs.BAD_CUES)

    def test_cue_with_a_blank_line_refused_never_written(self):
        """A blank line inside cue text would break the file's own blocks."""
        self.assertRefused(
            cs.export_captions_srt(str(self.delivery),
                                   [{"text": "line\n\nbreak",
                                     "start": 0.0, "end": 1.0}]),
            cs.BAD_CUES)

    def test_check_on_an_empty_folder_fails_naming_the_file(self):
        verdict, detail = cs.check_captions_srt(str(self.delivery))
        self.assertEqual(verdict, "FAIL")
        self.assertIn(self.name, detail)


class TamperedFile(unittest.TestCase):
    """The gate bites: a broken file is a FAIL, not a pass."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="del10-"))
        self.delivery = self.tmp / "delivery"
        self.path = self.delivery / "10 - Captions.srt"
        self.assertTrue(cs.export_captions_srt(
            str(self.delivery), DATA["golden"]["cues"])["ok"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_wrong_index_fails(self):
        self.path.write_text(
            self.path.read_text(encoding="utf-8").replace(
                "1\n00:00:00,000", "9\n00:00:00,000"), encoding="utf-8")
        verdict, detail = cs.check_captions_srt(str(self.delivery))
        self.assertEqual(verdict, "FAIL")
        self.assertIn("index", detail)

    def test_missing_text_fails(self):
        self.path.write_text(
            "1\n00:00:00,000 --> 00:00:01,500\n\n", encoding="utf-8")
        self.assertEqual(cs.check_captions_srt(str(self.delivery))[0], "FAIL")

    def test_dot_separator_instead_of_comma_fails(self):
        self.path.write_text(
            self.path.read_text(encoding="utf-8").replace(
                "00:00:01,500", "00:00:01.500"), encoding="utf-8")
        self.assertEqual(cs.check_captions_srt(str(self.delivery))[0], "FAIL")

    def test_zero_byte_file_fails(self):
        self.path.write_bytes(b"")
        self.assertEqual(cs.check_captions_srt(str(self.delivery))[0], "FAIL")


class CliAndNaming(unittest.TestCase):
    """The runbook commands: export from a cues file, check the folder."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="del10-"))
        self.delivery = self.tmp / "delivery"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_numbered_name(self):
        self.assertEqual(cs.srt_file_name(), "10 - Captions.srt")
        self.assertEqual(cs.srt_file_name(3), "03 - Captions.srt")
        with self.assertRaises(ValueError):
            cs.srt_file_name(100)

    def test_cli_export_then_check(self):
        cues_file = self.tmp / "cues.json"
        cues_file.write_text(json.dumps(DATA["golden"]["cues"]),
                             encoding="utf-8")
        self.assertEqual(cs._cli(["export", str(self.delivery),
                                  str(cues_file)]), 0)
        self.assertEqual(cs._cli(["check", str(self.delivery)]), 0)

    def test_cli_check_missing_folder_exits_5(self):
        self.assertEqual(cs._cli(["check", str(self.delivery)]), 5)

    def test_cli_bad_usage_exits_1(self):
        self.assertEqual(cs._cli([]), 1)
        self.assertEqual(cs._cli(["export", str(self.delivery)]), 1)


if __name__ == "__main__":
    unittest.main()
