# Channel responder ownership — one responder per conversation

**Status:** workflow WF28 interface checkpoint `WF28-CP01` (frozen).
**Machine-checked by** `tools/responder_policy.py`, its suite
`tools/tests/test_responder_policy.py`, and `scripts/qc-responder-policy.sh`.

A location can have three things that answer a person at once: the OpenClaw
brain (this skill), GHL Workflow AI steps, and a native GHL Conversation AI
agent. The native agent is **not** an interchangeable replacement for the
brain. Before any native agent is created or switched on, the operator records
which component answers each channel. The record is the authority; a second
declared responder is a refusal, not a preference.

Source contract: the GHL Hybrid implementation specification v3.0 §25
(native Conversation AI and single-responder ownership). Activation behaviour is
detailed in `references/native-ghl-ai-provisioning.md`; the layer distinction is
in `references/GHL_AI_LAYERS.md`.

## 1. The routing record

One record per location, stored with the location's Skill 38 configuration
(never in the repo, never in a prompt). Schema version 1:

```json
{
  "schema_version": 1,
  "record_id": "responders/<location_id>",
  "location_id": "SYNTHETIC_LOCATION",
  "channels": {
    "sms": {
      "native_channel": "SMS",
      "primary_responder": "openclaw_inbound",
      "native_mode": "off",
      "handoff": {
        "trigger": "customer_requests_human",
        "pauses_automation": true,
        "resumes_on": "operator_release"
      },
      "workflow_sends": {
        "allowed": false,
        "deduplicates_with_primary": true,
        "reason": "the primary responder owns every send on this channel"
      },
      "identity": {
        "contact_identity": "canonical_contact_id",
        "thread_identity": "conversation_id"
      },
      "allowed_actions": ["reply", "book_appointment", "escalate_to_human"],
      "limits": {"opt_out": true, "quiet_hours": true, "client_test_mode": true}
    }
  },
  "production_primary": {
    "agent_id": "SYNTHETIC_NATIVE_AGENT",
    "snapshot_ref": "snapshots/<agent>.before.json",
    "approved_switch_ref": null,
    "switched": false
  },
  "quiet_hours": {"start": "21:00", "end": "08:00", "offset_minutes": -300},
  "native_prompt": {"effective_prompt_field": "fullPrompt"}
}
```

Every field is required per channel except `production_primary`, `quiet_hours`
and `native_prompt`, which are optional when absent means "no native agent and
no quiet-hours window recorded". Unknown properties are refused at every level:
a customer message, a model output or a pasted JSON blob can never add policy.

`primary_responder` is one of `openclaw_inbound`, `native_ghl`, `none`.
`none` is refused (an inbound channel always needs exactly one responder).
`native_mode` is one of `off`, `suggestive`, `auto-pilot`.

| primary_responder | native_mode | Verdict |
|---|---|---|
| `openclaw_inbound` | `off` | `ALLOW_LOCAL` — the brain answers |
| `native_ghl` | `suggestive` | `ALLOW_NATIVE_SUGGESTIVE` — native drafts, a human sends |
| `native_ghl` | `auto-pilot` | `ALLOW_NATIVE_AUTOPILOT` — native sends |
| `openclaw_inbound` | not `off` | refused `REFUSE_RESPONDER_CONFLICT` (two senders) |
| `native_ghl` | `off` | refused `REFUSE_NO_RESPONDER` (nobody answers) |

## 2. Channel map (explicit, never coerced)

The native Conversation AI contract enumerates exactly seven channels. The
internal Skill 38 names map deliberately:

| Skill 38 name(s) | Native enumeration |
|---|---|
| `sms`, `text`, `phone` | `SMS` |
| `email` | `Email` |
| `fb`, `facebook`, `facebook_dm`, `messenger` | `FB` |
| `ig`, `instagram`, `instagram_dm` | `IG` |
| `whatsapp` | `WhatsApp` |
| `webchat`, `web_chat`, `web_chat_widget` | `WebChat` |
| `live_chat`, `livechat`, `live-chat` | `Live_Chat` |

`webchat` and `live_chat` are different destinations and are never merged. The
bare label `chat` is ambiguous and is refused — name the real destination.

These are refused, not coerced: `linkedin`, `fb_comment` / `fb_comments` /
`facebook_comments`, `instagram_comments`, `all_in_one` / `all_in_one_chat`,
`gmb`, `tiktok`, `youtube`, and any unrecognized name. For those contexts the
existing local responder (or a verified native equivalent) is used; the local
skill's support for a channel never invents a native enumeration. A record that
maps two internal names onto the same native channel is refused
`REFUSE_TWO_RESPONDERS`; one destination has one responder.

## 3. Handoff, opt-out, quiet hours, returning contacts

- `handoff.trigger` must name the condition; `handoff.pauses_automation` must be
  `true`. On takeover both local and native dispatch are suppressed until an
  authorised operator release.
- Opt-out is absolute: `suppression_state` `global_stop` or `channel_opt_out`
  returns `SUPPRESS_OPT_OUT`, whichever responder owns the channel.
- Quiet hours: when the record carries a window and `now` falls inside it, the
  verdict is `WAIT_QUIET_HOURS` — queue, never drop, never send.
- A returning contact is allowed again only after the previous thread lease is
  released or expires. The lease is the same mechanism that suppresses two
  nearly simultaneous inbound messages.

`limits.opt_out`, `limits.quiet_hours` and `limits.client_test_mode` must all be
`true`. A record that turns any of them off is refused
`REFUSE_POLICY_WEAKENED`: routing never disables an existing hard gate.

## 4. The thread lease (dedupe across local and native dispatch)

`ResponderLease` keeps one active lease per `(tenant_id, thread_ref)` in the
existing Skill 38 SQLite conversation database. The thread identity is the
record's `identity.thread_identity` (`conversation_id` or `thread_id`); the
contact identity is `canonical_contact_id` from `tools/tenant_identity.py`.
Local and native dispatch both ask the same lease, so an inbound event cannot
produce one reply from each.

| Situation | Result |
|---|---|
| first inbound event on a free thread | lease acquired, responder verdict returned |
| a second provider event on the same thread inside the TTL | `SUPPRESS_DUPLICATE_EVENT` |
| the same provider `message_id` re-delivered | `SUPPRESS_DUPLICATE_EVENT` |
| human takeover | holder becomes `human:<actor>`, no expiry; every bot send `SUPPRESS_HUMAN_TAKEOVER` |
| operator release | lease clears; the next inbound (a returning contact) is allowed |

Default TTL is 120 seconds (`--ttl`). A takeover has **no** expiry: only
`release` lifts it, and only the holder that owns it may release.

## 5. Effective prompt

A non-empty native `fullPrompt` is the effective generation instruction instead
of the separate personality/goal/instructions fields. `native_prompt.
effective_prompt_field` must be `fullPrompt`. The native adapter refuses a write
whose intended field would be shadowed by an existing non-empty `fullPrompt`
(`prompt_ineffective`) and tests the effective prompt, not only saved text
fields. See `references/native-ghl-ai-provisioning.md`.

## 6. Creation and switch safety

- New native agents are created in a non-sending mode first (`native_mode:
  "off"`), then read back, then explicitly moved to `suggestive` or
  `auto-pilot` with an approval reference.
- An existing production primary agent is never switched by the adapter. The
  record's `production_primary.switched: true` requires both
  `approved_switch_ref` and `snapshot_ref`, and the adapter refuses every
  primary-ownership write: that transition is a separate, approved step.
- A configuration snapshot is taken before any change; rollback instructions
  accompany the handoff.

## 7. Running the proof

```bash
bash 38-conversational-ai-system/scripts/qc-responder-policy.sh
python3 38-conversational-ai-system/tools/tests/test_responder_policy.py

python3 38-conversational-ai-system/tools/responder_policy.py \
  validate --record <record.json>
python3 38-conversational-ai-system/tools/responder_policy.py \
  resolve --record <record.json> --channel sms \
  --event '{"kind":"inbound","message_id":"msg_1"}'
python3 38-conversational-ai-system/tools/responder_policy.py channel-map linkedin
```

Exit `0` = accepted/valid, `1` = refused/invalid, `2` = usage or IO. The suite
is offline and stdlib-only; no native agent is created and no message is sent.
