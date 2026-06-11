# GHL AI Prompt Layers — Authoritative Reference

> **Canonical home:** `38-conversational-ai-system/references/GHL_AI_LAYERS.md`
> **Cross-referenced by:** Skill 36 (GHL MCP Setup), Skill 38 (Conversational AI System),
> Skill 41 (Build With AI Playbook Generator), Skill 44 (Convert and Flow Operator)
>
> **Read this doc before writing ANY GHL AI prompt.** Pasting the wrong layer into the wrong
> slot breaks the build silently — the system compiles, the runtime never fires, or the
> agent drafts but never sends.

---

## The Three Layers at a Glance

GHL exposes three distinct AI prompt surfaces. They run at different times, in different
systems, and with different owners. **They are not interchangeable.**

| Layer | Name | When it runs | Where it lives | Who pastes it |
|-------|------|-------------|---------------|---------------|
| **Layer 0** | GHL Build-with-AI Compile-Time Prompt | **Build time** — once, when creating/editing the workflow | GHL Automations → "Build using AI" text box | Operator (or Skill 44 / Skill 41 via direct-build) |
| **Layer 1** | GHL Workflow AI Step Prompt | **Run time** — every time the Workflow AI node fires | Inside a "Conversation AI" action node in the published workflow | Operator (or Skill 44 patch-email) |
| **Layer 2** | OpenClaw Master-Files Playbook | **Run time** — when the agent's brain handles an inbound hook | `<MASTER_FILES_DIR>/conversation-workflows/<id>.md`, registered in AGENTS.md | Skill 38 or the agent itself (brainstorm → build → register) |

---

## Layer 0 — GHL Build-with-AI Compile-Time Prompt

**What it is:** A natural-language instruction set you paste into GHL's "Build using AI"
text box (Automations → Build using AI). The GHL AI reads it **once at build time**,
generates a workflow scaffold (trigger + action nodes + conditions), and then discards
the prompt. The prompt itself is never stored in the workflow; the resulting node
configuration is.

**Owner:** Skill 41 (Build With AI Playbook Generator) generates the standardized
8-section Layer 0 prompt. Skill 44 (Convert and Flow Operator) sends it directly to the
internal Build API when the Firebase token is available.

**When to use:**
- Creating a new GHL automation from scratch.
- Adding a new trigger or branch to an existing workflow (rebuild or patch).

**What it CANNOT do:**
- It cannot set the conversational AI reply logic at runtime (that is Layer 1).
- It cannot install the OpenClaw brain or configure conversation playbooks (that is Layer 2).
- It cannot persist between workflow runs.

**Format requirements (Layer 0 only):**
1. Plain natural language — no JSON, no YAML.
2. GHL merge field syntax (`{{contact.first_name}}`) for any runtime values.
3. 8 sections in order (per Skill 41's standardized template):
   workflow name → trigger → dependency list → action sequence → conditions
   → webhook config → settings → post-build verification checklist.
4. Ends with the 12-point post-build verification checklist (the operator or Skill 44
   MUST run it even when the build succeeds — Build-with-AI silently mangles fields).

**Key pitfall:** Build-with-AI gets the scaffold right but frequently drops the
Authorization header from webhook nodes, nests the raw body, or leaves required merge
fields as typed text instead of picker-inserted tokens. The verification checklist
(Section 5 of `GHL-INBOUND-AND-PLAYBOOKS.md`) catches every known failure mode.

---

## Layer 1 — GHL Workflow AI Step Prompt (Run-Time Reply Drafter)

**What it is:** The prompt configured inside a published GHL workflow's
"Conversation AI" action node. GHL's own AI reads it at run time to generate a reply
**draft**. The draft is then sent OR surfaced for review depending on the node's
"Auto-Reply" setting.

**Owner:** The operator configures this directly in the GHL workflow builder, or Skill 44
patches it via `workflows patch-email`. The content is owned by the client's GHL account.

**When to use:**
- When the operator wants GHL's native AI to draft a reply inside the workflow (without
  OpenClaw). This is a SIMPLER path for basic automations that do not need the full
  OpenClaw brain, conversation memory, or the 32 protocols from Skill 38.
- Patching an existing Conversation AI node's instructions without rebuilding.

**What it CANNOT do:**
- It cannot trigger OpenClaw to handle the message (that requires a Custom Webhook node
  pointing to the OpenClaw hook URL — see `GHL-INBOUND-AND-PLAYBOOKS.md` Section 1-4).
- It cannot access OpenClaw's typed knowledge bases, conversation logs, or playbooks.
- It cannot enforce the honesty floor, quiet hours, compliance detection, or any of the
  Skill 38 protocols.

**Key pitfall:** A Layer 1 prompt placed in a Layer 0 Build-with-AI box produces a
workflow whose Conversation AI nodes have their runtime reply logic baked into a static
system prompt — it won't adapt per contact. A Layer 0 Build-with-AI prompt placed inside
a Conversation AI node gets read as the step's reply instruction every time the node
fires, bloating tokens and producing unpredictable output.

---

## Layer 2 — OpenClaw Master-Files Playbook (Run-Time Brain)

**What it is:** A markdown file under `<MASTER_FILES_DIR>/conversation-workflows/<id>.md`
that tells the OpenClaw agent HOW to handle a specific conversation type — which playbook
to invoke, what the goal is, what tone to use, what escalation triggers exist, and how to
handle FAQs within that flow. The agent reads it at run time when the GHL Custom Webhook
fires the OpenClaw hook.

**Owner:** Skill 38 (Conversational AI System). The agent brainstorms, builds, and
registers Layer 2 playbooks. The `AGENTS.md` Step 1.75 workflow-match block routes the
agent to the correct Layer 2 playbook based on inbound signals.

**When to use:**
- For every GHL workflow that has a Custom Webhook node pointed at the OpenClaw hook URL.
- Whenever the agent needs conversation memory, typed knowledge bases, appointment
  booking, the honesty floor, compliance detection, quiet hours, or any Skill 38 protocol.
- The first Layer 2 playbook every client gets is the **appointment-booking playbook**
  (Section 10 of `GHL-INBOUND-AND-PLAYBOOKS.md`).

**What it CANNOT do:**
- It does not generate or configure the GHL workflow structure (that is Layer 0).
- It is not a GHL Conversation AI node prompt and is never pasted into the GHL builder.
- It does not replace the `messageTemplate` in the OpenClaw `hooks.mappings` entry (that
  is the hook's server-side dispatch instruction, a separate concern).

**Key pitfall:** Placing a Layer 2 playbook inside a GHL Conversation AI node (Layer 1
slot) means GHL's AI reads the OpenClaw protocol markdown verbatim as a reply instruction
every time the node fires. The reply will quote protocol headers, "When to invoke"
sections, and Guardrails blocks at the contact. The client's phone lights up with internal
documentation.

---

## The CAF-Build Workflow: Layer 0 via Skill 44 (Option 1 — PRIMARY)

When the client has Skill 44 (Convert and Flow Operator) installed and a healthy
`GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`:

```
Operator intent
    │
    ▼
Skill 41  ──► generates standardized 8-section Layer 0 structure
    │             (dependency-first: tags / custom fields / values created FIRST)
    │
    ▼
Skill 44  ──► sends structure to GHL internal Build API (workflows build)
    │             link_steps() runs BEFORE save → no corrupted step order (v2.1.0 fix)
    │             rejected save exits non-zero → never silent Steps:0/Errors:0/exit-0
    │
    ▼
12-point verification  ──► human verifies post-build (ALWAYS — even on success)
    │
    ▼
Skill 38  ──► Layer 2 playbook registered + human-facing doc created
```

**This is Option 1 — the reliable path.** Skill 44 v2.1.0+ (engine CLI 2.1.0, shipped in
the Skill-44 engine fix `beb43e35`) resolves both critical build bugs:
- `link_steps()` now runs before save, eliminating GHL 400 corrupted-order errors.
- A rejected step-save exits non-zero; the operator sees the failure instead of a
  silent Steps:0/Errors:0/exit-0 false-pass.

---

## The Build-with-AI Workflow: Layer 0 via Manual Paste (Option 2 — FALLBACK)

When Skill 44 is NOT installed, or the Firebase token is missing or expired:

```
Operator intent
    │
    ▼
Skill 41  ──► generates standardized 8-section Layer 0 prompt (plain text)
    │
    ▼
Operator  ──► opens GHL Automations → Build using AI → pastes prompt → Builds
    │
    ▼
12-point verification  ──► operator runs checklist (MANDATORY — Build-with-AI silently mangles fields)
    │
    ▼
Skill 38  ──► Layer 2 playbook registered + human-facing doc created
```

**This is Option 2 — the fallback path.** It works but requires manual paste and is
more prone to Build-with-AI field-mangling. Always run the 12-point verification
checklist (Section 5 of `GHL-INBOUND-AND-PLAYBOOKS.md`).

---

## The Human Is Always the Final Verifier

Regardless of which path builds the workflow:

1. **The operator MUST run the 12-point post-build verification checklist** after every
   build — Option 1 (Skill 44 direct) and Option 2 (Build-with-AI paste) alike.
2. **The operator MUST perform a real inbound test** (send an actual message on the
   channel; do NOT rely on GHL's in-builder "Test" button — it sends empty merge fields
   and passes even when the live payload is broken).
3. **The operator MUST confirm the backend self-test passed** (`selfTestPassed=true` in
   the run-state file) before telling the client to test.

The agent cannot verify what GHL's builder silently changed. The human is the ground
truth for every GHL workflow state.

---

## Quick Decision Table

| Situation | Correct action |
|-----------|---------------|
| Need to create a new GHL workflow | Layer 0: use Skill 44 (Option 1) if Firebase token present; else Skill 41 → manual paste (Option 2) |
| Need to update the Conversation AI node's reply logic | Layer 1: patch the workflow AI step prompt via `caf workflows patch-email` or manually in GHL |
| Need to add/change a conversation playbook for the OpenClaw brain | Layer 2: use Skill 38 brainstorm → build → register |
| Agent drafts a reply but never sends it to the contact | Missing Layer 2 SEND-DIRECTIVE in `hooks.mappings` messageTemplate — see `GHL-INBOUND-AND-PLAYBOOKS.md` §4 |
| Build-with-AI produces Steps:0/Errors:0/exit-0 | Engine bug pre-v2.1.0 — upgrade Skill 44 to v1.0.3+ (engine CLI 2.1.0) |
| GHL 400 error on workflow save | Corrupted step order bug pre-v2.1.0 — `link_steps()` fix in Skill 44 v1.0.3+ (engine CLI 2.1.0) |
| Layer 2 playbook content appearing in GHL contact replies | Layer 2 markdown was pasted into a Layer 1 Conversation AI node by mistake — move it back to `conversation-workflows/` |

---

## Cross-References

- **Skill 36 (`36-ghl-mcp-setup/`)** — GHL MCP tool setup; the MCP tools call GHL's
  public API. MCP is a SEPARATE surface from the Build API that Skill 44 uses. MCP
  tools cover contacts/conversations/calendar/tags reads and writes; they do NOT build
  workflows. Layer 0/1/2 are orthogonal to MCP.
- **Skill 38 (`38-conversational-ai-system/`)** — owns Layer 2. This document lives in
  its `references/` directory as the canonical 3-layer reference for every operator reading Skill 38.
- **Skill 41 (`41-build-with-ai-playbook/`)** — the Layer 0 prompt generator. It
  produces the 8-section structure that either goes to Skill 44's Build API (Option 1)
  or to the operator's clipboard for manual paste (Option 2).
- **Skill 44 (`44-convert-and-flow-operator/`)** — Tier 0 GHL operator. Handles
  Option 1 direct-build via the internal API when the Firebase token is present.
  Falls through to Option 2 (Build-with-AI manual paste) when the token is missing.
- **`GHL-INBOUND-AND-PLAYBOOKS.md` Section 4** — the canonical Build-with-AI prompt
  template (Option 2 paste content). Updated to reflect CAF-first routing.
- **`workflow-ai-instructions-standard.md`** — the Layer 1 standards checklist.
- **`communications-playbook-standard.md`** — the Layer 2 content standards checklist.

---

*Last updated: 2026-06-11 — Skill 38 v1.7.0. CAF-first (Option 1) promoted to primary;
Build-with-AI (Option 2) demoted to fallback. Human=final verifier on both paths.*
