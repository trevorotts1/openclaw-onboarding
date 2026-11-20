#!/usr/bin/env python3
"""Two gate false positives that refused a real client's song.

(1) is_no_voice_tag matched substrings, so a sung [Breakthrough] section
    counted as a [Break]: render_lyrics dropped its lines.
(2) check_no_voice_lines read the WHOLE bracket, so a declared spoken intro
    whose cue said "over a light instrumental bed" was refused as music-only.
(3) the closing check had no quiz call: "Take the quiz" was a summary-only
    promise, while the bare noun ("The quiz is beautiful.") must stay refused.

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

HER_CUE = ("[Intro (spoken): her own voice, plain speech, no melody, "
           "over a light instrumental bed, close and dry]")


def test_declared_cue_words_never_make_a_section_music_only():
    assert R.check_no_voice_lines(HER_CUE + "\nI kept the lights on alone.") == []
    assert R.check_no_voice_lines("[Verse (sung): a short break in the drums]\nHold on.") == []


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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("ALL PASS")
