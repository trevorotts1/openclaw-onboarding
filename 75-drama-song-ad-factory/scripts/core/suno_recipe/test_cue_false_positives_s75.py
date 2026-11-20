#!/usr/bin/env python3
"""Two gate false positives that refused a real client's song.

(1) is_no_voice_tag matched substrings, so a sung [Breakthrough] section
    counted as a [Break]: render_lyrics dropped its lines.
(2) check_no_voice_lines read the WHOLE bracket, so a declared spoken intro
    whose cue said "over a light instrumental bed" was refused as music-only.
(3) the closing check had no quiz call: "Take the quiz" was a summary-only
    promise, while the bare noun ("The quiz is beautiful.") must stay refused,
    and so must a negated call ("Do not take the quiz.").
(4) parse_tag read the whole bracket, so music_styles/lyric_structure saw her
    declared spoken intro as instrumental; the declaration now decides there too.

Real no-voice sections ([Instrumental], [Instrumental Break: band only],
[Break]) with a lyric line under them must still be refused.

Run: python3 scripts/core/suno_recipe/test_cue_false_positives_s75.py
stdlib only, no network, no spend.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

import suno_recipe as R               # noqa: E402
import story_arc.story_arc as SA       # noqa: E402
from lyric_writer import lyric_structure as LS   # noqa: E402
from music_styles import music_styles as MS      # noqa: E402
from song_contract import song_contract as SC    # noqa: E402
from words_fit import words_fit as WF            # noqa: E402

HER_CUE = ("[Intro (spoken): her own voice, plain speech, no melody, "
           "over a light instrumental bed, close and dry]")


def test_declared_cue_words_never_make_a_section_music_only():
    assert R.check_no_voice_lines(HER_CUE + "\nI kept the lights on alone.") == []
    assert R.check_no_voice_lines("[Verse (sung): a short break in the drums]\nHold on.") == []


def test_her_cue_reads_spoken_in_every_consumer():
    """The cue is data, the declaration is the delivery: every reader of the
    one tag grammar sees a spoken section, end to end."""
    sheet = HER_CUE + "\nI kept the lights on alone.\n\n[End]"
    assert R.parse_tag(HER_CUE) == "spoken"
    assert LS.delivery_of_tag(HER_CUE[1:-1]) == "spoken"
    assert [(s["tag"], s["delivery"]) for s in R.parse_lyrics(sheet)] == [("Intro", "spoken")]
    assert MS.sheet_deliveries(sheet) == {"spoken"}
    assert "SPEAKS" in MS.delivery_map(sheet)        # no EMPTY_SHEET_DELIVERIES
    try:
        MS.assert_no_contradiction(["spoken word"], sheet)
    except MS.MusicStyleError as e:
        assert e.code == "NEGATIVE_TAG_CONTRADICTION", e
    else:
        raise AssertionError("a 'spoken word' negative tag beside her spoken intro passed")
    assert WF.parse_sheet_words(sheet) == (0, 6, 0)
    assert [(s["tag"], s["delivery"]) for s in SC.parse_sections(sheet)][0] == ("Intro", "spoken")
    assert R.check_no_voice_lines(sheet) == []
    # a declared NAME still decides: an instrumental name stays instrumental
    assert R.parse_tag("[Instrumental Break (sung): band]") == "instrumental"
    assert R.parse_tag("[Instrumental Break: band only]") == "instrumental"


def test_real_no_voice_sections_still_refuse_a_lyric_line():
    for tag in ("[Instrumental]", "[Instrumental Break: band only]", "[Break]"):
        assert len(R.check_no_voice_lines(tag + "\nsix seconds, band only")) == 1, tag
    # a declared delivery cannot hide a no-voice NAME
    assert len(R.check_no_voice_lines("[Instrumental Break (sung): band]\nla la")) == 1


def test_whole_words_only():
    for tag in ("Breakthrough", "Heartbreak", "Breakdown"):
        assert not R.is_no_voice_tag(tag), tag
    for tag in ("Instrumental", "Instrumental Break", "Break", "break 2"):
        assert R.is_no_voice_tag(tag), tag


def test_breakthrough_lines_survive_render_lyrics():
    sheet = [{"tag": "Breakthrough", "delivery": "sung",
              "lines": ["I found the door,", "I walk right through,"]}]
    text = R.render_lyrics(sheet)
    assert "I found the door," in text and "I walk right through," in text, text
    assert R.check_no_voice_lines(text) == []


def test_quiz_call_counts_bare_noun_does_not():
    def closing(line):
        return SA.check_payload_closing("[CTA (spoken)]\n" + line)["outcome"]
    assert closing("Take the quiz: https://example.com") == "ok"
    for line in ("Take our quiz today.", "Take this quiz now.", "Start the quiz."):
        assert closing(line) == "ok", line
    assert closing("The quiz is beautiful.") == "rejected"


def test_negated_call_asks_for_nothing():
    def closing(line, **kw):
        return SA.check_payload_closing("[CTA (spoken)]\n" + line, **kw)["outcome"]
    for line in ("Do not take the quiz.", "Don't take the quiz.",
                 "Do not ever take the quiz.", "Never book a call.",
                 "Don't wait\nto never book"):
        assert closing(line) == "rejected", line
    for line in ("Don't wait. Book now.", "Don't wait\nBook now",
                 "No need to wait, book now.", "Why not book today?"):
        assert closing(line) == "ok", line
    # the approved action itself must be asked for, not refused
    assert closing("Do not call. Book now.", commercial_action="call") == "rejected"
    assert closing("Call now.", commercial_action="call") == "ok"


def test_cue_words_never_hide_the_closing_block():
    sheet = ("[Verse (sung)]\nla\n\n"
             "[Outro (spoken): over a light instrumental bed, to the end]\n"
             "Take the quiz: https://example.com\n\n[End]")
    assert SA.closing_block(sheet)["lines"] == ["Take the quiz: https://example.com"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("ALL PASS")
