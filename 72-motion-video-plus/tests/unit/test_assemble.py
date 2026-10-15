"""MG-022: assembly implementation tests.

Unit tests cover the registry, the pure graph builder, plan
validation, and the legacy bridge's plan compilation. Integration
tests render real outputs with the box's ffmpeg and probe them:
the six acceptance examples (single-scene, multi-scene with
transitions, no-audio, narration-only, music/SFX, mixed-engine
labels) plus the legacy wrapper end to end. Defect regressions for
D-ASSEMBLE-TUPLE, D-ASSEMBLE-SINGLE-SCENE-FILTER,
D-ASSEMBLE-AUDIO-INDEX and D-ASSEMBLE-SHORTEST-SFX-DRIFT are named
after the defects they close; the pre-repair failures are reproduced
in tests/evidence/mg022/repro/.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILL = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPTS = os.path.join(SKILL, "scripts")
FIXTURES = os.path.join(SKILL, "tests", "fixtures", "assembly")

spec = importlib.util.spec_from_file_location(
    "assemble", os.path.join(SCRIPTS, "assemble.py"))
assemble = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assemble)

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def fake_job(scenes=1, narration=(), sfx=(), music=False, ducking=False,
             handles=(), total_frames=90):
    """A minimal job in the graph builder's shape (no files needed)."""
    job = assemble.empty_job("unit")
    job["fps"] = 30
    job["canvas"] = {"width": 320, "height": 180}
    cursor = 0
    for i in range(scenes):
        dur = 60
        job["scenes"].append({
            "id": "s%d" % i, "path": "/x/s%d.mp4" % i,
            "placed_start": cursor, "placed_end": cursor + dur,
            "source_start": 0, "source_end": dur})
        cursor += dur
    job["handles"] = list(handles)
    job["total_frames"] = total_frames
    job["total_samples"] = total_frames * 1600
    job["narration"] = [{"id": "n%d" % i, "path": "/x/n%d.wav" % i,
                         "start_sample": a, "end_sample": b}
                        for i, (a, b) in enumerate(narration)]
    job["sfx"] = [{"id": "x%d" % i, "path": "/x/x%d.wav" % i,
                   "sample": s, "file_samples": 9600}
                  for i, s in enumerate(sfx)]
    if music:
        job["music"] = {"path": "/x/music.wav"}
    job["mix"] = {"musicVolume": 0.35 if music else 1.0,
                  "ducking": (dict(assemble.LEGACY_DUCKING) if ducking else None)}
    job["audio_expected"] = bool(narration or sfx or music)
    return job


def graph_for(job):
    registry = assemble.InputRegistry()
    idx = assemble.register_inputs(job, registry)
    graph, has_audio = assemble.build_filter_complex(job, idx)
    return registry, graph, has_audio


class RegistryTests(unittest.TestCase):
    def test_indexes_are_sequential_and_typed(self):
        job = fake_job(scenes=2, narration=[(0, 96000)], music=True, sfx=[48000])
        registry, _, _ = graph_for(job)
        kinds = [(e["index"], e["kind"]) for e in registry.entries]
        self.assertEqual(kinds[0], (0, "scene"))
        self.assertEqual(kinds[1], (1, "scene"))
        self.assertEqual(kinds[2], (2, "narration"))
        self.assertEqual(kinds[3], (3, "music"))
        self.assertEqual(kinds[4], (4, "sfx"))
        self.assertEqual(kinds[5], (5, "canvas"))

    def test_registry_argv_pairs_every_input(self):
        registry = assemble.InputRegistry()
        registry.add("scene", "a", "/x/a.mp4")
        registry.add("canvas", "silence", "anullsrc=cl=stereo:r=48000",
                     pre_args=["-f", "lavfi", "-t", "3.000000"])
        argv = registry.argv()
        self.assertEqual(argv, ["-i", "/x/a.mp4", "-f", "lavfi", "-t",
                                "3.000000", "-i", "anullsrc=cl=stereo:r=48000"])

    def test_no_canvas_when_nothing_is_offset(self):
        job = fake_job(scenes=1, narration=[(0, 96000)])
        registry, _, _ = graph_for(job)
        self.assertNotIn("canvas", [e["kind"] for e in registry.entries])


class GraphTests(unittest.TestCase):
    def test_single_scene_terminates_with_a_filter(self):
        # D-ASSEMBLE-SINGLE-SCENE-FILTER: the old graph was
        # "[0:v][vout];", two labels and no filter.
        _, graph, _ = graph_for(fake_job(scenes=1, total_frames=60))
        self.assertIn("trim=end_frame=60,setpts=PTS-STARTPTS,format=yuv420p[vout]",
                      graph)
        self.assertNotIn("[vs0][vout]", graph)

    def test_no_shortest_anywhere(self):
        # D-ASSEMBLE-SHORTEST-SFX-DRIFT.
        for job in (fake_job(scenes=2, narration=[(0, 96000)], music=True,
                             ducking=True, sfx=[48000],
                             handles=[{"from": "s0", "to": "s1", "frames": 15}]),
                    fake_job(scenes=1)):
            _, graph, _ = graph_for(job)
            self.assertNotIn("shortest", graph)

    def test_audio_indexes_come_from_the_registry(self):
        # D-ASSEMBLE-AUDIO-INDEX: with two segments the narration is
        # input 2, never [0:a] (that is segment 1's slot).
        job = fake_job(scenes=2, narration=[(0, 96000)])
        _, graph, _ = graph_for(job)
        self.assertIn("[2:a]aresample=48000", graph)
        self.assertNotIn("[0:a]", graph)
        self.assertNotIn("[1:a]", graph)

    def test_xfade_offset_uses_the_plan_cursor(self):
        job = fake_job(scenes=2, total_frames=105,
                       handles=[{"from": "s0", "to": "s1", "frames": 15}])
        _, graph, _ = graph_for(job)
        # First scene 60 frames, overlap 15: offset (60-15)/30 = 1.5s.
        self.assertIn("xfade=transition=fade:duration=0.500000:offset=1.500000",
                      graph)
        self.assertIn("trim=end_frame=105", graph)

    def test_butt_join_uses_concat(self):
        job = fake_job(scenes=2, total_frames=120)
        _, graph, _ = graph_for(job)
        self.assertIn("concat=n=2:v=1:a=0[vx1]", graph)

    def test_ducking_splits_narration_and_keys_on_it(self):
        job = fake_job(scenes=1, narration=[(0, 96000)], music=True,
                       ducking=True)
        _, graph, _ = graph_for(job)
        self.assertIn("[narr]asplit=2[narr_mix][narr_key]", graph)
        self.assertIn("[mus][narr_key]sidechaincompress=threshold=0.02:"
                      "ratio=8:attack=20:release=400[mus_d]", graph)

    def test_no_audio_graph_when_plan_has_none(self):
        _, graph, has_audio = graph_for(fake_job(scenes=2, total_frames=120))
        self.assertFalse(has_audio)
        self.assertNotIn("[aout]", graph)

    def test_sfx_placement_is_sample_exact(self):
        job = fake_job(scenes=1, sfx=[84000])
        _, graph, _ = graph_for(job)
        # Pre-silence of exactly 84000 samples precedes the cue.
        self.assertIn("atrim=start_sample=0:end_sample=84000[cvp_sp0]", graph)

    def test_normalization_chain_present(self):
        _, graph, _ = graph_for(fake_job(scenes=1, total_frames=60))
        self.assertIn("scale=320:180,fps=30,settb=AVTB,format=yuv420p", graph)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe required")
class PlanValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mg022-unit-")
        subprocess.run([sys.executable, os.path.join(FIXTURES, "make_media.py"),
                        "multi", os.path.join(self.tmp, "media")],
                       check=True, capture_output=True)
        self.media = os.path.join(self.tmp, "media", "media.json")
        self.plan = os.path.join(FIXTURES, "plans", "multi.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def load(self):
        return assemble.job_from_plan(self.plan, None, self.media, "ffprobe")

    def test_valid_plan_loads(self):
        job = self.load()
        self.assertEqual(job["total_frames"], 150)
        self.assertEqual(job["total_samples"], 240000)
        self.assertEqual(len(job["scenes"]), 3)
        self.assertEqual(len(job["handles"]), 2)

    def test_missing_media_file_is_input_error(self):
        os.remove(os.path.join(self.tmp, "media", "scenes", "b.mp4"))
        with self.assertRaises(assemble.AssembleError) as cm:
            self.load()
        self.assertEqual(cm.exception.code, "ASSEMBLE_INPUT_MISSING")
        self.assertEqual(cm.exception.exit_code, assemble.EXIT_INPUT)

    def test_truncated_segment_is_plan_mismatch(self):
        seg = os.path.join(self.tmp, "media", "scenes", "a.mp4")
        short = os.path.join(self.tmp, "media", "scenes", "a-short.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", seg,
                        "-frames:v", "30", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", short], check=True)
        os.replace(short, seg)
        with self.assertRaises(assemble.AssembleError) as cm:
            self.load()
        self.assertEqual(cm.exception.code, "ASSEMBLE_MEDIA_SHORTER_THAN_PLAN")

    def test_inconsistent_sidecar_rejected(self):
        bad = json.load(open(self.plan))
        bad["sidecar"]["total_frames"] = 999
        path = os.path.join(self.tmp, "bad-plan.json")
        json.dump(bad, open(path, "w"))
        with self.assertRaises(assemble.AssembleError) as cm:
            assemble.job_from_plan(path, None, self.media, "ffprobe")
        self.assertEqual(cm.exception.code, "ASSEMBLE_PLAN_INCONSISTENT")


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe required")
class RenderTests(unittest.TestCase):
    """Real renders of the acceptance examples through the CLI."""

    def render(self, example):
        tmp = tempfile.mkdtemp(prefix="mg022-render-")
        media_dir = os.path.join(tmp, "media")
        subprocess.run([sys.executable,
                        os.path.join(FIXTURES, "make_media.py"), example, media_dir],
                       check=True, capture_output=True)
        out = os.path.join(tmp, "out.mp4")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "assemble.py"),
             "--plan", os.path.join(FIXTURES, "plans", example + ".json"),
             "--media", os.path.join(media_dir, "media.json"),
             "--out", out, "--workdir", os.path.join(tmp, "work")],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        record = json.loads(proc.stdout)
        self.addCleanup(shutil.rmtree, tmp, True)
        return record, out

    def test_single_scene(self):
        # Also the D-ASSEMBLE-SINGLE-SCENE-FILTER render regression.
        record, _ = self.render("single")
        self.assertEqual(record["decoded_frames"], 90)

    def test_multi_scene_transitions(self):
        record, _ = self.render("multi")
        self.assertEqual(record["decoded_frames"], 150)
        self.assertEqual(record["duration_seconds"], 5.0)

    def test_no_audio(self):
        record, _ = self.render("noaudio")
        self.assertEqual(record["decoded_frames"], 105)
        self.assertFalse(record["audio_present"])

    def test_narration_only(self):
        record, _ = self.render("narration")
        self.assertEqual(record["decoded_frames"], 105)
        self.assertTrue(record["audio_present"])

    def test_music_and_sfx(self):
        record, _ = self.render("musicsfx")
        self.assertEqual(record["decoded_frames"], 165)
        kinds = [e["kind"] for e in record["inputs"]]
        self.assertEqual(kinds, ["scene", "scene", "narration", "music",
                                 "sfx", "sfx", "canvas"])

    def test_mixed_engine_labels(self):
        record, _ = self.render("mixed")
        self.assertEqual(record["decoded_frames"], 150)
        prov = record["media_provenance"]
        self.assertTrue(prov["syntheticSegments"])
        self.assertEqual(prov["engines"],
                         {"a": "remotion", "b": "hyperframes", "c": "remotion"})

    def test_ffmpeg_failure_is_structured_not_traceback(self):
        tmp = tempfile.mkdtemp(prefix="mg022-fail-")
        self.addCleanup(shutil.rmtree, tmp, True)
        media_dir = os.path.join(tmp, "media")
        subprocess.run([sys.executable,
                        os.path.join(FIXTURES, "make_media.py"), "single", media_dir],
                       check=True, capture_output=True)
        # An odd canvas width passes plan validation but libx264 with
        # yuv420p cannot encode it: ffmpeg must fail, and the CLI must
        # answer with a structured finding (exit 5) and a retained
        # log, no traceback.
        media_path = os.path.join(media_dir, "media.json")
        media = json.load(open(media_path))
        media["canvas"]["width"] = 33
        json.dump(media, open(media_path, "w"))
        workdir = os.path.join(tmp, "work")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "assemble.py"),
             "--plan", os.path.join(FIXTURES, "plans", "single.json"),
             "--media", media_path,
             "--out", os.path.join(tmp, "out.mp4"),
             "--workdir", workdir],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, assemble.EXIT_FFMPEG)
        self.assertNotIn("Traceback", proc.stderr)
        finding = json.loads(proc.stderr)
        self.assertEqual(finding["code"], "ASSEMBLE_FFMPEG_FAILED")
        self.assertTrue(os.path.exists(os.path.join(workdir, "ffmpeg.log")))


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe required")
class LegacyBridgeTests(unittest.TestCase):
    """The pre-V2 manifest path, through the assemble.sh wrapper.
    Regressions: D-ASSEMBLE-TUPLE (the old script died on any input),
    D-ASSEMBLE-MUSIC-RESET, D-ASSEMBLE-SHORTEST-SFX-DRIFT."""

    def build_job(self, vo_seconds=2.4, music_bed=None):
        tmp = tempfile.mkdtemp(prefix="mg022-legacy-")
        self.addCleanup(shutil.rmtree, tmp, True)
        ff = ["ffmpeg", "-v", "error", "-y"]
        for sid, color in (("intro", "red"), ("outro", "blue")):
            d = os.path.join(tmp, "scenes", sid)
            os.makedirs(d)
            subprocess.run(ff + ["-f", "lavfi", "-i",
                                 "color=c=%s:s=640x360:r=30" % color,
                                 "-frames:v", "45", "-c:v", "libx264",
                                 "-pix_fmt", "yuv420p",
                                 os.path.join(d, sid + ".mp4")], check=True)
        vo = os.path.join(tmp, "vo.wav")
        subprocess.run(ff + ["-f", "lavfi", "-i",
                             "sine=frequency=440:duration=%s" % vo_seconds,
                             "-ar", "48000", vo], check=True)
        manifest = {"scenes": [{"id": "intro"},
                               {"id": "outro", "sfx_events": [
                                   {"sound": "pop", "at_seconds": 0.5}]}],
                    "music_bpm": 120, "music_seed": 7}
        if music_bed is not None:
            manifest["music_bed"] = music_bed
        mpath = os.path.join(tmp, "manifest.json")
        json.dump(manifest, open(mpath, "w"))
        return tmp, mpath, vo

    def test_wrapper_assembles(self):
        tmp, mpath, vo = self.build_job()
        out = os.path.join(tmp, "final.mp4")
        proc = subprocess.run(
            ["bash", os.path.join(SCRIPTS, "assemble.sh"),
             "--manifest", mpath, "--workdir", tmp, "--voiceover", vo,
             "--out", out], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        self.assertIn("assembled:", proc.stdout)
        record = json.load(open(os.path.join(tmp, "assemble-probe.json")))
        # Two 45-frame scenes with one 15-frame fade: 75 frames, 2.5s.
        self.assertEqual(record["decoded_frames"], 75)
        self.assertEqual(record["expected_frames"], 75)
        # The synthesized score is in the input registry: it was
        # actually mixed, not discarded (D-ASSEMBLE-MUSIC-RESET).
        kinds = [e["kind"] for e in record["inputs"]]
        self.assertIn("music", kinds)
        self.assertIn("sfx", kinds)
        # The pop is placed on the compiled timeline: intro placed
        # [0,45), outro at frame 30; event at 30 + 15 = frame 45.
        job = json.load(open(os.path.join(tmp, "legacy-plan", "job.json")))
        self.assertEqual(job["sfx"][0]["sample"], 45 * 1600)

    def test_long_voiceover_is_refused_not_cut(self):
        tmp, mpath, vo = self.build_job(vo_seconds=3.4)
        proc = subprocess.run(
            ["bash", os.path.join(SCRIPTS, "assemble.sh"),
             "--manifest", mpath, "--workdir", tmp, "--voiceover", vo,
             "--out", os.path.join(tmp, "final.mp4")],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, assemble.EXIT_PLAN)
        self.assertIn("ASSEMBLE_NARRATION_EXCEEDS_PICTURE", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_missing_voiceover_is_input_error(self):
        tmp, mpath, vo = self.build_job()
        proc = subprocess.run(
            ["bash", os.path.join(SCRIPTS, "assemble.sh"),
             "--manifest", mpath, "--workdir", tmp,
             "--voiceover", os.path.join(tmp, "nope.wav"),
             "--out", os.path.join(tmp, "final.mp4")],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, assemble.EXIT_INPUT)


if __name__ == "__main__":
    unittest.main()
