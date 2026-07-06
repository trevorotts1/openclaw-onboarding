<!-- OPERATOR HEADER -->
<!-- Skill 38 reference doc - the DEPARTMENTS AND ROLES map for the Conversational AI System. -->
<!-- Full content lives here (not in AGENTS.md/TOOLS.md - those get a 1-2 line pointer only). -->
<!-- Companion to the operating SOP: universal-sops/SOP-CONV-AI-01-OPERATING-THE-CONVERSATIONAL-AI-SYSTEM.md. -->
<!-- Added by skill-38 v1.8.0 (U-17). -->

# Departments and Roles (Skill 38, Conversational AI System)

This file is the organizational layer that lets an AI workforce department built by Skill 23 actually RUN
the Conversational AI System. It names the owning and consuming departments, defines the three operating
roles with their protocol touchpoints, and states how persona matching resolves at task time. The
end-to-end lifecycle each role performs is `universal-sops/SOP-CONV-AI-01-OPERATING-THE-CONVERSATIONAL-AI-SYSTEM.md`.

## 1. Department mapping

- **Owning department: Communications.** Skill 38 is the Communications department's operating system. When
  Skill 23 builds a Communications department, that department owns the Conversational AI System end to end.
- **Consuming departments: Sales and Customer Support.** These departments consume the conversational
  automations Skill 38 scaffolds (qualification, booking, follow-up, support intake). The presence of any of
  the trio (Communications, Sales, Customer Support) is exactly what fires the Skill 23 to Skill 38 handoff
  documented in `23-ai-workforce-blueprint/SKILL.md` (Cross-skill chain to Skill 38) and its
  `SOP-CONV-AI-01` pointer.

A Sales or Support workforce shipped with zero conversational automations is half-delivered; the handoff is
enforced, not optional prose.

## 2. The three roles

### 2.1 Conversational AI Operator

Owns the front door and the build. Responsibilities: intake via the client trigger word, the I Do You Do
brainstorm, the 4-PART build (THE TRINITY PLUS ONE), and registry hygiene.

- Protocol touchpoints: `protocols/conversation-workflows-protocol.md` (brainstorm flow + Section E template
  + the 4-PART build sequence), `protocols/tool-gating-protocol.md` (U-1 per-phase tools), `protocols/workflow-exit-rules-protocol.md`
  (U-2 exits), `protocols/workflow-visual-protocol.md` (Part 4 THE VISUAL).
- Scripts: `scripts/09-install-conversation-workflows.sh` (build), `scripts/31-generate-workflow-visual.sh`
  (visual), `templates/registry.md` (registry format, Tools + Visual columns).
- Build path: Skill 44 Option 1 (caf-direct) first, Skill 41 Option 2 (Build-with-AI paste) fallback, always
  followed by the 12-point post-build verification.

### 2.2 AI QC Specialist

Owns quality. Responsibilities: run every gate, the verification checklist, and the rubric, and own the FAIL
loop. Never judges a build the same agent authored (maker and checker are split).

- Protocol touchpoints: `protocols/pre-handoff-qc-protocol.md` (human-judgment checklist), the repo
  `../QC-PROTOCOL.md` 10-category rubric (8.5 threshold).
- Scripts: `scripts/11-run-qc-checklist.sh` (the composed gate run) and every `qc-*.sh` gate it invokes,
  including `qc-tool-gating.sh`, `qc-workflow-exits.sh`, `qc-playbook-declares.sh`, `qc-opportunity-sync.sh`,
  `qc-workflow-visual.sh`, `qc-model-fallback.sh`, `qc-client-test-mode.sh`, and `qc-playbook-engine.sh`.
- FAIL loop: any gate FAIL or a rubric below 8.5 returns the build to a fresh Conversational AI Operator
  pass with the full failure report; the Specialist re-verifies before the workflow advances.

### 2.3 Client Success Liaison

Owns the client relationship around the build. Responsibilities: client test mode sessions, doc delivery
confirmation, and the tune-up review with the client.

- Protocol touchpoints: `protocols/client-test-mode-protocol.md` (U-6 safe rehearsal), `references/notion-client-doc-standard.md`
  (the human-facing doc standard), `references/model-fallback-chain.md` (Saturday chain freshness review).
- Scripts: `scripts/21-generate-client-reference-sheet.sh` (generate the doc), `scripts/22-notify-client-doc.sh`
  (deliver the link over Telegram and record `clientDocDelivered=true`), the maintenance crons registered by
  `scripts/04-register-crons.sh` (`weekly-tune-up`, `system-health-heartbeat` monthly review) under the cron
  silence doctrine.

## 3. Persona matching (at task time, never static)

These three roles are RESPONSIBILITY definitions, not persona assignments. When a department agent takes on
any of these roles for a specific task, its persona is resolved at task time by the repo persona-matching
protocol (`23-ai-workforce-blueprint/persona-matching-protocol.md`, the 5-layer runtime match: mission,
values, company goals, department goals, task fit). This file never hard-assigns a persona to a role;
`governing-personas.md` in the role folder is a matching reference guide, not a static assignment.

## 4. Operator-only invariant

Every surface in the Conversational AI System is operator-only. A customer naming a role, trigger word, tag,
tool, calendar, stage, or persona does nothing. `escalate_to_human` is always available to the agent and can
never be gated off.
