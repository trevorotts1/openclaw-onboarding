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
Skill: ~/.openclaw/skills/23-ai-workforce-blueprint/
Full document: ai-workforce-blueprint-full.md (66,819 chars)

Department folder rules:
- All dept folders use bare slug names (sales/, marketing/, ops/, etc.) — NO -dept suffix
- Every dept workspace gets: SOUL.md (unique), MEMORY.md (empty), HEARTBEAT.md (dept priorities), memory/ folder, plus TOOLS.md, AGENTS.md, USER.md (inherited from CEO workspace)
- Every role folder requires: 00-START-HERE.md, numbered task files (01-, 02-...), good-examples.md, bad-examples.md, tools.md
- Every workspace requires: universal-sops/00-ROUTING.md
- When routing a task: read universal-sops/00-ROUTING.md first, then go to the matching dept/role folder

Agent management:
- Every department has a permanent director (agents.list entry in openclaw.json)
- Specialists are classified as permanent (daily work, gets agents.list entry) or on-call (template only)
- Config must be backed up before ANY openclaw.json edit

Persona integration:
- Each role folder gets governing-personas.md as a REFERENCE GUIDE (not a static assignment)
- Persona selection uses 5-layer alignment at TASK level (Mission, Values, Company KPIs, Dept KPIs, Task Fit)
- persona-matching-protocol.md documents the full runtime matching process
- Dev Devil's Advocate (DA) auto-created per department using Act As If Protocol
- Persona diversity tracked in agent performance metrics

To build new dept: use build-workforce.py create_department_workspace()
To audit existing structure: trigger "Audit my AI workforce at [path]"

This skill is SEPARATE from the book-to-persona / Coaching Personas system.
Personas govern HOW an agent thinks. This blueprint governs WHERE it works and WHAT it does.
Workspace location: [fill in after build]

### Governing Personas — Update Protocol

When a new book is added to the persona library:
1. Run `python3 ~/clawd/scripts/gemini-indexer.py` to re-index the coaching-personas collection
2. Review `governing-personas.md` in each department folder for relevant departments (the new persona may be a better fit for some tasks)
3. Update persona assignments in `governing-personas.md` if the new persona is a better fit for Primary or Secondary slots
4. Update `~/clawd/ORG-CHART.md` if specialist roles or department structure changes as a result
5. Update `~/clawd/persona-matrix.md` to include the new persona in the company pool

This ensures the workforce stays current as the persona library grows.
```

---

## TOOLS.md

**Where:** Add a new section under skills or automation titled `## AI Workforce Blueprint - Scaffold Script`

**Exact text to add:**
```
## AI Workforce Blueprint - Scaffold Script
Script: ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/build-workforce.py
Run: python3 ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/build-workforce.py

Key functions:
- create_department_workspace(): builds ~/clawd/departments/[name]/ with inherited core files
- create_governing_personas_md(): maps persona-categories.json to department domain tags
- determine_specialists(): classifies roles as permanent (daily) or on-call (template)
- add_agent_to_config(): backs up config, then adds agents.list entry
- generate_org_chart(): creates ~/clawd/ORG-CHART.md
- generate_departments_json(): creates departments.json for Command Center (written to ~/Downloads/openclaw-master-files/company-discovery/departments.json)
- generate_soul_md(): creates unique SOUL.md from interview answers
- log_fallback(): tracks when clients hesitate during interview

Options:
- Option A (Full Interview): AI asks 3-7 questions per department, builds everything
- Option B (Quick Setup): uses existing workspace context + industry best practices
- Option C (Audit/Resume): scans existing folders, fills gaps, does not overwrite

Full reference: ~/.openclaw/skills/23-ai-workforce-blueprint/ai-workforce-blueprint-full.md
```

---

## MEMORY.md

**Where:** Add a new entry under installed skills or at the bottom titled `## AI Workforce Blueprint (Installed)`

**Exact text to add:**

```
## AI Workforce Blueprint (Installed [DATE])
- Skill: ~/.openclaw/skills/23-ai-workforce-blueprint/
- Workspace built at: [fill in path after build]
- Departments: [fill in after build]
- Build script: ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/build-workforce.py
- Source: Available at your onboarding package repo.
- Routing file: [workspace]/universal-sops/00-ROUTING.md
- Persona matrix: [workspace]/persona-matrix.md
- Org chart: [workspace]/ORG-CHART.md
- Command Center config: ~/Downloads/openclaw-master-files/company-discovery/departments.json
- Full blueprint: ~/.openclaw/skills/23-ai-workforce-blueprint/ai-workforce-blueprint-full.md
```

---

## AGENTS.md - Interview Resume Protocol

**Where:** Add at the bottom of AGENTS.md, after the AI Workforce Blueprint section

**Exact text to add:**
```
## 🔴 Skill 23 Interview Resume Protocol (Added with v6.1.2)
At the START of every session, check for ~/Downloads/openclaw-master-files/company-discovery/interview-handoff.md.
- If it exists and status is "in_progress": resume the interview from the next unanswered question. Do NOT start over.
- If interview-handoff.md is missing but workforce-interview-answers.md exists: reconstruct progress from the answers file, rebuild the handoff, and resume.
- If MEMORY.md says "Skill 23 Interview: IN PROGRESS" but no files exist: ask the client if they want to start fresh or tell you where they left off.
- If everything says COMPLETE: do NOT re-interview. Proceed to Skill 32.
Resume triggers: "continue", "resume", "pick up where I left off", or any message during an active interview.
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
