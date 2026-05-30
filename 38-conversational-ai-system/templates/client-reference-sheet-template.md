<!--
  Client Reference Sheet template — verbatim playbook v5.14, Parts 2 + 3 (lines 8224-8527).
  Rendering paths:
    1. Notion-first  → scripts/21-generate-client-reference-sheet.sh (agent #5) writes this to a fresh page in the client's Notion workspace, substituting <PLACEHOLDER> tokens with captured run values.
    2. Markdown fallback → if Notion is unavailable, the same script saves the rendered file to $MASTER_FILES_DIR/openclaw-ghl-webhook-setup-<timestamp>.md.
  The six channel-specific Raw Body JSONs (SMS, Email, Facebook, Instagram, Live Chat, All-in-One) live below in Part 3 — copy the one matching each GHL workflow's "Custom Webhook" body.
-->

# Part 2 — The Client Reference Sheet (what gets written to Notion or the markdown file)

This is the content the agent generates and saves. Every code block in the reference sheet must be a real, copy-paste-ready code block so the operator can hit the "copy" button and paste straight into GHL.

## Reference Sheet structure

```
# OpenClaw Inbound Webhook Setup — Client Reference Sheet

**Setup completed:** <date and time>
**Hostname:** <PUBLIC_HOSTNAME>
**OpenClaw version at setup time:** <OPENCLAW_VERSION>
**Hook name (mapping id):** <HOOK_NAME>
**Endpoint URL:** https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>

---

## 🔐 Save these secrets to your password manager NOW

- CLOUDFLARE_API_TOKEN: <value>
- TUNNEL_TOKEN: <value>
- HOOKS_TOKEN: <value>
- TUNNEL_ID: <value>
- CLOUDFLARE_ACCOUNT_ID: <value>

These have also been saved to <SECRETS_ENV_FILE>.

---

## 🚀 GHL CUSTOM WEBHOOK SETUP (copy-paste sections)

For EACH channel you want OpenClaw to handle, build a separate workflow in GHL. Copy the matching JSON block from Part 3 below. Use these same values across all workflows:

### URL field (same for every channel)

[code block, copy button]
https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>
[/code block]

### Headers (same for every channel)

Leave the "AUTHORIZATION" dropdown set to "None". A GHL custom-webhook header has a **Key** box and a **Value** box — so each header is TWO separate copy blocks below. Paste block 1 into the **Key** (header-name) box and block 2 into the **Value** box. Watch for extra spaces — no leading/trailing whitespace, double-check spelling.

**Header 1 — Authorization**

Paste into the **Key** (header-name) box:

[code block, copy button]
Authorization
[/code block]

Paste into the **Value** box:

[code block, copy button]
Bearer <HOOKS_TOKEN>
[/code block]

**Header 2 — Content-Type**

Paste into the **Key** (header-name) box:

[code block, copy button]
Content-Type
[/code block]

Paste into the **Value** box:

[code block, copy button]
application/json
[/code block]

### Content-Type dropdown (below Headers)

Set to: application/json

---

## 📦 GHL WORKFLOW BUILD — DO THIS FOR EACH CHANNEL

(Verbatim click-by-click — see Part 3 for the matching Raw Body per channel)

1. GHL sub-account → **Automation → Workflows → + Create Workflow → Start from Scratch**
2. Name it `OpenClaw — Inbound [Channel]` (e.g. `OpenClaw — Inbound SMS`)
3. **+ Add New Trigger** → choose **Customer Replied**
4. In the trigger filter: **+ Add Filter** → choose **Reply Channel** → select the matching channel (SMS, Email, Facebook, Instagram, Live Chat, or All-in-One Chat)
5. Hit **Save Trigger**
6. Below the trigger, click the **+** button in the middle of the canvas
7. In the popup, type **webhook** in the search box
8. Choose **Custom Webhook** (NOT GHL's native webhook action — they are different)
9. Method: **POST**
10. URL: paste the URL block from above
11. AUTHORIZATION dropdown: leave as **None**
12. Under HEADERS, click **Add another item** TWICE to create two rows. Each row has a **Key** box and a **Value** box — paste them from the two-block Headers section above:
    - Row 1 — **Key** box: paste the `Authorization` key block | **Value** box: paste the `Bearer <HOOKS_TOKEN>` value block (the value is JUST `Bearer ` + the token — it does NOT repeat the word `Authorization`)
    - Row 2 — **Key** box: paste the `Content-Type` key block | **Value** box: paste the `application/json` value block
13. CONTENT-TYPE dropdown: set to `application/json`
14. Scroll to **RAW BODY** field
15. Paste the matching JSON from Part 3 (SMS body for SMS workflow, Email body for Email workflow, etc.)
16. Click **Save Action**
17. Top middle of the workflow → click **Settings** tab → turn **Allow Reentry** ON
18. Top right → toggle from **Draft** to **Publish**
19. Top → hit the **Save** button above the toggle
20. Test: send yourself a message in the matching channel from GHL, reply from your phone/inbox, and watch for the agent's reply

⚠️ Reminders:
- One workflow per channel — don't try to combine them
- Watch for extra spaces when pasting — leading or trailing whitespace breaks auth
- The `channel` value in each JSON is hardcoded to match the workflow's channel filter — don't change it

---

(See Part 3 for the six Raw Body blocks)

---

## 🛠️ Setup Verification

- ✅ Cloudflare tunnel: <TUNNEL_ID>
- ✅ DNS CNAME created at <PUBLIC_HOSTNAME>
- ✅ cloudflared service: auto-start flags verified, Restart Survival Test passed
- ✅ OpenClaw config: backup at <CONFIG_BACKUP_PATH>, hooks.mappings active for <HOOK_NAME>
- ✅ End-to-end test: 200 OK at https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>
- ✅ OpenClaw version at time of setup: <OPENCLAW_VERSION> (schema verified against docs.openclaw.ai on <date>)
- ✅ Agent classification rules installed in AGENTS.md (spam/marketing filtering active)
- ✅ Communication playbooks created (links below)

## 📘 Your communication playbooks

The agent reads these on every reply turn. Open each one and fill in the sections for your business — tone, signature, example replies, escalation rules. The agent picks up changes automatically; no restart needed.

- SMS Communication Playbook: <URL or path>
- Email Communication Playbook: <URL or path>
- Facebook Communication Playbook: <URL or path>
- Instagram Communication Playbook: <URL or path>

The agent will use professional defaults until you fill these in. Filling them in is what makes replies sound like YOUR business.

## 🧪 How to test your system

When everything is built and published, test it end-to-end yourself. Do these in order:

1. **Go to Contacts** (left menu).
2. **Search your own name** in the search box at the top.
3. **Open your own contact record** (click your name).
4. **Send yourself a text (SMS)** from inside that contact record.
5. **On your phone, REPLY to that text** — write a normal message like "hi, can you help me?" (don't just open it; actually reply).
6. **Go to Automations** (left menu) and **open the workflow you built**.
7. **Click the Execution Logs tab.**
8. **Every step should show green / success — ESPECIALLY the Custom Webhook step.** Within a few seconds your phone should also get the AI's reply back.

**If anything is red = that step FAILED.** A red Custom Webhook step is the most common one — it means the URL, the Authorization header, or the Raw Body is wrong. Re-run the verification checklist (re-paste the URL, the two header blocks, and the 23-key Raw Body), or contact support.


## 🔄 Recall prompt — save this somewhere durable

Paste this into any AI session with access to this machine to retrieve your URL + Bearer token later:

[code block]
Look up my OpenClaw hooks.mappings setup in ~/.openclaw/openclaw.json.
Tell me the URL pattern (https://<hostname>/hooks/<id>), the Bearer token
(hooks.token), and the agent session key pattern (mappings[].sessionKey).
Resolve the hostname from my Cloudflare tunnel if not in memory. Output
ready-to-paste headers and URL for an external service.
[/code block]

## 🔌 Adding other services later

To wire Stripe, n8n, Calendly, Zapier, or any other service into the same OpenClaw, add another entry to the `hooks.mappings` array in `~/.openclaw/openclaw.json` with its own `id`, `match.path`, and a `messageTemplate` shaped for that service's payload. Reuses the same `HOOKS_TOKEN`. URL becomes `https://<PUBLIC_HOSTNAME>/hooks/<new-id>`.
```

---

# Part 3 — Six channel-specific Raw Body JSONs

These are the Raw Body blocks the operator pastes into GHL's Custom Webhook action. ONE block per channel, ONE workflow per channel. The `channel` field is hardcoded because GHL's `{{message.channel}}` merge field doesn't reliably populate — and since each workflow's trigger filter already constrains the channel, hardcoding is correct.

All six blocks have the same structure. Only the `channel` value changes. The operator copies the block matching the channel they're setting up.

> **ALL 23 KEYS REQUIRED (owner directive).** Each block below has all 23 keys. 23 is the MINIMUM — never
> paste a shorter body. Only `channel` + the `session_key` prefix differ between channels. The body's
> `messageTemplate` is placeholder-free so GHL never mangles it.

### SMS workflow — Raw Body

```json
{
  "id": "<HOOK_NAME>",
  "match": "<HOOK_NAME>",
  "action": "agent",
  "agent_id": "<ROUTING_AGENT_ID>",
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

### Email workflow — Raw Body

```json
{
  "id": "<HOOK_NAME>",
  "match": "<HOOK_NAME>",
  "action": "agent",
  "agent_id": "<ROUTING_AGENT_ID>",
  "model": "ollama/deepseek-v4-flash:cloud",
  "wakeMode": "now",
  "name": "GHL Sales Inbound",
  "session_key": "hook:ghl:email:{{contact.id}}",
  "messageTemplate": "Respond as the Sales agent and reply to this contact via the GHL Conversations API per TOOLS.md",
  "deliver": false,
  "timeoutSeconds": 300,
  "channel": "email",
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

### Facebook Messenger workflow — Raw Body

```json
{
  "id": "<HOOK_NAME>",
  "match": "<HOOK_NAME>",
  "action": "agent",
  "agent_id": "<ROUTING_AGENT_ID>",
  "model": "ollama/deepseek-v4-flash:cloud",
  "wakeMode": "now",
  "name": "GHL Sales Inbound",
  "session_key": "hook:ghl:fb:{{contact.id}}",
  "messageTemplate": "Respond as the Sales agent and reply to this contact via the GHL Conversations API per TOOLS.md",
  "deliver": false,
  "timeoutSeconds": 300,
  "channel": "fb",
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

### Instagram DM workflow — Raw Body

```json
{
  "id": "<HOOK_NAME>",
  "match": "<HOOK_NAME>",
  "action": "agent",
  "agent_id": "<ROUTING_AGENT_ID>",
  "model": "ollama/deepseek-v4-flash:cloud",
  "wakeMode": "now",
  "name": "GHL Sales Inbound",
  "session_key": "hook:ghl:instagram:{{contact.id}}",
  "messageTemplate": "Respond as the Sales agent and reply to this contact via the GHL Conversations API per TOOLS.md",
  "deliver": false,
  "timeoutSeconds": 300,
  "channel": "instagram",
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

### Live Chat workflow — Raw Body

```json
{
  "id": "<HOOK_NAME>",
  "match": "<HOOK_NAME>",
  "action": "agent",
  "agent_id": "<ROUTING_AGENT_ID>",
  "model": "ollama/deepseek-v4-flash:cloud",
  "wakeMode": "now",
  "name": "GHL Sales Inbound",
  "session_key": "hook:ghl:live_chat:{{contact.id}}",
  "messageTemplate": "Respond as the Sales agent and reply to this contact via the GHL Conversations API per TOOLS.md",
  "deliver": false,
  "timeoutSeconds": 300,
  "channel": "live_chat",
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

### All-in-One Chat workflow — Raw Body

```json
{
  "id": "<HOOK_NAME>",
  "match": "<HOOK_NAME>",
  "action": "agent",
  "agent_id": "<ROUTING_AGENT_ID>",
  "model": "ollama/deepseek-v4-flash:cloud",
  "wakeMode": "now",
  "name": "GHL Sales Inbound",
  "session_key": "hook:ghl:allinone:{{contact.id}}",
  "messageTemplate": "Respond as the Sales agent and reply to this contact via the GHL Conversations API per TOOLS.md",
  "deliver": false,
  "timeoutSeconds": 300,
  "channel": "allinone",
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

