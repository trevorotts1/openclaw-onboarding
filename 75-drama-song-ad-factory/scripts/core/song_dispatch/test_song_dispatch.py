#!/usr/bin/env python3
"""Run: python3 core/song_dispatch/test_song_dispatch.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "suno_recipe"))
import length_formula as LF  # noqa: E402
import song_dispatch as SD  # noqa: E402
import suno_recipe as R  # noqa: E402

CLIENT = "I am not small. I never was. One seed of truth made me strong. She Found Power in the Climb."
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
         {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
         {"tag": "Verse", "delivery": "sung", "lines": ["One seed of truth made me stro-o-ong,"]},
         {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
         {"tag": "Outro", "delivery": "spoken", "lines": ["She Found Power in the Climb. Get the book. Link below."]}]
req = R.build_request("soul-ballad", SHEET, CLIENT, "T", 58)
assert SD.validate_request(req, "soul-ballad", CLIENT) == [], SD.validate_request(req, "soul-ballad", CLIENT)
# refusals: spoken word in negatives, missing dry negatives, wrong model, style naming spoken twice
for k, v in (("negative_tags", req["negative_tags"] + ", spoken word"), ("negative_tags", "rap"),
             ("model", "V5"), ("style", req["style"] + " Spoken spoken."), ("style_weight", 0.5)):
    assert SD.validate_request(dict(req, **{k: v}), "soul-ballad", CLIENT), k
# the researched negatives and band wording are NOT refused
assert "band dropout" in req["negative_tags"] and "keeps playing" in req["style"]
OAI = "openai-" + "wh" + "isper"
for bad in (OAI, "wh" + "isper", OAI.replace("-", "_")):
    try:
        SD.refuse_asr(bad)
    except SD.DispatchError:
        pass
    else:
        raise AssertionError(bad)
assert SD.refuse_asr("faster-" + "wh" + "isper").startswith("faster-")

plan = LF.plan(60, (15, 20))
words = [{"word": w, "startS": i, "endS": i + 0.5} for i, w in enumerate(
    "one closed door oo-o-oh i am not small i never was one seed of truth made me strong "
    "i am not small i never was i am not small i never was she found power in the climb get the book link below".split())]
GOOD = {"segments": [{"delivery": "spoken", "start": 0, "end": 2, "source": "measured"},
                     {"delivery": "sung", "start": 2.5, "end": 45, "source": "measured"},
                     {"delivery": "spoken", "start": 45, "end": 54, "source": "measured"}],
        "aligned_words": [dict(w, startS=3 + i * 1.0, endS=3.5 + i * 1.0) for i, w in enumerate(words)],
        "detector": "singing_detector 2.0.0", "duration_s": 57.5, "music_under_speech_ratio": 0.6,
        "tail_rms_dbfs": -30.0, "first_sung_s": 2.5}
script = "One closed door. She Found Power in the Climb. Get the book. Link below."
hook = " ".join(HOOK)
j = SD.judge_take(GOOD, plan, script, hook, (15, 20))
assert j["verdict"] in ("PASS", "FLAG"), j
# each gate bites
for k, v, gate in (("tail_rms_dbfs", -70.0, "clean_ending"), ("music_under_speech_ratio", 0.05, "music_under_speech"),
                   ("duration_s", 60.0, "length"), ("first_sung_s", 30.0, "first_sung"),
                   ("detector", "singcheck v1", "detector"),
                   ("aligned_words", words[:5], "script_words")):
    r = SD.judge_take(dict(GOOD, **{k: v}), plan, script, hook, (15, 20))
    assert r["verdict"] == "FAIL" and gate in r["failed"], (gate, r)

# loop: stops at the first pass, saves stem for every take, whole tracks only, cap respected
calls, saved = [], []
seq = [dict(GOOD, detector="singcheck v1")] * 2 + [GOOD, GOOD]
def gen(rq):
    calls.append(rq["duration"]); return [seq[2 * (len(calls) - 1)], seq[2 * (len(calls) - 1) + 1]]
out = SD.run_takes(req, plan, gen, lambda t: {}, lambda t, r: saved.append(r["verdict"]), script, hook, (15, 20))
assert out["verdict"] in ("PASS", "FLAG") and len(calls) == 2 and len(saved) == 3, (out["verdict"], calls, saved)
out = SD.run_takes(req, plan, lambda rq: [dict(GOOD, detector="x")] * 2, lambda t: {}, lambda t, r: saved.append(1),
                   script, hook, cap_cents=18)
assert out["verdict"] == "FAIL" and out["spent_cents"] == 18 and out["delivered"] is None
try:
    SD.run_takes(dict(req, duration=30), plan, gen, lambda t: {}, lambda t, r: None, script, hook)
except SD.DispatchError:
    pass
else:
    raise AssertionError("patch/short duration accepted")
print("ok: song_dispatch")
