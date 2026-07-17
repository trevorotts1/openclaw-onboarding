#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_verify_seams.py — offline-except-ffmpeg unit tests for
scripts/verify_seams.py (Skill 62, build unit U14).

Uses REAL ffmpeg/ffprobe against real synthesized fixtures, chained through
the REAL U13 extract_boundaries.py output format (spec 19.2 "seam metric
fixtures") -- no subprocess mocking, no hand-authored SSIM/PSNR numbers. If
ffmpeg is not on this machine, setUpClass raises loudly rather than skipping.

stdlib unittest only. Run:
  python3 -m unittest discover -s tests/unit -v
  (from the 62-cinematic-web-funnel-engine/ directory)
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"
for p in (str(_SCRIPTS_DIR), str(_SCRIPTS_DIR / "lib")):
    if p not in sys.path:
        sys.path.insert(0, p)

import media_ffmpeg as mf  # noqa: E402
import extract_boundaries as eb  # noqa: E402
import verify_seams as vs  # noqa: E402


def _make_clip(binaries, out_path: Path, *, source: str, extra_args=None, duration=None):
    cmd = [binaries["ffmpeg"], "-y", "-f", "lavfi", "-i", source]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += (extra_args or []) + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path)]
    proc = mf.run_cmd(cmd, label=f"ffmpeg-fixture-{out_path.stem}")
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"could not build fixture {out_path.name}: {proc.stderr[-400:]}")
    return out_path


class TestVerifySeams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binaries = mf.require_binaries()  # fail closed if absent
        cls.tmp = Path(tempfile.mkdtemp(prefix="cwfe-verifyseams-ut-"))

        # Clip A: real testsrc2 motion.
        cls.clip_a = _make_clip(
            cls.binaries, cls.tmp / "clip-a.mp4",
            source="testsrc2=size=96x96:rate=10:duration=1",
        )
        cls.receipt_a = eb.extract_boundaries(cls.clip_a, cls.tmp / "boundaries-a")
        cls.receipt_a_path = cls.tmp / "boundaries-a" / f"{cls.clip_a.stem}.boundary-frames.json"
        last_a = Path({f["position"]: f for f in cls.receipt_a["frames"]}["last"]["output_path"])

        # Clip B: opens by HOLDING clip A's real extracted last frame (a
        # realistic connector-opening-frame stand-in per ADR-9), then
        # continues with more motion -- a genuinely continuous hand-off.
        cls.clip_b = cls.tmp / "clip-b.mp4"
        proc = mf.run_cmd(
            [
                cls.binaries["ffmpeg"], "-y",
                "-loop", "1", "-t", "0.3", "-i", str(last_a),
                "-f", "lavfi", "-i", "testsrc2=size=96x96:rate=10:duration=1",
                "-filter_complex",
                "[0:v]fps=10,format=yuv420p,setsar=1[v0];[1:v]format=yuv420p,setsar=1[v1];"
                "[v0][v1]concat=n=2:v=1:a=0[outv]",
                "-map", "[outv]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.clip_b),
            ],
            label="ffmpeg-fixture-clip-b",
        )
        if proc.returncode != 0 or not cls.clip_b.exists():
            raise RuntimeError(f"could not build continuous clip B: {proc.stderr[-400:]}")
        cls.receipt_b = eb.extract_boundaries(cls.clip_b, cls.tmp / "boundaries-b")
        cls.receipt_b_path = cls.tmp / "boundaries-b" / f"{cls.clip_b.stem}.boundary-frames.json"

        # Clip C: an unrelated, independently-changing pattern (mandelbrot
        # zoom) -- the "hard cut" fixture. Also genuinely changes
        # frame-to-frame so extract_boundaries's own fault detector does
        # not trip on an internally-static source.
        cls.clip_c = _make_clip(
            cls.binaries, cls.tmp / "clip-c.mp4",
            source="mandelbrot=size=96x96:rate=10", duration=1,
        )
        cls.receipt_c = eb.extract_boundaries(cls.clip_c, cls.tmp / "boundaries-c")
        cls.receipt_c_path = cls.tmp / "boundaries-c" / f"{cls.clip_c.stem}.boundary-frames.json"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _out(self, name: str) -> Path:
        return self.tmp / name

    def _sequence(self, *pairs):
        """pairs: list of (clip_id, receipt_path)."""
        return {"clips": [{"clip_id": cid, "boundary_frames_path": str(p)} for cid, p in pairs]}

    # --- classify_seam: pure boundary logic ---

    def test_classify_pass_requires_both_metrics_above_pass_floor(self):
        t = vs.DEFAULT_THRESHOLDS
        self.assertEqual(vs.classify_seam(0.99, 50.0, t), vs.SEAM_STATUS_PASS)
        self.assertEqual(vs.classify_seam(0.99, t["psnr_pass_min"] - 0.01, t), vs.SEAM_STATUS_REVIEW)

    def test_classify_fail_triggers_on_either_metric_below_review_floor(self):
        t = vs.DEFAULT_THRESHOLDS
        self.assertEqual(vs.classify_seam(t["ssim_review_min"] - 0.01, 50.0, t), vs.SEAM_STATUS_FAIL)
        self.assertEqual(vs.classify_seam(0.99, t["psnr_review_min"] - 1.0, t), vs.SEAM_STATUS_FAIL)

    def test_classify_review_band_between_floors(self):
        t = vs.DEFAULT_THRESHOLDS
        mid_ssim = (t["ssim_pass_min"] + t["ssim_review_min"]) / 2
        mid_psnr = (t["psnr_pass_min"] + t["psnr_review_min"]) / 2
        self.assertEqual(vs.classify_seam(mid_ssim, mid_psnr, t), vs.SEAM_STATUS_REVIEW)

    # --- compute_frame_similarity: real ffmpeg SSIM/PSNR ---

    def test_identical_frames_score_perfect_similarity(self):
        by_pos = {f["position"]: f for f in self.receipt_a["frames"]}
        frame = Path(by_pos["last"]["output_path"])
        metrics = vs.compute_frame_similarity(self.binaries, frame, frame)
        self.assertGreaterEqual(metrics["ssim"], 0.999)
        self.assertGreaterEqual(metrics["psnr_db"], 90.0)

    def test_continuous_handoff_beats_hard_cut_on_both_metrics(self):
        by_pos_a = {f["position"]: f for f in self.receipt_a["frames"]}
        by_pos_b = {f["position"]: f for f in self.receipt_b["frames"]}
        by_pos_c = {f["position"]: f for f in self.receipt_c["frames"]}
        cont = vs.compute_frame_similarity(
            self.binaries, Path(by_pos_a["last"]["output_path"]), Path(by_pos_b["first"]["output_path"]),
        )
        cut = vs.compute_frame_similarity(
            self.binaries, Path(by_pos_a["last"]["output_path"]), Path(by_pos_c["first"]["output_path"]),
        )
        self.assertGreater(cont["ssim"], cut["ssim"])
        self.assertGreater(cont["psnr_db"], cut["psnr_db"])
        self.assertEqual(vs.classify_seam(cont["ssim"], cont["psnr_db"], vs.DEFAULT_THRESHOLDS), vs.SEAM_STATUS_PASS)
        self.assertEqual(vs.classify_seam(cut["ssim"], cut["psnr_db"], vs.DEFAULT_THRESHOLDS), vs.SEAM_STATUS_FAIL)

    def test_dimension_mismatch_rejected(self):
        by_pos_a = {f["position"]: f for f in self.receipt_a["frames"]}
        small = self._out("small.png")
        proc = mf.run_cmd(
            [self.binaries["ffmpeg"], "-y", "-f", "lavfi", "-i", "color=c=green:s=48x48:d=1:r=1",
             "-frames:v", "1", str(small)],
            label="ffmpeg-fixture-small",
        )
        self.assertEqual(proc.returncode, 0)
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            vs.compute_frame_similarity(self.binaries, Path(by_pos_a["last"]["output_path"]), small)
        self.assertEqual(ctx.exception.reason, "seam-dimension-mismatch")

    # --- verify_seams(): end-to-end sequence ---

    def test_two_clip_continuous_sequence_passes(self):
        sequence = self._sequence(("a", self.receipt_a_path), ("b", self.receipt_b_path))
        report = vs.verify_seams(sequence, thresholds=vs.DEFAULT_THRESHOLDS, out_dir=self._out("out1"))
        self.assertEqual(report["seam_count"], 1)
        self.assertEqual(report["overall_status"], vs.SEAM_STATUS_PASS)
        self.assertEqual(report["seams"][0]["seam_id"], "a->b")

    def test_two_clip_hard_cut_sequence_fails_and_raises_by_default(self):
        sequence = self._sequence(("a", self.receipt_a_path), ("c", self.receipt_c_path))
        with self.assertRaises(vs.SeamDiscontinuityError) as ctx:
            vs.verify_seams(sequence, thresholds=vs.DEFAULT_THRESHOLDS, out_dir=self._out("out2"))
        self.assertEqual(ctx.exception.report["overall_status"], vs.SEAM_STATUS_FAIL)

    def test_fail_closed_false_returns_failed_report_without_raising(self):
        sequence = self._sequence(("a", self.receipt_a_path), ("c", self.receipt_c_path))
        report = vs.verify_seams(
            sequence, thresholds=vs.DEFAULT_THRESHOLDS, out_dir=self._out("out3"), fail_closed=False,
        )
        self.assertEqual(report["overall_status"], vs.SEAM_STATUS_FAIL)

    def test_report_written_atomically_and_round_trips(self):
        sequence = self._sequence(("a", self.receipt_a_path), ("b", self.receipt_b_path))
        out_dir = self._out("out4")
        report = vs.verify_seams(sequence, thresholds=vs.DEFAULT_THRESHOLDS, out_dir=out_dir)
        report_path = out_dir / vs.DEFAULT_REPORT_FILENAME
        self.assertTrue(report_path.exists())
        self.assertEqual(json.loads(report_path.read_text(encoding="utf-8")), report)

    def test_report_evidence_survives_a_fail_closed_raise(self):
        sequence = self._sequence(("a", self.receipt_a_path), ("c", self.receipt_c_path))
        out_dir = self._out("out5")
        with self.assertRaises(vs.SeamDiscontinuityError):
            vs.verify_seams(sequence, thresholds=vs.DEFAULT_THRESHOLDS, out_dir=out_dir)
        self.assertTrue((out_dir / vs.DEFAULT_REPORT_FILENAME).exists())

    def test_three_clip_chain_produces_two_seams_with_correct_ids(self):
        sequence = self._sequence(
            ("scene-1", self.receipt_a_path), ("connector-1-2", self.receipt_b_path), ("scene-2", self.receipt_c_path),
        )
        report = vs.verify_seams(sequence, thresholds=vs.DEFAULT_THRESHOLDS, out_dir=self._out("out6"), fail_closed=False)
        self.assertEqual(report["seam_count"], 2)
        seam_ids = [s["seam_id"] for s in report["seams"]]
        self.assertEqual(seam_ids, ["scene-1->connector-1-2", "connector-1-2->scene-2"])
        # scene-1 -> connector-1-2 is the genuinely continuous pair -> pass.
        # connector-1-2 -> scene-2 is the hard-cut pair -> fail.
        by_id = {s["seam_id"]: s for s in report["seams"]}
        self.assertEqual(by_id["scene-1->connector-1-2"]["status"], vs.SEAM_STATUS_PASS)
        self.assertEqual(by_id["connector-1-2->scene-2"]["status"], vs.SEAM_STATUS_FAIL)
        self.assertEqual(report["overall_status"], vs.SEAM_STATUS_FAIL)

    def test_fewer_than_two_clips_rejected(self):
        sequence = self._sequence(("a", self.receipt_a_path))
        with self.assertRaises(mf.MediaProcessingError):
            vs.verify_seams(sequence, thresholds=vs.DEFAULT_THRESHOLDS, out_dir=self._out("out7"))

    def test_duplicate_clip_id_rejected(self):
        sequence = self._sequence(("dup", self.receipt_a_path), ("dup", self.receipt_b_path))
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            vs.verify_seams(sequence, thresholds=vs.DEFAULT_THRESHOLDS, out_dir=self._out("out8"))
        self.assertEqual(ctx.exception.reason, "seam-sequence-invalid")

    def test_missing_boundary_frame_position_rejected(self):
        one_pos_dir = self._out("one-position")
        eb.extract_boundaries(self.clip_a, one_pos_dir, positions=["first"])
        one_pos_receipt = one_pos_dir / f"{self.clip_a.stem}.boundary-frames.json"
        sequence = self._sequence(("missing-last", one_pos_receipt), ("b", self.receipt_b_path))
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            vs.verify_seams(sequence, thresholds=vs.DEFAULT_THRESHOLDS, out_dir=self._out("out9"))
        self.assertEqual(ctx.exception.reason, "seam-sequence-invalid")

    def test_nonexistent_boundary_frames_path_rejected(self):
        sequence = self._sequence(("a", self.receipt_a_path), ("ghost", self.tmp / "does-not-exist.json"))
        with self.assertRaises(mf.MediaProcessingError):
            vs.verify_seams(sequence, thresholds=vs.DEFAULT_THRESHOLDS, out_dir=self._out("out10"))

    def test_malformed_sequence_missing_clips_key_rejected(self):
        with self.assertRaises(mf.MediaProcessingError):
            vs.verify_seams({}, thresholds=vs.DEFAULT_THRESHOLDS, out_dir=self._out("out11"))

    def test_fails_closed_when_ffprobe_unavailable(self):
        import os
        sequence = self._sequence(("a", self.receipt_a_path), ("b", self.receipt_b_path))
        os.environ[mf.FFPROBE_ENV] = "/nonexistent/ffprobe"
        try:
            with self.assertRaises(mf.MediaToolingUnavailable):
                vs.verify_seams(sequence, thresholds=vs.DEFAULT_THRESHOLDS, out_dir=self._out("out12"))
        finally:
            del os.environ[mf.FFPROBE_ENV]

    # --- load_thresholds ---

    def test_load_thresholds_defaults_when_no_path(self):
        self.assertEqual(vs.load_thresholds(None), vs.DEFAULT_THRESHOLDS)

    def test_load_thresholds_overrides_a_subset(self):
        path = self._out("custom-thresholds.json")
        path.write_text(json.dumps({"ssim_pass_min": 0.95}), encoding="utf-8")
        thresholds = vs.load_thresholds(path)
        self.assertEqual(thresholds["ssim_pass_min"], 0.95)
        self.assertEqual(thresholds["psnr_pass_min"], vs.DEFAULT_THRESHOLDS["psnr_pass_min"])

    def test_load_thresholds_rejects_unknown_key(self):
        path = self._out("bad-thresholds.json")
        path.write_text(json.dumps({"nonexistent_key": 1}), encoding="utf-8")
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            vs.load_thresholds(path)
        self.assertEqual(ctx.exception.reason, "seam-thresholds-invalid")

    def test_load_thresholds_rejects_inverted_band(self):
        path = self._out("inverted-thresholds.json")
        path.write_text(json.dumps({"psnr_review_min": 40.0, "psnr_pass_min": 10.0}), encoding="utf-8")
        with self.assertRaises(mf.MediaProcessingError) as ctx:
            vs.load_thresholds(path)
        self.assertEqual(ctx.exception.reason, "seam-thresholds-invalid")

    # --- evaluate(): CWFE-MANIFEST.json P10-ENCODE-SEAM gate contract ---

    def test_evaluate_fails_closed_when_sequence_file_absent(self):
        run_dir = self._out("gate-no-sequence")
        run_dir.mkdir(parents=True, exist_ok=True)
        passed, detail = vs.evaluate(run_dir)
        self.assertFalse(passed)
        self.assertIn(vs.AF_CODE, detail)

    def test_evaluate_passes_and_writes_report_for_continuous_sequence(self):
        run_dir = self._out("gate-pass")
        run_dir.mkdir(parents=True, exist_ok=True)
        sequence = self._sequence(("a", self.receipt_a_path), ("b", self.receipt_b_path))
        (run_dir / vs.DEFAULT_SEQUENCE_FILENAME).write_text(json.dumps(sequence), encoding="utf-8")
        passed, detail = vs.evaluate(run_dir)
        self.assertTrue(passed)
        self.assertTrue((run_dir / vs.DEFAULT_REPORT_FILENAME).exists())

    def test_evaluate_does_not_pass_for_hard_cut_sequence(self):
        run_dir = self._out("gate-fail")
        run_dir.mkdir(parents=True, exist_ok=True)
        sequence = self._sequence(("a", self.receipt_a_path), ("c", self.receipt_c_path))
        (run_dir / vs.DEFAULT_SEQUENCE_FILENAME).write_text(json.dumps(sequence), encoding="utf-8")
        passed, detail = vs.evaluate(run_dir)
        self.assertFalse(passed)
        self.assertTrue((run_dir / vs.DEFAULT_REPORT_FILENAME).exists(), "gate must still write evidence on a failed run")

    def test_evaluate_respects_sequence_path_env_override(self):
        import os
        run_dir = self._out("gate-env-override")
        run_dir.mkdir(parents=True, exist_ok=True)
        elsewhere = self._out("elsewhere-sequence.json")
        sequence = self._sequence(("a", self.receipt_a_path), ("b", self.receipt_b_path))
        elsewhere.write_text(json.dumps(sequence), encoding="utf-8")
        os.environ[vs.SEQUENCE_PATH_ENV] = str(elsewhere)
        try:
            passed, _detail = vs.evaluate(run_dir)
            self.assertTrue(passed)
        finally:
            del os.environ[vs.SEQUENCE_PATH_ENV]

    def test_evaluate_respects_thresholds_path_env_override(self):
        import os
        run_dir = self._out("gate-thresholds-override")
        run_dir.mkdir(parents=True, exist_ok=True)
        sequence = self._sequence(("a", self.receipt_a_path), ("c", self.receipt_c_path))
        (run_dir / vs.DEFAULT_SEQUENCE_FILENAME).write_text(json.dumps(sequence), encoding="utf-8")
        # Loosen the thresholds so far that even the hard-cut pair passes --
        # proves the override path is actually wired, not merely accepted.
        lax_thresholds = self._out("lax-thresholds.json")
        lax_thresholds.write_text(json.dumps({"ssim_pass_min": 0.0, "psnr_pass_min": 0.0, "ssim_review_min": -1.0, "psnr_review_min": 0.0}), encoding="utf-8")
        os.environ[vs.THRESHOLDS_PATH_ENV] = str(lax_thresholds)
        try:
            passed, _detail = vs.evaluate(run_dir)
            self.assertTrue(passed)
        finally:
            del os.environ[vs.THRESHOLDS_PATH_ENV]


if __name__ == "__main__":
    unittest.main()
