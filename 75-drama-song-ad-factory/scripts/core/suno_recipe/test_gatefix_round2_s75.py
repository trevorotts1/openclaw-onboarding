#!/usr/bin/env python3
"""Round-2 gate findings on PR #465 (head 99d2bb7): cue words never decide a
section's delivery, and a quiz/book/call phrase counts as a call only when
nothing says not to act.

Failing-first: on head 99d2bb7 the colon case, the nobody case, the shared
parse_tag spoken case and the newline book case FAIL; after the fix all pass.
The unicode pin already holds on that head and stays green.

Run: python3 scripts/core/suno_recipe/test_gatefix_round2_s75.py
stdlib only, no network, no spend.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

import suno_recipe as R               # noqa: E402
import story_arc.story_arc as SA       # noqa: E402


def closing(line):
    return SA.check_payload_closing("[CTA (spoken)]\n" + line)["outcome"]


def test_colon_never_ends_the_negation_sentence():
    assert closing("Take the quiz: https://example.com") == "ok"
    assert closing("Do not: take the quiz.") == "rejected"


def test_negative_subjects_refuse():
    for line in ("Nobody should take the quiz.",
                 "No one should take the quiz.",
                 "Neither should take the quiz.",
                 "Nobody should book a call."):
        assert closing(line) == "rejected", line


def test_negation_reaches_across_line_breaks_for_every_action():
    for line in ("Never\ntake the quiz.",
                 "Do not\nbook a call.",
                 "Do not\ntake the quiz."):
        assert closing(line) == "rejected", line
    # a call in its own sentence still counts
    for line in ("Do not wait. Take the quiz now.",
                 "Don't wait! Start the quiz."):
        assert closing(line) == "ok", line


def test_shared_parser_reads_the_declared_delivery_not_the_cue():
    tag = ("[Intro (spoken): her own voice, plain speech, no melody, "
           "over a light instrumental bed, close and dry]")
    assert R.parse_tag(tag) == "spoken", R.parse_tag(tag)
    import music_styles.music_styles as MS
    sheet = tag + "\nI kept the lights on alone."
    assert "spoken" in MS.sheet_deliveries(sheet), MS.sheet_deliveries(sheet)
    # an intro-only sheet keeps spoken delivery: no EMPTY_SHEET_DELIVERIES
    intro_only = sheet + "\n\n[End]"
    assert MS.delivery_map(intro_only), "EMPTY_SHEET_DELIVERIES on a spoken intro"


def test_every_caller_reads_the_declared_delivery():
    sys.path.insert(0, os.path.join(CORE, "lyric_writer"))
    try:
        import lyric_structure as LS        # noqa: E402
    finally:
        sys.path.pop(0)
    tag = "[Intro (spoken): over a light instrumental bed, close and dry]"
    assert LS.delivery_of_tag(tag) == "spoken", LS.delivery_of_tag(tag)


def test_unicode_letters_are_word_characters():
    for tag in ("Breakthrough", "Heartbreak", "Breakdown", "Breaké", "breakα"):
        assert not R.is_no_voice_tag(tag), tag
    for tag in ("Instrumental", "Instrumental Break", "Break"):
        assert R.is_no_voice_tag(tag), tag


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("ALL PASS")
