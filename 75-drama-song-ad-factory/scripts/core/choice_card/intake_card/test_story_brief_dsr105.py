#!/usr/bin/env python3
"""DSR-105: the story brief is asked by the card, so it reaches every run.

The chat intake asks for the offer, the web address, the audience, the
character and the photos (SKILL.md); the Drama Studio page asked only the
production choices, so an order placed on the page carried no brief at all and
the crew had nothing to write from. intake_card.py stays the ONE place
questions are defined, and the brief is part of the card.

S75-006 moved the brief's screens: OFFER now takes the web address in the same
reply, and PHOTOS is a recap line rather than a screen the client must get
past. The brief and its ids are unchanged.

Run: python3 core/choice_card/intake_card/test_story_brief_dsr105.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import intake_card as IC  # noqa: E402

#: The ids the brief is stored under. `photos` rides the recap (S75-006).
TYPED_ON_CARD = ("offer", "link", "audience", "character")


def test_the_brief_screens_open_the_card_and_the_ids_are_unchanged():
    ids = [q["id"] for q in IC.QUESTIONS]
    assert ids[:len(TYPED_ON_CARD)] == list(TYPED_ON_CARD), ids
    assert ids.count("photos") == 1 and IC.QUESTIONS[-1]["id"] == "photos", ids
    assert IC.BRIEF_REQUIRED == ("offer", "link", "audience", "character")
    assert "photos" not in IC.BRIEF_REQUIRED        # stored, never required


def test_each_brief_question_is_typed_with_one_option_the_page_reads():
    for qid in IC.BRIEF_IDS:
        q = next(x for x in IC.QUESTIONS if x["id"] == qid)
        assert q["free_text"] is True, qid
        assert len(q["options"]) == 1, qid
        assert q["options"][0][1].lower().startswith("reply with"), qid
        assert "recommended" not in q, qid          # nothing to recommend: it is typed
        assert q["ask"].strip(), qid
    for q in IC.QUESTIONS:
        if q["id"] not in IC.BRIEF_IDS:
            assert not q.get("free_text"), q["id"]


def test_the_chat_card_asks_them_as_typed_blocks_not_menus():
    total = len(IC.QUESTIONS)
    for i, qid in enumerate(TYPED_ON_CARD, 1):
        block = IC.render_step(i)
        lines = block.split("\n")
        assert lines[0] == "Question %d of %d - %s" % (i, total, qid.upper()), block
        assert lines[-1] == IC.FREE_TEXT_HINT, block
        assert not [x for x in lines if x[:2] in ("1.", "2.")], block   # no menu
    # the OFFER screen is one sentence of why; the address follow-up asks only
    # its own sentence, because the offer is already in hand
    offer = IC.render_step(1).split("\n")
    assert offer[1].endswith(".") and offer[2] == ""
    link = IC.render_step(2).split("\n")
    assert link[1] == "Thanks. What web address should the video send people to?"
    # and the whole card carries one typed block per brief screen
    card = IC.render_card()
    assert card.startswith("Question 1 of %d - OFFER\n" % total)
    assert card.count(IC.FREE_TEXT_HINT) == len(IC.BRIEF_IDS)


def test_a_typed_answer_is_stored_verbatim_and_the_pick_words_are_refused():
    q = IC.QUESTIONS[0]
    got = IC._parse("My 6-week Confident Speaker program", q)
    assert got == {"n": 1, "text": "My 6-week Confident Speaker program",
                   "value": "My 6-week Confident Speaker program", "id": "offer"}
    for junk in ("1", "yes", "recommended", "  ", "", "go"):
        assert IC._parse(junk, q) is None, junk
    assert IC._parse("x" * (IC.MAX_TYPED_ANSWER_CHARS + 1), q) is None


def test_one_reply_carries_the_offer_and_its_address():
    q = IC.QUESTIONS[0]
    got = IC._parse("My course, https://example.com/course", q)
    assert got["text"] == "My course" and got["address"] == "https://example.com/course", got
    # a reply with no address stores the offer and asks for the address after it
    plain = IC._parse("My course", q)
    assert plain.get("address") is None and plain["text"] == "My course", plain


def test_the_recap_lists_the_brief_and_the_run_carries_it():
    replies = ["1", "My course, example.com/course", "Women 35-55", "Tasha, 40, locs",
               "5", "1", "1", "2", "1", "$25"]
    recap = IC.conversation(replies, purpose_flow=True)["message"]
    for n, label in ((2, "Offer"), (3, "Offer Link"), (4, "Audience"), (5, "Character")):
        assert "%d. %s: " % (n, label) in recap, recap
    assert "2. Offer: My course" in recap and "3. Offer Link: example.com/course" in recap
    assert "Photos: none yet - send them any time (default - reply" in recap, recap
    assert IC.conversation(replies + ["yes"], purpose_flow=True)["done"] is True


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
    assert len(qs) == len(IC.QUESTIONS), ids         # the same count either way
    assert ids.count("character") == 0 and ids.count("saved_character") == 1, ids
    assert ids.index("saved_character") == [q["id"] for q in IC.QUESTIONS].index("character")
    # no folder at all: the plain card, typed CHARACTER included
    assert IC._with_saved_character("") == IC.QUESTIONS


def test_the_studio_export_marks_the_brief_as_typed_and_still_refuses_a_half_screen():
    screens = {s["id"]: s for s in IC.studio_json()["questions"]}
    for qid in IC.BRIEF_IDS:
        assert screens[qid]["typed"] is True, qid
        assert screens[qid]["options"][0]["detail"].lower().startswith("reply with"), qid
    for qid in ("models", "length", "music", "look", "checkpoints", "spend"):
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
