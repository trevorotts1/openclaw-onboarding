<!-- OPERATOR HEADER -->
<!-- Skill 38 reference/protocol doc — the COMMUNICATIONS PLAYBOOK STANDARD. -->
<!-- Full content lives here (not in AGENTS.md/TOOLS.md — those get a 1-2 line pointer only). -->
<!-- Added 2026-05-29 by skill38-comms-and-workflowai-standards. -->

# Communications Playbook Standard (Skill 38)

A **communications playbook** (a.k.a. conversation playbook / conversation workflow Layer 2)
is the markdown document that tells the agent HOW to behave once a specific conversation lands —
the phases, edge cases, tone, success action, and escalation path for one scenario. This file is
the **single standard** for what every communications playbook must contain, where it is stored,
and the order in which a human-readable copy is placed in the client's account.

> This standard is part of THE TRINITY. A communications playbook never travels alone — see
> `protocols/conversation-workflows-protocol.md` Section "THE TRINITY". If you author a
> communications playbook you MUST also create (or confirm) its matching **workflow-AI prompt** and
> its **GHL workflow/automation**. One implies the other two.

---

## 1. Standardized format

Every communications playbook uses the canonical Layer-2 template in
`protocols/conversation-workflows-protocol.md` Section E (`# Conversation Workflow: <Name>`).
Do not invent a new shape per client — fill that template. The sections below are the
**must-appear checklist** that template satisfies.

## 2. MUST-APPEAR checklist — every communications playbook

A playbook is INCOMPLETE (do not register it, do not declare it live) until ALL of these are present:

- [ ] **`slug` / `id`** — the kebab-case workflow id (matches the filename `conversation-workflows/<id>.md` and the registry row).
- [ ] **Owner agent id** — which agent runs this playbook (e.g. `main`, `sales`). Matches the workflow-AI prompt's `agent_id`.
- [ ] **Channel** — sms / email / facebook / instagram / gmb / gbp / whatsapp / conversations.
- [ ] **Trigger phrases / intent** — the keywords + semantic intent that activate this playbook (the "When to invoke" + "Trigger keywords / intent signals" sections).
- [ ] **Goal** — one sentence: what success looks like for this scenario.
- [ ] **Step-by-step flow** — the phases (acknowledge/qualify → gather → deliver value → close), each with concrete behavior.
- [ ] **GHL reply mechanism + MANDATORY SEND-DIRECTIVE** — an explicit statement that the agent replies via the **GHL Conversations API per TOOLS.md** (never post directly to the GHL API; use the installed GHL skill, which handles auth/rate-limits/retries), AND that **SENDING is mandatory**: drafting/composing is NOT sending — the agent must actually call the Conversations API and must NOT end its turn until a messageId/conversationId is returned. The hook's SERVER-mapping `messageTemplate` carries this send-directive (verify with `scripts/qc-send-directive.sh`); the in-GHL-body `messageTemplate` stays placeholder-free. See `references/GHL-INBOUND-AND-PLAYBOOKS.md` §4.
- [ ] **CONVERSATION MEMORY — read-before / append-after** — an explicit statement that GHL inbound hook sessions are **single-turn / stateless**, so the agent's only memory of a contact across messages is that contact's conversation log (`<MASTER_FILES_DIR>/conversational-logs/<contact_id>__<name>.md`). The playbook must say: READ the log BEFORE drafting (recover prior conversation + any in-progress booking/topic and CONTINUE it; if missing, treat as new), and APPEND the inbound + reply to the log AFTER sending (create if missing). A reply that ignores or fails to update the log is a failure. The hook's SERVER-mapping `messageTemplate` carries these steps (verify with `scripts/qc-conversation-memory.sh`); the dir is created + made writable by Step 9 (`scripts/09-install-conversation-workflows.sh`). See `references/GHL-INBOUND-AND-PLAYBOOKS.md` §4b + AGENTS.md Conversation Memory Protocol.
- [ ] **Cross-playbook transition rules** — when this playbook should hand off to another playbook (per the Intelligent Playbook Routing protocol: max 3 switches/conversation, soft transition phrasing). Name the destination playbooks.
- [ ] **Edge cases** — at minimum: frustration (→ sentiment-monitoring escalation), refund request (→ honesty floor, no promises without operator approval), legal threat / "speak to a human" (→ NEEDS_HUMAN escalation). Add scenario-specific edge cases too.
- [ ] **On-success / tagging** — the action that fires on success (book / invoice / tag / send document / trigger downstream) and which tag(s) get applied (tags must be created via the GHL skill FIRST — see the workflow-AI standard).
- [ ] **Tone** — the specific tone for THIS scenario, layered on top of the channel communication playbook's baseline voice.
- [ ] **Honesty floor** — the agent never invents discount codes, never promises refunds/exceptions without operator approval, never bluffs below the confidence threshold, escalates instead.

## 3. STORAGE — where the playbook FILE lives (master-files folder)

The playbook markdown file is ALWAYS saved in the OpenClaw master-files folder under the existing
`conversation-workflows/` directory (the repo's "communications playbooks" folder):

- Playbook (Layer 2): `<MASTER_FILES_DIR>/conversation-workflows/<id>.md`
- GHL/workflow-AI prompt (Layer 1, Part 1): `<MASTER_FILES_DIR>/conversation-workflows/<id>--workflow-ai-prompt.md`
- Verification checklist: `<MASTER_FILES_DIR>/conversation-workflows/<id>--verification-checklist.md`
- (If new GHL routing was built) GHL side notes: `<MASTER_FILES_DIR>/conversation-workflows/<id>--ghl-side.md`

Then **register** it in `<MASTER_FILES_DIR>/conversation-workflows/registry.md` (the single source of
truth the agent reads on every reply turn via AGENTS.md Step 1.8/1.75). A playbook that exists on disk
but is NOT in the registry is invisible to the runtime — registration is mandatory.

> CORE-MD RULE: AGENTS.md / TOOLS.md get only a **1-2 line pointer** (what the playbook is + its file
> path). The playbook BODY never goes into a core md file — that bloats the bootstrap layer. The
> registry + the existing Step 1.8/1.75 read are how the runtime finds it.

## 4. STORAGE ORDER — the human-readable copy in the CLIENT's account (fallback chain)

In ADDITION to the master-files file above, every new communications playbook gets a human-readable
copy placed in the CLIENT's own account so the operator has a shareable, editable record. Place it in
this EXACT fallback order (never co-mingle clients — always the client's OWN workspace):

1. **(a) The client's Notion account first.** If the client has a Notion workspace connected, create a
   new Notion doc in THAT client's workspace (never a generic/operator or another client's workspace).
   The Notion doc mirrors the playbook body + the workflow-AI prompt + the verification checklist.
2. **(b) If no Notion → the client's Google Docs.** If there is no Notion workspace, create a Google Doc
   in the client's own Google Drive (per the Google Workspace integration / TOOLS.md helper).
3. **(c) If no Google Docs → a plain text document the client can access later.** If neither Notion nor
   Google Docs is available, write a plain `.txt` / `.md` file to a location the client can reach
   (e.g. their master-files folder root or an agreed shared path) and tell the operator exactly where it is.

Always in that order: Notion → Google Docs → plain text. Record which destination was used in the
playbook's registry row / run manifest so it is auditable.

## 5. Distinction — communications playbook vs channel communication playbook

These are complementary, not redundant:

- **Channel communication playbook** = baseline tone/voice for ONE channel (one per channel), in
  `<MASTER_FILES_DIR>/communication-playbooks/` (template: `templates/channel-playbook-template.md`).
  Applies to EVERY reply on that channel.
- **Communications playbook (this standard)** = a specific SCENARIO override (many per client), in
  `<MASTER_FILES_DIR>/conversation-workflows/`. Applies only when its trigger fires.

When a communications playbook fires, the agent uses its scenario instructions while still honoring the
channel communication playbook's baseline tone/signature.

## 6. Build sequence

Author the communications playbook via the Conversation Playbook Builder (Step 9.20,
`protocols/conversation-workflows-protocol.md`). The brainstorm flow gathers the gaps, you confirm a
concise summary, then you build the TRINITY (Part 1 workflow-AI prompt + Part 2 this playbook + the
GHL workflow), register it, and place the human-readable copy per the storage order in Section 4.
