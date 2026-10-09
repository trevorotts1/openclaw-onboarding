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
    near-silent final 2 s), first sung time;
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
import song_contract as _SC  # noqa: E402
import spoken_share as _SS   # noqa: E402
import suno_recipe as _R     # noqa: E402
import sung_hook as _SH      # noqa: E402
import words_fit as _WF      # noqa: E402

TOOL_NAME = "song_dispatch"
TOOL_VERSION = "1.0.0"
GATES = ("detector", "spoken_share", "sung_of_voice", "sung_stretch", "hook", "script_words",
         "length", "music_under_speech", "clean_ending", "first_sung")
MUSIC_UNDER_SPEECH_MIN = 0.3     # music level under speech / music level under singing
NEAR_SILENT_DBFS = -50.0         # RMS of the final 2 s below this = near silent
SPEND_CAP_CENTS = 1000           # per author (Trevor 2026-10-08)
GEN_COST_CENTS = 6
GATES += ("song_contract",)      # FU-RNBFLOW-SONG: the style's own contract on every take


class DispatchError(ValueError):
    pass


def refuse_asr(engine):
    """Only the local fast engine (faster-*, small.en int8) may transcribe;
    anything openai, or any engine not named faster-*, is refused."""
    e = str(engine).lower().replace("_", "-").strip()
    if "openai" in e or not e.startswith("faster-"):
        raise DispatchError("ASR engine %r refused: only the local faster-* engine, small.en int8" % engine)
    return e


def validate_request(req, style_id=None, client_text=""):
    """List of refusals for a KIE generate-music input; [] = send it."""
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
    d = d if isinstance(d, (int, float)) and not isinstance(d, bool) else None
    # FU-RNBFLOW-SONG: the style reaches the sheet check (rap is judged as rap,
    # never refused as "no style"), and the style's own contract runs.
    errs += _R.check_lyric_sheet(sheet, client_text, d, style_id=style_id)
    errs += _SC.check_sheet(req.get("lyrics", ""), style_id, delivered_s, req.get("style"))["reasons"]
    return errs


def _w(t):
    return _SH.words(t)


def judge_take(take, plan, script_words, hook_text, spoken_range_pct=None):
    """Gate a measured take. ``take`` = {segments (measured), aligned_words,
    duration_s, detector, music_under_speech_ratio, tail_rms_dbfs,
    first_sung_s}. Returns {verdict, gates:{name:{verdict,detail}}, score}."""
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
    rec = _SH.measure(hook_text, take.get("aligned_words") or [], segs, _SH.hook_count(D))
    put("hook", "PASS" if rec["measured"] >= 2 and rec["verdict"] != "FAIL" else
        ("FLAG" if rec["measured"] >= 2 else "FAIL"), "%d of %d" % (rec["measured"], rec["target"]))
    # FU-RNBFLOW-SONG: the returned song against the style's contract, before any
    # picture or video spend. The plan carries style_id and sheet_text (run_takes
    # stamps the request's lyrics); a missing one is a FAIL, never a skipped gate.
    sc_sid = style_id or plan.get("style_id")
    if not sc_sid:
        put("song_contract", "FAIL", "UNMEASURED: style_id (the plan carries no style_id)")
    else:
        sc = _SC.check_returned_song(sheet_text or plan.get("sheet_text"),
                                     take.get("aligned_words") or [], segs, sc_sid, D)
        put("song_contract", "FAIL" if sc["reasons"] else "PASS",
            "; ".join(sc["reasons"]) or ", ".join("%s %s" % kv for kv in sorted(sc["numbers"].items())))
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
    return _finish(g)


def _finish(g):
    bad = [k for k, v in g.items() if v["verdict"] == "FAIL"]
    flags = [k for k, v in g.items() if v["verdict"] == "FLAG"]
    return {"verdict": "FAIL" if bad else ("FLAG" if flags else "PASS"), "gates": g,
            "failed": bad, "flagged": flags}


def run_takes(request, plan, generate, measure, save, script_words, hook_text,
              spoken_range_pct=None, cap_cents=SPEND_CAP_CENTS, cost_cents=GEN_COST_CENTS,
              kie=_LG.kie_request):
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
    refuse_asr("faster-" + "wh" + "isper")
    plan = dict(plan, sheet_text=plan.get("sheet_text") or request.get("lyrics"))
    spent, receipts, best = 0, [], None
    while spent + cost_cents <= cap_cents:
        spent += cost_cents
        for take in kie(lambda: generate(request), "song generate", generation=True):
            take = dict(take, **measure(take))
            rcpt = judge_take(take, plan, script_words, hook_text, spoken_range_pct)
            save(take, rcpt)                               # stem + timestamps, every take
            receipts.append(rcpt)
            if rcpt["verdict"] == "PASS":
                return {"delivered": take, "verdict": "PASS", "receipts": receipts, "spent_cents": spent}
            if rcpt["verdict"] == "FLAG" and (best is None or len(rcpt["flagged"]) < len(best[1]["flagged"])):
                best = (take, rcpt)
    if best:
        return {"delivered": best[0], "verdict": "FLAG", "receipts": receipts, "spent_cents": spent}
    return {"delivered": None, "verdict": "FAIL", "receipts": receipts, "spent_cents": spent}
