#!/usr/bin/env python3
"""Automatic 60- and 90-second clips for the 3, 5 and 10 minute ads.

Owner order 2026-10-09 (FU-LENGTH-CLIPS): the 3 minute ad comes with a
60-second and a 90-second clip, exactly like 5 minutes; 10 minutes gets the
same two. 60 and 90 second ads get none. Cutting is an FFmpeg edit of the
finished master: no new AI media, so it costs $0 and the card price already
includes it.

Picking the clip (pure, no media, no network):
  * cut only on whole lines of the timeline's ``lines`` (start_s/end_s), so a
    clip never starts or ends mid-word;
  * the clip fits L-2 seconds (the same I4 end-early rule as the master);
  * hook placement (core/sung_hook): lines marked ``"hook": true`` are the
    sung hook. A clip opens on a line that puts its first hook inside the
    first FIRST_HOOK_AT (15%) of the clip, and carries as many hooks as fit
    (at least two when the ad has two);
  * never into the end card (``endcard_start_s``);
  * tie-break: more story beats (line ``beat`` tags), then the earlier start.
No window that meets those rules raises ClipCutdownError (fail closed).

stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)
from master_length import master_max_s  # noqa: E402
from sung_hook import sung_hook as _SH  # noqa: E402

TOOL_NAME = "clip_cutdown"
CLIP_LENGTHS_S = (60, 90)
MIN_CLIP_AD_S = 180          # 3 minutes and longer get clips; 60/90 do not
FADE_S = 0.75                # short music fade at the end of each clip


class ClipCutdownError(ValueError):
    pass


def clips_for(chosen_length_s):
    """The clip lengths an ad of this chosen length comes with: (60, 90) or ()."""
    return CLIP_LENGTHS_S if chosen_length_s >= MIN_CLIP_AD_S else ()


def _lines(tl):
    ls = tl.get("lines")
    if not isinstance(ls, list) or not ls:
        raise ClipCutdownError("CLIP_NO_LINES: timeline needs lines[] with start_s/end_s")
    cap = tl.get("endcard_start_s")
    out = [l for l in ls if cap is None or l["end_s"] <= cap + 1e-6]
    return sorted(out, key=lambda l: l["start_s"])


def _best_window(lines, budget):
    total_hooks = sum(1 for l in lines if l.get("hook"))
    need = min(2, total_hooks)
    best = None
    for i, first in enumerate(lines):
        t0 = first["start_s"]
        j = i
        while j + 1 < len(lines) and lines[j + 1]["end_s"] - t0 <= budget + 1e-6:
            j += 1
        win = lines[i:j + 1]
        if win[-1]["end_s"] - t0 > budget + 1e-6:
            continue
        hooks = [l for l in win if l.get("hook")]
        if len(hooks) < max(need, 1):
            continue
        dur = win[-1]["end_s"] - t0
        if hooks[0]["start_s"] - t0 > _SH.FIRST_HOOK_AT * dur + 1e-6:
            continue
        beats = len({l.get("beat") for l in win if l.get("beat")})
        key = (len(hooks), beats, -t0)
        if best is None or key > best[0]:
            best = (key, t0, win[-1]["end_s"], len(hooks), beats)
    return best


def plan_clips(tl, chosen_length_s):
    """Clip plan for a timeline: [] for 60/90 s, else one entry per clip length."""
    plans = []
    for L in clips_for(chosen_length_s):
        budget = master_max_s(L)
        best = _best_window(_lines(tl), budget)
        if best is None:
            raise ClipCutdownError(
                "CLIP_NO_WINDOW: no whole-line window of %gs holds the sung hook "
                "within its first 15%% (mark hook lines with hook: true)" % budget)
        _, s, e, nh, nb = best
        plans.append({"name": "clip-%ds" % L, "clip_length_s": L, "start_s": round(s, 3),
                      "end_s": round(e, 3), "duration_s": round(e - s, 3),
                      "hooks": nh, "beats": nb, "captions_offset_s": round(-s, 3)})
    return plans


def build_argv(master, plan, out_dir, ffmpeg="ffmpeg"):
    """ffmpeg argv for one clip: whole-line cut, short video and music fade-out."""
    d = plan["duration_s"]
    fo = max(d - FADE_S, 0)
    return [ffmpeg, "-y", "-ss", "%.3f" % plan["start_s"], "-i", master,
            "-t", "%.3f" % d,
            "-vf", "fade=t=out:st=%.3f:d=%.2f" % (fo, FADE_S),
            "-af", "afade=t=out:st=%.3f:d=%.2f" % (fo, FADE_S),
            "-c:v", "libx264", "-c:a", "aac",
            os.path.join(out_dir, plan["name"] + ".mp4")]


def run_clips(master, plans, out_dir, runner=subprocess.run, ffmpeg="ffmpeg"):
    """Cut every planned clip; returns the output paths. runner is injectable."""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for p in plans:
        argv = build_argv(master, p, out_dir, ffmpeg)
        r = runner(argv, capture_output=True, text=True)
        if getattr(r, "returncode", 0) != 0:
            raise ClipCutdownError("CLIP_FFMPEG_FAILED: %s" % p["name"])
        paths.append(argv[-1])
    return paths


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("timeline")
    ap.add_argument("--length", type=int, required=True, help="chosen ad length in seconds")
    ap.add_argument("--master", help="rendered master; with --outdir the clips are cut")
    ap.add_argument("--outdir")
    a = ap.parse_args(argv)
    with open(a.timeline, encoding="utf-8") as fh:
        plans = plan_clips(json.load(fh), a.length)
    if a.master and a.outdir:
        run_clips(a.master, plans, a.outdir)
    json.dump(plans, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
