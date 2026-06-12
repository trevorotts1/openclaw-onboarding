<!-- OPERATOR HEADER -->
<!-- Skill 38 template: SMS Build-with-AI prompt — copy-paste-ready. Pasted into GHL Automations → "Build with AI". -->
<!-- Built from playbook v5.14 Step 9.20-D.2 (lines 4015-4069). -->
<!-- Substitution placeholders are listed below. Rendered per-client by scripts/21-generate-client-reference-sheet.sh. -->
<!-- The single fenced code block below is what the client pastes into GHL Automations → "Build with AI". -->

# Your First Workflow — SMS Inquiry Responder

This is the first conversation workflow we're wiring up for **<CLIENT_BUSINESS_NAME>**. When a contact texts you, this workflow fires, sends the message to your conversational AI, and lets the AI respond on your behalf — including, when the conversation is ready, helping the contact <DESIRED_OUTCOME>.

You don't have to build this workflow by hand — and in most cases you don't have to do anything at all.

**Primary path (Tier 0 — Skill 44 / `caf`):** if your Convert and Flow (Firebase) token is connected, your agent builds this workflow for you directly via the internal API (`caf workflows build`). You do nothing; the agent tells you when it's built, then hands you the verification checklist. The prompt below is the exact spec the agent uses.

**Fallback path (no token):** only if the Firebase token isn't connected, you build it yourself with GHL's **"Build with AI"** button, which constructs the entire workflow from the prompt below. Copy it once, paste it once, done.

## How to use this (fallback — only when the Firebase token is NOT connected)

1. Open your Convert and Flow account.
2. Click **Automations** on the left menu.
3. Start a **new automation**, then click the **"Build with AI"** button (top-right).
4. Copy the entire block below (the one starting with `Build a workflow for me with these exact specifications:`) and paste it into **Build with AI**.
5. Let **Build with AI** build the workflow.
6. Open the **Workflow Verification Checklist** (Section 4 of this Notion page, or the matching `.md` file on your Mac) and verify each item before publishing.

## The copy-paste prompt

```text
Build a workflow for me with these exact specifications:

CONTEXT:
This workflow is for <CLIENT_BUSINESS_NAME>, which operates in <INDUSTRY_CONTEXT>. The end goal for every conversation that flows through this workflow is to <DESIRED_OUTCOME>. Build the workflow exactly to the spec below — do not improvise or add steps.

TRIGGER:
- Type: Customer Replied
- Sub-option: On Reply
- Channel: SMS

FILTERS (in this exact order):
- Filter 1: Channel equals "SMS"
- Filter 2: Message Direction equals "Inbound"

ACTIONS (in this exact order):
- Action 1: Send Custom Webhook  (set EVERY field below — Build-with-AI fumbles these)
  - EVENT: CUSTOM
  - METHOD: POST  (choose from the dropdown — not GET/PUT)
  - URL: https://<PUBLIC_HOSTNAME>/hooks/<ROUTE_ID>  (paste this EXACT url — do NOT leave the sample-url placeholder; no trailing slash; keep the /hooks/ segment)
  - AUTHORIZATION dropdown: None  (the token goes in Headers, NOT in the Authorization dropdown — leave the dropdown set to None)
  - HEADERS (click "Add item" once per header):
    - Key: Authorization   Value: Bearer <HOOKS_TOKEN>
    - Key: Content-Type    Value: application/json
  - CONTENT-TYPE: application/json
  - Body type: Raw JSON
  - RAW BODY (Raw JSON — FLAT, no nested objects, ALL 23 keys, placeholder-free messageTemplate; insert each {{…}} via GHL's Custom Values picker, not typed as plain text):
    {
      "id": "<ROUTE_ID>",
      "match": "<ROUTE_ID>",
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

SETTINGS:
- ALLOW RE-ENTRY: ON (the workflow MUST be allowed to re-enter / fire repeatedly per contact — a contact who texts today and again next week must re-trigger it. If Allow Re-entry is OFF the workflow fires once per contact and silently drops every later message.)

PUBLISH: Yes, publish the workflow when done — don't leave it as draft.

RUN SCHEDULE: All Day (so the AI can respond at any hour the customer texts in).

SAVE ORDER: Save the action, then flip the top-right Publish toggle to Published, then Save again.
```

## What Build with AI will build

After you paste the prompt above, **Build with AI** should produce a workflow with:

- **One trigger node**: "Customer Replied" with sub-option "On Reply" and channel filter "SMS".
- **Two filter nodes** (in order): Channel = SMS, Message Direction = Inbound.
- **One action node**: "Send Custom Webhook" pointing at `https://<PUBLIC_HOSTNAME>/hooks/<ROUTE_ID>` with the two headers above and the Raw JSON body above.
- **Settings -> Allow Re-entry**: ON.
- **Status**: Published (NOT draft).
- **Run schedule**: All Day.

If the workflow Build with AI produced doesn't match this shape, that's normal — Build with AI is a helper, not infallible. Use the verification checklist (Section 4) to fix the gaps.

## MANDATORY — manually fill the Custom Webhook AFTER Build with AI runs

**AFTER Build-with-AI runs, you MUST open the Custom Webhook action and MANUALLY enter the values below.**
Build-with-AI only builds the workflow SHAPE (the trigger + an EMPTY Custom Webhook action) — it does
**NOT** fill in the URL, the Authorization/Bearer header, the Content-Type header, or the Raw Body JSON.
**Build with AI will not fill these for you.** Do it yourself:

1. Open the **Custom Webhook** action in the workflow Build with AI just made.
2. **Method dropdown** = `POST`.
3. **URL box** = `https://<PUBLIC_HOSTNAME>/hooks/<ROUTE_ID>` (no trailing slash; keep the `/hooks/` segment).
4. **AUTHORIZATION dropdown** = `None`.
5. Under **HEADERS**, click **"Add item"**, then fill **Key box** = `Authorization` and **Value box** =
   `Bearer <HOOKS_TOKEN>`. Click **"Add item"** AGAIN, then **Key box** = `Content-Type` and **Value box** =
   `application/json`.
6. **Content-Type field** = `application/json`.
7. **RAW BODY box** = paste the full 23-key FLAT JSON from the prompt above (Body type = Raw JSON; insert each
   `{{…}}` via GHL's Custom Values picker).
8. Open **Settings** (top of the workflow) and turn **Allow Re-entry = ON** (so the workflow re-fires every
   time a contact replies — OFF makes it run once per contact and silently drop every later message).
9. **Save**, then flip the top-right toggle to **Publish**, then **Save** again.

**Verify every field above is non-empty before publishing.** An empty URL, a missing Authorization header,
or an empty Raw Body means the webhook silently does nothing and the customer gets no reply. This manual
Custom-Webhook fill is MANDATORY — do not skip it.

## Multi-action note (this template is the single-action starter)

The prompt above is the simplest shape: trigger + 2 filters + one Custom Webhook action. Real funnels are
often MULTI-ACTION. The same Build-with-AI prompt format supports **trigger + (optional if/else) +
one-or-more actions**:

- **If/else (if-else) branches** — branch on a tag, channel, or field value before the webhook (e.g. "if
  contact has tag `vip` → branch A, else → branch B").
- **Add-Tag actions** — apply a tag at a branch (e.g. tag `discovery-scheduled` after a booking step).
- **Tag-check conditions** — gate a branch on an existing tag ("only continue if contact has tag `lead`").
- **Multiple sequential actions** — e.g. Add-Tag → Custom Webhook → Add-Tag, or a different Custom Webhook
  per branch (each with its own URL + headers + the SAME 23-key flat body — no stripped bodies in any branch).

If a workflow needs a tag, the agent CREATES the tag first via the GHL skill (before building the
workflow), then references it by name in the prompt. Full multi-action spec + the field-by-field Custom
Webhook standard: `references/workflow-ai-instructions-standard.md`.

## Common Build with AI mistakes to verify against the checklist

Build with AI is helpful but has known failure modes. The most common ones:

- Puts the bearer token in the **AUTHORIZATION dropdown** instead of in the **Headers** section. The dropdown must be "None" — the `Authorization: Bearer <HOOKS_TOKEN>` line goes in Headers.
- Adds a trailing slash to the webhook URL, or drops the `/hooks/` path segment.
- Uses single curly-brace variables (`{contact.id}`) instead of GHL double-brace syntax (`{{contact.id}}`).
- **Re-nests the body** into `contact:{…}` / `customer_message:{…}` objects. The body MUST stay FLAT — a
  nested body makes EVERY field arrive EMPTY at the hook (verified live, even a hardcoded `"channel"` came
  through blank). Keep the flat keys exactly as shown above.
- **Changes the `messageTemplate` value in the body.** The body's `messageTemplate` MUST stay placeholder-free
  (no `{{…}}`) — if Build with AI inserts merge tokens into it, GHL mangles the JSON and the webhook is Skipped.
  Keep the exact placeholder-free string shown above.
- Types the `{{…}}` tokens as plain text instead of inserting them via GHL's **Custom Values picker**
  (typed-as-text tokens send empty).
- Saves the workflow as **Draft** instead of **Published**.
- Skips one of the 23 FLAT JSON body keys (most often `location_id`/`location_name`, `model`, `thinking`, or
  `to`). The body MUST have ALL 23 keys — 23 is the minimum, no short bodies.
- Sets the wrong run schedule (e.g., business hours only when you wanted 24/7).

Each of these failure modes is covered in **Section 4 — Workflow Verification Checklist** with the exact click-by-click fix. Run the checklist top-to-bottom after Build with AI finishes. Don't publish until every item is checked.

## Placeholders used in this template

When this template is rendered for a real client, the following placeholders are substituted with concrete values:

- `<CLIENT_BUSINESS_NAME>` — e.g., "Acme Coaching Co."
- `<CLIENT_FIRST_NAME>` — e.g., "Alex"
- `<PUBLIC_HOSTNAME>` — e.g., `claw.example.com`
- `<ROUTE_ID>` — e.g., `ZHC` (the hooks.mappings key configured in Step 3; also the flat body's `match` value)
- `<ROUTING_AGENT_ID>` — the agent the hook routes to (e.g., `main` or `sales`); also the flat body's `agent_id`
- `<HOOKS_TOKEN>` — the bearer token from `SECRETS_ENV_FILE`
- `<WORKFLOW_ID>` — `sms-inquiry-responder` (or the matching workflow file under `conversation-workflows/`)
- `<INDUSTRY_CONTEXT>` — e.g., "grants writing", "real estate", "coaching"
- `<DESIRED_OUTCOME>` — e.g., "book a 15-minute discovery call on your calendar", "set up a free consultation"
