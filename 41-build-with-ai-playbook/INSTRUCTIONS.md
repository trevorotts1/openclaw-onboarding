# Skill 41 -- Build With AI Playbook Generator: Runtime Instructions

This is the operator-facing runtime guide. It assumes the install scripts (00--06) have run. Read it top to bottom before acting (N3).

## The non-fabrication floor (read first)

**NEVER fabricate GHL capabilities.** This is the #1 rule of this skill, enforced by scripts/qc-prompt-completeness.sh. This rule extends to skill 44 (failed probe / unknown endpoint -> say so and degrade, never claim an unverified build). When a trigger or action is not available in the operator's plan tier, a lookup returns nothing, or a value is uncertain:

- Report the honest gap: "That trigger is not available on your current plan tier. I can suggest an alternative, or you can upgrade."
- Offer the operator the manual path: the GHL help docs, the API reference, or a manual build in the workflow builder.
- Do NOT invent a trigger, action, or capability that does not exist in GHL.
- Mark operator-provided configuration as such in the event log (source: "operator" vs source: "ghl_catalog").

## The master protocol: brainstorm --> dependencies --> build --> verify

### Command Center reflection (best-effort, silent when absent)

As the build moves through the steps below, reflect progress on the operator's Command Center
Kanban so the board mirrors real work (this skill otherwise only appends to
build-with-ai-events.jsonl, leaving the board static). This is **best-effort and fail-soft**:
when no Command Center is running (e.g. a client VPS without mission-control) every call is a
silent no-op and the build proceeds unchanged. It uses HTTP only (never writes the Command
Center database), never blocks a build, and logs to the operator's stderr only -- no
client-facing chatter.

Source the helper once at the start of a build session, then move the card per transition.
`$TASK_ID` and `$AGENT_ID` are supplied by the orchestrator when a Kanban card exists; if they
are unset the calls are harmless no-ops.

```bash
# Mac: $HOME/.openclaw ; VPS: /data/.openclaw
source "$HOME/.openclaw/skills/41-build-with-ai-playbook/scripts/lib-command-center.sh"
```

| Build transition | Column | Call |
|---|---|---|
| Step 1 brainstorm starts | planning | `cc_move_task "${TASK_ID:-}" planning "${AGENT_ID:-}"` |
| Step 5 build initiated | in_progress | `cc_move_task "${TASK_ID:-}" in_progress "${AGENT_ID:-}"` |
| Step 6 build completed (verified) | review | `cc_move_task "${TASK_ID:-}" review "${AGENT_ID:-}"` |
| Step 6 verification failed | blocked | `cc_move_task "${TASK_ID:-}" blocked "${AGENT_ID:-}"` (or return to orchestrator) |

`review -> done` is owned by the Command Center's QC scorer, NOT this builder: `cc_move_task`
refuses a `done` move on purpose (the builder must not self-grade to done). Requires
`MC_API_TOKEN` (sent only in the Authorization header, never logged) and optionally
`MISSION_CONTROL_URL` (default `http://localhost:4000`).

### Step 1: Brainstorm flow (friendly, concise)

When the operator asks to build a workflow, do NOT dump 50 questions. USE what you already know (business, products, services, calendars, who they are, habits -- from Typed Knowledge Bases + USER.md + MEMORY.md) and ask ONLY the smart gaps.

1. **Summarize what you understand** in one concise sentence: "You want a workflow that [trigger] -> [action sequence] -> [outcome]. Is that right?"
2. **Ask the smart gaps only:**
   - What should trigger this? (if not stated)
   - Who should it target? (all contacts, tagged segment, new leads only)
   - What should happen if they don't respond? (wait + follow-up, or exit)
   - Any external system involved? (webhook to another tool)
3. **Confirm with YES** before proceeding. Never build on a guess.

> Best-effort Command Center: `cc_move_task "${TASK_ID:-}" planning "${AGENT_ID:-}"` (silent no-op if no Command Center / no card).

### Step 2: Dependency audit (what must exist FIRST)

Before generating the Build With AI prompt, audit what tags, custom fields, and custom values the workflow will reference. The Workflow AI Builder inserts placeholder syntax but does NOT create these objects.

> This dependency-first contract (tags, custom fields, custom values created
> BEFORE the workflow references them) is a HARD INPUT CONTRACT on skill 44: skill
> 44 will REFUSE to build a workflow whose dependencies do not yet exist. GET-back
> verification (Step 3) and the ZHC-/ZHC_ standing-approval rule bind skill 44's
> writes identically.

**Dependency types to check:**
- **Tags** referenced in: Contact Tag trigger, Add/Remove Contact Tag actions, If/Else conditions
- **Custom fields** referenced in: Update Contact Field action, If/Else conditions, trigger filters
- **Custom values** referenced in: merge fields in emails/SMS/webhooks ({{custom_values.<name>}})

**For each dependency:**
1. Check if it already exists (GET /locations/{locationId}/tags, /customFields, /customValues)
2. If missing, add it to the CREATE-FIRST list
3. The operator must approve creation (standing approval for ZHC- / ZHC_ prefixed objects). This ZHC- standing approval extends to skill 44 writes identically.

**ZHC prefix rules:**
- Agent-created tags: ZHC- prefix (e.g., ZHC-new-lead, ZHC-welcome-sent)
- Agent-created custom fields: ZHC_ prefix (e.g., ZHC_lead_source, ZHC_appointment_date)
- Agent-created custom values: no prefix required (they are global merge fields)

### Step 3: Create dependencies (via GHL API)

Call scripts/dependency-creation.sh (or the equivalent API calls) to create each missing dependency BEFORE generating the workflow prompt.

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

**Verification:** GET the object back immediately after creation. If the GET fails, retry once, then surface to the operator. This GET-back retry-once pattern extends to skill 44 (failed probe / unknown endpoint -> say so and degrade, never claim an unverified build).

**Logging:** emit a dependency_created event to build-with-ai-events.jsonl for each object created.

### Step 4: Generate the standardized Build With AI prompt

Every prompt MUST follow the 8-section template at templates/build-with-ai-prompt-template.md. Sections in order:

1. **Workflow name** -- clear, descriptive, under 60 characters
2. **Trigger specification** -- trigger type + any filters (e.g., "Contact Created, filter: tag = ZHC-new-lead")
3. **Dependency list** -- all tags, custom fields, custom values that were created in Step 3
4. **Action sequence** -- numbered steps with exact configuration:
   - Step 1: Add Tag ZHC-welcome-sent
   - Step 2: Send Email (template: Welcome, from: {{location.name}}, subject: "Welcome!")
   - Step 3: Wait 1 day
   - Step 4: If/Else: has tag ZHC-responded? YES -> exit, NO -> Send SMS follow-up
5. **Conditions** -- If/Else logic with explicit YES/NO branches and segment conditions
6. **Webhook configuration** -- if applicable: method (GET/POST/PUT/DELETE), URL, headers, raw JSON body with merge fields
7. **Settings** -- re-entry (yes/no), stop on response (yes/no), time windows, sender details
8. **Post-build verification checklist** -- copy-paste the 12-point checklist from protocols/verification-checklist.md

**Formatting rules for the prompt:**
- Use plain English, not JSON
- Use GHL merge field syntax: {{contact.first_name}}, {{custom_values.office_phone}}
- For webhooks, show the raw JSON body with merge fields embedded
- Number every action step
- Label If/Else branches clearly: "YES branch:" and "NO branch:"

### Step 5: Build the workflow — Option 1 (CAF direct) or Option 2 (manual paste)

> Best-effort Command Center: on build start, `cc_move_task "${TASK_ID:-}" in_progress "${AGENT_ID:-}"` (silent no-op if absent). Build paths and event logging are unchanged by this.

> **3-layer architecture reference:** `38-conversational-ai-system/references/GHL_AI_LAYERS.md`
> is the canonical doc for the Layer 0 compile-time build-path decision (CAF vs Build-with-AI),
> Layer 1 (Workflow AI step prompt), and Layer 2 (OpenClaw playbook). Cross-read it before any
> workflow build.

**Option 1 — CAF direct (PRIMARY):** when the client has Skill 44 (convert-and-flow-operator)
installed AND a healthy `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`:

1. Skill 44 receives this skill's 8-section structure (Steps 2-4 output).
2. `caf workflows build` sends it to the GHL internal Build API directly.
   - Engine v2.1.0+ (`link_steps()` runs BEFORE save — no corrupted step order; rejected save
     exits non-zero — no silent Steps:0/Errors:0/exit-0 false-pass).
3. Proceed directly to Step 6 (12-point verification) — **do not skip even on a successful build**.

**Option 2 — Manual paste (FALLBACK):** when the Firebase token is absent or expired:

1. Navigate to Automations > Workflows in GHL / Convert and Flow.
2. Click "Build using AI" (top-right of workflow list).
3. Paste the generated prompt (from Step 4) into the AI prompt box.
4. Click "Build Workflow".
5. Wait for AI generation (under 30 seconds average).
6. Review the generated workflow visually.
7. Make any manual adjustments (the AI may need clarification on complex logic).
8. Run the 12-point verification checklist (Step 6).
9. Toggle to Published and Save.

> The dependency-first contract (Steps 2-3) and the 12-point verification (Step 6) bind BOTH paths.
> **The human is always the final verifier** on both paths — the in-builder "Test" button sends
> empty merge fields and passes even when the live payload is broken.

### Step 6: Post-build verification (12-point checklist)

> Skill 44 runs this exact 12-point checklist as its structural post-build check
> after an internal-API build, the same way the manual path runs it after a paste
> build. The checklist is path-agnostic.

Run protocols/verification-checklist.md after every build:

1. Workflow name matches the prompt
2. Trigger is correct type and filters are applied
3. All referenced tags exist and are spelled correctly
4. All referenced custom fields exist and have correct data type
5. All referenced custom values exist and have values set
6. Action sequence matches the prompt (order, configuration)
7. If/Else conditions evaluate the right fields with correct operators
8. Wait steps have correct duration
9. Webhook URL is correct and method matches the prompt
10. Webhook headers include Content-Type: application/json (for raw JSON body)
11. Settings: re-entry, stop on response, time windows are correct
12. Test the workflow with a test contact before going live

**If any checklist item fails:** note the failure, suggest the fix, and re-verify.

> Best-effort Command Center: on a clean pass, `cc_move_task "${TASK_ID:-}" review "${AGENT_ID:-}"` (let the Command Center QC scorer promote review->done -- never self-promote). On a failure that cannot be fixed in-line, `cc_move_task "${TASK_ID:-}" blocked "${AGENT_ID:-}"` and return to the orchestrator. Silent no-op if no Command Center.

### Step 7: Log to build-with-ai-events.jsonl

Append one line per build session to MASTER_FILES_DIR/build-with-ai-events.jsonl. Schema in references/f52-data-contract.md. The jsonl log is the canonical record and is written on every path; the Command Center reflection above is an additional best-effort mirror, never a substitute. After Step 6 the card rests in `review` for the Command Center QC scorer to promote -- this builder never moves a card to `done`.

## Webhook configuration deep-dive

When the workflow needs to send data to an external system, use the Custom Webhook action. The protocol at protocols/webhook-configuration-protocol.md covers:

**Modes:**
- CUSTOM (advanced): choose method, Content-Type, Raw Body editor for JSON
- POST (simple): Body key/value pairs only
- GET (simple): No body, only query parameters

**Headers:**
- Content-Type: application/json for JSON raw body
- Authorization: Bearer ${TOKEN} for bearer auth
- Custom keys like X-API-Key
- Dynamic values: {{location.api_token}}, {{location.external_api_key}}

**Raw JSON Body (CUSTOM mode only):**
- Must use CUSTOM event mode
- Set Content-Type: application/json
- Paste valid JSON with merge fields: {{contact.id}}, {{contact.email}}, etc.
- Nested JSON supported

**Merge fields in webhooks:**
- Contact fields: {{contact.id}}, {{contact.first_name}}, {{contact.email}}, {{contact.phone}}
- Location fields: {{location.api_token}}, {{location.external_api_key}}
- Custom values: {{custom_values.<name>}}
- Tags: {{contact.tag}}

**Save Response:**
- Enable "Save response from this Webhook" to store response for follow-up actions

## Conversation playbook pairing (with Skill 38)

When a workflow triggers a conversation (e.g., Customer Replied trigger, Conversation AI action), pair the workflow with a conversation playbook:

1. Register the workflow trigger in Skill 38's conversation-workflows/registry.md
2. Create the conversation playbook at conversation-workflows/<workflow-id>.md
3. Use templates/conversation-playbook-template.md as the starting structure
4. The conversation playbook handles: tone, signature, escalation triggers, FAQ scope, interrupt handling

Full pairing protocol: see Skill 38 INSTRUCTIONS.md -- "Conversation Playbook Builder trigger phrases."

## build-with-ai-events.jsonl schema

Append-only JSONL at MASTER_FILES_DIR/build-with-ai-events.jsonl. One JSON object per line. Common fields on every event:

| Field | Type | Meaning |
|---|---|---|
| ts | string (ISO-8601 UTC) | When the event was appended |
| skill | string | Always "41-build-with-ai-playbook" |
| event | string | One of the event types below |
| session_ref | string | Opaque session reference (NOT PII) |
| source | string | Data origin: "ghl_catalog", "operator", "api_response" |

Event types and type-specific payload fields:

| event | Type-specific fields |
|---|---|
| brainstorm_started | operator_intent_summary (string) |
| dependency_audited | missing_tags (array), missing_fields (array), missing_values (array) |
| dependency_created | object_type (tag/field/value), object_name, zhc_prefixed (bool) |
| prompt_generated | prompt_section_count (int), sections_present (array) |
| build_initiated | operator_confirmed (bool) |
| build_completed | workflow_name, verification_score (int/12) |
| verification_failed | failed_items (array), fix_suggested (string) |
| webhook_configured | method, url_domain (string, not full URL), save_response_enabled (bool) |
| conversation_playbook_paired | workflow_id, playbook_path |
| qc_result | total (int), pass_count (int), fixed_count (int), escalated_count (int), publish_decision (bool) |

**PII discipline:** the event log records object names and counts, never raw contact data or full URLs with tokens.

## Idempotency & re-runs

All 00--06 scripts are idempotent (version/marker compare, then act) -- including 05-configure-executor-model.sh (config deep-merge, skip if current-version marker present) and 06-verify-agent-browser.sh (skips install when the binary is already found, re-runs the probe). dependency-creation.sh checks for existence before creating (GET first, POST only if missing). Re-running the installer never double-appends core-file blocks (BEGIN/END markers).

## Verification checklist (post-install)

- [ ] ~/.openclaw/skills/41-build-with-ai-playbook/ exists with all listed files
- [ ] scripts/*.sh are chmod +x
- [ ] 00-verify-prerequisites.sh passes (jq, curl, GHL PIT, locationId present)
- [ ] MASTER_FILES_DIR/build-with-ai-events.jsonl exists (created by 03-init-jsonl-sinks.sh)
- [ ] bash scripts/qc-no-personal-data.sh --> PASS
- [ ] bash scripts/qc-prompt-completeness.sh --> PASS
- [ ] bash scripts/qc-dependency-order.sh --> PASS
