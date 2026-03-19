---
name: book-to-persona-coaching-leadership-system
description: >
  Converts any bestselling book PDF into a dual-purpose persona blueprint — one that coaches
  humans through personal and professional challenges AND governs AI agents executing professional
  work across departments. Runs a 3-phase pipeline: Kimi K2.5 extracts, DeepSeek V3.2-Speciale
  analyzes, GPT-5.3 Codex synthesizes. Output is Gemini Engine-indexed for retrieval. Uses the
  Teach Yourself Protocol before every run.
---

## MANDATORY - Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01) on this folder.**

Required read order:
1. SKILL.md (this file)
2. PIPELINE.md - the full 3-phase pipeline architecture
3. CHECKLIST.md - the 14-section persona blueprint checklist
4. GOOD-AND-BAD-EXAMPLES.md - quality standards for persona output
5. PERSONA-ROUTER.md - task-type to persona routing map
6. GEMINI-RETRIEVAL-GUIDE.md - how agents query personas at runtime
7. CORE_UPDATES.md - what to add to your workspace files
8. INSTALL.md - setup and dependencies

Do NOT run the pipeline or add any book before completing all 8 reads.
Do NOT claim the skill is installed until CORE_UPDATES.md has been applied.

# Book Intelligence Pipeline
## Bestselling Book to Coaching Framework and AI Leadership Guidance

**Version:** 1.0.0
**Owner:** [Your Name / Organization]
**Skill folder:** `~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/`
**Output destination:** Auto-detected master files folder (see INSTALL.md)

---

## Supported Input Formats

| Format | Extension | Handler |
|--------|-----------|---------|
| PDF | .pdf | pdfplumber (primary), pypdf (fallback) |
| EPUB | .epub | ebooklib (primary), Calibre (fallback) |
| MOBI | .mobi | Calibre ebook-convert |
| Kindle AZW | .azw | Calibre ebook-convert |
| Kindle AZW3 | .azw3 | Calibre ebook-convert |
| Kindle KFX | .kfx | Calibre ebook-convert |

Drop any supported format into the `books/` folder and the pipeline handles the rest.

---

## What This Skill Does

Takes any book (PDF, EPUB, MOBI, or Kindle) and produces a **dual-purpose persona blueprint** through a 3-phase sub-agent pipeline:

- **Phase 1 - Extraction** (Kimi K2.5): Reads the full book text, extracts 20 structured items across two lenses - coaching methodology and agent governance frameworks
- **Phase 2 - Analysis** (DeepSeek V3.2-Speciale): Deep analytical work across 12 dimensions including Amateur-to-Expert Gap, failure taxonomy, execution standards, decision logic
- **Phase 3 - Synthesis** (GPT-5.3 Codex via OAuth): Writes the complete 14-section persona blueprint - fully deployable for both human coaching and AI agent governance

Every persona supports:
1. **Coaching Mode** - activates when a human needs guidance through a challenge
2. **Task Mode** - activates when an AI agent needs a methodology standard for professional work

---

## Teach Yourself Protocol (MANDATORY)

Before running this skill for the first time, or after any update:

1. Read `SKILL.md` (this file) - overview and how it works
2. Read `PIPELINE.md` - the full 3-phase pipeline architecture
3. Read `CHECKLIST.md` - the 14-section persona blueprint checklist
4. Read `GOOD-AND-BAD-EXAMPLES.md` - quality standards for persona output
5. Read `PERSONA-ROUTER.md` - task-type to persona routing map
6. Read `GEMINI-RETRIEVAL-GUIDE.md` - how agents query personas at runtime
7. Read `CORE_UPDATES.md` - what to add to your workspace files
8. Read `INSTALL.md` - setup and dependencies

**Do not run the pipeline until all 8 files have been read in this session.**
Confirm by saying: "TYP complete - ready to run Book Intelligence Pipeline."

---

## When To Use This Skill

- You have a new book PDF to add to the persona library
- You want to rebuild an existing persona with updated extraction
- You are setting up the pipeline for the first time on a new workspace
- You need to add Gemini Engine indexing to an existing persona blueprint

---

## Quick Start (After TYP)

```
Run Book Intelligence Pipeline on: [book title or PDF path]
```

The skill will:
1. Locate or create the master files folder
2. Extract text from the PDF
3. Spawn Phase 1 → Phase 2 → Phase 3 sub-agents in sequence
4. Save extraction notes, analysis notes, and persona blueprint
5. Index the persona in Gemini Engine
6. Update CORE_UPDATES references in core .md files

---

## Model Routing

| Phase | Model | Route | Fallback |
|-------|-------|-------|---------|
| Phase 1 - Extraction | Kimi K2.5 | Moonshot direct API | None needed |
| Phase 2 - Analysis | DeepSeek V3.2-Speciale | OpenRouter | deepseek-reasoner (direct) |
| Phase 3 - Synthesis | GPT-5.3 Codex | OpenAI OAuth (OpenClaw) | Kimi K2.5 |

---

## Output File Structure

```
[master-files-folder]/coaching-personas/
├── books/                          ← Original PDFs (never modified)
├── text/                           ← Extracted plain text (auto-generated)
└── personas/
    └── [author-lastname]-[book-slug]/
        ├── extraction-notes.md     ← Phase 1 output
        ├── analysis-notes.md       ← Phase 2 output
        ├── persona-blueprint.md    ← Phase 3 output (the deployable persona)
        └── qmd-index/              ← Gemini Vector Database for this persona
```

---

## Full Documentation

- **How to install:** `INSTALL.md`
- **Pipeline technical reference:** `PIPELINE.md`
- **Core file updates:** `CORE_UPDATES.md`
- **Gemini Engine retrieval at runtime:** `GEMINI-RETRIEVAL-GUIDE.md`
- **Build checklist:** `CHECKLIST.md`
- **Good and bad examples:** `GOOD-AND-BAD-EXAMPLES.md`

---

## Connection to AI Workforce Blueprint (Skill 23)

**⚠️ DEPENDENCY WARNING: Skill 23 requires Skill 22 to be FULLY installed first.**

Skill 23 checks for the `coaching-personas` Gemini Vector Database before running. If not found, it stops with:
> "Install Skill 22 (Book-to-Persona) first"

These two skills are separate but work together automatically.

**If skill 23 (ai-workforce-blueprint) is installed:**
- The workforce scaffold script detects the `coaching-personas` Gemini Vector Database during build
- Each department folder gets a `governing-personas.md` showing which personas govern it
- Each role folder gets its own `governing-personas.md` for role-specific tasks
- Each `00-START-HERE.md` includes a Governing Personas section with Gemini Engine query
- Agents know: go to the right department, use the right persona

**If skill 23 is NOT installed:**
- Personas operate standalone - no department structure required
- Same persona blueprints, same Gemini Engine search, just without dept folder wiring

**Cross-reference path:** `~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/PERSONA-ROUTER.md`
