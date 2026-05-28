# Skill 38: Conversational AI System (v5.14)

## MANDATORY - Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01) on this folder.**

Required read order:
1. SKILL.md (this file)
2. INSTALL.md — one-time setup: prerequisites + the 9 install scripts in `scripts/`
3. INSTRUCTIONS.md — the v5.14 playbook organized by Phase 0 through Phase 7 (the operator's runtime walkthrough)
4. CORE_UPDATES.md — what gets appended to AGENTS.md + MEMORY.md
5. references/conversational-ai-strategic-roadmap.md — strategic context (what's ✅ shipped vs 📋 pending)
6. CHANGELOG.md — change history

Per N3 ("read before act"), do not skip. Per N4, follow steps in declared order.


## Governing protocol (binding for this skill and all skills in the repo)

This skill is governed by `../QC-PROTOCOL.md` (repo root) — the Sub-Agent Handoff and Mandatory QC Protocol. Every install, every PR, every multi-file change runs the 10-category QC rubric (8.5 threshold) BEFORE declaring done. Sub-agents receive full instructions (never summaries). See `QC-PROTOCOL.md` Part 5 for the sub-agent contract.

## What This Skill Is

**Skill 38 is the conversational AI BRAIN that runs on top of skill 29 (GHL Convert and Flow).** Skill 29 installs Convert and Flow and the basic GHL integration. Skill 38 adds the brain layer: sales best practices, intelligent follow-up, dual-mode customer service + support, typed knowledge bases, intelligent routing, weekly + monthly self-tuning, model version freshness checking, and 21 more protocols from v5.14.

These two skills are SIBLINGS, not duplicates. **Skill 29 is a hard prerequisite.**

## Prerequisites (ALL required; install scripts check at runtime)

- Skill 05 — GHL Setup
- Skill 10 — GitHub Setup (latest version)
- Skill 19 — Humanizer (used ALWAYS-ON; skill 38 does NOT duplicate)
- Skill 29 — GHL Convert and Flow (Convert and Flow CONNECTED to operator's GHL location)

## What This Skill Ships

- 31 protocol files under `protocols/` (humanizer is intentionally NOT here — skill 19 owns it)
- **8 customer journey templates** under `templates/journey-templates/` (coach fully detailed; 7 stubbed)
- **9 install scripts** under `scripts/` (idempotent, OS-aware: Darwin + Linux)
- 10 reference documents** under `references/` (6 deep-dives + the full v5.14 source playbook + the **Cloudflare & GoDaddy Setup Guide** from School of AI — the client-facing walk-through for the missing-CF-token halt path)
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
