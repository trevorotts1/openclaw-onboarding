#!/usr/bin/env python3
"""F18 tests: the caption and lyric checks consume measured word timing.

Part F F18 (wire F17's lyric_timing into the caption + lyric checks).
Every timing fixture is a mocked receipt — zero paid calls, zero local model
loads, stdlib only.

    python3 core/test_caption_lyric_timing_f18.py
    python3 -m pytest core/test_caption_lyric_timing_f18.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import caption_timing as CT  # noqa: E402  module under test
import protected_names as P  # noqa: E402  cue building
import music_qc  # noqa: E402  lyric check
from delivery_variants import checks  # noqa: E402  caption check

SHEET = ("[Verse]\nThe house went Stale\nI cleaned it all day\n"
         "[Chorus]\nStop Stale, take back the wheel")
LINES = [
    {"line_id": "v1", "text": "The house went Stale"},
    {"line_id": "v2", "text": "I cleaned it all day"},
    {"line_id": "c1", "text": "Stop Stale, take back the wheel",
     "critical": True},
]
NAMES = ["Stale", "Stop Stale"]

#: tier-1 receipt exactly as lyric_timing returns it (Suno alignedWords).
SUNO_WORDS = [
    {"word": "The", "start": 0.0, "end": 0.2},
    {"word": "house", "start": 0.2, "end": 0.5},
    {"word": "went", "start": 0.5, "end": 0.8},
    {"word": "Stale", "start": 0.8, "end": 1.3},
    {"word": "I", "start": 1.3, "end": 1.4},
    {"word": "cleaned", "start": 1.4, "end": 1.8},
    {"word": "it", "start": 1.8, "end": 1.9},
    {"word": "all", "start": 1.9, "end": 2.1},
    {"word": "day", "start": 2.1, "end": 2.5},
    {"word": "Stop", "start": 3.0, "end": 3.3},
    {"word": "Stale", "start": 3.3, "end": 3.8},
    {"word": "take", "start": 3.8, "end": 4.0},
    {"word": "back", "start": 4.0, "end": 4.2},
    {"word": "the", "start": 4.2, "end": 4.3},
    {"word": "wheel", "start": 4.3, "end": 4.8},
]


def suno_receipt(words=None, source="suno-timestamped-lyrics"):
    return {"ok": True, "timings": {
        "schema_version": "blackceo.audio-c3/lyric-timing/v1",
        "tool": "lyric_timing", "tool_version": "1.0.0",
        "source": source, "transcription_provider": "suno (KIE timeStamped-lyrics)",
        "words": list(SUNO_WORDS if words is None else words),
        "local_model_loads": 0}}


def failed_timing(code="SUNO_TIMING_DISPATCH_FAILED"):
    return {"ok": False, "error_code": code,
            "next_action": "tier 1 refused; no measured words"}


# ── measure-now path: dispatcher + track named by env, mocked KIE file ──────

#: measure-now fixture files, shared with the dispatcher by PATH so the
#: env-imported copy of this module (importlib reloads it by name) reads the
#: same bytes the test asserts on.
ENV_DOC = "DRAMA75_F18_TEST_ALIGNED"
ENV_CALLS = "DRAMA75_F18_TEST_CALLS"


def fake_dispatch(**kw):
    doc = os.environ[ENV_DOC]
    calls_path = os.environ[ENV_CALLS]
    n = 0
    try:
        with open(calls_path, encoding="utf-8") as f:
            n = int(f.read().strip() or "0")
    except (OSError, ValueError):
        n = 0
    with open(calls_path, "w", encoding="utf-8") as f:
        f.write(str(n + 1))
    return {"outcome": "ok", "reason_code": "KIE_DISPATCH_OK",
            "evidence": {"saved_paths": [doc]}}


class CuesFromMeasuredTiming(unittest.TestCase):
    """The caption check builds its cue clock from measured words."""

    def test_cues_take_measured_times_and_source(self):
        cues, rec = CT.captions(SHEET, suno_receipt())
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["source"], "suno-timestamped-lyrics")
        self.assertEqual(rec["words"], len(SUNO_WORDS))
        # text is the sheet's own; times are the measured ones; the
        # [Verse]/[Chorus] tags are not caption lines (protected_names
        # strips section tags), so three cues come back.
        self.assertEqual(len(cues), 3)
        self.assertEqual(cues[0]["text"], "The house went Stale")
        self.assertEqual((cues[0]["start"], cues[0]["end"]), (0.0, 1.3))
        self.assertEqual(cues[2]["start"], 3.0)

    def test_bare_word_list_is_accepted(self):
        cues, rec = CT.captions(SHEET, list(SUNO_WORDS))
        self.assertTrue(rec["ok"])
        self.assertEqual(len(cues), 3)  # section tags are not caption lines

    def test_failed_timing_yields_no_cues_and_no_clock(self):
        cues, rec = CT.captions(SHEET, failed_timing())
        self.assertEqual(cues, [])
        self.assertFalse(rec["ok"])
        self.assertEqual(rec["reason_code"],
                         "SUNO_TIMING_DISPATCH_FAILED")

    def test_empty_word_receipt_cannot_build_a_clock(self):
        cues, rec = CT.captions(SHEET, suno_receipt(words=[]))
        self.assertEqual(cues, [])
        self.assertEqual(rec["reason_code"], "TIMING_NO_WORDS")

    def test_no_timing_bound_never_invents_one(self):
        # no receipt, no dispatcher, no recorded track -> refusal, not a pass
        for key in ("DRAMA75_TIMING_DISPATCHER", "DRAMA75_TIMING_TRACK",
                    "DRAMA75_TRACK", "DRAMA75_STATE", "DRAMA75_TIMING_OFF"):
            os.environ.pop(key, None)
        cues, rec = CT.captions(SHEET, None)
        self.assertEqual(cues, [])
        self.assertEqual(rec["reason_code"], "TIMING_NOT_BOUND")

    def test_off_switch_is_an_explicit_unavailable(self):
        os.environ["DRAMA75_TIMING_OFF"] = "1"
        try:
            cues, rec = CT.captions(SHEET, None)
        finally:
            os.environ.pop("DRAMA75_TIMING_OFF", None)
        self.assertEqual(cues, [])
        self.assertEqual(rec["reason_code"], "TIMING_DISABLED")


class CaptionCheckConsumesTiming(unittest.TestCase):
    """delivery_variants.checks.check_captions reports measured timing."""

    def test_pass_carries_measured_source(self):
        v, why = checks.check_captions(
            ["The house went Stale", "I cleaned it all day",
             "Stop Stale, take back the wheel"],
            ["The house went Stale", "I cleaned it all day",
             "Stop Stale, take back the wheel"],
            protected=NAMES, timing=suno_receipt())
        self.assertEqual(v, checks.PASS, why)
        self.assertIn("measured from suno-timestamped-lyrics", why)
        self.assertIn("15 words", why)

    def test_unusable_timing_is_unavailable_not_pass(self):
        v, why = checks.check_captions(
            ["The house went Stale"],
            ["The house went Stale"], protected=NAMES,
            timing=failed_timing())
        self.assertEqual(v, checks.UNAVAILABLE, why)
        self.assertIn("SUNO_TIMING_DISPATCH_FAILED", why)

    def test_empty_measured_words_is_unavailable(self):
        v, why = checks.check_captions(
            ["The house went Stale"],
            ["The house went Stale"], protected=NAMES,
            timing=suno_receipt(words=[]))
        self.assertEqual(v, checks.UNAVAILABLE, why)
        self.assertIn("TIMING_NO_WORDS", why)

    def test_backwards_measured_clock_fails(self):
        # words in sheet order, but line 1 measured AFTER line 2: the cue
        # clock runs backwards (rewound/corrupt timing, never a pass)
        words = [
            {"word": "The", "start": 5.0, "end": 5.2},
            {"word": "house", "start": 5.2, "end": 5.5},
            {"word": "went", "start": 5.5, "end": 5.8},
            {"word": "Stale", "start": 5.8, "end": 6.3},
            {"word": "Stop", "start": 0.0, "end": 0.3},
            {"word": "Stale", "start": 0.3, "end": 0.8},
            {"word": "take", "start": 0.8, "end": 1.0},
            {"word": "back", "start": 1.0, "end": 1.2},
            {"word": "the", "start": 1.2, "end": 1.3},
            {"word": "wheel", "start": 1.3, "end": 1.8},
        ]
        v, why = checks.check_captions(
            ["The house went Stale", "Stop Stale, take back the wheel"],
            ["The house went Stale", "Stop Stale, take back the wheel"],
            protected=NAMES, timing=suno_receipt(words=words))
        self.assertEqual(v, checks.FAIL, why)
        self.assertIn("backwards", why)

    def test_text_only_call_keeps_working(self):
        v, why = checks.check_captions(
            ["The house went Stale"], ["The house went Stale"],
            protected=NAMES)
        self.assertEqual(v, checks.PASS, why)


CONTINUITY = {"persona_continuity": True, "genre_continuity": True,
              "tempo_continuity": True, "clipping": True,
              "transitions": True, "master_duration": True}


class LyricCheckConsumesTiming(unittest.TestCase):
    """music_qc.check_song_qc judges the measured words themselves."""

    def test_pass_names_the_measured_source(self):
        r = music_qc.check_song_qc(LINES, [], CONTINUITY, protected=NAMES,
                                   timing=suno_receipt())
        self.assertEqual(r["verdict"], "PASS", r["findings"])
        self.assertEqual(r["lyric_diff"]["observed_source"],
                         "measured-timing:suno-timestamped-lyrics")
        self.assertEqual(r["lyric_diff"]["coverage"], 1.0)

    def test_measured_words_outrank_a_clean_text_claim(self):
        # the text transcript claims a full take; the TIMING never heard the
        # critical line -> measured evidence decides, the take fails.
        text_claims = [{"line_id": ln["line_id"], "text": ln["text"]}
                       for ln in LINES]
        partial = [w for w in SUNO_WORDS
                   if w["word"] not in ("Stop", "Stale", "take", "back",
                                        "the", "wheel")]
        r = music_qc.check_song_qc(LINES, text_claims, CONTINUITY,
                                   protected=NAMES,
                                   timing=suno_receipt(words=partial))
        self.assertEqual(r["verdict"], "FAIL", r["findings"])
        self.assertTrue(any(f["check"] == "coverage" for f in r["findings"]))

    def test_unusable_timing_is_an_unavailable_finding(self):
        r = music_qc.check_song_qc(LINES, list(LINES), CONTINUITY,
                                   protected=NAMES, timing=failed_timing())
        self.assertEqual(r["verdict"], "UNAVAILABLE", r["findings"])
        timing = [f for f in r["findings"] if f["check"] == "timing"]
        self.assertEqual(len(timing), 1, r["findings"])
        self.assertEqual(timing[0]["verdict"], "UNAVAILABLE")

    def test_text_fail_still_outranks_timing_unavailable(self):
        bad = [{"line_id": "c1",
                "text": "Stop Stale, take back the weel"}]
        r = music_qc.check_song_qc(LINES, bad, CONTINUITY, protected=NAMES,
                                   timing=failed_timing())
        self.assertEqual(r["verdict"], "FAIL", r["findings"])

    def test_adlib_in_measured_words_fails(self):
        words = list(SUNO_WORDS) + [
            {"word": "yodel", "start": 5.0, "end": 5.4}]
        r = music_qc.check_song_qc(LINES, [], CONTINUITY, protected=NAMES,
                                   timing=suno_receipt(words=words))
        self.assertEqual(r["verdict"], "FAIL", r["findings"])
        self.assertTrue(any(f["check"] == "adlib" for f in r["findings"]))

    def test_text_only_call_keeps_working(self):
        seen = [{"line_id": ln["line_id"], "text": ln["text"]}
                for ln in LINES]
        r = music_qc.check_song_qc(LINES, seen, CONTINUITY,
                                   protected=NAMES)
        self.assertEqual(r["verdict"], "PASS", r["findings"])
        self.assertNotIn("observed_source", r["lyric_diff"])


class MeasureNowThroughTheOneStep(unittest.TestCase):
    """A run with a recorded track measures via lyric_timing (tier 1)."""

    def setUp(self):
        tmp = tempfile.mkdtemp(prefix="f18-measure-")
        doc = os.path.join(tmp, "aligned.json")
        with open(doc, "w", encoding="utf-8") as f:
            json.dump({"alignedWords": [
                {"word": w["word"], "startS": w["start"], "endS": w["end"]}
                for w in SUNO_WORDS]}, f)
        calls_path = os.path.join(tmp, "calls")
        with open(calls_path, "w", encoding="utf-8") as f:
            f.write("0")
        self._env = {
            ENV_DOC: doc,
            ENV_CALLS: calls_path,
            "DRAMA75_TIMING_DISPATCHER":
                "test_caption_lyric_timing_f18:fake_dispatch",
            "DRAMA75_TIMING_TRACK": json.dumps(
                {"task_id": "t1", "audio_id": "a1"}),
        }
        for k, v in self._env.items():
            os.environ[k] = v
        os.environ.pop("DRAMA75_TIMING_OFF", None)

    def tearDown(self):
        for k in list(self._env) + ["DRAMA75_TIMING_OFF"]:
            os.environ.pop(k, None)

    def _calls(self):
        with open(os.environ[ENV_CALLS], encoding="utf-8") as f:
            return int(f.read().strip() or "0")

    def test_caption_check_measures_when_no_receipt_is_bound(self):
        # the reach-for-step path: module entry with timing=None measures now
        cues, rec = CT.captions(SHEET, None)
        self.assertTrue(rec["ok"], rec)
        self.assertEqual(rec["source"], "suno-timestamped-lyrics")
        self.assertEqual(self._calls(), 1)
        self.assertEqual(len(cues), 3)

    def test_lyric_check_measures_and_reports_source(self):
        observed, rec = CT.lyric_observed(LINES, None)
        self.assertTrue(rec["ok"], rec)
        self.assertEqual(rec["source"], "suno-timestamped-lyrics")
        self.assertEqual(self._calls(), 1)
        diff = music_qc.diff_lyrics(LINES, observed)
        self.assertEqual(diff["coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
