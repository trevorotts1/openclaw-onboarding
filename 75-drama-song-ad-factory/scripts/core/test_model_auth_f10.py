#!/usr/bin/env python3
"""F-MODEL-AUTH (Lock 10): only authorized video models; rest refuse pre-spend.

Allowed: minimax-h3/reference-to-video, minimax-h3/image-to-video,
omnihuman-2-0 (N-12 / S-42 replaces the retired Kling avatar id, November
23). Everything else refuses MODEL_UNAUTHORIZED, fail-closed on unreadable
model. Only override: Trevor written order binding model + shot. stdlib
only, zero paid calls. Run: python3 core/test_model_auth_f10.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import never_again as NA  # noqa: E402

FAILS = []


def check(name, cond):
    print("%s: %s" % ("ok" if cond else "FAIL", name))
    if not cond:
        FAILS.append(name)


def main():
    for m in ("minimax-h3/reference-to-video", "minimax-h3/image-to-video",
              "omnihuman-2-0"):
        check("allowed: %s" % m, NA.check_model_authorized(m) is None)

    for m in ("minimax-h3/text-to-video", "kling-3.0/video",
              "kling-3.0-omni/image-to-video", "kling/ai-avatar-standard",
              "bytedance/seedance-2-5",
              "bytedance/seedance-1.5-pro", "hailuo/02-image-to-video-standard",
              "veo-3-1", "", None, 123):
        r = NA.check_model_authorized(m)
        check("refused: %r" % (m,),
              r is not None and r["code"] == NA.MODEL_UNAUTHORIZED)

    o = {"signed_by": "Trevor", "signature": "x", "model": "kling-3.0/video",
         "shot_id": "T05"}
    check("order binds model+shot",
          NA.check_model_order(o, "kling-3.0/video", "T05"))
    check("order wrong shot refused",
          not NA.check_model_order(o, "kling-3.0/video", "T06"))
    check("order wrong model refused",
          not NA.check_model_order(o, "veo-3-1", "T05"))
    check("order no shot refused",
          not NA.check_model_order(o, "kling-3.0/video", None))
    check("unsigned order refused",
          not NA.check_model_order(dict(o, signed_by="agent"),
                                   "kling-3.0/video", "T05"))

    print("FAILURES: %d" % len(FAILS))
    return 1 if FAILS else 0


def test_model_auth():
    """pytest entry: every F-MODEL-AUTH check in main() must pass."""
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
