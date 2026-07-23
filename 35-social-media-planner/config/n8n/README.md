# Skill 35 — n8n Workflow Definitions (config/n8n)

Skill 35's Google Sheet integration runs through two n8n webhooks hosted on the
BlackCEO Automations hub (`main.blackceoautomations.com`):

| Webhook | When called | Purpose |
|---------|-------------|---------|
| `social-planner-sheet-create` | ONCE, at install (INSTALL.md Step 7) | Copy the fleet template into a new client Google Sheet, grant the client edit access, return `{sheetUrl, sheetId, sheetName}`. |
| `social-planner-row-append` | EVERY publish cycle (SKILL.md Media Delivery Contract step 4) | Append one content row to the client sheet's **Weekly Overview** tab. Image cells arrive as `=IMAGE("url", 1)` formula strings and are written with `valueInputOption: USER_ENTERED`. |

## Status of these files

The two `*.json` files here are **reconstructed-from-contract placeholders**, not
live `n8n export` dumps. The production workflows live on the n8n instance at
`main.blackceoautomations.com` and were not checked into this repo; the operator
and Maria boxes were not reachable during the v21.0 fix pass, so a real export was
not possible. Each JSON file documents the expected node graph, payload contract,
Google Sheets target, and (for row-append) the `=IMAGE()`/`USER_ENTERED` handling
and the 108px-column / 133px-row sizing, all taken from the documented ground truth
(CHANGELOG v2.6.0, INSTALL.md Step 7 sections 4a-4f, CORE_UPDATES.md).

**To replace with the live workflows** (when the instance is reachable):

```bash
# On a host with n8n CLI access to main.blackceoautomations.com:
n8n export:workflow --id=myXde6jbIIkaG5zW --output=social-planner-row-append.json
# (look up the sheet-create workflow id in the n8n UI, then export it likewise)
```

Overwrite the placeholder JSON with the real export and drop the `_PLACEHOLDER_NOTE`
field. Do not hand-edit the node graph to match the placeholder — the live workflow
is the source of truth.
