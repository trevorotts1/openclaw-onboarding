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
HOOK_PLAN = {"true_at_beat": "the_world"}   # FU-HOOK-PLACEMENT: hooks measured from the sheet
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
         {"tag": "Verse", "delivery": "sung", "lines": ["One seed of truth made me stro-o-ong,"]},
         {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
         {"tag": "Outro", "delivery": "spoken", "lines": ["She Found Power in the Climb. Get the book. Link below."]}]
req = R.build_request("soul-ballad", SHEET, CLIENT, "T", 58, hook_plan=HOOK_PLAN)
assert SD.validate_request(req, "soul-ballad", CLIENT, 58) == [], SD.validate_request(req, "soul-ballad", CLIENT, 58)
# refusals: spoken word in negatives, missing dry negatives, wrong model, style naming spoken twice
for k, v in (("negative_tags", req["negative_tags"] + ", spoken word"), ("negative_tags", "rap"),
             ("model", "V5"), ("style", req["style"] + " Spoken spoken."), ("style_weight", 0.5)):
    assert SD.validate_request(dict(req, **{k: v}), "soul-ballad", CLIENT, 58), k
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

# FU-HOOK-PLACEMENT: the plan carries the sheet sent to Suno, the style and
# the hook_plan, so the always-on hook_placement gate can measure every take
plan = dict(LF.plan(60, (15, 20)), sheet_text=req["lyrics"], style_id="soul-ballad",
            hook_plan=HOOK_PLAN)
def _suno_words(lyrics):
    """Aligned words the way Suno returns them: each section header rides
    inline on the section's first word (FU-HOOK-PLACEMENT reads them)."""
    out = []
    for block in lyrics.split("\n\n"):
        head, *lines = block.split("\n")
        toks = " ".join(lines).split() or [""]
        out += [{"word": (head + "\n" + t + " ") if k == 0 else t + " "} for k, t in enumerate(toks)]
    return out


words = [dict(w, startS=i, endS=i + 0.5) for i, w in enumerate(_suno_words(req["lyrics"]))]
GOOD = {"segments": [{"delivery": "spoken", "start": 0, "end": 2, "source": "measured"},
                     {"delivery": "sung", "start": 2.5, "end": 45, "source": "measured"},
                     {"delivery": "spoken", "start": 45, "end": 54, "source": "measured"}],
        "aligned_words": [dict(w, startS=3 + i * 1.0, endS=3.5 + i * 1.0) for i, w in enumerate(words)],
        "detector": "singing_detector 2.0.0", "duration_s": 57.5, "music_under_speech_ratio": 0.6,
        "tail_rms_dbfs": -30.0, "first_sung_s": 2.5}
script = "One closed door. She Found Power in the Climb. Get the book. Link below."
hook = " ".join(HOOK)
j = SD.judge_take(GOOD, dict(plan, sheet_text=req["lyrics"]), script, hook, (15, 20))
assert j["verdict"] in ("PASS", "FLAG"), j
# each gate bites
for k, v, gate in (("tail_rms_dbfs", -70.0, "clean_ending"), ("music_under_speech_ratio", 0.05, "music_under_speech"),
                   ("duration_s", 60.0, "length"), ("first_sung_s", 30.0, "first_sung"),
                   ("detector", "singcheck v1", "detector"),
                   ("aligned_words", words[:5], "script_words")):
    r = SD.judge_take(dict(GOOD, **{k: v}), dict(plan, sheet_text=req["lyrics"]), script, hook, (15, 20))
    assert r["verdict"] == "FAIL" and gate in r["failed"], (gate, r)

# FU-HOOK-PLACEMENT: Suno moving/adding a hook earlier than the sheet fails
# the take before any picture spend (the One-Check Chanel v2 shape).
lyr = req["lyrics"]
hook_block = lyr[lyr.index("[Hook 1"):lyr.index("\n\n", lyr.index("[Hook 1"))]
early = lyr.replace("\n\n[Verse", "\n\n" + hook_block + "\n\n[Verse", 1)
EARLY = dict(GOOD, aligned_words=[dict(w, startS=3 + i * 1.0, endS=3.5 + i * 1.0)
                                  for i, w in enumerate(_suno_words(early))])
r = SD.judge_take(EARLY, plan, script, hook, (15, 20), "soul-ballad", lyr)
assert r["verdict"] == "FAIL" and "hook_placement" in r["failed"], r
assert "added at 7.0 s" in r["gates"]["hook_placement"]["detail"], r["gates"]["hook_placement"]
r = SD.judge_take(GOOD, plan, script, hook, (15, 20), "soul-ballad", lyr)
assert r["gates"]["hook_placement"]["verdict"] == "PASS", r["gates"]["hook_placement"]
# the gate never switches itself off: no sheet, style or hook_plan = FAIL, UNMEASURED
bare = {k: v for k, v in plan.items() if k not in ("sheet_text", "style_id", "hook_plan")}
r = SD.judge_take(GOOD, bare, script, hook, (15, 20))
assert "hook_placement" in r["failed"], r
assert r["gates"]["hook_placement"]["detail"] == ("UNMEASURED: sheet_text; UNMEASURED: style_id; "
                                                  "UNMEASURED: hook_plan"), r
# the take is measured against the plan's beat: hook 1 at about 13 s, the
# turn starts at 33.1 s of 58 s
r = SD.judge_take(GOOD, dict(plan, hook_plan={"true_at_beat": "the_turn"}), script, hook, (15, 20))
assert "before 'the_turn' starts at 33.1 s" in r["gates"]["hook_placement"]["detail"], r["gates"]["hook_placement"]
# a true_at_beat that is not a beat, or the opening beat, FAILS the take with
# the same reason the sheet check gives: the story-beat check is never dropped
for beat, why in (("bogus", "is not a beat of the story arc"), ("hook", "never the opener")):
    r = SD.judge_take(GOOD, dict(plan, hook_plan={"true_at_beat": beat}), script, hook, (15, 20))
    assert "hook_placement" in r["failed"], (beat, r["gates"]["hook_placement"])
    assert why in r["gates"]["hook_placement"]["detail"], (beat, r["gates"]["hook_placement"])

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
# FU-HOOK-PLACEMENT: the director's _hook_plan rides the request into run_takes,
# moves into the judge's plan, and never reaches KIE
sent = []
noplan = {k: v for k, v in plan.items() if k != "hook_plan"}
out = SD.run_takes(dict(req, _hook_plan={"true_at_beat": "the_turn"}), noplan,
                   lambda rq: sent.append(rq) or [dict(GOOD), dict(GOOD)], lambda t: {},
                   lambda t, r: None, script, hook, (15, 20), cap_cents=6)
assert sent and all("_hook_plan" not in rq for rq in sent), sent
assert "before 'the_turn'" in out["receipts"][0]["gates"]["hook_placement"]["detail"], out["receipts"][0]
out = SD.run_takes(req, noplan, lambda rq: [dict(GOOD), dict(GOOD)], lambda t: {}, lambda t, r: None,
                   script, hook, (15, 20), cap_cents=6)
assert out["receipts"][0]["gates"]["hook_placement"]["detail"] == "UNMEASURED: hook_plan", out["receipts"][0]
print("ok: song_dispatch")

# load governor wiring: every generation is a NEW request on the 20-per-10-s bucket; a 429 is resubmitted
calls = []
def _kie(fn, label, generation=False):
    calls.append((label, generation))
    r = fn()
    return r if r else _kie(fn, label, generation)
tries = []
def flaky(rq):
    tries.append(1)
    return [] if len(tries) == 1 else [dict(GOOD), dict(GOOD)]
SD.run_takes(req, plan, flaky, lambda t: {}, lambda t, r: None, script, hook, (15, 20), kie=_kie)
assert calls and all(g is True for _, g in calls), calls
import load_governor as LG  # noqa: E402
seen = []
n429 = []
def g429(rq):
    n429.append(1)
    if len(n429) == 1:
        raise RuntimeError("HTTP 429 rate limit")
    return [dict(GOOD), dict(GOOD)]
SD.run_takes(req, plan, g429, lambda t: {}, lambda t, r: None, script, hook, (15, 20),
             kie=lambda fn, label, generation=False: LG.kie_request(fn, label, generation=generation,
                                                                      sleep=lambda s: None, acquire=lambda: seen.append(1)))
assert len(n429) == 2 and len(seen) == 2, (n429, seen)
print("PASS song_dispatch load-governor wiring")
