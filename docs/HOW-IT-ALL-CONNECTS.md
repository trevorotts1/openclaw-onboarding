# HOW IT ALL CONNECTS: The Zero-Human Company Build Chain

**Version:** v10.15.49
**Last updated:** 2026-06-06
**Sourced from:** Skill 22 SKILL.md + GEMINI-RETRIEVAL-GUIDE.md, Skill 23 SKILL.md + INSTRUCTIONS.md, Skill 31 SKILL.md + INSTRUCTIONS.md, Skill 32 SKILL.md, and the committed graphify knowledge map at `graphify-out/` (built from commit `8e664a85`).

---

## The One-Line Summary

A client interview (Skill 23) is the single source of truth that drives role and department creation. Those roles pull coaching methodology from a persona library (Skill 22). The built workforce is remembered across sessions via an 8-layer memory system (Skill 31). The live dashboard (Skill 32) surfaces everything as a real, operating company.

This document explains **why each system exists, what data flows between them, and which connections are non-obvious**.

---

## System Roles

### Skill 22 — Book-to-Persona Coaching Leadership System
**What it is:** A 3-phase pipeline that converts any book (PDF/EPUB/MOBI/video transcript) into a dual-purpose persona blueprint. Each blueprint serves two modes simultaneously:
- **Coaching Mode** — activates when a human needs guidance through a challenge
- **Task Mode** — activates when an AI agent needs a methodology standard for professional work

**What it produces:**
- `persona-blueprint.md` — 14-section deployable document per book (extraction notes → analysis notes → synthesis)
- `persona-categories.json` — machine-readable registry of every persona with 12 domain tags (Marketing, Sales, Leadership, Finance, Operations, Communication, Copywriting, Mindset, Productivity/Systems, Coaching, Strategy/Innovation, Personal Development) and 6 perspective tags (African American experience, Women's challenges, etc.)
- A Gemini Embedding 2 index (`coaching-personas` collection) — the semantic search layer that lets any agent pull the exact methodology section they need without loading entire blueprints into context

**Source:** Skill 22 SKILL.md lines 86-97; GEMINI-RETRIEVAL-GUIDE.md lines 1-15.

---

### Skill 23 — AI Workforce Blueprint
**What it is:** The single build skill that interviews the client and creates their entire AI company. It consolidates what were formerly three separate skills (23, 33-Department-Heads, 34-Intelligent-Staffing) into one unified flow.

**What it produces:**
- `workforce-interview-answers.md` — permanent record of every client answer (the canonical source of truth for the entire build)
- `interview-handoff.md` — progress tracker enabling interview resume across sessions, gateway restarts, and context resets
- Department workspace folders for 16+ canonical departments (each with unique SOUL.md, MEMORY.md, HEARTBEAT.md, plus inherited TOOLS.md, AGENTS.md, USER.md)
- Role-library files (130-200 `how-to.md` documents in `templates/role-library/<dept>/<slug>.md`) instantiated from templates
- SOP library (standardized operating procedure blocks under each role)
- `governing-personas.md` per department — the pre-qualified persona pool for that department's work
- `departments.json` — the config the Command Center dashboard reads directly
- `company-config.json` and `department-config.json` per department
- `ORG-CHART.md` — the visual org structure
- Devil's Advocate agent in every department (auto-created, never mentioned to the client)

**Source:** Skill 23 SKILL.md lines 63-111; INSTRUCTIONS.md lines 1-30.

---

### Skill 31 — Upgraded Memory System
**What it is:** An 8-layer memory architecture that makes every agent in the workforce genuinely persistent across sessions, gateway restarts, and context compaction events.

**The 8 layers and their purpose:**

| Layer | Technology | What It Solves |
|-------|-----------|----------------|
| 1 | Markdown files (MEMORY.md + daily logs) | Permanent on-disk source of truth |
| 2 | Memory flush (custom capture prompt) | Prevents important context from being lost on compaction |
| 3 | Session indexing | Makes past conversations searchable by topic, not just today |
| 4 | **Gemini Embedding 2** | Finds information by meaning (semantic search), not keyword |
| 5 | memory-core plugin (autoCapture + autoRecall) | Native OpenClaw auto-capture; survives compaction without manual intervention |
| 6 | Cognee graph | Connects facts, people, and projects in a graph database for complex relational queries |
| 7 | Obsidian Vault | Structured knowledge base with wikilinks and frontmatter for browsing |
| 8 | Active Memory + Wiki System | Unified structured knowledge store; wiki pages searchable via `wiki_search` + `wiki_get` |

**What it produces (relevant to the workforce build):**
- Memory embeddings indexed via Gemini Embedding 2 for every department agent's knowledge base
- Wiki pages per department: persona matrix, governing personas, interview answers, daily session logs
- Persistent department-agent memory that survives the client's Mac mini going to sleep or the gateway restarting

**Source:** Skill 31 SKILL.md lines 67-78; INSTRUCTIONS.md lines 1-15.

---

### Skill 32 — Command Center Setup
**What it is:** The activation phase. Takes the blueprint Skill 23 produced and makes it real: persistent agents, a Telegram control room organized by department topics, and a Kanban dashboard at `localhost:4000`.

**What it produces:**
- One persistent OpenClaw agent per department, each bound to its department workspace
- A Telegram supergroup with one topic per department (each topic wired to the correct agent)
- A Cross-Department topic for interdepartmental coordination
- The visual Kanban dashboard (Next.js, port 4000) with 5 columns: Backlog / Ready / In Progress / Review / Complete
- 3-check daily standup cadence (9 AM / 1 PM / 5 PM) running autonomously

**Source:** Skill 32 SKILL.md lines 25-49; 63-100.

---

## The End-to-End Data Flow

```
[Client's Business]
       |
       v
PHASE 0: Pre-interview research
  - Skill 23 fetches URLs, parses LinkedIn/YouTube/uploaded docs
  - Writes pre-interview-research.md with Mission/Industry/Brand/Audience
  - Research proposes context; client must confirm every answer (never auto-accepted)
       |
       v
SKILL 23 INTERVIEW (~30 questions, Katie Couric/Oprah style)
  - Answers written to workforce-interview-answers.md IMMEDIATELY after each answer
  - Progress tracked in interview-handoff.md (enables resume across gateway restarts)
  - MEMORY.md updated with a single living progress line
  - build-state JSON updated via update-interview-state.sh (resume cron reads this)
       |
       v
ROLE LIBRARY INSTANTIATION (gated — build does not complete until this passes)
  - Templates pulled from 23-ai-workforce-blueprint/templates/role-library/<dept>/<slug>.md
  - Token-personalized copies written to each department workspace (130-200 files)
  - SOPs authored in each role file under "### SOP 9.x" blocks
  - State fields roleLibraryStatus / sopLibraryStatus tracked
  - scripts/verify-library-gate.sh must exit 0 before buildCompletedAt is written
       |
       v
PERSONA ASSIGNMENT (uses Skill 22's output)
  - Skill 23 checks for the coaching-personas Gemini Engine collection
  - Reads persona-categories.json to build department-specific pools (domain tag filter)
  - Runs 5-layer alignment per department:
      Layer 1: Company Mission alignment
      Layer 2: Owner Values alignment
      Layer 3: Company Goals/KPIs
      Layer 4: Department Goals/KPIs
      Layer 5: Task-type fit
  - Layers 1-2 run once at setup (pre-qualified pool written to governing-personas.md)
  - Layers 3-5 re-run fresh at task time
  - "Act as if you are [persona] executing this task" instruction written to each workspace
       |
       v
DEPARTMENT WORKSPACE CREATION
  - One folder per department under ~/.openclaw/workspace/departments/<dept>/
  - Unique files: SOUL.md (generated from interview answers), MEMORY.md, HEARTBEAT.md, memory/
  - Inherited files: TOOLS.md, AGENTS.md, USER.md (copied from main CEO workspace)
  - governing-personas.md (pre-qualified persona pool for this department)
  - devils-advocate/ subfolder (DA config + challenge questions, auto-created)
  - specialists/: full-time roles get workspace + agents.list entry; on-call roles get subagent template only
       |
       v
CONFIG FILES WRITTEN FOR COMMAND CENTER (Skill 32 reads these)
  - departments.json: which departments exist, their names, emoji, head titles
  - company-config.json: company KPIs, industry, connected systems
  - department-config.json per department: department KPIs, specialist assignments
  - ORG-CHART.md: organizational structure
  - persona-matrix.md: which personas are available and pre-qualified across the company
       |
       v
SKILL 31 MEMORY ACTIVATION (runs alongside the workforce build)
  - Gemini Embedding 2 indexes every persona blueprint (coaching-personas collection)
  - Also indexes department workspace markdown (department agent knowledge bases)
  - memory-core plugin auto-captures interview decisions into persistent memory
  - Wiki pages created: Company Org Chart, Department Config, Persona Matrix,
    Governing Personas, Interview Answers, Interview Handoff
  - Department agents get autoCapture:true + autoRecall:true in their agent config
       |
       v
SKILL 32 ACTIVATION (runs after Skill 23 is complete)
  - Reads departments.json, company-config.json, department-config.json
  - Creates one persistent OpenClaw agent per department (agents.list entries in openclaw.json)
  - Creates Telegram supergroup + one topic per department + Cross-Department topic
  - Binds each topic to its department agent
  - Starts the Next.js Kanban dashboard (PM2 on port 4000)
  - Configures 3-check standup cadence (cron at 9 AM / 1 PM / 5 PM)
       |
       v
SKILL 38 COMMS-AUTOMATION HANDOFF (enforced gate, not optional prose)
  - If Skill 23 built a Communications, Sales, or Customer-Support department,
    commsAutomationStatus gate must pass before buildCompletedAt
  - Skill 38 scaffolds conversational automations + GHL Build-with-AI prompts
  - Starting point: appointment booking playbook
       |
       v
LIVE OPERATION: PERSONA RETRIEVAL AT RUNTIME
  - Department agent receives a task (e.g., "Write a sales email campaign")
  - Routing engine matches task type to persona category (using domain tags from persona-categories.json)
  - Agent queries gemini-search.py with the task description
  - Gemini Embedding 2 returns the most semantically relevant sections from matching persona blueprints
  - Agent executes: "Act as if you are [Alex Hormozi / Seth Godin / Chris Voss] executing this task"
  - Self-review runs against the non-negotiable execution rules returned by Gemini Engine
```

---

## The Non-Obvious Connections

These are the data dependencies that are easy to miss and cause silent failures when skipped.

### 1. Skill 22 must exist BEFORE Skill 23 runs persona assignment
Skill 23 checks for the `coaching-personas` Gemini Engine collection at build time. If the collection is absent, persona assignment is skipped and the workforce builds without coaching governance. This is recoverable (Option C — Audit/Resume Mode can wire personas in later), but only if Skill 22 is installed and re-indexed first.

**Source:** Skill 23 SKILL.md lines 394-399; Skill 22 SKILL.md lines 229-255.

### 2. persona-categories.json is the bridge between Skill 22 and Skill 23
Every persona blueprint Skill 22 generates gets a stub entry in `persona-categories.json` with domain tags and perspective tags. Skill 23 reads this file to build department-specific persona pools (a marketing task filters to Marketing-tagged personas only, never Finance personas). Without this file, persona assignment degrades to searching all 40+ blueprints on every task — expensive and inaccurate.

**Source:** Skill 23 SKILL.md lines 95-100; graphify nodes from `22-book-to-persona-coaching-leadership-system/persona-categories.json`.

### 3. Skill 32 reads config files Skill 23 writes — not the workspace directly
The Command Center dashboard does NOT scan department folders. It reads specific JSON config files Skill 23 generates: `departments.json`, `company-config.json`, per-department `department-config.json`. If a department is added later without regenerating these files, it will not appear in the dashboard even though the workspace folder exists.

**Source:** Skill 23 SKILL.md lines 102-110; Skill 32 SKILL.md lines 25-49.

### 4. Skill 31's Gemini Embedding 2 serves TWO separate indexes
Layer 4 (Gemini Embedding 2) is used in two distinct ways that share the same infrastructure:
- **Persona retrieval** (Skill 22's `coaching-personas` collection) — for finding the right methodology at task time
- **Department agent knowledge** (each agent's own indexed markdown) — for agents to recall facts, decisions, and SOPs from their own department history

Both use the same `gemini-indexer.py` / `gemini-search.py` scripts, but they query different collections. Adding a new persona blueprint requires re-indexing the `coaching-personas` collection; adding new department content requires re-indexing that department's collection.

**Source:** Skill 31 SKILL.md lines 67-78; Skill 22 GEMINI-RETRIEVAL-GUIDE.md lines 1-50.

### 5. The role library and SOP library are GATED — interview alone is not enough
A common misread: "the interview is done, so the workforce is done." It is not. The build state machine requires both `roleLibraryStatus` and `sopLibraryStatus` to be populated before `buildCompletedAt` is written and before ZHC closeout fires. The resume cron fires `[LIBRARY-RESUME]` ticks until both gates pass. Skill 32 activation should not proceed until the library gate passes (`scripts/verify-library-gate.sh` exits 0).

**Source:** Skill 23 SKILL.md lines 73-75.

### 6. Persona assignment is per-TASK, not per-role — the governing-personas.md is a pool, not a fixed assignment
The `governing-personas.md` file in each department workspace is a PRE-QUALIFIED POOL, not a static assignment. At task time, Skill 23's persona-matching-protocol runs Layers 3-5 fresh against the pool. A Marketing Director might run Seth Godin for content strategy, Gary Vee for social media, and Alex Hormozi for a lead magnet — different personas for different tasks, all from the same pre-qualified pool.

**Source:** Skill 23 SKILL.md lines 157-173.

### 7. The Devil's Advocate also uses the persona system — and rotates personas per challenge
Every department's DA selects a persona through the same 5-layer alignment for EACH challenge it issues. The DA is not a mechanical critic — it reasons AS a persona (Jim Collins for "Is this good enough?", Mike Michalowicz for "Where is the profit?"). This means Skill 22 blueprints directly govern QA behavior inside each department, not just creative execution.

**Source:** Skill 23 SKILL.md lines 326-335.

### 8. Memory wiki pages are the connective tissue between all four skills
When all four skills are installed and running, the wiki system (Skill 31 Layer 8) holds structured pages that span the entire build:
- Persona matrix (from Skill 22 + Skill 23)
- Governing personas per department (from Skill 23)
- Interview answers with provenance (from Skill 23)
- Department configs and KPIs (from Skill 23 + Skill 32)
- Daily session logs per department agent (from Skill 32 ongoing operation)

Any agent across any department can query `wiki_search` or `wiki_get` to access this shared knowledge base. This is the mechanism that prevents departments from operating in silos — the marketing director and finance director share the same wiki, and can query each other's published SOPs.

**Source:** Skill 23 SKILL.md lines 401-431; Skill 31 SKILL.md lines 67-78; Skill 22 GEMINI-RETRIEVAL-GUIDE.md lines 201-250.

---

## What Still Grows — Known Gaps (as of graphify map commit 8e664a85)

The graphify semantic layer has 45,052 nodes and 44,718 edges extracted from the repo. The graph's BFS traversal confirms that the `persona-categories.json` ↔ `departments.json` ↔ `department-config.json` data edges are **structurally present** in the repo but are **runtime-written** (not static files), so they do not appear as explicit graph edges. The connections in this document are sourced directly from the skill files rather than from graphify path queries.

If you run `graphify update .` after a live workforce build (where those JSON files actually exist on disk), the graph will materialize those edges and you can use `graphify path "departments.json" "command-center-setup/SKILL.md"` to verify them directly.

Areas where a re-run of graphify after a real client build would add edges:
- `workforce-interview-answers.md` → role-library instantiation
- `departments.json` → Command Center dashboard consumption
- `governing-personas.md` → per-department task execution
- Daily memory logs → Gemini Embedding 2 index

---

## Quick Reference: Skill Dependency Order

```
Skill 22 (Book-to-Persona)        ← Can run independently; must be done BEFORE Skill 23 for persona wiring
    ↓
Skill 31 (Memory System)           ← Install in parallel with 22; required for persistent department agents
    ↓
Skill 23 (AI Workforce Blueprint)  ← Requires 22's Gemini collection; produces all config files
    ↓
Skill 32 (Command Center)          ← Reads Skill 23's config files; activates the live workforce
    ↓
Skill 38 (Conversational AI)       ← Enforced handoff gate for Comms/Sales/Support departments
```

---

*Doc generated from skill files + graphify map. To enrich with runtime-materialized edges, run `graphify update .` from the repo root after a live client workforce build.*
