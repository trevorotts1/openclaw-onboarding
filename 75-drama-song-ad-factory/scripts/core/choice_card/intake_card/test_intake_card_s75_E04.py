#!/usr/bin/env python3
"""U-E04 / S75-020, S75-021, S75-030: the Agnes pick, the yes words, stale
answers after a change, and the recap's plain headings.

Nothing here calls a provider, and nothing outside a temp folder is written.

Run: python3 scripts/core/choice_card/intake_card/test_intake_card_s75_E04.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import intake_card as IC  # noqa: E402

TYPED = "Sweet Details Cookie-Decorating Class"


def _campaign_replies(overrides=None):
    """The replies that walk the campaign card to its recap, in ask order."""
    overrides = dict(overrides or {})
    answers, qs, replies = [], IC._shaped(IC.QUESTIONS, []), []
    while len(answers) < len(qs) and not qs[len(answers)].get("defaulted"):
        q = qs[len(answers)]
        r = overrides.get(q["id"])
        if r is None:
            if q.get("free_text"):
                r = TYPED
            elif q["id"] == "spend":
                r = "$25"
            elif q["id"] == "agnes":
                r = "1"                      # nothing is marked on this screen
            else:
                r = "recommended"
        a = IC._parse(r, q)
        assert a and "error" not in a, (q["id"], r)
        answers.append(a)
        replies.append(r)
        qs = IC._shaped(IC.QUESTIONS, answers)
    return qs, replies


# ------------------------------------------------------------- S75-020 --------
def test_agnes_marks_a_pick_only_for_a_client_who_said_yes_before():
    unknown = IC._agnes_q("unknown")
    assert unknown["recommended"] is None
    assert unknown["closing"] == "Reply 1 or 2."
    yes = IC._agnes_q("yes")
    assert yes["recommended"] == 0
    assert yes["closing"] == "Reply with a number."

    step = IC.render_step(1, [unknown])
    assert "RECOMMENDED" not in step, step
    assert step.endswith("Reply 1 or 2."), step
    marked = IC.render_step(1, [yes])
    assert "(RECOMMENDED when you said yes before)" in marked
    assert marked.endswith("Reply with a number.")

    assert IC._parse("yes", unknown) is None           # nothing to recommend
    assert IC._parse("2", unknown)["n"] == 2
    assert IC._parse("yes", yes)["n"] == 1


def test_a_bare_yes_answers_only_an_approval_question():
    music = next(q for q in IC.QUESTIONS if q["id"] == "music")
    for word in IC._YES:
        assert IC._parse(word, music) is None, word    # MUSIC STYLE is not a yes/no
    assert IC._parse("recommended", music)["n"] == 1   # the pick word still works

    checkpoints = next(q for q in IC.QUESTIONS if q["id"] == "checkpoints")
    assert IC._parse("yes", checkpoints)["n"] == 1     # top option is "Everything"

    storyboard = next(q for q in IC._gate_questions() if q["id"] == "storyboard")
    assert IC._parse("ok", storyboard)["n"] == 1       # its first option is a yes

    permission = next(q for q in IC._conditional_questions()
                      if q["id"] == "permission")
    assert IC._parse("yes", permission) is None        # nothing recommended here


# ------------------------------------------------------------- S75-021 --------
def test_changing_the_length_drops_the_answers_given_to_the_later_questions():
    qs, replies = _campaign_replies()
    ids = [q["id"] for q in qs]
    assert "agnes" in ids, ids                         # 3 minutes still asks Agnes
    length_at = ids.index("episode_length")

    recap = IC.conversation(replies, purpose_flow=True)
    assert recap["message"].startswith("Here is what you picked:")

    # 10 minutes is KIE-only, so the Agnes screen after the length is gone.
    # The saved-setup answer carries no "id" key (production pairs answers
    # with questions by position), so prove the pairing positionally: every
    # kept answer is exactly what its own reply parses to against the question
    # now in that slot, and no answer outlives the changed question.
    st = IC.conversation(replies + [str(length_at + 1), "6"], purpose_flow=True)
    later = IC._shaped(IC.QUESTIONS, st["answers"])
    assert len(st["answers"]) == length_at + 1
    assert [q["id"] for q in later[:len(st["answers"])]] == ids[:length_at + 1]
    for i, q in enumerate(later[:length_at]):
        assert st["answers"][i] == IC._parse(replies[i], q), (i, q["id"])
    assert st["answers"][length_at]["n"] == 6
    assert "agnes" not in [q["id"] for q in later]
    assert "That changes a few of the later choices" in st["message"], st["message"]
    assert st["done"] is False


# ------------------------------------------------------------- S75-030 --------
def test_the_recap_names_every_screen_in_plain_words():
    assert IC._RECAP_LABEL == {"models": "AI setup", "model": "Video model",
                               "link": "Web address", "spend": "Budget"}
    _, replies = _campaign_replies()
    recap = IC.conversation(replies, purpose_flow=True)["message"]
    assert "AI setup: " in recap, recap
    assert "Web address: " in recap, recap
    assert "Budget: up to $25.00" in recap, recap
    assert "Video model: " in recap, recap              # the defaulted recap line
    assert "Music style: " in recap, recap
    assert "Ai models" not in recap and "Offer Link" not in recap, recap


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
