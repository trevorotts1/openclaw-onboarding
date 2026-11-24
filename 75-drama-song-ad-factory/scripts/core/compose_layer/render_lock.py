"""Render rules: one master, one intermediate, fixed encode profiles
(row N-59, sections 3D.2 and 3D.5).

- One full-master render at a time per box. A second master never starts
  beside the first; piece renders of the same master may run side by side as
  a fresh memory reading allows.
- The intermediate master is written once; Clean and Captioned are both
  made from it, never three encodes of the same final.
- Hardware encoder on a Mac (``h264_videotoolbox``), software on Linux
  (``libx264``). A Mac whose hardware encoder is missing falls back to
  ``libx264``; both deliverables keep the same frame rate and pixel format.

Stdlib only. The lock is advisory across Skill 75 processes on one box.
"""
from __future__ import annotations

import contextlib
import fcntl
import os
import subprocess
import time

TOOL_NAME = "compose_render_lock"
TOOL_VERSION = "1.0.0"

MASTER_FPS = 24               # native rate of H3 clips (3D.2)
PIX_FMT = "yuv420p"
AUDIO_RATE = 48000

HW_ENCODER = "h264_videotoolbox"
SW_ENCODER = "libx264"

MASTER_BUSY = "MASTER_RENDER_BUSY"
SECOND_INTERMEDIATE = "SECOND_INTERMEDIATE_MASTER"
DELIVERABLE_SOURCE_MISMATCH = "DELIVERABLE_SOURCE_MISMATCH"
NO_ENCODER = "NO_ENCODER_AVAILABLE"

INTERMEDIATE_NAME = "master_intermediate.mp4"


class RenderLockError(RuntimeError):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def hardware_encoder_available(ffmpeg="ffmpeg"):
    """True when this ffmpeg lists the Mac hardware H.264 encoder."""
    try:
        p = subprocess.run([ffmpeg, "-hide_banner", "-encoders"],
                           capture_output=True, text=True, timeout=20,
                           check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return HW_ENCODER in p.stdout


def encoder_for(platform=None, hardware=None, ffmpeg="ffmpeg"):
    """macOS -> hardware when present; Linux -> software (3D.2)."""
    name = platform or ("darwin" if os.uname().sysname == "Darwin" else "linux")
    if name == "darwin":
        if hardware is None:
            hardware = hardware_encoder_available(ffmpeg)
        return HW_ENCODER if hardware else SW_ENCODER
    return SW_ENCODER


def video_args(encoder, quality=18, preset="medium"):
    """Encoder arguments; both profiles share fps and pixel format."""
    if encoder == HW_ENCODER:
        # VideoToolbox has no CRF scale; q:v is its quality control.
        args = ["-c:v", encoder, "-q:v", str(min(100, max(1, 100 - quality * 4)))]
    elif encoder == SW_ENCODER:
        args = ["-c:v", encoder, "-crf", str(quality), "-preset", preset]
    else:
        raise RenderLockError(NO_ENCODER, "unsupported encoder %r" % encoder)
    return args + ["-r", str(MASTER_FPS), "-pix_fmt", PIX_FMT]


def encode_argv(source, output, encoder, quality=18, audio="copy"):
    """One deliverable encode from the intermediate master."""
    return ["ffmpeg", "-y", "-i", source, *video_args(encoder, quality),
            "-c:a", audio, "-ar", str(AUDIO_RATE), output]


def one_intermediate(paths):
    """Exactly one intermediate master; refuse a second (3D.5)."""
    paths = [p for p in paths if p]
    if len(paths) != 1:
        raise RenderLockError(SECOND_INTERMEDIATE,
                              "expected one intermediate master, got %d" % len(paths))
    return paths[0]


def plan_deliverables(intermediate, clean_out, captioned_out, encoder,
                      quality=18, caption_overlay=None):
    """Clean and Captioned, both recorded against the SAME source file.

    A Captioned deliverable exists only when a caption overlay is given: it
    is the same intermediate with the one overlay stream burned in a single
    pass (row N-49). Without an overlay there is no Captioned file and none
    is claimed. The import is local because ``captions`` imports this
    module for the shared encode profile.
    """
    source = one_intermediate([intermediate])
    rows = [
        {"name": "clean", "source": source, "output": clean_out,
         "argv": encode_argv(source, clean_out, encoder, quality)},
    ]
    if caption_overlay:
        from .captions import burn_argv
        rows.append({"name": "captioned", "source": source,
                     "output": captioned_out,
                     "argv": burn_argv(source, caption_overlay, captioned_out,
                                       encoder, quality)})
    return {"intermediate": source, "fps": MASTER_FPS, "pix_fmt": PIX_FMT,
            "encoder": encoder, "captioned": bool(caption_overlay),
            "deliverables": rows}


def assert_same_source(deliverables):
    sources = {row.get("source") for row in deliverables}
    if len(sources) != 1:
        raise RenderLockError(DELIVERABLE_SOURCE_MISMATCH,
                              "Clean and Captioned must come from one master")
    return sources.pop()


@contextlib.contextmanager
def master_lock(box_dir, run_id, wait_s=0.0, poll_s=2.0):
    """One full-master render at a time per box (3D.5).

    ``wait_s`` of 0 refuses at once; a longer wait polls in one place.
    Piece renders do not take this lock.
    """
    os.makedirs(box_dir, exist_ok=True)
    path = os.path.join(box_dir, "compose-master.lock")
    handle = open(path, "a+", encoding="utf-8")
    deadline = time.time() + max(0.0, wait_s)
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() >= deadline:
                    raise RenderLockError(MASTER_BUSY,
                                          "another full-master render is running")
                time.sleep(poll_s)
        handle.seek(0)
        handle.truncate()
        handle.write("%s\n" % run_id)
        handle.flush()
        try:
            yield {"lock": path, "run_id": str(run_id)}
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()
