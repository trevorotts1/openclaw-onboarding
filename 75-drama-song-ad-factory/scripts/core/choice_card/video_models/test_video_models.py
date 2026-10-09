#!/usr/bin/env python3
"""FU-VIDEO-MODEL-CHOICES tests. Zero paid calls: Skill 74 is a fake runner.

Run: python3 core/choice_card/video_models/test_video_models.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, CORE)

from choice_card.intake_card import intake_card as IC  # noqa: E402
from choice_card.video_models import video_models as VM  # noqa: E402
import kie_dispatch as D  # noqa: E402
import kie_dispatch.model_lock as ML  # noqa: E402
import spend_ledger as L  # noqa: E402
from catalog_calculator import card_render as CR  # noqa: E402

NAMES = ["MiniMax H3", "Seedance 2.5", "Seedance 2.0 Mini", "Google Veo 3.1"]


def _model_turn(length_reply):
    return IC.conversation(["1", length_reply, "1", "1"])["message"]


def _fake74(model, units):
    """Skill 74 stand-in. Video is deliberately priced at the HIGHEST tier (the
    real `price` behaviour) so a card that leaked it would not match the question."""
    if model.startswith("google/imagen"):
        return {"state": "ok", "data": {"credits_estimate": 4.0 * units, "unit": "per-image"}}
    if model.startswith("ai-music-api"):
        return {"state": "ok", "data": {"credits_estimate": 12.0, "unit": "per-job"}}
    return {"state": "ok", "data": {"credits_estimate": 999.0 * units, "unit": "per-second"}}


def _half_up(num, den):
    return (2 * num + den) // (2 * den)


def _expect(rate, per_clip, shot_s, seconds):
    """Independent restatement of the card, in whole cents: video + (7 character
    reference pictures + 1 keyframe per shot) at 2c + song 6c, then +20% half-up."""
    shots = -(-seconds // shot_s)
    mills = round(rate * 1000) * (shots if per_clip else seconds)
    total = _half_up(mills, 10) + 2 * (shots + 7) + 6
    return total + _half_up(total * 20, 100)


EXPECT = {  # (rate, per_clip, shot_s) -> the four models in order
    "MiniMax H3": (0.04, False, 15), "Seedance 2.5": (0.315, False, 15),
    "Seedance 2.0 Mini": (0.041, False, 15), "Google Veo 3.1": (0.30, True, 8)}
LENGTHS = (("1", 60, "60 seconds"), ("3", 180, "3 minutes"))


def _card_total(n, label, price_fn, **kw):
    """The final card's spending line: the number after the last '=' on Total."""
    text, ok = CR.render({"length": label, "video_model": n}, price_fn, **kw)
    assert ok, text
    return text, next(l for l in text.split("\n") if "Total:" in l).rsplit("= $", 1)[1]


def _question_price(reply, name):
    msg = _model_turn(reply)
    line = next(l for l in msg.split("\n") if l[3:].startswith(name + " - "))
    return line.split("about $")[1].split(" ")[0]


def test_four_options_in_order_h3_first_and_recommended():
    msg = _model_turn("1")
    opts = [l for l in msg.split("\n") if l[:2] in ("1.", "2.", "3.", "4.")]
    assert len(opts) == 4, msg
    for line, name in zip(opts, NAMES):
        assert line[3:].startswith(name + " - "), line
    assert "(RECOMMENDED)" in opts[0] and sum("(RECOMMENDED)" in l for l in opts) == 1
    assert "I recommend option 1 (MiniMax H3)" in msg
    assert "Prices are for your 60-second ad" in msg


def test_question_price_equals_final_card_total_all_models_60s_and_3min():
    for reply, secs, label in LENGTHS:
        for n, name in enumerate(NAMES, 1):
            q = _question_price(reply, name)
            _text, card = _card_total(n, label, _fake74)
            assert q == card, (name, label, q, card)
            cents = _expect(*EXPECT[name], secs)
            assert q == "%d.%02d" % (cents // 100, cents % 100), (name, label, q, cents)


def test_question_price_equals_card_with_real_skill_74_registry_prices():
    pf = CR.price_fn_default()
    if pf is None:
        return  # no Skill 74 beside this skill: nothing to compare
    for reply, _secs, label in LENGTHS:
        for n, name in enumerate(NAMES, 1):
            assert _question_price(reply, name) == _card_total(n, label, pf)[1], (name, label)


def test_recap_line_is_plain_and_priced():
    msg = IC.conversation(["1", "3", "1", "1", "2", "$25", "1", "1", "1"])["message"]
    cents = _expect(*EXPECT["Seedance 2.5"], 180)
    assert "5. Video model: Seedance 2.5 - about $%d.%02d" % (cents // 100, cents % 100) in msg, msg


def test_changing_length_reprices_the_recap():
    # nine answers (60 s, Seedance 2.5), recap, change line 2 (length), pick 3 minutes
    msg = IC.conversation(["1", "1", "1", "1", "2", "$25", "1", "1", "1", "2", "3"])["message"]
    cents = _expect(*EXPECT["Seedance 2.5"], 180)
    assert "5. Video model: Seedance 2.5 - about $%d.%02d" % (cents // 100, cents % 100) in msg, msg


# ---- payload tests: lock -> dispatch -> the request Skill 74 would submit ----

#: input fields and enums from the live createTask schemas (Skill 74 `schema`, 2026-10-09)
SCHEMA = {
    "minimax-h3/image-to-video": {"prompt", "first_frame_url", "last_frame_url", "duration", "resolution"},
    "bytedance/seedance-2-5": {"prompt", "first_frame_url", "last_frame_url", "resolution", "aspect_ratio",
                               "generate_audio", "duration"},
    "bytedance/seedance-2-mini": {"prompt", "first_frame_url", "last_frame_url", "resolution", "aspect_ratio",
                                  "generate_audio", "duration"},
    "veo-3-1": {"prompt", "model", "image_urls", "generation_type", "aspect_ratio", "resolution", "duration"},
}


class Fake74:
    def __init__(self):
        self.submitted = None

    def __call__(self, argv):
        sub = argv[1]
        if sub == "submit":
            with open(argv[argv.index("--request") + 1], encoding="utf-8") as f:
                self.submitted = json.load(f)
            return 0, {"state": "queued", "task_id": "t-1", "raw_family": "market"}
        if sub == "wait":
            return 0, {"state": "success", "task_id": "t-1", "credits_consumed": 10}
        if sub == "save":
            return 0, {"state": "success", "task_id": "t-1", "saved_paths": ["/x.mp4"]}
        if sub == "health":
            return 0, {"adapter_mode": "active", "state": "success"}
        if sub == "preflight":
            return 0, {"state": "validated", "data": {"ok": True}}
        if sub == "prompt-budget":
            return 0, {"state": "success", "data": {"status": "OK", "exit_code": 0, "max": 20000}}
        raise AssertionError("unexpected Skill 74 call %r" % sub)


def _dispatch_choice(n, first_frame=None):
    """Lock choice n, build its request, dispatch through the factory. -> (envelope, submitted)."""
    m = VM.model_for(n)
    tmp = tempfile.mkdtemp(prefix="vm-")
    state, ledger = os.path.join(tmp, "state.db"), os.path.join(tmp, "spend.db")
    L.init_run(ledger, "run-vm", 10000)
    IC.conversation(["1", "1", "1", "1", str(n)], state_store=state, run_id="run-vm")   # the client answers; run state is written
    req = VM.request_for_run(state, "run-vm", "A woman sings at a kitchen window. " * 6, 8, "9:16", first_frame)
    req["storyboard"] = {"shots": [{"shot_id": "s1", "status": "storyboard_approved"}],
                         "review": {"outcome": "pass", "reason_code": "storyboard-accepted"}}
    req["card_receipt"] = {"answers": {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
                                       "length": 60, "video_model": m["name"]},
                           "who": "FU-VIDEO-MODEL-CHOICES test", "at": "2026-10-09T09:00:00Z"}
    import hashlib
    req["prompt_receipt"] = {"prompt_sha256": hashlib.sha256(req["input"]["prompt"].encode("utf-8")).hexdigest(),
                             "check": {"verdict": "PASS", "reasons": []}}  # H3 only; others ignore it
    fake = Fake74()
    env = D.dispatch(model=req["model"], request=req, save_dir=os.path.join(tmp, "out"),
                     ledger_db=ledger, run_id="run-vm", logical_key="k%d" % n, attempt_id="a1",
                     estimated_cost=100, prompt=req["input"]["prompt"], adapter_path=__file__,
                     runner=fake, state_store=state, video_job=True)
    return env, fake.submitted


def _check_fields(submitted):
    fields = SCHEMA[submitted["model"]]
    extra = set(submitted["input"]) - fields
    assert not extra, "fields the provider schema does not have: %s" % sorted(extra)


def test_payload_seedance_2_5():
    env, sub = _dispatch_choice(2, "https://example.invalid/f.png")
    assert env["outcome"] == "ok", env
    assert sub["model"] == "bytedance/seedance-2-5"
    assert sub["input"]["resolution"] == "720p" and sub["input"]["duration"] == 8
    assert sub["input"]["generate_audio"] is False and sub["input"]["aspect_ratio"] == "9:16"
    assert sub["input"]["first_frame_url"] == "https://example.invalid/f.png"
    _check_fields(sub)


def test_payload_seedance_2_mini():
    env, sub = _dispatch_choice(3)
    assert env["outcome"] == "ok", env
    assert sub["model"] == "bytedance/seedance-2-mini"
    assert sub["input"]["resolution"] == "720p" and sub["input"]["generate_audio"] is False
    assert "first_frame_url" not in sub["input"]
    _check_fields(sub)


def test_payload_google_veo_3_1_fast():
    env, sub = _dispatch_choice(4, "https://example.invalid/f.png")
    assert env["outcome"] == "ok", env
    assert sub["model"] == "veo-3-1" and sub["input"]["model"] == "veo3_fast"
    assert sub["input"]["generation_type"] == "FIRST_AND_LAST_FRAMES_2_VIDEO"
    assert sub["input"]["image_urls"] == ["https://example.invalid/f.png"]
    assert sub["input"]["resolution"] == "720p" and sub["input"]["duration"] == 8
    _check_fields(sub)


def test_payload_h3_unchanged():
    env, sub = _dispatch_choice(1)
    assert env["outcome"] == "ok", env
    assert sub["model"] == "minimax-h3/image-to-video" and sub["input"]["resolution"] == "768P"


def test_unsupported_durations_refused_before_any_call():
    for n, d in ((4, 5), (4, 9), (2, 31), (3, 16)):
        try:
            VM.build_request(VM.model_for(n), "p", d)
        except ValueError:
            continue
        raise AssertionError("duration %s accepted for choice %s" % (d, n))


def test_client_pick_reaches_card_row_and_dispatch_payload_for_every_model():
    want = {1: ("minimax-h3/image-to-video", "768P", "MiniMax H3 768P (RECOMMENDED)"),
            2: ("bytedance/seedance-2-5", "720p", "Seedance 2.5 720p"),
            3: ("bytedance/seedance-2-mini", "720p", "Seedance 2.0 Mini 720p"),
            4: ("veo-3-1", "720p", "Google Veo 3.1 720p")}
    for n, (kie, res, row) in want.items():
        env, sub = _dispatch_choice(n)
        assert env["outcome"] == "ok" and sub["model"] == kie and sub["input"]["resolution"] == res, (n, env, sub)
        tmp = tempfile.mkdtemp(prefix="vm-")
        state = os.path.join(tmp, "state.db")
        IC.conversation(["1", "1", "1", "1", str(n)], state_store=state, run_id="r")
        text, _ok = CR.render({"length": "60 seconds"}, _fake74, state_store=state, run_id="r")   # no card field: run state decides
        assert "Video model: %s" % row in " ".join(text.split()), text


def test_dispatch_stamps_the_chosen_resolution_over_a_wrong_one():
    tmp = tempfile.mkdtemp(prefix="vm-")
    state = os.path.join(tmp, "state.db")
    IC.conversation(["1", "1", "1", "1", "2"], state_store=state, run_id="r")
    req = {"model": "bytedance/seedance-2-5", "input": {"prompt": "x", "duration": 8, "resolution": "1080p"}}
    assert VM.apply_locked_choice(req, ML.read_locked_model(state, "r"))["input"]["resolution"] == "720p"


def test_a_run_locked_to_one_model_refuses_another():
    tmp = tempfile.mkdtemp(prefix="vm-")
    state = os.path.join(tmp, "state.db")
    VM.lock_choice(state, "r", 3)
    locked = ML.read_locked_model(state, "r")
    assert locked == "bytedance/seedance-2-mini"
    assert not ML.matches_family("veo-3-1", locked) and not ML.matches_family("bytedance/seedance-2-5", locked)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print("ALL PASS" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
