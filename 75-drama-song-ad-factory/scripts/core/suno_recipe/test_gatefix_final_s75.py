#!/usr/bin/env python3
"""Round-2 findings (final) on PR #3892 head f3a5db34: cue words never decide,
underscore is a word character, semicolons never end negation, negated
approval refuses.

Failing-first: on head f3a5db34 the underscore case, the non-parenthesized
cue scan (both parse_tag cases), the non-parenthesized no-voice cue case,
the cue-masked closing case, the semicolon case and the negated-approval
case FAIL; after the fix all pass. Pins hold: the declared (spoken) intro
keeps spoken delivery everywhere, real no-voice sections still refuse a
lyric, and the quiz closing accepts/refuses as before.

Run: python3 scripts/core/suno_recipe/test_gatefix_final_s75.py
stdlib only, no network, no spend.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

import suno_recipe as R               # noqa: E402
import story_arc.story_arc as SA       # noqa: E402

def test_underscore_is_a_word_character():
    for tag in ("Break_more", "break_more", "Break_down"):
        assert not R.is_no_voice_tag(tag), tag

def test_cue_never_decides_delivery_outside_parens():
    assert R.parse_tag("[Intro spoken: instrumental bed]") == "spoken"
    assert R.parse_tag("[Verse: rap beat]") is None

def test_no_voice_judges_name_not_cue():
    assert R.check_no_voice_lines("[Verse: instrumental bed]\nlyric") == []
    for tag in ("[Instrumental]", "[Instrumental Break: band only]", "[Break]"):
        assert len(R.check_no_voice_lines(tag + "\nlyric")) == 1, tag

def test_closing_with_instrumental_cue_is_still_the_closing():
    sheet = ("[Verse]\nBook a call.\n\n"
             "[CTA (spoken): over a light instrumental bed]\n"
             "The quiz is beautiful.")
    assert SA.closing_block(sheet)["tag"].startswith("CTA"), SA.closing_block(sheet)
    out = SA.check_payload_closing(sheet, commercial_action="take the quiz",
                                   require_cta=True)
    assert out["outcome"] == "rejected", out
    assert out["reason_code"] == "summary-only-promise", out

def test_semicolon_never_ends_the_negation_sentence():
    assert SA.check_payload_closing("[CTA (spoken)]\nDo not; take the quiz.")["outcome"] == "rejected"
    assert SA._commercial_calls("Do not; take the quiz.") == []

def test_negated_approval_refuses():
    out = SA.check_payload_closing("[CTA (spoken)]\nTake the quiz now.",
                                   commercial_action="Do not book a call.",
                                   require_cta=True)
    assert out["outcome"] == "rejected", out
    assert out["reason_code"] == "closing-not-approved-call", out

def test_pins_hold():
    tag = ("[Intro (spoken): her own voice, plain speech, no melody, "
           "over a light instrumental bed, close and dry]")
    assert R.parse_tag(tag) == "spoken", R.parse_tag(tag)
    import music_styles.music_styles as MS       # noqa: E402
    sheet = tag + "\nI kept the lights on alone."
    assert "spoken" in MS.sheet_deliveries(sheet), MS.sheet_deliveries(sheet)
    assert MS.delivery_map(sheet + "\n\n[End]"), "EMPTY on spoken intro"
    assert R.check_no_voice_lines(
        "[Verse (sung): a short break in the drums]\nHold on.") == []
    assert len(R.check_no_voice_lines("[Instrumental Break (sung): band]\nla la")) == 1
    def closing(line):
        return SA.check_payload_closing("[CTA (spoken)]\n" + line)["outcome"]
    assert closing("Take the quiz: https://example.com") == "ok"
    assert closing("The quiz is beautiful.") == "rejected"
    assert closing("Do not: take the quiz.") == "rejected"
    assert closing("Nobody should take the quiz.") == "rejected"
    assert closing("Never\ntake the quiz.") == "rejected"
    assert closing("Do not\nbook a call.") == "rejected"

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("ALL PASS")
