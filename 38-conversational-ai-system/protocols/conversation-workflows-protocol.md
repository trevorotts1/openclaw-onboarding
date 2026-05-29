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

### The 3-PART build — every time, no exceptions

Every "build me a conversation playbook" request produces all three of these. Do not skip a part; do not
collapse them. They map onto the historical 3-layer architecture (Layer 0/1/2) but the operator-facing
contract is the THREE PARTS below:

| Part | Name | What it produces | Where it goes |
|---|---|---|---|
| **Part 1** | **Workflow AI instruction set** (the Build-with-AI prompt) | (a) the AI prompt, (b) a manual-build fallback, (c) a verification checklist | `conversation-workflows/<id>--workflow-ai-prompt.md` + `<id>--verification-checklist.md` |
| **Part 2** | **The conversation playbook itself** (Layer 2 markdown) | the agent's behavior once the conversation lands | `conversation-workflows/<id>.md`, registered in `conversation-workflows/registry.md` |
| **Part 3** | **The brainstorm trigger** | the friendly, proactive Q&A that KICKS OFF Parts 1 + 2 | runtime behavior wired into AGENTS.md Step 1.85 (see Section J) |

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
When the operator says "help me create a conversation playbook" (or close), the agent runs a FRIENDLY
proactive Q&A. Full rules in Section B and Section J. The non-negotiable rules: **DO NOT dump 50
questions.** USE what the agent already knows (business, products, services, calendars, who they are,
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

Per Christy's design preference (automation over operator manual steps), the agent creates tags programmatically using the GHL skill rather than telling the operator to navigate Settings → Tags.

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
- Action 1: [e.g., "Send Custom Webhook"]
  - URL: https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>
  - Method: POST
  - Headers:
    - Authorization: Bearer <HOOKS_TOKEN>
    - Content-Type: application/json
  - Body (Raw JSON):
    {
      "channel": "<channel name>",
      "contact": {
        "id": "{{contact.id}}",
        "first_name": "{{contact.first_name}}",
        "last_name": "{{contact.last_name}}",
        "email": "{{contact.email}}",
        "phone": "{{contact.phone}}",
        "tags": "{{contact.tags}}"
      },
      "location": {
        "id": "{{location.id}}",
        "name": "{{location.name}}"
      },
      "customer_message": {
        "body": "{{message.body}}",
        "subject": "{{message.subject}}"
      },
      "workflow_id": "<workflow-id>"
    }

PUBLISH: Yes, publish the workflow when done — don't leave it as draft.
```

Each field is filled in with the EXACT values from the operator's setup (`PUBLIC_HOSTNAME`, `HOOK_NAME`, `HOOKS_TOKEN`, channel name, tag names from D.1). Because Build-with-AI gets the SHAPE right but often mis-sets the token/JSON, the prompt's closing line instructs the operator to confirm the webhook URL and the `Authorization: Bearer <HOOKS_TOKEN>` header by hand after it builds.

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

- [ ] Raw Body matches the JSON below EXACTLY (whitespace doesn't
       matter, but every field, every quote, every brace must match):

```json
{
  "channel": "<channel>",
  ... [full body from D.2 prompt] ...
}
```
  - Common Build-with-AI mistake: skips fields, uses wrong variable
    syntax (e.g., `{contact.id}` instead of `{{contact.id}}`)
  - FIX IF WRONG: Click Raw Body → replace entirely with the JSON above

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

After Layer 1 is done (or skipped per Layer 0), the agent builds the conversation playbook itself at `<MASTER_FILES_DIR>/conversation-workflows/<workflow-id>.md`:

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

| ID | Name | Trigger summary | Layer 1? | OpenClaw playbook | GHL prompt | Verification checklist |
|---|---|---|---|---|---|---|
| pricing-inquiry | New lead asks about pricing | "price", "cost", "how much" | No (uses existing inbound) | pricing-inquiry.md | n/a | n/a |
| webinar-followup | Lead from Tuesday webinar | New tag `webinar-attendee` | Yes | webinar-followup.md | webinar-followup--workflow-ai-prompt.md | webinar-followup--verification-checklist.md |
| ... | ... | ... | ... | ... | ... | ... |
```

The registry is the single source of truth the agent reads on every reply turn (via AGENTS.md Step 1.75)
to decide which workflow (if any) applies. AGENTS.md **Step 1.85** (see Section A + Section J) recognizes
the operator-side workflow-builder trigger phrases and starts the builder flow.

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
4. **Create a NEW Notion doc for that playbook** — in the CLIENT's own Notion workspace (never co-mingle
   with another client's workspace). The Notion doc mirrors the Part 2 playbook plus the Part 1 prompt +
   verification checklist so the operator has a shareable, human-readable copy.
5. **Register it** — add the row to `conversation-workflows/registry.md` (Section F), and add the hook-path
   entry to Reusable Tunnel Values (`references/GHL-INBOUND-AND-PLAYBOOKS.md` §6) if Part 1 created a new
   hook path.

### J. AGENTS.md Step 1.85 — the runtime hook for Part 3

Step 1.85 (installed by `scripts/05-update-agents-md.sh`, marker `STEP_1_85_WORKFLOW_BUILDER_TRIGGERS`)
is what makes Part 3 fire at runtime. It recognizes the operator-side trigger phrases (I.1) and hands
control to this protocol's brainstorm flow (Section I). Confirm the full 3-PART build completed — Part 1
(prompt + fallback + checklist), Part 2 (playbook + registry), Part 3 (brainstorm → concise confirmation →
Notion doc) — before declaring the playbook live.

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
