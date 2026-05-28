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

## Webhook Action

- [ ] Webhook URL is EXACTLY: `https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>`
  - Common mistake: Workflow AI adds trailing slash or wrong path
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

- [ ] Raw Body matches the JSON below EXACTLY (whitespace doesn't
       matter, but every field, every quote, every brace must match):

```json
{
  "channel": "<channel>",
  ... [full body from D.2 prompt] ...
}
```
  - Common Workflow AI mistake: skips fields, uses wrong variable
    syntax (e.g., `{contact.id}` instead of `{{contact.id}}`)
  - FIX IF WRONG: Click Raw Body → replace entirely with the JSON above

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
