#!/usr/bin/env python3
"""U-L01: an approval must name who approved it.

Run: python3 test_character_approval_l01.py  (or under unittest/pytest)

Audit row F6 (open half): ``character_approval.approve`` used to write
``approved_by: ""`` when no approver was given, so the versioned approval
event carried no provenance at all. It now refuses with
``APPROVER_MISSING`` and writes no record: no approval event, no queued
continuation.
"""
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

from character_bible import character_approval as CA  # noqa: E402
from choice_card.intake_card import delivery_outbox as DO  # noqa: E402


def _png(path, w=24, h=32, rgb=(180, 60, 60)):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    with open(path, "wb") as fh:        fh.write(b"\x89PNG\r\n\x1a\n"
                 + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw))
                 + chunk(b"IEND", b""))
    return path


#: Generic fixture cast. Never a client.
def _entries(img_dir):
    images = {view: _png(os.path.join(img_dir, "sample-%s.png" % view))
              for view in ("close-up", "side-profile", "three-quarter",
                           "full-standing")}
    return [{
        "name": "Sample Character", "role": "protagonist",
        "background": "Grew up in a small coastal town and ran the family shop.",
        "appearance": "Medium-brown skin, short coily hair, a broad easy smile.",
        "voice_notes": "Low, unhurried, warm. Sings the verses plainly.",
        "images": images,
    }]


class ApproverRequired(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="s75ul01-approver-")
        self.run = os.path.join(self.t, "run-1")
        imgs = os.path.join(self.t, "imgs")
        os.makedirs(self.run)
        os.makedirs(imgs)
        DO.save_origin(self.run, DO.origin_record(
            tenant_id="tenant-7", account_id="bot-7", channel="app",
            conversation_id="conv-7", thread_id="thread-7"))
        CA.save_bible(self.run, CA.bible_from_entries(_entries(imgs)))
        CA.present(self.run, run_id="run-1")

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def _assert_nothing_written(self):
        self.assertIsNone(CA.approval_record(self.run))
        self.assertFalse(
            os.path.exists(os.path.join(self.run, CA.APPROVAL_NAME)))
        self.assertFalse(
            os.path.exists(os.path.join(self.run, CA.CONTINUATION_NAME)))

    def test_a_missing_approver_is_refused_and_writes_nothing(self):
        res = CA.approve(self.run, "approve", run_id="run-1")
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["reason_code"], "APPROVER_MISSING")
        self.assertTrue(res["detail"])
        self._assert_nothing_written()

    def test_an_empty_or_blank_approver_is_refused(self):
        for blank in ("", "   ", None):
            res = CA.approve(self.run, "approve", approved_by=blank,
                             run_id="run-1")
            self.assertEqual(res["status"], "error", blank)
            self.assertEqual(res["reason_code"], "APPROVER_MISSING", blank)
            self._assert_nothing_written()

    def test_a_named_approver_still_writes_the_record(self):
        res = CA.approve(self.run, "approve", approved_by="client-7",
                         run_id="run-1")
        self.assertEqual(res["status"], CA.APPROVED)
        self.assertEqual(res["event"]["approved_by"], "client-7")
        rec = CA.approval_record(self.run)
        self.assertEqual(rec["approved_by"], "client-7")
        entries = CA._continuation_doc(self.run)["entries"]
        self.assertEqual(len(entries), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
