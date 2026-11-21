#!/usr/bin/env python3
"""Round-3 findings on PR #3892 head f09cda23: em-dash never ends a negation,
cue words never discard lyrics during rendering.

Failing-first: on head f09cda23 the em-dash negation rows and the
render_lyrics cue row FAIL; after the fix all pass. Pins hold: the shared
tag parser keeps spoken delivery for an intro whose cue names an
instrumental bed (intro-only sheet never raises EMPTY_SHEET_DELIVERIES),
real [Instrumental] / [Instrumental Break: band only] / [Break] sections
with a lyric under them are still refused, and the closing accept/refuse
rows (colon, negative subjects, line breaks, own-sentence calls) hold.

Run: python3 scripts/core/suno_recipe/test_gatefix_round3_s75.py
stdlib only, no network, no spend.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

import suno_recipe as R               # noqa: E402
import story_arc.story_arc as SA       # noqa: E402


def test_em_dash_never_ends_the_negation_sentence():
    for line in ("Never — take the quiz.", "Nobody — take the quiz.",
                 "Never — book a call.", "Nobody — book a call."):
        assert SA._commercial_calls(line) == [], (line, SA._commercial_calls(line))
        out = SA.check_payload_closing("[CTA (spoken)]\n" + line)
        assert out["outcome"] == "rejected", (line, out)


def test_cue_words_never_discard_lyrics_during_rendering():
    sheet = R.parse_lyrics("[Intro spoken: instrumental bed]\nHello world")
    assert sheet and sheet[0]["delivery"] == "spoken", sheet
    assert sheet[0]["lines"] == ["Hello world"], sheet
    text = R.render_lyrics(sheet)
    assert "Hello world" in text, repr(text)
    assert R.check_no_voice_lines(text) == [], repr(text)


def test_shared_parser_keeps_spoken_delivery_with_instrumental_cue():
    tag = ("[Intro (spoken): her own voice over a light instrumental bed, "
           "close and dry]")
    assert R.parse_tag(tag) == "spoken", R.parse_tag(tag)
    import music_styles.music_styles as MS       # noqa: E402
    sheet = tag + "\nI kept the lights on alone."
    assert "spoken" in MS.sheet_deliveries(sheet), MS.sheet_deliveries(sheet)
    assert MS.delivery_map(sheet + "\n\n[End]"), "EMPTY on spoken intro"


def test_real_no_voice_sections_still_refuse_a_lyric_line():
    for tag in ("[Instrumental]", "[Instrumental Break: band only]", "[Break]"):
        assert len(R.check_no_voice_lines(tag + "\nsix seconds, band only")) == 1, tag
        try:
            sheet = R.parse_lyrics(tag + "\nsix seconds, band only")
        except Exception as e:
            assert "UNTAGGED_LYRIC_LINES" in type(e).__name__ or "UNTAGGED" in str(e), (tag, e)
        else:
            assert sheet == [], (tag, sheet)
        assert "six seconds" not in R.render_lyrics(
            [{"tag": tag.strip("[]"), "delivery": None,
              "lines": ["six seconds, band only"]}]), tag


def test_closing_accept_refuse_rows_hold():
    def closing(line, **kw):
        kw.setdefault("require_cta", True)
        return SA.check_payload_closing("[CTA (spoken)]\n" + line, **kw)["outcome"]
    assert closing("Take the quiz: https://example.com") == "ok"
    assert closing("Take the quiz: https://example.com",
                   commercial_action="take the quiz") == "ok"
    for line in ("The quiz is beautiful.", "Do not: take the quiz.",
                 "Nobody should take the quiz.", "No one should take the quiz.",
                 "Never\ntake the quiz.", "Do not\nbook a call.",
                 "Do not; take the quiz.", "Do not book a call."):
        assert closing(line) == "rejected", line
    for line in ("Do not wait. Take the quiz now.",
                 "No more guessing. Take our quiz.",
                 "Don't wait! Start the quiz."):
        assert closing(line) == "ok", line


def test_whole_word_no_voice_pins_hold():
    for tag in ("Breakthrough", "Heartbreak", "Breakdown", "Breaké",
                "breakα", "Break_more", "Break_down"):
        assert not R.is_no_voice_tag(tag), tag
    for tag in ("Instrumental", "Instrumental Break", "Break", "break 2"):
        assert R.is_no_voice_tag(tag), tag


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("ALL PASS")
