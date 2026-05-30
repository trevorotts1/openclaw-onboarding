<!-- OPERATOR HEADER -->
<!-- Skill 38 reference/protocol doc — the GHL RAW BODY JSON STANDARD. -->
<!-- Full content lives here (not in AGENTS.md/TOOLS.md — those get a 1-2 line pointer only). -->
<!-- 23-key rule honored: the GHL RAW BODY here = all 23 keys, FLAT, placeholder-free messageTemplate, no \n. -->
<!-- Added 2026-05-30 by skill38-three-qc-standards. -->

# GHL Raw Body JSON Standard (Skill 38)

The **GHL Custom Webhook Raw Body** is the JSON payload GHL (Convert and Flow) POSTs to the OpenClaw
public hook URL when an inbound message fires a workflow. This file is the **single standard** for what
that body must be. The authoritative source-of-truth spec lives in
`references/GHL-INBOUND-AND-PLAYBOOKS.md` §0-§2 (the 23-key section); this doc codifies it as the single,
human-readable standard, and the rule is **machine-enforced** by `scripts/qc-23-key-bodies.sh` and the
new `scripts/qc-ghl-raw-body-standard.sh`.

> Do not confuse the GHL RAW BODY (this standard, "object A": snake_case `agent_id`, FLAT) with the
> OpenClaw `hooks.mappings` server entry ("object B": camelCase `agentId`, a nested `match:{path}`, and a
> TEMPLATED `messageTemplate`). They are different objects in different systems. This standard governs the
> RAW BODY only. See `references/GHL-INBOUND-AND-PLAYBOOKS.md` §4 for the server mapping.

---

## 0. EVERY GHL CUSTOM WEBHOOK RAW BODY MUST BE THE FULL 23-KEY FLAT JSON

> **THIS IS THE STANDARD. NON-NEGOTIABLE. NO EXCEPTIONS (OWNER DIRECTIVE).** Every GHL Custom Webhook Raw
> Body — in this doc, in `references/GHL-INBOUND-AND-PLAYBOOKS.md`, in `references/v6.0-source-playbook.md`,
> in the scripts, the templates, and the protocols — MUST be the FULL **23-key FLAT** JSON below. **23 is
> the MINIMUM AND the standard — never fewer, never nested.** No stripped/short bodies (no 4-key, 8-key,
> 11-key, 13-key, or 16-key versions) are allowed ANYWHERE in this skill. A sub-23-key body is a stripped
> body and is machine-FAILED. A nested body makes EVERY field resolve EMPTY at the hook (proven: even a
> hardcoded `"channel":"sms"` arrived blank when nested) and is machine-FAILED. This is enforced by
> `scripts/qc-23-key-bodies.sh` (CI + pre-handoff QC) and asserted as a standard by
> `scripts/qc-ghl-raw-body-standard.sh`.

The four hard rules:

- [ ] **(1) ALL 23 keys, every time.** 23 is the minimum AND the canonical shape. Never reduce, "simplify,"
      or drop keys. Where a smaller body appears, replace it with the 23-key body.
- [ ] **(2) FLAT — no nested objects.** No nested `contact:{…}` / `customer_message:{…}` / `message:{…}`.
      A nested body makes every field arrive EMPTY at the hook. Each field is its own top-level key.
- [ ] **(3) `messageTemplate` in the BODY is a placeholder-free stub.** Its VALUE must contain NO `{{…}}`
      tokens, or GHL tries to expand them as its own merge fields, mangles the JSON, and Skips the webhook.
      The REAL run-time template (with the send-directive + conversation-memory steps) lives **server-side
      only** in the `hooks.mappings` entry — NOT in the body.
- [ ] **(4) `deliver` is `false`.** The agent replies via the GHL Conversations API (it does not let the
      gateway auto-deliver). No literal `\n` escapes anywhere in the JSON (single-line JSON string values).

## 1. The 23 keys (exact, in order) + one-line purpose each

| # | Key | Purpose |
|---|-----|---------|
| 1 | `id` | The hook/route id — matches the client's `hooks.mappings` entry + the workflow-AI `id`. |
| 2 | `match` | The route match token (the per-client hook name; mirrors `id`). |
| 3 | `action` | Always `agent` — this inbound is handled by an agent, not a static reply. |
| 4 | `agent_id` | Which agent runs this inbound (e.g. `main`, `sales`) — the routing agent. |
| 5 | `model` | The model the agent runs on (e.g. `ollama/deepseek-v4-flash:cloud`). |
| 6 | `wakeMode` | `now` — process the inbound immediately (not queued/deferred). |
| 7 | `name` | Human-readable label for the inbound (e.g. `GHL Sales Inbound`). |
| 8 | `session_key` | The conversation session key — `hook:ghl:<channel>:{{contact.id}}` (channel + contact). |
| 9 | `messageTemplate` | The placeholder-free body stub (the REAL template is server-side; see §0 rule 3). |
| 10 | `deliver` | `false` — the agent sends via the GHL Conversations API, the gateway does not auto-deliver. |
| 11 | `timeoutSeconds` | Per-inbound agent timeout (e.g. `300`). |
| 12 | `channel` | The inbound channel (`sms`/`email`/`fb`/`instagram`/`whatsapp`/`live_chat`) — mirrored on reply. |
| 13 | `to` | The reply target (the contact's phone for SMS). |
| 14 | `thinking` | Reasoning budget for the agent turn (e.g. `medium`). |
| 15 | `contact_id` | GHL contact id — the thread key GHL uses to thread the reply. |
| 16 | `first_name` | Contact first name (for personalization). |
| 17 | `last_name` | Contact last name. |
| 18 | `email` | Contact email. |
| 19 | `phone` | Contact phone. |
| 20 | `subject` | Inbound subject (used for Email replies). |
| 21 | `message_body` | The actual inbound message text the agent responds to. |
| 22 | `location_id` | GHL location id (the API credential context for the send). |
| 23 | `location_name` | GHL location name (orientation/label). |

The 23 keys (exact): `id`, `match`, `action`, `agent_id`, `model`, `wakeMode`, `name`, `session_key`,
`messageTemplate`, `deliver`, `timeoutSeconds`, `channel`, `to`, `thinking`, `contact_id`, `first_name`,
`last_name`, `email`, `phone`, `subject`, `message_body`, `location_id`, `location_name`.

## 2. The canonical RAW BODY (embed this exactly)

```json
{
  "id": "ghl-sales",
  "match": "ghl-sales",
  "action": "agent",
  "agent_id": "sales",
  "model": "ollama/deepseek-v4-flash:cloud",
  "wakeMode": "now",
  "name": "GHL Sales Inbound",
  "session_key": "hook:ghl:sms:{{contact.id}}",
  "messageTemplate": "Respond as the Sales agent and reply to this contact via the GHL Conversations API per TOOLS.md",
  "deliver": false,
  "timeoutSeconds": 300,
  "channel": "sms",
  "to": "{{contact.phone}}",
  "thinking": "medium",
  "contact_id": "{{contact.id}}",
  "first_name": "{{contact.first_name}}",
  "last_name": "{{contact.last_name}}",
  "email": "{{contact.email}}",
  "phone": "{{contact.phone}}",
  "subject": "{{message.subject}}",
  "message_body": "{{message.body}}",
  "location_id": "{{location.id}}",
  "location_name": "{{location.name}}"
}
```

## 3. Per-channel variants — change ONLY `channel` + the `session_key` prefix

Every channel variant keeps ALL 23 keys. Only TWO values change — `channel` and the `session_key` prefix
(`hook:ghl:<channel>:{{contact.id}}`). The per-client `id`/`match`/`agent_id` are substituted to the
client's hook name + routing agent. Nothing else changes.

- SMS → `"channel":"sms"`, `"session_key":"hook:ghl:sms:{{contact.id}}"`
- Email → `"channel":"email"`, `"session_key":"hook:ghl:email:{{contact.id}}"`
- Facebook Messenger → `"channel":"fb"`, `"session_key":"hook:ghl:fb:{{contact.id}}"`
- Instagram → `"channel":"instagram"`, `"session_key":"hook:ghl:instagram:{{contact.id}}"`
- WhatsApp → `"channel":"whatsapp"`, `"session_key":"hook:ghl:whatsapp:{{contact.id}}"`
- Live Chat → `"channel":"live_chat"`, `"session_key":"hook:ghl:live_chat:{{contact.id}}"`

> **Threading:** the inbound `channel` key is what the agent mirrors when it picks the reply `type`;
> `contact_id` + `location_id` are already keys. On the OUTBOUND send, GHL threads the reply BY
> `contactId` — `conversationId` is never sent, it is looked up only to READ prior history. No key
> changes: the 23-key set above is unchanged for every channel.

## 4. Enforcement

- **Source of truth:** `references/GHL-INBOUND-AND-PLAYBOOKS.md` §0-§2 (the 23-key section) — the
  authoritative owner-directive spec this standard codifies.
- **Machine-enforced:** `scripts/qc-23-key-bodies.sh` scans EVERY GHL RAW BODY example (object A, the
  `agent_id` discriminator) across `references/` + `templates/` + `scripts/` and asserts exactly 23 flat
  keys, a placeholder-free `messageTemplate`, no nested objects, and no literal `\n`. `scripts/qc-ghl-raw-body-standard.sh`
  asserts THIS standard doc carries the 23-key list, the FLAT rule, and the canonical body, and composes
  the existing `qc-23-key-bodies.sh` so the build FAILS on any violation. Both run in
  `scripts/11-run-qc-checklist.sh` + CI `.github/workflows/qc-static.yml`.
- **Related standards:** `references/workflow-ai-instructions-standard.md` §3 (where the body is pasted in
  the Custom Webhook) and `references/communications-playbook-standard.md` §7 (the body as a copyable block
  in the client reference sheet).
