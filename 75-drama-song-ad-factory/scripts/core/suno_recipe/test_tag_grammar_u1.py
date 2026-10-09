#!/usr/bin/env python3
"""FU-U1: one lyric tag grammar, rap-aware, no silent skips.

Plan 18-OPUS-SKILL75-FUTURE-PLAN section 2.A (root causes A1/A2). Proves:

  (a) parse of the One-Check sheet gives sung, rap and spoken word counts
      with rap = 254 and spoken = 24 (before this unit: rap = 0, the
      "rap-blind" pass -- every [Rap Verse ... (rap)] line was dropped);
  (b) check_lyric_sheet(sheet, CLIENT, 148, style_id="rnb-flow") returns
      errors (before: [] -- the blind pass; the 254 rap words were never
      counted against the budget);
  (c) words_fit counts [Intro (spoken)] as spoken (before: sung);
  (d) a lyric line under an unknown tag raises UNTAGGED_LYRIC_LINES.

Acceptance: all four parsers (suno_recipe.parse_lyrics,
words_fit.parse_sheet_words, music_styles.sheet_deliveries,
lyric_writer.lyric_structure.delivery_of_tag) return the same per-delivery
counts for one sheet; no lyric line is ever dropped quietly.

Run: python3 core/suno_recipe/test_tag_grammar_u1.py
stdlib only, no network, no spend.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

import suno_recipe as R                 # noqa: E402
import words_fit as W                   # noqa: E402
import music_styles as MS               # noqa: E402

# lyric_structure needs core/ on sys.path for its own imports (the module
# bootstraps that itself); import it the way lyric_writer does.
sys.path.insert(0, os.path.join(CORE, "lyric_writer"))
try:
    import lyric_structure as LS        # noqa: E402
finally:
    sys.path.pop(0)

FIXTURE = os.path.join(HERE, "fixtures", "one-check-lyrics.txt")
CLIENT = ("Girl, I got you. You need to register for the "
          "Girl, I Got You Masterclass.")

#: The One-Check counts, measured on the fixture by hand: 25 sung (vocalise
#: 1 + six hooks x 4), 24 spoken (intro 8 + outro 16), 254 rap.
SUNG, SPOKEN, RAP = 25, 24, 254

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def load_fixture():
    with open(FIXTURE, encoding="utf-8") as fh:
        return fh.read()


def test_a_parse_counts_all_three_deliveries():
    text = load_fixture()
    try:
        sheet = R.parse_lyrics(text)
    except Exception as exc:                        # noqa: BLE001
        check("(a) parse_lyrics reads the One-Check sheet", False,
              "%s: %s" % (type(exc).__name__, exc))
        return None
    sung = R.sheet_words(sheet, "sung")
    spoken = R.sheet_words(sheet, "spoken")
    rap = R.sheet_words(sheet, "rap")
    check("(a) rap words are read (254)", rap == RAP, "rap=%d" % rap)
    check("(a) spoken words are read (24)", spoken == SPOKEN, "spoken=%d" % spoken)
    check("(a) sung words are read (25)", sung == SUNG, "sung=%d" % sung)
    return sheet


def test_b_lyric_gate_counts_rap_in_the_budget(sheet):
    if sheet is None:
        check("(b) check_lyric_sheet sees rap (skipped: no sheet)", False)
        return
    try:
        errs = R.check_lyric_sheet(sheet, CLIENT, 148, style_id="rnb-flow")
    except TypeError as exc:
        check("(b) check_lyric_sheet takes style_id", False, str(exc))
        return
    check("(b) the One-Check sheet is REFUSED with style_id=rnb-flow",
          bool(errs), repr(errs[:2]))
    check("(b) the refusal names the budget (rap counted against it)",
          any("budget" in e for e in errs), repr(errs))
    # rap sections are only legal in the rap style
    soul = R.check_lyric_sheet(sheet, CLIENT, 148, style_id="soul-ballad")
    check("(b) rap sections are refused for soul-ballad",
          any("rap" in e for e in soul), repr(soul[:2]))


def test_c_words_fit_counts_the_spoken_intro_as_spoken():
    sung, spoken, rap = W.parse_sheet_words("[Intro (spoken)]\nGirl you ready")
    check("(c) words_fit counts [Intro (spoken)] as spoken",
          (sung, spoken, rap) == (0, 3, 0), (sung, spoken, rap))


def test_d_unknown_tag_raises_and_drops_nothing():
    bad = "[Whistle Solo]\nla la la under a tag with no delivery\n"
    try:
        R.parse_lyrics(bad)
    except R.RecipeError as exc:
        check("(d) unknown tag raises UNTAGGED_LYRIC_LINES",
              exc.code == "UNTAGGED_LYRIC_LINES", exc.code)
        check("(d) the error names the dropped line",
              "la la la under a tag" in str(exc), str(exc)[:120])
    except Exception as exc:                        # noqa: BLE001
        check("(d) unknown tag raises RecipeError (not %s)" % type(exc).__name__,
              False, str(exc))
    else:
        check("(d) unknown tag raises UNTAGGED_LYRIC_LINES", False,
              "parse_lyrics returned without raising")
    # an empty unknown tag with no lyric text under it is still legal
    try:
        sheet = R.parse_lyrics("[End]\n")
        check("(d) trailing [End] with no lyrics does not raise",
              sheet == [], repr(sheet))
    except Exception as exc:                        # noqa: BLE001
        check("(d) trailing [End] with no lyrics does not raise", False, str(exc))


def test_four_parsers_agree_on_one_sheet():
    text = load_fixture()
    try:
        sheet = R.parse_lyrics(text)
        recipe = (R.sheet_words(sheet, "sung"), R.sheet_words(sheet, "spoken"),
                  R.sheet_words(sheet, "rap"))
    except Exception as exc:                        # noqa: BLE001
        check("four parsers agree (recipe side)", False, str(exc))
        return
    try:
        fit = W.parse_sheet_words(text)
    except Exception as exc:                        # noqa: BLE001
        check("four parsers agree (words_fit side)", False, str(exc))
        return
    check("suno_recipe and words_fit agree: %r" % (recipe,),
          fit == recipe, "words_fit=%r" % (fit,))
    deliveries = MS.sheet_deliveries(text)
    check("music_styles sees all three deliveries",
          deliveries == {"sung", "spoken", "rap"}, repr(deliveries))
    # per-tag: the U1 grammar and lyric_structure agree on every tag the
    # fixture uses, in both bracket dialects.
    tags = [ln.strip()[1:-1] for ln in text.splitlines()
            if ln.strip().startswith("[") and ln.strip().endswith("]")]
    mismatch = [t for t in tags
                if R.delivery_of_tag(t) != LS.delivery_of_tag(t)]
    check("lyric_structure and suno_recipe agree on every fixture tag",
          not mismatch, repr(mismatch[:3]))
    check("fixture tags classify: Intro=spoken, Hook=sung, Rap Verse=rap, "
          "Instrumental Break=instrumental",
          R.delivery_of_tag("Intro (spoken): x") == "spoken"
          and R.delivery_of_tag("Hook (sung): x") == "sung"
          and R.delivery_of_tag("Rap Verse 1 Friend (rap): x") == "rap"
          and R.delivery_of_tag("Instrumental Break") == "instrumental"
          and LS.delivery_of_tag("Sung - lead, long held notes") == "sung",
          "")


def test_style_text_per_style_and_gendered():
    rap_sheet = R.parse_lyrics("[Vocalise (sung): wordless]\noo-oo\n\n"
                               "[Rap Verse (rap): flow]\none two\n\n"
                               "[Outro (spoken): close]\nbye\n")
    rnb = R.style_text("rnb-flow", rap_sheet, vocal_gender="m")
    ballad = R.style_text("soul-ballad", None)
    check("R&B Flow lead drops the ballad wording",
          "long held open vowels" not in rnb and "slow tempo" not in rnb, rnb)
    check("R&B Flow lead keeps the dry close vocal rule",
          "dry close vocal" in rnb, rnb)
    check("ballad lead keeps its wording",
          "long held open vowels" in ballad, ballad)
    check("gender comes from vocal_gender",
          "male lead" in rnb and "female" not in rnb.lower(), rnb)
    check("rap sheet: no 'only intro/outro spoken' claim",
          "only the short intro" not in rnb.lower(), rnb)
    check("style rules still pass on the built text",
          R.check_style_text(rnb) == [], repr(R.check_style_text(rnb)))
    check("style text still fits the 1000-char field",
          len(rnb) <= R.suno_recipe.SUNO_STYLE_FIELD_MAX,
          "%d" % len(rnb))


def main():
    sheet = test_a_parse_counts_all_three_deliveries()
    test_b_lyric_gate_counts_rap_in_the_budget(sheet)
    test_c_words_fit_counts_the_spoken_intro_as_spoken()
    test_d_unknown_tag_raises_and_drops_nothing()
    test_four_parsers_agree_on_one_sheet()
    test_style_text_per_style_and_gendered()
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
