#!/usr/bin/env python3
"""G9 words-fit suite (unit W-G-009).

Proves, stdlib only and with zero paid calls:
  1. LeAnne Dolce's ~220-word script at 90 s with 55% sung is flagged
     infeasible with the three options and their numbers (review G7).
  2. The reference sheet (~65 words) at 300 s passes (review G7).
  3. Suno duration always carries >= 15% headroom over the plan.
  4. The check runs BEFORE spend: music_director.build_generate_request
     refuses an infeasible sheet and never builds a payload.
  5. Malformed input raises (caller bug); a feasible plan never does.
  6. One constants module: the band comes from core/spoken_share.

Exit 0 = all pass, 1 = failures, 2 = tooling failure.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

# Judge the SOURCE on disk, never a stale __pycache__.
_CACHE = os.path.join(HERE, "__pycache__")
if os.path.isdir(_CACHE):
    for _name in os.listdir(_CACHE):
        if _name.endswith(".pyc"):
            try:
                os.remove(os.path.join(_CACHE, _name))
            except OSError:
                pass

import words_fit as W                      # noqa: E402
import spoken_share as SS                  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# ---- fixtures -------------------------------------------------------------

# LeAnne Dolce: ~220 lyric words, 90 s card, 55% sung (review G7 / order 1150).
# Split 55/45 of the WORDS (worst case for a ballad: the slow sung rate eats
# the clock) -> 121 sung, 99 spoken.
LEANNE_SUNG, LEANNE_SPOKEN = 121, 99

# Reference sheet: the measured prototype shape at 300 s. Word mix chosen so
# the implied sung share of VOICE time lands on the default 77.5% target
# (sung_w/spoken_w ~= 1.86 at Soul Ballad rates).
REF_SUNG, REF_SPOKEN = 56, 30


def test_leanne_90s_infeasible_with_three_options():
    r = W.preflight(90, LEANNE_SUNG, LEANNE_SPOKEN,
                    sung_target_pct=55.0, style="Soul Ballad")
    check("LeAnne 90s is waiting (not ok)",
          r["outcome"] == "waiting", r.get("outcome"))
    check("LeAnne reason is WORDS_DO_NOT_FIT",
          r["reason_code"] == "WORDS_DO_NOT_FIT", r.get("reason_code"))
    # Calm spoken alone: 220 / 1.85 ~= 119s — cannot fit 90s even fully spoken.
    spoken_only = 220 / 1.85
    check("sanity: 220 words fully spoken needs ~119s",
          spoken_only > 90, "%.1f" % spoken_only)
    opts = r.get("options") or {}
    check("LeAnne carries three options",
          set(opts) == {"longer_ad", "lower_sung_target", "fewer_words"},
          sorted(opts))
    # longer_ad names a card length that fits the plan.
    longer = opts.get("longer_ad") or {}
    check("longer_ad offers a bigger card",
          longer.get("length_s", 0) > 90 and longer.get("length_s") in W.CARD_LENGTHS_S,
          repr(longer))
    check("longer_ad length >= plan",
          longer.get("length_s", 0) >= r["plan_s"], repr(longer))
    # lower_sung_target names the number, or explains why lowering cannot help.
    lower = opts.get("lower_sung_target") or {}
    check("lower_sung_target carries a number or a cannot-help detail",
          (isinstance(lower.get("sung_target_pct"), float)
           and 0 < lower["sung_target_pct"] <= 100)
          or (lower.get("sung_target_pct") is None
              and "cannot help" in lower.get("detail", "")),
          repr(lower))
    # fewer_words names the budget and the cut.
    fewer = opts.get("fewer_words") or {}
    check("fewer_words carries max_total_words",
          isinstance(fewer.get("max_total_words"), float)
          and fewer["max_total_words"] < 220,
          repr(fewer))
    check("fewer_words carries cut_words > 0",
          fewer.get("cut_words", 0) > 0, repr(fewer))
    check("every option has a human detail",
          all(isinstance(v.get("detail"), str) and v["detail"]
              for v in opts.values()), repr(opts))


def test_reference_300s_passes():
    r = W.preflight(300, REF_SUNG, REF_SPOKEN, style="Soul Ballad")
    check("reference 300s is ok", r["outcome"] == "ok",
          r.get("reason_code") or r.get("detail"))
    check("reference reason WORDS_FIT_OK",
          r["reason_code"] == "WORDS_FIT_OK", r.get("reason_code"))
    check("reference plan under 300", r["plan_s"] <= 300, r["plan_s"])


def test_suno_duration_headroom():
    for plan in (10.0, 58.0, 119.0, 300.0):
        d = W.suno_duration_s(plan)
        check("headroom >= 15%% on plan %g" % plan,
              d >= plan * 1.15 - 1e-9, "%s vs %s" % (d, plan * 1.15))
    check("max_suno_duration is an int >= plan*1.15",
          isinstance(W.max_suno_duration(58.0), int)
          and W.max_suno_duration(58.0) >= 58.0 * 1.15)
    try:
        W.suno_duration_s(58.0, headroom=0.05)
        check("headroom below 15% raises", False)
    except W.WordsFitError as e:
        check("headroom below 15% raises", e.code == "BAD_INPUT", e.code)


def test_band_comes_from_spoken_share():
    check("BAND_PTS is spoken_share.ACCEPT_PTS", W.BAND_PTS == SS.ACCEPT_PTS)
    check("default sung target is spoken_share.SUNG_TARGET_PCT",
          W.DEFAULT_SUNG_TARGET_PCT == SS.SUNG_TARGET_PCT)
    # Mix whose implied share is within 5 points of the 77.5% default.
    r = W.preflight(300, 48, 20, style="Soul Ballad")
    check("in-band share at 300s is ok",
          r["outcome"] == "ok", r.get("detail"))
    check("in-band share within ACCEPT_PTS",
          r["gap_pts"] <= SS.ACCEPT_PTS, r.get("gap_pts"))


def test_share_off_target_offers_lower_target():
    # Words fit the card, but the mix's sung share is >10 points SHORT of the
    # target (FU-RNBFLOW-SONG: the target is a floor; over it is never a miss).
    r = W.preflight(300, 5, 200, sung_target_pct=55.0, style="Soul Ballad")
    check("word-mix share miss is waiting",
          r["outcome"] == "waiting", r.get("detail"))
    check("share miss reason SHARE_OFF_TARGET",
          r["reason_code"] == "SHARE_OFF_TARGET", r.get("reason_code"))
    lower = (r.get("options") or {}).get("lower_sung_target") or {}
    check("share miss still offers lower_sung_target",
          isinstance(lower.get("sung_target_pct"), float), repr(lower))


def test_parse_sheet_and_preflight_sheet():
    sheet = "\n".join([
        "[Spoken - lead, plain natural speech over the music]",
        "Wake up happy sis",
        "[Sung - lead, soul ballad lead, long held notes]",
        "Who is holding me?",
        "The cape was never yours",
        "[Instrumental]",
        "this line is not lyrics",
        "[Rap - lead, smooth flow]",
        "rise and shine",
    ])
    sung, spoken, rap = W.parse_sheet_words(sheet)
    check("parse spoken opener = 4 words", spoken == 4, spoken)
    check("parse sung body = 9 words", sung == 9, sung)
    check("parse rap = 3 words", rap == 3, rap)
    check("instrumental line adds nothing", sung + spoken + rap == 16,
          sung + spoken + rap)
    r = W.preflight_sheet(300, sheet, sung_target_pct=55.0)
    check("preflight_sheet runs", r["outcome"] in ("ok", "waiting"),
          r.get("reason_code"))


def test_music_director_refuses_before_payload():
    """G9 wires into build_generate_request: infeasible -> no payload."""
    import music_director as MD
    sheet = "[Sung - lead, ballad]\n" + ("word " * 200).strip()
    try:
        MD.build_generate_request(sheet, "soul ballad style", "t",
                                  length_s=90)
        check("build_generate_request refuses 200-word 90s sheet", False)
    except W.WordsFitError as e:
        check("build_generate_request refuses 200-word 90s sheet",
              e.code in ("WORDS_DO_NOT_FIT", "SHARE_OFF_TARGET"), e.code)
    except Exception as e:  # noqa: BLE001
        check("build_generate_request refuses (non-WordsFit)",
              False, "%s: %s" % (type(e).__name__, e))
    # Feasible mixed sheet at 60s: velvet skips the recipe guard so this
    # proves the G9 duration stamp alone. 20 sung / 11 spoken at Soul
    # Ballad rates -> sung share ~77.5% of voice time (band-pass).
    spoken_line = "short open words for this brand right now"  # 9 words
    sung_block = "hook line here now " * 5                     # 20 words
    short = ("[Spoken - lead, plain]\n" + spoken_line.strip()
             + "\n[Sung - lead, ballad]\n" + sung_block.strip()
             + "\n[Spoken - lead, plain]\nok then my friend")   # +3 -> 12
    sung, spoken, rap = W.parse_sheet_words(short)
    check("MD fixture is 20 sung / 12 spoken",
          (sung, spoken) == (20, 12), (sung, spoken))
    r = W.preflight(60, sung, spoken, style="Soul Ballad")
    check("MD fixture passes words_fit",
          r["outcome"] == "ok", r.get("detail"))
    req = MD.build_generate_request(short, "soul ballad style", "t",
                                    length_s=60, style_id="velvet_voiceover")
    dur = req.get("input", {}).get("duration")
    plan = W.planned_seconds(20, 12, 0.0, W.INTRO_OUTRO_S, W.rates_for("Soul Ballad"))
    check("feasible request carries duration with >=15% headroom",
          isinstance(dur, int) and dur >= plan * 1.15 - 1e-6,
          "%s vs plan %s" % (dur, plan))
    check("duration is plan*1.15 ceil", dur == W.max_suno_duration(plan),
          "%s vs %s" % (dur, W.max_suno_duration(plan)))
    # Caller-supplied duration is never overwritten.
    req2 = MD.build_generate_request(short, "soul ballad style", "t",
                                     length_s=60, duration=72,
                                     style_id="velvet_voiceover")
    check("caller duration wins",
          req2.get("input", {}).get("duration") == 72,
          repr(req2.get("input", {}).get("duration")))


def test_bad_input_raises():
    for args in ((None, 10, 0), (90, -1, 0), (90, 10, None), (0, 10, 0)):
        try:
            W.preflight(*args)
            check("preflight raises on %r" % (args,), False)
        except W.WordsFitError:
            check("preflight raises on %r" % (args,), True)
    try:
        W.preflight(90, 10, 10, sung_target_pct=0)
        check("target 0 raises", False)
    except W.WordsFitError:
        check("target 0 raises", True)
    try:
        W.planned_seconds(10, 10, rates={"sung": 1.0, "spoken": 0.0, "rap": 1.0})
        check("zero spoken rate raises", False)
    except W.WordsFitError:
        check("zero spoken rate raises", True)


def main():
    test_leanne_90s_infeasible_with_three_options()
    test_reference_300s_passes()
    test_suno_duration_headroom()
    test_band_comes_from_spoken_share()
    test_share_off_target_offers_lower_target()
    test_parse_sheet_and_preflight_sheet()
    test_music_director_refuses_before_payload()
    test_bad_input_raises()
    print()
    if FAILS:
        print("FAILED: %d" % len(FAILS))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
