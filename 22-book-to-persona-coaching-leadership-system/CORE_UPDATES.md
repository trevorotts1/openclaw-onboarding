# CORE_UPDATES.md - Book-to-Persona Skill

## Rule: Reference Only - No Full Docs in Core Files
Add concise summaries and file paths only. Never paste full documentation into core files.

---

## Quick Reference - Dependency Installation

**One-line install for all Python packages:**
```bash
pip3 install google-genai numpy pdfplumber pypdf ebooklib aiohttp beautifulsoup4 mobi lxml --break-system-packages
```

**Verify all packages:**
```bash
python3 -c "import google.genai, numpy, pdfplumber, pypdf, ebooklib, aiohttp, bs4, mobi, lxml; print('ALL PASS')"
```

---

## AGENTS.md

**Where:** Add a new section at the bottom of AGENTS.md titled `## Book-to-Persona Skill (Installed)`

**Exact text to add:**
```
## Book-to-Persona Skill (Installed)
Converts any book (PDF/EPUB/MOBI/AZW3) into a dual-purpose persona blueprint.
Pre-built personas already included. Run: python3 ~/.openclaw/workspace/scripts/gemini-indexer.py --status to see total count. Pipeline runs on new books only.

Pipeline (model selection is DYNAMIC via shared-utils/select_model.py — Anthropic FORBIDDEN):
- Phase 1: Latest Kimi (Ollama Cloud preferred) → OpenRouter Kimi → OAuth GPT → DeepSeek V4+ → ask owner. Temperature 1.0. → extraction-notes.md
- Phase 2: Same Kimi-first chain as Phase 1 (was hardcoded deepseek/deepseek-v3.2 prior to v9.5.0). → analysis-notes.md
- Phase 3: OAuth GPT preferred → latest Kimi fallback. → persona-blueprint.md (all 14 sections)
- Runtime fallback: selector re-runs with failed model excluded, walks down tier list. Never selects Anthropic.

Persona Reflex (MANDATORY for every professional / non-mechanical task — not optional):
A persona blueprint is DUAL-PURPOSE. The Coaching half guides conversation; the LEADERSHIP / Task-Mode
half (Section 4 "Agent Governance Framework" + Section 7B Task-Mode Triggers) GOVERNS HOW WORK IS BUILT.
At task time you MUST load and APPLY the leadership/Task-Mode half — naming the persona is NOT enough.

1. SEARCH — run: python3 ~/.openclaw/workspace/scripts/gemini-search.py "<task keywords>"
   For the governance/standard (not the coaching voice), add: --mode leadership
2. LOAD THE TASK MODE — open the matched persona's persona-blueprint.md and read its Section 4
   (4A Execution Standard + Decision Logic Table, 4B Quality Control Protocol + Definition of Done,
   4C Failure Pattern Recognition, 4D Task Mode Activation Language) AND Section 7B Task-Mode Triggers.
   The persona NAME alone does not load the Task Mode — the Section-4 governance is what you build to.
3. EXECUTE TO STANDARD — perform the task THROUGH that methodology: apply the decision-logic rules,
   meet the Definition of Done, and steer clear of the documented failure patterns. Build to standard,
   do not merely echo the persona's voice.
4. VERIFY — before reporting done, self-check the output against the persona's Definition of Done and
   failure-pattern table (per persona-matching-protocol.md "Post-Task Persona Verification").
Skip ONLY if the user explicitly says so, or for purely mechanical tasks (no judgment/build involved).

Key paths:
- Skill: ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/
- Personas: ~/Downloads/openclaw-master-files/coaching-personas/personas/
- Router: ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/PERSONA-ROUTER.md
- Orchestrator: ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/pipeline/orchestrator.py
- Gemini Vector Database: coaching-personas [run: python3 ~/.openclaw/workspace/scripts/gemini-indexer.py --status to get current counts]

To add a new book: follow SOP in MEMORY.md under "Add New Book to Coaching Personas Matrix"

Re-indexing trigger (MANDATORY after adding any new persona):
When a new book persona is added to ~/Downloads/openclaw-master-files/coaching-personas/personas/:
Run: python3 ~/.openclaw/workspace/scripts/gemini-indexer.py
This updates the Gemini embedding index with the new persona.
Do NOT skip this step -- the search will not find the new persona until re-indexed.
```

---

## TOOLS.md

**Where:** Add a new section under model routing titled `## Book-to-Persona - Model Routing and Gemini Engine`

**Exact text to add:**
```
## Book-to-Persona - Model Routing and Gemini Engine
Pipeline model routing (DYNAMIC selection via shared-utils/select_model.py — never hardcoded):
- Phase 1: latest Kimi (Ollama Cloud preferred) → OpenRouter Kimi → OAuth GPT → DeepSeek V4+. Temperature 1.0.
- Phase 2: same Kimi-first chain as Phase 1. (Was hardcoded deepseek/deepseek-v3.2-speciale prior to v9.5.0.)
- Phase 3: OAuth GPT preferred (subscription, no per-call cost) → latest Kimi fallback.
- Runtime fallback: selector re-runs with failed model excluded.
- ABSOLUTE: Anthropic models (anthropic/claude-*) are FORBIDDEN. Filter applied at every tier.
- Auto-adapts: when client adds a new Kimi or GPT version, selector picks the higher number automatically.

Gemini Vector Database: coaching-personas
Setup commands (run once on fresh install):
  python3 ~/.openclaw/workspace/scripts/gemini-indexer.py
  # Handled by gemini-indexer.py  (takes 3-8 min first time, downloads local model, runs offline after)

Runtime query: python3 ~/.openclaw/workspace/scripts/gemini-search.py "<task keywords>"
After adding new book: python3 ~/.openclaw/workspace/scripts/gemini-indexer.py (no need to re-embed everything)
If stale/broken: python3 ~/.openclaw/workspace/scripts/gemini-indexer.py --rebuild && python3 ~/.openclaw/workspace/scripts/gemini-indexer.py

Full pipeline reference: ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/PIPELINE.md
Full Gemini Engine guide: ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/GEMINI-RETRIEVAL-GUIDE.md
```

---

## MEMORY.md

**Where:** Add a new entry under installed skills or at the bottom titled `## Book-to-Persona Persona Library`

**Exact text to add:**
```
## Book-to-Persona Persona Library (Installed [DATE])
- Skill: ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/
- Pre-built personas (see python3 ~/.openclaw/workspace/scripts/gemini-indexer.py --status for count): ~/Downloads/openclaw-master-files/coaching-personas/personas/
- Gemini Vector Database: coaching-personas [run: python3 ~/.openclaw/workspace/scripts/gemini-indexer.py --status to get current counts]
- Source: Available at your onboarding package repo.
- Persona Reflex: query Gemini Engine before every professional task (see AGENTS.md)
- Add new book SOP: see "Add New Book to Coaching Personas Matrix" section in this file
```

---

## SOUL.md

**Where:** Add under the Boundaries section

**Exact text to add:**
```
## Persona Coaching Voice Rule (Added [DATE])
When operating through a persona from the book-to-persona library:
- NEVER use the author's name in the coaching voice
- The author's name appears ONLY inside attribution-flagged direct quotes
- Coaching Mode speaks in the methodology's voice, not the author's identity
- Example: Do not say "As Mel Robbins says..." - say "The 5-second countdown works because..."
```

---

## USER.md

No update required. This skill does not change anything about how you interact with the user directly.

---

## IDENTITY.md

No update required unless you are setting up a persona as your primary operating identity.

---

## HEARTBEAT.md

**Where:** Add under Active Capabilities if this section exists, otherwise skip.

**Exact text to add:**
```
## Persona Reflex - ACTIVE (MANDATORY before professional tasks)
Gemini Vector Database coaching-personas loaded [run: python3 ~/.openclaw/workspace/scripts/gemini-indexer.py --status to get current counts].
Before professional tasks: python3 ~/.openclaw/workspace/scripts/gemini-search.py "<task>" [--mode leadership]
→ open matched persona-blueprint.md → load Section 4 Task Mode (Execution Standard + Definition of Done + failure patterns) → build to that standard → verify against the Definition of Done.
```

---

## What NOT to Add to Core Files
- Do NOT paste PIPELINE.md into AGENTS.md
- Do NOT paste prompt templates into TOOLS.md
- Do NOT paste the 14-section blueprint format into any core file
- Do NOT add API keys to core files
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
When user provides the key: save it to ~/.openclaw/workspace/secrets/.env and mark the entry Status: COMPLETE.
Never nag - bring it up once per session max, only when relevant.
```
