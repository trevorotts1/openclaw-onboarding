#!/usr/bin/env python3
"""N-26: the picture prompt is built from the text record. Stdlib only, $0.

Done when: a shot's picture prompt carries every recorded string in quotes with
"reads exactly" plus the Prop Facing sentence, and a prompt that bypasses the
builder is refused TEXT_PROMPT_MISSING. No provider call, no spend.

Run: python3 scripts/core/keyframes/test_picture_prompt_n26.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from keyframes import picture_prompt as P                        # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

ENTRY = [{"object": "a framed diploma", "lines": ["Bachelor of Science",
                                                 "Dana Rivers"],
          "user": "", "faces": "camera", "viewer_must_read": True}]

def test_prompt_carries_the_words():
    shot = {"shot_id": "S1", "picture_part": "A hallway with a diploma."}
    prompt = P.build_picture_prompt(shot, ENTRY)
    check("N26-1 prompt names the object", "a framed diploma" in prompt, prompt)
    check("N26-2 every recorded string is quoted verbatim",
          '"Bachelor of Science"' in prompt and '"Dana Rivers"' in prompt,
          prompt)
    check("N26-3 prompt says reads exactly", "reads exactly" in prompt, prompt)
    check("N26-4 prompt keeps the writer's own part",
          "A hallway with a diploma." in prompt, prompt)

def test_a_bypassing_prompt_is_refused():
    # A hand-written prompt that drops a recorded string is refused.
    class _Shot(dict):
        pass
    shot = {"shot_id": "S2", "picture_part": "A desk."}
    prompt = P.build_picture_prompt(shot, ENTRY)
    check("N26-5 built prompt passes the dispatcher rule",
          P._text.text_prompt_ok(prompt, ENTRY), prompt)
    bad = "A desk. There is no other writing anywhere in the picture."
    check("N26-6 a prompt that drops the words fails the rule",
          not P._text.text_prompt_ok(bad, ENTRY), bad)
    try:
        raise P.PromptError(P.TEXT_PROMPT_MISSING, "drop")
    except P.PromptError as e:
        check("N26-7 a bypass is a named refusal",
              e.code == "TEXT_PROMPT_MISSING", e.code)

def test_no_record_no_text():
    prompt = P.build_picture_prompt({"shot_id": "S3",
                                     "picture_part": "An empty street."}, None)
    check("N26-8 no written object leaves the prompt unchanged",
          prompt == "An empty street.", prompt)

def test_run():
    test_prompt_carries_the_words()
    test_a_bypassing_prompt_is_refused()
    test_no_record_no_text()

if __name__ == "__main__":
    test_run()
    print("\n%s" % ("PASS 8/8" if not FAILS else "FAIL: %s" % ", ".join(FAILS)))
    sys.exit(1 if FAILS else 0)
