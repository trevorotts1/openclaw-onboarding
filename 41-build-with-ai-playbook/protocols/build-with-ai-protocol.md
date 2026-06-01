# Build With AI Protocol -- Skill 41

## Purpose

The master protocol for generating GoHighLevel / Convert and Flow workflows using the Workflow AI Builder. This protocol governs the full lifecycle: brainstorm --> dependency audit --> dependency creation --> prompt generation --> operator build --> verification --> logging.

## Step 1: Brainstorm flow

When the operator asks to build a workflow, do NOT dump 50 questions. USE what you already know (business, products, services, calendars, who they are, habits -- from Typed Knowledge Bases + USER.md + MEMORY.md) and ask ONLY the smart gaps.

1. Summarize the operator's intent in one concise sentence.
2. Ask only the smart gaps:
   - What should trigger this? (if not stated)
   - Who should it target, and who should be EXCLUDED? (this becomes the trigger filters: all contacts, a tagged segment, new leads only, a pipeline, a value threshold)
   - What should happen if they don't respond? (wait + follow-up, or exit)
   - Any external system involved? (webhook to another tool)
3. Confirm with YES before proceeding. Never build on a guess.

## Step 2: Dependency audit

Before generating the Build With AI prompt, audit what tags, custom fields, and custom values the workflow will reference.

**Checklist:**
- [ ] List every tag referenced in triggers, actions, or conditions
- [ ] List every custom field referenced in Update Contact Field or If/Else
- [ ] List every custom value referenced in merge fields ({{custom_values.<name>}})
- [ ] Query GHL API to check which already exist
- [ ] Add missing items to the CREATE-FIRST list

**ZHC prefix rules:**
- Agent-created tags: ZHC- prefix (e.g., ZHC-new-lead)
- Agent-created custom fields: ZHC_ prefix (e.g., ZHC_lead_source)
- Agent-created custom values: no prefix required

## Step 3: Dependency creation

Create each missing dependency BEFORE generating the workflow prompt. Use the GHL API v2.

**API patterns:**

```
# Create tag
POST https://services.leadconnectorhq.com/locations/{locationId}/tags
Authorization: Bearer ${GOHIGHLEVEL_API_KEY}
Version: 2021-07-28
Content-Type: application/json

{"name": "ZHC-new-lead"}

# Create custom field
POST https://services.leadconnectorhq.com/locations/{locationId}/customFields
Authorization: Bearer ${GOHIGHLEVEL_API_KEY}
Version: 2021-07-28
Content-Type: application/json

{"name": "ZHC_lead_source", "dataType": "text", "group": "contact"}

# Create custom value
POST https://services.leadconnectorhq.com/locations/{locationId}/customValues
Authorization: Bearer ${GOHIGHLEVEL_API_KEY}
Version: 2021-07-28
Content-Type: application/json

{"name": "office_phone", "value": "+1 555 123 4567"}
```

**Verification:** GET the object back immediately after creation. If GET fails, retry once, then surface to operator.

**Logging:** emit dependency_created event to build-with-ai-events.jsonl.

## Step 4: Prompt generation

Generate the standardized 8-section prompt. Every prompt MUST contain:

1. Workflow name
2. Trigger specification
3. Dependency list
4. Action sequence
5. Conditions
6. Webhook configuration
7. Settings
8. Post-build verification checklist

Two sections need extra rigor:

- Trigger specification MUST include the trigger filters, stated explicitly as field, operator, and
  value, scoped to the intended audience. Build filters per protocols/trigger-filters-protocol.md,
  using the filter fields that the chosen trigger actually exposes and Any of / None of for tag
  include/exclude. Never leave a trigger unfiltered by omission; if the operator truly wants everyone,
  say so in the prompt. Add a re-fire guard where the trigger can fire repeatedly.
- Conditions MUST be designed as real If/Else branches per references/ghl-conditions-reference.md: name
  each If/Else as a question, set AND/OR grouping to match intent, order branches correctly (first
  match wins), and always give the auto-created None branch a sensible fallback. Any dynamic value
  referenced in a condition must already exist from the dependency-first step.

Reference templates/build-with-ai-prompt-template.md for the full template.

## Step 5: Operator build

Direct the operator to:
1. Navigate to Automations > Workflows
2. Click "Build using AI"
3. Paste the generated prompt
4. Click "Build Workflow"
5. Review the generated workflow
6. Make manual adjustments if needed

## Step 6: Verification

Run the 12-point checklist from protocols/verification-checklist.md. If any item fails, note the failure, suggest the fix, and re-verify.

## Step 7: Logging

Append one line to MASTER_FILES_DIR/build-with-ai-events.jsonl for the build session. Schema in references/f52-data-contract.md.

## Idempotency

All steps are idempotent:
- Dependency creation checks for existence before POST
- Core file updates use BEGIN/END markers
- Event log is append-only
