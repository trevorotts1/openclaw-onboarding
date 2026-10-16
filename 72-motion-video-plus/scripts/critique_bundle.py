"""Coverage-indexed visual review bundles for Skill 72 (MG-031).

Directive MG-031 replaces the truncated contact-sheet review with a
review bundle whose coverage is explicit, indexed, and enforced. The
legacy assembler (the old ``critique-bundle.sh``, now a thin wrapper
over this module) sampled a 2 fps strip into one 8x8 tile and a 1 fps
strip into one 6x6 tile: 64 and 36 cells, which is the first 32 and 36
seconds of the video. Everything past that was never seen by any
critic, the per-beat sheet was capped at 64 beats, the safe-zone check
was one frame at t=1s, and no ffmpeg failure changed the exit status:
the script ended by listing the output directory, so a bundle with
missing sheets still reported success. None of that survives here.

What this tool builds, for one video and one job, into one bundle
directory:

- Fixed-interval samples across the ENTIRE runtime, paginated into
  contact sheets (pages of ``columns`` x ``columns`` tiles). There is
  no first-sheet cutoff and no sample cap: pagination is the answer
  to length, never truncation.
- Targeted frames at every scene boundary (first and last frame of
  every scene), every compiled proof state, hold start, reveal start,
  and cue event, every text swap (caption starts from the MG-021
  timeline sidecar), the final frame, and every beat of a caller-
  supplied beat grid. Targeted points come from the job's compiled
  timeline (canonical contracts timeline document) and its sidecar,
  never from guesses.
- Every sampled frame as an individual PNG at the video's own full
  resolution, plus one variant per caller-declared destination size
  (``--destination WxH``, repeatable): the actual pixels a viewer of
  that destination gets. A contact-sheet tile is a thumbnail for
  navigation; readability is judged on the destination-size frames.
- Contact sheets composed from the extracted frame sequence with an
  explicit xstack layout (the MG-024 ``buildContactSheet``
  discipline), never unrelated inputs handed to ``tile``.
- ``coverage.json``: the index. Every sample with its frame, time,
  kind, scene, file paths, and status; the covered intervals and the
  omitted intervals (each with a reason); the sampling policy; and a
  verdict. Covered plus omitted account for exactly 100 percent of
  the declared runtime. Missing REQUIRED coverage (any targeted
  sample, or any interval of the runtime left unsampled) makes the
  verdict ``incomplete`` and the exit code 6
  (``MG_COVERAGE_INCOMPLETE``).
- ``metrics.json``: probed duration, exact frame count, fps,
  dimensions, and loudness when an audio stream exists (the legacy
  bundle's metrics, kept).

Identity and collisions: every artifact filename carries the job id,
so two jobs building into neighboring (or even the same) directories
never overwrite each other's stills. The canonical coverage record is
``<job>__coverage.json``; a plain ``coverage.json`` copy is written
only when the directory has none or the existing one belongs to the
same job, so the per-job record is always intact. A timeline,
sidecar, or MG-024 review record whose job id disagrees with the
requested job id stops the build with exit 9 (``MG_FOREIGN_JOB``).

Failure discipline: every subprocess is a checked argument array
(never a shell string); every produced file is verified to exist, be
non-empty, and probe to its expected dimensions before it is
reported. A sheet-generation failure exits 5 (``MG_ENCODE_FAILED``).
This tool never prints the word PASS, in success or in failure: the
verdict vocabulary is ``complete`` / ``incomplete`` / ``failed``, and
the stdout report follows the Section 16.9 result shape with
``status`` SUCCEEDED only when the verdict is ``complete``.

Inputs beyond the video are optional but change what is required:

- ``--timeline``: a compiled canonical timeline document (the
  ``timeline`` half of the MG-021 compiler output). Supplies scene
  boundaries, events, fps, total frames, and the job id.
- ``--sidecar``: the MG-021 ``TimelineSidecar`` JSON. Supplies
  caption ranges (text swaps) and narration ranges.
- ``--review-record``: an MG-024 ``preview.review.json`` sidecar.
  Its hashes and geometry are bound into the coverage record so a
  reviewer can prove the bundle describes the exact artifact the
  preview gate saw, and its label is carried through (a bundle over
  a ``rough_layout_only`` artifact says so; MG-031 records evidence,
  it does not upgrade rough evidence into motion evidence).
- ``--beats``: a beat grid JSON with ``beat_times`` in seconds (the
  ``scripts/beat-grid.py`` output shape the legacy assembler read).

Sampling policy: interval samples at frames ``0, step, 2*step, ...``
with ``step = round(interval_seconds * fps)`` (at least 1), so the
largest unsampled gap never exceeds the declared interval. Frame
numbers are decoded-frame indices in presentation order; a frame's
timestamp is ``frame / fps``.

Exit codes (Section 16.9): 0 complete; 2 MG_SCHEMA_INVALID (a record
that cannot be parsed or contradicts the request); 3 MG_INPUT_MISSING
(video or a required tool absent); 5 MG_ENCODE_FAILED (probe,
extraction, scaling, or sheet failure); 6 MG_COVERAGE_INCOMPLETE;
9 MG_FOREIGN_JOB.

CLI:
    python3 scripts/critique_bundle.py build --video V --outdir D
        [--job-id ID] [--timeline T] [--sidecar S]
        [--review-record R] [--beats B]
        [--interval SECONDS] [--destination WxH ...]
        [--sheet-columns N] [--tile-width PX]

Prints one JSON report to stdout; diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

VERSION = "2.0"

EXIT_OK = 0
EXIT_SCHEMA_INVALID = 2
EXIT_INPUT_MISSING = 3
EXIT_ENCODE_FAILED = 5
EXIT_COVERAGE_INCOMPLETE = 6
EXIT_FOREIGN_JOB = 9


class BundleError(Exception):
    """A build failure with its stable Section 16.9 category."""

    def __init__(self, message: str, category: str, exit_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.exit_code = exit_code


def schema_error(message: str) -> BundleError:
    return BundleError(message, "MG_SCHEMA_INVALID", EXIT_SCHEMA_INVALID)


def encode_error(message: str) -> BundleError:
    return BundleError(message, "MG_ENCODE_FAILED", EXIT_ENCODE_FAILED)


# ---------------------------------------------------------------------------
# Subprocess and probe discipline (checked argument arrays, verified output)
# ---------------------------------------------------------------------------


def run_checked(argv: list[str], what: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=3600
        )
    except FileNotFoundError as exc:
        raise BundleError(
            f"{what}: required tool not found: {argv[0]}",
            "MG_INPUT_MISSING",
            EXIT_INPUT_MISSING,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise encode_error(f"{what}: {argv[0]} timed out") from exc
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        tail = detail[-1] if detail else "no diagnostics"
        raise encode_error(
            f"{what}: {argv[0]} exited {result.returncode}: {tail}"
        )
    return result


def require_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        try:
            subprocess.run(
                [tool, "-version"], capture_output=True, timeout=30
            )
        except FileNotFoundError as exc:
            raise BundleError(
                f"required tool not found: {tool}",
                "MG_INPUT_MISSING",
                EXIT_INPUT_MISSING,
            ) from exc


def probe_video(path: Path) -> dict:
    """Probe the video stream and return exact geometry and counts.

    The frame count comes from a full ``-count_frames`` pass (the
    legacy assembler's method): container headers under-report often
    enough that a coverage index cannot be built on them.
    """
    result = run_checked(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-count_frames",
            "-show_entries",
            "stream=width,height,avg_frame_rate,nb_read_frames",
            "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        f"probe {path}",
    )
    try:
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        width = int(stream["width"])
        height = int(stream["height"])
        frames = int(stream["nb_read_frames"])
        rate = Fraction(stream["avg_frame_rate"])
        duration = float(data["format"]["duration"])
    except (KeyError, IndexError, ValueError, ZeroDivisionError) as exc:
        raise encode_error(f"probe {path}: unparseable ffprobe output") from exc
    if frames <= 0 or width <= 0 or height <= 0 or rate <= 0:
        raise encode_error(
            f"probe {path}: no usable video stream "
            f"(frames={frames}, {width}x{height}, rate={rate})"
        )
    return {
        "width": width,
        "height": height,
        "frames": frames,
        "fps": rate,
        "duration_seconds": duration,
    }


def png_dimensions(path: Path) -> tuple[int, int]:
    """Dimensions of a produced PNG from its IHDR header.

    Every still this tool produces is a PNG, and a PNG's width and
    height are fixed fields in its first chunk. Reading them directly
    (the same header parse the MG-010 style-frame gate uses) verifies
    the produced geometry without a subprocess per frame.
    """
    try:
        with open(path, "rb") as handle:
            header = handle.read(24)
    except OSError as exc:
        raise encode_error(f"read dimensions of {path}: {exc}") from exc
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" \
            or header[12:16] != b"IHDR":
        raise encode_error(f"dimensions of {path}: not a PNG file")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def probe_has_audio(path: Path) -> bool:
    result = run_checked(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=index", "-of", "csv=p=0", str(path),
        ],
        f"probe audio of {path}",
    )
    return bool(result.stdout.strip())


def measure_loudness(path: Path) -> dict | None:
    """Integrated loudness via loudnorm analysis (metrics only).

    Returns None when the measurement cannot be parsed; loudness is
    informational here (sound sync scoring belongs to the critic and
    to MG-034 QC), never a bundle verdict input.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-i", str(path),
                "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=1800,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    text = result.stderr or ""
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        parsed = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None
    return {
        "integrated_lufs": parsed.get("input_i"),
        "true_peak_dbtp": parsed.get("input_tp"),
        "lra_lu": parsed.get("input_lra"),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_produced(path: Path, what: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise encode_error(f"{what}: expected output {path} was not produced")


def atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Input records: compiled timeline, sidecar, review record, beat grid
# ---------------------------------------------------------------------------

JOB_ID_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)


def sanitize_job_id(raw: str) -> str:
    cleaned = "".join(ch if ch in JOB_ID_CHARS else "-" for ch in raw)
    cleaned = cleaned.strip("-.")
    if not cleaned:
        raise schema_error(f"job id {raw!r} has no usable characters")
    return cleaned


def load_json_record(path: Path, what: str) -> dict:
    if not path.is_file():
        raise BundleError(
            f"{what} not found: {path}", "MG_INPUT_MISSING", EXIT_INPUT_MISSING
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise schema_error(f"{what} at {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise schema_error(f"{what} at {path} is not a JSON object")
    return data


def check_foreign(record_job: object, job_id: str, what: str) -> None:
    if record_job is not None and str(record_job) != job_id:
        raise BundleError(
            f"{what} belongs to job {record_job!r}, not job {job_id!r}",
            "MG_FOREIGN_JOB",
            EXIT_FOREIGN_JOB,
        )


def _int_field(record: dict, field: str, what: str) -> int:
    value = record.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise schema_error(f"{what}: field {field!r} must be an integer")
    return value


def parse_timeline(data: dict) -> dict:
    """Validate and normalize the canonical compiled timeline."""
    what = "timeline"
    scenes_raw = data.get("scenes")
    if not isinstance(scenes_raw, list) or not scenes_raw:
        raise schema_error("timeline: scenes must be a non-empty list")
    scenes = []
    for entry in scenes_raw:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise schema_error("timeline: every scene needs a string id")
        start = _int_field(entry, "start_frame", "timeline scene")
        end = _int_field(entry, "end_frame_exclusive", "timeline scene")
        if start < 0 or end <= start:
            raise schema_error(
                f"timeline scene {entry['id']!r}: invalid range [{start}, {end})"
            )
        scenes.append({"id": entry["id"], "start_frame": start,
                       "end_frame_exclusive": end})
    events = []
    events_raw = data.get("events", [])
    if not isinstance(events_raw, list):
        raise schema_error("timeline: events must be a list")
    for entry in events_raw:
        if not isinstance(entry, dict):
            raise schema_error("timeline: every event must be an object")
        etype = entry.get("type")
        if etype not in ("reveal_start", "proof", "hold_start", "cue"):
            raise schema_error(f"timeline: unknown event type {etype!r}")
        events.append({
            "id": str(entry.get("id", "")),
            "scene_id": str(entry.get("scene_id", "")),
            "frame": _int_field(entry, "frame", "timeline event"),
            "type": etype,
        })
    total = _int_field(data, "total_frames", "timeline")
    if total <= 0:
        raise schema_error("timeline: total_frames must be positive")
    return {
        "job_id": data.get("job_id"),
        "fps": data.get("fps"),
        "total_frames": total,
        "scenes": scenes,
        "events": events,
    }


def parse_sidecar(data: dict) -> dict:
    """Normalize the MG-021 sidecar facts this tool consumes."""
    captions = []
    for entry in data.get("captions", []) or []:
        if not isinstance(entry, dict):
            raise schema_error("sidecar: every caption must be an object")
        captions.append({
            "id": str(entry.get("id", "")),
            "scene_id": entry.get("sceneId"),
            "start_frame": _int_field(entry, "startFrame", "sidecar caption"),
            "end_frame_exclusive": _int_field(
                entry, "endFrameExclusive", "sidecar caption"
            ),
        })
    narration = []
    for entry in data.get("narration", []) or []:
        if not isinstance(entry, dict):
            raise schema_error("sidecar: every narration range must be an object")
        narration.append({
            "id": str(entry.get("id", "")),
            "scene_id": entry.get("sceneId"),
            "start_frame": _int_field(entry, "startFrame", "sidecar narration"),
        })
    return {
        "job_id": data.get("job_id"),
        "total_frames": data.get("total_frames"),
        "captions": captions,
        "narration": narration,
    }


def parse_beats(data: dict) -> list[float]:
    times = data.get("beat_times")
    if not isinstance(times, list) or not all(
        isinstance(t, (int, float)) and not isinstance(t, bool) for t in times
    ):
        raise schema_error("beat grid: beat_times must be a list of numbers")
    return sorted(float(t) for t in times)


def parse_destination(raw: str) -> tuple[int, int]:
    parts = raw.lower().split("x")
    if len(parts) != 2:
        raise schema_error(f"destination {raw!r} must look like 360x640")
    try:
        width, height = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise schema_error(f"destination {raw!r} must look like 360x640") from exc
    if width <= 0 or height <= 0:
        raise schema_error(f"destination {raw!r} must be positive")
    return width, height


# ---------------------------------------------------------------------------
# Sample planning (pure) and coverage accounting (pure)
# ---------------------------------------------------------------------------


def frame_time(frame: int, fps: Fraction) -> float:
    return round(frame * fps.denominator / fps.numerator, 3)


def scene_at(scenes: list[dict], frame: int) -> str | None:
    for scene in scenes:
        if scene["start_frame"] <= frame < scene["end_frame_exclusive"]:
            return scene["id"]
    return None


def plan_samples(
    total_frames: int,
    fps: Fraction,
    interval_seconds: float,
    timeline: dict | None,
    sidecar: dict | None,
    beat_times: list[float] | None,
) -> list[dict]:
    """The full sample plan: interval pagination plus targeted frames.

    Returns one entry per distinct (frame, kind, ref). Interval
    samples carry the runtime coverage; targeted samples are the
    frames the directive names (scene boundaries, proof states, text
    swaps, final hold) and are all required.
    """
    samples: list[dict] = []
    seen: set[tuple[int, str, str]] = set()

    def add(frame: int, kind: str, required: bool,
            scene_id: str | None = None, ref: str | None = None) -> None:
        key = (frame, kind, ref or "")
        if key in seen:
            return
        seen.add(key)
        samples.append({
            "frame": frame,
            "time_seconds": frame_time(frame, fps),
            "kind": kind,
            "scene_id": scene_id,
            "ref": ref,
            "required": required,
            "status": "planned",
        })

    scenes = timeline["scenes"] if timeline else []

    step = max(1, round(interval_seconds * fps.numerator / fps.denominator))
    frame = 0
    while frame < total_frames:
        add(frame, "interval", False, scene_at(scenes, frame))
        frame += step

    for scene in scenes:
        add(scene["start_frame"], "scene_boundary_start", True, scene["id"])
        add(scene["end_frame_exclusive"] - 1, "scene_boundary_end", True,
            scene["id"])

    if timeline:
        kind_by_type = {
            "proof": "proof",
            "hold_start": "hold_start",
            "reveal_start": "reveal_start",
            "cue": "cue",
        }
        for event in timeline["events"]:
            add(event["frame"], kind_by_type[event["type"]],
                event["type"] != "cue", event["scene_id"] or None,
                event["id"] or None)

    if sidecar:
        for caption in sidecar["captions"]:
            # The compiled sidecar's caption tracks carry no scene id
            # (CompiledRangeTrack is a job-level range); attribute the
            # scene from the timeline placement when the record does
            # not name one itself.
            add(caption["start_frame"], "text_swap", True,
                caption["scene_id"]
                or scene_at(scenes, caption["start_frame"]),
                caption["id"] or None)

    if beat_times:
        for index, seconds in enumerate(beat_times):
            beat_frame = int(round(seconds * fps.numerator / fps.denominator))
            add(beat_frame, "beat", True, scene_at(scenes, beat_frame),
                f"beat_{index}")

    add(total_frames - 1, "final_frame", True,
        scenes[-1]["id"] if scenes else None)

    samples.sort(key=lambda s: (s["frame"], s["kind"], s["ref"] or ""))
    return samples


def compute_coverage(
    samples: list[dict],
    declared_total: int,
    probed_frames: int,
    fps: Fraction,
) -> dict:
    """Covered and omitted intervals over [0, declared_total).

    An interval sample covers from its frame up to the next interval
    sample (or the end of the probed video). Everything else in the
    declared runtime is omitted, with the reason recorded per range.
    Covered plus omitted always sum to the declared total.
    """
    interval_frames = sorted(
        s["frame"] for s in samples
        if s["kind"] == "interval" and s["status"] == "extracted"
    )
    covered: list[tuple[int, int]] = []
    for index, start in enumerate(interval_frames):
        end = (interval_frames[index + 1]
               if index + 1 < len(interval_frames) else probed_frames)
        end = min(end, declared_total)
        if start < end:
            covered.append((start, end))
    covered.sort()
    merged: list[list[int]] = []
    for start, end in covered:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    omitted: list[dict] = []
    cursor = 0
    for start, end in merged:
        if cursor < start:
            omitted.append(_omitted_range(cursor, start, probed_frames))
        cursor = max(cursor, end)
    if cursor < declared_total:
        omitted.append(_omitted_range(cursor, declared_total, probed_frames))

    covered_frames = sum(end - start for start, end in merged)
    omitted_frames = sum(o["frames"] for o in omitted)
    return {
        "covered_intervals": [
            {
                "start_frame": start,
                "end_frame_exclusive": end,
                "start_seconds": frame_time(start, fps),
                "end_seconds": frame_time(end, fps),
            }
            for start, end in merged
        ],
        "omitted_intervals": omitted,
        "covered_frames": covered_frames,
        "omitted_frames": omitted_frames,
        "accounted_frames": covered_frames + omitted_frames,
    }


def _omitted_range(start: int, end: int, probed_frames: int) -> dict:
    if start >= probed_frames:
        reason = "beyond_probed_video_frames"
    else:
        reason = "sampling_gap_not_covered"
    return {
        "start_frame": start,
        "end_frame_exclusive": end,
        "frames": end - start,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Frame extraction, destination variants, contact sheets
# ---------------------------------------------------------------------------


def extract_frames(video: Path, frames: list[int],
                   out_paths: list[Path]) -> None:
    """Extract the requested frames in ONE decode pass.

    A select expression over the sorted frame list decodes the video
    once; outputs arrive in presentation order, which is the sorted
    order requested. The output count is verified against the request
    before any frame is claimed.
    """
    if not frames:
        return
    scratch = Path(tempfile.mkdtemp(
        prefix=".extract-", dir=str(out_paths[0].parent)
    ))
    try:
        pattern = str(scratch / "extract_%05d.png")
        expression = "+".join(f"eq(n\\,{f})" for f in frames)
        run_checked(
            [
                "ffmpeg", "-v", "error", "-i", str(video),
                "-vf", f"select={expression}",
                "-fps_mode", "vfr", "-frames:v", str(len(frames)),
                "-y", pattern,
            ],
            f"extract {len(frames)} frames",
        )
        produced = sorted(scratch.glob("extract_*.png"))
        if len(produced) != len(frames):
            raise encode_error(
                f"extract frames: requested {len(frames)}, ffmpeg produced "
                f"{len(produced)}"
            )
        for source, target in zip(produced, out_paths):
            os.replace(source, target)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def scale_frame(source: Path, target: Path, width: int, height: int) -> None:
    run_checked(
        [
            "ffmpeg", "-v", "error", "-i", str(source),
            "-vf", f"scale={width}:{height}:flags=lanczos",
            "-frames:v", "1", "-y", str(target),
        ],
        f"scale frame to {width}x{height}",
    )
    assert_produced(target, "scale frame")
    actual = png_dimensions(target)
    if actual != (width, height):
        raise encode_error(
            f"scale frame: expected {width}x{height}, probed {actual}"
        )


def _even(value: int) -> int:
    return max(2, int(round(value / 2.0)) * 2)


def build_sheets(frame_paths: list[Path], out_paths: list[Path],
                 columns: int, tile_width: int,
                 video_width: int, video_height: int) -> list[dict]:
    """Tile an extracted frame sequence into paginated contact sheets.

    Explicit compositing: every input is scaled to the tile size and
    placed by an xstack layout computed from its position, the same
    discipline as the runtime's ``buildContactSheet``. Returns one
    record per page with the frame file names it carries.
    """
    tile_height = _even(tile_width * video_height / video_width)
    per_page = columns * columns
    pages: list[dict] = []
    for page_index in range(math.ceil(len(frame_paths) / per_page)):
        chunk = frame_paths[page_index * per_page:(page_index + 1) * per_page]
        out = out_paths[page_index]
        if len(chunk) == 1:
            scale_frame(chunk[0], out, tile_width, tile_height)
        else:
            args = ["ffmpeg", "-v", "error"]
            for path in chunk:
                args += ["-i", str(path)]
            scaled = ";".join(
                f"[{i}:v]scale={tile_width}:{tile_height}[t{i}]"
                for i in range(len(chunk))
            )
            inputs = "".join(f"[t{i}]" for i in range(len(chunk)))
            layout = "|".join(
                f"{(i % columns) * tile_width}_{(i // columns) * tile_height}"
                for i in range(len(chunk))
            )
            args += [
                "-filter_complex",
                f"{scaled};{inputs}xstack=inputs={len(chunk)}"
                f":layout={layout}[out]",
                "-map", "[out]", "-frames:v", "1", "-y", str(out),
            ]
            run_checked(args, f"build contact sheet page {page_index + 1}")
            assert_produced(out, "build contact sheet")
            rows = math.ceil(len(chunk) / columns)
            cols_used = min(columns, len(chunk))
            expected = (tile_width * cols_used, tile_height * rows)
            actual = png_dimensions(out)
            if actual != expected:
                raise encode_error(
                    f"contact sheet page {page_index + 1}: expected "
                    f"{expected}, probed {actual}"
                )
        pages.append({
            "path": out.name,
            "frames": [p.name for p in chunk],
            "tile_width": tile_width,
            "tile_height": tile_height,
        })
    return pages


# ---------------------------------------------------------------------------
# Bundle assembly
# ---------------------------------------------------------------------------


def frame_file_name(job_id: str, frame: int) -> str:
    return f"{job_id}__f{frame:07d}.png"


def ensure_dir(path: Path) -> None:
    """Create a bundle directory, or fail as an encode-stage error.

    A path that already exists as a regular file (the forced
    sheet-failure shape) must surface as a named build failure with
    the JSON report, never as an uncaught traceback.
    """
    if path.exists() and not path.is_dir():
        raise encode_error(
            f"output path {path} exists and is not a directory"
        )
    path.mkdir(parents=True, exist_ok=True)


def write_records(outdir: Path, job_id: str, coverage: dict,
                  metrics: dict) -> dict:
    """Write the per-job records; add plain-name copies when safe.

    The per-job file names are the canonical, collision-proof records.
    A plain ``coverage.json`` / ``metrics.json`` copy is written only
    when none exists or the existing one names the same job, so a
    neighboring job's record is never overwritten.
    """
    coverage_name = f"{job_id}__coverage.json"
    metrics_name = f"{job_id}__metrics.json"
    atomic_write_json(outdir / coverage_name, coverage)
    atomic_write_json(outdir / metrics_name, metrics)
    plain = {"coverage": coverage_name, "metrics": metrics_name}
    for plain_name, payload, key in (
        ("coverage.json", coverage, "job_id"),
        ("metrics.json", metrics, "job_id"),
    ):
        plain_path = outdir / plain_name
        write_plain = True
        if plain_path.is_file():
            try:
                existing = json.loads(plain_path.read_text(encoding="utf-8"))
                if existing.get(key) != job_id:
                    write_plain = False
            except (OSError, json.JSONDecodeError):
                write_plain = False
        if write_plain:
            atomic_write_json(plain_path, payload)
            plain[plain_name.split(".")[0]] = plain_name
    return plain


def build_bundle(args: argparse.Namespace) -> dict:
    video = Path(args.video)
    outdir = Path(args.outdir)
    if not video.is_file():
        raise BundleError(
            f"video not found: {video}", "MG_INPUT_MISSING", EXIT_INPUT_MISSING
        )
    require_tools()

    timeline = None
    if args.timeline:
        timeline = parse_timeline(
            load_json_record(Path(args.timeline), "timeline")
        )
    sidecar = None
    if args.sidecar:
        sidecar = parse_sidecar(load_json_record(Path(args.sidecar), "sidecar"))
    review_record = None
    if args.review_record:
        review_record = load_json_record(
            Path(args.review_record), "review record"
        )
    beat_times = None
    if args.beats:
        beat_times = parse_beats(load_json_record(Path(args.beats), "beat grid"))

    if args.job_id:
        job_id = sanitize_job_id(args.job_id)
    elif timeline and timeline.get("job_id"):
        job_id = sanitize_job_id(str(timeline["job_id"]))
    elif review_record and review_record.get("jobId"):
        job_id = sanitize_job_id(str(review_record["jobId"]))
    else:
        job_id = sanitize_job_id(video.stem)

    if timeline:
        check_foreign(timeline.get("job_id"), job_id, "timeline")
    if sidecar:
        check_foreign(sidecar.get("job_id"), job_id, "sidecar")
    if review_record:
        check_foreign(review_record.get("jobId"), job_id, "review record")

    probed = probe_video(video)
    fps = probed["fps"]
    if timeline and timeline.get("fps"):
        timeline_fps = Fraction(str(timeline["fps"]))
        if timeline_fps != fps:
            raise schema_error(
                f"timeline fps {timeline['fps']} contradicts probed fps "
                f"{fps.numerator}/{fps.denominator}"
            )
    declared_total = (
        timeline["total_frames"] if timeline else probed["frames"]
    )
    if sidecar and sidecar.get("total_frames") not in (None, declared_total):
        raise schema_error(
            f"sidecar total_frames {sidecar['total_frames']} contradicts "
            f"declared total {declared_total}"
        )

    destinations = [parse_destination(raw) for raw in args.destination or []]

    samples = plan_samples(
        declared_total, fps, args.interval, timeline, sidecar, beat_times
    )
    for sample in samples:
        if sample["frame"] >= probed["frames"]:
            sample["status"] = "omitted"
            sample["omit_reason"] = "beyond_probed_video_frames"

    ensure_dir(outdir)
    full_dir = outdir / "frames" / "full"
    ensure_dir(full_dir)

    extractable = sorted(
        {s["frame"] for s in samples if s["status"] == "planned"}
    )
    out_paths = [full_dir / frame_file_name(job_id, f) for f in extractable]
    if extractable:
        extract_frames(video, extractable, out_paths)
    extracted = set()
    for frame, path in zip(extractable, out_paths):
        assert_produced(path, f"extract frame {frame}")
        actual = png_dimensions(path)
        if actual != (probed["width"], probed["height"]):
            raise encode_error(
                f"frame {frame}: expected {probed['width']}x"
                f"{probed['height']}, probed {actual}"
            )
        extracted.add(frame)
    for sample in samples:
        if sample["status"] == "planned" and sample["frame"] in extracted:
            sample["status"] = "extracted"
            name = frame_file_name(job_id, sample["frame"])
            sample["files"] = {"full": f"frames/full/{name}"}

    for width, height in destinations:
        label = f"{width}x{height}"
        dest_dir = outdir / "frames" / f"dest-{label}"
        ensure_dir(dest_dir)
        for frame in extractable:
            target = dest_dir / frame_file_name(job_id, frame)
            scale_frame(full_dir / frame_file_name(job_id, frame),
                        target, width, height)
        for sample in samples:
            if sample["status"] == "extracted":
                sample["files"][f"dest-{label}"] = (
                    f"frames/dest-{label}/"
                    f"{frame_file_name(job_id, sample['frame'])}"
                )

    sheets_dir = outdir / "sheets"
    ensure_dir(sheets_dir)
    interval_paths = [
        full_dir / frame_file_name(job_id, f)
        for f in sorted({s["frame"] for s in samples
                         if s["kind"] == "interval"
                         and s["status"] == "extracted"})
    ]
    targeted_paths = [
        full_dir / frame_file_name(job_id, f)
        for f in sorted({s["frame"] for s in samples
                         if s["kind"] != "interval"
                         and s["status"] == "extracted"})
    ]
    sheet_records: dict[str, list[dict]] = {}
    if interval_paths:
        page_paths = [
            sheets_dir / f"{job_id}__samples__p{i + 1:02d}.png"
            for i in range(math.ceil(len(interval_paths)
                                     / (args.sheet_columns ** 2)))
        ]
        sheet_records["interval"] = build_sheets(
            interval_paths, page_paths, args.sheet_columns,
            args.tile_width, probed["width"], probed["height"],
        )
    if targeted_paths:
        page_paths = [
            sheets_dir / f"{job_id}__targeted__p{i + 1:02d}.png"
            for i in range(math.ceil(len(targeted_paths)
                                     / (args.sheet_columns ** 2)))
        ]
        sheet_records["targeted"] = build_sheets(
            targeted_paths, page_paths, args.sheet_columns,
            args.tile_width, probed["width"], probed["height"],
        )

    coverage_math = compute_coverage(
        samples, declared_total, probed["frames"], fps
    )
    missing_required = [
        s for s in samples if s["required"] and s["status"] != "extracted"
    ]
    incomplete_reasons = []
    if coverage_math["omitted_frames"] > 0:
        incomplete_reasons.append(
            f"{coverage_math['omitted_frames']} frame(s) of the declared "
            "runtime are not covered by any sample"
        )
    if missing_required:
        incomplete_reasons.append(
            f"{len(missing_required)} required targeted sample(s) missing"
        )
    if timeline and probed["frames"] != declared_total:
        incomplete_reasons.append(
            f"probed frame count {probed['frames']} contradicts the "
            f"timeline total {declared_total}"
        )
    verdict = "complete" if not incomplete_reasons else "incomplete"

    coverage = {
        "schema_version": "1.0",
        "item": "MG-031",
        "job_id": job_id,
        "verdict": verdict,
        "video": {
            "path": str(video),
            "sha256": sha256_file(video),
            "bytes": video.stat().st_size,
            "width": probed["width"],
            "height": probed["height"],
            "fps": f"{fps.numerator}/{fps.denominator}",
            "probed_frames": probed["frames"],
            "duration_seconds": round(probed["duration_seconds"], 3),
        },
        "declared_total_frames": declared_total,
        "policy": {
            "interval_seconds": args.interval,
            "destinations": [f"{w}x{h}" for w, h in destinations],
            "sheet_columns": args.sheet_columns,
            "tile_width": args.tile_width,
        },
        "inputs": {
            "timeline": ({"sha256": sha256_file(Path(args.timeline))}
                         if args.timeline else None),
            "sidecar": ({"sha256": sha256_file(Path(args.sidecar))}
                        if args.sidecar else None),
            "review_record": None,
            "beats": ({"sha256": sha256_file(Path(args.beats))}
                      if args.beats else None),
        },
        "samples": samples,
        "sheets": sheet_records,
        "coverage": coverage_math,
        "findings": incomplete_reasons,
    }
    if review_record:
        coverage["inputs"]["review_record"] = {
            "engine": review_record.get("engine"),
            "label": review_record.get("label"),
            "rough_layout_only": review_record.get("roughLayoutOnly"),
            "source_hash": review_record.get("sourceHash"),
            "props_hash": review_record.get("propsHash"),
            "preview_hash": review_record.get("previewHash"),
        }
        coverage["review_record_sha256"] = sha256_file(
            Path(args.review_record)
        )

    loudness = measure_loudness(video) if probe_has_audio(video) else None
    metrics = {
        "schema_version": "1.0",
        "item": "MG-031",
        "job_id": job_id,
        "duration_seconds": round(probed["duration_seconds"], 3),
        "video_frames": probed["frames"],
        "fps": f"{fps.numerator}/{fps.denominator}",
        "width": probed["width"],
        "height": probed["height"],
        "loudness": loudness,
    }

    record_names = write_records(outdir, job_id, coverage, metrics)
    report = {
        "command": "critique_bundle",
        "job_id": job_id,
        "status": "SUCCEEDED" if verdict == "complete" else "FAILED",
        "exit_code": EXIT_OK if verdict == "complete"
        else EXIT_COVERAGE_INCOMPLETE,
        "verdict": verdict,
        "coverage_record": record_names["coverage"],
        "metrics_record": record_names["metrics"],
        "bundle_dir": str(outdir),
        "samples": len(samples),
        "sheets": sum(len(pages) for pages in sheet_records.values()),
        "findings": incomplete_reasons,
    }
    if verdict != "complete":
        report["category"] = "MG_COVERAGE_INCOMPLETE"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="critique_bundle",
        description="Build a coverage-indexed visual review bundle (MG-031).",
    )
    parser.add_argument("--version", action="version",
                        version=f"critique_bundle {VERSION}")
    sub = parser.add_subparsers(dest="command")
    build = sub.add_parser("build", help="build a review bundle")
    build.add_argument("--video", required=True)
    build.add_argument("--outdir", required=True)
    build.add_argument("--job-id")
    build.add_argument("--timeline")
    build.add_argument("--sidecar")
    build.add_argument("--review-record")
    build.add_argument("--beats")
    build.add_argument("--interval", type=float, default=5.0,
                       help="interval sampling period in seconds (default 5)")
    build.add_argument("--destination", action="append", default=[],
                         help="destination size WxH; repeatable")
    build.add_argument("--sheet-columns", type=int, default=4)
    build.add_argument("--tile-width", type=int, default=480)
    args = parser.parse_args(argv)
    if args.command != "build":
        parser.print_help(sys.stderr)
        return EXIT_SCHEMA_INVALID
    if args.interval <= 0:
        print("interval must be positive", file=sys.stderr)
        return EXIT_SCHEMA_INVALID
    if args.sheet_columns < 1 or args.tile_width < 16:
        print("sheet geometry must be positive", file=sys.stderr)
        return EXIT_SCHEMA_INVALID
    try:
        report = build_bundle(args)
    except BundleError as exc:
        print(json.dumps({
            "command": "critique_bundle",
            "status": "FAILED",
            "exit_code": exc.exit_code,
            "category": exc.category,
            "message": exc.message,
        }, indent=2, sort_keys=True))
        print(f"critique_bundle: {exc.category}: {exc.message}",
              file=sys.stderr)
        return exc.exit_code
    except OSError as exc:
        wrapped = encode_error(f"filesystem failure: {exc}")
        print(json.dumps({
            "command": "critique_bundle",
            "status": "FAILED",
            "exit_code": wrapped.exit_code,
            "category": wrapped.category,
            "message": wrapped.message,
        }, indent=2, sort_keys=True))
        print(f"critique_bundle: {wrapped.category}: {wrapped.message}",
              file=sys.stderr)
        return wrapped.exit_code
    print(json.dumps(report, indent=2, sort_keys=True))
    return int(report["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
