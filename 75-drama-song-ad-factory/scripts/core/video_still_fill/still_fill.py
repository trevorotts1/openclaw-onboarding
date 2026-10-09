#!/usr/bin/env python3
"""Full height for a 9:16 master: crop-in of the source frame, never a blur fill.

DEL-14 (Trevor order 2026-10-09, mass swarm item C via relita): a vertical
delivery frame that is short of full height is repaired by scaling the source
up until it covers 9:16 and cropping the overflow. It is NEVER repaired by
letterboxing, by padding with an edge-sampled or gaussian-blurred backdrop, by
a duplicated blurred strip, or by stretching an edge. The lip-sync subject
stays full height because the crop is centred on the frame (subject-centre
offset via --center-x 0..1).

The assembler-side refusal gate is qc_gate: a PASS record for the no_blur_fill
check whose evidence names a blur fill is refused as FILL_CLAIM_MEASURED
(fill_claim below is the shared scanner, so the render path and the gate agree).

Heavy renders go through load_governor like every other ffmpeg call site.
Probe uses ffprobe only (same as final_assembler.probe_duration).

CLI:
  python3 video_still_fill.py render   --source <clip> --output <mp4> \
      [--center-x 0.5] [--fps N]
  python3 video_still_fill.py inspect  --output <mp4>
  python3 video_still_fill.py scan-core

Exit codes: ok=0, error=1, rejected=5 (blur fill found in core, or the
rendered output is not a clean full-height crop-in).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

# Skill 75 load governor: every heavy local job goes through it (see load_governor/).
import os as _gos, sys as _gsys
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), ".."))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402

TOOL_NAME = "video_still_fill"
TOOL_VERSION = "1.0.0"

DEFAULT_WIDTH, DEFAULT_HEIGHT = 1080, 1920          # 9:16, full height

#: the only path this module is allowed to take.
NO_FILL = "crop-in"
#: every fill this module refuses, named for the error text.
FILL_METHODS = ("letterbox-pad", "edge-sampled-blur", "gaussian-blur-backdrop",
                "duplicated-blur-strip", "stretch")

EXIT = {"ok": 0, "error": 1, "rejected": 5}

# DEL-14 scan surface: the fill attempt in the wild was an ffmpeg gblur +
# alphamerge mask chain (qualification lane spot2 build.py: gblur=sigma=30
# over a mask). Any of these tokens in a shipped core script is a blur fill
# the build system must refuse to run.
BLUR_MARKERS = ("gblur", "boxblur", "avgblur", "alphamerge",
                "blur_fill", "blur-fill", "blurfill")

#: the two scanners spell the marker tokens themselves (the list above and
#: qc_gate.fill_claim); exempt by name so the scanner never trips its own
#: source — the same self-exemption qc-operator-path-leak.sh uses.
SCANNER_FILES = frozenset({"still_fill.py", "qc_gate.py"})

# DEL-14 (Trevor order 2026-10-09): blur fill is never used. Full height is
# reached by crop-in of the source frame only. This gate cannot render or
# inspect pixels (stdlib only), so it refuses the CLAIM in evidence text the
# same way G3 refuses an unmeasured sung claim: a PASS record for the
# no_blur_fill check whose evidence names a blur fill can never pass.
# ponytail: negation-aware string matching on evidence.summary (qc-schema
# v1.0.0 evidence allows summary+refs only); move to a schema evidence key
# (e.g. fill_method) when qc-schema names one.
FILL_CLAIM_DETECTOR = "fill_claim"
_FILL_TOKEN = (
    r"(?:blur[-_\s]?fill|blurfill"
    r"|blur(?:red)?\s+(?:fill|backdrop|background|mask|strip|edge|band)"
    r"|fill(?:ed)?\s+with\s+a\s+blur|gaussian[-_\s]?fill"
    r"|gblur|boxblur|avgblur|smartblur|alphamerge)")
#: a negator up to 40 chars ahead of the token (and coordinated tokens after
#: it: "never a blur fill or blurred mask") documents the refusal, it is not
#: a fill claim. The span stops at sentence punctuation so "no letterbox;
#: gblur sigma=30" still claims.
_FILL_NEGATED = re.compile(
    r"\b(?:no|not|never|without|zero|free\s+of|absent|lacks?"
    r"|avoid(?:s|ed)?)\b[^.!?\n;]{0,40}?"
    r"(?:\s+(?:or\s+|and\s+|nor\s+)?" + _FILL_TOKEN + r")+",
    re.I)
#: the same refusal spelled the other way round: "blur fill is never used".
_FILL_REPEALED = re.compile(
    _FILL_TOKEN + r"[^.!?\n;]{0,24}\s+(?:is\s+|are\s+|was\s+|were\s+|be\s+)?"
    r"(?:never|not|no\b|none\b|without|absent)", re.I)
_FILL_CLAIM = re.compile(_FILL_TOKEN, re.I)


def fill_claim(summary):
    """True when evidence text asserts a blur fill / blurred mask backdrop."""
    if not isinstance(summary, str):
        return False
    text = _FILL_NEGATED.sub(" ", summary)
    text = _FILL_REPEALED.sub(" ", text)
    return bool(_FILL_CLAIM.search(text))


def classify(source_w, source_h, target_w=DEFAULT_WIDTH,
             target_h=DEFAULT_HEIGHT):
    """How the source reaches the target frame: uniform zoom + crop, no fill.

    zoom is the single scale factor that makes the source cover the target on
    both axes (never below 1.0 for a source that already covers). The overflow
    is cropped, never padded away and never stretched.
    """
    sw, sh = int(source_w), int(source_h)
    tw, th = int(target_w), int(target_h)
    if sw <= 0 or sh <= 0 or tw <= 0 or th <= 0:
        raise ValueError("dimensions must be positive: %sx%s -> %sx%s"
                         % (sw, sh, tw, th))
    zoom = max(float(tw) / sw, float(th) / sh)
    return {"tool": TOOL_NAME, "tool_version": TOOL_VERSION,
            "fit": NO_FILL, "fill": None,
            "source": [sw, sh], "target": [tw, th],
            "zoom": zoom, "covers": True, "never": list(FILL_METHODS)}


def plan_fill(source_w, source_h, target_w=DEFAULT_WIDTH,
              target_h=DEFAULT_HEIGHT):
    """Plan-shaped name of classify(); the assembler wires this one."""
    return classify(source_w, source_h, target_w, target_h)


def frame_size(path, ffprobe="ffprobe", timeout=60):
    """First video stream width/height of path, via ffprobe."""
    argv = [ffprobe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x",
            str(path)]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("PROBE_FAILED: %s: %s" % (path, exc))
    out = (proc.stdout or "").strip().splitlines()
    if proc.returncode != 0 or not out:
        raise RuntimeError("PROBE_FAILED: %s: %s"
                           % (path, (proc.stderr or "").strip()[:200]))
    try:
        w_s, h_s = out[0].split("x")[:2]
        w, h = int(w_s), int(h_s)
    except (ValueError, IndexError):
        raise RuntimeError("PROBE_FAILED: unparseable size %r (%s)"
                           % (out[0], path))
    if w <= 0 or h <= 0:
        raise RuntimeError("PROBE_FAILED: %sx%s (%s)" % (w, h, path))
    return w, h


def build_argv(source, output, source_w, source_h, center_x=0.5, fps=None,
               target_w=DEFAULT_WIDTH, target_h=DEFAULT_HEIGHT):
    """ffmpeg argv: uniform cover-scale, then a centred crop. Never a fill.

    uniform zoom to cover the target, crop w:h at (x, y) where x follows
    --center-x (the lip-sync subject) and y is centred, so a short-of-height
    source reaches full height by showing LESS width, never by inventing
    picture above and below it. No pad=, no blur, no forced w:h.
    """
    cx = float(center_x)
    if not (0.0 <= cx <= 1.0):
        raise ValueError("center-x must be within 0..1: %r" % center_x)
    plan = classify(source_w, source_h, target_w, target_h)
    tw, th = int(plan["target"][0]), int(plan["target"][1])
    zw = max(tw, int(round(plan["source"][0] * plan["zoom"])))
    zh = max(th, int(round(plan["source"][1] * plan["zoom"])))
    x = int(round((zw - tw) * cx))
    y = (zh - th) // 2
    filters = ["scale=%d:%d" % (zw, zh),
               "crop=%d:%d:%d:%d" % (tw, th, x, y),
               "setsar=1"]
    args = ["-y", "-i", str(source)]
    if fps:
        args += ["-r", "%g" % float(fps)]
    args += ["-vf", ",".join(filters),
             "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-movflags", "faststart", str(output)]
    return _LG.ffmpeg_argv(args, threads=2)


def render(source, output, center_x=0.5, fps=None, ffprobe="ffprobe",
           job="still-fill-render", timeout=300):
    """Probe the source, then run the crop-in render through the governor."""
    src_w, src_h = frame_size(source, ffprobe=ffprobe)
    plan = classify(src_w, src_h)
    if not plan["covers"]:
        raise RuntimeError("SOURCE_TOO_SMALL: %sx%s cannot cover %sx%s"
                           % (src_w, src_h, DEFAULT_WIDTH, DEFAULT_HEIGHT))
    argv = build_argv(source, output, src_w, src_h, center_x=center_x,
                      fps=fps)
    return _LG.run_ffmpeg(argv, job, capture_output=True, text=True,
                          timeout=timeout)


def _rotation_degrees(path, ffprobe="ffprobe", timeout=60):
    """Display-matrix rotation of the first video stream, in whole degrees.

    A rotation fill (rotate 9:16 sideways, tag it with a 90-degree rotation,
    let the player stand it up) is full height only on the player's screen;
    the stored frames are not. This is what tells it apart from crop-in.
    """
    argv = [ffprobe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream_side_data=rotation", "-of", "json",
            str(path)]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout)
        data = json.loads(proc.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return 0
    for stream in data.get("streams", []) or []:
        for side in stream.get("side_data_list", []) or []:
            try:
                return int(round(float(side.get("rotation", 0)))) % 360
            except (TypeError, ValueError):
                continue
    return 0


def verify_output(output, ffprobe="ffprobe"):
    """Measure the rendered file. ok only for a clean full-height crop-in.

    Full height must live in the stored frames (crop-in). A file that reaches
    1080x1920 by rotation metadata — the rotated-fill trick — is refused as
    ROTATED_FILL; a file short of full height is OUTPUT_NOT_FULL_HEIGHT.
    """
    w, h = frame_size(output, ffprobe=ffprobe)
    rot = _rotation_degrees(output, ffprobe=ffprobe)
    geom_ok = (w == DEFAULT_WIDTH and h == DEFAULT_HEIGHT)
    upright = rot % 360 == 0
    ok = geom_ok and upright
    if not geom_ok:
        reason = "OUTPUT_NOT_FULL_HEIGHT"
        action = ("output is %sx%s, expected %sx%s full height via %s"
                  % (w, h, DEFAULT_WIDTH, DEFAULT_HEIGHT, NO_FILL))
    elif not upright:
        reason = "ROTATED_FILL"
        action = ("output carries a %d deg display rotation; rotation fill "
                  "is refused, %s is the only full-height path"
                  % (rot, NO_FILL))
    else:
        reason, action = None, ""
    return {"tool": TOOL_NAME, "tool_version": TOOL_VERSION,
            "fit": NO_FILL if ok else None,
            "outcome": "ok" if ok else "rejected",
            "reason_code": reason,
            "width": w, "height": h, "rotation_deg": rot,
            "expected": [DEFAULT_WIDTH, DEFAULT_HEIGHT],
            "next_action": action}


def inspect(path, ffprobe="ffprobe"):
    """Envelope for one file: measured size plus the fill classification."""
    w, h = frame_size(path, ffprobe=ffprobe)
    plan = classify(w, h)
    out = dict(plan)
    verdict = verify_output(path, ffprobe=ffprobe)
    out.update({"schema_version": "blackceo.video-still-fill/v1",
                "path": str(path),
                "rotation_deg": verdict["rotation_deg"],
                "outcome": verdict["outcome"],
                "reason_code": verdict["reason_code"]})
    return out


def scan_core_scripts(core_dir):
    """Source-level refusal gate: no shipped core script may carry a fill.

    A hit is a blur fill sitting in the build system itself — the spot-2
    incident was exactly a gblur+alphamerge chain in a hand script.
    """
    hits = []
    for dirpath, dirnames, filenames in os.walk(core_dir):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if not fn.endswith((".py", ".sh", ".js", ".json")):
                continue
            if fn in SCANNER_FILES:
                continue
            p = os.path.join(dirpath, fn)
            try:
                with open(p, encoding="utf-8", errors="ignore") as fh:
                    text = fh.read().lower()
            except OSError:
                continue
            for marker in BLUR_MARKERS:
                if marker in text:
                    hits.append((os.path.relpath(p, core_dir), marker))
    return {"tool": TOOL_NAME, "tool_version": TOOL_VERSION,
            "fit": NO_FILL,
            "scan_markers": list(BLUR_MARKERS),
            "outcome": "rejected" if hits else "ok",
            "reason_code": "BLUR_FILL_IN_CORE" if hits else None,
            "hits": hits,
            "next_action": ("remove the blur fill from %s; crop-in is the "
                            "only full-height path" % hits[0][0])
            if hits else ""}


def _envelope(outcome, reason_code="", next_action="", **data):
    out = {"schema_version": "blackceo.video-still-fill/v1",
           "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
           "outcome": outcome, "reason_code": reason_code,
           "next_action": next_action}
    out.update(data)
    return out


def _emit(obj, code):
    print(json.dumps(obj, indent=2, sort_keys=True))
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(prog=TOOL_NAME, description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("render", help="crop-in render, never a fill")
    rp.add_argument("--source", required=True)
    rp.add_argument("--output", required=True)
    rp.add_argument("--center-x", type=float, default=0.5)
    rp.add_argument("--fps", type=float, default=None)
    rp.add_argument("--ffprobe", default="ffprobe")
    ip = sub.add_parser("inspect", help="classify one rendered file")
    ip.add_argument("--output", required=True)
    ip.add_argument("--ffprobe", default="ffprobe")
    sub.add_parser("scan-core", help="refuse blur fill anywhere in core/")
    ns = ap.parse_args(argv)
    try:
        if ns.cmd == "render":
            res = render(ns.source, ns.output, center_x=ns.center_x,
                         fps=ns.fps, ffprobe=ns.ffprobe)
            if res.returncode != 0:
                return _emit(_envelope("error", "RENDER_FAILED",
                                       (res.stderr or "").strip()[-400:]
                                       or "ffmpeg failed"),
                             EXIT["error"])
            out = verify_output(ns.output, ffprobe=ns.ffprobe)
            return _emit(out, EXIT["ok"] if out["outcome"] == "ok"
                         else EXIT["rejected"])
        if ns.cmd == "inspect":
            res = inspect(ns.output, ffprobe=ns.ffprobe)
            return _emit(res, EXIT["ok"] if res["outcome"] == "ok"
                         else EXIT["rejected"])
        res = scan_core_scripts(_gcore)
        return _emit(res, EXIT["rejected"] if res["hits"] else EXIT["ok"])
    except (RuntimeError, ValueError, OSError) as exc:
        return _emit(_envelope("error", "STILL_FILL_ERROR", str(exc)),
                     EXIT["error"])


if __name__ == "__main__":
    sys.exit(main())
