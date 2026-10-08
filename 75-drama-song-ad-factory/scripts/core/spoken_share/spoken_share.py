#!/usr/bin/env python3
"""Spoken-share targets (SPK001): one band, every length, every style.

Source: Decision log 37 (D15 retarget) 2026-10-07; plan 6.7; SPK001 retarget
(Trevor, 2026-10-08): "Okay, let's go to your recommendation that cut it to
about 20-25%."

Why: Suno turns spoken lyric lines into long talking, and the old targets did
not add up (spoken 35-40% of runtime plus a music-only intro and end card left
at most about 50% for singing, never the 55-60% goal). Now:

  * spoken share of RUNTIME: 20-25%, target 22.5 (SPOKEN_TARGET_PCT);
  * the lyric writer budgets spoken lines at about 15-18% of the lyric WORDS
    (LYRIC_SPOKEN_WORD_PCT), because Suno stretches spoken parts;
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

#: Delivery labels a timing segment may carry.
DELIVERIES = ("spoken", "rap", "sung")

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
#: The lyric writer budgets spoken lines at this share of the lyric WORDS
#: (min, max), because Suno stretches spoken parts so the same words take far
#: more runtime than sung ones. Lands the runtime share near SPOKEN_TARGET_PCT.
LYRIC_SPOKEN_WORD_PCT = (15.0, 18.0)
#: The only hard reject when singing was chosen: no real singing, i.e. no
#: sung stretch this long (seconds). Same number as the singing detector's.
NO_REAL_SINGING_STRETCH_S = 6.0
#: Sung segments closer together than this are one stretch.
SUNG_STRETCH_JOIN_S = 0.25
# H6 spellings of the same numbers (one definition, two names).
TARGET_ACCEPT_PCT = ACCEPT_PTS
TARGET_FLAG_PCT = FLAG_PTS
REAL_SINGING_STRETCH_S = NO_REAL_SINGING_STRETCH_S
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

def segment_basis(segments):
    """Basis of one segment list: "measured" only when EVERY segment is
    detector output carrying source="measured" (plus its detector version
    and stem id); a list built from lyric/section labels is "planned"."""
    if not isinstance(segments, list) or not segments:
        return BASIS_PLANNED
    for seg in segments:
        if not isinstance(seg, dict) or seg.get("source") != MEASURED_SOURCE:
            return BASIS_PLANNED
    return BASIS_MEASURED

def _require_basis(segments, basis, where):
    """G8 gate: refuse a label timeline where a measurement is required.

    basis="measured" (the default on every measuring function) demands
    detector segments; basis="planned" is the planner's own timeline and is
    allowed, but its result names itself planned and is never a share of
    record.
    """
    if basis != BASIS_MEASURED:
        return
    if segment_basis(segments) != BASIS_MEASURED:
        raise SpokenShareError(
            "LABELS_NOT_MEASURED",
            "%s: segments are built from lyric labels, not measured; feed "
            "the detector output (source=\"measured\", detector version and "
            "stem id), or pass basis=\"planned\" to plan with labels" % where)

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
                or delivery.strip().lower() not in DELIVERIES):
            raise SpokenShareError("BAD_DELIVERY",
                                   "delivery must be one of %s, got %r"
                                   % (list(DELIVERIES), delivery))
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


def measure_share(segments, basis=BASIS_MEASURED):
    """Spoken-style share of runtime from timing segments (G8: AUDIO, never
    labels).

    ``basis="measured"`` (default) accepts only detector segments carrying
    source="measured"; a list built from lyric/section labels is refused
    with LABELS_NOT_MEASURED ("labels, not measured"). ``basis="planned"``
    is the planner's own timeline: it is measured and returned, but the
    result carries basis="planned" / share_source="planned" and is never a
    share of record.

    Rap is spoken-style, so it is counted -- that is the rule that catches a
    rap-heavy R&B cut. Returns spoken/rap/sung/total seconds, the
    spoken-style share as a fraction of total, and ``first_sung_start_s``
    (None when the cut carries no sung line). Total 0 is refused rather than
    reported as 0%.
    """
    parsed = _segments(segments)
    _require_basis(segments, basis, "measure_share")
    seconds = dict.fromkeys(DELIVERIES, 0.0)
    for delivery, _start, _end, secs in parsed:
        seconds[delivery] += secs
    spoken, rap, sung = (seconds[d] for d in ("spoken", "rap", "sung"))
    total = spoken + rap + sung
    if total <= 0:
        raise SpokenShareError("ZERO_RUNTIME",
                               "segments total 0 seconds; share undefined")
    spoken_style = sum(v for d, v in seconds.items()
                       if d in SPOKEN_STYLE_DELIVERIES)
    sung_starts = [start for delivery, start, _e, _s in parsed
                   if delivery == "sung"]
    out = {
        "spoken_seconds": round(spoken, 6),
        "rap_seconds": round(rap, 6),
        "sung_seconds": round(sung, 6),
        "total_seconds": round(total, 6),
        "spoken_style_seconds": round(spoken_style, 6),
        "share": round(spoken_style / total, 6),
        "share_pct": share_pct(spoken_style / total),
        "sung_share": round(sung / total, 6),
        "first_sung_start_s": min(sung_starts) if sung_starts else None,
        "opener_seconds": (round(min(sung_starts), 6)
                           if sung_starts else None),
        "rap_counts_as_spoken": True,
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
                        spoken_s=None, basis=BASIS_MEASURED):
    """Judge singing against voice time with Trevor's band.

    Give timing ``segments`` (rap counts as spoken) or ``sung_s`` and
    ``spoken_s`` directly. ``target_pct`` defaults to SUNG_TARGET_PCT (77.5).
    Returns {"verdict": PASS|FLAG|FAIL, "band", "sung_of_voice_pct",
    "target_pct", "gap_pts", "reasons", "flags", ...}. The only other hard
    reject (no 6 s sung stretch) is check_real_singing, run on segments.
    """
    if segments is not None:
        m = measure_share(segments, basis)
        sung_s = m["sung_seconds"]
        spoken_s = m["spoken_style_seconds"]
    target = SUNG_TARGET_PCT if target_pct is None else float(target_pct)
    pct = sung_of_voice_pct(sung_s, spoken_s)
    j = judge_gap(pct, target)
    text = ("sung %.1f%% of voice time (sung %.1f s, spoken %.1f s), target "
            "%g%%, %.1f points off" % (pct, float(sung_s), float(spoken_s),
                                       target, j["gap_pts"]))
    out = {"verdict": j["verdict"], "band": j["band"],
           "sung_of_voice_pct": round(pct, 3), "target_pct": target,
           "gap_pts": j["gap_pts"], "sung_seconds": float(sung_s),
           "spoken_seconds": float(spoken_s), "reasons": [], "flags": []}
    if j["verdict"] == VERDICT_FLAG:
        out["flags"].append("FLAG: " + text)
    elif j["verdict"] == VERDICT_FAIL:
        out["reasons"].append(text + "; over %d points, redo" % FLAG_PTS)
    return out


def spoken_word_budget(total_words):
    """Spoken words the lyric writer should plan for ``total_words`` lyric
    words: (min, max) at LYRIC_SPOKEN_WORD_PCT (15-18%). Suno stretches
    spoken parts, so this small word share lands near the 22.5% runtime
    target."""
    total_words = _number(total_words, "total_words", "BAD_WORDS")
    if total_words <= 0:
        raise SpokenShareError("BAD_WORDS", "total_words must be positive")
    lo, hi = LYRIC_SPOKEN_WORD_PCT
    return (round(total_words * lo / 100.0, 1),
            round(total_words * hi / 100.0, 1))


def check_spoken_word_budget(sections):
    """Judge a lyric sheet's spoken words against the 15-18% budget.

    ``sections`` = [{"delivery": "sung"|"spoken"|"rap", "lines": [str]}].
    Inside 15-18% is on target; outside, the gap is points to the nearest
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
    lo, hi = LYRIC_SPOKEN_WORD_PCT
    gap = lo - pct if pct < lo else (pct - hi if pct > hi else 0.0)
    verdict = judge_gap(gap)
    text = ("spoken lines are %.1f%% of the lyric words, budget %g-%g%% "
            "(%.1f points outside)" % (pct, lo, hi, gap))
    return {"verdict": verdict, "spoken_word_pct": pct,
            "budget_pct": [lo, hi], "gap_pts": round(gap, 3),
            "reasons": [text + "; redo the sheet"] if verdict == VERDICT_FAIL else [],
            "flags": ["FLAG: " + text] if verdict == VERDICT_FLAG else []}


def check_share(share, segments=None, basis=BASIS_MEASURED):
    """Enforce the band on one measured share. Never raises on a share that
    is merely out of band -- that is a FAIL verdict, not an error.

    Returns {"verdict": PASS|FAIL, "share", "floor", "cap", "target",
             "reasons": [...]}. Raises SpokenShareError only for a malformed
    share, which is a caller bug.

    segments, when given, is measured first and its share is the one judged
    (rap included); share then must agree with it or the check fails closed.
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
    result = {
        "share": share,
        "share_pct": share_pct(share),
        "floor": FLOOR,
        "cap": CAP,
        "target": TARGET,
        "floor_pct": SPOKEN_MIN_PCT,
        "cap_pct": SPOKEN_MAX_PCT,
        "target_pct": SPOKEN_TARGET_PCT,
        "rap_counts_as_spoken": True,
        "measurement": None,
        "checker_version": TOOL_VERSION,
        "source": SOURCE,
    }
    if segments is not None:
        measured = measure_share(segments, basis)
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
    gap = round((share - TARGET) * 100.0, 6)
    verdict = VERDICT_FAIL if reasons else judge_gap(gap)
    if verdict == VERDICT_FAIL and not reasons:
        reasons.append("spoken share %.1f%% is %.1f points from the %g%% "
                       "goal, past %d: redo (rap counts as spoken-style "
                       "delivery)" % (share_pct(share), abs(gap),
                                      SPOKEN_TARGET_PCT, FLAG_PTS))
    flags = []
    if verdict == VERDICT_FLAG:
        flags.append("spoken share %.1f%% is %.1f points from the %g%% "
                     "goal (past %d, within %d): accepted with a flag"
                     % (share_pct(share), abs(gap), SPOKEN_TARGET_PCT,
                        ACCEPT_PTS, FLAG_PTS))
    result.update({
        "verdict": verdict,
        "in_band": abs(gap) <= ACCEPT_PTS,
        "gap_pts": abs(gap),
        "delta_from_target": round(share - TARGET, 6),
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
                                 stem_id=None):
    """Turn the vocal-stem detector's sung stretches [(start, end), ...]
    into spoken/sung segments covering ``total_s``, so the measured stem
    feeds check_first_sung. Whatever the detector did not call sung is
    spoken-style here.

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
    for start, end in sorted((float(a), float(b)) for a, b in stretches):
        if start > cursor:
            out.append(dict(stamp, delivery="spoken", start=cursor, end=start))
        out.append(dict(stamp, delivery="sung", start=start, end=end))
        cursor = max(cursor, end)
    if total_s > cursor:
        out.append(dict(stamp, delivery="spoken", start=cursor,
                        end=float(total_s)))
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
    "LYRIC_SPOKEN_WORD_PCT",
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
    "BASIS_MEASURED",
    "BASIS_PLANNED",
    "MEASURED_SOURCE",
    "segment_basis",
    "plan_refusal",
    "refusal",
    "seconds_for",
    "share_pct",
]
