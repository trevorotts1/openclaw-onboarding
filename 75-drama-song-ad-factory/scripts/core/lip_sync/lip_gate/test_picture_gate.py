#!/usr/bin/env python3
"""LPG001 picture gate: the 28% / smile+teeth cases fail, the crop passes, a
missing mediapipe is a refusal. $0, stdlib only (mediapipe is faked/absent).
Run: python3 scripts/core/lip_sync/lip_gate/test_picture_gate.py"""
import builtins
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import picture_gate as P                                # noqa: E402

GOOD = {"faces": 1, "size": [1126, 2003], "face_h_pct": 37.8, "face_cx": 500.0, "face_cy": 900.0,
        "roll_deg": -4.3, "yaw": -0.045, "smile": 0.36, "jaw_open": 0.0, "inner_gap_pct": 0.03, "sharp": 375.1}
THIRTY_DAY = dict(GOOD, face_h_pct=28.1, roll_deg=2.3, yaw=0.018, smile=0.62, inner_gap_pct=0.33)
DAUGHTER = dict(GOOD, face_h_pct=34.4, roll_deg=-7.8, yaw=-0.069, smile=0.83, inner_gap_pct=1.65)


def codes(n):
    return {c for c, _ in P.judge_picture(n)[1]}


def img(name, body=b"x"):
    p = os.path.join(tempfile.mkdtemp(prefix="lpg-"), name)
    open(p, "wb").write(body)
    return p


def test_real_numbers():
    assert P.judge_picture(GOOD)[0] == "PASS"
    assert P.judge_picture(dict(GOOD, face_h_pct=36.8, smile=0.59, roll_deg=3.1, inner_gap_pct=0.38))[0] == "PASS"
    assert {"PICTURE_FACE_SMALL", "PICTURE_SMILE"} <= codes(THIRTY_DAY)
    assert {"PICTURE_FACE_SMALL", "PICTURE_SMILE", "PICTURE_TEETH", "PICTURE_HEAD_TILT"} <= codes(DAUGHTER)
    assert P.judge_picture(dict(GOOD, faces=2))[0] == "FAIL"
    assert "PICTURE_UNMEASURED" in codes({"faces": 1})


def test_crop_fixes_small_face_for_free():
    src = img("a.png", b"small")
    seen = {}

    def measure(path):
        return dict(GOOD) if path.endswith("-crop.png") else dict(GOOD, face_h_pct=28.1)

    def crop(path, out, n):
        open(out, "wb").write(b"cropped")
        seen["crop"] = n
        return out

    final, rec = P.fix_picture(src, measure=measure, crop=crop)
    assert final.endswith("-crop.png") and rec["verdict"] == "PASS" and "local crop" in rec["steps"]
    assert P.receipt_refusal(final) is None


def test_smile_regenerates_once_then_refuses():
    src = img("b.png", b"smile")
    calls = []

    def regen(path, prompt):
        calls.append(prompt)
        return img("regen.png", b"new")

    measure = lambda p: dict(GOOD) if p.endswith("regen.png") else dict(THIRTY_DAY, face_h_pct=40)  # noqa: E731
    final, rec = P.fix_picture(src, regenerate=regen, measure=measure)
    assert rec["verdict"] == "PASS" and len(calls) == 1 and "lips closed" in calls[0]
    try:                                    # regen still bad -> refused, FAIL receipt kept
        P.fix_picture(src, regenerate=regen, measure=lambda p: dict(DAUGHTER), crop=lambda p, o, n: p)
    except P.PictureRefused:
        pass
    else:
        raise AssertionError("must refuse")
    assert P.receipt_refusal(src)[0] == "LIPSYNC_PICTURE_FAILED"


def test_receipt_rules():
    p = img("c.png", b"one")
    assert P.receipt_refusal(p)[0] == "LIPSYNC_PICTURE_NO_RECEIPT"
    P.gate_picture(p, lambda _: dict(GOOD))
    assert P.receipt_refusal(p) is None
    open(p, "wb").write(b"changed")         # different bytes -> stale
    assert P.receipt_refusal(p)[0] == "LIPSYNC_PICTURE_RECEIPT_STALE"
    assert P.receipt_refusal(None)[0] == "LIPSYNC_PICTURE_MISSING"


def test_missing_mediapipe_is_refused():
    real = builtins.__import__

    def deny(name, *a, **k):
        if name.startswith("mediapipe"):
            raise ImportError("no mediapipe")
        return real(name, *a, **k)

    builtins.__import__ = deny
    try:
        P.gate_picture(img("d.png"))
    except P.PictureRefused as e:
        assert e.reasons[0][0] == "PICTURE_MEDIAPIPE_MISSING"
    else:
        raise AssertionError("missing mediapipe must refuse")
    finally:
        builtins.__import__ = real


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL CHECKS PASS")
