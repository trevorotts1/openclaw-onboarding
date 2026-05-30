# GHL Inbound + Conversation Playbooks — Authoritative Reference (Mac mini / Homebrew)

> **Scope:** This is the canonical, verified reference for wiring GoHighLevel (Convert and Flow)
> inbound messages into OpenClaw and building the agent's conversation playbooks, **for the
> Mac-mini / Homebrew install** (paths `~/clawd/…` and `~/.openclaw/…`, `cloudflared` via launchd).
> It is derived from a live build and supersedes any conflicting prose in
> `v6.0-source-playbook.md`. Where the source playbook and this doc disagree, **this doc wins.**
>
> **Mac vs VPS divergences are flagged inline.** The biggest two:
> 1. `cloudflared` runs via **launchd** (`sudo cloudflared service install`) — needs **interactive sudo**.
> 2. There is **NO Hostinger wrapper**, so the `HOOKS_TOKEN` in `~/.openclaw/openclaw.json` is **stable** —
>    no `OPENCLAW_HOOKS_TOKEN` env trick needed (the VPS repo needs it; the Mac repo does not).

---

## CORRECTED GHL HOOK STRUCTURE (2026-05-29)

> Verified LIVE on a live client, OpenClaw **2026.5.27**. This **supersedes** any older nested-body
> or in-body-`messageTemplate` example anywhere in this skill (this doc, `v6.0-source-playbook.md`, the
> scripts, and the templates).

**CARDINAL RULE — the GHL Custom Webhook RAW BODY is FLAT (no nesting) and carries ALL 23 keys** (owner
directive — 23 is the minimum, no stripped bodies). The body's `messageTemplate` value is kept
**placeholder-free** (no `{{…}}`) so GHL never tries to expand it and never mangles the JSON. The matching
OpenClaw `hooks.mappings` entry in `openclaw.json` is configured separately; the body is what GHL POSTs.

**0) THE GHL RAW BODY MUST CONTAIN ALL 23 KEYS (OWNER DIRECTIVE — NON-NEGOTIABLE).** 23 is the MINIMUM.
No stripped/short bodies (no 8-key, 11-key, or 13-key versions) are allowed ANYWHERE in this skill. Every GHL
Custom Webhook RAW BODY example — in this doc, in `v6.0-source-playbook.md`, in the scripts, the templates,
and the protocols — MUST be the full 23-key body below. Do NOT reduce, "simplify," or drop keys. Where a
smaller body appears, replace it with this 23-key body. **The 23 keys (exact):** `id`, `match`, `action`,
`agent_id`, `model`, `wakeMode`, `name`, `session_key`, `messageTemplate`, `deliver`, `timeoutSeconds`,
`channel`, `to`, `thinking`, `contact_id`, `first_name`, `last_name`, `email`, `phone`, `subject`,
`message_body`, `location_id`, `location_name`.

**1) GHL RAW BODY MUST BE FLAT (no nested objects).** Nested `contact:{…}` / `customer_message:{…}` makes
EVERY field resolve EMPTY at the hook (proven: even a hardcoded `"channel":"sms"` arrived blank when nested).
The `messageTemplate` value in the BODY is kept **placeholder-free** (no `{{…}}`) so GHL never mangles it.
Canonical correct 23-key flat body:

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

**PER-CHANNEL VARIANTS:** every channel variant keeps all 23 keys; only two values change — `channel` and the
`session_key` prefix. SMS → `"channel":"sms"`, `"session_key":"hook:ghl:sms:{{contact.id}}"`.
Facebook Messenger → `"channel":"fb"`, `"session_key":"hook:ghl:fb:{{contact.id}}"`.
Instagram → `"channel":"instagram"`, `"session_key":"hook:ghl:instagram:{{contact.id}}"`.
WhatsApp → `"channel":"whatsapp"`, `"session_key":"hook:ghl:whatsapp:{{contact.id}}"`.
Live Chat → `"channel":"live_chat"`, `"session_key":"hook:ghl:live_chat:{{contact.id}}"`.
Email → `"channel":"email"`, `"session_key":"hook:ghl:email:{{contact.id}}"`.

**2) The GHL body's `messageTemplate` MUST be placeholder-free (no `{{…}}`).** The `messageTemplate` key IS
one of the 23 required body keys, but its VALUE must never contain `{{…}}` tokens. If it did, GHL would try to
expand them as ITS OWN merge fields, fail (they are not valid GHL field names), mangle them to `##{}##`, drop
the closing quote ⇒ GHL error "Error while parsing the object to JSON" ⇒ webhook Skipped. Use the exact
placeholder-free string from the canonical 23-key body above.

**3) The server mapping REQUIRES a `messageTemplate`.** With none, the hook returns
`{"ok":false,"error":"hook mapping requires message"}`.

**4) The server `messageTemplate` MUST include the MANDATORY SEND-DIRECTIVE**, or the agent drafts a reply
but never sends it (zero GHL API calls ⇒ customer gets nothing). Drafting/composing is NOT sending. A
soft "reply via the GHL Conversations API per TOOLS.md" phrasing is NOT enough — the template MUST contain
all of: the word **SEND**, the **GHL Conversations API** (POST `conversations/messages`), the
**drafting-is-NOT-sending** clause, and **"do not end your turn until a messageId/conversationId is
returned."** **Channel-mirroring (not hardcoded SMS):** the directive instructs the agent to reply on the
SAME channel the message arrived on — read `{{channel}}` and set the send `type` to the MIRRORED value
(SMS→`SMS`, Email→`Email`, Facebook→`FB`, Instagram→`IG`, WhatsApp→`WhatsApp`, Live Chat→`Live_Chat`). The
**send body is threaded by `contactId`** — `{type, contactId, locationId, message}` (Email also adds
`subject`/`html`/`emailFrom`/`emailTo`); GHL threads the reply into the contact's conversation BY `contactId`
and returns `conversationId`+`messageId`. **`conversationId` is NEVER a send-body field** — it is the READ
key only (GET `conversations/search?locationId=&contactId=` → GET `conversations/{conversationId}/messages`
to pull thread history). This is machine-enforced by `scripts/qc-send-directive.sh` (CI + pre-handoff QC).
Canonical correct mapping (`openclaw.json` `hooks.mappings` entry):

```json
{
  "id": "ghl-sales",
  "match": { "path": "ghl-sales" },
  "action": "agent",
  "agentId": "sales",
  "model": "ollama/deepseek-v4-flash:cloud",
  "wakeMode": "now",
  "name": "GHL Sales Inbound",
  "sessionKey": "{{session_key}}",
  "messageTemplate": "Contact {{contact_id}}: {{message_body}} -- You are the Sales agent (check conversation-workflows for the matching playbook). CONVERSATION MEMORY — THIS HOOK SESSION IS SINGLE-TURN AND STATELESS, your only memory of this contact is the log file. FIRST, before drafting anything, READ this contact's conversation log at <MASTER_FILES_DIR>/conversational-logs/{{contact_id}}__<name>.md for the full prior conversation and any in-progress booking/context (see AGENTS.md Conversation Memory Protocol); if it is missing, treat as a new contact, and CONTINUE any in-progress topic/booking from the log instead of restarting. To pull deeper prior thread history use GET conversations/search?locationId={{location_id}}&contactId={{contact_id}} to find the conversationId, then GET conversations/{conversationId}/messages — conversationId is a READ key only, never a send field. MANDATORY — SEND on the SAME channel the message arrived on, do not just draft: read the inbound channel ({{channel}}) and SEND your reply via the GHL Conversations API (POST conversations/messages) with type = the MIRRORED channel value (SMS->SMS, Email->Email, Facebook->FB, Instagram->IG, WhatsApp->WhatsApp, Live Chat->Live_Chat); do NOT hardcode SMS. Send body = {type:<mirrored>, contactId:{{contact_id}}, locationId:{{location_id}}, message:<your reply>} (for Email also subject+html+emailFrom+emailTo). GHL threads the reply into this contact's conversation BY contactId — do NOT put conversationId in the send body. Per TOOLS.md. Composing or drafting a reply is NOT sending — the customer receives nothing unless you make the API call. Do NOT end your turn until the send call returns a messageId/conversationId. AFTER the send returns a messageId, APPEND both this inbound message and your reply to <MASTER_FILES_DIR>/conversational-logs/{{contact_id}}__<name>.md (create the file if missing) — a reply that does not update the log loses this contact's memory and is a failure.",
  "deliver": false,
  "timeoutSeconds": 300
}
```

The `messageTemplate` references the FLAT body key names (`{{contact_id}}`, `{{message_body}}`), and
`sessionKey:"{{session_key}}"` pulls the flat `session_key` the body sends.

**4b) The server `messageTemplate` MUST also include the CONVERSATION-MEMORY read-before / append-after
steps.** GHL inbound hook sessions are **single-turn / stateless** (confirmed: every hook run is a fresh
session, user-turns = 1). The agent has NO in-session memory of prior messages — its ONLY memory of a
contact across messages is that contact's conversation log file
(`<MASTER_FILES_DIR>/conversational-logs/<contact_id>__<name>.md`). The server `messageTemplate` MUST order
the agent to **READ** that log BEFORE drafting (and **CONTINUE** any in-progress booking/topic) and to
**APPEND** the inbound + reply AFTER sending. On a live client this broke because the template was
"simplified" during testing and lost the read/append steps — the agent had zero memory mid-booking. The
template MUST contain all of: the **conversational-logs** path, a **READ**-before-replying instruction, and
an **APPEND**-after-sending instruction (the canonical mapping above shows them). This is machine-enforced by
`scripts/qc-conversation-memory.sh` (CI + pre-handoff QC), the same way `scripts/qc-send-directive.sh`
enforces the send-directive. The read/append directive lives ONLY on this SERVER mapping — the in-GHL-body
`messageTemplate` stays placeholder-free per the 23-key rule.

**5) `deliver` MUST be `false`.** `deliver:true` makes OpenClaw ALSO try to push the reply to a channel,
conflicting with the agent's own GHL-API reply.

**6) There is NO GHL merge tag for channel / message-type.** Hardcode `"channel":"sms"` in the body (one
workflow per channel; for multi-channel branch on the Customer-Replied trigger's Reply-Channel filter and
hardcode per branch).

**7) Body VALUES use GHL's real merge tokens** (`{{contact.id}}`, `{{contact.first_name}}`,
`{{contact.last_name}}`, `{{contact.email}}`, `{{contact.phone}}`, `{{message.body}}`, `{{message.subject}}`,
`{{location.id}}`, `{{location.name}}`) and MUST be inserted via GHL's **Custom Values picker** (typed-as-text
tokens send empty). The body KEY NAMES (`contact_id`, `message_body`, etc.) are what OpenClaw reads/maps.

**8) A body-supplied or templated `sessionKey` requires `hooks.allowRequestSessionKey=true` AND
`hooks.allowedSessionKeyPrefixes`** (e.g. `["hook:"]`). Without any `sessionKey`, all contacts collapse into
one shared `hook:ghl:default` session (their conversations merge).

**9) `agentId` is NOT templatable in a mapping** (a `{{…}}` agentId silently falls back to the default agent).
To push the target agent from the webhook, POST to `/hooks/agent` (it reads top-level body fields `agentId`,
`sessionKey`, `message`, `name`, `channel`, `to`, `model`, `thinking` directly). Otherwise use one hook PATH
per agent with `agentId` hardcoded.

**10) `fallbacks` is NOT a valid `hooks.mappings` key** (the schema is `.strict()` and rejects it). It belongs
only on a model-routing config.

**11) `GHL_LOCATION_ID` (env) is the REQUIRED GHL API credential the agent uses to send the reply.** It is NOT
the `location_id` / `location_name` body merge fields. Keep the env credential; the `location_*` body fields
are optional data only.

**12) Valid `hooks.mappings` keys (`.strict()` schema, 2026.5.27):** `id`, `match`, `action`, `agentId`,
`model`, `wakeMode`, `name`, `sessionKey`, `messageTemplate`, `textTemplate`, `deliver`,
`allowUnsafeExternalContent`, `channel`, `to`, `thinking`, `timeoutSeconds`, `transform`.

---

## 1. The FOUR tokens — keep them disambiguated

This is the #1 source of confusion. There are exactly four secrets. Conflating any two breaks the install.

| # | Secret | Example format | Direction | Create-once vs reuse |
|---|--------|----------------|-----------|----------------------|
| 1 | `CLOUDFLARE_API_TOKEN` (= "Cloudflare API key" — the SAME secret, two names) | `cfut_…` | Agent → Cloudflare API (build tunnel + DNS) | Client creates it; agent uses it **ONCE** during setup. |
| 2 | Tunnel **connector token** | `eyJ…` (long JWT-looking) | `cloudflared` ↔ Cloudflare edge | Created once when the tunnel is created; `cloudflared` runs with it forever. |
| 3 | `HOOKS_TOKEN` | 64-hex, e.g. `527cef27…` | GHL → OpenClaw (INBOUND `Authorization: Bearer`) | Created once; **shared by ALL hooks**; does not change. This is the token you paste into the Build-with-AI prompt header. |
| 4 | `GHL_PRIVATE_INTEGRATION_TOKEN` (PIT) | `pit-9f…` | Agent → GHL API (OUTBOUND, send replies / book) | Created once in GHL; the agent uses it as Bearer for every Conversations/Calendar call. |

**Mnemonic:**
- #1 builds the pipe (once).
- #2 runs the pipe (forever, via cloudflared/launchd).
- #3 lets GHL knock on the door (inbound auth, OpenClaw verifies).
- #4 lets the agent talk back to GHL (outbound, send the reply / book the appointment).

**Where they live on a Mac:** `~/clawd/secrets/.env` and/or `~/.openclaw/.env`. The `hooks.token`
also lives in `~/.openclaw/openclaw.json` and — because there is no Hostinger wrapper — it is **stable**
(not rewritten on boot). Do **not** use `OPENCLAW_HOOKS_TOKEN` env trickery on Mac.

---

## 2. One-tunnel-many-hooks model

The tunnel + hostname + connector token + `HOOKS_TOKEN` are created **ONCE**. Every new automation
adds a **new hook path** under the same hostname — you do **NOT** create a new tunnel.

```
https://<PUBLIC_HOSTNAME>/hooks/ghl-inbound-sms      → SMS automation
https://<PUBLIC_HOSTNAME>/hooks/ghl-inbound-email    → Email automation
https://<PUBLIC_HOSTNAME>/hooks/stripe-events        → Stripe automation
                       ▲                  ▲
              same tunnel + hostname   distinct hook path per automation
```

Each new hook path = one new entry in `hooks.mappings` (distinct `id` + `match.path`), reusing the
same `HOOKS_TOKEN`. **Never recreate the tunnel to add an automation.**

---

## 3. JSON structure rule (BINDING)

**One value per key — proper JSON structure. Never cram multiple distinct values into a single string
field. Each field gets its own key (nested or flat).**

```jsonc
// WRONG — packed string, breaks downstream parsers, unreadable to the next agent:
{ "tunnel": "id=abc123; token=eyJ...; host=client.example.com" }

// RIGHT — one value per key:
{
  "tunnel_id": "abc123",
  "connector_token": "eyJ...",
  "public_hostname": "client.example.com"
}
```

This applies to every config edit, every hook payload, every secrets-env record, and the Reusable
Tunnel Values record (Section 5). It is Rule 7 of the playbook's Rules of Engagement.

---

## 4. Build-with-AI prompt TEMPLATE (the operator pastes this into GHL)

**GHL / Convert and Flow has NO API and NO MCP for building automations.** The only way to build one
programmatically-ish is the **"Build with AI"** feature: Automations → **Build with AI** → paste a prompt
→ Publish. The agent's job is to generate a precise, copy-paste-ready prompt with every value substituted.

> Placeholders: `{{PUBLIC_HOSTNAME}}`, `{{HOOK_PATH}}`, `{{HOOKS_TOKEN}}`, `{{CHANNEL}}`.
> `{{CHANNEL}}` must be one of the VALID send types in Section 7 (`SMS`, `Email`, `FB`, `IG`,
> `WhatsApp`, `Live_Chat`).

```
Build a workflow for me with these exact specifications:

TRIGGER:
- Type: "Customer Replied"
- Filter: Reply Channel = "{{CHANNEL}}"

ACTIONS (in this exact order):
- Action 1: "Send Custom Webhook" (NOT GHL's native webhook action)
  - URL: https://{{PUBLIC_HOSTNAME}}/hooks/{{HOOK_PATH}}
  - Method: POST
  - AUTHORIZATION dropdown: None   (the token goes in Headers, not this dropdown)
  - Headers:
    - Authorization: Bearer {{HOOKS_TOKEN}}
    - Content-Type: application/json
  - Body (Raw JSON, exact — FLAT, no nested objects, ALL 23 keys, placeholder-free messageTemplate):
    {
      "id": "ghl-sales",
      "match": "ghl-sales",
      "action": "agent",
      "agent_id": "sales",
      "model": "ollama/deepseek-v4-flash:cloud",
      "wakeMode": "now",
      "name": "GHL Sales Inbound",
      "session_key": "hook:ghl:{{CHANNEL}}:{{contact.id}}",
      "messageTemplate": "Respond as the Sales agent and reply to this contact via the GHL Conversations API per TOOLS.md",
      "deliver": false,
      "timeoutSeconds": 300,
      "channel": "{{CHANNEL}}",
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

PUBLISH: Yes, publish the workflow when done — do not leave it as a draft.
```

> **CRITICAL (owner directive + verified live on a live client 2026-05-29, OpenClaw 2026.5.27):** the
> GHL RAW BODY MUST have ALL 23 keys (23 is the minimum — no stripped bodies) and be FLAT — no nested
> `contact:{…}` / `customer_message:{…}` objects. A nested body makes EVERY field resolve EMPTY at the hook
> (even a hardcoded `"channel":"sms"` arrived blank when nested). The body's `messageTemplate` VALUE MUST stay
> placeholder-free (no `{{…}}`) — otherwise GHL tries to expand the template's `{{…}}` as its own merge fields,
> fails, mangles them to `##{}##`, drops the closing quote, and the webhook is Skipped with GHL error "Error
> while parsing the object to JSON". See **CORRECTED GHL HOOK STRUCTURE (2026-05-29)** at the top of this doc
> for the full 23-key spec.

The agent saves the filled-in prompt as
`<MASTER_FILES_DIR>/conversation-workflows/<workflow-id>--build-with-ai-prompt.md` and tells the operator
to paste it into Automations → Build with AI.

---

## 5. Post-build VERIFICATION CHECKLIST (REQUIRED — even when Build with AI "succeeds")

Build with AI frequently gets the scaffold right but silently mangles one critical piece. **Always run
this against the built workflow**, item by item. Each item names the failure mode AND the fix.

- [ ] **URL is EXACTLY** `https://{{PUBLIC_HOSTNAME}}/hooks/{{HOOK_PATH}}` — no trailing slash, correct path.
      FIX: click the webhook action → URL field → paste exact URL.
- [ ] **Method is POST** (not GET/PUT). FIX: Method dropdown → POST.
- [ ] **AUTHORIZATION dropdown is "None"** — the token goes in Headers, NOT this dropdown.
      FIX: set dropdown to None, then add the header below.
- [ ] **`Authorization: Bearer {{HOOKS_TOKEN}}` header present, with the CORRECT token** (HOOKS_TOKEN — secret #3,
      not the PIT, not the gateway token). FIX: re-add the header, paste HOOKS_TOKEN exactly, no extra spaces.
- [ ] **`Content-Type: application/json` header present** (and the Content-Type dropdown set to application/json).
- [ ] **Raw Body has ALL 23 keys, is FLAT (no nested objects), and matches the template field-for-field** — the
      23 flat keys `id`, `match`, `action`, `agent_id`, `model`, `wakeMode`, `name`, `session_key`,
      `messageTemplate`, `deliver`, `timeoutSeconds`, `channel`, `to`, `thinking`, `contact_id`, `first_name`,
      `last_name`, `email`, `phone`, `subject`, `message_body`, `location_id`, `location_name`. 23 is the MINIMUM —
      a body with fewer keys is WRONG. The body's `messageTemplate` value MUST stay placeholder-free (no `{{…}}`)
      so GHL never mangles it. Watch for Build with AI re-nesting fields into `contact:{…}` / `customer_message:{…}`
      (a nested body makes every field arrive EMPTY) or dropping keys. FIX: paste the exact 23-key FLAT Raw JSON
      from Section 4.
- [ ] **Body values were inserted via GHL's Custom Values picker** (not typed as plain text). Typed-as-text
      `{{contact.id}}`-style tokens send EMPTY. FIX: delete the typed token, re-insert via the merge-field picker.
- [ ] **Trigger is "Customer Replied"** filtered to the right Reply Channel.
- [ ] **Workflow is PUBLISHED, not Draft.** FIX: top-right → Publish.
- [ ] **REAL inbound test performed.** Send an actual message on the channel and confirm OpenClaw received it
      and the agent replied. **Do NOT rely on GHL's in-builder "Test" button** — it sends empty merge fields and
      passes even when the live payload is broken.

---

## 6. Reusable Tunnel Values — storage rule (BINDING, every time, kept updated)

Store the reusable assets — **one value per key (Section 3)** — under a **"Reusable Tunnel Values"** section
in **ALL THREE** of these, and keep them in sync whenever a value changes or a new hook is added:

1. **AGENTS.md** (`## Reusable Tunnel Values`)
2. **TOOLS.md** (`## Reusable Tunnel Values`)
3. **The client's own Notion doc** (never co-mingle with another client's workspace)

Record:

```json
{
  "public_hostname": "<PUBLIC_HOSTNAME>",
  "hooks_token": "<HOOKS_TOKEN>",
  "tunnel_id": "<TUNNEL_ID>",
  "connector_token_ref": "secrets/.env:TUNNEL_TOKEN",
  "hook_path_registry": [
    {
      "hook_path": "ghl-inbound-sms",
      "automation_name": "OpenClaw — Inbound SMS",
      "channel": "SMS",
      "playbook_path": "conversation-workflows/appointment-booking.md"
    }
  ]
}
```

> For the connector token, store a **reference** to the secrets-env key (not the raw `eyJ…` value) in
> Notion/AGENTS.md/TOOLS.md. The raw value lives only in `~/clawd/secrets/.env` / `~/.openclaw/.env`.

---

## 7. Verified channel → `type` enum (GHL Conversations API send)

**Endpoint:** `POST https://services.leadconnectorhq.com/conversations/messages`
**Headers:** `Authorization: Bearer <GHL_PRIVATE_INTEGRATION_TOKEN>`, `Version: 2021-04-15`, `Content-Type: application/json`

| Channel | `type` value (VALID) | Required body fields |
|---|---|---|
| SMS | `SMS` | `contactId`, `locationId`, `message` |
| Email | `Email` | `contactId`, `locationId`, `subject`, `html`, `emailFrom`, `emailTo` |
| Facebook Messenger | `FB` | `contactId`, `locationId`, `message` |
| Instagram DM | `IG` | `contactId`, `locationId`, `message` |
| WhatsApp | `WhatsApp` | `contactId`, `locationId`, `message` |
| Live Chat | `Live_Chat` | `contactId`, `locationId`, `message` |

**VALID send types (the complete `SendMessageBodyDto` enum):** `SMS`, `Email`, `FB`, `IG`, `WhatsApp`,
`Live_Chat` (also valid but rare: `RCS`, `Custom`, `TIKTOK`).

**INVALID — the API rejects these as a send `type`:** `GMB`, `Call`, and the long-forms
`Instagram`, `Facebook`, `Webchat`. **GMB is inbound-only** — it has no Conversations send type, so you
**cannot reply to GMB via this endpoint**. **TikTok inbound** is a workflow-action-only channel; the send
type when sending is `TIKTOK`. Always use the short codes (`FB`, `IG`).

**Mirror the inbound channel.** Reply on the SAME channel the message arrived on (the inbound hook's
`{{channel}}`): SMS→`SMS`, Email→`Email`, Facebook→`FB`, Instagram→`IG`, WhatsApp→`WhatsApp`, Live
Chat→`Live_Chat`. Do NOT hardcode `SMS`.

---

## 8. GHL Conversations reply recipe (OUTBOUND)

The send body is threaded into the contact's conversation **BY `contactId`** — it does **NOT** accept
`conversationId`. GHL returns `conversationId`+`messageId`.

```bash
curl -s -X POST "https://services.leadconnectorhq.com/conversations/messages" \
  -H "Authorization: Bearer $GHL_PRIVATE_INTEGRATION_TOKEN" \
  -H "Version: 2021-04-15" \
  -H "Content-Type: application/json" \
  --data '{
    "type": "SMS",
    "contactId": "<contactId>",
    "locationId": "<locationId>",
    "message": "<reply text>"
  }'
```

Swap `type` (mirror the inbound channel) + required fields per the enum in Section 7. For Email, include
`subject`, `html`, `emailFrom`, `emailTo` instead of `message`.

**READ the thread (scope `conversations.readonly`).** `conversationId` is the READ key only — find the
thread by contact, then read its history:
```
GET /conversations/search?locationId=<locationId>&contactId=<contactId>   # → conversationId
GET /conversations/<conversationId>/messages                              # → message history
```
The inbound webhook payload already carries `conversationId`, `contactId`, and `messageType`; use
search/messages only for deeper history than the local conversation log holds.

---

## 9. GHL Calendar recipe (VERIFIED)

All Calendar calls use the same headers as Section 8 (PIT Bearer, `Version: 2021-04-15`).

**Availability (free-slots):** epoch **MILLISECONDS** for `startDate`/`endDate`.
```
GET /calendars/{calendarId}/free-slots?startDate={epochMillis}&endDate={epochMillis}
```

**Book appointment:** REQUIRED `calendarId`, `locationId`, `contactId`, `startTime`. `endTime` is OPTIONAL
(the calendar's slot duration fills it). The response returns the appointment `id`.
```bash
curl -s -X POST "https://services.leadconnectorhq.com/calendars/events/appointments" \
  -H "Authorization: Bearer $GHL_PRIVATE_INTEGRATION_TOKEN" \
  -H "Version: 2021-04-15" -H "Content-Type: application/json" \
  --data '{
    "calendarId": "<calendarId>",
    "locationId": "<locationId>",
    "contactId": "<contactId>",
    "startTime": "<ISO8601 start>"
  }'
```

**Reschedule:** `PUT /calendars/events/appointments/{eventId}`
**Cancel:** `DELETE /calendars/events/{eventId}`

> Epoch-millis gotcha: GHL free-slots expects milliseconds. `date +%s` gives seconds — multiply by 1000.
> `startDate=$(( $(date +%s) * 1000 ))`.

---

## 10. First conversation playbook = APPOINTMENT BOOKING (Layer 2 template)

The base SMS automation MUST also create this first conversation playbook and wire the SMS hook path to it,
so every fresh install ships one working end-to-end conversation (inbound SMS → agent → booked appointment).

Save as `<MASTER_FILES_DIR>/conversation-workflows/appointment-booking.md`:

```markdown
# Conversation Playbook: Appointment Booking

## When to invoke
Customer asks to book / schedule / set up a meeting, demo, consultation, or appointment.

## Behavior (Layer 2)
1. Identify the service + preferred time window. If unspecified, ask which service; if one calendar exists, default to it.
2. Check availability:
   GET /calendars/{BOOKING_CALENDAR_ID}/free-slots?startDate={nowMillis}&endDate={nowPlus7dMillis}
   (epoch MILLISECONDS). Prioritize slots in the first 72 hours.
3. Offer the customer 2–3 specific times in the reply (date + time + timezone).
4. When the customer picks one, book it:
   POST /calendars/events/appointments
   { "calendarId": "{BOOKING_CALENDAR_ID}", "locationId": "{LOCATION_ID}",
     "contactId": "{contactId}", "startTime": "<chosen ISO time>" }
   Capture the returned appointment `id`.
5. Confirm back to the customer: time, date, timezone, any prep info.
6. On a later reschedule request → PUT /calendars/events/appointments/{eventId}.
   On a cancel request → DELETE /calendars/events/{eventId}.

## Guardrails
- Never offer a slot outside the operator's booking window (default 7 days) or inside min lead time (default 2h).
- After 3 declined offers, escalate to the operator.
- Reply on the same channel the customer used (per the inbound hook's {{channel}}).
```

Register it in `conversation-workflows/registry.md` and add its hook-path entry to the Reusable Tunnel
Values hook-path registry (Section 6).

**MANDATORY (gated) — create the human-facing doc for this first playbook in the CLIENT's account.** The
base install is NOT complete until the appointment-booking playbook ALSO has a human-readable copy in the
client's OWN account, created in the fallback order **Notion → Google Docs → plain-text**, with its URL/path
recorded in the registry's `Doc (Notion/Docs/text)` column (and the run manifest). This is the exact step an
agent skipped on a live client — files scaffolded locally, install reported "clean," but no client doc. It is
NOT optional prose: it is machine-enforced by `scripts/qc-playbook-doc.sh` (wired into
`scripts/11-run-qc-checklist.sh` + CI `.github/workflows/qc-static.yml`), and the installer
`scripts/09-install-conversation-workflows.sh` creates + records it automatically (Notion via
`NOTION_API_KEY` + the client's designated parent page → Google Docs → a `.md` in
`<MASTER_FILES_DIR>/playbook-docs/`). See `references/communications-playbook-standard.md` §4.

---

## 11. Mac cloudflared (launchd) — interactive-sudo blocker

```bash
brew list cloudflared || brew install cloudflared
sudo cloudflared service install <CONNECTOR_TOKEN>   # secret #2 (eyJ…)
```

> **🛑 BLOCKER:** `sudo cloudflared service install` prompts for the admin password and **cannot run over a
> non-interactive rescue SSH session** (no TTY). If operating remotely, STOP and hand this one command to the
> operator to run in a local Terminal (or an interactive TTY SSH session), then resume once they confirm the
> LaunchDaemon is installed. This was a real onboarding blocker — don't let the install silently stall here.

On macOS this writes `/Library/LaunchDaemons/com.cloudflare.cloudflared.plist` (`RunAtLoad=true`,
`KeepAlive=true`). Verify: `sudo launchctl list | grep com.cloudflare.cloudflared` (PID must be a number),
and run the restart-survival test (`kill -9` the PID, confirm a new PID appears).

---

## 12. `deliver: false` on GHL reply hooks (CRITICAL)

The inbound hook's mapping MUST set `"deliver": false`. With `deliver: true`, the gateway tries to publish
the agent's response to the agent's **default** channel binding — which for a GHL-only agent has no `chatId`
— and fails with `"Delivering to Telegram requires target <chatId>"`. The agent's real reply (sent OUTBOUND
via the GHL Conversations API, Section 8) then never reaches the customer. The agent already delivers its own
reply, so the hook must not deliver it again. **Always `deliver: false` for API-reply hooks.**

---

## 13. Cron registration on openclaw 2026.5.27 — use the CLI, not `cron.jobs` JSON

The `cron.jobs` JSON block does **NOT** validate on openclaw 2026.5.27. Register every cron via the CLI:

```bash
openclaw cron add \
  --name <job-name> \
  --cron "<cron-expr>" \
  --agent main \
  --message "<instruction>" \
  --light-context \
  --best-effort-deliver
```

Example (weekly calendar sync, Section 14):
```bash
openclaw cron add --name skill38-calendar-sync --cron "0 9 * * 0" --agent main \
  --light-context --best-effort-deliver \
  --message "run ~/clawd/scripts/skill38-calendar-sync.sh ~/.openclaw/workspace/TOOLS.md and report calendar count"
```

---

## 14. Calendar sync script

`scripts/skill38-calendar-sync.sh` pulls the client's current GHL calendars weekly and rewrites the marked
`<!-- GHL_CALENDARS_START -->` … `<!-- GHL_CALENDARS_END -->` table in TOOLS.md (adds new calendars, removes
ones that no longer exist). It auto-detects Mac vs VPS env/paths. Install it to `~/clawd/scripts/` and register
the Sunday 9am cron per Section 13.

---

## 15. BACKEND SELF-TEST STANDARD — the agent tests ITSELF before the client (MANDATORY, gated)

After the agent configures the hook, and **BEFORE the client is ever told to test**, the agent MUST
self-test the full inbound -> reply chain **by ground truth** — not by self-report. Setup is **NOT** marked
complete and the client is **NOT** told to test until the self-test passes. This is executed by
`scripts/24-self-test-hook.sh`, statically enforced by `scripts/qc-self-test.sh`, and wired as a BLOCKING
readiness gate in `scripts/11-run-qc-checklist.sh` (which asserts `selfTestPassed=true`).

**(a) Readiness** — the backend must be prepared to RECEIVE: `hooks.enabled` true; a live `hooks.mappings`
entry for `HOOK_NAME` with `action:agent`, `deliver:false`, and a working `model`; GHL creds in
`secrets/.env` (`GHL_PRIVATE_INTEGRATION_TOKEN` + `GHL_LOCATION_ID` — the location IS set); the
`conversational-logs/` dir present + writable (node-owned); `/healthz` 200.

**(b) Synthetic inbound** — POST a SYNTHETIC GHL inbound to the agent's OWN public hook URL
(`https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>`) with the **FLAT 23-key body** (§0/§1), `channel:"sms"`, a
DEDICATED throwaway test contact id, and the REAL `Authorization: Bearer <HOOKS_TOKEN>`. The self-test builds
the body field-by-field at runtime (it is NOT a fenced ```json block) so it carries the live values and is
not double-scanned by `qc-23-key-bodies.sh`. The exact synthetic payload (23 flat keys; `deliver:false`;
`messageTemplate` placeholder-free; a reserved `+1555` test phone; `selftest@example.com`) is emitted by
`scripts/24-self-test-hook.sh`.

**(c) Verify by ground truth (pass criteria):**
1. the hook returns **HTTP 200** and `{"ok":true}`;
2. the agent session ran on the **configured model with NO 401/429** (read the gateway/session transcript
   for the run, not a self-report);
3. the agent **READ the conversation log** for the test contact;
4. the agent **called the GHL Conversations API** (`POST conversations/messages`) and got **200/201** with a
   `messageId`. If a real contact is required, the self-test **CREATES a temporary test contact via the GHL
   API**, confirms the send returns a `messageId`, then **DELETES the temp contact + the test conversation
   log** (cleanup).

**(d) Fix-and-retest** — on ANY failure the script prints the exact remediation (creds; location id; model;
DND on the contact; `secrets/.env` placement) and exits non-zero. The agent FIXES it and RE-RUNS until green.

**(e) Gate** — `selfTestPassed=true|false` is written to the run-state file. The install is **NOT** complete
and the client is **NOT** told to test (Section 7 of their doc) until `selfTestPassed=true`.
