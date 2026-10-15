#!/usr/bin/env python3
"""W1-agnes-core-U6 tests: Agnes frame-text rows + the measured Agnes conform.

SPEC A6 (words in pictures) and SPEC A8 (clip conform, measured on trial A).

  frame_text.agnes_clip_rows  - one NAMED row per Agnes clip: PASS /
                                TEXT_CHANGED / GARBLED_TEXT_FRAME /
                                UNAVAILABLE, and the default stub NEVER
                                returns PASS.
  fps_conform                 - native_fps("agnes-video-2.5-flash") == 24.0;
                                agnes_conform_argv strips the clip's AAC
                                track (-an), motion-interpolates 24 -> 30
                                (minterpolate, the H3 filter) and cover-
                                scales with lanczos, never a blur fill and
                                never a letterbox pad.
                                On a 704x1280 24 fps clip with audio (trial
                                A's clip1.mp4 when the trial tree is on this
                                box, else a 1 s synthetic clip built here)
                                the output probes 1080x1920, 30 fps, no
                                audio stream. Point AGNES_TRIAL_CLIP at
                                trial-oct13/test-a-30s-cartoon/clip1.mp4 to
                                run that case on trial A's own clip; the
                                trial tree is not part of this repo, so the
                                default run builds the synthetic clip.

stdlib only, no network, no Agnes call, no KIE call, no spend. The ffmpeg
case SKIPS (never passes) when no ffmpeg/ffprobe is installed.

Run:
    python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/final_assembler/test_agnes_conform.py
    python3 75-drama-song-ad-factory/scripts/core/final_assembler/test_agnes_conform.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from final_assembler import frame_text as FT          # noqa: E402
from final_assembler import fps_conform as F          # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
HAS_FFMPEG = bool(FFMPEG) and bool(FFPROBE)

# SPEC A8 master frame (9:16), and the measured Agnes source.
MASTER_W, MASTER_H = 1080, 1920
AGNES_W, AGNES_H, AGNES_FPS = 704, 1280, 24


def _mock(texts):
    """A findings-only extractor returning `texts` on every call."""
    def extract(_paths):
        return list(texts)
    extract.__name__ = "mock_ocr"
    return extract


def _trial_clip():
    """trial-oct13/test-a-30s-cartoon/clip1.mp4 when it is on this box."""
    env = os.environ.get("AGNES_TRIAL_CLIP")
    if env and os.path.isfile(env):
        return env
    rel = os.path.join("trial-oct13", "test-a-30s-cartoon", "clip1.mp4")
    d = HERE
    for _ in range(8):
        cand = os.path.join(d, rel)
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def _probe(path):
    """{video: {...}, audio: n} for one file, ffprobe JSON."""
    cmd = [FFPROBE, "-v", "error", "-show_entries",
           "stream=codec_type,width,height,avg_frame_rate",
           "-of", "json", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError("ffprobe failed on %s: %s"
                             % (path, (proc.stderr or "").strip()[:300]))
    streams = json.loads(proc.stdout).get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = len([s for s in streams if s.get("codec_type") == "audio"])
    return {"video": video, "audio": audio}


def _synthetic_clip(dst):
    """1 s, 704x1280, 24 fps WITH an AAC track: trial A's measured shape."""
    argv = [FFMPEG, "-y", "-f", "lavfi",
            "-i", "testsrc2=size=%dx%d:rate=%d" % (AGNES_W, AGNES_H,
                                                   AGNES_FPS),
            "-f", "lavfi", "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", "1", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", str(dst)]
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError("synthetic clip failed: %s"
                             % (proc.stderr or "").strip()[-400:])
    return str(dst)


# --------------------------------------------------------------- rows ------

class AgnesClipRowsTest(unittest.TestCase):
    """frame_text.agnes_clip_rows: the named verdicts (SPEC A6)."""

    def test_stub_is_unavailable_never_pass(self):
        """The default stub opens no pixel, so it clears nothing (U5/U6)."""
        rows = FT.agnes_clip_rows([{"src": "seg0.mp4"}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], FT.UNAVAILABLE)
        self.assertNotEqual(rows[0]["status"], FT.PASS)
        self.assertEqual(rows[0]["extractor"], FT.STUB_NAME)
        self.assertEqual(rows[0]["sampled"], 3)

    def test_no_text_segment_with_readable_word_is_garbled(self):
        """SPEC A6: a no-text segment showing a 3+ letter word fails."""
        row = FT.agnes_clip_rows([{"src": "seg0.mp4"}],
                                 extractor=_mock(["OPEN", None, None]))[0]
        self.assertEqual(row["status"], FT.GARBLED_TEXT_FRAME)

    def test_two_letters_is_not_a_readable_word(self):
        """SPEC A6's bar is 3+ letters; shorter noise is not a finding."""
        row = FT.agnes_clip_rows([{"src": "seg0.mp4"}],
                                 extractor=_mock(["ab", None, None]))[0]
        self.assertEqual(row["status"], FT.PASS)

    def test_clean_no_text_segment_passes_with_a_real_reader(self):
        row = FT.agnes_clip_rows([{"src": "seg0.mp4"}],
                                 extractor=_mock([None, None, None]))[0]
        self.assertEqual(row["status"], FT.PASS)

    def test_expected_words_match_and_change(self):
        segs = [{"src": "seg0.mp4"}]
        exp = {0: "OPEN"}
        same = FT.agnes_clip_rows(segs, exp,
                                  extractor=_mock(["OPEN", "OPEN", "OPEN"]))[0]
        self.assertEqual(same["status"], FT.PASS)
        self.assertEqual(same["expected"], "OPEN")
        # Same frame count, different words: the clip changed.
        changed = FT.agnes_clip_rows(segs, exp,
                                     extractor=_mock(["poen", None, None]))[0]
        self.assertEqual(changed["status"], FT.TEXT_CHANGED)
        # Words expected, none read: also a change, never a silent pass.
        gone = FT.agnes_clip_rows(segs, exp,
                                  extractor=_mock([None, None, None]))[0]
        self.assertEqual(gone["status"], FT.TEXT_CHANGED)

    def test_expectation_is_keyed_by_segment_index(self):
        segs = [{"src": "seg0.mp4"}, {"src": "seg1.mp4"}]
        rows = FT.agnes_clip_rows(
            segs, {1: "OPEN"}, extractor=_mock([None, None, None]))
        # Only segment 1 carries an expectation, so only segment 1 changes.
        self.assertEqual([r["status"] for r in rows],
                         [FT.PASS, FT.TEXT_CHANGED])
        # Segment 0 has no expectation (a no-text segment): any word fails.
        rows = FT.agnes_clip_rows(
            segs, {1: "OPEN"}, extractor=_mock(["OPEN", "OPEN", "OPEN"]))
        self.assertEqual([r["status"] for r in rows],
                         [FT.GARBLED_TEXT_FRAME, FT.PASS])

    def test_sample_failure_is_unavailable_not_a_pass(self):
        """A clip that cannot be probed is UNAVAILABLE, never PASS."""
        rows = FT.agnes_clip_rows([{"src": "no-such-clip.mp4"}],
                                  extractor=_mock([None, None, None]),
                                  ffmpeg=FFMPEG or "ffmpeg")
        self.assertEqual(rows[0]["status"], FT.UNAVAILABLE)
        self.assertEqual(rows[0]["sampled"], 0)

    def test_unknown_extractor_still_fails_closed(self):
        with self.assertRaises(FT.FrameTextError):
            FT.agnes_clip_rows([{"src": "seg0.mp4"}], extractor="nope")


# -------------------------------------------------------------- argv -------

class AgnesConformArgvTest(unittest.TestCase):
    """fps_conform: the measured Agnes entry and its argv (SPEC A8)."""

    def test_native_fps_has_measured_agnes_entry(self):
        self.assertEqual(F.NATIVE_FPS["agnes"], 24.0)
        self.assertEqual(F.native_fps("agnes-video-2.5-flash"), 24.0)
        self.assertEqual(F.native_fps("agnes-video-2.5"), 24.0)
        # The other generators keep their measured rates.
        self.assertEqual(F.native_fps("kling"), 30.0)
        self.assertEqual(F.native_fps("minimax-hailuo-h3"), 24.0)

    def test_argv_strips_audio_and_conforms(self):
        argv = F.agnes_conform_argv("in.mp4", "out.mp4", MASTER_W, MASTER_H)
        self.assertIsInstance(argv, list)
        self.assertIn("-an", argv)                 # the song is the only audio
        self.assertIn("-i", argv)
        chain = argv[argv.index("-vf") + 1]
        self.assertIn("minterpolate=fps=30:mi_mode=mci", chain)  # 24 -> 30
        self.assertIn("flags=lanczos", chain)      # cover-scale, no blur
        self.assertIn("crop=w=%d:h=%d" % (MASTER_W, MASTER_H), chain)
        # Load governor owns every ffmpeg argv.
        self.assertEqual(os.path.basename(argv[0]), "nice")
        self.assertIn("-threads", argv)

    def test_argv_never_blurs_or_pads(self):
        """DEL-14: no blur fill and no letterbox pad, anywhere in the chain."""
        argv = F.agnes_conform_argv("in.mp4", "out.mp4", MASTER_W, MASTER_H)
        chain = argv[argv.index("-vf") + 1]
        for banned in ("blur", "gblur", "boxblur", "pad=", "setsar=2"):
            self.assertNotIn(banned, chain)
        # Order is load bearing: interpolate FIRST, cover-scale SECOND.
        self.assertLess(chain.index("minterpolate"), chain.index("scale="))

    def test_argv_rejects_bad_geometry(self):
        with self.assertRaises(Exception):
            F.agnes_conform_argv("in.mp4", "out.mp4", 0, MASTER_H)


# ------------------------------------------------------- real ffmpeg -------

@unittest.skipUnless(HAS_FFMPEG,
                     "SKIPPED: ffmpeg/ffprobe not installed")
class AgnesConformMeasureTest(unittest.TestCase):
    """The measured end of the prove line: a real clip, a real probe."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="W1-agnes-core-U6-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_output_probes_1080x1920_30fps_no_audio(self):
        trial = _trial_clip()
        src = trial or _synthetic_clip(os.path.join(self.tmp, "src.mp4"))
        if not trial:
            # The fixture must be trial A's measured shape, or the prove
            # is not measuring what SPEC A8 says.
            s = _probe(src)["video"]
            self.assertEqual((s["width"], s["height"]),
                             (AGNES_W, AGNES_H))
            self.assertEqual(s["avg_frame_rate"], "%d/1" % AGNES_FPS)
            self.assertEqual(_probe(src)["audio"], 1,
                             "the source must carry audio for -an to strip")

        dst = os.path.join(self.tmp, "conformed.mp4")
        argv = F.agnes_conform_argv(src, dst, MASTER_W, MASTER_H)
        proc = subprocess.run(argv, capture_output=True, text=True,
                              check=False)
        self.assertEqual(proc.returncode, 0,
                         "ffmpeg failed: %s" % (proc.stderr or "")[-600:])
        self.assertTrue(os.path.isfile(dst) and os.path.getsize(dst) > 0)

        out = _probe(dst)
        self.assertEqual((out["video"]["width"], out["video"]["height"]),
                         (MASTER_W, MASTER_H))
        num, den = out["video"]["avg_frame_rate"].split("/")
        self.assertEqual(float(num) / float(den), F.MASTER_FPS)
        self.assertEqual(out["audio"], 0, "the clip's own audio must be gone")


def main():
    unittest.main(verbosity=2)


if __name__ == "__main__":
    main()
