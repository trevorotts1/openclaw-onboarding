"""DEL-09: the lyric sheet PDF. Run:
python3 scripts/core/lyric_sheet/test_lyric_sheet.py   (from the skill folder)
or pytest scripts/core/lyric_sheet/test_lyric_sheet.py. stdlib only."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lyric_sheet import lyric_sheet as LS  # noqa: E402

#: a generic fixture: no client name, no offer, no money
SCRIPT = {
    "title": "Morning Light",
    "sheet": [
        {"tag": "Intro", "lines": ["Wake up, the morning is mine"]},
        {"tag": "Verse 1", "lines": ["I used to rush through the day",
                                     "Now I start it slow and steady"]},
        {"tag": "Chorus", "lines": ["One small step, then another",
                                    "That is how the morning lights up"]},
        {"tag": "Spoken Word", "lines": ["Take sixty seconds and breathe"]},
        {"tag": "Instrumental", "lines": []},
        {"tag": "Outro", "lines": ["Start tomorrow, start today"]},
    ],
}


def _tj_strings(pdf_bytes):
    """Every literal string the file draws, unescaped, in draw order."""
    out = []
    for raw in re.findall(rb"\((?:\\.|[^()\\])*\) Tj", pdf_bytes):
        body = raw[1:raw.rindex(b")")]
        out.append(body.decode("latin-1")
                   .replace("\\(", "(").replace("\\)", ")")
                   .replace("\\\\", "\\"))
    return out


def _sizes(pdf_bytes):
    return [float(s) for s in
            re.findall(rb"/F\d+ (\d+(?:\.\d+)?) Tf", pdf_bytes)]


class LyricSheetTest(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp(prefix="del09-"))
        self.out = self.t / LS.FILE_NAME

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def build(self, script=None):
        return LS.build_pdf(SCRIPT if script is None else script, self.out)

    def data(self):
        return self.out.read_bytes()

    # ---- the file ------------------------------------------------------
    def test_module_carries_the_numbered_package_name(self):
        self.assertEqual(LS.SLOT, "09")
        self.assertEqual(LS.FILE_NAME, "09 - Lyric Sheet.pdf")
        self.assertTrue(LS.FILE_NAME.endswith(".pdf"))
        self.assertGreaterEqual(LS.MIN_PT, 12.0)

    def test_build_writes_a_parseable_pdf(self):
        receipt = self.build()
        data = self.data()
        self.assertTrue(data.startswith(b"%PDF-1.4"))
        self.assertTrue(data.rstrip().endswith(b"%%EOF"))
        startxref = int(data.rsplit(b"startxref", 1)[1].split()[0])
        self.assertEqual(data[startxref:startxref + 4], b"xref")
        self.assertGreater(receipt["bytes"], 512)
        self.assertEqual(receipt["name"], "09 - Lyric Sheet.pdf")
        self.assertEqual(receipt["sections"], 6)

    def test_same_approved_sheet_renders_byte_for_byte_same(self):
        first = self.build()
        a = self.out.read_bytes()
        second = self.build()
        b = self.out.read_bytes()
        self.assertEqual(a, b)
        self.assertEqual(first["bytes"], second["bytes"])

    def test_nothing_on_the_page_is_under_12_point(self):
        self.build()
        sizes = _sizes(self.data())
        self.assertTrue(sizes, "no type on the page")
        self.assertGreaterEqual(min(sizes), LS.MIN_PT)
        self.assertIn(13.0, sizes)          # lyric lines are readable, not tiny

    def test_page_is_white_no_full_page_fill(self):
        self.build()
        # the bright page is the paper itself: the module draws type and
        # rules only, never a painted rectangle
        self.assertNotRegex(self.data().decode("latin-1"), r"\d+ \d+ \d+ re f")

    # ---- the song's own structure --------------------------------------
    def test_section_breaks_match_the_song_structure(self):
        receipt = self.build()
        strings = _tj_strings(self.data())
        headings = [s for s in strings
                    if s in ("Intro", "Verse 1", "Chorus", "Spoken Word",
                             "Instrumental", "Outro")]
        self.assertEqual(headings, ["Intro", "Verse 1", "Chorus", "Spoken Word",
                                    "Instrumental", "Outro"])
        self.assertEqual(receipt["sections"], len(SCRIPT["sheet"]))

    def test_approved_words_and_title_are_printed_verbatim(self):
        self.build()
        drawn = "\n".join(_tj_strings(self.data()))
        self.assertIn("Morning Light", drawn)
        for block in SCRIPT["sheet"]:
            for line in block["lines"]:
                self.assertIn(line, drawn)
        self.assertIn(LS.EYEBROW, drawn)
        self.assertIn(LS.SUBTITLE, drawn)

    def test_instrumental_section_says_it_has_no_words(self):
        self.build()
        self.assertIn(LS.INSTRUMENTAL_NOTE, "\n".join(_tj_strings(self.data())))

    def test_long_sheet_paginates_with_a_footer_on_every_page(self):
        lines = ["Line %d of the long approved song" % i for i in range(80)]
        script = {"title": "Long One",
                  "sheet": [{"tag": "Verse", "lines": lines}]}
        receipt = LS.build_pdf(script, self.out)
        data = self.data()
        self.assertGreaterEqual(receipt["pages"], 3)
        drawn = "\n".join(_tj_strings(data))
        self.assertEqual(drawn.count("page "), receipt["pages"])
        self.assertIn("page 1 of %d" % receipt["pages"], drawn)
        self.assertIn("page %d of %d" % (receipt["pages"], receipt["pages"]),
                      drawn)
        self.assertGreaterEqual(min(_sizes(data)), LS.MIN_PT)

    def test_lyrics_only_script_uses_the_shared_sheet_parser(self):
        script = {"title": "Only Words",
                  "lyrics": "[Chorus]\nSing the one line\n[Verse]\nThen this\n"}
        receipt = LS.build_pdf(script, self.out)
        drawn = "\n".join(_tj_strings(self.data()))
        self.assertEqual(receipt["sections"], 2)
        self.assertIn("Chorus", drawn)
        self.assertIn("Verse", drawn)
        self.assertIn("Sing the one line", drawn)

    # ---- layout maths ---------------------------------------------------
    def test_wrap_never_exceeds_the_column(self):
        long_line = ("a " * 200).strip()
        for font in ("F1", "F2", "F3"):
            for line in LS.wrap(long_line, 13.0, LS.CONTENT_W, font):
                self.assertLessEqual(LS.text_width(line, 13.0, font),
                                     LS.CONTENT_W)
        no_spaces = "x" * 400
        for line in LS.wrap(no_spaces, 13.0, LS.CONTENT_W, "F1"):
            self.assertLessEqual(LS.text_width(line, 13.0, "F1"),
                                 LS.CONTENT_W)

    def test_bright_palette_and_no_money_on_chrome(self):
        for color in (LS.INK, LS.ACCENT, LS.ACCENT_INK, LS.MUTED, LS.RULE):
            for channel in color:
                self.assertGreaterEqual(channel, 0.05)   # never muddy black-blue
                self.assertLessEqual(channel, 1.0)
        LS._chrome_clean([LS.EYEBROW, LS.SUBTITLE, LS.INSTRUMENTAL_NOTE])
        with self.assertRaises(LS.LyricSheetError) as ctx:
            LS._chrome_clean(["only $9 today"])
        self.assertEqual(ctx.exception.code, "MONEY_ON_PAGE")

    # ---- the page law ---------------------------------------------------
    def test_tool_name_reaching_the_page_is_refused(self):
        script = {"title": "Made with Suno", "sheet": SCRIPT["sheet"]}
        with self.assertRaises(LS.LyricSheetError) as ctx:
            LS.build_pdf(script, self.out)
        self.assertEqual(ctx.exception.code, "TOOL_NAME_ON_PAGE")

    # ---- fail closed -----------------------------------------------------
    def test_missing_or_empty_approved_script_refuses(self):
        with self.assertRaises(LS.LyricSheetError) as ctx:
            LS.load_script(str(self.t))
        self.assertEqual(ctx.exception.code, "SCRIPT_MISSING")
        for bad in ({}, {"title": "x", "sheet": []},
                    {"title": "x", "sheet": [{"tag": "a", "lines": []}]},
                    {"title": "x", "lyrics": "   "}):
            with self.assertRaises(LS.LyricSheetError) as ctx:
                LS.sections_of(bad)
            self.assertEqual(ctx.exception.code, "EMPTY_SHEET",
                              "accepted %r" % (bad,))
        with self.assertRaises(LS.LyricSheetError) as ctx:
            LS.sections_of("not an object")
        self.assertEqual(ctx.exception.code, "SCRIPT_UNREADABLE")

    def test_type_under_the_floor_never_draws(self):
        canvas = LS._Canvas()
        with self.assertRaises(LS.LyricSheetError) as ctx:
            canvas.text("small", "F1", 9.0, LS.INK, 11.0)
        self.assertEqual(ctx.exception.code, "BELOW_MIN_PT")

    # ---- the delivery folder -------------------------------------------
    def test_write_delivery_lands_the_numbered_file(self):
        run = self.t / "run"
        (run / "creative").mkdir(parents=True)
        (run / "creative" / "script.json").write_text(
            json.dumps(SCRIPT), encoding="utf-8")
        receipt = LS.write_delivery(str(run))
        landed = run / "delivery" / "09 - Lyric Sheet.pdf"
        self.assertTrue(landed.is_file(), landed)
        self.assertEqual(os.path.abspath(receipt["file"]),
                         os.path.abspath(str(landed)))
        self.assertEqual(os.path.basename(receipt["file"]),
                         "09 - Lyric Sheet.pdf")
        self.assertTrue(landed.read_bytes().startswith(b"%PDF-1.4"))
        self.assertEqual(receipt["outcome"] if "outcome" in receipt else "ok",
                         "ok")

    def test_cli_exit_codes_and_receipt(self):
        missing = LS.main(["--run", str(self.t / "nope")])
        self.assertEqual(missing, 1)
        run = self.t / "run2"
        (run / "creative").mkdir(parents=True)
        (run / "creative" / "script.json").write_text(
            json.dumps(SCRIPT), encoding="utf-8")
        self.assertEqual(LS.main(["--run", str(run)]), 0)
        self.assertTrue((run / "delivery" / "09 - Lyric Sheet.pdf").is_file())


if __name__ == "__main__":
    unittest.main()
