"""Tests for the MG-031 coverage-indexed review bundle builder.

The builder (scripts/critique_bundle.py) replaces the legacy
critique-bundle.sh assembler, whose 8x8 tile at 2 fps showed only the
first 32 seconds of a video and whose exit status never reflected a
failed sheet. These tests prove the MG-031 acceptance behaviors:

- A five-minute fixture with a planted visible defect at 4:50 has the
  defect inside the bundle's samples, proven by decoded-pixel
  measurement, not by eye.
- The coverage record accounts for 100 percent of the runtime as
  covered or explicitly omitted-with-reason; sheets paginate instead
  of truncating.
- Two concurrent builds for different jobs produce disjoint file
  sets with both coverage records intact.
- A forced sheet-generation failure exits nonzero (5,
  MG_ENCODE_FAILED) and the string PASS appears nowhere in output.
- A timeline that declares frames beyond the probed video exits 6
  (MG_COVERAGE_INCOMPLETE) with the missing range recorded as
  omitted.

Fixture videos are synthesized with ffmpeg lavfi sources in a
temporary directory (testsrc2; the long fixture gains a full-frame
red drawbox between t=290 and t=294 as the planted defect). The
committed fixtures under tests/fixtures/review/ are the compiled
timeline, sidecar, and preview review records the builds consume.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import critique_bundle  # noqa: E402

FIXTURES = SKILL_ROOT / "tests" / "fixtures" / "review"
SCRIPT = SKILL_ROOT / "scripts" / "critique_bundle.py"
WRAPPER = SKILL_ROOT / "scripts" / "critique-bundle.sh"


def make_video(path: Path, size: str, seconds: int,
               defect: bool = False) -> None:
    argv = [
        "ffmpeg", "-v", "error", "-f", "lavfi",
        "-i", f"testsrc2=size={size}:rate=30:duration={seconds}",
    ]
    if defect:
        argv += [
            "-vf",
            "drawbox=x=0:y=0:w=iw:h=ih:color=red:t=fill:"
            "enable='between(t,290,294)'",
        ]
    argv += [
        "-c:v", "libx264", "-crf", "30", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-y", str(path),
    ]
    subprocess.run(argv, check=True, capture_output=True, text=True)


def run_build(argv: list[str]) -> tuple[int, dict]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = critique_bundle.main(argv)
    return code, json.loads(buffer.getvalue())


def frame_means(png: Path) -> tuple[float, float, float]:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(png),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True,
    ).stdout
    count = len(raw) // 3
    assert count > 0
    return (
        sum(raw[0::3]) / count,
        sum(raw[1::3]) / count,
        sum(raw[2::3]) / count,
    )


def samples_by(coverage: dict, kind: str) -> list[dict]:
    return [s for s in coverage["samples"] if s["kind"] == kind]


class FixtureBase(unittest.TestCase):
    """Shared synthesized videos in one temporary directory."""

    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("ffmpeg") is None:
            raise unittest.SkipTest(
                "ffmpeg is required to synthesize critique fixtures")
        cls.tmp = Path(tempfile.mkdtemp(prefix="mg031-tests-"))
        cls.short_video = cls.tmp / "short.mp4"
        make_video(cls.short_video, "640x360", 12)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def outdir(self, name: str) -> Path:
        return self.tmp / name


class FiveMinuteDefectTests(FixtureBase):
    """Acceptance (a) and (d): late defect sampled; full accounting."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.long_video = cls.tmp / "long.mp4"
        make_video(cls.long_video, "320x180", 300, defect=True)
        cls.bundle = cls.tmp / "long-bundle"
        code, report = run_build([
            "build", "--video", str(cls.long_video),
            "--outdir", str(cls.bundle),
            "--timeline", str(FIXTURES / "long-timeline.json"),
            "--interval", "5",
        ])
        assert code == 0, report
        cls.coverage = json.loads(
            (cls.bundle / "mg031-long-fixture__coverage.json")
            .read_text(encoding="utf-8")
        )

    def test_defect_frame_is_sampled_and_measures_red(self) -> None:
        interval_frames = {
            s["frame"] for s in samples_by(self.coverage, "interval")
        }
        # t=290s at 30 fps is frame 8700, inside the defect window.
        self.assertIn(8700, interval_frames)
        sample = next(
            s for s in self.coverage["samples"]
            if s["frame"] == 8700 and s["kind"] == "interval"
        )
        self.assertEqual(sample["status"], "extracted")
        png = self.bundle / sample["files"]["full"]
        red, green, blue = frame_means(png)
        self.assertGreater(red, 150)
        self.assertGreater(red - green, 80)
        self.assertGreater(red - blue, 80)

    def test_control_frame_does_not_measure_red(self) -> None:
        sample = next(
            s for s in self.coverage["samples"]
            if s["frame"] == 6000 and s["kind"] == "interval"
        )
        red, green, _blue = frame_means(self.bundle / sample["files"]["full"])
        self.assertLess(abs(red - green), 40)

    def test_coverage_accounts_for_the_full_runtime(self) -> None:
        math_block = self.coverage["coverage"]
        self.assertEqual(math_block["accounted_frames"], 9000)
        self.assertEqual(math_block["covered_frames"], 9000)
        self.assertEqual(math_block["omitted_frames"], 0)
        self.assertEqual(math_block["omitted_intervals"], [])
        self.assertEqual(
            math_block["covered_intervals"],
            [{"start_frame": 0, "end_frame_exclusive": 9000,
              "start_seconds": 0.0, "end_seconds": 300.0}],
        )
        self.assertEqual(self.coverage["verdict"], "complete")

    def test_interval_sheets_paginate_without_truncation(self) -> None:
        pages = self.coverage["sheets"]["interval"]
        self.assertEqual(len(pages), 4)
        carried: list[str] = []
        for page in pages:
            self.assertLessEqual(len(page["frames"]), 16)
            self.assertTrue((self.bundle / "sheets" / page["path"]).is_file())
            carried.extend(page["frames"])
        interval_files = {
            Path(s["files"]["full"]).name
            for s in samples_by(self.coverage, "interval")
        }
        self.assertEqual(set(carried), interval_files)
        self.assertEqual(len(carried), 60)


class TargetedFrameTests(FixtureBase):
    """Targeted frames come from the compiled timeline and sidecar."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.bundle = cls.tmp / "short-bundle"
        code, report = run_build([
            "build", "--video", str(cls.short_video),
            "--outdir", str(cls.bundle),
            "--timeline", str(FIXTURES / "short-timeline.json"),
            "--sidecar", str(FIXTURES / "short-sidecar.json"),
            "--review-record", str(FIXTURES / "short-review-record.json"),
            "--destination", "180x320",
            "--interval", "5",
        ])
        assert code == 0, report
        cls.coverage = json.loads(
            (cls.bundle / "mg031-beta__coverage.json")
            .read_text(encoding="utf-8")
        )

    def test_targeted_kinds_and_frames(self) -> None:
        by_kind: dict[str, set[int]] = {}
        for sample in self.coverage["samples"]:
            by_kind.setdefault(sample["kind"], set()).add(sample["frame"])
        self.assertEqual(by_kind["scene_boundary_start"], {0, 180})
        self.assertEqual(by_kind["scene_boundary_end"], {179, 359})
        self.assertEqual(by_kind["reveal_start"], {15})
        self.assertEqual(by_kind["proof"], {75})
        self.assertEqual(by_kind["hold_start"], {300})
        self.assertEqual(by_kind["text_swap"], {200})
        self.assertEqual(by_kind["final_frame"], {359})
        text_swap = samples_by(self.coverage, "text_swap")[0]
        # Frame 200 sits inside scene s2 ([180, 360)); the compiled
        # sidecar's caption tracks carry no scene id, so the builder
        # attributes the scene from the timeline placement.
        self.assertEqual(text_swap["scene_id"], "s2")
        self.assertEqual(text_swap["ref"], "cap-1")
        self.assertTrue(
            all(s["status"] == "extracted"
                for s in self.coverage["samples"])
        )

    def test_full_and_destination_dimensions_are_exact(self) -> None:
        for sample in self.coverage["samples"]:
            full = self.bundle / sample["files"]["full"]
            self.assertEqual(
                critique_bundle.png_dimensions(full), (640, 360)
            )
            dest = self.bundle / sample["files"]["dest-180x320"]
            self.assertEqual(
                critique_bundle.png_dimensions(dest), (180, 320)
            )

    def test_review_record_and_video_hashes_are_bound(self) -> None:
        bound = self.coverage["inputs"]["review_record"]
        self.assertEqual(bound["source_hash"], "a" * 64)
        self.assertEqual(bound["props_hash"], "b" * 64)
        self.assertEqual(bound["preview_hash"], "c" * 64)
        self.assertEqual(bound["label"], "preview")
        self.assertEqual(
            self.coverage["video"]["sha256"],
            critique_bundle.sha256_file(self.short_video),
        )


class ConcurrencyTests(FixtureBase):
    """Acceptance (b): two concurrent jobs, disjoint, both intact."""

    def _timeline_for(self, job_id: str) -> Path:
        data = json.loads(
            (FIXTURES / "short-timeline.json").read_text(encoding="utf-8")
        )
        data["job_id"] = job_id
        path = self.tmp / f"timeline-{job_id}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_two_concurrent_jobs_in_one_directory(self) -> None:
        shared = self.outdir("shared")
        commands = []
        for job_id in ("mg031-alpha", "mg031-beta"):
            commands.append(subprocess.Popen(
                [
                    sys.executable, str(SCRIPT), "build",
                    "--video", str(self.short_video),
                    "--outdir", str(shared),
                    "--job-id", job_id,
                    "--timeline", str(self._timeline_for(job_id)),
                    "--interval", "5",
                ],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
            ))
        results = [proc.communicate() for proc in commands]
        for proc, (stdout, _stderr) in zip(commands, results):
            self.assertEqual(proc.returncode, 0, stdout)

        stills = {
            p.name for p in (shared / "frames" / "full").glob("*.png")
        }
        alpha = {n for n in stills if n.startswith("mg031-alpha__")}
        beta = {n for n in stills if n.startswith("mg031-beta__")}
        self.assertTrue(alpha)
        self.assertTrue(beta)
        self.assertFalse(alpha & beta)
        self.assertEqual(alpha | beta, stills)

        for job_id in ("mg031-alpha", "mg031-beta"):
            record = json.loads(
                (shared / f"{job_id}__coverage.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(record["verdict"], "complete")
            self.assertEqual(record["job_id"], job_id)
            for sample in record["samples"]:
                self.assertTrue(
                    sample["files"]["full"].split("/")[-1]
                    .startswith(job_id + "__")
                )
        plain = json.loads(
            (shared / "coverage.json").read_text(encoding="utf-8")
        )
        self.assertIn(plain["job_id"], ("mg031-alpha", "mg031-beta"))


class FailureBehaviorTests(FixtureBase):
    """Acceptance (c) plus the coverage-incomplete and foreign paths."""

    def test_sheet_failure_exits_5_without_pass(self) -> None:
        outdir = self.outdir("sheet-fail")
        outdir.mkdir(parents=True)
        (outdir / "sheets").write_text("blocked", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable, str(SCRIPT), "build",
                "--video", str(self.short_video),
                "--outdir", str(outdir),
                "--job-id", "mg031-fail",
                "--interval", "5",
            ],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 5, result.stdout)
        combined = result.stdout + result.stderr
        self.assertNotIn("PASS", combined)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["category"], "MG_ENCODE_FAILED")

    def test_timeline_beyond_video_exits_6_with_omission(self) -> None:
        outdir = self.outdir("beyond")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = critique_bundle.main([
                "build", "--video", str(self.short_video),
                "--outdir", str(outdir),
                "--timeline", str(FIXTURES / "beyond-timeline.json"),
                "--interval", "5",
            ])
        self.assertEqual(code, 6)
        self.assertNotIn("PASS", buffer.getvalue())
        coverage = json.loads(
            (outdir / "mg031-beta__coverage.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(coverage["verdict"], "incomplete")
        math_block = coverage["coverage"]
        self.assertEqual(math_block["accounted_frames"], 720)
        self.assertEqual(math_block["covered_frames"], 360)
        self.assertEqual(len(math_block["omitted_intervals"]), 1)
        omitted = math_block["omitted_intervals"][0]
        self.assertEqual(omitted["start_frame"], 360)
        self.assertEqual(omitted["end_frame_exclusive"], 720)
        self.assertEqual(omitted["reason"], "beyond_probed_video_frames")
        late = [s for s in coverage["samples"] if s["frame"] >= 360]
        self.assertTrue(late)
        self.assertTrue(all(s["status"] == "omitted" for s in late))

    def test_foreign_review_record_exits_9(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = critique_bundle.main([
                "build", "--video", str(self.short_video),
                "--outdir", str(self.outdir("foreign")),
                "--job-id", "mg031-other",
                "--review-record",
                str(FIXTURES / "short-review-record.json"),
            ])
        self.assertEqual(code, 9)
        report = json.loads(buffer.getvalue())
        self.assertEqual(report["category"], "MG_FOREIGN_JOB")


class VideoOnlyTests(FixtureBase):
    def test_video_without_timeline_covers_probed_runtime(self) -> None:
        outdir = self.outdir("video-only")
        code, report = run_build([
            "build", "--video", str(self.short_video),
            "--outdir", str(outdir), "--interval", "5",
        ])
        self.assertEqual(code, 0, report)
        coverage = json.loads(
            (outdir / "short__coverage.json").read_text(encoding="utf-8")
        )
        self.assertEqual(coverage["declared_total_frames"], 360)
        self.assertEqual(coverage["coverage"]["accounted_frames"], 360)
        interval_frames = {
            s["frame"] for s in samples_by(coverage, "interval")
        }
        self.assertEqual(interval_frames, {0, 150, 300})
        finals = samples_by(coverage, "final_frame")
        self.assertEqual([s["frame"] for s in finals], [359])


class WrapperTests(FixtureBase):
    def test_legacy_wrapper_delegates_and_derives_job(self) -> None:
        named = self.tmp / "jobwrap.mp4"
        shutil.copyfile(self.short_video, named)
        outdir = self.outdir("wrapped")
        result = subprocess.run(
            ["bash", str(WRAPPER), "--video", str(named),
             "--outdir", str(outdir)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        coverage = json.loads(
            (outdir / "jobwrap__coverage.json").read_text(encoding="utf-8")
        )
        self.assertEqual(coverage["verdict"], "complete")
        self.assertEqual(coverage["job_id"], "jobwrap")


class PlanningMathTests(unittest.TestCase):
    """Pure planning: pagination and coverage math without media."""

    def test_interval_plan_and_coverage_math(self) -> None:
        samples = critique_bundle.plan_samples(
            9000, Fraction(30, 1), 5.0, None, None, None
        )
        interval = [s["frame"] for s in samples if s["kind"] == "interval"]
        self.assertEqual(interval, list(range(0, 9000, 150)))
        for sample in samples:
            sample["status"] = "extracted"
        math_block = critique_bundle.compute_coverage(
            samples, 9000, 9000, Fraction(30, 1)
        )
        self.assertEqual(math_block["covered_frames"], 9000)
        self.assertEqual(math_block["omitted_frames"], 0)
        self.assertEqual(math_block["accounted_frames"], 9000)


if __name__ == "__main__":
    unittest.main()
