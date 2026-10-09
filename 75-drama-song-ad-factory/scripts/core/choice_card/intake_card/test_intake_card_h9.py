#!/usr/bin/env python3
"""H9 tests: the intake card keeps one question per block, one option per line,
a blank line between questions, and the send payloads keep those newlines.

Run: python3 core/choice_card/intake_card/test_intake_card_h9.py
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, CORE)
from choice_card.intake_card import intake_card as IC  # noqa: E402

N = len(IC.QUESTIONS)
CARD = IC.render_card()


def _blocks(text):
    return text.split("\n\n")


def test_six_questions_each_own_block():
    assert N == 6
    blocks = _blocks(CARD)
    assert len(blocks) == N + 1                       # six questions + closing
    for i, b in enumerate(blocks[:N], 1):
        first = b.split("\n")[0]
        assert first.startswith("Question %d of %d - " % (i, N)), first
    labels = [b.split("\n")[0].split(" - ")[1] for b in blocks[:N]]
    assert labels == ["LENGTH", "MUSIC STYLE", "VIDEO STYLE", "VIDEO MODEL",
                      "SPEND LIMIT", "STORYBOARD APPROVAL"]


def test_each_option_on_its_own_numbered_line_recommended_marked():
    for q, b in zip(IC.QUESTIONS, _blocks(CARD)):
        lines = b.split("\n")
        opts = lines[2:]
        assert len(opts) == len(q["options"])
        for n, line in enumerate(opts, 1):
            assert re.match(r"^%d\. .+ - .+(?:[.)]|\d)$" % n, line), line
            assert "\n" not in line
        if q["recommended"] is None:        # unpriced SPEND LIMIT: nothing to recommend
            assert not any(IC.REC in l for l in opts)
            continue
        assert sum(IC.REC in l for l in opts) == 1
        assert IC.REC in opts[q["recommended"]]


def test_closing_line_last():
    assert _blocks(CARD)[-1] == IC._closing(IC.QUESTIONS)
    assert CARD.startswith("Question 1 of 6")


def test_no_markup_that_a_sender_could_strip():
    assert not re.search(r"[*_`<>]|\\n", CARD)


def test_messages_under_limit_and_split_between_questions():
    one = IC.render_messages()
    assert len(one) == 1 and one[0] == CARD
    small = IC.render_messages(limit=400)
    assert len(small) > 1
    assert all(len(m) <= 400 for m in small)
    assert "\n\n".join(small) == CARD         # only blank-line seams were cut
    for m in small:                       # never starts a message mid-question
        assert m.startswith("Question") or m == IC.CLOSING_LINE
    # a single oversize question still splits on line boundaries
    big = [dict(IC.QUESTIONS[0], options=[("Opt %d" % i, "x" * 60) for i in range(80)])]
    parts = IC.render_messages(big, limit=500)
    assert all(len(p) <= 500 for p in parts) and len(parts) > 1


def test_telegram_payload_keeps_newlines():
    for m in IC.render_messages(limit=400):
        body = json.loads(json.dumps(IC.telegram_payload("123", m)))
        assert body["text"] == m and body["text"].count("\n") == m.count("\n")
        assert "parse_mode" not in body and len(body["text"]) <= 4096
    assert "\n" in IC.telegram_payload("1", CARD)["text"]


def test_openclaw_argv_keeps_newlines_through_a_real_subprocess():
    argv = IC.openclaw_send_argv("123", CARD)
    assert argv[:6] == ["openclaw", "message", "send", "--channel", "telegram", "--target"]
    msg = argv[argv.index("--message") + 1]
    # round-trip through a real process boundary (no shell): echo argv back
    out = subprocess.run([sys.executable, "-c", "import sys;sys.stdout.write(sys.argv[1])", msg],
                         capture_output=True, text=True, check=True).stdout
    assert out == CARD and out.count("\n") == CARD.count("\n")


def test_cli_text_is_raw_newlines_and_json_formats():
    script = os.path.join(HERE, "intake_card.py")
    raw = subprocess.run([sys.executable, script], capture_output=True, text=True).stdout
    assert raw == CARD + "\n" and "\\n" not in raw
    js = json.loads(subprocess.run([sys.executable, script, "--format", "openclaw-json",
                                    "--target", "9"], capture_output=True, text=True).stdout)
    assert js[0][-1].count("\n") > 10


def test_format_questions_blank_line_between():
    msg = IC.format_questions(["What product?", "Who is it for?", "How much?"])
    assert msg.split("\n\n")[0] == "Question 1 of 3\nWhat product?"
    assert len(msg.split("\n\n")) == 4 and IC.format_questions([]) is None


def test_intake_question_message_uses_it():
    sys.path.insert(0, os.path.join(CORE, "intake_preflight"))
    import intake as I  # noqa: E402
    r = I.evaluate({}, {}, None, "h9")
    m = r["question_message"]
    assert m and "\n\n" in m and m.count("Question ") == len(r["questions"])


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
