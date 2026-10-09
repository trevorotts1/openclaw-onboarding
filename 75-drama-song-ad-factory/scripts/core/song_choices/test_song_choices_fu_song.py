#!/usr/bin/env python3
"""FU-SONG-APPROVAL tests: the SONG APPROVAL card question, three labelled songs,
the pick gate, and the extra song price.

Run: python3 core/song_choices/test_song_choices_fu_song.py   (needs ffmpeg + ffprobe)
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for sub in ("", "intake_preflight"):
    sys.path.insert(0, os.path.join(CORE, sub))
from choice_card.intake_card import intake_card as IC          # noqa: E402
from song_choices import song_choices as SC                     # noqa: E402
import length_formula as LF                                     # noqa: E402
import kie_dispatch.kie_dispatch as KD                          # noqa: E402
import factory as F                                             # noqa: E402

N = len(IC.QUESTIONS)
CLIENT = "I am not small. I never was. One seed of truth made me strong. She Found Power in the Climb."
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
         {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
         {"tag": "Verse", "delivery": "sung", "lines": ["One seed of truth made me stro-o-ong,"]},
         {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
         {"tag": "Outro", "delivery": "spoken", "lines": ["She Found Power in the Climb. Get the book. Link below."]}]
PLAN = LF.plan(60, (15, 20))
SCRIPT = "One closed door. She Found Power in the Climb. Get the book. Link below."
HOOKTXT = " ".join(HOOK)
_W = "one closed door oo-o-oh i am not small i never was one seed of truth made me strong " \
     "i am not small i never was i am not small i never was she found power in the climb get the book link below".split()
GOOD = {"segments": [{"delivery": "spoken", "start": 0, "end": 2, "source": "measured"},
                     {"delivery": "sung", "start": 2.5, "end": 45, "source": "measured"},
                     {"delivery": "spoken", "start": 45, "end": 54, "source": "measured"}],
        "aligned_words": [{"word": w, "startS": 3 + i, "endS": 3.5 + i} for i, w in enumerate(_W)],
        "detector": "singing_detector 2.0.0", "duration_s": 57.5, "music_under_speech_ratio": 0.6,
        "tail_rms_dbfs": -30.0, "first_sung_s": 2.5}


def _mp3(path, hz):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=%d:duration=1" % hz, path],
                   check=True, capture_output=True)


def _tag(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=title", "-of",
                          "default=nw=1:nk=1", path], capture_output=True, text=True, check=True).stdout
    return out.strip()


def _pipeline(tmp, bad_first=(), bad_always=()):
    """Run the Yes path with a fake generator. Returns (results, calls, barrier_ok)."""
    reqs = SC.build_requests("rnb-flow", SHEET, CLIENT, "T", 58)
    calls, seen, lock = {}, set(), threading.Lock()
    barrier = threading.Barrier(3, timeout=10)

    def generate(v, rq):
        with lock:
            calls[v["id"]] = calls.get(v["id"], 0) + 1
            k = calls[v["id"]]
        if k == 1:
            barrier.wait()                     # only passes if all three run at the same time
        with lock:
            seen.add(threading.get_ident())
        src = os.path.join(tmp, "%s-%d.mp3" % (v["id"], k))
        _mp3(src, 300 + 100 * len(calls))
        bad = v["id"] in bad_always or (v["id"] in bad_first and k == 1)
        t = dict(GOOD, audio_path=src)
        if bad:
            t["detector"] = "singcheck v1"
        return [t]

    res = SC.generate_choices(reqs, PLAN, generate, lambda t: {}, lambda v, t, r: None,
                              SCRIPT, HOOKTXT, (15, 20))
    return res, calls, len(seen)


def test_card_has_song_approval_after_storyboard():
    labels = [q["label"] for q in IC.QUESTIONS]
    assert N == 7 and labels[-2:] == ["STORYBOARD APPROVAL", "SONG APPROVAL"], labels
    block = IC.render_card().split("\n\n")[6].split("\n")
    assert block[0] == "Question 7 of 7 - SONG APPROVAL"
    assert block[1] == "Do you want to hear and pick the song before any video is made?"
    assert block[2].startswith("1. Yes, send me 3 versions to choose from - ") and IC.REC in block[2]
    assert block[3].startswith("2. No, just make it - ") and IC.REC not in block[3]
    step = IC.conversation(["1"] * 6)["message"]
    assert step.startswith("Question 7 of 7 - SONG APPROVAL") and 'say "recommended".' in step
    assert IC.conversation(["1"] * 6 + ["recommended"])["answers"][6]["n"] == 1


def test_recap_lists_it_and_line_change_works():
    st = IC.conversation(["1"] * 7)
    assert "7. Song Approval: Yes, send me 3 versions to choose from" in st["message"]
    assert IC.song_required(st["answers"]) is True
    fix = IC.conversation(["1"] * 7 + ["7"])
    assert fix["message"].startswith("Question 7 of 7 - SONG APPROVAL")
    no = IC.conversation(["1"] * 7 + ["7", "2"])
    assert IC.song_required(no["answers"]) is False and "7. Song Approval: No, just make it" in no["message"]


def test_three_distinct_variants_per_style_all_pass_the_request_check():
    for style in ("rnb-flow", "soul-ballad", "soul-rise"):
        reqs = SC.build_requests(style, SHEET, CLIENT, "T", 58)
        assert len({rq["style"] for _, rq in reqs}) == 3 and len({v["label"] for v, _ in reqs}) == 3
        assert len({rq["lyrics"] for _, rq in reqs}) == 1        # same lyric sheet
        for v, rq in reqs:
            assert rq["style"].endswith(v["clause"].rstrip(".") + ".")


def test_yes_path_three_labelled_files_titles_readme_and_parallel():
    with tempfile.TemporaryDirectory() as tmp:
        res, calls, threads = _pipeline(tmp)
        assert [r["status"] for r in res] == ["PASS", "PASS", "PASS"] or all(r["status"] in ("PASS", "FLAG") for r in res)
        assert threads == 3 and sorted(calls.values()) == [1, 1, 1]
        run, deliv = os.path.join(tmp, "run"), os.path.join(tmp, "Delivery")
        msg = SC.deliver_choices(res, deliv, run)
        folder = os.path.join(deliv, "SONG-CHOICES")
        names = sorted(f for f in os.listdir(folder) if f.endswith(".mp3"))
        assert len(names) == 3 and [n[:4] for n in names] == ["1 - ", "2 - ", "3 - "]
        for n in names:
            assert _tag(os.path.join(folder, n)) == n[:-4], (n, _tag(os.path.join(folder, n)))
        readme = open(os.path.join(folder, "README.txt")).read().splitlines()
        assert len(readme) == 3 and readme[0].startswith("1 - POLISHED MODERN - 0:58 - ")
        assert "1. POLISHED MODERN" in msg and "2. WARM LIVE BAND" in msg and "3. CINEMATIC STRINGS" in msg
        assert "Reply 1, 2 or 3 to pick your song." in msg


def test_failed_version_regenerated_once_then_reported():
    with tempfile.TemporaryDirectory() as tmp:
        res, calls, _ = _pipeline(tmp, bad_first=("warm-live-band",), bad_always=("cinematic-strings",))
        by = {r["variant"]["id"]: r for r in res}
        assert calls["warm-live-band"] == 2 and by["warm-live-band"]["status"] != "FAILED"
        assert calls["cinematic-strings"] == 2 and by["cinematic-strings"]["status"] == "FAILED"
        msg = SC.deliver_choices(res, os.path.join(tmp, "D"), os.path.join(tmp, "run"))
        assert "Reply 1 or 2 to pick" in msg and "Version 3 did not pass" in msg
        assert len([f for f in os.listdir(os.path.join(tmp, "D", "SONG-CHOICES")) if f.endswith(".mp3")]) == 2
        all_bad = [dict(r, status="FAILED", take=None) for r in res]
        try:
            SC.deliver_choices(all_bad, os.path.join(tmp, "D2"), os.path.join(tmp, "run"))
        except SC.ChoiceError:
            pass
        else:
            raise AssertionError("zero good versions must fail closed")


def _stage_run(tmp, music_done=True):
    run = os.path.join(tmp, "run")
    os.makedirs(os.path.join(run, "control"), exist_ok=True)
    stages = ("research", "creative-strategy", "script-lyrics", "music", "continuity-bible", "storyboard",
              "image-keyframes", "video-generation", "qc-retakes", "assembly", "final-qc", "delivery")
    with sqlite3.connect(os.path.join(run, "control", "state.sqlite3")) as con:
        con.execute("CREATE TABLE stages(run_id TEXT, stage TEXT, state TEXT)")
        for i, s in enumerate(stages):
            con.execute("INSERT INTO stages VALUES('R', ?, ?)", (s, "COMPLETE" if i < (4 if music_done else 3) else "NOT_STARTED"))
    return run


class _A:
    def __init__(self, d):
        self.run_dir = d


def test_gate_blocks_picture_and_paid_jobs_until_pick():
    with tempfile.TemporaryDirectory() as tmp:
        res, _, _ = _pipeline(tmp)
        run = _stage_run(tmp)
        SC.init(run, True)
        SC.deliver_choices(res, os.path.join(tmp, "D"), run)
        env = F.cmd_next(_A(run))
        assert env["outcome"] == "error" and env["reason_code"] == "SONG_PICK_MISSING", env
        assert KD._song_pick_refusal("kling/video", run)["reason_code"] == "SONG_PICK_MISSING"
        assert KD._song_pick_refusal("google/imagen4-fast", run)["reason_code"] == "SONG_PICK_MISSING"
        assert KD._song_pick_refusal("ai-music-api/generate", run) is None      # the song stage itself may run
        for bad in ("4", "", "abc"):
            try:
                SC.record_pick(run, bad)
            except SC.ChoiceError:
                pass
            else:
                raise AssertionError("pick %r accepted" % bad)
        assert KD._song_pick_refusal("kling/video", run) is not None
        label = SC.record_pick(run, "2")
        assert label.startswith("2 - WARM LIVE BAND")
        picked = SC.picked_song(run)
        src = os.path.join(tmp, "D", "SONG-CHOICES", [f for f in os.listdir(os.path.join(tmp, "D", "SONG-CHOICES")) if f.startswith("2 - ")][0])
        assert open(picked, "rb").read() == open(src, "rb").read()
        assert KD._song_pick_refusal("kling/video", run) is None
        env = F.cmd_next(_A(run))
        assert env["outcome"] == "ok" and env["data"]["stage"] == "continuity-bible", env
        with open(picked, "ab") as f:                      # a changed song closes the gate again
            f.write(b"x")
        assert SC.refusal(run)["reason_code"] == "SONG_PICK_MISSING"
        os.remove(picked)
        assert F.cmd_next(_A(run))["reason_code"] == "SONG_PICK_MISSING"


def test_no_path_is_unchanged_and_broken_state_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        run = _stage_run(tmp)
        assert SC.refusal(run) is None and KD._song_pick_refusal("kling/video", run) is None   # no state file
        env = F.cmd_next(_A(run))
        assert env["outcome"] == "ok" and env["data"]["stage"] == "continuity-bible"
        SC.init(run, False)
        assert SC.refusal(run) is None and F.cmd_next(_A(run))["outcome"] == "ok"
        with open(os.path.join(run, "song-choices", "state.json"), "w") as f:
            f.write("{not json")
        assert SC.refusal(run)["reason_code"] == "SONG_PICK_MISSING"
        assert F.cmd_next(_A(run))["outcome"] == "error"


CARD = {"answers": {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad", "length": 60,
                    "video_model": "MiniMax H3 768P"}, "who": "t", "at": "2026-10-09T09:00:00Z"}


def _dispatch(run, model):
    def runner(*a, **k):
        raise AssertionError("a paid call was made")
    return KD.dispatch(model=model, request={"model": model, "input": {"prompt": "p" * 200}, "card_receipt": CARD},
                       save_dir=os.path.join(run, "out"), ledger_db=os.path.join(run, "spend.sqlite3"),
                       run_id="r", logical_key="k", attempt_id="a1", estimated_cost=1,
                       prompt="q" * 200, runner=runner)


def test_kie_dispatch_itself_refuses_before_any_ledger_row_or_call():
    with tempfile.TemporaryDirectory() as tmp:
        run = os.path.join(tmp, "run")
        SC.init(run, True)
        env = _dispatch(run, "google/imagen4-fast")
        assert env["outcome"] == "rejected" and env["reason_code"] == "SONG_PICK_MISSING", env
        assert not os.path.exists(os.path.join(run, "spend.sqlite3"))       # nothing reserved
        SC.init(run, False)                                                  # No answer: not this gate
        try:                                      # past the gate it hits the (absent) ledger instead
            assert _dispatch(run, "google/imagen4-fast").get("reason_code") != "SONG_PICK_MISSING"
        except Exception as e:  # noqa: BLE001
            assert "SONG_PICK_MISSING" not in repr(e)


def test_pick_needs_a_yes_run_and_an_offered_file():
    with tempfile.TemporaryDirectory() as tmp:
        run = os.path.join(tmp, "run")
        f = os.path.join(tmp, "x.mp3")
        _mp3(f, 400)
        SC._write(run, "state.json", {"required": False, "offered": {"1": {"label": "1 - X", "file": f}}})
        try:
            SC.record_pick(run, "1")
        except SC.ChoiceError:
            pass
        else:
            raise AssertionError("a pick was recorded on a No run")
        res, _, _ = _pipeline(tmp)
        SC.init(run, True)
        SC.deliver_choices(res, os.path.join(tmp, "D"), run)
        folder = os.path.join(tmp, "D", "SONG-CHOICES")
        os.remove(os.path.join(folder, [f for f in os.listdir(folder) if f.startswith("1 - ")][0]))
        try:
            SC.record_pick(run, "1")
        except SC.ChoiceError:
            pass
        else:
            raise AssertionError("picked a song whose file is gone")
        assert SC.refusal(run) is not None


def test_card_price_includes_two_extra_songs_when_yes():
    from catalog_calculator import card_render
    resp = json.load(open(os.path.join(CORE, "catalog_calculator", "extensions", "fixtures", "skill74-responses.json")))

    def price(model, units):
        spec = resp.get(model)
        if spec is None:
            return {"state": "fail", "error": {"code": "price_unavailable", "msg": model}}
        unit, tier = spec["unit"], spec["tier_credits"]
        est = round(tier * units, 4) if unit in ("per-second", "per-1k-chars", "per-image", "per-1m-tokens") else round(tier, 4)
        return {"state": "ok", "model_id": model, "warnings": [], "data": {
            "pricing_desc": "x", "credits_min": tier, "credits_max": tier, "unit": unit, "units": units,
            "credits_estimate": est, "preflight_required": round(est * 1.3, 2), "preflight_multiplier": 1.3,
            "price_source": "test"}}

    base, ok1 = card_render.render({}, price)
    yes, ok2 = card_render.render({"song_choices": True}, price)
    assert ok1 and ok2 and "Song picks:" not in base and "Song picks:" in yes
    tot = lambda t: float(t.split("= $")[1].split()[0])
    music = float([l for l in base.splitlines() if l.strip().startswith("Music:")][0].split("$")[-1])
    assert abs((tot(yes) - tot(base)) - 2 * music * 1.2) < 0.02, (tot(yes), tot(base), music)
    assert "added $" in yes
    assert SC.extra_cost_cents() == 2 * SC._SD.GEN_COST_CENTS


if __name__ == "__main__":
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        sys.exit("ffmpeg and ffprobe are required for this suite")
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
