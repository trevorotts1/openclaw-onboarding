"""qc_no_blur.crop_relip: the crop-in re-lip-sync recovery path (DEL-14).

The ONLY path to full height is crop-in of the source frame. Never stretch,
never letterbox, never duplicate-and-blur the edge, never gaussian-fill the
background, never a blurred mask.

When the assembler or the quality check refuses a fill, regenerate() rebuilds
the clip from the SOURCE frame with a crop-in (content aspect -> target 9:16,
centered), re-encodes it, verifies the result carries no fill and is full
height, and hands back a receipt the re-lip-sync step runs on. The flow
recovers instead of filling.

Stdlib only; shells to ffmpeg/ffprobe. No spend, no provider call, no
network: the paid lip-sync job is dispatched by the caller on the receipt's
``next_step`` path.
"""
from __future__ import annotations

import os
import subprocess

try:                                    # package import (house style)
    from . import detect
except ImportError:                     # direct-script fallback
    import detect  # type: ignore

TOOL = "qc_no_blur.crop_relip"
SCHEMA = "blackceo.crop-relip-receipt/v1"

BIASES = ("center", "top", "upper_third")
BIAS_NUDGE = 0.5        # 0 = centered, 1 = as far up as the crop allows
DEFAULT_OUT_W = 1080
DEFAULT_OUT_H = 1920
DEFAULT_FPS = 30

# Never stretch, never letterbox: no pad=, no blur, no duplicate.
CROP_IN_VF = ("crop={cw}:{ch}:{ox}:{oy},scale={w}:{h}:"
              "flags=lanczos,setsar=1")


class CropRelipError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def crop_box(src_w, src_h, out_w, out_h, bias="center"):
    """The largest centered crop of the source at the target aspect.

    Full height is reached by cropping WIDTH IN (a 16:9 source becomes a
    vertical frame by losing its sides, never by padding or blurring). The
    same box is used the other way when the source is taller than the
    target: the width is kept and the height is cropped in.
    """
    if not all(isinstance(v, int) and v > 0
               for v in (src_w, src_h, out_w, out_h)):
        raise CropRelipError("BAD_INPUT",
                             "widths/heights must be positive integers")
    if bias not in BIASES:
        raise CropRelipError("BAD_BIAS",
                             "bias must be one of %s" % (", ".join(BIASES),))
    aspect = float(out_w) / float(out_h)
    if src_w / float(src_h) > aspect:      # source wider: crop width in
        ch = src_h
        cw = min(src_w, max(2, int(round(ch * aspect))))
    else:                                   # source taller: crop height in
        cw = src_w
        ch = min(src_h, max(2, int(round(cw / aspect))))
    if bias == "top":
        oy = 0
    elif bias == "upper_third":
        oy = int(round((src_h - ch) * BIAS_NUDGE / 3.0))
    else:
        oy = (src_h - ch) // 2
    oy = max(0, min(oy, src_h - ch))
    ox = max(0, (src_w - cw) // 2)
    return cw, ch, ox, oy


def crop_in_argv(src, out, out_w=DEFAULT_OUT_W, out_h=DEFAULT_OUT_H,
                 bias="center", fps=None, ffmpeg="ffmpeg"):
    """ffmpeg argv: crop-in the source frame to a full-height target."""
    src_w, src_h = detect.probe_size(src)
    cw, ch, ox, oy = crop_box(src_w, src_h, out_w, out_h, bias)
    vf = CROP_IN_VF.format(cw=cw, ch=ch, ox=ox, oy=oy, w=out_w, h=out_h)
    cmd = [ffmpeg, "-y", "-hide_banner", "-nostats", "-v", "error",
           "-i", str(src), "-vf", vf, "-map", "0:v:0"]
    if fps:
        cmd += ["-r", "%g" % float(fps)]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(out)]
    return cmd, {"source": [src_w, src_h], "crop": [cw, ch, ox, oy],
                 "output": [out_w, out_h], "vf": vf}


def regenerate(src, out, out_w=DEFAULT_OUT_W, out_h=DEFAULT_OUT_H,
               bias="center", fps=None, ffmpeg="ffmpeg", ffprobe="ffprobe",
               timeout=600):
    """Crop-in re-lip-sync path: rebuild the clip from the SOURCE frame.

    Returns a receipt dict (schema blackceo.crop-relip-receipt/v1) with the
    argv, the crop box, the frame verification and the ``next_step`` the
    caller runs: re-lip-sync the regenerated clip (never a fill). Raises
    CropRelipError when the source is unusable or the result still carries
    a fill.
    """
    if not os.path.isfile(str(src)):
        raise CropRelipError("MISSING_SOURCE",
                             "source clip not found: %s" % src)
    argv, box = crop_in_argv(src, out, out_w, out_h, bias, fps, ffmpeg)
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CropRelipError("CROP_IN_FAILED",
                             "ffmpeg crop-in failed: %s" % exc) from exc
    if p.returncode != 0 or not os.path.isfile(str(out)):
        raise CropRelipError(
            "CROP_IN_FAILED",
            "ffmpeg exit %s: %s" % (p.returncode, (p.stderr or "")[-300:]))
    violations, stats = detect.scan_frame(out, expect_width=out_w,
                                          expect_height=out_h,
                                          ffmpeg=ffmpeg, ffprobe=ffprobe)
    if violations:
        raise CropRelipError(
            "CROP_IN_STILL_FILLED",
            "; ".join("%s: %s" % (v["code"], v["detail"])
                      for v in violations))
    try:
        got_w, got_h = detect.probe_size(out, ffprobe)
    except (OSError, ValueError, subprocess.TimeoutExpired, RuntimeError) as exc:
        raise CropRelipError("CROP_IN_UNVERIFIED",
                             "ffprobe failed on the regenerated clip: %s"
                             % exc) from exc
    if (got_w, got_h) != (int(out_w), int(out_h)):
        raise CropRelipError(
            "CROP_IN_UNVERIFIED",
            "regenerated clip is %dx%d, expected %dx%d"
            % (got_w, got_h, out_w, out_h))
    return {"schema_version": SCHEMA, "tool": TOOL, "outcome": "ok",
            "reason_code": "CROP_IN_REGENERATED",
            "source": str(src), "output": str(out), "box": box,
            "frame": stats,
            "next_step": ("re-lip-sync the regenerated clip "
                          "(qc_no_blur is satisfied: full-height crop-in, "
                          "no fill)")}
