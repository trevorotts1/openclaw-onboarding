#!/usr/bin/env python3
"""U1 / S75-074: the studio-json export (heading / question / example / price inputs).

The Drama Studio renders one screen per intake question. Every screen needs a
plain heading (never the shouting LABEL), its question text, and -- when it
shows one -- a "See a great answer" example. A typed question carries no option
row: the page asks for the words itself. A priced option carries the price
inputs the page turns into a true price for the length the client picks, never
a fixed dollar string.

The negative controls: a screen missing its question text, and a typed screen
with no example, must make the export REFUSE -- a real non-zero exit and a
named field on stderr -- never a json file the studio would render half-empty.

Run: python3 core/choice_card/intake_card/test_studio_json_u1.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import agnes_explanation as AE  # noqa: E402
from choice_card.intake_card import intake_card as IC  # noqa: E402

SCRIPT = os.path.join(HERE, "intake_card.py")
REQUIRED = ("title", "question", "example", "why", "typed", "options")
OPTION_KEYS = {"n", "text", "detail", "price", "recommended"}
RATE_KEYS = {"rate_usd", "unit", "shot_s", "keyframe_usd", "song_usd",
             "redo_rate", "keyframe_count_extra"}
#: S75-074 step 3: the exact examples a typed answer shows on the page.
TYPED_EXAMPLES = {
    "link": '"https://example.com/speaker"',
    "photos": '"My logo and one product photo. I will send them after this."',
    "character": '"Tasha, a warm 40-year-old braider with locs, in a denim apron."',
}


def _cli(*args, **kw):
    return subprocess.run([sys.executable, SCRIPT] + list(args),
                          capture_output=True, text=True, **kw)


def _screens(**kw):
    return {s["id"]: s for s in IC.studio_json(**kw)["questions"]}


def test_every_screen_carries_a_plain_heading_and_a_question():
    payload = IC.studio_json()
    assert payload["format"] == "studio-json" and payload["version"] == 0
    assert payload["question_count"] == len(IC.QUESTIONS) == len(payload["questions"])
    for screen in payload["questions"]:
        for field in REQUIRED:
            assert field in screen, (screen.get("id"), field)
        assert screen["question"].strip(), screen["id"]
        assert screen["title"].strip(), screen["id"]
        # S75-074 step 1: a heading is a sentence, never the shouting LABEL
        assert screen["title"] != screen["label"], screen["id"]
        assert screen["title"] != screen["title"].upper(), screen["id"]
        for o in screen["options"]:
            assert OPTION_KEYS <= set(o), (screen["id"], o)


def test_no_exported_option_opens_a_screen_the_export_does_not_carry():
    """U-GEN437: the export never offers an option that only opens another screen.

    The page branches on an ANSWER, not on a follow-up screen, so an option that
    just opens one is a dead end. The card marks such an option with
    ``opens_screen``; the export drops the opener and never carries the screen it
    would have opened. MUSIC STYLE therefore exports its three styles, not the
    "Show me all N styles" row."""
    screens = _screens(conditional=True)
    ids, checked = set(screens), 0
    for q in list(IC.QUESTIONS) + IC._conditional_questions():
        opens = q.get("opens_screen") or {}
        if not opens:
            continue
        checked += 1
        assert opens["id"] not in ids, (q["id"], opens["id"])
        opener = q["options"][opens["n"] - 1][0]
        shown = [o["text"] for o in screens[q["id"]]["options"]]
        assert opener not in shown, (q["id"], opener)
        assert len(shown) == len(q["options"]) - 1, q["id"]
    assert checked, "no screen carries an opens_screen marker any more"
    assert "music_full" not in ids
    assert len(screens["music"]["options"]) == 3


def test_headings_come_from_the_page_table():
    # the purpose screens ride only on the conditional export (SPEC B1), and
    # this test names all of them
    screens = _screens(conditional=True)
    for qid, title in (("purpose", "What is this video for?"),
                       ("permission", "Your client's permission"),
                       ("where", "Where it will run"),
                       ("offer", "What you are promoting"),
                       ("link", "Where to send people"),
                       ("audience", "Who it is for"),
                       ("character", "Who stars in it"),
                       ("photos", "Photos and logos"),
                       ("models", "Who builds and who checks"),
                       ("length", "How long"),
                       ("shape", "Tall or wide"),
                       ("music", "The sound"),
                       ("look", "The look"),
                       ("model", "Picture quality"),
                       ("spend", "Your spending limit"),
                       ("checkpoints", "What you want to see first")):
        assert screens[qid]["title"] == title, (qid, screens[qid]["title"])
    assert _screens(conditional=True)["episode_length"]["title"] == "How long"
    conditional = _screens(conditional=True)
    for qid in ("script", "song", "storyboard"):
        assert qid not in conditional          # CHECKPOINTS replaces all three
    assert conditional["agnes"]["title"] == "Your Agnes plan"


def test_typed_screens_carry_no_option_row_and_the_exact_example():
    screens = _screens()
    for qid in IC.BRIEF_IDS:
        assert screens[qid]["typed"] is True, qid
        assert screens[qid]["options"] == [], qid
        assert screens[qid]["example"].strip(), qid
    for qid, example in TYPED_EXAMPLES.items():
        assert screens[qid]["example"] == example, (qid, screens[qid]["example"])
    # the offer and the audience keep the guide's own example for their step
    assert screens["offer"]["example"].startswith('"My 6-week Confident Speaker')
    assert screens["audience"]["example"].startswith('"Women 35-55')
    for qid in ("models", "length", "music", "look", "checkpoints", "spend",
                "model", "shape"):
        assert screens[qid]["typed"] is False, qid


def test_a_choice_screen_shows_no_example_and_no_verbatim_option_row():
    screens = _screens(conditional=True)
    for qid in ("purpose", "episode_length", "permission", "where", "agnes",
                "models", "length", "music", "look", "checkpoints", "spend",
                "model", "shape"):
        assert screens[qid]["example"] is None, (qid, screens[qid]["example"])
        assert screens[qid]["options"], qid


def test_model_screen_carries_price_inputs_not_a_fixed_dollar_string():
    screen = _screens()["model"]
    # S75-059 step 2: the fixed sentence is gone from the page's question
    assert "50% redo allowance" not in screen["question"], screen["question"]
    assert screen["question"] == "Which video model should make your shots?"
    assert screen["price"] is None
    assert screen["example"] is None                 # the Hailuo example is gone
    assert len(screen["options"]) == 4
    for o in screen["options"]:
        assert o["price"] is None, o
        assert "$" not in o["detail"], o          # no fixed dollar string travels
        assert RATE_KEYS <= set(o), o
        assert o["unit"] in ("second", "clip"), o
    # the live allowance, not the stale 0.2 in the table
    assert all(o["redo_rate"] == 0.5 for o in screen["options"])
    # exactly one option is marked recommended
    assert sum(1 for o in screen["options"] if o["recommended"]) == 1


def test_budget_screen_is_in_the_page_words_with_the_computed_limit():
    screen = _screens()["spend"]
    assert screen["question"] == ("What is the most this video may spend? Work stops "
                                  "and asks you before going over.")
    assert screen["price"] is None and screen["example"] is None
    assert screen["options"][0]["text"].startswith("Use the recommended limit - about $")
    assert screen["options"][0]["recommended"] is True
    assert RATE_KEYS <= set(screen["options"][0])
    assert screen["options"][-1]["text"] == "Set my own limit"
    assert not screen["options"][-1]["recommended"]
    assert screen["options"][-1]["n"] == len(screen["options"])


def test_sample_links_ride_with_their_option_only_when_one_exists():
    look = _screens()["look"]
    with_link = [o for o in look["options"] if o.get("sample_url")]
    assert with_link and all(o["sample_url"].startswith("http") for o in with_link)
    for screen in (_screens(conditional=True)).values():
        for o in screen["options"]:
            if screen["id"] != "look":
                assert "sample_url" not in o, (screen["id"], o["n"])


def test_agnes_carries_no_recommended_mark_in_the_export():
    agnes = _screens(conditional=True)["agnes"]
    assert agnes["options"] and not any(o["recommended"] for o in agnes["options"])
    assert agnes["supplementary_explanation"] == AE.lines()
    text = " ".join(agnes["supplementary_explanation"])
    for vendor in ("KIE", "Suno", "Kling"):
        assert vendor not in text, vendor


def test_no_screen_text_uses_internal_or_vendor_jargon():
    import re
    screens = _screens(conditional=True)
    for screen in screens.values():
        words = [screen["title"], screen["question"],
                 screen.get("why") or "", screen["example"] or ""]
        for o in screen["options"]:
            words += [o["text"], o["detail"]]
        words += list(screen.get("supplementary_explanation") or [])
        text = " ".join(words)
        assert not re.search(r"reply with", text, re.I), (screen["id"], text)
        assert "the card" not in text.lower(), screen["id"]


def test_cli_writes_the_export_and_exits_zero():
    p = _cli("--format", "studio-json")
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    # DSR-105 + S75-006: the typed brief opens the card, then the AI setup
    assert [q["id"] for q in payload["questions"][:4]] == ["offer", "link", "audience",
                                                           "character"]
    assert payload["questions"][4]["id"] == "models"
    assert set(payload["questions"][0]) >= set(REQUIRED)


def test_negative_control_missing_question_text_fails_loudly():
    bad = [dict(q) for q in IC.QUESTIONS]
    at = [q["id"] for q in bad].index("length")
    bad[at].pop("ask")                    # the LENGTH screen loses its question text
    try:
        IC.studio_json(bad)
    except IC.StudioExportError as e:
        assert "field=question" in str(e) and "id='length'" in str(e), e
    else:
        raise AssertionError("export accepted a screen with no question text")


def test_negative_control_typed_example_missing_fails_loudly():
    bad = [dict(q) for q in IC.QUESTIONS]
    bad[1]["id"] = "not_a_guide_step"     # a typed screen with no example anywhere
    try:
        IC.studio_json(bad)
    except IC.StudioExportError as e:
        assert "field=example" in str(e), e
    else:
        raise AssertionError("export accepted a typed screen with no example")


def test_negative_control_process_exit_is_non_zero():
    driver = ("import sys; sys.path.insert(0, %r);"
              "from choice_card.intake_card import intake_card as IC;"
              "bad=[dict(q) for q in IC.QUESTIONS]; bad[1].pop('ask');"
              "print(IC.studio_json(bad))"
              % os.path.dirname(os.path.dirname(HERE)))
    p = subprocess.run([sys.executable, "-c", driver], capture_output=True, text=True)
    assert p.returncode != 0, ("expected a non-zero exit, got %d" % p.returncode, p.stdout)
    assert p.stdout.strip() == "", p.stdout          # no degraded file on stdout
    assert "field=question" in p.stderr, p.stderr


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
