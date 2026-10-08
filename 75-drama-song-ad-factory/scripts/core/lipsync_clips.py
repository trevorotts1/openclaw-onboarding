#!/usr/bin/env python3
"""lipsync_clips.py: the one place that says HOW MUCH lip-sync an ad carries.

Owner order (Trevor, 2026-10-08): double the lip-sync, with MORE PIECES, NOT
LONGER ONES. A 60 s ad carries 6-8 short lip-sync clips of 4-6 s each (30-40 s
in total, was 15-20 s). Every clip is capped at 6 s (short clips hold mouth
sync on sung lines). Clips go on the lines that matter: every sung hook, the
spoken opener and the spoken closing line.

Everything scales linearly with the ad length L (scale = L / 60). The
operator's length-formula module is not on main yet; when it lands, replace
`scale()` with its function and nothing else changes.

Every lip-sync clip is a paid KIE job (`kling/ai-avatar-standard`), so doubling
the footage roughly doubles the lip-sync cost. `check_budget` refuses LOUDLY
when the job would pass the cap (or when the price or the cap is unknown); it
never trims the plan or spends past a cap silently. Prices are never stored
here: the per-second rate comes from Skill 74 `price`.

Stdlib only, no network, no spend.
"""
from __future__ import annotations

REF_LENGTH_S = 60.0
CLIPS_PER_REF = (6, 8)          # clips in a 60 s ad
CLIP_MIN_S = 4.0
CLIP_MAX_S = 6.0                # hard cap per clip
TOTAL_PER_REF_S = (30.0, 40.0)  # lip-sync seconds in a 60 s ad
MIN_CLIPS_FLOOR = 3             # never fewer than 3, whatever the length
PRIORITY_ROLES = ("hook", "opener", "closing")   # sung hooks, spoken open/close

OVER_CAP = "LIPSYNC_OVER_CAP"
PRICE_UNKNOWN = "LIPSYNC_PRICE_UNKNOWN"
CAP_UNKNOWN = "LIPSYNC_CAP_UNKNOWN"
BAD_PLAN = "LIPSYNC_PLAN_OUT_OF_RULE"


class LipsyncClipsError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def scale(ad_length_s):
    if not _num(ad_length_s) or ad_length_s <= 0:
        raise LipsyncClipsError("BAD_INPUT", "ad_length_s must be positive")
    return ad_length_s / REF_LENGTH_S


def _round(x):
    return int(x + 0.5)


def budget(ad_length_s):
    """The rule for one ad length: clip count range, per-clip seconds, total."""
    k = scale(ad_length_s)
    lo = max(MIN_CLIPS_FLOOR, _round(CLIPS_PER_REF[0] * k))
    hi = max(lo, _round(CLIPS_PER_REF[1] * k))
    return {"ad_length_s": ad_length_s, "min_clips": lo, "max_clips": hi,
            "clip_min_s": CLIP_MIN_S, "clip_max_s": CLIP_MAX_S,
            "total_min_s": TOTAL_PER_REF_S[0] * k,
            "total_max_s": TOTAL_PER_REF_S[1] * k}


def check_clips(clip_seconds, ad_length_s):
    """Does a clip list obey the rule? Fails on any clip over 6 s, a clip
    count outside the range, or a total below the minimum (above the maximum
    total is a failure too: the cost cap is planned on it)."""
    b = budget(ad_length_s)
    secs = [float(s) for s in clip_seconds]
    total = sum(secs)
    why = []
    if any(s <= 0 for s in secs):
        why.append("a clip has no length")
    if any(s > CLIP_MAX_S + 1e-9 for s in secs):
        why.append("a clip is longer than %.0f s" % CLIP_MAX_S)
    if not b["min_clips"] <= len(secs) <= b["max_clips"]:
        why.append("%d clips; need %d-%d" % (len(secs), b["min_clips"],
                                             b["max_clips"]))
    if total + 1e-9 < b["total_min_s"]:
        why.append("%.1f s of lip-sync; need at least %.1f s"
                   % (total, b["total_min_s"]))
    if total > b["total_max_s"] + 1e-9:
        why.append("%.1f s of lip-sync; budgeted at most %.1f s"
                   % (total, b["total_max_s"]))
    return {"pass": not why, "reason_code": "LIPSYNC_CLIPS_OK" if not why
            else BAD_PLAN, "reasons": why, "total_s": round(total, 3),
            "clips": len(secs), "budget": b}


def estimate_cost_usd(total_s, usd_per_s, shapes=1, attempts=1):
    """Worst-case lip-sync spend: seconds x rate x shapes x attempts. usd_per_s
    is Skill 74's price for kling/ai-avatar-standard (never a stored number)."""
    if not _num(usd_per_s) or usd_per_s <= 0:
        raise LipsyncClipsError(PRICE_UNKNOWN, "no usable per-second price "
                                "from Skill 74; refusing to dispatch")
    return round(total_s * usd_per_s * shapes * attempts, 4)


def check_budget(total_s, usd_per_s, remaining_usd, shapes=1, attempts=1):
    """Pre-dispatch cap check. Raises LipsyncClipsError (OVER_CAP,
    PRICE_UNKNOWN, CAP_UNKNOWN) instead of ever overspending or guessing."""
    if not _num(remaining_usd) or remaining_usd < 0:
        raise LipsyncClipsError(CAP_UNKNOWN, "no cap or remaining budget "
                                "recorded; refusing to dispatch")
    cost = estimate_cost_usd(total_s, usd_per_s, shapes, attempts)
    if cost > remaining_usd + 1e-9:
        raise LipsyncClipsError(
            OVER_CAP, "lip-sync would cost $%.2f (%.1f s x $%.3f/s x %d "
            "shape(s) x %d attempt(s)) but only $%.2f of the cap is left; "
            "nothing was dispatched" % (cost, total_s, usd_per_s, shapes,
                                        attempts, remaining_usd))
    return {"pass": True, "cost_usd": cost, "remaining_usd": remaining_usd,
            "left_after_usd": round(remaining_usd - cost, 4)}
