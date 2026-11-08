#!/usr/bin/env python3
"""One canonical question, three shapes.

Claude Code and claude-nine get the structured question tool payload (2-4 options,
short header, ONE question per call, free text via Other). OpenClaw and plain get one
short numbered chat message per question and `parse_reply` for the answer. The agent
says the message in its OWN session channel: this module sends nothing and reads no
credentials.

WHICH question is asked is not decided here. `pending` asks the intake engine
(`shared-utils/client_intake/engine.py`) for the single next APPLICABLE question, so a
conditional topic whose condition is false is never offered, a confirmed answer is never
asked twice, and a `suggested` answer is asked until the client confirms it. The renderer
only gives that one question its shape; it never selects, filters or forks the rules.

A question is the bank's object: id, text (or prompt), why (or reason),
choices (strings or {label,value,description|example}, at most 3), optional example,
header, group, default.value (never_default questions have none), and a nested
help object (`help` may also be one plain sentence, which is read as its explanation).
The nested `help.examples`, the `default.value` and every per-option explanation are
preserved all the way into the rendered question: they are never flattened into a phrase
like "Use this one". "I'm not sure, help me" is always added, and its description names
the coaching ways out (show an example, help me answer, recommend from what is already
known). Resume: `pending` reads the answers file, so a confirmed answer is never asked
twice.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_profile  # noqa: E402

HELP_LABEL = "I'm not sure, help me"
HINT = "Pick this one if it sounds right to you."
TYPE_LABEL = "Type my own answer"
MAX_CHOICES = 3
MAX_TOOL_QUESTIONS = 1  # one question at a time: the client is never handed a wall of questions
MAX_HEADER = 12
DONE_STATUSES = ("provided", "default_to_confirm")  # unknown/suggested get asked again
_HELP_WORDS = {"help", "?", "not sure", "im not sure", "i'm not sure", "idk", "i dont know",
               "i don't know", "dont know", "don't know", "no idea", "help me",
               "help me answer", "show me an example", "give me an example",
               "recommend using what is known"}
_HELP_PHRASES = re.compile(
    r"\b(?:not sure|no idea|no clue|don'?t know|help|show me an example|give me an example)\b")
_MAX_HELP_WORDS = 6  # longer replies are real answers that merely mention a phrase
_DEFAULT_WORDS = {"default", "use default", "skip", "you choose", "you pick"}


def _choice(c):
    """One choice, keeping its own explanation. A per-option `example` counts as its
    explanation, so a bank that explains options that way is never flattened."""
    if isinstance(c, dict):
        label = str(c.get("label") or c.get("value"))
        return {"label": label, "value": c.get("value", label),
                "description": str(c.get("description") or c.get("example") or "")}
    return {"label": str(c), "value": str(c), "description": ""}

def _help(q):
    """The nested help object. A bank that carries `help` as one plain sentence (Skill 83's picture
    questions do) is read as its explanation, so its coaching is kept instead of being dropped."""
    h = q.get("help")
    if isinstance(h, dict):
        return h
    return {"explain": str(h)} if isinstance(h, str) and h.strip() else {}


def _examples(q):
    """The nested help examples, never dropped when they are the only examples there are."""
    out = []
    for e in (_help(q).get("examples") or []):
        if str(e).strip() and str(e) not in out:
            out.append(str(e))
    if q.get("example") and str(q["example"]) not in out:
        out.insert(0, str(q["example"]))
    return out

def _safe_default(q):
    """The safe default from the bank. The nested default.value wins over a flat key."""
    nested = (q.get("default") or {}).get("value") if isinstance(q.get("default"), dict) else None
    return nested if nested not in (None, "") else q.get("safe_default")

def normalize(q):
    choices = [_choice(c) for c in (q.get("choices") or [])]  # a description is the bank's own words, or ""
    qid = str(q["id"])
    examples = _examples(q)
    return {
        "id": qid,
        "text": str(q.get("text") or q.get("prompt") or qid),
        "why": str(q.get("why") or q.get("reason") or ""),
        "example": examples[0] if examples else "",
        "examples": examples,
        "help_text": str(_help(q).get("explain") or ""),
        "choices": choices[:MAX_CHOICES],
        "dropped": [c["label"] for c in choices[MAX_CHOICES:]],
        "header": str(q.get("header") or q.get("group") or qid.split("_", 1)[-1])
        .replace("_", " ").strip().title()[:MAX_HEADER].strip() or "Question",
        "group": str(q.get("group") or q.get("phase") or ""),
        "safe_default": _safe_default(q),
        "never_default": bool(q.get("never_default")),
    }


def can_default(n):
    return n["safe_default"] not in (None, "") and not n["never_default"]


def structured(questions):
    """Calls for the structured question tool, ONE question per call.

    The client is asked one thing at a time: handing over four pickers at once is exactly
    the overwhelm the guided experience removes. MAX_TOOL_QUESTIONS is the single place
    that decides how many go in one call.
    """
    calls = []
    for i in range(0, len(questions), MAX_TOOL_QUESTIONS):
        chunk = questions[i:i + MAX_TOOL_QUESTIONS]
        calls.append({"tool": "AskUserQuestion", "questions": [_tool_question(normalize(q)) for q in chunk],
                      "ids": [str(q["id"]) for q in chunk]})
    return calls

def _coach(n):
    """What the help option promises, in the client's own words: concrete ways out."""
    ways = ["show you an example"]
    if n["help_text"]:
        ways.append("explain it in plain language")
    if can_default(n):
        ways.append("recommend something using what I already know")
    return "I will " + ", ".join(ways[:-1] + ["or " + ways[-1]]) if len(ways) > 1 else ways[0]

def _says_it_all(label):
    """A long label, or one that reads as a sentence, needs nothing said under it."""
    return len(label.split()) > 4 or label.rstrip().endswith((".", "!", "?", ")"))


# How a client says "I can't or won't pick one of these": a way out, not an answer.
_WAY_OUT = ("not sure", "unsure", "i don't know", "i do not know", "don't know", "do not know",
            "no idea", "skip", "other", "something else", "decide later", "i'll decide later",
            "none of these", "none of the above", "prefer not to say", "i'd rather not say")
_WAY_OUT_RE = re.compile(r"(?:%s)\b" % "|".join(re.escape(w) for w in _WAY_OUT))


def _is_way_out(label):
    """'Not sure', 'I don't know', 'Skip', 'Other' ...: "Pick this one if it sounds right to you"
    under those reads as nonsense, so they never get the hint (the bank's own words still show)."""
    text = " ".join(label.lower().replace("\u2019", "'").replace("_", " ").split())
    return len(text.split()) <= 5 and bool(_WAY_OUT_RE.match(text))


def _hints(choices):
    """What each choice says under its label. The bank's own words always win. A choice the bank
    leaves unexplained gets one short, warm line that never repeats the label, unless a label in
    the same question already says it all: then none of them get one, because a line under some
    options and not others looks unfinished, and a line under a long label only repeats it.
    A way out ("Not sure", "Skip", "Other") never gets the line: it is not an answer to pick
    because it "sounds right", and it does not count when deciding whether the others get one.
    The chat message never adds a hint: "1. Monthly" needs none."""
    quiet = any(_says_it_all(c["label"]) for c in choices
                if not c["description"] and not _is_way_out(c["label"]))
    return [c["description"] or ("" if quiet or _is_way_out(c["label"]) else HINT) for c in choices]


def _tool_question(n):
    opts = [{"label": c["label"], "description": d}
            for c, d in zip(n["choices"], _hints(n["choices"]))]
    if not opts:
        opts.append({"label": TYPE_LABEL,
                     "description": "Pick Other below and type your own answer, or pick this and I will ask you right here"})
    opts.append({"label": HELP_LABEL, "description": _coach(n)})
    text = n["text"]
    if n["why"]:
        text += "\n" + n["why"]
    return {"question": text, "header": n["header"], "multiSelect": False, "options": opts}

def chat(q, index=None, total=None):
    n = normalize(q)
    head = f"Question {index} of {total}: " if index and total else ""
    lines = [head + n["text"]]
    if n["why"]:
        lines.append(f"Why we ask: {n['why']}")
    for ex in n["examples"][:2]:
        lines.append(f"Example: {ex}")
    if n["help_text"]:  # the explanation is never dropped just because a bank has no example
        lines.append(f"If none of that fits: {n['help_text']}")
    if n["choices"]:
        lines.append("Reply with a number, or type your own answer:")
        for i, c in enumerate(n["choices"], 1):
            lines.append(f"{i}. {c['label']}" + (f" - {c['description']}" if c["description"] else ""))
        lines.append(f"{len(n['choices']) + 1}. {HELP_LABEL}")
    else:
        lines.append("Just type your answer. Not sure? Reply \"help\" and I will show you some options.")
    if can_default(n):
        lines.append("Or reply \"default\" and I will pick a sensible answer for now, and we will double-check it together later.")
    return "\n".join(lines)


def parse_reply(q, reply):
    """-> {kind: choice|free_text|help|default|repeat, value}. Never a dead end."""
    n = normalize(q)
    t = str(reply or "").strip()
    low = re.sub(r"[.!?]+$", "", t.lower().replace("\u2019", "'").replace("\u2018", "'"))
    if not t:
        return {"kind": "repeat", "value": None}
    if not low or low in _HELP_WORDS:  # bare "?" or "??" strips to empty: still a help request
        return {"kind": "help", "value": None}
    if low in _DEFAULT_WORDS:  # a never-default question turns "skip" into help, not a silent gap
        return ({"kind": "default", "value": n["safe_default"]} if can_default(n)
                else {"kind": "help", "value": None})
    if n["choices"] and low.isdigit():
        k = int(low)
        if 1 <= k <= len(n["choices"]):
            return {"kind": "choice", "value": n["choices"][k - 1]["value"]}
        if k == len(n["choices"]) + 1:
            return {"kind": "help", "value": None}
    for c in n["choices"]:
        if low == c["label"].lower():
            return {"kind": "choice", "value": c["value"]}
    if low == HELP_LABEL.lower() or (len(low.split()) <= _MAX_HELP_WORDS and _HELP_PHRASES.search(low)):
        return {"kind": "help", "value": None}
    return {"kind": "free_text", "value": t}


def records(answers):
    """{question_id: record} from the answers file (dict or list form)."""
    a = (answers or {}).get("answers", answers or {})
    if isinstance(a, list):
        return {str(r.get("question_id") or r.get("id")): r for r in a if isinstance(r, dict)}
    return {str(k): (v if isinstance(v, dict) else {"value": v, "status": "provided"})
            for k, v in a.items() if k not in ("to_confirm", "harness", "runtime")}


# ---------------------------------------------------------------- selection (the intake engine's)
_CLIENT_INTAKE = Path(__file__).resolve().parents[2] / "client_intake"  # shared-utils/client_intake


def engine_module():
    """shared-utils/client_intake/engine.py: the ONE selection authority. Never re-implemented here."""
    if str(_CLIENT_INTAKE) not in sys.path:
        sys.path.insert(0, str(_CLIENT_INTAKE))
    import engine  # noqa: E402
    return engine


def bank_of(questions):
    """A bank the engine can read, whether the caller passed a list or a whole bank document."""
    if isinstance(questions, dict):
        bank = dict(questions)
        bank.setdefault("questions", [])
    else:
        bank = {"questions": list(questions or [])}
    bank.setdefault("help_label", HELP_LABEL)
    # the shared engine reads these keys directly; a partial bank (a bank-shaped question
    # without them) is asked as an unconditional, defaultable question, as it always was
    bank["questions"] = [{"condition": "always", "never_default": False, **q}
                         for q in bank["questions"]]
    return bank


def doc_of(answers, mode=None):
    """The client-intake answers document the engine selects from: answers, branch, resume state intact."""
    a = answers or {}
    meta = a.get("meta") if isinstance(a.get("meta"), dict) else {}
    doc = {"schema": "client-intake-answers/v1",
           "meta": {"mode": meta.get("mode") or mode or "launch",
                    "phase": meta.get("phase") or "pre_build"},
           "answers": {}, "to_confirm": a.get("to_confirm") or []}
    for qid, r in records(a).items():
        if r.get("status"):
            # a suggestion is not the client's answer until they confirm it: the shared engine
            # asks anything it sees as unknown, so a suggested answer reaches it as unknown
            doc["answers"][qid] = {"value": r.get("value"),
                                   "status": "unknown" if r["status"] == "suggested" else r["status"],
                                   "source": r.get("source", "client")}
    return doc


def next_applicable(questions, answers, mode=None):
    """THE one next applicable question, or None when every applicable one is answered.

    Selection, conditional applicability and never-ask-twice all come from the intake engine
    (`engine.next_question`), so the renderer cannot ask an inapplicable question and cannot
    re-ask a confirmed answer. A `suggested` answer is still asked: a suggestion is not the
    client's answer until they confirm it."""
    return engine_module().next_question(doc_of(answers, mode), bank_of(questions))


def pending(questions, answers, mode=None):
    """The resume list, now at most ONE question. Kept as the name every adapter already calls."""
    q = next_applicable(questions, answers, mode)
    return [q] if q else []


def _progress(q):
    """(index, total) from the engine's own honest progress, or (None, None) when it has none."""
    p = q.get("progress") or {}
    of = p.get("of")
    answered = p.get("answered")
    if of is None or answered is None:
        return None, None
    return answered + 1, of


def render(questions, profile):
    """One question, one shape: a structured call (Claude Code, claude-nine) or one chat message.

    The structured shape is used only when the profile says it AND the session's question
    tool is actually available (``question_tool`` false/absent means no tool). Codex and
    every other plain-chat harness therefore get the same interview as one message, over
    the same answers file and resume state. An empty list means the interview is done."""
    one = list(questions or [])[:MAX_TOOL_QUESTIONS]
    if not one:
        return []
    if profile["question_shape"] == "structured" and profile.get("question_tool", True):
        return structured(one)
    q = one[0]
    index, total = _progress(q)
    return [{"message": chat(q, index, total), "id": q["id"]}]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--questions-file",
                    help="JSON list or {questions:[...]}; default: the shared client-intake bank")
    ap.add_argument("--answers-file")
    ap.add_argument("--harness")
    ap.add_argument("--mode", choices=("launch", "legacy", "bf"),
                    help="run mode when the answers file does not name one")
    ap.add_argument("--request", help="the client's opening words: routes launch vs legacy when --mode is absent")
    a = ap.parse_args(argv)
    mode, routed = a.mode, None
    if mode is None and a.request:
        mode, routed = engine_module().route_mode(a.request)
    qs = (json.loads(Path(a.questions_file).read_text(encoding="utf-8"))
          if a.questions_file else str(_CLIENT_INTAKE / "question-bank.json"))
    if isinstance(qs, str):
        qs = json.loads(Path(qs).read_text(encoding="utf-8"))
    answers = json.loads(Path(a.answers_file).read_text(encoding="utf-8")) if a.answers_file else None
    prof = harness_profile.detect(a.harness, answers)
    one = pending(qs, answers, mode)
    print(json.dumps({"profile": prof, "mode": mode, "mode_reason": routed,
                      "next_id": one[0]["id"] if one else None,
                      "done": not one, "render": render(one, prof)}, indent=2))


if __name__ == "__main__":
    main()
