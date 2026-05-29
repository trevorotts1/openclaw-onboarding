<!-- OPERATOR HEADER -->
<!-- Skill 38 template: Workflow AI verification checklist (VERBATIM from playbook v5.14 Step 9.20-D.3, lines 4069-4170). -->
<!-- The pattern: every checklist item names the failure mode + the click-by-click fix. -->
<!-- Substitution placeholders: <PUBLIC_HOSTNAME>, <ROUTE_ID>, <CHANNEL>, <HOOKS_TOKEN>. -->
<!-- Rendered per-workflow by scripts/21-generate-client-reference-sheet.sh. -->

> "✓ Workflow AI prompt ready. Two things to do:
>
> 1. Open your Convert and Flow account
> 2. Click Automations on the left menu
> 3. Create a new workflow → Use Workflow AI
> 4. Paste the prompt I saved at:
>    `<MASTER_FILES_DIR>/conversation-workflows/<workflow-id>--workflow-ai-prompt.md`
> 5. Let Workflow AI build it
>
> Once it's built, come back and tell me. I'll give you a verification
> checklist — sometimes Workflow AI gets the scaffolding right but
> misses critical pieces."

#### D.3 — Generate the brutally-specific verification checklist

The agent writes a verification checklist tailored to the EXACT specifications the prompt was supposed to produce. Saved as: `<MASTER_FILES_DIR>/conversation-workflows/<workflow-id>--verification-checklist.md`.

The checklist follows this pattern — every item names the specific failure mode and the specific fix:

```markdown
# Verification Checklist — <Workflow Name>

After Workflow AI builds the workflow, open it and check EACH item below.
If any item is wrong, the fix is listed right there.

## Trigger

- [ ] Trigger is set to EXACTLY "<exact trigger name>"
  - WRONG VALUES TO WATCH FOR: <common Workflow AI mistakes>
  - FIX IF WRONG: Click the trigger node → change to "<exact value>"

## Filters

- [ ] Filter 1: <field> equals "<exact value>"
  - WRONG VALUES TO WATCH FOR: <variants Workflow AI may pick>
  - FIX IF WRONG: <specific click-by-click fix>

- [ ] Filter 2: <field> equals "<exact value>"
  - WRONG VALUES TO WATCH FOR: ...
  - FIX IF WRONG: ...

## Actions (count + identity)

- [ ] Exactly the intended action(s) exist — no extra nodes, no missing nodes,
       and any if/else branches + Add-Tag actions are present as designed.
  - FIX IF WRONG: Add/remove nodes so the action list matches the prompt spec.

## Webhook Action

- [ ] Event is CUSTOM (a Custom Webhook, not a templated integration webhook)
  - FIX IF WRONG: Webhook action → Event → CUSTOM

- [ ] Webhook URL is EXACTLY: `https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>`
  - Common mistake: Workflow AI leaves the SAMPLE-URL placeholder, adds a
    trailing slash, or drops the `/hooks/` path segment
  - FIX IF WRONG: Click the webhook action → URL field → paste exact URL

- [ ] Method is POST (not GET, not PUT)
  - FIX IF WRONG: Change Method dropdown to POST

- [ ] AUTHORIZATION dropdown is set to "None" (NOT "Bearer Token" — the
       token goes in Headers, not in this dropdown — common Workflow AI
       mistake)
  - FIX IF WRONG: AUTHORIZATION dropdown → None

- [ ] Headers section contains TWO headers:
       Header 1: Authorization = Bearer <HOOKS_TOKEN>
       Header 2: Content-Type = application/json
  - FIX IF WRONG: Add missing header(s) in the Headers section

- [ ] Content-Type dropdown is "application/json"
  - FIX IF WRONG: Change dropdown

- [ ] Raw Body has ALL 23 keys, is FLAT, and matches the JSON below
       EXACTLY (whitespace doesn't matter, but every key, every quote,
       every brace must match). 23 is the MINIMUM — a shorter body is WRONG.
       Only `channel` + the `session_key` prefix change per channel.

```json
{
  "id": "<HOOK_NAME>",
  "match": "<HOOK_NAME>",
  "action": "agent",
  "agent_id": "<ROUTING_AGENT_ID>",
  "model": "ollama/deepseek-v4-flash:cloud",
  "wakeMode": "now",
  "name": "GHL Sales Inbound",
  "session_key": "hook:ghl:<channel>:{{contact.id}}",
  "messageTemplate": "Respond as the Sales agent and reply to this contact via the GHL Conversations API per TOOLS.md",
  "deliver": false,
  "timeoutSeconds": 300,
  "channel": "<channel>",
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
  - Common Workflow AI mistake: skips one of the 23 keys, uses wrong
    variable syntax (e.g., `{contact.id}` instead of `{{contact.id}}`),
    or inserts merge tokens into the placeholder-free `messageTemplate`.
  - FIX IF WRONG: Click Raw Body → replace entirely with the 23-key JSON above

## Tags & multi-action

- [ ] Every `{{…}}` token in the Raw Body was inserted via GHL's Custom Values
       picker (NOT typed as plain text — typed tokens send empty)
  - FIX IF WRONG: Click into the body → delete the typed token → re-insert via
    the Custom Values picker

- [ ] Any tags this workflow applies were created/applied (tags are created
       FIRST via the GHL skill, then referenced by name)
  - FIX IF WRONG: Have the agent create the tag via the GHL skill, then add the
    Add-Tag action / select the existing tag

## Publish

- [ ] Workflow status is "Published" (NOT "Draft" — Workflow AI often
       saves as draft)
  - FIX IF WRONG: Click the toggle at top right of the workflow → Publish

- [ ] Workflow has a "When should this workflow run" setting that
       includes the times you want (e.g., All Day, or specific business
       hours)
  - FIX IF WRONG: Click workflow settings → adjust schedule

## End-to-end test

- [ ] Trigger the workflow manually (e.g., reply to your test SMS)
- [ ] Watch the workflow execution log in Convert and Flow — should
       show "Webhook sent successfully" with a 2xx status
- [ ] Check your conversation log file — should show the new message
       arrived in the AI's log

If end-to-end test passes, the workflow is fully wired and live.

If end-to-end test fails, copy the error from the Convert and Flow
execution log and bring it back to the agent.
```

Each verification item is generated from the same source-of-truth as the prompt — so they're guaranteed to match.
