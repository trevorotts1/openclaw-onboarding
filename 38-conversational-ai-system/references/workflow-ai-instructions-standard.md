<!-- OPERATOR HEADER -->
<!-- Skill 38 reference/protocol doc — the WORKFLOW-AI INSTRUCTIONS STANDARD. -->
<!-- Full content lives here (not in AGENTS.md/TOOLS.md — those get a 1-2 line pointer only). -->
<!-- 23-key rule honored: every GHL RAW BODY here = all 23 keys, FLAT, placeholder-free messageTemplate, no \n. -->
<!-- Added 2026-05-29 by skill38-comms-and-workflowai-standards. -->

# Workflow-AI Instructions Standard (Skill 38)

A **workflow-AI prompt** is the instruction set the agent generates — used by skill 44's internal-API path (Option 1, PRIMARY, when the Firebase token is present) or, as the no-token fallback, pasted by the operator into GHL / Convert and Flow's **"Build with AI" button** (Option 2) — to construct a NEW automation/workflow. GHL Automations have no PUBLIC API or MCP, but Skill 44's internal-API path (Tier 0) IS a programmatic build path and is the primary one when the token is present; Build with AI is the no-token fallback. This file
is the single standard for what every workflow-AI instruction set must contain, WHERE it goes, the
exact field-by-field steps for the Custom Webhook action (which Build-with-AI repeatedly fails to
populate), and how to teach MULTI-ACTION workflows.

> This standard is part of THE TRINITY. A workflow-AI prompt never travels alone — see
> `protocols/conversation-workflows-protocol.md` Section "THE TRINITY". If you create a workflow-AI
> prompt you MUST also have its matching **communications playbook** (Layer 2) and the **GHL
> workflow/automation** it builds. One implies the other two.


## 0. EVERY workflow-AI instruction set MUST INCLUDE ALL OF THE FOLLOWING

> **THIS IS THE STANDARD. NON-NEGOTIABLE. NO EXCEPTIONS.** The workflow-AI output was wildly different
> every run — that is the bug this section kills. Every workflow-AI instruction set the agent generates —
> for EVERY client, EVERY run, the STARTER SMS responder and EVERY custom playbook alike — MUST contain
> ALL of the numbered items below, in this order, with these exact structural pieces. The generator
> (`scripts/21-generate-client-reference-sheet.sh`) and the template
> (`templates/sms-workflow-ai-prompt-template.md`) emit this EXACT structure so every client gets the SAME
> experience. A workflow-AI instruction set that is missing ANY of these is INCOMPLETE and is machine-FAILED
> by `scripts/qc-reference-sheet.sh --require-manual-fill`.

1. **Workflow NAME + an explicit PUBLISH instruction.** Name the workflow, and end with "publish when done —
   do not leave it as a draft." (Build-with-AI loves to leave workflows in Draft.)
2. **TRIGGER — type + sub-option + filters, in this EXACT order.** State the trigger TYPE (for the SMS
   starter: **Customer Replied**), its SUB-OPTION (**On Reply**), and its FILTERS in the exact order they go
   in: **Filter 1: Channel = SMS**, then **Filter 2: Message Direction = Inbound**. If a filter references a
   TAG, that tag is created FIRST (item 6).
3. **SETTINGS — ALLOW RE-ENTRY = ON.** The workflow MUST be allowed to re-enter / fire repeatedly per
   contact. A contact who texts in today and again next week must re-trigger the workflow. If Allow Re-entry
   is OFF, the workflow fires ONCE per contact and every later message is silently dropped — the customer
   gets no reply and the failure is invisible. Set **Settings -> Allow Re-entry = ON** explicitly, every time.
4. **CUSTOM WEBHOOK — every field, the exact value (Section 3 verbatim).** EVENT = CUSTOM; METHOD = POST;
   URL = the exact hook URL; AUTHORIZATION dropdown = None; HEADERS via **Add item** (Authorization: Bearer
   <HOOKS_TOKEN>, then Content-Type: application/json); RAW BODY = the full FLAT 23-key JSON. No hand-waving —
   the prompt names every box and the exact value. See Section 3.
5. **SAVE -> PUBLISH toggle ON -> SAVE.** Save the action, flip the top-right Publish toggle from Draft to
   **Published**, then hit Save again. (Yes — Save, then Publish, then Save. The publish toggle does not
   persist without the final Save.)

> **Plus (carried from the original must-appear list, still required):** every action's fields spelled out
> (item 4 covers the Custom Webhook); multi-action support when the scenario needs it (Section 5); tags
> created FIRST (Section 6); a numbered manual-build fallback for when Build-with-AI is unavailable or mangles
> the structure; and a closing pointer to the verification checklist (Section 4).

---

## 1. WHERE it goes (do not guess) — CAF-first (Tier 0 PRIMARY)

The build path is decided by the canonical 3-layer doc `references/GHL_AI_LAYERS.md`. Two paths, in order:

**Option 1 — PRIMARY (Skill 44 / Tier 0, internal API).** When the client has Skill 44 installed AND a
healthy `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`, skill 44 builds the workflow structure directly via the
internal API (`caf workflows build`) from this same spec — the owner does nothing. This is the reliable
path and the default. Skill 44 then runs the same post-build verification checklist (Section 4).

**Option 2 — FALLBACK (no token, GHL "Build with AI" button).** Only when the Firebase token is absent or
expired, the prompt is pasted into GHL's **"Build with AI"** button in the **Automations area** when
creating a NEW automation/workflow:

1. Open Convert and Flow → **Automations** (left menu).
2. Click **Build with AI** (top-right of the Automations section).
3. Paste the prompt the agent saved at `<MASTER_FILES_DIR>/conversation-workflows/<id>--workflow-ai-prompt.md`.
4. Let Build with AI construct the structure.
5. Run the **Build-with-AI Verification Checklist** (Section 4) before publishing.

> CRITICAL — no PUBLIC API/MCP. GHL Automations have no PUBLIC API or MCP. Skill 44's internal-API path
> (Tier 0) IS a programmatic build path and is the PRIMARY one when the Firebase token is present. The
> Build with AI button is the no-token FALLBACK. See `references/GHL_AI_LAYERS.md` (canonical) and
> `references/GHL-INBOUND-AND-PLAYBOOKS.md` §4.

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
name — naming the EXACT box in the GHL Custom Webhook UI so a non-technical client can follow — and the
verification checklist MUST re-confirm each one:

- **EVENT** = `CUSTOM` (a Custom Webhook, not a templated integration webhook).
- **Method dropdown** = `POST` (choose POST from the dropdown — not GET/PUT).
- **URL box** = the EXACT hook URL: `https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>`. Do **NOT** leave the
  sample-url placeholder, do not add a trailing slash, do not drop the `/hooks/` segment.
- **AUTHORIZATION dropdown** = `None`. (The bearer token goes in HEADERS, not in this dropdown — the
  single most common Build-with-AI mistake.)
- **HEADERS** — under the HEADERS section click **"Add item"**, then fill the **Key box** and the **Value
  box** for that row; click **"Add item"** AGAIN for the second header. Each header is split into TWO
  separate copy blocks (Key + Value) on the client reference sheet — NEVER one combined block:
  - Row 1: **Key box** = `Authorization`, **Value box** = `Bearer <HOOKS_TOKEN>`. The Value box is ONLY
    `Bearer ` + the token — it must **NOT** repeat the word `Authorization` (a combined
    `Authorization: Bearer <token>` in the Value box is the bug, and is machine-FAILED by
    `scripts/qc-reference-sheet.sh`).
  - Row 2: **Key box** = `Content-Type`, **Value box** = `application/json` (the Value box is ONLY
    `application/json` — not `Content-Type: application/json`).
  - (add any other header the scenario needs the same way — one **"Add item"** per header)
- **CONTENT-TYPE field** = `application/json`.
- **RAW BODY box** = the FULL **23-key FLAT JSON** below, inserted with each `{{…}}` value placed via GHL's
  **Custom Values picker** (typed-as-text tokens send empty). Do NOT shorten to 4 keys (or 8/11/13/16) —
  23 is the MINIMUM. Keep it FLAT (no nested `contact:{…}` / `customer_message:{…}` — a nested body makes
  EVERY field arrive EMPTY at the hook). Keep `messageTemplate` placeholder-free (no `{{…}}` inside its
  value, or GHL mangles the JSON and the webhook is Skipped). No `\n` escapes inside the JSON.
- **Settings -> ALLOW RE-ENTRY = ON** (workflow-level, not a webhook field — but set it in the SAME build).
  The workflow must be allowed to re-enter / fire repeatedly per contact. With Allow Re-entry OFF the
  workflow fires ONCE per contact and silently drops every later message — the customer gets no reply and
  the failure is invisible. Turn it ON every time (Section 0, item 3).

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

> **Note (threading):** the inbound `{{channel}}` key is what the agent mirrors when it picks the reply
> `type`; `contact_id` + `location_id` are already keys. On the OUTBOUND send, GHL preserves the thread BY
> `contactId` — `conversationId` is never sent, it is looked up only to READ prior history. (No key changes:
> the 23-key set above is unchanged.)

## 3b. MANDATORY — manually fill the Custom Webhook AFTER Build-with-AI runs (it will NOT do it for you)

> **AFTER Build-with-AI runs, you MUST open the Custom Webhook action and MANUALLY enter every field
> below.** Build-with-AI only builds the workflow SHAPE (the trigger + an EMPTY Custom Webhook action) —
> it does **NOT** reliably populate the URL, the Authorization/Bearer header, the Content-Type header, or
> the Raw Body JSON. **Build-with-AI will NOT fill these for you.**
>
> Open the Custom Webhook action and enter, by hand:
> - **Method** = `POST`
> - **URL** = `https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>` (no trailing slash; keep the `/hooks/` segment)
> - **Headers** — click **"Add item"** for each: `Authorization: Bearer <HOOKS_TOKEN>` and
>   `Content-Type: application/json` (the AUTHORIZATION dropdown stays `None`)
> - **Raw Body JSON** = the full 23-key FLAT body from Section 3 (insert each `{{…}}` via the Custom
>   Values picker)
>
> Then **Save + Publish**. **Verify every field is non-empty before publishing** — an empty URL, a missing
> Authorization header, or an empty Raw Body means the webhook silently does nothing and the customer gets
> no reply. This manual fill is MANDATORY in every client setup.

## 4. BUILD-WITH-AI VERIFICATION CHECKLIST

Because Build-with-AI populates poorly, run this AFTER it finishes (even when it reports success) and
fix any item before publishing. For each item, the doc states WHERE to go, WHAT you should SEE, and WHAT
to put if it is missing/wrong. (Per-workflow, brutally-specific version generated alongside the prompt
— see `templates/workflow-verification-checklist-template.md`.)

- [ ] **Trigger type + filter** correct (matches the spec). **WHERE:** open the workflow → the Trigger
      node. **SEE:** the correct trigger TYPE + the intended filters. **If a filter references a TAG**
      (a "tag is/contains/does not contain" condition), confirm that tag ACTUALLY EXISTS and is the
      intended one — a **blank or non-existent tag in a "does not contain"/"contains" filter is the known
      bug** (a live client: Build-with-AI made a "does not contain `<blank>`" filter where the tag was never
      created, so it matched nothing). **PUT IF WRONG:** select/create the correct tag (it must appear under
      **Settings → Tags**), or remove the bad filter if it should not be there.
- [ ] **Exactly the intended action(s)** exist (no extra/missing nodes; branches as designed).
- [ ] Custom Webhook **EVENT = CUSTOM**.
- [ ] Custom Webhook **METHOD = POST** (not GET/PUT).
- [ ] **URL is the REAL hook URL** `https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>` (not sample-url; no trailing slash; `/hooks/` present).
- [ ] **AUTHORIZATION dropdown = None.**
- [ ] **HEADERS** contains `Authorization: Bearer <HOOKS_TOKEN>` (added via Add item) and `Content-Type: application/json`.
- [ ] **CONTENT-TYPE = application/json.**
- [ ] **RAW BODY = all 23 keys, FLAT**, placeholder-free `messageTemplate`, `{{…}}` inserted via Custom Values picker.
- [ ] **Settings -> Allow Re-entry = ON** (the workflow must re-fire per contact; OFF = it runs once per contact and silently drops every later message).
- [ ] **Tags** created/applied as designed (created via GHL skill first).
- [ ] **Workflow Published** (not Draft); run schedule correct.
- [ ] **End-to-end test** passes (execution log shows 2xx; message lands in the conversation log).

> **Machine-enforced.** Every GHL RAW BODY example in this skill (references/ + templates/ + scripts/) is
> scanned by `scripts/qc-23-key-bodies.sh`, which asserts exactly 23 flat keys, a placeholder-free
> `messageTemplate`, no nested objects, and no literal `\n` — and exits non-zero on any violation (it also
> runs in CI). THE TRINITY (this prompt ⇄ its communications playbook ⇄ its registry row) is enforced by
> `scripts/qc-trinity-registry.sh`. The 23-key rule is a check, not just a human checklist item.
>
> **MANDATORY SEND-DIRECTIVE (machine-enforced).** The in-GHL-body `messageTemplate` stays placeholder-free,
> but the SERVER-mapping `messageTemplate` (the `hooks.mappings` entry in `openclaw.json`) MUST carry the
> send-directive — the word **SEND**, the **GHL Conversations API** (POST `conversations/messages`), the
> **drafting-is-NOT-sending** clause, and **"do not end your turn until a messageId/conversationId is
> returned."** Without it the agent drafts a reply and stops — the customer gets nothing. This is verified by
> `scripts/qc-send-directive.sh` (CI + pre-handoff QC); see `references/GHL-INBOUND-AND-PLAYBOOKS.md` §4 for
> the canonical server mapping.
>
> **CRITICAL DESIGN PATTERN — one endpoint, mirror the channel, thread by `contactId`.** Replies go through
> exactly ONE endpoint — `POST /conversations/messages`. The reply `type` MIRRORS the inbound channel
> (SMS→`SMS`, Email→`Email`, Facebook→`FB`, Instagram→`IG`, WhatsApp→`WhatsApp`, Live Chat→`Live_Chat`) — do
> NOT hardcode `SMS`. The send body is `{type, contactId, locationId, message}` (Email also adds
> `subject`/`html`/`emailFrom`/`emailTo`); GHL threads the reply into the contact's conversation BY
> `contactId` automatically. **`conversationId` is read-only** — it is NOT a send-body field; use it only to
> read thread history (GET `/conversations/search?locationId=&contactId=` → GET
> `/conversations/{conversationId}/messages`). See `references/ghl-api-quick-reference.md` (MESSAGING) and
> `references/GHL-INBOUND-AND-PLAYBOOKS.md` §7-8.
>
> **CONVERSATION MEMORY — read-before / append-after (machine-enforced).** The in-GHL-body `messageTemplate`
> stays placeholder-free, but the SERVER-mapping `messageTemplate` MUST ALSO carry the conversation-memory
> steps: GHL inbound hook sessions are **single-turn / stateless**, so the agent's only memory of a contact
> across messages is that contact's conversation log
> (`<MASTER_FILES_DIR>/conversational-logs/<contact_id>__<name>.md`). The template MUST contain the
> **conversational-logs** path, a **READ**-before-replying instruction (continue any in-progress
> booking/topic), and an **APPEND**-after-sending instruction. Dropping these left a live client mid-booking
> with no memory. This is verified by `scripts/qc-conversation-memory.sh` (CI + pre-handoff QC); the
> `conversational-logs/` dir is created + made writable by the runtime/gateway user in Step 9
> (`scripts/09-install-conversation-workflows.sh`). See `references/GHL-INBOUND-AND-PLAYBOOKS.md` §4b.

## 5. MULTI-ACTION workflows (not just one action)

Teach Build-with-AI (and the manual fallback) to build more than a single webhook step when the scenario
needs it. The prompt template supports: **trigger + (optional if/else) + one-or-more actions.**

- **If/else (if-else) branches** — branch on tag, channel, or field value for additional filtering BEFORE
  the webhook step. Each branch lists its condition and its own action(s).
- **Add-Tag actions** — apply a tag at a branch (e.g. tag `ZHC-discovery-scheduled` after booking; agent-created tags carry the `ZHC-` prefix per MEMORY Rule 20).
- **Tag-check conditions** — "only continue if contact has tag `vip`" style gates.
- **Multiple sequential actions** — e.g. Add-Tag → Custom Webhook → Add-Tag; or different Custom Webhooks
  per branch (each with its own URL + headers + 23-key body).

Every Custom Webhook in a multi-action workflow uses the SAME 23-key flat-body rule from Section 3 — no
stripped bodies in any branch.

## 6. Tags: create the tag FIRST, then use it

**If the workflow uses ANY tag — a trigger or If/Else filter ("tag is" / "contains" / "does not contain")
or an Add-Tag action — the tag(s) MUST be CREATED FIRST, BEFORE the workflow is built, so the filter
references a REAL, existing tag.** This is non-negotiable: Build-with-AI will happily create a filter that
points at a tag that does not exist (e.g. `does not contain <blank>`), and that filter then silently
matches nothing (or everything). That blank/non-existent-tag filter is a confirmed live-client bug
(a live client) — see the post-build verification in Section 4 and `templates/workflow-verification-checklist-template.md`.

- **Agent path (preferred):** the agent CREATES the tag(s) via the GHL skill BEFORE building the workflow,
  then references each tag BY NAME in the Build-with-AI prompt. If the GHL skill lacks a create-tag method,
  fall back to the direct API call documented in `protocols/conversation-workflows-protocol.md` Section D.1.
  **Every tag the agent creates programmatically carries the `ZHC-` prefix** (e.g. `ZHC-discovery-scheduled`)
  per the ZHC tag-prefix rule (MEMORY Rule 20 / `protocols/zhc-tag-prefix-protocol.md`) — NOT retroactive;
  operator-created tags keep their existing names.
- **Client/operator path (where to check):** in GHL, tags live under **Settings → Tags**. Tell the client
  to open **Settings → Tags** and confirm they SEE every tag the workflow uses, spelled exactly as the
  workflow references it. A tag in a filter that is NOT listed under Settings → Tags is the bug — create it
  there (or via the agent) before the filter will work.
- Record created tag names + IDs in the workflow's `--ghl-side.md` file.

## 7. "YOUR COMMUNICATION PLAYBOOKS" — where they live + how the client builds a new one

The generated Client Reference Sheet carries a prominent **"Your Communication Playbooks"** section
(after the Quick Start, before the deep reference) that tells the client WHERE their playbooks live and HOW
the AI helps them build ADDITIONAL communication playbooks. This is part of the standard so every client doc
answers it the same way (friendly tone, generous emojis 💬🚀🛠️📅🏷️✅):

- **WHERE they live / are stored** — the working copies are in the client's OpenClaw master-files
  **`conversation-workflows/`** folder (the source of truth the agent reads on every reply); the
  human-facing copies are **mirrored to their Notion** (Notion → Google Docs → text). Both stay in sync.
- **"Want another communication playbook? Just ask me!"** — a clear CTA with a concrete COPYABLE example: the
  client just tells their AI **"Help me build a [purpose] playbook"** (e.g. *"Help me build a missed-call
  follow-up playbook"*), with more examples surfaced — **appointment-reminder, lead-nurture, review-request.**
- **A personal TRIGGER WORD (offered on the first build)** — explained like **"Alexa" / "Hey Siri"**: a
  word/phrase (e.g. *"Playbook time!"*) that instantly tells the AI the client wants to build a playbook. The
  AI offers it, confirms it, and remembers it so future builds recognize it.
- **The "I Do / You Do" process + ~15-30 min expectation** — so the client knows who does what and that a
  good playbook takes about 15-30 minutes to get right (YOU trigger → AI brainstorms a few questions → YOU
  answer → AI drafts → YOU review → AI finalizes/stores/wires the Workflow AI prompt → AI wires the actions →
  YOU approve, go live).
- **WHAT THE AI WILL DO when they ask:** (1) **brainstorm it with you** using what it already knows about
  your business (not a 50-question interrogation) — the AI's job is to brainstorm the PERFECT playbook with
  you (think: goal, who it's for, channel, offer, tone, timing/follow-up, the win action — "if you're unsure,
  that's what I'm here to brainstorm"); (2) **create the communication playbook** for you;
  (3) **store it** — the working copy in the master-files `conversation-workflows/` folder, mirrored to Notion;
  (4) **help you create the matching Workflow AI prompt** (Section 1 above), wired to **YOUR** Convert and Flow
  (GoHighLevel) account; and (5) that **the AI can take real actions in Convert and Flow on your behalf** — it
  CAN **create tags 🏷️, update your calendar 📅, create/book appointments 🗓️,** and similar automations.
- **The explicit statement:** *"You have an AI that is connected to your Convert and Flow account and can do
  these things for you — just ask."*

Machine-enforced by `scripts/qc-reference-sheet.sh --require-manual-fill` and detailed in
`references/communications-playbook-standard.md` §9. The agent-behavior detail (trigger-word offer +
"I Do / You Do" + brainstorm "what to think about") lives in `protocols/conversation-workflows-protocol.md`
§I.1a/§I.1b/§I.2.

## 8. Templates this standard governs

- `templates/sms-workflow-ai-prompt-template.md` — the copy-paste Build-with-AI prompt (field-by-field + multi-action note).
- `templates/workflow-verification-checklist-template.md` — the per-workflow verification checklist.
- `protocols/conversation-workflows-protocol.md` Step 9.20 D.2 / D.2b / D.3 — the runtime builder.
