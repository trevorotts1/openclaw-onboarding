#!/usr/bin/env python3
"""qc_no_blur CLI: refuse a blur fill by hand, or regenerate the crop-in.

  python3 cli.py check master.mp4 --width 1080 --height 1920
  python3 cli.py scan-argv -filter_complex "[0:v]gblur=sigma=30[v]"
  python3 cli.py crop-in source.mp4 out.mp4 --width 1080 --height 1920

Exit 0 = no fill (or the crop-in regenerated). Exit 5 = refused.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qc_no_blur import (assembler_gate, crop_relip, detect,  # noqa: E402
                        quality_gate)


def main(argv=None):
    p = argparse.ArgumentParser(prog="qc_no_blur",
                                description="DEL-14 no-blur-fill gates")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="quality check on a rendered file")
    c.add_argument("path")
    c.add_argument("--width", type=int, default=None)
    c.add_argument("--height", type=int, default=None)

    s = sub.add_parser("scan-argv", help="scan an ffmpeg command for a fill")
    s.add_argument("rest", nargs="+")

    g = sub.add_parser("plan", help="scan a plan/receipt JSON for a fill")
    g.add_argument("path")

    r = sub.add_parser("crop-in", help="crop-in re-lip-sync regeneration")
    r.add_argument("src")
    r.add_argument("out")
    r.add_argument("--width", type=int, default=crop_relip.DEFAULT_OUT_W)
    r.add_argument("--height", type=int, default=crop_relip.DEFAULT_OUT_H)
    r.add_argument("--bias", default="center", choices=crop_relip.BIASES)
    r.add_argument("--fps", type=float, default=None)

    ns = p.parse_args(argv)
    if ns.cmd == "check":
        out = quality_gate.check_deliverable(
            ns.path, expect_width=ns.width, expect_height=ns.height)
    elif ns.cmd == "scan-argv":
        out = assembler_gate.check_render(argv=ns.rest, frame_scan=False)
    elif ns.cmd == "plan":
        with open(ns.path, encoding="utf-8") as fh:
            out = assembler_gate.check_render(plan=json.load(fh),
                                              frame_scan=False)
    else:                                   # crop-in
        try:
            out = crop_relip.regenerate(ns.src, ns.out, ns.width, ns.height,
                                        bias=ns.bias, fps=ns.fps)
        except crop_relip.CropRelipError as exc:
            print("%s: %s" % (exc.code, exc), file=sys.stderr)
            return 5
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") or out.get("outcome") == "ok" else 5


if __name__ == "__main__":
    sys.exit(main())
