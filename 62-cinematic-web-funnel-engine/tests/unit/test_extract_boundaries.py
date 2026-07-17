#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_extract_boundaries.py — offline-except-ffmpeg unit tests for
scripts/extract_boundaries.py (Skill 62, build unit U13).

Uses REAL ffmpeg/ffprobe against real synthesized fixtures (spec 19.2 "actual
boundary extraction") -- no subprocess mocking. If ffmpeg is not on this
machine, setUpClass raises loudly rather than skipping.

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
import extract_boundaries as eb  # noqa: E402


class TestExtractBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binaries = mf.require_binaries()  # fail closed if absent
        cls.tmp = Path(tempfile.mkdtemp(prefix="cwfe-boundaries-ut-"))

        # A clip whose visible content genuinely changes over time.
        cls.changing_clip = cls.tmp / "changing.mp4"
        proc = mf.run_cmd(
            [
                cls.binaries["ffmpeg"], "-y",
                "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=12:duration=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.changing_clip),
            ],
            label="ffmpeg-fixture-changing",
        )
        if proc.returncode != 0 or not cls.changing_clip.exists():
            raise RuntimeError(f"could not build changing-content fixture: {proc.stderr[-400:]}")

        # A GENUINELY STATIC multi-frame clip (solid color, several encoded
        # frames, no motion at all) -- the edge case that distinguishes "a
        # real static clip legitimately has identical boundary frames" from
        # "the extractor collapsed to the same frame due to a bug": with
        # frame_count > 1 this module treats identical first/last hashes as
        # a suspected fault (see extract_boundaries.py docstring) since a
        # genuinely frozen multi-frame clip is not the expected shape of any
        # scene/connector clip this engine ever produces.
        cls.static_clip = cls.tmp / "static.mp4"
        proc2 = mf.run_cmd(
            [
                cls.binaries["ffmpeg"], "-y",
                "-f", "lavfi", "-i", "color=c=blue:s=160x120:d=1:r=8",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.static_clip),
            ],
            label="ffmpeg-fixture-static",
        )
        if proc2.returncode != 0 or not cls.static_clip.exists():
            raise RuntimeError(f"could not build static fixture: {proc2.stderr[-400:]}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _out(self, name: str) -> Path:
        return self.tmp / name

    def test_first_and_last_frame_indices(self):
        n = mf.count_frames(self.binaries, self.changing_clip)
        receipt = eb.extract_boundaries(self.changing_clip, self._out("out1"))
        by_pos = {f["position"]: f for f in receipt["frames"]}
        self.assertEqual(by_pos["first"]["frame_index"], 0)
        self.assertEqual(by_pos["last"]["frame_index"], n - 1)

    def test_first_and_last_frames_are_distinct_for_changing_content(self):
        receipt = eb.extract_boundaries(self.changing_clip, self._out("out2"))
        by_pos = {f["position"]: f for f in receipt["frames"]}
        self.assertNotEqual(by_pos["first"]["hash_sha256"], by_pos["last"]["hash_sha256"])

    def test_frame_dimensions_match_source(self):
        receipt = eb.extract_boundaries(self.changing_clip, self._out("out3"))
        for f in receipt["frames"]:
            self.assertEqual((f["width"], f["height"]), (receipt["source_probe"]["width"], receipt["source_probe"]["height"]))

    def test_single_position_request(self):
        receipt = eb.extract_boundaries(self.changing_clip, self._out("out4"), positions=["last"])
        self.assertEqual(len(receipt["frames"]), 1)
        self.assertEqual(receipt["frames"][0]["position"], "last")

    def test_receipt_written_atomically_and_round_trips(self):
        out_dir = self._out("out5")
        receipt = eb.extract_boundaries(self.changing_clip, out_dir)
        receipt_path = out_dir / f"{self.changing_clip.stem}.boundary-frames.json"
        self.assertTrue(receipt_path.exists())
        self.assertEqual(json.loads(receipt_path.read_text(encoding="utf-8")), receipt)

    def test_static_multiframe_clip_trips_identical_boundary_fault(self):
        """The load-bearing edge case: a genuinely static multi-frame clip
        must be rejected as a suspected extraction fault, not silently
        accepted as a valid pair of connector-pinning endpoints."""
        n = mf.count_frames(self.binaries, self.static_clip)
        self.assertGreater(n, 1, "fixture must genuinely have more than one encoded frame")
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            eb.extract_boundaries(self.static_clip, self._out("out6"))
        self.assertEqual(ctx.exception.reason, "boundary-frames-identical")

    def test_single_frame_clip_first_equals_last_without_raising(self):
        """A genuine 1-frame clip (frame_count == 1) is the legitimate case
        where first_index == last_index == 0 -- must NOT trip the
        identical-hash fault detector, since there is only one real frame,
        not a suspected extraction bug."""
        still = self.tmp / "onef.mp4"
        proc = mf.run_cmd(
            [
                self.binaries["ffmpeg"], "-y", "-f", "lavfi", "-i", "color=c=green:s=64x64:d=1:r=1",
                "-frames:v", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(still),
            ],
            label="ffmpeg-fixture-onef",
        )
        self.assertEqual(proc.returncode, 0)
        receipt = eb.extract_boundaries(still, self._out("out7"))
        by_pos = {f["position"]: f for f in receipt["frames"]}
        self.assertEqual(by_pos["first"]["frame_index"], 0)
        self.assertEqual(by_pos["last"]["frame_index"], 0)

    def test_rejects_corrupt_input(self):
        corrupt = self.tmp / "corrupt.mp4"
        corrupt.write_bytes(b"not a real encoded clip")
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            eb.extract_boundaries(corrupt, self._out("out8"))
        self.assertEqual(ctx.exception.reason, "corrupt-source")

    def test_rejects_empty_input(self):
        empty = self.tmp / "empty.mp4"
        empty.write_bytes(b"")
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            eb.extract_boundaries(empty, self._out("out9"))
        self.assertEqual(ctx.exception.reason, "empty-source")

    def test_no_receipt_written_on_rejection(self):
        corrupt = self.tmp / "corrupt2.mp4"
        corrupt.write_bytes(b"nope")
        out_dir = self._out("out10")
        with self.assertRaises(mf.MediaProcessingError):
            eb.extract_boundaries(corrupt, out_dir)
        self.assertFalse((out_dir / "corrupt2.boundary-frames.json").exists())

    def test_unknown_position_rejected(self):
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            eb.extract_boundaries(self.changing_clip, self._out("out11"), positions=["middle"])
        self.assertEqual(ctx.exception.reason, "unknown-position")

    def test_fails_closed_when_ffprobe_unavailable(self):
        import os
        os.environ[mf.FFPROBE_ENV] = "/nonexistent/ffprobe"
        try:
            with self.assertRaises(mf.MediaToolingUnavailable):
                eb.extract_boundaries(self.changing_clip, self._out("out12"))
        finally:
            del os.environ[mf.FFPROBE_ENV]

    def test_composes_with_encode_scrub_media_output(self):
        """End-to-end: real encode -> real boundary extraction on the SAME
        clip, proving the two U13 scripts chain the way spec 12.2 requires
        (connector generation consumes encode_scrub_media's own output)."""
        sys.path.insert(0, str(_SCRIPTS_DIR))
        import encode_scrub_media as esm  # noqa: E402 (local import to avoid a hard module-load cycle)

        encoded_dir = self._out("out13-encoded")
        enc_receipt = esm.encode_scrub_media(self.changing_clip, encoded_dir, asset_id="chain-fixture", variant_names=["desktop"])
        encoded_clip = Path(enc_receipt["variants"][0]["output_path"])

        boundary_receipt = eb.extract_boundaries(encoded_clip, self._out("out13-boundaries"))
        by_pos = {f["position"]: f for f in boundary_receipt["frames"]}
        self.assertEqual((boundary_receipt["source_probe"]["width"], boundary_receipt["source_probe"]["height"]), (1920, 1080))
        self.assertNotEqual(by_pos["first"]["hash_sha256"], by_pos["last"]["hash_sha256"])


if __name__ == "__main__":
    unittest.main()
