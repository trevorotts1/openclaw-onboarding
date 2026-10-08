#!/usr/bin/env python3
"""intake_card: the six intake questions as a card a client can read (H9).

Trevor 2026-10-08: the questions arrived "smashed together, no spaces, nothing
on different lines". Cause: nothing built the card -- the agent wrote it free
hand, the JSON envelope carried it as one escaped string, and the only joiner
(``"\\n".join``) gave no blank line between questions. This module is the one
place the text is built, with a fixed layout:

    Question 1 of 6 - LENGTH
    How long should the ad be?
    1. 60 seconds - one sentence. (RECOMMENDED)
    2. 90 seconds - one sentence.
    <blank line>
    ...
    How to answer: reply with one number per question ...

Plain text only: no Markdown, no HTML, no parse mode, so nothing is stripped
or escaped on the way out. ``render_messages`` splits on question boundaries
under Telegram's 4096-character limit. ``telegram_payload`` and
``openclaw_send_argv`` build the exact send payloads with the text untouched
(an argv list, never a shell string, so no shell flattens the newlines).

Stdlib only. No network: this module builds text, it never sends.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

#: Telegram's hard limit is 4096 characters per message; stay under it.
TELEGRAM_LIMIT = 4000

CLOSING_LINE = ('How to answer: reply with one number per question, in order, '
                'like "1, 1, 1, 1, 1, 1". Say "all recommended" to take every '
                'RECOMMENDED choice.')

REC = "(RECOMMENDED)"

#: (label, question, [(option, one short sentence)], recommended option index)
#: Looks and music come from the choice-card modules so the menu cannot drift.
#: Short plain sentences (the library descriptions are build notes, not client text).
_LOOK_SENTENCE = {
    "lifelike-3d": "Cinematic, lifelike animated people.",
    "2d-hand-painted": "A hand-painted cartoon look.",
    "sketch-to-life": "A pencil sketch that turns into real footage.",
    "canvas-to-life": "A painted cartoon that turns into real footage.",
    "canvas-to-3d": "A painted cartoon that turns into lifelike 3D.",
}
_MUSIC_SENTENCE = {
    "soul-ballad": "Slow, emotional, soulful singing.",
    "rnb-flow": "Smooth R&B with a catchy sung hook.",
    "soul-rise": "Starts soulful and lifts into an upbeat groove.",
}


def _menu(ids, labels, sentences):
    return [(labels[i], sentences[i]) for i in ids]


def _looks():
    from choice_card.looks import looks as L
    return _menu(L.LOOK_ORDER, L.LOOK_LABELS, _LOOK_SENTENCE)


def _musics():
    from music_styles import music_styles as MS
    return _menu(list(_MUSIC_SENTENCE), {k: MS.STYLES[k]["label"] for k in _MUSIC_SENTENCE},
                 _MUSIC_SENTENCE)


def _questions():
    return [
        {"id": "length", "label": "LENGTH", "ask": "How long should the ad be?",
         "options": [("60 seconds", "The standard ad length."),
                     ("90 seconds", "Room for a fuller story."),
                     ("3 minutes", "A short film."),
                     ("5 minutes", "A long story, with automatic 60 and 90 second clips."),
                     ("10-minute long version", "The full-length cut, with automatic clips.")],
         "recommended": 0},
        {"id": "music", "label": "MUSIC STYLE", "ask": "What should the song sound like?",
         "options": _musics(), "recommended": 0},
        {"id": "look", "label": "VIDEO STYLE", "ask": "What should the video look like?",
         "options": _looks(), "recommended": 0},
        {"id": "model", "label": "VIDEO MODEL", "ask": "Which video model should make the shots?",
         "options": [("MiniMax H3, 768P", "Best balance of quality and price."),
                     ("Show me every model and its price", "I will list them, then you pick.")],
         "recommended": 0},
        {"id": "spend", "label": "SPEND LIMIT",
         "ask": "What is the most you want to spend on this ad?",
         "options": [("The price on the card", "Includes a 20% allowance for redoing shots."),
                     ("My own limit", "Reply with a dollar amount, for example $25.")],
         "recommended": 0},
        {"id": "storyboard", "label": "STORYBOARD APPROVAL",
         "ask": "Do you want to approve the storyboard before any video is made?",
         "options": [("Yes, show me first", "Nothing is generated until you say go."),
                     ("No, just make it", "I start as soon as the card is approved.")],
         "recommended": 0},
    ]


QUESTIONS = _questions()


def _block(i, total, q):
    lines = ["Question %d of %d - %s" % (i, total, q["label"]), q["ask"]]
    for n, (opt, sentence) in enumerate(q["options"], 1):
        mark = (" " + REC) if n - 1 == q.get("recommended") else ""
        lines.append("%d. %s - %s%s" % (n, opt, sentence, mark))
    return "\n".join(lines)


def _blocks(questions):
    return [_block(i, len(questions), q) for i, q in enumerate(questions, 1)]


def render_card(questions=None):
    """The whole card as one string: blank line between questions, closing line."""
    qs = questions or QUESTIONS
    return "\n\n".join(_blocks(qs) + [CLOSING_LINE])


def format_questions(texts):
    """Plain question strings -> numbered, blank-line separated message.

    Used by intake / intake_book for their ``question_message`` so those
    questions get the same layout (one per line group, blank line between).
    """
    texts = [t for t in texts if t]
    if not texts:
        return None
    blocks = ["Question %d of %d\n%s" % (i, len(texts), t)
              for i, t in enumerate(texts, 1)]
    return "\n\n".join(blocks + ["Reply with one answer per question, in order."])


def _split_long(block, limit):
    """A block over the limit splits on line boundaries, never mid-line."""
    out, cur = [], ""
    for line in block.split("\n"):
        cand = cur + "\n" + line if cur else line
        if len(cand) > limit and cur:
            out.append(cur)
            cur = line
        else:
            cur = cand
    return out + ([cur] if cur else [])


def render_messages(questions=None, limit=TELEGRAM_LIMIT):
    """The card as a list of messages, each <= limit chars, split only between
    questions (one message per question when they do not all fit)."""
    parts = []
    for b in _blocks(questions or QUESTIONS) + [CLOSING_LINE]:
        parts.extend(_split_long(b, limit) if len(b) > limit else [b])
    msgs, cur = [], ""
    for p in parts:
        cand = cur + "\n\n" + p if cur else p
        if len(cand) > limit and cur:
            msgs.append(cur)
            cur = p
        else:
            cur = cand
    return msgs + ([cur] if cur else [])


def telegram_payload(chat_id, text):
    """Exact JSON body for the Bot API ``sendMessage``. No ``parse_mode`` on
    purpose: with none, Telegram shows the text verbatim, newlines included."""
    return {"chat_id": chat_id, "text": text}


def openclaw_send_argv(target, text):
    """Exact argv for ``openclaw message send`` on Telegram. A list, not a
    shell string: run it with subprocess (shell=False) and the newlines in
    ``text`` reach the sender untouched."""
    return ["openclaw", "message", "send", "--channel", "telegram",
            "--target", str(target), "--message", text]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Print the six-question intake card.")
    ap.add_argument("--format", choices=("text", "openclaw-json", "telegram-json"),
                    default="text",
                    help="text: raw card for the Claude Code chat. "
                         "openclaw-json / telegram-json: one send payload per message.")
    ap.add_argument("--target", default="", help="Telegram chat id (send formats)")
    a = ap.parse_args(argv)
    if a.format == "text":
        sys.stdout.write(render_card() + "\n")      # raw newlines, no JSON escaping
        return 0
    msgs = render_messages()
    if a.format == "openclaw-json":
        out = [openclaw_send_argv(a.target, m) for m in msgs]
    else:
        out = [telegram_payload(a.target, m) for m in msgs]
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
