"""qc_no_blur.quality_gate: the quality check's refusal (DEL-14).

check_deliverable() is the quality check on a delivered file. It fails:

  * a frame that is short of full height because of a fill;
  * a frame carrying a fill -- edge-sampled backdrop, gaussian-filled
    background, duplicated blurred strip, blurred mask, letterbox bars;
  * an unreadable file (fail closed: UNREADABLE is never PASS).

Delivery shape mirrors core/delivery_audio.check_delivery_audio: a dict
with ok / reason_code / reason, plus require_no_fill() for callers that
want an exception. The reason always names the violation AND the repair
(crop-in re-lip-sync), so the flow recovers instead of filling.
"""
from __future__ import annotations

from . import detect

TOOL = "qc_no_blur.quality_gate"
NO_FILL = "NO_BLUR_FILL_OK"


def _res(ok, code, reason, violations=None, stats=None, **kw):
    out = {"ok": ok, "reason_code": code, "reason": reason,
           "tool": TOOL, "violations": violations or [],
           "stats": stats or {}}
    out.update(kw)
    return out


def check_deliverable(path, expect_width=None, expect_height=None,
                      ffmpeg="ffmpeg", ffprobe="ffprobe"):
    """Quality check on one deliverable. ok=False refuses it."""
    violations, stats = detect.scan_frame(path, expect_width=expect_width,
                                          expect_height=expect_height,
                                          ffmpeg=ffmpeg, ffprobe=ffprobe)
    if not violations:
        return _res(True, NO_FILL,
                    "full-height frame, no blur fill "
                    "(%sx%s)" % (stats.get("width"), stats.get("height")),
                    stats=stats)
    code = violations[0]["code"]
    detail = "; ".join("%s: %s" % (v["code"], v["detail"])
                       for v in violations)
    return _res(False, code, detect.message(code, detail), violations, stats)


class BlurFillRefused(Exception):
    """The quality check refused a deliverable. .result is the gate dict."""

    def __init__(self, result):
        self.result = result
        self.code = result.get("reason_code", "BLUR_FILL")
        super().__init__("%s: %s" % (self.code, result.get("reason", "")))


def require_no_fill(path, **kw):
    """check_deliverable, but a fill raises instead of returning."""
    result = check_deliverable(path, **kw)
    if not result["ok"]:
        raise BlurFillRefused(result)
    return result
