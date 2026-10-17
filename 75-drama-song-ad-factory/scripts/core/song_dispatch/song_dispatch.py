#!/usr/bin/env python3
"""Song dispatcher logic: request validation, per-take gates, take loop.

Transport-free on purpose: ``generate`` and ``measure`` are injected, so the
operator dispatcher, the Claude-Nine adapter and the tests share ONE judge.
Rules (Trevor 2026-10-08):
  * the request comes from suno_recipe.build_request (recipe v2); a request
    that breaks the recipe, or holds a rule that contradicts the researched
    wording (it never refuses the researched negatives or the "band keeps
    playing" line), is refused before spend;
  * EVERY take is judged per variant; three variants run in parallel lanes:
    singing detector v2, spoken share band (per-ad
    target), sung share of voice, 6 s sung stretch, hook sung 2+, all script
    words, length (L-2), music level under spoken lines, clean ending (no
    near-silent final 2 s), first sung time, and hook placement (FU-HOOK-
    PLACEMENT: Suno added or moved no hook block earlier than the sheet and
    sang the first hook after the build-up window) -- before any picture or
    video spend;
  * WW-21: the aggregation/evidence-binding boundary (`accept_audio_results`)
    is TOTAL and fail-closed -- missing, empty, malformed, unknown,
    unavailable, unmeasured, flagged, failed or stale-bound evidence BLOCKS,
    and only a complete set of five PASS, bound delivered-audio results
    advances. It is the boundary before spend, NOT a sixth audio gate;
  * stop at the first PASS, else deliver the best FLAG take inside the
    per-author spend cap, never a FAIL;
  * the vocal stem and timestamps are saved for EVERY take;
  * whole tracks only: every generation asks for the full duration, never a patch;
  * the openai transcription engine is refused (only the local fast engine, small.en int8).
stdlib only; no network, no spend of its own.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import load_governor as _LG   # noqa: E402
import music_qc as _QC       # noqa: E402  WW-08: the total verdict vocabulary + the receipt
import song_contract as _SC  # noqa: E402
import script_approval as _SA   # noqa: E402
import spoken_share as _SS   # noqa: E402
#: the spoken_share MODULE itself, for the method first-vocal rule the package
#: ``__init__`` does not re-export (same shape as _RM/_SCM below).
_SSM = getattr(_SS, "spoken_share", _SS)
import suno_recipe as _R     # noqa: E402
#: the recipe MODULE itself, whether core/suno_recipe/ is a package (whose
#: __init__ re-exports a fixed list) or the bare module on sys.path -- so a new
#: recipe helper can be called without editing the package's export list (which
#: this unit does not own).
_RM = getattr(_R, "suno_recipe", _R)
#: WW-23: the song_contract MODULE itself, for a new helper the package
#: __init__ does not re-export (same shape as _RM above).
_SCM = getattr(_SC, "song_contract", _SC)
import sung_hook as _SH      # noqa: E402
from sung_hook import hook_placement as _HP   # noqa: E402
import words_fit as _WF      # noqa: E402
import music_qc.pace_change as _PC   # noqa: E402
import music_qc.rap_check as _RC     # noqa: E402
import timing_guard as _TG     # noqa: E402  WW-24: measured-only evidence provenance

TOOL_NAME = "song_dispatch"
TOOL_VERSION = "1.2.0"
GATES = ("detector", "spoken_share", "rap_share", "sung_of_voice", "sung_stretch", "hook", "script_words",
         "length", "music_under_speech", "clean_ending", "first_sung", "hook_placement")
MUSIC_UNDER_SPEECH_MIN = 0.3     # music level under speech / music level under singing
NEAR_SILENT_DBFS = -50.0         # RMS of the final 2 s below this = near silent
SPEND_CAP_CENTS = 1000           # per author (Trevor 2026-10-08)
GEN_COST_CENTS = 6
GATES += ("song_contract",)      # FU-RNBFLOW-SONG: the style's own contract on every take
# WWFIXGAPS U1 (defect 2): the two D1 audio gates were shipped but NEVER
# CALLED by the pipeline, so "UNMEASURED blocks a take PASS" was only true of
# the module in isolation. Both are now gates of the take judge.
GATES += ("rap_audio", "pace_change")
# WW-08: the story and timeline-integrity gates are declared take gates too
# -- judge_take emits them for EVERY take, so their names belong in GATES
# (WW-21's "no gate in GATES is a dead name" control compares the declared
# set with exactly what the judge writes).
GATES += ("story", "timeline")

# ---- WW-21: total fail-closed acceptance (the aggregation boundary) --------
#
# WW-21 IS NOT A SIXTH AUDIO GATE. The operator plan (WW-ROUND3-FIX-PLAN.md,
# unit WW-21, lines 54-58; sha256 ce567435cae0d7933156db7034c8eb8069b9846c24
# d382b6a2ebcba1a921162f) names exactly FIVE delivered-audio gates -- D1 real
# rap, D2 story start, D3 both pace changes, D4 three audibly different
# versions, D5 more than one character voice. WW-21 is the aggregation and
# EVIDENCE-BINDING stage that runs BEFORE spend: it decides only whether the
# five results CARRIED to it may advance. It claims no audio-quality outcome.
#
# WW-24 (2026-10-11): the carried results are not trusted on their binding
# alone -- each result that carries an ``evidence`` record is held to the
# measured-only provenance boundary in ``timing_guard`` (matching export digest,
# actual duration, detector/alignment artifacts, trusted context); a planned or
# stretched timeline never becomes a measurement. That validates the INPUTS to
# D1..D5, so it adds no sixth audio gate.
#
# PROPOSED (WW-21, 2026-10-11): _MIN_AUDIO_RESULTS is the COUNT OF THE FIVE
# GATE NAMES THE PLAN ALREADY NAMES. It is a proposed value -- not a measured
# limit, and NOT a number Trevor set -- and it moves only when the plan's own
# gate list moves. Same label in acceptance-profile.json, CHANGELOG.md and the
# test docstring.
AUDIO_RESULTS = ("D1", "D2", "D3", "D4", "D5")
_MIN_AUDIO_RESULTS = 5            # PROPOSED -- see the note above
#: Every gate verdict that is NOT a PASS blocks. Only PASS advances.
BLOCKING_VERDICTS = ("FAIL", "FLAG", "UNMEASURED", "UNAVAILABLE", "UNKNOWN")
#: A binding naming one of these is a HAND-SET LABEL, not a binding.
_MANUAL_SOURCES = ("manual", "hand", "handset", "hand-set", "relabel", "relabelled",
                   "relabeled", "typed", "literal", "assumed")
_BINDING_KEYS = ("export_digest", "creative_revision", "profile_revision")
_ACCEPTANCE_DIR = os.path.join("music", "acceptance")
ACCEPTANCE_CODE_OK = "ACCEPTANCE_OK"
ACCEPTANCE_CODE_NOT_PROVEN = "ACCEPTANCE_NOT_PROVEN"
# WW-08: the acceptance-critical take gates. EVERY one is emitted for EVERY
# take, and delivery refuses a take whose required gates did not all PASS.
REQUIRED_TAKE_GATES = ("detector", "length", "song_contract", "script_words",
                       "clean_ending", "hook", "hook_placement",
                       "music_under_speech", "story", "timeline")
#: gates that are only DELIVERY-required when THIS run's approved plan declares
#: the matching requirement. A run that plans rap must prove measured rap
#: (WW-06/17.8); a run that plans none has nothing to measure. The gate is
#: recorded either way -- never silently skipped -- and it always counts toward
#: the take's verdict, so an unmeasured read can never make a take PASS.
CONDITIONAL_TAKE_GATES = ("rap_audio", "pace_change")
#: the key that opts a run into the story protocol (WW-02/WW-03). A run that
#: declares no approved revision records the story gate NOT_APPLICABLE WITH
#: the flag below (WW-08 item 2) -- never a bare skip.
STORY_PROTOCOL_KEY = "story_revision"
STORY_OFF_FLAG = "story_protocol_off"
TIMELINE_PENDING_FLAG = "timeline_check_pending"


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
    """List of refusals for ONE KIE createTask music request; [] = send it.

    ``delivered_s`` is the plan's delivered seconds (plan["delivered_s"]),
    never the request duration, which carries Suno's 15% headroom: the
    style contract (core/song_contract, FU-RNBFLOW-SONG) counts hooks on it,
    and a missing style_id or delivered_s is a refusal ("UNMEASURED: ..."),
    never a skipped check.

    WW-30: the ONE accepted contract is the createTask envelope
    (``suno_recipe.check_envelope``: outer model, TOP-LEVEL callBackUrl,
    nested snake_case input, exactly one lyrics source at ``input.lyrics``).
    Every direction below is read from ``input`` -- never from the top level,
    where the retired flat contract used to put them. A payload that is not
    an envelope is refused up front and nothing below is measured on it.
    """
    errs = _R.check_envelope(req)
    inp = _R.envelope_input(req)
    if inp is None:
        return errs
    if inp.get("custom_mode") is not True or inp.get("instrumental") is not False:
        errs.append("custom_mode must be true and instrumental false")
    d = inp.get("duration")
    if not isinstance(d, (int, float)) or isinstance(d, bool) or not 10 <= d <= 360:
        errs.append("duration must be 10-360 s")
    if inp.get("vocal_gender") not in ("f", "m"):
        errs.append("vocal_gender must be f or m")
    for k, v in (("style_weight", 0.75), ("weirdness_constraint", 0.3), ("variety", 0)):
        if inp.get(k) != v:
            errs.append("%s must be %s" % (k, v))
    errs += _R.check_style_text(inp.get("style", ""))
    errs += _R.check_negatives(inp.get("negative_tags", ""), style_id)
    sheet = _R.parse_lyrics(_lyrics_of(req))
    d = d if isinstance(d, (int, float)) and not isinstance(d, bool) else None
    # FU-RNBFLOW-SONG: the style reaches the sheet check (rap is judged as rap,
    # never refused as "no style"), and the style's own contract runs.
    errs += _R.check_lyric_sheet(sheet, client_text, d, style_id=style_id)
    # WW-16: the declared opening vocalise cue must satisfy the ceiling.
    errs += _SC.check_sheet(_lyrics_of(req), style_id, delivered_s, inp.get("style"))["reasons"]
    return errs


def _lyrics_of(req):
    """The ONE approved lyrics source of an envelope: ``input.lyrics``.

    A ``prompt`` beside it is already refused by ``check_envelope``
    (COMPETING_LYRICS); this reader never falls back to it, so a competing
    lyrics source can never reach the judge or the provider.
    """
    return (_R.envelope_input(req) or {}).get("lyrics") or ""


def _input_of(req):
    """The envelope's nested input, refused loudly when it is not one."""
    inp = _R.envelope_input(req)
    if inp is None:
        raise DispatchError("REQUEST_ENVELOPE_REJECTED: %s"
                            % "; ".join(_R.check_envelope(req)))
    return inp


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


def _gate(verdict, detail="", style_flag=None):
    """WW-08: one gate record on the TOTAL vocabulary, with the style flag that
    backs a NOT_APPLICABLE (never a bare skip)."""
    rec = {"verdict": _QC.norm_verdict(verdict), "detail": detail}
    if style_flag:
        rec["style_flag"] = style_flag
    return rec


def _story_gate(take, plan, style_id, D, sheet_text):
    """WW-02/WW-08: the story gate, CALLED from judge_take. A run that declares
    its approved revision runs song_contract.check_returned_story (story start,
    lexical coverage, story arc, words floor) and a checker that is absent, that
    raises, or that cannot pass BLOCKS. A run that declares no revision records
    the flag-backed NOT_APPLICABLE (WW-08 item 2)."""
    rev = (plan or {}).get(STORY_PROTOCOL_KEY) or (take or {}).get(STORY_PROTOCOL_KEY)
    if not rev:
        return _gate("NOT_APPLICABLE",
                     "this run declares no approved story revision (STORY_PROTOCOL_KEY)",
                     style_flag=STORY_OFF_FLAG)
    fn = getattr(_SC, "check_returned_story", None)
    if fn is None:
        return _gate("UNAVAILABLE", "check_returned_story is not installed")
    try:
        res = fn(take, style_id, D, sheet_text, plan)
    except Exception as exc:            # noqa: BLE001 - a gate that raises blocks
        return _gate("UNAVAILABLE", "check_returned_story raised %r" % (exc,))
    res = res or {}
    detail = str(res.get("detail") or res.get("reason") or "")
    return _gate(res.get("verdict", "UNKNOWN"), "story revision %s: %s" % (rev, detail))


def _timeline_gate(take, plan, style_id, D):
    """WW-08/WW-04: the timeline-integrity gate, CALLED from judge_take. WW-04
    owns the partition check (timing_guard); when this revision ships no
    checker the gate is recorded NOT_APPLICABLE WITH the flag below, never a
    silent skip, and an absent or raising checker BLOCKS."""
    try:
        import timing_guard as _TG   # noqa: PLC0415
    except Exception:                # noqa: BLE001 - an unimportable checker blocks
        return _gate("UNAVAILABLE", "timing_guard is not installed")
    fn = (getattr(_TG, "timeline_integrity", None)
          or getattr(_TG, "check_timeline", None))
    if fn is None:
        return _gate("NOT_APPLICABLE",
                     "this revision ships no timeline-integrity checker",
                     style_flag=TIMELINE_PENDING_FLAG)
    try:
        res = fn(take, D)
    except Exception as exc:         # noqa: BLE001 - a gate that raises blocks
        return _gate("UNAVAILABLE", "the timeline gate raised %r" % (exc,))
    res = res or {}
    return _gate(res.get("verdict", "UNKNOWN"), str(res.get("detail", "")))


def _rap_required(plan, style_id):
    """True when the approved plan carries a rap budget (WW-06 item 3). A run
    with no rap budget has no rap delivery to prove."""
    words = (plan or {}).get("words") or {}
    return bool(words.get("rap")) or _planned_pct(plan, style_id, "rap") is not None


def _pace_required(plan, take):
    """True on EVERY run, method or not (Trevor 2026-10-13, METHOD-INTEGRATION
    F4 / conflict C5).

    It used to be "True when this run carries an approved pace order", so a
    run that ordered no pace change had "nothing to enforce" and PASSed --
    the gate was optional. Both musical turns are now mandatory and measured:
    the ERM drop and the second turn at the Hero Shift (on a run with no
    method block the seams sit on the arc's pain-turn and solution-arrival
    beats). The gate is therefore a REQUIRED gate of every take everywhere --
    an unmeasured turn can never reach PASS -- and ANY run, method or not,
    that carries no pace order at all is refused at dispatch
    (``PACE_TURNS_REQUIRED``, in ``run_takes``) or records the gate
    UNMEASURED when it is judged directly.
    The arguments are kept so no caller changes.
    """
    return True


def _method_plan(plan):
    """True when the approved plan carries the run's method block
    (``control/method.json`` read by the factory). Everything this unit adds
    for the first vocal is INERT without it: a run with no method block is
    judged exactly as it is today."""
    m = (plan or {}).get("method")
    return isinstance(m, dict) and bool(m)


def _erm_apex_s(plan, delivered_s):
    """The ERM apex of a METHOD run, read off the plan -- no table here.

    SPEC B4's pacing profile picks it: ``feed`` (paid ads, short form, every
    trailer and ad clip cut from a master) compresses the ERM so the first
    sung line lands by 15 percent of the runtime; ``story`` (campaign
    episodes, testimonials, lessons) uses the method's own ERM window, whose
    midpoint is the apex the plan already carries (``erm_apex_s``, else the
    window's midpoint). A plan that carries an explicit ``erm_apex_s`` always
    wins, and a run that carries neither returns None (the caller records
    UNMEASURED: missing evidence is never PASS)."""
    m = (plan or {}).get("method")
    if not isinstance(m, dict) or not m:
        return None

    def _num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if _num(m.get("erm_apex_s")) and float(m["erm_apex_s"]) > 0:
        return float(m["erm_apex_s"])
    if str(m.get("profile") or "").strip().lower() == "feed":
        if isinstance(delivered_s, (int, float)) and delivered_s > 0:
            return float(delivered_s) * _SS.FIRST_SUNG_TARGET_PCT / 100.0
        return None
    w = m.get("erm_window_s")
    if isinstance(w, (list, tuple)) and len(w) == 2 and all(_num(v) for v in w):
        return (float(w[0]) + float(w[1])) / 2.0
    return None


def _pace_turns_required_detail():
    return ("PACE_TURNS_REQUIRED: both pace turns are mandatory and measured "
            "on every run (Trevor 2026-10-13); this run carries no pace order, "
            "so the ERM drop and the second turn cannot be measured")


def judge_take(take, plan, script_words, hook_text, spoken_range_pct=None,
               style_id=None, sheet_text=None):
    """WW-08: run EVERY required gate; a gate that raises blocks and never
    passes."""
    try:
        return _judge_take_inner(take, plan, script_words, hook_text,
                                 spoken_range_pct, style_id, sheet_text)
    except Exception as exc:      # noqa: BLE001 - a raised exception blocks
        return _finish({"judge_exception": _gate("FAIL", "the judge raised %r" % (exc,))})


def _judge_take_inner(take, plan, script_words, hook_text, spoken_range_pct=None,
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

    def put(name, verdict, detail="", style_flag=None):
        g[name] = _gate(verdict, detail, style_flag)

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
            # WW-21: THE no-planned-and-no-measured-rap LOOPHOLE. This branch
            # used to be a PASS ("no rap planned, none measured"), so an
            # R&B Flow take whose plan carries no rap word count AND whose
            # audio measured 0.0 s of rap advanced as if the rap gate had been
            # satisfied. It had not: the style's whole definition is that it
            # DELIVERS rap. Missing evidence is not a deviation, so this can
            # never be a PASS -- the take is flagged here and the WW-21
            # acceptance boundary (accept_audio_results) blocks it outright,
            # because only PASS advances there.
            put("rap_share", "FLAG",
                "RAP_NEITHER_PLANNED_NOR_MEASURED: style %r delivers rap, the approved plan "
                "declares no rap words (_planned_pct -> None) and the take measured %.1f s of "
                "rap. Missing evidence is not a deviation; this take cannot pass."
                % (style_id, m["rap_seconds"]))
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
    # WWFIXGAPS U1 (defect 2): THE TWO D1 AUDIO GATES ARE WIRED IN HERE.
    # Before this they were never called by the pipeline, so nothing made an
    # UNMEASURED result block a take; `run_takes` could deliver a PASS on an
    # unmeasured rap read or an unmeasured gear change.
    # RAP (music_qc/rap_check): only a rap-delivering style carries rap, so
    # the gate applies there and nowhere else; with no labelled rap control it
    # returns UNMEASURED, and `_finish` never lets UNMEASURED reach PASS.
    if t["rap_delivery"]:
        rg = _RC.gate(segs)
        put("rap_audio", rg["verdict"], rg["reason"])
    else:
        put("rap_audio", "PASS", "style %r delivers no rap" % (style_id,))
    # PACE (music_qc/pace_change): the ordered gear change rides the plan. An
    # order with missing onset or energy evidence on the TAKE is UNMEASURED
    # (blocks PASS); evidence that shows no gear change is FAIL. bpm is
    # reported and never grants a PASS.
    #
    # METHOD C5 (Trevor 2026-10-13, BUILD-PLAN W1-method-song-U1): both turns
    # are mandatory on EVERY run, so a take that reaches the judge with no
    # order cannot be told "there is nothing to enforce" -- that verdict is a
    # PASS, and an unmeasured turn may never reach PASS. The gate records
    # UNMEASURED (PACE_TURNS_REQUIRED) and blocks, method run or not; every
    # real run was already refused at dispatch, so this is the direct-judge
    # seam (and the last line of defence) rather than a second dispatch rule.
    pg = _PC.judge_plan_pace(plan, take.get("pace_before"), take.get("pace_problem"),
                             take.get("pace_after"),
                             envelope=take.get("pace_envelope"),
                             hop_s=take.get("pace_hop_s"),
                             bpm_before=take.get("bpm_before"),
                             bpm_after=take.get("bpm_after"))
    if pg.get("applicable") is False:
        put("pace_change", "UNMEASURED", _pace_turns_required_detail())
    else:
        put("pace_change", pg["verdict"], pg.get("detail") or pg.get("reason_code", ""))
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
    if _method_plan(plan):
        # METHOD C3 (Trevor 2026-10-13): on a method run the first sung line
        # lands at the ERM apex, so the gate is the ERM window -- early AND
        # late are FAIL -- and never the 15 percent of runtime target, which
        # would call a method-correct 15 s take "late, redo". One copy of the
        # rule lives in spoken_share.judge_first_vocal_at_erm.
        erm_r = _SSM.judge_first_vocal_at_erm(fs, take.get("sung_starts"),
                                              _erm_apex_s(plan, D))
        put("first_sung", erm_r["verdict"], erm_r["detail"])
    elif isinstance(fs, (int, float)):
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
    # WW-02/WW-08: the story gate (check_returned_story) is CALLED here, in the
    # judge, together with the timeline-integrity gate. Both are emitted for
    # EVERY take: a checker that is absent, that raises, or that cannot pass
    # BLOCKS; a genuinely inapplicable one carries its style flag.
    g["story"] = _story_gate(take, plan, sc_sid or sid, D, sheet)
    g["timeline"] = _timeline_gate(take, plan, sc_sid or sid, D)
    # WW-18: the DELIVERY-required set = the always-required gates plus the
    # conditional gates THIS run declared on its approved plan. A run that plans
    # rap must prove measured rap; one that plans none has nothing to measure.
    required = list(REQUIRED_TAKE_GATES)
    if _rap_required(plan, sc_sid or sid):
        required.append("rap_audio")
    if _pace_required(plan, take):
        required.append("pace_change")
    return _finish(g, required)


def _finish(g, required=None):
    """THE TOTAL finisher, and the WW-08 aggregate over the WHOLE verdict
    vocabulary. FAIL when a gate FAILs; otherwise FLAG when any gate FLAGs OR
    is UNMEASURED; only an all-PASS take PASSes.

    WWFIXGAPS U1 (defect 2): UNMEASURED counts as a flag, never as nothing --
    a take carrying an unmeasured gate (no labelled rap control, no gear-change
    evidence) cannot reach PASS. It is kept OUT of ``failed`` on purpose: it is
    missing evidence, not a measured failure.

    WW-21 (total, fail-closed): this vocabulary is now TOTAL, so no shape of
    input can reach PASS by accident. A gate verdict of FAIL, FLAG,
    UNMEASURED, UNAVAILABLE or UNKNOWN, a verdict string that is missing,
    empty or unrecognised (a MALFORMED record), a non-mapping record, a gate
    of ``required`` that is ABSENT, an EMPTY gate set and any exception raised
    while reading the mapping ALL block. Before this, ``_finish({})`` returned
    PASS -- an empty gate set was indistinguishable from a perfect take -- and
    an UNKNOWN or UNAVAILABLE gate was silently ignored.

    WW-08 (kept whole, both sides): every required gate that did NOT run is
    recorded in ``gates`` as UNMEASURED evidence -- never silently absent --
    while the very same names stay in ``missing`` for the WW-21 reason list,
    and ``required_gates`` is carried for the DELIVERY decision
    (``take_accepted``). A non-mapping record is UNMEASURED evidence to
    ``take_accepted`` and a MALFORMED record to WW-21; both block.
    """
    req = tuple(GATES) if required is None else tuple(required)
    orig = g if isinstance(g, dict) else {}
    gates = dict(orig)
    if orig:
        for k in req:
            if k not in gates:
                gates[k] = _gate("UNMEASURED", "required gate %s was not run" % k)
    bad, flags, malformed, missing = [], [], [], []
    try:
        for k in req:
            if k not in orig:
                missing.append(k)
        for k, rec in orig.items():
            v = rec.get("verdict") if isinstance(rec, dict) else None
            if not isinstance(v, str) or not v.strip():
                malformed.append(k)
                continue
            v = v.strip().upper()
            # WW-08 (kept whole): PASS advances, and so does a NOT_APPLICABLE
            # that carries the style flag backing it. Everything else blocks.
            if _QC.verdict_advances(v, rec.get("style_flag") if isinstance(rec, dict) else None):
                continue
            if v == "FAIL":
                bad.append(k)
            elif v in BLOCKING_VERDICTS or v == "NOT_APPLICABLE":
                flags.append(k)
            else:
                malformed.append(k)
    except Exception as e:                     # noqa: BLE001 -- a raised error blocks
        malformed.append("RAISED_ERROR:%s" % type(e).__name__)
    if not isinstance(g, dict) or not gates:
        missing = missing or ["<empty>"]
    blocked_by = (["EMPTY_GATE_SET: an empty gate set never passes"] if (not isinstance(g, dict) or not gates) else [])
    blocked_by += ["MISSING_REQUIRED_GATE: %s" % k for k in missing]
    blocked_by += ["MALFORMED_GATE_RECORD: %s" % k for k in malformed]
    verdict = "FAIL" if (bad or malformed or missing or not gates) else ("FLAG" if flags else "PASS")
    return {"verdict": verdict, "gates": gates, "failed": bad, "flagged": flags,
            "malformed": malformed, "missing": missing, "blocked_by": blocked_by,
            "required_gates": sorted(req), "missing_required": sorted(missing),
            "blocked": sorted(set(bad) | set(flags) | set(malformed))}
# ---- WW-21: the aggregation and evidence-binding boundary ------------------
#
# One implementation, one place. `judge_take`/`_finish` judge ONE take's gates;
# `accept_audio_results` is the boundary that stands between the five CARRIED
# delivered-audio results and any offer, pick or purchase. It is pure (no
# network, no spend of its own), so a refusal costs zero purchases by
# construction -- every path that calls it is asserted at zero spend.


def _open_json(path):
    """Read a JSON document; None for absent or unreadable. Never raises."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def acceptance_profile():
    """core/acceptance-profile.json. None when absent/unreadable -- and None
    BLOCKS, so a lost profile can never be read as "no gates required"."""
    return _open_json(os.path.join(_CORE, "acceptance-profile.json"))


def profile_revision(profile=None):
    p = profile if isinstance(profile, dict) else acceptance_profile()
    return (p or {}).get("profile_version")


def _profile_required(profile):
    """The required audio results from the profile, else the module constant.
    A malformed list falls back to ``AUDIO_RESULTS``; it never empties."""
    rows = ((profile or {}).get("audio_results") or {}).get("required")
    if isinstance(rows, list) and rows and all(isinstance(r, str) and r for r in rows):
        return tuple(rows)
    return AUDIO_RESULTS


def _profile_min_count(profile):
    """The PROPOSED minimum count of carried results, read from the profile so
    the key the profile WRITES is the key this boundary READS; the module
    constant is the fallback, never an empty value."""
    n = ((profile or {}).get("audio_results") or {}).get("minimum_count")
    if isinstance(n, int) and not isinstance(n, bool) and n > 0:
        return n
    return _MIN_AUDIO_RESULTS


def _block(reasons, results=None, binding=None, required=None):
    """Every refusal from this boundary has the same shape, and every one of
    them reports zero purchases -- nothing here can spend."""
    rs = [str(r) for r in reasons]
    return {"verdict": "FAIL", "blocked": True, "reasons": rs, "blocked_by": list(rs),
            "results": results if isinstance(results, dict) else {},
            "binding": binding if isinstance(binding, dict) else {},
            "required": list(required or AUDIO_RESULTS),
            "purchases": 0,
            "next_action": "no take is offered, picked or purchased on this path"}


def binding_reasons(binding, where="take"):
    """Why this binding is not admissible. [] = admissible.

    A binding is the take's OWN export digest (sha256 of the delivered file),
    its creative revision and the profile revision the result was produced
    against. A hand-set label -- ``source: manual``, a bare string, a missing
    key -- is NOT a binding; a manually relabelled source never substitutes
    for the digest of the export that was actually measured.
    """
    if not isinstance(binding, dict):
        return ["MALFORMED_BINDING: the %s binding is %s, not a mapping"
                % (where, type(binding).__name__)]
    out = []
    src = str(binding.get("source", "") or "").strip().lower().replace("_", "-")
    if src in _MANUAL_SOURCES:
        out.append("MANUAL_RELABEL: the %s binding says source=%r; a hand-set label is not a "
                   "binding and cannot stand in for the export digest" % (where, src))
    for k in _BINDING_KEYS:
        v = binding.get(k)
        if not isinstance(v, (str, int)) or isinstance(v, bool) or not str(v).strip():
            out.append("MISSING_BINDING: the %s binding carries no %s" % (where, k))
    dig = binding.get("export_digest")
    if isinstance(dig, str) and dig.strip() and not re.fullmatch(r"[0-9a-f]{64}", dig.strip().lower()):
        out.append("MALFORMED_DIGEST: the %s export_digest is not a sha256 (%r)"
                   % (where, dig))
    return out


def accept_audio_results(results, binding, required=None, profile=None):
    """WW-21: THE total, fail-closed aggregation boundary over the carried
    delivered-audio results. Returns ``{verdict, reasons, blocked_by, ...}``.

    It advances ONLY when every required delivered-audio result is present, is
    a mapping, carries a PASS verdict, and is bound to the exact export digest,
    creative revision and profile revision of the take being advanced. It
    BLOCKS, with a named reason, on: a missing result, an empty result set, a
    non-mapping result set, a malformed record (no verdict string), a verdict
    of FAIL/FLAG/UNMEASURED/UNAVAILABLE/UNKNOWN, an unrecognised verdict, a
    stale digest or revision, a manual relabel, a missing/absent binding, an
    unavailable profile and any exception raised while reading any of it.

    This is NOT a sixth audio gate: it measures no audio and claims no quality
    outcome. It is the boundary that stops an incomplete or unbound receipt
    from reaching spend.
    """
    try:
        return _accept_audio_results(results, binding, required, profile)
    except Exception as e:                     # noqa: BLE001 -- a raised error blocks
        return _block(["RAISED_ERROR: %s: %s" % (type(e).__name__, e)],
                      results if isinstance(results, dict) else None,
                      binding if isinstance(binding, dict) else None, required)


def _accept_audio_results(results, binding, required, profile):
    prof = profile if profile is not None else acceptance_profile()
    want = _profile_required(prof) if required is None else tuple(required)
    if not isinstance(prof, dict):
        return _block(["PROFILE_UNAVAILABLE: acceptance-profile.json is missing or unreadable; "
                       "no result may advance without the profile revision it was produced against"],
                      results, binding, want)
    reasons = []
    if not isinstance(results, dict):
        return _block(["MALFORMED_RESULT_SET: the carried results are %s, not a mapping"
                       % type(results).__name__], None, binding, want)
    if not results:
        return _block(["EMPTY_GATE_SET: no delivered-audio results were carried; "
                       "an empty result set never passes"], results, binding, want)
    reasons += binding_reasons(binding, "take")
    prof_rev = prof.get("profile_version")
    if not isinstance(prof_rev, str) or not prof_rev.strip():
        reasons.append("PROFILE_UNAVAILABLE: acceptance-profile.json carries no profile_version")
    minimum = _profile_min_count(prof)
    if len(results) < minimum:
        reasons.append("INCOMPLETE_EVIDENCE: %d delivered-audio results carried, %d required "
                       "(PROPOSED count of the five gates the plan names)"
                       % (len(results), minimum))
    for name in want:
        rec = results.get(name)
        if rec is None:
            reasons.append("MISSING_AUDIO_RESULT: required delivered-audio result %s was not "
                           "carried" % name)
            continue
        if not isinstance(rec, dict):
            reasons.append("MALFORMED_RECORD: %s is %s, not a mapping"
                           % (name, type(rec).__name__))
            continue
        v = rec.get("verdict")
        if not isinstance(v, str) or not v.strip():
            reasons.append("MALFORMED_RECORD: %s carries no verdict string" % name)
            continue
        if v.strip().upper() != "PASS":
            reasons.append("BLOCKING_VERDICT: %s returned %r; only PASS advances"
                           % (name, v.strip().upper()))
            continue
        rb = rec.get("binding")
        br = binding_reasons(rb, name)
        if br:
            reasons.extend(br)
            continue
        for k in _BINDING_KEYS:
            if str(rb.get(k)).strip().lower() != str(binding.get(k)).strip().lower():
                reasons.append("STALE_BINDING: %s was produced against %s=%r but the take being "
                               "advanced carries %r" % (name, k, rb.get(k), binding.get(k)))
        if isinstance(prof_rev, str) and str(rb.get("profile_revision")).strip() != prof_rev.strip():
            reasons.append("STALE_PROFILE: %s was produced against profile revision %r; the "
                           "profile in force is %r"
                           % (name, rb.get("profile_revision"), prof_rev))
        # WW-24: validate the PROVENANCE of the evidence this result carries.
        # A PLANNED/stretched timeline, a digest that does not match the take
        # being advanced, a missing actual duration, a doubled runtime, a
        # missing detector/alignment artifact or a hand-set source="measured"
        # label BLOCKS the result HERE -- the input validator for the five
        # delivered-audio results, never a sixth audio gate. A result carrying
        # no evidence record makes no measurement claim to validate.
        ev = rec.get("evidence")
        if ev is not None:
            reasons.extend(_TG.measured_evidence_reasons(ev, binding=binding))
    for name in sorted(results):
        if name in want:
            continue
        rec = results[name]
        v = rec.get("verdict") if isinstance(rec, dict) else None
        if not isinstance(v, str) or v.strip().upper() != "PASS":
            reasons.append("UNEXPECTED_AUDIO_RESULT: %s is carried but is not one of the "
                           "required results and did not PASS (%r)" % (name, v))
    if reasons:
        return _block(reasons, results, binding, want)
    return {"verdict": "PASS", "blocked": False, "reasons": [], "blocked_by": [],
            "results": dict(results), "binding": dict(binding), "required": list(want),
            "profile_revision": prof_rev, "purchases": 0,
            "note": "all %d delivered-audio results PASS and are bound to this take; "
                    "nothing was measured or claimed here" % len(want)}


def _sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def take_binding(export_path, creative_revision, profile=None):
    """The binding a take is advanced under: its OWN export digest plus the
    creative and profile revisions it was produced against."""
    return {"export_digest": _sha256_file(export_path),
            "creative_revision": str(creative_revision),
            "profile_revision": str(profile_revision(profile) or "")}


def record_acceptance(run_dir, variant_id, binding, results, required=None):
    """Write ONE variant's WW-21 acceptance record under
    ``<run>/music/acceptance/<variant>.json`` and return it. This is the
    WRITER ``acceptance_from_run`` reads, so the read key and the written key
    are the same key by construction."""
    rec = accept_audio_results(results, binding, required=required)
    out = dict(rec, variant_id=str(variant_id))
    p = os.path.join(run_dir, _ACCEPTANCE_DIR, "%s.json" % variant_id)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, sort_keys=True)
    return out


def _take_exists(d):
    try:
        return any(n.lower().endswith((".mp3", ".wav", ".flac", ".m4a", ".aac"))
                   for n in os.listdir(d))
    except OSError:
        return False


def acceptance_from_run(run_dir):
    """Read the WW-21 acceptance records and the take folders under the run.

    ``applicable`` is False only when the run has NEITHER an acceptance record
    NOR a produced take -- a run that never reached the music stage has
    nothing to gate. The moment a variant has a produced take under
    ``<run>/music/takes/<variant>/`` (the folder ``_real_generate`` fills,
    where the dispatch envelope is written), an acceptance record is REQUIRED
    for it: a take on disk with no all-PASS acceptance record BLOCKS. That is
    what keeps this a live guard and not a key nobody writes.
    """
    base = os.path.join(run_dir, _ACCEPTANCE_DIR)
    takes = os.path.join(run_dir, "music", "takes")
    records = {}
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if not name.endswith(".json"):
                continue
            rec = _open_json(os.path.join(base, name))
            if not isinstance(rec, dict):
                continue
            vid = str(rec.get("variant_id") or name[:-5])
            records[vid] = dict(rec, variant_id=vid)
    if os.path.isdir(takes):
        for name in sorted(os.listdir(takes)):
            d = os.path.join(takes, name)
            if not os.path.isdir(d) or not _take_exists(d):
                continue
            if name in records:
                continue
            records[name] = {
                "variant_id": name, "verdict": "FAIL", "blocked": True,
                "reasons": ["ACCEPTANCE_RECORD_MISSING: music/takes/%s holds a produced take but "
                            "no WW-21 acceptance record was written for it; only a complete set "
                            "of five PASS, bound delivered-audio results may advance" % name],
                "purchases": 0}
    if not records:
        return {"applicable": False, "verdict": "UNAVAILABLE", "allowed": False,
                "blocked": [], "variants": {}}
    bad = sorted(v for v, r in records.items() if r.get("verdict") != "PASS")
    return {"applicable": True, "verdict": "FAIL" if bad else "PASS",
            "allowed": not bad, "blocked": bad, "variants": records}


def acceptance_refusal(run_dir, action):
    """The delivery-boundary refusal: None when nothing is held, else the
    refusal record. Mirrors ``song_choices.overlap._overlap_refusal``; the
    BLOCK reaches the offer, the pick and every paid job."""
    chk = acceptance_from_run(run_dir)
    if not chk.get("applicable"):
        return None
    if chk.get("allowed"):
        return None
    detail = []
    for v in chk.get("blocked") or []:
        detail += ["%s: %s" % (v, r) for r in (chk["variants"][v].get("reasons") or [])]
    return {"reason_code": ACCEPTANCE_CODE_NOT_PROVEN,
            "detail": "the WW-21 acceptance boundary has not passed (%s); %s is held. Only a "
                      "complete set of five PASS delivered-audio results, each bound to the "
                      "take's export digest, creative revision and profile revision, may "
                      "advance -- zero purchases on this path."
                      % ("; ".join(detail[:4]) or "no PASS record", action),
            "blocked": chk.get("blocked") or [],
            "next_action": "re-run the five delivered-audio results against the export being "
                           "advanced and record them with record_acceptance; no paid retry is "
                           "authorised by this refusal."}
def take_accepted(rcpt):
    """WW-18: the ONE delivery decision. A take whose REQUIRED gate set is not
    all PASS (bar a style-backed NOT_APPLICABLE) is never offered; a missing
    required gate and an empty gate set are refused. Returns (ok, reason)."""
    if not isinstance(rcpt, dict):
        return False, "no receipt"
    gates = rcpt.get("gates") or {}
    if not gates:
        return False, "empty gate set"
    required = rcpt.get("required_gates") or REQUIRED_TAKE_GATES
    missing = [k for k in required if k not in gates]
    if missing:
        return False, "missing required gate(s): %s" % ",".join(missing)
    bad = sorted(k for k in required if _QC.gate_blocked(gates[k]))
    if bad:
        return False, "required gate(s) not PASS: %s" % ",".join(bad)
    return True, ""


def constituent_receipt(take, rcpt, plan=None):
    """WW-08 item 3: the per-take constituent-evidence receipt, bound to the
    audio digest, the creative fingerprint, the acceptance-profile version and
    the checker identity, carrying every gate verdict and the delivery verdict."""
    plan = plan or {}
    prof_v = plan.get("acceptance_profile_version") or plan.get("profile_version")
    gates = (rcpt or {}).get("gates") or {}
    rec = _QC.constituent_receipt(
        audio_digest=take.get("audio_digest") or take.get("audio_sha256"),
        creative_fingerprint=plan.get("creative_fingerprint") or plan.get(STORY_PROTOCOL_KEY),
        profile_version=prof_v, checker=TOOL_NAME, gates=gates)
    ok, why = take_accepted(rcpt)
    rec["required_gates"] = list(rcpt.get("required_gates") or REQUIRED_TAKE_GATES)
    rec["accepted"] = ok
    rec["blocked"] = [] if ok else [why]
    return rec


def constituent_ok(rec):
    """(ok, reason) for a constituent-evidence receipt recorded with a take.
    WW-08: a missing, non-current or blocked receipt never counts."""
    if not isinstance(rec, dict) or rec.get("schema") != _QC.CONSTITUENT_SCHEMA:
        return False, "no constituent-evidence receipt"
    if not rec.get("accepted"):
        return False, "; ".join(str(x) for x in (rec.get("blocked") or
                                                 ["required gates did not all PASS"]))
    return True, ""


def run_takes(request, plan, generate, measure, save, script_words, hook_text,
              spoken_range_pct=None, cap_cents=SPEND_CAP_CENTS, cost_cents=GEN_COST_CENTS,
              kie=_LG.kie_request, style_id=None, script_approval=None, run_dir=None):
    """Generate until a take passes or the cap is spent.

    generate(request) -> list of takes (2 per generation, each with audio ids);
    measure(take) -> the measured fields for judge_take; save(take, receipt)
    must store the vocal stem and timestamps (called for EVERY take, even
    failures). Every generation goes through the load governor (``kie``): a NEW
    request draws from the 20-per-10-s bucket and a 429 is resubmitted.
    ``script_approval`` is the run's script-approval record; left out, it is read from ``run_dir`` (or request["run_dir"]):
    required and not approved for these lyrics = refused before any generation.
    Returns {delivered, verdict, receipt, receipts, spent_cents}.
    WW-18: only a take whose REQUIRED gate set all PASSes is delivered; every
    other take (FAIL, FLAG, UNMEASURED, UNAVAILABLE, UNKNOWN) is judged and its
    paid stem kept, but never delivered.
    """
    # WW-30: every direction is read from the createTask envelope's nested
    # input. A request that is not an envelope (the retired flat contract, a
    # misplaced callback, competing lyrics) is refused HERE, before the script
    # gate, the ledger and any generation.
    envelope_errs = _R.check_envelope(request)
    if envelope_errs:
        raise DispatchError("REQUEST_ENVELOPE_REJECTED: %s"
                            % "; ".join(envelope_errs))
    inp = _input_of(request)
    # SCRIPT APPROVAL: a client who asked to approve the script first gets no generation until they do.
    if script_approval is None:       # found in the run folder; nobody passes it by hand
        script_approval = _SA.record_near(run_dir, request.get("run_dir"))
    refusal = _SA.check_script_approval(script_approval, _lyrics_of(request))
    if refusal:
        raise DispatchError("%s: %s" % (refusal["reason_code"], refusal["detail"]))
    # G9 (FU-U6, plan E.2 default): the request carries the planned time plus the
    # >=15 percent Suno headroom; the master is still trimmed to L-2 by
    # master_length, so "whole tracks only" is judged against that headroom
    # (words_fit.max_suno_duration), never a patch/short duration.
    allowed = _WF.max_suno_duration(plan["delivered_s"])
    if inp.get("duration") not in (plan["delivered_s"], allowed):
        raise DispatchError("whole tracks only: request duration %r != planned %r (or its %r s "
                            "Suno headroom; never a patch)"
                            % (inp.get("duration"), plan["delivered_s"], allowed))
    # FU-HOOK-PLACEMENT: the director's hook_plan rides the request as
    # _hook_plan; it moves into the judge's plan and never reaches KIE.
    plan = dict(plan, hook_plan=request.get("_hook_plan") or plan.get("hook_plan"))
    request = {k: v for k, v in request.items() if k != "_hook_plan"}
    # WWFIX D1/F2: the ordered pace change rides the request the same way
    # (_pace_plan). It moves into the judge's plan and NEVER reaches KIE.
    plan = dict(plan, pace_change=request.get("_pace_plan") or plan.get("pace_change"))
    request = {k: v for k, v in request.items() if k != "_pace_plan"}
    # WW-23: BEFORE any generation, the ordered pace change must be complete and
    # the exact request the provider would receive must carry BOTH directions.
    # A missing seam, a reused boundary, a final style that carries only one
    # transition, or the internal _pace_plan metadata leaking into any
    # provider-visible field is refused HERE -- nothing is spent. The audio
    # check (D3) runs later, on the exports, inside judge_take.
    #
    # METHOD C5 (Trevor 2026-10-13, METHOD-INTEGRATION F4): BOTH pace turns are
    # mandatory and measured, so "this run ordered no pace change" is no longer
    # "nothing to enforce": a run that carries no pace order at all is refused
    # HERE, at dispatch, before any spend, with PACE_TURNS_REQUIRED -- the two
    # turns cannot be measured off a take nobody ordered. BUILD-PLAN
    # W1-method-song-U1 makes this EVERY run, method or not: `_pace_required`
    # is True on every run, so the order is as mandatory at dispatch as the
    # gate is at the judge. A method run names its seams after the blueprint's
    # own cues (ERM Drop / Hero Shift); a run with no method block names the
    # arc's pain-turn and solution-arrival beats -- the ORDER is required in
    # both cases, only its anchor names differ. The first-sung rule and every
    # other method-only check stay exactly as they are: those run only when
    # the run carries control/method.json (inert-until-wired).
    # The order is read the SAME two keys the judge reads (``judge_plan_pace``):
    # ``pace_change`` (merged from the request's _pace_plan above) or a plan
    # that carries the runner's own ``_pace_plan`` key (song_choices.cmd_generate).
    if not (plan.get("pace_change") or plan.get("_pace_plan")):
        raise DispatchError(_pace_turns_required_detail())
    pace_errs = _PC.check_pace_plan(plan["pace_change"])
    pace_errs += _SCM.check_pace_style(inp.get("style"), plan["pace_change"])
    if _PC.pace_provider_leak(request):
        pace_errs.append("PACE_INTERNAL_METADATA_IN_PAYLOAD: the internal "
                         "_pace_plan judging metadata reaches a provider field")
    if pace_errs:
        raise DispatchError("PACE_PAYLOAD_REJECTED: %s" % "; ".join(pace_errs))
    # D2: when the run answered Yes to SONG APPROVAL the music stage runs as
    # THREE variants, and each variant is generated per variant; the three
    # variants run in PARALLEL lanes (song_choices.plan_units, providerSlots 3,
    # reserve 0), so a variant is one lane's whole job, never a second take of
    # the same arrangement.
    refuse_asr("faster-" + "wh" + "isper")
    plan = dict(plan, sheet_text=plan.get("sheet_text") or _lyrics_of(request))
    spent, receipts = 0, []
    while spent + cost_cents <= cap_cents:
        spent += cost_cents
        for take in kie(lambda: generate(request), "song generate", generation=True):
            take = dict(take, **measure(take))
            rcpt = judge_take(take, plan, script_words, hook_text, spoken_range_pct,
                              style_id, _lyrics_of(request))
            save(take, rcpt)                               # stem + timestamps, every take
            receipts.append(rcpt)
            # WW-18: only a take whose REQUIRED gate set all PASSes is delivered.
            # Every other take is judged and its paid stem kept, never offered.
            if take_accepted(rcpt)[0]:
                return {"delivered": take, "verdict": rcpt["verdict"],
                        "receipt": constituent_receipt(take, rcpt, plan),
                        "receipts": receipts, "spent_cents": spent}
    return {"delivered": None, "verdict": "FAIL", "receipts": receipts, "spent_cents": spent}
