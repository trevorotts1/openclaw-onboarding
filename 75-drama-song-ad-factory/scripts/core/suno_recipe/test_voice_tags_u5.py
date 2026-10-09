#!/usr/bin/env python3
"""FU-U5: voice tags come from the cast (plan 18-OPUS-SKILL75-FUTURE-PLAN, unit U5).

The failure this prevents (plan 2.A7): a lyric sheet's hand-written bracket
voice tags were never compared with the cast record, so a sheet could name a
voice the cast does not have and still pass every gate. The live-run fault
(the One-Check Chanel run) is the BOX COWORKER bracket tagged "Female voice"
against a cast record of MALE.

The cast record used here is the LIVE one, cast/CAST.md
(qualification/spaulding-gigy-one-check-chanel-150/cast/CAST.md), NOT the
plan-time record: the plan's section A7 was written before the 2026-10-08
recast. On that day the sung voices in take g1b were measured (desk
neighbour female, manager male; box coworker L019/L020 P(male) 0.992) and
the cast was recast to match them, so the plan-time cast is superseded:
  line 14 "Desk neighbour (WOMAN, recast 2026-10-08 to the measured female
          voice; was a man)" -> desk neighbour is FEMALE;
  line 15 "Manager (MAN, recast 2026-10-08 to the measured male voice; was
          a woman)" -> manager is MALE;
  line 33 the BOX COWORKER was recast to a MAN over the storyboard's
          "female coworker", to match the measured voice; "song/lyrics.txt
          and LYRICS-SHEET.md coworker tag now 'Male voice'" -> coworker
          is MALE;
  line 30 the second whisperer was recast to a woman, so BOTH whisperers
          are women (lines 12/13) -> Coworkers FEMALE;
  line 16 "White male supervisor" -> supervisor MALE;
  line 17 "African American woman instructor" -> instructor FEMALE.
Each LIVE_CAST entry below cites its source; where CAST.md's supporting
table is silent (Friend, Chanel, Inner Chanel, Narrator) the sheet's own
tag is the only record available and is carried as such.

Proves:
  (a) parse_voice_tags reads the gender word out of a bracket tag;
  (b) DIRECTION A, must refuse: the One-Check sheet with the box coworker
      tagged "Female" against the live cast record (coworker a man) is
      REFUSED, code VOICE_TAG_MISMATCH, naming the tag and both sides;
  (c) DIRECTION B, must pass: the UNMODIFIED One-Check fixture against the
      live cast is CLEAN (zero errors). The mandatory control is inside
      (c): the desk neighbour bracket tagged "Female" passes against the
      live cast FEMALE -- the check is not a blanket refusal, and the same
      bracket is refused when the cast says male;
  (d) a bracket naming a cast character with no gender word is refused
      fail-closed (VOICE_TAG_UNCHECKED) -- an unverifiable tag is not a pass;
  (e) the recipe seam refuses it: suno_recipe.guard_request(...,
      cast_genders=...) raises RecipeError; brackets that name no cast
      character ([Hook], [Intro]) are never judged;
  (f) All Suno is unchanged: the built request still carries ONE
      vocal_gender and the same KIE params; no per-character voice map and
      no new voice option is added (Trevor's locked rule, plan section 8).

Run: python3 core/suno_recipe/test_voice_tags_u5.py
stdlib only, no network, no spend.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

import protected_names as PN            # noqa: E402
import suno_recipe as R                 # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "one-check-lyrics.txt")

#: The LIVE cast record. Source: cast/CAST.md for the ledger run
#: spaulding-gigy-one-check-chanel-150, including the 2026-10-08 recast
#: (the plan's A7 record is superseded -- see the module docstring).
LIVE_CAST = {
    # CAST.md's supporting table (lines 10-17) does not name the friend,
    # Chanel or Inner Chanel -- their sheets belong to another lane (line
    # 25) -- so the sheet's own tag is the only record available.
    "Friend": "female",
    "Chanel": "female",
    "Inner Chanel": "female",
    # BOX COWORKER: CAST.md line 33, recast 2026-10-08 to a MAN to match
    # the measured voice (L019/L020 P(male) 0.992); the table row "Female
    # coworker with the box" is superseded. Sheet tag now "Male voice".
    "Coworker": "male",
    # The whisperers: CAST.md lines 12/13 are women, and line 30 recast
    # the second whisperer to a woman ("the second whisperer is now a
    # woman"), so BOTH whisperers are women.
    "Coworkers": "female",
    # Narrator: not named in CAST.md's table; the sheet tag is the record.
    "Narrator": "male",
    # CAST.md line 14: "Desk neighbour (WOMAN, recast 2026-10-08 to the
    # measured female voice; was a man)" -> FEMALE. The sheet's "Female
    # voice - desk neighbor" is CORRECT and must PASS.
    "Desk Neighbor": "female",
    # CAST.md line 15: "Manager (MAN, recast 2026-10-08 to the measured
    # male voice; was a woman)" -> MALE.
    "Manager": "male",
    # CAST.md line 16: "White male supervisor".
    "Supervisor": "male",
    # CAST.md line 17: "African American woman instructor".
    "Instructor": "female",
}

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def load_fixture():
    with open(FIXTURE, encoding="utf-8") as fh:
        return fh.read()

def coworker_tagged_female(text):
    """The fixture with the box coworker wrongly tagged "Female".

    DIRECTION A fixture: the live-run fault. CAST.md line 33 records the
    coworker as a MAN, so this tag contradicts the cast.
    """
    return text.replace("Male voice - coworker", "Female voice - coworker")

def test_a_parse_voice_tags_reads_the_gender_word():
    try:
        tags = R.parse_voice_tags(load_fixture())
    except Exception as exc:                            # noqa: BLE001
        check("(a) parse_voice_tags reads the One-Check sheet", False,
              "%s: %s" % (type(exc).__name__, exc))
        return
    genders = [t["gender"] for t in tags if t["gender"]]
    check("(a) the sheet's voice tags carry gender words", len(genders) >= 20,
          "found %d" % len(genders))
    desk = [t for t in tags if t["name"] == "desk neighbor"]
    check("(a) the desk neighbour bracket reads female",
          bool(desk) and all(t["gender"] == "female" for t in desk),
          repr([t["gender"] for t in desk]))
    check("(a) [Hook], [Intro] and [End] name nobody (never judged)",
          all(t["name"] is None for t in tags
              if t["tag"].lower().startswith(("hook", "intro", "end", "vocalise"))
              or t["tag"].lower() == "instrumental break"),
          repr([(t["tag"], t["name"]) for t in tags
                if t["tag"].lower().startswith("hook")][:3]))
    check("(a) the rap verse brackets name their character",
          {t["name"] for t in tags if t["name"]} >=
          {"desk neighbor", "manager", "chanel", "friend", "supervisor"},
          repr(sorted({t["name"] for t in tags if t["name"]})))

def test_b_the_mismatched_coworker_is_refused():
    """DIRECTION A: a tag contradicting the live cast is caught."""
    text = coworker_tagged_female(load_fixture())
    try:
        errs = R.check_voice_tags(text, LIVE_CAST)
    except Exception as exc:                            # noqa: BLE001
        check("(b) check_voice_tags exists and runs", False,
              "%s: %s" % (type(exc).__name__, exc))
        return
    check("(b) the coworker tagged Female against the cast MALE is REFUSED",
          bool(errs), repr(errs[:2]))
    check("(b) the refusal names the Coworker",
          any("Coworker" in e for e in errs), repr(errs))
    check("(b) the refusal code is VOICE_TAG_MISMATCH",
          all(e.startswith("VOICE_TAG_MISMATCH") for e in errs), repr(errs[:2]))
    check("(b) the refusal states tag and cast, both sides",
          any("female" in e and "male" in e for e in errs), repr(errs[:2]))
    # exactly the one faulted bracket, nothing else
    check("(b) only the one untrue tag is refused",
          len(errs) == 1, "%d errors: %r" % (len(errs), errs))

def test_c_the_live_fixture_is_clean():
    """DIRECTION B + the mandatory control: the check discriminates."""
    text = load_fixture()
    try:
        errs = R.check_voice_tags(text, LIVE_CAST)
    except Exception as exc:                            # noqa: BLE001
        check("(c) the unmodified fixture passes against the live cast", False,
              "%s: %s" % (type(exc).__name__, exc))
        return
    check("(c) DIRECTION B: the unmodified One-Check fixture is CLEAN "
          "against the live cast (desk neighbour Female and manager Male "
          "are now the cast's own values)",
          errs == [], repr(errs))
    check("(c) the desk neighbour 'Female' tag is never refused by the "
          "live cast (the control: no blanket refusal)",
          not any("Desk Neighbor" in e for e in errs), repr(errs))
    check("(c) the manager 'Male' tag is never refused by the live cast",
          not any("Manager" in e for e in errs), repr(errs))
    # the same desk-neighbour bracket flips both ways with the cast: it
    # passes on the live FEMALE cast and is refused on a male cast, so the
    # clean result above is discrimination, not a dead check.
    desk = "[Rap Verse 3 Desk Neighbor (rap): Female voice - desk neighbor]\nline\n"
    check("(c) the desk neighbour tag PASSES when the cast says female",
          R.check_voice_tags(desk, {"Desk Neighbor": "female"}) == [],
          repr(R.check_voice_tags(desk, {"Desk Neighbor": "female"})))
    bad = R.check_voice_tags(desk, {"Desk Neighbor": "male"})
    check("(c) the same desk neighbour tag is REFUSED when the cast says "
          "male (the check discriminates)",
          bool(bad) and any("Desk Neighbor" in e for e in bad), repr(bad))
    check("(c) no cast judges nothing (the check is off)",
          R.check_voice_tags(text, {}) == []
          and R.check_voice_tags(text, None) == [])

def test_d_a_tag_with_no_gender_word_is_refused():
    sheet = ("[Vocalise (sung): wordless]\noo-oo\n\n"
             "[Verse 1 Chanel (rap): voice - chanel, warm alto]\nline one\n\n"
             "[Outro (spoken): close]\nbye now\n\n[End]\n")
    try:
        errs = R.check_voice_tags(sheet, {"Chanel": "female"})
    except Exception as exc:                            # noqa: BLE001
        check("(d) an unchecked character tag is refused", False,
              "%s: %s" % (type(exc).__name__, exc))
        return
    check("(d) an unchecked character tag is refused fail-closed",
          any(e.startswith("VOICE_TAG_UNCHECKED") for e in errs), repr(errs))
    check("(d) the refusal names Chanel",
          any("Chanel" in e for e in errs), repr(errs))
    # a cast record with no usable gender refuses too, never silently passes
    badge = "[Verse 1 Chanel (rap): voice - chanel]\nline one\n"
    check("(d) a cast gender that is not male/female still fails closed",
          bool(R.check_voice_tags(badge, {"Chanel": None})),
          repr(R.check_voice_tags(badge, {"Chanel": None})))

def test_e_the_recipe_seam_refuses():
    text = coworker_tagged_female(load_fixture())
    try:
        R.guard_request("style text", text, style_id=None,
                        cast_genders=LIVE_CAST)
    except R.RecipeError as exc:
        check("(e) guard_request raises RecipeError for the wrong tag",
              getattr(exc, "code", None) == "VOICE_TAG_MISMATCH"
              and "Coworker" in str(exc), str(exc)[:160])
    except TypeError as exc:
        check("(e) guard_request takes cast_genders", False, str(exc))
    except Exception as exc:                            # noqa: BLE001
        check("(e) guard_request raises RecipeError (not %s)" % type(exc).__name__,
              False, str(exc))
    else:
        check("(e) guard_request raises RecipeError for the wrong tag", False,
              "guard_request returned without raising")
    # the clean live fixture passes the seam (DIRECTION B through the seam)
    try:
        out = R.guard_request("style text", load_fixture(), style_id=None,
                              cast_genders=LIVE_CAST)
        check("(e) the clean live fixture passes the seam", out is None, repr(out))
    except Exception as exc:                            # noqa: BLE001
        check("(e) the clean live fixture passes the seam", False,
              "%s: %s" % (type(exc).__name__, exc))
    # a sheet whose brackets name no cast character is left alone
    try:
        out = R.guard_request("style text",
                              "[Hook (sung): full melody]\nline one\n",
                              style_id=None, cast_genders=LIVE_CAST)
        check("(e) brackets naming no cast character are never judged",
              out is None, repr(out))
    except Exception as exc:                            # noqa: BLE001
        check("(e) brackets naming no cast character are never judged", False,
              "%s: %s" % (type(exc).__name__, exc))

def test_g_plan_time_record_and_the_brief_helper():
    """The plan unit row's own acceptance, plus the brief -> map helper.

    Plan row U5 acceptance, verbatim: "The One-Check sheet with the desk
    neighbour tagged 'Female' when the cast says man is refused (today
    passes)." The cast that says man is the PLAN-TIME record (plan section
    A7 off CAST.md before the 2026-10-08 recast; superseded by the live
    record the other tests use, and kept here because it is the acceptance
    the unit was written against). Both directions are asserted.
    """
    plan_time = {"Desk Neighbor": "male", "Manager": "female",
                 "Coworker": "male", "Friend": "female", "Chanel": "female",
                 "Inner Chanel": "female", "Coworkers": "female",
                 "Narrator": "male", "Supervisor": "male",
                 "Instructor": "female"}
    errs = R.check_voice_tags(load_fixture(), plan_time)
    check("(g) acceptance: the One-Check sheet with the desk neighbour "
          "tagged Female against a cast that says man is REFUSED",
          any("Desk Neighbor" in e and e.startswith("VOICE_TAG_MISMATCH")
              for e in errs), repr(errs[:3]))
    check("(g) and the manager tagged Male against a cast that says woman "
          "is REFUSED",
          any("Manager" in e and e.startswith("VOICE_TAG_MISMATCH")
              for e in errs), repr(errs[:3]))
    # protected_names.cast_genders is the helper that builds the map from a
    # brief (brief.characters[].gender), the same entries protected_list reads.
    brief = {"characters": [{"name": "Chanel", "gender": "female"},
                            {"name": "Desk Neighbor", "gender": "male"},
                            {"name": "Supervisor", "gender": "male"}]}
    m = PN.cast_genders(brief)
    check("(g) protected_names.cast_genders reads brief.characters[].gender",
          m.get("Chanel") == "female" and m.get("Desk Neighbor") == "male",
          repr(m))
    check("(g) brief -> map -> check refuses end to end",
          bool(R.check_voice_tags(
              "[Rap Verse 3 Desk Neighbor (rap): Female voice - desk neighbor]"
              "\nline\n", m)), "no error for a female tag against a male cast")
    check("(g) a brief with no character list yields an empty map (check off)",
          PN.cast_genders({}) == {} and PN.cast_genders(None) == {})


def test_f_all_suno_is_unchanged():
    sheet_text = ("[Vocalise (sung): wordless]\noo-oo\n\n"
                  "[Hook (sung): full melody]\ngirl i got you\n\n"
                  "[Hook (sung): full melody]\ngirl i got you\n\n"
                  "[Outro (spoken): close]\nbye now\n\n[End]\n")
    sheet = R.parse_lyrics(sheet_text)
    try:
        req = R.build_request("soul-ballad", sheet, "girl i got you",
                              "T", None)
    except Exception as exc:                            # noqa: BLE001
        check("(f) build_request still builds a clean sheet", False,
              "%s: %s" % (type(exc).__name__, exc))
        return
    check("(f) exactly ONE vocal_gender on the request",
          req.get("vocal_gender") == "f", repr(req.get("vocal_gender")))
    check("(f) the KIE params are untouched",
          all(req.get(k) == v for k, v in R.KIE_PARAMS.items()),
          repr({k: req.get(k) for k in R.KIE_PARAMS}))
    check("(f) no per-character voice map was added",
          not [k for k in req if "voice" in k and k != "vocal_gender"], repr(sorted(req)))
    check("(f) the request shape is exactly the KIE fields plus the song",
          sorted(req) == sorted(list(R.KIE_PARAMS) + [
              "duration", "vocal_gender", "title", "style", "lyrics",
              "negative_tags"]), repr(sorted(req)))

def main():
    test_a_parse_voice_tags_reads_the_gender_word()
    test_b_the_mismatched_coworker_is_refused()
    test_c_the_live_fixture_is_clean()
    test_d_a_tag_with_no_gender_word_is_refused()
    test_e_the_recipe_seam_refuses()
    test_g_plan_time_record_and_the_brief_helper()
    test_f_all_suno_is_unchanged()
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
