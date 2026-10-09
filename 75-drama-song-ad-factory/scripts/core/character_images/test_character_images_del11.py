#!/usr/bin/env python3
"""DEL-11: character pictures delivered as separate full-resolution files.

Done-when cases:
  1. a saved character's four views (close-up, side profile, three-quarter,
     full standing) land in the delivery folder as four separate files with
     clear numbered names, byte-for-byte identical to the approved source
     (full resolution: a copy, never a re-encode);
  2. view words in the reference file names pick the right picture, one
     file never claims two views;
  3. an explicit ``views`` mapping on the record wins over file names;
  4. a missing view FAILS naming exactly the missing views, and the plan is
     computed before any write -- the delivery folder is left untouched;
  5. the CLI delivers from a records file and from a saved character, and
     refuses bad input with a non-zero exit.

Run: python3 core/character_images/test_character_images_del11.py
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                  # scripts/core
from character_images import character_images as CI  # noqa: E402
from character_library import character_library as CL  # noqa: E402

SCRIPT = os.path.join(HERE, "character_images.py")
VIEWS = CI.VIEWS
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def png_bytes(salt, size=32):
    """A real, openable PNG; each salt gets its own color (distinct bytes)."""
    h = zlib.crc32(salt if isinstance(salt, bytes) else str(salt).encode())
    color = (h & 0xFF, (h >> 8) & 0xFF, (h >> 16) & 0xFF)
    raw = b"".join(b"\x00" + bytes(color) * size for _ in range(size))
    return (PNG_MAGIC
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, 9))
            + _chunk(b"IEND", b""))


def make_pic(path, salt=b""):
    with open(path, "wb") as f:
        f.write(png_bytes(salt))
    return path


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


class CharacterImagesDel11(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.client = os.path.join(self.tmp, "client")
        self.delivery = os.path.join(self.tmp, "delivery")
        self.src = os.path.join(self.tmp, "src")
        os.makedirs(self.src)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _saved(self, name, files):
        paths = [make_pic(os.path.join(self.src, n), n.encode())
                 for n in files]
        CL.save_character(self.client, name, "Generic fixture character.",
                          paths)
        return CL.get_character(self.client, name)

    # ---------------------------------------------------------------- 1
    def test_four_separate_full_resolution_files(self):
        rec = self._saved("Hero One", ["close-up.png", "side-profile.png",
                                       "three-quarter.png",
                                       "full-standing.png"])
        rows = CI.copy_character_images(self.delivery, [rec])
        names = sorted(os.listdir(self.delivery))
        self.assertEqual(names, [
            "11-character-hero-one-close-up.png",
            "11-character-hero-one-full-standing.png",
            "11-character-hero-one-side-profile.png",
            "11-character-hero-one-three-quarter.png"])
        # every delivered file is the approved picture, byte for byte
        for row in rows:
            dest = os.path.join(self.delivery, row["filename"])
            with open(dest, "rb") as f:
                got = f.read()
            src = next(p for p in rec["reference_paths"]
                       if os.path.basename(p) == row["source"])
            with open(src, "rb") as f:
                want = f.read()
            self.assertEqual(got, want)              # full resolution: the
            self.assertEqual(len(got), len(want))     # copy IS the original
            self.assertEqual(row["bytes"], os.path.getsize(dest))
            self.assertEqual(row["source"], os.path.basename(src))
            self.assertNotIn(os.sep, row["source"])   # receipt carries a name,
            self.assertFalse(os.path.isabs(row["source"]))  # never a path
        self.assertEqual([r["view"] for r in rows], list(VIEWS))
        self.assertEqual(rows[0]["character"], "Hero One")
        # four separate files, not one bundle
        self.assertEqual(len(names), 4)
        self.assertEqual(len({read_bytes(os.path.join(self.delivery, n))
                              for n in names}), 4)   # four distinct pictures
        # every delivered file still OPENS as a picture (a copy of a valid
        # PNG is a valid PNG; a re-encode that broke it would fail here)
        for n in names:
            blob = read_bytes(os.path.join(self.delivery, n))
            self.assertTrue(blob.startswith(PNG_MAGIC), n)
            self.assertTrue(blob.endswith(_chunk(b"IEND", b"")), n)
        if shutil.which("sips"):                     # macOS opener, when present
            r = subprocess.run(["sips", "-g", "pixelWidth",
                                os.path.join(self.delivery, names[0])],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("pixelWidth: 32", r.stdout)

    # ---------------------------------------------------------------- 2
    def test_two_characters_deliver_eight_files(self):
        a = self._saved("Hero One", ["close-up.png", "side-profile.png",
                                     "three-quarter.png", "full-standing.png"])
        b = self._saved("Hero Two", ["close-up.png", "side-profile.png",
                                     "three-quarter.png", "full-standing.png"])
        rows = CI.copy_character_images(self.delivery, [a, b])
        self.assertEqual(len(rows), 8)
        self.assertEqual(len(os.listdir(self.delivery)), 8)
        self.assertEqual(
            sum(1 for n in os.listdir(self.delivery) if n.startswith("11-character-hero-two-")),
            4)

    # ---------------------------------------------------------------- 3
    def test_view_words_in_file_names_pick_the_picture(self):
        rec = self._saved("Alias Hero", ["4-lipsync-closeup.png", "2-side.png",
                                         "3-three-quarter.png",
                                         "1-standing.png"])
        found = CI.view_sources(rec)
        self.assertEqual(set(found), set(VIEWS))
        self.assertTrue(found["close-up"].endswith("4-lipsync-closeup.png"))
        self.assertTrue(found["side-profile"].endswith("2-side.png"))
        self.assertTrue(found["three-quarter"].endswith("3-three-quarter.png"))
        self.assertTrue(found["full-standing"].endswith("1-standing.png"))
        # whole words only: "outside" can never claim the side profile
        rec2 = self._saved("Word Hero", ["outside.png", "close-up.png",
                                         "three-quarter.png", "standing.png"])
        found2 = CI.view_sources(rec2)
        self.assertNotIn("side-profile", found2)
        self.assertEqual(found2.get("full-standing"),
                         rec2["reference_paths"][3])

    # ---------------------------------------------------------------- 3b
    def test_one_file_never_claims_two_views(self):
        rec = self._saved("Greedy Hero", ["close-up-side.png"])
        found = CI.view_sources(rec)
        self.assertEqual(list(found), ["close-up"])     # first view wins it
        with self.assertRaises(CI.CharacterImagesError) as cm:
            CI.copy_character_images(self.delivery, [rec])
        self.assertEqual(cm.exception.code, "VIEW_MISSING")
        self.assertIn("side-profile", str(cm.exception))
        self.assertIn("three-quarter", str(cm.exception))
        self.assertIn("full-standing", str(cm.exception))

    # ---------------------------------------------------------------- 4
    def test_explicit_views_mapping_wins_over_file_names(self):
        pics = {v: make_pic(os.path.join(self.src, "shot-%s.png" % v),
                            v.encode())
                for v in VIEWS}
        rec = {"name": "Mapped Hero",
               "views": {"close-up": pics["close-up"],
                         "side profile": pics["side-profile"],
                         "three-quarter": pics["three-quarter"],
                         "full-standing": pics["full-standing"]}}
        rows = CI.copy_character_images(self.delivery, [rec])
        self.assertEqual([r["view"] for r in rows], list(VIEWS))
        for row in rows:
            with open(os.path.join(self.delivery, row["filename"]), "rb") as f:
                got = f.read()
            with open(pics[row["view"]], "rb") as f:
                self.assertEqual(got, f.read())

    # ---------------------------------------------------------------- 4b
    def test_missing_view_fails_closed_before_any_write(self):
        rec = self._saved("Half Hero", ["close-up.png", "side-profile.png"])
        with self.assertRaises(CI.CharacterImagesError) as cm:
            CI.copy_character_images(self.delivery, [rec])
        self.assertEqual(cm.exception.code, "VIEW_MISSING")
        self.assertIn("three-quarter", str(cm.exception))
        self.assertIn("full-standing", str(cm.exception))
        self.assertNotIn("close-up has no", str(cm.exception))
        self.assertFalse(os.path.exists(self.delivery))   # plan runs first

    def test_no_characters_refused(self):
        with self.assertRaises(CI.CharacterImagesError) as cm:
            CI.copy_character_images(self.delivery, [])
        self.assertEqual(cm.exception.code, "NO_CHARACTERS")
        self.assertFalse(os.path.exists(self.delivery))

    def test_missing_source_file_refused(self):
        rec = self._saved("Gone Hero", ["close-up.png", "side-profile.png",
                                        "three-quarter.png",
                                        "full-standing.png"])
        os.remove(rec["reference_paths"][0])
        with self.assertRaises(CI.CharacterImagesError) as cm:
            CI.plan_copies([rec])
        self.assertEqual(cm.exception.code, "SOURCE_MISSING")
        self.assertIn("close-up", str(cm.exception))

    def test_non_picture_refused(self):
        bad = os.path.join(self.src, "notes.txt")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("not a picture")
        rec = {"name": "Text Hero", "reference_paths": [bad] * 4}
        with self.assertRaises(CI.CharacterImagesError) as cm:
            CI.plan_copies([rec])
        self.assertEqual(cm.exception.code, "VIEW_MISSING")   # no view words

    def test_bad_extension_refused(self):
        rec = {"name": "Bad Hero", "views": {
            v: make_pic(os.path.join(self.src, "%s.dat" % v), v.encode())
            for v in VIEWS}}
        with self.assertRaises(CI.CharacterImagesError) as cm:
            CI.plan_copies([rec])
        self.assertEqual(cm.exception.code, "BAD_IMAGE")
        self.assertIn("png", str(cm.exception))

    def test_duplicate_slug_refused(self):
        rec = {"name": "Dup Hero", "views": {
            v: make_pic(os.path.join(self.src, "%s.png" % v), v.encode())
            for v in VIEWS}}
        with self.assertRaises(CI.CharacterImagesError) as cm:
            CI.plan_copies([rec, dict(rec)])
        self.assertEqual(cm.exception.code, "DUPLICATE_SLUG")

    # ---------------------------------------------------------------- 5
    def test_cli_from_records_file(self):
        rec = self._saved("Cli Hero", ["close-up.png", "side-profile.png",
                                       "three-quarter.png",
                                       "full-standing.png"])
        records = os.path.join(self.tmp, "records.json")
        with open(records, "w", encoding="utf-8") as f:
            json.dump([rec], f)
        r = subprocess.run(
            [sys.executable, SCRIPT, "--delivery-dir", self.delivery,
             "--records", records],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["count"], 4)
        self.assertEqual(out["schema"], CI.SCHEMA)
        self.assertEqual(len(os.listdir(self.delivery)), 4)

        # bad input: a records file that is not a list
        with open(records, "w", encoding="utf-8") as f:
            json.dump({"name": "not a list"}, f)
        r3 = subprocess.run(
            [sys.executable, SCRIPT, "--delivery-dir", self.delivery,
             "--records", records],
            capture_output=True, text=True)
        self.assertEqual(r3.returncode, 1)
        self.assertIn("BAD_RECORDS", r3.stderr)
        # no arguments at all
        r4 = subprocess.run([sys.executable, SCRIPT, "--delivery-dir",
                             self.delivery], capture_output=True, text=True)
        self.assertEqual(r4.returncode, 1)
        self.assertIn("BAD_INPUT", r4.stderr)

    def test_cli_from_saved_character(self):
        self._saved("Saved Hero", ["close-up.png", "side-profile.png",
                                   "three-quarter.png", "full-standing.png"])
        r = subprocess.run(
            [sys.executable, SCRIPT, "--delivery-dir", self.delivery,
             "--client-dir", self.client, "--name", "Saved Hero"],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["count"], 4)
        r2 = subprocess.run(
            [sys.executable, SCRIPT, "--delivery-dir", self.delivery,
             "--client-dir", self.client, "--name", "Nobody"],
            capture_output=True, text=True)
        self.assertEqual(r2.returncode, 1)
        self.assertIn("BAD_RECORD", r2.stderr)

    def test_recopies_are_idempotent(self):
        rec = self._saved("Twice Hero", ["close-up.png", "side-profile.png",
                                         "three-quarter.png",
                                         "full-standing.png"])
        first = CI.copy_character_images(self.delivery, [rec])
        second = CI.copy_character_images(self.delivery, [rec])
        self.assertEqual([r["filename"] for r in first],
                         [r["filename"] for r in second])
        self.assertEqual(sorted(os.listdir(self.delivery)),
                         sorted(r["filename"] for r in second))


if __name__ == "__main__":
    unittest.main()
