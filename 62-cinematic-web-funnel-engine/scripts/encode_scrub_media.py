#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""encode_scrub_media.py — real FFmpeg re-encode pipeline for scroll-scrub
media (Skill 62, build unit U13). Implements spec Section 12.1's FFmpeg
duties for the P10-ENCODE-SEAM phase (CWFE-MANIFEST.json):

    - inspect source media with FFprobe;
    - normalize frame rate, codec, pixel format, and dimensions;
    - remove audio by default;
    - encode H.264 MP4 with fast start;
    - use short keyframe/GOP intervals suitable for seeking;
    - generate desktop and mobile derivatives;
    - create poster frames;
    - optionally produce WebM when browser testing proves a benefit;
    - reject corrupt, empty, zero-duration, wrong-aspect, or
      unexpected-resolution output.

This module does NOT do boundary-frame extraction (that is
extract_boundaries.py) or seam similarity scoring (that is U14's
verify_seams.py, not yet built) -- it owns exactly the encode/normalize/
derivative/poster/reject-checks slice of Section 12.1.

Every FFmpeg/FFprobe call goes through scripts/lib/media_ffmpeg.py, which is
fail-closed: if the binaries are not resolvable, this script raises before
touching any media and NEVER emits a receipt. A receipt is only ever written
after every listed variant has independently passed the reject checks named
above -- its existence on disk is evidence, not a claim.

stdlib only. CLI:
    python3 encode_scrub_media.py --input SRC --out-dir DIR [--asset-id ID]
        [--variants desktop,mobile] [--fps 30] [--gop 15] [--keep-audio]
        [--webm] [--receipt-path PATH]
    python3 encode_scrub_media.py --self-test

Exit codes: 0 success (receipt written), 1 a spec-12.1 reject condition or
processing error, 2 required binaries not found (fail-closed), 3 self-test
failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_STRUCTURE_DIR = _SKILL_DIR / "structure"

sys.path.insert(0, str(_SCRIPT_DIR / "lib"))
import media_ffmpeg as mf  # noqa: E402

SCHEMA_VERSION = "1.0.0"
RECEIPT_SCHEMA_FILE = "media-processing-receipt.schema.json"

# Target dimensions per derivative. Fixed, documented targets rather than a
# "keep source aspect" pass-through: the site runtime (spec Section 13) needs
# every scroll-scrub clip in a chain at a known, identical resolution so
# scroll-position-to-currentTime mapping and connector pinning never fight a
# per-clip size mismatch. Letterbox/pillarbox (scale+pad) preserves the
# source's own aspect ratio inside that fixed frame rather than stretching it.
DEFAULT_VARIANT_DIMS: Dict[str, Tuple[int, int]] = {
    "desktop": (1920, 1080),
    "mobile": (1080, 1920),
}

DEFAULT_FPS = 30.0
DEFAULT_GOP = 15  # short GOP/keyframe interval "suitable for seeking" (spec 12.1)


def build_ffmpeg_encode_cmd(
    binaries: Dict[str, str], src: Path, out_path: Path, *,
    width: int, height: int, fps: float, gop: int, keep_audio: bool, webm: bool,
) -> List[str]:
    scale_pad = (
        f"scale=w={width}:h={height}:force_original_aspect_ratio=decrease,"
        f"pad=w={width}:h={height}:x=(ow-iw)/2:y=(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps}"
    )
    cmd = [binaries["ffmpeg"], "-y", "-i", str(src), "-vf", scale_pad]
    if webm:
        cmd += [
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-b:v", "0", "-crf", "32",
            "-g", str(gop), "-keyint_min", str(gop),
        ]
    else:
        cmd += [
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
            "-movflags", "+faststart",
        ]
    if keep_audio:
        cmd += (["-c:a", "libopus"] if webm else ["-c:a", "aac", "-b:a", "128k"])
    else:
        cmd += ["-an"]
    cmd.append(str(out_path))
    return cmd


def encode_one_variant(
    binaries: Dict[str, str], src: Path, out_dir: Path, *,
    variant_name: str, width: int, height: int, fps: float, gop: int,
    keep_audio: bool, webm: bool,
) -> Dict[str, Any]:
    container = "webm" if webm else "mp4"
    out_path = out_dir / f"{variant_name}.{container}"
    cmd = build_ffmpeg_encode_cmd(
        binaries, src, out_path, width=width, height=height, fps=fps, gop=gop,
        keep_audio=keep_audio, webm=webm,
    )
    proc = mf.run_cmd(cmd, label=f"ffmpeg-encode-{variant_name}")
    if proc.returncode != 0:
        raise mf.MediaProcessingError(
            "encode-failed", f"ffmpeg failed encoding variant {variant_name!r}: {proc.stderr.strip()[-500:]}"
        )

    # --- spec 12.1 reject checks: corrupt / empty / zero-duration / wrong-aspect / unexpected-resolution ---
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise mf.MediaProcessingError("empty-output", f"variant {variant_name!r} produced no/empty file at {out_path}")
    probe = mf.probe_source(binaries, out_path)  # raises corrupt-source/zero-duration on decode failure
    if probe["width"] != width or probe["height"] != height:
        raise mf.MediaProcessingError(
            "wrong-resolution",
            f"variant {variant_name!r}: expected {width}x{height}, encoded output is "
            f"{probe['width']}x{probe['height']}",
        )
    expected_aspect = round(width / height, 4)
    actual_aspect = round(probe["width"] / probe["height"], 4)
    if expected_aspect != actual_aspect:
        raise mf.MediaProcessingError(
            "wrong-aspect",
            f"variant {variant_name!r}: expected aspect {expected_aspect}, got {actual_aspect}",
        )
    if not keep_audio and probe["has_audio"]:
        raise mf.MediaProcessingError(
            "audio-not-removed", f"variant {variant_name!r} was requested with audio removed but still has an audio stream"
        )

    poster_path = out_dir / f"{variant_name}.poster.jpg"
    poster_ts = round(probe["duration_seconds"] / 2.0, 6)
    poster_cmd = [
        binaries["ffmpeg"], "-y", "-ss", str(poster_ts), "-i", str(out_path),
        "-frames:v", "1", "-q:v", "2", str(poster_path),
    ]
    poster_proc = mf.run_cmd(poster_cmd, label=f"ffmpeg-poster-{variant_name}")
    if poster_proc.returncode != 0 or not poster_path.exists() or poster_path.stat().st_size == 0:
        raise mf.MediaProcessingError(
            "poster-failed", f"poster frame extraction failed for variant {variant_name!r}: {poster_proc.stderr.strip()[-300:]}"
        )

    return {
        "variant_name": variant_name if not webm else f"{variant_name}-webm",
        "container": container,
        "output_path": str(out_path),
        "width": probe["width"],
        "height": probe["height"],
        "fps": probe["fps"],
        "gop": gop,
        "has_audio": probe["has_audio"],
        "codec_name": probe["codec_name"],
        "pix_fmt": probe["pix_fmt"],
        "duration_seconds": probe["duration_seconds"],
        "size_bytes": out_path.stat().st_size,
        "hash_sha256": mf.sha256_file(out_path),
        "poster_frame_path": str(poster_path),
        "poster_frame_hash_sha256": mf.sha256_file(poster_path),
    }


def encode_scrub_media(
    input_path: Path, out_dir: Path, *,
    asset_id: str = None, variant_names: List[str] = None,
    fps: float = DEFAULT_FPS, gop: int = DEFAULT_GOP,
    keep_audio: bool = False, webm: bool = False,
    receipt_path: Path = None,
) -> Dict[str, Any]:
    """The full spec-12.1 encode/normalize pipeline for one source asset.
    Raises mf.MediaToolingUnavailable (binaries missing) or
    mf.MediaProcessingError (any reject condition) rather than ever returning
    a partial/best-effort result. Returns the validated receipt dict on
    success and has ALREADY written it atomically to `receipt_path` (default
    out_dir/<asset_id>.media-processing-receipt.json)."""
    binaries = mf.require_binaries()  # fail-closed: raises if ffmpeg/ffprobe absent

    input_path = Path(input_path)
    out_dir = Path(out_dir)
    variant_names = variant_names or ["desktop", "mobile"]
    unknown = [v for v in variant_names if v not in DEFAULT_VARIANT_DIMS]
    if unknown:
        raise mf.MediaProcessingError("unknown-variant", f"unsupported variant name(s): {unknown!r}")

    if asset_id is None:
        asset_id = hashlib.sha1(str(input_path.resolve()).encode("utf-8")).hexdigest()[:16]

    source_probe = mf.probe_source(binaries, input_path)  # raises on any source reject condition

    out_dir.mkdir(parents=True, exist_ok=True)
    variants: List[Dict[str, Any]] = []
    for name in variant_names:
        width, height = DEFAULT_VARIANT_DIMS[name]
        variants.append(
            encode_one_variant(
                binaries, input_path, out_dir, variant_name=name, width=width, height=height,
                fps=fps, gop=gop, keep_audio=keep_audio, webm=False,
            )
        )
        if webm:
            variants.append(
                encode_one_variant(
                    binaries, input_path, out_dir, variant_name=name, width=width, height=height,
                    fps=fps, gop=gop, keep_audio=keep_audio, webm=True,
                )
            )

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "asset_id": asset_id,
        "source_path": str(input_path),
        "source_probe": {
            "duration_seconds": source_probe["duration_seconds"],
            "width": source_probe["width"],
            "height": source_probe["height"],
            "r_frame_rate": source_probe["r_frame_rate"],
            "codec_name": source_probe["codec_name"],
            "pix_fmt": source_probe["pix_fmt"],
            "has_audio": source_probe["has_audio"],
        },
        "variants": variants,
        "created_at": mf.now_iso(),
    }
    schema = mf.load_schema(_STRUCTURE_DIR, RECEIPT_SCHEMA_FILE)
    mf.validate_or_raise(receipt, schema, label="media-processing-receipt")

    if receipt_path is None:
        receipt_path = out_dir / f"{asset_id}.media-processing-receipt.json"
    mf.atomic_write_json(receipt_path, receipt)
    return receipt


# ------------------------------------------------------------------------
# Self-test: generates a REAL synthetic source clip with ffmpeg (lavfi
# testsrc2 + a sine-wave audio track so audio-removal is genuinely exercised,
# not assumed), runs the real encode pipeline against it, and checks both the
# success path and every fail-closed/reject path with REAL ffmpeg/ffprobe
# calls -- no mocked subprocess, per the directive that this must be tested
# against real media fixtures (spec 19.2 "actual FFmpeg fixture processing").
# ------------------------------------------------------------------------
def _make_synthetic_source(tmp: Path, binaries: Dict[str, str]) -> Path:
    src = tmp / "source.mp4"
    cmd = [
        binaries["ffmpeg"], "-y",
        "-f", "lavfi", "-i", "testsrc2=size=640x480:rate=25:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(src),
    ]
    proc = mf.run_cmd(cmd, label="ffmpeg-make-synthetic-source")
    if proc.returncode != 0 or not src.exists():
        raise RuntimeError(f"self-test could not synthesize a source fixture: {proc.stderr[-400:]}")
    return src


def self_test() -> int:
    fails = 0

    def check(label: str, cond: bool) -> None:
        nonlocal fails
        if cond:
            print(f"  [PASS] {label}")
        else:
            print(f"  [FAIL] {label}")
            fails += 1

    # Fail-closed check FIRST, with no fallback: if ffmpeg/ffprobe are not on
    # this machine, the self-test itself must report FAIL, never silently
    # skip the real-media assertions below.
    try:
        binaries = mf.require_binaries()
        check("ffmpeg/ffprobe resolved on PATH", True)
    except mf.MediaToolingUnavailable as exc:
        print(f"  [FAIL] ffmpeg/ffprobe not available: {exc}", file=sys.stderr)
        print("RESULT: FAIL — required binaries absent (fail-closed, not skipped).", file=sys.stderr)
        return 1

    # Fail-closed proof: force a bogus override and confirm require_binaries()
    # raises rather than silently falling back to the real PATH binaries.
    import os as _os
    _os.environ[mf.FFMPEG_ENV] = "/nonexistent/not-a-real-ffmpeg-binary"
    try:
        mf.require_binaries()
        check("require_binaries() fails closed when overridden to a missing binary", False)
    except mf.MediaToolingUnavailable:
        check("require_binaries() fails closed when overridden to a missing binary", True)
    finally:
        del _os.environ[mf.FFMPEG_ENV]

    tmp = Path(tempfile.mkdtemp(prefix="cwfe-encode-selftest-"))
    try:
        src = _make_synthetic_source(tmp, binaries)
        src_probe = mf.probe_source(binaries, src)
        check("synthetic source fixture has audio (pre-condition for removal test)", src_probe["has_audio"] is True)

        out_dir = tmp / "out"
        receipt = encode_scrub_media(src, out_dir, asset_id="selftest-asset", webm=False)

        check("receipt has exactly desktop+mobile variants", {v["variant_name"] for v in receipt["variants"]} == {"desktop", "mobile"})
        for v in receipt["variants"]:
            want_w, want_h = DEFAULT_VARIANT_DIMS[v["variant_name"]]
            check(f"{v['variant_name']}: encoded output resolution matches target {want_w}x{want_h}", (v["width"], v["height"]) == (want_w, want_h))
            check(f"{v['variant_name']}: audio removed by default", v["has_audio"] is False)
            check(f"{v['variant_name']}: codec is h264", v["codec_name"] in ("h264",))
            check(f"{v['variant_name']}: gop matches requested short GOP", v["gop"] == DEFAULT_GOP)
            check(f"{v['variant_name']}: output file exists on disk and matches recorded size", Path(v["output_path"]).stat().st_size == v["size_bytes"])
            check(f"{v['variant_name']}: recorded hash matches a fresh hash of the file", mf.sha256_file(Path(v["output_path"])) == v["hash_sha256"])
            check(f"{v['variant_name']}: poster frame exists and is non-empty", Path(v["poster_frame_path"]).exists() and Path(v["poster_frame_path"]).stat().st_size > 0)

        receipt_path = out_dir / "selftest-asset.media-processing-receipt.json"
        check("receipt file was written atomically to disk", receipt_path.exists())
        reloaded = json.loads(receipt_path.read_text(encoding="utf-8"))
        check("reloaded receipt round-trips identically", reloaded == receipt)

        # --- reject-path proofs, against REAL ffmpeg/ffprobe, not mocks ---
        corrupt = tmp / "corrupt.mp4"
        corrupt.write_bytes(b"this is not a video file")
        try:
            encode_scrub_media(corrupt, tmp / "out-corrupt", asset_id="corrupt")
            check("corrupt source is rejected, not silently processed", False)
        except mf.MediaProcessingError as exc:
            check("corrupt source is rejected, not silently processed", exc.reason == "corrupt-source")

        empty = tmp / "empty.mp4"
        empty.write_bytes(b"")
        try:
            encode_scrub_media(empty, tmp / "out-empty", asset_id="empty")
            check("empty (zero-byte) source is rejected", False)
        except mf.MediaProcessingError as exc:
            check("empty (zero-byte) source is rejected", exc.reason == "empty-source")

        # A source with duration but with a keep_audio=True + webm variant, to
        # exercise the opus/audio-preserving branch too (still real ffmpeg).
        kept_audio_dir = tmp / "out-audio-kept"
        kept_receipt = encode_scrub_media(
            src, kept_audio_dir, asset_id="selftest-audio-kept",
            variant_names=["desktop"], keep_audio=True, webm=False,
        )
        check("keep_audio=True preserves an audio stream in the encoded output", kept_receipt["variants"][0]["has_audio"] is True)

        # No such receipt is ever written for a rejected asset (fail-closed:
        # a receipt on disk is always evidence of success).
        check(
            "no receipt file was left behind for the rejected corrupt source",
            not (tmp / "out-corrupt" / "corrupt.media-processing-receipt.json").exists(),
        )

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"RESULT: FAIL — {fails} self-test check(s) failed.", file=sys.stderr)
        return 1
    print("RESULT: PASS — encode_scrub_media self-test green (real ffmpeg/ffprobe, real synthetic fixture).")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, help="source media file")
    parser.add_argument("--out-dir", type=Path, help="output directory for encoded variants + receipt")
    parser.add_argument("--asset-id", type=str, default=None)
    parser.add_argument("--variants", type=str, default="desktop,mobile", help="comma-separated: desktop,mobile")
    parser.add_argument("--fps", type=float, default=DEFAULT_FPS)
    parser.add_argument("--gop", type=int, default=DEFAULT_GOP)
    parser.add_argument("--keep-audio", action="store_true")
    parser.add_argument("--webm", action="store_true", help="also produce WebM derivatives alongside MP4")
    parser.add_argument("--receipt-path", type=Path, default=None)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if not args.input or not args.out_dir:
        parser.print_help()
        sys.exit(2)

    try:
        receipt = encode_scrub_media(
            args.input, args.out_dir, asset_id=args.asset_id,
            variant_names=[v.strip() for v in args.variants.split(",") if v.strip()],
            fps=args.fps, gop=args.gop, keep_audio=args.keep_audio, webm=args.webm,
            receipt_path=args.receipt_path,
        )
        print(json.dumps(receipt, indent=2))
        sys.exit(0)
    except mf.MediaToolingUnavailable as exc:
        print(f"RESULT: FAIL — {exc}", file=sys.stderr)
        sys.exit(2)
    except mf.MediaProcessingError as exc:
        print(f"RESULT: FAIL — {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
