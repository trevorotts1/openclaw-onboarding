# CORE_UPDATES.md - AI Workforce Blueprint Skill

## Rule: Reference Only - No Full Docs in Core Files
Add concise summaries and file paths only. Never paste full documentation into core files.

---

## AGENTS.md

**Where:** Add a new section at the bottom of AGENTS.md titled `## AI Workforce Blueprint (Installed)`

**Exact text to add:**
```
## AI Workforce Blueprint (Installed)
Builds the folder and file system that turns your AI into a trained workforce.
Skill: ~/.openclaw/skills/22-ai-workforce-blueprint/
Full document: ai-workforce-blueprint-full.md (66,819 chars)

Department folder rules:
- All dept folders end with -dept (sales-dept/, marketing-dept/, ops-dept/, etc.)
- Every role folder requires: 00-START-HERE.md, numbered task files (01-, 02-...), good-examples.md, bad-examples.md, tools.md
- Every workspace requires: universal-sops/00-ROUTING.md
- When routing a task: read universal-sops/00-ROUTING.md first, then go to the matching dept/role folder

To build new dept: create [name]-dept/ folder, create role subfolders, create all 7 required files
To audit existing structure: trigger "Audit my AI workforce at [path]"

This skill is SEPARATE from the book-to-persona / Coaching Personas system.
Personas govern HOW an agent thinks. This blueprint governs WHERE it works and WHAT it does.
Workspace location: [fill in after build]
```

---

## TOOLS.md

**Where:** Add a new section under skills or automation titled `## AI Workforce Blueprint - Scaffold Script`

**Exact text to add:**
```
## AI Workforce Blueprint - Scaffold Script
Script: ~/.openclaw/skills/22-ai-workforce-blueprint/scripts/build-workforce.py
Run: python3 ~/.openclaw/skills/22-ai-workforce-blueprint/scripts/build-workforce.py
What it does: asks questions about your business, creates all dept/role folders and starter files

Options:
- Option A (automated): AI asks questions, builds everything
- Option B (manual): follow ai-workforce-blueprint-full.md step by step
- Option C (resume/audit): AI scans existing folders, fills gaps, does not overwrite

Full reference: ~/.openclaw/skills/22-ai-workforce-blueprint/ai-workforce-blueprint-full.md
```

---

## MEMORY.md

**Where:** Add a new entry under installed skills or at the bottom titled `## AI Workforce Blueprint (Installed)`

**Exact text to add:**
```
## AI Workforce Blueprint (Installed [DATE])
- Skill: ~/.openclaw/skills/22-ai-workforce-blueprint/
- Workspace built at: [fill in path after build]
- Departments: [fill in after build]
- GitHub: https://github.com/trevorotts1/openclaw-onboarding (skill 22-ai-workforce-blueprint)
- Routing file: [workspace]/universal-sops/00-ROUTING.md
- Full blueprint: ~/.openclaw/skills/22-ai-workforce-blueprint/ai-workforce-blueprint-full.md
```

---

## SOUL.md

No update required. This skill governs workspace structure, not agent personality or voice.

---

## USER.md

No update required. This skill is about workspace structure, not user preferences.

---

## IDENTITY.md

No update required.

---

## HEARTBEAT.md

**Where:** Add under Active Projects after the workforce is built.

**Exact text to add:**
```
## AI Workforce Structure - ACTIVE
Workforce folder: [path]
Departments: [list]
Routing file: [path]/universal-sops/00-ROUTING.md
All tasks route through 00-ROUTING.md before execution.
```

---

## What NOT to Add to Core Files
- Do NOT paste the full ai-workforce-blueprint-full.md into any core file
- Do NOT paste the scaffold script into core files
- Do NOT add department-specific SOPs to core files (they live in the dept folders)
- Core files get: what it is, what it does, where to find details. That is all.

---

## AGENTS.md - Pending Skill Setup Rule

**Where:** Add at the bottom of AGENTS.md

**Exact text to add:**
```
## Pending Skill Setup - Check and Remind
File: ~/.openclaw/skills/.pending-setup.md
If this file exists with entries marked Status: PENDING, proactively remind the user.
When relevant to what they are working on, say: "You have a pending skill setup for [key] - want to add that now?"
When user provides the key: save it to ~/clawd/secrets/.env and mark the entry Status: COMPLETE.
Never nag - bring it up once per session max, only when relevant.
```
