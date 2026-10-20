#!/usr/bin/env python3
"""Length formula: chosen ad length L (any seconds) -> the whole song plan.

Source: Perplexity length-formula research 2026-10-08 (file 11), CALIBRATED
to the measured passing songs: the four BSW 58 s songs (14 spoken words in
about 10 s, about 65 words in all). Perplexity's own rates (1.8 spoken / 1.0
sung words per second) came from an assumed spoken/sung split; ours come from
measured stems, so ours are the constants:

    delivered D   = L - 2                       (master_length rule)
    spoken_s      = f * D                       (f = the ad's spoken share)
    break_s       = instrumental breaks (6-12 s each, none at 60 s)
    sung_s        = D - spoken_s - break_s
    words         = spoken_s * SPOKEN_WPS + sung_s * SUNG_WPS
    L = 60, f = 0.175 -> 65 words (14 spoken + 51 sung).

Hook repeats stay sung_hook.hook_count (clamp(1 + floor(D/25), 2, 12)):
Perplexity's 24-36 repeats at 10 min contradict the measured 3 repeats in
58 s; one hook per 25 s of runtime keeps the hook a hook.

Spoken placement is ONE rule for every length (recipe v2): spoken only in
[Intro] and [Outro]. Opener <= 3 words up to 90 s (the measured pass), up to
12 on a long song; the closing CTA carries the rest. The block caps keep the
OPENER short; the CTA grows with the ad so the spoken share can REACH the
owner band (Trevor, 2026-10-09: do not lower targets -- spoken is 20-25% of
runtime, BSW 15-20%, at every length). The earlier fixed 30-word CTA cap
clipped the plan to 16.9% at 3 min, 10.1% at 5 min and 5.0% at 10 min; it is
retired. Short ads (60/90/120 s) are unchanged by this.

Over one generation (MAX_GEN_S) the plan is a base take plus extends: same
model, vocal gender, style, key and tempo, each extend continues
EXTEND_OVERLAP_S before the end of the audio so the join overlaps.
stdlib only; no network, no spend.
"""
from __future__ import annotations

import json
import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import math                  # noqa: E402

import music_styles as _MS   # noqa: E402
import sung_hook as _SH      # noqa: E402
import spoken_share as _SS   # noqa: E402
import words_fit as _WF      # noqa: E402

TOOL_NAME = "length_formula"
TOOL_VERSION = "1.0.0"
END_EARLY_S = 2
SPOKEN_WPS = 1.4          # measured: BSW passes, 14 words in ~10 s
SUNG_WPS = 1.07           # calibrated so L=60 gives 65 words at f=0.175
MAX_GEN_S = 300           # KIE generate-music duration 10-360 s (V6, custom_mode only); stay under
EXTEND_OVERLAP_S = 30     # continue_at = audio length - 30
EXTEND_NEW_S = MAX_GEN_S - EXTEND_OVERLAP_S
OPENER_MAX_WORDS_SHORT = 3        # up to 90 s: the measured pass
OPENER_MAX_WORDS_LONG = 12
OUTRO_MAX_WORDS = 30              # the CTA's own floor cap; it scales for long ads
#: NEW ACCEPTANCE RULE (WWFIX 2026-10-11, D1). A rap style's rap budget has a
#: FLOOR: ``rap_s >= max(RAP_FLOOR_S, RAP_FLOOR_SHARE * D)`` and
#: ``rap_words >= ceil(rap_s * style_rap_rate)``. Before this fix the rap budget
#: was a bare remainder -- ``rap_s = max(spoken_s - spoken_words / SPOKEN_WPS,
#: 0.0)`` -- so when the [Intro]/[Outro] spoken caps spent the whole spoken
#: allowance, rap_s went to 0, rap_words went to 0, the ``rap`` key was never
#: emitted and the plan silently reported NO RAP while raising nothing. That is
#: exactly the failure the owner measured on the R&B-plus-rap order. Both numbers
#: below are rules set by this fix, not measured limits of the failed run; the
#: opener and the closing call to action YIELD to them.
RAP_FLOOR_S = 8.0          # absolute seconds of rap, whatever the length
RAP_FLOOR_SHARE = 0.10     # and at least this share of the delivered seconds
#: WW-01 item 2 (NEW PROPOSED 2026-10-11). The TOTAL rap floor above is about
#: 11 words per verse at D 88 -- not a real rap budget, which is how a 19-word
#: two-verse sheet shipped. So every DECLARED rap verse has its own floor, and a
#: sheet must declare at least MIN_RAP_VERSES of them. Two verses at the floor
#: give 16.0 s / 40 words, so the total floor (8.8 s / 22 words) still holds:
#: the per-verse rule is strictly STRONGER than the total, never a replacement.
RAP_VERSE_MIN_S = 8.0      # every declared rap verse, on its own
MIN_RAP_VERSES = 2         # a sheet with fewer than this many rap verses refuses
#: WW-01 item 3 (NEW PROPOSED). The plan the formula emits must itself satisfy
#: the 70 % lexical floor, with the sung allocation re-priced at the STYLE's real
#: rate instead of the generic SUNG_WPS. The shipped formula priced sung words at
#: 1.07 words/s and emitted 15/2.0 + 23/2.5 + 67/1.9 = 51.9632 lexical seconds
#: against the 61.6 owed at D = 88. ONE copy of the rule: story_coverage holds
#: the same 0.70 for the delivered audio, and the two must agree.
LEXICAL_COVERAGE_MIN = 0.70
#: Block caps that keep a spoken block from turning the track into speech. The
#: OPENER never passes OPENER_MAX_WORDS_*; the CTA may carry what the ad's own
#: spoken target needs once the length is past the short classes, so the band is
#: reachable at every length (Trevor 2026-10-09). 30 words stays the CTA cap for
#: every short ad and for any long ad the band does not push past it.
def spoken_block_caps(D, spoken_words):
    """(opener cap, CTA cap) for one delivered length and spoken word count."""
    opener = OPENER_MAX_WORDS_SHORT if D <= 105 else OPENER_MAX_WORDS_LONG
    return opener, max(OUTRO_MAX_WORDS, spoken_words - opener)

# upper edge of the bracket (delivered seconds) -> section plan.
_BRACKETS = (
    (75, dict(name="60s", verses=1, pre=0, chorus=1, bridge=0, breaks=0, break_s=0)),
    (105, dict(name="90s", verses=2, pre=2, chorus=2, bridge=0, breaks=1, break_s=6)),
    (150, dict(name="2min", verses=2, pre=2, chorus=2, bridge=1, breaks=1, break_s=6)),
    (240, dict(name="3min", verses=2, pre=2, chorus=3, bridge=1, breaks=2, break_s=8)),
    (450, dict(name="5min", verses=3, pre=2, chorus=4, bridge=1, breaks=3, break_s=10)),
    (10 ** 9, dict(name="10min", verses=5, pre=4, chorus=7, bridge=2, breaks=5, break_s=12)),
)


# ---------------------------------------------------------------------------
# FU-U16: story doctrine -- villain, pain, rise (Trevor order 2026-10-08).
# "People don't care about the hero until they meet the villain." - Trevor Otts
# These are not music videos: they are compelling true stories told through
# the animation, the music and the lyrics, songs strong enough to sell as a
# soundtrack (the Grey's Anatomy standard). Every ad carries the PAIN and the
# RISE; every ad names its VILLAIN -- a person or not a person (cancer, debt,
# a layoff, a lie, burnout, fear, the inner critic, a system) -- named in the
# story plan, shown on screen in its OWN shots, felt in the lyrics, then
# confronted and defeated or transformed at the rise.
VILLAIN_PAIN_LO_PCT = 20.0            # pain share of runtime: target band
VILLAIN_PAIN_HI_PCT = 35.0
SHOT_DEFAULT_S = 3.0                  # a tagged shot with no stated duration
STORY_ARC_U16 = ("hook", "the_world", "villain_arrives", "pain_deepens",
                 "lowest_point", "the_turn", "the_rise", "call_to_action")
VILLAIN_TAGS = ("villain",)

def _u16_tagged(obj, tag):
    if not isinstance(obj, dict):
        return False
    v = obj.get(tag)
    if v is True:
        return True
    vis = obj.get("villain_visibility") if tag == "villain" else None
    if tag == "villain" and isinstance(vis, str) and vis.strip().lower() not in ("", "none"):
        return True
    tags = obj.get("tags") or ()
    if isinstance(tags, str):
        tags = (tags,)
    return tag in tags

def _u16_seconds(obj):
    for k in ("seconds", "duration_s", "duration"):
        v = obj.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            return float(v)
    return SHOT_DEFAULT_S

def plan_villain_doctrine(plan, shots=None, lyric_lines=None):
    """FU-U16 planner: the villain contract, pain seconds and rise seconds.

    Fails closed (verdict FAIL, never pass) on exactly two shapes: no villain
    named in the story plan, or a named villain with no villain-tagged shot.
    The pain share of runtime is a TARGET band of 20-35 percent: outside it
    is a FLAG carrying the measured seconds and percent, never a block.
    Stdlib only; pure; no network, no spend.
    """
    runtime_s = float(plan.get("delivered_s") or plan.get("chosen_length_s") or 0.0)
    if runtime_s <= 0:
        raise LengthError("plan carries no delivered_s/chosen_length_s")
    shots = [s for s in (shots or []) if isinstance(s, dict)]
    lines = [l for l in (lyric_lines or []) if isinstance(l, dict)]

    villain = plan.get("villain")
    if isinstance(villain, str):
        villain = {"name": villain} if villain.strip() else None
    name = villain.get("name") if isinstance(villain, dict) else None
    named = bool(isinstance(name, str) and name.strip())

    villain_shots = [s for s in shots if _u16_tagged(s, "villain")]
    villain_seconds = round(sum(_u16_seconds(s) for s in villain_shots), 1)
    pain_seconds = round(sum(_u16_seconds(o) for o in shots + lines
                             if _u16_tagged(o, "pain")), 1)
    rise_seconds = round(sum(_u16_seconds(o) for o in shots + lines
                             if _u16_tagged(o, "rise")), 1)
    pain_percent = round(pain_seconds / runtime_s * 100.0, 1)
    in_target = VILLAIN_PAIN_LO_PCT <= pain_percent <= VILLAIN_PAIN_HI_PCT

    fail_codes = []
    if not named:
        fail_codes.append("NO_VILLAIN_NAMED")
    if named and not villain_shots:
        fail_codes.append("VILLAIN_HAS_NO_SHOT")
    flags = []
    if not in_target:
        flags.append("PAIN_SHARE_OUTSIDE_TARGET")
    verdict = "FAIL" if fail_codes else ("PASS" if not flags else "FLAG")
    return {
        "arc": list(STORY_ARC_U16),
        "arc_rule": ("hook -> the world -> the villain arrives -> the pain "
                     "deepens -> the lowest point -> the turn (the product "
                     "is the key) -> the rise -> the call to action; the "
                     "pain gets real screen time and the rise is earned"),
        "runtime_s": runtime_s,
        "villain": {"name": name if named else None,
                    "kind": (villain.get("kind") if isinstance(villain, dict)
                             else None),
                    "named": named},
        "villain_shots": len(villain_shots),
        "villain_seconds": villain_seconds,
        "pain_seconds": pain_seconds,
        "pain_percent": pain_percent,
        "rise_seconds": rise_seconds,
        "target_lo_pct": VILLAIN_PAIN_LO_PCT,
        "target_hi_pct": VILLAIN_PAIN_HI_PCT,
        "in_target": in_target,
        "verdict": verdict,
        "fail_codes": fail_codes,          # the only two hard cases
        "flags": flags,
        "blocking": bool(fail_codes),      # FLAG never blocks
        "card_line": "Villain: %s, shown in %d shots"
                     % (name if named else "NONE", len(villain_shots)),
        "source": "FU-U16 villain doctrine (pain target 20-35% of runtime)",
    }

class LengthError(ValueError):
    pass


class RapFloorError(LengthError):
    """A rap style planned less than its rap floor: a loud refusal, never a
    silent "no rap planned"."""


class LexicalFloorError(LengthError):
    """A plan that does not clear the 70 % lexical-completeness floor it is
    judged on: the formula must never emit such a plan (WW-01 item 3)."""


def rap_floor_s(delivered_s):
    """The rap floor in SECONDS: max(8.0, 10% of the delivered seconds).

    NEW ACCEPTANCE RULE. One rule, one number: the plan and the gate both read
    this, so a plan can never carve its rap budget below the gate's floor."""
    return max(RAP_FLOOR_S, RAP_FLOOR_SHARE * float(delivered_s))


def rap_floor_words(style_id, delivered_s=None):
    """The rap floor in WORDS at the style's calibrated rap rate.

    ``ceil(rap_floor_s * rate)`` -- the word floor is derived from the seconds
    floor at the style's own measured rap rate, so the two can never drift."""
    rate = _WF.rates_for(style_id)["rap"]
    secs = RAP_FLOOR_S if delivered_s is None else rap_floor_s(delivered_s)
    return int(math.ceil(secs * rate))


def rap_verse_min_words(style_id):
    """``ceil(RAP_VERSE_MIN_S * the style's rap rate)`` -- 20 words at the R&B
    Flow rap rate of 2.5 words/s. NEW PROPOSED ACCEPTANCE RULE (WW-01)."""
    return int(math.ceil(RAP_VERSE_MIN_S * _WF.rates_for(style_id)["rap"]))


def rap_verse_budget_s(delivered_s):
    """The rap budget the PLAN must reserve for the verses: the larger of the
    total floor and MIN_RAP_VERSES verses at RAP_VERSE_MIN_S each. At D = 88
    that is max(8.8, 16.0) = 16.0 s, so the plan emits the two verses a sheet is
    required to declare. NEW PROPOSED ACCEPTANCE RULE (WW-01)."""
    return max(rap_floor_s(delivered_s), MIN_RAP_VERSES * RAP_VERSE_MIN_S)


def rap_verse_floor_for(style_id):
    """The PER-VERSE rap floor for one style: seconds and words per verse, the
    minimum verse count, and the rate the word floor is derived from.

    NEW PROPOSED ACCEPTANCE RULE (WW-01 item 2): every declared rap verse must
    reach ``RAP_VERSE_MIN_S`` seconds and ``ceil(RAP_VERSE_MIN_S * rap rate)``
    words, and a sheet declaring fewer than ``MIN_RAP_VERSES`` rap verses is
    refused before any spend."""
    rate = _WF.rates_for(style_id)["rap"]
    return {"min_s": RAP_VERSE_MIN_S, "min_words": rap_verse_min_words(style_id),
            "min_verses": MIN_RAP_VERSES, "rate": rate,
            "source": "WW-01 (NEW PROPOSED): every declared rap verse >= 8.0 s "
                      "and >= ceil(8.0 * the style's rap rate) words"}


def rap_reserve_s(delivered_s, spoken_allowance_s):
    """The seconds a rap style keeps OUT of its spoken allowance for the rap
    verses: ``max(rap_floor_s(D), rap_verse_budget_s(D))``, never more than the
    allowance itself (WF1848F-U1 fix 3).

    Where the ordered reservation is larger than the style's WHOLE spoken
    allowance the style cannot fit at that length (D 60: 16.0 s asked of
    13.5 s), so the reservation IS the allowance: the spoken words fall to zero
    and the plan reports the rap seconds it can actually carve. The plan and the
    gate both read this ONE function, so they can never disagree -- before this
    the cap reserved ``rap_floor_s(D)`` while ``rap_s`` was raised to
    ``rap_verse_budget_s(D)``, and spoken plus rap overspent the allowance at
    every length (26.7143 s of 19.8 s at D 88)."""
    ordered = max(rap_floor_s(delivered_s), rap_verse_budget_s(delivered_s))
    return min(ordered, float(spoken_allowance_s))


def spoken_allowance_s(plan):
    """The spoken-style seconds a PLAN was built on: the ad's own spoken target
    applied to its delivered length (the one number ``word_budget`` gives)."""
    D = (plan or {}).get("delivered_s")
    if isinstance(D, bool) or not isinstance(D, (int, float)):
        return None
    try:
        return word_budget(D, (plan or {}).get("spoken_share_pct_requested"))["spoken_s"]
    except (LengthError, TypeError, ValueError):
        return None


def rap_floor_gate(plan, style_id=None):
    """The D1 rap gate: PASS / FAIL / N/A for one plan.

    FAILS whenever a RAP STYLE plans zero rap words, and also when it plans
    fewer than the floor (the per-verse reservation in seconds, and the word
    floor at the style's own rap rate). A style whose deliveries carry no rap
    is not applicable and PASSes. The gate reads the plan, so it can run on the
    plan BEFORE any paid generation.

    WF1848F-U1 fix 3: the seconds floor is ``rap_reserve_s(D, the plan's spoken
    allowance)`` -- the SAME reservation plan() carves, for the same reason and
    from the same one function. At D 88 and above nothing changes (the 16.0 s
    reservation is below the allowance, so it stays 16.0 s); where the plan
    cannot fit the full reservation the gate judges it against what it CAN
    carve instead of refusing a plan the length makes impossible.

    NEW PROPOSED ACCEPTANCE RULE: every threshold here comes from this fix."""
    sid = style_id or (plan or {}).get("style_id")
    D = (plan or {}).get("delivered_s")
    floor_s = rap_verse_budget_s(D) if isinstance(D, (int, float)) \
        and not isinstance(D, bool) else MIN_RAP_VERSES * RAP_VERSE_MIN_S
    allowance = spoken_allowance_s(plan)
    if allowance is not None:
        floor_s = rap_reserve_s(D, allowance)
    if not _rap_style(sid):
        return {"verdict": "PASS", "applicable": False,
                "detail": "style %r does not deliver rap" % (sid,),
                "rap_floor_s": floor_s}
    words = (plan or {}).get("words") or {}
    rap_words = words.get("rap", 0) or 0
    rap_s = (plan or {}).get("rap_s", 0.0) or 0.0
    floor_words = max(rap_floor_words(sid, D),
                      rap_verse_min_words(sid) * MIN_RAP_VERSES)
    if not rap_words:
        verdict, code = "FAIL", "RAP_PLANNED_ZERO_WORDS"
    elif rap_words < floor_words or rap_s + 1e-9 < floor_s:
        verdict, code = "FAIL", "RAP_BELOW_FLOOR"
    else:
        verdict, code = "PASS", "RAP_FLOOR_MET"
    return {
        "verdict": verdict, "applicable": True, "reason_code": code,
        "style_id": sid, "rap_words": rap_words, "rap_s": round(rap_s, 3),
        "rap_floor_s": round(floor_s, 3), "rap_floor_words": floor_words,
        "thresholds_are_new_acceptance_rules": True,
        "detail": ("%s planned %d rap words / %.1f s (floor %d words / %.1f s)"
                   % (sid, rap_words, rap_s, floor_words, floor_s)),
        "source": "WW-01: rap floor + the gate that FAILS on zero rap words",
    }


def assert_rap_floor(plan, style_id=None):
    """Raise RapFloorError unless the rap gate PASSes (or is not applicable).
    The plan builder calls this so a rap style can never ship a no-rap plan."""
    gate = rap_floor_gate(plan, style_id)
    if gate["verdict"] != "PASS":
        raise RapFloorError("%s: %s" % (gate["reason_code"], gate["detail"]))
    return gate


# ---------------------------------------------------------------------------
# WW-01 item 3: THE LEXICAL-COMPLETENESS ASSERTION. The plan the formula emits
# must satisfy the 70 % lexical floor ITSELF, with the sung allocation priced at
# the STYLE's real rate. The shipped formula priced sung words at the generic
# SUNG_WPS (1.07) and the R&B Flow plan emitted 15/2.0 + 23/2.5 + 67/1.9 =
# 51.9632 lexical seconds against the 61.6 owed at D = 88.

def lexical_floor_s(delivered_s):
    """The lexical seconds a delivered length owes: 70 % of D.

    NEW PROPOSED ACCEPTANCE RULE (WW-01 item 3)."""
    return LEXICAL_COVERAGE_MIN * float(delivered_s)


def lexical_seconds(plan, style_id=None):
    """Real lexical seconds of a plan: the sung, spoken and rap word counts at
    the STYLE's own rates (words_fit), never the generic SUNG_WPS."""
    sid = style_id or (plan or {}).get("style_id")
    rates = _WF.rates_for(sid)
    w = (plan or {}).get("words") or {}
    return (w.get("sung", 0) / float(rates["sung"])
            + w.get("spoken", 0) / float(rates["spoken"])
            + w.get("rap", 0) / float(rates["rap"]))


def lexical_gate(plan, style_id=None):
    """PASS / FAIL for one plan against the 70 % lexical floor.

    NEW PROPOSED ACCEPTANCE RULE (WW-01 item 3), derived from the same 0.70 the
    delivered-audio lexical gate uses, re-priced at the plan's own style rates."""
    D = (plan or {}).get("delivered_s")
    owed = lexical_floor_s(D) if isinstance(D, (int, float)) \
        and not isinstance(D, bool) else 0.0
    have = lexical_seconds(plan, style_id)
    ok = have + 1e-9 >= owed
    return {"verdict": "PASS" if ok else "FAIL", "lexical_s": round(have, 4),
            "owed_s": round(owed, 4), "floor_pct": LEXICAL_COVERAGE_MIN,
            "thresholds_are_new_acceptance_rules": True,
            "reason_code": "LEXICAL_FLOOR_MET" if ok else "LEXICAL_FLOOR_SHORT",
            "detail": ("%.4f lexical seconds against the %.4f owed (%.0f%% of %s s)"
                       % (have, owed, LEXICAL_COVERAGE_MIN * 100, D)),
            "source": "WW-01 item 3: the plan must clear the 70 % lexical floor "
                      "at the style's real rates"}


def assert_lexical_floor(plan, style_id=None):
    """Raise LexicalFloorError unless the plan clears the lexical floor."""
    gate = lexical_gate(plan, style_id)
    if gate["verdict"] != "PASS":
        raise LexicalFloorError("%s: %s" % (gate["reason_code"], gate["detail"]))
    return gate


def _bracket(d):
    for edge, b in _BRACKETS:
        if d <= edge:
            return b
    return _BRACKETS[-1][1]


def _spoken_share(spoken_share_pct):
    """The ad's own spoken target (percent) or the 20-25 default midpoint."""
    pct = _SS.SPOKEN_TARGET_PCT if spoken_share_pct is None else spoken_share_pct
    if isinstance(pct, (list, tuple)):
        pct = sum(pct) / len(pct)
    if isinstance(pct, bool) or not isinstance(pct, (int, float)) or not 5 <= pct <= 40:
        raise LengthError("spoken_share_pct must be 5-40 (or a (lo, hi) pair), got %r" % (pct,))
    return pct / 100.0


def word_budget(delivered_s, spoken_share_pct=None, break_s=0.0):
    f = _spoken_share(spoken_share_pct)
    spoken_s = f * delivered_s
    sung_s = max(delivered_s - spoken_s - break_s, 0.0)
    return {"spoken_s": round(spoken_s, 1), "sung_s": round(sung_s, 1),
            "spoken_words": int(round(spoken_s * SPOKEN_WPS)),
            "sung_words": int(round(sung_s * SUNG_WPS))}


def extend_plan(delivered_s):
    """Segments for a song longer than one generation. [] when one take is enough."""
    if delivered_s <= MAX_GEN_S:
        return []
    segs = [{"kind": "base", "duration_s": MAX_GEN_S, "covers_to_s": MAX_GEN_S}]
    covered = MAX_GEN_S
    while covered < delivered_s - 1e-6:
        cont = covered - EXTEND_OVERLAP_S
        new = min(EXTEND_NEW_S, delivered_s - covered)
        covered = covered + new
        # KIE extend-music (KIE docs, suno-api/extend-music, checked 2026-10-08):
        # job model "ai-music-api/extend", input {audio_id, continue_at,
        # model}; model must equal the source take's; 0 < continue_at < source
        # duration. The extend input has NO duration field, so new_s is an
        # EXPECTATION: measure the returned take and re-plan from its real length.
        segs.append({"kind": "extend", "continue_at_s": cont, "new_s": round(new, 1),
                     "covers_to_s": round(covered, 1), "model_must_equal_source": True,
                     "new_s_is_expected_not_requested": True,
                     "request": {"model": "ai-music-api/extend",
                                 "input": {"audio_id": "<previous take id>",
                                           "continue_at": cont, "model": "V6"}}})
    return segs


# ---------------------------------------------------------------------------
# FU-U13: story-arc rule + product-connection target (Trevor order 2026-10-08).
# Story arc: struggle -> what changed -> the product is why -> get the
# product. The product is named and connected inside the lyrics AND on
# screen (cover, title, link) -- never only as an end card. The 10-15% band
# below is a TARGET, never a hard cap: inside is PASS, outside is FLAG with
# the measured seconds and percent, never a blocker by itself.
PRODUCT_TARGET_LO_PCT = 10.0
PRODUCT_TARGET_HI_PCT = 15.0
PRODUCT_TARGET_MID_PCT = 12.5        # planner's aim when nothing measured yet
SHOT_DEFAULT_S = 3.0                 # a tagged shot with no stated duration
ARC_STAGES = ("struggle", "what_changed", "product_is_why", "get_product")
END_CARD_TAGS = ("end_card", "endcard", "cta_card")


def _tagged(obj, tag):
    if not isinstance(obj, dict):
        return False
    v = obj.get(tag)
    if v is True:
        return True
    tags = obj.get("tags") or ()
    if isinstance(tags, str):
        tags = (tags,)
    return tag in tags


def _obj_seconds(obj, fallback):
    for k in ("seconds", "duration_s", "duration"):
        v = obj.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            return float(v)
    words = len(str(obj.get("text", "")).split())
    return words / SUNG_WPS if words else fallback


def plan_product_connection(plan, shots=None, lyric_lines=None):
    """FU-U13 planner: seconds and share of the run connecting story to product.

    Counts lyric lines tagged product (per-line tags from the lyric sheet) plus
    shots tagged product (each shot's own seconds), against the plan's
    delivered runtime. With no tagged material yet, plans the target seconds
    at PRODUCT_TARGET_MID_PCT.

    Returns seconds, percent, a PASS/FLAG verdict against the 10-15% band
    (FLAG is never a blocker), the arc check, and the spoken-word / struggle
    requirements check. Stdlib only; pure; no network, no spend.
    """
    runtime_s = float(plan.get("delivered_s") or plan.get("chosen_length_s") or 0.0)
    if runtime_s <= 0:
        raise LengthError("plan carries no delivered_s/chosen_length_s")
    shots = list(shots or [])
    lines = list(lyric_lines or [])

    shot_s = sum(_obj_seconds(s, SHOT_DEFAULT_S) for s in shots
                 if _tagged(s, "product"))
    line_s = sum(_obj_seconds(l, SHOT_DEFAULT_S) for l in lines
                 if _tagged(l, "product"))
    measured = bool(shots or lines)
    seconds = round(shot_s + line_s, 1) if measured \
        else round(runtime_s * PRODUCT_TARGET_MID_PCT / 100.0, 1)
    percent = round(seconds / runtime_s * 100.0, 1)
    in_band = PRODUCT_TARGET_LO_PCT <= percent <= PRODUCT_TARGET_HI_PCT

    product_shots = [s for s in shots if _tagged(s, "product")] if measured else []
    end_card_only = bool(product_shots) and all(
        any(_tagged(s, t) for t in END_CARD_TAGS) for s in product_shots)
    product_lines = [l for l in lines if _tagged(l, "product")] if measured else []
    on_screen = any(not any(_tagged(s, t) for t in END_CARD_TAGS)
                    for s in product_shots)

    spoken_parts = [l for l in lines if _tagged(l, "spoken")]
    struggle_shots = [s for s in shots
                      if _tagged(s, "struggle") and _tagged(s, "motion")]
    missing = []
    if measured and not spoken_parts:
        missing.append("spoken_word_parts")
    if measured and not struggle_shots:
        missing.append("struggle_motion_shots")
    if end_card_only:
        missing.append("product_on_screen_only_on_end_card")
    if measured and not product_lines:
        missing.append("product_not_in_lyrics")

    verdict = "PASS" if in_band and not missing else "FLAG"
    return {
        "arc": list(ARC_STAGES),
        "arc_rule": ("struggle -> what changed -> the product is why -> "
                     "get the product; the product is named in the lyrics "
                     "and on screen, never only on an end card"),
        "runtime_s": runtime_s,
        "product_seconds": seconds,
        "product_percent": percent,
        "target_lo_pct": PRODUCT_TARGET_LO_PCT,
        "target_hi_pct": PRODUCT_TARGET_HI_PCT,
        "in_target": in_band,
        "verdict": verdict,
        "blocking": False,          # target is a target: FLAG never blocks
        "measured": measured,
        "requirements": {"spoken_word_parts": len(spoken_parts),
                         "struggle_motion_shots": len(struggle_shots),
                         "product_lyric_lines": len(product_lines),
                         "product_on_screen": on_screen or not measured},
        "missing": missing,
        "source": "FU-U13 product-connection target (10-15% of runtime)",
    }


def _rap_style(style_id):
    """True when the style's OWN deliveries include rap (R&B Flow, D18).

    Unknown / absent style -> False (fail closed): an unrecognized style
    never silently earns a rap allowance. One copy of the fact: the
    deliveries come from core/music_styles, never a second list here.
    """
    try:
        return "rap" in _MS.style(style_id)["deliveries"]
    except _MS.MusicStyleError:
        return False


def _sung_style(style_id):
    """True for a KNOWN style that delivers no rap (Soul Ballad, Soul Rise).
    No style or an unknown style -> False: that plan stays byte-identical."""
    if style_id is None:
        return False
    try:
        return "rap" not in _MS.style(style_id)["deliveries"]
    except (_MS.MusicStyleError, TypeError):
        return False

def _fit_rap_style_words(D, spoken_words, sung_words, rap_words, style_id):
    """Size (spoken, sung) so words_fit.preflight passes WITH the rap floor held.

    v2.9.72 (R1). Before this, a rap style's plan kept its rap reservation and
    its generic sung budget, and the two together missed the style's sung-share
    floor at 30/45/60 s: R&B Flow planned sung 53 + rap 40 at 60 s and
    words_fit refused it SHARE_OFF_TARGET (63.5% against 72.9%). The fix sizes
    the sung allocation from the share the gate actually checks, at the
    style's own rates, and never raises a word count. Returns
    (spoken, sung, feasible); feasible False means the reservation and the
    share floor cannot both hold inside this card length.
    """
    r = _WF.rates_for(style_id)
    vocal_s = max(D - _WF.INTRO_OUTRO_S, 0.0)
    f = _WF.style_sung_target_pct(style_id, D) / 100.0
    if not 0.0 < f < 1.0:
        return spoken_words, sung_words, True
    orig_spoken, orig_sung = spoken_words, sung_words
    rap_t = rap_words / float(r["rap"])
    # Spoken yields first: it is the block the style's own rules let the rap
    # verses crowd out, and its words are already capped by the opener/CTA.
    spoken_t = spoken_words / float(r["spoken"])
    room = vocal_s - rap_t
    if room < 0:                                 # nothing left for voice
        return orig_spoken, orig_sung, False
    # share = sung_t / (sung_t + spoken_t + rap_t) >= f
    #   => sung_t >= f/(1-f) * (spoken_t + rap_t)
    k = f / (1.0 - f)
    need_sung_t = k * (spoken_t + rap_t)
    if need_sung_t > room:                       # spoken must give ground
        spoken_t = max(room - need_sung_t, 0.0)
        spoken_words = int(math.floor(spoken_t * r["spoken"] + 1e-9))
        need_sung_t = k * (spoken_words / float(r["spoken"]) + rap_t)
    if need_sung_t > room + 1e-9:
        # Card too short for this style. Leave the v2.9.71 allocation alone:
        # the plan is refused up front and a zeroed opener would change what
        # every other gate sees for no reason.
        return orig_spoken, orig_sung, False
    max_sung_t = room - spoken_words / float(r["spoken"])
    sung_words = min(sung_words,
                     int(math.floor(max_sung_t * r["sung"] + 1e-9)))
    need_words = int(math.ceil(need_sung_t * r["sung"] - 1e-9))
    if sung_words < need_words:
        sung_words = need_words
    return spoken_words, sung_words, True


def infeasible_length(style_id, spoken_share_pct=None):
    """-> None, or the card length at which this style first fits both gates.

    Reads the SAME two rules plan() and words_fit use (the rap reservation and
    the style's sung-share floor), so a refusal names a length that really
    works. Only a rap style can be infeasible: R&B Flow needs 70 s or more.
    """
    if not _rap_style(style_id):
        return None
    L = 20
    while L <= 3600:
        if _rap_style_words_for(style_id, L, spoken_share_pct)[2]:
            return L
        L += 1
    return None


def _rap_style_words_for(style_id, L, spoken_share_pct=None):
    D = L - END_EARLY_S
    wb = word_budget(D, spoken_share_pct, 0.0)
    opener = min(opener_cap_for(D), max(wb["spoken_words"] // 4, 1))
    spoken = min(wb["spoken_words"], opener + OUTRO_MAX_WORDS)
    reserve_s = min(rap_reserve_s(D, wb["spoken_s"]), max(D - _WF.INTRO_OUTRO_S, 0.0))
    rap_words = max(int(math.ceil(reserve_s * _WF.rates_for(style_id)["rap"])),
                    rap_verse_min_words(style_id) * MIN_RAP_VERSES)
    sp, sg, ok = _fit_rap_style_words(D, spoken, wb["sung_words"], rap_words, style_id)
    return sp, sg, ok


def opener_cap_for(D):
    return OPENER_MAX_WORDS_SHORT if D <= 105 else OPENER_MAX_WORDS_LONG

def _fit_style_words(D, spoken_words, sung_words, style_id):
    """Cap (spoken, sung) so words_fit.preflight(D, sung, spoken, style) is ok.

    The ceiling is words_fit's own budget split (_fewer_words_budget's
    arithmetic: delivered minus intro/outro, divided by the style's sung
    target and priced at the style's rates). Spoken keeps its plan count up to
    its share of that budget; sung takes the vocal seconds left. Never raises
    a word count, so a plan that already fits returns unchanged.
    """
    if _WF.preflight(D, sung_words, spoken_words, style=style_id)["outcome"] == "ok":
        return spoken_words, sung_words
    r = _WF.rates_for(style_id)
    vocal_s = max(D - _WF.INTRO_OUTRO_S, 0.0)
    f = _WF.style_sung_target_pct(style_id, D) / 100.0
    spoken = min(spoken_words, int(math.floor(vocal_s * (1.0 - f) * r["spoken"] + 1e-9)))
    sung = min(sung_words, int(math.floor(
        max(vocal_s - spoken / float(r["spoken"]), 0.0) * r["sung"] + 1e-9)))
    return spoken, sung

# ---------------------------------------------------------------------------
# W1-method-song-U3 (Trevor 2026-10-13): THE METHOD'S RUNTIME TARGETS, in the
# ONE length function. Method sections 7.1-7.2 of the Drama-to-Demand method:
# the editorial starting targets and the illustrative time allocation. The
# numbers live in method_runtime.json beside this module, so a method run and a
# non-method run are planned by the same plan() and can never drift apart.
#
# INERT UNTIL WIRED: nothing below runs unless plan(..., method=True) is asked
# for, so every existing caller keeps its byte-identical plan (the golden pins).
# Conflict C2 is answered here -- the opener may carry the backstory NARRATION
# the method allows (section 6), instead of the 3-word cap alone.

METHOD_RUNTIME_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "method_runtime.json")
METHOD_PROFILE_DEFAULT = "story"
_METHOD_RUNTIME = None


class MethodProfileError(LengthError):
    """A pacing profile the method does not define (SPEC B4: story, feed)."""


def method_runtime():
    """The parsed method_runtime.json -- THE method runtime table, read once."""
    global _METHOD_RUNTIME
    if _METHOD_RUNTIME is None:
        with open(METHOD_RUNTIME_PATH, "r", encoding="utf-8") as fh:
            _METHOD_RUNTIME = json.load(fh)
    return _METHOD_RUNTIME


def method_profiles():
    """The pacing profiles (SPEC B4): which clock a purpose runs on."""
    return dict(method_runtime()["profiles"])


def method_profile_rules(profile=METHOD_PROFILE_DEFAULT):
    """One profile's rules. Raises MethodProfileError for anything else."""
    prof = method_profiles()
    if profile not in prof:
        raise MethodProfileError("profile must be one of %s, got %r"
                                 % (sorted(prof), profile))
    return prof[profile]


def method_row(chosen_length_s):
    """The section 7.1 targets and section 7.2 blocks for one chosen length.

    An exact row is copied out as the data file states it. Any other length is
    the linear interpolation between the two nearest rows and is returned marked
    ``origin == "interpolated"`` with the two rows it came from, so a number the
    data file never states is never read as one it did. Below the smallest row
    (30 s) is a LengthError; above the largest (600 s) returns that row marked
    ``origin == "clamped"`` -- the 10-minute targets are the method's longest
    and must not be presented as targets for a longer run.
    """
    doc = method_runtime()
    rows = doc["lengths"]
    L = float(chosen_length_s)
    hit = [r for r in rows if float(r["length_s"]) == L]
    if hit:
        return dict(hit[0])
    below = [r for r in rows if r["length_s"] < L]
    if not below:
        raise LengthError("no method runtime target at or below %s s "
                          "(method_runtime.json starts at %s s)"
                          % (L, rows[0]["length_s"]))
    lo = below[-1]
    above = [r for r in rows if r["length_s"] > L]
    if not above:
        out = dict(lo)
        out["origin"] = "clamped"
        out["note"] = ("%s s is longer than the method's longest row; these are "
                       "the 600 s targets, offered as the closest shape and not "
                       "as the method's targets for this length" % (L,))
        out["length_s"] = L
        return out
    hi = above[0]
    t = (L - lo["length_s"]) / float(hi["length_s"] - lo["length_s"])

    def _mix(key):
        return [lo[key][0] + t * (hi[key][0] - lo[key][0]),
                lo[key][1] + t * (hi[key][1] - lo[key][1])]

    return {"length_s": L, "origin": "interpolated",
            "interpolated_between_s": [lo["length_s"], hi["length_s"]],
            "backstory_s": _mix("backstory_s"),
            "erm_window_s": _mix("erm_window_s"),
            "cta_reserve_s": _mix("cta_reserve_s"),
            "blocks": {k: lo["blocks"][k] + t * (hi["blocks"][k] - lo["blocks"][k])
                       for k in doc["block_order"]}}


def method_anchors(row):
    """The section 7.2 block column turned into ARRIVAL timestamps.

    Each anchor is the end of its block, so it is also the first second of the
    next one: ``hero_shift_s`` is where the solution enters, ``hook_from_s``
    where the earned Solution Signature Hook may start -- the method's own
    "the first hook begins at 0:40, 1:00, 1:20, 1:35, 2:00, and 2:45" -- and
    ``commercial_from_s`` where the closing commercial begins. The ERM apex is
    the midpoint of the section 7.1 window: the method says the apex is placed
    at an explicitly chosen point inside the ERM/pain block, so the block is
    never assumed to be the ERM itself.
    """
    doc = method_runtime()
    ends = {}
    end = 0.0
    for name in doc["block_order"]:
        end += float(row["blocks"][name])
        ends[name] = round(end, 2)
    erm = row["erm_window_s"]
    return {"block_anchors_s": ends,
            "backstory_end_s": ends["backstory_instrumental"],
            "erm_apex_s": round((float(erm[0]) + float(erm[1])) / 2.0, 2),
            "hero_shift_s": ends["solution_introduction_and_hero_shift"],
            "hook_from_s": ends["solution_use_and_first_breakthrough"],
            "commercial_from_s": ends["further_story_and_reprises"],
            "total_s": round(end, 2)}


def method_plan(chosen_length_s, delivered_s, profile=METHOD_PROFILE_DEFAULT):
    """The ``out["method"]`` targets for one run: section 7.1 windows plus the
    section 7.2 arrival anchors (SPEC B4 pacing profiles).

    ``story`` (default) is the method's own table. ``feed`` keeps the method's
    ORDER and compresses only the clock: a 0-3 s attention opener and the first
    sung line by 15 % of the delivered seconds -- the measured BSW timing SPEC
    B4 pins at about 4-5 s at 30 s, 8-9 s at 60 s, 12-13 s at 90 s. Both music
    turns stay required and measured; only the clock differs.
    """
    rules = method_profile_rules(profile)
    row = method_row(chosen_length_s)
    a = method_anchors(row)
    if profile == "feed":
        opener = [float(v) for v in rules["attention_opener_s"]]
        by = round(float(rules["first_sung_pct_of_delivered"]) * float(delivered_s), 2)
        backstory, erm, apex = list(opener), [0.0, by], by
    else:
        backstory = [float(v) for v in row["backstory_s"]]
        erm = [float(v) for v in row["erm_window_s"]]
        apex = a["erm_apex_s"]
    out = {
        "profile": profile,
        "backstory_s": backstory,
        "erm_window_s": erm,
        "cta_reserve_s": [float(v) for v in row["cta_reserve_s"]],
        "erm_apex_s": apex,
        "first_sung_by_s": apex,
        "hero_shift_s": a["hero_shift_s"],
        "hook_from_s": a["hook_from_s"],
        "commercial_from_s": a["commercial_from_s"],
        "block_anchors_s": a["block_anchors_s"],
        "total_s": a["total_s"],
        "origin": row["origin"],
        "note": ("planning targets, not timing laws: the ERM target is an arrival "
                 "timestamp and the closing commercial reserve is already inside "
                 "the runtime"),
        "source": method_runtime()["source"],
    }
    if row.get("interpolated_between_s"):
        out["interpolated_between_s"] = row["interpolated_between_s"]
    if row.get("note"):
        out["row_note"] = row["note"]
    return out


def plan(chosen_length_s, spoken_share_pct=None, style_id=None, rap_floor=True,
         method=False, profile=METHOD_PROFILE_DEFAULT):
    """The full plan for one ad. ``spoken_share_pct`` is the ad's own setting
    (default 20-25 -> 22.5; BSW passes (15, 20)).

    ``rap_floor`` (default True) applies the WWFIX D1 rap reservation. With
    ``rap_floor=False`` a rap style's split is the FU-U2 carve WITHOUT that
    reservation -- rap is whatever the [Intro]/[Outro] caps leave of the
    spoken allowance, rounded, and no rap gate is asserted -- which is exactly
    the split the style held before D1 existed. That reading has ONE caller:
    ``words_fit.style_sung_target_pct`` (the sung-share FLOOR every sheet is
    held to). The D1 rap floor is a separate SHEET floor with its own gate
    (``rap_floor_gate`` / ``song_contract.rap_floor_for``); re-pricing the
    sung-share floor through it would silently WEAKEN the existing floor
    (R&B Flow 148 s: 71.1 -> 68.5), which the golden pins forbid.

    FU-U2: ``style_id`` makes the plan style-aware. Rap styles (deliveries
    include rap, i.e. R&B Flow) split the D15 spoken-STYLE allowance -- the
    same f * delivered seconds every style already honors, because rap counts
    as spoken-style delivery -- into the [Intro]/[Outro] spoken blocks (capped
    exactly as before) plus a rap budget for the verses, at the calibrated
    rap rate from core/words_fit (one copy of the number). The plan then
    returns words {spoken, rap, sung} and a top-level ``rap_s``. No style, an
    unknown style, Soul Ballad and Soul Rise keep the previous output
    BYTE-IDENTICAL -- no rap key is added for them -- except (v2.9.70) that a
    named non-rap style's ``words`` are capped to what words_fit.preflight
    admits at that style's rates (_fit_style_words); no style is untouched.

    ``method`` (default False) adds the Drama-to-Demand runtime targets (method
    sections 7.1-7.2) as ``out["method"]``: the backstory, ERM and closing
    commercial windows, the ERM apex and the Hero Shift / hook / commercial
    arrival anchors, on the pacing profile's clock (``profile``, SPEC B4 --
    ``story`` is the method's own table, ``feed`` compresses the ERM onto the
    measured 15 % of the delivered seconds). A method run's OPENER may carry the
    backstory narration the method allows, up to the backstory window spoken at
    SPOKEN_WPS words; the spoken share band and the rap reservation are
    untouched. Without ``method`` the output is byte-identical to before.
    """
    L = chosen_length_s
    if isinstance(L, bool) or not isinstance(L, (int, float)) or L < 20 or L > 3600:
        raise LengthError("chosen length must be 20-3600 seconds, got %r" % (L,))
    D = L - END_EARLY_S
    b = _bracket(D)
    break_s = b["breaks"] * b["break_s"]
    wb = word_budget(D, spoken_share_pct, break_s)
    # W1-method-song-U3: the method's targets are computed FIRST, because they
    # raise the OPENER cap -- and the opener is what carries the backstory
    # narration. Everything below is the same arithmetic it always was.
    method_block = method_plan(L, D, profile) if method else None
    opener_cap = OPENER_MAX_WORDS_SHORT if D <= 105 else OPENER_MAX_WORDS_LONG
    if method_block is not None:
        # Conflict C2: narration over light instrumental music is allowed
        # (method section 6), so the whole backstory window may be spoken at the
        # measured rate. The spoken share band still binds (spoken_words is
        # still min(wb, opener + cta_cap)) and the rap reservation is untouched.
        opener_cap = int(math.floor(method_block["backstory_s"][1] * SPOKEN_WPS))
    opener = min(opener_cap, max(wb["spoken_words"] // 4, 1))
    cta_cap = max(OUTRO_MAX_WORDS, wb["spoken_words"] - opener)
    if _rap_style(style_id):
        # FU-U2 x 2026-10-09 CTA scaling (train MGB013): a rap style keeps the
        # fixed [Intro]/[Outro] caps so the allowance they leave unspent is the
        # rap budget; the scaled CTA would spend all of it as speech.
        opener = min(opener_cap, max(min(wb["spoken_words"], opener_cap + OUTRO_MAX_WORDS) // 4, 1))
        cta_cap = OUTRO_MAX_WORDS
    spoken_words = min(wb["spoken_words"], opener + cta_cap)
    sung_words = wb["sung_words"]
    planned_share = round(spoken_words / SPOKEN_WPS / D * 100.0, 1)
    rap_words, rap_s = 0, 0.0
    if _rap_style(style_id):
        # WWFIX D1 (2026-10-11) x WW-01 (2026-10-11): THE RAP FLOOR. The spoken
        # blocks may spend no more than (spoken_s - RAP_FLOOR_S) seconds, so the
        # opener and the closing call to action YIELD to the rap verses. Without
        # this, the caps above could spend the whole spoken allowance and the
        # plan would silently report NO RAP (rap_s = 0, rap_words = 0, no
        # ``rap`` key). These floors are NEW PROPOSED ACCEPTANCE RULES; the
        # gates below re-check them.
        rates = _WF.rates_for(style_id)
        rap_rate = rates["rap"]
        # The floor is max(RAP_FLOOR_S, RAP_FLOOR_SHARE * D) -- one rule, read
        # from rap_floor_s() so the plan and the gate can never disagree. The
        # OPENER keeps the cap it always had; it is the CTA (and any other
        # spoken room) that YIELDS, so an existing sheet's spoken intro stays
        # inside the same cap while the rap verses are guaranteed their floor.
        # rap_floor=False keeps the FU-U2 carve verbatim: no cap, rap rounded.
        if rap_floor:
            # WW-01 item 2: the per-verse reservation. The plan must emit the
            # MIN_RAP_VERSES verses a sheet is required to declare, each at
            # RAP_VERSE_MIN_S, so the budget is max(total floor, 16.0 s) at
            # D = 88 -- strictly stronger than the total floor, never a
            # replacement for it.
            # WF1848F-U1 fix 3: the cap must reserve the SAME seconds rap_s is
            # held to below. It reserved only rap_floor_s(D) (8.8 s at D 88)
            # while rap_s was then raised to rap_verse_budget_s(D) (16.0 s), so
            # spoken + rap spent 26.7143 s of a 19.8 s spoken allowance and the
            # words did not add up. At D 60 the ordered 16.0 s two-verse
            # reservation is larger than the style's whole 13.5 s allowance:
            # the reservation is then the allowance (rap_reserve_s), the spoken
            # words fall to zero, and the plan reports the rap seconds it can
            # actually carve instead of 16.0 s inside 13.5 s.
            reserve_s = rap_reserve_s(D, wb["spoken_s"])
            spoken_cap_words = int(max(wb["spoken_s"] - reserve_s, 0.0) * SPOKEN_WPS)
            spoken_words = min(spoken_words, spoken_cap_words)
        rap_s = max(wb["spoken_s"] - spoken_words / SPOKEN_WPS, 0.0)
        if rap_floor:
            rap_s = max(rap_s, reserve_s)
            # ceil(rap_s * rate), and never below the per-verse word floor the
            # gate reads -- the caps above are computed in floats, so this pins
            # the invariant.
            rap_words = max(int(math.ceil(rap_s * rap_rate)),
                            rap_verse_min_words(style_id) * MIN_RAP_VERSES)
            # WW-01 item 3: THE LEXICAL-COMPLETENESS ASSERTION. The plan must
            # clear the 70 % lexical floor itself, so the sung allocation is
            # re-priced at the STYLE's real sung rate (1.9 words/s for R&B Flow)
            # instead of the generic SUNG_WPS -- the shipped formula emitted
            # 51.9632 lexical seconds against the 61.6 owed at D = 88. The
            # generic sung budget stays a FLOOR: more singing is never a fault.
            lex_need_s = (lexical_floor_s(D)
                          - spoken_words / float(rates["spoken"]) - rap_s)
            if lex_need_s > 0:
                sung_words = max(sung_words, int(math.ceil(lex_need_s * rates["sung"])))
        else:
            rap_words = int(round(rap_s * rap_rate))
        # the D15 share counts rap as spoken-style: the plan reaches the
        # requested target by construction, so the caps-bind note never fires.
        planned_share = round((spoken_words / SPOKEN_WPS + rap_s) / D * 100.0, 1)
    infeasible = None
    # rap_floor=False is words_fit's own style_sung_target_pct reading: it must
    # stay the pre-D1 carve (its docstring pins that), and sizing here would
    # recurse into the very target this function is asked to compute.
    if _rap_style(style_id) and rap_floor:
        # v2.9.72 (R1): the rap reservation and the style's sung-share floor are
        # BOTH binding. Size the sung allocation against the share the gate
        # checks; when the card is too short to hold both, say so on the plan
        # with the length that does work, instead of letting stage 3 loop.
        spoken_words, sung_words, fit = _fit_rap_style_words(
            D, spoken_words, sung_words, rap_words, style_id)
        # The opener cap is NOT re-clamped to the spoken count here: a rap
        # style's reservation can leave zero spoken words while the plan still
        # reports the opener the sheet is allowed (v2.9.71 behaviour, and what
        # the shipped sheets rely on).
        planned_share = round((spoken_words / SPOKEN_WPS + rap_s) / D * 100.0, 1)
        if not fit:
            need = infeasible_length(style_id, spoken_share_pct)
            infeasible = {
                "chosen_length_s": L,
                "min_length_s": need,
                "reason_code": "STYLE_TOO_SHORT_FOR_RAP",
                "message": ("%s needs the rap reservation and the sung-share "
                            "floor to both fit; the shortest card that works is "
                            "%s s%s. Choose a longer card or a style without "
                            "rap verses before stage 3."
                            % (style_id, need,
                               "" if need is None else " (%d s selected)" % L)),
            }
    if _sung_style(style_id):
        # v2.9.70: a named non-rap style's budget must pass the gate that
        # judges it (words_fit.preflight, at the style's own rates, + intro/
        # outro). Without this the 60 s Soul Ballad plan (66 words, 65.7 s)
        # was refused WORDS_DO_NOT_FIT by music_director -- an unpassable
        # stage 3. A plan that already fits is untouched.
        spoken_words, sung_words = _fit_style_words(D, spoken_words, sung_words, style_id)
        opener = min(opener, spoken_words)
        planned_share = round(spoken_words / SPOKEN_WPS / D * 100.0, 1)
    words = {"total": spoken_words + sung_words + rap_words,
             "spoken": spoken_words, "sung": sung_words, "opener_max": opener,
             "closing": max(spoken_words - opener, 0)}
    if _rap_style(style_id):
        # WWFIX D1: words.rap is ALWAYS emitted for a rap style, even at 0, so a
        # plan that lost its rap budget is visible instead of silently absent.
        words["rap"] = rap_words
    out = {
        "chosen_length_s": L, "delivered_s": D, "bracket": b["name"],
        "spoken_share_pct_requested": round(_spoken_share(spoken_share_pct) * 100, 1),
        "spoken_share_pct_planned": planned_share,
        "words": words,
        "sections": {"verses": b["verses"], "pre_chorus": b["pre"],
                     "chorus": b["chorus"], "bridge": b["bridge"]},
        "hook_repeats": _SH.hook_count(D),
        "hook_seconds": _SH.hook_times(D),
        "instrumental": {"breaks": b["breaks"], "seconds_each": b["break_s"]},
        "spoken_placement": ("[Intro] opener (%d words max) and [Outro] closing call to "
                             "action; rap verses run anywhere between the vocalise and "
                             "the outro" % opener) if rap_words else
                            ("[Intro] opener (%d words max) and [Outro] closing call to action only; "
                             "never mid-song" % opener),
        "first_sung_by_s": round(D * _SS.FIRST_SUNG_TARGET_PCT / 100.0, 1),
        "extend": extend_plan(D),
        "continuity": ("same model, vocal gender, style text, tempo and key tag on every segment; "
                       "each extend continues %d s before the end of the audio" % EXTEND_OVERLAP_S)
                      if D > MAX_GEN_S else None,
        "source": "Perplexity length formula 2026-10-08, calibrated to measured BSW 58 s passes",
    }
    # FU-U13: the plan carries its product-connection target seconds too.
    out["product_connection"] = plan_product_connection(out)
    # W1-method-song-U3: only a method run carries the method's runtime targets.
    if method_block is not None:
        out["method"] = method_block
    if _rap_style(style_id):
        # WWFIX D1: rap_s is ALWAYS emitted for a rap style, and the plan carries
        # its own rap verdict, so a rap style that planned zero rap words is
        # visible ON THE PLAN, before any spend.
        out["style_id"] = style_id
        # WF1848F-U1 fix 3: the plan REPORTS rap_s to one decimal and must never
        # report MORE seconds than it reserved. round() took 16.4571 UP to 16.5
        # and the spoken + rap total then read 0.0429 s over the spoken
        # allowance. Floor to the tenth so the reported plan always adds up.
        out["rap_s"] = math.floor(rap_s * 10 + 1e-9) / 10.0
        if rap_floor:
            out["rap_floor_s"] = round(rap_floor_s(D), 3)
            out["rap_verse_floor"] = rap_verse_floor_for(style_id)
            out["rap_gate"] = rap_floor_gate(out, style_id)
            out["lexical_s"] = round(lexical_seconds(out, style_id), 4)
            out["lexical_gate"] = lexical_gate(out, style_id)
            assert_rap_floor(out, style_id)
            assert_lexical_floor(out, style_id)
    if infeasible is not None:
        out["infeasible"] = infeasible
        out["words_fit"] = "infeasible"
    if planned_share + 1.0 < out["spoken_share_pct_requested"]:
        out["note"] = ("spoken block caps bind: set this ad's spoken target to %.1f%%"
                       % planned_share)
    return out

# ---------------------------------------------------------------------------
# U15h: cross-check against the class table (design 6; never a second formula).

def class_check(chosen_length_s):
    """This module's plan equals the class row for L. [] when they agree.

    Cross-check only -- ``plan()`` stays THE plan; the class table is the
    shared reader (``prompt_templates.length_class``). Returns the reasons
    naming each drifted field, so a table that describes a different song
    than the code computes can never be read silently.
    """
    try:
        from prompt_templates import prompt_templates as _PT
    except ImportError:                        # template layer not installed
        return []
    L = int(chosen_length_s)
    try:
        row = _PT.length_class(L)
    except _PT.PromptTemplateError as e:
        return ["length_class(%d): %s" % (L, e)]
    p = plan(L)
    ext = p.get("extend") or []
    mine = {"delivered_s": L - END_EARLY_S, "bracket": p["bracket"],
            "hooks": p["hook_repeats"],
            "song_words": {k: p["words"][k] for k in
                           ("total", "spoken", "sung", "opener_max")},
            "sections": dict(p["sections"]),
            "instrumental_breaks": {"count": p["instrumental"]["breaks"],
                                    "seconds_each": p["instrumental"]["seconds_each"]},
            "spoken_share_planned_pct": p["spoken_share_pct_planned"],
            "suno_generations": ("1 base" if not ext
                                 else "1 base + %d extends" % len(ext))}
    return ["%s class=%r plan=%r" % (f, row.get(f), v)
            for f, v in sorted(mine.items()) if row.get(f) != v]


def selfcheck():
    """WW-01's own numbers, asserted: run ``python3 length_formula.py --selfcheck``.

    The plan must reserve the two verses and clear the 70 % lexical floor, and
    the non-rap control must stay byte-identical with no ``rap`` key (WW-01).
    """
    p = plan(90, style_id="rnb-flow")          # D_plan = 88
    assert p["delivered_s"] == 88, p["delivered_s"]
    assert p["words"]["rap"] >= 40, p["words"]         # 2 verses x 20 words
    assert p["rap_s"] + 1e-9 >= 16.0, p["rap_s"]       # 2 verses x 8.0 s
    assert p["lexical_gate"]["verdict"] == "PASS", p["lexical_gate"]
    assert p["lexical_s"] + 1e-9 >= 0.70 * 88, p["lexical_s"]
    assert p["rap_gate"]["verdict"] == "PASS", p["rap_gate"]
    control = plan(90, style_id="soul-ballad")         # the non-rap control
    assert "rap" not in control["words"] and "rap_s" not in control, control["words"]
    assert control == plan(90, style_id="soul-ballad")
    return {"rnb-flow": {"rap_s": p["rap_s"], "rap_words": p["words"]["rap"],
                         "lexical_s": p["lexical_s"], "owed_s": p["lexical_gate"]["owed_s"]},
            "soul-ballad": "deterministic, no rap key", "ok": True}


if __name__ == "__main__":  # python3 length_formula.py <chosen_s> | --selfcheck
    import json
    if len(sys.argv) > 1 and sys.argv[1] == "--selfcheck":
        print(json.dumps(selfcheck(), indent=2))
    else:
        print(json.dumps(plan(float(sys.argv[1])), indent=2))
