---
name: book-to-persona-coaching-leadership-system
description: >
  Converts any bestselling book PDF into a dual-purpose persona blueprint - one that coaches
  humans through personal and professional challenges AND governs AI agents executing professional
  work across departments. Runs a 3-phase pipeline with dynamic model selection via
  shared-utils/select_model.py: every phase uses the model the client selected, or the
  client's configured default model, resolved from the client's own openclaw.json. No model
  is prescribed by name. Never Anthropic. Output is Gemini Engine-indexed for retrieval.
  Wiki-enabled for unified knowledge access. Uses the Teach Yourself Protocol before every run.
---

> **Wiki Note:** This skill is integrated with the OpenClaw Memory Wiki system. All persona blueprints are searchable via `wiki_search` and `wiki_get` for unified knowledge retrieval alongside other memory sources.

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

## Prerequisites

All dependencies must be installed and verified before running the pipeline.

| Prerequisite | Required For | Install Command | Verify Command |
|--------------|--------------|-----------------|----------------|
| Python 3.8+ | Entire pipeline | `python3 --version` | `python3 --version` (should show 3.8 or higher) |
| google-genai | Gemini Engine indexing | `pip3 install google-genai` | `python3 -c "import google.genai; print('PASS')"` |
| numpy | Gemini embeddings | `pip3 install numpy` | `python3 -c "import numpy; print('PASS')"` |
| pdfplumber | PDF text extraction | `pip3 install pdfplumber` | `python3 -c "import pdfplumber; print('PASS')"` |
| pypdf | PDF fallback extraction | `pip3 install pypdf` | `python3 -c "import pypdf; print('PASS')"` |
| ebooklib | EPUB text extraction | `pip3 install ebooklib` | `python3 -c "import ebooklib; print('PASS')"` |
| aiohttp | Async HTTP for pipeline | `pip3 install aiohttp` | `python3 -c "import aiohttp; print('PASS')"` |
| beautifulsoup4 | HTML parsing for MOBI | `pip3 install beautifulsoup4` | `python3 -c "import bs4; print('PASS')"` |
| mobi | MOBI file extraction | `pip3 install mobi` | `python3 -c "import mobi; print('PASS')"` |
| lxml | XML parsing (ebooklib uses this) | `pip3 install lxml` | `python3 -c "import lxml; print('PASS')"` |
| Calibre (ebook-convert) | Kindle format conversion | Mac: `brew install --cask calibre`<br>Linux: `sudo apt-get install calibre` | `ebook-convert --version` |
| GOOGLE_API_KEY env var | Gemini Engine | Add to `secrets/.env` (in your agent workspace) | `[ -n "$GOOGLE_API_KEY" ] && echo "GOOGLE_API_KEY: SET" \|\| echo "GOOGLE_API_KEY: NOT-SET"` |
| Provider key for the resolved model's route | All phases | Depends on the resolved model (the client's choice, or the client's configured default): Ollama Cloud via `OLLAMA_API_KEY` in env or `models.providers.ollama.apiKey` in openclaw.json; OpenRouter via `OPENROUTER_API_KEY`; OAuth GPT via the OpenClaw OAuth token | `[ -n "$OLLAMA_API_KEY" ] && echo "OLLAMA_API_KEY: SET" \|\| echo "OLLAMA_API_KEY: NOT-SET"` |

> **Credential verification is presence-only.** These checks report `SET` or `NOT-SET` and emit no character of any key — the same pattern `qc-book-to-persona-coaching-leadership-system.sh` uses. Never `grep`, `echo`, `cat` or `head` a secrets file to confirm a credential: the matching line carries the value, and terminal transcripts, agent logs and shell history retain it.

**One-line install for all pip packages:**
```bash
pip3 install google-genai numpy pdfplumber pypdf ebooklib aiohttp beautifulsoup4 mobi lxml --break-system-packages
```

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

- **Phase 1 - Extraction** (model resolved at runtime: the client's choice, or the client's configured default model): Reads the full book text, extracts 30 structured items across THREE lenses — coaching methodology (1-11), agent governance frameworks (12-20), and the **Playbook Asset Lens (21-30)** that captures the book's actual reusable, swipe-able assets (headline/hook/subject formulas, funnel page recipes, scripts, frameworks, brand-voice patterns, swipe file) at full fidelity. If the resolved model fails at runtime, the selector re-runs with it excluded. Recommendation: a large-context model, because extraction passes the whole book at once.
- **Phase 2 - Analysis** (same runtime resolution as Phase 1): Deep analytical work across 13 dimensions including Amateur-to-Expert Gap, failure taxonomy, execution standards, decision logic, and Dimension 13 (Playbook Asset Inventory & Patternization) that organizes the reusable assets into clean PATTERN + worked-example form for the appendix.
- **Phase 3 - Synthesis** (same runtime resolution as Phase 1): Writes the complete 14-section persona blueprint - fully deployable for both human coaching and AI agent governance.
- **Phase 3b - Playbook Appendix** (same resolution as Phase 3): Writes a mandatory companion `PLAYBOOK-APPENDIX.md` alongside the blueprint. The blueprint DISTILLS the book; the appendix PRESERVES its reusable copy/funnel assets at full fidelity (8 sections A-H) so copy specialists write rich, brand-building copy — never the over-concise output the distilled blueprint alone produced. A quality floor is enforced in the orchestrator (fail-loud on the structure/honesty gate; one stricter retry on richness shortfall; no fabrication for thin books).

Every persona supports:
1. **Coaching Mode** - activates when a human needs guidance through a challenge
2. **Task Mode** - activates when an AI agent needs a methodology standard for professional work

Every persona ships as a PAIR of files: `persona-blueprint.md` (the distilled two-sided persona) and `PLAYBOOK-APPENDIX.md` (the full-fidelity reusable asset library).

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

- You have a new book PDF, EPUB, MOBI, AZW3, or KFX to add to the persona library
- You have a YouTube link (talk, podcast, lecture, interview) that contains the same kind of teaching as a book
- You have a local video file (seminar recording, course session, keynote)
- You have a generic web URL (article, blog post, interview transcript, sales page) — `http://` or `https://` non-YouTube
- You have already-transcribed text from any of the above
- You want to rebuild an existing persona with updated extraction
- You are setting up the pipeline for the first time on a new workspace

---

## Quick Start (After TYP) — v9.6.4+

**Single entry point: `add-persona-from-source.sh`** — routes any of the source types above to the right extractor and then through the standard 3-phase pipeline.

```bash
# Book PDF/EPUB/MOBI:
bash ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/scripts/add-persona-from-source.sh \
    --source "/path/to/Atomic Habits - James Clear.pdf"

# YouTube video (uses yt-dlp auto-subs → whisper-cpp fallback — NOT Skill 16):
bash ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/scripts/add-persona-from-source.sh \
    --source "https://youtube.com/watch?v=abc123" \
    --title "Hormozi Million Dollar Offers Talk" \
    --author "Alex Hormozi"

# Local video file (uses ffmpeg + whisper for transcript):
bash ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/scripts/add-persona-from-source.sh \
    --source "/path/to/seminar.mp4" --title "Seth Godin Keynote" --author "Seth Godin"

# Generic web URL (article, blog post, interview transcript — any http/https non-YouTube):
bash ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/scripts/add-persona-from-source.sh \
    --source "https://somesite.com/article-about-leadership" \
    --title "Leadership Article" --author "Site Author"

# Already-transcribed text:
bash ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/scripts/add-persona-from-source.sh \
    --source "/path/to/transcript.txt" --title "Foo" --author "Bar"
```

The script will:
1. Detect source type (book / YouTube / video / web URL / text)
2. Extract text via the right tool:
   - PDF books → pdfplumber (script-side pre-extraction)
   - EPUB/MOBI/AZW3/KFX books → orchestrator `extract_book_text()` (ebooklib for EPUB, mobi lib for MOBI, Calibre for AZW/AZW3/KFX)
   - YouTube → yt-dlp auto-subs (free/fast); falls back to yt-dlp audio + whisper-cpp
   - Local video → ffmpeg audio extract → whisper-cpp transcript
   - Generic web URL → curl download + BeautifulSoup HTML→text
   - Text/MD → copied directly
3. Drop the text into the persona library and register a `source.json` marker
4. Invoke Skill 22's 3-phase pipeline (Extraction → Analysis → Synthesis)
5. Re-index Gemini Engine so the new persona is immediately searchable
6. Add an entry to `persona-categories.json` with auto-classified `domain[]`/`perspective[]` tags (keyword-based, instant, no LLM required)

**Dependencies for non-book sources:**
- YouTube: `yt-dlp` (auto-installed by install.sh). Uses yt-dlp auto-subs (free, no API key) first; falls back to yt-dlp audio + whisper-cpp transcription. Skill 16 is NOT used.
- Video: `ffmpeg` + `whisper-cpp` (or `whisper`). Mac: `brew install ffmpeg whisper-cpp`. Linux: `apt install ffmpeg` + `pip3 install openai-whisper`. Auto-installed by install.sh v10.14.32+.

---

## Model Routing

**All model selection runs through `shared-utils/select_model.py`. The model for every phase is the one the client selected, or the client's configured default model, resolved by the selector from the client's own `openclaw.json`. No model is prescribed by name or family in this skill. See `PIPELINE.md` for the full resolution contract.**

**Per-phase resolution:**

| Phase | Model |
|-------|-------|
| Phase 1 - Extraction | The client's choice, or the client's configured default model |
| Phase 2 - Analysis | The client's choice, or the client's configured default model |
| Phase 3 - Synthesis | The client's choice, or the client's configured default model |
| Phase 3b - Playbook Appendix | Same resolution as Phase 3 |

**Recommendations (guidance only - the client's selection always wins):**
- Prefer a model with a large context window for Phases 1 and 2, because extraction and analysis pass whole books and full extraction notes at once; a small-window model forces chunking and loses cross-chapter patterns.
- Prefer a subscription-billed route over per-token billing where the client has one, because per-book cost stays flat instead of scaling with book length.
- Prefer the same model via a direct route over an aggregator route when both are configured, because the direct route is usually cheaper for the identical model.

**ABSOLUTE RULES (enforced by the selector):**
- Anthropic models (`anthropic/claude-*`) are FORBIDDEN by policy. Hardcoded filter at every step.
- If nothing is configured, the selector stops and asks the owner which model to use. It never silently substitutes a model the client did not choose or configure.
- The selector reads the client's actual `openclaw.json`. When the client configures a newer model, it is picked up automatically - no code change needed.
- Runtime fallback: if the resolved model fails mid-run, the selector re-runs with the failed model excluded and resolves the next model from the client's remaining configured models.

---

## Output File Structure

```
[master-files-folder]/coaching-personas/
├── books/                          <- Original PDFs (never modified)
├── text/                           <- Extracted plain text (auto-generated)
└── personas/
    └── [author-lastname]-[book-slug]/
        ├── extraction-notes.md     <- Phase 1 output (30 items incl. Playbook Asset Lens 21-30)
        ├── analysis-notes.md       <- Phase 2 output (13 dimensions incl. Asset Inventory)
        ├── persona-blueprint.md    <- Phase 3 output (the deployable two-sided persona)
        ├── PLAYBOOK-APPENDIX.md    <- Phase 3b output (MANDATORY companion: full-fidelity reusable asset library)
        └── google-embedding-index/              <- Gemini Engine index for this persona
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

**WARNING: Skill 23 requires Skill 22 to be FULLY installed first.**

Skill 23 checks for the `coaching-personas` Gemini Engine collection before running. If not found, it stops with:
> "Install Skill 22 (Book-to-Persona) first"

These two skills are separate but work together automatically.

**If skill 23 (ai-workforce-blueprint) is installed:**
- The workforce scaffold script detects the `coaching-personas` Gemini Engine collection during build
- Each department folder gets a `governing-personas.md` showing which personas govern it
- Each role folder gets its own `governing-personas.md` for role-specific tasks
- Each `00-START-HERE.md` includes a Governing Personas section with Gemini Engine query
- Agents know: go to the right department, use the right persona

**If skill 23 is NOT installed:**
- Personas operate standalone - no department structure required
- Same persona blueprints, same Gemini Engine search, just without dept folder wiring

**Categorization:**
Every persona is registered in `persona-categories.json` after generation with:
- A stub `domain: []` array (MUST be filled manually — see PERSONA-ROUTER.md §Domain Tags)
- A stub `perspective: []` array (fill manually)
- `author`, `book`, `source_type`, `added` fields (auto-populated)
The dept-scope filter in Skill 23 reads `domain` and `perspective` — until those arrays
are filled, the persona will NOT appear in dept-scoped candidate pools. Run Skill 22,
then open `persona-categories.json` and fill in the tags for the new persona.

**Cross-reference path:** `~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/PERSONA-ROUTER.md`

---

---

## Self-Service: Add a Book Persona After Build (§1.5)

**After a persona is created, you MUST verify domain/perspective tags are non-empty, then run converge to push it into dept routing + the CC dashboard.**

### Add a Book/Video Persona

When the owner says "add a book persona named after `<Author>`" or "add `<Title>` as a coaching persona":

```bash
# 1. Add the persona from source (book PDF, video, etc.)
bash 22-book-to-persona-coaching-leadership-system/scripts/add-persona-from-source.sh --source <path-or-url> \
  [--title "<Book Title>"] [--author "<Author Name>"]

# 2. REQUIRED: Verify domain and perspective tags are non-empty
#    Open persona-categories.json and fill in the tags for the new persona.
#    Until these are filled, the persona is NOT routable (visible in CC with
#    needs_tags=true flag; excluded from dept candidate pools).

# 3. Run converge (MANDATORY closing step — never skip)
bash 32-command-center-setup/scripts/sync-extensions.sh --converge
```

**Tag requirement (§1.7):** domain[] and perspective[] must both be non-empty before the persona appears as routable in the CC dashboard. Converge writes untagged personas to `extension-sync/needs-tags.json` and surfaces them in the Telegram summary. After hand-tagging, re-run converge to clear the flag.

<!-- BREADCRUMB: memory-surgery/skill-22-mac | 2026-04-12 | v6.5.7 | Added wiki note, memory system verified -->
<!-- SKILL.md updated: Added Self-Service Add-and-Wire persona section (§1.5) -->
