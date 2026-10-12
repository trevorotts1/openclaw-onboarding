#!/usr/bin/env python3
"""person_question: the U9 talk-to-a-person / send-a-question code path (v1, NO live send).

During an interactive drama-song run a client can do two things the choice card
does not cover: ask a free-text QUESTION, or ask to TALK TO A PERSON. Both travel
as ONE payload. This module BUILDS that payload, VALIDATES it at the trust
boundary, and ROUTES it to an epic (the owning work bucket a human picks up from).

Nothing is transmitted. The send is STUBBED at the boundary: ``deliver()`` reuses
the skill's ONE channel-neutral send path
(``choice_card.intake_card.channel_send``) with a RECORDING sink, so the stub
records exactly what WOULD have been sent (the ``openclaw message send`` argv) and
the client's device is never touched. With a run_dir, each question appends one
JSON line to ``<run_dir>/control/person-question.jsonl`` -- the same ``control/``
folder ``channel_send.device_notice`` already records into. No new sender, no new
adapter, no network, no credential.

Routing is load-bearing: the epic decides the target the message would go to when
the caller names none, so two different questions take two different routes.

Stdlib only. The sink is always the recording sink, so the transport never runs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

SCHEMA = "blackceo.person-question/v1"
#: The two things a client can send. A person request is not a support question.
KINDS = ("question", "talk-to-a-person")
#: Longest client question this path accepts. Beyond it the card asks for a shorter one.
MAX_TEXT = 2000
#: Refused (invalid or unroutable) send: the same exit code the skill's gates use.
REFUSED_EXIT = 5

DEFAULT_EPIC = "intake"
HANDOFF_EPIC = "handoff"

#: epic id -> (routing inbox, topic keywords). The inbox is the target the message
#: would be sent to when the caller names none; topic keywords route by content.
#: Ordered: the FIRST keyword match wins, so the order is part of the contract.
EPICS = (
    ("billing", "inbox:billing",
     ("price", "cost", "refund", "charge", "invoice", "payment", "money",
      "discount", "quote", "bill", "pay", "budget")),
    ("song", "inbox:song",
     ("song", "music", "lyric", "lyrics", "voice", "sing", "melody",
      "instrumental", "chorus")),
    ("storyboard", "inbox:storyboard",
     ("storyboard", "shot", "image", "picture", "photo", "frame", "scene")),
    ("delivery", "inbox:delivery",
     ("deliver", "download", "file", "link", "caption", "export", "clip", "receive")),
)
#: The handoff epic is reached by the KIND (talk-to-a-person) or by name, never by
#: a topic keyword -- a person request about billing still routes to billing.
_EPIC_INBOX = {e: inbox for e, inbox, _kw in EPICS}
_EPIC_INBOX[HANDOFF_EPIC] = "inbox:handoff"
_EPIC_INBOX[DEFAULT_EPIC] = "inbox:intake"

class QuestionError(ValueError):
    """The payload is invalid or unroutable. ``reason_code`` names the exact failure."""

    def __init__(self, reason_code, detail=""):
        super().__init__("%s%s" % (reason_code, (": " + detail) if detail else ""))
        self.reason_code = reason_code
        self.detail = detail

def _channel_send():
    """The ONE existing send path (U11). Imported lazily so this module loads
    standalone (the battery loads it by file path, without the package)."""
    from choice_card.intake_card import channel_send as CS   # noqa: PLC0415
    return CS

def inbox_for(epic):
    """The routing inbox a resolved epic sends to (None when the epic is unknown)."""
    return _EPIC_INBOX.get(epic)

def build(kind, text, run_id, target="", contact="", channel="app", epic=None):
    """Build the payload. Static fields are validated here and a bad payload is
    REFUSED loudly (never built then sent). ``target`` may be empty -- it is then
    resolved from the epic in :func:`route`."""
    payload = {
        "schema_version": SCHEMA,
        "kind": kind,
        "text": (text or "").strip(),
        "run_id": (run_id or "").strip(),
        "target": (target or "").strip(),
        "contact": (contact or "").strip(),
        "channel": channel,
        "epic": epic or "",
    }
    validate(payload)
    return payload

def validate(payload):
    """The trust boundary. Raises :class:`QuestionError` on the FIRST problem;
    returns the payload when it is sound."""
    if payload.get("kind") not in KINDS:
        raise QuestionError("unknown-kind",
                            "%r is not one of %s" % (payload.get("kind"), ", ".join(KINDS)))
    text = payload.get("text") or ""
    if not text.strip():
        raise QuestionError("empty-text", "the question is empty")
    if len(text) > MAX_TEXT:
        raise QuestionError("text-too-long", "%d chars > %d" % (len(text), MAX_TEXT))
    if not (payload.get("run_id") or "").strip():
        raise QuestionError("missing-run-id", "a question is bound to a run")
    channel = payload.get("channel")
    if channel not in _channel_send().CHANNELS:
        raise QuestionError("unknown-channel", "%r is not a delivery channel" % (channel,))
    epic = payload.get("epic") or ""
    if epic and epic not in _EPIC_INBOX:
        raise QuestionError("unknown-epic", "%r is not a known epic" % (epic,))
    return payload

def route(payload):
    """Resolve the payload to an epic. Returns
    ``{"epic", "inbox", "target", "matched", "routed_by", "reason_code"}``.

    Order: an explicit epic wins; else the first topic keyword match; else the
    talk-to-a-person KIND; else the default intake epic. ``target`` is the caller's
    own target when named, else the epic's routing inbox."""
    text = (payload.get("text") or "").lower()
    epic = payload.get("epic") or ""
    matched = "explicit"
    routed_by = "explicit"
    if not epic:
        matched = ""
        routed_by = ""
        for eid, _inbox, keywords in EPICS:
            hit = next((k for k in keywords if k in text), None)
            if hit:
                epic, matched, routed_by = eid, hit, "topic"
                break
    if not epic and payload.get("kind") == "talk-to-a-person":
        epic, matched, routed_by = HANDOFF_EPIC, "kind:talk-to-a-person", "kind"
    if not epic:
        epic, matched, routed_by = DEFAULT_EPIC, "default", "default"
    inbox = inbox_for(epic)
    target = (payload.get("target") or "").strip() or inbox
    return {"epic": epic, "inbox": inbox, "target": target, "matched": matched,
            "routed_by": routed_by, "reason_code": "route-%s" % routed_by}

def _message(payload):
    """The plain message that WOULD be sent. No Markdown, so nothing is stripped."""
    label = ("TALK TO A PERSON" if payload["kind"] == "talk-to-a-person" else "QUESTION")
    lines = ["%s - run %s" % (label, payload["run_id"])]
    if payload.get("contact"):
        lines.append("Reply to: %s" % payload["contact"])
    lines.append("")
    lines.append(payload["text"])
    return "\n".join(lines)

def _record_path(run_dir):
    return os.path.join(run_dir, "control", "person-question.jsonl")

def _append_record(run_dir, record):
    os.makedirs(os.path.join(run_dir, "control"), exist_ok=True)
    with open(_record_path(run_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")

def deliver(payload, run_dir=None):
    """Validate, route, and hand the composed argv to the RECORDING sink -- never
    the transport. Returns the record of what WOULD have been sent (``sent`` is
    always False) and appends it to ``<run_dir>/control/person-question.jsonl``
    when a run_dir is given."""
    validate(payload)
    r = route(payload)
    if not r["target"]:
        raise QuestionError("missing-target", "no target named and the epic has none")
    message = _message(payload)
    captured = []                       # the recording sink: the stub of the send boundary
    argv = _channel_send().CHANNEL_SEND[payload["channel"]](r["target"], message,
                                                            sink=captured.append)
    record = {
        "schema_version": SCHEMA,
        "kind": payload["kind"],
        "run_id": payload["run_id"],
        "contact": payload.get("contact", ""),
        "channel": payload["channel"],
        "epic": r["epic"],
        "routed_by": r["routed_by"],
        "matched": r["matched"],
        "reason_code": r["reason_code"],
        "target": r["target"],
        "message": message,
        "argv": argv,                   # EXACTLY what would have been sent
        "sent": False,                  # the stub never transmits
        "stubbed": len(captured) == 1,  # the sink the send path actually reached
    }
    if run_dir:
        _append_record(run_dir, record)
    return record

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build, validate and route a talk-to-a-person / send-a-question "
                    "payload to an epic. Nothing is sent: the stub records the argv.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask")
    a.add_argument("--kind", choices=KINDS, default="question")
    a.add_argument("--text", required=True)
    a.add_argument("--run-id", required=True)
    a.add_argument("--target", default="")
    a.add_argument("--contact", default="")
    a.add_argument("--channel", default="app")
    a.add_argument("--epic", default="")
    a.add_argument("--run-dir", default="")
    ns = ap.parse_args(argv)
    try:
        payload = build(ns.kind, ns.text, ns.run_id, target=ns.target,
                        contact=ns.contact, channel=ns.channel, epic=ns.epic or None)
        print(json.dumps(deliver(payload, run_dir=ns.run_dir or None), sort_keys=True))
    except QuestionError as e:
        sys.stderr.write("REFUSED %s: %s\n" % (e.reason_code, e.detail))
        return REFUSED_EXIT
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
