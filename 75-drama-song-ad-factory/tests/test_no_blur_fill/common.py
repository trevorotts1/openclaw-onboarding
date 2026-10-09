"""Shared helpers for the DEL-14 no-blur-fill suite (stdlib only).

The suite feeds a blur-fill render attempt through the pipeline and proves it
fails red, proves the crop-in path passes green, and asserts the refusal gates
fire. Everything here is local: tiny synthetic clips on disk, no network, no
paid provider.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CORE = os.path.join(SKILL_ROOT, "scripts", "core")
for _sub in ("", "video_still_fill"):
    _p = os.path.join(CORE, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import qc_gate  # noqa: E402
import video_still_fill  # noqa: E402  (package)
from video_still_fill import still_fill as SF  # noqa: E402

RUN = "pkg05u3"
STAGE = "final_edit"
MAKER = "assembler-maker"
REVIEWER = "independent-qc-checker"
RECORD_ID = "final:no_blur_fill:x"

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
HAVE_MEDIA = bool(FFMPEG and FFPROBE)


def have_media():
    """Render tests need ffmpeg + ffprobe; skip loudly when absent."""
    return HAVE_MEDIA


def qc_record(summary, verdict="PASS", check="no_blur_fill",
              check_id=RECORD_ID, run_id=RUN, stage=STAGE):
    """One schema-valid QC verdict record (qc-schema v1.0.0 shape)."""
    return {"schema_version": "1.0.0", "check_id": check_id,
            "run_id": run_id, "stage": stage, "check": check,
            "verdict": verdict,
            "evidence": {"summary": summary},
            "checker_version": "1.0.0",
            "reviewer": {"identity": REVIEWER, "session": "s1",
                         "authority": "qc"}}


def gate(records, required=("no_blur_fill",)):
    """Run the independent QC gate over the records."""
    makers = {r["check_id"]: MAKER for r in records}
    return qc_gate.evaluate(RUN, STAGE, list(records), makers, list(required))


def codes(res):
    return {f["code"] for f in res.get("failures", [])}


def make_source(path, w=720, h=1280, seconds=0.4):
    """Tiny synthetic 9:16-ish source clip (testsrc2, no audio)."""
    argv = [FFMPEG, "-y", "-f", "lavfi",
            "-i", "testsrc2=size=%dx%d:rate=24:duration=%s" % (w, h, seconds),
            "-pix_fmt", "yuv420p", str(path)]
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(path):
        raise RuntimeError("fixture render failed: %s"
                           % (proc.stderr or "")[-400:])
    return path


def render_blur_fill_attempt(source, output):
    """The DEL-14 forbidden path, run directly on purpose (never via the
    module): full height faked with a gaussian-blurred band over the top of a
    padded frame — the gblur + mask chain from the spot-2 incident, trimmed to
    what ffmpeg needs here.

    Returns the CompletedProcess; the caller proves the pipeline refuses it.
    """
    fc = ("[0:v]scale=1080:1440,split[bg][fg];"
          "[bg]gblur=sigma=30,crop=1080:480:0:0[top];"
          "[fg]pad=1080:1920:0:240:black,setsar=1[base];"
          "[base][top]overlay=0:0,format=yuv420p[out]")
    argv = [FFMPEG, "-y", "-i", str(source), "-filter_complex", fc,
            "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "faststart", str(output)]
    return subprocess.run(argv, capture_output=True, text=True)


def render_rotation_fill_attempt(source, output, degrees=90):
    """The other forbidden path: sideways frames plus a rotation tag, so a
    PLAYER stands them up to full height while the stored frames are not.

    Two steps on purpose: ffmpeg drops the display-matrix side data across a
    re-encode, so the tag is stamped on a remux, exactly like a hand tool
    would. Returns the last CompletedProcess.
    """
    landscape = output + ".landscape.mp4"
    proc = subprocess.run(
        [FFMPEG, "-y", "-i", str(source),
         "-vf", "transpose=1,scale=1920:1080,setsar=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(landscape)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        return proc
    return subprocess.run(
        [FFMPEG, "-y", "-display_rotation", str(int(degrees)),
         "-i", str(landscape), "-c", "copy", str(output)],
        capture_output=True, text=True)


def add_display_rotation(path, output, degrees=90):
    """Remux path with a display-matrix rotation tag stamped on it."""
    return subprocess.run(
        [FFMPEG, "-y", "-display_rotation", str(int(degrees)),
         "-i", str(path), "-c", "copy", str(output)],
        capture_output=True, text=True)


# the render attempts the suite feeds through the build_argv refusal:
# (label, source size, extra build_argv kwargs) — none may ever come back as
# an argv carrying a fill.
BUILD_ARGV_CASES = (
    ("landscape-still-into-9x16", (1920, 1080), {}),
    ("square-still-into-9x16", (1024, 1024), {}),
    ("tall-720x1280", (720, 1280), {}),
    ("off-centre-subject", (720, 1280), {"center_x": 0.28}),
)

#: tokens that spell a blur fill inside an ffmpeg command line. The incident
#: chain carried gblur + a mask overlay; every variant is listed.
FILL_TOKENS_IN_ARGV = ("gblur", "boxblur", "avgblur", "smartblur",
                       "alphamerge", "pad=", "blur=")
