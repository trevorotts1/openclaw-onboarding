#!/usr/bin/env python3
"""lipsync_clips.py: the one place that says HOW MUCH lip-sync an ad carries.

APPROVED DIRECTION (Trevor, 2026-10-23): coverage is a SHARE of the selected
duration, not a fixed block of seconds.

  * target 25-30% of the ad, hard MAXIMUM 35% (nothing may cross it);
  * the first 12 s must be clearly articulated: the spoken opener / first sung
    hook is lip-synced inside that window (`check_opening`);
  * still MORE PIECES, NOT LONGER ONES: every clip is 4-6 s, hard cap 6 s, and
    never fewer than 3 clips whatever the length.

This supersedes the 2026-10-08 "30-40 s per 60 s" order. That older text is
kept ONLY as the derived 60 s reference (`TOTAL_PER_REF_S`, `CLIPS_PER_REF` =
15-18 s and 3-5 clips) so the class table and the E6 reader keep one source;
it must not regain control of a run.

When a duration cannot satisfy the shares, the 3-clip / 4-s floor and the 6 s
clip cap at the same time, `duration_conflicts()` says which two bounds
collide and the caller EXPOSES it (card refuses, plan flags). The policy is
never silently bent and a run is never re-planned behind the owner's back.

The historical FREE / no-lip-sync route stays explicit (`ROUTE_NO_LIPSYNC`):
zero paid Kling jobs is a valid plan when the owner asks for it, and is never
the default and never a reason to drop lip-sync from an ordinary run.

Every lip-sync clip is a paid KIE job (`kling/ai-avatar-standard`), so the
footage drives the lip-sync cost. `check_budget` refuses LOUDLY when the job
would pass the cap (or when the price or the cap is unknown); it never trims
the plan or spends past a cap silently. Prices are never stored here: the
per-second rate comes from Skill 74 `price`.

TWO-TRY RULE (Trevor 2026-10-08, unchanged): at most 2 paid Kling jobs per
segment, every name variant counted (`count_jobs`, `check_try_limit`); after
that the best measured take wins. Budgets are priced with attempts=MAX_TRIES.

Stdlib only, no network, no spend.
"""
from __future__ import annotations

import math
import re

REF_LENGTH_S = 60.0
TARGET_SHARE = (0.25, 0.30)     # approved target coverage of the ad length
MAX_SHARE = 0.35                # HARD maximum: nothing may cross it
OPENING_WINDOW_S = 12.0         # the opening must be clearly articulated
CLIP_MIN_S = 4.0
CLIP_MAX_S = 6.0                # hard cap per clip
MIN_CLIPS_FLOOR = 3             # never fewer than 3, whatever the length
#: 60 s reference values, DERIVED from the shares above. Kept because the
#: length-class table and final_assembler/lipsync_coverage read them as a 60 s
#: reference; they are outputs of the policy, never a second policy.
TOTAL_PER_REF_S = (TARGET_SHARE[0] * REF_LENGTH_S,
                   TARGET_SHARE[1] * REF_LENGTH_S)
PRIORITY_ROLES = ("hook", "opener", "closing")   # sung hooks, spoken open/close
MAX_TRIES = 2                   # paid Kling jobs per segment, then keep the best
PRE_S, TAIL_S = 0.30, 0.20      # padding around the first/last word
MIN_ONSETS_PER_S = 1.5
MAX_HELD_WORD_S = 1.2
MIN_REST_S = 0.12
LIP_FRIENDLY = "pbmfvw"         # force a visible lip closure / lip shape
TRY_LIMIT = "LIPSYNC_TRY_LIMIT"

OVER_CAP = "LIPSYNC_OVER_CAP"
PRICE_UNKNOWN = "LIPSYNC_PRICE_UNKNOWN"
CAP_UNKNOWN = "LIPSYNC_CAP_UNKNOWN"
BAD_PLAN = "LIPSYNC_PLAN_OUT_OF_RULE"
DURATION_CONFLICT = "LIPSYNC_DURATION_CONFLICT"
OPENING_SHORT = "LIPSYNC_OPENING_NOT_ARTICULATED"

#: The two explicit routes. Ordinary runs carry lip-sync; the historical FREE
#: route is opt-in only and never becomes the default.
ROUTE_LIPSYNC = "lipsync"
ROUTE_NO_LIPSYNC = "no_lipsync"
ROUTES = (ROUTE_LIPSYNC, ROUTE_NO_LIPSYNC)
FREE_ROUTE_OK = "LIPSYNC_FREE_ROUTE"


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


def _clip_bounds(ad_length_s):
    """(min_clips, max_clips) for one length: enough pieces to reach the 25%
    target inside the 6 s clip cap, never more than the 35% maximum allows at
    the 4 s clip floor, and never below the 3-clip floor."""
    lo = max(MIN_CLIPS_FLOOR,
             int(math.ceil(TARGET_SHARE[0] * ad_length_s / CLIP_MAX_S - 1e-9)))
    hi = max(lo,
             int(math.floor(MAX_SHARE * ad_length_s / CLIP_MIN_S + 1e-9)))
    return lo, hi


#: 60 s reference clip range, derived by the same rule (see TOTAL_PER_REF_S).
CLIPS_PER_REF = _clip_bounds(REF_LENGTH_S)


def budget(ad_length_s):
    """The rule for one ad length: coverage shares, clip range, per-clip seconds.

    ``total_min_s``/``total_max_s`` are the 25-30% target band; ``hard_max_s``
    is the 35% refusal bound nothing may cross; ``floor_s`` is the smallest
    legal total (3 clips x 4 s). Conflicts between those bounds at a given
    duration are reported by ``duration_conflicts()``, never resolved here.
    """
    scale(ad_length_s)                       # validates the input
    lo, hi = _clip_bounds(ad_length_s)
    return {"ad_length_s": ad_length_s, "min_clips": lo, "max_clips": hi,
            "clip_min_s": CLIP_MIN_S, "clip_max_s": CLIP_MAX_S,
            "total_min_s": TARGET_SHARE[0] * ad_length_s,
            "total_max_s": TARGET_SHARE[1] * ad_length_s,
            "hard_max_s": MAX_SHARE * ad_length_s,
            "floor_s": MIN_CLIPS_FLOOR * CLIP_MIN_S,
            "target_share": TARGET_SHARE, "max_share": MAX_SHARE,
            "opening_window_s": OPENING_WINDOW_S}


def duration_conflicts(ad_length_s):
    """The bounds this duration cannot satisfy at the same time, or [].

    Each entry names both sides of the collision. The caller must EXPOSE it
    (refuse the card / flag the plan with DURATION_CONFLICT); it must never
    bend the policy, re-plan silently, or spend.
    """
    b = budget(ad_length_s)
    out = []
    if b["floor_s"] > b["hard_max_s"] + 1e-9:
        out.append("%.1f s floor (%d clips x %.0f s) exceeds the %.0f%% maximum "
                   "of %.1f s at %.1f s long"
                   % (b["floor_s"], MIN_CLIPS_FLOOR, CLIP_MIN_S,
                      MAX_SHARE * 100, b["hard_max_s"], ad_length_s))
    if b["max_clips"] * CLIP_MAX_S < b["total_min_s"] - 1e-9:
        out.append("%d clips x %.0f s = %.1f s cannot reach the %.0f%% target "
                   "of %.1f s at %.1f s long"
                   % (b["max_clips"], CLIP_MAX_S,
                      b["max_clips"] * CLIP_MAX_S, TARGET_SHARE[0] * 100,
                      b["total_min_s"], ad_length_s))
    return out


def check_opening(first_clip_start_s, ad_length_s):
    """The first 12 s (or the whole ad, if shorter) must be articulated: the
    first lip-sync clip starts inside that window."""
    window = min(OPENING_WINDOW_S, float(ad_length_s))
    ok = (_num(first_clip_start_s) and 0 <= first_clip_start_s <= window + 1e-9)
    return {"pass": ok,
            "reason_code": "LIPSYNC_OPENING_OK" if ok else OPENING_SHORT,
            "opening_window_s": window, "first_clip_start_s": first_clip_start_s}


def check_clips(clip_seconds, ad_length_s, route=ROUTE_LIPSYNC,
                first_clip_start_s=None):
    """Does a clip list obey the rule?

    ``route="lipsync"`` (the default, and the ordinary run): fails on a clip
    over 6 s, a clip count outside the range, a total below the 25% target, a
    total above the 35% maximum, or a duration whose bounds collide.
    ``route="no_lipsync"``: the explicit historical FREE route -- it passes
    only with ZERO clips (nothing paid), and it never becomes the default.
    """
    if route not in ROUTES:
        raise LipsyncClipsError(BAD_PLAN, "unknown lip-sync route %r (one of %s)"
                                % (route, ", ".join(ROUTES)))
    b = budget(ad_length_s)
    secs = [float(s) for s in clip_seconds]
    total = sum(secs)
    if route == ROUTE_NO_LIPSYNC:
        why = ([] if not secs else
               ["the free / no-lip-sync route carries %d clip(s); it is zero "
                "paid jobs" % len(secs)])
        return {"pass": not why, "reason_code": FREE_ROUTE_OK if not why
                else BAD_PLAN, "reasons": why, "route": route,
                "total_s": round(total, 3), "clips": len(secs), "budget": b}
    why = list(duration_conflicts(ad_length_s))
    if any(s <= 0 for s in secs):
        why.append("a clip has no length")
    if any(s > CLIP_MAX_S + 1e-9 for s in secs):
        why.append("a clip is longer than %.0f s" % CLIP_MAX_S)
    if not b["min_clips"] <= len(secs) <= b["max_clips"]:
        why.append("%d clips; need %d-%d" % (len(secs), b["min_clips"],
                                             b["max_clips"]))
    if total + 1e-9 < b["total_min_s"]:
        why.append("%.1f s of lip-sync; need at least %.1f s (%.0f%%)"
                   % (total, b["total_min_s"], TARGET_SHARE[0] * 100))
    if total > b["hard_max_s"] + 1e-9:
        why.append("%.1f s of lip-sync; the %.0f%% maximum at %.1f s is %.1f s"
                   % (total, MAX_SHARE * 100, ad_length_s, b["hard_max_s"]))
    if first_clip_start_s is not None:
        op = check_opening(first_clip_start_s, ad_length_s)
        if not op["pass"]:
            why.append("first clip starts at %.1f s; the first %.0f s must be "
                       "articulated" % (float(first_clip_start_s),
                                        op["opening_window_s"]))
    return {"pass": not why, "reason_code": "LIPSYNC_CLIPS_OK" if not why
            else BAD_PLAN, "reasons": why, "route": route,
            "total_s": round(total, 3), "clips": len(secs), "budget": b}


def estimate_cost_usd(total_s, usd_per_s, shapes=1, attempts=MAX_TRIES):
    """Worst-case lip-sync spend: seconds x rate x shapes x attempts. usd_per_s
    is Skill 74's price for kling/ai-avatar-standard (never a stored number)."""
    if not _num(usd_per_s) or usd_per_s <= 0:
        raise LipsyncClipsError(PRICE_UNKNOWN, "no usable per-second price "
                                "from Skill 74; refusing to dispatch")
    return round(total_s * usd_per_s * shapes * attempts, 4)


def check_budget(total_s, usd_per_s, remaining_usd, shapes=1, attempts=MAX_TRIES):
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


def count_jobs(job_keys, segment):
    """Paid lip-sync jobs already made for one segment, every name variant
    counted: 'lip-ad-ss3', 'lip-ad-ss3-b', 'x/lip-ad-ss3_retry' all count for
    'ss3'; 'ss30' does not."""
    pat = re.compile(r".*lip-ad-%s(?![0-9])" % re.escape(segment))
    return sum(1 for k in job_keys if pat.match(k))


def check_try_limit(job_keys, segment):
    """Refuse a 3rd paid job for a segment BEFORE anything is spent. Returns
    the tries left; raises LipsyncClipsError(TRY_LIMIT) at 0."""
    n = count_jobs(job_keys, segment)
    if n >= MAX_TRIES:
        raise LipsyncClipsError(TRY_LIMIT, "lip-sync try limit reached for "
                                "segment %s (%d jobs; limit %d, every name "
                                "variant counts): use the best-measured take, "
                                "mark it in the receipt, move on"
                                % (segment, n, MAX_TRIES))
    return MAX_TRIES - n


def _is_friendly(word):
    return any(c in LIP_FRIENDLY for c in str(word).lower())


def choose_window(word_stamps, role="hook", min_s=CLIP_MIN_S, max_s=CLIP_MAX_S,
                  pre=PRE_S, tail=TAIL_S, used_lines=()):
    """Pick the 4-6 s lip-sync window inside a hook/opener/closing.

    word_stamps: [{"word","start","end"}] Suno timestamps (s), in order.
    The window starts at a word start and ends at a word end (phrase
    boundaries), then pre/tail padding is added, so pre + words + tail is
    min_s..max_s. Rules, in order:
      1. cut at a real rest (gap >= MIN_REST_S) where one exists;
      2. most word onsets per second, at least MIN_ONSETS_PER_S;
      3. no held word over MAX_HELD_WORD_S (if every window breaks it, take the
         shortest held note and mark HELD_NOTE);
      4. prefer p, b, m, f, v, w words;
      5. a hook sung 2-3 times: a different line per clip (used_lines holds
         the word-text of lines already chosen; an identical line is skipped
         unless it is the only choice).
    Returns {"start","end","pad_start","pad_end","dur","words","onsets_per_s",
    "held_s","lip_words","flags"} or raises LipsyncClipsError(BAD_PLAN)."""
    w = [x for x in word_stamps if x["end"] > x["start"]]
    if not w:
        raise LipsyncClipsError(BAD_PLAN, "no word stamps to choose a window from")
    cands = []
    for i in range(len(w)):
        for j in range(i, len(w)):
            words = w[i:j + 1]
            span = words[-1]["end"] - words[0]["start"]
            total = pre + span + tail
            if total > max_s + 1e-9:
                break
            if total < min_s - 1e-9:
                continue
            held = max(x["end"] - x["start"] for x in words)
            rest_l = (w[i]["start"] - w[i - 1]["end"]) if i else 9.0
            rest_r = (w[j + 1]["start"] - w[j]["end"]) if j + 1 < len(w) else 9.0
            ops = len(words) / span
            text = " ".join(str(x["word"]).lower() for x in words)
            cands.append({
                "start": words[0]["start"], "end": words[-1]["end"],
                "pad_start": max(0.0, words[0]["start"] - pre),
                "pad_end": words[-1]["end"] + tail, "dur": round(total, 3),
                "words": text, "onsets_per_s": round(ops, 3),
                "held_s": round(held, 3),
                "lip_words": sum(_is_friendly(x["word"]) for x in words),
                "_rest": (rest_l >= MIN_REST_S) + (rest_r >= MIN_REST_S),
                "_new": text not in used_lines, "flags": []})
    if not cands:
        raise LipsyncClipsError(BAD_PLAN, "no %.0f-%.0f s window fits these words"
                                % (min_s, max_s))
    ok = [c for c in cands if c["held_s"] <= MAX_HELD_WORD_S]
    pool = ok or cands
    key = lambda c: (c["_new"], c["_rest"], c["onsets_per_s"] >= MIN_ONSETS_PER_S,
                     c["onsets_per_s"], c["lip_words"], -c["held_s"])
    if not ok:
        key = lambda c: (c["_new"], -c["held_s"], c["_rest"], c["onsets_per_s"], c["lip_words"])
    best = dict(max(pool, key=key))
    if not ok:
        best["flags"].append("HELD_NOTE")
    if best["onsets_per_s"] < MIN_ONSETS_PER_S:
        best["flags"].append("SPARSE_ONSETS")
    for k in ("_rest", "_new"):
        best.pop(k)
    return best


# ---------------------------------------------------------------------------
# U15h: cross-check against the class table (design 6; never a second formula).

def class_check(delivered_s):
    """This module's budget equals the class row for that delivered length.

    Cross-check only -- ``budget()`` stays THE lip-sync rule; the class table
    is the shared reader (``prompt_templates.length_class``). [] when they
    agree; the reasons name each drifted field otherwise.
    """
    try:
        from prompt_templates import prompt_templates as _PT
    except ImportError:                        # template layer not installed
        return []
    D = float(delivered_s)
    L = int(D) + 2                             # chosen length: D = L - 2
    try:
        row = _PT.length_class(L)
    except _PT.PromptTemplateError as e:
        return ["length_class(%d): %s" % (L, e)]
    b = budget(D)
    mine = {"delivered_s": D,
            "lipsync_clips": [b["min_clips"], b["max_clips"]],
            "lipsync_seconds": [round(b["total_min_s"], 1),
                                round(b["total_max_s"], 1)]}
    return ["%s class=%r budget=%r" % (f, row.get(f), v)
            for f, v in sorted(mine.items()) if row.get(f) != v]
