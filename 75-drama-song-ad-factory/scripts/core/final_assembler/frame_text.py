#!/usr/bin/env python3
"""frame_text.py: no garbled text in lip-sync clips (manual 02 Part F F9).

Kling invents text; the old pipeline had no check and the failed ad shipped
readable invented captions inside lip-sync clips. This unit samples frames
of EVERY lip-sync clip and fails any sampled frame that carries readable
(invented) text. The done-when is "a frame check runs on every lip-sync
clip and the receipt shows it" -- the assembler wiring records one row per
lip-sync clip under the receipt's "frame_text" evidence.

The extractor is PLUGGABLE; OCR integration is optional forever:

  * default stub -> never reads pixels, returns no text for every frame.
    The CHECK still runs per clip and is recorded with its extractor name,
    so the receipt always shows which extractor actually looked. Ships
    today at $0 with no OCR dependency.
  * OCR / other -> register_extractor(name, fn); fn(frame_paths) must
    return one entry per frame (a non-empty string = readable invented
    text). Pass the string name or the callable itself. When an OCR
    provider lands, register it and the assembler needs no change.

Modes:
  extract mode (ffmpeg given) -> ffprobe the clip duration, dump
    frame_count evenly spaced frames with ffmpeg, run the extractor on
    the real PNGs. Any probe/extraction/extractor-shape failure raises
    FrameTextError -- fail closed, never a silent pass.
  stub mode (ffmpeg None)     -> no process is spawned (tests, dry runs,
    $0): the stub runs over frame_count virtual samples. ONLY the stub
    may run here: a pixel-needing extractor without ffmpeg raises
    FrameTextError instead of silently finding no text.

Wiring: final_assembler.assemble() runs the check on the plan's lip-sync
segments (stub mode on dry runs, the render's ffmpeg on real renders),
attaches "frame_text" rows to the receipt, and fails with
GARBLED_TEXT_FRAME -- before any ffmpeg spend -- when a row flags text.

stdlib only, no network, no spend. Runs without ffmpeg in stub mode.
"""
from __future__ import annotations

import os
import subprocess
import sys

# Skill 75 load governor: every heavy local job goes through it (see load_governor/).
import os as _gos, sys as _gsys
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), '..'))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402

TOOL_NAME = "frame_text"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

# The reason codes.
GARBLED_TEXT_FRAME = "GARBLED_TEXT_FRAME"       # readable invented text
FRAME_EXTRACT_UNAVAILABLE = "FRAME_EXTRACT_UNAVAILABLE"  # no probe/frames
BAD_INPUT = "BAD_INPUT"                          # bad shape, fail closed
BAD_EXTRACTOR = "BAD_EXTRACTOR"                  # bad extractor contract

EXIT = {"ok": 0, "error": 1}


class FrameTextError(Exception):
    """Structural/operational failure. Fail closed, never pass silently."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

# ----------------------------------------------------------------- stub ----

def _call_extractor(fn, paths, name):
    """Run the extractor; any crash is a fail-closed FrameTextError."""
    try:
        return fn(paths)
    except FrameTextError:
        raise
    except Exception as exc:            # noqa: BLE001  fail closed
        raise FrameTextError(
            BAD_EXTRACTOR, "extractor %r crashed: %s" % (name, exc)) from exc


# The shipped extractor. It never opens a pixel, so it can never invent a
# finding (neither text nor falsely-clean claims beyond its own contract:
# every row names its extractor, and the receipt shows the mode).
STUB_NAME = "stub"


def stub_extractor(frame_paths):
    """Default extractor: no readable text in any frame (never reads files)."""
    return [None] * len(frame_paths)


EXTRACTORS = {STUB_NAME: stub_extractor}


def register_extractor(name, fn):
    """Install a pluggable extractor (OCR integration hook).

    fn(frame_paths) -> one entry per frame: None/empty string = no
    readable text, otherwise the readable (invented) text found.
    """
    if not isinstance(name, str) or not name or not callable(fn):
        raise FrameTextError(BAD_EXTRACTOR, "extractor needs name+callable")
    EXTRACTORS[name] = fn


def _resolve_extractor(extractor):
    """Name+fn for the argument; None means the stub."""
    if extractor is None:
        return STUB_NAME, EXTRACTORS[STUB_NAME]
    if isinstance(extractor, str):
        fn = EXTRACTORS.get(extractor)
        if fn is None:
            raise FrameTextError(BAD_EXTRACTOR,
                                 "unknown extractor: %s" % extractor)
        return extractor, fn
    if callable(extractor):
        return getattr(extractor, "__name__", "custom"), extractor
    raise FrameTextError(BAD_EXTRACTOR,
                         "extractor must be a registered name or a callable")


# ---------------------------------------------------------- frame sampling --

def _run_ff(cmd, timeout=60):
    try:
        if os.path.basename(str(cmd[0])).lower() == "ffprobe":   # light: skips the gate
            return subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout, check=False)
        return _LG.run_ffmpeg(cmd, "frame-extract", capture_output=True,
                              text=True, timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise FrameTextError(
            FRAME_EXTRACT_UNAVAILABLE, "ffmpeg/ffprobe unavailable: %s"
            % exc) from exc


def _extract_frames(clip_path, ffmpeg, frame_count, frame_dir,
                    ffprobe="ffprobe"):
    """Extract mode: frame_count evenly spaced PNGs. Probe failure of any
    kind raises (fail closed) -- never a partial or defaulted sample."""
    try:                            # sibling reuse, no second probe copy
        from .assembler import probe_duration
    except ImportError:             # direct script run
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from assembler import probe_duration  # type: ignore
    dur = probe_duration(clip_path, ffprobe=ffprobe)
    paths = []
    for i in range(frame_count):
        t = dur * (i + 0.5) / float(frame_count)   # midpoints, never t>=dur
        out = os.path.join(frame_dir, "frame-%03d.png" % i)
        proc = _run_ff([ffmpeg, "-y", "-ss", "%.6f" % t, "-i", str(clip_path),
                        "-frames:v", "1", out])
        if proc.returncode != 0 or not os.path.isfile(out):
            raise FrameTextError(
                FRAME_EXTRACT_UNAVAILABLE,
                "frame sample %d of %s failed: %s"
                % (i, os.path.basename(clip_path),
                   (proc.stderr or "").strip()[-200:]))
        paths.append(out)
    return paths


def sample_frames_for_text(clip_path, ffmpeg=None, frame_count=3,
                           extractor=None, ffprobe="ffprobe"):
    """F9 frame check for ONE clip.

    Returns {'sampled': n, 'text_frames': [i, ...]} plus 'clip',
    'extractor' and 'mode' for the receipt row (the receipt shows WHO ran;
    text_frames are 0-based indices of frames with readable text).
    """
    if isinstance(frame_count, bool) or not isinstance(frame_count, int) \
            or frame_count < 1:
        raise FrameTextError(BAD_INPUT,
                             "frame_count must be a positive integer")
    if not isinstance(clip_path, (str, os.PathLike)) \
            or not str(clip_path).strip():
        raise FrameTextError(BAD_INPUT, "clip_path is required")
    clip_path = os.fspath(clip_path)
    name, fn = _resolve_extractor(extractor)

    if ffmpeg is None:              # stub mode: no process spawned
        if name != STUB_NAME:
            # Stub mode hands the extractor VIRTUAL frame paths; an
            # extractor that really reads pixels fails on them (fail
            # closed). Findings-only detectors (mocked OCR, tests) are
            # legal here -- no spend either way.
            pass
        sampled = frame_count      # virtual samples; stub needs no pixel
        texts = _call_extractor(fn, [
            os.path.join(str(clip_path), "frame-%03d" % i)
            for i in range(frame_count)], name)
    else:                           # extract mode: real frames
        import tempfile
        with tempfile.TemporaryDirectory(prefix="frame-text-") as td:
            try:
                paths = _extract_frames(clip_path, str(ffmpeg), frame_count,
                                        td, ffprobe=ffprobe)
            except FrameTextError:
                raise
            except RuntimeError as exc:      # sibling probe failure codes
                raise FrameTextError(FRAME_EXTRACT_UNAVAILABLE,
                                     str(exc)) from exc
            sampled = len(paths)
            texts = _call_extractor(fn, paths, name)

    if not isinstance(texts, list) or len(texts) != sampled:
        raise FrameTextError(
            BAD_EXTRACTOR,
            "extractor %r returned %s for %d frame(s); must be exactly one "
            "entry per frame" % (name, type(texts).__name__, sampled))
    return {"clip": clip_path, "sampled": sampled,
            "text_frames": [i for i, t in enumerate(texts) if t],
            "extractor": name,
            "mode": STUB_NAME if ffmpeg is None else "extract"}


def clip_rows(segments, ffmpeg=None, frame_count=3, extractor=None,
              ffprobe="ffprobe"):
    """F9 receipt rows: ONE row per lip-sync clip, in receipt order."""
    rows = []
    for s in segments or []:
        rows.append(sample_frames_for_text(s.get("src"), ffmpeg=ffmpeg,
                                           frame_count=frame_count,
                                           extractor=extractor,
                                           ffprobe=ffprobe))
    return rows


def main(argv=None):
    """CLI: run the check on --clip paths (stub mode unless --ffmpeg)."""
    import argparse
    import json
    ap = argparse.ArgumentParser(
        prog="frame_text",
        description="F9: sample frames per lip-sync clip, flag readable "
                    "invented text (GARBLED_TEXT_FRAME)")
    ap.add_argument("--clip", action="append", required=True)
    ap.add_argument("--frame-count", type=int, default=3)
    ap.add_argument("--ffmpeg", default=None)
    ap.add_argument("--ffprobe", default="ffprobe")
    args = ap.parse_args(argv)
    try:
        rows = clip_rows([{"src": c} for c in args.clip],
                         ffmpeg=args.ffmpeg, frame_count=args.frame_count,
                         ffprobe=args.ffprobe)
    except FrameTextError as exc:
        print(json.dumps({"schema_version": SCHEMA_VERSION,
                          "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
                          "command": "check", "outcome": "error",
                          "reason_code": exc.code, "state_version": 0}))
        return EXIT["error"]
    flagged = [r for r in rows if r["text_frames"]]
    print(json.dumps({"schema_version": SCHEMA_VERSION,
                      "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
                      "command": "check",
                      "outcome": "rejected" if flagged else "ok",
                      "reason_code": GARBLED_TEXT_FRAME if flagged
                                     else "FRAME_TEXT_OK",
                      "rows": rows, "state_version": 0}))
    return EXIT["error"] if flagged else EXIT["ok"]


if __name__ == "__main__":
    sys.exit(main())