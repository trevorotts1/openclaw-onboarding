#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_encode_scrub_media.py — offline-except-ffmpeg unit tests for
scripts/encode_scrub_media.py (Skill 62, build unit U13).

Uses REAL ffmpeg/ffprobe against a small real synthesized fixture (spec 19.2
"actual FFmpeg fixture processing") -- no subprocess mocking. If ffmpeg is
not on this machine, setUpClass raises loudly rather than skipping, matching
the directive's fail-closed requirement.

stdlib unittest only. Run:
  python3 -m unittest discover -s tests/unit -v
  (from the 62-cinematic-web-funnel-engine/ directory)
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"
for p in (str(_SCRIPTS_DIR), str(_SCRIPTS_DIR / "lib")):
    if p not in sys.path:
        sys.path.insert(0, p)

import media_ffmpeg as mf  # noqa: E402
import encode_scrub_media as esm  # noqa: E402


class TestEncodeScrubMedia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binaries = mf.require_binaries()  # fail closed if absent
        cls.tmp = Path(tempfile.mkdtemp(prefix="cwfe-encode-ut-"))
        cls.src = cls.tmp / "source.mp4"
        proc = mf.run_cmd(
            [
                cls.binaries["ffmpeg"], "-y",
                "-f", "lavfi", "-i", "testsrc2=size=640x480:rate=25:duration=1",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                str(cls.src),
            ],
            label="ffmpeg-fixture-setup",
        )
        if proc.returncode != 0 or not cls.src.exists():
            raise RuntimeError(f"could not build test fixture source: {proc.stderr[-400:]}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _out(self, name: str) -> Path:
        d = self.tmp / name
        return d

    def test_desktop_and_mobile_variants_produced_with_correct_dims(self):
        receipt = esm.encode_scrub_media(self.src, self._out("out1"), asset_id="a1")
        by_name = {v["variant_name"]: v for v in receipt["variants"]}
        self.assertEqual((by_name["desktop"]["width"], by_name["desktop"]["height"]), (1920, 1080))
        self.assertEqual((by_name["mobile"]["width"], by_name["mobile"]["height"]), (1080, 1920))

    def test_audio_removed_by_default(self):
        receipt = esm.encode_scrub_media(self.src, self._out("out2"), asset_id="a2", variant_names=["desktop"])
        self.assertFalse(receipt["variants"][0]["has_audio"])

    def test_keep_audio_flag_preserves_audio(self):
        receipt = esm.encode_scrub_media(self.src, self._out("out3"), asset_id="a3", variant_names=["desktop"], keep_audio=True)
        self.assertTrue(receipt["variants"][0]["has_audio"])

    def test_short_gop_is_applied_and_recorded(self):
        receipt = esm.encode_scrub_media(self.src, self._out("out4"), asset_id="a4", variant_names=["desktop"], gop=8)
        self.assertEqual(receipt["variants"][0]["gop"], 8)

    def test_h264_mp4_faststart_container(self):
        receipt = esm.encode_scrub_media(self.src, self._out("out5"), asset_id="a5", variant_names=["desktop"])
        v = receipt["variants"][0]
        self.assertEqual(v["container"], "mp4")
        self.assertEqual(v["codec_name"], "h264")

    def test_webm_derivative_when_requested(self):
        receipt = esm.encode_scrub_media(self.src, self._out("out6"), asset_id="a6", variant_names=["desktop"], webm=True)
        names = {v["variant_name"] for v in receipt["variants"]}
        self.assertEqual(names, {"desktop", "desktop-webm"})
        webm_variant = next(v for v in receipt["variants"] if v["variant_name"] == "desktop-webm")
        self.assertEqual(webm_variant["container"], "webm")

    def test_poster_frame_is_extracted_and_hashed(self):
        receipt = esm.encode_scrub_media(self.src, self._out("out7"), asset_id="a7", variant_names=["desktop"])
        v = receipt["variants"][0]
        poster = Path(v["poster_frame_path"])
        self.assertTrue(poster.exists())
        self.assertGreater(poster.stat().st_size, 0)
        self.assertEqual(mf.sha256_file(poster), v["poster_frame_hash_sha256"])

    def test_receipt_written_atomically_and_schema_valid(self):
        out_dir = self._out("out8")
        receipt = esm.encode_scrub_media(self.src, out_dir, asset_id="a8", variant_names=["desktop"])
        receipt_path = out_dir / "a8.media-processing-receipt.json"
        self.assertTrue(receipt_path.exists())
        reloaded = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(reloaded, receipt)

    def test_asset_id_defaults_deterministically_from_input_path(self):
        r1 = esm.encode_scrub_media(self.src, self._out("out9a"), variant_names=["desktop"])
        r2 = esm.encode_scrub_media(self.src, self._out("out9b"), variant_names=["desktop"])
        self.assertEqual(r1["asset_id"], r2["asset_id"])

    def test_rejects_corrupt_source(self):
        corrupt = self.tmp / "corrupt.mp4"
        corrupt.write_bytes(b"not a real video file at all")
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            esm.encode_scrub_media(corrupt, self._out("out10"), asset_id="bad")
        self.assertEqual(ctx.exception.reason, "corrupt-source")

    def test_rejects_empty_source(self):
        empty = self.tmp / "empty.mp4"
        empty.write_bytes(b"")
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            esm.encode_scrub_media(empty, self._out("out11"), asset_id="bad2")
        self.assertEqual(ctx.exception.reason, "empty-source")

    def test_rejects_unknown_variant_name(self):
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            esm.encode_scrub_media(self.src, self._out("out12"), asset_id="bad3", variant_names=["ultrawide"])
        self.assertEqual(ctx.exception.reason, "unknown-variant")

    def test_no_receipt_written_on_rejection(self):
        corrupt = self.tmp / "corrupt2.mp4"
        corrupt.write_bytes(b"still not real")
        out_dir = self._out("out13")
        with self.assertRaises(mf.MediaProcessingError):
            esm.encode_scrub_media(corrupt, out_dir, asset_id="bad4")
        self.assertFalse((out_dir / "bad4.media-processing-receipt.json").exists())

    def test_fails_closed_when_ffmpeg_unavailable(self):
        import os
        os.environ[mf.FFMPEG_ENV] = "/nonexistent/ffmpeg"
        try:
            with self.assertRaises(mf.MediaToolingUnavailable):
                esm.encode_scrub_media(self.src, self._out("out14"), asset_id="a14")
        finally:
            del os.environ[mf.FFMPEG_ENV]


if __name__ == "__main__":
    unittest.main()
