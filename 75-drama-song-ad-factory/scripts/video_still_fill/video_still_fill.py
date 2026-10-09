"""video_still_fill: DEL-14's still-fill path -- full height by CROP-IN only.

Trevor order 2026-10-09 (mass swarm item C), unit PKG-05-U1.

A vertical master must be a full-height nine-by-sixteen frame with a PLAIN
top and the lip-sync subject filling it. The only legal way to reach full
height is to CROP IN to the source frame: scale the source up until it
covers the master canvas, then cut the overhang off, anchoring at the top
so the subject's face keeps its headroom and the plain top is the source's
own top.

The three illegal ways are named here once so nothing under this package
can reach for them:

  * STRETCH        one `scale` to the exact canvas, distorting the subject.
  * LETTERBOX      fit the whole source inside the canvas and pad the
                   remainder, so the frame is short of full height.
  * BLUR FILL      fake the missing height out of the frame itself -- an
                   edge-sampled backdrop, a gaussian-filled background, a
                   duplicated-and-blurred strip. There is no blurred mask
                   backdrop in this path, and there never is one.

The filter this module emits is therefore always a scale-up plus a crop:

    scale=<W>:<H>:force_original_aspect_ratio=increase,crop=w=<W>:h=<H>:x=0:y=0

`force_original_aspect_ratio=increase` guarantees the scaled frame is at
least W wide and at least H tall, so the following crop always has real
overhang to cut (no clamped crop of a too-small frame) and the aspect
ratio survives untouched -- that is what makes it a crop-in and not a
stretch. Anchoring at ``x=0, y=0`` is the plain-top anchor: the top rows of
the output are the top rows of the source, unchanged, never a synthesized
band.

Measurement (used by the assembler's QC and by this package's own test):

  top_band(path)      mean / max local horizontal gradient in the top rows
                      of the first frame;
  detail_ratio(path)  that same top-band mean over the mid-frame mean.

A crop-in frame carries the source's own detail at the top, so the top
band is as textured as the middle and the ratio sits near 1. A filled
frame has a synthesized, locally flat top, so the ratio collapses toward
0. The rule is measured, conservative and reportable -- it never guesses
from silence: an unreadable frame raises, it does not pass.

Pure stdlib. ffmpeg / ffprobe are invoked with argument arrays, never a
shell string, and only when this module is asked to measure. No media is
written; nothing here spends money.
"""
import json
import subprocess

TOOL_NAME = "video_still_fill"

#: Master canvas for a vertical deliverable.
PORTRAIT_W, PORTRAIT_H = 1080, 1920

#: Rows measured as the "plain top" band (2% of a 1920-tall master).
TOP_BAND_ROWS = 40

#: Rows measured as the subject band, centred on the middle of the frame.
MID_BAND_HALF = 20

#: detail_ratio = top_mean / mid_mean sits at ~1.0 for a crop-in frame and
#: collapses to ~0.0 for a filled one (measured on a sharp checkerboard
#: source: 0.985 crop-in, 0.000 filled). This floor is the only thing that
#: decides plain top vs. fill, and it is deliberately loose -- a real
#: photographic top band has plenty of local gradient even when it is soft.
PLAIN_TOP_RATIO_FLOOR = 0.25

#: A locally flat top band can never be the source's own detail, so the
#: crop-in claim also carries an absolute floor. Both must hold for the
#: top to count as plain; either one alone is undetermined, not a pass.
FLAT_BAND_MAX_FLOOR = 4


class StillFillError(ValueError):
    """Loud failure from this module (unreadable frame, bad geometry)."""


# --- the render path ---------------------------------------------------------

def cover_crop_filter(width=PORTRAIT_W, height=PORTRAIT_H, flags="lanczos"):
    """Filter segment that takes ANY source frame to a full-size canvas
    by crop-in only.

    Order is load bearing: scale-up FIRST (so the frame covers the canvas
    and has overhang to cut), crop SECOND (so nothing is ever padded,
    stretched or synthesized). `setsar=1` follows so concat/xfade never
    refuses a mixed-SAR join.

    Never a stretch (aspect ratio is preserved by
    ``force_original_aspect_ratio=increase``), never a letterbox (nothing
    is padded), never a blurred backdrop (nothing is sampled, duplicated
    or masked -- the top rows are the source's own, anchored at y=0).
    """
    w, h = _geometry(width, height)
    return ("scale=%d:%d:force_original_aspect_ratio=increase:flags=%s,"
            "crop=w=%d:h=%d:x=0:y=0,setsar=1" % (w, h, flags, w, h))


def still_clip_filter(width=PORTRAIT_W, height=PORTRAIT_H, flags="lanczos"):
    """Same crop-in path for a SINGLE still image driven with ffmpeg's
    ``-loop 1 -i <image>`` input: the image has no duration of its own, so
    nothing is trimmed or re-timed here, only filled to full height.
    """
    return cover_crop_filter(width, height, flags)


def still_clip_argv(src, output, width=PORTRAIT_W, height=PORTRAIT_H,
                    duration_s=2.0, fps=30, ffmpeg="ffmpeg"):
    """Argument ARRAY rendering one still image to a full-height clip.

    Crop-in only (see cover_crop_filter). No threads/nice prefix here --
    the caller is the one that owns the load governor, exactly as the
    assembler owns it for a master render.
    """
    w, h = _geometry(width, height)
    if not isinstance(duration_s, (int, float)) or duration_s <= 0:
        raise StillFillError("STILL_DURATION_BAD: %r" % (duration_s,))
    return [ffmpeg, "-y", "-loop", "1", "-framerate", "%g" % (fps,),
            "-t", "%.6f" % (duration_s,), "-i", str(src),
            "-vf", still_clip_filter(w, h),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "%g" % (fps,),
            str(output)]


# --- measurement -------------------------------------------------------------

def _geometry(width, height):
    for name, v in (("width", width), ("height", height)):
        if (isinstance(v, bool) or not isinstance(v, (int, float))
                or v != v or int(v) != v or v <= 0):
            raise StillFillError("STILL_GEOMETRY_BAD: %s=%r" % (name, v))
    return int(width), int(height)


def geometry(width, height):
    """Validate a canvas the crop-in path can cover: (width, height).

    Positive integers only. A canvas that fails this cannot be reached by
    a cover-then-crop -- the crop would clamp and the frame would ship
    short of full height -- so callers fail closed on it instead of
    rendering.
    """
    return _geometry(width, height)


def probe_size(path, ffprobe="ffprobe", timeout=30):
    """(width, height) of the first video stream, or StillFillError.

    Fail closed: a probe that cannot read the file names the file, and a
    stream with no decodable geometry is never treated as full height.
    """
    argv = [ffprobe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", str(path)]
    try:
        out = subprocess.run(argv, capture_output=True, text=True,
                             timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise StillFillError("FFPROBE_UNAVAILABLE: %s" % (exc,)) from exc
    if out.returncode != 0:
        raise StillFillError(
            "STILL_PROBE_FAILED: %s (%s)" % (path, (out.stderr or "").strip()))
    try:
        streams = json.loads(out.stdout).get("streams") or []
        w, h = streams[0]["width"], streams[0]["height"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise StillFillError(
            "STILL_GEOMETRY_UNKNOWN: %s (%s)" % (path, exc)) from exc
    return int(w), int(h)


def is_full_height(path, width=PORTRAIT_W, height=PORTRAIT_H, **kw):
    """True only when the file really probes to the full canvas.

    A frame that cannot be probed raises rather than passing -- absence of
    geometry is never evidence of full height.
    """
    return probe_size(path, **kw) == _geometry(width, height)


def frame_gray(path, ffmpeg="ffmpeg", ffprobe="ffprobe", timeout=60):
    """First frame of `path` as (width, height, bytes) of 8-bit luma."""
    try:
        meta = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=timeout, check=False)
        size = json.loads(meta.stdout)["streams"][0]
        w, h = int(size["width"]), int(size["height"])
        out = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(path), "-frames:v", "1",
             "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise StillFillError("FFMPEG_UNAVAILABLE: %s" % (exc,)) from exc
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise StillFillError("STILL_GEOMETRY_UNKNOWN: %s (%s)" % (path, exc)) \
            from exc
    if out.returncode != 0 or len(out.stdout) < w * h:
        raise StillFillError(
            "STILL_FRAME_UNREADABLE: %s (%s)"
            % (path, (out.stderr or b"").decode("utf-8", "replace").strip()))
    return w, h, out.stdout[:w * h]


def _band_stats(raw, width, y0, y1):
    """(mean, max) local horizontal gradient over rows [y0, y1)."""
    total, n, peak = 0.0, 0, 0
    for y in range(y0, y1):
        row = raw[y * width:(y + 1) * width]
        for x in range(width - 1):
            d = abs(row[x + 1] - row[x])
            total += d
            n += 1
            if d > peak:
                peak = d
    if n == 0:
        raise StillFillError("STILL_BAND_EMPTY: rows [%d, %d)" % (y0, y1))
    return total / n, peak


def frame_metrics(path, rows=TOP_BAND_ROWS, half=MID_BAND_HALF, **kw):
    """One decode, both bands: {'top_mean', 'top_max', 'rows',
    'mid_mean', 'ratio'}.

    The two metrics that decide plain top vs. fill are read off the SAME
    frame, so a disagreeing pair of ffmpeg calls can never be the reason a
    deliverable passes. Raises when the frame is unreadable.
    """
    w, h, raw = frame_gray(path, **kw)
    n = max(1, min(int(rows), h))
    top_mean, top_max = _band_stats(raw, w, 0, n)
    mid = h // 2
    mid_mean, _ = _band_stats(raw, w, max(0, mid - half), min(h, mid + half))
    return {"top_mean": top_mean, "top_max": top_max, "rows": n,
            "mid_mean": mid_mean, "ratio": top_mean / (mid_mean + 1e-9)}


def top_band(path, **kw):
    """{'mean', 'max', 'rows'} for the top rows of the first frame.

    These are the rows DEL-14 calls the plain top: a crop-in path shows
    the source's own detail here, a fill shows a synthesized flat band.
    """
    m = frame_metrics(path, **kw)
    return {"mean": m["top_mean"], "max": m["top_max"], "rows": m["rows"]}


def detail_ratio(path, **kw):
    """top-band mean over mid-frame mean -- the plain-top discriminator.

    ~1.0 for crop-in (the top carries the same detail as the subject
    band), ~0.0 for a filled frame (the top is locally flat while the
    subject band is not). Raises when the frame is unreadable.
    """
    return frame_metrics(path, **kw)["ratio"]


def is_plain_top(path, ratio_floor=PLAIN_TOP_RATIO_FLOOR,
                 flat_max_floor=FLAT_BAND_MAX_FLOOR, **kw):
    """True when the frame's top is the source's own plain top, not a fill.

    Both conditions must hold: the top band must carry real local detail
    (above the absolute floor) AND be as textured as the subject band
    (above the ratio floor). An unreadable frame raises instead of
    answering -- silence is never a pass.
    """
    m = frame_metrics(path, **kw)
    return m["top_max"] > flat_max_floor and m["ratio"] >= ratio_floor
