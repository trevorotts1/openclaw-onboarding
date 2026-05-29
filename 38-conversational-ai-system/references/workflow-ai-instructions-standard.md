<!-- OPERATOR HEADER -->
<!-- Skill 38 reference/protocol doc — the WORKFLOW-AI INSTRUCTIONS STANDARD. -->
<!-- Full content lives here (not in AGENTS.md/TOOLS.md — those get a 1-2 line pointer only). -->
<!-- 23-key rule honored: every GHL RAW BODY here = all 23 keys, FLAT, placeholder-free messageTemplate, no \n. -->
<!-- Added 2026-05-29 by skill38-comms-and-workflowai-standards. -->

# Workflow-AI Instructions Standard (Skill 38)

A **workflow-AI prompt** is the instruction set the agent generates and the operator pastes into
GHL / Convert and Flow's **"Build with AI" button** to construct a NEW automation/workflow. This file
is the single standard for what every workflow-AI instruction set must contain, WHERE it goes, the
exact field-by-field steps for the Custom Webhook action (which Build-with-AI repeatedly fails to
populate), and how to teach MULTI-ACTION workflows.

> This standard is part of THE TRINITY. A workflow-AI prompt never travels alone — see
> `protocols/conversation-workflows-protocol.md` Section "THE TRINITY". If you create a workflow-AI
> prompt you MUST also have its matching **communications playbook** (Layer 2) and the **GHL
> workflow/automation** it builds. One implies the other two.

---

## 1. WHERE it goes (do not guess)

The workflow-AI prompt is pasted into GHL's **"Build with AI"** button in the **Automations area** when
creating a NEW automation/workflow:

1. Open Convert and Flow → **Automations** (left menu).
2. Click **Build with AI** (top-right of the Automations section).
3. Paste the prompt the agent saved at `<MASTER_FILES_DIR>/conversation-workflows/<id>--workflow-ai-prompt.md`.
4. Let Build with AI construct the structure.
5. Run the **Build-with-AI Verification Checklist** (Section 4) before publishing.

> CRITICAL — no API, no MCP. GHL Automations have NO API and NO MCP for building automations. The ONLY
> path is the Build-with-AI button (manual paste). Do NOT write code that "calls the GHL Automations
> API" — it does not exist. See `references/GHL-INBOUND-AND-PLAYBOOKS.md` §4.

## 2. MUST-APPEAR checklist — every workflow-AI instruction set

The prompt's PRIMARY JOB is to get the **SHAPE** right (trigger, branches, tags, actions). Build-with-AI
often fumbles tokens/URLs, so the prompt must still spell every field out and the operator confirms via
the checklist. A workflow-AI instruction set is INCOMPLETE until ALL of these appear:

- [ ] **Workflow name** + an explicit **PUBLISH** instruction ("publish when done — don't leave it as draft").
- [ ] **Trigger** — the trigger TYPE (e.g. "Customer Replied" / "Form Submitted" / "Tag Added" / "FB Comment") + its FILTERS (in exact order).
- [ ] **Every action, every field spelled out** — for each action node, name the node type and every field value. (For Custom Webhook, use Section 3 verbatim.)
- [ ] **Custom Webhook field-by-field** (Section 3) — EVENT, METHOD, URL, AUTHORIZATION dropdown, HEADERS via Add item, CONTENT-TYPE, RAW BODY = full 23-key flat JSON via Custom Values picker.
- [ ] **Multi-action support** (Section 5) — if/else branches, Add-Tag actions, tag-check conditions, multiple sequential actions, as the scenario needs.
- [ ] **Tags created FIRST** — if any tag is referenced, the agent creates it via the GHL skill BEFORE building the workflow (Section 6), then references it by name.
- [ ] **Manual-build fallback** — a numbered click-by-click build of the SAME shape, in case Build-with-AI is unavailable or mangles the structure.
- [ ] **Pointer to the verification checklist** — the prompt ends by telling the operator to run the checklist.

## 3. Custom Webhook — explicit field-by-field (Build-with-AI fumbles these)

Build-with-AI repeatedly fails to populate the webhook fields. The prompt MUST instruct each field by
name, and the verification checklist MUST re-confirm each one:

- **EVENT** = `CUSTOM` (a Custom Webhook, not a templated integration webhook).
- **METHOD** = `POST` (choose from the dropdown — not GET/PUT).
- **URL** = the EXACT hook URL: `https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>`. Do **NOT** leave the
  sample-url placeholder, do not add a trailing slash, do not drop the `/hooks/` segment.
- **AUTHORIZATION dropdown** = `None`. (The bearer token goes in HEADERS, not in this dropdown — the
  single most common Build-with-AI mistake.)
- **HEADERS** — click **"Add item"** for each header:
  - Key = `Authorization`, Value = `Bearer <HOOKS_TOKEN>`
  - Key = `Content-Type`, Value = `application/json`
  - (add any other header the scenario needs the same way)
- **CONTENT-TYPE** = `application/json`.
- **RAW BODY** = the FULL **23-key FLAT JSON** below, inserted with each `{{…}}` value placed via GHL's
  **Custom Values picker** (typed-as-text tokens send empty). Do NOT shorten to 4 keys (or 8/11/13/16) —
  23 is the MINIMUM. Keep it FLAT (no nested `contact:{…}` / `customer_message:{…}` — a nested body makes
  EVERY field arrive EMPTY at the hook). Keep `messageTemplate` placeholder-free (no `{{…}}` inside its
  value, or GHL mangles the JSON and the webhook is Skipped). No `\n` escapes inside the JSON.

### Canonical 23-key RAW BODY (embed this exactly)

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

The 23 keys (exact): `id`, `match`, `action`, `agent_id`, `model`, `wakeMode`, `name`, `session_key`,
`messageTemplate`, `deliver`, `timeoutSeconds`, `channel`, `to`, `thinking`, `contact_id`, `first_name`,
`last_name`, `email`, `phone`, `subject`, `message_body`, `location_id`, `location_name`.

Per-channel variants keep ALL 23 keys; only `channel` and the `session_key` prefix
(`hook:ghl:<channel>:{{contact.id}}`) change. The per-client `id`/`match`/`agent_id` are substituted to
the client's hook name + routing agent.

## 4. BUILD-WITH-AI VERIFICATION CHECKLIST

Because Build-with-AI populates poorly, run this AFTER it finishes (even when it reports success) and
fix any item before publishing. (Per-workflow, brutally-specific version generated alongside the prompt
— see `templates/workflow-verification-checklist-template.md`.)

- [ ] **Trigger type + filter** correct (matches the spec).
- [ ] **Exactly the intended action(s)** exist (no extra/missing nodes; branches as designed).
- [ ] Custom Webhook **EVENT = CUSTOM**.
- [ ] Custom Webhook **METHOD = POST** (not GET/PUT).
- [ ] **URL is the REAL hook URL** `https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>` (not sample-url; no trailing slash; `/hooks/` present).
- [ ] **AUTHORIZATION dropdown = None.**
- [ ] **HEADERS** contains `Authorization: Bearer <HOOKS_TOKEN>` (added via Add item) and `Content-Type: application/json`.
- [ ] **CONTENT-TYPE = application/json.**
- [ ] **RAW BODY = all 23 keys, FLAT**, placeholder-free `messageTemplate`, `{{…}}` inserted via Custom Values picker.
- [ ] **Tags** created/applied as designed (created via GHL skill first).
- [ ] **Workflow Published** (not Draft); run schedule correct.
- [ ] **End-to-end test** passes (execution log shows 2xx; message lands in the conversation log).

> **Machine-enforced.** Every GHL RAW BODY example in this skill (references/ + templates/ + scripts/) is
> scanned by `scripts/qc-23-key-bodies.sh`, which asserts exactly 23 flat keys, a placeholder-free
> `messageTemplate`, no nested objects, and no literal `\n` — and exits non-zero on any violation (it also
> runs in CI). THE TRINITY (this prompt ⇄ its communications playbook ⇄ its registry row) is enforced by
> `scripts/qc-trinity-registry.sh`. The 23-key rule is a check, not just a human checklist item.

## 5. MULTI-ACTION workflows (not just one action)

Teach Build-with-AI (and the manual fallback) to build more than a single webhook step when the scenario
needs it. The prompt template supports: **trigger + (optional if/else) + one-or-more actions.**

- **If/else (if-else) branches** — branch on tag, channel, or field value for additional filtering BEFORE
  the webhook step. Each branch lists its condition and its own action(s).
- **Add-Tag actions** — apply a tag at a branch (e.g. tag `discovery-scheduled` after booking).
- **Tag-check conditions** — "only continue if contact has tag `vip`" style gates.
- **Multiple sequential actions** — e.g. Add-Tag → Custom Webhook → Add-Tag; or different Custom Webhooks
  per branch (each with its own URL + headers + 23-key body).

Every Custom Webhook in a multi-action workflow uses the SAME 23-key flat-body rule from Section 3 — no
stripped bodies in any branch.

## 6. Tags: create FIRST via the GHL skill

If a workflow references a tag, the agent CREATES the tag via the GHL skill BEFORE building the workflow
(do not tell the operator to navigate Settings → Tags by hand), then references the tag by name in the
prompt. If the GHL skill lacks a create-tag method, fall back to the direct API call documented in
`protocols/conversation-workflows-protocol.md` Section D.1. Record created tag names + IDs in the
workflow's `--ghl-side.md` file.

## 7. Templates this standard governs

- `templates/sms-workflow-ai-prompt-template.md` — the copy-paste Build-with-AI prompt (field-by-field + multi-action note).
- `templates/workflow-verification-checklist-template.md` — the per-workflow verification checklist.
- `protocols/conversation-workflows-protocol.md` Step 9.20 D.2 / D.2b / D.3 — the runtime builder.
