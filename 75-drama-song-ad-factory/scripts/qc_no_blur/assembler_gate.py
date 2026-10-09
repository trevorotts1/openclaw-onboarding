"""qc_no_blur.assembler_gate: the assembler's refusal (DEL-14).

final_assembler calls check_render() twice in spirit, once in code:

  * BEFORE the render -- the argv it is about to run and the plan it is
    building from are scanned, so an attempted blur fill (edge-sampled
    backdrop, gaussian-filled background, duplicated blurred strip,
    blurred mask, letterbox pad) never reaches ffmpeg;
  * AFTER the render -- the produced frame is scanned, so a fill that
    landed anyway is refused before anything is delivered.

Failure shape mirrors core/delivery_audio: check_* returns a dict,
require_* raises. Fail closed: a violation is never a warning.
"""
from __future__ import annotations

from . import detect

TOOL = "qc_no_blur.assembler_gate"
NO_FILL = "ASSEMBLER_NO_BLUR_FILL"


def _res(ok, code, reason, violations=None, stats=None, **kw):
    out = {"ok": ok, "reason_code": code, "reason": reason,
           "tool": TOOL, "violations": violations or [],
           "stats": stats or {}}
    out.update(kw)
    return out


def check_render(plan=None, argv=None, output=None, expect_width=None,
                 expect_height=None, ffmpeg="ffmpeg", ffprobe="ffprobe",
                 frame_scan=True):
    """Refuse an attempted or landed blur fill. Returns the gate dict.

    plan/argv are checked as the attempt; output (when the file exists) is
    checked as the result. frame_scan=False skips pixel work (dry runs).
    """
    found = []
    if plan:
        found.extend(detect.scan_plan(plan))
    if argv:
        found.extend(detect.scan_argv(argv))
    stats = {}
    if output and frame_scan and _exists(output):
        want_h = expect_height or (plan or {}).get("height")
        want_w = expect_width or (plan or {}).get("width")
        fv, stats = detect.scan_frame(output, expect_width=want_w,
                                      expect_height=want_h, ffmpeg=ffmpeg,
                                      ffprobe=ffprobe)
        found.extend(fv)
    if not found:
        return _res(True, NO_FILL, "no blur fill in plan, command or frame",
                    stats=stats)
    code = found[0]["code"]
    detail = "; ".join("%s: %s" % (v["code"], v["detail"]) for v in found)
    return _res(False, code, detect.message(code, detail), found, stats)


def _exists(path):
    import os
    try:
        return os.path.isfile(str(path))
    except (TypeError, ValueError):
        return False


class BlurFillRefused(Exception):
    """The assembler refused a blur fill. .result is the gate dict."""

    def __init__(self, result):
        self.result = result
        self.code = result.get("reason_code", "BLUR_FILL")
        super().__init__("%s: %s" % (self.code, result.get("reason", "")))


def require_render(**kw):
    """check_render, but a violation raises instead of returning."""
    result = check_render(**kw)
    if not result["ok"]:
        raise BlurFillRefused(result)
    return result
