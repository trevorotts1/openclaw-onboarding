#!/usr/bin/env python3
"""F-KLING-TEXT-BAIT: Kling request builder refuses letter-bait prompts.

Proves lock 9: check_kling_prompt_text refuses any prompt carrying
text/signage/decor-bait words BEFORE submit (TEXT_BAIT), fail-closed on
unreadable prompt text (LETTER_GATE_UNAVAILABLE), and stays silent on the
fixed no-text template clauses + book/print strands + overlay intent.

stdlib only, zero paid calls. Run: python3 core/test_kling_text_bait.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import never_again as NA  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


BAIT = ["sign on the wall", "neon signage glow", "a framed poster",
        "billboard in the distance", "caption across her chest",
        "subtitle at the bottom", "the title glowing", "logo on his shirt",
        "watermark in the corner", "doodle on the glass", "graffiti wall",
        "readable lettering", "letters forming words", "a headline banner",
        "emblem on the door", "shop sign", "chalkboard menu",
        "whiteboard notes", "placard held high", "marquee lights"]


def test_bait_words_refuse():
    for bait in BAIT:
        r = NA.check_kling_prompt_text(
            "She sings this line, %s, steady locked camera" % bait)
        check("bait refuses: %r" % bait,
              r is not None and r["code"] == NA.TEXT_BAIT, r)


def test_clean_prompts_pass():
    for prompt in [
        "She sings this line to the camera with a calm expression. "
        "Minimal head movement, steady locked camera, natural blinks. "
        "Her whole face and mouth stay fully visible, "
        "with no text, captions or watermark.",
        "Cinematic CGI animation, clearly animated with lifelike faces; "
        "soft global illumination, fine grain, no plastic skin.",
        "The clip is silent: no dialogue, music or sound effects. "
        "No captions, subtitles, logos, watermarks or readable signs "
        "are generated; any surface that would carry writing shows soft, "
        "unreadable texture, because exact words are added in "
        "post-production.",
        "Every visible page is filled with dense, realistic printed text: "
        "small black serif type in even lines and paragraph blocks.",
        "Upper third stays clean for the exact title, offer and link "
        "added in post.",
    ]:
        check("clean passes: %.50r" % prompt,
              NA.check_kling_prompt_text(prompt) is None,
              NA.check_kling_prompt_text(prompt))


def test_fail_closed_on_unreadable():
    for bad in (None, "", "   ", 123, ["sign"]):
        r = NA.check_kling_prompt_text(bad)
        check("unreadable refuses fail-closed: %r" % (bad,),
              r is not None and r["code"] == NA.LETTER_GATE_UNAVAILABLE, r)


if __name__ == "__main__":
    test_bait_words_refuse()
    test_clean_prompts_pass()
    test_fail_closed_on_unreadable()
    print("FAILURES: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)
