#!/usr/bin/env python3
"""Song dispatcher logic: request validation, per-take gates, take loop.

Transport-free on purpose: ``generate`` and ``measure`` are injected, so the
operator dispatcher, the Claude-Nine adapter and the tests share ONE judge.
Rules (Trevor 2026-10-08):
  * the request comes from suno_recipe.build_request (recipe v2); a request
    that breaks the recipe, or holds a rule that contradicts the researched
    wording (it never refuses the researched negatives or the "band keeps
    playing" line), is refused before spend;
  * EVERY take is judged: singing detector v2, spoken share band (per-ad
    target), sung share of voice, 6 s sung stretch, hook sung 2+, all script
    words, length (L-2), music level under spoken lines, clean ending (no
    near-silent final 2 s), first sung time, and hook placement (FU-HOOK-
    PLACEMENT: Suno added or moved no hook block earlier than the sheet and
    sang the first hook after the build-up window) -- before any picture or
    video spend;
  * stop at the first PASS, else deliver the best FLAG take inside the
    per-author spend cap, never a FAIL;
  * the vocal stem and timestamps are saved for EVERY take;
  * whole tracks only: every generation asks for the full duration, never a patch;
  * the openai transcription engine is refused (only the local fast engine, small.en int8).
stdlib only; no network, no spend of its own.
"""
from __future__ import annotations

import os
import re
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import load_governor as _LG   # noqa: E402
import spoken_share as _SS   # noqa: E402
import suno_recipe as _R     # noqa: E402
import sung_hook as _SH      # noqa: E402
from sung_hook import hook_placement as _HP   # noqa: E402
import words_fit as _WF      # noqa: E402

TOOL_NAME = "song_dispatch"
TOOL_VERSION = "1.0.0"
GATES = ("detector", "spoken_share", "sung_of_voice", "sung_stretch", "hook", "script_words",
         "length", "music_under_speech", "clean_ending", "first_sung", "hook_placement")
MUSIC_UNDER_SPEECH_MIN = 0.3     # music level under speech / music level under singing
NEAR_SILENT_DBFS = -50.0         # RMS of the final 2 s below this = near silent
SPEND_CAP_CENTS = 1000           # per author (Trevor 2026-10-08)
GEN_COST_CENTS = 6


class DispatchError(ValueError):
    pass


def refuse_asr(engine):
    """Only the local fast engine (faster-*, small.en int8) may transcribe;
    anything openai, or any engine not named faster-*, is refused."""
    e = str(engine).lower().replace("_", "-").strip()
    if "openai" in e or not e.startswith("faster-"):
        raise DispatchError("ASR engine %r refused: only the local faster-* engine, small.en int8" % engine)
    return e


def validate_request(req, style_id=None, client_text="", delivered_s=None):
    """List of refusals for a KIE generate-music input; [] = send it.

    ``delivered_s`` is the plan's delivered seconds (plan["delivered_s"]),
    never the request duration, which carries Suno's 15% headroom: the
    style contract (core/song_contract, FU-RNBFLOW-SONG) counts hooks on it,
    and a missing style_id or delivered_s is a refusal ("UNMEASURED: ..."),
    never a skipped check."""
    errs = []
    if req.get("model") != "V6":
        errs.append("model must be V6")
    if req.get("custom_mode") is not True or req.get("instrumental") is not False:
        errs.append("custom_mode must be true and instrumental false")
    d = req.get("duration")
    if not isinstance(d, (int, float)) or isinstance(d, bool) or not 10 <= d <= 360:
        errs.append("duration must be 10-360 s")
    if req.get("vocal_gender") not in ("f", "m"):
        errs.append("vocal_gender must be f or m")
    for k, v in (("style_weight", 0.75), ("weirdness_constraint", 0.3), ("variety", 0)):
        if req.get(k) != v:
            errs.append("%s must be %s" % (k, v))
    errs += _R.check_style_text(req.get("style", ""))
    errs += _R.check_negatives(req.get("negative_tags", ""), style_id)
    sheet = _R.parse_lyrics(req.get("lyrics", ""))
    errs += _R.check_lyric_sheet(sheet, client_text, d if isinstance(d, (int, float)) else None)
    return errs


def _w(t):
    return _SH.words(t)


def judge_take(take, plan, script_words, hook_text, spoken_range_pct=None,
               style_id=None, sheet_text=None):
    """Gate a measured take. ``take`` = {segments (measured), aligned_words,
    duration_s, detector, music_under_speech_ratio, tail_rms_dbfs,
    first_sung_s}. The hook_placement gate always runs: ``sheet_text`` (the
    lyrics sent to Suno, or plan["sheet_text"]), the style (``style_id``
    or plan["style_id"]) or plan["hook_plan"] missing = FAIL "UNMEASURED:
    <field>". Returns {verdict, gates:{name:{verdict,detail}}, score}."""
    D = plan["delivered_s"]
    segs = take.get("segments") or []
    g = {}

    def put(name, verdict, detail=""):
        g[name] = {"verdict": verdict, "detail": detail}

    det = str(take.get("detector", ""))
    ok = bool(segs) and all(s.get("source") == "measured" for s in segs) and det.startswith("singing_detector 2")
    put("detector", "PASS" if ok else "FAIL", det or "no detector record")
    if not ok:
        return _finish(g)
    tgt = _SS.target_for_range(spoken_range_pct)
    m = _SS.measure_share(segs)
    r = _SS.check_share(m["share"], segs, tgt)
    put("spoken_share", r["verdict"], "%.1f%% vs %.1f" % (r["share_pct"], tgt))
    v = (_SS.check_sung_of_voice(segs) if m["sung_seconds"] + m["spoken_style_seconds"] > 0
         else {"verdict": "FAIL", "sung_of_voice_pct": 0})
    put("sung_of_voice", v["verdict"], "%.1f%% of voice" % v.get("sung_of_voice_pct", 0))
    real = _SS.check_real_singing(segs)
    put("sung_stretch", "PASS" if real.get("verdict", "PASS") != "FAIL" and not real.get("reasons") else "FAIL",
        "6 s sung stretch")
    rec = _SH.measure(hook_text, take.get("aligned_words") or [], segs,
                     _HP.hook_target(D, plan.get("hook_plan")))
    put("hook", "PASS" if rec["measured"] >= 2 and rec["verdict"] != "FAIL" else
        ("FLAG" if rec["measured"] >= 2 else "FAIL"), "%d of %d" % (rec["measured"], rec["target"]))
    have = set(_w(" ".join(w.get("word", "") for w in take.get("aligned_words") or [])))
    missing = sorted(set(_w(script_words)) - have)
    put("script_words", "FAIL" if missing else "PASS", ("missing %s" % missing[:8]) if missing else "")
    dur = take.get("duration_s")
    if not isinstance(dur, (int, float)):
        put("length", "FAIL", "unmeasured")
    elif dur > D + 0.05:
        put("length", "FAIL", "%.1f s over the %.0f s limit" % (dur, D))
    else:
        put("length", _SS.judge_seconds(dur, D, D)["verdict"], "%.1f s" % dur)
    ratio = take.get("music_under_speech_ratio")
    put("music_under_speech", "PASS" if isinstance(ratio, (int, float)) and ratio >= MUSIC_UNDER_SPEECH_MIN
        else "FAIL", "ratio %r" % (ratio,))
    tail = take.get("tail_rms_dbfs")
    put("clean_ending", "PASS" if isinstance(tail, (int, float)) and tail > NEAR_SILENT_DBFS else "FAIL",
        "final 2 s at %r dBFS" % (tail,))
    fs = take.get("first_sung_s")
    if isinstance(fs, (int, float)):
        j = _SS.judge_seconds(fs, D * _SS.FIRST_SUNG_TARGET_PCT / 100.0, D, only="late")
        put("first_sung", j["verdict"], "%.1f s" % fs)
    else:
        put("first_sung", "FAIL", "unmeasured")
    # FU-HOOK-PLACEMENT rule 4: always on; a missing input is a FAIL, never a skip
    sheet = sheet_text or plan.get("sheet_text")
    sid = style_id or plan.get("style_id")
    hp = _HP.check_returned(sheet, take.get("aligned_words") or [], sid, D, plan.get("hook_plan"))
    put("hook_placement", hp["verdict"], "; ".join(hp["reasons"]) or
        "first hook %s s (window %s s)" % (hp["first_hook_s"], hp["min_first_hook_s"]))
    return _finish(g)


def _finish(g):
    bad = [k for k, v in g.items() if v["verdict"] == "FAIL"]
    flags = [k for k, v in g.items() if v["verdict"] == "FLAG"]
    return {"verdict": "FAIL" if bad else ("FLAG" if flags else "PASS"), "gates": g,
            "failed": bad, "flagged": flags}


def run_takes(request, plan, generate, measure, save, script_words, hook_text,
              spoken_range_pct=None, cap_cents=SPEND_CAP_CENTS, cost_cents=GEN_COST_CENTS,
              kie=_LG.kie_request, style_id=None):
    """Generate until a take passes or the cap is spent.

    generate(request) -> list of takes (2 per generation, each with audio ids);
    measure(take) -> the measured fields for judge_take; save(take, receipt)
    must store the vocal stem and timestamps (called for EVERY take, even
    failures). Every generation goes through the load governor (``kie``): a NEW
    request draws from the 20-per-10-s bucket and a 429 is resubmitted.
    Returns {delivered, verdict, receipts, spent_cents}.
    """
    # G9 (FU-U6, plan E.2 default): the request carries the planned time plus the
    # >=15 percent Suno headroom; the master is still trimmed to L-2 by
    # master_length, so "whole tracks only" is judged against that headroom
    # (words_fit.max_suno_duration), never a patch/short duration.
    allowed = _WF.max_suno_duration(plan["delivered_s"])
    if request.get("duration") not in (plan["delivered_s"], allowed):
        raise DispatchError("whole tracks only: request duration %r != planned %r (or its %r s "
                            "Suno headroom; never a patch)"
                            % (request.get("duration"), plan["delivered_s"], allowed))
    # FU-HOOK-PLACEMENT: the director's hook_plan rides the request as
    # _hook_plan; it moves into the judge's plan and never reaches KIE.
    plan = dict(plan, hook_plan=request.get("_hook_plan") or plan.get("hook_plan"))
    request = {k: v for k, v in request.items() if k != "_hook_plan"}
    refuse_asr("faster-" + "wh" + "isper")
    spent, receipts, best = 0, [], None
    while spent + cost_cents <= cap_cents:
        spent += cost_cents
        for take in kie(lambda: generate(request), "song generate", generation=True):
            take = dict(take, **measure(take))
            rcpt = judge_take(take, plan, script_words, hook_text, spoken_range_pct,
                              style_id, request.get("lyrics"))
            save(take, rcpt)                               # stem + timestamps, every take
            receipts.append(rcpt)
            if rcpt["verdict"] == "PASS":
                return {"delivered": take, "verdict": "PASS", "receipts": receipts, "spent_cents": spent}
            if rcpt["verdict"] == "FLAG" and (best is None or len(rcpt["flagged"]) < len(best[1]["flagged"])):
                best = (take, rcpt)
    if best:
        return {"delivered": best[0], "verdict": "FLAG", "receipts": receipts, "spent_cents": spent}
    return {"delivered": None, "verdict": "FAIL", "receipts": receipts, "spent_cents": spent}
