"""MG-023 tests: audio policy, mode-specific mixing, measured
loudness, and the D-ASSEMBLE-MUSIC-RESET repair at the plan layer.

scripts/audio_policy.py resolves audio sources ONCE from the
compiled plan (the timeline's audio_owner) and the media registry;
scripts/assemble.py consumes only the resolved plan. These tests
pin the modes (none / inherited / own), the resolution rules, the
measurement helpers, and the encoded-output verification:
silent output carries no unintended audio, inherited audio is not
duplicated (measured, not just stream-counted), the chosen score
is audible in the planned sections, and clipping and missing final
words fail by name.

Run from the skill root:  python3 -m unittest tests.unit.test_audio_policy
"""

import array
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

SKILL = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPTS = os.path.join(SKILL, "scripts")
FIXTURES = os.path.join(SKILL, "tests", "fixtures", "assembly")
sys.path.insert(0, SCRIPTS)

import assemble  # noqa: E402
import audio_policy  # noqa: E402

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
RATE = audio_policy.SAMPLE_RATE


def sine_samples(freq, seconds, amp=0.5, rate=RATE):
    n = int(seconds * rate)
    return array.array("h", [int(amp * 32767 * math.sin(2 * math.pi * freq * i / rate))
                             for i in range(n)])


class ResolutionTests(unittest.TestCase):
    """resolve_audio_plan: modes, rules, and defaults, no ffmpeg."""

    def test_owner_mapping(self):
        plan = audio_policy.resolve_audio_plan("none", [], [], {})
        self.assertEqual(plan["mode"], "none")
        self.assertIsNone(plan["music"])
        self.assertIsNone(plan["loudnessTarget"])
        plan = audio_policy.resolve_audio_plan("parent", [], [], {})
        self.assertEqual(plan["mode"], "inherited")
        plan = audio_policy.resolve_audio_plan("self", ["n1"], [],
                                               {"music": {"path": "m.wav"}})
        self.assertEqual(plan["mode"], "own")
        self.assertEqual(plan["music"], {"kind": "supplied", "path": "m.wav"})

    def test_unknown_owner_fails_as_mode_mismatch(self):
        with self.assertRaises(audio_policy.AudioPolicyError) as cm:
            audio_policy.resolve_audio_plan("sideways", [], [], {})
        err = cm.exception
        self.assertEqual(err.code, "ASSEMBLE_AUDIO_MODE_VIOLATION")
        self.assertEqual(err.exit_code, 4)
        self.assertEqual(err.mg_category, "MG_MODE_MISMATCH")

    def test_none_mode_rejects_any_audio(self):
        for media, narr, sfx in (({"music": {"path": "m.wav"}}, [], []),
                                 ({}, ["n1"], []),
                                 ({}, [], ["x1"])):
            with self.assertRaises(audio_policy.AudioPolicyError) as cm:
                audio_policy.resolve_audio_plan("none", narr, sfx, media)
            self.assertEqual(cm.exception.code,
                             "ASSEMBLE_AUDIO_MODE_VIOLATION")

    def test_inherited_excludes_registry_music_and_records_it(self):
        plan = audio_policy.resolve_audio_plan(
            "parent", [], [], {"music": {"path": "audio/music.wav"}})
        self.assertIsNone(plan["music"])
        self.assertEqual(len(plan["exclusions"]), 1)
        self.assertEqual(plan["exclusions"][0]["code"],
                         "ASSEMBLE_AUDIO_PARENT_OWNED")
        self.assertIsNone(plan["loudnessTarget"])

    def test_inherited_rejects_placed_narration(self):
        # A second narrator under the parent's narration is a
        # defect, not a variation.
        with self.assertRaises(audio_policy.AudioPolicyError):
            audio_policy.resolve_audio_plan("parent", ["n1"], [], {})

    def test_own_defaults_ducking_and_loudness(self):
        plan = audio_policy.resolve_audio_plan(
            "self", ["n1"], [], {"music": {"path": "m.wav"}})
        self.assertEqual(plan["mix"]["ducking"], audio_policy.DEFAULT_DUCKING)
        self.assertEqual(plan["mix"]["musicVolume"], 1.0)
        self.assertEqual(plan["loudnessTarget"],
                         {"integratedLufs": -14.0, "truePeakDb": -1.0})

    def test_own_music_without_narration_gets_no_ducking(self):
        plan = audio_policy.resolve_audio_plan(
            "self", [], [], {"music": {"path": "m.wav"}})
        self.assertIsNone(plan["mix"]["ducking"])
        self.assertIsNotNone(plan["loudnessTarget"])

    def test_declared_ducking_null_is_honored(self):
        plan = audio_policy.resolve_audio_plan(
            "self", ["n1"], [],
            {"music": {"path": "m.wav"}, "mix": {"ducking": None}})
        self.assertIsNone(plan["mix"]["ducking"])

    def test_audio_record_wins_over_mix_record(self):
        plan = audio_policy.resolve_audio_plan(
            "self", [], [],
            {"music": {"path": "m.wav"},
             "mix": {"musicVolume": 0.4},
             "audio": {"musicVolume": 0.7}})
        self.assertEqual(plan["mix"]["musicVolume"], 0.7)

    def test_registry_mode_contradiction_fails(self):
        with self.assertRaises(audio_policy.AudioPolicyError) as cm:
            audio_policy.resolve_audio_plan(
                "none", [], [], {"audio": {"mode": "own"}})
        self.assertEqual(cm.exception.code, "ASSEMBLE_AUDIO_MODE_VIOLATION")

    def test_synthesized_declaration(self):
        plan = audio_policy.resolve_audio_plan(
            "self", [], [], {"music": {"synthesized": {"bpm": 120, "seed": 7}}})
        self.assertEqual(plan["music"]["kind"], "synthesized")
        self.assertEqual(plan["music"]["bpm"], 120)
        self.assertEqual(plan["music"]["seed"], 7)
        self.assertIsNone(plan["music"]["path"])

    def test_malformed_music_declaration_fails(self):
        with self.assertRaises(audio_policy.AudioPolicyError):
            audio_policy.resolve_audio_plan(
                "self", [], [], {"music": {"url": "https://example.invalid/x"}})


class MeasurementTests(unittest.TestCase):
    """The measurement helpers, on in-memory sample arrays."""

    def test_clipping_report(self):
        square = array.array("h", [32767, -32768] * 24000)
        rep = audio_policy.clipping_report(square)
        self.assertTrue(rep["clipped"])
        self.assertEqual(rep["fullScaleRatio"], 1.0)
        tone = sine_samples(440, 1.0, amp=0.5)
        rep = audio_policy.clipping_report(tone)
        self.assertFalse(rep["clipped"])
        self.assertAlmostEqual(rep["peakDbfs"], -6.02, delta=0.05)
        self.assertFalse(audio_policy.clipping_report(
            array.array("h", bytes(96000)))["clipped"])

    def test_longest_gap(self):
        self.assertEqual(audio_policy.longest_gap([(48000, 96000)], 264000),
                         (96000, 264000))
        self.assertEqual(audio_policy.longest_gap([], 264000), (0, 264000))
        # Overlapping ranges merge before gaps are measured.
        self.assertEqual(audio_policy.longest_gap(
            [(4800, 9600), (7200, 14400)], 48000), (14400, 48000))
        # A gap shorter than the 0.3 s floor does not qualify.
        self.assertIsNone(audio_policy.longest_gap([(0, 264000)], 264000))

    def test_band_presence_self_and_silence(self):
        tone = sine_samples(440, 2.0, amp=0.5)
        rep = audio_policy.segment_presence_report(tone, tone, 0, len(tone))
        self.assertTrue(rep["present"])
        self.assertGreater(rep["bandRatio"], 0.9)
        silence = array.array("h", bytes(len(tone) * 2))
        rep = audio_policy.segment_presence_report(silence, tone, 0, len(tone))
        self.assertFalse(rep["present"])
        self.assertEqual(rep["bandRatio"], 0.0)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe required")
class AssembledAudioTests(unittest.TestCase):
    """End-to-end CLI renders judged on the encoded output."""

    def render(self, example, plan_mutator=None, media_mutator=None):
        tmp = tempfile.mkdtemp(prefix="mg023-render-")
        self.addCleanup(shutil.rmtree, tmp, True)
        media_dir = os.path.join(tmp, "media")
        subprocess.run([sys.executable,
                        os.path.join(FIXTURES, "make_media.py"), example, media_dir],
                       check=True, capture_output=True)
        plan_path = os.path.join(FIXTURES, "plans", example + ".json")
        if plan_mutator:
            plan = json.load(open(plan_path))
            plan_mutator(plan)
            plan_path = os.path.join(tmp, "plan.json")
            json.dump(plan, open(plan_path, "w"))
        media_path = os.path.join(media_dir, "media.json")
        if media_mutator:
            media = json.load(open(media_path))
            media_mutator(media, media_dir)
            json.dump(media, open(media_path, "w"))
        out = os.path.join(tmp, "out.mp4")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "assemble.py"),
             "--plan", plan_path, "--media", media_path,
             "--out", out, "--workdir", os.path.join(tmp, "work")],
            capture_output=True, text=True)
        return proc, out, media_dir

    def test_none_mode_output_is_silent(self):
        proc, out, _ = self.render("noaudio")
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        record = json.loads(proc.stdout)
        self.assertEqual(record["audio_plan"]["mode"], "none")
        self.assertFalse(record["audio_present"])

    def test_inherited_audio_is_not_duplicated(self):
        # The package carries a music bed (220/330 Hz) but the
        # parent owns the soundtrack: the insert must add neither a
        # narrator nor a second bed.
        proc, out, media_dir = self.render("inherited")
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        record = json.loads(proc.stdout)
        plan = record["audio_plan"]
        self.assertEqual(plan["mode"], "inherited")
        self.assertIsNone(plan["music"])
        self.assertEqual(plan["exclusions"][0]["code"],
                         "ASSEMBLE_AUDIO_PARENT_OWNED")
        self.assertFalse(record["audio_present"])
        # Measured contrast: the identical package resolved as own
        # DOES carry the bed (220 Hz band amplitude in the thousands
        # of int16 units); the inherited deliverable has no audio to
        # measure at all.
        proc2, out2, _ = self.render(
            "inherited",
            plan_mutator=lambda p: p["timeline"].__setitem__("audio_owner", "self"))
        self.assertEqual(proc2.returncode, 0, proc2.stderr[-800:])
        samples = audio_policy.decode_pcm(FFMPEG, out2)
        amp = audio_policy.band_amplitude(samples[RATE:2 * RATE], RATE, 220)
        self.assertGreater(amp, 1000.0)

    def test_own_mode_measured_loudness_stems_and_score(self):
        proc, out, _ = self.render("ownmix")
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        record = json.loads(proc.stdout)
        plan = record["audio_plan"]
        # The spec declares musicVolume only: the ducking default is
        # policy, so it appears in the RESOLVED plan, not the input.
        self.assertEqual(plan["mix"]["ducking"], audio_policy.DEFAULT_DUCKING)
        self.assertEqual(plan["mix"]["musicVolume"], 0.9)
        qc = record["audio_qc"]
        loud = qc["loudness"]
        self.assertTrue(loud["ok"])
        self.assertAlmostEqual(loud["measured"]["integratedLufs"], -14.0,
                               delta=audio_policy.LOUDNESS_TOLERANCE_LU)
        self.assertLessEqual(loud["measured"]["truePeakDb"], -1.0 + 0.5)
        self.assertTrue(qc["scoreAudible"]["audible"])
        self.assertGreater(qc["scoreAudible"]["windowRmsDbfs"], -45.0)
        self.assertTrue(qc["finalWords"]["presentAtPlannedEnd"])
        # Stems preserved, one per contributing role, and audible.
        self.assertEqual(sorted(record["stems"]), ["music", "narration", "sfx"])
        for role, stem_path in record["stems"].items():
            self.assertTrue(os.path.exists(stem_path))
            samples = audio_policy.decode_pcm(FFMPEG, stem_path)
            self.assertGreater(audio_policy.rms_dbfs(samples), -45.0, role)

    def test_synthesized_score_resolved_once_and_audible(self):
        tmp = tempfile.mkdtemp(prefix="mg023-synth-")
        self.addCleanup(shutil.rmtree, tmp, True)
        media_dir = os.path.join(tmp, "media")
        subprocess.run([sys.executable,
                        os.path.join(FIXTURES, "make_media.py"), "synthown", media_dir],
                       check=True, capture_output=True)

        def run_once(tag):
            proc = subprocess.run(
                [sys.executable, os.path.join(SCRIPTS, "assemble.py"),
                 "--plan", os.path.join(FIXTURES, "plans", "synthown.json"),
                 "--media", os.path.join(media_dir, "media.json"),
                 "--out", os.path.join(tmp, "out-%s.mp4" % tag),
                 "--workdir", os.path.join(tmp, "work-%s" % tag)],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
            return json.loads(proc.stdout)

        record = run_once("a")
        music = record["audio_plan"]["music"]
        self.assertEqual(music["kind"], "synthesized")
        produced = os.path.join(media_dir, "generated", "score.wav")
        self.assertEqual(music["path"], produced)
        self.assertTrue(os.path.exists(produced))
        with open(produced, "rb") as f:
            first_bytes = f.read()
        first_mtime = os.stat(produced).st_mtime_ns
        self.assertTrue(record["audio_qc"]["scoreAudible"]["audible"])
        # A second assembly over the SAME media package reuses the
        # produced score byte for byte (same bpm, seed, duration):
        # resolution executed the synthesis exactly once.
        run_once("b")
        with open(produced, "rb") as f:
            self.assertEqual(f.read(), first_bytes)
        self.assertEqual(os.stat(produced).st_mtime_ns, first_mtime)

    def test_clipped_source_fails_by_name(self):
        def clip_source(media, media_dir):
            path = os.path.join(media_dir, "audio", "n1.wav")
            with wave.open(path, "rb") as w:
                frames, channels = w.getnframes(), w.getnchannels()
            with wave.open(path, "wb") as w:
                w.setnchannels(channels)
                w.setsampwidth(2)
                w.setframerate(RATE)
                # Full-scale square wave, the SAME value in every
                # channel per frame (a per-sample alternation would
                # be anti-phase between channels and cancel in the
                # mono decode, which is a fixture artifact, not the
                # clipping under test).
                square = array.array("h")
                for f in range(frames):
                    v = 32767 if (f // 50) % 2 == 0 else -32767
                    square.extend([v] * channels)
                w.writeframes(square.tobytes())

        proc, _, _ = self.render("narration", media_mutator=clip_source)
        self.assertEqual(proc.returncode, assemble.EXIT_VERIFY)
        finding = json.loads(proc.stderr)
        self.assertEqual(finding["code"], "ASSEMBLE_AUDIO_CLIPPING")
        self.assertEqual(finding["mg_category"], "MG_QC_FAILED")

    def test_audio_injected_into_none_mode_fails_by_name(self):
        def inject_music(media, media_dir):
            media["music"] = {"path": "audio/music.wav"}
            tone = sine_samples(220, 3.5, amp=0.5)
            with wave.open(os.path.join(media_dir, "audio", "music.wav"),
                           "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(tone.tobytes())

        proc, _, _ = self.render("noaudio", media_mutator=inject_music)
        self.assertEqual(proc.returncode, 4)
        finding = json.loads(proc.stderr)
        self.assertEqual(finding["code"], "ASSEMBLE_AUDIO_MODE_VIOLATION")
        self.assertEqual(finding["mg_category"], "MG_MODE_MISMATCH")


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe required")
class VerifyAudioTests(unittest.TestCase):
    """verify_audio against doctored outputs: QC failures by name."""

    def build_job(self, example):
        tmp = tempfile.mkdtemp(prefix="mg023-verify-")
        self.addCleanup(shutil.rmtree, tmp, True)
        media_dir = os.path.join(tmp, "media")
        subprocess.run([sys.executable,
                        os.path.join(FIXTURES, "make_media.py"), example, media_dir],
                       check=True, capture_output=True)
        job = assemble.job_from_plan(
            os.path.join(FIXTURES, "plans", example + ".json"), None,
            os.path.join(media_dir, "media.json"), shutil.which("ffprobe"))
        out = os.path.join(tmp, "out.mp4")
        assemble.run_assembly(job, out, os.path.join(tmp, "work"),
                              FFMPEG, shutil.which("ffprobe"))
        return job, out, tmp

    def doctor(self, out, tmp, audio_filter, name):
        doctored = os.path.join(tmp, name)
        proc = subprocess.run(
            [FFMPEG, "-y", "-i", out, "-af", audio_filter,
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", doctored],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
        return doctored

    def test_missing_final_words_fail_by_name(self):
        job, out, tmp = self.build_job("narration")
        # Silence exactly the final segment's measured tail
        # (the narration example runs 3.5 s; its tail window opens
        # at 3.2 s). Broadband loudness barely moves; the words go.
        doctored = self.doctor(out, tmp, "volume=0:enable='gte(t,3.2)'",
                               "noend.mp4")
        with self.assertRaises(assemble.AssembleError) as cm:
            assemble.verify_audio(FFMPEG, doctored, job)
        self.assertEqual(cm.exception.code,
                         "ASSEMBLE_AUDIO_FINAL_WORDS_MISSING")
        self.assertEqual(cm.exception.mg_category, "MG_QC_FAILED")

    def test_off_target_loudness_fails_by_name(self):
        job, out, tmp = self.build_job("narration")
        doctored = self.doctor(out, tmp, "volume=2", "loud.mp4")
        with self.assertRaises(assemble.AssembleError) as cm:
            assemble.verify_audio(FFMPEG, doctored, job)
        self.assertEqual(cm.exception.code,
                         "ASSEMBLE_AUDIO_LOUDNESS_OFF_TARGET")

    def test_clipped_output_fails_by_name(self):
        job, out, tmp = self.build_job("narration")
        doctored = self.doctor(out, tmp, "volume=8", "clipped.mp4")
        with self.assertRaises(assemble.AssembleError) as cm:
            assemble.verify_audio(FFMPEG, doctored, job)
        self.assertEqual(cm.exception.code, "ASSEMBLE_AUDIO_CLIPPING")


if __name__ == "__main__":
    unittest.main()
