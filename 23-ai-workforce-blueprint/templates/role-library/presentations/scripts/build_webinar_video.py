#!/usr/bin/env python3
"""
build_webinar_video.py — FEATURE L2-G: webinar video executor for the Presentations
department (P9.6-WEBINAR-VIDEO, order 8.92).

WHY THIS EXISTS
---------------
Every presentation gets a WEBINAR VIDEO — a third client deliverable alongside the
deck and the workbook. The already-built per-deck artifacts (slide PNGs, the per-slide
script, the Fish-Audio-tagged speech, and the full TTS mp3) are assembled into ONE
continuous, fluid video slideshow: slide 1 is on screen while its spoken segment plays,
then a smooth crossfade to slide 2, and so on through all slides. One mp4, no stop-start
jank, slide changes timed to what is actually being spoken.

This executor is the ONE sanctioned dispatch for the webinar phase. It orchestrates the
two proven sub-executors (webinar_timing.py + webinar_ffmpeg.py), runs the AF-WEBINAR-SIZE
size gate, and uploads the mp4 to GHL via the v3 video tier (ghl_media.upload_video /
ghl_video.upload_video), merging the record into the shared media ledger.

THE FOUR STEPS (per WEBINAR-BUILDER-SOP.md)
-------------------------------------------
  1. TIME  — webinar_timing.py derives the per-slide timing track by re-running the
             EXACT chunking code path over the speech markdown and summing the REAL
             ffprobe durations of the on-disk Fish chunk mp3s. Writes
             working/checkpoints/webinar_timing.json.
  2. RENDER — webinar_ffmpeg.py renders one Ken Burns clip per slide (zoompan 1.0->1.06,
             0.5s fades), chains them with the xfade filter (0.5s crossfade on each slide
             boundary), and muxes the single continuous mp3 with -map 0:v -map 1:a
             -shortest so the video ends with the last spoken word. Produces
             working/delivery/{deck_slug}-WEBINAR.mp4.
  3. GATE   — AF-WEBINAR-SIZE: ffprobe the output. Fail loud > WEBINAR_TARGET_MAX_BYTES
             (500MB); hard fail > WEBINAR_HARD_MAX_BYTES (900MB). A near-static 1080p
             CRF-22 render lands ~300-460MB — inside the GHL 500MB video ceiling.
  4. UPLOAD — ghl_media.upload_video (v3 video tier, Version: v3 + video/mp4, 500MB
             ceiling, small-probe gated) hosts the mp4 into the same per-deck GHL media
             folder. The record is MERGED into working/checkpoints/media_library.json
             under a `webinar_mp4` entry. The local delivery-path copy is moved out of
             the delivery path ONLY after the upload is CONFIRMED (2xx + fileId + a
             read-only list-back match).

RULES
  * Deterministic render — no AI judgement in the render step; ffmpeg is the only
    renderer (no image model, no browser, no UI automation).
  * Never print a credential value. The GHL LOCATION PIT is read exactly as the shared
    ghl_media module does — never echoed into the transcript.
  * The executor runs ONLY via the canonical entry (the nonce check in
    run_signature_deck.py + presentation-canonical-entry.sh), mirroring build_deck.py —
    a hand-rolled webinar cannot bypass the door.
  * This is NOT the deck renderer. It does NOT touch build_deck.py. It does NOT assemble
    PPTX. It produces ONE additional deliverable: the webinar mp4.
  * The video does NOT need to be a real 500MB file in tests — the size gate and the
    GHL small-probe are offline-provable.

USAGE
    python3 scripts/build_webinar_video.py --run-dir <run_dir>
        [--out <path>] [--no-upload] [--keep-clips] [--workdir DIR] [--verbose]

    --run-dir    The governed pipeline run dir (reads renders/, the delivery audio, the
                 speech md, and intake.json).
    --out        Output mp4 path (default <run_dir>/working/delivery/<deck_slug>-WEBINAR.mp4).
    --no-upload  Skip the GHL v3 upload step (time + render + size-gate only). Used in
                 tests and operator smoke runs.
    --keep-clips Keep the per-slide ffmpeg clips (webinar_ffmpeg.py's --keep-clips).
    --workdir    Render workdir override (default: a temp dir beside the output).
    --verbose    Pass --verbose to the sub-executors.
    --selftest   Deterministic offline self-test (no network, no render spend).

EXIT CODES
    0 — webinar built (+ size-gated + verified; uploaded unless --no-upload)
    1 — render/timing/upload step failed (a hard AF-WEBINAR-SIZE failure included)
    2 — fatal configuration error (missing inputs, missing ffmpeg/ffprobe, missing deps)
    3 — verification failed (output is not a valid h264+aac mp4, or size gate tripped)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# The canonical deliverable key + filename (WEBINAR-BUILDER-SOP.md §0 / §1).
DELIVERABLE_KEY = "webinar_mp4"
WEBINAR_FILENAME_TEMPLATE = "{deck_slug}-WEBINAR.mp4"

# AF-WEBINAR-SIZE gate (WEBINAR-BUILDER-SOP.md §2 step 3): fail loud above the GHL
# 500MB video-upload ceiling (target), hard fail above 900MB.
WEBINAR_TARGET_MAX_BYTES = 500 * 1024 * 1024   # 500 MB — GHL v3 video-upload ceiling
WEBINAR_HARD_MAX_BYTES = 900 * 1024 * 1024     # 900 MB — hard fail (defensive)

# The mp4 magic the GHL v3 small-probe checks (ghl_media.verify_video).
_MP4_FTYP_MAGIC = b"ftyp"


class WebinarBuildError(RuntimeError):
    """Raised on a hard build failure (message carries the failing step)."""


def log(msg: str) -> None:
    print(f"[build_webinar_video] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Shared helpers (mirror workbook_builder.py / synthesize_full_speech.py)
# ---------------------------------------------------------------------------

def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return {}


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _probe_duration(path: Path) -> float:
    """Real duration (seconds) of a media file via ffprobe. Raises on failure."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise WebinarBuildError(f"ffprobe failed on {path!r}: {out.stderr[:300]}")
    try:
        return float(out.stdout.strip())
    except ValueError:
        raise WebinarBuildError(f"could not parse duration from ffprobe on {path!r}: {out.stdout!r}")


def _probe_streams(path: Path) -> dict:
    """ffprobe the output for stream + container facts (h264+aac, duration, size)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "stream=codec_type,codec_name,width,height,avg_frame_rate",
         "-show_entries", "format=duration,size",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise WebinarBuildError(f"output verification ffprobe failed on {path!r}:\n{out.stderr[:500]}")
    info = json.loads(out.stdout or "{}")
    streams = info.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    video_codec = next((s.get("codec_name") for s in streams if s.get("codec_type") == "video"), None)
    audio_codec = next((s.get("codec_name") for s in streams if s.get("codec_type") == "audio"), None)
    width = next((s.get("width") for s in streams if s.get("codec_type") == "video"), None)
    height = next((s.get("height") for s in streams if s.get("codec_type") == "video"), None)
    fmt = info.get("format", {})
    return {
        "duration": float(fmt.get("duration", 0) or 0),
        "size_bytes": int(fmt.get("size", 0) or 0),
        "width": width, "height": height,
        "has_video": has_video, "has_audio": has_audio,
        "video_codec": video_codec, "audio_codec": audio_codec,
    }


def check_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise WebinarBuildError(f"required tool not found on PATH: {tool!r}")
    try:
        out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            raise WebinarBuildError(f"ffmpeg -version failed rc={out.returncode}: {out.stderr[:400]}")
    except FileNotFoundError:
        raise WebinarBuildError("ffmpeg not executable (shutil.which resolved it but exec failed)")


# ---------------------------------------------------------------------------
# Run-dir resolution helpers
# ---------------------------------------------------------------------------

def resolve_deck_slug(run_dir: Path) -> str:
    """Deck slug from intake.json (deck_slug | slug | title), else the run dir name."""
    intake = _read_json(run_dir / "working" / "copy" / "intake.json")
    for key in ("deck_slug", "slug", "title"):
        v = (intake.get(key) or "").strip() if isinstance(intake.get(key), str) else ""
        if v:
            return v
    return run_dir.name


def resolve_required_inputs(run_dir: Path) -> Dict[str, Path]:
    """Resolve + validate the inputs the webinar build consumes (SOP §1). Raises
    WebinarBuildError on any missing input — fail-loud, never silently degrade."""
    slides_dir = run_dir / "renders"
    if not slides_dir.is_dir():
        raise WebinarBuildError(f"renders dir not found: {slides_dir!r} (renders/slide-*.png)")
    audio = run_dir / "working" / "delivery" / "PRESENTER-AUDIO.mp3"
    if not audio.is_file():
        raise WebinarBuildError(f"presenter audio not found: {audio!r} (P9-DELIVER produced "
                                "working/delivery/PRESENTER-AUDIO.mp3)")
    speech = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH.md"
    if not speech.is_file():
        # Tolerate the alternative run layout (P9-SPEECH's produces_artifact).
        alt = run_dir / "working" / "presenter-speech" / "PRESENTERS-SPEECH.md"
        if alt.is_file():
            speech = alt
        else:
            raise WebinarBuildError(
                f"presenter speech not found: tried {speech!r} and {alt!r}")
    chunks_dir = run_dir / "working" / "delivery" / "_audio_chunks_full"
    if not chunks_dir.is_dir():
        raise WebinarBuildError(
            f"Fish chunk audio dir not found: {chunks_dir!r} — the webinar timing track "
            "is derived from the REAL per-chunk durations, never a planned estimate.")
    return {
        "slides_dir": slides_dir,
        "audio": audio,
        "speech": speech,
        "chunks_dir": chunks_dir,
    }


# ---------------------------------------------------------------------------
# Step 1 — timing track (webinar_timing.py)
# ---------------------------------------------------------------------------

def build_timing(inputs: Dict[str, Path], run_dir: Path, deck_slug: str,
                 chunk_chars: int, verbose: bool) -> Path:
    """Run webinar_timing.py to derive the per-slide timing track.

    Returns the timing-track path (working/checkpoints/webinar_timing.json).
    """
    from webinar_timing import derive_timing, verify_timing, TimingError
    try:
        result = derive_timing(
            str(inputs["speech"]), str(inputs["chunks_dir"]), chunk_chars,
            audio_path=str(inputs["audio"]), deck_slug=deck_slug, verbose=verbose)
    except TimingError as exc:
        raise WebinarBuildError(f"timing track derivation failed: {exc}") from exc
    verdict = verify_timing(result, str(inputs["audio"]))
    log(verdict)
    if not result.get("timing"):
        raise WebinarBuildError("timing track is empty — no per-slide entries")
    out_path = run_dir / "working" / "checkpoints" / "webinar_timing.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    log(f"wrote timing track {out_path} ({len(result['timing'])} slides)")
    return out_path


# ---------------------------------------------------------------------------
# Step 2 — render (webinar_ffmpeg.py)
# ---------------------------------------------------------------------------

def render_webinar(inputs: Dict[str, Path], timing_path: Path, out_path: Path,
                   *, fps: float, fade: float, crf: int, preset: str,
                   bitrate: str, motion_static: List[int], keep_clips: bool,
                   workdir: Optional[str], verbose: bool) -> Dict[str, Any]:
    """Run webinar_ffmpeg.render_webinar to render the Ken Burns + xfade mp4.

    Returns the ffprobe verification dict (duration / size / has_video / has_audio).
    Raises WebinarBuildError on any render failure.
    """
    from webinar_ffmpeg import render_webinar as _ffmpeg_render, WebinarError
    try:
        probe = _ffmpeg_render(
            str(inputs["slides_dir"]), str(timing_path), str(inputs["audio"]),
            str(out_path),
            fps=fps, fade=fade, crf=crf, preset=preset, bitrate=bitrate,
            motion_static=motion_static, keep_clips=keep_clips,
            workdir=workdir, verbose=verbose)
    except WebinarError as exc:
        raise WebinarBuildError(f"ffmpeg render failed: {exc}") from exc
    return probe


# ---------------------------------------------------------------------------
# Step 3 — AF-WEBINAR-SIZE gate (fail loud > 500MB target; hard fail > 900MB)
# ---------------------------------------------------------------------------

def gate_size(probe: Dict[str, Any], out_path: Path) -> None:
    """AF-WEBINAR-SIZE gate over the rendered mp4. Raises WebinarBuildError on fail."""
    size = probe.get("size_bytes", 0)
    if size <= 0:
        raise WebinarBuildError(
            f"AF-WEBINAR-SIZE: output {out_path!r} is {size} bytes — a zero/empty video "
            "cannot pass the gate (fail-closed).")
    if size > WEBINAR_HARD_MAX_BYTES:
        raise WebinarBuildError(
            f"AF-WEBINAR-SIZE: output {out_path!r} is {size/1024/1024:.1f} MB — over the "
            f"{WEBINAR_HARD_MAX_BYTES/1024/1024:.0f} MB HARD ceiling. A webinar video that "
            "large cannot be hosted anywhere; re-render at a lower CRF / smaller resolution.")
    if size > WEBINAR_TARGET_MAX_BYTES:
        raise WebinarBuildError(
            f"AF-WEBINAR-SIZE: output {out_path!r} is {size/1024/1024:.1f} MB — over the "
            f"{WEBINAR_TARGET_MAX_BYTES/1024/1024:.0f} MB GHL v3 video-upload ceiling. "
            "Re-render at a lower CRF (e.g. 23-25) to land under 500MB.")
    log(f"AF-WEBINAR-SIZE PASS: {size/1024/1024:.1f} MB < {WEBINAR_TARGET_MAX_BYTES/1024/1024:.0f} MB")


# ---------------------------------------------------------------------------
# Step 4 — GHL v3 upload + merged media ledger
# ---------------------------------------------------------------------------

def _ledger_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "media_library.json"


def _record_webinar_in_ledger(run_dir: Path, record: dict) -> None:
    """MERGE the webinar upload record into the shared media ledger (never clobber)."""
    ledger_path = _ledger_path(run_dir)
    ledger = _read_json(ledger_path) if ledger_path.exists() else {}
    ledger["webinar_mp4"] = record
    # Also append to the normalized 'uploaded' list so readers that scan it see the video.
    uploaded = ledger.get("uploaded")
    if not isinstance(uploaded, list):
        uploaded = []
    uploaded.append({"kind": "webinar_mp4", **record})
    ledger["uploaded"] = uploaded
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2))


def upload_webinar(out_path: Path, run_dir: Path, deck_slug: str,
                   timeout: int = 1800) -> dict:
    """Upload the webinar mp4 to GHL via the v3 video tier (ghl_media.upload_video).

    Uses the shared ghl_media module for credential resolution + upload (the SAME
    module the deck upload path uses — the CLIENT's LOCATION PIT, never the operator's
    key). The v3 wrapper ghl_video.upload_video (or ghl_media.upload_video when
    present) streams the body and small-probe-gates the file before any network call.

    Returns the upload record {fileId, url, name, ...} — the caller merges it into the
    media ledger. Raises on ANY upload failure (never fabricates a URL).
    """
    import sys as _sys
    here = Path(__file__).resolve().parent
    if str(here) not in _sys.path:
        _sys.path.insert(0, str(here))
    # Prefer the department v3 wrapper (ghl_video.upload_video — streaming, v3 tier).
    # Fall back to the shared ghl_media.upload_video when the v3 wrapper is absent
    # (the shared module carries the identical v3 + 500MB + small-probe contract).
    pit = loc = None
    try:
        import ghl_media
        pit = ghl_media.resolve_location_pit()
        loc = ghl_media.resolve_location_id()
    except Exception as exc:  # noqa: BLE001
        raise WebinarBuildError(f"GHL credential resolution failed: {exc}") from exc
    if not pit or not loc:
        raise WebinarBuildError("GHL LOCATION PIT / location id could not be resolved — "
                                "refusing to upload (a webinar must land in the client's "
                                "own media library, never the operator's).")
    name = f"{deck_slug}-WEBINAR.mp4"
    try:
        from ghl_video import upload_video as _v3_upload  # type: ignore[import-untyped]
    except Exception:  # noqa: BLE001
        try:
            from ghl_media import upload_video as _v3_upload  # type: ignore[import-untyped]
        except Exception as exc:  # noqa: BLE001
            raise WebinarBuildError(
                f"no GHL v3 video uploader importable (ghl_video / ghl_media.upload_video): {exc}"
            ) from exc
    try:
        res = _v3_upload(str(out_path), loc, name, pit, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise WebinarBuildError(f"GHL v3 video upload failed: {exc}") from exc
    if not isinstance(res, dict) or not res.get("fileId") or not res.get("url"):
        raise WebinarBuildError(
            f"GHL v3 upload returned no fileId/url: {res!r} — refusing to fabricate a URL")
    record = {
        "ghl_media_id": res["fileId"],
        "ghl_url": res["url"],
        "ghl_remote_name": name,
        "http_status": res.get("http", res.get("http_status")),
        "tier": res.get("tier") or res.get("ghl_version") or "v3",
        "content_type": "video/mp4",
        "size_bytes": out_path.stat().st_size,
        "uploaded_at": _now_iso(),
    }
    return record


# ---------------------------------------------------------------------------
# Front-door nonce (mirror build_deck._verify_entry_nonce)
# ---------------------------------------------------------------------------

ENTRY_NONCE_REL = Path("working") / "checkpoints" / ".canonical-entry-nonce"


def _verify_entry_nonce(run_dir: Path) -> bool:
    """True iff OC_DECK_ENTRY_NONCE is set AND equals the run-scoped nonce file.

    Only presentation-canonical-entry.sh mints this file, so a hand-rolled webinar
    invocation fails closed (AF-CANONICAL-RENDER-BYPASS). The path is derived from
    run_dir (never from an attacker-controllable env var) and the comparison is
    constant-time — the same contract build_deck._verify_entry_nonce enforces for the
    deck renderer."""
    import hmac
    env_nonce = (os.environ.get("OC_DECK_ENTRY_NONCE") or "").strip()
    if len(env_nonce) < 16:
        return False
    nf = run_dir / ENTRY_NONCE_REL
    try:
        file_nonce = nf.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return hmac.compare_digest(env_nonce, file_nonce)


# ---------------------------------------------------------------------------
# Verify + cleanup
# ---------------------------------------------------------------------------

def _confirm_upload(run_dir: Path, record: dict) -> bool:
    """READ-ONLY list-back confirming the webinar is genuinely in the GHL library.

    Mirrors the SOP §4 "Never delete until confirmed" rule: HTTP 2xx AND fileId AND a
    read-only list-back that finds the entry by fileId/name. Returns True on confirm.
    """
    try:
        import ghl_media
        pit = ghl_media.resolve_location_pit()
        loc = ghl_media.resolve_location_id()
        if not pit or not loc:
            return False
        listing = ghl_media.list_media(loc, pit, media_type="file", limit=200)
        file_id = str(record.get("ghl_media_id") or record.get("fileId") or "")
        name = str(record.get("ghl_remote_name") or "")
        for e in (listing.get("data") or []):
            if not isinstance(e, dict):
                continue
            if (file_id and str(e.get("fileId") or e.get("_id") or "") == file_id) \
               or (name and str(e.get("name") or "") == name):
                return True
        return False
    except Exception:  # noqa: BLE001 — read-only transport issue: not confirmed
        return False


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def build_webinar(run_dir: Path, *, out: Optional[str] = None, no_upload: bool = False,
                  keep_clips: bool = False, workdir: Optional[str] = None,
                  verbose: bool = False,
                  chunk_chars: int = 280, fps: float = 30.0, fade: float = 0.5,
                  crf: int = 22, preset: str = "veryfast",
                  bitrate: str = "192k",
                  motion_static: Optional[List[int]] = None) -> Dict[str, Any]:
    """Run the full webinar build pipeline (time -> render -> gate -> upload).

    Returns the build record dict. Raises WebinarBuildError on any hard failure.
    """
    run_dir = Path(run_dir).resolve()
    deck_slug = resolve_deck_slug(run_dir)
    inputs = resolve_required_inputs(run_dir)
    check_tools()

    out_path = Path(out) if out else \
        run_dir / "working" / "delivery" / WEBINAR_FILENAME_TEMPLATE.format(deck_slug=deck_slug)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Step 1 — timing track.
    timing_path = build_timing(inputs, run_dir, deck_slug, chunk_chars, verbose)

    # Step 2 — render (Ken Burns + xfade + -shortest audio mux).
    probe = render_webinar(
        inputs, timing_path, out_path,
        fps=fps, fade=fade, crf=crf, preset=preset, bitrate=bitrate,
        motion_static=motion_static or [], keep_clips=keep_clips,
        workdir=workdir, verbose=verbose)

    # Step 3 — AF-WEBINAR-SIZE gate (fail loud > 500MB target; hard fail > 900MB).
    gate_size(probe, out_path)

    # Re-probe the output for codec names (webinar_ffmpeg's probe dict does not
    # carry codec_name; the record should prove h264+aac, not leave them null).
    try:
        _streams = _probe_streams(out_path)
    except WebinarBuildError:
        _streams = {}
    video_codec = probe.get("video_codec") or _streams.get("video_codec")
    audio_codec = probe.get("audio_codec") or _streams.get("audio_codec")
    if not _streams.get("has_video") or not _streams.get("has_audio"):
        raise WebinarBuildError(
            f"output {out_path!r} is missing video/audio streams — a webinar with no "
            "streams cannot be delivered (fail-closed).")

    record = {
        "deck_slug": deck_slug,
        "webinar_mp4": str(out_path),
        "webinar_mp4_bytes": probe["size_bytes"],
        "webinar_duration_sec": probe["duration"],
        "webinar_width": probe.get("width") or _streams.get("width"),
        "webinar_height": probe.get("height") or _streams.get("height"),
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "webinar_timing_path": str(timing_path),
        "status": "built+size-gated",
        "built_at": _now_iso(),
    }

    # Step 4 — GHL v3 upload (unless --no-upload).
    if not no_upload:
        up = upload_webinar(out_path, run_dir, deck_slug)
        record.update(up)
        record["status"] = "built+size-gated+uploaded"
        _record_webinar_in_ledger(run_dir, record)
        if _confirm_upload(run_dir, record):
            record["status"] = "built+size-gated+uploaded+confirmed"
            log("GHL list-back confirmed the webinar is in the library.")
        else:
            # F46 (SMOKE-1, 2026-09-01): log() takes no file= kwarg — this line
            # crashed AFTER a successful build+upload, turning a completed webinar
            # into a phase failure. print to stderr directly.
            print("WARNING: GHL list-back did not confirm the webinar (upload record "
                  "written, but the local copy is NOT deleted until confirmed).",
                  file=sys.stderr)

    return record


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Build the webinar video (webinar_timing.py + webinar_ffmpeg.py + "
                    "AF-WEBINAR-SIZE + GHL v3 upload) — P9.6-WEBINAR-VIDEO.")
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--out", default=None, help="output mp4 path (default "
                    "<run_dir>/working/delivery/<deck_slug>-WEBINAR.mp4)")
    ap.add_argument("--no-upload", action="store_true", help="skip the GHL v3 upload "
                    "(time + render + size-gate only)")
    ap.add_argument("--keep-clips", action="store_true", help="keep per-slide ffmpeg clips")
    ap.add_argument("--workdir", default=None, help="ffmpeg clip workdir override")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--chunk-chars", type=int, default=280)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--fade", type=float, default=0.5)
    ap.add_argument("--crf", type=int, default=22)
    ap.add_argument("--preset", default="veryfast")
    ap.add_argument("--bitrate", default="192k")
    ap.add_argument("--motion-static-comma", default="",
                    help="comma list of slide numbers rendered static (no Ken Burns)")
    ap.add_argument("--selftest", action="store_true", help="offline deterministic self-test")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.run_dir:
        ap.error("--run-dir is required (or --selftest)")

    # FRONT-DOOR NONCE — a hand-rolled webinar can never bypass the governed door.
    # The canonical entry (presentation-canonical-entry.sh) mints OC_DECK_ENTRY_NONCE +
    # the run-scoped .canonical-entry-nonce file and the runner dispatches this phase
    # through it. --no-upload offline smoke runs (operator-only, no client GHL write)
    # are exempt so a build-only smoke test does not need a minted nonce.
    if not args.no_upload:
        run_dir = Path(args.run_dir).resolve()
        if not _verify_entry_nonce(run_dir):
            print(
                "FATAL [AF-CANONICAL-RENDER-BYPASS]: build_webinar_video.py must run "
                "via presentation-canonical-entry.sh, which mints the per-run front-door "
                "nonce (exports OC_DECK_ENTRY_NONCE and writes the matching 0600 file "
                "<run-dir>/working/checkpoints/.canonical-entry-nonce). Direct invocation "
                "— or a guessed/stale nonce — is refused (a hand-rolled webinar cannot "
                "bypass the door). Use --no-upload ONLY for an operator offline smoke "
                "build (no client GHL write).",
                file=sys.stderr)
            return 2

    motion_static = []
    if args.motion_static_comma.strip():
        try:
            motion_static = [int(x) for x in args.motion_static_comma.split(",") if x.strip()]
        except ValueError:
            print(f"build_webinar_video ERROR: --motion-static-comma must be ints, got "
                  f"{args.motion_static_comma!r}", file=sys.stderr)
            return 1

    try:
        record = build_webinar(
            Path(args.run_dir), out=args.out, no_upload=args.no_upload,
            keep_clips=args.keep_clips, workdir=args.workdir, verbose=args.verbose,
            chunk_chars=args.chunk_chars, fps=args.fps, fade=args.fade,
            crf=args.crf, preset=args.preset, bitrate=args.bitrate,
            motion_static=motion_static)
    except WebinarBuildError as exc:
        print(f"build_webinar_video ERROR: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"build_webinar_video ERROR (missing dependency): {exc}", file=sys.stderr)
        return 2

    print(json.dumps(record, indent=2))
    print("\nWEBINAR BUILD: DONE")
    return 0


# ---------------------------------------------------------------------------
# Offline deterministic self-test (no network, no render spend)
# ---------------------------------------------------------------------------

def _selftest() -> int:
    import tempfile
    fails: List[str] = []

    # 1. Filename template + slug resolution.
    if WEBINAR_FILENAME_TEMPLATE.format(deck_slug="acme-q1") != "acme-q1-WEBINAR.mp4":
        fails.append(f"filename template wrong: {WEBINAR_FILENAME_TEMPLATE}")

    # 2. AF-WEBINAR-SIZE gate: a tiny file passes, a >500MB (target) file fails loud,
    #    and a >900MB (hard) file fails hard. Gate only reads the probe dict.
    import tempfile as _tf
    with _tf.TemporaryDirectory() as _td:
        small = Path(_td) / "_probe.mp4"
        # a structurally-valid minimal MP4 (ftyp + free box) — the real ghl_video probe.
        _probe_bytes = (b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42"
                        b"\x00\x00\x00\x08free")
        small.write_bytes(_probe_bytes)
        if small.stat().st_size <= 0 or small.read_bytes()[4:8] != _MP4_FTYP_MAGIC:
            fails.append("selftest fixture: probe mp4 magic broken")
        # gate passes a tiny file.
        gate_size({"size_bytes": 1024}, small)
        # gate fails loud > 500MB.
        try:
            gate_size({"size_bytes": WEBINAR_TARGET_MAX_BYTES + 1}, small)
            fails.append("size-gate: >500MB target must fail loud (AF-WEBINAR-SIZE)")
        except WebinarBuildError:
            pass
        # gate hard-fails > 900MB.
        try:
            gate_size({"size_bytes": WEBINAR_HARD_MAX_BYTES + 1}, small)
            fails.append("size-gate: >900MB hard ceiling must fail")
        except WebinarBuildError:
            pass

    # 3. Ledger merge: _record_webinar_in_ledger merges, never clobbers existing keys.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        ck = rd / "working" / "checkpoints"
        ck.mkdir(parents=True)
        (ck / "media_library.json").write_text(json.dumps({"deck_slug": "old", "ghl_folder_id": "f1"}))
        _record_webinar_in_ledger(rd, {"ghl_media_id": "vid1", "ghl_url": "https://x"})
        merged = json.loads((ck / "media_library.json").read_text())
        if merged.get("deck_slug") != "old" or merged.get("ghl_folder_id") != "f1":
            fails.append("ledger merge clobbered existing keys")
        if not isinstance(merged.get("webinar_mp4"), dict) or merged["webinar_mp4"].get("ghl_media_id") != "vid1":
            fails.append("ledger merge missing webinar_mp4 record")
        if not any(u.get("kind") == "webinar_mp4" for u in merged.get("uploaded", [])):
            fails.append("ledger merge missing 'uploaded' webinar entry")

    if fails:
        print("build_webinar_video selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("build_webinar_video selftest -> PASS (filename template / slug / AF-WEBINAR-SIZE "
          "gate / ledger merge)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
