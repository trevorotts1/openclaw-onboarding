#!/usr/bin/env python3
"""The guided client experience: the introduction, the computed length estimate, the
progress line, and the plan review that ends the interview.

The client is an entrepreneur, not a software engineer or a marketing expert, and may be
a non-technical business owner in their sixties. Everything here is written for that reader,
in a warm, supportive voice, like a helpful guide and not a robot: plain words, one thing at
a time, decisions explained, how it helps them said out loud, and no technical detail
(schema names, ids, hashes, provider routing, version numbers) ever shown. Nothing here
mentions a technical problem or offers to install anything.

Every number is COMPUTED from the questions that actually apply to this run. Nothing is
stored and nothing is hardcoded, so a Black Friday run, a launch run and a legacy run
each report their own real length, and a run that already knows some answers reports a
shorter one. When a computed estimate changes, `estimate_change()` says why.

Stdlib only. No network, no credentials, no client messages: the agent says the lines in
its OWN session channel.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_CLIENT_INTAKE = HERE.parent.parent / "client_intake"
if str(_CLIENT_INTAKE) not in sys.path:
    sys.path.insert(0, str(_CLIENT_INTAKE))

MODES = {
    "A": "recommend a plan for me",
    "B": "guide me through each decision",
    "C": "I already have a plan",
}

INTRO = (
    "Hi {name}! I'm so glad you're here. I'm going to help you get {sale} ready, from start to finish.\n"
    "\n"
    "Here's what I'll put together for you:\n"
    "\u2022 A sales page that explains your offer and invites people to buy\n"
    "\u2022 An order form where people can pay you\n"
    "\u2022 A small add-on people can grab right at checkout\n"
    "\u2022 Special one-time offers people see right after they buy\n"
    "\u2022 A thank-you page\n"
    "\u2022 Your launch emails and text messages, written and ready for you to look over\n"
    "\n"
    "Everything starts as a draft for you to look over first. Nothing goes live and nothing is "
    "sent to anyone until you've told me it looks right. After that, we'll get it set up in "
    "your Convert and Flow account.\n"
    "\n"
    "Here's how this works: I'll ask you some simple questions, one at a time \u2014 things like "
    "what you'd like to sell and the price. There are no wrong answers, and if you're not sure "
    "about something, just tell me and I'll help you figure it out.\n"
    "\n"
    "Once you've answered, you can sit back and relax. I'll do the building, and I'll let you "
    "know as soon as everything is ready for you to look at.")

# The first question of this guided flow is how the client would like to be helped.
# The A, B and C words match the shared question bank, so a reply of "A" or of the full
# sentence is understood either way.
CHOICES = (
    "Let's start with the first question: what's the best way for me to help you?\n"
    "  A. Recommend a plan for me. I'll use what you tell me, ask only what I still need, "
    "and you'll look the plan over before anything is built.\n"
    "  B. Guide me through each decision. I'll explain your options in plain words and help "
    "you choose.\n"
    "  C. I already have a plan. I'll help you carry it out, and I'll point out anything "
    "important that might get missed.\n"
    "You can change your mind about this at any time.")


def _bank(bank=None):
    import engine  # shared-utils/client_intake/engine.py
    return bank if bank is not None else engine.load_bank()


def applicable_questions(doc, bank=None):
    """The questions that actually apply to this run, in bank order.

    A conditional topic whose condition is false is not counted and is never asked, so a
    legacy run is not told about launch or Black Friday decisions."""
    import engine
    return engine.applicable(doc, bank or _bank(bank))


def estimate(doc, bank=None):
    """(remaining, total) computed from the applicable questions right now."""
    import engine
    total = len(applicable_questions(doc, bank))
    remaining = len([q for q in applicable_questions(doc, bank) if engine._askable(doc, q)])
    return remaining, total


def estimate_line(doc, bank=None):
    """One warm, plain sentence with the real number, never a stored one."""
    remaining, total = estimate(doc, bank)
    if total == 0:
        return "I have everything I need from you. Thank you!"
    if remaining == 0:
        return "That was the last question. Thank you, I have everything I need."
    if remaining == 1:
        return "I have just one short question left for you."
    return (f"I have about {remaining} short questions for you. Many take just a few seconds, "
            "and I'll skip any I already know the answer to.")


def estimate_change(before, after, reason):
    """A changed count is explained in friendly words, never silently revised."""
    if before == after:
        return None
    if after < before:
        return (f"Good news: {reason}, so I have fewer questions for you than I first "
                f"thought. It's about {after} now, instead of {before}.")
    return (f"Just so you know: {reason}, so I have a few more questions for you than I "
            f"first thought. It's about {after} now, instead of {before}.")


def progress_line(doc, bank=None):
    """Progress over the applicable questions only, plus the stage being worked on."""
    remaining, total = estimate(doc, bank)
    answered = total - remaining
    pct = 0 if total == 0 else round(100 * answered / total)
    q = None
    try:
        import engine
        q = engine.next_question(doc, bank)
    except Exception:  # a doc no engine can read is still honestly reported
        q = None
    stage = _stage_name(q.get("group") if q else None)
    tail = f" Next up: {stage}." if stage else ""
    return f"You've answered {answered} of {total} questions so far ({pct}%).{tail}"


_STAGES = {
    "start": "how you'd like me to work", "you": "you and your business",
    "offer": "your offer and what it costs", "funnel": "how people will buy from you",
    "design": "your look and brand", "brand": "your look and brand",
    "images": "the pictures for your pages", "launch": "your launch plans",
    "bf": "your Black Friday details", "approval": "your look-over of the plan",
}


def _stage_name(group):
    # a group with no plain name is never shown raw: it becomes a friendly catch-all
    return _STAGES.get(str(group or ""), "a few more details" if group else "")


def _fact(doc, qid, fallback="not answered yet"):
    import engine
    v = engine.view(doc).get(qid)
    if v in (None, "", [], {}):
        return fallback
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    if isinstance(v, dict):
        return v.get("display_name") or v.get("description") or v.get("text") or fallback
    return str(v)


def plan_review(doc, plan=None, costs=None, assumptions=None):
    """The ending: the client's own plan review, in four parts.

    1 what the client told us, 2 what we understand and recommend and why, 3 what will be
    built and the outcome it is meant to produce, 4 what is still assumed or limited and
    what it costs. Approval stays a separate, explicit step: this text recommends and
    never approves, and it never promises sales."""
    lines = ["Here is everything you've told me so far, and what I plan to do with it. "
             "Please read it over and tell me if anything looks wrong.", ""]
    lines.append("What you told me:")
    for label, qid in (("Your business", "business_name"), ("What you are offering", "offer_name"),
                       ("Who it is for", "audience"), ("What changes for them", "offer_transformation"),
                       ("What the buyer gets", "deliverables"), ("Your price", "price")):
        lines.append(f"  - {label}: {_fact(doc, qid)}")
    lines.append("")
    lines.append("What I understand, and what I recommend:")
    shape = _fact(doc, "funnel_shape", "one offer")
    lines.append(f"  - How people will buy from you: {shape}. I suggest this because it fits "
                 f"how you described your offer.")
    lines.append(f"  - Your look: {_fact(doc, 'design_style', 'the standard look')}. I chose it to "
                 f"match the feeling you described for your brand.")
    lines.append("")
    lines.append("What will be built, and what it is meant to do:")
    lines.append("  - The pages people will visit, designed for computers and phones and written in your words.")
    lines.append("  - The order form that takes the payment, and the follow-up messages a buyer gets afterwards.")
    lines.append("  - What this is meant to do: help more of the right people see your offer, and give "
                 "them a clear, easy way to buy it.")
    lines.append("")
    lines.append("Assumptions, limits and costs:")
    items = list(assumptions or [])
    ev = doc.get("answers", {})
    for qid, e in ev.items():
        if e.get("status") in ("default_to_confirm", "suggested"):
            items.append(f"For {qid.replace('_', ' ')}, I used {_fact(doc, qid, str(e.get('value')))} for now. "
                         f"Please tell me if that isn't right.")
    lines += [f"  - {i}" for i in items] or ["  - I haven't assumed anything: every answer above came from you."]
    lines.append(f"  - Costs: {costs or 'approving this plan costs you nothing. If any paid pictures are needed, I will ask you first.'}")
    lines.append("")
    lines.append("I'm only recommending this, not approving it for you. Nothing is built until you tell me "
                 "it looks right. I can't promise any sales numbers, but I can promise to build "
                 "everything the way we agreed.")
    return "\n".join(lines)


def opening(doc=None, first_name=None):
    """The warm introduction, the computed number of questions, then the first question.

    The name is the client's first name when the agent knows it, and "there" when it does
    not. A Black Friday run says so; any other run says "your launch"."""
    mode = ((doc or {}).get("meta") or {}).get("mode")
    intro = INTRO.format(name=(first_name or "").strip() or "there",
                         sale="your Black Friday sale" if mode == "bf" else "your launch")
    count = f"{estimate_line(doc)}\n\n" if doc is not None else ""
    return f"{intro}\n\n{count}{CHOICES}"


def main(argv=None):
    ap_args = sys.argv[1:] if argv is None else argv
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("answers_file", nargs="?")
    ap.add_argument("--mode", default="launch", choices=("launch", "legacy", "bf"))
    ap.add_argument("--harness")
    ap.add_argument("--first-name", help="the client's first name, for the greeting")
    ap.add_argument("--what", default="opening", choices=("opening", "estimate", "progress", "review"))
    a = ap.parse_args(ap_args)
    import engine
    doc = engine.load(a.answers_file, a.mode) if a.answers_file else engine.new_doc(a.mode)
    doc["meta"]["mode"] = a.mode
    if a.what == "opening":
        print(opening(doc, a.first_name))
    elif a.what == "estimate":
        print(estimate_line(doc))
    elif a.what == "progress":
        print(progress_line(doc))
    else:
        print(plan_review(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
