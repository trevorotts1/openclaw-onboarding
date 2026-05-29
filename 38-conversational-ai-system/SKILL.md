# Skill 38: Conversational AI System (v5.14)

## MANDATORY - Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01) on this folder.**

Required read order:
1. SKILL.md (this file)
2. INSTALL.md — one-time setup: prerequisites + the numbered install scripts (`00`–`23`) + QC linters in `scripts/`
3. INSTRUCTIONS.md — the v5.14 playbook organized by Phase 0 through Phase 7 (the operator's runtime walkthrough)
4. CORE_UPDATES.md — what gets appended to AGENTS.md + MEMORY.md
5. references/conversational-ai-strategic-roadmap.md — strategic context (what's ✅ shipped vs 📋 pending)
6. CHANGELOG.md — change history

Per N3 ("read before act"), do not skip. Per N4, follow steps in declared order.


## Governing protocol (binding for this skill and all skills in the repo)

This skill is governed by `../QC-PROTOCOL.md` (repo root) — the Sub-Agent Handoff and Mandatory QC Protocol. Every install, every PR, every multi-file change runs the 10-category QC rubric (8.5 threshold) BEFORE declaring done. Sub-agents receive full instructions (never summaries). See `QC-PROTOCOL.md` Part 5 for the sub-agent contract.

## What This Skill Is

**Skill 38 is the conversational AI BRAIN that runs on top of skill 29 (GHL Convert and Flow).** Skill 29 installs Convert and Flow and the basic GHL integration. Skill 38 adds the brain layer: sales best practices, intelligent follow-up, dual-mode customer service + support, typed knowledge bases, intelligent routing, weekly + monthly self-tuning, model version freshness checking, and the rest of the 32 protocols from v5.14 (see the SELF-COUNTS note under "What This Skill Ships").

These two skills are SIBLINGS, not duplicates. **Skill 29 is a hard prerequisite.**

## Upstream trigger — Skill 23 (AI Workforce Blueprint) hands off to this skill

When **Skill 23** builds an AI workforce that includes a **Communications, Sales, or Customer-Support**
department, its post-build closeout is REQUIRED to hand off here to scaffold the matching comms
automations. This is an ENFORCED cross-skill chain (not prose): Skill 23 tracks it via the
`commsAutomationStatus` field in its `build-state-schema.json` and re-fires a `[COMMS-AUTOMATION-RESUME]`
self-ping (in `resume-workforce-build.sh`) until this skill has registered at least the appointment-booking
starter playbook + its Build-with-AI prompt (THE TRINITY), verifiable via
`scripts/qc-trinity-registry.sh`. So when you're invoked off a `[COMMS-AUTOMATION-RESUME]` message, the
upstream is Skill 23: read its `INSTRUCTIONS.md → "Moment 3.8"`, then build the trinity here. See
`23-ai-workforce-blueprint/SKILL.md → "Cross-skill chain → Skill 38"`.

## Prerequisites (ALL required; install scripts check at runtime)

- Skill 05 — GHL Setup
- Skill 10 — GitHub Setup (latest version)
- Skill 19 — Humanizer (used ALWAYS-ON; skill 38 does NOT duplicate)
- Skill 29 — GHL Convert and Flow (Convert and Flow CONNECTED to operator's GHL location)

## What This Skill Ships

<!-- SELF-COUNTS: re-verify on EVERY version bump — see scripts/bump-version.sh "Skill 38 self-count
     re-verification" note. Counts as of v1.4.9: protocols/=32 (*.md), scripts/=29 (*.sh), references/=14
     (*.md), journey templates=8 dirs. Run: ls -1 protocols/*.md scripts/*.sh references/*.md | per-dir wc -l. -->
- 32 protocol files under `protocols/` (humanizer is intentionally NOT here — skill 19 owns it)
- **8 customer journey templates** under `templates/journey-templates/` (coach + all 7 verticals fully detailed: consulting, course-creator, e-commerce, real-estate, saas, service-provider, wellness)
- **29 scripts** under `scripts/` (idempotent, OS-aware: Darwin + Linux) — the numbered install scripts `00`–`23` plus `skill38-calendar-sync.sh`, the three QC linters `qc-23-key-bodies.sh` (machine-enforces the 23-key GHL body rule, including the v6.0 playbook) + `qc-trinity-registry.sh` (machine-enforces THE TRINITY against both the table and bullet registry forms) + `qc-send-directive.sh` (machine-enforces the mandatory GHL send-directive on every inbound server messageTemplate — drafting != sending), and `qc-trinity-registry.test.sh` (fixture tests for the TRINITY reconciliation)
- 14 reference documents under `references/` (deep-dives + the full v6.0 source playbook + the communications-playbook & workflow-AI/Build-with-AI standards + the **Cloudflare & GoDaddy Setup Guide** from School of AI — the client-facing walk-through for the missing-CF-token halt path)
- **AGENTS.md updates:** Steps 1.7, 1.8, 1.9, 2.8 inserted; Step 1.75 upgraded
- **MEMORY.md design rules 6-14** appended
- **4 cron jobs registered:** Sunday 2am tune-up; Saturday 11pm proactive scan + 11:30pm model freshness; 1st-of-month comprehensive review

## What This Skill Does NOT Do

- Does NOT modify skill 17 (self-improving-agent), 18 (proactive-agent), 31 (upgraded-memory-system), 19 (humanizer), or 29 (ghl-convert-and-flow). Each runs independently.
- Does NOT implement pending roadmap features (F14 Voice, F15 Proactive Outreach Campaigns, F16 A/B Testing, F17 Segmentation, F18 Webhook Chaining, F21 Multi-Tenant Isolation).
- Does NOT auto-update primary models. Model version checks SUGGEST; operator approves.
- Does NOT generate discount codes outside per-product policy.
- Does NOT promise refunds/exceptions without operator approval (honesty floor enforced).

## When the Agent Should Invoke This Skill

After skills 05, 10, 19, 29 are installed AND the operator is ready to wire up the full conversational AI brain. Estimated install time: 60-90 minutes (per v5.14 playbook).
