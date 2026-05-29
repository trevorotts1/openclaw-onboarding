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
- [ ] **HUMAN-FACING DOC created in the CLIENT's account + URL recorded (MANDATORY, machine-enforced)** — a human-readable copy of this playbook MUST be created in the client's OWN account in the fallback order **Notion → Google Docs → plain-text** (Section 4), and its URL/path MUST be recorded in the playbook's `registry.md` row (the `Doc (Notion/Docs/text)` column) and the run manifest. A playbook with no recorded human-facing doc is INCOMPLETE — the customer is left with no shareable reference of what was set up. **This item is MACHINE-ENFORCED by `scripts/qc-playbook-doc.sh`** (wired into `scripts/11-run-qc-checklist.sh` + CI `.github/workflows/qc-static.yml`): the gate FAILs (exit 1) any registered playbook whose doc cell is empty / `n/a` / placeholder, and exits 2 (never a blind PASS) if no playbooks exist. The installer `scripts/09-install-conversation-workflows.sh` creates + records this doc automatically for every on-disk playbook (Notion → Google Docs → text). It is no longer optional prose.

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

## 4. STORAGE ORDER — the human-readable copy in the CLIENT's account (fallback chain) — MANDATORY, MACHINE-ENFORCED

In ADDITION to the master-files file above, every new communications playbook gets a human-readable
copy placed in the CLIENT's own account so the operator has a shareable, editable record. **This is a
MANDATORY deliverable, not optional prose** — it is the deliverable an agent skipped on a live client
(files scaffolded locally, install reported "clean," but no client doc), leaving the customer stranded
with no human-facing reference. It is now machine-enforced exactly like the send-directive and
conversation-memory gates. Place it in this EXACT fallback order (never co-mingle clients — always the
client's OWN workspace):

1. **(a) The client's Notion account first.** If the client has a Notion workspace connected, create a
   new Notion doc in THAT client's workspace (never a generic/operator or another client's workspace).
   The Notion doc mirrors the playbook body + the workflow-AI prompt + the verification checklist.
2. **(b) If no Notion → the client's Google Docs.** If there is no Notion workspace, create a Google Doc
   in the client's own Google Drive (per the Google Workspace integration / TOOLS.md helper).
3. **(c) If no Google Docs → a plain text document the client can access later.** If neither Notion nor
   Google Docs is available, write a plain `.txt` / `.md` file to a location the client can reach
   (e.g. their master-files folder root or an agreed shared path) and tell the operator exactly where it is.

Always in that order: Notion → Google Docs → plain text. **Record the resulting URL/path** in the
playbook's `registry.md` row — the `Doc (Notion/Docs/text)` column (Section §F of
`protocols/conversation-workflows-protocol.md`) — AND in the run manifest, so it is auditable.

**ENFORCEMENT (un-skippable).** This step is gated three ways, mirroring the send-directive /
conversation-memory enforcement:
- **Installer action** — `scripts/09-install-conversation-workflows.sh` runs the Notion → Google Docs →
  plain-text fallback for every on-disk playbook that has no recorded doc, records the URL/path into the
  registry's doc column, and emits a clear operator-facing line stating WHERE the doc was created (or which
  fallback was used). For Notion it creates a subpage under the client's designated parent page via
  `NOTION_API_KEY` (the integration must be shared with that parent; set `NOTION_PARENT_PAGE_ID` or
  `NOTION_PARENT_SEARCH`). If the key/parent is missing or Notion errors, it falls to Google Docs, then to a
  plain-text `.md` in `<MASTER_FILES_DIR>/playbook-docs/`.
- **QC gate** — `scripts/qc-playbook-doc.sh` FAILs (exit 1) if any registered playbook has no recorded doc,
  PASSes (exit 0) when all do, and exits 2 (never a blind PASS) if no playbooks exist. Wired into
  `scripts/11-run-qc-checklist.sh` and CI `.github/workflows/qc-static.yml` (via its fixture test
  `qc-playbook-doc.test.sh`).
- **Binding install step** — the install is NOT complete until the doc URL/path is recorded; an incomplete
  doc is retried by the installer's verify/resume loop, not silently skipped.

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

## 7. CLIENT REFERENCE SHEET — bearer token + copyable GHL Raw Body are MANDATORY (machine-enforced)

The Client Reference Sheet (generated by `scripts/21-generate-client-reference-sheet.sh`, delivered to
the client in Notion or as markdown) is the doc the client opens to wire OpenClaw into GHL. It **MUST
always** contain BOTH of the following as real, copy-paste-ready fenced code blocks — never as prose,
never omitted:

- [ ] **Authorization Header — TWO separate copy blocks (Key + Value, NEVER combined).** A GHL custom-webhook
      header has a **Key** box and a **Value** box, so the Authorization header MUST be emitted as TWO separate
      copyable code blocks: block 1 contains exactly `Authorization` (paste into the **Key** / header-name box)
      and block 2 contains exactly `Bearer <token>` (paste into the **Value** box), with the ACTUAL `hooks.token`
      (read from `HOOKS_TOKEN` / `OPENCLAW_HOOKS_TOKEN` / `hooks.token` in `openclaw.json` at generation time)
      inside the value block. **The VALUE block must be ONLY `Bearer <token>` — it must NOT repeat the word
      `Authorization`.** A combined `Authorization: Bearer <token>` copy block is the bug (the client pastes the
      whole string into the Value box) and is machine-FAILED. Apply the SAME Key/Value split to the Content-Type
      header (block 1 = `Content-Type`, block 2 = `application/json` — never a combined `Content-Type: application/json`
      value block). If the token cannot be resolved, the generator emits a clearly-marked PLACEHOLDER value block
      and warns — it never silently omits the section.
- [ ] **GHL Custom Webhook — Raw Body** — the canonical FLAT 23-key body as a ` ```json ` fenced code block
      (copyable), plus the **Method (POST)**, the **hook URL** (`https://<host>/hooks/<id>`), and
      **Content-Type** (`application/json`), each as a copyable code block. The body stays placeholder-free
      in `messageTemplate` and is never nested or stripped below 23 keys.
- [ ] **Manual Custom-Webhook fill instructions (MANDATORY in EVERY client doc)** — an explicit, prominent
      statement that AFTER Build-with-AI runs the client MUST open the Custom Webhook action and MANUALLY
      enter the Method, URL, the `Authorization: Bearer <token>` + `Content-Type: application/json` headers
      (via **Add item**), and the Raw Body JSON, then Save + Publish — because **Build with AI will NOT fill
      these for you** (it only builds the workflow SHAPE / an empty Custom Webhook action). The reference
      sheet LEADS with the copy-paste values (URL → Bearer token → Raw Body JSON → manual-fill steps →
      Workflow-AI prompt); explanation/reference follows after. This is machine-enforced by
      `scripts/qc-reference-sheet.sh --require-manual-fill` (CI + pre-handoff QC).

> The manual Custom-Webhook fill step is MANDATORY in every client doc, not optional prose. GHL's
> Build-with-AI only constructs the workflow SHAPE (trigger + an empty Custom Webhook action) and does NOT
> reliably populate the URL / Authorization / Content-Type / Raw Body, so every client must paste those by
> hand. The generated reference sheet (Section above) makes this explicit and is gated in CI.

A live client (Teresa) was stranded by a reference sheet that had NEITHER the bearer token NOR a copyable
Raw Body JSON — there was nothing to paste into GHL's Build-with-AI. This is now **machine-enforced by
`scripts/qc-reference-sheet.sh`** (wired into `scripts/11-run-qc-checklist.sh` AND CI
`.github/workflows/qc-static.yml`): the gate drives the generator in an offline sandbox and FAILS the
build if the rendered sheet lacks the word `Bearer`, a ` ```json ` fenced code block, or the hook URL. It
is no longer optional prose.

## 8. MANDATORY — deliver the doc LINK to the client via Telegram (un-skippable, machine-enforced)

**Every client gets their setup-doc LINK via Telegram, no matter what.** The install is NOT complete until
the client has been SENT their Quick-Start / Notion doc link via Telegram
(`openclaw message send --channel telegram -t <chat>`). Drafting/generating the doc is NOT delivering it —
this is a separate, GATED step. The operator was tired of repeating this, so it is now enforced exactly
like the send-directive / conversation-memory / playbook-doc gates.

- [ ] **Doc LINK delivered via Telegram, state-recorded.** `scripts/22-notify-client-doc.sh` sends the
      Quick-Start / Notion doc link to the client and records `clientDocDelivered=true` in the run-state
      file. The reference-sheet generator (`scripts/21-generate-client-reference-sheet.sh`) already sends
      the link as part of Step 6; the dedicated notify script makes the delivery a re-runnable, gated step.

**Chat-id resolution — grep the TRANSCRIPTS, not just `sessions.json`.** `22-notify-client-doc.sh` uses
`CLIENT_TELEGRAM_CHAT_ID` when the operator captured it; when it is empty, it DISCOVERS the chat by
grepping `agents/*/sessions/*.jsonl` for every shape a paired chat appears in — `"chat":{"id":<n>`,
`telegram:direct:<n>`, `"chatId":<n>`, and `"from":{"id":<n>` — and takes the **most-frequent NON-operator
id**. Reading `sessions.json` keys alone MISSES paired chats (the Teresa lesson). If NO chat is found, the
script FLAGS LOUDLY (stderr banner + `clientDocDelivered=false`) and exits non-zero so the install is
marked incomplete — it NEVER silently skips.

**ENFORCEMENT.** Machine-enforced by `scripts/qc-notify-client-doc.sh` (wired into
`scripts/11-run-qc-checklist.sh` AND CI `.github/workflows/qc-static.yml`): the gate FAILS unless the
notify script exists, sends via the gateway (never `api.telegram.org`), discovers the chat from the
transcripts, LOUD-fails on no chat, and is wired into the binding instructions. The pre-handoff checklist
ALSO asserts the run-state field `clientDocDelivered=true` at runtime.

## 9. "YOUR COMMUNICATION PLAYBOOKS" section — MANDATORY in the generated client doc (machine-enforced)

The generated Client Reference Sheet (`scripts/21-generate-client-reference-sheet.sh`) MUST carry a
prominent **"Your Communication Playbooks"** section, placed **AFTER the Quick Start and BEFORE the deep
Full Reference & Explanation.** It exists to answer — high up, where the client will actually see it — the
FIRST question every client asks on their first test: *"where are my workflows / communication playbooks?"*

The section MUST contain, prominently (a heading + a callout + a BIG BOLD CTA), and teach the client how the
AI helps them build ADDITIONAL communication playbooks (friendly tone, generous emojis 💬🚀🛠️📅🏷️✅):

- [ ] **WHERE they live / are stored** — the working copies are in the client's OpenClaw master-files
      **`conversation-workflows/`** folder (the source of truth the agent reads on every reply), and the
      human-facing copies are **mirrored to their Notion** (Notion → Google Docs → text). Both stay in sync;
      each playbook is recorded in `conversation-workflows/registry.md`.
- [ ] **A "Want another communication playbook? Just ask me!" call-to-action** with a concrete COPYABLE
      example — the client just tells their AI **"Help me build a [purpose] playbook"** (e.g.
      *"Help me build a missed-call follow-up playbook"*), and also surfaces more examples:
      **appointment-reminder, lead-nurture, review-request.**
- [ ] **A walkthrough of WHAT THE AI WILL DO when they ask:** (1) **brainstorm it with you** using what it
      already knows about your business (NOT a 50-question interrogation); (2) **create the communication
      playbook** for you; (3) **store it** for you — the working copy in the master-files
      `conversation-workflows/` folder, mirrored to Notion; (4) **help you create the matching Workflow AI
      prompt** (what you paste into Convert and Flow → Build with AI), wired to **YOUR** Convert and Flow
      (GoHighLevel) account; and (5) that **the AI can take real actions in Convert and Flow on your behalf** —
      it CAN **create tags 🏷️, update your calendar 📅, create/book appointments 🗓️,** and similar automations.
- [ ] **The explicit statement:** *"You have an AI that is connected to your Convert and Flow account and can
      do these things for you — just ask."*

This section is **machine-enforced by `scripts/qc-reference-sheet.sh --require-manual-fill`** (CI +
pre-handoff QC): the gate FAILS unless the generated doc carries the "Communication Playbooks" heading; the
`conversation-workflows` + Notion (stored/mirrored) location facts; the "Want another communication playbook?
Just ask me!" CTA; the copyable "Help me build a [purpose] playbook" example + at least one of the
missed-call/appointment-reminder/lead-nurture/review-request examples; the brainstorm explanation; the matching
Workflow AI prompt wired to the client's Convert and Flow account; the Convert-and-Flow abilities (create
**tags**, update the **calendar**, create/book **appointments**); the explicit "connected to your Convert and
Flow account … just ask" statement — and unless that section sits after Quick Start and before the deep reference.
