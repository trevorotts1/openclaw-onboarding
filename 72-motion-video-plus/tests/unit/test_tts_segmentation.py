"""Narration segmentation and production-order tests for Skill 72 (MG-020).

Proves mechanically that:
(a) a short narrated scene (well under the old 2,000-character floor)
    produces a single short transport chunk with no padding and no floor
    error, end to end through main() with a stubbed provider;
(b) a long narration segments at sentence boundaries under the
    transport cap and reassembles losslessly in order;
(c) a silent job exits 0 with the structured no-narration result and no
    TTS credential present in the environment;
(d) changing one word of the narration changes the narration
    fingerprint (and identical inputs reproduce it exactly);
(e) chunking never splits mid-sentence when a sentence boundary fits
    under the cap;
(f) the served-model verification from the original script is preserved:
    a provider fallback still hard-fails.

The provider is stubbed in every narrated test: no network, no real
credentials.

Run from the skill root:
    python3 -m unittest discover -s tests/unit
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[2]
TTS_PATH = SKILL_ROOT / "scripts" / "tts.py"

spec = importlib.util.spec_from_file_location("skill72_tts", TTS_PATH)
tts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tts)

SETTINGS = {"model": "s2.1-pro", "reference_id": "voice-1",
            "temperature": 0.4, "max_chars_per_request": 4000}
SHORT_TEXT = "First the work piles up. Then the system clears it."


def _write_manifest(directory: Path, manifest: dict) -> Path:
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _run_main(manifest_path: Path, outdir: Path):
    argv = ["tts.py", "--manifest", str(manifest_path), "--outdir", str(outdir)]
    with mock.patch.object(sys, "argv", argv):
        tts.main()


class SegmentationTests(unittest.TestCase):
    def test_short_scene_produces_one_unpadded_chunk(self):
        self.assertLess(len(SHORT_TEXT), 2000, "the fixture must sit under the old floor")
        plan = tts.plan_chunks([("scene-01", SHORT_TEXT)], 4000)
        self.assertEqual(1, len(plan), "a short scene is exactly one transport chunk")
        self.assertEqual(SHORT_TEXT, plan[0]["text"], "the chunk is the text itself, unpadded")
        self.assertEqual("scene-01", plan[0]["scene_id"])

    def test_long_narration_segments_at_sentence_boundaries(self):
        sentences = ["Sentence %02d walks the work item through one named stage." % i
                     for i in range(30)]
        text = " ".join(sentences)
        plan = tts.plan_chunks([("scene-01", text)], 200)
        self.assertGreater(len(plan), 3, "a long narration must need several chunks")
        for chunk in plan:
            self.assertLessEqual(len(chunk["text"]), 200, "every chunk respects the cap")
            self.assertTrue(chunk["text"].rstrip().endswith("."),
                            "every chunk ends at a sentence boundary")
        reassembled = "".join(c["text"] for c in plan)
        self.assertEqual(text, reassembled, "chunking is lossless and in order")

    def test_chunking_never_splits_mid_sentence_when_boundary_fits(self):
        s1 = "Alpha bravo charlie delta echo."
        s2 = "Foxtrot golf hotel india juliet."
        s3 = "Lima mike november oscar papa."
        text = " ".join([s1, s2, s3])
        spans = tts.split_sentence_spans(text)
        self.assertEqual(text, "".join(spans), "spans reassemble losslessly")
        # A cap that lands inside s2 for a naive fixed-width cutter:
        # sentence packing must break at the s1 boundary instead.
        cap = len(spans[0]) + 10
        chunks = [c["text"] for c in tts.plan_chunks([("scene-01", text)], cap)]
        self.assertEqual(spans, chunks, "chunks are whole sentence spans, never mid-sentence cuts")
        self.assertTrue(all(len(c) <= cap for c in chunks))

    def test_oversize_single_sentence_is_never_cut(self):
        text = "One very long sentence " + "with many trailing clauses " * 4 + "ends here."
        self.assertGreater(len(text), 50)
        chunks = [c["text"] for c in tts.plan_chunks([("scene-01", text)], 50)]
        self.assertEqual([text], chunks, "a lone oversize sentence travels whole, never cut")


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_is_stable_for_identical_inputs(self):
        texts = [("scene-01", "The system removes the bottleneck.")]
        self.assertEqual(tts.narration_fingerprint(texts, SETTINGS),
                         tts.narration_fingerprint(list(texts), dict(SETTINGS)))

    def test_one_word_change_changes_the_fingerprint(self):
        before = [("scene-01", "The system removes the bottleneck.")]
        after = [("scene-01", "The system clears the bottleneck.")]
        self.assertNotEqual(tts.narration_fingerprint(before, SETTINGS),
                            tts.narration_fingerprint(after, SETTINGS),
                            "a narration change must invalidate the fingerprint")

    def test_provider_setting_change_changes_the_fingerprint(self):
        texts = [("scene-01", "The system removes the bottleneck.")]
        changed = dict(SETTINGS, temperature=0.45)
        self.assertNotEqual(tts.narration_fingerprint(texts, SETTINGS),
                            tts.narration_fingerprint(texts, changed))


class RequirementTests(unittest.TestCase):
    def test_v2_silent_policies_need_no_narration(self):
        for audio in ({"mode": "none", "create_voiceover": False},
                      {"mode": "inherited", "create_voiceover": False},
                      {"mode": "own", "create_voiceover": False}):
            with self.subTest(audio=audio):
                manifest = {"audio": audio,
                            "scenes": [{"id": "bar-01", "spec": "scenes/bar-01.json"}]}
                required, _reason, texts = tts.narration_requirement(manifest)
                self.assertFalse(required)
                self.assertEqual([], texts)

    def test_v1_manifest_without_voiceover_text_is_silent(self):
        manifest = {"scenes": [{"id": "scene-01", "voiceover_text": "  "}]}
        required, _reason, _texts = tts.narration_requirement(manifest)
        self.assertFalse(required)

    def test_narration_is_required_when_text_is_present(self):
        manifest = {"scenes": [{"id": "scene-01", "voiceover_text": SHORT_TEXT}]}
        required, _reason, texts = tts.narration_requirement(manifest)
        self.assertTrue(required)
        self.assertEqual([("scene-01", SHORT_TEXT)], texts)


class CliTests(unittest.TestCase):
    def test_silent_job_exits_zero_without_any_credential(self):
        manifest = {"schema_version": "2.0", "mode": "powerpoint_graphic",
                    "audio": {"mode": "none", "parent_audio_ref": None,
                              "create_voiceover": False, "create_music": False,
                              "source_assets": []},
                    "scenes": [{"id": "bar-01", "spec": "scenes/bar-01.json"}]}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            manifest_path = _write_manifest(tmp, manifest)
            outdir = tmp / "audio"
            env = {k: v for k, v in os.environ.items() if k != "FISH_AUDIO_API_KEY"}
            proc = subprocess.run(
                [sys.executable, str(TTS_PATH), "--manifest", str(manifest_path),
                 "--outdir", str(outdir)],
                capture_output=True, text=True, env=env)
            self.assertEqual(0, proc.returncode,
                             "silent job must exit 0 with no credential; stderr: " + proc.stderr)
            printed = json.loads(proc.stdout)
            self.assertEqual("no_narration", printed["status"])
            self.assertIsNone(printed["narration_fingerprint"])
            recorded = json.loads((outdir / "durations.json").read_text(encoding="utf-8"))
            self.assertEqual("no_narration", recorded["status"])
            self.assertEqual({}, recorded["scenes"])

    def _stubbed_main(self, manifest, captured, served="s2.1-pro", duration=2.5):
        def fake_request(api_key, model, reference_id, temperature, text):
            captured.append(text)
            return b"fake-mp3-bytes", served

        def fake_run(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"")
            return subprocess.CompletedProcess(cmd, 0)

        tmp = tempfile.TemporaryDirectory()
        directory = Path(tmp.name)
        manifest_path = _write_manifest(directory, manifest)
        outdir = directory / "audio"
        with mock.patch.dict(os.environ, {"FISH_AUDIO_API_KEY": "test-only-not-a-credential"}), \
                mock.patch.object(tts, "tts_request", fake_request), \
                mock.patch.object(tts, "probe_duration", lambda path: duration), \
                mock.patch.object(tts.subprocess, "run", fake_run):
            _run_main(manifest_path, outdir)
        return tmp, outdir

    def test_short_narrated_scene_runs_end_to_end_unpadded(self):
        manifest = {"tts": {"model": "s2.1-pro", "reference_id": "voice-1", "temperature": 0.4},
                    "scenes": [{"id": "scene-01", "voiceover_text": SHORT_TEXT}]}
        captured = []
        tmp, outdir = self._stubbed_main(manifest, captured)
        with tmp:
            self.assertEqual([SHORT_TEXT], captured,
                             "the provider receives the short scene exactly, unpadded")
            record = json.loads((outdir / "durations.json").read_text(encoding="utf-8"))
            self.assertEqual("ok", record["status"])
            self.assertEqual({"scene-01": 2.5}, record["scenes"])
            self.assertTrue(record["narration_fingerprint"].startswith("sha256:"))
            self.assertEqual(1, len(record["chunks"]))

    def test_long_scene_chunks_through_main_under_the_cap(self):
        text = " ".join("Step %02d moves the same work item forward." % i for i in range(12))
        manifest = {"tts": {"model": "s2.1-pro", "reference_id": "voice-1",
                            "temperature": 0.4, "max_chars_per_request": 120},
                    "scenes": [{"id": "scene-01", "voiceover_text": text}]}
        captured = []
        tmp, outdir = self._stubbed_main(manifest, captured)
        with tmp:
            self.assertGreater(len(captured), 1, "the long scene must use several requests")
            self.assertTrue(all(len(c) <= 120 for c in captured))
            self.assertEqual(text, "".join(captured), "requests reassemble losslessly in order")
            record = json.loads((outdir / "durations.json").read_text(encoding="utf-8"))
            self.assertEqual(len(captured), len(record["chunks"]))

    def test_served_model_mismatch_still_hard_fails(self):
        manifest = {"tts": {"model": "s2.1-pro", "reference_id": "voice-1", "temperature": 0.4},
                    "scenes": [{"id": "scene-01", "voiceover_text": SHORT_TEXT}]}
        captured = []
        with self.assertRaises(SystemExit) as ctx:
            self._stubbed_main(manifest, captured, served="s2-pro")
        self.assertNotEqual(0, ctx.exception.code,
                            "a silent provider fallback must remain a hard failure")


if __name__ == "__main__":
    unittest.main()
