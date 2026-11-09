# Native GHL Conversation AI provisioning — non-sending first, owner last

**Scope:** how an operator provisions, reads back and activates a NATIVE GHL
Conversation AI agent without replacing the OpenClaw brain by accident.
**Owners:** WF28 (this document, the policy module and the adapter),
WF27 (voice/phone), WF30 (knowledge-base attachment), WF00 (operation rows),
WF03 (CLI registration).
**Machine-checked by:** `tools/responder_policy.py`,
`tools/tests/test_responder_policy.py`,
`cli_anything/gohighlevel/public/conversation_ai.py`,
`cli_anything/gohighlevel/tests/test_conversation_ai.py`,
`scripts/qc-responder-policy.sh`.

Read `protocols/channel-responder-ownership.md` first: the routing record, not
this runbook, decides who answers. Read `references/GHL_AI_LAYERS.md` for how the
native agent differs from Layers 0, 1 and 2.

## 1. What the native agent is, and is not

| | Native Conversation AI agent | OpenClaw brain (Layer 2) |
|---|---|---|
| Who configures it | GHL, through the capability-gated public API | This skill, in the operator's master files |
| Channels | exactly `IG`, `FB`, `SMS`, `WebChat`, `WhatsApp`, `Live_Chat`, `Email` | whatever the inbound hook accepts |
| Modes | `off`, `suggestive`, `auto-pilot` | local policy (draft/send/handoff) |
| Knowledge | the agent's attached GHL knowledge sources | typed KBs + conversation logs + playbooks |
| Hard gates | whatever GHL offers | opt-out, quiet hours, honesty floor, client test mode, the 32+ protocols |
| Effective prompt | a non-empty `fullPrompt` overrides personality/goal/instructions | the active conversation playbook |

The native agent is a **separate surface**, not Layer 1 and not a replacement
for Layer 2. A location may run it only on channels the routing record assigns
to it. Workflow AI steps remain compile-time/runtime workflow artifacts and are
not a responder.

## 2. Provisioning sequence (Document 1 §25.3)

1. **Inventory** existing native agents (`conversation-ai inventory`). Record
   each one's id, name, mode, channels and whether it is a production primary.
2. **Compile approved behaviour from Skill 38**: the goal, tone, allowed
   actions, knowledge sources and limits come from the conversation playbook and
   the routing record — never from customer content.
3. **Validate channels and knowledge sources** against the exact enumeration.
   LinkedIn, public comments, all-in-one labels and any unlisted destination are
   refused, never coerced. WebChat and Live_Chat are different destinations.
4. **Create or update through Skill 44** (`conversation-ai create|update`). The
   command goes through the capability-gated public adapter: operation row,
   tenant binding, auth class, approval, idempotency fingerprint and read-back
   all still apply.
5. **Read back settings** and compare the fields that control reply behaviour.
   A 2xx alone is not proof.
6. **Configure the inbox/widget/channel association** (widget behaviour belongs
   to WF31; this lane owns the responder side of the thread).
7. **Test with an allowlisted contact** on the test environment. Never a real
   customer.
8. **Verify the actual thread and message identity** — a generated answer in a
   preview is not a delivered message.
9. **Assess behaviour independently** of the build.
10. **Authorise auto-pilot or primary-agent status separately** (see §5).

## 3. Non-sending first

- `conversation-ai create` accepts **only** mode `off`. A create request for
  `suggestive` or `auto-pilot` is refused before transport with
  `conversation_create_must_be_non_sending`. Create off, read back, then move.
- A mode change is a separate `update` and requires an approval reference; a
  change to `auto-pilot` additionally requires the operator's own authorization
  outside this adapter.
- Before any update the adapter reads the CURRENT agent and returns a snapshot
  of the response-behaviour fields (`id`, `name`, `mode`, `channels`,
  `fullPrompt`, `personality`, `goal`, `instructions`, `status`, `updatedAt`)
  with a SHA-256 digest. Keep that snapshot beside the run manifest; it is the
  rollback payload.

## 4. `fullPrompt` precedence

The native create schema makes a non-empty `fullPrompt` the effective generation
instruction **instead of** the separate personality/goal/instructions fields.

- `effective_prompt()` returns `fullPrompt` when it is non-empty, and names the
  structured fields it shadowed.
- The adapter refuses a write whose intended field would be shadowed:
  `prompt_ineffective`. Saving "personality" while a non-empty `fullPrompt`
  exists changes nothing at reply time, so it is refused rather than silently
  stored.
- Test the effective prompt, not the saved text fields:
  `conversation-ai effective-prompt --agent-id <id>`.
- When `fullPrompt` is empty, the structured fields are the effective prompt and
  are returned as a deterministic composition.

## 5. Existing production primary agents

This adapter **never** switches primary ownership. Any patch naming
`primary`, `isPrimary`, `is_primary`, `primaryAgent` or `primary_agent` is
refused with `primary_switch_requires_separate_authorization`.

A routing record may describe an existing primary (`production_primary`), but:

- `switched: true` requires `approved_switch_ref` **and** `snapshot_ref`;
- without both, the record is refused (`REFUSE_PRIMARY_SWITCH_UNAPPROVED` /
  invalid record), and the old agent keeps answering;
- the actual switch is a separate, explicitly approved operator action with its
  own snapshot and rollback.

## 6. Channels

| Skill 38 | Native |
|---|---|
| `sms`, `text`, `phone` | `SMS` |
| `email` | `Email` |
| `fb`, `facebook`, `facebook_dm`, `messenger` | `FB` |
| `ig`, `instagram`, `instagram_dm` | `IG` |
| `whatsapp` | `WhatsApp` |
| `webchat`, `web_chat`, `web_chat_widget` | `WebChat` |
| `live_chat`, `livechat`, `live-chat` | `Live_Chat` |

Refused: `linkedin`, `fb_comment`/`fb_comments`/`facebook_comments`,
`instagram_comments`, `all_in_one`/`all_in_one_chat`, `gmb`, `tiktok`,
`youtube`, the ambiguous bare `chat`, and anything else. For those contexts keep
the local responder or use a verified native equivalent; local support for a
channel never invents a native enumeration.

## 7. One responder, one lease

Native and local dispatch share the conversation-thread lease in
`tools/responder_policy.py`. Two messages arriving close together, a redelivered
provider event, a human takeover, an opt-out and a returning contact all resolve
there. A response from two different agents to the same input is a failure
unless the approved design explicitly requires it — and the routing record has
no vocabulary for "two responders", so it cannot be declared.

Preserved hard gates: the local brain, THE TRINITY, opt-out, quiet hours and
client test mode stay in force. A routing record that disables any of them is
refused (`REFUSE_POLICY_WEAKENED`). Customer/source content can never add an
administrative action; the record's `allowed_actions` is the only authority and
unknown properties are refused.

## 8. Upstream dependency and what is NOT verified

- The four operation rows (`conversation_ai.agents.list|get|create|update`) are
  **WF00-owned**. They are not frozen on the current branch. The adapter refuses
  at construction with `conversation_operations_missing`, naming the checkpoint
  `WF00 operation rows for native Conversation AI`; it never guesses a path or a
  Version. Change request: `change-requests/WF00/` (native Conversation AI rows).
- The marketplace documentation page renders an application shell and returned
  no operation list when re-read on 2026-11-08, so no path or Version is claimed
  here. The body field names used by the adapter (`name`, `channels`, `mode`,
  `fullPrompt`, `personality`, `goal`, `instructions`) are the ones named in the
  implementation specification §25; they are not a substitute for the frozen
  rows.
- Live activation is **NOT RUN** in the build lane: no real agent was created,
  no message was sent, no client account was touched. A unit/offline proof is
  not live proof.

## 9. Handoff and rollback

The handoff must identify: the active responder per channel, native mode, the
attached knowledge sources, the test evidence, the snapshot reference and the
rollback command. Do not describe a local playbook change as a native GHL change
unless the native API/UI was actually updated; conversely do not claim a native
preview as delivered customer behaviour.

Rollback: re-apply the snapshot through the same approved update path (mode back
to `off` first, then the previous prompt fields), or restore the previous agent
configuration in GHL. A primary switch rolls back to the recorded previous
primary only through the same separate approval that made the switch.
