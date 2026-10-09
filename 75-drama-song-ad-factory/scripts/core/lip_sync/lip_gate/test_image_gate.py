#!/usr/bin/env python3
"""Lip-sync source-picture gate: refuses loudly before any paid job. $0.
Run: python3 scripts/core/lip_sync/lip_gate/test_image_gate.py"""
import os
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import image_gate as G                                 # noqa: E402
import lip_gate as L                                   # noqa: E402
import picture_gate as PG                              # noqa: E402


def png(w, h):
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IEND", b""))


GOOD = {"face_count": 1, "face_h_pct": 34.0, "roll_deg": 1.0, "yaw_proxy": 0.02,
        "jaw_open": 0.02, "smile": 0.1, "inner_gap_pct": 0.3, "sharp_face_256": 220.0,
        "mouth_occluded": False, "jaw_occluded": False, "light_evenness": 0.9,
        "mouth_hard_shadow": False, "background_separation": 0.4,
        "reference_similarity": 0.93, "provenance": "generated"}
SIZE = (1080, 1920)


def codes(size, a):
    return {c for c, _ in G.check_image(size, a)[0]}


def with_(**kw):
    return dict(GOOD, **kw)


def test_good_picture_passes():
    r, nums = G.check_image(SIZE, GOOD)
    assert r == [], r
    assert nums["face_h_pct"] == 34.0 and nums["flags"] == []


def test_one_rule_set_with_picture_gate():
    # image_gate owns no close-up threshold of its own: the numbers are picture_gate's
    for name in ("FACE_H_ACCEPT", "FACE_H_TARGET", "MAX_ROLL_DEG", "MAX_YAW_DEG",
                 "SMILE_REFUSE", "MIN_SHARPNESS", "CENTER_X", "MAX_MOUTH_OPEN"):
        assert not hasattr(G, name), name
    for a in (with_(face_h_pct=19.0), with_(roll_deg=21.0), with_(yaw_proxy=0.3),
              with_(jaw_open=0.4), with_(sharp_face_256=40.0), with_(face_count=2),
              with_(face_h_pct=24.0, smile=0.7), with_(face_h_pct=80.0)):
        want_pass = not PG.check_numbers(a)[0]
        assert (G.check_image(SIZE, a)[0] == []) == want_pass, a


def test_each_rule_refuses_with_its_own_code():
    cases = [
        ((640, 1138), GOOD, G.RESOLUTION),
        ((1920, 1080), GOOD, G.NOT_PORTRAIT),
        (SIZE, with_(face_h_pct=15.0), G.FACE_SIZE),
        (SIZE, with_(yaw_proxy=0.4), G.NOT_FRONTAL),
        (SIZE, with_(roll_deg=25.0), G.NOT_FRONTAL),
        (SIZE, with_(jaw_open=0.5), G.MOUTH_OPEN),
        (SIZE, with_(mouth_occluded=True), G.OCCLUDED),
        (SIZE, with_(jaw_occluded=True), G.OCCLUDED),
        (SIZE, with_(light_evenness=0.3), G.LIGHT),
        (SIZE, with_(mouth_hard_shadow=True), G.MOUTH_SHADOW),
        (SIZE, with_(background_separation=0.02), G.BACKGROUND),
        (SIZE, with_(reference_similarity=0.4), G.WRONG_CHARACTER),
        (SIZE, with_(sharp_face_256=20.0), G.SOFT),
        (SIZE, with_(provenance="upscaled"), G.CROPPED),
        (SIZE, with_(face_count=0), G.UNMEASURED),
    ]
    for size, a, code in cases:
        assert code in codes(size, a), (code, codes(size, a))


def test_leanne_control_numbers_pass_with_flags():
    # Trevor-approved close-ups that synced: face 21-27% of height, roll 10.5, smile .82
    a = with_(face_h_pct=21.4, roll_deg=10.5, smile=0.82, inner_gap_pct=3.5)
    r, nums = G.check_image((720, 1280), a)
    assert r == [], r
    assert nums["flags"], "small face, tilt, smile and teeth are flags, not silence"


def test_smile_and_teeth_are_flags_never_refusals():
    r, nums = G.check_image(SIZE, with_(smile=0.95, inner_gap_pct=4.0))
    assert r == [] and nums["flags"]
    assert G.check_image(SIZE, with_(smile=0.5))[1]["flags"] == []


def test_crop_allowed_when_it_passes_but_upscale_refused():
    assert G.CROPPED not in codes((720, 1280), with_(provenance="cropped_from_wide"))
    assert G.CROPPED in codes(SIZE, with_(provenance="upscaled"))


def test_unmeasured_is_a_refusal_never_a_pass():
    for k in GOOD:
        a = dict(GOOD)
        del a[k]
        assert G.UNMEASURED in codes(SIZE, a), k
    assert G.UNMEASURED in codes(None, GOOD)
    assert G.UNMEASURED in codes(SIZE, with_(roll_deg=None))


def test_reports_every_reason_at_once():
    c = codes((640, 1138), with_(yaw_proxy=0.4, roll_deg=30.0, sharp_face_256=1.0))
    assert {G.RESOLUTION, G.NOT_FRONTAL, G.SOFT} <= c


def test_file_header_size_and_detector_failure():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.png")
        open(p, "wb").write(png(1080, 1920))
        assert G.image_size(p) == (1080, 1920)
        assert G.check_source_image(p, lambda i: GOOD)["pass"]
        assert G.image_size(os.path.join(d, "none.png")) is None
        bad = G.check_source_image(p, lambda i: 1 / 0)
        assert not bad["pass"] and bad["reasons"][0][0] == G.UNMEASURED
        small = os.path.join(d, "s.png")
        open(small, "wb").write(png(540, 960))     # below 720x1280
        assert not G.check_source_image(small, lambda i: GOOD)["pass"]
        assert G.check_source_image({"path": ""}, lambda i: GOOD)["reasons"][0][0] == G.IMAGE_MISSING


def test_run_gate_refuses_before_any_paid_job():
    spent = []
    gen = lambda provider, spec: spent.append(provider) or "clip"
    meas = lambda clip: {}
    for kw, code in (({}, G.IMAGE_MISSING),
                     ({"source_image": "x.png"}, G.IMAGE_UNCHECKED),
                     ({"source_image": "x.png",
                       "image_check": lambda i: {"pass": False, "reasons": [(G.SOFT, "soft")]}},
                      G.SOFT),
                     ({"source_image": "x.png", "image_check": lambda i: None}, G.UNMEASURED)):
        try:
            L.run_gate("l1", gen, meas, acquire=lambda: None, **kw)
        except G.LipsyncImageRefused as e:
            assert e.reasons[0][0] == code, e.reasons
        else:
            raise AssertionError("did not refuse: %r" % (kw,))
    assert spent == [], "a paid job ran before the picture passed"


def test_prompt_template_carries_every_requirement():
    p = G.closeup_prompt("A tired mother in her thirties, curly brown hair",
                         "soft 3D render", "ref set image 1")
    for need in ("same 3D character", "9:16", "720x1280", "30-40 percent",
                 "straight into the camera",
                 "lips relaxed and very slightly parted",
                 "no big toothy smile", "no hands", "no microphone", "hat brim",
                 "soft even light", "no hard shadow", "separated from the head",
                 "sharp focus", "soft 3D render"):
        assert need in p, need
    try:
        G.closeup_prompt(" ")
    except ValueError:
        pass
    else:
        raise AssertionError


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL CHECKS PASS")
