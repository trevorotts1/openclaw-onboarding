"""qc_no_blur.detect: DEL-14 no-blur-fill detection (stdlib + ffmpeg).

Blur fill is never used. This module is the one place that names what a fill
looks like, in two forms:

  * ATTEMPT   -- a filtergraph / ffmpeg argv / plan field that would build a
                 fill: edge-sampled backdrop, gaussian-filled background,
                 duplicated blurred strip, blurred mask, letterbox pad.
  * RESULT    -- a rendered frame that already carries one, or a frame that
                 is short of full height because of a fill.

Every detection returns a violation dict {"code", "detail"} so the two gates
(final_assembler assembler_gate, delivery quality_gate) can refuse with an
error that names the violation and the repair: crop-in re-lip-sync
(qc_no_blur.crop_relip.regenerate) regenerates the clip from the source frame
so the flow recovers instead of filling.

Stdlib only for the analysis; shells to ffmpeg/ffprobe for pixels.
"""
from __future__ import annotations

import os
import re
import statistics
import subprocess

# ---------------------------------------------------------------- codes
EDGE_SAMPLED_BACKDROP = "EDGE_SAMPLED_BACKDROP"
GAUSSIAN_FILL = "GAUSSIAN_FILL"
DUPLICATED_BLURRED_STRIP = "DUPLICATED_BLURRED_STRIP"
BLUR_MASK = "BLUR_MASK"
LETTERBOX_FILL = "LETTERBOX_FILL"
FILL_ATTEMPT = "FILL_ATTEMPT"
FRAME_SHORT_OF_FULL_HEIGHT = "FRAME_SHORT_OF_FULL_HEIGHT"
UNREADABLE = "NO_BLUR_FILL_UNREADABLE"

#: The repair every refusal names. Crop-in is the ONLY path to full height.
REPAIR = ("blur fill is never used; regenerate the clip with crop-in "
          "re-lip-sync (qc_no_blur.crop_relip.regenerate) so the source "
          "frame fills the full height, then re-run lip-sync on it")

VIOLATIONS = (EDGE_SAMPLED_BACKDROP, GAUSSIAN_FILL,
              DUPLICATED_BLURRED_STRIP, BLUR_MASK, LETTERBOX_FILL,
              FILL_ATTEMPT, FRAME_SHORT_OF_FULL_HEIGHT)

_IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif",
                        ".tiff", ".gif"})

# ---------------------------------------------------------- text / argv
# Blur filters: none of them is ever legitimate in this skill's render path.
_BLUR = re.compile(r"(?<![a-z0-9_])(boxblur|gblur|avgblur|dblur)(?![a-z0-9_])")
# A 1-4 px crop taken from an edge and scaled up = edge-sampled backdrop.
_EDGE_CROP = re.compile(
    r"crop=(?:iw|ow):[1-4](?:[:\s,]|$)"
    r"|crop=[1-4]:(?:ih|oh)(?:[:\s,]|$)"
    r"|crop=(?:iw|ow):[1-4]:\d+:\d+"
    r"|crop=[1-4]:(?:ih|oh):\d+:\d+"
    r"|crop=\d{1,5}:[1-4]:\d+:\d+"
    r"|crop=[1-4]:\d{1,5}:\d+:\d+")
# Blur applied to a duplicated strip: split / tile / vstack / hstack / stack.
_DUP = re.compile(r"(?<![a-z0-9_])(split|tile|vstack|hstack|stack)(?:=|\[|,)")
# A blurred alpha mask: alphamerge (or a geq alpha) fed by a blurred layer.
_MASK = re.compile(r"alphamerge|geq=[^\]]*alpha")
# Black bars. Lookbehind keeps `apad` (audio) out of it.
_PAD = re.compile(r"(?<![a-z0-9_])pad=")

# Plan fields that carry a fill attempt (a renderer asking for one).
_FILL_KEY = re.compile(
    r"^(fill|fill_mode|backdrop|backdrop_fill|bg_fill|background_fill|"
    r"mask|mask_type|blur_mask|pad_fill)$", re.IGNORECASE)
_FILL_VALUE = re.compile(
    r"blur|gaussian|edge[_\s-]?sampl|duplicat|letterbox|black[_\s-]?bar",
    re.IGNORECASE)


def violation(code, detail):
    return {"code": code, "detail": detail}


def scan_text(text):
    """Violation list for a filtergraph / filter string. Pure, no I/O."""
    out = []
    if not text or not isinstance(text, str):
        return out
    if _EDGE_CROP.search(text):
        out.append(violation(
            EDGE_SAMPLED_BACKDROP,
            "filter uses a 1-4 px edge crop to build a backdrop: %s"
            % _EDGE_CROP.search(text).group(0)))
    if _PAD.search(text):
        out.append(violation(
            LETTERBOX_FILL,
            "filter pads the frame with bars instead of filling it: %s"
            % _PAD.search(text).group(0)))
    blurs = _BLUR.findall(text)
    if blurs:
        if _MASK.search(text):
            out.append(violation(
                BLUR_MASK,
                "blurred mask in the filtergraph (%s + %s)"
                % (sorted(set(blurs))[0], _MASK.search(text).group(0))))
        elif _DUP.search(text):
            out.append(violation(
                DUPLICATED_BLURRED_STRIP,
                "duplicated blurred strip in the filtergraph (%s + %s)"
                % (sorted(set(blurs))[0], _DUP.search(text).group(0))))
        else:
            out.append(violation(
                GAUSSIAN_FILL,
                "background blur fill in the filtergraph (%s)"
                % sorted(set(blurs))[0]))
    return out


_FILTER_ARGS = ("-filter_complex", "-vf", "-af", "-filter_script",
                "-lavfi")


def scan_argv(argv):
    """Violations in an ffmpeg argv: every filtergraph it would run."""
    parts = []
    for i, a in enumerate(argv or []):
        if not isinstance(a, str):
            continue
        if a in _FILTER_ARGS and i + 1 < len(argv):
            parts.append(argv[i + 1])
        elif any(a.startswith(x + "=") for x in _FILTER_ARGS):
            parts.append(a.split("=", 1)[1])
        elif "scale=" in a or "crop=" in a:
            parts.append(a)          # a bare filter string, argv or not
    return scan_text(";".join(p for p in parts if isinstance(p, str)))


def scan_plan(plan):
    """Violations in a plan/receipt structure: a renderer asking for a fill."""
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                here = "%s.%s" % (path, k) if path else str(k)
                if isinstance(v, str) and _FILL_KEY.match(str(k)) \
                        and _FILL_VALUE.search(v):
                    out.append(violation(
                        FILL_ATTEMPT, "%s = %r is a blur/edge fill request"
                        % (here, v)))
                walk(v, here)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i))

    walk(plan, "")
    return out


# --------------------------------------------------------------- frames
# ponytail: band thresholds calibrated on synthetic ffmpeg fixtures (blur
# band, edge column, duplicated strip, black pad, clean crop-in). They are
# fail-closed on purpose: a real master that trips them is repaired by the
# crop-in path, never by loosening a number. Upgrade to a perceptual /
# learned backdrop detector only when a shipped master shows a false fill.
SAMPLE_W = 192             # analysis width; height follows the frame
BAND_MIN_PCT = 0.08        # a fill band is at least 8% of the frame
BLUR_RATIO = 0.25          # band laplacian vs core laplacian
BLUR_FLOOR = 0.35          # absolute floor when the core is flat too
# A gaussian backdrop is a BIG band: a real fill covers the area the subject
# does not (measured fills are 30%+ per side). Naturally smooth content --
# a sky, a wall, a gradient bar in a test pattern -- is smooth AND small.
# ponytail: a smooth band under this floor is legal content; fills smaller
# than 18% per side are caught by the attempt gate (plan / argv), which is
# why the pre-render scan is not optional.
GAUSSIAN_MIN_PCT = 0.18
EDGE_RANGE_MAX = 8.0       # gray levels: a stretched edge column is flat
FLAT_ROWS_PCT = 0.80       # of the band must be flat to call it that
PLAIN_MEAN_STD = 3.0       # a LEGAL plain band has a constant row mean
LETTERBOX_MEAN = 12.0      # near-black rows = letterbox bars
STRIP_RATIO = 0.15         # a stretched strip has almost no row-to-row
STRIP_FLOOR = 0.5          # absolute floor when the core is flat too
STRIP_DETAIL_RATIO = 0.75  # and less detail than the frame it sits on
FILL_MAX_PCT = 0.45        # more than this much band = unreadable frame


def _rows(buf, w, h):
    return [buf[i * w:(i + 1) * w] for i in range(h)]


def _laplacian(row):
    """Horizontal |second difference|.

    A blur crushes it (smooth gradient), and a stretched edge column kills
    it too (flat across x) -- which is why a plain/flat band and a fill band
    are told apart by the row means, not by this number.
    """
    if len(row) < 3:
        return 0.0
    return sum(abs(row[i - 1] - 2 * row[i] + row[i + 1])
               for i in range(1, len(row) - 1)) / (len(row) - 2)


def _range(row):
    if not row:
        return 0.0
    return float(max(row) - min(row))


def _mean(row):
    if not row:
        return 0.0
    return sum(row) / float(len(row))


def _std(values):
    if len(values) < 2:
        return 0.0
    m = sum(values) / float(len(values))
    return (sum((v - m) ** 2 for v in values) / float(len(values) - 1)) ** .5


def _edges(band_flags):
    """Contiguous True runs anchored at row 0 and at the last row."""
    h = len(band_flags)

    def run_from(y, step):
        n, gap = 0, 0
        while 0 <= y < h and n < h:
            if band_flags[y]:
                n += 1
                gap = 0
            else:
                gap += 1
                if gap > 2:
                    break
            y += step
        return n

    top = run_from(0, 1) if band_flags[0] else 0
    bot = run_from(h - 1, -1) if band_flags[h - 1] else 0
    return top, bot


def _vdetail(rows_):
    """Mean |row[y] - row[y-1]| per row.

    A strip that was scaled out of a few source rows has ~0 here: its rows
    are copies of each other. Real content -- and any gaussian-blurred
    backdrop of real content -- keeps a visible row-to-row change, which is
    how a duplicated strip is told apart from a blurred one.
    """
    out = [0.0]
    for y in range(1, len(rows_)):
        a, b = rows_[y - 1], rows_[y]
        n = min(len(a), len(b))
        out.append(sum(abs(a[i] - b[i]) for i in range(0, n, 4))
                   / float((n + 3) // 4) if n else 0.0)
    if len(out) > 1:
        out[0] = out[1]
    return out


def _detail(rows_, lo, hi, w):
    band = rows_[lo:hi]
    return statistics.fmean(_laplacian(r) for r in band) if band else 0.0


def _classify_band(rows_, lo, hi, h, w, stats):
    """Letterbox -> plain (legal) -> edge column -> strip -> gaussian.

    Returns the violation dict, or None for a band that is NOT a fill
    (a plain top/bottom: a flat, constant band the render path may use).
    """
    band = rows_[lo:hi]
    if not band:
        return None
    flat = [r for r in band if _range(r) <= EDGE_RANGE_MAX]
    flat_frac = len(flat) / float(len(band))
    means = [_mean(r) for r in band]
    mean = sum(means) / float(len(means))
    spread = _std(means)
    pct = 100.0 * (hi - lo) / h
    if flat_frac >= FLAT_ROWS_PCT and mean <= LETTERBOX_MEAN:
        return violation(
            LETTERBOX_FILL,
            "rows %d..%d of %d are a near-black bar (%.0f%% of the frame "
            "is fill; content is short of full height)"
            % (lo, hi, h, pct))
    if spread <= PLAIN_MEAN_STD and flat_frac >= FLAT_ROWS_PCT:
        return None                        # a plain band: legal, not a fill
    if flat_frac >= FLAT_ROWS_PCT:
        return violation(
            EDGE_SAMPLED_BACKDROP,
            "rows %d..%d of %d are a stretched edge column "
            "(%.0f%% of the frame is an edge-sampled backdrop)"
            % (lo, hi, h, pct))
    vmean = statistics.fmean(_vdetail(band)) if band else 0.0
    core_vd = stats.get("core_vdetail", 0.0)
    static = vmean <= STRIP_FLOOR or vmean < STRIP_RATIO * core_vd
    band_sharp = stats.get("band_sharp", 0.0)
    core_sharp = stats.get("core_sharp", 0.0)
    detail_ratio = (band_sharp / core_sharp) if core_sharp > 0 else 1.0
    if static and detail_ratio < STRIP_DETAIL_RATIO:
        return violation(
            DUPLICATED_BLURRED_STRIP,
            "rows %d..%d of %d are a blurred strip stretched over the "
            "frame (row-to-row change %.2f vs core %.2f, detail %.2f vs "
            "core %.2f, %.0f%% of the frame): a duplicated blurred strip"
            % (lo, hi, h, vmean, core_vd, band_sharp, core_sharp, pct))
    if static:
        return None        # a still, sharp band (a graphic): legal
    if (hi - lo) / float(h) < GAUSSIAN_MIN_PCT:
        return None        # a small smooth band: natural content, not a fill
    return violation(
        GAUSSIAN_FILL,
        "rows %d..%d of %d are a smooth backdrop "
        "(detail %.2f vs core %.2f, %.0f%% of the frame is a "
        "gaussian-filled background)"
        % (lo, hi, h, band_sharp, core_sharp, pct))


def analyze(buf, w, h):
    """Frame violations + stats. buf is raw gray8, w*h bytes."""
    out = []
    if w <= 0 or h <= 0 or len(buf) < w * h:
        return [violation(UNREADABLE, "frame buffer is %dx%d (%d bytes)"
                          % (w, h, len(buf)))], {}
    rows_ = _rows(buf[:w * h], w, h)
    detail = [_laplacian(r) for r in rows_]
    vdetail = _vdetail(rows_)
    mid = slice(int(h * 0.30), int(h * 0.70))
    core_detail = statistics.median(detail[mid] or detail)
    core_vd = statistics.median(vdetail[mid] or vdetail)
    smooth = max(BLUR_RATIO * core_detail, BLUR_FLOOR)
    strip = max(STRIP_RATIO * core_vd, STRIP_FLOOR)
    flags = [d < smooth for d in detail]
    vflags = [v < strip for v in vdetail]
    s_top, s_bot = _edges(flags)
    v_top, v_bot = _edges(vflags)
    min_band = max(4, int(h * BAND_MIN_PCT))
    top = max(s_top if s_top >= min_band else 0,
              v_top if v_top >= min_band else 0)
    bot = max(s_bot if s_bot >= min_band else 0,
              v_bot if v_bot >= min_band else 0)
    if top + bot > h:                       # never let the sides meet
        bot = max(0, h - top)
    stats = {"width": w, "height": h, "core_sharp": round(core_detail, 3),
             "core_vdetail": round(core_vd, 3),
             "top_band": top, "bottom_band": bot,
             "fill_height_px": 0, "content_height_pct": 100.0}
    fill_px = 0
    for lo, hi in [(0, top) if top else (None, None),
                   (h - bot, h) if bot else (None, None)]:
        if not hi:
            continue
        stats["band_sharp"] = round(_detail(rows_, lo, hi, w), 3)
        v = _classify_band(rows_, lo, hi, h, w, stats)
        if v is not None:
            out.append(v)
            fill_px += hi - lo
    stats["fill_height_px"] = fill_px
    stats["content_height_pct"] = round(100.0 * (h - fill_px) / h, 1)
    if fill_px > h * FILL_MAX_PCT:
        out.insert(0, violation(
            FRAME_SHORT_OF_FULL_HEIGHT,
            "only %.0f%% of the frame height is real content "
            "(%d px of %d are fill: top band %d px, bottom band %d px)"
            % (stats["content_height_pct"], fill_px, h, top, bot)))
    return out, stats


def probe_size(path, ffprobe="ffprobe"):
    """(width, height) of the first video stream. Raises RuntimeError."""
    p = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x",
         str(path)],
        capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError("ffprobe failed: " + (p.stderr or "")[-200:])
    raw = (p.stdout or "").strip().splitlines()
    if not raw or "x" not in raw[0]:
        raise RuntimeError("no video stream in %s" % path)
    w, _, hh = raw[0].partition("x")
    return int(w), int(float(hh))


def gray_frame(path, ffmpeg="ffmpeg", ss=None, width=SAMPLE_W):
    """Raw gray8 sample of one frame. Returns (buf, w, h). Raises."""
    vf = "scale=%d:-2,format=gray" % width
    cmd = [ffmpeg, "-hide_banner", "-nostats", "-v", "error"]
    if ss is not None:
        cmd += ["-ss", "%.3f" % ss]
    cmd += ["-i", str(path), "-frames:v", "1", "-vf", vf, "-f", "rawvideo",
            "-pix_fmt", "gray", "-"]
    p = subprocess.run(cmd, capture_output=True, timeout=180)
    if p.returncode != 0 or not p.stdout:
        err = p.stderr or b""
        raise RuntimeError("frame extract failed: "
                           + err.decode("utf-8", "replace")[-200:])
    if len(p.stdout) % width:
        raise RuntimeError("frame extract returned %d bytes for width %d"
                           % (len(p.stdout), width))
    h = len(p.stdout) // width
    return p.stdout, width, h


def is_image(path):
    return os.path.splitext(str(path))[1].lower() in _IMAGE_EXT


def scan_frame(path, expect_width=None, expect_height=None,
               ffmpeg="ffmpeg", ffprobe="ffprobe"):
    """Frame-level violations for a rendered file (attempt already landed).

    Fails a frame that is short of full height, and a frame whose bands are
    a fill: edge-sampled backdrop, gaussian-filled background, duplicated
    blurred strip, blurred mask or letterbox bars.
    """
    try:
        pw, ph = probe_size(path, ffprobe)
    except (OSError, ValueError, subprocess.TimeoutExpired, RuntimeError) as exc:
        return [violation(UNREADABLE, "%s: %s" % (path, exc))], {}
    out = []
    if expect_height and ph < int(expect_height):
        out.append(violation(
            FRAME_SHORT_OF_FULL_HEIGHT,
            "frame height %d px is short of the required %d px (fill/"
            "letterbox instead of a full-height crop-in)" % (ph, expect_height)))
    try:
        buf, w, h = gray_frame(path, ffmpeg,
                               ss=None if is_image(path) else 0.5)
    except (OSError, ValueError, subprocess.TimeoutExpired, RuntimeError) as exc:
        return out + [violation(UNREADABLE, "%s: %s" % (path, exc))], \
            {"width": pw, "height": ph}
    band_violations, stats = analyze(buf, w, h)
    out.extend(band_violations)
    if expect_height and stats.get("content_height_pct") is not None:
        content_px = ph * stats["content_height_pct"] / 100.0
        if content_px + 1 < float(expect_height) and not any(
                v["code"] == FRAME_SHORT_OF_FULL_HEIGHT for v in out):
            out.append(violation(
                FRAME_SHORT_OF_FULL_HEIGHT,
                "content covers %.0f%% of the frame (%d px of %d) because "
                "of a fill; the frame is short of full height"
                % (stats["content_height_pct"], content_px, ph)))
    stats.update({"width": pw, "height": ph})
    return out, stats


def message(code, detail):
    """The actionable refusal text: violation named, repair named."""
    return "%s: %s; %s" % (code, detail, REPAIR)
