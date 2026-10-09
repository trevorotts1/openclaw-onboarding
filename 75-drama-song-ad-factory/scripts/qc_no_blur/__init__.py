"""qc_no_blur: DEL-14 -- blur fill is never used, crop-in is the only path.

Two refusal gates, one recovery path:

  assembler_gate  final_assembler refuses an attempted blur fill BEFORE the
                  render (plan + ffmpeg command) and a landed one AFTER it
                  (the produced frame). check_render / require_render.
  quality_gate    the delivery quality check fails a deliverable whose frame
                  is short of full height because of a fill, and one that
                  carries a fill: edge-sampled backdrop, gaussian-filled
                  background, duplicated blurred strip, blurred mask,
                  letterbox bars. check_deliverable / require_no_fill.
  crop_relip      the recovery: regenerate() rebuilds the clip from the
                  SOURCE frame with a crop-in to full height and verifies
                  the result carries no fill, so the flow recovers instead
                  of filling.

Detection lives in detect.py (attempt = text/argv/plan scan, result = frame
analysis). Stdlib only; shells to ffmpeg/ffprobe.

Run: python3 scripts/qc_no_blur/test_qc_no_blur.py
CLI: python3 scripts/qc_no_blur/cli.py check <file> [--width W --height H]
     python3 scripts/qc_no_blur/cli.py scan-argv <ffmpeg argv...>
"""
from __future__ import annotations

from . import detect
from .assembler_gate import (BlurFillRefused as AssemblerBlurFillRefused,
                             check_render, require_render)
from .quality_gate import (BlurFillRefused as QualityBlurFillRefused,
                           check_deliverable, require_no_fill)
from .crop_relip import (CropRelipError, crop_box, crop_in_argv, regenerate)

TOOL_NAME = "qc_no_blur"
TOOL_VERSION = "1.0.0"

#: The one repair every refusal names.
REPAIR = detect.REPAIR

__all__ = [
    "TOOL_NAME", "TOOL_VERSION", "REPAIR", "detect",
    "check_render", "require_render", "AssemblerBlurFillRefused",
    "check_deliverable", "require_no_fill", "QualityBlurFillRefused",
    "CropRelipError", "crop_box", "crop_in_argv", "regenerate",
]
