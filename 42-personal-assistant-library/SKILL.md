---
name: personal-assistant-library
description: 29 pre-built personal assistant specialists covering inbox management, calendar, coaching, emotional support, travel, finance, relationships, spiritual life, and productivity — each with role identity, voice/soul file, operating playbook, persona governance, and DMAIC SOPs. Ships as a ready-to-deploy library that the agent materializes into the owner's workspace on demand.
triggers:
  - "set up my personal assistant"
  - "deploy my PA team"
  - "install personal assistant specialists"
  - "personal assistant library"
  - "set up inbox manager"
  - "set up my coach"
  - "personal assistant"
version: 1.0.4
---

# Skill 42: Personal Assistant Library

## MANDATORY - Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01) on this folder.**

Required read order:
1. SKILL.md (this file) -- overview, component map, relationship to Skill 23
2. INSTALL.md -- one-time setup: prerequisites + materialization steps + verification
3. INSTRUCTIONS.md -- runtime guide: how the agent selects, materializes, and runs a specialist
4. CORE_UPDATES.md -- what gets appended to AGENTS.md + TOOLS.md + MEMORY.md
5. EXAMPLES.md -- worked, copy-pasteable example flows (UNIVERSAL placeholders only)
6. CHANGELOG.md -- version history

Per N3 ("read before act"), do not skip. Per N4, follow steps in declared order.

## Governing protocol (binding for this skill and all skills in the repo)

This skill is governed by ../QC-PROTOCOL.md (repo root) -- the Sub-Agent Handoff and Mandatory QC Protocol. Every install, every PR, every multi-file change runs the 10-category QC rubric (8.5 threshold) BEFORE declaring done. Sub-agents receive full instructions (never summaries). See QC-PROTOCOL.md Part 5 for the sub-agent contract.

## What This Skill Is

**Skill 42 is the Personal Assistant Library** -- a ready-to-deploy collection of 29 personal-life specialists that the agent materializes into the owner's workspace on demand. Where Skill 23 (AI Workforce Blueprint) builds the owner's *business* departments (marketing, sales, billing, CRM, operations), Skill 42 builds the owner's *personal* department: the life/productivity team that manages the owner's inbox, calendar, coaching, emotional support, travel, finances, relationships, spiritual life, and goals.

Each of the 29 specialists is a full sub-workspace spec, not a flat role file. Every specialist folder contains:

- `00-START-HERE.md` -- the read order and orientation for that specialist
- `IDENTITY.md` -- who the specialist is (name, role, mandate, boundaries)
- `SOUL.md` -- the specialist's voice, tone, and operating personality
- `governing-personas.md` -- the 5-layer persona alignment (integrates with Skill 22's persona library)
- `how-to.md` -- the operating playbook
- `ROSTER.md` -- summon conditions: when this specialist activates and what it does
- `SOP/` -- DMAIC standard operating procedures (`00-INDEX.md` + the `PA-NN-NN-slug.md` procedures, named consistently across all 29 specialists)

## Relationship to Skill 23 (AI Workforce Blueprint)

Skill 42 is **additive**, not a replacement. It extends Skill 23 by adding the owner's personal-life department alongside the business departments Skill 23 builds.

- Skill 23's `templates/role-library/` holds one flat `.md` per *business* role. Skill 42's `specialists/` holds 29 full sub-workspace specs for *personal-life* roles. Different taxonomy, different structure.
- Skill 23's `department-naming-map.json` already carries the note: "Personal Assistant department pending proposal -- when approved it will bring the floor to 24." Adding `personal-assistant` to that map's mandatory block (so Skill 23 auto-builds the PA department for every client) is an **optional one-line patch** to Skill 23 -- a product decision, intentionally NOT bundled into this skill's first ship. Skill 23 can reference this library once it is installed without a naming-map change, using Option C (Audit/Resume).
- This skill is a SIBLING of domain-vertical skills 39 (Real Estate Playbook) and 41 (Build With AI Playbook) -- standalone skills that bolt onto Skills 23/38 rather than modifying them.

## Component Map (the 29 specialists)

| # | Specialist | SOPs | What it owns |
|---|------------|------|--------------|
| 01 | Inbox Manager | 8 | Email triage, draft replies, follow-up tracking, zero-inbox protocol |
| 02 | Calendar & Scheduling Manager | 7 | Booking, conflict resolution, focus-block protection, day-before confirmations |
| 03 | Daily Briefing & Debrief | 4 | Morning briefing, evening debrief, weekly preview/review |
| 04 | Task & Priority Manager | 6 | Capture, daily top-3, deadlines, delegation routing, overwhelm triage |
| 05 | Meeting Assistant | 5 | Agendas, live notes, action-item extraction, follow-up distribution |
| 06 | Research & Answers | 4 | Deep-research briefs, comparisons, vendor research, summarization |
| 07 | Brainstorming & Ideation | 5 | Structured brainstorms, parking lot, idea evaluation/scoring |
| 08 | My Coach | 8 | Goal-setting, accountability, confidence/fear reset, weekly review |
| 09 | Emotional Support & Wellbeing | 8 | Check-ins, grounding, boundaries, gratitude (coaching-scope, with crisis referrals) |
| 10 | Travel Logistics | 5 | Itinerary build, booking checklists, trip prep |
| 11 | Personal Finance | 5 | Subscription audit, expense capture, budgeting (coaching-scope) |
| 12 | Relationships & Dates | 4 | Relationship cadence, important dates, thoughtful gestures |
| 13 | Errands & Purchases | 4 | Errand batching, purchase research, ordering |
| 14 | Life-Admin Archivist | 5 | Account inventory, credential hygiene (pointers, never secrets), document filing |
| 15 | Christian Spiritual Life | 6 | Devotional rhythm, scripture engagement, prayer practice |
| 16 | Motivation & Momentum | 4 | Monday ignition, mid-week boosts, post-setback bounce-back |
| 17 | The Challenger | 4 | Hard-mirror sessions, excuse audits, comfort-zone stretch |
| 18 | Family & Life-Stage | 6 | Family rhythms, life-stage transitions, caregiving coordination |
| 19 | Study Partner | 5 | Snippet curation, reflection, book curation, accountability (sub-specialist roster: ships 6 sub-role files — `01-snippet-curator` … `06-study-partner-director` — in addition to the standard 6-file set, for 12 role files total) |
| 20 | Passion & Purpose | 4 | Purpose clarity, passion mapping, alignment |
| 21 | Clarity Specialist | 5 | Decision clarity, thought untangling, next-step naming |
| 22 | YouTube Teacher | 4 | Curated learning, channel/video curation, study plans |
| 23 | Goal Setter | 5 | Goal architecture, milestone mapping, review cadence |
| 24 | Superwoman Syndrome | 6 | Cape inventory, permission-to-receive, delegation, crisis-referral boundary |
| 25 | Imposter Syndrome | 6 | Evidence ledger, reframe protocols, self-talk audits |
| 26 | Therapeutic Support | 12 | Active listening, emotional check-ins, stress triage (coaching-scope, crisis referrals) |
| 27 | Focus & Completion | 5 | Deep-work protocols, completion sprints, distraction defense |
| 28 | Celebration Agent | 6 | Win capture, milestone celebration, gratitude rituals |
| 29 | Greatness Agent | 6 | Standards elevation, excellence prompts, identity-level coaching |

A machine-light navigation index lives at `specialists/_index.md`.

## Scope & Safety

Several specialists (09 Emotional Support, 24 Superwoman, 26 Therapeutic Support) operate in a **coaching scope only** -- explicitly NOT therapy, medical advice, or crisis intervention. Their SOPs carry crisis-referral protocols (988, NAMI 1-800-950-6264, National DV Hotline 1-800-799-7233) and STOP-and-refer rules. These are public crisis resources, not PII.

## What This Skill Ships

```
42-personal-assistant-library/
├── SKILL.md
├── INSTRUCTIONS.md
├── INSTALL.md
├── CORE_UPDATES.md
├── EXAMPLES.md
├── CHANGELOG.md
├── skill-version.txt          # 1.0.0
├── qc-personal-assistant-library.sh
├── scripts/
│   └── verify-pa-install.sh
└── specialists/               # 29 specialist folders + _index.md
    ├── _index.md
    ├── 01-inbox-manager/  ...  29-greatness-agent/
```

28 specialists × 6 role files + Specialist 19's 12 role files = 180 role files, plus 162 `PA-NN-NN-slug.md` SOPs, plus 29 `SOP/00-INDEX.md`, plus `_index.md`. (Specialist 19 ships 6 sub-specialist role files **in addition to** its standard 6-file set — its `IDENTITY.md` and `SOUL.md` are present alongside the sub-roles, not replaced by them. This is an intentional structural exception: the Study Partner is a roster of 6 sub-specialists rather than one specialist, so it carries both the standard orientation set and a sub-role file per member. The QC script (`qc-personal-assistant-library.sh`) and `scripts/verify-pa-install.sh` exempt Specialist 19 from the per-file role check for this reason.)
