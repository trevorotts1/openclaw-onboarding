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
    asks = [m for i in range(N) for m in [IC.render_step(i + 1, qs)] if "OK spending" in m]
    assert len(asks) == 1 and asks[0].startswith("Question %d of %d - SPEND LIMIT" % (SPEND_AT + 1, N))
    assert IC.render_card(qs).count("OK spending") == 1
    assert sum(q["id"] == "spend" for q in qs) == 1


def test_real_dollar_figure_in_option_one():
    msg = IC.render_step(SPEND_AT + 1, _qs(18.5))
    assert "1. $18.50 - the price shown above (includes a 20% allowance for redoing shots)" in msg, msg
    assert "A different limit - reply with a dollar amount, like $25" in msg
    assert "price on the card" not in msg.lower()


def test_brief_limit_is_option_one_and_price_second():
    q = IC.spend_question(18.5, 25)
    assert q["options"][0] == ("Your limit: $25.00", "from your brief")
    assert q["options"][1][0] == "$18.50" and q["options"][2][0] == "A different limit"
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
    assert "Spend Limit: Your limit: $25.00" in recap, recap
    recap = IC.conversation(full, _qs(18.5))["message"]
    assert "Spend Limit: $18.50" in recap, recap


def test_cli_passes_price_and_limit():
    s = os.path.join(HERE, "intake_card.py")
    out = subprocess.run([sys.executable, s, "--step", "--price", "18.5", "--limit", "25"]
                         + [x for r in BEFORE for x in ("--reply", r)],
                         capture_output=True, text=True).stdout
    assert "1. Your limit: $25.00 - from your brief" in out and "2. $18.50 - the price shown above" in out, out


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
