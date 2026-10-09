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
        {"id": "length", "why": "Length decides the story size and the price.", "reason": "the standard length for ads, and it fits stories, reels and ads.", "label": "LENGTH", "ask": "How long do you want your ad to be? The longer ads also come with short clips you can post on social media.",
         "options": [("60 seconds", "The standard ad length."),
                     ("90 seconds", "Room for a fuller story."),
                     ("3 minutes + 60s and 90s clips", "Plus a 60-second clip and a 90-second clip."),
                     ("5 minutes + 60s and 90s clips", "Plus a 60-second clip and a 90-second clip."),
                     ("10 minutes (the long version) + 60s and 90s clips", "Plus a 60-second clip and a 90-second clip.")],
         "recommended": 0},
        {"id": "music", "why": "The song carries the feeling of the whole ad.", "reason": "it is the style that tests best for emotional stories.", "label": "MUSIC STYLE", "ask": "What should the song sound like?",
         "options": _musics(), "recommended": 0},
        {"id": "look", "why": "The look is what viewers see in every shot.", "reason": "it gives the most real, cinematic result.", "label": "VIDEO STYLE", "ask": "What should the video look like?",
         "options": _looks(), "recommended": 0},
        {"id": "model", "why": "The video model sets how good the shots look and what they cost.", "reason": "it gives the best balance of quality and price.", "label": "VIDEO MODEL", "ask": "Which video model should make the shots?",
         "options": [("MiniMax H3, 768P", "Best balance of quality and price."),
                     ("Show me every model and its price", "I will list them, then you pick.")],
         "recommended": 0},
        {"id": "spend", "why": "This keeps you in control of the cost.", "reason": "it already covers a 20% allowance for redoing shots.", "label": "SPEND LIMIT",
         "ask": "What is the most you want to spend on this ad?",
         "options": [("The price on the card", "Includes a 20% allowance for redoing shots."),
                     ("My own limit", "Reply with a dollar amount, for example $25.")],
         "recommended": 0},
        {"id": "storyboard", "why": "The storyboard is cheap to fix now and costly to fix after video is made.", "reason": "you see every scene before any money is spent on video.", "label": "STORYBOARD APPROVAL",
         "ask": "Do you want to approve the storyboard before any video is made?",
         "options": [("Yes, show me first", "Nothing is generated until you say go."),
                     ("No, just make it", "I start as soon as the card is approved.")],
         "recommended": 0},
    ]


QUESTIONS = _questions()


#: Shown once, before the first question, when the client has no saved characters.
NO_SAVED_LINE = ("You don't have any saved characters yet, so I'll create a new one "
                 "for this ad and save it for next time.")


def _block(i, total, q):
    if "body" in q:                       # saved-character question: fixed text
        return "\n".join(["Question %d of %d - %s" % (i, total, q["label"])] + q["body"])
    lines = ["Question %d of %d - %s" % (i, total, q["label"]), q["ask"]]
    for n, (opt, sentence) in enumerate(q["options"], 1):
        mark = (" " + REC) if n - 1 == q.get("recommended") else ""
        lines.append("%d. %s - %s%s" % (n, opt, sentence, mark))
    return "\n".join(lines)


def _blocks(questions):
    blocks = [_block(i, len(questions), q) for i, q in enumerate(questions, 1)]
    if questions and questions[0].get("preface"):
        blocks[0] = questions[0]["preface"] + "\n\n" + blocks[0]
    return blocks


def render_step(i, questions=None):
    """ONE question as its own message (Trevor 2026-10-08, I7): a one-sentence
    why, numbered options one per line, the RECOMMENDED one marked and
    explained, then how to answer."""
    qs = questions or QUESTIONS
    q = qs[i - 1]
    if "body" in q:
        return _block(i, len(qs), q)
    lines = ["Question %d of %d - %s" % (i, len(qs), q["label"]), q["why"], "", q["ask"]]
    for n, (opt, sentence) in enumerate(q["options"], 1):
        mark = (" " + REC) if n - 1 == q.get("recommended") else ""
        lines.append("%d. %s - %s%s" % (n, opt, sentence, mark))
    r = q.get("recommended", 0)
    lines += ["", "I recommend option %d (%s) because %s" % (r + 1, q["options"][r][0], q["reason"]),
              "Reply with a number, or say \"recommended\"."]
    return "\n".join(lines)


def render_recap(answers, questions=None):
    qs = questions or QUESTIONS
    lines = ["Here is what you picked:"]
    for i, (q, a) in enumerate(zip(qs, answers), 1):
        lines.append("%d. %s" % (i, q["recap"][a["n"] - 1] if "recap" in q
                                 else "%s: %s" % (q["label"].title(), a["text"])))
    lines += ["", 'Reply "yes" to start, or the number of a line to change it.']
    return "\n".join(lines)


_YES = ("yes", "y", "yep", "go", "ok", "okay", "start", "approve", "approved")


def _parse(reply, q):
    """Reply -> {"n": option number, "text": ..., "value": ...} or None."""
    t = (reply or "").strip().lower()
    opts = q["options"]
    if t in ("recommended", "recommend", "rec") or (t in _YES and len(opts) > 0):
        n = q.get("recommended", 0) + 1
    elif t.isdigit() and 1 <= int(t) <= len(opts):
        n = int(t)
    elif q["id"] == "spend" and t.lstrip("$").replace(".", "", 1).isdigit():
        return {"n": 2, "text": "up to $" + t.lstrip("$"), "value": t.lstrip("$")}
    else:
        return None
    return {"n": n, "text": opts[n - 1][0], "value": None}


def conversation(replies, questions=None):
    """Replay the client's replies from the start; return the state and the ONE
    message to send next. Stateless, so claude-nine and OpenClaw can both call
    it with the replies so far. state: answers, done, message."""
    qs = questions or QUESTIONS
    answers, fix, note, done = [], None, "", False
    for r in replies:
        note = ""
        if len(answers) < len(qs) and fix is None:
            a = _parse(r, qs[len(answers)])
            if a:
                answers.append(a)
            else:
                note = "Sorry, I did not catch that. "
        elif fix is not None:                       # re-answering one line
            a = _parse(r, qs[fix])
            if a:
                answers[fix], fix = a, None
            else:
                note = "Sorry, I did not catch that. "
        else:                                       # recap: yes, or a line number
            t = r.strip().lower()
            if t in _YES:
                done = True
            elif t.isdigit() and 1 <= int(t) <= len(qs):
                fix = int(t) - 1
            else:
                note = "Sorry, I did not catch that. "
    if done:
        msg = "Locked in. I am starting now."
    elif fix is not None:
        msg = note + render_step(fix + 1, qs)
    elif len(answers) < len(qs):
        msg = note + render_step(len(answers) + 1, qs)
        if not replies and qs[0].get("preface"):
            msg = qs[0]["preface"] + "\n\n" + msg
    else:
        msg = note + render_recap(answers, qs)
    return {"answers": answers, "done": done, "message": msg}


def render_card(questions=None, book_plan=None, notes=()):
    """The whole card as one string: blank line between questions, closing line.

    FU-U11: a book card also carries the Book shots APPROVAL BLOCK. It shows
    approvals and notices only -- it adds no question and no option, so the
    card's answer shape (one number per question, then yes) is unchanged.
    """
    qs = questions or QUESTIONS
    blocks = _blocks(qs) + [CLOSING_LINE]
    book = _book_block(book_plan, notes)
    if book:
        blocks = blocks + book
    return "\n\n".join(blocks)


def _book_block(book_plan, notes=()):
    """FU-U11: the Book shots approval block, or [] for a non-book card."""
    if not book_plan:
        return []
    _core = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    if _core not in sys.path:
        sys.path.insert(0, _core)
    try:
        from book_shot import book_shot as BS
    except ImportError:
        return ["Book shots: the book plan is present but the book module "
                "could not be loaded, so its rows cannot be shown."]
    return ["\n".join(BS.plan_card_block(book_plan, notes))]


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


def render_messages(questions=None, limit=TELEGRAM_LIMIT, book_plan=None,
                    notes=()):
    """The card as a list of messages, each <= limit chars, split only between
    questions (one message per question when they do not all fit).

    FU-U11: a book card's approval block rides as its own message(s), after
    the closing line; it is never split mid-row unless a single row exceeds
    the limit.
    """
    parts = []
    for b in _blocks(questions or QUESTIONS) + [CLOSING_LINE] + \
            _book_block(book_plan, notes):
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


# --- FU-U4: the fit STOP card (registry-only options, plan 2.3) ----------------

FEWER_WORDS_ID = "fewer_words"


def _client_words(packet_lines):
    """[(line_id, word_count)] for the client's own lines, in order."""
    import protected_names as PN
    out = []
    for n, ln in enumerate(packet_lines or [], 1):
        lid = (ln.get("id") or ln.get("line_id")) if isinstance(ln, dict) else None
        text = ln.get("text", "") if isinstance(ln, dict) else str(ln)
        out.append((lid or "line %d" % n, len(PN._tokens(text))))
    return out


def _fit_row(style_id, length_s, words):
    """One style's numbers for the client's words at length_s. Rap styles may
    carry the words as spoken (intro/outro) plus rap; the others only as spoken
    in [Intro]/[Outro] (suno recipe rule 1)."""
    import length_formula as LF
    import words_fit as WF
    from music_styles import music_styles as MS
    plan = LF.plan(length_s, style_id=style_id)
    cap_spoken = plan["words"]["spoken"]
    cap_rap = plan["words"].get("rap", 0)
    rap_style = "rap" in MS.style(style_id)["deliveries"]
    spoken = min(words, cap_spoken) if rap_style else words
    rap = words - spoken if rap_style else 0
    planned_s = WF.planned_seconds(0, spoken, rap, rates=WF.rates_for(style_id))
    cap = cap_spoken + cap_rap
    return {"style_id": style_id, "label": MS.style(style_id)["label"],
            "length_s": length_s, "client_words": words, "capacity_words": cap,
            "split": {"sung": 0, "spoken": spoken, "rap": rap},
            "planned_s": round(planned_s, 1),
            "fits": words <= cap and planned_s <= length_s}


def assert_registry_options(card):
    """Refuse any card option whose id is not in the registries: lengths in
    music_styles.OFFERED_LENGTHS_S, styles in music_styles.style_ids(), voices
    in voice_velvet_echo, and the one words_fit fewer_words option."""
    import words_fit as WF
    from music_styles import music_styles as MS
    from voice_velvet_echo import velvet_voiceover as VV
    opts = card.get("options") or {}
    ok = {"longer_ad": set(MS.OFFERED_LENGTHS_S), "music_style": set(MS.style_ids()),
          "voice": {VV.ALL_SUNO_ID, VV.VELVET_ID}}
    for kind, allowed in ok.items():
        for o in opts.get(kind, []):
            if o.get("id") not in allowed:
                raise ValueError("FIT_CARD_OPTION_NOT_IN_REGISTRY %s option %r; allowed %s"
                                 % (kind, o.get("id"), sorted(allowed, key=str)))
    fw = opts.get(FEWER_WORDS_ID)
    if fw is not None and fw.get("id") not in WF.preflight(60, 0, 9999)["options"]:
        raise ValueError("FIT_CARD_OPTION_NOT_IN_REGISTRY fewer_words id %r" % (fw.get("id"),))
    return card


def fit_card(brief, packet_lines):
    """The STOP card for a client who brought their own lines: for each real
    music style, the numbers at the client's length; options only from the
    registries; notices for what the skill will not make. Free: no spend.
    outcome "ok" when the chosen style (brief.music, default Soul Ballad) fits,
    else "waiting" (exit 2). Nothing is cut: fewer_words names exact line ids
    for the client to approve."""
    from intake_preflight import intake as INT
    from music_styles import music_styles as MS
    from voice_velvet_echo import velvet_voiceover as VV
    import words_fit as WF
    brief = brief or {}
    packet_lines = brief.get("packet_lines") if packet_lines is None else packet_lines
    fields, _ = INT.normalize(brief)
    length_s = fields["target_length_s"]
    per_line = _client_words(packet_lines)
    words = sum(n for _, n in per_line)
    rows = [_fit_row(sid, length_s, words) for sid in MS.style_ids()]
    chosen = MS._style_key(fields["music"])
    crow = next(r for r in rows if r["style_id"] == chosen)
    longer = []
    for L in MS.OFFERED_LENGTHS_S:
        if L > length_s:
            fits = [r["style_id"] for r in (_fit_row(sid, L, words) for sid in MS.style_ids())
                    if r["fits"]]
            longer.append({"id": L, "fits_styles": fits})
    kept, cut = 0, []
    for lid, n in per_line:                       # keep from the top; the tail is named
        if kept + n <= crow["capacity_words"]:
            kept += n
        else:
            cut.append(lid)
    card = {
        "outcome": "ok" if crow["fits"] else "waiting",
        "reason_code": "FIT_OK" if crow["fits"] else "CLIENT_LINES_DO_NOT_FIT",
        "length_s": length_s, "chosen_style": chosen, "client_words": words,
        "rows": rows,
        "options": {
            "longer_ad": longer,
            "music_style": [{"id": r["style_id"], "fits": r["fits"]} for r in rows],
            "voice": [{"id": VV.ALL_SUNO_ID, "default": True}, {"id": VV.VELVET_ID}],
            FEWER_WORDS_ID: {"id": FEWER_WORDS_ID, "cut_line_ids": cut,
                             "cut_words": words - kept, "needs_client_approval": True},
        },
        "notices": INT.notices(brief, packet_lines),
    }
    assert_registry_options(card)
    card["text"] = _render_fit(card)
    return card


def _render_fit(card):
    from music_styles import music_styles as MS
    L = card["length_s"]
    out = ["Your lines are %d words. Here is how each music style handles them at %d seconds:"
           % (card["client_words"], L)]
    for r in card["rows"]:
        out.append("- %s: room for %d words at the planned share, all your words need %.1f seconds (%d spoken, %d rap) - %s"
                   % (r["label"], r["capacity_words"], r["planned_s"], r["split"]["spoken"],
                      r["split"]["rap"], "fits" if r["fits"] else "does not fit"))
    if card["outcome"] == "ok":
        return "\n".join(out + ["Everything fits. Nothing is cut."])
    o = card["options"]
    out += ["", "Nothing is cut until you approve it. Your options:"]
    n = 1
    for x in o["longer_ad"]:
        out.append("%d. A %d second ad - %s" % (n, x["id"], (
            "fits in " + ", ".join(MS.style(s)["label"] for s in x["fits_styles"]))
            if x["fits_styles"] else "does not fit any style"))
        n += 1
    out.append("%d. A different music style (see the lines above)" % n)
    n += 1
    out.append("%d. Voice: All Suno (default) or Velvet Voiceover" % n)
    n += 1
    fw = o[FEWER_WORDS_ID]
    out.append("%d. Fewer words - these exact lines would be cut, and you approve the list: %s"
               % (n, ", ".join(fw["cut_line_ids"]) or "none"))
    for nt in card["notices"]:
        out.append("Notice: " + nt["text"])
    return "\n".join(out)


def _with_saved_character(client_dir):
    """QUESTIONS, with the saved-character question first when the client has
    saved characters (Part I, I6). With a client folder but no saved characters
    the plain six open with one short line (``NO_SAVED_LINE``). No folder: plain six."""
    if not client_dir:
        return QUESTIONS
    from character_library import character_library as CL
    q = CL.saved_character_question(client_dir)
    if not q:
        return [dict(QUESTIONS[0], preface=NO_SAVED_LINE)] + QUESTIONS[1:]
    return [q] + QUESTIONS


try:
    from choice_card.intake_card.intro import INTRO as _INTRO, take as _intro_take
except ImportError:                                # run as a plain script
    from intro import INTRO as _INTRO, take as _intro_take  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Print the six-question intake card.")
    ap.add_argument("--format", choices=("text", "openclaw-json", "telegram-json"),
                    default="text",
                    help="text: raw card for the Claude Code chat. "
                         "openclaw-json / telegram-json: one send payload per message.")
    ap.add_argument("--target", default="", help="Telegram chat id (send formats)")
    ap.add_argument("--step", action="store_true",
                    help="one question at a time: print only the NEXT message, "
                         "given every --reply the client has sent so far (I7)")
    ap.add_argument("--reply", action="append", default=[],
                    help="a client reply, in order (repeat the flag)")
    ap.add_argument("--run-state-file", default="",
                    help="with --step and no replies: send the one-time intro as its "
                         "own message first (recorded as intro_shown in this file)")
    ap.add_argument("--client-dir", default="",
                    help="client data folder; when it holds saved characters the "
                         "card opens with the saved-character question (I6)")
    a = ap.parse_args(argv)
    qs = _with_saved_character(a.client_dir)
    if a.step:
        st = conversation(a.reply, qs)
        if not a.reply and a.run_state_file and _intro_take(a.run_state_file):
            st = dict(st, message=_INTRO)          # FU-INTRO-MESSAGE
        if a.format == "text":
            sys.stdout.write(st["message"] + "\n")
        else:
            send = openclaw_send_argv if a.format == "openclaw-json" else telegram_payload
            sys.stdout.write(json.dumps(
                {"done": st["done"], "send": send(a.target, st["message"])}, indent=2) + "\n")
        return 0
    if a.format == "text":
        sys.stdout.write(render_card(qs) + "\n")      # raw newlines, no JSON escaping
        return 0
    msgs = render_messages(qs)
    if a.format == "openclaw-json":
        out = [openclaw_send_argv(a.target, m) for m in msgs]
    else:
        out = [telegram_payload(a.target, m) for m in msgs]
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
