#!/usr/bin/env python3
"""words_fit.py — G9: words-and-time feasibility before any spend.

Owner order (2026-10-08 11:50, Part G, G9), verbatim:
  "before spending, check the words fit the length at measured delivery
   speed (~220 words cannot fit 90 s even fully spoken); if not, show
   options (longer ad / lower sung target / fewer words); give the Suno
   duration >= 15% headroom."

Review item G7 (Opus audio review) done-when:
  * LeAnne Dolce's ~220-word script at 90 s with 55% sung is flagged
    infeasible with the three options and their numbers;
  * the reference sheet (~65 words) at 300 s passes.

Measured delivery rates (review, section on words-and-time):
  sung Soul Ballad 0.4-1.3 w/s; sung R&B hooks ~1.9 w/s;
  spoken 1.85 (calm ballad) to 2.75 w/s; O3 sung-tagged words 1.57 w/s.
Defaults are the calm Soul Ballad midpoints — the fail-closed direction
for a ballad is "too slow to fit", never "promised to fit".

stdlib only: no network, no provider, no spend, no media file, no absolute
operator path. The check is pure arithmetic on word counts.

Run: python3 core/words_fit/test_words_fit_g9.py
"""
from __future__ import annotations

from math import ceil, isfinite

try:
    import music_styles as _MS                      # core/ on sys.path
    import music_styles.music_styles as _MSM        # the submodule: the LENGTHS table
    import spoken_share as _SS
except ImportError:                                 # imported as core.*
    from .. import music_styles as _MS
    from ..music_styles import music_styles as _MSM
    from .. import spoken_share as _SS

TOOL_NAME = "words_fit"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.words-fit/v1"
SOURCE = ("Owner order 2026-10-08 11:50 (Part G, G9); review G7 measured "
          "delivery rates; Trevor's 5/10 band from core/spoken_share.")

# ---- measured delivery rates (words per second) ---------------------------
# Calm Soul Ballad defaults (review). R&B Flow hooks measured ~1.9 sung.
# Rap: the One-Check calibration (plan A3, 2026-10-08) -- 278 rapped plus
# spoken words over about 112.6 s of non-sung voice = about 2.47 w/s, a
# LOWER bound (the non-sung time also holds instrumental gaps); 2.5 is that
# calibration rounded up, never below it.
DEFAULT_RATES = {"sung": 1.0, "spoken": 1.85, "rap": 2.0}
#: FU-U2: keyed by music_styles STYLE ID (never the display label), so the
#: card, the plan and the gate all name the same style. Rates for any style
#: not listed here are the calm ballad defaults (fail closed: "too slow to
#: fit", never "promised to fit").
STYLE_RATES = {
    "soul-ballad": {"sung": 1.0, "spoken": 1.85, "rap": 2.0},
    "rnb-flow": {"sung": 1.9, "spoken": 2.0, "rap": 2.5},
    "soul-rise": {"sung": 1.2, "spoken": 1.85, "rap": 2.0},
}

#: Music-only intro + outro budgeted into the plan (seconds).
INTRO_OUTRO_S = 8.0

#: Suno `duration` must be planned time + at least this share (G9).
HEADROOM = 0.15

#: Card lengths (choice-card-spec 3.1), seconds, ascending. FU-U2: the ONE
#: copy is music_styles.OFFERED_LENGTHS_S (the 2-minute 120 s entry included);
#: this name only re-exports it so no second list can drift.
CARD_LENGTHS_S = tuple(_MSM.OFFERED_LENGTHS_S)

#: The 5-point accept band (spoken_share ACCEPT_PTS); never a second 5 here.
BAND_PTS = _SS.ACCEPT_PTS

#: Default sung target: share of VOICE time, from the one constants module.
DEFAULT_SUNG_TARGET_PCT = _SS.SUNG_TARGET_PCT   # 77.5


class WordsFitError(ValueError):
    """Malformed input -- a caller bug, never a domain verdict."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _num(v, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)) \
            or not isfinite(float(v)) or float(v) < 0:
        raise WordsFitError("BAD_INPUT", "%s must be a finite number >= 0, got %r"
                            % (name, v))
    return float(v)


def rates_for(style=None):
    """Delivery rates for a music style; unknown/None -> Soul Ballad.

    ``style`` may be a style id ("rnb-flow"), a display label ("R&B Flow") or
    a card option record -- one normalizer (core/music_styles.style) decides,
    so no caller can pass a spelling this module does not know.
    """
    try:
        sid = _MS.style(style)["style_id"]
    except (_MS.MusicStyleError, TypeError):
        return dict(DEFAULT_RATES)
    return dict(STYLE_RATES.get(sid, DEFAULT_RATES))


def planned_seconds(sung_words, spoken_words, rap_words=0.0,
                    intro_outro_s=INTRO_OUTRO_S, rates=None):
    """Planned vocal seconds = sum(words / rate) + intro/outro.

    ``rates`` is a dict with positive ``sung``/``spoken``/``rap`` words-per-
    second. Word counts may be zero; rates may not.
    """
    r = dict(DEFAULT_RATES if rates is None else rates)
    for k in ("sung", "spoken", "rap"):
        if k not in r:
            raise WordsFitError("BAD_INPUT", "rates missing %r" % k)
        rate = _num(r[k], "rates[%s]" % k)
        if rate <= 0:
            raise WordsFitError("BAD_INPUT", "rates[%s] must be > 0" % k)
    sw = _num(sung_words, "sung_words")
    kw = _num(spoken_words, "spoken_words")
    rw = _num(rap_words, "rap_words")
    io = _num(intro_outro_s, "intro_outro_s")
    vocal = sw / r["sung"] + kw / r["spoken"] + rw / r["rap"]
    return vocal + io


def sung_share_of_voice(sung_words, spoken_words, rap_words=0.0, rates=None):
    """Sung share of VOICE time the word mix implies at these rates.

    Rap is spoken-style delivery (spoken_share), so it counts in the
    denominator, never the numerator.
    """
    r = dict(DEFAULT_RATES if rates is None else rates)
    sw = _num(sung_words, "sung_words")
    kw = _num(spoken_words, "spoken_words")
    rw = _num(rap_words, "rap_words")
    sung_t = sw / r["sung"]
    spoken_t = kw / r["spoken"] + rw / r["rap"]
    voice = sung_t + spoken_t
    if voice <= 0:
        raise WordsFitError("BAD_INPUT", "no vocal words: sung share undefined")
    return sung_t / voice * 100.0


def suno_duration_s(plan_s, headroom=HEADROOM):
    """Suno `duration` = planned seconds * (1 + headroom), >= 15% by law."""
    p = _num(plan_s, "plan_s")
    h = _num(headroom, "headroom")
    if h < HEADROOM:
        raise WordsFitError("BAD_INPUT",
                            "headroom must be >= %.0f%% (G9), got %g%%"
                            % (HEADROOM * 100, h * 100))
    return p * (1.0 + h)


def _next_card_length(seconds):
    """Smallest offered card length that is >= ``seconds`` (or the largest)."""
    for L in CARD_LENGTHS_S:
        if seconds <= L:
            return L
    return CARD_LENGTHS_S[-1]


def _fewer_words_budget(chosen_length_s, sung_target_pct, rates,
                        intro_outro_s):
    """Max total words that fit at the carded length keeping the sung share.

    ``sung_target_pct`` is sung share of VOICE time (0-100). Vocal budget =
    length - intro/outro. Words are split by that share and each rate.
    """
    vocal_budget = chosen_length_s - intro_outro_s
    if vocal_budget <= 0:
        return 0.0
    f = max(0.0, min(1.0, sung_target_pct / 100.0))
    sung_t = vocal_budget * f
    spoken_t = vocal_budget * (1.0 - f)
    return sung_t * rates["sung"] + spoken_t * rates["spoken"]


def _max_sung_share_that_fits(total_words, chosen_length_s, rates,
                              intro_outro_s):
    """Highest sung share of VOICE time at which ``total_words`` still fit.

    Returns a percent in [0, 100], or None when even an all-spoken sheet
    cannot fit (lowering the sung target cannot help; only a longer card or
    fewer words can).
    """
    vocal_budget = chosen_length_s - intro_outro_s
    if vocal_budget <= 0:
        return None
    need = total_words / vocal_budget   # words per vocal second required
    rs, rp = rates["sung"], rates["spoken"]
    if need >= rp:
        return None                     # all-spoken is already too slow
    # need = f*rs + (1-f)*rp  =>  f = (rp - need) / (rp - rs)
    f = (rp - need) / (rp - rs)
    return max(0.0, min(1.0, f)) * 100.0


def preflight(chosen_length_s, sung_words, spoken_words, rap_words=0.0,
              sung_target_pct=None, style=None, rates=None,
              intro_outro_s=INTRO_OUTRO_S):
    """Feasibility of the word mix at the carded length. Never spends.

    Returns a dict:
      outcome: "ok" | "waiting"
      reason_code: WORDS_FIT_OK | WORDS_DO_NOT_FIT | SHARE_OFF_TARGET
      plan_s, length_s, sung_share_pct, sung_target_pct, gap_pts,
      suno_duration_s, rates, intro_outro_s
      options: (only when waiting) longer_ad / lower_sung_target /
               fewer_words, each with the number that makes it work.

    "waiting" means show the person the options BEFORE spending; it never
    cancels the run and never dispatches. Malformed input raises.
    """
    L = _num(chosen_length_s, "chosen_length_s")
    if L <= 0:
        raise WordsFitError("BAD_INPUT", "chosen_length_s must be > 0")
    target = (DEFAULT_SUNG_TARGET_PCT if sung_target_pct is None
              else _num(sung_target_pct, "sung_target_pct"))
    if not 0.0 < target <= 100.0:
        raise WordsFitError("BAD_INPUT",
                            "sung_target_pct must be in (0, 100], got %r"
                            % (sung_target_pct,))
    r = rates_for(style) if rates is None else dict(rates)
    io = _num(intro_outro_s, "intro_outro_s")

    plan_s = planned_seconds(sung_words, spoken_words, rap_words, io, r)
    share = sung_share_of_voice(sung_words, spoken_words, rap_words, r)
    gap_pts = round(abs(share - target), 6)
    dur = suno_duration_s(plan_s)

    base = {
        "length_s": L, "plan_s": round(plan_s, 3),
        "sung_share_pct": round(share, 3), "sung_target_pct": target,
        "gap_pts": gap_pts, "suno_duration_s": round(dur, 3),
        "rates": r, "intro_outro_s": io,
        "sung_words": _num(sung_words, "sung_words"),
        "spoken_words": _num(spoken_words, "spoken_words"),
        "rap_words": _num(rap_words, "rap_words"),
    }

    too_long = plan_s > L + 1e-6
    share_off = gap_pts > BAND_PTS

    if not too_long and not share_off:
        out = dict(base, outcome="ok", reason_code="WORDS_FIT_OK",
                   detail=("plan %.1fs fits the %gs card and the sung share "
                           "%.1f%% is within %d points of target %.1f%%"
                           % (plan_s, L, share, BAND_PTS, target)))
        return out

    # Three options, each with its number (order 1150, review G7).
    total_w = base["sung_words"] + base["spoken_words"] + base["rap_words"]
    min_length_s = plan_s if plan_s > L else L
    longer = _next_card_length(min_length_s)
    natural = round(share, 3)
    budget = _fewer_words_budget(L, target, r, io)
    cut = round(max(0.0, total_w - budget), 1)
    max_f = _max_sung_share_that_fits(total_w, L, r, io)

    reasons = []
    if too_long:
        reasons.append("plan %.1fs exceeds the %gs card" % (plan_s, L))
    if share_off:
        reasons.append("sung share %.1f%% is %g points from target %.1f%%"
                       % (share, gap_pts, target))

    if max_f is None:
        lower_detail = (
            "even an all-spoken sheet of %g words needs more than the %gs "
            "card; lowering the sung target cannot help — take a longer card "
            "or cut words" % (total_w, L))
        lower_num = None
    elif max_f < target:
        lower_detail = (
            "at the %gs card this word mix only fits if the sung target is "
            "at most %.1f%% of voice time (was %.1f%%)"
            % (L, max_f, target))
        lower_num = round(max_f, 3)
    else:
        lower_detail = (
            "the word mix already sings %.1f%% of voice time; accept that as "
            "the target (band still applies)" % natural)
        lower_num = natural

    options = {
        "longer_ad": {
            "length_s": longer,
            "detail": ("a %gs card fits this word mix (plan %.1fs)"
                       % (longer, plan_s)),
        },
        "lower_sung_target": {
            "sung_target_pct": lower_num,
            "detail": lower_detail,
        },
        "fewer_words": {
            "max_total_words": round(budget, 1),
            "cut_words": cut,
            "detail": ("keep the %gs card and the %.1f%% sung target: at "
                       "most %.1f lyric words (cut about %.1f)"
                       % (L, target, budget, cut)),
        },
    }

    return dict(base, outcome="waiting",
                reason_code=("WORDS_DO_NOT_FIT" if too_long
                             else "SHARE_OFF_TARGET"),
                options=options,
                detail="; ".join(reasons) + " — choose before spending")


def parse_sheet_words(sheet_text):
    """Count lyric words per delivery from a tagged Suno sheet.

    FU-U1: THE grammar lives in suno_recipe.parse_lyrics/parse_tag; this is a
    thin delegate so the words-fit gate and the recipe gate measure the SAME
    sheet. Both bracket dialects parse ([Name (sung|spoken|rap): note] and the
    G2 [Sung|Spoken|Rap - ...] form). ``[Instrumental]`` contributes nothing.
    A lyric line under a tag that names no delivery raises RecipeError
    (UNTAGGED_LYRIC_LINES) -- it is never dropped quietly. Returns
    (sung, spoken, rap) integer word counts.
    """
    if not isinstance(sheet_text, str) or not sheet_text.strip():
        raise WordsFitError("BAD_INPUT", "sheet_text must be a non-empty string")
    from suno_recipe.suno_recipe import parse_lyrics, sheet_words
    sheet = parse_lyrics(sheet_text)
    return (sheet_words(sheet, "sung"), sheet_words(sheet, "spoken"),
            sheet_words(sheet, "rap"))


def preflight_sheet(chosen_length_s, sheet_text, sung_target_pct=None,
                    style=None, rates=None, intro_outro_s=INTRO_OUTRO_S):
    """``preflight`` over a tagged lyric sheet (the caller's usual entry)."""
    sung, spoken, rap = parse_sheet_words(sheet_text)
    return preflight(chosen_length_s, sung, spoken, rap,
                     sung_target_pct=sung_target_pct, style=style,
                     rates=rates, intro_outro_s=intro_outro_s)


def max_suno_duration(plan_s):
    """The number a generate payload should carry: plan + 15% (ceil to 1s)."""
    return int(ceil(suno_duration_s(plan_s)))
