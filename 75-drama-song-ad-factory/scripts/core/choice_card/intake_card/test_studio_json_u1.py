#!/usr/bin/env python3
"""U1: the studio-json export (question / price / example).

The Drama Studio renders one screen per intake question. Every screen needs the
question text, the price line it shows (when it shows one) and a "See a great
answer" example from the client guide. ``intake_card.py --format studio-json``
emits exactly those, from the SAME question list the card asks, so the card and
the studio cannot disagree.

The negative control: a screen missing its question text (or its example) must
make the export REFUSE -- a real non-zero exit and a named field on stderr --
never a json file the studio would render half-empty.

Run: python3 core/choice_card/intake_card/test_studio_json_u1.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import intake_card as IC  # noqa: E402

SCRIPT = os.path.join(HERE, "intake_card.py")
REQUIRED = ("question", "price", "example")
OPTION_KEYS = {"n", "text", "detail", "price", "recommended"}


def _cli(*args, **kw):
    return subprocess.run([sys.executable, SCRIPT] + list(args),
                          capture_output=True, text=True, **kw)


def test_export_has_question_price_and_example_for_every_screen():
    payload = IC.studio_json()
    assert payload["format"] == "studio-json" and payload["version"] == 0
    assert payload["question_count"] == len(IC.QUESTIONS) == len(payload["questions"])
    for screen in payload["questions"]:
        for field in REQUIRED:
            assert field in screen, (screen.get("id"), field)
        assert screen["question"].strip(), screen["id"]
        assert screen["example"].strip(), screen["id"]
        src = next(q for q in IC.QUESTIONS if q["id"] == screen["id"])
        assert len(screen["options"]) == len(src["options"]), screen["id"]
        for o in screen["options"]:
            assert set(o) == OPTION_KEYS, o


def test_model_screen_carries_the_live_prices_and_the_model_example():
    screen = next(s for s in IC.studio_json()["questions"] if s["id"] == "model")
    assert screen["price"] == ("Prices are for your 60-second ad, with the song, "
                               "pictures and a 20% redo allowance.")
    assert screen["question"].endswith(screen["price"])       # card ask and export agree
    prices = [o["price"] for o in screen["options"]]
    assert len(prices) == 4 and all(p and p.startswith("$") for p in prices), prices
    assert screen["example"].startswith('"MiniMax H3.'), screen["example"]


def test_every_other_screen_has_no_price_but_still_an_example():
    screens = {s["id"]: s for s in IC.studio_json()["questions"]}
    assert screens["length"]["price"] is None
    assert screens["length"]["example"].startswith('"60 seconds.'), screens["length"]
    for qid in ("models", "music", "look", "storyboard", "song", "script"):
        assert screens[qid]["example"].startswith('"'), (qid, screens[qid]["example"])


def test_budget_screen_shows_the_card_total_when_given():
    qs = [IC.spend_question(18.5, 25, True) if q["id"] == "spend" else q
          for q in IC.QUESTIONS]
    screen = next(s for s in IC.studio_json(qs)["questions"] if s["id"] == "spend")
    assert screen["price"] == "$18.50", screen["price"]
    assert [o["price"] for o in screen["options"]] == ["$25.00", "$18.50", None]


def test_cli_writes_the_export_and_exits_zero():
    p = _cli("--format", "studio-json")
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert payload["questions"][0]["id"] == "models"
    assert set(payload["questions"][0]) >= set(REQUIRED)


def test_negative_control_missing_question_text_fails_loudly():
    bad = [dict(q) for q in IC.QUESTIONS]
    bad[1].pop("ask")                     # the LENGTH screen loses its question text
    try:
        IC.studio_json(bad)
    except IC.StudioExportError as e:
        assert "field=question" in str(e) and "id='length'" in str(e), e
    else:
        raise AssertionError("export accepted a screen with no question text")


def test_negative_control_example_missing_fails_loudly():
    bad = [dict(q) for q in IC.QUESTIONS]
    bad[1]["id"] = "not_a_guide_step"     # no client-guide example for this id
    try:
        IC.studio_json(bad)
    except IC.StudioExportError as e:
        assert "field=example" in str(e), e
    else:
        raise AssertionError("export accepted a screen with no example")


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
