#!/usr/bin/env python3
"""FU-RNBFLOW-SONG: the music style's own definition, enforced.

Replays the One-Check 150 s R&B Flow sheets (v1: one 4-word hook
sung 6 times, 254 words tagged rap with no rap cue; v2: the same hook line
doubled, Suno returned 9 hook blocks) -- both must FAIL with the reason --
and a proper R&B Flow sheet at the same length (build-up before the first
hook, every chorus = the hook plus another line) must PASS the contract.
The six golden sheets must PASS song_contract and guard_request (the merged
gate: recipe + hook placement + contract), and the story beat is MEASURED:
the proper sheet cut to its first 3 hooks (first hook about a quarter in)
FAILS a plan whose words only become true at the turn.
Every test ends with ``assert not FAILS`` so pytest fails it too.

Fixtures:
  ../suno_recipe/fixtures/one-check-lyrics.txt   v1 sheet (byte-identical
                                                  to the run's song/lyrics.txt)
  fixtures/one-check-v2-lyrics.txt               v2 sheet
  fixtures/one-check-v1-g1b-take.json            v1 take g1b: Suno aligned words
  fixtures/one-check-v2-g2a-take.json            v2 take g2a: Suno aligned words
                                                  + singing_detector sung stretches
  fixtures/rnb-flow-150-pass.txt                 a proper R&B Flow 150 s sheet

Run: python3 core/song_contract/test_song_contract.py
stdlib only, no network, no spend, no speech-to-text.
"""
from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

import song_contract as SC       # noqa: E402
import song_dispatch as SD       # noqa: E402
import prompt_templates as PT   # noqa: E402
import spoken_share as SS        # noqa: E402
import suno_recipe as R          # noqa: E402
from sung_hook import hook_placement as HP   # noqa: E402

FIX = os.path.join(HERE, "fixtures")
D = 148                                    # 150 s ordered, delivered L - 2
CLIENT = ("Girl, I got you. You will never walk alone. "
          "Register for the Girl I Got You Masterclass.")
FAILS = []
#: FU-HOOK-PLACEMENT not installed: the contract keeps the hook-count fallback
NO_HP = getattr(SC, "song_contract", SC)._HP is None
#: R&B Flow's own sung-share floor: the share its length plan holds after the rap budget
RNB_TARGET = SC.sung_target("rnb-flow", D)
#: the honest beat for the proper sheet: "Girl, I got you" is the friend's
#: answer the moment the layoff (the villain) arrives
GOOD_PLAN = {"true_at_beat": "villain_arrives"}
GOLDEN = sorted(glob.glob(os.path.join(str(PT.TEMPLATES_DIR), "fixtures", "suno-sheets", "*.json")))


def _start():
    del FAILS[:]


def _end():
    assert not FAILS, FAILS


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


V1 = _read(CORE, "suno_recipe", "fixtures", "one-check-lyrics.txt")
V2 = _read(FIX, "one-check-v2-lyrics.txt")
GOOD = _read(FIX, "rnb-flow-150-pass.txt")


def _has(reasons, *words):
    return any(all(w in r for w in words) for r in reasons)


def _take(name):
    d = json.loads(_read(FIX, name))
    segs = SS.segments_from_sung_stretches(d["sung_stretches"], d["duration_s"], "2.1.0")
    return "".join(w["word"] for w in d["aligned_words"]), d["aligned_words"], segs


def _request(lyrics):
    req = R.kie_params()
    req.update({"duration": D, "vocal_gender": "f", "title": "T",
                "style": R.style_text("rnb-flow", R.parse_lyrics(GOOD)),
                "lyrics": lyrics, "negative_tags": R.negative_tags("rnb-flow")})
    return req


def test_a_v1_sheet_fails_with_the_reason():
    _start()
    r = SC.check_sheet(V1, "rnb-flow", D)
    rs = r["reasons"]
    check("a0 v1 sheet FAILS", r["verdict"] == "FAIL", r["verdict"])
    check("a1 rap counted: 254 rap words, 101.6 s", (r["totals"]["rap_words"],
          r["totals"]["rap_s"]) == (254, 101.6), r["totals"])
    check("a2 every chorus is only the hook repeated", _has(rs, "6 of 6 chorus blocks are only the hook"),
          rs[:3])
    check("a3 no sung non-hook sections vs the plan's 3",
          _has(rs, "0 sung non-hook sections", "calls for 3"), rs[:3])
    check("a4 planned sung share of voice named with the numbers (R&B Flow's own floor)",
          _has(rs, "planned sung share of voice 10.4%", "at least %g%%" % RNB_TARGET), rs[:4])
    check("a5 rap blocks not tagged as rhythmic rap on the beat",
          _has(rs, "29 of 29 rap blocks are not tagged as rhythmic rap on the beat"), rs)
    check("a6 'slow long held notes' refused in upbeat R&B Flow",
          _has(rs, "6 sung blocks ask for slow delivery in upbeat R&B Flow"), rs)
    check("a7 the spoken outro is not tagged no melody (sung on the hook melody)",
          _has(rs, "spoken outro 'Outro'", "no melody"), rs)
    check("a9 the spoken intro is not asked for no melody",
          not _has(rs, "'Intro'", "no melody"), rs)
    check("a8 per-section rows carry words, seconds, word share",
          all({"words", "seconds", "word_share_pct", "delivery"} <= set(x) for x in r["sections"]))
    _end()


def test_b_v2_sheet_fails_with_the_reason():
    _start()
    r = SC.check_sheet(V2, "rnb-flow", D)
    rs = r["reasons"]
    check("b0 v2 sheet FAILS", r["verdict"] == "FAIL", r["verdict"])
    check("b1 the doubled hook line is still only the hook",
          r["hook"]["blocks_with_only_the_hook"] == 6 and _has(rs, "only the hook repeated"), r["hook"])
    check("b2 still no sung non-hook sections", _has(rs, "0 sung non-hook sections"), rs[:3])
    check("b3 rap untagged", _has(rs, "rap blocks are not tagged"), rs)
    _end()


def _lyric_errs(text, d=D):
    """The sheet errors that are NOT the contract's (hook doctrine, word budget)."""
    return R.check_lyric_sheet(R.parse_lyrics(text), CLIENT, d, style_id="rnb-flow",
                               hook_plan=GOOD_PLAN)


def test_c_proper_rnb_flow_sheet_passes():
    _start()
    r = SC.check_sheet(GOOD, "rnb-flow", D)
    check("c0 proper R&B Flow sheet PASSES the contract", r["verdict"] == "PASS",
          r["reasons"] + r["flags"])
    check("c1 6 chorus blocks, none of them only the hook",
          (r["hook"]["blocks"], r["hook"]["blocks_with_only_the_hook"]) == (6, 0), r["hook"])
    one_line = GOOD.replace("Girl, I got you-u,\nyou will ne-ever walk alo-one", "Girl, I got you-u")
    r1 = SC.check_sheet(one_line, "rnb-flow", D)
    check("c1b a one-line hook alone in the chorus FAILS (I8 hook, chorus needs another line)",
          _has(r1["reasons"], "6 of 6 chorus blocks are only the hook"), r1["reasons"])
    two = GOOD.replace("Girl, I got you-u,\nyou will ne-ever walk alo-one",
                       "Girl, I got you-u,\nwe rise together, side by si-ide", 1)
    check("c1c one 4-10 word hook line plus one other line PASSES",
          SC.check_sheet(two, "rnb-flow", D)["verdict"] == "PASS",
          SC.check_sheet(two, "rnb-flow", D)["reasons"])
    # guard_request / validate_request add NO contract reason to the sheet's
    # own errors (which belong to the hook doctrine and word budget).
    lyr = _lyric_errs(GOOD)
    try:
        R.guard_request(R.style_text("rnb-flow", R.parse_lyrics(GOOD)), GOOD, "rnb-flow", CLIENT, D,
                        hook_plan=GOOD_PLAN)
        got = ""
    except R.RecipeError as exc:
        got = str(exc)
    check("c3 guard_request adds no contract reason", got in ("", "RECIPE_BYPASSED: " + "; ".join(lyr))
          or all(e in got for e in lyr) and got.count(";") == max(0, len(lyr) - 1), got)
    errs = SD.validate_request(_request(GOOD), "rnb-flow", CLIENT, D)
    check("c4 validate_request adds no contract reason", errs == lyr, (errs, lyr))
    _end()


def test_d_old_sheets_are_refused_before_spend():
    _start()
    for name, text in (("v1", V1), ("v2", V2)):
        try:
            R.guard_request(R.style_text("rnb-flow", R.parse_lyrics(GOOD)), text, "rnb-flow",
                            CLIENT, D)
            refused = ""
        except R.RecipeError as exc:
            refused = str(exc)
        check("d0 guard_request refuses %s" % name, "only the hook repeated" in refused,
              refused[:200])
        errs = SD.validate_request(_request(text), "rnb-flow", CLIENT, D)
        check("d1 validate_request refuses %s with the contract reason" % name,
              _has(errs, "sung non-hook sections"), errs[:3])
    _end()


def test_e_no_gate_switches_itself_off():
    _start()
    try:
        R.guard_request(R.style_text("rnb-flow", R.parse_lyrics(GOOD)), V1, "rnb-flow", CLIENT, None)
        got = ""
    except R.RecipeError as exc:
        got = str(exc)
    check("e0 guard_request with no length refuses: UNMEASURED: length_s",
          "UNMEASURED: length_s" in got, got[:200])
    errs = SD.validate_request(_request(GOOD), None, CLIENT, D)
    check("e1 validate_request with no style_id refuses: UNMEASURED: style_id",
          "UNMEASURED: style_id" in errs, errs)
    errs = SD.validate_request(_request(GOOD), "rnb-flow", CLIENT)
    check("e2 validate_request with no delivered_s refuses: UNMEASURED: length_s",
          "UNMEASURED: length_s" in errs, errs)
    check("e3 check_sheet with no style: FAIL UNMEASURED",
          SC.check_sheet(GOOD, None, D)["reasons"] == ["UNMEASURED: style_id"])
    # the hook count is judged on the plan's delivered seconds, not the request
    # duration with Suno's 15% headroom
    seven = GOOD.replace("[Outro (spoken)", "[Hook (sung): smooth r&b melody, sustained notes]\n"
                         "Girl, I got you-u,\nyou will ne-ever walk alo-one\n\n[Outro (spoken)", 1)
    big = dict(_request(seven), duration=171)
    if NO_HP:
        check("e4 7 hook blocks refused on delivered 148 s even with a 171 s request",
              _has(SD.validate_request(big, "rnb-flow", CLIENT, D), "7 hook blocks", "allows 6"),
              SD.validate_request(big, "rnb-flow", CLIENT, D))
    _end()


def _sung_as_written(text, hook_extra=None):
    """Aligned words + measured segments for a sheet sung exactly as written
    (headers inline, the way Suno returns them)."""
    t, aligned, segs = 0.0, [], []
    for s in SC.parse_sections(text):
        start = t
        head = "%s (%s): %s" % (s["tag"], s["delivery"], s["cue"]) if s["delivery"] else s["tag"]
        aligned.append({"word": "[%s]\n" % head, "startS": t, "endS": t})
        lines = list(s["lines"]) + (hook_extra if hook_extra and s["kind"] == "outro" else [])
        for ln in lines:
            ws = ln.split()
            for i, w in enumerate(ws):
                aligned.append({"word": w + ("\n" if i == len(ws) - 1 else " "),
                                "startS": t, "endS": t + 0.4})
                t += 0.5
        if s["delivery"] and t > start:
            segs.append({"delivery": "sung" if s["delivery"] == "sung" else "spoken",
                         "start": start, "end": t, "source": "measured"})
    return aligned, segs


def test_f_returned_song_gate():
    _start()
    words, segs = _take("one-check-v1-g1b-take.json")[1:]
    g = SC.check_returned_song(V1, words, segs, "rnb-flow", D)
    check("f0 v1 take FAILS: no sung lyrics outside the hook",
          g["verdict"] == "FAIL" and _has(g["reasons"], "no sung lyrics outside the hook"),
          g["reasons"])
    check("f1 v1 take: measured sung share of voice 24.9%, a FAIL reason",
          g["numbers"]["sung_of_voice_pct"] == 24.9 and _has(g["reasons"], "24.9%"),
          (g["numbers"], g["reasons"]))
    check("f3 rap versus spoken is UNMEASURED, said so",
          g["numbers"]["rap_vs_spoken"].startswith("UNMEASURED"))
    words, segs = _take("one-check-v2-g2a-take.json")[1:]
    g = SC.check_returned_song(V2, words, segs, "rnb-flow", D)
    check("f4 v2 take FAILS: Suno sang the hook more often than the sheet",
          _has(g["reasons"], "Suno sang the hook line", "girl i got you got you"), g["reasons"])
    check("f5 v2 take: sung share 45.9%, a FAIL reason",
          g["numbers"]["sung_of_voice_pct"] == 45.9 and _has(g["reasons"], "45.9%"),
          (g["numbers"], g["reasons"]))
    aligned, segs = _sung_as_written(GOOD)
    g = SC.check_returned_song(GOOD, aligned, segs, "rnb-flow", D)
    check("f6 control: the proper sheet sung as written PASSES", g["verdict"] == "PASS",
          g["reasons"])
    aligned, segs = _sung_as_written(GOOD, ["Girl, I got you-u,"])
    g = SC.check_returned_song(GOOD, aligned, segs, "rnb-flow", D)
    check("f7 the hook lyric sung untagged in the outro is counted (sheet: 6 hooks + product + outro = 8)",
          _has(g["reasons"], "girl i got you", "9 times", "has it 8 times"), g["reasons"])
    for field, args in (("sheet_text", (None, aligned, segs)), ("aligned_words", (GOOD, [], segs))):
        g = SC.check_returned_song(*args, style_id="rnb-flow", delivered_s=D)
        check("f8 missing %s fails closed as UNMEASURED" % field,
              g["verdict"] == "FAIL" and "UNMEASURED: %s" % field in g["reasons"], g["reasons"])
    g = SC.check_returned_song(GOOD, [dict(w, word=w["word"].split("]")[-1]) for w in aligned],
                               segs, "rnb-flow", D)
    check("f9 the untagged repeat is still counted when Suno returns no headers",
          _has(g["reasons"], "girl i got you", "9 times"), g["reasons"])
    _end()


def test_g_dispatch_gate_runs_before_pictures():
    _start()
    text, words, segs = _take("one-check-v2-g2a-take.json")
    take = {"segments": segs, "aligned_words": words,
            "detector": "singing_detector 2.1.0", "duration_s": 147.0,
            "music_under_speech_ratio": 0.9, "tail_rms_dbfs": -20.0, "first_sung_s": 10.0}
    plan = {"delivered_s": D, "style_id": "rnb-flow", "sheet_text": V2}
    j = SD.judge_take(take, plan, "", "Girl, I got you")
    check("g0 judge_take fails the v2 take on song_contract",
          j["gates"]["song_contract"]["verdict"] == "FAIL" and "song_contract" in j["failed"],
          j["gates"].get("song_contract"))
    j = SD.judge_take(take, dict(plan, sheet_text=None), "", "Girl, I got you")
    check("g1 a plan with no sheet_text fails closed",
          "UNMEASURED: sheet_text" in j["gates"]["song_contract"]["detail"], j["gates"]["song_contract"])
    j = SD.judge_take(take, {"delivered_s": D}, "", "Girl, I got you")
    check("g2 a plan with no style_id fails closed (the gate is never absent)",
          j["gates"].get("song_contract", {}).get("verdict") == "FAIL"
          and "UNMEASURED: style_id" in j["gates"]["song_contract"]["detail"], j["gates"].get("song_contract"))
    check("g3 song_contract is a named gate", "song_contract" in SD.GATES)
    _end()


def test_h_other_styles_by_their_own_definition():
    _start()
    r = SC.check_sheet(GOOD, "soul-ballad", D)
    check("h0 rap blocks refused in Soul Ballad", _has(r["reasons"], "rap blocks in Soul Ballad"),
          r["reasons"][:2])
    check("h1 Soul Ballad needs its 2 sung verses too (5 sung non-hook sections)",
          r["sung_non_hook"]["required_sections"] == 5, r["sung_non_hook"])
    check("h2 'slow' is fine in Soul Ballad (62-68 bpm)",
          not _has(SC.check_sheet(V1.replace("(rap)", "(sung)"), "soul-ballad", D)["reasons"],
                   "slow delivery"))
    check("h3 the spoken voiceover version is EXEMPT",
          SC.check_sheet(V1, "velvet_voiceover", D)["verdict"] == "EXEMPT")
    talky = GOOD.replace("rhythmic rap on the beat, tight metered flow",
                         "rhythmic rap on the beat, conversational flow")
    check("h4a a rap cue asking for conversational delivery is refused",
          _has(SC.check_sheet(talky, "rnb-flow", D)["reasons"], "2 of 2 rap blocks"))
    lyr = R.render_lyrics([{"tag": "Rap Verse", "delivery": "rap", "lines": ["x y"]},
                           {"tag": "Refrain", "delivery": "sung", "lines": ["x y"]}], "rnb-flow")
    check("h4 the recipe tags R&B Flow rap as rhythmic rap on the beat",
          "rhythmic rap on the beat" in lyr and "conversational" not in lyr, lyr)
    check("h5 an R&B Flow sung block never inherits 'slow'", "slow" not in lyr, lyr)
    _end()


def _cut_to_first_hooks(text, n):
    """The sheet with every hook block after the first n removed."""
    blocks = text.split("\n\n")
    hooks = [i for i, b in enumerate(blocks) if b.startswith("[Hook")]
    return "\n\n".join(b for i, b in enumerate(blocks) if i not in hooks[n:])


def _guard(style_id, text, client, d, plan):
    try:
        R.guard_request(R.style_text(style_id, R.parse_lyrics(text)), text, style_id, client, d,
                        hook_plan=plan)
        return ""
    except R.RecipeError as exc:
        return str(exc)


def test_i_story_beat_is_measured_not_handed_out():
    _start()
    cut = _cut_to_first_hooks(GOOD, 3)
    turn = {"true_at_beat": "the_turn"}
    check("i0 the cut sheet keeps 3 hooks and the build-up", len(cut.split("\n\n")) == 15
          and HP.check_buildup(cut, "rnb-flow", D) == [])
    got = _guard("rnb-flow", cut, CLIENT, D, turn)
    check("i1 checker counter-example (first hook about a quarter in, true at the turn) FAILS",
          "before 'the_turn'" in got, got[:300])
    got = _guard("rnb-flow", cut, CLIENT, D, HP.plan_for(cut, D, "the_turn", "rnb-flow"))
    check("i2 a plan built for the turn cannot move the hook: still FAILS", "before 'the_turn'" in got,
          got[:300])
    check("i3 the plan's beats are measured, not handed out from true_at_beat",
          HP.plan_for(cut, D, "the_turn", "rnb-flow")["beats"][0] == "villain_arrives")
    check("i4 the proper sheet at its honest beat passes guard_request",
          _guard("rnb-flow", GOOD, CLIENT, D, GOOD_PLAN) == "",
          _guard("rnb-flow", GOOD, CLIENT, D, GOOD_PLAN)[:300])
    got = _guard("rnb-flow", GOOD, CLIENT, D, None)
    check("i5 no hook_plan: guard_request refuses, UNMEASURED: hook_plan", "UNMEASURED: hook_plan" in got,
          got[:300])
    _end()


def _golden(path):
    g = json.loads(_read(path))
    text = "\n\n".join(seg["lyrics"] for seg in g["segments"])
    hooks = [s for s in R.parse_lyrics(text) if HP.kind_of(s) == "hook"]
    return g, text, " ".join(hooks[0]["lines"])        # the chorus words are the client's


def test_j_every_golden_sheet_passes_the_merged_gates():
    _start()
    check("j0 six golden sheets on disk", len(GOLDEN) == 6, GOLDEN)
    for path in GOLDEN:
        g, text, client = _golden(path)
        name, sid, d = os.path.basename(path), g["music_style"], g["delivered_s"]
        r = SC.check_sheet(text, sid, d, g["style"])
        check("j1 %s PASSES song_contract" % name, r["verdict"] == "PASS", r["reasons"] + r["flags"])
        got = _guard(sid, text, client, d, g["hook_plan"])
        check("j2 %s PASSES guard_request (recipe + hook placement + contract)" % name, got == "",
              got[:400])
    # the test can fail: a golden sheet put back the old way is refused
    g, text, client = _golden([p for p in GOLDEN if "90s-rnb" in p][0])
    talky = text.replace("rhythmic rap on the beat, tight metered flow", "tight rhythmic rap, conversational flow")
    check("j3 a golden R&B Flow sheet with a conversational rap cue is refused",
          "not tagged as rhythmic rap on the beat" in _guard("rnb-flow", talky, client, 88, g["hook_plan"]))
    thin = text.replace(",\nthe morning in your e-eyes", "")
    check("j4 a golden sheet whose chorus is only the hook is refused",
          "only the hook repeated" in _guard("rnb-flow", thin, client, 88, g["hook_plan"]))
    _end()


def test_k_proper_sheet_goes_through_the_director():
    """The proper R&B Flow sheet (held vowels and all) goes through
    music_director.build_generate_request; the director's words-fit check
    and this contract hold the sung share to the same per-style floor."""
    _start()
    import music_director as MD
    import words_fit as W
    style = R.style_text("rnb-flow", R.parse_lyrics(GOOD))
    names = ("Chanel", "Girl I Got You Masterclass", "GirlIGotYouEvent.com")
    try:
        req = MD.build_generate_request(GOOD, style, "T", style_id="rnb-flow", client_text=CLIENT,
                                        length_s=D, true_at_beat=GOOD_PLAN["true_at_beat"],
                                        protected=names)
        got = req["_hook_plan"]["true_at_beat"]
    except Exception as exc:                     # noqa: BLE001 - report the refusal
        got = "%s: %s" % (type(exc).__name__, exc)
    check("k0 the proper R&B Flow sheet goes through the director", got == "villain_arrives", got[:300])
    for sid, d in (("rnb-flow", 148), ("rnb-flow", 298), ("soul-ballad", 58), ("soul-rise", 598)):
        check("k1 %s at %d s: one floor for the contract and words-fit" % (sid, d),
              SC.sung_target(sid, d) == W.style_sung_target_pct(sid, d),
              (SC.sung_target(sid, d), W.style_sung_target_pct(sid, d)))
    fit = W.preflight_sheet(D, V1, style="rnb-flow")
    check("k2 the director's words-fit refuses the v1 sheet on the same floor",
          fit["reason_code"] == "SHARE_OFF_TARGET" and fit["sung_target_pct"] == RNB_TARGET,
          (fit["reason_code"], fit["sung_target_pct"], RNB_TARGET))
    _end()


def main():
    bad = []
    for t in (test_a_v1_sheet_fails_with_the_reason, test_b_v2_sheet_fails_with_the_reason,
              test_c_proper_rnb_flow_sheet_passes, test_d_old_sheets_are_refused_before_spend,
              test_e_no_gate_switches_itself_off, test_f_returned_song_gate,
              test_g_dispatch_gate_runs_before_pictures, test_h_other_styles_by_their_own_definition,
              test_i_story_beat_is_measured_not_handed_out,
              test_j_every_golden_sheet_passes_the_merged_gates,
              test_k_proper_sheet_goes_through_the_director):
        try:
            t()
        except AssertionError as exc:
            bad.append("%s: %s" % (t.__name__, exc))
    print()
    if bad:
        print("FAILED: %d" % len(bad))
        for f in bad:
            print("  - %s" % f)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
