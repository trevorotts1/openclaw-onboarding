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

import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import sung_hook as _SH      # noqa: E402
import spoken_share as _SS   # noqa: E402

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


def plan(chosen_length_s, spoken_share_pct=None):
    """The full plan for one ad. ``spoken_share_pct`` is the ad's own setting
    (default 20-25 -> 22.5; BSW passes (15, 20))."""
    L = chosen_length_s
    if isinstance(L, bool) or not isinstance(L, (int, float)) or L < 20 or L > 3600:
        raise LengthError("chosen length must be 20-3600 seconds, got %r" % (L,))
    D = L - END_EARLY_S
    b = _bracket(D)
    break_s = b["breaks"] * b["break_s"]
    wb = word_budget(D, spoken_share_pct, break_s)
    opener_cap = OPENER_MAX_WORDS_SHORT if D <= 105 else OPENER_MAX_WORDS_LONG
    opener = min(opener_cap, max(wb["spoken_words"] // 4, 1))
    cta_cap = max(OUTRO_MAX_WORDS, wb["spoken_words"] - opener)
    spoken_words = min(wb["spoken_words"], opener + cta_cap)
    planned_share = round(spoken_words / SPOKEN_WPS / D * 100.0, 1)
    out = {
        "chosen_length_s": L, "delivered_s": D, "bracket": b["name"],
        "spoken_share_pct_requested": round(_spoken_share(spoken_share_pct) * 100, 1),
        "spoken_share_pct_planned": planned_share,
        "words": {"total": spoken_words + wb["sung_words"], "spoken": spoken_words,
                  "sung": wb["sung_words"], "opener_max": opener,
                  "closing": spoken_words - opener},
        "sections": {"verses": b["verses"], "pre_chorus": b["pre"],
                     "chorus": b["chorus"], "bridge": b["bridge"]},
        "hook_repeats": _SH.hook_count(D),
        "hook_seconds": _SH.hook_times(D),
        "instrumental": {"breaks": b["breaks"], "seconds_each": b["break_s"]},
        "spoken_placement": "[Intro] opener (%d words max) and [Outro] closing call to action only; "
                            "never mid-song" % opener,
        "first_sung_by_s": round(D * _SS.FIRST_SUNG_TARGET_PCT / 100.0, 1),
        "extend": extend_plan(D),
        "continuity": ("same model, vocal gender, style text, tempo and key tag on every segment; "
                       "each extend continues %d s before the end of the audio" % EXTEND_OVERLAP_S)
                      if D > MAX_GEN_S else None,
        "source": "Perplexity length formula 2026-10-08, calibrated to measured BSW 58 s passes",
    }
    # FU-U13: the plan carries its product-connection target seconds too.
    out["product_connection"] = plan_product_connection(out)
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


if __name__ == "__main__":  # python3 length_formula.py <chosen_s>
    import json
    print(json.dumps(plan(float(sys.argv[1])), indent=2))
