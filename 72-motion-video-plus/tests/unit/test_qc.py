"""Tests for the MG-034 technical QC layer (scripts/qc.py).

The legacy qc.sh printed PASS for its contact sheet whether or not
the sheet build succeeded, counted grep matches for its black and
freeze sweeps (an ffmpeg failure read as zero defects), and compared
the output's audio stream against its video stream instead of the
plan (defect register D-QC-FALSE-GREEN). These tests prove the
replacement's acceptance behaviors, each failing or passing by name:

- missing FFmpeg fails the gate (tools.available, QC_TOOL_MISSING);
- a failed contact sheet / incomplete MG-031 bundle fails by name
  (legacy.contact_sheet, review.receipt);
- truncated audio fails against the compiled total samples
  (audio.duration, QC_AUDIO_TRUNCATED), never against the video
  stream;
- corrupt media surfaces as a named probe/decode failure, never a
  traceback;
- a wrong aspect ratio fails against the plan canvas
  (plan.dimensions, QC_DIMENSIONS_MISMATCH);
- an absent review receipt fails (QC_REVIEW_RECEIPT_MISSING);
- an approved silent hold passes: the freeze is covered by the
  timeline's hold_start event, loudness is SKIPPED_WITH_REASON for
  mode none, and the gate stays green;
- unapproved black and frozen intervals fail by name, and the same
  intervals pass when the plan package declares them;
- loudness bites only in mode own; an inherited insert carrying a
  bed fails as a duplicated parent soundtrack;
- a mandatory check that cannot run fails the gate on its own;
- a process still registered as live to this job in the MG-029
  process registry fails the gate (process.registry,
  QC_PROCESS_STILL_RUNNING), a malformed registry record fails
  by name instead of being ignored, and another job's records
  are never judged here;
- a font requirement declared by its canonical alias token
  resolves through the shipped runtime registry
  (package.fonts): an unknown alias, or an alias whose
  resolved family is not installed, fails QC_FONT_UNRESOLVED
  by name, and a registry that cannot be read or parsed fails
  QC_FONT_REGISTRY_UNREADABLE instead of falling back to
  comparing the raw token against fontconfig families (the
  comparison that false-failed the MG-035 and MG-037
  packages, which declare the alias the canonical schema
  requires).

Fixtures are real: finals are produced by the actual assembler
(scripts/assemble.py) from lavfi segments and stdlib sine narration,
and review receipts are produced by the actual bundle builder
(scripts/critique_bundle.py). Nothing is mocked except the broken
tools in the tool-failure tests.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import critique_bundle  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "qc", str(SKILL_ROOT / "scripts" / "qc.py"))
qc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qc)

SCRIPT = SKILL_ROOT / "scripts" / "qc.py"
WRAPPER = SKILL_ROOT / "scripts" / "qc.sh"
SCHEMA = SKILL_ROOT / "references" / "qc-schema.json"
RATE = 48000
HAVE_TOOLS = shutil.which("ffmpeg") and shutil.which("ffprobe")


def sine_wav(path: Path, freq: float, seconds: float,
             amplitude: float = 0.5) -> None:
    frames = int(round(seconds * RATE))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        buf = bytearray()
        for i in range(frames):
            v = int(32767 * amplitude
                    * math.sin(2 * math.pi * freq * i / RATE))
            buf += struct.pack("<hh", v, v)
        w.writeframes(bytes(buf))


def lavfi_video(path: Path, source: str, frames: int,
                extra: list[str] | None = None) -> None:
    argv = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source,
            "-frames:v", str(frames), "-c:v", "libx264",
            "-pix_fmt", "yuv420p"]
    if extra:
        argv += extra
    argv.append(str(path))
    subprocess.run(argv, check=True, capture_output=True, text=True)


def run_qc(argv: list[str]) -> tuple[int, dict]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = qc.main(argv)
    return code, json.loads(buffer.getvalue())


def checks_by_id(report: dict) -> dict:
    return {c["id"]: c for c in report["checks"]}


def sidecar_for(job_id: str, scenes: list[dict], narration=(),
                fps: int = 30) -> dict:
    total = scenes[-1]["end"]
    return {
        "schema_version": "1.0", "item": "MG-021", "job_id": job_id,
        "fps": fps, "sample_rate": RATE,
        "rounding_rule": "round_half_up", "mode": "program",
        "total_frames": total, "total_samples": total * RATE // fps,
        "scenes": [{
            "id": s["id"],
            "placedRange": {"startFrame": s["start"],
                            "endFrameExclusive": s["end"]},
            "durationFrames": s["end"] - s["start"],
            "sourceRange": {"startFrame": s.get("source_start", 0),
                            "endFrameExclusive":
                                s.get("source_start", 0)
                                + (s["end"] - s["start"])},
            "sourceRangeSamples": {
                "startSample": s.get("source_start", 0) * RATE // fps,
                "endSampleExclusive":
                    (s.get("source_start", 0) + s["end"] - s["start"])
                    * RATE // fps},
            "transitionInFrames": 0, "transitionOutFrames": 0,
        } for s in scenes],
        "handles": [], "cues": [],
        "narration": list(narration), "captions": [], "sfx": [],
        "property_overlaps_declared": [], "slot": None,
    }


def timeline_for(job_id: str, scenes: list[dict], owner: str,
                 events=(), fps: int = 30) -> dict:
    return {
        "schema_version": "2.0", "job_id": job_id, "fps": fps,
        "total_frames": scenes[-1]["end"],
        "scenes": [{"id": s["id"], "start_frame": s["start"],
                    "end_frame_exclusive": s["end"],
                    "source_start_frame": s.get("source_start", 0),
                    "transition_in_frames": 0,
                    "transition_out_frames": 0} for s in scenes],
        "events": list(events), "parent_slot": None,
        "audio_owner": owner,
    }


def manifest_for(job_id: str, profile: str = "h264_opaque",
                 width: int = 320, height: int = 180) -> dict:
    return {
        "schema_version": "2.0", "job_id": job_id,
        "company_id": "fixture-company",
        "execution_context": "fixture", "parent": None,
        "mode": "standalone_video", "content_scope": "full_program",
        "canvas": {"width": width, "height": height, "fps": 30},
        "duration_frames": 90,
        "authoring": {"selection": "inherit_config", "provider": None,
                      "model": None, "harness": None},
        "rendering": {"default_engine": "remotion",
                      "allow_legacy_fallback": False,
                      "runtime_lock": "runtime-lock.json"},
        "storyboard": "storyboard.json", "assets": "assets.json",
        "design": "design.json", "timeline": "timeline.json",
        "audio": {"mode": "self", "parent_audio_ref": None,
                  "create_voiceover": False, "create_music": False,
                  "source_assets": []},
        "approval_policy": "fixture_only", "variants": [],
        "scenes": [{"id": "a", "spec": "scenes/a.json"}],
        "delivery": {"video_profile": profile, "poster_frame": 10,
                     "placement": "full_frame",
                     "playback": {"start": "on_click", "repeat": "once",
                                  "end": "hold_final"},
                     "required": ["mp4"]},
    }


def build_bundle(video: Path, outdir: Path, timeline: Path,
                 sidecar: Path) -> tuple[int, dict]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = critique_bundle.main(
            ["build", "--video", str(video), "--outdir", str(outdir),
             "--timeline", str(timeline), "--sidecar", str(sidecar)])
    return code, json.loads(buffer.getvalue())


def assemble(plan_path: Path, media_path: Path, out: Path,
             workdir: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "scripts" / "assemble.py"),
         "--plan", str(plan_path), "--media", str(media_path),
         "--out", str(out), "--workdir", str(workdir)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError("assemble failed: %s\n%s"
                             % (proc.stdout[-1500:],
                                proc.stderr[-1500:]))
    return json.loads(proc.stdout)


def write_package(job_dir: Path, timeline: dict, sidecar: dict,
                  media: dict, final_src: Path,
                  manifest: dict | None = None,
                  font_alias: str = "Liberation Sans",
                  bundle_timeline: dict | None = None,
                  bundle: bool = True) -> Path:
    """Assemble a job package directory around an existing final."""
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "renders").mkdir(exist_ok=True)
    (job_dir / "review").mkdir(exist_ok=True)
    (job_dir / "scenes").mkdir(exist_ok=True)
    manifest = manifest or manifest_for(timeline["job_id"])
    (job_dir / "manifest.json").write_text(json.dumps(manifest))
    (job_dir / "timeline.json").write_text(json.dumps(timeline))
    (job_dir / "timeline-sidecar.json").write_text(json.dumps(sidecar))
    (job_dir / "media.json").write_text(json.dumps(media))
    (job_dir / "storyboard.json").write_text(json.dumps(
        {"schema_version": "2.0", "id": "story-qc", "beats": []}))
    (job_dir / "assets.json").write_text(json.dumps({
        "schema_version": "2.0", "assets": [],
        "font_requirements": [{
            "id": "font-qc-sans", "source": "runtime_registry",
            "family_alias": font_alias, "weights": [400],
            "substitution": "forbidden"}]}))
    final_dst = job_dir / "renders" / "final.mp4"
    shutil.copy(final_src, final_dst)
    if bundle:
        bt = bundle_timeline or timeline
        bt_path = job_dir / "review" / "bundle-timeline.json"
        bt_path.write_text(json.dumps(bt))
        code, report = build_bundle(final_dst, job_dir / "review",
                                    bt_path,
                                    job_dir / "timeline-sidecar.json")
        if bt is timeline and code != 0:
            raise AssertionError("bundle build failed: %s" % report)
    return job_dir


@unittest.skipUnless(HAVE_TOOLS, "ffmpeg/ffprobe required")
class OwnModeJobTests(unittest.TestCase):
    """The own-mode narration job: the green baseline and the
    negatives that mutate it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mg034-own-"))
        media_dir = cls.tmp / "media"
        (media_dir / "scenes").mkdir(parents=True)
        (media_dir / "audio").mkdir(parents=True)
        lavfi_video(media_dir / "scenes" / "a.mp4",
                    "testsrc2=size=320x180:rate=30:duration=3", 90)
        sine_wav(media_dir / "audio" / "n1.wav", 440, 2.0)
        cls.timeline = timeline_for(
            "qc-own", [{"id": "a", "start": 0, "end": 90}], "self")
        cls.sidecar = sidecar_for(
            "qc-own", [{"id": "a", "start": 0, "end": 90}],
            narration=[{"id": "n1", "startFrame": 30,
                        "endFrameExclusive": 90, "startSample": 48000,
                        "endSampleExclusive": 144000}])
        cls.media = {
            "canvas": {"width": 320, "height": 180},
            "scenes": [{"id": "a", "path": "scenes/a.mp4"}],
            "narration": [{"id": "n1", "path": "audio/n1.wav"}],
            "sfx": [], "music": None,
        }
        (cls.tmp / "plan.json").write_text(json.dumps(
            {"timeline": cls.timeline, "sidecar": cls.sidecar}))
        (media_dir / "media.json").write_text(json.dumps(cls.media))
        cls.final = cls.tmp / "final.mp4"
        assemble(cls.tmp / "plan.json", media_dir / "media.json",
                 cls.final, cls.tmp / "asm")
        cls.job = write_package(cls.tmp / "job", cls.timeline,
                                cls.sidecar, cls.media, cls.final)
        # Narration sources must sit beside the package media.json.
        (cls.job / "scenes").mkdir(exist_ok=True)
        shutil.copy(media_dir / "scenes" / "a.mp4",
                    cls.job / "scenes" / "a.mp4")
        (cls.job / "audio").mkdir(exist_ok=True)
        shutil.copy(media_dir / "audio" / "n1.wav",
                    cls.job / "audio" / "n1.wav")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def copy_job(self, name: str) -> Path:
        dst = self.tmp / name
        shutil.copytree(self.job, dst)
        return dst

    def run_job(self, job: Path, *extra: str):
        return run_qc(["check", "--job-dir", str(job), *extra])

    def test_good_job_passes_with_every_check_named(self):
        code, report = self.run_job(self.job)
        self.assertEqual(code, 0, json.dumps(report["summary"],
                                             indent=1))
        self.assertEqual(report["verdict"], "pass")
        by_id = checks_by_id(report)
        for check_id in (
                "tools.available", "inputs.plan", "artifact.exists",
                "artifact.hash", "artifact.probe", "artifact.decode",
                "plan.dimensions", "plan.fps", "plan.frame_count",
                "plan.duration", "plan.streams", "audio.decode",
                "audio.duration", "audio.clipping", "audio.loudness",
                "audio.final_words",
                "video.black", "video.freeze", "video.alpha",
                "review.receipt", "package.assets", "package.fonts"):
            self.assertIn(check_id, by_id)
            self.assertEqual(by_id[check_id]["status"], "PASS",
                             "%s: %s" % (check_id,
                                         by_id[check_id]["message"]))
        # Own mode's promise is kept through the loudness, clipping,
        # and narration checks; the promise check itself is a named
        # skip, not a silent pass.
        self.assertEqual(by_id["audio.mode_promise"]["status"],
                         "SKIPPED_WITH_REASON")
        self.assertEqual(by_id["audio.score_audible"]["status"],
                         "SKIPPED_WITH_REASON")
        # tools.available records the resolved tool paths and
        # points its evidence at the run's plan input (it used to
        # carry a null evidence pointer).
        tools_check = by_id["tools.available"]
        self.assertEqual(tools_check["observed"]["tool_paths"]
                         ["ffmpeg"], shutil.which("ffmpeg"))
        self.assertEqual(tools_check["observed"]["tool_paths"]
                         ["ffprobe"], shutil.which("ffprobe"))
        self.assertIsNotNone(tools_check["evidence"])
        self.assertTrue(tools_check["evidence"].endswith(
            "timeline.json"))
        # No registry records exist for this fixture job on this
        # box, so the MG-029 registry check is a named skip.
        self.assertEqual(by_id["process.registry"]["status"],
                         "SKIPPED_WITH_REASON")
        # The report is the delivery gate's final-QC record shape.
        self.assertEqual(report["artifact_path"], "renders/final.mp4")
        self.assertEqual(len(report["artifact_sha256"]), 64)
        written = self.job / "qc" / "final-qc.json"
        self.assertTrue(written.exists())

    def test_missing_ffmpeg_fails_by_name(self):
        code, report = run_qc(
            ["check", "--job-dir", str(self.job),
             "--ffmpeg", "/nonexistent/bin/ffmpeg",
             "--ffprobe", "/nonexistent/bin/ffprobe"])
        self.assertNotEqual(code, 0)
        self.assertEqual(code, 3)
        by_id = checks_by_id(report)
        self.assertEqual(by_id["tools.available"]["status"], "FAIL")
        self.assertEqual(by_id["tools.available"]["code"],
                         "QC_TOOL_MISSING")
        self.assertEqual(by_id["artifact.probe"]["status"], "NOT_RUN")
        self.assertEqual(report["verdict"], "fail")

    def test_crashing_ffprobe_is_a_named_failure_not_a_traceback(self):
        stub = self.tmp / "ffprobe-boom"
        stub.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"-version\" ]; then "
            "echo 'ffprobe version stub'; exit 0; fi\n"
            "echo 'simulated probe explosion' >&2\n"
            "exit 3\n")
        stub.chmod(0o755)
        code, report = run_qc(
            ["check", "--job-dir", str(self.job),
             "--ffprobe", str(stub)])
        self.assertNotEqual(code, 0)
        by_id = checks_by_id(report)
        probe = by_id["artifact.probe"]
        self.assertEqual(probe["status"], "FAIL")
        self.assertEqual(probe["code"], "QC_MEDIA_CORRUPT")
        self.assertEqual(probe["exit_status"], 3)
        self.assertIn("ffprobe", probe["command"])
        self.assertIn("plan.dimensions",
                      report["summary"]["mandatory_not_run"])

    def test_absent_review_receipt_fails_by_name(self):
        job = self.copy_job("job-no-receipt")
        for f in (job / "review").glob("*coverage.json"):
            f.unlink()
        code, report = self.run_job(job)
        self.assertNotEqual(code, 0)
        receipt = checks_by_id(report)["review.receipt"]
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["code"], "QC_REVIEW_RECEIPT_MISSING")

    def test_incomplete_coverage_fails_by_name(self):
        job = self.copy_job("job-incomplete")
        # Build the bundle against a CONSISTENT plan pair that
        # declares twice the frames the video holds: MG-031's
        # verdict is incomplete, and its record replaces the good
        # one in the package.
        greedy_tl = timeline_for(
            "qc-own", [{"id": "a", "start": 0, "end": 180}], "self")
        greedy_sc = sidecar_for(
            "qc-own", [{"id": "a", "start": 0, "end": 180}],
            narration=[{"id": "n1", "startFrame": 30,
                        "endFrameExclusive": 90, "startSample": 48000,
                        "endSampleExclusive": 144000}])
        scratch = self.tmp / "greedy-bundle"
        greedy_tl_path = self.tmp / "greedy-timeline.json"
        greedy_tl_path.write_text(json.dumps(greedy_tl))
        greedy_sc_path = self.tmp / "greedy-sidecar.json"
        greedy_sc_path.write_text(json.dumps(greedy_sc))
        code_b, bundle = build_bundle(
            job / "renders" / "final.mp4", scratch,
            greedy_tl_path, greedy_sc_path)
        self.assertEqual(code_b, 6)
        self.assertEqual(bundle["verdict"], "incomplete")
        for f in (job / "review").glob("*coverage.json"):
            f.unlink()
        shutil.copy(scratch / "qc-own__coverage.json",
                    job / "review" / "qc-own__coverage.json")
        code, report = self.run_job(job)
        self.assertNotEqual(code, 0)
        receipt = checks_by_id(report)["review.receipt"]
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["code"], "QC_REVIEW_INCOMPLETE")
        self.assertEqual(receipt["category"], "MG_COVERAGE_INCOMPLETE")

    def test_failed_bundle_verdict_fails_by_name(self):
        job = self.copy_job("job-bundle-failed")
        record_path = next((job / "review").glob("*__coverage.json"))
        record = json.loads(record_path.read_text())
        record["verdict"] = "failed"
        record_path.write_text(json.dumps(record))
        code, report = self.run_job(job)
        self.assertNotEqual(code, 0)
        receipt = checks_by_id(report)["review.receipt"]
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["code"], "QC_REVIEW_BUNDLE_FAILED")

    def test_wrapper_delegates_the_job_dir_invocation(self):
        proc = subprocess.run(
            ["bash", str(WRAPPER), "--job-dir", str(self.job)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
        report = json.loads(proc.stdout)
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["mode"], "package")

    def test_receipt_for_other_bytes_fails_hash(self):
        job = self.copy_job("job-stale-receipt")
        # Replace the artifact after the bundle was built: the
        # receipt now binds different bytes than the ones under QC.
        other = self.tmp / "other.mp4"
        lavfi_video(other, "testsrc2=size=320x180:rate=30:duration=3",
                    90)
        shutil.copy(other, job / "renders" / "final.mp4")
        code, report = self.run_job(job)
        self.assertNotEqual(code, 0)
        receipt = checks_by_id(report)["review.receipt"]
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["code"], "QC_REVIEW_HASH_MISMATCH")
        self.assertEqual(code, 9)

    def test_truncated_audio_fails_against_the_plan(self):
        job = self.copy_job("job-truncated")
        truncated = self.tmp / "truncated.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(self.final),
             "-map", "0:v", "-map", "0:a", "-c:v", "copy",
             "-af", "atrim=end_sample=72000", "-c:a", "aac",
             str(truncated)], check=True, capture_output=True,
            text=True)
        shutil.copy(truncated, job / "renders" / "final.mp4")
        # Fresh receipt over the truncated bytes, so the ONLY
        # defects are in the audio itself.
        for f in (job / "review").glob("*coverage.json"):
            f.unlink()
        code_b, bundle = build_bundle(
            job / "renders" / "final.mp4", job / "review",
            job / "timeline.json", job / "timeline-sidecar.json")
        self.assertEqual(code_b, 0)
        code, report = self.run_job(job)
        self.assertNotEqual(code, 0)
        by_id = checks_by_id(report)
        dur = by_id["audio.duration"]
        self.assertEqual(dur["status"], "FAIL")
        self.assertEqual(dur["code"], "QC_AUDIO_TRUNCATED")
        self.assertEqual(dur["observed"]["expected_samples"], 144000)
        self.assertLess(dur["observed"]["decoded_samples"], 100000)
        # The video side of the same file is untouched and passes:
        # the failure is the audio measured against the plan, not
        # one stream compared against the other.
        self.assertEqual(by_id["plan.frame_count"]["status"], "PASS")

    def test_wrong_aspect_ratio_fails_against_the_canvas(self):
        job = self.copy_job("job-wrong-ratio")
        scaled = self.tmp / "scaled.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(self.final),
             "-vf", "scale=320:240", "-c:a", "copy", str(scaled)],
            check=True, capture_output=True, text=True)
        shutil.copy(scaled, job / "renders" / "final.mp4")
        for f in (job / "review").glob("*coverage.json"):
            f.unlink()
        code_b, _bundle = build_bundle(
            job / "renders" / "final.mp4", job / "review",
            job / "timeline.json", job / "timeline-sidecar.json")
        self.assertEqual(code_b, 0)
        code, report = self.run_job(job)
        self.assertNotEqual(code, 0)
        dims = checks_by_id(report)["plan.dimensions"]
        self.assertEqual(dims["status"], "FAIL")
        self.assertEqual(dims["code"], "QC_DIMENSIONS_MISMATCH")
        self.assertEqual(dims["observed"]["expected"]["aspect"],
                         round(16 / 9, 4))
        self.assertEqual(dims["observed"]["observed"]["aspect"],
                         round(320 / 240, 4))

    def test_quiet_mix_fails_loudness_in_own_mode(self):
        job = self.copy_job("job-quiet")
        quiet = self.tmp / "quiet.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(self.final),
             "-c:v", "copy", "-af", "volume=0.05", "-c:a", "aac",
             str(quiet)], check=True, capture_output=True, text=True)
        shutil.copy(quiet, job / "renders" / "final.mp4")
        for f in (job / "review").glob("*coverage.json"):
            f.unlink()
        code_b, _bundle = build_bundle(
            job / "renders" / "final.mp4", job / "review",
            job / "timeline.json", job / "timeline-sidecar.json")
        self.assertEqual(code_b, 0)
        code, report = self.run_job(job)
        self.assertNotEqual(code, 0)
        loud = checks_by_id(report)["audio.loudness"]
        self.assertEqual(loud["status"], "FAIL")
        self.assertEqual(loud["code"], "QC_AUDIO_LOUDNESS_OFF_TARGET")
        self.assertAlmostEqual(
            loud["observed"]["target"]["integratedLufs"], -14.0)

    def test_corrupt_media_is_a_named_failure(self):
        job = self.copy_job("job-corrupt")
        target = job / "renders" / "final.mp4"
        data = bytearray(target.read_bytes())
        # Destroy the container head: the probe must fail by name
        # and every measurement downstream must be NOT_RUN.
        for i in range(0, 8192):
            data[i] = 0
        target.write_bytes(bytes(data))
        code, report = self.run_job(job)
        self.assertNotEqual(code, 0)
        self.assertEqual(report["verdict"], "fail")
        by_id = checks_by_id(report)
        named = [by_id[k] for k in ("artifact.probe", "artifact.decode")
                 if by_id[k]["status"] == "FAIL"]
        self.assertTrue(named, "corruption must fail a named check")
        self.assertTrue(all(c["code"] == "QC_MEDIA_CORRUPT"
                            for c in named))
        # Dependents are NOT_RUN, and a mandatory NOT_RUN fails the
        # gate even where nothing else failed.
        self.assertIn("plan.dimensions",
                      report["summary"]["mandatory_not_run"])

    def test_alpha_profile_claim_on_opaque_file_fails(self):
        job = self.copy_job("job-alpha-lie")
        manifest = json.loads((job / "manifest.json").read_text())
        manifest["delivery"]["video_profile"] = "prores_4444_alpha"
        (job / "manifest.json").write_text(json.dumps(manifest))
        code, report = self.run_job(job)
        self.assertNotEqual(code, 0)
        alpha = checks_by_id(report)["video.alpha"]
        self.assertEqual(alpha["status"], "FAIL")
        self.assertEqual(alpha["code"], "QC_ALPHA_MISMATCH")
        self.assertEqual(alpha["observed"]["pix_fmt"], "yuv420p")

    def test_foreign_manifest_job_id_fails(self):
        job = self.copy_job("job-foreign")
        manifest = json.loads((job / "manifest.json").read_text())
        manifest["job_id"] = "someone-elses-job"
        (job / "manifest.json").write_text(json.dumps(manifest))
        code, report = self.run_job(job)
        self.assertEqual(code, 9)
        plan = checks_by_id(report)["inputs.plan"]
        self.assertEqual(plan["status"], "FAIL")
        self.assertEqual(plan["code"], "QC_FOREIGN_JOB")

    def test_unresolvable_font_fails_by_name(self):
        job = self.copy_job("job-font-missing")
        assets = json.loads((job / "assets.json").read_text())
        assets["font_requirements"][0]["family_alias"] = \
            "QC Family That Does Not Exist"
        (job / "assets.json").write_text(json.dumps(assets))
        code, report = self.run_job(job)
        self.assertNotEqual(code, 0)
        fonts = checks_by_id(report)["package.fonts"]
        self.assertEqual(fonts["status"], "FAIL")
        self.assertEqual(fonts["code"], "QC_FONT_UNRESOLVED")

    def test_alias_declared_font_resolves_through_registry(self):
        job = self.copy_job("job-font-alias")
        assets = json.loads((job / "assets.json").read_text())
        # The canonical declaration form: the alias token, not
        # the resolved family name. This is the package shape
        # the canonical schema requires (and the shape MG-037's
        # insert package carries); it used to fail
        # QC_FONT_UNRESOLVED because the check compared the raw
        # token against fontconfig families directly.
        assets["font_requirements"][0]["family_alias"] = \
            "fixture-sans"
        (job / "assets.json").write_text(json.dumps(assets))
        code, report = self.run_job(job)
        self.assertEqual(code, 0, json.dumps(report["summary"],
                                             indent=1))
        fonts = checks_by_id(report)["package.fonts"]
        self.assertEqual(fonts["status"], "PASS")
        entry = fonts["observed"]["fonts"][0]
        self.assertEqual(entry["resolution"],
                         "runtime_registry_alias")
        self.assertEqual(entry["declared_family"], "fixture-sans")
        self.assertEqual(entry["resolved_family"],
                         "Liberation Sans")
        self.assertTrue(entry["registry_source"].endswith(
            "runtime/src/remotion/fonts.ts"))
        registry = fonts["observed"]["font_registry"]
        self.assertTrue(registry["consulted"])
        self.assertIn("fixture-sans",
                      registry["aliases_registered"])
        self.assertIsNone(registry["problem"])

    def test_lint_record_is_consumed_not_upgraded(self):
        job = self.copy_job("job-lint")
        lint_path = self.tmp / "lint-pass.json"
        lint_path.write_text(json.dumps({
            "engine": "fixture", "fileName": "Scene.tsx",
            "findings": [], "counts": {"errors": 0, "warnings": 0},
            "visualAudit": {"status": "pending", "evidence": None,
                            "note": "MG-034 must render frames"},
            "pass": True}))
        code, report = self.run_job(job, "--lint-report",
                                    str(lint_path))
        self.assertEqual(code, 0)
        lint = checks_by_id(report)["package.lint"]
        self.assertEqual(lint["status"], "PASS")
        self.assertEqual(lint["observed"]["visual_audit_status"],
                         "pending")
        lint_path.write_text(json.dumps({
            "engine": "fixture", "fileName": "Scene.tsx",
            "findings": [{"category": "grammar", "rule": "x",
                          "line": 1, "column": 1, "message": "bad"}],
            "counts": {"errors": 1, "warnings": 0},
            "visualAudit": {"status": "pending", "evidence": None,
                            "note": ""},
            "pass": False}))
        code, report = self.run_job(job, "--lint-report",
                                    str(lint_path))
        self.assertNotEqual(code, 0)
        self.assertEqual(checks_by_id(report)["package.lint"]
                         ["status"], "FAIL")

    def test_asset_tamper_and_loss_fail_by_name(self):
        import hashlib
        job = self.copy_job("job-assets")
        blob = job / "asset.bin"
        blob.write_bytes(b"qc fixture asset bytes")
        assets = json.loads((job / "assets.json").read_text())
        assets["assets"] = [{
            "id": "blob", "path": "asset.bin",
            "sha256": hashlib.sha256(b"qc fixture asset bytes")
            .hexdigest(), "kind": "data"}]
        (job / "assets.json").write_text(json.dumps(assets))
        code, report = self.run_job(job)
        self.assertEqual(code, 0, json.dumps(report["summary"],
                                             indent=1))
        self.assertEqual(checks_by_id(report)["package.assets"]
                         ["status"], "PASS")
        blob.write_bytes(b"tampered bytes")
        code, report = self.run_job(job)
        self.assertNotEqual(code, 0)
        assets_check = checks_by_id(report)["package.assets"]
        self.assertEqual(assets_check["status"], "FAIL")
        self.assertEqual(assets_check["code"],
                         "QC_ASSET_HASH_MISMATCH")
        self.assertEqual(code, 9)
        blob.unlink()
        code, report = self.run_job(job)
        self.assertNotEqual(code, 0)
        self.assertEqual(checks_by_id(report)["package.assets"]
                         ["code"], "QC_ASSET_MISSING")

    def test_motion_proof_record_is_consumed(self):
        job = self.copy_job("job-motion-proof")
        proof = self.tmp / "motion-proof.json"
        proof.write_text(json.dumps({"verdict": "pass",
                                     "label": "full_motion"}))
        code, report = self.run_job(job, "--motion-proof",
                                    str(proof))
        self.assertEqual(code, 0, json.dumps(report["summary"],
                                             indent=1))
        self.assertEqual(checks_by_id(report)["package.motion_proof"]
                         ["status"], "PASS")
        proof.write_text(json.dumps({"verdict": "fail",
                                     "label": "full_motion"}))
        code, report = self.run_job(job, "--motion-proof",
                                    str(proof))
        self.assertNotEqual(code, 0)
        self.assertEqual(checks_by_id(report)["package.motion_proof"]
                         ["code"], "QC_MOTION_PROOF_FAILED")

    def test_live_registered_render_process_fails_the_gate(self):
        reg_dir = self.tmp / "registry-live"
        reg_dir.mkdir()
        sleeper = subprocess.Popen(["sleep", "60"])
        try:
            ticks = qc.read_start_time_ticks(sleeper.pid)
            self.assertIsNotNone(ticks)
            (reg_dir / "qc-own.json").write_text(json.dumps({
                "jobId": "qc-own", "token": "tok-live",
                "processes": [{
                    "jobId": "qc-own", "token": "tok-live",
                    "role": "ffmpeg", "bin": "sleep",
                    "argv": ["sleep", "60"], "cwd": str(self.tmp),
                    "pid": sleeper.pid, "pgid": sleeper.pid,
                    "startTimeTicks": ticks,
                    "startedAt": "2026-10-15T00:00:00Z",
                    "state": "running", "exitCode": None}]}))
            with mock.patch.dict(os.environ, {
                    "MOTION_PROCESS_REGISTRY_DIR": str(reg_dir)}):
                code, report = self.run_job(self.job)
            self.assertNotEqual(code, 0)
            self.assertEqual(report["verdict"], "fail")
            reg = checks_by_id(report)["process.registry"]
            self.assertEqual(reg["status"], "FAIL")
            self.assertEqual(reg["code"],
                             "QC_PROCESS_STILL_RUNNING")
            self.assertEqual(
                reg["observed"]["live_processes"][0]["pid"],
                sleeper.pid)
        finally:
            sleeper.kill()
            sleeper.wait()
        # The same package, the same record, the process now dead:
        # the record reads stale and the gate is green again.
        with mock.patch.dict(os.environ, {
                "MOTION_PROCESS_REGISTRY_DIR": str(reg_dir)}):
            code, report = self.run_job(self.job)
        self.assertEqual(code, 0, json.dumps(report["summary"],
                                             indent=1))
        reg = checks_by_id(report)["process.registry"]
        self.assertEqual(reg["status"], "PASS")
        self.assertEqual(reg["observed"]["stale_pids"],
                         [sleeper.pid])

    def test_report_validates_against_the_qc_schema(self):
        import jsonschema
        schema = json.loads(SCHEMA.read_text())
        validator = jsonschema.Draft202012Validator(schema)
        _code, good = self.run_job(self.job)
        self.assertEqual(list(validator.iter_errors(good)), [])
        job = self.copy_job("job-schema-fail")
        for f in (job / "review").glob("*coverage.json"):
            f.unlink()
        _code, bad = self.run_job(job)
        self.assertEqual(bad["verdict"], "fail")
        self.assertEqual(list(validator.iter_errors(bad)), [])


@unittest.skipUnless(HAVE_TOOLS, "ffmpeg/ffprobe required")
class HoldAndIntentTests(unittest.TestCase):
    """The approved silent hold, and black/freeze intent handling."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mg034-hold-"))
        media_dir = cls.tmp / "media"
        (media_dir / "scenes").mkdir(parents=True)
        lavfi_video(media_dir / "scenes" / "a.mp4",
                    "testsrc2=size=320x180:rate=30:duration=2", 60)
        lavfi_video(media_dir / "scenes" / "b.mp4",
                    "color=c=0x3a7bd5:size=320x180:rate=30:duration=2",
                    60)
        scenes = [{"id": "a", "start": 0, "end": 60},
                  {"id": "b", "start": 60, "end": 120}]
        cls.scenes = scenes
        cls.sidecar = sidecar_for("qc-hold", scenes)
        cls.media = {
            "canvas": {"width": 320, "height": 180},
            "scenes": [{"id": "a", "path": "scenes/a.mp4"},
                       {"id": "b", "path": "scenes/b.mp4"}],
            "narration": [], "sfx": [], "music": None,
        }
        (media_dir / "media.json").write_text(json.dumps(cls.media))
        cls.hold_timeline = timeline_for(
            "qc-hold", scenes, "none",
            events=[{"id": "hold-b", "scene_id": "b", "frame": 60,
                     "type": "hold_start"}])
        (cls.tmp / "plan-hold.json").write_text(json.dumps(
            {"timeline": cls.hold_timeline, "sidecar": cls.sidecar}))
        cls.final = cls.tmp / "hold-final.mp4"
        assemble(cls.tmp / "plan-hold.json", media_dir / "media.json",
                 cls.final, cls.tmp / "asm-hold")
        manifest = manifest_for("qc-hold")
        cls.job = write_package(
            cls.tmp / "job-hold", cls.hold_timeline, cls.sidecar,
            cls.media, cls.final,
            manifest={**manifest,
                      "scenes": [{"id": "a", "spec": "scenes/a.json"},
                                 {"id": "b", "spec": "scenes/b.json"}]})
        # The eventless twin: identical bytes, a timeline that
        # never approved the hold.
        cls.plain_timeline = timeline_for("qc-hold", scenes, "none")
        cls.job_plain = write_package(
            cls.tmp / "job-plain", cls.plain_timeline, cls.sidecar,
            cls.media, cls.final,
            manifest={**manifest,
                      "scenes": [{"id": "a", "spec": "scenes/a.json"},
                                 {"id": "b", "spec": "scenes/b.json"}]})

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_approved_silent_hold_passes(self):
        code, report = run_qc(["check", "--job-dir", str(self.job)])
        self.assertEqual(code, 0, json.dumps(report["summary"],
                                             indent=1))
        by_id = checks_by_id(report)
        freeze = by_id["video.freeze"]
        self.assertEqual(freeze["status"], "PASS")
        self.assertTrue(any("hold_start" in s for s in
                            freeze["observed"]["approval_sources"]),
                        freeze["observed"])
        self.assertEqual(freeze["observed"]
                         ["approved_freeze_intervals_frames"],
                         [[60, 120]])
        # Silence is the mode's promise: loudness is skipped with
        # the reason, and the mode promise itself passes.
        self.assertEqual(by_id["audio.loudness"]["status"],
                         "SKIPPED_WITH_REASON")
        self.assertIn("mode own", by_id["audio.loudness"]["message"])
        self.assertEqual(by_id["audio.mode_promise"]["status"],
                         "PASS")
        # The no-audio-stream skips name the resolved plan as
        # their evidence (they used to carry a null pointer).
        for check_id in ("audio.duration", "audio.clipping"):
            self.assertEqual(by_id[check_id]["status"],
                             "SKIPPED_WITH_REASON")
            self.assertIsNotNone(by_id[check_id]["evidence"])
            self.assertTrue(by_id[check_id]["evidence"].endswith(
                "timeline.json"))
        self.assertEqual(report["verdict"], "pass")

    def test_same_hold_without_plan_approval_fails(self):
        code, report = run_qc(
            ["check", "--job-dir", str(self.job_plain)])
        self.assertNotEqual(code, 0)
        freeze = checks_by_id(report)["video.freeze"]
        self.assertEqual(freeze["status"], "FAIL")
        self.assertEqual(freeze["code"], "QC_FREEZE_UNAPPROVED")
        self.assertTrue(freeze["observed"]
                        ["uncovered_intervals_frames"])

    def _black_package(self, name: str, approved: bool) -> Path:
        work = self.tmp / name
        work.mkdir(parents=True, exist_ok=True)
        segs = []
        for i, src in enumerate((
                "testsrc2=size=320x180:rate=30:duration=1",
                "color=c=black:size=320x180:rate=30:duration=1",
                "testsrc2=size=320x180:rate=30:duration=1")):
            seg = work / ("seg%d.mp4" % i)
            lavfi_video(seg, src, 30)
            segs.append(seg)
        listfile = work / "concat.txt"
        listfile.write_text("".join("file '%s'\n" % s for s in segs))
        final = work / "black-final.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe",
             "0", "-i", str(listfile), "-c", "copy", str(final)],
            check=True, capture_output=True, text=True)
        scenes = [{"id": "a", "start": 0, "end": 90}]
        timeline = timeline_for("qc-black", scenes, "none")
        sidecar = sidecar_for("qc-black", scenes)
        media = {"canvas": {"width": 320, "height": 180},
                 "scenes": [], "narration": [], "sfx": [],
                 "music": None}
        job = write_package(work / "job", timeline, sidecar, media,
                            final, manifest=manifest_for("qc-black"))
        if approved:
            (job / "qc-approved-intervals.json").write_text(
                json.dumps({"intervals": [{
                    "start_frame": 30, "end_frame_exclusive": 60,
                    "kinds": ["dark", "freeze"],
                    "reason": "intentional silent dark beat before "
                              "the reveal",
                    "source": "storyboard beat beat-dark"}]}))
        return job

    def test_unapproved_black_interval_fails_by_name(self):
        job = self._black_package("black-unapproved", approved=False)
        code, report = run_qc(["check", "--job-dir", str(job)])
        self.assertNotEqual(code, 0)
        black = checks_by_id(report)["video.black"]
        self.assertEqual(black["status"], "FAIL")
        self.assertEqual(black["code"], "QC_BLACK_UNAPPROVED")
        self.assertEqual(black["observed"]
                         ["detected_intervals_frames"], [[30, 60]])

    def test_plan_declared_dark_beat_passes(self):
        job = self._black_package("black-approved", approved=True)
        code, report = run_qc(["check", "--job-dir", str(job)])
        self.assertEqual(code, 0, json.dumps(report["summary"],
                                             indent=1))
        by_id = checks_by_id(report)
        self.assertEqual(by_id["video.black"]["status"], "PASS")
        self.assertTrue(any("intentional silent dark beat" in s
                            for s in by_id["video.black"]["observed"]
                            ["approval_sources"]))
        self.assertEqual(by_id["video.freeze"]["status"], "PASS")


@unittest.skipUnless(HAVE_TOOLS, "ffmpeg/ffprobe required")
class InheritedModeTests(unittest.TestCase):
    """Mode inherited: silent inserts pass; a carried bed fails as
    a duplicated parent soundtrack."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mg034-inh-"))
        media_dir = cls.tmp / "media"
        (media_dir / "scenes").mkdir(parents=True)
        (media_dir / "audio").mkdir(parents=True)
        lavfi_video(media_dir / "scenes" / "a.mp4",
                    "testsrc2=size=320x180:rate=30:duration=3", 90)
        sine_wav(media_dir / "audio" / "bed.wav", 220, 3.0)
        scenes = [{"id": "a", "start": 0, "end": 90}]
        cls.timeline = timeline_for("qc-inherited", scenes, "parent")
        cls.sidecar = sidecar_for("qc-inherited", scenes)
        cls.media = {
            "canvas": {"width": 320, "height": 180},
            "scenes": [{"id": "a", "path": "scenes/a.mp4"}],
            "narration": [], "sfx": [],
            "music": {"path": "audio/bed.wav"},
        }
        (cls.tmp / "plan.json").write_text(json.dumps(
            {"timeline": cls.timeline, "sidecar": cls.sidecar}))
        (media_dir / "media.json").write_text(json.dumps(cls.media))
        cls.final = cls.tmp / "insert.mp4"
        assemble(cls.tmp / "plan.json", media_dir / "media.json",
                 cls.final, cls.tmp / "asm")
        cls.job = write_package(cls.tmp / "job", cls.timeline,
                                cls.sidecar, cls.media, cls.final,
                                manifest=manifest_for("qc-inherited"))
        cls.bed = media_dir / "audio" / "bed.wav"

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_silent_insert_passes_and_loudness_is_skipped(self):
        code, report = run_qc(["check", "--job-dir", str(self.job)])
        self.assertEqual(code, 0, json.dumps(report["summary"],
                                             indent=1))
        by_id = checks_by_id(report)
        self.assertEqual(by_id["audio.mode_promise"]["status"],
                         "PASS")
        self.assertEqual(by_id["audio.loudness"]["status"],
                         "SKIPPED_WITH_REASON")
        self.assertEqual(by_id["plan.streams"]["status"], "PASS")
        # The package music bed was excluded by the resolved plan,
        # and the exclusion is visible in the check's evidence.
        self.assertTrue(by_id["audio.mode_promise"]["observed"]
                        ["exclusions"])

    def test_insert_carrying_a_bed_fails_as_duplication(self):
        job = self.tmp / "job-bed"
        shutil.copytree(self.job, job)
        muxed = self.tmp / "muxed.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(self.final),
             "-i", str(self.bed), "-map", "0:v", "-map", "1:a",
             "-c", "copy", str(muxed)],
            check=True, capture_output=True, text=True)
        shutil.copy(muxed, job / "renders" / "final.mp4")
        for f in (job / "review").glob("*coverage.json"):
            f.unlink()
        code_b, _bundle = build_bundle(
            job / "renders" / "final.mp4", job / "review",
            job / "timeline.json", job / "timeline-sidecar.json")
        self.assertEqual(code_b, 0)
        code, report = run_qc(["check", "--job-dir", str(job)])
        self.assertNotEqual(code, 0)
        promise = checks_by_id(report)["audio.mode_promise"]
        self.assertEqual(promise["status"], "FAIL")
        self.assertEqual(promise["code"],
                         "QC_AUDIO_PARENT_BED_DUPLICATED")
        self.assertGreater(
            promise["observed"]["carried_stream_rms_dbfs"], -55.0)


@unittest.skipUnless(HAVE_TOOLS, "ffmpeg/ffprobe required")
class AlphaProfileTests(unittest.TestCase):
    """A real alpha artifact against an alpha profile passes; the
    profile is consumed from the manifest's delivery record."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mg034-alpha-"))
        cls.final = cls.tmp / "alpha.mov"
        # ProRes 4444 is the alpha carrier that survives an ffmpeg
        # round trip on this platform (libvpx-vp9 drops the alpha
        # plane on encode); the gradient alpha varies per pixel.
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y",
             "-f", "lavfi", "-i",
             "testsrc2=size=320x180:rate=30:duration=2",
             "-f", "lavfi", "-i",
             "gradients=size=320x180:rate=30:duration=2",
             "-filter_complex",
             "[0:v]format=yuva420p[v];[1:v]format=gray[a];"
             "[v][a]alphamerge,format=yuva420p",
             "-frames:v", "60", "-c:v", "prores_ks",
             "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
             "-an", str(cls.final)],
            check=True, capture_output=True, text=True)
        scenes = [{"id": "a", "start": 0, "end": 60}]
        cls.timeline = timeline_for("qc-alpha", scenes, "none")
        cls.sidecar = sidecar_for("qc-alpha", scenes)
        cls.media = {"canvas": {"width": 320, "height": 180},
                     "scenes": [], "narration": [], "sfx": [],
                     "music": None}
        cls.job = write_package(
            cls.tmp / "job", cls.timeline, cls.sidecar, cls.media,
            cls.final, manifest=manifest_for(
                "qc-alpha", profile="prores_4444_alpha"))
        # write_package copies to renders/final.mp4; the alpha
        # artifact is a mov, so point the package at the real file.
        (cls.job / "renders" / "final.mp4").unlink()
        shutil.copy(cls.final, cls.job / "renders" / "final.mov")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_varying_alpha_passes_alpha_profile(self):
        code, report = run_qc(
            ["check", "--job-dir", str(self.job),
             "--final", str(self.job / "renders" / "final.mov")])
        self.assertEqual(code, 0, json.dumps(report["summary"],
                                             indent=1))
        alpha = checks_by_id(report)["video.alpha"]
        self.assertEqual(alpha["status"], "PASS")
        self.assertTrue(alpha["observed"]["alpha_varies"])
        self.assertLess(alpha["observed"]["alpha_plane_sample"]
                        ["min"], alpha["observed"]
                        ["alpha_plane_sample"]["max"])


@unittest.skipUnless(HAVE_TOOLS, "ffmpeg/ffprobe required")
class LegacyLaneTests(unittest.TestCase):
    """The historical qc.sh invocation path, fail-closed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mg034-legacy-"))
        cls.workdir = cls.tmp / "work"
        cls.scenes = []
        for sid in ("s1", "s2", "s3"):
            seg_dir = cls.workdir / "scenes" / sid
            seg_dir.mkdir(parents=True)
            lavfi_video(seg_dir / ("%s.mp4" % sid),
                        "testsrc2=size=320x180:rate=30:duration=2",
                        60)
            cls.scenes.append({
                "id": sid, "duration_seconds": 2.0,
                "file": "./scenes/%s.html" % sid,
                "voiceover_text": "", "sfx_events": []})
        cls.manifest = {
            "video_name": "legacy-smoke", "fps": 30, "width": 320,
            "height": 180, "music_bed": None,
            "scenes": cls.scenes,
        }
        cls.manifest_path = cls.tmp / "manifest.json"
        cls.manifest_path.write_text(json.dumps(cls.manifest))
        listfile = cls.tmp / "concat.txt"
        listfile.write_text("".join(
            "file '%s'\n" % (cls.workdir / "scenes" / s["id"]
                             / ("%s.mp4" % s["id"]))
            for s in cls.scenes))
        cls.final = cls.tmp / "final.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe",
             "0", "-i", str(listfile), "-c", "copy", str(cls.final)],
            check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_legacy(self, manifest=None, workdir=None, final=None,
                   via_wrapper=False):
        argv = ["--manifest", str(manifest or self.manifest_path),
                "--workdir", str(workdir or self.workdir),
                "--final", str(final or self.final)]
        if via_wrapper:
            proc = subprocess.run(
                ["bash", str(WRAPPER), *argv],
                capture_output=True, text=True)
            return proc.returncode, json.loads(proc.stdout)
        return run_qc(["check", "--legacy-manifest",
                       str(manifest or self.manifest_path),
                       "--workdir", str(workdir or self.workdir),
                       "--final", str(final or self.final)])

    def test_legacy_run_passes_and_sheet_is_written(self):
        code, report = self.run_legacy()
        self.assertEqual(code, 0, json.dumps(report["summary"],
                                             indent=1))
        by_id = checks_by_id(report)
        self.assertEqual(by_id["legacy.segments"]["status"], "PASS")
        self.assertEqual(by_id["legacy.contact_sheet"]["status"],
                         "PASS")
        sheet = self.workdir / "contact-sheet.jpg"
        self.assertTrue(sheet.exists() and sheet.stat().st_size > 0)
        self.assertEqual(by_id["plan.frame_count"]["status"], "PASS")
        self.assertEqual(by_id["review.receipt"]["status"],
                         "SKIPPED_WITH_REASON")
        self.assertEqual(by_id["legacy.determinism"]["status"],
                         "SKIPPED_WITH_REASON")

    def test_wrapper_keeps_the_legacy_invocation(self):
        code, report = self.run_legacy(via_wrapper=True)
        self.assertEqual(code, 0)
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["mode"], "legacy")

    def test_missing_segment_fails_segments_and_sheet_by_name(self):
        work = self.tmp / "work-broken"
        shutil.copytree(self.workdir, work)
        (work / "scenes" / "s2" / "s2.mp4").unlink()
        code, report = self.run_legacy(workdir=work)
        self.assertNotEqual(code, 0)
        by_id = checks_by_id(report)
        self.assertEqual(by_id["legacy.segments"]["status"], "FAIL")
        sheet = by_id["legacy.contact_sheet"]
        # The exact legacy false-green: the old script printed PASS
        # for this sheet. Here it is a named failure.
        self.assertEqual(sheet["status"], "FAIL")
        self.assertEqual(sheet["code"], "QC_CONTACT_SHEET_FAILED")


class PureFunctionTests(unittest.TestCase):
    """Interval arithmetic and approval derivation, no ffmpeg."""

    def test_subtract_approvals(self):
        self.assertEqual(qc.subtract_approvals([(10, 50)], [(0, 100)]),
                         [])
        self.assertEqual(
            qc.subtract_approvals([(10, 50)], [(20, 30)]),
            [(10, 18), (32, 50)])
        # Edge tolerance: a 2-frame detection overhang is covered.
        self.assertEqual(
            qc.subtract_approvals([(10, 52)], [(12, 50)]), [])

    def test_approval_sources_come_from_plan_data(self):
        run = object.__new__(qc.QcRun)
        run.timeline = {
            "scenes": [{"id": "b", "start_frame": 60,
                        "end_frame_exclusive": 120}],
            "events": [{"id": "h", "scene_id": "b", "frame": 60,
                        "type": "hold_start"}],
        }
        run.sidecar = {"scenes": [{
            "id": "b",
            "placedRange": {"startFrame": 60,
                            "endFrameExclusive": 120},
            "sourceRange": {"startFrame": 0,
                            "endFrameExclusive": 60}}]}
        run.job_dir = None
        run.args = type("A", (), {"planner": None, "storyboard": None,
                                  "approved_intervals": None,
                                  "legacy_manifest": None,
                                  "workdir": None})()
        run._scene_specs = lambda: [{
            "id": "b",
            "motion": {"end_frame_exclusive": 30,
                       "hold_to_frame_exclusive": 60}}]
        dark, freeze, sources = run.approved_intervals()
        self.assertEqual(dark, [])
        self.assertIn((60, 120), freeze)   # the hold_start event
        self.assertIn((90, 120), freeze)   # the spec hold, placed
        self.assertTrue(any("hold_start" in s for s in sources))


@unittest.skipUnless(Path("/proc").exists(),
                     "registry identity is read from /proc")
class ProcessRegistryTests(unittest.TestCase):
    """The MG-029 process-registry check (process.registry).

    Direct-method tests: the check needs only a job identity and
    a registry directory, so these build a bare QcRun the way
    PureFunctionTests does and point MOTION_PROCESS_REGISTRY_DIR
    at a fixture directory in temp space. The real default
    registry directory is never opened.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mg034-registry-"))
        self.reg_dir = self.tmp / "processes"
        self.reg_dir.mkdir()
        self.sleepers: list[subprocess.Popen] = []
        self._env = mock.patch.dict(
            os.environ,
            {"MOTION_PROCESS_REGISTRY_DIR": str(self.reg_dir)})
        self._env.start()
        self.addCleanup(self._env.stop)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(self._kill_sleepers)

    def _kill_sleepers(self) -> None:
        for proc in self.sleepers:
            if proc.poll() is None:
                proc.kill()
            proc.wait()

    def spawn_sleeper(self) -> subprocess.Popen:
        proc = subprocess.Popen(["sleep", "60"])
        self.sleepers.append(proc)
        return proc

    def entry(self, pid: int, ticks, state: str = "running",
              job_id: str = "qc-registry") -> dict:
        return {
            "jobId": job_id, "token": "tok-fixture",
            "role": "hyperframes", "bin": "sleep",
            "argv": ["sleep", "60"], "cwd": str(self.tmp),
            "pid": pid, "pgid": pid, "startTimeTicks": ticks,
            "startedAt": "2026-10-15T00:00:00Z", "state": state,
            "exitCode": None}

    def write_registry(self, job_id: str, processes: list,
                       token: str = "tok-fixture") -> Path:
        path = self.reg_dir / (qc.sanitize_job_segment(job_id)
                               + ".json")
        path.write_text(json.dumps(
            {"jobId": job_id, "token": token,
             "processes": processes}))
        return path

    def run_check(self, job_id: str = "qc-registry") -> dict:
        run = object.__new__(qc.QcRun)
        run.checks = []
        run.timeline = {"job_id": job_id}
        run.plan_error = None
        return run.check_process_registry()

    def test_live_registered_process_fails_by_name(self):
        proc = self.spawn_sleeper()
        ticks = qc.read_start_time_ticks(proc.pid)
        self.assertIsNotNone(ticks)
        self.write_registry(
            "qc-registry", [self.entry(proc.pid, ticks)])
        check = self.run_check()
        self.assertEqual(check["status"], "FAIL")
        self.assertEqual(check["code"], "QC_PROCESS_STILL_RUNNING")
        self.assertTrue(check["mandatory"])
        self.assertEqual(
            check["observed"]["live_processes"][0]["pid"],
            proc.pid)
        self.assertEqual(check["observed"]["records_found"], 1)

    def test_dead_pid_record_passes_as_stale(self):
        proc = self.spawn_sleeper()
        pid, ticks = proc.pid, qc.read_start_time_ticks(proc.pid)
        proc.kill()
        proc.wait()
        self.write_registry("qc-registry", [self.entry(pid, ticks)])
        check = self.run_check()
        self.assertEqual(check["status"], "PASS")
        self.assertEqual(check["observed"]["stale_pids"], [pid])
        self.assertEqual(check["observed"]["live_processes"], [])

    def test_pid_reuse_record_is_stale_not_live(self):
        proc = self.spawn_sleeper()
        ticks = qc.read_start_time_ticks(proc.pid)
        self.assertIsNotNone(ticks)
        # The pid is alive, but the recorded start-time belongs to
        # an earlier incarnation: the pid was recycled and the
        # live process is not the job's.
        self.write_registry(
            "qc-registry", [self.entry(proc.pid, ticks + 4096)])
        check = self.run_check()
        self.assertEqual(check["status"], "PASS")
        self.assertEqual(check["observed"]["stale_pids"],
                         [proc.pid])
        self.assertEqual(check["observed"]["live_processes"], [])

    def test_finished_records_pass(self):
        proc = self.spawn_sleeper()
        pid, ticks = proc.pid, qc.read_start_time_ticks(proc.pid)
        proc.kill()
        proc.wait()
        self.write_registry("qc-registry", [
            self.entry(pid, ticks, state="exited"),
            self.entry(pid + 500000, None, state="terminated")])
        check = self.run_check()
        self.assertEqual(check["status"], "PASS")
        self.assertEqual(check["observed"]["records_found"], 2)
        self.assertEqual(
            len(check["observed"]["finished_processes"]), 2)
        self.assertEqual(check["observed"]["live_processes"], [])

    def test_foreign_job_live_record_does_not_fail_this_job(self):
        proc = self.spawn_sleeper()
        ticks = qc.read_start_time_ticks(proc.pid)
        self.write_registry(
            "qc-other-job",
            [self.entry(proc.pid, ticks, job_id="qc-other-job")],
            )
        check = self.run_check("qc-registry")
        self.assertEqual(check["status"], "SKIPPED_WITH_REASON")
        self.assertEqual(check["observed"]["records_found"], 0)

    def test_registry_file_for_another_job_id_is_not_judged(self):
        # "qc registry" and "qc_registry" sanitize to the same
        # registry segment, so the file this job's check opens can
        # belong to the other job. Its live processes are not
        # this job's and must not fail it.
        proc = self.spawn_sleeper()
        ticks = qc.read_start_time_ticks(proc.pid)
        path = self.reg_dir / (qc.sanitize_job_segment(
            "qc registry") + ".json")
        path.write_text(json.dumps({
            "jobId": "qc_registry", "token": "tok-fixture",
            "processes": [self.entry(proc.pid, ticks,
                                     job_id="qc_registry")]}))
        check = self.run_check("qc registry")
        self.assertEqual(check["status"], "SKIPPED_WITH_REASON")
        self.assertEqual(check["observed"]["registry_job_id"],
                         "qc_registry")
        self.assertEqual(check["observed"]["records_found"], 0)

    def test_malformed_registry_json_fails_by_name(self):
        path = self.reg_dir / (qc.sanitize_job_segment(
            "qc-registry") + ".json")
        path.write_text("{not json")
        check = self.run_check()
        self.assertEqual(check["status"], "FAIL")
        self.assertEqual(check["code"],
                         "QC_PROCESS_REGISTRY_INVALID")
        self.assertTrue(check["mandatory"])

    def test_malformed_registry_shape_fails_by_name(self):
        path = self.reg_dir / (qc.sanitize_job_segment(
            "qc-registry") + ".json")
        path.write_text(json.dumps({
            "jobId": "qc-registry", "token": "tok-fixture",
            "processes": {"pid": 4242}}))
        check = self.run_check()
        self.assertEqual(check["status"], "FAIL")
        self.assertEqual(check["code"],
                         "QC_PROCESS_REGISTRY_INVALID")
        path.write_text(json.dumps({
            "jobId": "qc-registry", "token": "tok-fixture",
            "processes": [{"pid": "not-an-integer"}]}))
        check = self.run_check()
        self.assertEqual(check["status"], "FAIL")
        self.assertEqual(check["code"],
                         "QC_PROCESS_REGISTRY_INVALID")

    def test_absent_registry_directory_skips_with_reason(self):
        shutil.rmtree(self.reg_dir)
        check = self.run_check()
        self.assertEqual(check["status"], "SKIPPED_WITH_REASON")
        self.assertEqual(check["observed"]["records_found"], 0)
        self.assertFalse(
            check["observed"]["registry_file_present"])
        self.assertIn("no records", check["message"])


@unittest.skipUnless(shutil.which("fc-list"),
                     "fontconfig (fc-list) is required")
class FontAliasRegistryTests(unittest.TestCase):
    """The package.fonts alias resolution, tested directly on
    the check (the ProcessRegistryTests pattern: the check
    needs only an assets record, so these build a bare QcRun).
    Registry sources are fixture files in temp space, pointed
    to by MOTION_FONT_REGISTRY_PATH; the real shipped registry
    is never modified. One test deliberately consumes the real
    shipped registry, unmodified, to prove the shipped data
    parses and resolves. Liberation Sans is the installed
    family these fixtures resolve to; the whole module already
    depends on it being installed (write_package's default)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mg034fix-fonts-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.assets_path = self.tmp / "assets.json"

    def requirement(self, alias):
        return {"id": "font-test", "source": "runtime_registry",
                "family_alias": alias, "weights": [400],
                "substitution": "forbidden"}

    def run_fonts(self, requirements):
        self.assets_path.write_text(json.dumps({
            "schema_version": "2.0", "assets": [],
            "font_requirements": requirements}))
        run = object.__new__(qc.QcRun)
        run.checks = []
        run.manifest = None
        run.job_dir = None
        run.args = type("A", (), {
            "assets": str(self.assets_path)})()
        return run.check_fonts()

    @contextlib.contextmanager
    def registry_env(self, path):
        with mock.patch.dict(os.environ):
            if path is None:
                os.environ.pop("MOTION_FONT_REGISTRY_PATH", None)
            else:
                os.environ["MOTION_FONT_REGISTRY_PATH"] = str(path)
            yield

    def test_alias_token_resolves_through_shipped_registry(self):
        with self.registry_env(None):
            check = self.run_fonts([self.requirement("fixture-sans")])
        self.assertEqual(check["status"], "PASS")
        entry = check["observed"]["fonts"][0]
        self.assertEqual(entry["status"], "resolved")
        self.assertEqual(entry["resolution"],
                         "runtime_registry_alias")
        self.assertEqual(entry["declared_family"], "fixture-sans")
        self.assertEqual(entry["resolved_family"], "Liberation Sans")
        self.assertTrue(entry["registry_source"].endswith(
            "runtime/src/remotion/fonts.ts"))
        registry = check["observed"]["font_registry"]
        self.assertTrue(registry["consulted"])
        self.assertIn("fixture-sans",
                      registry["aliases_registered"])
        self.assertIsNone(registry["problem"])

    def test_unknown_alias_fails_by_name(self):
        with self.registry_env(None):
            check = self.run_fonts([self.requirement(
                "qc-alias-not-registered-anywhere")])
        self.assertEqual(check["status"], "FAIL")
        self.assertEqual(check["code"], "QC_FONT_UNRESOLVED")
        self.assertIn("qc-alias-not-registered-anywhere",
                      check["message"])
        entry = check["observed"]["fonts"][0]
        self.assertEqual(entry["resolution"], "unknown_alias")

    def test_alias_to_uninstalled_family_fails_by_name(self):
        registry = self.tmp / "fonts-ghost.ts"
        registry.write_text(
            "// test fixture registry\n"
            "const ALIAS_REGISTRY: Record<string, "
            "AliasRegistration> = {\n"
            '  "fixture-ghost": {\n'
            '    family: "QC Ghost Family Not Installed",\n'
            "    fileByWeight: {\n"
            '      400: "QCGhost-Regular.ttf",\n'
            "    },\n"
            "  },\n"
            "};\n")
        with self.registry_env(registry):
            check = self.run_fonts(
                [self.requirement("fixture-ghost")])
        self.assertEqual(check["status"], "FAIL")
        self.assertEqual(check["code"], "QC_FONT_UNRESOLVED")
        self.assertIn("QC Ghost Family Not Installed",
                      check["message"])
        self.assertIn("fixture-ghost", check["message"])
        entry = check["observed"]["fonts"][0]
        self.assertEqual(entry["status"],
                         "resolved_family_not_installed")
        self.assertEqual(entry["resolved_family"],
                         "QC Ghost Family Not Installed")

    def test_direct_family_name_still_passes(self):
        with self.registry_env(None):
            check = self.run_fonts(
                [self.requirement("Liberation Sans")])
        self.assertEqual(check["status"], "PASS")
        entry = check["observed"]["fonts"][0]
        self.assertEqual(entry["resolution"], "installed_family")
        self.assertEqual(entry["resolved_family"], "Liberation Sans")
        self.assertFalse(
            check["observed"]["font_registry"]["consulted"])

    def test_missing_registry_source_fails_by_name(self):
        missing = self.tmp / "fonts-that-do-not-exist.ts"
        with self.registry_env(missing):
            check = self.run_fonts([self.requirement("fixture-sans")])
        self.assertEqual(check["status"], "FAIL")
        self.assertEqual(check["code"],
                         "QC_FONT_REGISTRY_UNREADABLE")
        self.assertIn(str(missing), check["message"])
        entry = check["observed"]["fonts"][0]
        self.assertEqual(entry["status"], "registry_unreadable")

    def test_corrupted_registry_source_fails_by_name(self):
        broken = self.tmp / "fonts-broken.ts"
        broken.write_text("this file is not a font registry\n")
        with self.registry_env(broken):
            check = self.run_fonts([self.requirement("fixture-sans")])
        self.assertEqual(check["status"], "FAIL")
        self.assertEqual(check["code"],
                         "QC_FONT_REGISTRY_UNREADABLE")
        self.assertEqual(check["observed"]["fonts"][0]["status"],
                         "registry_unreadable")
        # A registry literal with no entries is just as
        # unusable for resolution purposes.
        empty = self.tmp / "fonts-empty.ts"
        empty.write_text(
            "const ALIAS_REGISTRY: Record<string, "
            "AliasRegistration> = {};\n")
        with self.registry_env(empty):
            check = self.run_fonts([self.requirement("fixture-sans")])
        self.assertEqual(check["status"], "FAIL")
        self.assertEqual(check["code"],
                         "QC_FONT_REGISTRY_UNREADABLE")


if __name__ == "__main__":
    unittest.main()
