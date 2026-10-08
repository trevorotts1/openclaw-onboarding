#!/usr/bin/env python3
"""Spoken share on the choice card and in the docs (owner D15 retarget,
retargeted by SPK001).

Source: Decision log 37 (D15 retarget) 2026-10-07; plan 6.7; SPK001
(Trevor, 2026-10-08: "Okay, let's go to your recommendation that cut it to
about 20-25%."): *spoken target 22.5% of the runtime (20-25%), singing target
77.5% of VOICE time (75-80%), judged by Trevor's band (within 5 accept, 5-10
flag, past 10 redo), same for every length and every music style (rap counts
as spoken). The spoken opener stays short and the first real singing
(measured on the vocal stem) is targeted at 15% of the runtime. It replaces
the earlier 45 percent target and the per-length targets.*

This package owns the canonical card line and the canonical docs wording for
that retarget, plus the reference note the owner asked for:

  * the owner-approved **5-minute** reference ad measures **57.0% spoken**
    (170.9 s of 300 s, ``qualification/hybrid-one-check-chanel/
    storyboard-5min.md``) -- that is **over the new 32.5% redo limit**, so it does
    not set the spoken share and no new ad may copy that number;
  * its **recipe still stands for everything else** -- story, beats, look,
    timing map, voices, the C3 audio method.

``check_card_text()`` / ``check_docs_text()`` are the fail-closed readers:
hand them card or docs text and they return the list of requirements that
text is missing (empty list = the text carries the new rule). ``find_stale``
names any retired-band wording it finds. The tests plant known-bad text so
both readers are proven able to fail -- a checker that cannot fail is not
evidence.

stdlib only, no network module, no provider call, no spend, no media file,
no absolute operator path (build root is found by walking up from this file).

Run: python3 core/spoken_share_card_docs/test_share_card_docs.py
"""
from __future__ import annotations

import os

# ---- canonical numbers (owner D15 retarget, plan 6.7) ---------------------
SPOKEN_TARGET_PCT = 22.5        # the target, same for every length and style
SPOKEN_BAND_PCT = (20, 25)      # accept band shown on the card (target +- 2.5)
SUNG_VOICE_TARGET_PCT = 77.5    # singing, as a share of VOICE time
SUNG_VOICE_BAND_PCT = (75, 80)
SPOKEN_MAX_PCT = 32.5           # redo edge: target + 10 points
SPOKEN_MIN_PCT = 12.5           # redo edge: target - 10 points
FIRST_SUNG_TARGET_PCT = 15      # H6: first real singing, measured, as a share of runtime

#: The retired bands, kept only so tests can name what was replaced.
RETIRED_TARGET_PCT = 45
RETIRED_BAND_PCT = (40, 70)

#: Owner-approved 5-minute reference ad: measured spoken share.
REFERENCE_NAME = "5-minute One Check Chanel reference ad"
REFERENCE_LENGTH_SECONDS = 300.0
REFERENCE_SPOKEN_SECONDS = 170.9
REFERENCE_SPOKEN_PCT = 57.0

TOOL_NAME = "spoken_share_card_docs"
TOOL_VERSION = "1.1.0"
SCHEMA_VERSION = "blackceo.spoken-share-card-docs/v1"
SOURCE = "Decision log 37 (D15 retarget) 2026-10-07; plan 6.7; SPK001 2026-10-08"

# ---- choice card line (plan 4.1 column alignment: label + body at col 13) --
SPOKEN_LINE_PREFIX = "Spoken:"
_CARD_SPACING = " " * (13 - len(SPOKEN_LINE_PREFIX))

CARD_LINE = (
    "%s%s%g%% of the runtime (%d-%d%%)  /  sung %g%% of voice time "
    "(%d-%d%%)  /  short spoken opener  /  first real singing at about %d%% "
    "of the ad"
    % (SPOKEN_LINE_PREFIX, _CARD_SPACING, SPOKEN_TARGET_PCT,
       SPOKEN_BAND_PCT[0], SPOKEN_BAND_PCT[1], SUNG_VOICE_TARGET_PCT,
       SUNG_VOICE_BAND_PCT[0], SUNG_VOICE_BAND_PCT[1], FIRST_SUNG_TARGET_PCT)
)

#: The one field this line reports on; it writes nothing by itself.
SPOKEN_FIELD = "spoken_share"

# ---- docs wording ---------------------------------------------------------
DOCS_STATEMENT = (
    "Spoken share (SPK001, owner 2026-10-08): target %g%% of the ad's runtime "
    "(%d-%d%%), and singing is measured against voice time, sung / (sung + "
    "spoken), target %g%% (%d-%d%%); a music-only intro, gaps and the end "
    "card never count against it. Both are judged by Trevor's band: within 5 "
    "points accept, 5 to 10 accept with a flag, past 10 redo. The lyric "
    "writer budgets spoken lines at about 15-18%% of the lyric words because "
    "Suno stretches spoken parts. Same for every length and every music "
    "style -- rap counts as spoken. The spoken opener stays short and the "
    "first real singing, measured on the vocal stem, is targeted at %d%% of "
    "the runtime. This replaces the earlier %d percent target and the "
    "per-length targets."
    % (SPOKEN_TARGET_PCT, SPOKEN_BAND_PCT[0], SPOKEN_BAND_PCT[1],
       SUNG_VOICE_TARGET_PCT, SUNG_VOICE_BAND_PCT[0], SUNG_VOICE_BAND_PCT[1],
       FIRST_SUNG_TARGET_PCT, RETIRED_TARGET_PCT)
)

REFERENCE_NOTE = (
    "Reference note -- the %s measures %.1f%% spoken (%.1f s of %.0f s), "
    "which is over the new %g%% redo limit, so it does not set the spoken share "
    "and no new ad may copy that number. Its recipe still stands for "
    "everything else: story, beats, look, timing map, voices and the C3 "
    "audio method."
    % (REFERENCE_NAME, REFERENCE_SPOKEN_PCT, REFERENCE_SPOKEN_SECONDS,
       REFERENCE_LENGTH_SECONDS, SPOKEN_MAX_PCT)
)

#: What the card block ships, in card order.
def card_block():
    """The choice-card lines this unit owns (the Spoken line)."""
    return [CARD_LINE]


def docs_statement(with_reference_note=True):
    """The docs wording: the retarget, plus the 5-minute reference note."""
    if with_reference_note:
        return "%s\n\n%s" % (DOCS_STATEMENT, REFERENCE_NOTE)
    return DOCS_STATEMENT


def reference_is_over_limit():
    """True: the 5-minute reference's 57% spoken is past the new redo edge."""
    return REFERENCE_SPOKEN_PCT > SPOKEN_MAX_PCT


def reference_within_retired_band():
    """True: it passed the OLD 40-70 band, which is why it was never flagged."""
    return RETIRED_BAND_PCT[0] <= REFERENCE_SPOKEN_PCT <= RETIRED_BAND_PCT[1]


# ---- fail-closed readers --------------------------------------------------
#: Retired-band wording no card or docs may carry any more. Assembled so the
#: exact old advertisement of the band is never stored as one literal here.
STALE_PHRASES = (
    "40-70",
    "40 to 70",
    "40–70",
    "40%..70%",
    "0.40..0.70",
    "0.40-0.70",
    "cap 70%",
    "never above 70%",
    "never more than 70%",
    "55-60%",
    "55–60%",
    "55-60",
    "45% of the runtime",
    "never above 55%",
    "never more than 55%",
    "never below 40%",
    "never less than 40%",
)

_CARD_REQUIRED = (
    ("%g%%" % SPOKEN_TARGET_PCT, "states the 22.5 percent target"),
    ("%d-%d%%" % SPOKEN_BAND_PCT, "states the 20-25 percent band"),
    ("sung %g%% of voice time" % SUNG_VOICE_TARGET_PCT,
     "states the 77.5 percent sung-of-voice target"),
    ("short spoken opener", "keeps the spoken opener short"),
    ("first real singing at about %d%% of the ad" % FIRST_SUNG_TARGET_PCT,
     "first real singing at about 15 percent of the ad"),
)

_DOCS_REQUIRED = (
    ("target %g%%" % SPOKEN_TARGET_PCT, "states the 22.5 percent target"),
    ("voice time", "measures singing against voice time"),
    ("target %g%%" % SUNG_VOICE_TARGET_PCT,
     "states the 77.5 percent sung-of-voice target"),
    ("past 10 redo", "states the redo rule"),
    ("rap counts as spoken", "counts rap as spoken"),
    ("opener stays short", "keeps the spoken opener short"),
    ("targeted at %d%% of the runtime" % FIRST_SUNG_TARGET_PCT,
     "first real singing targeted at 15 percent of the runtime"),
    ("%.1f%%" % REFERENCE_SPOKEN_PCT, "carries the 57 percent reference figure"),
    ("over the new %g%% redo limit" % SPOKEN_MAX_PCT,
     "says the reference figure is over the new limit"),
    ("recipe still stands", "says the reference recipe still stands"),
    ("everything else", "scopes the recipe to everything else"),
)


def find_stale(text):
    """Retired-band phrases found in text (empty = clean)."""
    if not isinstance(text, str):
        raise TypeError("find_stale expects text, got %s" % type(text).__name__)
    return [p for p in STALE_PHRASES if p in text]


def _missing(text, required):
    if not isinstance(text, str):
        raise TypeError("expected text, got %s" % type(text).__name__)
    haystack = text.lower()
    reasons = [why for needle, why in required if needle.lower() not in haystack]
    reasons += ["retired band wording present: %r" % p for p in find_stale(text)]
    return reasons


def check_card_text(text):
    """Requirements a choice-card text is missing (empty = it carries D15)."""
    return _missing(text, _CARD_REQUIRED)


def check_docs_text(text):
    """Requirements a docs text is missing (empty = it carries D15 + note)."""
    return _missing(text, _DOCS_REQUIRED)


__all__ = [
    "CARD_LINE",
    "DOCS_STATEMENT",
    "FIRST_SUNG_TARGET_PCT",
    "REFERENCE_LENGTH_SECONDS",
    "REFERENCE_NAME",
    "REFERENCE_NOTE",
    "REFERENCE_SPOKEN_PCT",
    "REFERENCE_SPOKEN_SECONDS",
    "RETIRED_BAND_PCT",
    "SCHEMA_VERSION",
    "SOURCE",
    "SPOKEN_FIELD",
    "SPOKEN_LINE_PREFIX",
    "SPOKEN_MAX_PCT",
    "SPOKEN_BAND_PCT",
    "SUNG_VOICE_TARGET_PCT",
    "SUNG_VOICE_BAND_PCT",
    "RETIRED_TARGET_PCT",
    "SPOKEN_MIN_PCT",
    "SPOKEN_TARGET_PCT",
    "STALE_PHRASES",
    "TOOL_NAME",
    "TOOL_VERSION",
    "card_block",
    "check_card_text",
    "check_docs_text",
    "docs_statement",
    "find_stale",
    "reference_is_over_limit",
    "reference_within_retired_band",
]


def build_root():
    """Directory that owns core/ -- found by walking up, never hard-coded."""
    parent = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        if os.path.isdir(os.path.join(parent, "core")):
            return parent
        up = os.path.dirname(parent)
        if up == parent:
            break
        parent = up
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
