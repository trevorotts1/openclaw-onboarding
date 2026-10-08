#!/usr/bin/env python3
"""D15 spoken-share retarget: one band, every length, every style.

Source: Decision log 37 (D15 retarget) 2026-10-07; plan 6.7.

Owner order, verbatim: "It should be 45% and never more than 55%." The 40%
floor stays. Same for every length and every music style -- rap counts as
spoken-style delivery, so a rap-heavy cut cannot measure under the band by
accident. The earlier per-length targets and the earlier wider ceiling are
retired: this module holds ONE band and nothing keyed by length.

The spoken opener (D12) stays short, so the first sung line starts within
about 10 seconds. ``check_first_sung`` is the planner-side rule;
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
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.spoken-share/v1"
SOURCE = "Decision log 37 (D15 retarget) 2026-10-07; plan 6.7"

# ---- the three numbers (owner D15 retarget) -------------------------------
SPOKEN_TARGET_PCT = 45   # the target: spoken share of runtime, as a percent
SPOKEN_MIN_PCT = 40      # hard floor: never less than this
SPOKEN_MAX_PCT = 55      # hard ceiling: never more than this

TARGET = SPOKEN_TARGET_PCT / 100.0
FLOOR = SPOKEN_MIN_PCT / 100.0
CAP = SPOKEN_MAX_PCT / 100.0

#: Music arrives sooner: the spoken opener is short and the first sung line
#: starts within about this many seconds (owner D12 + D15 retarget).
FIRST_SUNG_WITHIN_SECONDS = 10

#: Delivery labels a timing segment may carry.
DELIVERIES = ("spoken", "rap", "sung")

#: Rap is talking over a beat, so it is spoken-style delivery. Counting it is
#: what stops a rap-heavy cut from measuring under the floor by accident.
SPOKEN_STYLE_DELIVERIES = frozenset({"spoken", "rap"})

# ---- H8: ONE singing rule + ONE tolerance band (Trevor, 2026-10-08) --------
# Trevor: "We always want to try to be within 5% of the goal. Once you get
# past 5%, 5% to 7% gets a flag. Once you get past 10%, it's got to be
# redone." Every share / first-sung / length / lip-sync-seconds goal in the
# skill is judged by judge_gap() below; no check keeps its own tolerance.
ACCEPT_PTS = 5      # within this many points of the goal: accept
FLAG_PTS = 10       # past ACCEPT_PTS up to this: accept WITH A FLAG
VERDICT_PASS = "PASS"
VERDICT_FLAG = "FLAG"    # accepted, but the receipt must carry the flag
VERDICT_FAIL = "FAIL"    # past FLAG_PTS: REDO (never keep the closest)

#: The only hard reject when singing was chosen: no real singing, i.e. no
#: sung stretch this long (seconds). Same number as the singing detector's.
NO_REAL_SINGING_STRETCH_S = 6.0
#: Sung segments closer together than this are one stretch.
SUNG_STRETCH_JOIN_S = 0.25


def judge_gap(gap_points):
    """Trevor's band on a gap in percentage points (sign ignored)."""
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


def measure_share(segments):
    """Spoken-style share of runtime from timing segments.

    Rap is spoken-style, so it is counted -- that is the rule that catches a
    rap-heavy R&B cut. Returns spoken/rap/sung/total seconds, the
    spoken-style share as a fraction of total, and ``first_sung_start_s``
    (None when the cut carries no sung line). Total 0 is refused rather than
    reported as 0%.
    """
    parsed = _segments(segments)
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
    return {
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


def check_share(share, segments=None):
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
        measured = measure_share(segments)
        result["measurement"] = measured
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
        reasons.append("spoken share %.1f%% is %.1f points from the %.0f%% "
                       "goal, past %d: redo (rap counts as spoken-style "
                       "delivery)" % (share_pct(share), abs(gap),
                                      SPOKEN_TARGET_PCT, FLAG_PTS))
    flags = []
    if verdict == VERDICT_FLAG:
        flags.append("spoken share %.1f%% is %.1f points from the %.0f%% "
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


def longest_sung_stretch_s(segments):
    """Longest unbroken sung stretch in the plan, in seconds."""
    sung = sorted((st, en) for d, st, en, _s in _segments(segments)
                  if d == "sung")
    best = cur = 0.0
    prev_end = None
    for st, en in sung:
        if prev_end is not None and st - prev_end <= SUNG_STRETCH_JOIN_S:
            cur += en - max(st, prev_end)
        else:
            cur = en - st
        prev_end = max(en, prev_end if prev_end is not None else en)
        best = max(best, cur)
    return round(best, 6)


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


def check_first_sung(segments):
    """Planner rule: the first sung line starts within about 10 seconds,
    judged by the band (points of runtime past the limit). A cut with no
    real singing fails -- an ad with no singing is rebuilt.

    Returns {"verdict": PASS|FLAG|FAIL, "first_sung_start_s",
             "opener_seconds", "limit_s", "reasons": [...], "flags": [...]}.
    """
    parsed = _segments(segments)
    sung_starts = [start for delivery, start, _e, _s in parsed
                   if delivery == "sung"]
    real = check_real_singing(segments)
    if not sung_starts or not real["real_singing"]:
        return {
            "verdict": VERDICT_FAIL,
            "first_sung_start_s": (round(min(sung_starts), 6)
                                   if sung_starts else None),
            "opener_seconds": (round(min(sung_starts), 6)
                               if sung_starts else None),
            "limit_s": FIRST_SUNG_WITHIN_SECONDS,
            "reasons": real["reasons"],
            "flags": [],
        }
    first = min(sung_starts)
    total = sum(p[3] for p in parsed)
    j = judge_seconds(first, FIRST_SUNG_WITHIN_SECONDS, total, only="late")
    msg = ("first sung line starts at %.1f s, %.1f points of runtime past "
           "the %.0f s goal" % (first, j["gap_pts"], FIRST_SUNG_WITHIN_SECONDS))
    return {
        "verdict": j["verdict"],
        "first_sung_start_s": round(first, 6),
        "opener_seconds": round(first, 6),
        "limit_s": FIRST_SUNG_WITHIN_SECONDS,
        "gap_pts": j["gap_pts"],
        "reasons": [msg + ": redo"] if j["verdict"] == VERDICT_FAIL else [],
        "flags": ([msg + ": accepted with a flag"]
                  if j["verdict"] == VERDICT_FLAG else []),
    }


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
        "first_sung_within_s": FIRST_SUNG_WITHIN_SECONDS,
        "band": band(),
    }


def check_plan(length_s, segments):
    """QC verdict for one cut: the band, the first-sung rule, the length
    goal, and the one singing rule. All judged by Trevor's band; FAIL means
    redo, FLAG means accepted with the flags in the receipt.
    """
    measured = measure_share(segments)
    share_check = check_share(measured["share"], segments)
    first_sung = check_first_sung(segments)
    real = check_real_singing(segments)
    length_check = judge_seconds(measured["total_seconds"], length_s, length_s)
    parts = (share_check, first_sung, length_check)
    reasons = list(share_check["reasons"]) + list(first_sung["reasons"])
    flags = list(share_check["flags"]) + list(first_sung["flags"])
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
        "first_sung": first_sung,
        "length_check": length_check,
        "real_singing": real,
        "rap_counts_as_spoken": True,
        "reasons": reasons,
        "flags": flags,
        "checker_version": TOOL_VERSION,
        "source": SOURCE,
    }


def plan_refusal(length_s, segments):
    """Compact refusal text for a FAILED plan; empty string when it passes."""
    result = check_plan(length_s, segments)
    if result["verdict"] != VERDICT_FAIL:
        return ""
    return "REFUSED %ss plan: %s" % (length_s, "; ".join(result["reasons"]))


__all__ = [
    "ACCEPT_PTS",
    "CAP",
    "FLAG_PTS",
    "NO_REAL_SINGING_STRETCH_S",
    "VERDICT_FAIL",
    "VERDICT_FLAG",
    "VERDICT_PASS",
    "check_real_singing",
    "judge_gap",
    "judge_seconds",
    "longest_sung_stretch_s",
    "DELIVERIES",
    "FIRST_SUNG_WITHIN_SECONDS",
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
    "plan_refusal",
    "refusal",
    "seconds_for",
    "share_pct",
]
