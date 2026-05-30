<!-- OPERATOR HEADER (6 lines) — DO NOT EDIT BELOW -->
<!-- Source: openclaw-cloudflare-tunnel-prompt (1).md v5.14 — lines 3857-4322 -->
<!-- Section: Step 9.20 — Conversation Playbook Builder (3-PART, communication-driven) -->
<!-- This file is a VERBATIM extraction from the v5.14 playbook, hardened by the v1.4.1 -->
<!-- conversation-playbook-builder enhancement. Do not summarize. -->
<!-- Patch source: skill-38-patch-1 agent — 2026-05-28; builder enhancement — 2026-05-28 -->

## Step 9.20 — Conversation Playbook Builder (the system's differentiator)

> **What this step is, in one line:** the recurring, bulletproof flow for when the operator says
> "help me build a conversation playbook." It is ALWAYS a **3-PART build** (below). This is the system's
> USP: **communication-driven funnels / communication-driven automations** — the operator and the agent
> BUILD by talking and brainstorming, NOT by clicking and dragging nodes. This is what beats CloseBot and
> every visual-node competitor.

The Conversation Playbook Builder is the system's biggest single differentiator. Other conversational AI platforms make operators BUILD workflows in visual node-based UIs (n8n, Zapier, GHL/Convert and Flow Workflow Builder, CloseBot). This system makes operators TALK through workflows — the agent asks intelligent questions, synthesizes a Conversation Playbook, AND auto-builds the GHL routing layer the customer needs to reach the AI in the first place.

### DISTINCTION MAP — four terms operators confuse (read this first)

These four terms are correct but were spread across three files. This is the one canonical table. Skim
it before building anything; the rest of this protocol uses these terms precisely.

| Term | What it is | Where it lives | Who it's for | One per… |
|---|---|---|---|---|
| **Channel communication playbook** | The baseline tone/voice/signature for ONE channel (SMS, email, FB, IG, WhatsApp, Live Chat, etc.). Applies to EVERY reply on that channel. | `<MASTER_FILES_DIR>/` channel playbooks (scaffolded by `scripts/12-scaffold-channel-playbooks.sh`); pointer in AGENTS.md Step 4. | The AI (read at reply time) | channel |
| **Communications playbook** (a.k.a. Layer 2 conversation-workflow playbook) | A SCENARIO-specific behavior override (pricing inquiry, booking, refund, FAQ…). Phases + edge cases + on-success/escalation. Overrides the channel playbook's body when its trigger fires, but still honors the channel's tone. | `<MASTER_FILES_DIR>/conversation-workflows/<slug>.md`, registered in `registry.md`. Standard: `references/communications-playbook-standard.md`. | The AI (read at reply time when the scenario fires) | scenario (many per client) |
| **Workflow-AI prompt** (a.k.a. Build-with-AI prompt) | A natural-language INSTRUCTION SET the OPERATOR pastes into GHL to build the routing. It is text the human copies; it is NOT what the AI runs. | `<MASTER_FILES_DIR>/conversation-workflows/<slug>--build-with-ai-prompt.md`. Standard: `references/workflow-ai-instructions-standard.md`. | The HUMAN operator (paste-once) | scenario needing new GHL routing |
| **GHL automation / workflow** | The actual built thing inside GHL (Convert and Flow) Automations — trigger + filters + Custom Webhook — that DELIVERS the inbound conversation to OpenClaw. Built by pasting the workflow-AI prompt into **Automations → "Build with AI"** (no API, no MCP). | Inside the client's GHL account (Automations area). Mirrored for reference in `<slug>--ghl-side.md`. | The GHL platform (runs server-side) | scenario / channel route |

**The relationship in one line:** the operator pastes the **workflow-AI (Build-with-AI) prompt** to
build the **GHL automation**, which routes inbound messages to OpenClaw, where the AI runs the
**communications playbook** (scenario override) on top of the **channel communication playbook**
(baseline tone). THE TRINITY below binds three of these (GHL automation + communications playbook +
workflow-AI prompt) so they always ship together.

---

### THE TRINITY — three artifacts travel together (binding connection rule)

A GHL **workflow/automation**, a **communications playbook**, and a **workflow-AI prompt** are ONE unit
of three parts. They are inseparable — building or creating any one of them implies the other two:

- If you build a **GHL workflow/automation**, you MUST also have its **communications playbook** (Layer 2,
  `conversation-workflows/<id>.md`) AND its **workflow-AI prompt** (`<id>--workflow-ai-prompt.md`).
- If you create a **communications playbook**, you MUST create the matching **workflow-AI prompt** AND the
  **GHL workflow** (or confirm existing routing covers it per the Layer 0 check).
- If you create a **workflow-AI prompt**, you MUST have its **communications playbook** AND build the
  **GHL workflow** it constructs.

One implies the other two. A playbook with no workflow-AI prompt, or a workflow with no playbook, is an
incomplete build — do not register it and do not declare it live. The TRINITY maps onto the 3-PART build
(below): Part 1 = the workflow-AI prompt (+ the GHL workflow it builds), Part 2 = the communications
playbook. The physical link at runtime is the **hook path** (see Section F).

**Full standards for two of the three legs live in dedicated reference docs (keep them out of the core md
files):**

- **Communications playbook** — format + must-appear checklist + storage + the Notion→Google Docs→plain-text
  fallback order: `references/communications-playbook-standard.md`.
- **Workflow-AI prompt** — must-appear checklist + WHERE (Build-with-AI button in Automations) + the
  field-by-field Custom Webhook steps + multi-action teaching + the Build-with-AI verification checklist:
  `references/workflow-ai-instructions-standard.md`.

**Machine-enforced:** `scripts/qc-trinity-registry.sh` scans the client's
`conversation-workflows/registry.md` + files and FAILS any row that has a communications playbook but no
matching Build-with-AI prompt (or an orphan prompt with no playbook). THE TRINITY is a check, not just a
checklist item. (A registry row marked Layer 1 = "No (uses existing inbound routing)" is legitimately
prompt-free and passes.) The 23-key GHL body authority (`references/GHL-INBOUND-AND-PLAYBOOKS.md` §14) is
likewise machine-enforced by `scripts/qc-23-key-bodies.sh`.

> **Upstream — Skill 23 triggers this.** When **Skill 23 (AI Workforce Blueprint)** builds a
> Communications / Sales / Customer-Support department, its closeout hands off here to scaffold these
> automations (ENFORCED via Skill 23's `commsAutomationStatus` state field + `[COMMS-AUTOMATION-RESUME]`
> gate in its `resume-workforce-build.sh`). If you were invoked off a `[COMMS-AUTOMATION-RESUME]` ping,
> build the trinity for the appointment-booking starter + the department-matched scenario, then run
> `qc-trinity-registry.sh`. See `23-ai-workforce-blueprint/INSTRUCTIONS.md → "Moment 3.8"`.

### The 3-PART build — every time, no exceptions

Every "build me a conversation playbook" request produces all three of these. Do not skip a part; do not
collapse them. They map onto the historical 3-layer architecture (Layer 0/1/2) but the operator-facing
contract is the THREE PARTS below:

| Part | Name | What it produces | Where it goes |
|---|---|---|---|
| **Part 1** | **Workflow AI instruction set** (the Build-with-AI prompt) | (a) the AI prompt, (b) a manual-build fallback, (c) a verification checklist | `conversation-workflows/<id>--workflow-ai-prompt.md` + `<id>--verification-checklist.md` |
| **Part 2** | **The conversation playbook itself** (Layer 2 markdown) | the agent's behavior once the conversation lands | `conversation-workflows/<id>.md`, registered in `conversation-workflows/registry.md` |
| **Part 3** | **The brainstorm trigger** | the trigger-word offer (first build) + the "I Do / You Do" overview + the friendly, proactive Q&A that KICKS OFF Parts 1 + 2 | runtime behavior wired into AGENTS.md Step 1.85 (see Section J) |

**Part 1 — Workflow AI instruction set (the Build-with-AI prompt).**
PRIMARY JOB: get the **SHAPE** of the funnel right — trigger, if/else branches, tags, Custom Webhook
step(s). Bonus if the AI also plugs in tokens/JSON correctly, but it often **WON'T** set tokens correctly,
so the operator pastes those after. Design the prompt to nail the STRUCTURE, then explicitly tell the
operator to paste their own values (HOOKS_TOKEN, PUBLIC_HOSTNAME, etc.). Part 1 always includes:
(a) the AI prompt, (b) a **manual-build fallback** (multi-step is fine — if-scenarios, tags, multiple
webhooks), and (c) a **verification checklist** giving the exact places to click to confirm settings even
when the AI built it.

**Part 2 — The conversation playbook itself (Layer 2 markdown).**
Saved to `conversation-workflows/<id>.md` and registered in `conversation-workflows/registry.md`.
The hook path is what wires the GHL automation (Part 1) → this playbook (Part 2). That hook path is how
the two halves connect: GHL fires the Custom Webhook → OpenClaw receives it on the mapped hook path →
the agent loads this playbook.

**Part 3 — The brainstorm trigger.**
When the operator says "help me create a conversation playbook" (or close) — or says their **personal
trigger word** (offered on the FIRST build, "Alexa"/"Hey Siri" style; Section I.1a) — the agent presents the
short **"I Do / You Do"** overview (Section I.1b: who does what + a great playbook takes ~15-30 min) and then
runs a FRIENDLY proactive Q&A. Full rules in Section B, Section I, and Section J. The non-negotiable rules:
**DO NOT dump 50 questions.** USE what the agent already knows (business, products, services, calendars, who they are,
habits — from Typed Knowledge Bases (Step 9.22) + USER.md + MEMORY.md) and ask ONLY the smart gaps, like
brainstorming. Then regurgitate a **CONCISE** summary — "is this what you want to happen?" — as the final
confirmation. On YES → build Part 1 → build Part 2 → decide + write a pointer into AGENTS.md / TOOLS.md /
MEMORY.md → create a NEW Notion doc for that playbook → register it.

### How this differs from Communication Playbooks (Step 8)

These are complementary, not redundant:

- **Communication Playbook** = baseline tone/voice for a channel. One per channel. Applies to every reply on that channel.
- **Conversation Workflow** = specific scenario behavior override. Many per client. Applies only when its trigger fires (pricing inquiry, booking request, FAQ, etc.).

When a Conversation Workflow fires, the agent uses its specific instructions for that scenario's phases, while still honoring the Communication Playbook's baseline tone/signature for the channel. Both inform every reply, but at different levels of specificity.

### How the 3 PARTS map to the historical 3 layers

The 3 PARTS above are the operator-facing contract. Under the hood they are built with the 3-layer
architecture below. The mapping:

- **Part 1 (Workflow AI instruction set)** = **Layer 0 routing check** + **Layer 1 GHL side**. Layer 0
  decides whether a new GHL automation is even needed; if it is, Layer 1 produces the Build-with-AI prompt,
  the manual-build fallback, and the verification checklist.
- **Part 2 (conversation playbook)** = **Layer 2 OpenClaw side** — always built.
- **Part 3 (brainstorm trigger)** = the operator-invoked entry point (Section B + Section J) that produces
  Parts 1 and 2 in the first place.

### Three layers per Conversation Workflow

Every workflow has potentially three layers. The agent decides which layers apply for each workflow build:

**Layer 0 — Routing check (does this workflow even need new GHL setup?)**
- Does an existing GHL workflow already deliver this conversation to OpenClaw?
- If YES → only Layer 2 is needed. The OpenClaw playbook handles the scenario inside an already-routed inbound conversation. Skip Layer 1 entirely.
- If NO → Layer 1 is needed. New GHL routing must be built.

**Layer 1 — GHL Side (how the conversation gets to OpenClaw)**
- Tags the customer needs (auto-created by the agent via GHL skill — NOT manually by the operator)
- Build-with-AI prompt (generated by the agent, copy-pasteable for the operator)
- Verification checklist (brutally specific, matches what the prompt should have produced)
- Saved as separate file: `<workflow-id>--ghl-side.md`

**Layer 2 — OpenClaw Side (what the AI does once the conversation lands)**
- The conversation playbook itself (phases, edge cases, tone, success/escalation)
- Saved as: `<workflow-id>.md`

### A. Trigger phrases — how the operator invokes the builder

The operator should be able to start the workflow builder by saying ANY of these (or close variants):

- "Help me build a conversation playbook"
- "Help me build out a conversation flow"
- "Help me create a workflow"
- "Let's add a new conversation"
- "I want to build a new playbook"
- "Build me a workflow for [scenario]"
- "Add a workflow for [scenario]"

When the agent (during normal operation, post-setup) detects one of these from the operator, it kicks off the workflow-builder flow described below.

The trigger-recognition rule goes into AGENTS.md as part of Step 1.75 (the workflow check). Specifically, AGENTS.md gets a small addition that says: "If the message is from the operator AND matches workflow-builder trigger phrases, start the workflow-builder flow per conversation-workflows-protocol.md."

### B. Subagent walks the operator through INITIAL workflow creation

The subagent asks:

> "Now the most powerful feature of your AI: conversation workflows.
>
> Instead of building visual node-based workflows, you and I just TALK
> about what you want the AI to do, and I'll build the whole thing —
> the GHL routing AND the OpenClaw playbook.
>
> Let's start with your most important workflow. What's a conversation
> pattern that happens often in your business that you'd like the AI
> to handle smoothly?
>
> Examples (pick one or describe your own):
> 1. 'When a new lead asks about pricing' — AI handles pricing
>    questions, qualifies, books a discovery call
> 2. 'When a customer wants to reschedule' — AI checks calendar, offers
>    alternatives, books
> 3. 'When a customer asks about a refund' — AI gathers info, applies
>    policy, escalates if needed
> 4. 'When a lead comes in from a webinar' — AI follows up with the
>    next step in your funnel
> 5. Your own example: __________"

Once operator picks/describes a workflow, the subagent asks follow-up questions (asks conversationally — doesn't force formal answers):

1. **What's the goal?** What does success look like? (Booking? Sale? Information shared? Escalation?)
2. **Who's the customer in this scenario?** New lead? Returning? Hot prospect? Cold? Existing client?
3. **What's the customer feeling?** Curious? Frustrated? Urgent? Casual?
4. **What's the ideal outcome FOR THE CUSTOMER?** Not for you — for them. (This shapes tone.)
5. **What info does the AI need to handle this well?** (Pricing knowledge source? Calendar? Past purchases? Policy doc?)
6. **What are the edge cases?** What could go wrong?
7. **When the AI succeeds, what action should fire?** (Book, invoice, escalate, tag, send document, trigger downstream)
8. **When the AI is stuck, what's the escalation path?**

### C. Layer 0 — Routing check

After gathering the workflow's scenario details, the subagent determines whether the workflow needs new GHL routing.

**Existing routing covers it (skip Layer 1) when:**
- The workflow triggers off normal inbound channel conversations the agent already receives (SMS, email, Facebook, Instagram, etc.) AND
- No new tags are needed for the workflow to be identified AND
- The agent can recognize the workflow's scenario from message content alone (keyword/semantic matching)

**Example:** A "pricing inquiry" workflow fires when a customer texts asking about prices. The agent already receives SMS via the inbound hook. The workflow just needs Layer 2 (the playbook) — Layer 1 is skipped. The agent recognizes "pricing inquiry" semantically when reading the inbound message and applies the playbook.

**New routing needed (Layer 1 required) when:**
- The workflow triggers from a NEW source not already wired (e.g., a different Facebook page, a new ad form, a webinar platform) OR
- The workflow needs tag-based filtering (e.g., "only fire this for customers tagged `vip`") OR
- The workflow needs a different webhook trigger than "Customer Replied" (e.g., "FB Comment", "Form Submitted", "Tag Added") OR
- The workflow needs if/else branching at the GHL level before reaching OpenClaw

**The agent makes this decision and tells the operator:**

> "Layer 0 check: [Yes/No], new GHL routing is needed for this workflow.
>
> [If yes:] Here's what needs to happen:
> - [Specific reason]
> - I'll build the GHL side (tags + Build-with-AI prompt + verification checklist)
> - Then I'll build the OpenClaw playbook.
>
> [If no:] Good news — this workflow uses existing routing. I'll build
> the OpenClaw playbook only, and your existing inbound webhook will
> deliver the conversation to me."

### D. Layer 1 — GHL Side (if needed)

If Layer 1 is needed, the agent does THREE things in sequence:

#### D.1 — Auto-create required tags via the GHL skill

Per the operator's design preference (automation over operator manual steps), the agent creates tags programmatically using the GHL skill rather than telling the operator to navigate Settings → Tags.

The agent identifies what tags this workflow needs (e.g., `pricing-interest`, `discovery-scheduled`, `quoted`). For each tag, it calls the GHL skill:

```
ghl_skill.create_tag(
  location_id=<client's location ID>,
  name=<tag name>,
  color=<color, optional>
)
```

If the GHL skill doesn't expose a create_tag method (some versions only expose tag application), the agent falls back to a direct API call:

```
POST https://services.leadconnectorhq.com/locations/{locationId}/tags
Headers:
  Authorization: Bearer <GHL_PRIVATE_INTEGRATION_TOKEN>
  Version: 2021-07-28
  Content-Type: application/json
Body:
  {
    "name": "<tag name>",
    "locationId": "<location ID>"
  }
```

After creating all tags, the agent reports back to the operator:

> "✓ Created these tags in your Convert and Flow account:
>  - `pricing-interest` (ID: abc123)
>  - `discovery-scheduled` (ID: def456)
>  - `quoted` (ID: ghi789)
>
> You don't need to create them manually — they're already there."

The agent saves the tag list (names + IDs) to the workflow's `--ghl-side.md` file for reference.

#### D.2 — Generate the Build-with-AI prompt (Part 1a)

> **CRITICAL — no API, no MCP.** GHL / Convert and Flow Automations have **NO API and NO MCP** for
> building automations. The ONLY path is the **"Build with AI" button** (top-right of the Automations
> section): the operator clicks it, then pastes the prompt the agent generates here. (Future: Playwright /
> browser-control auto-paste; right now it is a manual paste.) Do NOT write code that "calls the GHL
> Automations API" — it does not exist. See `references/GHL-INBOUND-AND-PLAYBOOKS.md` §4.

The agent writes a precise prompt the operator pastes into the GHL **Build with AI** button. The prompt's
PRIMARY JOB is to get the **SHAPE** right — trigger, if/else branches, filters, tags, and the Custom
Webhook step(s). It is a BONUS if Build-with-AI also fills in the tokens/JSON correctly; it frequently
**won't** (especially the HOOKS_TOKEN header and the exact webhook URL), so the prompt's closing lines tell
the operator to paste their own values afterward. The prompt is saved as its own file:
`<MASTER_FILES_DIR>/conversation-workflows/<workflow-id>--workflow-ai-prompt.md`.

The prompt structure:

```
Build a workflow for me with these exact specifications:

TRIGGER:
- Type: [exact trigger name, e.g., "Customer Replied"]
- [Any trigger sub-options, e.g., "On Reply"]

FILTERS (in this exact order):
- Filter 1: [Field] = [Value]
- Filter 2: [Field] = [Value]
- [etc.]

ACTIONS (in this exact order):
- Action 1: Send Custom Webhook  (field-by-field — Build-with-AI fumbles these)
  - EVENT: CUSTOM
  - METHOD: POST  (from the dropdown — not GET/PUT)
  - URL: https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>  (exact — NOT the sample-url placeholder; no trailing slash; keep /hooks/)
  - AUTHORIZATION dropdown: None  (the token goes in HEADERS, NOT this dropdown — the #1 mistake)
  - HEADERS (click "Add item" for each):
    - Key: Authorization   Value: Bearer <HOOKS_TOKEN>
    - Key: Content-Type    Value: application/json
  - CONTENT-TYPE: application/json
  - RAW BODY (Raw JSON — FLAT, no nested objects, ALL 23 keys, placeholder-free messageTemplate; insert each {{…}} via the Custom Values picker):
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
      "channel": "<channel name>",
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
```

Each field is filled in with the EXACT values from the operator's setup (`PUBLIC_HOSTNAME`, `HOOK_NAME`, `HOOKS_TOKEN`, channel name, tag names from D.1). Because Build-with-AI gets the SHAPE right but often mis-sets the token/JSON, the prompt's closing line instructs the operator to confirm the webhook URL and the `Authorization: Bearer <HOOKS_TOKEN>` header by hand after it builds.

> **Standard reference.** The full field-by-field Custom Webhook spec (EVENT=CUSTOM, METHOD=POST, real
> URL, AUTHORIZATION=None, HEADERS via Add item, CONTENT-TYPE, 23-key flat RAW BODY via Custom Values
> picker) AND the multi-action teaching (if/else branches, Add-Tag, tag-check, multiple sequential
> actions) live in `references/workflow-ai-instructions-standard.md`. Use that as the authoritative
> "must-appear" checklist when generating any workflow-AI prompt — the block above is the SMS starter
> shape; the standard covers every channel + multi-action funnel.

> **⚠️ GHL HOOK STRUCTURE (owner directive — 23 keys, FLAT) — verified live on a live client (OpenClaw 2026.5.27).**
> The body MUST have **ALL 23 keys** (23 is the minimum — no stripped bodies) and be **FLAT** — no nested
> `contact:{…}` / `customer_message:{…}` (a nested body makes EVERY field arrive EMPTY at the hook, even a
> hardcoded `"channel"`). The body's `messageTemplate` VALUE MUST stay **placeholder-free** (no `{{…}}`) — if it
> carried `{{…}}` tokens, GHL would expand them as its own merge fields, fail, mangle them to `##{}##`, and the
> webhook would be Skipped ("Error while parsing the object to JSON"). Use the exact placeholder-free
> `messageTemplate` string from the 23-key body. Set `deliver:false`. Insert each `{{…}}` value via GHL's
> Custom Values picker (typed-as-text tokens send empty). See
> `references/GHL-INBOUND-AND-PLAYBOOKS.md` → **CORRECTED GHL HOOK STRUCTURE (2026-05-29)** for the full spec.

The agent then tells the operator:

> "✓ Build-with-AI prompt ready. Here's how to use it:
>
> 1. Open your Convert and Flow account
> 2. Click **Automations** on the left menu
> 3. Click the **Build with AI** button (top-right of Automations) — this
>    is the ONLY way to build a GHL automation; there is no API for it
> 4. Paste the prompt I saved at:
>    `<MASTER_FILES_DIR>/conversation-workflows/<workflow-id>--workflow-ai-prompt.md`
> 5. Let Build with AI build the structure
>
> Once it's built, come back and tell me. I'll give you a verification
> checklist — Build with AI gets the SHAPE (trigger, branches, tags,
> webhook step) right, but it often fumbles the token and the exact
> webhook URL, so you'll paste those values in yourself."

#### D.2b — Manual-build fallback (Part 1b)

If Build-with-AI is unavailable, mangles the structure beyond a quick fix, or the operator prefers to build
by hand, the agent ALSO ships a manual-build fallback in the same `--workflow-ai-prompt.md` file (under a
`## Manual-build fallback` heading). The fallback is a numbered, click-by-click build of the SAME shape —
and it is fine for the fallback to be multi-step:

- **If/else scenarios** — branch on tag, channel, or field value before the webhook step.
- **Tags** — which tags to add at which branch (names from D.1; the agent already created them).
- **Multiple webhooks** — when different branches need different hook paths (e.g. one path for booking,
  another for support), list each Custom Webhook step with its own URL + headers + body.

Each manual step names: the node type to add, the exact field values, and the connecting branch condition.
The manual fallback and the Build-with-AI prompt describe the SAME workflow — they are two routes to one
shape — so the verification checklist (D.3) validates either one.

#### D.3 — Generate the brutally-specific verification checklist (Part 1c)

The agent writes a verification checklist tailored to the EXACT specifications the prompt was supposed to produce. Saved as: `<MASTER_FILES_DIR>/conversation-workflows/<workflow-id>--verification-checklist.md`. This checklist is REQUIRED **even when Build-with-AI reports success** — it gets the shape right but silently mangles tokens, URLs, or the Authorization dropdown. The checklist gives the operator the EXACT places to click to confirm every setting, whether Build-with-AI or the manual fallback produced the workflow.

The checklist follows this pattern — every item names the specific failure mode and the specific fix:

```markdown
# Verification Checklist — <Workflow Name>

After Build with AI (or the manual build) finishes, open the workflow and
check EACH item below. If any item is wrong, the fix is listed right there.

## Trigger

- [ ] Trigger is set to EXACTLY "<exact trigger name>"
  - WRONG VALUES TO WATCH FOR: <common Build-with-AI mistakes>
  - FIX IF WRONG: Click the trigger node → change to "<exact value>"

## Filters

- [ ] Filter 1: <field> equals "<exact value>"
  - WRONG VALUES TO WATCH FOR: <variants Build-with-AI may pick>
  - FIX IF WRONG: <specific click-by-click fix>

- [ ] Filter 2: <field> equals "<exact value>"
  - WRONG VALUES TO WATCH FOR: ...
  - FIX IF WRONG: ...

## Webhook Action

- [ ] Webhook URL is EXACTLY: `https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>`
  - Common mistake: Build-with-AI adds trailing slash or wrong path
  - FIX IF WRONG: Click the webhook action → URL field → paste exact URL

- [ ] Method is POST (not GET, not PUT)
  - FIX IF WRONG: Change Method dropdown to POST

- [ ] AUTHORIZATION dropdown is set to "None" (NOT "Bearer Token" — the
       token goes in Headers, not in this dropdown — common Build-with-AI
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
  - Common Build-with-AI mistake: skips one of the 23 keys, uses wrong
    variable syntax (e.g., `{contact.id}` instead of `{{contact.id}}`),
    or inserts merge tokens into the placeholder-free `messageTemplate`.
  - FIX IF WRONG: Click Raw Body → replace entirely with the 23-key JSON above

## Publish

- [ ] Workflow status is "Published" (NOT "Draft" — Build-with-AI often
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

### E. Layer 2 — OpenClaw Side (always built)

After Layer 1 is done (or skipped per Layer 0), the agent builds the conversation playbook itself at `<MASTER_FILES_DIR>/conversation-workflows/<workflow-id>.md`. This is the **communications playbook** leg of the TRINITY — it MUST satisfy the must-appear checklist and storage rules in `references/communications-playbook-standard.md` (slug/id, owner agent id, channel, trigger phrases/intent, goal, step-by-step flow, the GHL Conversations-API reply mechanism per TOOLS.md, cross-playbook transition rules, edge cases incl. frustration/refund/legal escalation, on-success/tagging, tone, honesty floor). Save the FILE under `conversation-workflows/`, register it in `registry.md`, AND place a human-readable copy in the CLIENT's account in the order **Notion → Google Docs → plain text** (Section 4 of that standard). The template below is the canonical shape:

```markdown
# Conversation Workflow: <Workflow Name>

**Created:** <ISO date>
**Trigger:** <What activates this workflow>
**Goal:** <One sentence>
**Customer profile:** <Who this is for>
**Desired customer outcome:** <What good looks like for them>

## When to invoke this workflow

The agent triggers this workflow when:
- <Trigger condition 1>
- <Trigger condition 2>
- <Trigger keywords/semantic intent>

## What the agent does

### Phase 1 — Acknowledge and qualify
<Specific behavior — what to say, what to ask, what to listen for>

### Phase 2 — Gather context
<What info the agent needs to collect>

### Phase 3 — Deliver value
<The core of the workflow — providing the information, booking, etc.>

### Phase 4 — Close
<How the conversation ends — confirmation, follow-up scheduled, etc.>

## Information the agent needs

The agent should consult:
- <Knowledge Source 1>
- <Knowledge Source 2>

## Edge cases

### If customer asks for X
<Behavior>

### If customer becomes frustrated
<Escalate via sentiment monitoring protocol>

### If the AI can't answer with confidence
<Escalate via confidence threshold protocol>

## On success

When the workflow concludes successfully, the agent:
- <Action 1>
- <Action 2>

## On escalation

If this workflow stalls or hits an edge case the agent can't handle:
- Escalate to: <operator | specific team member | route via notification protocol>
- Include in escalation: <what context to surface>

## Tone

<Specific tone guidance for THIS workflow, on top of channel Communication Playbook>

## Example conversation

(Optional but powerful)

> Customer: "Hey, just wondering about your prices?"
> Agent: "Great question — happy to walk you through it. Quick thing
> first: are you looking at this for yourself, or for a team?"
> ...

## Trigger keywords / intent signals

The agent recognizes this workflow's trigger when the inbound message
contains:
- <keyword/phrase 1>
- <keyword/phrase 2>
- Or matches semantic intent: <description>

## Linked GHL routing (Layer 1)

- GHL routing built: [yes | no — uses existing inbound routing]
- If yes:
  - Tags created: <list with IDs>
  - Build-with-AI prompt file: <path>
  - Verification checklist file: <path>
```

### F. Registry and AGENTS.md insertion

The agent maintains a registry at `<MASTER_FILES_DIR>/conversation-workflows/registry.md`:

```markdown
# Conversation Workflows Registry

| ID | Name | Trigger summary | Layer 1? | OpenClaw playbook | GHL prompt | Verification checklist | Doc (Notion/Docs/text) |
|---|---|---|---|---|---|---|---|
| pricing-inquiry | New lead asks about pricing | "price", "cost", "how much" | No (uses existing inbound) | pricing-inquiry.md | n/a | n/a | https://www.notion.so/client/pricing-inquiry-abc123 |
| webinar-followup | Lead from Tuesday webinar | New tag `webinar-attendee` | Yes | webinar-followup.md | webinar-followup--workflow-ai-prompt.md | webinar-followup--verification-checklist.md | https://docs.google.com/document/d/xyz/edit |
| ... | ... | ... | ... | ... | ... | ... | ... |
```

The registry is the single source of truth the agent reads on every reply turn (via AGENTS.md Step 1.75)
to decide which workflow (if any) applies. AGENTS.md **Step 1.85** (see Section A + Section J) recognizes
the operator-side workflow-builder trigger phrases and starts the builder flow.

**The `Doc (Notion/Docs/text)` column is MANDATORY and machine-enforced.** Every registered playbook MUST
carry a recorded human-facing doc — a Notion URL, a Google Docs URL, or a `.md`/`.txt` path the client can
reach — created in the client's OWN account in the fallback order Notion → Google Docs → plain-text (see
`references/communications-playbook-standard.md` §4). A row whose doc cell is empty / `n/a` / a placeholder
FAILS `scripts/qc-playbook-doc.sh` (wired into `scripts/11-run-qc-checklist.sh` + CI `qc-static.yml`); the
install is NOT complete until the doc is created and its URL/path recorded here. The installer
`scripts/09-install-conversation-workflows.sh` creates + records this doc automatically for every on-disk
playbook. This is NOT optional prose — it is a gated deliverable, like the send-directive and
conversation-memory gates.

**How Parts 1 and 2 connect (the hook path).** The registry's `GHL prompt` column points at the Part 1
artifact; the `OpenClaw playbook` column points at the Part 2 artifact. The thing that physically links
them at runtime is the **hook path**: the GHL automation's Custom Webhook (Part 1) POSTs to
`https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>`; OpenClaw's `hooks.mappings` maps that path to a session; the
agent then loads the matching Part 2 playbook from the registry. Record the hook path in the Reusable Tunnel
Values hook-path registry (see `references/GHL-INBOUND-AND-PLAYBOOKS.md` §6) so the GHL side and the
OpenClaw side never drift apart.

### G. Initial workflow creation during setup

The subagent walks the operator through 3-5 starter workflows during install. Recommended starters:

1. **Pricing inquiry** — handles pricing questions, qualifies, offers next step
2. **Booking / rescheduling** — uses Smart Booking (Step 9.19)
3. **General FAQ** — uses Knowledge Sources (Step 9.14) to answer common questions
4. **Onboarding new customer** — welcome flow after they sign up
5. **Win-back for cold leads** — re-engagement when a long-dormant contact reaches out

The subagent asks:

> "Want to build a starter workflow now, or come back to it later?
> Recommended starters: pricing, booking, FAQ, onboarding, win-back.
> Aim for 3-5 during setup. You can add more anytime."

Loop until operator is done.

### H. Append to Run Manifest

```markdown
## Step 9.20 — Conversation Workflow Builder (3-Layer)

Workflows created during setup:
- <workflow-1-id>: <name>
  - Layer 0: <existing routing | new routing required>
  - Layer 1: [tags created: <list> | Build-with-AI prompt: <path> | verification checklist: <path>] (or "skipped")
  - Layer 2: <path to OpenClaw playbook>
  - Human-facing doc (Notion → Google Docs → text): <recorded URL or path>  ← MANDATORY, gated by qc-playbook-doc.sh
- ...

Registry: <MASTER_FILES_DIR>/conversation-workflows/registry.md
AGENTS.md Step 1.75: includes workflow check on every reply turn AND
operator-side workflow-builder trigger-phrase recognition.

CRITICAL: Workflow content stays in conversation-workflows/ folder. Only
the AGENTS.md Step 1.75 instruction + registry pointer reach the
bootstrap layer. MEMORY.md, AGENTS.md, TOOLS.md are NOT bloated.

GHL design principle: smaller workflows beat massive workflows. The agent
split layered work across multiple focused GHL workflows where applicable
(per MEMORY.md Design Principle Rule 1, seeded in O.7).
```

---

### I. Part 3 — The brainstorm trigger (the recurring "build me a playbook" flow)

This is the operator-invoked entry point that, post-setup, produces a NEW conversation playbook on demand.
It is what makes the system **communication-driven**: the operator BRAINSTORMS the funnel into existence
instead of dragging nodes.

#### I.1 — Recognize the trigger

When the operator (NOT a customer) says any of these or a close variant, start the brainstorm flow
(the recognition rule lives in AGENTS.md Step 1.85 — see Section A):

- "Help me create a conversation playbook"
- "Help me build a conversation playbook / workflow / flow"
- "Let's build a funnel for <X>"
- "I want a workflow that does <X>"
- "Build me a playbook for <X>"
- "Help me build a [purpose] playbook" (the client-facing phrasing taught in the reference sheet)

#### I.1a — Offer a PERSONAL TRIGGER WORD (on the client's FIRST playbook build)

The VERY FIRST time a client asks to build a communication playbook (or hits the proactive
brainstorm trigger in Step 9.34), and BEFORE diving into the brainstorm, the agent OFFERS to set a
**personal trigger word** — a word or short phrase that instantly tells the AI the client wants to
build a playbook. Frame it exactly the way people already understand wake words:

> "Quick thing before we start — want to set a personal **trigger word** for this? It works just like
> **"Alexa"** or **"Hey Siri"**: a word or short phrase that instantly tells me you want to build a
> communication playbook, so you never have to explain it. A lot of people use something fun like
> **"Playbook time!"** — what would you like yours to be? (Totally optional — you can always just say
> *"Help me build a [purpose] playbook"*.)"

Then:

1. **Ask for it.** Let the client pick anything memorable ("Playbook time!", "Build mode", "New funnel", etc.).
2. **Confirm it back.** Play it back so they know it's set: *"Got it — from now on, whenever you say
   **"<trigger word>"**, I'll know you want to build a communication playbook and I'll kick this off."*
3. **REMEMBER it (persist it).** Store the trigger word so future builds recognize it — write it to the
   client's **`USER.md`** (the durable who-they-are/preferences file) AND record it in the playbook
   config at `<MASTER_FILES_DIR>/conversation-workflows/registry.md` (a small `<!-- trigger-word: "<phrase>" -->`
   header comment at the top of the registry, or a `Trigger word:` line in the run manifest). It is a
   durable preference, so the natural home is `USER.md`; the registry copy keeps it next to the playbooks
   it triggers. **Never co-mingle clients** — the trigger word lives in THAT client's own workspace files.
4. **On every LATER build, recognize it.** AGENTS.md Step 1.85 (Section J) reads the stored trigger word
   on each operator turn; when the client says their trigger word, the agent treats it exactly like the
   Section I.1 trigger phrases and starts THIS flow. (The standard "Help me build a [purpose] playbook"
   phrasing always works too — the trigger word is an additional, personalized shortcut, never a
   replacement.)

If the client declines, that's fine — note it and move on; the standard trigger phrases still work.

#### I.1b — Present the "I Do / You Do" process (so the client knows responsibilities + timing)

When a build actually starts, the agent presents a short **"I Do / You Do"** overview FIRST, so the
client knows what to expect, who does what, and that **a good playbook takes about 15-30 minutes** to get
right (it is a collaboration, not an instant button). Keep it friendly and brief — this is orientation,
not a contract:

> "Here's how we'll build this together — it usually takes about **15-30 minutes** to get a great one:
>
> 1. **YOU** — trigger it (your trigger word, or *"Help me build a [purpose] playbook"*).
> 2. **I (your AI) DO** — ask you a few quick brainstorm questions, using what I already know about your
>    business (NOT a 50-question interrogation).
> 3. **YOU** — answer them (goal, audience, channel, offer, tone).
> 4. **I DO** — draft the full playbook + conversation flow for your approval.
> 5. **YOU** — review it and tell me any tweaks.
> 6. **I DO** — finalize it, store it (your `conversation-workflows/` folder, mirrored to Notion), and
>    build the matching **Workflow AI prompt** wired to your Convert and Flow account.
> 7. **I DO** — wire the actions: create tags, update your calendar, create/book appointments.
> 8. **YOU** — approve, and we go live."

This sets the expectation (collaboration + ~15-30 min) and maps cleanly onto I.2 (the brainstorm) → I.3
(the build/store/register sequence). Don't recite it verbatim every time once a client knows the rhythm;
always present it on a client's FIRST build.

#### I.2 — Friendly proactive Q&A — DO NOT dump 50 questions

This is the single most important rule of Part 3. **The agent runs a FRIENDLY, brainstorm-style Q&A — it
does NOT interrogate the operator with a wall of questions.** Before asking anything, the agent LOADS what
it already knows about the business and asks ONLY the smart gaps:

1. **Pull existing context first.** Read, in this order:
   - Typed Knowledge Bases (Step 9.22) — products, services, pricing, policies, FAQs already captured
   - `USER.md` — who the operator is, their preferences, their voice
   - `MEMORY.md` — habits, prior decisions, design rules, established facts
   - existing entries in `conversation-workflows/registry.md` — so it doesn't rebuild something that exists
   - calendars / Smart Booking config (Step 9.19) if the scenario is booking-shaped

2. **Ask ONLY the gaps.** If the agent already knows the product, the price, the calendar, and the brand
   voice, it does NOT ask about them again. It asks the 2-5 things it genuinely cannot infer — e.g.
   "When this fires, do you want me to book straight into your discovery calendar, or qualify budget
   first?" Treat it like brainstorming with a smart colleague who already knows the business, not like a
   form. (This is the explicit anti-pattern: never fire all 8 of Section B's questions verbatim when the
   answers are already in the Knowledge Bases.)

   **The agent's JOB here is to BRAINSTORM with the client to land the PERFECT playbook** — not to extract
   a form. Frame the gaps you ask around the **things to think about**, and reassure the client that
   uncertainty is fine because that is literally what the brainstorm is for. The things to think about:
   - **The goal** — what should this playbook accomplish? (book a call / recover a sale / get a review /
     answer an FAQ — pick the ONE primary win.)
   - **Who it's for** — the audience (new lead, returning customer, hot prospect, cold/dormant, existing client).
   - **The channel(s)** — where it runs (SMS, email, Facebook/Instagram DM, WhatsApp, Live Chat).
   - **The offer / hook** — what's the pitch, the value, or the reason they'll respond?
   - **The tone / brand voice** — how it should sound (layered on top of the channel's baseline voice).
   - **Timing & follow-up cadence** — when it fires and how persistently it follows up (e.g. the
     intelligent-followup touchpoints, quiet hours).
   - **The "win" action** — what fires on success: booked / replied / tagged / purchased.

   Always reassure: *"If you're not sure about any of these, that's exactly what I'm here to brainstorm —
   we'll figure it out together."* The agent only asks the things it genuinely cannot infer from the
   Knowledge Bases / USER.md / MEMORY.md; the list above is the brainstorm's COMPASS, not a questionnaire to read aloud.

3. **Regurgitate a CONCISE summary and ask for confirmation.** Before building anything, the agent plays
   back a short, plain-language summary — NOT the full spec — and asks:

   > "Here's what I think you want to happen:
   > • When **<trigger>**, I'll **<action>**, then **<next action>**, and if **<edge case>** I'll **<escalate/branch>**.
   > Is this what you want to happen?"

   Keep it to a few bullets. The operator says YES, tweaks it, or says no.

#### I.3 — On YES, execute in this exact order

1. **Build Part 1** — the Workflow AI instruction set: Layer 0 routing check → (if needed) the
   Build-with-AI prompt (D.2) + manual-build fallback (D.2b) + verification checklist (D.3).
2. **Build Part 2** — the conversation playbook (Section E) at `conversation-workflows/<id>.md`.
3. **Decide + write the pointer.** Decide which bootstrap file should point at the new playbook and write
   a ONE-LINE pointer there — NOT the whole playbook (keep the bootstrap layer un-bloated):
   - **AGENTS.md** — if it changes runtime routing behavior (new trigger the agent must recognize).
   - **TOOLS.md** — if it introduces a new tool/hook path / Reusable Tunnel Values hook entry.
   - **MEMORY.md** — if it establishes a durable business rule the agent must always remember.
   (Most playbooks need only the registry entry + the existing Step 1.75 read. Add a bootstrap pointer
   ONLY when one of the three conditions above is genuinely met.)
4. **Create the human-facing doc for that playbook in the CLIENT's account — MANDATORY, GATED (Notion →
   Google Docs → plain-text).** Create a human-readable copy in the CLIENT's OWN account (never co-mingle
   with another client's workspace), in this EXACT fallback order: **(a) Notion** (a new subpage under the
   client's designated parent page), **(b) if no Notion → Google Docs**, **(c) if neither → a plain-text
   `.md` the client can access**. The doc mirrors the Part 2 playbook plus the Part 1 prompt + verification
   checklist. **This is NOT optional prose — it is machine-enforced by `scripts/qc-playbook-doc.sh`**: the
   playbook is INCOMPLETE (do NOT declare it live) until this doc exists and its URL/path is recorded in the
   registry's `Doc (Notion/Docs/text)` column (step 5) and the run manifest. The installer
   `scripts/09-install-conversation-workflows.sh` performs this fallback + recording automatically for
   on-disk playbooks; a doc that fails to create is RETRIED (verify/resume), never silently skipped.
5. **Register it (with the recorded doc URL/path)** — add the row to `conversation-workflows/registry.md`
   (Section F) INCLUDING the `Doc (Notion/Docs/text)` cell from step 4, and add the hook-path entry to
   Reusable Tunnel Values (`references/GHL-INBOUND-AND-PLAYBOOKS.md` §6) if Part 1 created a new hook path.

### J. AGENTS.md Step 1.85 — the runtime hook for Part 3

Step 1.85 (installed by `scripts/05-update-agents-md.sh`, marker `STEP_1_85_WORKFLOW_BUILDER_TRIGGERS`)
is what makes Part 3 fire at runtime. It recognizes the operator-side trigger phrases (I.1) **AND the
client's stored personal trigger word (I.1a)** and hands control to this protocol's brainstorm flow
(Section I). On each operator turn it reads the stored trigger word (from `USER.md` / the
`conversation-workflows/registry.md` `trigger-word` header) and, if the message matches it, kicks off the
flow exactly as a Section I.1 phrase would. On a client's FIRST build it OFFERS the trigger word (I.1a) and
presents the "I Do / You Do" overview (I.1b) before the brainstorm. Confirm the full 3-PART build completed
— Part 1 (prompt + fallback + checklist), Part 2 (playbook + registry), Part 3 (trigger-word offer on first
build → "I Do / You Do" overview → brainstorm → concise confirmation → human-facing doc) — before declaring
the playbook live. The human-facing doc (Notion → Google Docs → text, §I.3 step 4) is MANDATORY and
machine-enforced by `scripts/qc-playbook-doc.sh`: a playbook with no recorded doc URL/path in its registry
row is NOT live.

### K. Cross-references — builder ↔ router ↔ proactive engine

The Conversation Playbook Builder does not stand alone. It is one corner of a triangle:

- **Step 9.20 (this protocol) — the BUILDER.** Operator-invoked. Brainstorms ONE playbook into existence
  (Parts 1-3).
- **Step 9.33 — Intelligent Playbook Routing** (`intelligent-routing-protocol.md`). Runtime, cross-playbook
  TRANSITIONS: a customer who starts in one playbook can be moved to another based on their responses. The
  agent detects the topic shift after every customer message, caps at **max 3 switches** per conversation,
  and uses **soft transition** phrasing ("Sounds like this is more about X now — let me switch gears").
  Every playbook the BUILDER creates becomes a routable destination the ROUTER can switch into.
- **Step 9.34 — Proactive Features Suite** (`proactive-suggestions-protocol.md`). The pattern-based engine:
  sub-feature 34.1 watches for "I've seen N customers ask about X with no playbook — want one?" and, on
  YES, drafts a new playbook *via this very builder* (Step 9.20) into `conversation-workflows/drafts/`.

So the flow is circular: the **proactive engine (9.34)** notices a gap and proposes a build → the
**builder (9.20)** creates the playbook → the **router (9.33)** transitions live conversations into it.
When editing any one of the three, check the other two for consistency.

### L. Mac env note (where keys live)

When the brainstorm flow (or any Part 1/Part 2 step) needs a secret (HOOKS_TOKEN, GHL PIT, etc.) on a
**Mac** install, the keys live in **`~/clawd/secrets/.env`** AND/OR **`~/.openclaw/.env`** — check BOTH
before claiming a key is missing. This differs from a VPS (Docker) install, where env lives in
`/docker/<project>/.env`. See Step O.5 and `references/GHL-INBOUND-AND-PLAYBOOKS.md` §1 for the full
token map. Never tell the operator a key is missing without first checking both Mac locations.
