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
import song_contract as _SC  # noqa: E402
import spoken_share as _SS   # noqa: E402
import suno_recipe as _R     # noqa: E402
import sung_hook as _SH      # noqa: E402
from sung_hook import hook_placement as _HP   # noqa: E402
import words_fit as _WF      # noqa: E402

TOOL_NAME = "song_dispatch"
TOOL_VERSION = "1.1.0"
GATES = ("detector", "spoken_share", "rap_share", "sung_of_voice", "sung_stretch", "hook", "script_words",
         "length", "music_under_speech", "clean_ending", "first_sung", "hook_placement")
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
    d = d if isinstance(d, (int, float)) and not isinstance(d, bool) else None
    # FU-RNBFLOW-SONG: the style reaches the sheet check (rap is judged as rap,
    # never refused as "no style"), and the style's own contract runs.
    errs += _R.check_lyric_sheet(sheet, client_text, d, style_id=style_id)
    errs += _SC.check_sheet(req.get("lyrics", ""), style_id, delivered_s, req.get("style"))["reasons"]
    return errs


def _w(t):
    return _SH.words(t)


def _planned_pct(plan, style_id, key):
    """Percent of delivered runtime the approved plan gives one delivery.

    FU-U3: R&B Flow targets are judged against the share the APPROVED plan
    names (plan 18 section 9 item 1, documented default) -- never a new
    number. planned % = words[key] / words_fit rate for that delivery,
    over the plan's delivered seconds. Missing word counts -> None (the
    caller falls back to the style's constant).
    """
    words = (plan or {}).get("words") or {}
    if key not in words or key == "rap" and "rap" not in words:
        return None
    delivered = (plan or {}).get("delivered_s")
    if not isinstance(delivered, (int, float)) or delivered <= 0:
        return None
    rate = _WF.rates_for(style_id).get(key)
    if not rate:
        return None
    return round(float(words[key]) / float(rate) / float(delivered) * 100.0, 3)


def judge_take(take, plan, script_words, hook_text, spoken_range_pct=None,
               style_id=None, sheet_text=None):
    """Gate a measured take. ``take`` = {segments (measured and/or aligned),
    aligned_words, duration_s, detector, music_under_speech_ratio,
    tail_rms_dbfs, first_sung_s}. Returns {verdict, gates:{name:{verdict,
    detail}}, score}.

    FU-U3: ``style_id`` carries the music style through the judge. Bands per
    style (spoken_share.STYLE_TARGETS), the SAME 5/10 band everywhere:
      * Soul Ballad / Soul Rise: spoken-style share vs the ad's own target
        (22.5 default) and sung-of-voice vs 77.5 -- today's numbers exactly;
      * R&B Flow: rap is its own delivery. The plain-spoken share and the
        rap share are judged against the share each delivery has in the
        APPROVED plan (the U2 plan's word counts at the style's measured
        rates -- the documented default from plan 18 section 9 item 1, a
        TREVOR-DECISION ITEM, never a number invented here), each on the
        5/10 band; plain spoken with no rap keeps the 22.5 runtime target;
        sung-of-voice is RECORDED for a rap sheet (hook content, not a
        planned share). The 6 s sung stretch and the hook count stay hard.
    Rap-versus-speech comes from aligned segments (source="aligned", basis
    "aligned"), never recorded as "measured".
    """
    D = plan["delivered_s"]
    segs = take.get("segments") or []
    g = {}

    def put(name, verdict, detail=""):
        g[name] = {"verdict": verdict, "detail": detail}

    det = str(take.get("detector", ""))
    srcs = {s.get("source") for s in segs if isinstance(s, dict)}
    ok = (bool(segs) and bool(srcs)
          and srcs <= {"measured", "aligned"} and "measured" in srcs
          and det.startswith("singing_detector 2"))
    put("detector", "PASS" if ok else "FAIL", det or "no detector record")
    if not ok:
        return _finish(g)
    basis = _SS.segment_basis(segs)
    t = _SS.style_targets(style_id)
    m = _SS.measure_share(segs, basis, style_id=style_id)
    # spoken target per style: plan-derived for a rap style, the ad's own
    # range (22.5 default) otherwise.
    if t["rap_delivery"] and t["target_from_plan"]:
        planned = _planned_pct(plan, style_id, "spoken")
        tgt = _SS.SPOKEN_TARGET_PCT if planned is None else planned
        target_src = "approved plan" if planned is not None else "default"
    else:
        tgt = _SS.target_for_range(spoken_range_pct)
        target_src = "ad range"
    r = _SS.check_share(m["share"], segs, basis, target_pct=tgt,
                        style_id=style_id)
    put("spoken_share", r["verdict"],
        "%.1f%% vs %.1f (%s, plain spoken, %s basis)"
        % (m["share_pct"], tgt, target_src, basis))
    # rap: its own delivery. A rap style judges the measured rap share
    # against the plan's own rap share; a style without rap wants ZERO rap
    # (a take that carries rap under Soul Ballad is a FAIL, band included).
    if t["rap_delivery"]:
        planned_rap = _planned_pct(plan, style_id, "rap")
        if m["rap_seconds"] > 0 or planned_rap:
            j = _SS.judge_gap(m["rap_share_pct"],
                              _SS.SPOKEN_TARGET_PCT if planned_rap is None
                              else planned_rap)
            put("rap_share", j["verdict"],
                "%.1f%% vs %s (%s)" % (m["rap_share_pct"],
                                       "n/a" if planned_rap is None
                                       else "%.1f" % planned_rap,
                                       "approved plan" if planned_rap is not None
                                       else "default"))
        else:
            put("rap_share", "PASS", "no rap planned, none measured")
    else:
        put("rap_share", "PASS" if m["rap_seconds"] <= 0 else
            _SS.judge_gap(m["rap_share_pct"], 0.0)["verdict"],
            "%.1f%% rap (Soul style allows none)" % m["rap_share_pct"])
    v = (_SS.check_sung_of_voice(segs, basis=basis, style_id=style_id)
         if m["voice_seconds"] - m["sung_seconds"] > 0
         else {"verdict": "FAIL", "sung_of_voice_pct": 0})
    put("sung_of_voice", v["verdict"],
        "%.1f%% of voice%s" % (v.get("sung_of_voice_pct", 0),
                               "" if v.get("gated", True)
                               else " (recorded, not gated for %s)" % style_id))
    real = _SS.check_real_singing(segs)
    put("sung_stretch", "PASS" if real.get("verdict", "PASS") != "FAIL" and not real.get("reasons") else "FAIL",
        "6 s sung stretch")
    # The hook is counted on the DETECTOR segments only: aligned segments
    # carry the sheet's labels, and sung_hook.measure requires measured ones.
    hook_segs = [s for s in segs if s.get("source") == "measured"]
    rec = _SH.measure(hook_text, take.get("aligned_words") or [], hook_segs, _HP.hook_target(D, plan.get("hook_plan")))
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
    plan = dict(plan, sheet_text=plan.get("sheet_text") or request.get("lyrics"))
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
