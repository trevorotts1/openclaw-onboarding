#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: transcript sync verification (U045)
# -----------------------------------------------------------------------------
# Stdlib unittest only. No ffmpeg, no network: the verification core is a pure
# function driven with hand-built SRT fixtures, plus a subprocess CLI check
# (the --duration path needs no ffprobe). Proves F45: a transcript that does
# not sync to the audio — wrong episode (zero timestamps in range), truncated
# (last cue far short of the duration), or longer than the audio (last cue
# beyond it) — is REJECTED instead of silently attaching, while a genuine
# full-episode transcript verifies.
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_verify_transcript_sync.py
# =============================================================================
"""Deterministic tests for the SRT-vs-audio sync verifier (U045 / F45)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "verify_transcript_sync.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_transcript_sync", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    # Register BEFORE exec: Python 3.14's dataclass machinery resolves the
    # defining module via sys.modules during class creation.
    sys.modules["verify_transcript_sync"] = mod
    spec.loader.exec_module(mod)
    return mod


VS = _load_module()


def _ts(t: float) -> str:
    """Seconds -> SRT timestamp 'HH:MM:SS,mmm'."""
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _srt(*cues: tuple[float, float, str]) -> str:
    """Build an SRT from (start_s, end_s, text) cues."""
    blocks = []
    for i, (start, end, text) in enumerate(cues, 1):
        blocks.append(f"{i}\n{_ts(start)} --> {_ts(end)}\n{text}\n")
    return "\n".join(blocks)


# A 10-minute episode with cues at the head, middle, and tail: genuine.
VALID = _srt((0.0, 5.0, "Welcome to the show."),
             (300.0, 306.0, "Halfway through the episode."),
             (595.0, 599.0, "Thanks for listening."))
AUDIO_10MIN = 600.0


class VerifySyncUnitTests(unittest.TestCase):
    # -- required test 1: a valid SRT matching the audio verifies -----------
    def test_valid_transcript_verifies(self):
        r = VS.verify_srt_sync(VALID, AUDIO_10MIN)
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(r.cues, 3)
        self.assertEqual(r.in_range, 3)

    # -- required test 2: timestamps far exceeding the audio fail -----------
    def test_last_timestamp_beyond_duration_fails(self):
        # One cue in range, but the last cue lands minutes past the audio.
        srt = _srt((0.0, 5.0, "In range."), (700.0, 705.0, "Beyond the audio."))
        r = VS.verify_srt_sync(srt, AUDIO_10MIN)
        self.assertFalse(r.ok)
        self.assertIn("exceeds", r.reason)

    # -- AC4: a wrong-episode transcript (zero timestamps in range) ---------
    def test_wrong_episode_zero_in_range_fails(self):
        srt = _srt((700.0, 705.0, "Different show."), (800.0, 805.0, "Also different."))
        r = VS.verify_srt_sync(srt, AUDIO_10MIN)
        self.assertFalse(r.ok)
        self.assertEqual(r.in_range, 0)
        self.assertIn("zero timestamps", r.reason)

    # -- AC5: a truncated transcript is detected ----------------------------
    def test_truncated_transcript_fails(self):
        # Cues stop at 105s of a 600s episode — 17% coverage, well under 50%.
        srt = _srt((0.0, 5.0, "Intro."), (100.0, 105.0, "Then it cuts off."))
        r = VS.verify_srt_sync(srt, AUDIO_10MIN)
        self.assertFalse(r.ok)
        self.assertIn("truncated", r.reason)

    # -- AC3: timestamps must match spoken-word segments when supplied ------
    def test_no_cue_overlaps_spoken_segment_fails(self):
        # Speech (per silencedetect) is only at 10-20s; no cue touches it.
        srt = _srt((0.0, 2.0, "Before the speech."), (30.0, 35.0, "After it."),
                   (595.0, 599.0, "Tail."))
        r = VS.verify_srt_sync(srt, AUDIO_10MIN, spoken_segments=[(10.0, 20.0)])
        self.assertFalse(r.ok)
        self.assertIn("spoken-word", r.reason)

    def test_cue_overlapping_spoken_segment_passes(self):
        r = VS.verify_srt_sync(VALID, AUDIO_10MIN,
                               spoken_segments=[(0.0, 6.0), (300.0, 306.0)])
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(r.matched_spoken, 2)

    def test_without_segments_in_range_cues_are_the_speech_evidence(self):
        # No silence map (the --duration path): in-range cues satisfy AC3,
        # while the zero-match rejection still catches a wrong episode.
        r = VS.verify_srt_sync(VALID, AUDIO_10MIN, spoken_segments=None)
        self.assertTrue(r.ok, r.reason)

    # -- garbage / empty input fails closed, never throws -------------------
    def test_empty_srt_fails_closed(self):
        r = VS.verify_srt_sync("", AUDIO_10MIN)
        self.assertFalse(r.ok)
        self.assertEqual(r.cues, 0)

    def test_malformed_srt_fails_closed(self):
        r = VS.verify_srt_sync("this is not an srt at all", AUDIO_10MIN)
        self.assertFalse(r.ok)

    # -- tolerance: a cue ending a hair past the duration is still in -------
    def test_tolerance_allows_rounding_past_duration(self):
        srt = _srt((0.0, 5.0, "Head."), (595.0, 601.5, "Ends 1.5s past."))
        r = VS.verify_srt_sync(srt, AUDIO_10MIN)  # default 2s tolerance
        self.assertTrue(r.ok, r.reason)


class VerifySyncCliTests(unittest.TestCase):
    """The CLI --duration path (no ffprobe needed) end to end."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="podcast-u045-")
        self.srt = os.path.join(self.tmp, "episode.srt")

    def _run(self, *args):
        return subprocess.run([sys.executable, str(_SCRIPT), *args],
                              capture_output=True, text=True, timeout=30)

    def test_cli_verifies_a_good_transcript(self):
        with open(self.srt, "w", encoding="utf-8") as fh:
            fh.write(VALID)
        r = self._run("--srt", self.srt, "--duration", "600")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("VERIFIED", r.stdout)

    def test_cli_rejects_a_wrong_episode(self):
        with open(self.srt, "w", encoding="utf-8") as fh:
            fh.write(_srt((700.0, 705.0, "Different show.")))
        r = self._run("--srt", self.srt, "--duration", "600")
        self.assertEqual(r.returncode, 1)
        self.assertIn("REJECTED", r.stdout)

    def test_cli_json_output(self):
        with open(self.srt, "w", encoding="utf-8") as fh:
            fh.write(VALID)
        r = self._run("--srt", self.srt, "--duration", "600", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        verdict = json.loads(r.stdout)
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["cues"], 3)


if __name__ == "__main__":
    unittest.main()
