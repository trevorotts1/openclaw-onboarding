#!/usr/bin/env python3
"""U-L01: an extension-less reference picture is copied as ``.png``.

Run: python3 test_character_bible_l01.py  (or under unittest/pytest)

Audit rows C07 / F7 (leftover): the two ensemble copy loops read
``view + os.path.splitext(src)[1].lower() or ".png"``, which binds as
``(view + ext) or ".png"`` -- a truthy view name swallowed the fallback, so
a picture with no file extension was copied with no extension either. Both
now read ``view + (ext or ".png")``.
"""
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, os.path.join(CORE, "character_bible")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from character_bible import character_bible as CB  # noqa: E402
from character_bible import character_approval as CA  # noqa: E402
from choice_card.intake_card import delivery_outbox as DO  # noqa: E402
from delivery_package import contract as DC  # noqa: E402

ITEM = DC.ITEMS_BY_KEY["character_bible"]

#: Generic fixture character. Never a client.
FIXTURE = {
    "character_name": "Sample Character",
    "character_description": ("A warm, practical person in their late thirties "
                              "who shows up early and helps the neighbours."),
    "character_background": ("Grew up in a small coastal town, ran the family "
                             "shop for twelve years, and learned to fix "
                             "everything twice."),
    "character_ethnicity": ("Medium-brown skin, tight coily hair kept short, a "
                            "broad easy smile, about five foot eight."),
    "character_voice_notes": "Low, unhurried, warm.",
}


def _png(path, w=48, h=72, rgb=(180, 60, 60)):
    """Write real PNG bytes at ``path`` EXACTLY as given (no extension added)."""
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n"
                 + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw))
                 + chunk(b"IEND", b""))
    return path


def _same_bytes(test, left, right):
    with open(left, "rb") as a, open(right, "rb") as b:
        test.assertEqual(a.read(), b.read(), (left, right))


class ExtensionlessPictureCopied(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="s75ul01-name-")

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def _images(self, prefix, rgb):
        return {view: _png(os.path.join(self.t, "%s-%s" % (prefix, view)),
                           rgb=rgb)
                for view in CB.IMAGE_VIEWS}

    def test_ensemble_delivery_names_an_extensionless_picture_png(self):
        imgs = self._images("alpha", (60, 120, 180))
        for path in imgs.values():
            self.assertEqual(os.path.splitext(path)[1], "")
        out = os.path.join(self.t, "delivery")
        CB.write_ensemble_delivery(out, [{
            "slug": "alpha", "record": CB.record(FIXTURE), "images": imgs}])
        img_dir = os.path.join(out, ITEM.files[1])
        self.assertEqual(sorted(os.listdir(os.path.join(img_dir, "alpha"))),
                         sorted(view + ".png" for view in CB.IMAGE_VIEWS))
        for view in CB.IMAGE_VIEWS:
            _same_bytes(self, os.path.join(img_dir, "alpha", view + ".png"),
                        imgs[view])

    def test_approved_ensemble_delivery_names_an_extensionless_picture_png(self):
        run = os.path.join(self.t, "run")
        os.makedirs(os.path.join(run, "character"))
        entries = []
        for n, name in enumerate(("Alpha Person", "Bravo Person")):
            entries.append({
                "name": name,
                "role": "protagonist" if n == 0 else "foil",
                "slug": name.split()[0].lower(),
                "background": FIXTURE["character_background"],
                "appearance": FIXTURE["character_ethnicity"],
                "voice_notes": FIXTURE["character_voice_notes"],
                "images": self._images(name.split()[0].lower(),
                                       (40 + 70 * n, 30 * n + 20, 90)),
            })
        DO.save_origin(run, DO.origin_record(
            tenant_id="tenant-9", account_id="bot-9", channel="app",
            conversation_id="conv-9", thread_id="thread-9"))
        CA.save_bible(run, CA.bible_from_entries(entries))
        CA.present(run, run_id="run-9")
        self.assertEqual(CA.approve(run, "approve", approved_by="client-9",
                                    run_id="run-9")["status"], CA.APPROVED)
        os.makedirs(os.path.join(run, "audio"))
        with open(os.path.join(run, "audio", "timing.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"measured": True}, fh)
        staged = CB.produce_delivery(run, ITEM)
        img_dir = os.path.join(os.path.dirname(str(staged[0])), ITEM.files[1])
        for entry in entries:
            slug_dir = os.path.join(img_dir, entry["slug"])
            self.assertEqual(sorted(os.listdir(slug_dir)),
                             sorted(view + ".png" for view in CB.IMAGE_VIEWS))
            for view, src in entry["images"].items():
                _same_bytes(self, os.path.join(slug_dir, view + ".png"), src)


if __name__ == "__main__":
    unittest.main(verbosity=1)
