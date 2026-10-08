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


def test_constants_are_the_one_block():
    assert (P.MIN_FACE_H_PCT, P.MAX_ABS_ROLL_DEG, P.MAX_ABS_YAW, P.MAX_SMILE, P.MAX_JAW_OPEN,
            P.MAX_INNER_GAP_PCT, P.MIN_SHARP) == (35.0, 5.0, 0.12, 0.60, 0.15, 1.0, 100.0)
    assert (P.MAX_LOCAL_CROPS, P.MAX_REGENERATIONS) == (1, 2)
    assert P.REGEN_PROMPT == "neutral expression, lips closed, facing camera, head level"
    assert P.REGEN_MODEL == "gpt-image-2-image-to-image"
    assert P.FACE_MODEL_URL == ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
                                "face_landmarker/float16/latest/face_landmarker.task")
    assert len(P.FACE_MODEL_SHA256) == 64


def test_every_limit_at_the_edge():
    for k, ok, bad in [("face_h_pct", 35.0, 34.9), ("roll_deg", -5.0, -5.1), ("yaw", 0.12, 0.13),
                       ("smile", 0.60, 0.61), ("jaw_open", 0.15, 0.16),
                       ("inner_gap_pct", 1.0, 1.01), ("sharp", 100.0, 99.9)]:
        assert P.judge_picture(dict(GOOD, **{k: ok}))[0] == "PASS", k
        assert P.judge_picture(dict(GOOD, **{k: bad}))[0] == "FAIL", k
    assert P.judge_picture(dict(GOOD, face_h_pct=70.0))[0] == "PASS"     # no upper limit


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


def test_crop_is_tried_once_then_paid_fix_capped_at_two():
    src = img("e.png", b"e")
    crops, regens = [], []

    def crop(p, o, n):
        crops.append(o)
        open(o, "wb").write(b"crop%d" % len(crops))
        return o

    def regen(p, prompt):
        regens.append(prompt)
        return img("r%d.png" % len(regens), b"r%d" % len(regens))

    try:
        P.fix_picture(src, regenerate=regen, crop=crop, measure=lambda p: dict(THIRTY_DAY))
    except P.PictureRefused:
        pass
    else:
        raise AssertionError("must refuse after 2 paid tries")
    assert len(regens) == 2 and len(crops) == 3                  # 1 crop per fresh picture
    assert regens == [P.REGEN_PROMPT] * 2
    try:                                                         # no regenerator = no paid fix
        P.fix_picture(src, measure=lambda p: dict(DAUGHTER, face_h_pct=40))
    except P.PictureRefused:
        pass
    else:
        raise AssertionError("must refuse")


def _fake_mediapipe():
    import types
    mods = {}
    for n in ("cv2", "numpy", "mediapipe", "mediapipe.tasks", "mediapipe.tasks.python"):
        mods[n] = types.ModuleType(n)
    mods["mediapipe.tasks.python"].BaseOptions = object
    mods["mediapipe.tasks.python"].vision = object
    return mods


def test_missing_or_corrupt_model_refuses_naming_the_install_command():
    saved = {n: sys.modules.get(n) for n in _fake_mediapipe()}
    sys.modules.update(_fake_mediapipe())
    old = os.environ.pop(P.FACE_MODEL_ENV, None)
    real_dir = os.path.dirname(P.__file__)
    try:
        missing = os.path.join(real_dir, P.FACE_MODEL_NAME)
        if os.path.exists(missing):                       # a box with the model installed
            return
        try:
            P.measure_picture(img("m.png"))
        except P.PictureRefused as e:
            assert e.reasons[0][0] == "PICTURE_MODEL_MISSING" and "install_face_model.py" in e.reasons[0][1]
        else:
            raise AssertionError("missing model must refuse")
        open(missing, "wb").write(b"not the model")       # wrong hash -> corrupt
        try:
            P.measure_picture(img("m.png"))
        except P.PictureRefused as e:
            assert e.reasons[0][0] == "PICTURE_MODEL_CORRUPT" and "install_face_model.py" in e.reasons[0][1]
        else:
            raise AssertionError("corrupt model must refuse")
        finally:
            os.unlink(missing)
    finally:
        for n, m in saved.items():
            if m is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = m
        if old is not None:
            os.environ[P.FACE_MODEL_ENV] = old


def test_installer_verifies_the_pinned_hash():
    sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))
    import install_face_model as I
    d = tempfile.mkdtemp(prefix="lpg-inst-")
    src = os.path.join(d, "src.task")
    open(src, "wb").write(b"fake model bytes")
    url, sha, dest = "file://" + src, P.hashlib.sha256(b"fake model bytes").hexdigest(), os.path.join(d, "m", "f.task")
    try:
        I.install(url=url, sha256="0" * 64, dest=dest)
    except RuntimeError as e:
        assert "sha256 mismatch" in str(e)
    else:
        raise AssertionError("wrong hash must not install")
    assert not os.path.exists(dest) and os.listdir(os.path.dirname(dest)) == []      # nothing placed, no .part
    assert I.install(url=url, sha256=sha, dest=dest) == dest and open(dest, "rb").read() == b"fake model bytes"
    os.unlink(src)                                           # already correct -> no download needed
    assert I.install(url=url, sha256=sha, dest=dest) == dest
    try:
        I.install(url="file://" + os.path.join(d, "nope"), sha256=sha, dest=os.path.join(d, "x.task"))
    except RuntimeError as e:
        assert "download failed" in str(e)
    else:
        raise AssertionError("bad url must fail")


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
