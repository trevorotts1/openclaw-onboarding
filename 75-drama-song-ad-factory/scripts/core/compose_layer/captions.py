"""Caption burn as ONE overlay stream in ONE pass (row N-49, sections 3D.2
and 3D.6).

Every cue for the whole master becomes one see-through overlay stream.
One ffmpeg pass lays it on the master; never one input per cue. The
measured job that took over 60 minutes used 61 looped picture inputs; the
same job took 22 seconds through one overlay stream. Budget: under 2
minutes for a 10-minute master.

HyperFrames renders the caption layer; ffmpeg lays it on. When HyperFrames
is missing, cue pictures are joined into one overlay stream with the concat
method and the same single pass is used. This module builds the stream and
the argv as data; it never encodes.

Stdlib only.
"""
from __future__ import annotations

from .engine import FFMPEG_FALLBACK, HYPERFRAMES, REMOTION
from .render_lock import video_args  # the one encode profile (fps, pix_fmt)

TOOL_NAME = "compose_captions"
TOOL_VERSION = "1.0.0"

#: One pass, one overlay input; the 10-minute budget from 3D.6.
REFERENCE_MASTER_S = 600.0
REFERENCE_BUDGET_S = 120.0
BUDGET_RATE = REFERENCE_BUDGET_S / REFERENCE_MASTER_S  # 0.2 s per master s

CAPTION_BURN_BUDGET_MISSED = "CAPTION_BURN_BUDGET_MISSED"
CAPTION_CUES_INVALID = "CAPTION_CUES_INVALID"
OVERLAY_INPUTS_MULTIPLE = "CAPTION_OVERLAY_INPUTS_MULTIPLE"
CUES_OVERLAP = "CAPTION_CUES_OVERLAP"

SRT = "srt"
ASS = "ass"


class CaptionError(RuntimeError):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def _srt_time(seconds):
    ms = int(round(float(seconds) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def _ass_time(seconds):
    """ASS uses H:MM:SS.cc (centiseconds), not the SRT millisecond form."""
    cs = int(round(float(seconds) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def validate_cues(cues):
    """Ordered, non-empty, non-overlapping cues; no clock is invented."""
    rows = []
    previous_end = -1.0
    for index, cue in enumerate(cues):
        try:
            start = float(cue["start"])
            end = float(cue["end"])
        except (KeyError, TypeError, ValueError):
            raise CaptionError(CAPTION_CUES_INVALID,
                               "cue %d has no measured start/end" % index)
        text = str(cue.get("text", "")).strip()
        if not text or end <= start or start < 0:
            raise CaptionError(CAPTION_CUES_INVALID,
                               "cue %d is empty or has a bad time range" % index)
        if start < previous_end:
            raise CaptionError(CUES_OVERLAP,
                               "cue %d overlaps cue %d" % (index, index - 1))
        previous_end = end
        rows.append({"start": start, "end": end, "text": text})
    if not rows:
        raise CaptionError(CAPTION_CUES_INVALID, "no cues")
    return rows


def overlay_stream(cues, fmt=SRT):
    """All cues as ONE stream (one caption layer), never one input per cue."""
    rows = validate_cues(cues)
    if fmt == SRT:
        body = "\n".join(
            "%d\n%s --> %s\n%s\n" % (i, _srt_time(c["start"]),
                                     _srt_time(c["end"]), c["text"])
            for i, c in enumerate(rows, 1))
    elif fmt == ASS:
        body = "\n".join(
            "Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
            % (_ass_time(c["start"]), _ass_time(c["end"]), c["text"])
            for c in rows)
    else:
        raise CaptionError(CAPTION_CUES_INVALID, "unsupported format %r" % fmt)
    return {"format": fmt, "stream": body, "cue_count": len(rows),
            "overlay_inputs": 1}


def caption_layer_plan(cues, engine, size=(1080, 1920), fps=24):
    """The one caption layer the compose engine renders (or the fallback)."""
    stream = overlay_stream(cues, SRT)
    if engine in (HYPERFRAMES, REMOTION):
        method = "compose-caption-layer"
    else:
        method = "ffmpeg-overlay-video"
    return {"engine": engine, "method": method, "size": list(size),
            "fps": fps, "layer": stream, "overlay_inputs": 1}


def budget_seconds(master_seconds):
    """Under 2 minutes for a 10-minute master; scales by the same rate."""
    return max(REFERENCE_BUDGET_S, float(master_seconds) * BUDGET_RATE)


def check_budget(master_seconds, elapsed_seconds):
    """A measured overrun is named; the burn is not claimed successful."""
    limit = budget_seconds(master_seconds)
    ok = float(elapsed_seconds) < limit
    return {"ok": ok, "master_s": float(master_seconds),
            "elapsed_s": float(elapsed_seconds), "limit_s": limit,
            "code": None if ok else CAPTION_BURN_BUDGET_MISSED}


def burn_argv(master, overlay, output, encoder="libx264", quality=18,
              overlay_is_video=True):
    """ONE ffmpeg pass: master plus exactly one overlay stream."""
    if not master or not overlay or not output:
        raise CaptionError(OVERLAY_INPUTS_MULTIPLE,
                           "master, one overlay and one output are required")
    # Same encode profile as the Clean deliverable: hardware on a Mac,
    # software on Linux, same frame rate and pixel format (3D.2, N-59).
    video = video_args(encoder, quality)
    if overlay_is_video:
        # HyperFrames' see-through render, or the concat-joined cue stream.
        argv = ["ffmpeg", "-y", "-i", master, "-i", overlay,
                "-filter_complex", "[0:v][1:v]overlay=shortest=1",
                "-map", "0:a?", *video, "-c:a", "copy", output]
        if overlay_input_count(argv) != 1:
            raise CaptionError(OVERLAY_INPUTS_MULTIPLE,
                               "caption burn must have one overlay input")
    else:
        # ffmpeg subtitle filter path where it exists (not on this Mac, 3D.1).
        # One input, no overlay stream, so the one-overlay-input rule is met.
        argv = ["ffmpeg", "-y", "-i", master,
                "-vf", "subtitles=%s" % overlay, *video,
                "-c:a", "copy", output]
    return argv


def overlay_input_count(argv):
    """Overlay inputs beyond the master; one pass, one overlay."""
    return max(0, len([a for a in argv if a == "-i"]) - 1)


def concat_overlay_plan(cue_images):
    """Fallback: cue pictures joined into ONE overlay stream, then one pass."""
    if not cue_images:
        raise CaptionError(CAPTION_CUES_INVALID, "no cue pictures")
    listing = "\n".join("file '%s'" % path.replace("'", "'\\''")
                        for path in cue_images)
    return {"method": "concat-demuxer", "stream_file": listing,
            "overlay_inputs": 1,
            "then": "burn_argv(overlay_is_video=True)"}


def concat_overlay_argv(cue_images, overlay_out, fps=24):
    """Build the single overlay stream once, with the concat method."""
    plan = concat_overlay_plan(cue_images)
    list_path = overlay_out + ".concat.txt"
    return plan, ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                  "-i", list_path, "-r", str(fps), "-pix_fmt", "yuv420p",
                  "-c:v", "png", overlay_out]
