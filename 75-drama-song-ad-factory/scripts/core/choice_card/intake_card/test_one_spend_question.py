#!/usr/bin/env python3
"""FU-ONE-SPEND-QUESTION: the client is asked about money exactly once, on the
choice card, with the real price. Story questions never mention money.

Run: python3 core/choice_card/intake_card/test_one_spend_question.py
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "intake_preflight"))
from choice_card.intake_card import intake_card as IC  # noqa: E402
import intake as I  # noqa: E402

MONEY = re.compile(r"spend|budget|cost|price|\$|dollar", re.I)
N = len(IC.QUESTIONS)
SPEND_AT = [q["id"] for q in IC.QUESTIONS].index("spend")
BEFORE = ["1"] * SPEND_AT


def _qs(price=None, limit=None):
    return [IC.spend_question(price, limit) if q["id"] == "spend" else q for q in IC.QUESTIONS]


def test_no_story_question_mentions_money():
    briefs = [{}, {"offer": "x"}, {"offer": "my book at example.com"},
              {"offer": "x", "audience": "a", "action": "visit example.com"}]
    for b in briefs:
        r = I.evaluate(b, {})
        for q in r.get("questions") or []:
            assert not MONEY.search(q["question"]), (b, q)
            assert q["id"] != "spending_authority", (b, q)
        assert not MONEY.search(r.get("question_message") or ""), (b, r["question_message"])


def test_card_asks_money_exactly_once():
    qs = _qs(18.5)
    asks = [m for i in range(N) for m in [IC.render_step(i + 1, qs)] if "most you want to spend on this video" in m]
    assert len(asks) == 1 and asks[0].startswith("Question %d of %d - BUDGET" % (SPEND_AT + 1, N))
    assert IC.render_card(qs).count("most you want to spend on this video") == 1
    assert sum(q["id"] == "spend" for q in qs) == 1


def test_real_dollar_figure_in_option_one():
    msg = IC.render_step(SPEND_AT + 1, _qs(18.5))
    assert "1. $18.50 - the estimated price for your video, including a 20% allowance for redoing shots (RECOMMENDED)" in msg, msg
    assert "2. A different maximum - reply with a dollar amount, like $25" in msg
    assert "price on the card" not in msg.lower()


def test_brief_limit_is_option_one_and_price_second():
    q = IC.spend_question(18.5, 25, True)
    assert q["options"][0] == ("Your max: $25.00", "from your brief")
    assert q["options"][1][0] == "$18.50" and q["options"][2][0] == "A different maximum"
    st = IC.conversation(BEFORE + ["1"], _qs(18.5, 25))
    assert st["answers"][SPEND_AT]["value"] == "25"          # option 1 is the brief limit
    st = IC.conversation(BEFORE + ["2"], _qs(18.5, 25))
    assert st["answers"][SPEND_AT]["value"] == "18.5"
    st = IC.conversation(BEFORE + ["40"], _qs(18.5, 25))
    assert st["answers"][SPEND_AT]["value"] == "40" and st["answers"][SPEND_AT]["n"] == 3


def test_no_reply_means_no_spend():
    for qs in (_qs(), _qs(18.5), _qs(18.5, 25)):
        st = IC.conversation(BEFORE, qs)                      # never answered
        assert len(st["answers"]) == SPEND_AT and not st["done"]
        assert st["message"].startswith("Question %d of" % (SPEND_AT + 1))
        for junk in ("maybe", "", "free"):
            st = IC.conversation(BEFORE + [junk], qs)
            assert len(st["answers"]) == SPEND_AT and st["message"].startswith("Sorry")
    # with no price known, a bare number or "yes" is not an amount
    for r in ("1", "yes", "recommended"):
        assert len(IC.conversation(BEFORE + [r], _qs())["answers"]) == SPEND_AT, r
    # everything else answered but spend skipped via recap yes: still not done
    full = IC.conversation(BEFORE + ["$25"] + ["1"] * (N - SPEND_AT - 1), _qs())
    assert not full["done"] and full["message"].startswith("Here is what you picked:")
    assert not IC.conversation(BEFORE + ["maybe", "yes"], _qs())["done"]


def test_recap_shows_the_limit():
    full = ["1"] * N
    full[SPEND_AT] = "1"
    recap = IC.conversation(full, _qs(18.5, 25))["message"]
    assert "Budget: up to $25.00" in recap, recap
    recap = IC.conversation(full, _qs(18.5))["message"]
    assert "Budget: up to $18.50" in recap, recap


def test_no_price_no_limit_recommends_nothing_and_asks_for_a_dollar_amount():
    qs = _qs()
    q = qs[SPEND_AT]
    assert q["recommended"] is None
    msg = IC.render_step(SPEND_AT + 1, qs)
    assert "RECOMMENDED" not in msg and "I recommend" not in msg and "dollar amount" in msg, msg
    card = IC.render_card(qs)
    assert "all recommended" not in card, card
    assert "all recommended" not in " ".join(IC.render_messages(qs))
    # the other questions still show their recommended mark; with a price, the shortcut returns
    assert "(RECOMMENDED)" in card and "all recommended" in IC.render_card(_qs(18.5))
    for r in ("recommended", "yes", "1"):
        assert len(IC.conversation(BEFORE + [r], qs)["answers"]) == SPEND_AT, r


def _ask(price=None, limit=None, from_brief=False):
    m = IC.render_step(SPEND_AT + 1, [IC.spend_question(price, limit, from_brief) if q["id"] == "spend" else q for q in IC.QUESTIONS])
    return m[m.index("What's the most"):m.index("\n\nI recommend") if "\n\nI recommend" in m else None].strip()


def test_exact_rendering_four_cases():
    ask = "What's the most you want to spend on this video?"
    price = "$18.50 - the estimated price for your video, including a 20% allowance for redoing shots"
    other = "A different maximum - reply with a dollar amount, like $25"
    assert _ask(18.5, 40, True) == "\n".join([ask, "1. Your max: $40.00 - from your brief (RECOMMENDED)", "2. " + price, "3. " + other])
    assert _ask(18.5) == "\n".join([ask, "1. " + price + " (RECOMMENDED)", "2. " + other])
    assert _ask() == "\n".join([ask + " Reply with a dollar amount, like $25.", "1. " + other, "", "Reply with a dollar amount, like $25."])
    assert _ask(18.5, 30, False) == "\n".join([ask, "1. Your max: $30.00 (RECOMMENDED)", "2. " + price, "3. " + other])
    for m in (_ask(18.5, 40, True), _ask(), "".join(QUESTION_TEXT())):
        assert " ad" not in m.lower().replace("ad.", "x"), m


def QUESTION_TEXT():
    return [IC.spend_question(18.5, 40, True)["ask"], IC.spend_question()["ask"]]


def test_recap_line_exact():
    recap = IC.conversation(["1"] * N, _qs(18.5, 25))["message"]
    assert "5. Budget: up to $25.00\n" in recap and "Spend" not in recap, recap


def _factory(*args):
    f = os.path.join(CORE, "intake_preflight", "factory.py")
    return subprocess.run([sys.executable, f, "card", "--step"] + list(args)
                          + [x for r in BEFORE for x in ("--reply", r)],
                          capture_output=True, text=True).stdout


def test_factory_card_picks_up_brief_limit_without_flag():
    import json, tempfile
    out = _factory("--price", "18.5", "--brief", json.dumps({"budget_minor": 4000}))
    assert "1. Your max: $40.00 - from your brief (RECOMMENDED)" in out and "2. $18.50 - the estimated price for your video" in out, out
    with tempfile.TemporaryDirectory() as d:
        sf = os.path.join(d, "summary.json")
        json.dump({"data": {"summary": {"generation_ceiling": {"amount_minor": 2550, "currency": "usd"}}}},
                  open(sf, "w"))
        assert "1. Your max: $25.50 - from your brief" in _factory("--summary-file", sf)
        bf = os.path.join(d, "brief.json")
        json.dump({"budget_minor": 4000}, open(bf, "w"))
        assert "1. Your max: $40.00 - from your brief" in _factory("--brief-file", bf)
    # --limit overrides; credits or no amount leave the client to type one
    ov = _factory("--limit", "10", "--brief", '{"budget_minor": 4000}')
    assert "1. Your max: $10.00 (RECOMMENDED)" in ov and "from your brief" not in ov, ov
    assert "Your max" not in _factory("--brief", '{"budget_minor": 4000, "budget_currency": "credits"}')
    assert "Your max" not in _factory("--brief", "{}")


def test_cli_passes_price_and_limit():
    s = os.path.join(HERE, "intake_card.py")
    out = subprocess.run([sys.executable, s, "--step", "--price", "18.5", "--limit", "25"]
                         + [x for r in BEFORE for x in ("--reply", r)],
                         capture_output=True, text=True).stdout
    assert "1. Your max: $25.00 (RECOMMENDED)" in out and "from your brief" not in out and "2. $18.50 - the estimated price" in out, out


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
