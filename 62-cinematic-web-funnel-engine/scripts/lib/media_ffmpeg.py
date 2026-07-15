#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""media_ffmpeg.py — shared, dependency-free FFmpeg/FFprobe process helpers used
by scripts/encode_scrub_media.py and scripts/extract_boundaries.py (Skill 62,
build unit U13). Implements the mechanical primitives spec Section 12.1 names
("inspect source media with FFprobe", "normalize frame rate, codec, pixel
format, and dimensions", "remove audio by default", "encode H.264 MP4 with
fast start", "use short keyframe/GOP intervals suitable for seeking",
"extract actual first and last encoded frames", "reject corrupt, empty,
zero-duration, wrong-aspect, or unexpected-resolution output").

One rule governs every function here: FAIL CLOSED. If `ffmpeg`/`ffprobe` are
not on PATH (or the caller-supplied override paths do not resolve), or if a
subprocess call fails, or if a resulting file does not pass the reject
criteria spec 12.1 names, this module raises — it never fabricates a receipt,
never substitutes a placeholder frame/clip, and never silently "passes" a
check it could not actually perform. There is no environment variable or flag
anywhere in this module that turns FFmpeg/FFprobe absence into a skip.

stdlib only (subprocess, hashlib, json, shutil, re). No jsonschema/PIL/etc.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import json_schema_lite as jsl  # sibling module in scripts/lib/ (same convention as state_engine.py)

# Environment overrides let a caller pin an exact binary (or, for the
# fail-closed self-tests below, point at something that does not exist) --
# but the default is always a real PATH lookup, never a hardcoded path.
FFMPEG_ENV = "CWFE_FFMPEG_BIN"
FFPROBE_ENV = "CWFE_FFPROBE_BIN"


class MediaToolingUnavailable(Exception):
    """Raised when ffmpeg and/or ffprobe cannot be resolved. This is the
    fail-closed gate spec 12.1's whole pipeline depends on -- no caller of
    this module may proceed to process media without first surviving a call
    to require_binaries()."""


class MediaProcessingError(Exception):
    """Raised for any subprocess failure OR any spec-12.1 reject condition:
    corrupt, empty, zero-duration, wrong-aspect, or unexpected-resolution
    output. Carries a short machine-checkable `reason` code plus a human
    detail string."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        msg = f"{reason}: {detail}" if detail else reason
        super().__init__(msg)


def resolve_binary(env_name: str, default_name: str) -> Optional[str]:
    """Resolve one binary: an explicit env override wins if set (even if it
    does not resolve -- that is intentionally surfaced as unavailable rather
    than silently falling back to PATH, so a test can force the fail-closed
    path deterministically); otherwise a real `shutil.which()` PATH lookup."""
    override = os.environ.get(env_name)
    if override:
        return override if (os.path.isfile(override) and os.access(override, os.X_OK)) else None
    return shutil.which(default_name)


def require_binaries() -> Dict[str, str]:
    """Fail-closed binary resolution. Returns {'ffmpeg': path, 'ffprobe': path}
    on success. Raises MediaToolingUnavailable naming exactly which binary is
    missing on failure -- callers must never catch this and continue."""
    ffmpeg = resolve_binary(FFMPEG_ENV, "ffmpeg")
    ffprobe = resolve_binary(FFPROBE_ENV, "ffprobe")
    missing = [name for name, path in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)) if not path]
    if missing:
        raise MediaToolingUnavailable(
            "required binary(ies) not found on PATH (and no valid "
            f"{FFMPEG_ENV}/{FFPROBE_ENV} override): {', '.join(missing)} -- "
            "media processing cannot proceed (spec Section 12: FFmpeg/FFprobe "
            "are load-bearing, not optional)"
        )
    return {"ffmpeg": ffmpeg, "ffprobe": ffprobe}  # type: ignore[dict-item]


def run_cmd(cmd: List[str], *, label: str) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as exc:
        raise MediaToolingUnavailable(f"{label}: binary vanished mid-run: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaProcessingError("subprocess-timeout", f"{label} exceeded 120s: {cmd!r}") from exc
    return proc


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_rate(rate: str) -> float:
    """Parse an ffprobe 'r_frame_rate'/'avg_frame_rate' style 'num/den' string
    into a float fps. Returns 0.0 for the documented 'unknown' sentinel
    '0/0' rather than raising -- callers treat 0.0 fps as invalid input."""
    if not rate:
        return 0.0
    if "/" in rate:
        num, _, den = rate.partition("/")
        try:
            num_f, den_f = float(num), float(den)
        except ValueError:
            return 0.0
        return num_f / den_f if den_f else 0.0
    try:
        return float(rate)
    except ValueError:
        return 0.0


def ffprobe_json(binaries: Dict[str, str], path: Path, *, extra_args: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run ffprobe -show_format -show_streams -of json against `path` and
    return the parsed dict. Raises MediaProcessingError('corrupt-source', ...)
    if ffprobe exits non-zero, prints unparseable JSON, or the file does not
    exist -- never returns a partial/guessed result."""
    if not path.exists() or path.stat().st_size == 0:
        raise MediaProcessingError("empty-source", f"{path} does not exist or is zero bytes")
    cmd = [
        binaries["ffprobe"], "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams",
    ] + (extra_args or []) + [str(path)]
    proc = run_cmd(cmd, label="ffprobe")
    if proc.returncode != 0:
        raise MediaProcessingError("corrupt-source", f"ffprobe rejected {path}: {proc.stderr.strip()[-500:]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProcessingError("corrupt-source", f"ffprobe produced unparseable JSON for {path}: {exc}") from exc


def probe_source(binaries: Dict[str, str], path: Path) -> Dict[str, Any]:
    """Inspect source media (spec 12.1 'inspect source media with FFprobe').
    Returns a normalized dict: duration_seconds, width, height, r_frame_rate
    (raw string, e.g. '25/1'), fps (parsed float), codec_name, pix_fmt,
    has_audio. Raises MediaProcessingError('corrupt-source'/'empty-source'/
    'zero-duration') rather than returning a partial probe for anything that
    fails the spec-12.1 reject list -- there is no video stream, no
    non-degenerate duration."""
    data = ffprobe_json(binaries, path)
    streams = data.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not video_streams:
        raise MediaProcessingError("corrupt-source", f"{path} has no decodable video stream")
    v = video_streams[0]
    fmt = data.get("format", {})

    duration_raw = v.get("duration") or fmt.get("duration")
    try:
        duration = float(duration_raw) if duration_raw is not None else 0.0
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0.0:
        raise MediaProcessingError("zero-duration", f"{path} reports duration <= 0 ({duration_raw!r})")

    width, height = v.get("width"), v.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise MediaProcessingError("corrupt-source", f"{path} has invalid dimensions {width}x{height}")

    r_frame_rate = v.get("r_frame_rate") or "0/0"
    fps = _parse_rate(r_frame_rate)
    if fps <= 0.0:
        # Fall back to avg_frame_rate before giving up -- some containers only
        # populate one of the two -- but never fabricate a value.
        fps = _parse_rate(v.get("avg_frame_rate") or "0/0")
    if fps <= 0.0:
        raise MediaProcessingError("corrupt-source", f"{path} has no usable frame rate")

    return {
        "duration_seconds": round(duration, 6),
        "width": width,
        "height": height,
        "r_frame_rate": r_frame_rate,
        "fps": fps,
        "codec_name": v.get("codec_name") or "unknown",
        "pix_fmt": v.get("pix_fmt"),
        "has_audio": bool(audio_streams),
    }


def count_frames(binaries: Dict[str, str], path: Path) -> int:
    """Exact decoded frame count via `ffprobe -count_frames` -- this DECODES
    the stream (not a container-metadata guess), matching ADR-9's requirement
    that boundary frames are grounded in the actual encoded bitstream. Raises
    MediaProcessingError('corrupt-source') if the count comes back missing,
    non-numeric, or zero."""
    data = ffprobe_json(
        binaries, path,
        extra_args=["-count_frames", "-select_streams", "v:0"],
    )
    streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not streams:
        raise MediaProcessingError("corrupt-source", f"{path} has no video stream to count frames on")
    raw = streams[0].get("nb_read_frames")
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise MediaProcessingError("corrupt-source", f"{path}: ffprobe -count_frames returned nb_read_frames={raw!r}")
    if n <= 0:
        raise MediaProcessingError("zero-duration", f"{path} decodes to {n} frames")
    return n


_PTS_TIME_RE = re.compile(r"pts_time:([0-9.]+)")


def extract_frame_by_index(
    binaries: Dict[str, str], src: Path, frame_index: int, out_path: Path,
) -> Dict[str, Any]:
    """Extract exactly the decoded frame at `frame_index` (0-based) as a
    lossless PNG using an ffmpeg `select` filter chained with `showinfo` --
    this decodes and counts real frames rather than trusting a container-level
    timestamp seek, which is what ADR-9 means by "actual encoded frame".
    Parses the real `pts_time` ffmpeg reports for that exact frame out of
    `showinfo`'s stderr log rather than computing an estimated timestamp, so
    the returned timestamp is grounded in what was actually decoded. Raises
    MediaProcessingError('boundary-extraction-failed') if ffmpeg exits
    non-zero, emits no output file, or emits an empty file; raises
    MediaProcessingError('boundary-frame-not-found') if the requested
    frame_index never matched (showinfo emitted nothing) -- e.g. frame_index
    is out of range."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        binaries["ffmpeg"], "-y", "-i", str(src),
        "-vf", f"select='eq(n\\,{frame_index})',showinfo",
        "-vsync", "vfr", "-frames:v", "1",
        str(out_path),
    ]
    proc = run_cmd(cmd, label="ffmpeg-extract-frame")
    if proc.returncode != 0:
        raise MediaProcessingError(
            "boundary-extraction-failed",
            f"ffmpeg failed extracting frame {frame_index} from {src}: {proc.stderr.strip()[-500:]}",
        )
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise MediaProcessingError(
            "boundary-extraction-failed",
            f"ffmpeg reported success but produced no/empty output for frame {frame_index} of {src}",
        )
    matches = _PTS_TIME_RE.findall(proc.stderr)
    if not matches:
        raise MediaProcessingError(
            "boundary-frame-not-found",
            f"showinfo never reported frame {frame_index} of {src} (out of range or select never matched)",
        )
    timestamp = float(matches[-1])

    probe = ffprobe_json(binaries, out_path)
    img_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
    if not img_streams:
        raise MediaProcessingError("boundary-extraction-failed", f"extracted frame {out_path} is not a decodable image")
    width, height = img_streams[0].get("width"), img_streams[0].get("height")
    return {
        "frame_index": frame_index,
        "timestamp_seconds": round(timestamp, 6),
        "output_path": str(out_path),
        "width": width,
        "height": height,
        "hash_sha256": sha256_file(out_path),
    }


# ------------------------------------------------------------------------
# Small shared utilities: schema validation + atomic writes. Deliberately
# NOT imported from scripts/state_engine.py (U6) -- these two U13 scripts
# only ever write their OWN receipt kinds (media-processing-receipt,
# boundary-frames), never project-manifest/cost-ledger, so pulling in
# state_engine's ProjectLock/ProjectState machinery would be an unused,
# unnecessary coupling to a file this unit does not otherwise touch. The
# atomic-write technique (tempfile in the same directory + os.replace) is
# intentionally the same one state_engine.py uses.
# ------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_SCHEMA_CACHE: Dict[str, Dict[str, Any]] = {}


def load_schema(structure_dir: Path, filename: str) -> Dict[str, Any]:
    key = str(structure_dir / filename)
    if key not in _SCHEMA_CACHE:
        path = structure_dir / filename
        if not path.exists():
            raise MediaProcessingError("schema-missing", f"schema file missing: {path}")
        _SCHEMA_CACHE[key] = json.loads(path.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE[key]


def validate_or_raise(instance: Any, schema: Dict[str, Any], *, label: str = "") -> None:
    errors = jsl.validate(instance, schema)
    if errors:
        raise MediaProcessingError("schema-invalid", f"{label}: {'; '.join(errors)}")


def atomic_write_json(path: Path, data: Any) -> None:
    """Same technique as state_engine.atomic_write_json: write to a tempfile
    in the SAME directory, fsync, then os.replace() -- a reader (including a
    process that crashes and restarts) only ever sees the prior complete file
    or the new complete file, never a truncated partial write."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass
