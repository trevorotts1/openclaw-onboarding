#!/usr/bin/env python3
"""LPG001: the dispatcher refuses ANY lip-sync job without a PASS picture
receipt for that exact file; the paid runner is never reached. $0.
Run: python3 core/kie_dispatch/test_picture_gate_dispatch.py"""
import json
import os
import sqlite3
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import kie_dispatch as D                                   # noqa: E402
import importlib                                            # noqa: E402
import spend_ledger as L                                   # noqa: E402
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


M = importlib.import_module("kie_dispatch.kie_dispatch")      # private names live here
CARD = {"answers": {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad", "length": 60,
                    "video_model": "MiniMax H3 768P"}, "who": "t", "at": "2026-10-08T09:00:00Z"}
URL = "https://tmp.example.invalid/uploaded.png"


class Fake74:
    """Stands in for Skill 74. on_upload(copy_path) may tamper with the uploaded copy."""

    def __init__(self, on_upload=None, upload_ok=True):
        self.calls, self.sent, self.uploaded = [], [], []
        self.on_upload, self.upload_ok = on_upload, upload_ok

    def __call__(self, argv):
        sub = argv[1]
        self.calls.append(sub)
        if sub == "health":
            return 0, {"adapter_mode": "active", "state": "success"}
        if sub == "preflight":
            return 0, {"state": "validated", "data": {"ok": True}}
        if sub == "prompt-budget":
            return 0, {"state": "success", "data": {"status": "OK", "exit_code": 0, "max": 20000}}
        if sub == "upload":
            f = argv[argv.index("--file") + 1]
            self.uploaded.append((f, open(f, "rb").read()))
            if self.on_upload:
                self.on_upload(f)
            return (0, {"state": "success", "data": {"download_url": URL}}) if self.upload_ok \
                else (1, {"state": "fail", "error": {"code": "bad_file"}})
        if sub == "submit":
            self.sent.append(json.load(open(argv[argv.index("--request") + 1])))
            return 0, {"state": "queued", "task_id": "t1"}
        if sub == "wait":
            return 0, {"state": "success", "task_id": "t1", "credits_consumed": 16}
        if sub == "save":
            out = os.path.join(argv[argv.index("--save-dir") + 1], "regen.png")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(b"regenerated")
            return 0, {"state": "success", "saved_paths": [out], "credits_consumed": 16}
        raise AssertionError("unexpected Skill 74 call " + sub)


def gated(d, data=b"pic"):
    img = os.path.join(d, "c.png")
    open(img, "wb").write(data)
    P.gate_picture(img, lambda _: dict(GOOD))
    return img


def lip_dispatch(d, img, fake, cap=10000):
    db = os.path.join(d, "l.db")
    L.init_run(db, "r", cap)
    # The F14 video-menu lock is a separate, older gate (kling/ai-avatar is not a menu video model);
    # stub it so these tests reach the upload step this PR adds.
    real = M._is_menu_video, M._modality
    M._is_menu_video, M._modality = (lambda m, _p=None: False), (lambda m, a=None: "image")
    try:
        env = D.dispatch(model="kling/ai-avatar-standard",
                         request={"model": "kling/ai-avatar-standard", "card_receipt": CARD,
                                  "input": {"image_url": img, "prompt": "p" * 200}},
                         save_dir=os.path.join(d, "out"), ledger_db=db, run_id="r", logical_key="k",
                         attempt_id="a", estimated_cost=10, prompt="q" * 200,
                         adapter_path=os.path.abspath(__file__), runner=fake)
    finally:
        M._is_menu_video, M._modality = real
    return env, db


def test_upload_is_bound_to_the_exact_measured_file():
    d = tempfile.mkdtemp()
    img = gated(d)
    fake = Fake74()
    env, _ = lip_dispatch(d, img, fake)
    assert env["outcome"] == "ok", env
    assert fake.uploaded[0][1] == b"pic" and fake.uploaded[0][0] != img       # the measured bytes, via a private copy
    sent = fake.sent[0]["input"]
    assert sent["image_url"] == URL and img not in json.dumps(fake.sent[0])    # Kling gets the upload, never a local path
    assert env["evidence"]["lipsync_image_sha256"] == P.sha256_file(img)
    assert fake.calls.index("upload") < fake.calls.index("submit")


def test_file_swapped_during_upload_is_refused_before_submit():
    d = tempfile.mkdtemp()
    img = gated(d)
    fake = Fake74(on_upload=lambda f: open(f, "ab").write(b"swapped"))
    env, db = lip_dispatch(d, img, fake)
    assert env["outcome"] == "rejected" and env["reason_code"] == "LIPSYNC_PICTURE_UPLOAD_MISMATCH", env
    assert "submit" not in fake.calls
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT actual_cost FROM jobs").fetchone()[0] in (0, None)   # reservation settled at zero


def test_hash_at_upload_time_must_equal_the_measured_hash():
    d = tempfile.mkdtemp()
    img = gated(d)
    try:
        M._upload_exact(Fake74(), "adapter", img, d, want_sha="0" * 64)
    except M.UploadBindingError as e:
        assert e.code == "LIPSYNC_PICTURE_UPLOAD_MISMATCH"
    else:
        raise AssertionError("mismatch must refuse")
    assert M._upload_exact(Fake74(), "adapter", img, d, want_sha=P.sha256_file(img))[0] == URL


def test_upload_failure_is_a_refusal():
    d = tempfile.mkdtemp()
    fake = Fake74(upload_ok=False)
    env, _ = lip_dispatch(d, gated(d), fake)
    assert env["reason_code"] == "LIPSYNC_PICTURE_UPLOAD_FAILED" and "submit" not in fake.calls


def _regen_ctx(d, fake, cap=10000, cost=16):
    db = os.path.join(d, "r.db")
    L.init_run(db, "run", cap)
    character = os.path.join(d, "character3d.png")
    open(character, "wb").write(b"3d character")
    return dict(character_image=character, save_dir=os.path.join(d, "regen"), ledger_db=db, run_id="run",
                estimated_cost=cost, request_extra={"card_receipt": CARD}, runner=fake,
                adapter_path=os.path.abspath(__file__)), db


def test_default_regenerate_goes_through_dispatch_and_the_ledger():
    d = tempfile.mkdtemp()
    fake = Fake74()
    ctx, db = _regen_ctx(d, fake)
    out = D.make_picture_regenerator(**ctx)(os.path.join(d, "failed.png"), P.REGEN_PROMPT)
    assert open(out, "rb").read() == b"regenerated"
    req = fake.sent[0]
    assert req["model"] == "gpt-image-2-image-to-image" and req["input"]["prompt"] == P.REGEN_PROMPT
    assert req["input"]["input_urls"] == [URL] and fake.uploaded[0][1] == b"3d character"
    row = sqlite3.connect(db).execute("SELECT logical_key, state, actual_cost FROM jobs").fetchall()
    assert len(row) == 1 and row[0][0] == "lipsync-picture-regen-1" and row[0][2] == 16, row


def test_regenerate_reserves_against_the_cap_and_refuses_over_it():
    d = tempfile.mkdtemp()
    fake = Fake74()
    ctx, db = _regen_ctx(d, fake, cap=10, cost=16)           # cap 10 credits < one regeneration
    try:
        D.make_picture_regenerator(**ctx)(os.path.join(d, "failed.png"), P.REGEN_PROMPT)
    except P.PictureRefused as e:
        assert e.reasons[0][0] == "PICTURE_REGEN_FAILED"
    else:
        raise AssertionError("over-cap regeneration must refuse")
    assert "submit" not in fake.calls


def test_fix_picture_default_regenerate_two_tries_then_refuse_through_the_ledger():
    d = tempfile.mkdtemp()
    fake = Fake74()
    ctx, db = _regen_ctx(d, fake)
    pic = os.path.join(d, "smile.png")
    open(pic, "wb").write(b"smile")
    smiling = dict(GOOD, smile=0.83)
    try:
        P.fix_picture(pic, measure=lambda p: dict(smiling), crop=lambda p, o, n: p, dispatch_ctx=ctx)
    except P.PictureRefused:
        pass
    else:
        raise AssertionError("must refuse after two paid tries")
    assert fake.calls.count("submit") == 2
    assert len(sqlite3.connect(db).execute("SELECT 1 FROM jobs").fetchall()) == 2


def test_regenerate_submit_rides_load_governor_kie_request():
    d = tempfile.mkdtemp()
    ctx, db = _regen_ctx(d, None)
    ctx.pop("runner")
    fake, seen = Fake74(), []
    real_req, real_run = M._LG.kie_request, M.subprocess.run

    def kr(fn, label="kie", **kw):
        seen.append((label, kw.get("generation")))
        return fn()

    def sp(argv, **kw):
        rc, out = fake(argv[1:])
        return types.SimpleNamespace(returncode=rc, stdout=json.dumps(out))

    M._LG.kie_request, M.subprocess.run = kr, sp
    try:
        D.make_picture_regenerator(**ctx)(os.path.join(d, "failed.png"), P.REGEN_PROMPT)
    finally:
        M._LG.kie_request, M.subprocess.run = real_req, real_run
    assert any(l.startswith("submit") and g is True for l, g in seen), seen


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL CHECKS PASS")
