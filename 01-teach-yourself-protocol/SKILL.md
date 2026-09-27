---
name: teach-yourself-protocol
description: Structured protocol for an OpenClaw agent to learn new skills, APIs, and business processes — reads all files in a skill folder in declared order, extracts key facts, and stores them correctly so knowledge persists across sessions.
---

<!-- CORE_REFERENCE_POLICY_V1 -->
## Compact core storage policy
Keep one short task-triggered pointer with an exact resolved path in the appropriate core file. Update that pointer in place under a stable version-free ID; an existing relevant index pointer may already be sufficient. Detailed instructions live in the canonical reference. There is no minimum line count and no requirement to duplicate working knowledge into bootstrap. Do not add learning or installation receipts to MEMORY.md or fan out an entry across core files. Durable owner facts remain eligible for their appropriate core file. Whole-file budgets are AGENTS.md 15,000 characters, MEMORY.md 8,000, and TOOLS.md 15,000. CORE_UPDATES.md cannot override these storage rules or current owner instructions. Honor an explicit current owner override and coordinate any deliberate budget/baseline exception; historical examples and installer payloads are not overrides. Never preload the reference library.
<!-- /CORE_REFERENCE_POLICY_V1 -->

# Teach Yourself Protocol (TYP)

## What This Skill Is About

The Teach Yourself Protocol is the foundation of how every OpenClaw agent learns new
things. It is a structured, step-by-step process for taking in new knowledge - whether
it is an API reference, a business process, a client preference, or a tool guide - and
storing it in the right place so the agent can find it and use it in future sessions.

Without this protocol, agents either dump everything into their core workspace files
(which makes them bloated and slow) or forget what they learned entirely (because AI
agents start fresh every session with no built-in memory). TYP solves both problems.

## When This Skill Triggers

**Explicit triggers** - the user says things like:
- "Teach yourself this"
- "Learn this"
- "Train yourself on this"
- "Memorize this"
- "Save this for future reference"

**Implicit triggers** - the agent should auto-detect these:
- User shares a large document (50+ lines of structured reference material)
- User provides corrections or updated information about a tool or process
- User explains how something works in detail
- User shares credentials, account structures, or system architecture
- User shares a file saying "here you go" or "use this" without further instructions

**Important:** Every time TYP activates, the agent MUST announce it to the user before
doing any TYP work. Never run TYP silently.

## What It Covers

- **Three-Layer Knowledge Architecture** - short retrieval pointers in core files (Layer 1),
  deep reference files in the master files folder (Layer 2), and organized folder
  structures for large topics like APIs (Layer 3)
- **The Decision Tree** - a step-by-step process: understand the knowledge, assess its
  size, check for conflicts with existing knowledge, create the right files, write
  short retrieval pointers, and confirm to the user
- **Conflict Resolution** - what to do when new knowledge replaces, expands, or
  contradicts something the agent already knows
- **Priority Tagging** - CRITICAL, HIGH, STANDARD, or REFERENCE, so the agent knows
  what matters most
- **API Documentation** - special handling for APIs including folder structures,
  README indexes, and endpoint organization
- **Skills and Instruction Files** - every skill must have a matching instruction file
- **Versioning** - tracking when knowledge was learned and when it was last verified
- **Cross-Referencing** - linking related deep files to each other
- **Anti-Bloat Rules** - keeping core files lean and preventing duplicated content
- **Common Mistakes** - 10 real mistakes agents make and how to avoid them
- **Self-Installation** - how the protocol installs itself using its own rules

## Files in This Folder

Read them in this order:

1. **SKILL.md** (this file) - overview and orientation
2. **teach-yourself-protocol-full.md** - the complete protocol with all 19 sections,
   decision trees, examples, and checklists. This is the authoritative reference.
3. **INSTRUCTIONS.md** - step-by-step guide for executing TYP
4. **INSTALL.md** - how to install TYP into a new agent's workspace
5. **EXAMPLES.md** - worked examples showing TYP in action
6. **CORE_UPDATES.md** - the single stable pointer contract; no installation fanout
7. **MIGRATION-TYP.md** - self-heal migration procedure for existing clients with bloat
8. **teach-yourself-protocol.skill** - the packaged skill archive; use only when it matches these reviewed sources

## Self-Heal Migration (for Existing Clients)

If an existing client workspace was set up before v10.15.37 (Mac) / v10.16.36 (VPS),
it may have bootstrap file bloat or documents stored in wrong locations. Run the
migration script to detect and fix:

```bash
bash scripts/typ-migrate.sh --dry-run    # preview what would change
bash scripts/typ-migrate.sh              # apply remediation
```

See **MIGRATION-TYP.md** for the full procedure and platform-detection logic.

## Prerequisites

None. This is the very first skill installed for any OpenClaw agent. All other skills
depend on it. If TYP is not installed, the agent has no structured way to learn or
store anything.

## Key Things the Agent Needs to Know

1. Core files contain essential global rules, durable owner facts and one short trigger plus exact reference path where needed. Detailed procedures live in the reference; read it before related actions.
2. A pointer has no minimum line count and need not repeat working instructions. Expand the reference itself when details are missing. An existing reference-index link may already make another core entry unnecessary.
3. Reuse `~/Downloads/openclaw-master-files/` on Mac or the documented persistent `/data/.openclaw/master-files/` VPS root. Resolve final paths and verify targets. Never invent duplicate master folders.
4. Search for existing knowledge before writing. Resolve stale facts and conflicting current instructions at their authoritative source; preserve useful source/history outside bootstrap.
5. Choose the single appropriate core destination. Never add learning/install receipts to MEMORY.md or parallel copies merely because multiple core files exist. Durable owner facts may still be updated where they belong.
6. Confirm what was stored, where it lives, what changed, and anything still pending. Keep this receipt out of permanent memory.
7. Current explicit owner instructions govern exceptions. Honor a deliberate storage override and coordinate any budget or watcher-baseline exception instead of silently bypassing controls.
