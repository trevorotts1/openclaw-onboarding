#!/usr/bin/env python3
"""Spoken-share targets (SPK001): one band, every length, every style.

Source: Decision log 37 (D15 retarget) 2026-10-07; plan 6.7; SPK001 retarget
(Trevor, 2026-10-08): "Okay, let's go to your recommendation that cut it to
about 20-25%."

Why: Suno turns spoken lyric lines into long talking, and the old targets did
not add up (spoken 35-40% of runtime plus a music-only intro and end card left
at most about 50% for singing, never the 55-60% goal). Now:

  * spoken share of RUNTIME: 20-25%, target 22.5 (SPOKEN_TARGET_PCT);
  * the lyric writer's spoken WORD share is DERIVED, not a constant: the ad's
    spoken target (target_for_range) run through the length formula's measured
    words-per-second rates (spoken_word_pct); the measured BSW passes use
    about 21% of the words for a 17.5% runtime share;
  * singing is measured against VOICE time, sung / (sung + spoken), target
    77.5 (SUNG_TARGET_PCT). A music-only intro, gaps and the end card never
    count against it;
  * both numbers use Trevor's band: within 5 accept, 5-10 accept with a flag,
    past 10 redo. The only hard reject is no sung stretch of 6 s.

Same for every length and every music style -- rap counts as spoken-style
delivery, so a rap-heavy cut cannot measure under the band by accident. The
earlier per-length targets and the earlier wider ceiling are retired: this
module holds ONE band and nothing keyed by length.

The spoken opener (D12) stays short. H6 (owner, 2026-10-08): the first REAL
singing -- a sung stretch of at least 6 s, measured on the vocal stem, never
read off section labels -- is a TARGET of 15% of runtime (about 9 s in a 60 s
ad), judged by the band below. ``check_first_sung`` is the planner/QC rule;
``check_share``/``check_plan`` are the measuring and QC sides.

This package is the single source of truth for the three numbers. The length
engine, the lyric planner and the QC all read them from here instead of
keeping their own copy.

stdlib only: no network, no provider, no spend, no media file, no absolute
operator path (nothing in this package opens a file at all).

Run: python3 core/spoken_share/test_spoken_share.py
"""
from __future__ import annotations

from math import isfinite

TOOL_NAME = "spoken_share"
TOOL_VERSION = "1.1.0"
SCHEMA_VERSION = "blackceo.spoken-share/v1"
SOURCE = "Decision log 37 (D15 retarget) 2026-10-07; plan 6.7; SPK001 2026-10-08"

# ---- the three numbers (owner D15 retarget) -------------------------------
SPOKEN_TARGET_PCT = 22.5  # the target: spoken share of runtime (20-25), as a percent
SPOKEN_MIN_PCT = 12.5     # redo edge: target - FLAG_PTS (no absolute floor; reporting only)
SPOKEN_MAX_PCT = 32.5     # redo edge: target + FLAG_PTS (reporting only)

TARGET = SPOKEN_TARGET_PCT / 100.0
FLOOR = SPOKEN_MIN_PCT / 100.0
CAP = SPOKEN_MAX_PCT / 100.0

#: Lyric delivery labels: what a sheet tag or a sung/rap/spoken line carries.
DELIVERIES = ("spoken", "rap", "sung")
#: Timing-segment deliveries: the lyric deliveries plus FU-U3's "none" --
#: time with no voice at all (music-only intro, gaps, the end card). "none"
#: counts in RUNTIME and never in voice time; it is a segment state, not a
#: sheet tag, so it never joins DELIVERIES.
SEGMENT_DELIVERIES = DELIVERIES + ("none",)
#: Deliveries that ARE voice (somebody is speaking, rapping or singing).
VOICE_DELIVERIES = frozenset(DELIVERIES)

#: Rap is talking over a beat, so it is spoken-style delivery. Counting it is
#: what stops a rap-heavy cut from measuring under the floor by accident.
SPOKEN_STYLE_DELIVERIES = frozenset({"spoken", "rap"})

# ---- G10: the ONE constants set for targets and the band (Trevor, 2026-10-08)
# Trevor: "We always want to try to be within 5% of the goal. Once you get
# past 5%, 5% to 7% gets a flag. Once you get past 10%, it's got to be
# redone." and "It's not an absolute 55% or 20% ... within about 5 percentage
# points". Every share / first-sung / length / lip-sync-seconds goal in the
# skill is judged by judge_gap() below; no check keeps its own tolerance, and
# NO check keeps an absolute floor.
ACCEPT_PTS = 5      # within this many points of the goal: accept
FLAG_PTS = 10       # past ACCEPT_PTS up to this: accept WITH A FLAG
#: H6: first REAL singing lands at this share of runtime (60 s ad -> 9 s).
FIRST_SUNG_TARGET_PCT = 15
#: Default sung share of VOICE time for an ad whose choice card / plan names
#: no target of its own; music-only intro, gaps and the end card never count
#: against it. The ad's own target always wins (sung_vocal_guard).
SUNG_TARGET_PCT = 77.5   # sung share of VOICE time, sung / (sung + spoken); 75-80
#: The only hard reject when singing was chosen: no real singing, i.e. no
#: sung stretch this long (seconds). Same number as the singing detector's.
NO_REAL_SINGING_STRETCH_S = 6.0
#: Sung segments closer together than this are one stretch.
SUNG_STRETCH_JOIN_S = 0.25
# H6 spellings of the same numbers (one definition, two names).
TARGET_ACCEPT_PCT = ACCEPT_PTS
TARGET_FLAG_PCT = FLAG_PTS
REAL_SINGING_STRETCH_S = NO_REAL_SINGING_STRETCH_S

# ---- FU-U3: bands per music style -----------------------------------------
# One band (5/10) for every style, never changed. What U3 adds is WHICH
# number each style is judged against, per delivery:
#   * soul-ballad / soul-rise keep today's numbers EXACTLY: spoken share of
#     runtime 22.5, sung-of-voice 77.5. No rap delivery.
#   * rnb-flow: the DEFAULT IS A TREVOR-DECISION ITEM, flagged in the plan
#     (doc 18, section 9, item 1). No new number was invented here. The
#     documented default is: the target = the share PLANNED from the
#     approved sheet (the U2 plan's spoken_share_pct_planned), judged on the
#     5/10 band, so a take that matches its approved plan is not FAIL by
#     construction; plain spoken (NOT rap) keeps the 22.5% runtime target;
#     rap is its own DELIVERY, measured on its own planned seconds, never
#     folded into the spoken target; the 6 s sung stretch and the hook count
#     stay exactly as they are.
#: Per-style targets. ``spoken_pct`` = runtime spoken target;
#: ``sung_of_voice_pct`` = sung share of voice; ``rap_s`` = rap seconds each
#: style's own approved plan holds (0 = rap never appears in this style);
#: ``target_from_plan`` = use the plan's own planned share as the target.
STYLE_TARGETS = {
    "soul-ballad": {"spoken_pct": SPOKEN_TARGET_PCT, "sung_of_voice_pct": SUNG_TARGET_PCT,
                    "rap_delivery": False, "target_from_plan": False},
    "soul-rise": {"spoken_pct": SPOKEN_TARGET_PCT, "sung_of_voice_pct": SUNG_TARGET_PCT,
                  "rap_delivery": False, "target_from_plan": False},
    # R&B Flow: rap is its own delivery. The rap target is the share the
    # approved plan names (per delivery, 5/10 band); plain spoken keeps the
    # 22.5% runtime target; sung-of-voice is recorded, not a planned target
    # (a rap sheet's sung content is the hook and its ad-libs, which no word
    # count can plan -- a 77.5% gate on it would be FAIL by construction).
    "rnb-flow": {"spoken_pct": SPOKEN_TARGET_PCT, "sung_of_voice_pct": None,
                 "rap_delivery": True, "target_from_plan": True},
}
DEFAULT_STYLE_TARGET = STYLE_TARGETS["soul-ballad"]


def style_targets(style_id=None):
    """The targets for one style. Unknown/absent style -> Soul Ballad's
    (the default style), so a caller that forgets the style gets today's
    numbers, never a silent rap allowance."""
    if style_id is None:
        return dict(DEFAULT_STYLE_TARGET)
    return dict(STYLE_TARGETS.get(str(style_id).strip().lower(),
                                  DEFAULT_STYLE_TARGET))

VERDICT_PASS = "PASS"
VERDICT_FLAG = "FLAG"    # accepted, but the receipt must carry the flag
VERDICT_FAIL = "FAIL"    # past FLAG_PTS: REDO (never keep the closest)
BAND_ACCEPT, BAND_FLAG, BAND_REDO = "ACCEPT", "FLAG", "REDO"
_BAND_OF = {VERDICT_PASS: BAND_ACCEPT, VERDICT_FLAG: BAND_FLAG,
            VERDICT_FAIL: BAND_REDO}

def judge_gap(gap_points, target_pct=None):
    """Trevor's band. ``judge_gap(gap)`` judges a gap in percentage points
    (sign ignored) -> PASS | FLAG | FAIL. ``judge_gap(measured, target)``
    judges a measured percent against the ad's own target ->
    {"gap_pts", "band": ACCEPT | FLAG | REDO, "verdict"}."""
    if target_pct is not None:
        gap = round(abs(float(gap_points) - float(target_pct)), 6)
        v = judge_gap(gap)
        return {"gap_pts": gap, "band": _BAND_OF[v], "verdict": v}
    gap = round(abs(float(gap_points)), 6)
    if gap <= ACCEPT_PTS:
        return VERDICT_PASS
    if gap <= FLAG_PTS:
        return VERDICT_FLAG
    return VERDICT_FAIL


def judge_seconds(actual_s, goal_s, base_s, only=None):
    """Band for a goal in seconds; the gap is points of ``base_s`` (the
    runtime, or the goal itself for a length goal). ``only="short"`` counts
    just a shortfall (lip-sync seconds: more is fine), ``only="late"`` just
    an excess (first-sung: earlier is fine). Returns {verdict, gap_pts}.
    """
    diff = float(actual_s) - float(goal_s)
    if (only == "short" and diff > 0) or (only == "late" and diff < 0):
        diff = 0.0
    gap = abs(diff) / float(base_s) * 100.0
    return {"verdict": judge_gap(gap), "gap_pts": round(gap, 3)}


class SpokenShareError(ValueError):
    """Malformed input -- a caller bug, never a domain verdict."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def band():
    """The one band, in fractions and in percent. Identical for every
    length and every style -- that is the whole point of the retarget."""
    return {
        "target": TARGET,
        "floor": FLOOR,
        "cap": CAP,
        "target_pct": SPOKEN_TARGET_PCT,
        "floor_pct": SPOKEN_MIN_PCT,
        "cap_pct": SPOKEN_MAX_PCT,
        "applies_to": "every length and every music style",
        "rap_counts_as_spoken": True,
        "source": SOURCE,
    }


def is_spoken_style(delivery):
    """True when a delivery label counts toward the spoken share."""
    if not isinstance(delivery, str):
        return False
    return delivery.strip().lower() in SPOKEN_STYLE_DELIVERIES


#: Every segment the measuring functions accept as a measurement carries
#: this ``source`` value: it came from the singing detector on the vocal
#: stem (G2/G3), never from a lyric or section label.
MEASURED_SOURCE = "measured"
#: The two bases. "measured" = audio; "planned" = label timeline, planning
#: only -- a planned number is never a result (G8 / review G1).
BASIS_MEASURED = "measured"
BASIS_PLANNED = "planned"
#: FU-U3: "aligned" = measured word timestamps x the sheet's own delivery
#: labels (Suno aligned words joined to the line each word came from). It is
#: the ONLY basis a rap-versus-speech split may use, and it is NEVER recorded
#: as "measured": the split rests on the sheet's labels as well as the audio.
BASIS_ALIGNED = "aligned"
ALIGNED_SOURCE = BASIS_ALIGNED

def segment_basis(segments):
    """Basis of one segment list: "measured" only when EVERY segment is
    detector output carrying source="measured"; "aligned" when every segment
    carries source "measured" or "aligned" and at least one carries
    "aligned"; a list built from lyric/section labels is "planned"."""
    if not isinstance(segments, list) or not segments:
        return BASIS_PLANNED
    have_aligned = False
    for seg in segments:
        if not isinstance(seg, dict):
            return BASIS_PLANNED
        src = seg.get("source")
        if src == ALIGNED_SOURCE:
            have_aligned = True
        elif src != MEASURED_SOURCE:
            return BASIS_PLANNED
    return BASIS_ALIGNED if have_aligned else BASIS_MEASURED

def _require_basis(segments, basis, where):
    """G8 gate: refuse a label timeline where a measurement is required.

    basis="measured" (the default on every measuring function) demands
    detector segments; basis="aligned" (the rap-versus-speech split) accepts
    detector or aligned segments, never labels; basis="planned" is the
    planner's own timeline and is allowed, but its result names itself planned
    and is never a share of record.
    """
    if basis == BASIS_PLANNED:
        return
    have = segment_basis(segments)
    ok = (have == BASIS_MEASURED
          if basis == BASIS_MEASURED else have in (BASIS_MEASURED, BASIS_ALIGNED))
    if not ok:
        raise SpokenShareError(
            "LABELS_NOT_MEASURED",
            "%s: segments are built from lyric labels, not measured; feed "
            "the detector output (source=\"measured\", detector version and "
            "stem id), or align the words to the sheet labels (basis="
            "\"aligned\"), or pass basis=\"planned\" to plan with labels"
            % where)

def _provenance(segments, out):
    """Stamp the measurement's provenance onto a result dict."""
    out["basis"] = segment_basis(segments)
    out["share_source"] = out["basis"]
    first = segments[0] if isinstance(segments, list) and segments \
        and isinstance(segments[0], dict) else {}
    out["detector"] = first.get("detector")
    out["detector_version"] = first.get("detector_version")
    out["stem_id"] = first.get("stem_id")
    return out

def share_pct(share):
    """Human percent for a share fraction, rounded to one decimal."""
    return round(float(share) * 100.0, 1)


def _number(value, what, code="BAD_SEGMENT"):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpokenShareError(code, "%s must be a number, got %r"
                               % (what, value))
    value = float(value)
    if not isfinite(value):
        raise SpokenShareError(code, "%s must be finite, got %r" % (what, value))
    return value


def _segments(segments):
    """Normalize timing segments to [(delivery, start, end, seconds), ...].

    Accepts {"delivery": d, "seconds": n} or {"delivery": d, "start": a,
    "end": b}. Order in the list is the order in the song; a segment without
    an explicit start continues from the running cursor.
    """
    if not isinstance(segments, list) or not segments:
        raise SpokenShareError("BAD_SEGMENTS",
                               "segments must be a non-empty list")
    out = []
    cursor = 0.0
    for seg in segments:
        if not isinstance(seg, dict):
            raise SpokenShareError("BAD_SEGMENT",
                                   "segment must be a record, got %r"
                                   % (type(seg).__name__,))
        delivery = seg.get("delivery")
        if (not isinstance(delivery, str)
                or delivery.strip().lower() not in SEGMENT_DELIVERIES):
            raise SpokenShareError("BAD_DELIVERY",
                                   "delivery must be one of %s, got %r"
                                   % (list(SEGMENT_DELIVERIES), delivery))
        delivery = delivery.strip().lower()
        if "seconds" in seg:
            secs = _number(seg["seconds"], "seconds")
            if secs < 0:
                raise SpokenShareError("BAD_SEGMENT",
                                       "segment seconds must be >= 0")
            start = _number(seg["start"], "start") if "start" in seg else cursor
            if start < 0:
                raise SpokenShareError("BAD_SEGMENT",
                                       "segment start must be >= 0")
            end = start + secs
        elif "start" in seg and "end" in seg:
            start = _number(seg["start"], "start")
            end = _number(seg["end"], "end")
            if end < start:
                raise SpokenShareError("BAD_SEGMENT",
                                       "segment end must be >= start")
            secs = end - start
        else:
            raise SpokenShareError("BAD_SEGMENT",
                                   "segment needs seconds, or start and end")
        out.append((delivery, start, end, secs))
        cursor = max(cursor, end)
    return out


def measure_share(segments, basis=BASIS_MEASURED, style_id=None):
    """Spoken-style share of runtime from timing segments (G8: AUDIO, never
    labels).

    ``basis="measured"`` (default) accepts only detector segments carrying
    source="measured"; ``basis="aligned"`` accepts detector or word-aligned
    segments (the rap-versus-speech split, recorded as "aligned" and NEVER as
    "measured"); a list built from lyric/section labels is refused with
    LABELS_NOT_MEASURED ("labels, not measured"). ``basis="planned"`` is the
    planner's own timeline: it is measured and returned, but the result
    carries basis="planned" / share_source="planned" and is never a share of
    record.

    Rap is spoken-style, so it is counted -- that is the rule that catches a
    rap-heavy R&B cut. ``style_id`` marks which style's rules apply: a rap
    style (R&B Flow, the U2 plan) reports the rap share SEPARATELY
    (``rap_share_pct``), because rap is its own delivery there and its target
    comes from the plan, never from the spoken 22.5 target; every other style
    reports it inside the spoken-style share exactly as before.

    Segments with delivery "none" (music-only intro, gaps, the end card) count
    in RUNTIME and never in voice time -- a music-only gap is not spoken.

    Returns spoken/rap/sung/none seconds, the spoken-style share as a
    fraction of total, ``rap_share_pct``, and ``first_sung_start_s`` (None
    when the cut carries no sung line). Total 0 is refused rather than
    reported as 0%.
    """
    parsed = _segments(segments)
    _require_basis(segments, basis, "measure_share")
    t = style_targets(style_id)
    seconds = dict.fromkeys(SEGMENT_DELIVERIES, 0.0)
    for delivery, _start, _end, secs in parsed:
        seconds[delivery] += secs
    spoken, rap, sung, none = (seconds[d] for d in SEGMENT_DELIVERIES)
    total = spoken + rap + sung + none
    if total <= 0:
        raise SpokenShareError("ZERO_RUNTIME",
                               "segments total 0 seconds; share undefined")
    if t["rap_delivery"]:
        # rap is its own delivery: spoken share counts plain spoken only.
        spoken_style = spoken
        spoken_denominator = total - rap
        spoken_style_pct = (spoken / spoken_denominator * 100.0
                            if spoken_denominator > 0 else 0.0)
    else:
        spoken_style = spoken + rap
        spoken_denominator = total
        spoken_style_pct = spoken_style / total * 100.0
    sung_starts = [start for delivery, start, _e, _s in parsed
                   if delivery == "sung"]
    out = {
        "spoken_seconds": round(spoken, 6),
        "rap_seconds": round(rap, 6),
        "sung_seconds": round(sung, 6),
        "none_seconds": round(none, 6),
        "voice_seconds": round(spoken + rap + sung, 6),
        "total_seconds": round(total, 6),
        "spoken_style_seconds": round(spoken_style, 6),
        "spoken_denominator_seconds": round(spoken_denominator, 6),
        "share": round(spoken_style / total, 6),
        "share_pct": share_pct(spoken_style / total),
        "spoken_share_pct_of_voice": round(spoken_style_pct, 3),
        "rap_share_pct": round(rap / total * 100.0, 3) if total else 0.0,
        "style_id": t and style_id,
        "target_pct": t["spoken_pct"],
        "sung_share": round(sung / total, 6),
        "first_sung_start_s": min(sung_starts) if sung_starts else None,
        "opener_seconds": (round(min(sung_starts), 6)
                           if sung_starts else None),
        "rap_counts_as_spoken": not t["rap_delivery"],
    }
    return _provenance(segments, out)


def sung_of_voice_pct(sung_s, spoken_s):
    """Sung share of VOICE time as a percent: sung / (sung + spoken).

    Voice time is only the seconds somebody is singing or speaking. A
    music-only intro, gaps and the end card are not voice time, so they never
    count against singing. No voice at all is refused rather than called 0%.
    """
    sung_s = _number(sung_s, "sung_s")
    spoken_s = _number(spoken_s, "spoken_s")
    if sung_s < 0 or spoken_s < 0 or sung_s + spoken_s <= 0:
        raise SpokenShareError("ZERO_VOICE",
                               "sung + spoken must be positive; share undefined")
    return round(sung_s / (sung_s + spoken_s) * 100.0, 6)


def check_sung_of_voice(segments=None, target_pct=None, sung_s=None,
                        spoken_s=None, basis=BASIS_MEASURED, style_id=None):
    """Judge singing against voice time with Trevor's band.

    Give timing ``segments`` (rap counts as voice; "none" never does) or
    ``sung_s`` and ``spoken_s`` directly. ``target_pct`` defaults to the
    style's own sung-of-voice target (SUNG_TARGET_PCT, 77.5, for every style
    except a rap style whose sung content is the hook: there the percentage is
    RECORDED (``gated: False``) rather than gated, because no word count can
    plan a rap sheet's sung share and a 77.5 gate on it would be FAIL by
    construction).
    Returns {"verdict": PASS|FLAG|FAIL, "band", "sung_of_voice_pct",
    "target_pct", "gap_pts", "reasons", "flags", ...}. The only other hard
    reject (no 6 s sung stretch) is check_real_singing, run on segments.
    """
    t = style_targets(style_id)
    if segments is not None:
        m = measure_share(segments, basis, style_id=style_id)
        sung_s = m["sung_seconds"]
        spoken_s = round(m["voice_seconds"] - m["sung_seconds"], 6)
    if target_pct is None:
        target_pct = t["sung_of_voice_pct"]
    gated = target_pct is not None
    pct = sung_of_voice_pct(sung_s, spoken_s)
    out = {"gated": gated, "style_id": style_id,
           "sung_of_voice_pct": round(pct, 3),
           "sung_seconds": float(sung_s),
           "spoken_seconds": float(spoken_s),
           "target_pct": None if target_pct is None else float(target_pct),
           "reasons": [], "flags": []}
    if not gated:
        out.update({"verdict": VERDICT_PASS, "band": BAND_ACCEPT,
                    "gap_pts": None})
        out["note"] = (
            "sung-of-voice %g%% of voice time for %s is recorded, not gated "
            "(hook content, not a planned share)" % (pct, style_id))
        return out
    target = float(target_pct)
    j = judge_gap(pct, target)
    text = ("sung %.1f%% of voice time (sung %.1f s, spoken %.1f s), target "
            "%g%%, %.1f points off" % (pct, float(sung_s), float(spoken_s),
                                       target, j["gap_pts"]))
    out.update({"verdict": j["verdict"], "band": j["band"],
                "gap_pts": j["gap_pts"]})
    if j["verdict"] == VERDICT_FLAG:
        out["flags"].append("FLAG: " + text)
    elif j["verdict"] == VERDICT_FAIL:
        out["reasons"].append(text + "; over %d points, redo" % FLAG_PTS)
    return out


def spoken_word_pct(target_pct):
    """Spoken share of the lyric WORDS for a spoken runtime share (percent).

    Derived from the length formula's measured rates (SPOKEN_WPS spoken and
    SUNG_WPS sung words per second), so there is no second constant to drift:
    17.5 -> about 21.8 (the BSW passes), 22.5 -> about 27.5.
    """
    import os, sys  # lazy import below: length_formula imports this module
    core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core not in sys.path:
        sys.path.insert(0, core)
    import length_formula as LF
    f = float(target_pct) / 100.0
    sp = f * LF.SPOKEN_WPS
    return 100.0 * sp / (sp + (1.0 - f) * LF.SUNG_WPS)


def spoken_word_budget_pct(range_pct=None):
    """(min, max) spoken word share for an ad's own spoken range (default
    DEFAULT_AD_RANGE_PCT), each edge run through spoken_word_pct."""
    lo, hi = DEFAULT_AD_RANGE_PCT if range_pct is None else range_pct
    target_for_range((lo, hi))  # validates the range
    return (round(spoken_word_pct(lo), 3), round(spoken_word_pct(hi), 3))


def spoken_word_budget(total_words, range_pct=None):
    """Spoken words the lyric writer should plan for ``total_words`` lyric
    words: (min, max) from the ad's spoken range via spoken_word_budget_pct."""
    total_words = _number(total_words, "total_words", "BAD_WORDS")
    if total_words <= 0:
        raise SpokenShareError("BAD_WORDS", "total_words must be positive")
    lo, hi = spoken_word_budget_pct(range_pct)
    return (round(total_words * lo / 100.0, 1),
            round(total_words * hi / 100.0, 1))


def check_spoken_word_budget(sections, range_pct=None):
    """Judge a lyric sheet's spoken words against the ad's derived word budget.

    ``sections`` = [{"delivery": "sung"|"spoken"|"rap", "lines": [str]}].
    Inside the derived budget is on target; outside, the gap is points to the nearest
    edge and Trevor's band applies (5 accept, 5-10 flag, past 10 redo).
    Returns {"verdict", "spoken_word_pct", "budget_pct", "gap_pts",
    "reasons", "flags"}.
    """
    spoken = total = 0
    for sec in sections or []:
        n = sum(len(str(line).split()) for line in sec.get("lines") or [])
        total += n
        if is_spoken_style(sec.get("delivery")):
            spoken += n
    if total <= 0:
        raise SpokenShareError("BAD_WORDS", "sheet has no lyric words")
    pct = round(spoken / total * 100.0, 3)
    lo, hi = spoken_word_budget_pct(range_pct)
    gap = lo - pct if pct < lo else (pct - hi if pct > hi else 0.0)
    verdict = judge_gap(gap)
    text = ("spoken lines are %.1f%% of the lyric words, budget %g-%g%% "
            "(%.1f points outside)" % (pct, lo, hi, gap))
    return {"verdict": verdict, "spoken_word_pct": pct,
            "budget_pct": [lo, hi], "gap_pts": round(gap, 3),
            "reasons": [text + "; redo the sheet"] if verdict == VERDICT_FAIL else [],
            "flags": ["FLAG: " + text] if verdict == VERDICT_FLAG else []}


#: Per-ad spoken share setting (percent range): the default stays 20-25; an ad
#: (BSW Power in the Climb) can set its own, e.g. (15, 20).
DEFAULT_AD_RANGE_PCT = (20.0, 25.0)


def target_for_range(range_pct=None):
    """Midpoint percent of an ad's own spoken range (default 20-25 -> 22.5)."""
    lo, hi = DEFAULT_AD_RANGE_PCT if range_pct is None else range_pct
    if not 0 < lo <= hi < 100:
        raise SpokenShareError("BAD_RANGE", "spoken range must be 0 < lo <= hi < 100, got %r" % ((lo, hi),))
    return (float(lo) + float(hi)) / 2.0


def check_share(share, segments=None, basis=BASIS_MEASURED, target_pct=None,
                style_id=None):
    """Enforce the band on one measured share. Never raises on a share that
    is merely out of band -- that is a FAIL verdict, not an error.

    Returns {"verdict": PASS|FAIL, "share", "floor", "cap", "target",
             "reasons": [...]}. Raises SpokenShareError only for a malformed
    share, which is a caller bug.

    segments, when given, is measured first (under the same ``style_id``
    semantics: for a rap style the share is plain spoken, rap reported
    separately) and its share is the one judged; share then must agree with
    it or the check fails closed.
    """
    if isinstance(share, bool) or not isinstance(share, (int, float)):
        raise SpokenShareError("BAD_SHARE",
                               "share must be a fraction 0..1, got %r"
                               % (type(share).__name__,))
    share = float(share)
    if not isfinite(share):
        raise SpokenShareError("BAD_SHARE",
                               "share must be finite, got %r" % (share,))
    measured = None
    t = style_targets(style_id)
    result = {
        "share": share,
        "share_pct": share_pct(share),
        "floor": FLOOR,
        "cap": CAP,
        "target": TARGET,
        "floor_pct": SPOKEN_MIN_PCT,
        "cap_pct": SPOKEN_MAX_PCT,
        "target_pct": SPOKEN_TARGET_PCT,
        "rap_counts_as_spoken": not t["rap_delivery"],
        "measurement": None,
        "checker_version": TOOL_VERSION,
        "source": SOURCE,
    }
    if segments is not None:
        measured = measure_share(segments, basis, style_id=style_id)
        result["measurement"] = measured
        result["basis"] = measured["basis"]
        result["share_source"] = measured["basis"]
        if abs(measured["share"] - share) > 1e-6:
            result.update({
                "verdict": "FAIL",
                "measured_share": measured["share"],
                "reasons": ["share %s disagrees with the timing measurement "
                            "%s (rap included)" % (share, measured["share"])],
            })
            return result
    reasons = []
    if share < 0.0 or share > 1.0:
        reasons.append("share %r is not a fraction in 0..1" % share)
    tgt = SPOKEN_TARGET_PCT if target_pct is None else float(target_pct)
    result["target_pct"] = tgt
    gap = round(share * 100.0 - tgt, 6)
    verdict = VERDICT_FAIL if reasons else judge_gap(gap)
    if verdict == VERDICT_FAIL and not reasons:
        reasons.append("spoken share %.1f%% is %.1f points from the %g%% "
                       "goal, past %d: redo (rap counts as spoken-style "
                       "delivery)" % (share_pct(share), abs(gap),
                                      tgt, FLAG_PTS))
    flags = []
    if verdict == VERDICT_FLAG:
        flags.append("spoken share %.1f%% is %.1f points from the %g%% "
                     "goal (past %d, within %d): accepted with a flag"
                     % (share_pct(share), abs(gap), tgt,
                        ACCEPT_PTS, FLAG_PTS))
    result.update({
        "verdict": verdict,
        "in_band": abs(gap) <= ACCEPT_PTS,
        "gap_pts": abs(gap),
        "delta_from_target": round(share - tgt / 100.0, 6),
        "reasons": reasons,
        "flags": flags,
    })
    return result


def refusal(share, segments=None):
    """Compact refusal text for a FAILED share; empty string when it passes."""
    result = check_share(share, segments)
    if result["verdict"] != VERDICT_FAIL:
        return ""
    return "REFUSED spoken share %.1f%%: %s" % (
        result["share_pct"], "; ".join(result["reasons"]))


def _sung_stretches(parsed):
    """[[start, end, sung_seconds], ...]: sung stretches, joined across
    gaps of SUNG_STRETCH_JOIN_S or less (only sung time is counted)."""
    out = []
    for d, st, en, _s in sorted(parsed, key=lambda t: t[1]):
        if d != "sung":
            continue
        if out and st - out[-1][1] <= SUNG_STRETCH_JOIN_S:
            out[-1][2] += en - max(st, out[-1][1])
            out[-1][1] = max(out[-1][1], en)
        else:
            out.append([st, en, en - st])
    return out


def longest_sung_stretch_s(segments):
    """Longest unbroken sung stretch in the plan, in seconds."""
    return round(max((x[2] for x in _sung_stretches(_segments(segments))),
                     default=0.0), 6)


def segments_from_sung_stretches(stretches, total_s, detector_version=None,
                                 stem_id=None, voiced=None):
    """Turn the vocal-stem detector's sung stretches [(start, end), ...]
    into spoken/sung segments covering ``total_s``, so the measured stem
    feeds check_first_sung.

    FU-U3: ``voiced`` = the voiced ranges [(start, end), ...] measured on the
    vocal stem (RMS). Time outside them is music only: it becomes a fourth
    delivery "none", which counts in RUNTIME and never in voice time -- a
    music-only intro, gap or end card is NOT speech, so it can no longer
    inflate the spoken seconds or deflate the sung share of voice. With no
    ``voiced`` given, behavior is exactly as before (everything not sung is
    spoken-style), so existing callers keep their numbers.

    Every produced segment carries source="measured" (plus the detector
    version and stem id when given) -- this is the one builder whose output
    the measuring functions accept as a measurement (G8)."""
    out, cursor = [], 0.0
    stamp = {"source": MEASURED_SOURCE,
             "detector": "singing_detector"}
    if detector_version is not None:
        stamp["detector_version"] = detector_version
    if stem_id is not None:
        stamp["stem_id"] = stem_id
    voice = (sorted((float(a), float(b)) for a, b in voiced)
             if voiced else None)

    def fill(gap_start, gap_end, delivery):
        """One un-sung gap -> segments, split at the voiced/unvoiced edges."""
        if gap_end <= gap_start:
            return
        if voice is None:
            out.append(dict(stamp, delivery=delivery, start=gap_start,
                            end=gap_end))
            return
        pos = gap_start
        for a, b in voice:
            if b <= pos or a >= gap_end:
                continue
            if a > pos:
                out.append(dict(stamp, delivery="none", start=pos,
                                end=min(a, gap_end)))
            seg_start = max(pos, a)
            seg_end = min(b, gap_end)
            if seg_end > seg_start:
                out.append(dict(stamp, delivery=delivery, start=seg_start,
                                end=seg_end))
            pos = seg_end
            if pos >= gap_end:
                return
        if pos < gap_end:
            out.append(dict(stamp, delivery="none", start=pos, end=gap_end))

    for start, end in sorted((float(a), float(b)) for a, b in stretches):
        if start > cursor:
            fill(cursor, start, "spoken")
        out.append(dict(stamp, delivery="sung", start=start, end=end))
        cursor = max(cursor, end)
    if total_s > cursor:
        fill(cursor, float(total_s), "spoken")
    return out


def check_real_singing(segments):
    """THE singing rule, used by every check: singing was chosen, so the
    take must hold one sung stretch of NO_REAL_SINGING_STRETCH_S. Nothing
    else about singing is a hard reject; shares and timing use the band."""
    stretch = longest_sung_stretch_s(segments)
    ok = stretch + 1e-9 >= NO_REAL_SINGING_STRETCH_S
    return {
        "verdict": VERDICT_PASS if ok else VERDICT_FAIL,
        "real_singing": ok,
        "longest_sung_stretch_s": stretch,
        "required_stretch_s": NO_REAL_SINGING_STRETCH_S,
        "reasons": [] if ok else [
            "no real singing: longest sung stretch %.1f s, needs %.0f s; "
            "regenerate" % (stretch, NO_REAL_SINGING_STRETCH_S)],
    }


def check_first_sung(segments, basis="planned"):
    """H6 rule: the first REAL singing (first sung stretch >=
    NO_REAL_SINGING_STRETCH_S) is a TARGET of FIRST_SUNG_TARGET_PCT of
    runtime, judged by the band: within 5 points accept (10-20% of runtime),
    5-10 points accept with a flag, over 10 points redo. A cut with no real
    singing is redone (H8: the one hard reject).

    ``basis`` is "measured" when ``segments`` come from the vocal-stem
    detector (see segments_from_sung_stretches), "planned" when they come
    from labels; the result names it.

    Returns {"verdict": PASS|FLAG|FAIL, "band": ACCEPT|FLAG|REDO,
             "first_sung_start_s", "first_sung_pct", "opener_seconds",
             "target_pct", "accept_pct", "gap_pts", "basis",
             "reasons": [...], "flags": [...]}.
    """
    parsed = _segments(segments)
    _require_basis(segments, basis, "check_first_sung")
    total = sum(p[3] for p in parsed)
    if total <= 0:
        raise SpokenShareError("ZERO_RUNTIME",
                               "segments total 0 seconds; share undefined")
    out = {
        "verdict": VERDICT_FAIL, "band": BAND_REDO,
        "first_sung_start_s": None, "first_sung_pct": None,
        "opener_seconds": None, "target_pct": FIRST_SUNG_TARGET_PCT,
        "accept_pct": [FIRST_SUNG_TARGET_PCT - ACCEPT_PTS,
                       FIRST_SUNG_TARGET_PCT + ACCEPT_PTS],
        "gap_pts": None, "basis": basis, "reasons": [], "flags": [],
    }
    real = [st for st, _en, sung in _sung_stretches(parsed)
            if sung + 1e-9 >= NO_REAL_SINGING_STRETCH_S]
    if not real:
        out["reasons"].append(
            "no real singing: longest sung stretch %.1f s, needs %.0f s "
            "(%s); regenerate" % (longest_sung_stretch_s(segments),
                                  NO_REAL_SINGING_STRETCH_S, basis))
        return out
    first = min(real)
    pct = round(first / total * 100.0, 3)
    j = judge_gap(pct, FIRST_SUNG_TARGET_PCT)
    text = ("first real singing at %.1f s = %.1f%% of runtime (%s), target "
            "%d%%, %.1f points off" % (first, pct, basis,
                                       FIRST_SUNG_TARGET_PCT, j["gap_pts"]))
    out.update({
        "verdict": j["verdict"], "band": j["band"],
        "first_sung_start_s": round(first, 6), "first_sung_pct": pct,
        "opener_seconds": round(first, 6), "gap_pts": j["gap_pts"],
    })
    if j["verdict"] == VERDICT_FLAG:
        out["flags"].append(text + ": accepted with a flag")
    elif j["verdict"] == VERDICT_FAIL:
        out["reasons"].append(text + ": redo")
    return out


def steer_first_sung(segments, basis="planned"):
    """What the lyric-sheet builder does with a first-sung result: the check
    plus which way to move the sung hook and by how many seconds to land on
    the target. action: keep | shorten_opener | lengthen_opener |
    add_sung_hook (no real singing at all)."""
    res = check_first_sung(segments, basis)
    total = sum(p[3] for p in _segments(segments))
    target_s = round(total * FIRST_SUNG_TARGET_PCT / 100.0, 3)
    first = res["first_sung_start_s"]
    if first is None:
        action, move = "add_sung_hook", None
    elif res["verdict"] == VERDICT_PASS:
        action, move = "keep", 0.0
    else:
        move = round(target_s - first, 3)
        action = "lengthen_opener" if move > 0 else "shorten_opener"
    return {"check": res, "target_s": target_s, "action": action,
            "move_by_s": move}


def seconds_for(length_s):
    """The band expressed in seconds for one runtime -- the length engine's
    read of D15. No per-length table: the same fractions for 60 s and 600 s.
    """
    if isinstance(length_s, bool) or not isinstance(length_s, (int, float)):
        raise SpokenShareError("BAD_LENGTH",
                               "length_s must be a number of seconds, got %r"
                               % (length_s,))
    length_s = float(length_s)
    if not isfinite(length_s) or length_s <= 0:
        raise SpokenShareError("BAD_LENGTH",
                               "length_s must be a positive finite number, "
                               "got %r" % (length_s,))
    return {
        "length_s": length_s,
        "target_s": round(length_s * TARGET, 3),
        "floor_s": round(length_s * FLOOR, 3),
        "cap_s": round(length_s * CAP, 3),
        "first_sung_target_s": round(length_s * FIRST_SUNG_TARGET_PCT / 100.0, 3),
        "first_sung_accept_s": [
            round(length_s * (FIRST_SUNG_TARGET_PCT - ACCEPT_PTS) / 100.0, 3),
            round(length_s * (FIRST_SUNG_TARGET_PCT + ACCEPT_PTS) / 100.0, 3)],
        "band": band(),
    }


def check_plan(length_s, segments, basis="planned"):
    """QC verdict for one cut: the band, the first-sung rule, the length
    goal, and the one singing rule. All judged by Trevor's band; FAIL means
    redo, FLAG means accepted with the flags in the receipt.
    """
    measured = measure_share(segments, basis)
    share_check = check_share(measured["share"], segments, basis)
    first_sung = check_first_sung(segments, basis)
    real = check_real_singing(segments)
    length_check = judge_seconds(measured["total_seconds"], length_s, length_s)
    voice = (check_sung_of_voice(segments, basis=basis)
             if measured["sung_seconds"] + measured["spoken_style_seconds"] > 0
             else None)
    parts = [share_check, first_sung, length_check]
    reasons = list(share_check["reasons"]) + list(first_sung["reasons"])
    flags = list(share_check["flags"]) + list(first_sung["flags"])
    if voice is not None:
        parts.append(voice)
        reasons += voice["reasons"]
        flags += voice["flags"]
    if length_check["verdict"] == VERDICT_FAIL:
        reasons.append("cut runs %.1f s against a %.1f s goal (%.1f points "
                       "off): redo" % (measured["total_seconds"],
                                       float(length_s),
                                       length_check["gap_pts"]))
    elif length_check["verdict"] == VERDICT_FLAG:
        flags.append("cut runs %.1f s against a %.1f s goal (%.1f points "
                     "off): accepted with a flag"
                     % (measured["total_seconds"], float(length_s),
                        length_check["gap_pts"]))
    verdict = (VERDICT_FAIL if any(p["verdict"] == VERDICT_FAIL for p in parts)
               else VERDICT_FLAG if flags else VERDICT_PASS)
    return {
        "verdict": verdict,
        "share": measured["share"],
        "share_pct": measured["share_pct"],
        "floor": FLOOR,
        "cap": CAP,
        "target": TARGET,
        "length_s": length_s,
        "measurement": measured,
        "share_check": share_check,
        "sung_of_voice": voice,
        "first_sung": first_sung,
        "length_check": length_check,
        "real_singing": real,
        "rap_counts_as_spoken": True,
        "reasons": reasons,
        "flags": flags,
        "checker_version": TOOL_VERSION,
        "source": SOURCE,
    }


def plan_refusal(length_s, segments, basis="planned"):
    """Compact refusal text for a FAILED plan; empty string when it passes."""
    result = check_plan(length_s, segments, basis)
    if result["verdict"] != VERDICT_FAIL:
        return ""
    return "REFUSED %ss plan: %s" % (length_s, "; ".join(result["reasons"]))


__all__ = [
    "ACCEPT_PTS",
    "BAND_ACCEPT",
    "BAND_FLAG",
    "BAND_REDO",
    "FIRST_SUNG_TARGET_PCT",
    "REAL_SINGING_STRETCH_S",
    "SUNG_TARGET_PCT",
    "TARGET_ACCEPT_PCT",
    "TARGET_FLAG_PCT",
    "segments_from_sung_stretches",
    "steer_first_sung",
    "CAP",
    "FLAG_PTS",
    "NO_REAL_SINGING_STRETCH_S",
    "VERDICT_FAIL",
    "VERDICT_FLAG",
    "VERDICT_PASS",
    "check_real_singing",
    "check_sung_of_voice",
    "check_spoken_word_budget",
    "spoken_word_budget",
    "sung_of_voice_pct",
    "spoken_word_pct",
    "spoken_word_budget_pct",
    "judge_gap",
    "judge_seconds",
    "longest_sung_stretch_s",
    "DELIVERIES",
    "FLOOR",
    "SCHEMA_VERSION",
    "SOURCE",
    "SPOKEN_MAX_PCT",
    "SPOKEN_MIN_PCT",
    "SPOKEN_STYLE_DELIVERIES",
    "SPOKEN_TARGET_PCT",
    "TARGET",
    "TOOL_NAME",
    "TOOL_VERSION",
    "SpokenShareError",
    "band",
    "check_first_sung",
    "check_plan",
    "check_share",
    "is_spoken_style",
    "measure_share",
    "STYLE_TARGETS",
    "style_targets",
    "BASIS_ALIGNED",
    "ALIGNED_SOURCE",
    "VOICE_DELIVERIES",
    "SEGMENT_DELIVERIES",
    "BASIS_MEASURED",
    "BASIS_PLANNED",
    "MEASURED_SOURCE",
    "segment_basis",
    "plan_refusal",
    "refusal",
    "seconds_for",
    "target_for_range",
    "DEFAULT_AD_RANGE_PCT",
    "share_pct",
]
