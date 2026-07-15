#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_seams.py — real seam-continuity QC (Skill 62, build unit U14).

CWFE-MANIFEST.json wires this module to the P10-ENCODE-SEAM phase gate:

    {"id": "P10-ENCODE-SEAM", "gate": "scripts/verify_seams.py",
     "py_symbol": "verify_seams.evaluate", "af_code": "AF-CWFE-P10-ENCODE-SEAM"}

Implements spec Section 12.3 ("Seam QC"):

    Use SSIM and at least one complementary perceptual metric or
    visual-difference method. Initial policy may mirror: high-confidence
    pass; review band; fail/regenerate band. Do not freeze thresholds
    without testing against the engine's own fixtures.

and ADR-9 ("Real encoded boundary frames are authoritative": the next clip
or connector starts from the actual final frame extracted from the encoded
preceding clip, not from the original still and not solely from a
provider-returned preview frame).

WHAT THIS MODULE OWNS: given an ORDERED sequence of clips (scenes and/or
connectors), each already processed by U13's extract_boundaries.py into its
own boundary-frames.json receipt, this module computes REAL ffmpeg SSIM and
PSNR between clip[i]'s "last" frame and clip[i+1]'s "first" frame for every
adjacent pair, classifies each seam into pass/review/fail per calibrated
thresholds, and writes seam-report.json. It does NOT re-extract frames (that
is extract_boundaries.py, U13) and does NOT re-encode media (that is
encode_scrub_media.py, U13) -- it consumes their output.

Every ffmpeg/ffprobe call goes through scripts/lib/media_ffmpeg.py, which is
fail-closed: if the binaries are not resolvable, this module raises before
comparing anything. A seam-report.json is only ever written after every seam
it lists has an independently computed real measurement -- it is evidence,
never a placeholder. Beyond that, this module is ALSO fail-closed on its own
verdict: a seam whose SSIM/PSNR lands in the fail/regenerate band is a real
continuity discontinuity, and verify_seams() raises SeamDiscontinuityError
for it by default (the report is written to disk FIRST, so the evidence
survives the raise) -- callers that need to inspect a failed report without
an exception (the phase-gate evaluate() below) pass fail_closed=False and
read report["overall_status"] themselves.

stdlib only. CLI:
    python3 verify_seams.py --run-dir RUN_DIR
        (phase-gate mode -- CWFE-MANIFEST.json's uniform gate contract;
        reads RUN_DIR/seam-sequence.json, writes RUN_DIR/seam-report.json)
    python3 verify_seams.py --sequence SEQUENCE.json --out-dir DIR
        [--thresholds THRESHOLDS.json] [--report-path PATH]
        (standalone mode)
    python3 verify_seams.py --self-test

Exit codes: 0 pass, 2 fail (discontinuity, processing error, or tooling
unavailable), 3 usage error / self-test failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_STRUCTURE_DIR = _SKILL_DIR / "structure"

sys.path.insert(0, str(_SCRIPT_DIR / "lib"))
import media_ffmpeg as mf  # noqa: E402

SCHEMA_VERSION = "1.0.0"
SEQUENCE_SCHEMA_FILE = "seam-sequence.schema.json"
REPORT_SCHEMA_FILE = "seam-report.schema.json"

AF_CODE = "AF-CWFE-P10-ENCODE-SEAM"

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

DEFAULT_SEQUENCE_FILENAME = "seam-sequence.json"
DEFAULT_REPORT_FILENAME = "seam-report.json"

# Env-var override convention matches prove_p0_environment.py: the
# orchestrator invokes every phase gate uniformly as
# `python3 <gate> --run-dir <run_dir>` with no phase-specific CLI flags, so
# per-run configuration (a non-default thresholds file, or an explicit
# sequence path) travels through environment variables instead.
SEQUENCE_PATH_ENV = "CWFE_SEAM_SEQUENCE_PATH"
THRESHOLDS_PATH_ENV = "CWFE_SEAM_THRESHOLDS_PATH"

# ffmpeg reports an infinite PSNR for two byte-for-byte-identical frames.
# `float("inf")` round-trips through Python's json module as the
# non-standard `Infinity` token, which not every JSON consumer accepts, so
# a genuinely infinite PSNR is recorded as this large finite sentinel
# instead -- well above any realistic psnr_pass_min, so classification is
# unaffected, and the report stays strictly valid JSON.
PSNR_INFINITY_SENTINEL_DB = 100.0

SEAM_STATUS_PASS = "pass"
SEAM_STATUS_REVIEW = "review"
SEAM_STATUS_FAIL = "fail"

# Calibrated per spec 12.3 ("Do not freeze thresholds without testing
# against the engine's own fixtures. Build a fixture set of known-good,
# borderline, and bad seams; calibrate thresholds and pin them in the QC
# contract."). Calibrated here against this unit's own
# tests/unit/test_verify_seams.py real-ffmpeg fixtures:
#   - a genuinely continuous hand-off (a still frame held then continued
#     with motion, the realistic shape of a connector's own opening frame
#     after a provider round-trip) scores SSIM > 0.95 / PSNR well over
#     40 dB -- comfortably inside the pass band;
#   - a hard cut between two unrelated solid colors (what a broken/failed
#     connector produces, spec 9.4 "reject continuity drift rather than
#     hiding it behind a hard cut without approval") scores SSIM well under
#     0.3 -- comfortably inside the fail band.
# The review band between them is intentionally wide at this calibration
# pass (no real-world borderline connector-output corpus exists yet to
# narrow it further); a later unit with real generated-media QC data should
# re-narrow it and record the revised evidence here per spec 12.3's
# "calibrate ... and pin them in the QC contract" instruction.
DEFAULT_THRESHOLDS: Dict[str, float] = {
    "ssim_pass_min": 0.90,
    "ssim_review_min": 0.60,
    "psnr_pass_min": 28.0,
    "psnr_review_min": 15.0,
}


class SeamDiscontinuityError(mf.MediaProcessingError):
    """Raised by verify_seams(fail_closed=True) when overall_status is
    'fail' -- i.e. at least one seam fell below its review-band floor on
    either metric. Carries the already-written report (`.report`) so a
    caller that chooses to catch this still has the full evidence, not just
    a message. Fail band only -- the 'review' band deliberately does NOT
    raise here (spec 12.3's three-tier language: review means "needs a
    human look", not "proven discontinuous"; see evaluate() below, which
    still refuses to PASS the phase gate for a review-band report)."""

    def __init__(self, report: Dict[str, Any]):
        self.report = report
        fail_seams = [s["seam_id"] for s in report["seams"] if s["status"] == SEAM_STATUS_FAIL]
        super().__init__(
            "seam-discontinuity",
            f"{len(fail_seams)} of {report['seam_count']} seam(s) failed calibrated continuity "
            f"thresholds: {fail_seams!r}",
        )


# ---------------------------------------------------------------------------
# Metric computation — real ffmpeg SSIM + PSNR filters, never a Python-side
# pixel-diff reimplementation.
# ---------------------------------------------------------------------------

_SSIM_ALL_RE = re.compile(r"All:([0-9.]+)")
_PSNR_AVG_RE = re.compile(r"average:(inf|[0-9.]+)")


def _dims_from_probe(probe: Dict[str, Any], *, path: Path) -> Tuple[int, int]:
    streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
    if not streams:
        raise mf.MediaProcessingError("seam-frame-not-an-image", f"{path} has no decodable image/video stream")
    width, height = streams[0].get("width"), streams[0].get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise mf.MediaProcessingError("seam-frame-not-an-image", f"{path} has invalid dimensions {width}x{height}")
    return (width, height)


def compute_frame_similarity(binaries: Dict[str, str], frame_a: Path, frame_b: Path) -> Dict[str, float]:
    """Real ffmpeg SSIM (structural) + PSNR (the complementary perceptual
    metric spec 12.3 requires alongside it) between two already-extracted
    boundary-frame PNGs. Raises mf.MediaProcessingError('seam-dimension-
    mismatch') up front if the two frames are not the same pixel size --
    checked explicitly (rather than letting ffmpeg's own non-zero exit on a
    size mismatch surface as an opaque 'seam-metric-failed') so the failure
    reason names exactly what went wrong."""
    probe_a = mf.ffprobe_json(binaries, frame_a)  # raises empty-source/corrupt-source per media_ffmpeg's own checks
    probe_b = mf.ffprobe_json(binaries, frame_b)
    dims_a = _dims_from_probe(probe_a, path=frame_a)
    dims_b = _dims_from_probe(probe_b, path=frame_b)
    if dims_a != dims_b:
        raise mf.MediaProcessingError(
            "seam-dimension-mismatch",
            f"boundary frames are not the same size, so SSIM/PSNR would be meaningless: "
            f"{frame_a} is {dims_a[0]}x{dims_a[1]}, {frame_b} is {dims_b[0]}x{dims_b[1]}",
        )

    ssim_cmd = [binaries["ffmpeg"], "-i", str(frame_a), "-i", str(frame_b), "-lavfi", "ssim", "-f", "null", "-"]
    ssim_proc = mf.run_cmd(ssim_cmd, label="ffmpeg-ssim")
    ssim_match = _SSIM_ALL_RE.search(ssim_proc.stderr)
    if ssim_proc.returncode != 0 or not ssim_match:
        raise mf.MediaProcessingError(
            "seam-metric-failed",
            f"ffmpeg ssim filter failed for {frame_a} vs {frame_b}: {ssim_proc.stderr.strip()[-500:]}",
        )
    ssim_score = float(ssim_match.group(1))

    psnr_cmd = [binaries["ffmpeg"], "-i", str(frame_a), "-i", str(frame_b), "-lavfi", "psnr", "-f", "null", "-"]
    psnr_proc = mf.run_cmd(psnr_cmd, label="ffmpeg-psnr")
    psnr_match = _PSNR_AVG_RE.search(psnr_proc.stderr)
    if psnr_proc.returncode != 0 or not psnr_match:
        raise mf.MediaProcessingError(
            "seam-metric-failed",
            f"ffmpeg psnr filter failed for {frame_a} vs {frame_b}: {psnr_proc.stderr.strip()[-500:]}",
        )
    psnr_raw = psnr_match.group(1)
    psnr_score = PSNR_INFINITY_SENTINEL_DB if psnr_raw == "inf" else float(psnr_raw)

    return {"ssim": round(ssim_score, 6), "psnr_db": round(psnr_score, 6)}


def classify_seam(ssim: float, psnr_db: float, thresholds: Dict[str, float]) -> str:
    """spec 12.3's three-tier policy: 'high-confidence pass; review band;
    fail/regenerate band.' FAIL triggers the moment EITHER metric drops
    below its own review floor -- a real discontinuity in either measure is
    disqualifying on its own, one strong metric must never mask a weak one.
    PASS requires BOTH metrics to clear their pass floor. Anything else
    (both above their review floor, at least one below its pass floor)
    lands in REVIEW."""
    if ssim < thresholds["ssim_review_min"] or psnr_db < thresholds["psnr_review_min"]:
        return SEAM_STATUS_FAIL
    if ssim >= thresholds["ssim_pass_min"] and psnr_db >= thresholds["psnr_pass_min"]:
        return SEAM_STATUS_PASS
    return SEAM_STATUS_REVIEW


# ---------------------------------------------------------------------------
# Sequence / threshold loading
# ---------------------------------------------------------------------------


def _load_json(path: Path, *, label: str) -> Dict[str, Any]:
    if not path.exists():
        raise mf.MediaProcessingError(f"{label}-missing", f"{label} file does not exist: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise mf.MediaProcessingError(f"{label}-invalid-json", f"{label} at {path} is not valid JSON: {exc}") from exc


def load_thresholds(thresholds_path: Optional[Path]) -> Dict[str, float]:
    """Returns DEFAULT_THRESHOLDS, optionally overridden by a JSON file of
    (a subset of) the four threshold keys. Raises
    mf.MediaProcessingError('seam-thresholds-invalid') for an unknown key or
    an internally inconsistent band (a review floor above its own pass
    floor would make the pass band unreachable)."""
    thresholds = dict(DEFAULT_THRESHOLDS)
    if thresholds_path is not None:
        data = _load_json(thresholds_path, label="seam-thresholds")
        unknown = [k for k in data if k not in DEFAULT_THRESHOLDS]
        if unknown:
            raise mf.MediaProcessingError(
                "seam-thresholds-invalid", f"unknown threshold key(s) in {thresholds_path}: {unknown!r}"
            )
        thresholds.update({k: float(v) for k, v in data.items()})
    if thresholds["ssim_review_min"] > thresholds["ssim_pass_min"]:
        raise mf.MediaProcessingError("seam-thresholds-invalid", "ssim_review_min must be <= ssim_pass_min")
    if thresholds["psnr_review_min"] > thresholds["psnr_pass_min"]:
        raise mf.MediaProcessingError("seam-thresholds-invalid", "psnr_review_min must be <= psnr_pass_min")
    return thresholds


def _frame_entry(receipt: Dict[str, Any], position: str, *, source_desc: str) -> Dict[str, Any]:
    by_pos = {f["position"]: f for f in receipt.get("frames", [])}
    if position not in by_pos:
        raise mf.MediaProcessingError(
            "seam-sequence-invalid",
            f"{source_desc}: boundary-frames receipt has no '{position}' frame entry -- "
            "extract_boundaries.py must be run with --position both (the default) so every clip "
            "in a seam sequence has both endpoints available",
        )
    return by_pos[position]


# ---------------------------------------------------------------------------
# Core: verify a full ordered sequence
# ---------------------------------------------------------------------------


def verify_seams(
    sequence: Dict[str, Any], *, thresholds: Dict[str, float],
    out_dir: Optional[Path] = None, report_path: Optional[Path] = None,
    fail_closed: bool = True,
) -> Dict[str, Any]:
    """Real ffmpeg SSIM+PSNR seam-continuity check across an ORDERED
    sequence of already-extracted boundary-frame receipts (U13's
    extract_boundaries.py output) -- the seam between clip i and clip i+1 is
    clip i's LAST frame vs clip i+1's FIRST frame (ADR-9). Raises
    mf.MediaToolingUnavailable if ffmpeg/ffprobe are not resolvable; raises
    mf.MediaProcessingError for any malformed sequence/receipt/threshold
    input. Writes seam-report.json (to `report_path`, or `out_dir /
    "seam-report.json"`) BEFORE any fail_closed raise, so the report is
    always on disk as evidence regardless of the verdict. When
    fail_closed=True (the default) and overall_status is 'fail', raises
    SeamDiscontinuityError carrying the written report. Returns the report
    dict on any other outcome (including 'review', and including 'fail'
    when fail_closed=False)."""
    binaries = mf.require_binaries()  # fail-closed: raises if ffmpeg/ffprobe absent

    schema = mf.load_schema(_STRUCTURE_DIR, SEQUENCE_SCHEMA_FILE)
    mf.validate_or_raise(sequence, schema, label="seam-sequence")

    clips = sequence["clips"]
    seen_ids = set()
    receipts: List[Dict[str, Any]] = []
    for entry in clips:
        clip_id = entry["clip_id"]
        if clip_id in seen_ids:
            raise mf.MediaProcessingError("seam-sequence-invalid", f"duplicate clip_id in sequence: {clip_id!r}")
        seen_ids.add(clip_id)
        bf_path = Path(entry["boundary_frames_path"])
        receipt = _load_json(bf_path, label=f"boundary-frames[{clip_id}]")
        receipts.append({"clip_id": clip_id, "receipt": receipt, "path": str(bf_path)})

    seams: List[Dict[str, Any]] = []
    for i in range(len(receipts) - 1):
        left, right = receipts[i], receipts[i + 1]
        left_entry = _frame_entry(left["receipt"], "last", source_desc=left["path"])
        right_entry = _frame_entry(right["receipt"], "first", source_desc=right["path"])
        left_frame = Path(left_entry["output_path"])
        right_frame = Path(right_entry["output_path"])

        metrics = compute_frame_similarity(binaries, left_frame, right_frame)
        status = classify_seam(metrics["ssim"], metrics["psnr_db"], thresholds)

        seams.append({
            "seam_id": f"{left['clip_id']}->{right['clip_id']}",
            "left_clip_id": left["clip_id"],
            "right_clip_id": right["clip_id"],
            "left_frame_path": str(left_frame),
            "right_frame_path": str(right_frame),
            "left_frame_hash_sha256": left_entry["hash_sha256"],
            "right_frame_hash_sha256": right_entry["hash_sha256"],
            "ssim": metrics["ssim"],
            "psnr_db": metrics["psnr_db"],
            "status": status,
        })

    pass_count = sum(1 for s in seams if s["status"] == SEAM_STATUS_PASS)
    review_count = sum(1 for s in seams if s["status"] == SEAM_STATUS_REVIEW)
    fail_count = sum(1 for s in seams if s["status"] == SEAM_STATUS_FAIL)
    if fail_count:
        overall_status = SEAM_STATUS_FAIL
    elif review_count:
        overall_status = SEAM_STATUS_REVIEW
    else:
        overall_status = SEAM_STATUS_PASS

    report = {
        "schema_version": SCHEMA_VERSION,
        "af_code": AF_CODE,
        "clip_count": len(receipts),
        "seam_count": len(seams),
        "thresholds": thresholds,
        "seams": seams,
        "counts": {"pass": pass_count, "review": review_count, "fail": fail_count},
        "overall_status": overall_status,
        "created_at": mf.now_iso(),
    }
    report_schema = mf.load_schema(_STRUCTURE_DIR, REPORT_SCHEMA_FILE)
    mf.validate_or_raise(report, report_schema, label="seam-report")

    if report_path is None:
        if out_dir is None:
            raise mf.MediaProcessingError(
                "seam-report-no-destination", "either out_dir or report_path must be provided to write seam-report.json"
            )
        report_path = out_dir / DEFAULT_REPORT_FILENAME
    mf.atomic_write_json(report_path, report)

    if fail_closed and overall_status == SEAM_STATUS_FAIL:
        raise SeamDiscontinuityError(report)
    return report


# ---------------------------------------------------------------------------
# Phase-gate contract: evaluate(run_dir) -> (passed, detail)
# ---------------------------------------------------------------------------


def evaluate(run_dir: Path) -> Tuple[bool, str]:
    """CWFE-MANIFEST.json P10-ENCODE-SEAM gate (py_symbol
    'verify_seams.evaluate'). Reads run_dir/seam-sequence.json (or the
    CWFE_SEAM_SEQUENCE_PATH override), runs the real ffmpeg SSIM+PSNR seam
    check via verify_seams(fail_closed=False), writes seam-report.json into
    run_dir, and returns (passed, detail).

    FAILS CLOSED when no seam-sequence.json exists yet: that is the true
    state of this run_dir today, since P8/P9 (media generation, which would
    emit the ordered clip sequence) are not built in this build wave -- the
    same documented 'GATE-SCRIPT-MISSING'-style fail-closed behavior
    CWFE-MANIFEST.json's build_status names for every not-yet-built phase
    input; this gate correctly refuses to pass rather than inventing one.

    passed is False whenever overall_status is 'fail' OR 'review': spec
    12.3's review band means the seam has NOT been proven continuous, so
    P10 must not silently wave it through on a merely-ambiguous score. A
    human approval step (a later unit) is what would promote a review-band
    run to certified, not this gate."""
    env = os.environ
    sequence_override = env.get(SEQUENCE_PATH_ENV)
    sequence_path = Path(sequence_override) if sequence_override else (run_dir / DEFAULT_SEQUENCE_FILENAME)
    thresholds_override = env.get(THRESHOLDS_PATH_ENV)
    thresholds_path = Path(thresholds_override) if thresholds_override else None

    if not sequence_path.exists():
        return False, (
            f"[{AF_CODE}] seam-sequence.json not found at {sequence_path} -- P10-ENCODE-SEAM cannot run "
            "until final scene/connector media generation (P8/P9) has produced an ordered clip sequence "
            "with an extract_boundaries.py boundary-frames.json receipt for each clip"
        )

    try:
        thresholds = load_thresholds(thresholds_path)
        sequence = _load_json(sequence_path, label="seam-sequence")
        report = verify_seams(sequence, thresholds=thresholds, out_dir=run_dir, fail_closed=False)
    except mf.MediaToolingUnavailable as exc:
        return False, f"[{AF_CODE}] {exc}"
    except mf.MediaProcessingError as exc:
        return False, f"[{AF_CODE}] {exc}"

    detail = (
        f"seam-report.json written: {report['seam_count']} seam(s) across {report['clip_count']} clip(s), "
        f"pass={report['counts']['pass']} review={report['counts']['review']} fail={report['counts']['fail']}, "
        f"overall_status={report['overall_status']}"
    )
    return (report["overall_status"] == SEAM_STATUS_PASS), detail


# ------------------------------------------------------------------------
# Self-test: builds REAL encoded clips with ffmpeg, runs REAL
# extract_boundaries.py (U13) on them to get genuine boundary-frames.json
# receipts, then runs THIS module's real ffmpeg SSIM/PSNR comparison and
# fail-closed classification against them -- no mocked subprocess, no
# hand-authored metric numbers, per the directive that this must be tested
# against real media fixtures (spec 19.2 "seam metric fixtures").
# ------------------------------------------------------------------------
def _make_boundary_receipt(tmp: Path, out_subdir: str, clip: Path) -> Dict[str, Any]:
    sys.path.insert(0, str(_SCRIPT_DIR))
    import extract_boundaries as eb  # noqa: E402 (local import: avoid a hard import-time cycle)

    return eb.extract_boundaries(clip, tmp / out_subdir)


def _make_continuous_pair(tmp: Path, binaries: Dict[str, str]) -> Tuple[Path, Path]:
    """clip A: a genuine testsrc2 motion clip. clip B: opens with a ~0.3s
    HOLD of clip A's own real extracted last frame (re-encoded through
    libx264, so not byte-identical -- a realistic stand-in for a connector
    clip whose opening frame was generated FROM that reference image, per
    ADR-9/spec 12.2), then continues with more testsrc2 motion. This proves
    the pass band against a genuinely continuous, non-trivial hand-off, not
    a byte-identical tautology."""
    clip_a = tmp / "continuous-a.mp4"
    proc = mf.run_cmd(
        [
            binaries["ffmpeg"], "-y",
            "-f", "lavfi", "-i", "testsrc2=size=96x96:rate=10:duration=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_a),
        ],
        label="ffmpeg-fixture-continuous-a",
    )
    if proc.returncode != 0 or not clip_a.exists():
        raise RuntimeError(f"self-test could not synthesize clip A: {proc.stderr[-400:]}")

    receipt_a = _make_boundary_receipt(tmp, "continuous-a-boundaries", clip_a)
    last_frame_a = Path({f["position"]: f for f in receipt_a["frames"]}["last"]["output_path"])

    clip_b = tmp / "continuous-b.mp4"
    proc2 = mf.run_cmd(
        [
            binaries["ffmpeg"], "-y",
            "-loop", "1", "-t", "0.3", "-i", str(last_frame_a),
            "-f", "lavfi", "-i", "testsrc2=size=96x96:rate=10:duration=1",
            "-filter_complex",
            "[0:v]fps=10,format=yuv420p,setsar=1[v0];[1:v]format=yuv420p,setsar=1[v1];"
            "[v0][v1]concat=n=2:v=1:a=0[outv]",
            "-map", "[outv]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_b),
        ],
        label="ffmpeg-fixture-continuous-b",
    )
    if proc2.returncode != 0 or not clip_b.exists():
        raise RuntimeError(f"self-test could not synthesize clip B: {proc2.stderr[-400:]}")

    return clip_a, clip_b


def _make_hard_cut_pair(tmp: Path, binaries: Dict[str, str]) -> Tuple[Path, Path]:
    """Two clips with completely unrelated, EACH-genuinely-changing content
    (testsrc2 moving pattern vs a mandelbrot zoom) -- the shape of a
    broken/failed connector's hard cut spec 9.4 says must be rejected, not
    hidden. Both sources must change frame-to-frame (not e.g. static
    color bars) so extract_boundaries.py's own identical-hash fault
    detector does not trip on a source that is unrelated-to-the-other-clip
    but internally static."""
    clip_a = tmp / "hardcut-a.mp4"
    proc = mf.run_cmd(
        [
            binaries["ffmpeg"], "-y",
            "-f", "lavfi", "-i", "testsrc2=size=96x96:rate=10:duration=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_a),
        ],
        label="ffmpeg-fixture-hardcut-a",
    )
    if proc.returncode != 0 or not clip_a.exists():
        raise RuntimeError(f"self-test could not synthesize hard-cut clip A: {proc.stderr[-400:]}")

    clip_b = tmp / "hardcut-b.mp4"
    proc2 = mf.run_cmd(
        [
            binaries["ffmpeg"], "-y",
            "-f", "lavfi", "-i", "mandelbrot=size=96x96:rate=10", "-t", "1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_b),
        ],
        label="ffmpeg-fixture-hardcut-b",
    )
    if proc2.returncode != 0 or not clip_b.exists():
        raise RuntimeError(f"self-test could not synthesize hard-cut clip B: {proc2.stderr[-400:]}")

    return clip_a, clip_b


def self_test() -> int:
    fails = 0

    def check(label: str, cond: bool) -> None:
        nonlocal fails
        if cond:
            print(f"  [PASS] {label}")
        else:
            print(f"  [FAIL] {label}")
            fails += 1

    try:
        binaries = mf.require_binaries()
        check("ffmpeg/ffprobe resolved on PATH", True)
    except mf.MediaToolingUnavailable as exc:
        print(f"  [FAIL] ffmpeg/ffprobe not available: {exc}", file=sys.stderr)
        print("RESULT: FAIL — required binaries absent (fail-closed, not skipped).", file=sys.stderr)
        return 1

    import tempfile as _tempfile
    import shutil as _shutil

    tmp = Path(_tempfile.mkdtemp(prefix="cwfe-seams-selftest-"))
    try:
        # --- pure classification logic (deterministic, no media I/O) ---
        t = dict(DEFAULT_THRESHOLDS)
        check("classify_seam: strong SSIM+PSNR -> pass", classify_seam(0.99, 45.0, t) == SEAM_STATUS_PASS)
        check("classify_seam: weak SSIM only -> fail", classify_seam(0.10, 45.0, t) == SEAM_STATUS_FAIL)
        check("classify_seam: weak PSNR only -> fail", classify_seam(0.99, 5.0, t) == SEAM_STATUS_FAIL)
        check("classify_seam: mid-band both metrics -> review", classify_seam(0.75, 20.0, t) == SEAM_STATUS_REVIEW)
        check(
            "classify_seam: exactly at pass floor on both -> pass (inclusive boundary)",
            classify_seam(t["ssim_pass_min"], t["psnr_pass_min"], t) == SEAM_STATUS_PASS,
        )
        check(
            "classify_seam: exactly at review floor on both -> not fail (inclusive boundary)",
            classify_seam(t["ssim_review_min"], t["psnr_review_min"], t) != SEAM_STATUS_FAIL,
        )

        # --- load_thresholds: rejects unknown keys and inconsistent bands ---
        bad_thresholds_path = tmp / "bad-thresholds.json"
        bad_thresholds_path.write_text(json.dumps({"not_a_real_key": 1.0}), encoding="utf-8")
        try:
            load_thresholds(bad_thresholds_path)
            check("load_thresholds rejects an unknown key", False)
        except mf.MediaProcessingError as exc:
            check("load_thresholds rejects an unknown key", exc.reason == "seam-thresholds-invalid")

        inverted_path = tmp / "inverted-thresholds.json"
        inverted_path.write_text(json.dumps({"ssim_review_min": 0.99, "ssim_pass_min": 0.10}), encoding="utf-8")
        try:
            load_thresholds(inverted_path)
            check("load_thresholds rejects review_min > pass_min", False)
        except mf.MediaProcessingError as exc:
            check("load_thresholds rejects review_min > pass_min", exc.reason == "seam-thresholds-invalid")

        # --- real ffmpeg fixtures: continuous hand-off vs hard cut ---
        cont_a, cont_b = _make_continuous_pair(tmp, binaries)
        cut_a, cut_b = _make_hard_cut_pair(tmp, binaries)

        receipt_cont_a = _make_boundary_receipt(tmp, "cont-a-b", cont_a)
        receipt_cont_b = _make_boundary_receipt(tmp, "cont-b-b", cont_b)
        receipt_cut_a = _make_boundary_receipt(tmp, "cut-a-b", cut_a)
        receipt_cut_b = _make_boundary_receipt(tmp, "cut-b-b", cut_b)

        by_pos_cont_a = {f["position"]: f for f in receipt_cont_a["frames"]}
        by_pos_cont_b = {f["position"]: f for f in receipt_cont_b["frames"]}
        by_pos_cut_a = {f["position"]: f for f in receipt_cut_a["frames"]}
        by_pos_cut_b = {f["position"]: f for f in receipt_cut_b["frames"]}

        cont_metrics = compute_frame_similarity(
            binaries,
            Path(by_pos_cont_a["last"]["output_path"]),
            Path(by_pos_cont_b["first"]["output_path"]),
        )
        cut_metrics = compute_frame_similarity(
            binaries,
            Path(by_pos_cut_a["last"]["output_path"]),
            Path(by_pos_cut_b["first"]["output_path"]),
        )
        print(f"  [INFO] continuous-pair metrics: {cont_metrics}")
        print(f"  [INFO] hard-cut-pair metrics:   {cut_metrics}")

        check(
            "continuous hand-off scores strictly higher SSIM than a hard cut",
            cont_metrics["ssim"] > cut_metrics["ssim"],
        )
        check(
            "continuous hand-off scores strictly higher PSNR than a hard cut",
            cont_metrics["psnr_db"] > cut_metrics["psnr_db"],
        )
        check(
            "continuous hand-off classifies as pass under default thresholds",
            classify_seam(cont_metrics["ssim"], cont_metrics["psnr_db"], DEFAULT_THRESHOLDS) == SEAM_STATUS_PASS,
        )
        check(
            "hard cut classifies as fail under default thresholds",
            classify_seam(cut_metrics["ssim"], cut_metrics["psnr_db"], DEFAULT_THRESHOLDS) == SEAM_STATUS_FAIL,
        )

        # --- dimension-mismatch rejection, against REAL differently-sized frames ---
        small_png = tmp / "small.png"
        proc_small = mf.run_cmd(
            [binaries["ffmpeg"], "-y", "-f", "lavfi", "-i", "color=c=red:s=32x32:d=1:r=1",
             "-frames:v", "1", str(small_png)],
            label="ffmpeg-fixture-small-png",
        )
        check("small comparison PNG fixture encoded", proc_small.returncode == 0 and small_png.exists())
        try:
            compute_frame_similarity(binaries, Path(by_pos_cont_a["last"]["output_path"]), small_png)
            check("mismatched frame dimensions are rejected", False)
        except mf.MediaProcessingError as exc:
            check("mismatched frame dimensions are rejected", exc.reason == "seam-dimension-mismatch")

        # --- end-to-end verify_seams() over a 3-clip sequence built from the continuous pair ---
        receipt_cont_a_path = tmp / "cont-a-b" / f"{cont_a.stem}.boundary-frames.json"
        receipt_cont_b_path = tmp / "cont-b-b" / f"{cont_b.stem}.boundary-frames.json"
        # A third clip continuing from clip B's own last frame -- a real 3-clip chain.
        receipt_cont_c_source = tmp / "continuous-c.mp4"
        last_frame_b = Path(by_pos_cont_b["last"]["output_path"])
        proc3 = mf.run_cmd(
            [
                binaries["ffmpeg"], "-y",
                "-loop", "1", "-t", "0.3", "-i", str(last_frame_b),
                "-f", "lavfi", "-i", "testsrc2=size=96x96:rate=10:duration=1",
                "-filter_complex",
                "[0:v]fps=10,format=yuv420p,setsar=1[v0];[1:v]format=yuv420p,setsar=1[v1];"
                "[v0][v1]concat=n=2:v=1:a=0[outv]",
                "-map", "[outv]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(receipt_cont_c_source),
            ],
            label="ffmpeg-fixture-continuous-c",
        )
        check("3-clip chain: clip C encoded", proc3.returncode == 0 and receipt_cont_c_source.exists())
        receipt_cont_c = _make_boundary_receipt(tmp, "cont-c-b", receipt_cont_c_source)
        receipt_cont_c_path = tmp / "cont-c-b" / f"{receipt_cont_c_source.stem}.boundary-frames.json"

        sequence = {
            "clips": [
                {"clip_id": "scene-a", "boundary_frames_path": str(receipt_cont_a_path), "role": "scene"},
                {"clip_id": "scene-b", "boundary_frames_path": str(receipt_cont_b_path), "role": "scene"},
                {"clip_id": "scene-c", "boundary_frames_path": str(receipt_cont_c_path), "role": "scene"},
            ]
        }
        report = verify_seams(sequence, thresholds=DEFAULT_THRESHOLDS, out_dir=tmp / "report-out")
        check("verify_seams: 3 clips produce exactly 2 seams", report["seam_count"] == 2)
        check("verify_seams: all-continuous chain overall_status is pass", report["overall_status"] == SEAM_STATUS_PASS)
        report_path = tmp / "report-out" / DEFAULT_REPORT_FILENAME
        check("seam-report.json written atomically", report_path.exists())
        reloaded = json.loads(report_path.read_text(encoding="utf-8"))
        check("reloaded seam-report round-trips identically", reloaded == report)

        # --- fail_closed=True raises SeamDiscontinuityError for a broken chain, evidence still written ---
        broken_sequence = {
            "clips": [
                {"clip_id": "scene-a", "boundary_frames_path": str(receipt_cont_a_path)},
                {"clip_id": "scene-cut-b", "boundary_frames_path": str(tmp / "cut-b-b" / f"{cut_b.stem}.boundary-frames.json")},
            ]
        }
        broken_report_dir = tmp / "broken-report-out"
        try:
            verify_seams(broken_sequence, thresholds=DEFAULT_THRESHOLDS, out_dir=broken_report_dir, fail_closed=True)
            check("verify_seams(fail_closed=True) raises on a discontinuous seam", False)
        except SeamDiscontinuityError as exc:
            check("verify_seams(fail_closed=True) raises on a discontinuous seam", exc.report["overall_status"] == SEAM_STATUS_FAIL)
            check(
                "the report was still written to disk BEFORE the raise (evidence survives)",
                (broken_report_dir / DEFAULT_REPORT_FILENAME).exists(),
            )

        # fail_closed=False on the same broken sequence: returns instead of raising.
        broken_report_dir2 = tmp / "broken-report-out2"
        soft_report = verify_seams(broken_sequence, thresholds=DEFAULT_THRESHOLDS, out_dir=broken_report_dir2, fail_closed=False)
        check("verify_seams(fail_closed=False) returns (does not raise) on a discontinuous seam", soft_report["overall_status"] == SEAM_STATUS_FAIL)

        # --- malformed sequence rejections ---
        try:
            verify_seams({"clips": [{"clip_id": "only-one", "boundary_frames_path": str(receipt_cont_a_path)}]},
                         thresholds=DEFAULT_THRESHOLDS, out_dir=tmp / "reject-out-1")
            check("a sequence with fewer than 2 clips is rejected", False)
        except mf.MediaProcessingError:
            check("a sequence with fewer than 2 clips is rejected", True)

        try:
            verify_seams(
                {"clips": [
                    {"clip_id": "dup", "boundary_frames_path": str(receipt_cont_a_path)},
                    {"clip_id": "dup", "boundary_frames_path": str(receipt_cont_b_path)},
                ]},
                thresholds=DEFAULT_THRESHOLDS, out_dir=tmp / "reject-out-2",
            )
            check("a sequence with a duplicate clip_id is rejected", False)
        except mf.MediaProcessingError as exc:
            check("a sequence with a duplicate clip_id is rejected", exc.reason == "seam-sequence-invalid")

        # A boundary-frames receipt extracted with only ONE position must be
        # rejected when the seam needs the missing endpoint.
        one_position_receipt = eb_extract_one_position(tmp, cont_a)
        try:
            verify_seams(
                {"clips": [
                    {"clip_id": "missing-last", "boundary_frames_path": str(one_position_receipt)},
                    {"clip_id": "scene-b", "boundary_frames_path": str(receipt_cont_b_path)},
                ]},
                thresholds=DEFAULT_THRESHOLDS, out_dir=tmp / "reject-out-3",
            )
            check("a clip missing its required boundary-frame position is rejected", False)
        except mf.MediaProcessingError as exc:
            check("a clip missing its required boundary-frame position is rejected", exc.reason == "seam-sequence-invalid")

        # --- fail-closed on tooling absence ---
        import os as _os
        _os.environ[mf.FFPROBE_ENV] = "/nonexistent/not-a-real-ffprobe-binary"
        try:
            verify_seams(sequence, thresholds=DEFAULT_THRESHOLDS, out_dir=tmp / "reject-out-4")
            check("verify_seams fails closed when ffprobe is unavailable", False)
        except mf.MediaToolingUnavailable:
            check("verify_seams fails closed when ffprobe is unavailable", True)
        finally:
            del _os.environ[mf.FFPROBE_ENV]

        # --- gate contract: evaluate(run_dir) ---
        gate_run_dir = tmp / "gate-run-missing-sequence"
        gate_run_dir.mkdir(parents=True, exist_ok=True)
        passed, detail = evaluate(gate_run_dir)
        check("evaluate() fails closed when seam-sequence.json is absent from run_dir", passed is False)
        check("evaluate()'s fail-closed detail names the AF code", AF_CODE in detail)

        gate_run_dir_pass = tmp / "gate-run-pass"
        gate_run_dir_pass.mkdir(parents=True, exist_ok=True)
        (gate_run_dir_pass / DEFAULT_SEQUENCE_FILENAME).write_text(json.dumps(sequence), encoding="utf-8")
        passed2, detail2 = evaluate(gate_run_dir_pass)
        check("evaluate() passes for an all-continuous sequence and writes seam-report.json", passed2 is True)
        check("evaluate() writes seam-report.json into run_dir", (gate_run_dir_pass / DEFAULT_REPORT_FILENAME).exists())

        gate_run_dir_fail = tmp / "gate-run-fail"
        gate_run_dir_fail.mkdir(parents=True, exist_ok=True)
        (gate_run_dir_fail / DEFAULT_SEQUENCE_FILENAME).write_text(json.dumps(broken_sequence), encoding="utf-8")
        passed3, detail3 = evaluate(gate_run_dir_fail)
        check("evaluate() does NOT pass a run_dir whose sequence contains a discontinuous seam", passed3 is False)

    finally:
        _shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"RESULT: FAIL — {fails} self-test check(s) failed.", file=sys.stderr)
        return 1
    print("RESULT: PASS — verify_seams self-test green (real ffmpeg/ffprobe, real composed fixtures).")
    return 0


def eb_extract_one_position(tmp: Path, clip: Path) -> Path:
    """Self-test helper: extract ONLY the 'first' position for `clip`, to
    exercise the "seam needs a position this receipt does not have"
    rejection path."""
    sys.path.insert(0, str(_SCRIPT_DIR))
    import extract_boundaries as eb  # noqa: E402

    out_dir = tmp / "one-position"
    eb.extract_boundaries(clip, out_dir, positions=["first"])
    return out_dir / f"{clip.stem}.boundary-frames.json"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, default=None, help="phase-gate mode (CWFE-MANIFEST.json uniform gate contract)")
    parser.add_argument("--sequence", type=Path, default=None, help="standalone mode: seam-sequence.json path")
    parser.add_argument("--out-dir", type=Path, default=None, help="standalone mode: output directory for seam-report.json")
    parser.add_argument("--thresholds", type=Path, default=None, help="optional threshold override JSON")
    parser.add_argument("--report-path", type=Path, default=None)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if args.run_dir is not None:
        run_dir = args.run_dir
        if not run_dir.exists() or not run_dir.is_dir():
            print(f"USAGE ERROR: --run-dir does not exist or is not a directory: {run_dir}", file=sys.stderr)
            sys.exit(EXIT_USAGE)
        passed, detail = evaluate(run_dir)
        if passed:
            print(f"[PASS] P10-ENCODE-SEAM — {detail}")
            sys.exit(EXIT_OK)
        print(f"[FAIL] P10-ENCODE-SEAM — {detail}", file=sys.stderr)
        sys.exit(EXIT_FAIL)

    if args.sequence is None or args.out_dir is None:
        parser.print_help()
        sys.exit(EXIT_USAGE)

    try:
        thresholds = load_thresholds(args.thresholds)
        sequence = _load_json(args.sequence, label="seam-sequence")
        report = verify_seams(
            sequence, thresholds=thresholds, out_dir=args.out_dir,
            report_path=args.report_path, fail_closed=True,
        )
        print(json.dumps(report, indent=2))
        sys.exit(EXIT_OK)
    except mf.MediaToolingUnavailable as exc:
        print(f"RESULT: FAIL — {exc}", file=sys.stderr)
        sys.exit(EXIT_FAIL)
    except SeamDiscontinuityError as exc:
        print(json.dumps(exc.report, indent=2))
        print(f"RESULT: FAIL — {exc}", file=sys.stderr)
        sys.exit(EXIT_FAIL)
    except mf.MediaProcessingError as exc:
        print(f"RESULT: FAIL — {exc}", file=sys.stderr)
        sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
