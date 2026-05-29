<!-- OPERATOR HEADER -->
<!-- Skill 38 template: SMS Workflow AI prompt — copy-paste-ready. -->
<!-- Built from playbook v5.14 Step 9.20-D.2 (lines 4015-4069). -->
<!-- Substitution placeholders are listed below. Rendered per-client by scripts/21-generate-client-reference-sheet.sh. -->
<!-- The single fenced code block below is what the client pastes into Convert and Flow's Workflow AI. -->

# Your First Workflow — SMS Inquiry Responder

This is the first conversation workflow we're wiring up for **<CLIENT_BUSINESS_NAME>**. When a contact texts you, this workflow fires, sends the message to your conversational AI, and lets the AI respond on your behalf — including, when the conversation is ready, helping the contact <DESIRED_OUTCOME>.

You don't have to build this workflow by hand. Convert and Flow has a built-in tool called **Workflow AI** that constructs the entire workflow from a prompt. The prompt is below. Copy it once, paste it once, done.

## How to use this

1. Open your Convert and Flow account.
2. Click **Automations** on the left menu.
3. Click **Create workflow** → choose **Use Workflow AI**.
4. Copy the entire block below (the one starting with `Build a workflow for me with these exact specifications:`) and paste it into Workflow AI.
5. Let Workflow AI build the workflow.
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
- Action 1: Send Custom Webhook
  - URL: https://<PUBLIC_HOSTNAME>/hooks/<ROUTE_ID>
  - Method: POST
  - AUTHORIZATION dropdown: None  (the token goes in Headers, NOT in the Authorization dropdown — leave the dropdown set to None)
  - Headers:
    - Authorization: Bearer <HOOKS_TOKEN>
    - Content-Type: application/json
  - Content-Type dropdown: application/json
  - Body type: Raw JSON
  - Body (Raw JSON — FLAT, no nested objects, ALL 23 keys, placeholder-free messageTemplate):
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

PUBLISH: Yes, publish the workflow when done — don't leave it as draft.

RUN SCHEDULE: All Day (so the AI can respond at any hour the customer texts in).
```

## What Workflow AI will build

After you paste the prompt above, Workflow AI should produce a workflow with:

- **One trigger node**: "Customer Replied" with sub-option "On Reply" and channel filter "SMS".
- **Two filter nodes** (in order): Channel = SMS, Message Direction = Inbound.
- **One action node**: "Send Custom Webhook" pointing at `https://<PUBLIC_HOSTNAME>/hooks/<ROUTE_ID>` with the two headers above and the Raw JSON body above.
- **Status**: Published (NOT draft).
- **Run schedule**: All Day.

If the workflow Workflow AI produced doesn't match this shape, that's normal — Workflow AI is a helper, not infallible. Use the verification checklist (Section 4) to fix the gaps.

## Common Workflow AI mistakes to verify against the checklist

Workflow AI is helpful but has known failure modes. The most common ones:

- Puts the bearer token in the **AUTHORIZATION dropdown** instead of in the **Headers** section. The dropdown must be "None" — the `Authorization: Bearer <HOOKS_TOKEN>` line goes in Headers.
- Adds a trailing slash to the webhook URL, or drops the `/hooks/` path segment.
- Uses single curly-brace variables (`{contact.id}`) instead of GHL double-brace syntax (`{{contact.id}}`).
- **Re-nests the body** into `contact:{…}` / `customer_message:{…}` objects. The body MUST stay FLAT — a
  nested body makes EVERY field arrive EMPTY at the hook (verified live, even a hardcoded `"channel"` came
  through blank). Keep the flat keys exactly as shown above.
- **Changes the `messageTemplate` value in the body.** The body's `messageTemplate` MUST stay placeholder-free
  (no `{{…}}`) — if Workflow AI inserts merge tokens into it, GHL mangles the JSON and the webhook is Skipped.
  Keep the exact placeholder-free string shown above.
- Types the `{{…}}` tokens as plain text instead of inserting them via GHL's **Custom Values picker**
  (typed-as-text tokens send empty).
- Saves the workflow as **Draft** instead of **Published**.
- Skips one of the 23 FLAT JSON body keys (most often `location_id`/`location_name`, `model`, `thinking`, or
  `to`). The body MUST have ALL 23 keys — 23 is the minimum, no short bodies.
- Sets the wrong run schedule (e.g., business hours only when you wanted 24/7).

Each of these failure modes is covered in **Section 4 — Workflow Verification Checklist** with the exact click-by-click fix. Run the checklist top-to-bottom after Workflow AI finishes. Don't publish until every item is checked.

## Placeholders used in this template

When this template is rendered for a real client, the following placeholders are substituted with concrete values:

- `<CLIENT_BUSINESS_NAME>` — e.g., "The Winning Formula Course"
- `<CLIENT_FIRST_NAME>` — e.g., "Christy"
- `<PUBLIC_HOSTNAME>` — e.g., `claw.thewinningformulacourse.com`
- `<ROUTE_ID>` — e.g., `ZHC` (the hooks.mappings key configured in Step 3; also the flat body's `match` value)
- `<ROUTING_AGENT_ID>` — the agent the hook routes to (e.g., `main` or `sales`); also the flat body's `agent_id`
- `<HOOKS_TOKEN>` — the bearer token from `SECRETS_ENV_FILE`
- `<WORKFLOW_ID>` — `sms-inquiry-responder` (or the matching workflow file under `conversation-workflows/`)
- `<INDUSTRY_CONTEXT>` — e.g., "grants writing", "real estate", "coaching"
- `<DESIRED_OUTCOME>` — e.g., "book a 15-minute discovery call on your calendar", "set up a free consultation"
