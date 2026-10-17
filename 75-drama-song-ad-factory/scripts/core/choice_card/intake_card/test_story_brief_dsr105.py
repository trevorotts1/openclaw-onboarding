#!/usr/bin/env python3
"""DSR-105: the story brief is asked by the card, so it reaches every run.

The chat intake asks for the offer, the link, the audience, the character and
the photos (SKILL.md); the Drama Studio page asked only the nine production
choices, so an order placed on the page carried no brief at all and the crew
had nothing to write from. intake_card.py stays the ONE place questions are
defined, and these five are now part of the card.

Run: python3 core/choice_card/intake_card/test_story_brief_dsr105.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import intake_card as IC  # noqa: E402

#: The nine production choices, in the order they were asked before DSR-105.
PRODUCTION = ["models", "length", "music", "look", "model",
              "spend", "storyboard", "song", "script"]


def test_the_brief_opens_the_card_and_the_nine_follow_unchanged():
    ids = [q["id"] for q in IC.QUESTIONS]
    assert ids == list(IC.BRIEF_IDS) + PRODUCTION, ids
    assert len(ids) == 14
    assert IC.BRIEF_REQUIRED == ("offer", "link", "audience", "character")
    assert "photos" not in IC.BRIEF_REQUIRED        # asked and stored, never required


def test_each_brief_question_is_typed_with_one_option_the_page_reads():
    for q in IC.QUESTIONS[:len(IC.BRIEF_IDS)]:
        assert q["free_text"] is True, q["id"]
        assert len(q["options"]) == 1, q["id"]
        assert q["options"][0][1].lower().startswith("reply with"), q["id"]
        assert "recommended" not in q, q["id"]      # nothing to recommend: it is typed
        assert q["ask"].strip() and q["why"].strip(), q["id"]
    for q in IC.QUESTIONS[len(IC.BRIEF_IDS):]:
        assert not q.get("free_text"), q["id"]


def test_the_chat_card_asks_them_as_typed_blocks_not_menus():
    for i in range(1, len(IC.BRIEF_IDS) + 1):
        block = IC.render_step(i)
        lines = block.split("\n")
        assert lines[0].startswith("Question %d of 14 - " % i), block
        assert lines[2] == "" and lines[1].endswith("."), block      # the one-sentence why
        assert lines[-1] == IC.FREE_TEXT_HINT, block
        assert not [l for l in lines if l[:2] in ("1.", "2.")], block   # no menu to pick from
    # and the whole card carries the same five blocks
    card = IC.render_card()
    assert card.startswith("Question 1 of 14 - OFFER\n")
    assert card.count(IC.FREE_TEXT_HINT) == len(IC.BRIEF_IDS)


def test_a_typed_answer_is_stored_verbatim_and_the_pick_words_are_refused():
    q = IC.QUESTIONS[0]
    got = IC._parse("My 6-week Confident Speaker program", q)
    assert got == {"n": 1, "text": "My 6-week Confident Speaker program",
                   "value": "My 6-week Confident Speaker program", "id": "offer"}
    for junk in ("1", "yes", "recommended", "  ", "", "go"):
        assert IC._parse(junk, q) is None, junk
    assert IC._parse("x" * (IC.MAX_TYPED_ANSWER_CHARS + 1), q) is None


def test_the_recap_lists_the_brief_and_the_run_carries_it():
    replies = IC.example_replies()
    recap = IC.conversation(replies)["message"]
    for n, label in enumerate(["Offer", "Offer Link", "Audience", "Character", "Photos"], 1):
        assert "%d. %s: Sweet Details Cookie-Decorating Class" % (n, label) in recap, recap
    # the nine still land on their own lines, after the brief
    assert "6. Ai models: " in recap and "14. Script Approval: " in recap
    assert IC.conversation(replies + ["yes"])["done"] is True


def test_the_saved_character_pick_replaces_the_brief_character_question():
    """Exactly one 'who stars' question is ever asked (Part I, I6 keeps its rule)."""
    import tempfile
    from character_library import character_library as CL
    t = tempfile.mkdtemp()
    client = os.path.join(t, "client")
    img = os.path.join(t, "a.png")
    with open(img, "wb") as f:
        f.write(b"\x89PNG-fake")
    CL.save_character(client, "Maya Lee", "Warm, 40s, silver braids", [img])
    qs = IC._with_saved_character(client)
    ids = [q["id"] for q in qs]
    assert len(qs) == 14, ids                       # the same count either way
    assert ids.count("character") == 0 and ids.count("saved_character") == 1, ids
    assert "saved_character" in ids and ids.index("saved_character") == len(IC.BRIEF_IDS) - 1
    # no folder at all: the plain fourteen, typed CHARACTER included
    assert IC._with_saved_character("") == IC.QUESTIONS


def test_the_studio_export_marks_the_brief_as_typed_and_still_refuses_a_half_screen():
    screens = {s["id"]: s for s in IC.studio_json()["questions"]}
    for qid in IC.BRIEF_IDS:
        assert screens[qid]["typed"] is True, qid
        assert screens[qid]["options"][0]["detail"].lower().startswith("reply with"), qid
    for qid in PRODUCTION:
        assert screens[qid]["typed"] is False, qid
    # the export still refuses a screen the studio cannot render
    bad = [dict(q) for q in IC.QUESTIONS]
    bad[0].pop("ask")
    try:
        IC.studio_json(bad)
    except IC.StudioExportError as e:
        assert "field=question" in str(e) and "id='offer'" in str(e), e
    else:
        raise AssertionError("export accepted a brief screen with no question text")


def test_the_cli_still_prints_the_whole_card_and_the_step():
    script = os.path.join(HERE, "intake_card.py")
    card = subprocess.run([sys.executable, script], capture_output=True, text=True, check=True).stdout
    assert card == IC.render_card() + "\n"
    step = subprocess.run([sys.executable, script, "--step", "--reply", IC.example_replies()[0]],
                          capture_output=True, text=True, check=True).stdout
    assert step == IC.conversation([IC.example_replies()[0]])["message"] + "\n"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print("ALL PASS" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
