#!/usr/bin/env python3
"""rr_owner_message.py - write the message the OWNER reads when a rescue case ends.

DRAFT. Not installed anywhere. Target home after build:
  onboarding repo  65-rescue-receiver/rr_owner_message.py

It REPLACES the "final-body" command of 65-rescue-receiver/rescue-notification.py
(lines 161 to 194 at onboarding v27.1.71). Today the owner can only ever receive
one of three fixed sentences, and the actual answer is never shown:
    "Fixed and checked."
    "We are still working on this: <reason>."
    "A specialist will follow up."
A case that ended with clear instructions for the owner is reported as
"We are still working on this: we have not been able to confirm the fix yet."

NEW RULE: the words the owner reads are written by Rescue Rangers (the side
that knows the answer) and travel inside the instruction as "owner_message".
The box only chooses WHICH of four outcomes applies, from verified facts, and
wraps the text. The box's own model never has to produce the wording.

OUTCOMES
  solved               repair_status repaired AND verification_status verified
  owner_action         the instruction carries owner_message with kind "owner_action"
  answer               the instruction carries owner_message with kind "answer"
  specialist_follow_up anything else (including a turn that failed or timed out)

INPUT (one JSON object on stdin)
  {
    "ticket_id": "RR-000123",
    "result": { ...the result-v3 object the receiver built... },
    "owner_message": {"kind": "owner_action" | "answer" | "solved", "text": "plain words"},
    "transport_verdict": "delivered" | "failed"
  }

OUTPUT (one JSON object on stdout): {"outcome": "...", "body": "..."}

Rules that protect the owner:
  - "solved" is only ever said when the receiver's own check verified the repair.
  - Internal codes (snake_case words) are never shown.
  - The message is capped at 1200 characters and never contains a secret-shaped
    token (anything that looks like KEY=value with a long value is removed).
"""
from __future__ import annotations

import argparse
import json
import re
import sys

MAX_CHARS = 1200
SECRETISH = re.compile(r"\b[A-Z][A-Z0-9_]{3,}\s*=\s*\S{12,}")


def clean(text: str) -> str:
    text = SECRETISH.sub("[removed]", str(text)).replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    return text[:MAX_CHARS].rstrip()


def build(doc: dict) -> dict:
    ticket = str(doc.get("ticket_id") or "").strip()
    ref = " Reference: %s." % ticket if ticket else ""
    result = doc.get("result") if isinstance(doc.get("result"), dict) else {}
    om = doc.get("owner_message") if isinstance(doc.get("owner_message"), dict) else {}
    kind = om.get("kind")
    text = clean(om.get("text") or "")
    verified = result.get("repair_status") == "repaired" and result.get("verification_status") == "verified"

    if verified:
        detail = (" " + text) if text and kind == "solved" else ""
        return {"outcome": "solved",
                "body": "Good news. The problem you reported has been fixed, and we checked that it is working again.%s%s"
                        % (detail, ref)}
    if doc.get("transport_verdict") == "delivered" and kind == "owner_action" and len(text) >= 20:
        return {"outcome": "owner_action",
                "body": "Our support team looked into the problem you reported. There is one thing only you can do to finish the fix:\n\n%s\n\nReply here when it is done and I will check that everything works.%s"
                        % (text, ref)}
    if doc.get("transport_verdict") == "delivered" and kind == "answer" and len(text) >= 20:
        return {"outcome": "answer",
                "body": "Our support team looked into your question. Here is the answer:\n\n%s%s" % (text, ref)}
    return {"outcome": "specialist_follow_up",
            "body": "Our support team is still working on the problem you reported. A person on the team now has it and will contact you. You do not need to do anything right now.%s" % ref}


def selftest() -> int:
    ok = True
    r = build({"ticket_id": "RR-1", "result": {"repair_status": "repaired", "verification_status": "verified"}})
    ok &= r["outcome"] == "solved" and "RR-1" in r["body"]
    r = build({"result": {"repair_status": "repaired", "verification_status": "unverified"},
               "owner_message": {"kind": "solved", "text": "x" * 30}, "transport_verdict": "delivered"})
    ok &= r["outcome"] == "specialist_follow_up"          # never say solved without verification
    r = build({"result": {"repair_status": "advice_delivered"}, "transport_verdict": "delivered",
               "owner_message": {"kind": "owner_action", "text": "Open your billing page and add a payment card."}})
    ok &= r["outcome"] == "owner_action" and "billing page" in r["body"]
    r = build({"result": {}, "transport_verdict": "failed",
               "owner_message": {"kind": "owner_action", "text": "Open your billing page and add a payment card."}})
    ok &= r["outcome"] == "specialist_follow_up"          # the turn failed, so do not present instructions as final
    r = build({"result": {}, "transport_verdict": "delivered",
               "owner_message": {"kind": "answer", "text": "Set OPENAI_API_KEY=sk-aaaaaaaaaaaaaaaaaaaaaaaa in settings."}})
    ok &= "sk-aaaa" not in r["body"] and "[removed]" in r["body"]
    ok &= "repair_not_verified" not in build({"result": {"remaining_blocker": {"reason": "repair_not_verified"}}})["body"]
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    try:
        doc = json.load(sys.stdin)
    except ValueError:
        doc = {}
    print(json.dumps(build(doc if isinstance(doc, dict) else {}), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
