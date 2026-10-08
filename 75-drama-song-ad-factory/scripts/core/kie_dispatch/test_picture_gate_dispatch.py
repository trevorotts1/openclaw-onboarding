#!/usr/bin/env python3
"""LPG001: the dispatcher refuses ANY lip-sync job without a PASS picture
receipt for that exact file; the paid runner is never reached. $0.
Run: python3 core/kie_dispatch/test_picture_gate_dispatch.py"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import kie_dispatch as D                                   # noqa: E402
from lip_sync.lip_gate import picture_gate as P            # noqa: E402

GOOD = {"faces": 1, "size": [1126, 2003], "face_h_pct": 37.8, "roll_deg": -4.3, "yaw": -0.045,
        "smile": 0.36, "jaw_open": 0.0, "inner_gap_pct": 0.03, "sharp": 375.1}


def paid_runner(argv):
    raise AssertionError("paid runner reached without a picture receipt")


def go(model, image):
    return D.dispatch(model=model, request={"input": {"image_url": image, "prompt": "p"}},
                      save_dir=tempfile.mkdtemp(), ledger_db=":memory:", run_id="r", logical_key="k",
                      attempt_id="a", estimated_cost=10, runner=paid_runner)


def test_refused_without_receipt_and_on_fail_and_stale():
    d = tempfile.mkdtemp()
    img = os.path.join(d, "c.png")
    open(img, "wb").write(b"pic")
    for model in ("kling/ai-avatar-standard", "kling/ai-avatar-pro", "infinitalk/from-audio"):
        e = go(model, img)
        assert e["outcome"] == "rejected" and e["reason_code"] == "LIPSYNC_PICTURE_NO_RECEIPT", e
    assert go("kling/ai-avatar-standard", "https://x/y.png")["reason_code"] == "LIPSYNC_PICTURE_MISSING"
    P.gate_picture(img, lambda _: dict(GOOD, face_h_pct=28.1))
    assert go("kling/ai-avatar-standard", img)["reason_code"] == "LIPSYNC_PICTURE_FAILED"
    P.gate_picture(img, lambda _: dict(GOOD))
    assert D.picture_gate_refusal("kling/ai-avatar-standard", {"input": {"image_url": img}}) is None
    open(img, "wb").write(b"edited")
    assert go("kling/ai-avatar-standard", img)["reason_code"] == "LIPSYNC_PICTURE_RECEIPT_STALE"


def test_non_lipsync_untouched():
    assert D.picture_gate_refusal("gpt-image-2-text-to-image", {}) is None


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL CHECKS PASS")
