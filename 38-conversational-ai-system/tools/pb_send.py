#!/usr/bin/env python3
"""pb_send.py — the one chokepoint between a Purple agent and GHL.

WHY THIS EXISTS (review Wave 1, finding C1)
-------------------------------------------
The only live conversation path was a GHL webhook whose server-mapping template
told the model to "SEND your reply via the GHL Conversations API (POST
conversations/messages)".  Nothing called ``DurableStore.admit_event`` or
``outbound_gate.dispatch``, so a webhook retry produced a second agent run and a
second reply, and opt-out / refusal / the human fence / quiet hours depended on
the model following prose.

Two subcommands, stdlib only:

``admit``
    Persist provider-event identity BEFORE the agent may speak.  A duplicate
    ``message.id`` exits **3** and the agent must end the turn.

``reply``
    Create one durable reply intent (key
    ``reply:<tenant>:<contact>:<inbound message_id>``), queue it, and dispatch it
    through ``outbound_gate`` with the composed evaluator
    ``consent_gate -> HandoffStore.gate_decision -> answer_duty``.  The sender is
    the GHL transport from C2 (``outbound_sender.make_sender``) or the offline
    ``JournalTransport`` when ``--transport journal`` is explicit.

EXIT CODES
    0  admitted / sent (or already applied)
    2  usage or contract error (nothing sent)
    3  duplicate admission — END THE TURN, do not reply
    4  gate blocked (SUPPRESSED / QUARANTINED / WAIT_UNTIL) — do not send
    5  not claimed (already dispatched / unknown / lease held) — do not send

Never prints a credential.  Never sends on a gate that did not ALLOW.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _emit(payload: dict) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _load(name):
    return __import__(name)


def _compose(*evaluators):
    """Every evaluator must ALLOW. The first non-ALLOW answer is the answer."""
    def evaluator(ctx):
        for one in evaluators:
            answer = one(ctx)
            verdict = answer if isinstance(answer, str) else answer.get("verdict")
            if verdict != "ALLOW":
                return answer
        return {"verdict": "ALLOW", "evidence": {"composed": True}}
    return evaluator


def cmd_admit(args) -> int:
    ds = _load("durable_store")
    store = ds.DurableStore(args.outbox)
    try:
        result = store.admit_event(
            provider="ghl", tenant_id=args.tenant,
            provider_event_id=args.message_id, direction=args.direction,
            actor_id=args.contact, own_actor_ids=tuple(args.own_actor or ()),
        )
    finally:
        store.close()
    payload = {"command": "admit", "admitted": bool(result["admitted"]),
               "reason": result["reason"],
               "provider_event_id": args.message_id}
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not result["admitted"]:
        return 3
    return 0


def _sender(args, store, outbox_ctx):
    if args.transport == "journal":
        if not args.journal:
            raise SystemExit("--journal is required with --transport journal")
        df = _load("direct_fulfillment")
        return df.JournalTransport(args.journal)
    # GHL: the Skill 44 public adapter, never a new HTTP client.
    skill06 = Path(__file__).resolve().parents[2] / "06-ghl-install-pages" / "tools"
    if str(skill06) not in sys.path:
        sys.path.insert(0, str(skill06))
    client = _load("ghl_public_client")
    pit = os.environ.get(args.pit_env, "")
    if not pit:
        raise SystemExit("missing credential env %s (value never printed)" % args.pit_env)
    adapter, transport = client.make_adapter(args.tenant, pit)
    from cli_anything.gohighlevel.public.auth import TenantBinding
    from cli_anything.gohighlevel.public.outbound_sender import make_sender
    return make_sender(
        adapter, TenantBinding(location_id=args.tenant, source="pb_send"),
        transport=transport, sent_index_path=args.sent_index,
        approval=args.approval_ref,
    )


def _evaluator(args):
    ti = _load("tenant_identity")
    cg = _load("consent_gate")
    og = _load("outbound_gate")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared-utils" / "handoff"))
    handoff_mod = _load("handoff")

    identity = ti.TenantIdentity(args.identity_db)
    consent = cg.ConsentStore(identity)
    handoffs = handoff_mod.HandoffStore(args.handoff_db or args.identity_db)

    def handoff_gate(ctx):
        action = ctx.get("action") or {}
        return handoffs.gate_decision(action.get("tenant_id"),
                                      action.get("canonical_contact_id"))

    return _compose(cg.make_gate_evaluator(consent), handoff_gate,
                    og.answer_duty_evaluator())


def cmd_reply(args) -> int:
    ds = _load("durable_store")
    og = _load("outbound_gate")
    store = ds.DurableStore(args.outbox)
    try:
        intent = "reply:%s:%s:%s" % (args.tenant, args.contact,
                                     args.inbound_message_id)
        digest = hashlib.sha256(args.text.encode("utf-8")).hexdigest()
        row, _created = store.create_intent(
            logical_intent_key=intent,
            idempotency_key="idem:" + hashlib.sha256(intent.encode()).hexdigest()[:32],
            tenant_id=args.tenant, scope="person_directed",
            canonical_contact_id=args.contact, content_sha256=digest,
            purpose="reply",
        )
        store.queue(row["action_id"])
        context = {
            "channel": args.channel,
            "text": args.text,
            "contact_id": args.contact,
            "conversation_id": args.conversation_id,
            "approval_ref": args.approval_ref,
        }
        if args.answer_duty_log:
            context["answer_duty_log"] = Path(args.answer_duty_log).read_text()
        outcome = og.dispatch(
            store, _evaluator(args), _sender(args, store, context),
            row["action_id"], args.worker_id, context=context,
        )
    finally:
        store.close()
    payload = {"command": "reply", "status": outcome.status,
               "action_id": outcome.action_id, "verdict": outcome.verdict,
               "note": outcome.note,
               "provider_receipt": outcome.provider_receipt}
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    if outcome.sent:
        return 0
    if outcome.status == og.ST_BLOCKED:
        return 4
    return 5


def build_parser():
    parser = argparse.ArgumentParser(description="Purple send chokepoint")
    sub = parser.add_subparsers(dest="command", required=True)

    admit = sub.add_parser("admit", help="persist inbound event identity first")
    admit.add_argument("--outbox", required=True)
    admit.add_argument("--tenant", required=True)
    admit.add_argument("--message-id", required=True)
    admit.add_argument("--contact", default=None)
    admit.add_argument("--direction", default="inbound")
    admit.add_argument("--own-actor", action="append", default=[])
    admit.set_defaults(func=cmd_admit)

    reply = sub.add_parser("reply", help="gate-composed reply through one sender")
    reply.add_argument("--outbox", required=True)
    reply.add_argument("--tenant", required=True)
    reply.add_argument("--contact", required=True)
    reply.add_argument("--channel", required=True)
    reply.add_argument("--text", required=True)
    reply.add_argument("--inbound-message-id", required=True)
    reply.add_argument("--conversation-id", default=None)
    reply.add_argument("--identity-db", required=True)
    reply.add_argument("--handoff-db", default=None)
    reply.add_argument("--transport", choices=["journal", "ghl"], default="journal")
    reply.add_argument("--journal", default=None)
    reply.add_argument("--sent-index", default=None)
    reply.add_argument("--approval-ref", default=None)
    reply.add_argument("--pit-env", default="GHL_LOCATION_PIT")
    reply.add_argument("--answer-duty-log", default=None)
    reply.add_argument("--worker-id", default="pb-send")
    reply.set_defaults(func=cmd_reply)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
