#!/usr/bin/env python3
"""DEL-12 tests: the canonical package list and the one-page welcome sheet.

Done-when (Trevor order 2026-10-09 08:50):
  1. the shared constant names exactly 12 package items, numbered 01..12,
     every file name unique and prefixed with its own item number;
  2. the welcome sheet is a real one-page PDF that lists every one of those
     files with its number and what it is for;
  3. nothing the client reads is under 12 pt, and it carries no client name,
     no model or tool name, no price and no income claim;
  4. building twice produces identical bytes (no timestamps, no randomness);
  5. delivery_checklist consumes THIS constant -- same object, not a copy --
     and reports a missing package file from a real folder.

Run: python3 scripts/core/delivery_package/test_welcome_sheet_del12.py
stdlib only, no network, no spend, no absolute operator path.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parent                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import delivery_package.package_items as pi          # noqa: E402
import delivery_package.welcome_sheet as ws          # noqa: E402
import delivery_checklist.delivery_checklist as dc   # noqa: E402

#: Words a client-facing page may never carry: tool, model, provider names.
FORBIDDEN_TOOL = re.compile(
    r"\b(kie|suno|kling|minimax|openrouter|ollama|anthropic|claude|gpt|"
    r"openai|whisper|ffmpeg|ffprobe|gemini|deepseek|qwen|moonshot|"
    r"mistral|copilot|python|docker)\b", re.I)
#: Money and income promises are never written to a client.
FORBIDDEN_MONEY = re.compile(
    r"\b(guaranteed|guarantee|profit|profits|revenue|income|earnings?|"
    r"roi|dollars?|pricing|price)\b", re.I)


def pdf_strings(data):
    """Every text-showing string of the content stream, escapes resolved."""
    s = data.decode("latin-1")
    return [re.sub(r"\\(.)", r"\1", m.group(1))
            for m in re.finditer(r"\(((?:\\.|[^\\()])*)\)\s*Tj", s)]


class PackageListTest(unittest.TestCase):
    def test_twelve_items_numbered_in_order(self):
        numbers = [it["number"] for it in pi.PACKAGE_ITEMS]
        self.assertEqual(numbers, list(range(1, 13)))
        self.assertEqual(pi.PACKAGE_ITEM_COUNT, 12)
        self.assertEqual(len(set(it["key"] for it in pi.PACKAGE_ITEMS)), 12)

    def test_every_file_is_unique_and_carries_its_item_number(self):
        flat = []
        for item in pi.PACKAGE_ITEMS:
            prefix = "%02d - " % item["number"]
            self.assertTrue(item["files"], "item %d has no file" % item["number"])
            for name in item["files"]:
                self.assertTrue(name.startswith(prefix),
                                "%s does not start with %s" % (name, prefix))
                self.assertNotIn(name, flat, "duplicate file name %s" % name)
                flat.append(name)
        self.assertEqual(list(pi.PACKAGE_FILES), flat)
        self.assertEqual(len(set(flat)), len(flat))

    def test_welcome_sheet_is_item_twelve(self):
        self.assertEqual(pi.WELCOME_SHEET_FILE, "12 - Welcome Sheet.pdf")
        self.assertEqual(pi.files_for(12), (pi.WELCOME_SHEET_FILE,))
        self.assertEqual(pi.files_for(99), ())
        self.assertEqual(pi.DELIVERY_FOLDER, "delivery")

    def test_client_copy_is_clean_ascii_and_short_enough(self):
        for item in pi.PACKAGE_ITEMS:
            what = item["what"]
            self.assertTrue(what.isascii(), "non-ASCII copy: %r" % what)
            for rx, why in ((FORBIDDEN_TOOL, "tool/model name"),
                            (FORBIDDEN_MONEY, "money/income")):
                self.assertIsNone(rx.search(what),
                                  "%s in item %d: %r" % (why, item["number"], what))
            self.assertNotIn("$", what)
            # one line on the sheet -- the page stays a single page
            lines = ws.wrap(what, ws.TEXT_W, ws.BODY_SIZE)
            self.assertEqual(len(lines), 1,
                             "item %d description wraps: %r" % (item["number"], what))


class WelcomeSheetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="del12-")
        cls.path = Path(cls.tmp.name) / pi.WELCOME_SHEET_FILE
        cls.info = ws.build_welcome_sheet(cls.path)
        cls.data = cls.path.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_is_a_real_pdf_with_one_page(self):
        self.assertTrue(self.data.startswith(b"%PDF-1.4"))
        self.assertTrue(self.data.rstrip().endswith(b"%%EOF"))
        self.assertIn(b"/Count 1", self.data)
        self.assertEqual(len(re.findall(rb"/Type /Page[^s]", self.data)), 1)
        self.assertIn(b"xref", self.data)
        self.assertEqual(self.info["pages"], 1)
        self.assertEqual(self.info["items"], 12)
        self.assertEqual(self.info["files"], len(pi.PACKAGE_FILES))
        self.assertGreater(self.info["bytes"], 1500)

    def test_lists_every_canonical_file_and_every_number(self):
        text = "\n".join(pdf_strings(self.data))
        for name in pi.PACKAGE_FILES:
            self.assertIn(name, text, "sheet does not list %s" % name)
        for item in pi.PACKAGE_ITEMS:
            self.assertIn("%02d" % item["number"], text)

    def test_nothing_type_set_below_the_twelve_point_floor(self):
        sizes = [float(s) for s in re.findall(r"/F\d+ ([0-9.]+) Tf",
                                              self.data.decode("latin-1"))]
        self.assertTrue(sizes, "no type found in the content stream")
        self.assertGreaterEqual(min(sizes), pi.MIN_PDF_POINT_SIZE,
                                "type below %s pt: %s"
                                % (pi.MIN_PDF_POINT_SIZE, sorted(set(sizes))))
        self.assertGreaterEqual(pi.MIN_PDF_POINT_SIZE, 12)

    def test_client_facing_text_carries_no_forbidden_word(self):
        text = "\n".join(pdf_strings(self.data))
        self.assertTrue(text.isascii())
        for rx, why in ((FORBIDDEN_TOOL, "tool/model name"),
                        (FORBIDDEN_MONEY, "money/income")):
            hit = rx.search(text)
            self.assertIsNone(hit, "%s on the sheet: %r" % (why, hit and hit.group(0)))
        self.assertNotIn("$", text)
        self.assertTrue(text.strip(), "the sheet is blank")

    def test_build_is_deterministic(self):
        again = ws.pdf_bytes()
        self.assertEqual(again, self.data)
        self.assertEqual(len(pdf_strings(again)), len(pdf_strings(self.data)))


class DeliveryChecklistConsumesConstantTest(unittest.TestCase):
    def test_checklist_imports_the_same_objects(self):
        self.assertIs(dc.PACKAGE_ITEMS, pi.PACKAGE_ITEMS)
        self.assertIs(dc.PACKAGE_FILES, pi.PACKAGE_FILES)
        self.assertEqual(dc.PACKAGE_ITEM_COUNT, pi.PACKAGE_ITEM_COUNT)
        self.assertEqual(dc.WELCOME_SHEET_FILE, pi.WELCOME_SHEET_FILE)

    def test_missing_package_files_reads_a_real_folder(self):
        with tempfile.TemporaryDirectory(prefix="del12-") as td:
            root = Path(td)
            self.assertEqual(dc.missing_package_files(root), pi.PACKAGE_FILES)
            for name in pi.PACKAGE_FILES:
                (root / name).write_bytes(b"x")
            self.assertEqual(dc.missing_package_files(root), ())
            (root / "05 - Video Clean.mp4").write_bytes(b"")   # empty = missing
            (root / "10 - Captions.srt").unlink()
            missing = dc.missing_package_files(root)
            self.assertEqual(missing,
                             ("05 - Video Clean.mp4", "10 - Captions.srt"))
            self.assertEqual(dc.missing_package_files(root / "no-such-dir"),
                             pi.PACKAGE_FILES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
