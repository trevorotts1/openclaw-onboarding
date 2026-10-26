#!/usr/bin/env python3
"""One canonical question, one at a time, three shapes.

The intake engine picks the ONE next applicable question (conditions included); this
module shapes it for the harness and never feeds a renderer the raw bank. Claude Code
and claude-nine get one structured question tool call (exactly one question per call).
OpenClaw and plain get one short numbered chat message. The agent says the message in
its OWN session channel: this module sends nothing and reads no credentials.

A question is the bank's object: id, text (or prompt), why (or reason), choices
(strings or {label,value,description,example}, at most 3), nested help.examples,
default.value, per-option explanations, optional example, header, group, safe_default,
never_default. All of them survive to the client surface; a missing per-option
explanation stays missing, never "Use this one". "I'm not sure, help me" is always
added. Resume: `pending` reads the answers file (answered ones are skipped, and the
count/estimate over applicable questions only, never the whole bank).
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness_profile  # noqa: E402

HELP_LABEL = "I'm not sure, help me"
TYPE_LABEL = "Type my own answer"
MAX_CHOICES = 3
MAX_HEADER = 12
DONE_STATUSES = ("provided", "default_to_confirm")  # unknown/suggested get asked again
_HELP_WORDS = {"help", "?", "not sure", "im not sure", "i'm not sure", "idk", "i dont know",
               "i don't know", "dont know", "don't know", "no idea", "help me"}
_HELP_PHRASES = re.compile(r"\b(?:not sure|no idea|no clue|don'?t know|help)\b")
_MAX_HELP_WORDS = 6  # longer replies are real answers that merely mention a phrase
_DEFAULT_WORDS = {"default", "use default", "skip", "you choose", "you pick"}
_URL = re.compile(r"https?://")
_NO_EXAMPLE = re.compile(r"\bexample:\s*none\b", re.I)


def _style_examples(n):
    """The style block for design_style only: image links and the honest "no example" lines.
    Rendered BEFORE the question so the client sees what they are choosing between; the feel
    examples ("Warm and friendly: B") stay below it. Any other question keeps its examples
    below the question and never gets a "Style examples" label."""
    if n["id"] != "design_style":
        return []
    out = []
    for e in n["examples"]:
        s = str(e)  # a foreign bank may put non-strings here; they must never crash the ask
        if _URL.search(s) or _NO_EXAMPLE.search(s):
            out.append(s)
    return out


def _engine():
    """shared-utils/client_intake/engine.py: the repo checkout, then any installed tree."""
    home = Path.home()
    roots = list(HERE.parents) + [home / ".openclaw" / "skills", home / ".claude" / "skills",
                                  home / ".claude-nine" / "skills", Path("/data/.openclaw/skills")]
    for root in roots:
        for d in (root / "shared-utils" / "client_intake", root / "client_intake"):
            if (d / "engine.py").is_file():
                sys.path.insert(0, str(d))
                import engine  # noqa: E402
                return engine
    return None


def _choice(c):
    if isinstance(c, dict):
        label = str(c.get("label") or c.get("value"))
        out = {"label": label, "value": c.get("value", label),
               "description": str(c.get("description") or "")}
        if c.get("example"):  # the per-option explanation in the picture-question shape
            out["example"] = str(c["example"])
        return out
    return {"label": str(c), "value": str(c), "description": ""}


def normalize(q):
    choices = [_choice(c) for c in (q.get("choices") or [])]
    qid = str(q["id"])
    help_block = q.get("help") if isinstance(q.get("help"), dict) else {}
    return {
        "id": qid,
        "text": str(q.get("text") or q.get("prompt") or qid),
        "why": str(q.get("why") or q.get("reason") or ""),
        "example": str(q.get("example") or ""),
        "examples": list(q.get("examples") or []) or list(help_block.get("examples") or []),
        "help": help_block,
        "choices": choices[:MAX_CHOICES],
        "dropped": [c["label"] for c in choices[MAX_CHOICES:]],
        "header": str(q.get("header") or q.get("group") or qid.split("_", 1)[-1])
        .replace("_", " ").strip().title()[:MAX_HEADER].strip() or "Question",
        "group": str(q.get("group") or q.get("phase") or ""),
        "default": q.get("default"),
        "safe_default": q.get("safe_default"),
        "never_default": bool(q.get("never_default")),
        "topic": q.get("topic"),
        "condition": q.get("condition"),
    }


def can_default(n):
    if n["never_default"]:
        return False
    d = n["default"] if isinstance(n["default"], dict) else None
    return n["safe_default"] not in (None, "") or (d is not None and d.get("value") not in (None, ""))


def _default_say(n):
    d = n["default"] if isinstance(n["default"], dict) else {}
    what = d.get("value", n["safe_default"])
    why = d.get("reason", "")
    return f"{what} ({why})" if why else f"{what}"


def structured(questions):
    """Calls for the structured question tool: ONE question per call, never a batch."""
    return [{"tool": "AskUserQuestion", "questions": [_tool_question(normalize(q))],
             "ids": [str(q["id"])]} for q in questions]


def _tool_question(n):
    opts = [{"label": c["label"],
             "description": c.get("description") or c.get("example") or ""}
            for c in n["choices"]]  # a missing explanation stays missing, never "Use this one"
    if not opts:
        opts.append({"label": TYPE_LABEL,
                     "description": "Pick Other below and type it, or pick this and I will ask in chat"})
    tail = "We will show examples and suggestions"
    if can_default(n):
        tail += ", or use a safe default you confirm later"
    opts.append({"label": HELP_LABEL, "description": tail})
    style = _style_examples(n)
    text = "" if not style else "Style examples:\n" + "\n".join(style) + "\n\n"
    text += n["text"] + (f"\n{n['why']}" if n["why"] else "")
    if n["example"]:
        text += f"\nExample: {n['example']}"
    for ex in n["examples"]:  # every example reaches the client, never dropped in structured
        if ex not in style:
            text += f"\nExample: {ex}"
    return {"question": text, "header": n["header"], "multiSelect": False, "options": opts}


def chat(q, index=None, total=None, estimate_note=None):
    n = normalize(q)
    head = f"Question {index} of {total}: " if index and total else ""
    style = _style_examples(n)
    lines = []
    if style:  # the promised examples come BEFORE the question (finding 20)
        lines.append("Style examples - open the picture links before you answer:")
        lines.extend(f"- {ex}" for ex in style)
    lines.append(head + n["text"])
    if n["why"]:
        lines.append(f"Why we ask: {n['why']}")
    if n["example"]:
        lines.append(f"Example: {n['example']}")
    for ex in n["examples"]:  # every example, never a silent two-item cap
        if ex not in style:
            lines.append(f"Example: {ex}")
    if n["choices"]:
        lines.append("Reply with a number, or type your own answer:")
        for i, c in enumerate(n["choices"], 1):
            say = c.get("description") or c.get("example") or ""
            lines.append(f"{i}. {c['label']}" + (f" - {say}" if say else ""))
        lines.append(f"{len(n['choices']) + 1}. {HELP_LABEL}")
    else:
        lines.append("Just type your answer. Not sure? Reply \"help\" and I will show you options.")
    if can_default(n):
        lines.append(f"Or reply \"default\" and I will use {_default_say(n)}, marked \"to confirm\".")
    if estimate_note:
        lines.append(f"Note: {estimate_note}")
    return "\n".join(lines)


def parse_reply(q, reply):
    """-> {kind: choice|free_text|help|default|repeat, value}. Never a dead end."""
    n = normalize(q)
    t = str(reply or "").strip()
    low = re.sub(r"[.!?]+$", "", t.lower().replace("’", "'").replace("‘", "'"))
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


def _token(answers, key):
    if key in ("mode", "phase"):
        return (answers or {}).get("meta", {}).get(key)
    r = records(answers).get(key)
    if r is None or r.get("status") == "unknown":
        return None
    v = r.get("value")
    if v is None or (isinstance(v, str) and v.lower() in ("none", "no")):
        return "none"
    if isinstance(v, str):
        return "yes" if v.lower().startswith("yes") else v.lower()
    return "set"


def _cond_ok(q, answers):
    """The bank's own condition. The intake engine answers the forms it owns; anything
    else is asked rather than silently skipped."""
    cond = str(q.get("condition") or "always")
    if cond == "always":
        return True
    m = re.fullmatch(r"(\w+) (==|!=) (\w+)", cond)
    if m:
        key, op, want = m.groups()
        tok = _token(answers, key)
        return tok is not None and ((tok == want) == (op == "=="))
    m = re.fullmatch(r"(\w+) answered", cond)
    if m:
        r = records(answers).get(m.group(1))
        return r is not None and r.get("status") != "unknown"
    return True  # needs_role and engine-only forms: the engine path resolves these


def applicable(questions, answers):
    return [q for q in questions if _cond_ok(q, answers)]


def pending(questions, answers):
    done = {k for k, r in records(answers).items() if r.get("status") in DONE_STATUSES}
    return [q for q in applicable(questions, answers) if str(q["id"]) not in done]


def render(questions, profile):
    if profile["question_shape"] == "structured":
        return structured(questions)  # one question per call, never a batch
    return [{"message": chat(q, i, len(questions)), "id": q["id"]}
            for i, q in enumerate(questions, 1)]


def _as_doc(eng, answers):
    if isinstance(answers, dict) and isinstance(answers.get("answers"), dict):
        return {"schema": "client-intake-answers/v1",
                "meta": dict(answers.get("meta") or {"mode": "launch", "phase": "pre_build"}),
                "answers": answers["answers"], "to_confirm": answers.get("to_confirm", [])}
    return eng.new_doc()


def _is_shared_bank(qs):
    return bool(qs) and all(isinstance(q, dict) and "condition" in q
                            and "never_default" in q and "help" in q for q in qs)


def _find_canonical_bank(rel, questions_file):
    for base in [Path(questions_file).resolve().parent, *HERE.parents,
                 Path.home() / ".openclaw" / "skills", Path.home() / ".claude" / "skills"]:
        f = base / rel
        if f.is_file():
            return f
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--questions-file", required=True, help="JSON list, or {questions:[...]}")
    ap.add_argument("--answers-file")
    ap.add_argument("--harness")
    a = ap.parse_args(argv)
    data = json.loads(Path(a.questions_file).read_text(encoding="utf-8"))
    qs = data.get("questions", data) if isinstance(data, dict) else data
    if isinstance(data, dict) and data.get("canonical_bank"):
        # the old technical question files name the canonical guided bank: never ask the old interview
        canon = _find_canonical_bank(data["canonical_bank"], a.questions_file)
        if canon is not None:
            qs = json.loads(canon.read_text(encoding="utf-8")).get("questions", [])
    answers = json.loads(Path(a.answers_file).read_text(encoding="utf-8")) if a.answers_file else None
    prof = harness_profile.detect(a.harness, answers)
    eng = _engine() if _is_shared_bank(qs) else None
    if eng is not None:  # the engine selects the ONE next applicable question
        doc = _as_doc(eng, answers)
        q = eng.next_question(doc, bank={"questions": qs, "help_label": HELP_LABEL})
        if a.answers_file:
            eng.save(doc, a.answers_file)  # persist defaults and the estimate bookkeeping
        if q is None:
            print(json.dumps({"profile": prof, "render": [], "done": True,
                              "check": eng.check(doc, bank={"questions": qs, "help_label": HELP_LABEL})}, indent=2))
            return 0
        out = {"profile": prof, "render": render([q], prof), "progress": q.get("progress"),
               "estimate": q.get("estimate"), "source": "intake engine"}
        print(json.dumps(out, indent=2))
        return 0
    todo = pending(qs, answers)  # foreign bank: still one question at a time
    total = len(applicable(qs, answers))
    q = todo[0] if todo else None
    prog = {"answered": total - len(todo), "of": total,
            "percent": (round(100 * (total - len(todo)) / total) if total else 100)}
    out = {"profile": prof, "render": render([q], prof) if q else [], "progress": prog,
           "estimate": {"questions": total, "note": None,
                        "text": f"about {total} short questions, depending on what we already know"},
           "done": not todo, "source": "questions file"}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    main()
