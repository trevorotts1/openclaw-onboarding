#!/usr/bin/env python3
"""DEL-13 end-to-end: one fixture run through the packaging entry point.

The whole run, for real: package_run discovers each package item's component
(the DEL unit that produces it), writes the 12 canonical numbered files into
one delivery folder, and the test then opens every one of them -- PDF header,
SRT cue structure, media non-empty -- exactly as the client would.

Every DEL-01..DEL-12 component now exports ``produce_delivery(run_dir, item)``
and the ONE naming scheme lives in ``delivery_package.contract`` (``NN -
Label.ext`` per item number), so all twelve items are produced and this test
runs green with no skip. The twelve-item gate stays hard: delivery_checklist
Q12 PACKAGE_COMPLETE fails the run on any missing package item, and the
negative control below proves one missing item fails the folder contract.

Run: python3 delivery_package/test_delivery_package_e2e.py
"""
from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import delivery_package.contract as C           # noqa: E402
import delivery_package.packaging as P          # noqa: E402


class DeliveryPackageEndToEnd(unittest.TestCase):
    """One fixture run -> packaging entry point -> 12 files that open."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="del13-e2e-"))
        cls.run_dir = cls.tmp / "run"
        cls.run_dir.mkdir()
        cls.out = cls.tmp / "delivery"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_01_fixture_run_packages_all_twelve_items_and_they_open(self):
        # the packaging call itself: every component discovered, every item
        # written under its canonical numbered name, folder verified.
        res = P.package_run(self.run_dir, self.out)

        self.assertEqual(len(res["items"]), 12)
        report = C.verify_folder(self.out)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["missing"], [])

        # every one of the 12 package items exists AND opens
        for item in C.PACKAGE_ITEMS:
            for name, kind in zip(item.files, item.kinds):
                path = self.out / name
                with self.subTest(item=item.key, file=name, kind=kind):
                    self.assertTrue(path.exists(), "%s missing" % name)
                    self._opens(path, kind)

    def test_02_every_component_exports_produce_delivery(self):
        # no component is "not landed" any more; all twelve are wired.
        for item in C.PACKAGE_ITEMS:
            fn, note = P.resolve_producer(item)
            self.assertIsNotNone(fn, "%s not wired: %s" % (item.key, note))
            self.assertIn("wired via", note)

    def test_03_negative_control_one_missing_item_fails_the_folder(self):
        # the twelve-item gate is hard: drop one item, the folder must fail
        # and name exactly that item. Mirrors delivery_checklist Q12.
        victim = C.ITEMS_BY_KEY["welcome_sheet"]
        folder = C.write_reference_package(self.tmp / "neg")
        first = folder / victim.files[0]
        first.unlink()
        report = C.verify_folder(folder)
        self.assertFalse(report["ok"])
        self.assertEqual(report["missing"], [victim.key])
        self.assertEqual(report["problems"][0]["file"], victim.files[0])

    def _opens(self, path, kind):
        """Open one delivered file the way the contract defines 'opens'."""
        if kind.startswith("images"):
            self.assertTrue(path.is_dir(), "%s is not a directory" % path.name)
            images = [p for p in path.rglob("*")
                      if p.is_file()
                      and p.suffix.lower() in C.IMAGE_SUFFIXES]
            self.assertGreaterEqual(len(images), C.MIN_IMAGES, path.name)
            for image in images:
                self.assertGreater(image.stat().st_size, 0, image.name)
            return
        self.assertTrue(path.is_file(), "%s is not a file" % path.name)
        self.assertGreater(path.stat().st_size, 0, "%s is empty" % path.name)
        if kind == "pdf":
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(5), b"%PDF-",
                                 "%s has no PDF header" % path.name)
        elif kind == "srt":
            text = path.read_text(encoding="utf-8")
            self.assertRegex(
                text, r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}",
                "%s has no cue timing line" % path.name)
            self.assertRegex(text, r"(?m)^\d+\s*$",
                             "%s has no cue index line" % path.name)


class DeliveryNamesAgree(unittest.TestCase):
    """ONE scheme: every producer's native delivery name IS the contract's.

    The packaging adapters stage canonical names, but a real run also writes
    through each producer's own path (its CLI / deliver() entry). Those two
    paths must name a file the same way, or a real delivery folder fails the
    Q12 gate that the packaging test just proved green. This is the drift
    guard: it pins each producer's constant to the contract, so a rename in
    one place cannot land without the other.
    """

    def _module(self, dotted):
        return importlib.import_module(dotted)

    def test_single_file_items_use_the_contract_name(self):
        # producers whose item is exactly one file, named by a module constant
        for key, attr, dotted in (
                ("character_bible", "DELIVERY_PDF_NAME",
                 "character_bible.character_bible"),
                ("storyboard_pdf", "DELIVERY_NAME",
                 "storyboard_grid.storyboard_grid"),
                ("ready_to_post_kit", "PDF_NAME",
                 "ready_post_kit.ready_post_kit"),
                ("lyric_sheet", "FILE_NAME", "lyric_sheet.lyric_sheet"),
                ("welcome_sheet", "WELCOME_SHEET_FILE",
                 "delivery_package.package_items")):
            with self.subTest(item=key, module=dotted):
                expected = C.ITEMS_BY_KEY[key].files[0]
                self.assertEqual(getattr(self._module(dotted), attr),
                                 expected)

    def test_multi_file_items_use_the_contract_names(self):
        # audio versions: every file shares the ITEM number, told apart by
        # label -- never a second numbering of their own.
        from delivery_variants import song_files as sf
        audio = C.ITEMS_BY_KEY["audio_versions"]
        self.assertEqual(sf.VERSION_NOTE_NAME, audio.files[3])
        self.assertEqual([name for _k, _l, name in sf.expected_version_files()],
                         list(audio.files[:3]))
        for name in sf.expected_version_files():
            self.assertTrue(name[2].startswith(sf.ITEM_NUMBER + " - "))

        # the two videos and the two clips share their item number too.
        from delivery_variants import video_delivery as vd
        video = C.ITEMS_BY_KEY["video"]
        self.assertEqual(vd.captioned_name("Any Ad"), video.files[0])
        self.assertEqual(vd.clean_name("Any Ad"), video.files[1])

        from delivery_clips import delivery_clips as dc
        clips = C.ITEMS_BY_KEY["clips"]
        self.assertEqual(dc.clip_file_name(60), clips.files[0])
        self.assertEqual(dc.clip_file_name(90), clips.files[1])

    def test_directory_items_deliver_into_the_contract_directory(self):
        from delivery_variants import cover_image as ci
        self.assertEqual(ci.cover_file_name("Any Ad"),
                         C.ITEMS_BY_KEY["cover_thumbnail"].files[0])
        from character_images import character_images as cimg
        self.assertEqual(cimg.DELIVERY_DIR_NAME,
                         C.ITEMS_BY_KEY["character_images"].files[0])

    def test_caption_and_script_names_are_the_contract_names(self):
        from delivery_variants import caption_srt as cs
        self.assertEqual(cs.srt_file_name(),
                         C.ITEMS_BY_KEY["captions_srt"].files[0])
        from script_pdf import script_pdf as sp
        self.assertEqual(sp.PDF_NAME, C.ITEMS_BY_KEY["script_pdf"].files[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
