#!/usr/bin/env python3
"""H9 tests: the intake card keeps one question per block, one option per line,
a blank line between questions, and the send payloads keep those newlines.

Run: python3 core/choice_card/intake_card/test_intake_card_h9.py

SWI-002 (SPEC item 10): this file is also the companion test that encodes the
card's total. The card prints its own total from len(QUESTIONS); this file is
the one place the number 14 is written down, and it fails every string in the
three card-facing files that claims a different one.
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, CORE)
from choice_card.intake_card import intake_card as IC  # noqa: E402

N = len(IC.QUESTIONS)
CARD = IC.render_card()


def _blocks(text):
    return text.split("\n\n")


def test_fourteen_questions_each_own_block():
    assert N == 14                                  # five story brief + nine production choices
    blocks = _blocks(CARD)
    assert len(blocks) == N + 1                       # fourteen questions + closing
    for i, b in enumerate(blocks[:N], 1):
        first = b.split("\n")[0]
        assert first.startswith("Question %d of %d - " % (i, N)), first
    labels = [b.split("\n")[0].split(" - ")[1] for b in blocks[:N]]
    assert labels == ["OFFER", "OFFER LINK", "AUDIENCE", "CHARACTER", "PHOTOS",
                      "AI MODELS", "LENGTH", "MUSIC STYLE", "VIDEO STYLE", "VIDEO MODEL",
                      "BUDGET", "STORYBOARD APPROVAL", "SONG APPROVAL", "SCRIPT APPROVAL"]


def test_each_option_on_its_own_numbered_line_recommended_marked():
    for q, b in zip(IC.QUESTIONS, _blocks(CARD)):
        if q.get("free_text"):              # a brief block has no menu to number
            assert b.split("\n")[-1] == IC.FREE_TEXT_HINT, b
            continue
        lines = b.split("\n")
        opts = [l for l in lines[2:] if not l.startswith("   Watch: ")]   # sample links sit under their option
        assert len(opts) == len(q["options"])
        for n, line in enumerate(opts, 1):
            label, description = q["options"][n - 1]
            if description:
                assert re.match(r"^%d\. .+ - .+[.)\d]$" % n, line), line  # a priced line ends in the dollar figure
            else:
                expected = "%d. %s" % (n, label)
                if n - 1 == q.get("recommended"):
                    expected += " " + q.get("rec_mark", IC.REC)
                assert line == expected, line     # no unapproved description is invented
            assert "\n" not in line
        if q["recommended"] is None:        # unpriced BUDGET: nothing to recommend
            assert not any(IC.REC in l for l in opts)
            continue
        assert sum(IC.REC in l for l in opts) == 1
        assert IC.REC in opts[q["recommended"]]


def test_closing_line_last():
    assert _blocks(CARD)[-1] == IC._closing(IC.QUESTIONS)
    assert CARD.startswith("Question 1 of 14")


def test_no_markup_that_a_sender_could_strip():
    assert not re.search(r"[*_`<>]|\\n", CARD)


def test_messages_under_limit_and_split_between_questions():
    one = IC.render_messages()
    # fourteen questions no longer fit one Telegram message; they split only on
    # the blank-line seams, so joining them back gives the whole card.
    assert "\n\n".join(one) == CARD and all(len(m) <= IC.TELEGRAM_LIMIT for m in one)
    # 1000 not 400: the video question now carries five sample links (FU-STYLE-QUESTIONS)
    small = IC.render_messages(limit=1000)
    assert len(small) > 1
    assert all(len(m) <= 1000 for m in small)
    assert "\n\n".join(small) == CARD         # only blank-line seams were cut
    for m in small:                       # never starts a message mid-question
        assert m.startswith("Question") or m == IC._closing(IC.QUESTIONS)
    # a single oversize question still splits on line boundaries
    models = next(q for q in IC.QUESTIONS if q["id"] == "models")
    big = [dict(models, options=[("Opt %d" % i, "x" * 60) for i in range(80)])]
    parts = IC.render_messages(big, limit=500)
    assert all(len(p) <= 500 for p in parts) and len(parts) > 1


def test_telegram_payload_keeps_newlines():
    for m in IC.render_messages(limit=500):
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


def test_format_questions_one_text_is_one_unnumbered_message():
    """Trevor 2026-10-21: one question per message, so a single text carries no
    "Question 1 of 1" counter and no "one answer per question" line."""
    one = IC.format_questions(["What product?"])
    assert one.split("\n\n")[0] == "What product?", repr(one)
    assert "Question " not in one and "per question" not in one, repr(one)


def test_intake_question_message_uses_it():
    sys.path.insert(0, os.path.join(CORE, "intake_preflight"))
    import intake as I  # noqa: E402
    r = I.evaluate({}, {}, None, "h9")
    m = r["question_message"]
    # One question per message: the message IS the one question, unnumbered.
    assert len(r["questions"]) == 1, repr(r["questions"])
    assert m and m.startswith(r["questions"][0]["question"]), repr(m)
    assert "Question 1 of" not in m, repr(m)


def test_closing_example_answer_count_matches_question_count():
    # The "like a, a, a" example belongs to the all-choice card; a card with a
    # typed question closes with its own sentence instead (see below).
    choices = [q for q in IC.QUESTIONS if not q.get("free_text")]
    for qs in (choices, choices[:-1] + [dict(choices[-1], recommended=None)],
               choices + [choices[0]]):
        ex = re.search(r'like "([^"]+)"', IC._closing(qs)).group(1)
        assert len(ex.split(", ")) == len(qs)


def test_a_card_with_typed_questions_closes_with_its_own_sentence():
    closing = IC._closing(IC.QUESTIONS)
    assert closing.startswith("How to answer: type your own words for Offer, Offer Link, "
                               "Audience, Character, Photos"), closing
    # the unpriced BUDGET has nothing to recommend, so the shortcut stays off
    assert "all recommended" not in closing, closing
    priced = [IC.spend_question(18.5) if q["id"] == "spend" else q for q in IC.QUESTIONS]
    assert 'Say "all recommended"' in IC._closing(priced)
    assert IC.CLOSING_LINE == IC._closing(IC.QUESTIONS)     # the exported line is the real one


# --- SWI-002: the companion test that encodes 14 -------------------------------
#: The card's total, written down ONCE, here. Every string the client or the
#: operator reads is printed from len(QUESTIONS) instead, so this literal is
#: the assertion the card is held to -- never a second source of the answer.
CARD_TOTAL = 14

#: Numbers that can read as a card total in prose. "one" is deliberately absent:
#: "one question per message" is not a total and must never be scored as one.
_CARD_NUMBERS = {"zero": 0, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                 "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
                 "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
                 "nineteen": 19, "twenty": 20}
_NUMBER = r"(?:\d+|" + "|".join(sorted(_CARD_NUMBERS, key=len, reverse=True)) + r")"
#: The shapes this codebase uses to state a card total: "N questions",
#: "six-question", "N production choices", "N with a saved character", and the
#: header's own "Question i of N". One word may sit between the number and the
#: noun ("five story-brief questions"); "one question per message" stays out
#: because "one" is not in _CARD_NUMBERS.
_CLAIM_PATTERNS = (r"\b" + _NUMBER + r"(?:\s+[\w-]+)?[\s-]+questions?\b",
                   r"\bquestion\s+\d+\s+of\s+(\d+)\b",
                   r"\b" + _NUMBER + r"(?:\s+[\w-]+)?[\s-]+(?:production\s+)?choices\b",
                   r"\b" + _NUMBER + r"\s+with a saved character\b")


def _count_claims(text):
    """(value, matched text) for every card total written as a literal in text."""
    found = []
    for pattern in _CLAIM_PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            if m.lastindex:                       # "Question i of N" carries only N
                found.append((int(m.group(1)), m.group(0)))
                continue
            raw = m.group(0)
            digits = re.match(r"\d+", raw)
            word = re.search(r"[a-z]+", raw, re.I).group(0).lower()
            found.append((int(digits.group(0)) if digits else _CARD_NUMBERS[word], raw))
    return found


def _capture_help(runner, argv):
    """What --help prints, whitespace flattened (argparse exits 0 on --help and
    wraps long help to the terminal width, which would split a count claim)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            runner(argv)
        except SystemExit:
            pass
    return re.sub(r"\s+", " ", buf.getvalue())


def test_the_card_renders_exactly_fourteen_questions():
    assert CARD_TOTAL == 14                         # the number this file encodes
    assert len(IC.QUESTIONS) == CARD_TOTAL          # module count
    headers = re.findall(r"^Question (\d+) of (\d+) - ", CARD, re.M)
    assert len(headers) == CARD_TOTAL               # rendered count == module count
    assert {n for _, n in headers} == {str(CARD_TOTAL)}
    assert [int(i) for i, _ in headers] == list(range(1, CARD_TOTAL + 1))
    assert IC.studio_json()["question_count"] == CARD_TOTAL   # third surface, same list


def test_a_saved_character_swaps_in_and_never_moves_the_total():
    # both --help strings promise "the same total with a saved character".
    with tempfile.TemporaryDirectory() as tmp:
        client, empty = os.path.join(tmp, "client-a"), os.path.join(tmp, "client-b")
        img = os.path.join(tmp, "face.png")
        with open(img, "wb") as fh:
            fh.write(b"\x89PNG-fake-bytes")
        from character_library import character_library as CL   # noqa: PLC0415
        CL.save_character(client, "Maya Lee", "Warm, 40s, silver braids.", [img])
        assert CL.saved_character_question(client), "fixture saved no character"
        assert len(IC._with_saved_character(client)) == CARD_TOTAL
        assert len(IC._with_saved_character(empty)) == CARD_TOTAL   # NO_SAVED_LINE preface
    assert len(IC._with_saved_character("")) == CARD_TOTAL          # no folder at all


def test_the_help_strings_state_the_live_total_and_no_other():
    card_help = _capture_help(IC.main, ["--help"])
    assert "(%d questions" % N in card_help, card_help
    for value, hit in _count_claims(card_help):
        assert value == N, "intake_card --help claims %r, the card says %d" % (hit, N)

    sys.path.insert(0, os.path.join(CORE, "intake_preflight"))
    import factory  # noqa: PLC0415, E402 -- the sub-parser help lives here
    root_help = _capture_help(factory.main, ["--help"])
    assert "(%d questions" % N in root_help, root_help
    for value, hit in _count_claims(root_help):
        assert value == N, "factory --help claims %r, the card says %d" % (hit, N)


def test_the_init_docstring_claims_no_other_total():
    import choice_card.intake_card as package  # noqa: PLC0415, E402
    doc = re.sub(r"\s+", " ", package.__doc__ or "")
    assert "questions" in doc                   # it still says what it holds
    for value, hit in _count_claims(doc):
        assert value == N, "the package docstring claims %r, the card says %d" % (hit, N)


def test_the_card_string_sources_hold_no_other_total():
    """The hard guard: re-introduce a hardcoded total anywhere in the three
    card-facing files and this goes red on the exact line."""
    paths = (os.path.join(CORE, "choice_card", "intake_card", "__init__.py"),
             os.path.join(HERE, "intake_card.py"),
             os.path.join(CORE, "intake_preflight", "factory.py"))
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line_no, line in enumerate(fh.read().splitlines(), 1):
                for value, hit in _count_claims(line):
                    assert value == N, "%s:%d claims %r; the card says %d" % (
                        os.path.basename(path), line_no, hit, N)


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
