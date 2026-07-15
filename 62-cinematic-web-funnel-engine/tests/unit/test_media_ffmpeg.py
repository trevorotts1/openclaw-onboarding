#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_media_ffmpeg.py — offline-except-ffmpeg unit tests for
scripts/lib/media_ffmpeg.py (Skill 62, build unit U13).

These tests call REAL ffmpeg/ffprobe against small real fixture files built
in setUpClass (spec 19.2 "actual FFmpeg fixture processing" -- this module's
whole purpose is to be a thin, honest wrapper around real subprocess calls,
so mocking subprocess would test nothing meaningful). If ffmpeg/ffprobe are
not on this machine, setUpClass raises loudly (skipTest is NOT used here --
per the U13 directive, this module must fail closed, not silently skip).

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
_STRUCTURE_DIR = _SKILL_DIR / "structure"
for p in (str(_SCRIPTS_DIR), str(_SCRIPTS_DIR / "lib")):
    if p not in sys.path:
        sys.path.insert(0, p)

import media_ffmpeg as mf  # noqa: E402


class TestFailClosedBinaryResolution(unittest.TestCase):
    def test_require_binaries_succeeds_on_this_machine(self):
        binaries = mf.require_binaries()
        self.assertTrue(Path(binaries["ffmpeg"]).exists())
        self.assertTrue(Path(binaries["ffprobe"]).exists())

    def test_env_override_to_nonexistent_path_fails_closed(self):
        import os
        os.environ[mf.FFMPEG_ENV] = "/definitely/not/a/real/ffmpeg"
        try:
            with self.assertRaises(mf.MediaToolingUnavailable):
                mf.require_binaries()
        finally:
            del os.environ[mf.FFMPEG_ENV]

    def test_resolve_binary_returns_none_for_bogus_env_override(self):
        import os
        os.environ["CWFE_TEST_BOGUS_BIN"] = "/nope/nope/nope"
        try:
            self.assertIsNone(mf.resolve_binary("CWFE_TEST_BOGUS_BIN", "ffmpeg"))
        finally:
            del os.environ["CWFE_TEST_BOGUS_BIN"]

    def test_resolve_binary_falls_back_to_path_lookup_when_unset(self):
        self.assertIsNotNone(mf.resolve_binary("CWFE_TEST_UNSET_ENV_VAR", "ffmpeg"))


class TestParseRate(unittest.TestCase):
    def test_fraction(self):
        self.assertAlmostEqual(mf._parse_rate("30/1"), 30.0)
        self.assertAlmostEqual(mf._parse_rate("24000/1001"), 23.976, places=2)

    def test_zero_over_zero_is_unknown_not_an_error(self):
        self.assertEqual(mf._parse_rate("0/0"), 0.0)

    def test_bare_number(self):
        self.assertAlmostEqual(mf._parse_rate("25"), 25.0)

    def test_garbage_returns_zero_not_raise(self):
        self.assertEqual(mf._parse_rate("not-a-rate"), 0.0)
        self.assertEqual(mf._parse_rate(""), 0.0)


class TestSchemaHelpers(unittest.TestCase):
    def test_load_schema_reads_the_real_u13_schema_files(self):
        s1 = mf.load_schema(_STRUCTURE_DIR, "media-processing-receipt.schema.json")
        s2 = mf.load_schema(_STRUCTURE_DIR, "boundary-frames.schema.json")
        self.assertEqual(s1["required"][0], "schema_version")
        self.assertEqual(s2["required"][0], "schema_version")

    def test_load_schema_missing_file_raises(self):
        with self.assertRaises(mf.MediaProcessingError):
            mf.load_schema(_STRUCTURE_DIR, "does-not-exist.schema.json")

    def test_validate_or_raise_rejects_bad_instance(self):
        schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}}
        with self.assertRaises(mf.MediaProcessingError):
            mf.validate_or_raise({}, schema, label="test")
        mf.validate_or_raise({"a": "ok"}, schema, label="test")  # must not raise


class TestAtomicWriteJson(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-media-ffmpeg-atomic-ut-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_then_read_round_trips(self):
        path = self.tmp / "receipt.json"
        data = {"a": 1, "b": [1, 2, 3]}
        mf.atomic_write_json(path, data)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), data)

    def test_no_stray_tmp_file_left_behind(self):
        path = self.tmp / "receipt.json"
        mf.atomic_write_json(path, {"x": True})
        leftovers = [p for p in self.tmp.iterdir() if p.name.startswith(".") and p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])


class TestRealFfmpegFfprobeFixtures(unittest.TestCase):
    """Real ffmpeg/ffprobe calls against real synthesized fixtures -- no mocks."""

    @classmethod
    def setUpClass(cls):
        cls.binaries = mf.require_binaries()  # fail closed if absent, per directive
        cls.tmp = Path(tempfile.mkdtemp(prefix="cwfe-media-ffmpeg-fixtures-ut-"))
        cls.clip = cls.tmp / "clip.mp4"
        proc = mf.run_cmd(
            [
                cls.binaries["ffmpeg"], "-y",
                "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10:duration=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.clip),
            ],
            label="ffmpeg-fixture-setup",
        )
        if proc.returncode != 0 or not cls.clip.exists():
            raise RuntimeError(f"could not build test fixture clip: {proc.stderr[-400:]}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_probe_source_real_clip(self):
        probe = mf.probe_source(self.binaries, self.clip)
        self.assertEqual((probe["width"], probe["height"]), (320, 240))
        self.assertEqual(probe["codec_name"], "h264")
        self.assertFalse(probe["has_audio"])
        self.assertGreater(probe["duration_seconds"], 0)
        self.assertGreater(probe["fps"], 0)

    def test_probe_source_empty_file_raises(self):
        empty = self.tmp / "empty.mp4"
        empty.write_bytes(b"")
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            mf.probe_source(self.binaries, empty)
        self.assertEqual(ctx.exception.reason, "empty-source")

    def test_probe_source_corrupt_file_raises(self):
        corrupt = self.tmp / "corrupt.mp4"
        corrupt.write_bytes(b"garbage, not a real container")
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            mf.probe_source(self.binaries, corrupt)
        self.assertEqual(ctx.exception.reason, "corrupt-source")

    def test_count_frames_matches_expected_10fps_1s(self):
        n = mf.count_frames(self.binaries, self.clip)
        self.assertEqual(n, 10)  # exact: 10fps * 1s lavfi source, deterministic frame count

    def test_extract_frame_by_index_first_and_last_are_distinct(self):
        n = mf.count_frames(self.binaries, self.clip)
        first = mf.extract_frame_by_index(self.binaries, self.clip, 0, self.tmp / "f0.png")
        last = mf.extract_frame_by_index(self.binaries, self.clip, n - 1, self.tmp / "f_last.png")
        self.assertEqual(first["frame_index"], 0)
        self.assertEqual(last["frame_index"], n - 1)
        self.assertNotEqual(first["hash_sha256"], last["hash_sha256"])
        self.assertEqual((first["width"], first["height"]), (320, 240))
        self.assertAlmostEqual(first["timestamp_seconds"], 0.0, delta=0.05)

    def test_extract_frame_out_of_range_raises_extraction_failed(self):
        # An out-of-range select never matches any frame; ffmpeg still exits
        # 0 but writes no output file (0 frames selected), which
        # extract_frame_by_index's own empty-output check catches first --
        # see its docstring for the (defensive, harder to trigger in
        # practice) 'boundary-frame-not-found' path for when ffmpeg DOES
        # write a file but showinfo never logged a pts_time for it.
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            mf.extract_frame_by_index(self.binaries, self.clip, 99999, self.tmp / "oob.png")
        self.assertEqual(ctx.exception.reason, "boundary-extraction-failed")

    def test_sha256_file_is_deterministic(self):
        h1 = mf.sha256_file(self.clip)
        h2 = mf.sha256_file(self.clip)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)


if __name__ == "__main__":
    unittest.main()
