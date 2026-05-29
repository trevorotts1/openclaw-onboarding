<!-- OPERATOR HEADER -->
<!-- Skill 38 template: Build-with-AI verification checklist (from playbook v5.14 Step 9.20-D.3, lines 4069-4170; operator-instruction location corrected to Automations → "Build with AI"). -->
<!-- The pattern: every checklist item names the failure mode + the click-by-click fix. -->
<!-- Substitution placeholders: <PUBLIC_HOSTNAME>, <ROUTE_ID>, <CHANNEL>, <HOOKS_TOKEN>. -->
<!-- Rendered per-workflow by scripts/21-generate-client-reference-sheet.sh. -->

> "✓ Build-with-AI prompt ready. Two things to do:
>
> 1. Open your Convert and Flow account
> 2. Click **Automations** on the left menu (GHL Automations have no API
>    and no MCP — the **Build with AI** button is the only programmatic path)
> 3. Create a **new** automation/workflow → click **Build with AI** (top-right)
> 4. Paste the prompt I saved at:
>    `<MASTER_FILES_DIR>/conversation-workflows/<workflow-id>--build-with-ai-prompt.md`
> 5. Let Build with AI build it
>
> Once it's built, come back and tell me. I'll give you a verification
> checklist — sometimes Build with AI gets the scaffolding right but
> misses critical pieces."

> **MANDATORY — manually fill the Custom Webhook AFTER Build with AI runs.** Build-with-AI only builds the
> workflow SHAPE (the trigger + an EMPTY Custom Webhook action). It does **NOT** fill in the URL, the
> Authorization/Bearer header, the Content-Type header, or the Raw Body JSON. **Build with AI will not fill
> these for you.** Before you run the checklist below, open the Custom Webhook action and MANUALLY enter:
> Method = POST; the URL `https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>`; Headers via **Add item** →
> `Authorization: Bearer <HOOKS_TOKEN>` and `Content-Type: application/json`; the Raw Body JSON (23-key flat);
> then **Save + Publish**. **Verify every field is non-empty before publishing.**

#### D.3 — Generate the brutally-specific verification checklist

The agent writes a verification checklist tailored to the EXACT specifications the prompt was supposed to produce. Saved as: `<MASTER_FILES_DIR>/conversation-workflows/<workflow-id>--verification-checklist.md`.

The checklist follows this pattern — every item names the specific failure mode and the specific fix:

```markdown
# Verification Checklist — <Workflow Name>

After Build with AI builds the workflow, open it and check EACH item below.
If any item is wrong, the fix is listed right there.

## Trigger

- [ ] Trigger is set to EXACTLY "<exact trigger name>"
  - WHERE: open the workflow → click the Trigger node at the top
  - WRONG VALUES TO WATCH FOR: <common Build with AI mistakes>
  - FIX IF WRONG: Click the trigger node → change to "<exact value>"

- [ ] If the trigger (or any filter) references a TAG, that tag ACTUALLY EXISTS
       and is the intended one
  - WHERE: open the Trigger node → look at any "tag is" / "tag contains" /
    "tag does not contain" filter; then cross-check GHL **Settings → Tags**
  - WHAT YOU SHOULD SEE: a REAL tag name in the filter — the exact tag created
    FIRST (per the create-tags-first rule), listed under Settings → Tags
  - KNOWN BUG (Teresa): Build with AI created a filter like
    **"does not contain `<blank>`"** where the referenced tag was blank or never
    created, so the filter silently matched nothing — the workflow never fired
    for the right contacts
  - FIX IF WRONG: select/create the correct tag so the filter points at a REAL
    tag (it must appear under Settings → Tags), OR remove the bad filter if it
    should not be there

## Filters

- [ ] Filter 1: <field> equals "<exact value>"
  - WRONG VALUES TO WATCH FOR: <variants Build with AI may pick>
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
  - Common mistake: Build with AI leaves the SAMPLE-URL placeholder, adds a
    trailing slash, or drops the `/hooks/` path segment
  - FIX IF WRONG: Click the webhook action → URL field → paste exact URL

- [ ] Method is POST (not GET, not PUT)
  - FIX IF WRONG: Change Method dropdown to POST

- [ ] AUTHORIZATION dropdown is set to "None" (NOT "Bearer Token" — the
       token goes in Headers, not in this dropdown — common Build with AI
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
  - Common Build with AI mistake: skips one of the 23 keys, uses wrong
    variable syntax (e.g., `{contact.id}` instead of `{{contact.id}}`),
    or inserts merge tokens into the placeholder-free `messageTemplate`.
    (The skill's body EXAMPLES are machine-checked by `scripts/qc-23-key-bodies.sh` —
    run it if you edit any embedded body.)
  - FIX IF WRONG: Click Raw Body → replace entirely with the 23-key JSON above

- [ ] SERVER mapping carries the MANDATORY SEND-DIRECTIVE — the
       `hooks.mappings` entry in `~/.openclaw/openclaw.json` (NOT the GHL body)
       has a `messageTemplate` that ORDERS the agent to SEND: it must contain
       the word SEND, the GHL Conversations API (POST conversations/messages),
       the "drafting/composing is NOT sending" clause, and "do not end your turn
       until a messageId/conversationId is returned." Without it the agent
       drafts a reply and stops — the customer gets nothing.
  - MACHINE-CHECK: `scripts/qc-send-directive.sh` must PASS.
  - FIX IF WRONG: open `~/.openclaw/openclaw.json`, edit the mapping's
    `messageTemplate` to include the send-directive (the in-GHL-body
    `messageTemplate` stays placeholder-free — the directive lives on the
    SERVER mapping only), then `openclaw config validate`.

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

- [ ] Workflow status is "Published" (NOT "Draft" — Build with AI often
       saves as draft)
  - FIX IF WRONG: Click the toggle at top right of the workflow → Publish

- [ ] Workflow has a "When should this workflow run" setting that
       includes the times you want (e.g., All Day, or specific business
       hours)
  - FIX IF WRONG: Click workflow settings → adjust schedule

## THE TRINITY (registry completeness)

- [ ] This workflow has its communications playbook (`<slug>.md`) AND its
       Build-with-AI prompt (`<slug>--build-with-ai-prompt.md`) AND a row in
       `conversation-workflows/registry.md`.
  - MACHINE-CHECK: `scripts/qc-trinity-registry.sh` must PASS (a registry row
    with a playbook but no Build-with-AI prompt — or an orphan prompt — is
    flagged INCOMPLETE; a Layer-1 "No (uses existing inbound routing)" row is
    legitimately prompt-free and passes).

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
