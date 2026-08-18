#!/usr/bin/env python3
# =============================================================================
# webinar_ffmpeg.py — ffmpeg Ken Burns + xfade webinar slideshow renderer
# (P9.6-WEBINAR-VIDEO). Consumed by build_webinar_video.py.
#
# Inputs:
#   - per-slide PNGs  renders/slide-NN.png (2048x1152)
#   - timing track    webinar_timing.json (see webinar_timing.py — per-slide
#                     [audio_start, audio_end, duration], REAL spoken durations)
#   - single audio    working/delivery/PRESENTER-AUDIO.mp3
#
# Output:
#   - 1920x1080 h264 yuv420p mp4, CRF 22, 30 fps, faststart, audio muxed with
#     -shortest (video cut to the audio length so the webinar ends with the last
#     spoken word).
#
# Pipeline (one ffmpeg call per slide, then one xfade+audio mux call):
#   1. Per slide N: a Ken Burns clip sized to timing[N].duration, with a 0.5s
#      fade-in at 0 and fade-out ending at duration-0.5. Ken Burns = a slow
#      push-in (zoompan) so still slides read as "produced", not static.
#   2. Chain every clip with the xfade filter: offset_k = sum(dur_1..dur_k) - k*XF.
#      The 0.5s xfade is centered on each slide boundary.
#   3. Mux the single continuous mp3 with -map 0:v -map 1:a -shortest.
#
# WHY per-slide durations, not equal shares:
#   The timing track carries the REAL spoken duration per slide (derived from the
#   Fish chunk audio). Equal shares would drift the video off the audio by
#   minutes. This module honors timing[N].duration exactly, so each slide is on
#   screen while its own spoken segment plays (within the ±0.25s of the centered
#   0.5s crossfade). This is the "fluid, no stop-start" guarantee.
#
# Usage:
#   python3 webinar_ffmpeg.py \
#       --slides /path/renders        # dir of slide-NN.png (2048x1152)
#       --timing /path/webinar_timing.json
#       --audio  /path/PRESENTER-AUDIO.mp3
#       --out    /path/<deck>-WEBINAR.mp4
#   Optional:
#       --fps 30 --fade 0.5 --crf 22 --preset veryfast --bitrate 192k
#       --keep-clips --workdir DIR --verbose
#       --motion-static-comma "1,3,8"   # slides rendered static (no Ken Burns)
#       --audio-start 100 --audio-duration 30
#                   # slice a window out of the audio source instead of muxing the
#                   # whole track (default: start=0, duration=video timeline)
#
# Size discipline (master-plan §5.5): CRF 22 near-static 1080p lands ~300-420MB
# for a ~29 min video — inside the 500MB GHL video cap. A post-render size check
# is the caller's job (build_webinar_video.py); this module reports the size.
#
# DETERMINISTIC: given the same slides, timing track, and audio, this script
# produces the same video (ffmpeg runs are non-interactive, no AI judgement).
# =============================================================================

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

FADE_DEFAULT = 0.5
FPS_DEFAULT = 30
CRF_DEFAULT = 22
PRESET_DEFAULT = "veryfast"
AUDIO_BITRATE_DEFAULT = "192k"
SOURCE_W, SOURCE_H = 2048, 1152
OUT_W, OUT_H = 1920, 1080
KENBURNS_ZOOM_END = 1.06  # slow 6% push-in reads "produced", not static


class WebinarError(RuntimeError):
    """Raised on invalid inputs or ffmpeg failure (message carries ffmpeg stderr)."""


def log(msg: str) -> None:
    print(f"[webinar_ffmpeg] {msg}", file=sys.stderr)


def run(cmd: list, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ----------------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------------
def check_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise WebinarError(f"required tool not found on PATH: {tool!r}")
    try:
        out = run(["ffmpeg", "-version"], timeout=30)
        if out.returncode != 0:
            raise WebinarError(f"ffmpeg -version failed rc={out.returncode}: {out.stderr[:400]}")
    except FileNotFoundError:
        raise WebinarError("ffmpeg not executable (shutil.which resolved it but exec failed)")


def probe_stream_duration(path: str) -> float:
    out = run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        timeout=60,
    )
    if out.returncode != 0:
        raise WebinarError(f"ffprobe failed on {path!r}: {out.stderr[:300]}")
    try:
        return float(out.stdout.strip())
    except ValueError:
        raise WebinarError(f"could not parse duration from ffprobe on {path!r}: {out.stdout!r}")


# ----------------------------------------------------------------------------
# Timing-track loading (webinar_timing.py schema)
# ----------------------------------------------------------------------------
def load_timing(path: str) -> list:
    """Load timing track -> [{slide, duration, audio_start, audio_end}, ...].

    Accepts BOTH the webinar_timing.py object schema
    {"timing": [{"slide","duration","audio_start","audio_end"}, ...]} AND a
    bare list of per-slide objects. Durations drive the clip sizes.
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    timing = data.get("timing") if isinstance(data, dict) else data
    if not isinstance(timing, list) or not timing:
        raise WebinarError(
            f"timing track {path!r} must be a JSON object with a 'timing' list "
            f"(webinar_timing.py schema) or a bare list"
        )
    segs = []
    expected = 1
    for i, entry in enumerate(timing):
        if not isinstance(entry, dict):
            raise WebinarError(f"timing[{i}]: expected object, got {type(entry).__name__}")
        slide = entry.get("slide")
        duration = entry.get("duration")
        if not isinstance(slide, int) or slide < 1:
            raise WebinarError(f"timing[{i}]: 'slide' must be a 1-based int, got {slide!r}")
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise WebinarError(f"timing[{i}]: 'duration' must be > 0, got {duration!r}")
        if slide != expected:
            raise WebinarError(
                f"timing slides must be contiguous 1..N; got slide {slide} at index {i} "
                f"(expected {expected})"
            )
        segs.append({
            "slide": slide,
            "duration": float(duration),
            "audio_start": entry.get("audio_start", 0.0),
            "audio_end": entry.get("audio_end", float(duration)),
        })
        expected += 1
    return segs


# ----------------------------------------------------------------------------
# Slide resolution + dimension check
# ----------------------------------------------------------------------------
def resolve_slides(slides_dir: str, segs: list) -> list:
    paths = []
    for seg in segs:
        p = os.path.join(slides_dir, f"slide-{seg['slide']:02d}.png")
        if not os.path.isfile(p):
            raise WebinarError(f"slide PNG not found: {p!r} (timing slide={seg['slide']})")
        paths.append(p)
    probe = run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", paths[0]],
        timeout=60,
    )
    if probe.returncode != 0:
        raise WebinarError(f"ffprobe failed on {paths[0]!r}: {probe.stderr[:300]}")
    try:
        w, h = probe.stdout.strip().split(",")
        w, h = int(w), int(h)
    except (ValueError, AttributeError):
        raise WebinarError(f"could not parse slide dimensions from ffprobe: {probe.stdout!r}")
    # No hard source-resolution requirement: the Ken Burns filter chain
    # (force_original_aspect_ratio=increase + crop + zoompan s=OUTxOUT) rescales
    # any aspect to the output. Only guard against degenerate/non-image inputs.
    if w < 64 or h < 64:
        raise WebinarError(
            f"slide {paths[0]!r} is {w}x{h} — suspiciously small for a rendered slide. "
            "Expected a real rendered PNG (e.g. 2048x1152 or 2688x1520)."
        )
    return paths


# ----------------------------------------------------------------------------
# Ken Burns filter (zoompan) + per-slide clip render
# ----------------------------------------------------------------------------
def build_clip_filter(duration: float, fps: float, motion: str = "kenburns") -> str:
    """The -vf chain for one slide: scale/crop to 1920x1080 + optional zoompan.

    motion='kenburns' -> slow push-in (zoom 1.0 -> 1.06). motion='static' ->
    plain scale+crop (for heavy-text slides where motion reads wrong).
    """
    base = (
        f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
        f"crop={OUT_W}:{OUT_H}"
    )
    if motion == "kenburns":
        n = max(1, int(round(duration * fps)))
        zexpr = f"1+({KENBURNS_ZOOM_END}-1)*on/{n}"
        zoompan = (
            f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={n}:s={OUT_W}x{OUT_H}:fps={fps}"
        )
        return f"{base},{zoompan}"
    return base


def render_slide_clip(slide_png: str, filt: str, clip_path: str, duration: float,
                      fade: float, fps: float, crf: int, preset: str,
                      verbose: bool) -> None:
    """Render one Ken Burns clip with 0.5s fade-in/out at the boundaries.

    The fade is applied here (on the motion clip) so the later xfade crossfades
    ALREADY-faded clips — the crossfade centers on each slide boundary.
    """
    fade_out_start = max(0.0, duration - fade)
    vf = (
        f"{filt},"
        f"fade=t=in:st=0:d={fade},"
        f"fade=t=out:st={fade_out_start:.3f}:d={fade}"
    )
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", slide_png,
        "-vf", vf,
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-t", f"{duration:.3f}",
        clip_path,
    ]
    if verbose:
        print("    " + " ".join(cmd), file=sys.stderr)
    proc = run(cmd)
    if proc.returncode != 0:
        raise WebinarError(f"ffmpeg clip render failed for {slide_png!r}:\n{proc.stderr[-2000:]}")


def build_xfade_chain(clip_paths: list, durations: list, fade: float,
                      verbose: bool = False) -> tuple:
    """Build the xfade filtergraph string + the -i input list.

    Offsets: offset_k = sum(dur_1..dur_k) - k*fade  (cumulative minus overlaps).
    With N clips there are N-1 transitions; the final output label is v{N-2}.
    Returns (filtergraph|None, inputs, final_label).
    """
    if len(clip_paths) != len(durations):
        raise WebinarError("clip/duration count mismatch")
    if len(clip_paths) == 1:
        return None, ["-i", clip_paths[0]], "0:v"

    filters = []
    cumulative = 0.0
    for k in range(1, len(clip_paths)):
        offset = cumulative + durations[k - 1] - fade
        if k == 1:
            in0, in1, outl = "[0:v]", "[1:v]", "v0"
        else:
            in0, in1 = f"[v{k-2}]", f"[{k}:v]"
            outl = f"v{k-1}"
        filters.append(
            f"{in0}{in1}xfade=transition=fade:duration={fade}:offset={offset:.6f}[{outl}]"
        )
        cumulative = cumulative + durations[k - 1] - fade
    final_label = f"[v{len(clip_paths) - 2}]"
    inputs = []
    for c in clip_paths:
        inputs += ["-i", c]
    return ";".join(filters), inputs, final_label


# ----------------------------------------------------------------------------
# Main render
# ----------------------------------------------------------------------------
def render_webinar(slides_dir: str, timing_path: str, audio_path: str, out_path: str,
                   fps: float = FPS_DEFAULT, fade: float = FADE_DEFAULT,
                   crf: int = CRF_DEFAULT, preset: str = PRESET_DEFAULT,
                   bitrate: str = AUDIO_BITRATE_DEFAULT,
                   motion_static: list = None, keep_clips: bool = False,
                   workdir: str = None, verbose: bool = False,
                   audio_start: float = 0.0, audio_duration: float = None) -> dict:
    """Render the webinar video. Returns the ffprobe verification dict.

    motion_static: optional list of slide numbers rendered static (no Ken Burns).
    audio_start: seek offset into the audio source (seconds).
    audio_duration: audio slice length (seconds); default = the video timeline.
    """
    if audio_start < 0:
        raise WebinarError(f"--audio-start must be >= 0, got {audio_start}")
    if audio_duration is not None and audio_duration <= 0:
        raise WebinarError(f"--audio-duration must be > 0, got {audio_duration}")
    check_tools()
    if fade <= 0:
        raise WebinarError(f"--fade must be > 0, got {fade}")
    if not (0 <= crf <= 51):
        raise WebinarError(f"--crf out of range (0-51): {crf}")

    segs = load_timing(timing_path)
    n = len(segs)
    slide_paths = resolve_slides(slides_dir, segs)
    durations = [s["duration"] for s in segs]
    audio_dur = probe_stream_duration(audio_path)
    total_video = sum(durations)
    log(f"audio {audio_dur:.3f}s; timing total {total_video:.3f}s")

    motion_static = set(motion_static or [])
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    os.makedirs(out_dir, exist_ok=True)
    workdir = workdir or tempfile.mkdtemp(prefix="webinar_ffmpeg_", dir=out_dir)
    os.makedirs(workdir, exist_ok=True)

    # 1) Render per-slide clips.
    clips = []
    for idx, seg in enumerate(segs):
        motion = "static" if seg["slide"] in motion_static else "kenburns"
        filt = build_clip_filter(seg["duration"], fps, motion)
        clip_path = os.path.join(workdir, f"clip-{idx:02d}.mp4")
        log(f"render clip {idx+1}/{n}: slide-{seg['slide']:02d} "
            f"hold={seg['duration']:.3f}s motion={motion}")
        render_slide_clip(slide_paths[idx], filt, clip_path, seg["duration"],
                          fade, fps, crf, preset, verbose)
        clips.append(clip_path)

    # 2) Probe actual clip durations so xfade offsets are exact.
    clip_durs = [probe_stream_duration(c) for c in clips]
    if verbose:
        log("clip durations: " + ", ".join(f"{d:.3f}s" for d in clip_durs))

    # 3) xfade chain + mux with a sliced audio window (-shortest).
    filtergraph, inputs, vmap = build_xfade_chain(clips, clip_durs, fade, verbose)
    if len(clips) > 1:
        log(f"xfade chain: {len(clips)-1} transitions")

    # The video timeline length: sum(actual clips) - fade*(N-1) from the overlap.
    timeline = sum(clip_durs) - fade * (n - 1)
    slice_len = audio_duration if audio_duration is not None else timeline
    log(f"audio slice: start={audio_start:.3f}s len={slice_len:.3f}s "
        f"(video timeline {timeline:.3f}s)")

    # Slice the audio with atrim inside the filtergraph (works for any container)
    # so a >60min presenter audio never needs a second -ss decode pass.
    audio_filt = (
        f"[{len(clips)}:a]atrim=start={audio_start:.6f}:duration={slice_len:.6f},"
        f"asetpts=PTS-STARTPTS,aresample=async=1[aout]"
    )
    inputs += ["-i", audio_path]
    cmd = ["ffmpeg", "-y", "-v", "error"] + inputs
    if filtergraph:
        cmd += ["-filter_complex", filtergraph + ";" + audio_filt]
    else:
        cmd += ["-filter_complex", audio_filt]
    cmd += [
        "-map", vmap, "-map", "[aout]",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", bitrate,
        "-shortest", "-movflags", "+faststart",
        out_path,
    ]
    if verbose:
        print("    " + " ".join(cmd), file=sys.stderr)
    proc = run(cmd, timeout=1800)
    if proc.returncode != 0:
        raise WebinarError(f"final xfade+audio mux failed:\n{proc.stderr[-3000:]}")

    if not keep_clips:
        shutil.rmtree(workdir, ignore_errors=True)

    # 4) Verify output.
    return probe_output(out_path)


def probe_output(out_path: str) -> dict:
    probe = run(
        ["ffprobe", "-v", "error",
         "-show_entries", "stream=codec_type,codec_name,width,height,avg_frame_rate",
         "-show_entries", "format=duration,size",
         "-of", "json", out_path],
        timeout=60,
    )
    if probe.returncode != 0:
        raise WebinarError(f"output verification ffprobe failed on {out_path!r}:\n{probe.stderr[:500]}")
    info = json.loads(probe.stdout or "{}")
    streams = info.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    fmt = info.get("format", {})
    dur = float(fmt.get("duration", 0) or 0)
    size = int(fmt.get("size", 0) or 0)
    if not has_video or not has_audio:
        raise WebinarError(f"output {out_path!r} missing streams: video={has_video} audio={has_audio}")
    width = next((s.get("width") for s in streams if s.get("codec_type") == "video"), None)
    height = next((s.get("height") for s in streams if s.get("codec_type") == "video"), None)
    log(f"output {out_path!r} ok: {dur:.3f}s, {size/1024:.1f} KiB, "
        f"{width}x{height} h264+aac")
    log("DONE")
    return {"duration": dur, "size_bytes": size, "width": width, "height": height,
            "has_video": has_video, "has_audio": has_audio}


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="ffmpeg Ken Burns + xfade webinar slideshow renderer (P9.6-WEBINAR-VIDEO).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--slides", required=True, help="dir of slide-NN.png (2048x1152)")
    ap.add_argument("--timing", required=True, help="webinar_timing.json (webinar_timing.py schema)")
    ap.add_argument("--audio", required=True, help="single mp3 audio track")
    ap.add_argument("--out", required=True, help="output .mp4 path")
    ap.add_argument("--fps", type=float, default=FPS_DEFAULT)
    ap.add_argument("--fade", type=float, default=FADE_DEFAULT)
    ap.add_argument("--crf", type=int, default=CRF_DEFAULT)
    ap.add_argument("--preset", default=PRESET_DEFAULT)
    ap.add_argument("--bitrate", default=AUDIO_BITRATE_DEFAULT)
    ap.add_argument("--motion-static-comma", default="",
                    help="comma list of slide numbers rendered static (no Ken Burns)")
    ap.add_argument("--audio-start", type=float, default=0.0,
                    help="seek offset into the audio source in seconds (default 0)")
    ap.add_argument("--audio-duration", type=float, default=None,
                    help="audio slice length in seconds (default = video timeline)")
    ap.add_argument("--keep-clips", action="store_true")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--verbose", action="store_true")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    motion_static = []
    if args.motion_static_comma.strip():
        try:
            motion_static = [int(x) for x in args.motion_static_comma.split(",") if x.strip()]
        except ValueError:
            print(f"webinar_ffmpeg ERROR: --motion-static-comma must be ints, got {args.motion_static_comma!r}",
                  file=sys.stderr)
            return 1
    try:
        render_webinar(
            args.slides, args.timing, args.audio, args.out,
            fps=args.fps, fade=args.fade, crf=args.crf, preset=args.preset,
            bitrate=args.bitrate, motion_static=motion_static,
            keep_clips=args.keep_clips, workdir=args.workdir, verbose=args.verbose,
            audio_start=args.audio_start, audio_duration=args.audio_duration,
        )
        return 0
    except WebinarError as exc:
        print(f"webinar_ffmpeg ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except WebinarError as exc:
        print(f"webinar_ffmpeg ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
