#!/usr/bin/env python3
"""W1-method-lipsync-U2: the free face-crop ladder for a 0-face close-up and
the teeth-smile remake hook for the lip-sync shot.
$0: the measurer, the crops and the remakes are all injected; nothing paid and
nothing networked runs here.
Run: python3 test_crop_ladder.py   (passes with an empty HOME)"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, CORE)
import picture_gate as G                               # noqa: E402

# the same measured shapes the LPG001 calibration uses (mediapipe, 2026-10-08)
def N(h, roll, yaw, smile, gap, sharp, jaw=0.0, faces=1):
    return {"face_count": faces, "face_h_pct": h, "roll_deg": roll, "yaw_proxy": yaw,
            "smile": smile, "jaw_open": jaw, "inner_gap_pct": gap, "sharp_face_256": sharp}


GOOD = N(37.8, -4.3, -0.045, 0.36, 0.03, 375.1)               # accepted, neutral
SMILING = N(34.4, -7.8, -0.069, 0.83, 1.65, 519.7)            # smile 0.83 + teeth
NOFACE = dict(GOOD, face_count=0)                             # trial C's full frame
TWO_FACES = dict(GOOD, face_count=2)
TINY = dict(GOOD, face_h_pct=15.0)


def pic(d, name="a.png", data=b"x"):
    p = os.path.join(d, name)
    open(p, "wb").write(data)
    return p


def refused(fn, *a, **k):
    try:
        fn(*a, **k)
    except G.LipsyncPictureNotGated as e:
        return str(e)
    raise AssertionError("expected LipsyncPictureNotGated")


def _boom(*a, **k):
    raise AssertionError("must not be called")


def test_constants_are_the_research_numbers():
    assert G.CROP_LADDER_WIDTHS == (0.70, 0.60, 0.80)          # SPEC A7, rung order
    assert G.MAX_REMAKES == 3 and G.SMILING_CODE == "LIPSYNC_SOURCE_SMILING"
    assert G.SMILING_FLAGS == frozenset({"SMILE"})             # a smile, teeth or not


def test_zero_face_ladder_first_rung_passes_and_is_the_returned_image():
    with tempfile.TemporaryDirectory() as d:
        a = pic(d, "cartoon.png", b"2k close-up")
        widths = []
        def ladder(p, o, w):
            widths.append(w)
            return pic(d, os.path.basename(o), b"crop")
        meas = lambda p: GOOD if p.endswith("-ladder1.png") else NOFACE
        res = G.gate_picture(a, measure=meas, ladder=ladder, crop=_boom,
                             regenerate=_boom)
        assert widths == [0.70], widths                        # one free rung
        assert res["verdict"] == "PASS" and res["image"].endswith("-ladder1.png"), res
        assert [x["verdict"] for x in res["attempts"]] == ["FAIL", "PASS"]
        # the passing crop is THE picture: its receipt, and its bound upload
        G.require_receipt(res["image"])
        url = G.upload_measured(res["image"], lambda f: "https://k/ladder.png")
        G.require_upload_bound(res["image"], url)


def test_every_rung_runs_then_it_falls_through_to_todays_path():
    with tempfile.TemporaryDirectory() as d:
        a = pic(d, "cartoon.png", b"2k close-up")
        widths, made = [], []
        def ladder(p, o, w):
            widths.append(w)
            made.append(os.path.basename(o))
            return pic(d, os.path.basename(o), b"rung")
        # every crop still shows 0 faces: the ladder is exhausted, then today's
        # path runs (no paid fix wired = refuse, loudly)
        res = G.gate_picture(a, measure=lambda p: NOFACE, ladder=ladder,
                             crop=_boom, regenerate=_boom)
        assert widths == [0.70, 0.60, 0.80], widths
        assert [m.split("-ladder")[1] for m in made] == ["1.png", "2.png", "3.png"]
        assert res["verdict"] == "FAIL" and len(res["attempts"]) == 4, res
        assert res["reasons"][0][0] == "FACE_COUNT"
        refused(G.require_receipt, a)
        # ...and with a paid regeneration wired it is still today's behaviour:
        # the ladder never spends, the paid path is what runs after it
        calls = []
        def regen(p, prompt):
            calls.append(prompt)
            return pic(d, "r%d.png" % len(calls), b"paid")
        res = G.gate_picture(a, measure=lambda p: NOFACE, ladder=lambda p, o, w: None,
                             crop=_boom, regenerate=regen)
        assert len(calls) == G.MAX_PAID_REGENS and res["verdict"] == "FAIL", calls


def test_the_ladder_only_runs_for_zero_faces():
    with tempfile.TemporaryDirectory() as d:
        a = pic(d, "a.png", b"x")
        # 2+ faces is not a crop problem
        assert G.gate_picture(a, measure=lambda p: TWO_FACES, ladder=_boom,
                              crop=_boom)["verdict"] == "FAIL"
        # a too-small face keeps its ONE free crop-to-face, never the ladder
        crops = []
        meas = lambda p: GOOD if p.endswith("-crop.png") else TINY
        res = G.gate_picture(a, measure=meas, ladder=_boom,
                             crop=lambda p, o: crops.append(1) or pic(d, "-crop.png"))
        assert crops == [1] and res["verdict"] == "PASS", res


def test_smiling_close_up_is_remade_until_neutral():
    with tempfile.TemporaryDirectory() as d:
        a = pic(d, "a.png", b"smile")
        prompts, n = [], [0]
        def remake(p, prompt):
            prompts.append(prompt)
            n[0] += 1
            return pic(d, "m%d.png" % n[0], b"m")
        meas = lambda p: SMILING if p.endswith(("a.png", "m1.png")) else GOOD
        res = G.gate_picture(a, measure=meas, no_smile=True, remake=remake,
                             crop=_boom, ladder=_boom, regenerate=_boom)
        assert res["verdict"] == "PASS" and res["image"].endswith("m2.png"), res
        assert prompts == [G.REGEN_PROMPT, G.REGEN_PROMPT], prompts   # same prompt
        assert [x["verdict"] for x in res["attempts"]] == \
            ["ACCEPT_WITH_FLAG", "ACCEPT_WITH_FLAG", "PASS"]
        G.require_receipt(res["image"])                       # only the neutral one


def test_three_smiling_remakes_stop_for_a_human_pick():
    with tempfile.TemporaryDirectory() as d:
        a = pic(d, "a.png", b"smile")
        n = [0]
        def remake(p, prompt):
            n[0] += 1
            return pic(d, "m%d.png" % n[0], b"m")
        res = G.gate_picture(a, measure=lambda p: SMILING, no_smile=True, remake=remake,
                             crop=_boom, ladder=_boom, regenerate=_boom)
        assert n[0] == G.MAX_REMAKES == 3, n
        assert res["verdict"] == "FAIL" and res["image"].endswith("m3.png"), res
        assert res["reasons"][-1][0] == G.SMILING_CODE, res
        assert "still smiling after 3" in res["reasons"][-1][1], res["reasons"]
        assert [x["verdict"] for x in res["attempts"]][:-1] == ["ACCEPT_WITH_FLAG"] * 3
        refused(G.require_receipt, res["image"])              # never into Kling


def test_no_remake_callable_is_refused_never_accept_with_flag():
    with tempfile.TemporaryDirectory() as d:
        a = pic(d, "a.png", b"smile")
        # a smile with no free fix: refused, and the paid path never fires
        res = G.gate_picture(a, measure=lambda p: SMILING, no_smile=True,
                             crop=_boom, ladder=_boom, regenerate=_boom)
        assert res["verdict"] == "FAIL" and res["reasons"][-1][0] == G.SMILING_CODE, res
        assert "no remake callable" in res["reasons"][-1][1]
        assert res["flags"] and "SMILE" in {c for c, _ in res["flags"]}
        refused(G.require_receipt, a)
        calls = []
        G.gate_picture(a, measure=lambda p: SMILING, no_smile=True, crop=_boom,
                       ladder=_boom,
                       regenerate=lambda p, q: calls.append(q) or pic(d, "r.png"))
        assert calls == [], calls                              # a smile never spends
        # a smile WITH a remake that blows up is refused too, not accepted
        res = G.gate_picture(a, measure=lambda p: SMILING, no_smile=True,
                             remake=lambda p, q: _boom(), crop=_boom, ladder=_boom)
        assert res["verdict"] == "FAIL" and res["reasons"][-1][0] == "REMAKE_FAILED", res
        refused(G.require_receipt, a)


def test_inert_until_wired_a_smile_still_goes_through():
    with tempfile.TemporaryDirectory() as d:
        a = pic(d, "a.png", b"smile")
        # no no_smile= (today's run): the LPG003 calibration stands - the
        # Trevor-approved smiling pictures still reach Kling as flags
        res = G.gate_picture(a, measure=lambda p: SMILING, crop=_boom, ladder=_boom,
                             remake=lambda p, q: _boom())
        assert res["verdict"] == "ACCEPT_WITH_FLAG" and res["image"] == a, res
        assert {c for c, _ in res["flags"]} == {"HEAD_ROLL", "SMILE", "TEETH"}
        assert G.require_receipt(a)["verdict"] == "ACCEPT_WITH_FLAG"


def test_upper_centre_crop_is_916_upper_centre():
    try:
        import cv2
        import numpy as np
    except Exception:
        return                                             # OpenCV not installed here
    with tempfile.TemporaryDirectory() as d:
        src = pic(d, "full.png")
        img = np.zeros((2048, 1152, 3), np.uint8)          # 9:16 2K frame
        img[300:400, 500:600] = 255                        # a marker in the head end
        cv2.imwrite(src, img)
        out = os.path.join(d, "rung.png")
        assert G.upper_centre_crop(src, out, 0.70) == out
        got = cv2.imread(out)
        assert got.shape[:2] == (1433, 806), got.shape      # 9:16, 70% of the width
        assert (got == 255).any()                          # the head end survived
        # a frame the crop cannot hold returns None, never a padded picture
        wide = pic(d, "wide.png")
        cv2.imwrite(wide, np.zeros((2048, 2048, 3), np.uint8))
        assert G.upper_centre_crop(wide, os.path.join(d, "no.png"), 0.70) is None
        assert G.upper_centre_crop(pic(d, "junk.png", b"not an image"),
                                   os.path.join(d, "no.png"), 0.70) is None


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL CHECKS PASS")
