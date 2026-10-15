"""MG-039 standalone motion-video delivery: integration tests.

Drives both governed example packages (tests/fixtures/standalone/
narrated and .../silent) end to end through scripts/build_standalone.py:
contracts gate, MG-021 compile, routed adapter renders, MG-022 assembly
under the MG-023 audio plan, Section 17.2 poster, MG-031 coverage,
MG-032 proof, MG-033 review surface, MG-034 QC gate, and the delivery
record. Then checks the acceptance negatives: a delivery record
claiming an absent or hash-mismatched asset fails by name, coverage
that omits the ending cannot pass, and an ending that is not a designed
final state (a black tail beyond the plan) fails QC by name. The 9:16
package is proven at the scope the directive allows for fixtures: its
configuration validates under the same contracts classification gate,
its program compiles, and its proof scene renders genuinely recomposed
(MG-032 measures the portrait geometry on decoded frames).

The builds are the expensive part and run once per class. Everything
stages under the worktree's .scratch directory on the home filesystem.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = SKILL_DIR.parent
FIXTURES = SKILL_DIR / "tests" / "fixtures" / "standalone"
SCRATCH = REPO_ROOT / ".scratch" / "test-standalone"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_standalone = load_module("build_standalone", SKILL_DIR / "scripts" / "build_standalone.py")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def ffprobe_streams(path: Path) -> list:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    return json.loads(proc.stdout)["streams"]


def run_build(package: Path, stage: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, TMPDIR=str(REPO_ROOT / ".scratch" / "tmp"))
    return subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts" / "build_standalone.py"),
         "build", "--package", str(package), "--stage", str(stage)],
        capture_output=True, text=True, env=env,
    )


def ensure_runtime() -> None:
    runtime = SKILL_DIR / "runtime"
    if not (runtime / "node_modules").is_dir():
        subprocess.run(["npm", "ci"], cwd=runtime, check=True,
                       capture_output=True, text=True)
    if not (runtime / "dist" / "src" / "standalone" / "cli.js").is_file():
        subprocess.run(["npm", "run", "build"], cwd=runtime, check=True,
                       capture_output=True, text=True)
    current = REPO_ROOT / "shared-utils" / "motion-render-runtime" / ".runtime" / "current"
    if not current.is_dir():
        env = dict(os.environ, MOTION_RUNTIME_SKIP_APT="1")
        subprocess.run(
            ["bash", "shared-utils/motion-render-runtime/provision.sh"],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True, env=env,
        )


TOOLS_PRESENT = all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe", "node", "python3"))


@unittest.skipUnless(TOOLS_PRESENT, "ffmpeg, ffprobe, node, and python3 are required")
class StandaloneBuildTests(unittest.TestCase):
    """Both examples, built once and examined from every angle."""

    stages: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        ensure_runtime()
        SCRATCH.mkdir(parents=True, exist_ok=True)
        for name in ("narrated", "silent"):
            shutil.rmtree(SCRATCH / f"stage-{name}", ignore_errors=True)
        cls.stages = {}
        for name in ("narrated", "silent"):
            stage = SCRATCH / f"stage-{name}"
            proc = run_build(FIXTURES / name, stage)
            cls.stages[name] = {"stage": stage, "proc": proc}
            if proc.returncode != 0:
                raise AssertionError(
                    f"standalone build for {name} failed:\n{proc.stdout[-3000:]}\n{proc.stderr[-1500:]}"
                )

    @classmethod
    def tearDownClass(cls) -> None:
        for name in ("stage-narrated", "stage-silent", "negative-delivery",
                     "negative-coverage", "negative-black-tail"):
            shutil.rmtree(SCRATCH / name, ignore_errors=True)

    def job_dir(self, name: str) -> Path:
        return self.stages[name]["stage"] / "job"

    # -- end-to-end shape --------------------------------------------

    def test_both_builds_produce_a_complete_delivery_record(self):
        for name in ("narrated", "silent"):
            job = self.job_dir(name)
            record = read_json(job / "delivery" / "deliverables.json")
            self.assertEqual(record["mode"], "standalone_video")
            self.assertEqual(record["total_frames"], 405)
            kinds = {a["kind"] for a in record["assets"]}
            for required in ("final_mp4", "poster", "source_package", "placement_metadata",
                             "review_record", "qc_record", "coverage_record", "motion_proof",
                             "timeline", "timeline_sidecar"):
                self.assertIn(required, kinds, f"{name} delivery record lacks {required}")
            self.assertEqual(
                build_standalone.verify_job_dir(job), [],
                f"{name} delivery record does not verify against its own assets",
            )
            self.assertEqual(record["verification"]["qc_verdict"], "pass")
            self.assertEqual(record["verification"]["coverage_verdict"], "complete")
            self.assertEqual(record["verification"]["proof_verdict"], "pass")

    def test_story_progression_scales_and_proof_peak(self):
        plan = read_json(FIXTURES / "silent" / "build-plan.json")
        roles = [scene["role"] for scene in plan["scenes"]]
        self.assertEqual(roles, ["opening", "development", "proof_peak", "ending"])
        scales = {scene["shot_scale"] for scene in plan["scenes"]}
        self.assertGreaterEqual(len(scales), 2)
        timeline = read_json(self.job_dir("silent") / "timeline.json")
        events = {(e["scene_id"], e["type"]) for e in timeline["events"]}
        self.assertIn(("proof-chart", "proof"), events)
        self.assertIn(("final-state", "hold_start"), events)
        placed = {s["id"]: s for s in timeline["scenes"]}
        self.assertEqual(placed["open-reveal"]["start_frame"], 0)
        self.assertEqual(placed["final-state"]["end_frame_exclusive"], timeline["total_frames"])

    def test_coverage_includes_the_ending(self):
        for name in ("narrated", "silent"):
            job = self.job_dir(name)
            coverage = read_json(next((job / "review").glob("*__coverage.json")))
            self.assertEqual(coverage["verdict"], "complete")
            self.assertEqual(coverage["coverage"]["omitted_frames"], 0)
            frames = {sample["frame"] for sample in coverage["samples"]}
            self.assertIn(404, frames, "the final frame (the ending) is not sampled")

    def test_qc_verdict_pass_for_both(self):
        for name in ("narrated", "silent"):
            qc = read_json(self.job_dir(name) / "qc" / "final-qc.json")
            self.assertEqual(qc["verdict"], "pass")
            failed = [c for c in qc["checks"] if c["status"] == "FAIL"]
            self.assertEqual(failed, [])

    def test_poster_is_the_declared_final_state_frame(self):
        for name in ("narrated", "silent"):
            job = self.job_dir(name)
            record = read_json(job / "delivery" / "deliverables.json")
            self.assertEqual(record["poster_frame"], 390)
            poster = job / "delivery" / "poster.png"
            streams = ffprobe_streams(poster)
            self.assertEqual((streams[0]["width"], streams[0]["height"]), (1920, 1080))
            raw = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(poster), "-vf", "format=gray",
                 "-f", "rawvideo", "-"],
                capture_output=True,
            )
            mean = sum(raw.stdout) / len(raw.stdout)
            self.assertGreater(mean, 16.0, "poster frame is effectively black")

    # -- audio plan fidelity ------------------------------------------

    def test_narrated_audio_follows_the_declared_plan(self):
        stage = self.stages["narrated"]["stage"]
        job = self.job_dir("narrated")
        streams = ffprobe_streams(job / "renders" / "final.mp4")
        self.assertIn("audio", {s["codec_type"] for s in streams})
        probe = read_json(stage / "assemble" / "assemble-probe.json")
        audio_qc = probe["audio_qc"]
        self.assertEqual(audio_qc["mode"], "own")
        self.assertTrue(audio_qc["loudness"]["ok"], "loudness is not on target")
        spans = audio_qc["narrationSpans"]
        self.assertEqual(len(spans), 4)
        for segment_id, span in spans.items():
            self.assertTrue(span["present"], f"{segment_id} not present in the encoded output")
        self.assertTrue(audio_qc["finalWords"]["presentAtPlannedEnd"],
                        "final narration words are not intact at the planned end")
        self.assertTrue(audio_qc["scoreAudible"]["audible"], "declared music is not audible")
        measurements = read_json(job / "delivery" / "audio-measurements.json")
        self.assertIsInstance(measurements["integrated_lufs"], (int, float))
        self.assertTrue(measurements["loudness_on_target"])
        for stem in ("narration", "music", "sfx"):
            self.assertTrue((job / "delivery" / "stems" / f"{stem}.wav").is_file())
        captions = (job / "delivery" / "captions.srt").read_text(encoding="utf-8")
        self.assertEqual(captions.count(" --> "), 4)

    def test_silent_example_carries_no_audio_and_its_plan_says_none(self):
        job = self.job_dir("silent")
        streams = ffprobe_streams(job / "renders" / "final.mp4")
        self.assertNotIn("audio", {s["codec_type"] for s in streams})
        timeline = read_json(job / "timeline.json")
        self.assertEqual(timeline["audio_owner"], "none")
        media = read_json(job / "media.json")
        self.assertEqual(media["narration"], [])
        self.assertEqual(media["sfx"], [])
        self.assertNotIn("music", media)
        self.assertFalse((job / "delivery" / "stems").exists())
        self.assertFalse((job / "delivery" / "captions.srt").exists())

    # -- negatives ------------------------------------------------------

    def test_delivery_record_fails_by_name_for_absent_or_tampered_assets(self):
        job = self.job_dir("silent")
        staging = SCRATCH / "negative-delivery"
        copy = staging / "job"
        shutil.copytree(job, copy)
        (copy / "delivery" / "poster.png").unlink()
        failures = build_standalone.verify_job_dir(copy)
        self.assertTrue(
            any("poster" in failure for failure in failures),
            f"absent poster not named in failures: {failures}",
        )
        shutil.rmtree(staging)
        shutil.copytree(job, copy)
        record_path = copy / "delivery" / "deliverables.json"
        record = read_json(record_path)
        for entry in record["assets"]:
            if entry["kind"] == "timeline":
                entry["sha256"] = "0" * 64
        record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        failures = build_standalone.verify_job_dir(copy)
        self.assertTrue(
            any("timeline" in failure and "mismatch" in failure for failure in failures),
            f"tampered timeline hash not named in failures: {failures}",
        )

    def test_coverage_omitting_the_ending_cannot_pass(self):
        job = self.job_dir("silent")
        work = SCRATCH / "negative-coverage"
        work.mkdir()
        truncated = work / "truncated.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(job / "renders" / "final.mp4"),
             "-frames:v", "300", "-c", "copy", str(truncated)],
            check=True, capture_output=True,
        )
        outdir = work / "bundle"
        proc = subprocess.run(
            [sys.executable, str(SKILL_DIR / "scripts" / "critique_bundle.py"), "build",
             "--video", str(truncated), "--outdir", str(outdir),
             "--job-id", "fixture-standalone-silent",
             "--timeline", str(job / "timeline.json"),
             "--sidecar", str(job / "timeline-sidecar.json"), "--interval", "1"],
            capture_output=True, text=True,
        )
        record_path = outdir / "fixture-standalone-silent__coverage.json"
        verdict = read_json(record_path)["verdict"] if record_path.is_file() else None
        self.assertNotEqual(verdict, "complete",
                            "a piece missing its ending produced complete coverage")
        self.assertTrue(proc.returncode != 0 or verdict != "complete")

    def test_black_tail_beyond_the_plan_fails_qc_by_name(self):
        job = self.job_dir("silent")
        qc_script = build_standalone.resolve_qc_script(None)
        staging = SCRATCH / "negative-black-tail"
        copy = staging / "job"
        shutil.copytree(job, copy)
        black = staging / "black.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
             "-i", "color=c=black:s=1920x1080:r=30:d=2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(black)],
            check=True, capture_output=True,
        )
        tailed = staging / "tailed.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(copy / "renders" / "final.mp4"),
             "-i", str(black), "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
             "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tailed)],
            check=True, capture_output=True,
        )
        shutil.move(str(tailed), str(copy / "renders" / "final.mp4"))
        proc = subprocess.run(
            [sys.executable, str(qc_script), "check", "--job-dir", str(copy)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0, "QC passed a final with a black tail")
        report = read_json(copy / "qc" / "final-qc.json")
        self.assertNotEqual(report["verdict"], "pass")
        failed = [c for c in report["checks"] if c["status"] == "FAIL"]
        named = json.dumps(failed)
        self.assertTrue(
            "QC_BLACK_UNAPPROVED" in named or "frame_count" in named or "QC_FRAME" in named,
            f"no failure names the black tail or the frame count: {named[:600]}",
        )


@unittest.skipUnless(TOOLS_PRESENT, "ffmpeg, ffprobe, node, and python3 are required")
class PortraitVariantTests(unittest.TestCase):
    """The 9:16 variant: validated, compiled, one scene recomposed."""

    @classmethod
    def setUpClass(cls) -> None:
        ensure_runtime()
        cls.work = SCRATCH / "portrait"
        shutil.rmtree(cls.work, ignore_errors=True)
        cls.work.mkdir(parents=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(SCRATCH / "portrait", ignore_errors=True)

    def test_portrait_configuration_validates_and_compiles(self):
        findings = build_standalone.motion_contracts.validate_job(FIXTURES / "portrait")
        blocking = [
            f for f in findings
            if f["path"].split("#")[0] not in build_standalone.C01_SPEC_FILES
        ]
        self.assertEqual(blocking, [])
        manifest = read_json(FIXTURES / "portrait" / "manifest.json")
        self.assertEqual((manifest["canvas"]["width"], manifest["canvas"]["height"]), (1080, 1920))
        timeline = read_json(FIXTURES / "portrait" / "timeline.json")
        self.assertEqual(timeline["total_frames"], 405)
        design = read_json(FIXTURES / "portrait" / "design.json")
        self.assertNotEqual(
            design["layouts"]["portrait"]["plot"], design["layouts"]["landscape"]["plot"],
            "portrait reuses the landscape plot: that is a crop, not a recomposition")
        spec = read_json(FIXTURES / "portrait" / "scenes" / "proof-chart.json")
        self.assertEqual(spec["layout_variant"], "portrait")
        half = next(a for a in spec["semantic_motion_assertions"] if a["id"] == "half-reveal")
        self.assertEqual(half["expected_values"], [148.0, 222.0, 370.0],
                         "portrait proof geometry is not the recomposed scale")

    def test_portrait_proof_scene_renders_recomposed(self):
        # A single-scene portrait package through the same driver: the
        # proof scene's shell renders at 1080x1920 and MG-032 measures
        # the portrait bar geometry on decoded frames.
        package = self.work / "package"
        shutil.copytree(FIXTURES / "portrait", package)
        manifest = read_json(package / "manifest.json")
        manifest["scenes"] = [e for e in manifest["scenes"] if e["id"] == "proof-chart"]
        manifest["duration_frames"] = 150
        (package / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        storyboard = read_json(package / "storyboard.json")
        storyboard["beats"] = [b for b in storyboard["beats"] if b["scene_id"] == "proof-chart"]
        (package / "storyboard.json").write_text(json.dumps(storyboard, indent=2) + "\n", encoding="utf-8")
        plan = read_json(package / "build-plan.json")
        plan["scenes"] = [s for s in plan["scenes"] if s["id"] == "proof-chart"]
        plan["transitions"] = []
        (package / "build-plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        stage = self.work / "stage"
        cli = SKILL_DIR / "runtime" / "dist" / "src" / "standalone" / "cli.js"
        proc = subprocess.run(
            ["node", str(cli), "render", "--package", str(package), "--stage", str(stage)],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout[-2000:])
        segment = stage / "segments" / "proof-chart.mp4"
        streams = ffprobe_streams(segment)
        self.assertEqual((streams[0]["width"], streams[0]["height"]), (1080, 1920))
        proc = subprocess.run(
            ["node", str(cli), "proof", "--package", str(package), "--stage", str(stage)],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout[-2000:])
        proof = read_json(stage / "proof" / "motion-proof.json")
        self.assertEqual(proof["verdict"], "pass")


if __name__ == "__main__":
    unittest.main()
