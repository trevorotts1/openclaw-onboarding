"""Tests for the MG-035 PowerPoint packaging layer.

Covers scripts/poster_select.py (the poster selection rule and its
measurements), scripts/powerpoint_adapter.py (the OOXML embed and
the moved-deck structural proof), and scripts/powerpoint_package.py
(the QC gate, media and audio conformance, the placement text
audit, the loop seam check, and the governed package record).

The plan-level poster tests run on the real C05 fixture records.
The package-level tests build small synthetic job packages around
real ffmpeg-encoded artifacts, the same convention as
tests/unit/test_qc.py: no mocks, named refusals asserted exactly.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import poster_select  # noqa: E402
import powerpoint_adapter  # noqa: E402
import powerpoint_package  # noqa: E402
from poster_select import PosterSelectionError  # noqa: E402
from powerpoint_adapter import AdapterError  # noqa: E402
from powerpoint_package import PackageError  # noqa: E402

HAVE_TOOLS = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
HAVE_SOFFICE = bool(shutil.which("soffice") and shutil.which("pdftoppm"))
FIXTURE = SKILL_ROOT / "tests" / "fixtures" / "modes" / "powerpoint_graphic"

BG = "0xF7F4EE"
ACCENT = "0xC04A26"


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_ffmpeg(args: list[str]) -> None:
    proc = subprocess.run(["ffmpeg", "-v", "error", "-y"] + args,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError("ffmpeg failed: %s" % proc.stderr[-800:])


def encode_segment(path: Path, frames: int, box_width: int | None) -> None:
    vf = "format=yuv420p"
    if box_width:
        vf += (",drawbox=x=420:y=360:w=%d:h=90:color=%s:t=fill"
               % (box_width, ACCENT))
    run_ffmpeg([
        "-f", "lavfi", "-i",
        "color=c=%s:size=1920x1080:rate=30" % BG,
        "-vf", vf, "-frames:v", str(frames),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)])


def build_reveal_artifact(path: Path) -> None:
    """90 frames at 1920x1080: empty, a stepped reveal over frames
    10..29, then the full bar held to frame 89. Matches the plan the
    synthetic job declares (motion [10, 30), hold to 90)."""
    work = path.parent / (path.stem + "-segments")
    work.mkdir(parents=True, exist_ok=True)
    segments = []
    for index, (frames, width) in enumerate([
            (10, None), (5, 300), (5, 600), (5, 900), (5, 1200),
            (60, 1200)]):
        seg = work / ("seg%d.mp4" % index)
        encode_segment(seg, frames, width)
        segments.append(seg)
    listing = work / "concat.txt"
    listing.write_text(
        "".join("file '%s'\n" % s.name for s in segments),
        encoding="utf-8")
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing),
                "-c", "copy", str(path)])
    shutil.rmtree(work)


def build_loop_artifact(path: Path) -> None:
    """30 frames of a box oscillating with a one-second period, so
    the last frame sits one ordinary step before the first."""
    run_ffmpeg([
        "-f", "lavfi", "-i",
        "color=c=%s:size=1920x1080:rate=30:duration=1" % BG,
        "-f", "lavfi", "-i",
        "color=c=%s:size=120x180:rate=30:duration=1" % ACCENT,
        "-filter_complex",
        "[0][1]overlay=x='600+200*sin(2*PI*t)':y=450,format=yuv420p",
        "-frames:v", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(path)])


def build_audio_artifact(src: Path, path: Path) -> None:
    run_ffmpeg([
        "-i", str(src),
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
        "-shortest", str(path)])


def sidecar_for(job_id: str, total: int) -> dict:
    return {
        "schema_version": "1.0", "item": "MG-021", "job_id": job_id,
        "fps": 30, "sample_rate": 48000, "rounding_rule": "round_half_up",
        "mode": "program", "total_frames": total,
        "total_samples": total * 1600,
        "scenes": [{
            "id": "bar-01",
            "placedRange": {"startFrame": 0, "endFrameExclusive": total},
            "durationFrames": total,
            "sourceRange": {"startFrame": 0, "endFrameExclusive": total},
            "sourceRangeSamples": {
                "startSample": 0, "endSampleExclusive": total * 1600},
            "transitionInFrames": 0, "transitionOutFrames": 0}],
        "handles": [], "cues": [], "narration": [], "captions": [],
        "sfx": [], "property_overlaps_declared": [], "slot": None}


def write_job(job_dir: Path, artifact: Path, *,
              job_id: str = "test-powerpoint-job",
              total: int = 90,
              motion: tuple[int, int, int] = (10, 30, 90),
              events: list[dict] | None = None,
              poster_frame: int | None = 45,
              placement: str = "full_frame",
              playback: dict | None = None,
              qc: str | None = "pass",
              mode: str = "powerpoint_graphic") -> Path:
    """Assemble a synthetic delivery job package around an artifact."""
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "renders").mkdir(exist_ok=True)
    (job_dir / "scenes").mkdir(exist_ok=True)
    (job_dir / "data").mkdir(exist_ok=True)
    if qc is not None:
        (job_dir / "qc").mkdir(exist_ok=True)
    manifest = read_json(FIXTURE / "manifest.json")
    manifest["job_id"] = job_id
    manifest["mode"] = mode
    if mode == "standalone_video":
        manifest["content_scope"] = "full_program"
    manifest["duration_frames"] = total
    manifest["delivery"] = {
        "video_profile": "h264_opaque",
        "poster_frame": poster_frame,
        "placement": placement,
        "playback": playback or {
            "start": "on_click", "repeat": "once", "end": "hold_final"},
        "required": ["mp4", "poster", "source_package",
                     "placement_metadata"],
    }
    (job_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    timeline = {
        "schema_version": "2.0", "job_id": job_id, "fps": 30,
        "total_frames": total,
        "scenes": [{
            "id": "bar-01", "start_frame": 0,
            "end_frame_exclusive": total, "source_start_frame": 0,
            "transition_in_frames": 0, "transition_out_frames": 0}],
        "events": events if events is not None else [
            {"id": "reveal-start", "scene_id": "bar-01", "frame": 10,
             "type": "reveal_start"},
            {"id": "final-proof", "scene_id": "bar-01", "frame": 30,
             "type": "proof"},
            {"id": "final-hold", "scene_id": "bar-01", "frame": 30,
             "type": "hold_start"}],
        "parent_slot": None, "audio_owner": "none"}
    (job_dir / "timeline.json").write_text(json.dumps(timeline, indent=1))
    (job_dir / "timeline-sidecar.json").write_text(
        json.dumps(sidecar_for(job_id, total), indent=1))
    shutil.copy(FIXTURE / "storyboard.json", job_dir / "storyboard.json")
    shutil.copy(FIXTURE / "design.json", job_dir / "design.json")
    shutil.copy(FIXTURE / "assets.json", job_dir / "assets.json")
    shutil.copy(FIXTURE / "data" / "bars.json", job_dir / "data" / "bars.json")
    scene = read_json(FIXTURE / "scenes" / "bar-01.json")
    scene["duration_frames"] = total
    scene["motion"] = {
        "kind": "linear_bar_reveal", "start_frame": motion[0],
        "end_frame_exclusive": motion[1],
        "hold_to_frame_exclusive": motion[2],
        "overshoot_data": False}
    scene["semantic_motion_assertions"] = [{
        "id": "mid-reveal", "kind": "bar_widths",
        "subject_ids": ["bar-a", "bar-b", "bar-c"], "frame": 20,
        "expected_values": [240.0, 360.0, 600.0], "tolerance": 1,
        "unit": "source_px", "evidence": ["geometry"]}]
    (job_dir / "scenes" / "bar-01.json").write_text(
        json.dumps(scene, indent=1))
    (job_dir / "media.json").write_text(json.dumps({
        "canvas": {"width": 1920, "height": 1080}, "scenes": [],
        "narration": [], "sfx": [], "music": None,
        "audio": {"mode": "none"}}))
    shutil.copy(artifact, job_dir / "renders" / "final.mp4")
    if qc is not None:
        artifact_sha = sha256_file(job_dir / "renders" / "final.mp4")
        record = {
            "schema_version": "1.0", "item": "MG-034",
            "job_id": job_id if qc != "foreign" else "some-other-job",
            "verdict": "fail" if qc == "fail" else "pass",
            "artifact_sha256": ("0" * 64 if qc == "wrong-hash"
                                else artifact_sha),
            "summary": {
                "total": 3, "pass": 0 if qc == "fail" else 3,
                "fail": 1 if qc == "fail" else 0,
                "failed_checks": (["video.freeze"] if qc == "fail"
                                  else [])}}
        (job_dir / "qc" / "final-qc.json").write_text(
            json.dumps(record, indent=1))
    return job_dir


def fixture_sidecar() -> dict:
    return sidecar_for("fixture-powerpoint-graphic", 180)


# ---------------------------------------------------------------------------
# Poster selection: the plan rule
# ---------------------------------------------------------------------------

class PosterPlanTests(unittest.TestCase):
    """The selection rule on the real C05 fixture records."""

    def setUp(self) -> None:
        self.timeline = read_json(FIXTURE / "timeline.json")
        self.sidecar = fixture_sidecar()
        self.scene = read_json(FIXTURE / "scenes" / "bar-01.json")
        self.delivery = read_json(FIXTURE / "manifest.json")["delivery"]

    def select(self, delivery: dict, scene: dict | None = None,
               timeline: dict | None = None) -> dict:
        return poster_select.plan_selection(
            timeline or self.timeline, self.sidecar,
            [scene or self.scene], delivery)

    def test_declared_poster_in_final_hold_is_honored(self) -> None:
        record = self.select(self.delivery)
        self.assertEqual(record["frame"], 150)
        self.assertEqual(record["rule"],
                         "manifest_declared_in_final_hold")
        self.assertEqual(record["state"], "final_hold")
        self.assertEqual(record["stable_interval"], [75, 180])
        self.assertEqual(record["motion_complete_frame"], 75)

    def test_mid_reveal_declared_poster_is_refused_by_name(self) -> None:
        # Section 17.2: frame 45 shows bars at half reveal while the
        # final value labels print. A poster there is false data.
        delivery = dict(self.delivery, poster_frame=45)
        with self.assertRaises(PosterSelectionError) as caught:
            self.select(delivery)
        err = caught.exception
        self.assertEqual(err.code, "PPTX_POSTER_FRAME_INVALID")
        self.assertEqual(err.category, "MG_QC_FAILED")
        self.assertIn("half-reveal", err.message)
        self.assertIn("240", err.message)

    def test_undeclared_poster_uses_proof_event_in_hold(self) -> None:
        delivery = {k: v for k, v in self.delivery.items()
                    if k != "poster_frame"}
        record = self.select(delivery)
        self.assertEqual(record["frame"], 75)
        self.assertEqual(record["rule"], "proof_event_in_final_hold")

    def test_piece_without_stable_state_is_refused(self) -> None:
        scene = read_json(FIXTURE / "scenes" / "bar-01.json")
        scene["motion"] = dict(scene["motion"], end_frame_exclusive=180,
                               hold_to_frame_exclusive=180)
        timeline = dict(self.timeline, events=[])
        delivery = {k: v for k, v in self.delivery.items()
                    if k != "poster_frame"}
        with self.assertRaises(PosterSelectionError) as caught:
            self.select(delivery, scene=scene, timeline=timeline)
        self.assertEqual(caught.exception.code,
                         "PPTX_POSTER_STATE_UNAVAILABLE")

    def test_loop_representative_declared_frame(self) -> None:
        scene = read_json(FIXTURE / "scenes" / "bar-01.json")
        scene["motion"] = dict(scene["motion"], start_frame=0,
                               end_frame_exclusive=180,
                               hold_to_frame_exclusive=180)
        timeline = dict(self.timeline, events=[])
        delivery = dict(self.delivery, poster_frame=60)
        delivery["playback"] = {
            "start": "automatic", "repeat": "loop", "end": "loop"}
        record = self.select(delivery, scene=scene, timeline=timeline)
        self.assertEqual(record["frame"], 60)
        self.assertEqual(record["rule"], "loop_representative_declared")
        self.assertEqual(record["state"], "loop_representative")

    def test_loop_without_declaration_or_proof_is_refused(self) -> None:
        scene = read_json(FIXTURE / "scenes" / "bar-01.json")
        scene["motion"] = dict(scene["motion"], start_frame=0,
                               end_frame_exclusive=180,
                               hold_to_frame_exclusive=180)
        timeline = dict(self.timeline, events=[])
        delivery = {k: v for k, v in self.delivery.items()
                    if k != "poster_frame"}
        delivery["playback"] = {
            "start": "automatic", "repeat": "loop", "end": "loop"}
        with self.assertRaises(PosterSelectionError) as caught:
            self.select(delivery, scene=scene, timeline=timeline)
        self.assertEqual(caught.exception.code,
                         "PPTX_POSTER_STATE_UNAVAILABLE")


# ---------------------------------------------------------------------------
# Poster selection: measurement against a real artifact
# ---------------------------------------------------------------------------

@unittest.skipUnless(HAVE_TOOLS, "ffmpeg/ffprobe required")
class PosterMeasuredTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mg035-poster-"))
        cls.artifact = cls.tmp / "reveal.mp4"
        build_reveal_artifact(cls.artifact)
        cls.job = write_job(cls.tmp / "job", cls.artifact)

    def test_measured_selection_matches_final_and_not_mid_reveal(self):
        record = poster_select.select_poster(
            self.job, self.job / "renders" / "final.mp4")
        self.assertEqual(record["frame"], 45)
        measured = record["measured"]
        self.assertTrue(measured["equals_final_state"])
        self.assertEqual(measured["mid_reveal_frame"], 20)
        self.assertTrue(measured["differs_from_mid_reveal"])
        self.assertLess(measured["vs_final_frame"]["mean_abs_diff"], 1.0)
        self.assertGreater(
            measured["vs_mid_reveal_frame"]["mean_abs_diff"], 1.0)


# ---------------------------------------------------------------------------
# The packager
# ---------------------------------------------------------------------------

@unittest.skipUnless(HAVE_TOOLS, "ffmpeg/ffprobe required")
class PackagerTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mg035-package-"))
        cls.artifact = cls.tmp / "reveal.mp4"
        build_reveal_artifact(cls.artifact)
        cls.base_job = write_job(cls.tmp / "base-job", cls.artifact)

    def fresh_job(self, name: str = "job", **kwargs) -> Path:
        job = self.tmp / name
        if job.exists():
            shutil.rmtree(job)
        shutil.copytree(self.base_job, job)
        return job

    def package(self, job: Path, name: str = "package-out", **kwargs):
        out = self.tmp / name
        if out.exists():
            shutil.rmtree(out)
        return powerpoint_package.package(job, out, **kwargs)

    def test_happy_path_packages_and_verifies(self) -> None:
        result = self.package(self.fresh_job())
        record = result["record"]
        self.assertEqual(result["status"], "packaged")
        self.assertEqual(record["job_id"], "test-powerpoint-job")
        self.assertEqual(record["artifact"]["sha256"],
                         sha256_file(self.artifact))
        self.assertEqual(record["poster"]["frame"], 45)
        self.assertEqual(record["poster"]["rule"],
                         "manifest_declared_in_final_hold")
        self.assertEqual(record["qc"]["verdict"], "pass")
        self.assertEqual(record["audio"]["resolved_mode"], "none")
        self.assertEqual(record["platform"]["powerpoint_playback"],
                         "UNVERIFIED")
        self.assertEqual(record["checks"]["hold_final"]["status"], "pass")
        self.assertEqual(record["checks"]["loop_seam"]["status"],
                         "not_applicable")
        out = Path(result["package_dir"])
        for name in ("component.mp4", "poster.png", "fallback.png",
                     "deck.pptx", "package-record.json", "final-qc.json",
                     "source/manifest.json", "source/timeline.json"):
            self.assertTrue((out / name).exists(), name)
        verified = powerpoint_package.verify(out)
        self.assertEqual(verified["status"], "verified")

    def test_moved_deck_still_carries_its_media(self) -> None:
        result = self.package(self.fresh_job())
        record = result["record"]
        elsewhere = self.tmp / "somewhere-else"
        elsewhere.mkdir(exist_ok=True)
        moved = elsewhere / "renamed-copy.pptx"
        shutil.copy(Path(result["package_dir"]) / "deck.pptx", moved)
        proof = powerpoint_adapter.verify_deck(
            moved,
            expect_mp4_sha256=record["artifact"]["sha256"],
            expect_fallback_sha256=record["fallback"]["sha256"])
        self.assertTrue(proof["media_matches_packaged_artifact"])
        self.assertTrue(proof["all_relationships_internal"])
        self.assertEqual(proof["external_relationships_on_video_slide"],
                         [])
        self.assertTrue(proof["content_types_declare_mp4"])
        self.assertTrue(proof["poster_is_video_slide_image"])
        self.assertEqual(proof["poster_sha256"],
                         record["poster"]["sha256"])
        self.assertEqual(proof["fallback_slide"]["sha256"],
                         record["fallback"]["sha256"])
        probe = proof["media_probe"]
        self.assertEqual(probe["codec"], "h264")
        self.assertEqual(probe["width"], 1920)
        self.assertEqual(probe["height"], 1080)
        self.assertEqual(probe["frames"], 90)

    def test_missing_qc_record_is_refused(self) -> None:
        job = write_job(self.tmp / "job-no-qc", self.artifact, qc=None)
        with self.assertRaises(PackageError) as caught:
            self.package(job, "out-no-qc")
        self.assertEqual(caught.exception.code, "PPTX_QC_RECORD_MISSING")
        self.assertEqual(caught.exception.category, "MG_INPUT_MISSING")

    def test_failing_qc_verdict_is_refused(self) -> None:
        job = write_job(self.tmp / "job-qc-fail", self.artifact, qc="fail")
        with self.assertRaises(PackageError) as caught:
            self.package(job, "out-qc-fail")
        self.assertEqual(caught.exception.code, "PPTX_QC_NOT_PASSED")
        self.assertEqual(caught.exception.category, "MG_QC_FAILED")
        self.assertIn("video.freeze", caught.exception.message)

    def test_qc_hash_mismatch_is_refused(self) -> None:
        job = write_job(self.tmp / "job-qc-hash", self.artifact,
                        qc="wrong-hash")
        with self.assertRaises(PackageError) as caught:
            self.package(job, "out-qc-hash")
        self.assertEqual(caught.exception.code, "PPTX_QC_HASH_MISMATCH")
        self.assertEqual(caught.exception.category, "MG_HASH_MISMATCH")

    def test_qc_foreign_job_is_refused(self) -> None:
        job = write_job(self.tmp / "job-qc-foreign", self.artifact,
                        qc="foreign")
        with self.assertRaises(PackageError) as caught:
            self.package(job, "out-qc-foreign")
        self.assertEqual(caught.exception.code, "PPTX_QC_FOREIGN_JOB")
        self.assertEqual(caught.exception.category, "MG_FOREIGN_JOB")

    def test_wrong_mode_is_refused(self) -> None:
        job = write_job(self.tmp / "job-wrong-mode", self.artifact,
                        mode="standalone_video")
        with self.assertRaises(PackageError) as caught:
            self.package(job, "out-wrong-mode")
        self.assertEqual(caught.exception.code, "PPTX_MODE_MISMATCH")
        self.assertEqual(caught.exception.category, "MG_MODE_MISMATCH")

    def test_inset_text_below_floor_is_refused_by_name(self) -> None:
        # At a 960 px display width the scale is 0.5: the headline's
        # effective 56 px falls under the 96 px floor.
        with self.assertRaises(PackageError) as caught:
            self.package(self.fresh_job(), "out-inset",
                         display_width="960")
        err = caught.exception
        self.assertEqual(err.code, "PPTX_TEXT_BELOW_FLOOR")
        self.assertEqual(err.category, "MG_QC_FAILED")
        self.assertIn("headline", err.message)

    def test_inset_mm_width_uses_slide_px_per_mm(self) -> None:
        # 254 mm is the full slide width: scale 1.0, passes.
        result = self.package(self.fresh_job(), "out-mm-full",
                              display_width="254mm")
        self.assertEqual(result["record"]["placement"]["scale"], 1.0)
        # 127 mm is half the slide: the same failure as 960 px.
        with self.assertRaises(PackageError) as caught:
            self.package(self.fresh_job(), "out-mm-half",
                         display_width="127mm")
        self.assertEqual(caught.exception.code, "PPTX_TEXT_BELOW_FLOOR")

    def test_audio_stream_in_silent_job_is_refused(self) -> None:
        noisy = self.tmp / "noisy.mp4"
        build_audio_artifact(self.artifact, noisy)
        job = write_job(self.tmp / "job-noisy", noisy)
        with self.assertRaises(PackageError) as caught:
            self.package(job, "out-noisy")
        self.assertEqual(caught.exception.code,
                         "PPTX_AUDIO_MODE_VIOLATION")
        self.assertEqual(caught.exception.category, "MG_MODE_MISMATCH")

    def test_declared_mid_reveal_poster_is_refused(self) -> None:
        job = write_job(self.tmp / "job-bad-poster", self.artifact,
                        poster_frame=20)
        with self.assertRaises(PosterSelectionError) as caught:
            self.package(job, "out-bad-poster")
        self.assertEqual(caught.exception.code,
                         "PPTX_POSTER_FRAME_INVALID")

    def test_loop_seam_is_refused_for_a_reveal(self) -> None:
        job = write_job(
            self.tmp / "job-loop-reveal", self.artifact,
            playback={"start": "automatic", "repeat": "loop",
                      "end": "loop"})
        with self.assertRaises(PackageError) as caught:
            self.package(job, "out-loop-reveal")
        self.assertEqual(caught.exception.code, "PPTX_LOOP_SEAM")
        self.assertEqual(caught.exception.category, "MG_QC_FAILED")

    def test_seamless_loop_packages(self) -> None:
        loop_artifact = self.tmp / "loop.mp4"
        build_loop_artifact(loop_artifact)
        job = write_job(
            self.tmp / "job-loop", loop_artifact, total=30,
            motion=(0, 30, 30),
            events=[{"id": "loop-proof", "scene_id": "bar-01",
                     "frame": 15, "type": "proof"}],
            poster_frame=15,
            playback={"start": "automatic", "repeat": "loop",
                      "end": "loop"})
        result = self.package(job, "out-loop")
        record = result["record"]
        self.assertEqual(record["checks"]["loop_seam"]["status"], "pass")
        self.assertEqual(record["poster"]["rule"],
                         "loop_representative_declared")
        self.assertEqual(record["playback"]["repeat"], "loop")


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------

@unittest.skipUnless(HAVE_TOOLS, "ffmpeg/ffprobe required")
class AdapterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mg035-adapter-"))
        cls.mp4 = cls.tmp / "clip.mp4"
        run_ffmpeg([
            "-f", "lavfi", "-i",
            "testsrc2=size=320x180:rate=30:duration=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.mp4)])
        cls.poster = cls.tmp / "poster.png"
        run_ffmpeg([
            "-f", "lavfi", "-i",
            "color=c=%s:size=320x180" % BG, "-vf",
            "drawbox=x=40:y=60:w=200:h=40:color=%s:t=fill" % ACCENT,
            "-frames:v", "1", str(cls.poster)])

    def build(self, name: str, playback: dict) -> Path:
        out = self.tmp / name
        powerpoint_adapter.build_deck(
            self.mp4, self.poster, self.poster, playback, out,
            title="adapter test")
        return out

    def test_build_and_verify_round_trip(self) -> None:
        deck = self.build("round-trip.pptx", {
            "start": "on_click", "repeat": "once", "end": "hold_final"})
        proof = powerpoint_adapter.verify_deck(
            deck, expect_mp4_sha256=sha256_file(self.mp4),
            expect_fallback_sha256=sha256_file(self.poster))
        self.assertTrue(proof["media_matches_packaged_artifact"])
        self.assertEqual(proof["media_probe"]["frames"], 30)
        self.assertEqual(proof["poster_sha256"],
                         sha256_file(self.poster))

    def test_wrong_expected_hash_is_refused(self) -> None:
        deck = self.build("mismatch.pptx", {
            "start": "on_click", "repeat": "once", "end": "hold_final"})
        with self.assertRaises(AdapterError) as caught:
            powerpoint_adapter.verify_deck(
                deck, expect_mp4_sha256="0" * 64)
        self.assertEqual(caught.exception.code,
                         "PPTX_DECK_MEDIA_MISMATCH")
        self.assertEqual(caught.exception.category, "MG_HASH_MISMATCH")

    def test_playback_metadata_reaches_the_timing_node(self) -> None:
        import zipfile
        auto = self.build("auto-loop.pptx", {
            "start": "automatic", "repeat": "loop", "end": "loop"})
        with zipfile.ZipFile(auto) as zf:
            xml = zf.read("ppt/slides/slide1.xml").decode("utf-8")
        self.assertIn('<p:cond delay="0"/>', xml)
        self.assertIn('repeatCount="indefinite"', xml)
        click = self.build("click-once.pptx", {
            "start": "on_click", "repeat": "once", "end": "hold_final"})
        with zipfile.ZipFile(click) as zf:
            xml = zf.read("ppt/slides/slide1.xml").decode("utf-8")
        self.assertIn('<p:cond delay="indefinite"/>', xml)
        self.assertNotIn('repeatCount', xml)


# ---------------------------------------------------------------------------
# The PDF fallback, as far as this platform allows
# ---------------------------------------------------------------------------

@unittest.skipUnless(HAVE_TOOLS and HAVE_SOFFICE,
                     "ffmpeg, soffice and pdftoppm required")
class PdfFallbackTests(unittest.TestCase):
    """The deck's PDF path on this Linux box runs through
    LibreOffice; PowerPoint's own PDF export stays UNVERIFIED.
    Both PDF pages must render the poster's readable state."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mg035-pdf-"))
        artifact = cls.tmp / "reveal.mp4"
        build_reveal_artifact(artifact)
        job = write_job(cls.tmp / "job", artifact)
        result = powerpoint_package.package(job, cls.tmp / "package")
        cls.package_dir = Path(result["package_dir"])
        cls.poster = cls.package_dir / "poster.png"

    def _mean_abs_diff(self, a: Path, b: Path) -> float:
        def rgb(path: Path, scale: bool) -> bytes:
            args = ["ffmpeg", "-v", "error", "-i", str(path)]
            if scale:
                args += ["-vf", "scale=1920:1080"]
            args += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
            proc = subprocess.run(args, capture_output=True)
            if proc.returncode != 0:
                raise AssertionError("ffmpeg decode failed for %s" % path)
            return proc.stdout
        left, right = rgb(a, False), rgb(b, True)
        self.assertEqual(len(left), len(right))
        return (sum(abs(x - y) for x, y in zip(left, right))
                / len(left))

    def test_pdf_pages_carry_the_poster_state(self) -> None:
        out = self.tmp / "pdf"
        out.mkdir(exist_ok=True)
        proc = subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf",
             str(self.package_dir / "deck.pptx"), "--outdir", str(out)],
            capture_output=True, text=True, timeout=180)
        self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
        pdf = out / "deck.pdf"
        self.assertTrue(pdf.exists())
        proc = subprocess.run(
            ["pdftoppm", "-png", "-r", "192", str(pdf),
             str(self.tmp / "page")],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
        pages = sorted(self.tmp.glob("page-*.png"))
        self.assertEqual(len(pages), 2)
        for page in pages:
            self.assertLessEqual(
                self._mean_abs_diff(self.poster, page), 3.0,
                "%s does not render the poster's readable state"
                % page.name)


if __name__ == "__main__":
    unittest.main()
