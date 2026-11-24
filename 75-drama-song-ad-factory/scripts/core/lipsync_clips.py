#!/usr/bin/env python3
"""lipsync_clips.py: the one place that says HOW MUCH lip-sync an ad carries.

APPROVED DIRECTION (Trevor, 2026-11-23, replacing the October 8 "more pieces,
not longer ones" order for lip-sync length): coverage is a SHARE of the
selected duration, and a piece is the WHOLE SENTENCE.

  * target 25-30% of the ad; 35% is the normal top; whole sentences win over
    the share (3.3a rule 5), and when the story needs it lip-sync may pass the
    top by up to 20 s with the reason recorded (N-81);
  * the first 12 s must be clearly articulated: the spoken opener / first sung
    hook is lip-synced inside that window (`check_opening`);
  * a piece is one or more whole sentences, 5 to 30 seconds (N-101): it runs
    from the first word's start to the last word's end, never starts or ends
    inside a sentence, and is never padded, stretched or cut. A passage over
    30 s is a stitch group split only at a breath or a line boundary (N-112);
  * the floor of 3 pieces applies from 90 seconds up; under 90 s there is no
    floor of 3 (N-101).

This supersedes the 2026-10-08 "30-40 s per 60 s" order. The derived 60 s
reference (`TOTAL_PER_REF_S`, `CLIPS_PER_REF`) stays one output of the policy
for the class table and the E6 reader; it never regains control of a run.

When a duration cannot satisfy the shares and the 5 s piece floor at the same
time, `duration_conflicts()` says which bounds collide and the caller EXPOSES
it (card refuses, plan flags). The policy is never silently bent and a run is
never re-planned behind the owner's back.

The historical FREE / no-lip-sync route stays explicit (`ROUTE_NO_LIPSYNC`):
zero paid lip-sync jobs is a valid plan only when `control/method.json` records
a `lipsync_opt_out` with `who` and `at` (`no_lipsync_opt_out`); it is never the
default and never a reason to drop lip-sync from an ordinary run.

Every lip-sync clip is a paid KIE job on `omnihuman-2-0`, the only lip-sync
model (S-42, 3C.1a) -- Kling Avatar is retired and there is no backup -- so the
footage drives the lip-sync cost. The budget is priced at 14 credits per
rounded-up second of clip. `check_budget` refuses LOUDLY when the job would
pass the cap (or when the price or the cap is unknown); it never trims the plan
or spends past a cap silently. Prices are never stored here: the per-second
rate comes from Skill 74 `price`.

TWO-TRY RULE (Trevor 2026-10-08, unchanged): at most 2 paid lip-sync jobs per
segment, every name variant counted (`count_jobs`, `check_try_limit`); after
that the best measured take wins. Budgets are priced with attempts=MAX_TRIES.

Stdlib only, no network, no spend.
"""
from __future__ import annotations

import json
import math
import os
import re

REF_LENGTH_S = 60.0
TARGET_SHARE = (0.25, 0.30)     # approved target coverage of the ad length
MAX_SHARE = 0.35                # HARD maximum: nothing may cross it
OPENING_WINDOW_S = 12.0         # the opening must be clearly articulated
CLIP_MIN_S = 5.0                # N-101: a piece is never under 5 s
CLIP_MAX_S = 30.0               # N-101: one piece, 30 s top; longer stitches
MIN_CLIPS_FLOOR = 3             # the floor of 3 applies from 90 s up only
MIN_CLIPS_FROM_S = 90.0         # N-101: no floor of 3 under this length
SENTENCE_GAP_S = 1.0            # no breath between lines: same piece (3.3a)
SHARE_GRACE_S = 20.0            # N-81: story-need pass past the top, recorded
#: 60 s reference values, DERIVED from the shares above. Kept because the
#: length-class table and final_assembler/lipsync_coverage read them as a 60 s
#: reference; they are outputs of the policy, never a second policy.
TOTAL_PER_REF_S = (TARGET_SHARE[0] * REF_LENGTH_S,
                   TARGET_SHARE[1] * REF_LENGTH_S)
PRIORITY_ROLES = ("hook", "opener", "closing")   # sung hooks, spoken open/close
MAX_TRIES = 2                   # paid lip-sync jobs per segment, then keep the best
PRE_S, TAIL_S = 0.30, 0.20      # padding around the first/last word
MIN_ONSETS_PER_S = 1.5
MAX_HELD_WORD_S = 1.2
MIN_REST_S = 0.12
LIP_FRIENDLY = "pbmfvw"         # force a visible lip closure / lip shape
TRY_LIMIT = "LIPSYNC_TRY_LIMIT"

OVER_CAP = "LIPSYNC_OVER_CAP"
CLIP_TOO_SHORT = "LIPSYNC_CLIP_TOO_SHORT"
AUDIO_TOO_SHORT = "LIPSYNC_AUDIO_TOO_SHORT"
AUDIO_TOO_LONG = "LIPSYNC_AUDIO_TOO_LONG"
CUTS_SENTENCE = "LIPSYNC_CUTS_SENTENCE"
TAKE_SHORT = "LIPSYNC_TAKE_SHORT"
STITCH_NOT_ALLOWED = "LIPSYNC_STITCH_NOT_ALLOWED"
OPT_OUT_MISSING = "LIPSYNC_OPT_OUT_MISSING"
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


def no_lipsync_opt_out(run_dir):
    """The owner's recorded opt-out for the free / no-lip-sync route, or None.

    S75-047: ROUTE_NO_LIPSYNC is honoured only when the run's
    ``control/method.json`` carries ``lipsync_opt_out`` with a non-empty
    ``who`` and ``at``. A missing, unreadable or half-written record reads as
    no opt-out, so every caller keeps refusing. The card never offers this
    route; one reader serves the clip policy, the evidence gate and the
    final assembler so the three can never disagree.
    """
    if not run_dir:
        return None
    try:
        with open(os.path.join(str(run_dir), "control", "method.json"),
                  encoding="utf-8") as fh:
            method = json.load(fh)
    except (OSError, ValueError):
        return None
    opt = method.get("lipsync_opt_out") if isinstance(method, dict) else None
    if not isinstance(opt, dict):
        return None
    who, at = opt.get("who"), opt.get("at")
    if not (isinstance(who, str) and who.strip()
            and isinstance(at, str) and at.strip()):
        return None
    return {"who": who.strip(), "at": at.strip()}


def scale(ad_length_s):
    if not _num(ad_length_s) or ad_length_s <= 0:
        raise LipsyncClipsError("BAD_INPUT", "ad_length_s must be positive")
    return ad_length_s / REF_LENGTH_S


def _round(x):
    return int(x + 0.5)


def _floor_applies(ad_length_s):
    """N-101: the floor of 3 pieces applies from 90 s up, never under it."""
    return float(ad_length_s) >= MIN_CLIPS_FROM_S - 1e-9


def _clip_bounds(ad_length_s):
    """(min_clips, max_clips) for one length: enough pieces to reach the 25%
    target inside the 30 s piece top, never more than the 35% top allows at
    the 5 s floor. The absolute floor of 3 applies from 90 s up (N-101)."""
    floor = MIN_CLIPS_FLOOR if _floor_applies(ad_length_s) else 0
    lo = max(floor,
             int(math.ceil(TARGET_SHARE[0] * ad_length_s / CLIP_MAX_S - 1e-9)))
    hi = max(lo,
             int(math.floor(MAX_SHARE * ad_length_s / CLIP_MIN_S + 1e-9)))
    return lo, hi


#: 60 s reference clip range, derived by the same rule (see TOTAL_PER_REF_S).
CLIPS_PER_REF = _clip_bounds(REF_LENGTH_S)


def budget(ad_length_s):
    """The rule for one ad length: coverage shares, clip range, per-clip seconds.

    ``total_min_s``/``total_max_s`` are the 25-30% target band; ``hard_max_s``
    is the 35% normal top; ``share_grace_s`` is the recorded story-need pass
    (N-81); ``floor_s`` is the smallest legal total when the floor of 3
    applies (90 s up), else 0. Conflicts between those bounds at a given
    duration are reported by ``duration_conflicts()``, never resolved here.
    """
    scale(ad_length_s)                       # validates the input
    lo, hi = _clip_bounds(ad_length_s)
    return {"ad_length_s": ad_length_s, "min_clips": lo, "max_clips": hi,
            "clip_min_s": CLIP_MIN_S, "clip_max_s": CLIP_MAX_S,
            "total_min_s": TARGET_SHARE[0] * ad_length_s,
            "total_max_s": TARGET_SHARE[1] * ad_length_s,
            "hard_max_s": MAX_SHARE * ad_length_s,
            "share_grace_s": SHARE_GRACE_S,
            "floor_s": (MIN_CLIPS_FLOOR * CLIP_MIN_S
                        if _floor_applies(ad_length_s) else 0.0),
            "min_clips_floor_applies": _floor_applies(ad_length_s),
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
    if b["min_clips_floor_applies"] and b["floor_s"] > b["hard_max_s"] + 1e-9:
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
                first_clip_start_s=None, whole_sentences=False,
                story_reason=None):
    """Does a clip list obey the rule?

    ``route="lipsync"`` (the default, and the ordinary run): fails on a piece
    under the 5.0 s floor (LIPSYNC_CLIP_TOO_SHORT + LIPSYNC_AUDIO_TOO_SHORT --
    a short take stops counting toward lines and seconds), a piece over 30 s
    (LIPSYNC_AUDIO_TOO_LONG; the fix is the stitch), a piece count outside the
    range, a total below the 25% target, a total above the 35% top, or a
    duration whose bounds collide.
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
                else BAD_PLAN, "codes": [] if not why else [BAD_PLAN],
                "reasons": why, "route": route,
                "total_s": round(total, 3), "clips": len(secs), "budget": b}
    why = list(duration_conflicts(ad_length_s))
    codes = []
    if any(s <= 0 for s in secs):
        why.append("a piece has no length")
    # F-LIP-4 + N-101: the per-piece floor. A piece under CLIP_MIN_S is refused
    # and, crucially, stops counting toward the piece count and the seconds --
    # a pile of short takes never buys coverage it does not carry.
    short = [s for s in secs if 0 < s < CLIP_MIN_S - 1e-9]
    counted = [s for s in secs if s >= CLIP_MIN_S - 1e-9]
    total = sum(counted)
    if short:
        why.append("%s: %d piece(s) under the %.0f s floor (shortest %g s)"
                   % (CLIP_TOO_SHORT, len(short), CLIP_MIN_S, min(short)))
        codes.extend([CLIP_TOO_SHORT, AUDIO_TOO_SHORT])
    if any(s > CLIP_MAX_S + 1e-9 for s in secs):
        why.append("%s: a piece is longer than %.0f s; split it at a breath "
                   "or a line boundary into a stitch group"
                   % (AUDIO_TOO_LONG, CLIP_MAX_S))
        codes.append(AUDIO_TOO_LONG)
    over_count = len(counted) > b["max_clips"]
    if len(counted) < b["min_clips"] or (over_count and not whole_sentences):
        why.append("%d pieces; need %d-%d" % (len(counted), b["min_clips"],
                                              b["max_clips"]))
    if total + 1e-9 < b["total_min_s"]:
        why.append("%.1f s of lip-sync; need at least %.1f s (%.0f%%)"
                   % (total, b["total_min_s"], TARGET_SHARE[0] * 100))
    # N-81: past the 35% top is allowed when a story reason is recorded (up to
    # 20 s), and N-101 rule 5: finishing whole sentences wins over the top.
    reason_text = (story_reason.strip()
                   if isinstance(story_reason, str) and story_reason.strip()
                   else None)
    allowed_top = b["hard_max_s"] + (SHARE_GRACE_S if reason_text else 0.0)
    passed_share = total > b["hard_max_s"] + 1e-9
    if passed_share and not (whole_sentences or
                             (reason_text and total <= allowed_top + 1e-9)):
        why.append("%.1f s of lip-sync; the %.0f%% top at %.1f s is %.1f s "
                   "(a recorded story reason allows up to %.1f s)"
                   % (total, MAX_SHARE * 100, ad_length_s, b["hard_max_s"],
                      allowed_top))
        codes.append(OVER_CAP)
    if first_clip_start_s is not None:
        op = check_opening(first_clip_start_s, ad_length_s)
        if not op["pass"]:
            why.append("first piece starts at %.1f s; the first %.0f s must be "
                       "articulated" % (float(first_clip_start_s),
                                        op["opening_window_s"]))
    reason = ("LIPSYNC_CLIPS_OK" if not why
              else "+".join(dict.fromkeys(codes)) or BAD_PLAN)
    return {"pass": not why, "reason_code": reason, "codes":
            list(dict.fromkeys(codes)), "reasons": why, "route": route,
            "total_s": round(total, 3), "clips": len(secs),
            "share_pct": round(100.0 * total / ad_length_s, 2),
            "passed_share": passed_share,
            "share_note": (None if not passed_share else
                           reason_text or
                           "whole sentences win over the 35% top"),
            "whole_sentences": bool(whole_sentences),
            "clip_floor_s": CLIP_MIN_S, "budget": b}


def check_piece(audio_s, starts_in_sentence=False, ends_in_sentence=False,
                returned_s=None):
    """One Clip Sizer / dispatcher piece, before any spend (N-101, 3.3a).

    Refuses a piece whose audio starts or ends inside a sentence
    (LIPSYNC_CUTS_SENTENCE), under 5.0 s (LIPSYNC_AUDIO_TOO_SHORT), over 30 s
    (LIPSYNC_AUDIO_TOO_LONG; fix is the stitch), and a returned take shorter
    than its audio (LIPSYNC_TAKE_SHORT). Returns a verdict record.
    """
    why, codes = [], []
    if starts_in_sentence or ends_in_sentence:
        why.append("%s: the audio starts or ends inside a sentence"
                   % CUTS_SENTENCE)
        codes.append(CUTS_SENTENCE)
    if not _num(audio_s) or audio_s + 1e-9 < CLIP_MIN_S:
        why.append("%s: %.2f s of audio; the floor is %.1f s"
                   % (AUDIO_TOO_SHORT, audio_s if _num(audio_s) else 0.0,
                      CLIP_MIN_S))
        codes.append(AUDIO_TOO_SHORT)
    elif audio_s > CLIP_MAX_S + 1e-9:
        why.append("%s: %.2f s in one piece; %.0f s is the top -- stitch it"
                   % (AUDIO_TOO_LONG, audio_s, CLIP_MAX_S))
        codes.append(AUDIO_TOO_LONG)
    if returned_s is not None and (_num(audio_s)
                                   and returned_s + 1e-9 < audio_s):
        why.append("%s: returned %.2f s against %.2f s of audio"
                   % (TAKE_SHORT, returned_s, audio_s))
        codes.append(TAKE_SHORT)
    return {"pass": not why,
            "reason_code": "LIPSYNC_PIECE_OK" if not why else codes[0],
            "codes": codes, "reasons": why, "audio_s": audio_s,
            "returned_s": returned_s}


def check_take_length(audio_s, returned_s):
    """N-101: a take shorter than its audio fails LIPSYNC_TAKE_SHORT."""
    return check_piece(audio_s, returned_s=returned_s)


def tail_trim(returned_s, audio_s):
    """N-24: a lip-sync take ends with its line.

    The take is laid at its sentence's song time and used for the sentence's
    own length. The extra part a model adds at the end is cut, never kept and
    never used to extend the line; a take shorter than its audio is refused
    LIPSYNC_TAKE_SHORT. Nothing is stretched, sped up or frozen (3.8).
    """
    if not (_num(returned_s) and _num(audio_s)) or audio_s <= 0:
        raise LipsyncClipsError("BAD_INPUT",
                                "returned_s and audio_s must be positive")
    ok = returned_s + 1e-9 >= audio_s
    return {"pass": ok, "reason_code": "LIPSYNC_TAIL_OK" if ok else TAKE_SHORT,
            "use_s": round(min(returned_s, audio_s), 3),
            "trim_s": round(max(0.0, returned_s - audio_s), 3),
            "audio_s": audio_s, "returned_s": returned_s}


def split_stitch_group(word_stamps, max_s=CLIP_MAX_S, min_s=CLIP_MIN_S,
                       gap_s=SENTENCE_GAP_S):
    """A passage over 30 s as one stitch group (N-112, 3.3a rule 4).

    Split only at a breath (a singer's rest of ``gap_s`` or more, same singer)
    or a line boundary; every piece runs from a word start to a word end and
    is ``min_s``..``max_s`` long. Pieces stay in order, from the same picture,
    and the group counts as ONE take. Returns
    {"pieces":[{start,end,audio_s,dur,words}], "joins":[{at_s, kind}],
    "counts_as":1, "pass", "reason_code"}; raises LipsyncClipsError
    STITCH_NOT_ALLOWED when no legal split exists (a single run of words over
    the top with no rest: the line is too long for the model) or AUDIO_TOO_SHORT
    when a piece cannot reach the floor.
    """
    w = [x for x in word_stamps if x["end"] > x["start"]]
    if not w:
        raise LipsyncClipsError(BAD_PLAN, "no word stamps to stitch")
    # A legal split starts a piece at word i only where the singer rests.
    cuts = [i for i in range(1, len(w))
            if w[i]["start"] - w[i - 1]["end"] >= gap_s - 1e-9]
    pieces, i = [], 0
    while i < len(w):
        j = i
        while j + 1 < len(w) and \
                w[j + 1]["end"] - w[i]["start"] <= max_s + 1e-9:
            j += 1
        if j == len(w) - 1:
            end = j
        else:
            # A breath at j+1 (the boundary after the last word that fits) is a
            # legal cut: the piece is words i..j and the next starts at j+1.
            cut = max((c for c in cuts if i < c <= j + 1), default=None)
            if cut is None:
                raise LipsyncClipsError(
                    STITCH_NOT_ALLOWED,
                    "no breath inside %.2f s of words at %.2f s; a piece "
                    "cannot pass %.0f s"
                    % (w[j]["end"] - w[i]["start"], w[i]["start"], max_s))
            end = cut - 1
        words = w[i:end + 1]
        span = words[-1]["end"] - words[0]["start"]
        if span + 1e-9 < min_s:
            raise LipsyncClipsError(
                AUDIO_TOO_SHORT,
                "stitch piece at %.2f s is %.2f s; the floor is %.1f s"
                % (words[0]["start"], span, min_s))
        pieces.append({"start": words[0]["start"], "end": words[-1]["end"],
                       "audio_s": round(span, 3), "dur": round(span, 3),
                       "words": " ".join(str(x["word"]).lower()
                                         for x in words)})
        i = end + 1
    joins = [{"at_s": pieces[k]["end"],
              "kind": ("breath" if _gap_before(w, pieces[k + 1]["start"])
                       >= gap_s else "line")}
             for k in range(len(pieces) - 1)]
    return {"pieces": pieces, "joins": joins, "counts_as": 1,
            "pass": True, "reason_code": "LIPSYNC_STITCH_OK",
            "total_s": round(sum(p["audio_s"] for p in pieces), 3)}


def _gap_before(words, start):
    """Rest before the first word at ``start`` (0.0 when it is the first)."""
    for i, x in enumerate(words):
        if x["start"] >= start - 1e-9:
            return 9.0 if i == 0 else x["start"] - words[i - 1]["end"]
    return 0.0


def plan_stitch_passage(word_stamps, max_s=CLIP_MAX_S, min_s=CLIP_MIN_S):
    """N-101 + N-112: a passage up to 30 s is one piece; past 30 s it stitches."""
    w = [x for x in word_stamps if x["end"] > x["start"]]
    if not w:
        raise LipsyncClipsError(BAD_PLAN, "no word stamps in the passage")
    span = w[-1]["end"] - w[0]["start"]
    if span <= max_s + 1e-9:
        return {"pieces": [{
            "start": w[0]["start"], "end": w[-1]["end"],
            "audio_s": round(span, 3), "dur": round(span, 3),
            "words": " ".join(str(x["word"]).lower() for x in w)}],
            "joins": [], "counts_as": 1, "pass": True,
            "reason_code": "LIPSYNC_ONE_PIECE", "total_s": round(span, 3)}
    return split_stitch_group(w, max_s=max_s, min_s=min_s)


def estimate_cost_usd(total_s, usd_per_s, shapes=1, attempts=MAX_TRIES):
    """Worst-case lip-sync spend: seconds x rate x shapes x attempts. usd_per_s
    is Skill 74's price for omnihuman-2-0 (14 credits per rounded-up second of
    clip, section 3C.1a; never a stored number)."""
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


def check_try_limit(job_keys, segment, prior_prompts=None,
                    candidate_prompt=None):
    """Refuse a 3rd paid job for a segment BEFORE anything is spent. Returns
    the tries left; raises LipsyncClipsError(TRY_LIMIT) at 0.

    Lock 1 (NEVER-AGAIN): when the caller also passes the tried prompts plus
    the candidate, an unchanged 3rd prompt raises TEMPLATE_FAIL_LOCK.
    """
    n = count_jobs(job_keys, segment)
    if n >= MAX_TRIES:
        if prior_prompts is not None or candidate_prompt is not None:
            import never_again as _na
            lock = _na.check_template_fail(prior_prompts or [],
                                           candidate_prompt or "")
            if lock is not None:
                raise LipsyncClipsError(
                    lock["code"], lock["detail"] + " for segment %s "
                    "(drop the stillness line or stop and report)" % segment)
        raise LipsyncClipsError(TRY_LIMIT, "lip-sync try limit reached for "
                                "segment %s (%d jobs; limit %d, every name "
                                "variant counts): use the best-measured take, "
                                "mark it in the receipt, move on"
                                % (segment, n, MAX_TRIES))
    return MAX_TRIES - n


def _is_friendly(word):
    return any(c in LIP_FRIENDLY for c in str(word).lower())


def _phrase_record(words, pre, tail, used_lines=()):
    """One piece record from a whole run of words (start word to end word)."""
    span = words[-1]["end"] - words[0]["start"]
    held = max(x["end"] - x["start"] for x in words)
    text = " ".join(str(x["word"]).lower() for x in words)
    flags = []
    if held > MAX_HELD_WORD_S:
        # N-101: a held note is a flag on the receipt, never a reason to
        # move, shorten or drop the line.
        flags.append("HELD_NOTE")
    if len(words) / span < MIN_ONSETS_PER_S:
        flags.append("SLOW_ONSETS")
    if text in used_lines:
        flags.append("REPEATED_LINE")
    return {"start": words[0]["start"], "end": words[-1]["end"],
            "pad_start": max(0.0, words[0]["start"] - pre),
            "pad_end": words[-1]["end"] + tail,
            "audio_s": round(span, 3),
            "dur": round(pre + span + tail, 3),
            "words": text, "onsets_per_s": round(len(words) / span, 3),
            "held_s": round(held, 3),
            "lip_words": sum(_is_friendly(x["word"]) for x in words),
            "whole_sentence": True, "counts_as": 1, "stitch": False,
            "flags": flags}


def choose_window(word_stamps, role="hook", min_s=CLIP_MIN_S, max_s=CLIP_MAX_S,
                  pre=PRE_S, tail=TAIL_S, used_lines=()):
    """The piece for one whole line (N-101): word start to word end, never cut.

    word_stamps: [{"word","start","end"}] Suno timestamps (s), in order. The
    whole phrase is returned with pre/tail padding; it is never padded,
    stretched, shortened or moved. A held note or a slow passage is a flag on
    the receipt (HELD_NOTE, SLOW_ONSETS), never a reason to change the piece.
    Under 5 s the caller joins the line with the same singer's neighbour; over
    30 s the caller stitches (N-112); this function refuses both rather than
    bend the rule. Returns the piece record or raises LipsyncClipsError.
    """
    w = [x for x in word_stamps if x["end"] > x["start"]]
    if not w:
        raise LipsyncClipsError(BAD_PLAN, "no word stamps to choose a line from")
    piece = _phrase_record(w, pre, tail, used_lines)
    if piece["dur"] > max_s + 1e-9:
        raise LipsyncClipsError(AUDIO_TOO_LONG,
                                "%.2f s is over the %.0f s top; build a stitch "
                                "group split at a breath or a line boundary"
                                % (piece["dur"], max_s))
    if piece["dur"] < min_s - 1e-9:
        raise LipsyncClipsError(AUDIO_TOO_SHORT,
                                "%.2f s is under the %.0f s floor; join the "
                                "same singer's neighbouring sentence"
                                % (piece["dur"], min_s))
    return piece


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
