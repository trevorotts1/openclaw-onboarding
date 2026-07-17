#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_boundaries.py — real FFmpeg/FFprobe boundary-frame extraction
(Skill 62, build unit U13). Implements spec Section 12.1 ("extract actual
first and last encoded frames") and ADR-9 ("Real encoded boundary frames are
authoritative": the next clip or connector starts from the actual final frame
extracted from the encoded preceding clip, not from the original still and
not solely from a provider-returned preview frame).

Extraction is decode-grounded, not seek-estimated: this module counts the
REAL decoded frame total via `ffprobe -count_frames`, then extracts frame 0
("first") and frame N-1 ("last") with an ffmpeg `select` filter chained to
`showinfo`, reading the real `pts_time` ffmpeg reports for that exact decoded
frame out of stderr. A container-level `-ss` seek (which can land on the
nearest keyframe, not the exact requested frame) is never used for the
boundary frames themselves -- see spec Section 12.2, which requires these
exact frames to be uploaded to the first/last-frame video model for connector
generation, so an approximate frame would poison every downstream connector.

This module does NOT do seam similarity scoring (SSIM/perceptual metric) --
that is U14's verify_seams.py, not yet built. It owns exactly the "extract
actual first and last encoded frames" slice of Section 12.1/ADR-9.

Fail-closed via scripts/lib/media_ffmpeg.py: if ffmpeg/ffprobe are not
resolvable, or the source fails frame-count/decode/reject checks, this script
raises before writing anything -- a boundary-frames.json on disk is always
real extraction evidence, never a placeholder.

stdlib only. CLI:
    python3 extract_boundaries.py --input CLIP.mp4 --out-dir DIR
        [--position first|last|both] [--receipt-path PATH]
    python3 extract_boundaries.py --self-test

Exit codes: 0 success, 1 extraction/reject error, 2 required binaries not
found (fail-closed), 3 self-test failure.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_STRUCTURE_DIR = _SKILL_DIR / "structure"

sys.path.insert(0, str(_SCRIPT_DIR / "lib"))
import media_ffmpeg as mf  # noqa: E402

SCHEMA_VERSION = "1.0.0"
RECEIPT_SCHEMA_FILE = "boundary-frames.schema.json"
POSITIONS = ("first", "last")


def extract_boundaries(
    input_path: Path, out_dir: Path, *,
    positions: List[str] = None, receipt_path: Path = None,
) -> Dict[str, Any]:
    """Extract the requested boundary frame(s) of `input_path` (an ALREADY
    ENCODED clip, per ADR-9 -- this is called on the output of
    encode_scrub_media.py, or any equivalently-encoded connector clip, not
    on a raw provider preview). Raises mf.MediaToolingUnavailable or
    mf.MediaProcessingError rather than ever returning a partial result.
    Returns the validated receipt dict and has ALREADY written it atomically
    to `receipt_path` (default out_dir/<input-stem>.boundary-frames.json)."""
    binaries = mf.require_binaries()  # fail-closed: raises if ffmpeg/ffprobe absent

    input_path = Path(input_path)
    out_dir = Path(out_dir)
    positions = positions or list(POSITIONS)
    unknown = [p for p in positions if p not in POSITIONS]
    if unknown:
        raise mf.MediaProcessingError("unknown-position", f"unsupported position(s): {unknown!r}")

    source_probe = mf.probe_source(binaries, input_path)  # raises on corrupt/empty/zero-duration
    frame_count = mf.count_frames(binaries, input_path)  # raises corrupt-source/zero-duration; REAL decode count

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    index_by_position = {"first": 0, "last": frame_count - 1}

    frames: List[Dict[str, Any]] = []
    seen_hashes = set()
    for position in positions:
        idx = index_by_position[position]
        out_path = out_dir / f"{stem}.{position}.png"
        frame = mf.extract_frame_by_index(binaries, input_path, idx, out_path)
        if frame["width"] != source_probe["width"] or frame["height"] != source_probe["height"]:
            raise mf.MediaProcessingError(
                "wrong-resolution",
                f"{position} frame of {input_path}: expected {source_probe['width']}x{source_probe['height']}, "
                f"got {frame['width']}x{frame['height']}",
            )
        frames.append({"position": position, **frame})
        seen_hashes.add(frame["hash_sha256"])

    if len(positions) == 2 and len(seen_hashes) == 1 and frame_count > 1:
        # A multi-frame clip whose first and last extracted frames hash
        # identically almost certainly means the select/showinfo extraction
        # collapsed to the same frame (an extraction bug), not a genuinely
        # frozen clip -- surface it rather than silently accepting it, since
        # ADR-9 connectors depend on these being the two DISTINCT endpoints.
        raise mf.MediaProcessingError(
            "boundary-frames-identical",
            f"{input_path}: first and last extracted frames hash identically across {frame_count} decoded frames "
            "(suspected extraction fault, not a genuinely static clip)",
        )

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "source_path": str(input_path),
        "source_probe": {
            "duration_seconds": source_probe["duration_seconds"],
            "frame_count": frame_count,
            "width": source_probe["width"],
            "height": source_probe["height"],
            "r_frame_rate": source_probe["r_frame_rate"],
        },
        "frames": frames,
        "created_at": mf.now_iso(),
    }
    schema = mf.load_schema(_STRUCTURE_DIR, RECEIPT_SCHEMA_FILE)
    mf.validate_or_raise(receipt, schema, label="boundary-frames")

    if receipt_path is None:
        receipt_path = out_dir / f"{stem}.boundary-frames.json"
    mf.atomic_write_json(receipt_path, receipt)
    return receipt


# ------------------------------------------------------------------------
# Self-test: builds a REAL encoded clip whose visible content changes over
# time (so first != last is a meaningful, checkable assertion, not a
# tautology), extracts boundaries with real ffmpeg/ffprobe, and proves both
# the success path and the fail-closed/reject paths.
# ------------------------------------------------------------------------
def _make_changing_clip(tmp: Path, binaries: Dict[str, str]) -> Path:
    """A short H.264 clip built with encode_scrub_media's own encoder so this
    self-test also proves the two U13 scripts compose end to end (encode ->
    extract), which is exactly how spec 12.2 chains them for connectors."""
    sys.path.insert(0, str(_SCRIPT_DIR))
    import encode_scrub_media as esm  # noqa: E402 (local import: avoid a hard import-time cycle)

    raw_src = tmp / "raw.mp4"
    # testsrc2 renders a moving pattern + timecode-like overlay so the
    # decoded first and last frames are genuinely different images.
    cmd = [
        binaries["ffmpeg"], "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10:duration=2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(raw_src),
    ]
    proc = mf.run_cmd(cmd, label="ffmpeg-make-changing-source")
    if proc.returncode != 0 or not raw_src.exists():
        raise RuntimeError(f"self-test could not synthesize a changing-content fixture: {proc.stderr[-400:]}")

    encoded_dir = tmp / "encoded"
    receipt = esm.encode_scrub_media(raw_src, encoded_dir, asset_id="boundary-fixture", variant_names=["desktop"])
    return Path(receipt["variants"][0]["output_path"])


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

    import os as _os
    _os.environ[mf.FFPROBE_ENV] = "/nonexistent/not-a-real-ffprobe-binary"
    try:
        mf.require_binaries()
        check("require_binaries() fails closed when overridden to a missing binary", False)
    except mf.MediaToolingUnavailable:
        check("require_binaries() fails closed when overridden to a missing binary", True)
    finally:
        del _os.environ[mf.FFPROBE_ENV]

    tmp = Path(tempfile.mkdtemp(prefix="cwfe-boundaries-selftest-"))
    try:
        clip = _make_changing_clip(tmp, binaries)
        check("composed encode_scrub_media -> extract_boundaries fixture clip exists", clip.exists())

        expected_frame_count = mf.count_frames(binaries, clip)
        check("count_frames() returns a real decoded count > 1 for a 2s/10fps clip", expected_frame_count > 1)

        out_dir = tmp / "boundaries"
        receipt = extract_boundaries(clip, out_dir)

        check("receipt has both first and last frame entries", {f["position"] for f in receipt["frames"]} == {"first", "last"})
        by_pos = {f["position"]: f for f in receipt["frames"]}
        check("first frame_index is 0", by_pos["first"]["frame_index"] == 0)
        check("last frame_index is frame_count - 1", by_pos["last"]["frame_index"] == expected_frame_count - 1)
        check("first frame timestamp is ~0", by_pos["first"]["timestamp_seconds"] < 0.05)
        check(
            "last frame timestamp is near clip duration (grounded in real decode, not a container estimate)",
            abs(by_pos["last"]["timestamp_seconds"] - receipt["source_probe"]["duration_seconds"]) < 0.5,
        )
        check(
            "first and last extracted frames are genuinely different images (distinct sha256)",
            by_pos["first"]["hash_sha256"] != by_pos["last"]["hash_sha256"],
        )
        for pos in ("first", "last"):
            p = Path(by_pos[pos]["output_path"])
            check(f"{pos} frame PNG exists and is non-empty", p.exists() and p.stat().st_size > 0)
            check(f"{pos} frame dimensions match source probe", (by_pos[pos]["width"], by_pos[pos]["height"]) == (receipt["source_probe"]["width"], receipt["source_probe"]["height"]))
            check(f"{pos} frame recorded hash matches a fresh hash of the file", mf.sha256_file(p) == by_pos[pos]["hash_sha256"])

        receipt_path = out_dir / f"{clip.stem}.boundary-frames.json"
        check("receipt file was written atomically to disk", receipt_path.exists())
        reloaded = json.loads(receipt_path.read_text(encoding="utf-8"))
        check("reloaded receipt round-trips identically", reloaded == receipt)

        # --- single-frame single-position request path ---
        first_only = extract_boundaries(clip, tmp / "first-only", positions=["first"])
        check("positions=['first'] returns exactly one frame entry", len(first_only["frames"]) == 1 and first_only["frames"][0]["position"] == "first")

        # --- reject-path proofs, against REAL ffmpeg/ffprobe ---
        corrupt = tmp / "corrupt.mp4"
        corrupt.write_bytes(b"not a real video")
        try:
            extract_boundaries(corrupt, tmp / "out-corrupt")
            check("corrupt input is rejected, not silently processed", False)
        except mf.MediaProcessingError as exc:
            check("corrupt input is rejected, not silently processed", exc.reason == "corrupt-source")

        empty = tmp / "empty.mp4"
        empty.write_bytes(b"")
        try:
            extract_boundaries(empty, tmp / "out-empty")
            check("empty (zero-byte) input is rejected", False)
        except mf.MediaProcessingError as exc:
            check("empty (zero-byte) input is rejected", exc.reason == "empty-source")

        # A single, real, all-black 1-frame still (encoded as a 1-frame "clip")
        # exercises frame_index collision handling: first == last index == 0,
        # so requesting both positions must still succeed (not spuriously
        # trip the "identical hash" fault detector, since frame_count == 1
        # legitimately produces the same physical frame for both positions).
        still = tmp / "still.mp4"
        still_cmd = [
            binaries["ffmpeg"], "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=1:r=1",
            "-frames:v", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(still),
        ]
        proc = mf.run_cmd(still_cmd, label="ffmpeg-make-single-frame-still")
        check("single-frame still fixture encoded", proc.returncode == 0 and still.exists())
        still_receipt = extract_boundaries(still, tmp / "out-still")
        still_by_pos = {f["position"]: f for f in still_receipt["frames"]}
        check(
            "a genuine 1-frame clip: first and last both resolve to frame_index 0 without raising",
            still_by_pos["first"]["frame_index"] == 0 and still_by_pos["last"]["frame_index"] == 0,
        )

        check(
            "no receipt file was left behind for the rejected corrupt input",
            not (tmp / "out-corrupt" / "corrupt.boundary-frames.json").exists(),
        )

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"RESULT: FAIL — {fails} self-test check(s) failed.", file=sys.stderr)
        return 1
    print("RESULT: PASS — extract_boundaries self-test green (real ffmpeg/ffprobe, real composed fixture).")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, help="already-encoded source clip")
    parser.add_argument("--out-dir", type=Path, help="output directory for extracted frames + receipt")
    parser.add_argument("--position", type=str, default="both", choices=["first", "last", "both"])
    parser.add_argument("--receipt-path", type=Path, default=None)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if not args.input or not args.out_dir:
        parser.print_help()
        sys.exit(2)

    positions = list(POSITIONS) if args.position == "both" else [args.position]
    try:
        receipt = extract_boundaries(args.input, args.out_dir, positions=positions, receipt_path=args.receipt_path)
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
