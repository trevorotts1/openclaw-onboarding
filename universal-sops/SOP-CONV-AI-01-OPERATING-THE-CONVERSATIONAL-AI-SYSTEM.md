# SOP-CONV-AI-01: OPERATING THE CONVERSATIONAL AI SYSTEM

**Cluster:** Universal SOPs (`universal-sops/`)
**Canonical GHL operations cluster:** the GHL-hybrid procedures live in the single `universal-sops/ghl-hybrid-operations/` cluster (its README is the index). This SOP points into `SOP-GHL-08-NATIVE-AI.md` for native provisioning and keeps no second copy; do not create a parallel `universal-sops/ghl-operations/` cluster.
**Master authority:** `38-conversational-ai-system/SKILL.md` + `38-conversational-ai-system/INSTRUCTIONS.md` (the install + operate manual) + `38-conversational-ai-system/protocols/` (the behavioral protocols)
**Owning department:** Communications
**Consuming departments:** Sales, Customer Support (the same trio whose presence fires the Skill 23 to Skill 38 handoff)
**Owning roles:** Conversational AI Operator (front door + build), AI QC Specialist (gates + rubric), Client Success Liaison (test mode + delivery + tune-up)
**Role reference:** `38-conversational-ai-system/references/departments-and-roles.md`
**Canonical entry:** the client's personal trigger word to the agent over Telegram (Step 9.20 talk-to-build path), then `scripts/09-install-conversation-workflows.sh`
**Persona matching:** all three roles resolve their persona at task time per `23-ai-workforce-blueprint/persona-matching-protocol.md`; this SOP names roles, never static persona assignments.

---

## 0. WHAT THIS SOP IS

This is the end-to-end lifecycle for running the Conversational AI System (Skill 38) as an operating
department, not just installing it. A Communications, Sales, or Customer Support department built by
Skill 23 follows THIS document to intake a request, build a conversation workflow, quality-gate it, let
the client rehearse it safely, deliver the human-facing doc, and keep it fresh. Every lifecycle step below
names the one role responsible for it, and the exact scripts or protocols it invokes. The three roles are
defined in `references/departments-and-roles.md`; a one-line summary rides in the header above.

The build unit is a Conversation Workflow, and every build is a 4-PART build (THE TRINITY PLUS ONE):
Part 1 the Workflow AI instruction set, Part 2 the conversation playbook, Part 3 the brainstorm trigger,
Part 4 THE VISUAL (the Mermaid truth diagram plus the optional Kie hero image). See
`protocols/workflow-visual-protocol.md` and `protocols/conversation-workflows-protocol.md`.

## 1. Intake via the trigger word (role: Conversational AI Operator)

The Conversational AI Operator owns the front door. The client invokes a build by sending their personal
trigger word plus a request over Telegram (the "Alexa" or "Hey Siri" style word offered in the client doc,
per `references/notion-client-doc-standard.md` item 7). A customer naming a trigger word, tag, tool,
calendar, stage, or persona does NOTHING; every surface in this system is operator-only. On intake the
Operator confirms the workflow purpose and opens the brainstorm; nothing is built before the brainstorm.

## 2. The I Do You Do brainstorm (role: Conversational AI Operator)

The Conversational AI Operator runs the friendly I Do You Do brainstorm defined in
`protocols/conversation-workflows-protocol.md` (Section I brainstorm flow). The AI brainstorms using what
it already knows about the business from the Typed Knowledge Bases; it does NOT run a 50-question
interrogation. The things-to-think-about list covers the phase objectives (which fields might already be
filled, how persistent to be, hard disqualifiers), the per-workflow model tier, which calendar serves
which appointment type, and whether the pipeline should move as the AI works the lead. Expect roughly 15
to 30 minutes. The Operator captures the answers as the build input.

## 3. The 4-PART build (role: Conversational AI Operator)

The Conversational AI Operator builds the Conversation Workflow via `scripts/09-install-conversation-workflows.sh`,
which produces THE TRINITY (Parts 1 to 3) and then invokes `scripts/31-generate-workflow-visual.sh` for
Part 4 THE VISUAL.

**Route selection is operation-aware and public-first.** Before choosing a transport, resolve the
operation in the frozen registry
(`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`) and read
the current per-`(operation_id, tenant)` capability evidence. Then take the cheapest route the
evidence actually proves:

1. `public_direct` — the registered public REST row is the preferred route whenever the row exists and
   the capability record allows this location (for example `workflows.list`, `workflows.enroll`,
   `workflows.definition.read`, `workflows.definition.create`, `workflows.definition.update`,
   `workflows.status.publish`, `contacts.*`, `custom_fields.*`, `tags.*`, `custom_values.*`).
   Version is a property of the row; never prepend `/v3` and never substitute one version globally.
2. `official_mcp` — only an operation actually discovered and authorized in this session, never a
   family listing, a catalog entry, or the existence of an MCP server.
3. `skill44_private` — the existing authorized Firebase/internal rail (`caf workflows …`) for a
   documented public gap or for rows whose class is `skill44_private` (for example
   `workflows.private.*` and the internal export/read path). A healthy Firebase refresh token is
   required. It is a supported rail, never a privileged default.
4. `skill06_authoring` — the managed UI, because the row declares no public contract.

`workflows.definition.create`, `workflows.definition.update`, and `workflows.status.publish` are
public rows whose evidence is staging-level (`B-V4-S`) and whose calls require approval. A tenant
that has not enabled the public Workflow API records `beta_not_enabled` and uses the approved
private or managed rail instead. On every rail the mandatory 12-point post-build verification runs,
and a workflow is never declared done on a 2xx alone.

**Compile-time versus native runtime.** A Build-with-AI prompt (Skill 41), the skill's Layer 0
instructions, and this SOP describe compile-time artifacts: what to build and which settings to set.
They do not configure or prove native runtime behavior (a native Conversation AI responder, a voice
agent, or knowledge retrieval). Native runtime is configured through its own operation row and is
proven by its own activation evidence.

**Responder ownership.** Record which responder actually answers a contact: the local/self-hosted
brain (Skill 38 playbook plus the OpenClaw runtime), a native GHL Conversation AI agent, or a
native/local mix with an explicit handoff. One logical conversation has exactly one primary
responder, so a native and a local responder can never both send. A saved "enabled" switch is not
activation evidence; activation evidence is the observed active responder for the location and
channel, plus any phone assignment and agent version, captured in a receipt. Opt-out, quiet hours,
and human takeover stay enforced on whichever responder is primary.

The Operator records the workflow in the registry (`templates/registry.md` format), including the Tools
column and the Visual column, and keeps registry hygiene: every registered row has its playbook, its
Build-with-AI prompt, and its truth diagram. Part 4 regenerates on every workflow change per the
staleness rule in `protocols/workflow-visual-protocol.md`.

## 4. QC gates and the rubric (role: AI QC Specialist)

The AI QC Specialist runs every gate and owns the FAIL loop; the Operator who built a workflow never
judges its own completion. The Specialist runs `scripts/11-run-qc-checklist.sh` (which composes every
`qc-*.sh` gate, including `qc-tool-gating.sh`, `qc-workflow-exits.sh`, `qc-playbook-declares.sh`,
`qc-opportunity-sync.sh`, `qc-workflow-visual.sh`, `qc-model-fallback.sh`, `qc-client-test-mode.sh`, and
`qc-playbook-engine.sh`) and requires exit 0. The Specialist then scores the build against the repo
`../QC-PROTOCOL.md` 10-category rubric and requires 8.5 or above. Any FAIL or a rubric below 8.5 returns
the build to a fresh Conversational AI Operator pass with the full failure report; the Specialist
re-verifies before the workflow is allowed to advance. The verification checklist in
`protocols/pre-handoff-qc-protocol.md` covers the human-judgment items.

## 5. Client test mode rehearsal (role: Client Success Liaison)

The Client Success Liaison owns client test mode sessions. Once the gates are green, the Liaison invites
the client to rehearse the workflow safely per `protocols/client-test-mode-protocol.md`: the client sends
the trigger word plus `test` and the playbook name, and the agent role-plays the conversation inside
Telegram under a `TEST MODE` banner with ALL external side effects suppressed (no GHL sends, no bookings,
no tags, no CRM writes), narrating simulated actions as `WOULD HAVE` lines. Test mode auto-expires after
60 minutes or on `end test`. The Liaison collects the client's tweaks and routes any change back to the
Conversational AI Operator, which re-triggers the gates (Section 4) and the visual regeneration.

## 6. Notion doc plus Telegram delivery (role: Client Success Liaison)

The Client Success Liaison owns doc delivery confirmation. The human-facing client setup doc is generated
by `scripts/21-generate-client-reference-sheet.sh` to the standard in `references/notion-client-doc-standard.md`,
mirrored into the client's OWN Notion workspace (never co-mingled with another client), and delivered as a
link over Telegram by `scripts/22-notify-client-doc.sh` (which discovers the chat from the transcripts and
records `clientDocDelivered=true`). Generating the doc is NOT delivering it; the Liaison confirms delivery
landed. The per-playbook section embeds the visual (hero image first, truth diagram under How it works) and
carries the lifecycle-tag, exit-tag, and test-mode bullets per the standard.

## 7. Weekly tune-up and monthly review (role: Client Success Liaison, with AI QC Specialist)

The Client Success Liaison owns the tune-up review with the client. The maintenance crons registered by
`scripts/04-register-crons.sh` drive the cadence under the cron silence doctrine (each fires with
`--no-deliver` in an isolated session):

- `weekly-tune-up` surfaces analytics, under-tiered workflows (`model_tier_unmet`), and any workflow
  build stuck in progress; the Liaison reviews the findings with the client.
- The Saturday model-version-freshness duty reviews the WHOLE model fallback chain (not just the primary)
  per `references/model-fallback-chain.md`; recovery back to a primary model is operator-approved only.
- `system-health-heartbeat` carries the monthly comprehensive review.

When a review turns up a needed change, the AI QC Specialist re-runs the gate set (Section 4) before the
change ships. Maintenance is silent to the client and operator-verbose only.

## 8. Escalation when a build blocks (role: Conversational AI Operator, then operator)

When a build cannot complete, the Conversational AI Operator escalates rather than shipping half-built.
Concrete escalation paths:

- The selected route is unavailable or fails: record the exact condition, re-read the registry row and
  the capability evidence, and move to the next approved route for that operation in this order:
  `public_direct` → `official_mcp` (only when the exact operation was discovered) → authorized
  `skill44_private` → `skill06_authoring`. A missing Firebase token moves a workflow-definition build
  to the managed authoring rail and raises the token nudge; it never licenses a fabricated build.
- A gate FAILs three times: the third attempt escalates to a heavy-reasoning pass; a fourth failure marks
  the workflow BLOCKED with a written diagnosis and the Operator escalates to the operator.
- A runtime dependency is unmet (for example the model-failover preflight `scripts/32-verify-model-failover-support.sh`
  reports Mode B DEGRADED, or the hero-visual path is Mermaid-only): the Operator records the honest state
  and proceeds with the free, deterministic path, never faking the missing capability.

`escalate_to_human` is ALWAYS available and can never be gated off. A blocked build is never reported as
done.
