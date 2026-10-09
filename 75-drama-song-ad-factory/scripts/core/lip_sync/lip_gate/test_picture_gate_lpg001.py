#!/usr/bin/env python3
"""LPG001/LPG002: measured close-up gate, auto-fix, face-model install, paid
regeneration through kie_dispatch, bound upload, dispatcher hard block.
$0: the measurer, the transport and the network are all injected.
Run: python3 test_picture_gate_lpg001.py   (passes with an empty HOME)"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, CORE)
import picture_gate as G                               # noqa: E402
import picture_measure as PM                           # noqa: E402
import install_face_model as IM                        # noqa: E402
import kie_dispatch.kie_dispatch as D                  # noqa: E402
import spend_ledger as L                               # noqa: E402

# Measured 2026-10-08 with the mediapipe face landmarker (pic_check.py, read-only).
def N(h, roll, yaw, smile, gap, sharp, jaw=0.0):
    return {"face_count": 1, "face_h_pct": h, "roll_deg": roll, "yaw_proxy": yaw,
            "smile": smile, "jaw_open": jaw, "inner_gap_pct": gap, "sharp_face_256": sharp}


# Trevor-APPROVED lip-sync pictures: every one must PASS or ACCEPT_WITH_FLAG.
APPROVED = {
    "LeAnne CUa": N(26.3, 4.9, 0.067, 0.00, 0.05, 130.4),
    "LeAnne CUb": N(26.7, 5.2, 0.057, 0.11, 3.55, 119.8),
    "LeAnne CUc": N(26.0, 10.5, 0.070, 0.82, 0.24, 133.3),
    "Kiesett HO1": N(21.4, -14.8, -0.145, 0.00, 0.00, 258.1, 0.001),
    "Kiesett HO2": N(23.4, -13.5, -0.142, 0.00, 0.00, 455.0, 0.001),
    "Kiesett HO3": N(23.4, -13.8, -0.106, 0.01, 0.06, 541.9, 0.001),
    "Kiesett ST1 cartoon": N(28.4, -1.4, 0.011, 0.94, 1.66, 1711.1),
}
# today's BSW evidence pictures (30-Day Reset original + crop, Perfect Daughter original + fix)
GOOD = N(37.8, -4.3, -0.045, 0.36, 0.03, 375.1)               # Perfect Daughter fix
RESET_28 = N(28.1, 2.3, 0.018, 0.62, 0.33, 369.3)             # 30-Day Reset original
RESET_CROP = N(36.8, 3.1, 0.020, 0.59, 0.38, 279.5)           # 30-Day Reset crop
DAUGHTER = N(34.4, -7.8, -0.069, 0.83, 1.65, 519.7)           # Perfect Daughter original
BSW = {"BSW 30-Day original": RESET_28, "BSW 30-Day crop": RESET_CROP,
       "BSW Perfect Daughter original": DAUGHTER, "BSW Perfect Daughter fix": GOOD}
# clear problems: each must FAIL
BAD = dict(
    two_faces=dict(GOOD, face_count=2), no_face=dict(GOOD, face_count=0),
    tiny_face=dict(GOOD, face_h_pct=15.0), side_profile=dict(GOOD, yaw_proxy=0.40),
    strong_tilt=dict(GOOD, roll_deg=25.0), wide_mouth=dict(GOOD, jaw_open=0.55),
    very_soft=dict(GOOD, sharp_face_256=30.0))
CARD = {"answers": {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
                    "length": 60, "video_model": "MiniMax H3 768P"},
        "who": "test", "at": "2026-10-08T09:00:00Z"}


def verdict(n):
    fails, flags = G.check_numbers(n)
    return G.FAIL if fails else G.FLAGGED if flags else G.PASS


def codes(n):
    fails, flags = G.check_numbers(n)
    return {c for c, _ in fails}, {c for c, _ in flags}


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


def test_one_rule_set():
    assert (G.REQUIRED_FACE_COUNT, G.MIN_FACE_HEIGHT_PCT, G.MAX_FACE_HEIGHT_PCT,
            G.MAX_ABS_ROLL_DEG, G.MAX_ABS_YAW, G.MAX_JAW_OPEN, G.MIN_SHARPNESS,
            G.FLAG_FACE_HEIGHT_PCT, G.FLAG_ABS_ROLL_DEG, G.FLAG_ABS_YAW, G.FLAG_SMILE,
            G.FLAG_JAW_OPEN, G.FLAG_LIP_GAP_PCT, G.FLAG_SHARPNESS,
            G.MAX_FREE_CROPS, G.MAX_PAID_REGENS) == \
        (1, 20.0, None, 20.0, 0.25, 0.30, 60.0, 25.0, 5.0, 0.12, 0.60, 0.15, 1.0,
         100.0, 1, 2)
    assert G.REGEN_PROMPT == "neutral expression, lips closed, facing camera, head level"
    assert G.REGEN_MODEL == "gpt-image-2-image-to-image"


def test_every_approved_picture_passes_or_flags():
    for name, n in APPROVED.items():
        assert verdict(n) in G.ACCEPTED, (name, G.check_numbers(n))
    assert verdict(APPROVED["LeAnne CUa"]) == G.PASS
    assert codes(APPROVED["LeAnne CUc"]) == (set(), {"HEAD_ROLL", "SMILE"})
    assert codes(APPROVED["LeAnne CUb"]) == (set(), {"HEAD_ROLL", "TEETH"})
    assert codes(APPROVED["Kiesett HO1"]) == (set(), {"FACE_SIZE", "HEAD_ROLL", "HEAD_YAW"})


def test_bsw_evidence_pictures():
    assert verdict(GOOD) == G.PASS and verdict(RESET_CROP) == G.PASS
    assert codes(RESET_28) == (set(), {"SMILE"})               # 28.1% is no longer a failure
    assert codes(DAUGHTER) == (set(), {"HEAD_ROLL", "SMILE", "TEETH"})


def test_only_clear_problems_fail():
    want = dict(two_faces="FACE_COUNT", no_face="FACE_COUNT", tiny_face="FACE_SIZE",
                side_profile="HEAD_YAW", strong_tilt="HEAD_ROLL", wide_mouth="MOUTH_OPEN",
                very_soft="SOFT")
    for k, n in BAD.items():
        assert codes(n)[0] == {want[k]}, (k, G.check_numbers(n))
    # smile and teeth are flags at any size, never a fail
    assert codes(dict(GOOD, smile=1.0, inner_gap_pct=9.0)) == (set(), {"SMILE", "TEETH"})
    # the lines are exact
    assert codes(dict(GOOD, face_h_pct=20.0)) == (set(), {"FACE_SIZE"})
    assert codes(dict(GOOD, face_h_pct=19.9))[0] == {"FACE_SIZE"}
    assert codes(dict(GOOD, face_h_pct=25.0)) == (set(), set())
    assert codes(dict(GOOD, face_h_pct=70.0)) == (set(), set())    # no upper limit
    assert codes(dict(GOOD, roll_deg=-20.0))[0] == set() and codes(dict(GOOD, roll_deg=-20.1))[0]
    assert codes(dict(GOOD, yaw_proxy=0.25))[0] == set() and codes(dict(GOOD, yaw_proxy=0.26))[0]
    assert codes(dict(GOOD, jaw_open=0.30))[0] == set() and codes(dict(GOOD, jaw_open=0.31))[0]
    assert codes(dict(GOOD, sharp_face_256=60))[0] == set() and codes(dict(GOOD, sharp_face_256=59))[0]
    assert codes(dict(GOOD, jaw_open=0.16)) == (set(), {"MOUTH_OPEN"})
    assert codes(dict(GOOD, sharp_face_256=99)) == (set(), {"SOFT"})
    assert "UNMEASURED" in codes({k: v for k, v in GOOD.items() if k != "smile"})[0]


def test_flagged_picture_goes_through_with_flags_and_no_paid_call():
    with tempfile.TemporaryDirectory() as d:
        a = pic(d, "a.png", b"flagged")
        boom = lambda p, q: (_ for _ in ()).throw(AssertionError("paid"))
        res = G.gate_picture(a, measure=lambda p: DAUGHTER, regenerate=boom,
                             crop=lambda p, o: (_ for _ in ()).throw(AssertionError("crop")))
        assert res["verdict"] == "ACCEPT_WITH_FLAG" and res["image"] == a, res
        assert {c for c, _ in res["flags"]} == {"HEAD_ROLL", "SMILE", "TEETH"}
        assert G.require_receipt(a)["verdict"] == "ACCEPT_WITH_FLAG"


def test_tiny_face_one_free_crop_then_passes():
    with tempfile.TemporaryDirectory() as d:
        a = pic(d, "a.png", b"small")
        tiny = BAD["tiny_face"]
        meas = lambda p: RESET_CROP if p.endswith("-crop.png") else tiny if p == a else None
        res = G.gate_picture(a, measure=meas, crop=lambda p, o: pic(d, os.path.basename(o), b"crop"),
                             regenerate=lambda p, q: (_ for _ in ()).throw(AssertionError("paid")))
        assert res["verdict"] == "PASS" and res["image"].endswith("-crop.png"), res
        assert [x["verdict"] for x in res["attempts"]] == ["FAIL", "PASS"]
        G.require_receipt(res["image"])


def test_only_one_free_crop():
    with tempfile.TemporaryDirectory() as d:
        a = pic(d, "a.png", b"small")
        n = []
        def crop(p, o):
            n.append(1)
            return pic(d, os.path.basename(o), b"crop")
        res = G.gate_picture(a, measure=lambda p: BAD["tiny_face"], crop=crop)
        assert res["verdict"] == "FAIL" and len(n) == 1


def test_paid_regen_only_for_a_fail_a_crop_cannot_fix_max_two():
    with tempfile.TemporaryDirectory() as d:
        a = pic(d, "a.png", b"tilt")
        tilt = BAD["strong_tilt"]
        res = G.gate_picture(a, measure=lambda p: tilt)           # no paid fix wired: FAIL
        assert res["verdict"] == "FAIL"
        refused(G.require_receipt, a)
        calls = []
        def regen(p, prompt):
            calls.append(prompt)
            return pic(d, "r%d.png" % len(calls), b"r%d" % len(calls))
        meas = lambda p: GOOD if p.endswith("r2.png") else tilt
        res = G.gate_picture(a, measure=meas, crop=lambda p, o: None, regenerate=regen)
        assert res["verdict"] == "PASS" and calls == [G.REGEN_PROMPT] * 2, calls
        calls.clear()                                             # never passes: capped at 2
        res = G.gate_picture(a, measure=lambda p: tilt, crop=lambda p, o: None, regenerate=regen)
        assert res["verdict"] == "FAIL" and len(calls) == 2, calls
        # a tiny face the crop cannot fix IS a paid regen (crop returned None)
        calls.clear()
        G.gate_picture(a, measure=lambda p: BAD["tiny_face"], crop=lambda p, o: None, regenerate=regen)
        assert len(calls) == 2
        # flags (smile, teeth, tilt under 20, small face over 20) never spend
        calls.clear()
        for flagged in (DAUGHTER, RESET_28, APPROVED["Kiesett HO1"], APPROVED["LeAnne CUc"]):
            G.gate_picture(a, measure=lambda p: flagged, crop=lambda p, o: None, regenerate=regen)
        assert calls == []


def test_missing_mediapipe_or_model_refuses_and_names_install():
    real = PM._deps
    def gone():
        raise PM.PictureGateUnavailable("mediapipe not importable")
    PM._deps = gone
    try:
        with tempfile.TemporaryDirectory() as d:
            a = pic(d)
            res = G.gate_picture(a)
            assert res["verdict"] == "FAIL" and res["reasons"][0][0] == "GATE_UNAVAILABLE"
            refused(G.require_receipt, a)
    finally:
        PM._deps = real
    old = os.environ.get(PM.MODEL_ENV)
    os.environ[PM.MODEL_ENV] = os.path.join(tempfile.gettempdir(), "no-such-model.task")
    try:
        try:
            PM.model_path()
            raise AssertionError("must refuse")
        except PM.PictureGateUnavailable as e:
            assert "install_face_model.py" in str(e), e
    finally:
        os.environ.pop(PM.MODEL_ENV, None)
        if old is not None:
            os.environ[PM.MODEL_ENV] = old


def test_face_model_install_pins_sha256():
    prereqs = json.load(open(os.path.join(HERE, "..", "..", "..", "..", "PREREQS.json")))
    ids = {e["id"]: e for e in prereqs["prerequisites"]}
    # PREREQS type is "manual" (lint-valid); the pinned sha256 lives in its note
    assert IM.MODEL_SHA256 in ids["face-landmarker-model"]["check"]["note"]
    assert "install_face_model.py" in ids["face-landmarker-model"]["satisfy"]
    assert "mediapipe" in ids["python-mediapipe"]["satisfy"]
    assert IM.MODEL_URL.startswith("https://storage.googleapis.com/mediapipe-models/"
                                   "face_landmarker/face_landmarker/float16/latest/")
    data = b"pretend model"
    import hashlib, io
    sha = hashlib.sha256(data).hexdigest()
    opener = lambda url, timeout=0: io.BytesIO(data)
    with tempfile.TemporaryDirectory() as d:
        dest = os.path.join(d, "assets", "face_landmarker.task")
        try:
            IM.install(dest, sha256="0" * 64, opener=opener)         # wrong pin
            raise AssertionError("must refuse a hash mismatch")
        except RuntimeError:
            pass
        assert not os.path.exists(dest) and not os.path.exists(dest + ".part")
        assert IM.install(dest, sha256=sha, opener=opener) == dest   # right pin: placed
        assert open(dest, "rb").read() == data
        assert not IM.is_good(dest)                                  # not the real pinned model


def _fake74(script, calls):
    def run(argv):
        calls.append(list(argv))
        return script[argv[1]]
    return run


def test_default_regenerate_goes_through_dispatch_ledger_and_cap():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "spend.db")
        L.init_run(db, "run1", 10000)
        char = pic(d, "char3d.png", b"3d character")
        out = pic(d, "regen.png", b"neutral")
        calls = []
        run = _fake74({
            "health": (0, {"adapter_mode": "active", "state": "success"}),
            "preflight": (0, {"state": "validated", "data": {"ok": True}}),
            "prompt-budget": (0, {"state": "success", "data": {"status": "OK", "exit_code": 0}}),
            "upload": (0, {"state": "success", "data": {"download_url": "https://k/char.png"}}),
            "submit": (0, {"state": "queued", "task_id": "t1", "raw_family": "market"}),
            "wait": (0, {"state": "success", "task_id": "t1", "raw_family": "market",
                         "credits_consumed": 9}),
            "save": (0, {"state": "success", "task_id": "t1", "saved_paths": [out],
                         "credits_consumed": 9})}, calls)
        regen = G.make_regenerate(char, save_dir=os.path.join(d, "o"), ledger_db=db,
                                  run_id="run1", logical_key="regen", estimated_cost=10,
                                  card_receipt=CARD, adapter_path=os.path.abspath(__file__),
                                  runner=run)
        assert regen("ignored", G.REGEN_PROMPT) == out
        assert [c[1] for c in calls] == ["upload", "health", "preflight", "prompt-budget",
                                         "submit", "wait", "save"], calls
        pre = [c for c in calls if c[1] == "preflight"][0]
        assert G.REGEN_MODEL in pre
        import sqlite3
        row = sqlite3.connect(db).execute(
            "SELECT state, final_outcome, actual_cost FROM jobs WHERE logical_key='regen'").fetchone()
        assert row == ("reconciled", "succeeded", 9), row          # reserved + settled on the ledger
        # the author's cap is enforced: a cap of 5 refuses a 10-credit regeneration
        db2 = os.path.join(d, "cap.db")
        L.init_run(db2, "run2", 5)
        calls.clear()
        regen2 = G.make_regenerate(char, save_dir=d, ledger_db=db2, run_id="run2",
                                   logical_key="regen", estimated_cost=10, card_receipt=CARD,
                                   adapter_path=os.path.abspath(__file__), runner=run)
        try:
            regen2("x", G.REGEN_PROMPT)
            raise AssertionError("over-cap regeneration must fail")
        except G.RegenerationFailed:
            pass
        assert "submit" not in [c[1] for c in calls]
        # and gate_picture turns that failure into a refusal, not a pass
        a = pic(d, "a.png", b"smile")
        res = G.gate_picture(a, measure=lambda p: BAD["strong_tilt"], regenerate=regen2)
        assert res["verdict"] == "FAIL" and res["reasons"][-1][0] == "REGEN_FAILED"


def test_real_transport_rides_load_governor_kie_request():
    seen = []
    real_kr, real_run = D._LG.kie_request, D.subprocess.run
    def spy(fn, label="kie", **kw):
        seen.append((label, kw.get("generation")))
        return real_kr(fn, label, **dict(kw, acquire=lambda: None))
    class R:
        returncode, stdout = 0, json.dumps({"state": "success",
                                            "data": {"download_url": "https://k/x.png"}})
    D._LG.kie_request, D.subprocess.run = spy, lambda *a, **k: R()
    try:
        url = G.adapter_uploader(adapter_path=os.path.abspath(__file__))("/tmp/x.png")
    finally:
        D._LG.kie_request, D.subprocess.run = real_kr, real_run
    assert url == "https://k/x.png" and len(seen) == 1 and seen[0][1] is False, seen


def test_upload_is_bound_to_the_measured_bytes():
    with tempfile.TemporaryDirectory() as d:
        a = pic(d, data=b"v1")
        refused(G.upload_measured, a, lambda f: "https://k/a.png")      # no receipt: no upload
        G.gate_picture(a, measure=lambda p: GOOD)
        sent = []
        def up(f):
            sent.append(open(f, "rb").read())
            return "https://k/a.png"
        url = G.upload_measured(a, up)
        assert url == "https://k/a.png" and sent == [b"v1"]
        G.require_upload_bound(a, url)
        refused(G.require_upload_bound, a, "https://k/other.png")        # some other URL
        refused(G.require_upload_bound, a, None)
        # bytes that differ at upload time from the measured ones are refused
        import shutil
        real = shutil.copyfile
        def swap(src, dst):
            real(src, dst)
            open(dst, "wb").write(b"swapped")
        shutil.copyfile = swap
        try:
            msg = refused(G.upload_measured, a, lambda f: "https://k/b.png")
        finally:
            shutil.copyfile = real
        assert "changed between measuring and upload" in msg
        open(a, "wb").write(b"v2")                                       # edited after the receipt
        refused(G.require_receipt, a)


def _req(a=None, url=None, **kw):
    r = {"input": {"prompt": "p"}}
    if a:
        r["lipsync_image_path"] = a
    if url:
        r["input"]["image_url"] = url
    return dict(r, **kw)


def _dispatch(d, model, request, **kw):
    return D.dispatch(model=model, request=request, save_dir=d,
                      ledger_db=os.path.join(d, "l.db"), run_id="r", logical_key="k",
                      attempt_id="a", estimated_cost=1, **kw)


def test_dispatcher_hard_block():
    with tempfile.TemporaryDirectory() as d:
        a = pic(d)
        env = _dispatch(d, "kling/ai-avatar-standard", _req(a, "https://k/a.png"))
        assert env["reason_code"] == "LIPSYNC_PICTURE_NOT_GATED", env
        assert env["outcome"] == "rejected" and env["evidence"]["generated"] is False
        m = "kling/ai-avatar-standard"
        for other in ("kling/ai-avatar-pro", "infinitalk/from-audio"):   # same block, called directly
            assert D.lipsync_picture_refusal(other, _req(a, "https://k/a.png"))
        assert D.lipsync_picture_refusal(m, _req())                       # no path at all
        G.gate_picture(a, measure=lambda p: BAD["tiny_face"])             # FAIL receipt
        assert D.lipsync_picture_refusal(m, _req(a, "https://k/a.png"))
        G.gate_picture(a, measure=lambda p: GOOD)                         # PASS receipt
        assert D.lipsync_picture_refusal(m, _req(a, "https://k/a.png"))   # but not uploaded/bound
        url = G.upload_measured(a, lambda f: "https://k/a.png")
        assert D.lipsync_picture_refusal(m, _req(a, url)) is None         # measured + bound: go
        assert D.lipsync_picture_refusal(m, _req(a, "https://k/evil.png"))  # some other image
        assert D.lipsync_picture_refusal(m, _req(a))                      # no image_url
        assert D.lipsync_picture_refusal("kling-3.0/video", _req()) is None   # not lip-sync
        G.gate_picture(a, measure=lambda p: DAUGHTER)                     # ACCEPT_WITH_FLAG receipt
        url = G.upload_measured(a, lambda f: "https://k/b.png")
        assert D.lipsync_picture_refusal(m, _req(a, url)) is None         # a flagged picture goes


def test_f14_real_lipsync_dispatch_reaches_the_picture_gate():
    """F14 treated kling/ai-avatar-* as an off-menu VIDEO model (MODEL_NOT_ON_MENU).
    Nothing is stubbed: the real model lock, the real price-menu.md, the real dispatch."""
    import kie_dispatch.model_lock as ML
    m = "kling/ai-avatar-standard"
    assert ML.is_locked_lipsync(m) and not ML.is_locked_lipsync("kling/ai-avatar-pro")
    with tempfile.TemporaryDirectory() as d:
        a = pic(d)
        # 1. no receipt: the picture gate answers, not the menu lock
        env = _dispatch(d, m, _req(a, "https://k/a.png"))
        assert env["reason_code"] == "LIPSYNC_PICTURE_NOT_GATED", env
        # 2. gated + bound: it gets past F14 and the picture gate (never MODEL_NOT_ON_MENU,
        #    VIDEO_MODEL_LOCK_MISSING or the picture gate); it stops later, in front of no runner
        G.gate_picture(a, measure=lambda p: GOOD)
        url = G.upload_measured(a, lambda f: "https://k/a.png")
        env = _dispatch(d, m, _req(a, url), runner=lambda argv: (1, {}, "stop"))
        assert env["reason_code"] not in ("MODEL_NOT_ON_MENU", "VIDEO_MODEL_LOCK_MISSING",
                                          "VIDEO_MODEL_MISMATCH", "LIPSYNC_PICTURE_NOT_GATED"), env
        # 3. the lock is still shut for every other off-menu video model
        for other in ("kling/ai-avatar-pro", "bytedance/seedance-1.5-pro"):
            env = _dispatch(d, other, _req(a, "https://k/a.png"))
            assert env["reason_code"] == "MODEL_NOT_ON_MENU", (other, env)


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL CHECKS PASS")
