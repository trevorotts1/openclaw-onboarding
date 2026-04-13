# PIPELINE.md - Full Technical Reference
## Book Intelligence Pipeline - 3-Phase Sub-Agent Architecture

---

## Architecture Overview

```
PDF → Text Extraction (pdfplumber, free) → .txt file
                                              ↓
                              Phase 1: Model fallback chain (Extraction)
                              → MiMo V2 Pro (OpenRouter, 1M ctx) preferred
                              → Kimi K2.5 (Moonshot, 262K ctx) fallback
                              → GPT 5.4 (Codex OAuth, 196K ctx) fallback
                                    ↓ extraction-notes.md
                              Phase 2: deepseek/deepseek-v3.2 via OpenRouter (Analysis)
                                    ↓ analysis-notes.md
                              Phase 3: openai-codex/gpt-5.4 via OAuth (Synthesis) ← fallback: kimi-k2.5
                                    ↓ persona-blueprint.md
                              Gemini Engine Indexing
                                    ↓ searchable via Gemini semantic search
```

---

## Pre-Processing: PDF Text Extraction

**Tool:** pdfplumber (Python library)
**Cost:** Zero - runs locally, no API calls
**Time:** 5-200 seconds per book depending on size
**Output:** Plain .txt file saved to `[master-files]/coaching-personas/text/`

```python
import pdfplumber
with pdfplumber.open(pdf_path) as pdf:
    text = ""
    for page in pdf.pages:
        t = page.extract_text()
        if t:
            text += t + "\n"
```

Run all books in parallel using ThreadPoolExecutor for maximum speed.

---

## Phase 1 - Extraction (Model Fallback Chain)

**Model priority (try in order):**
1. `kimi-k2.5` via OpenRouter (262K context, 96K max output) - PREFERRED
2. `xiaomi/mimo-v2-pro` via OpenRouter (1M context, 131K max output) - fallback
3. `openai-codex/gpt-5.4` via OpenClaw OAuth (196K context) - if Codex active
4. `google/gemini-3.1-pro-preview` via OpenRouter (1M context, 65K max output)

**Which model to use:** The agent checks which API keys are available during Step 4 of INSTALL.md and uses the first available model from the priority list.

**Temperature:** 1.0 (MUST be exactly 1.0)
**Prompt:** agent-prompts/extraction-agent-prompt.md

**What it extracts (20 items):**
- Coaching lens (items 1-11): Author background, central problem, root cause, full methodology,
  principles, transformation arc, coaching questions, tools/exercises, objection handling,
  author voice, direct quotes
- Governance lens (items 12-20): Execution system, quality bar, non-negotiable rules,
  failure patterns, decision logic, self-review protocol, definition of done,
  amateur-to-expert gap, professional application

**Input to sub-agent:**
- Full content of extraction-agent-prompt.md (system instructions)
- Full book text (up to 200,000 characters)

**Output:** extraction-notes.md saved to persona folder

**Large book handling:**
- Books over 200,000 characters: pass first 200,000 chars (covers most books)
- Kimi's 262K context window safely handles this with room for the system prompt

---

## Phase 2 - Analysis (DeepSeek V3.2)

**Model:** `deepseek/deepseek-v3.2` (via OpenRouter)
**Route:** `https://openrouter.ai/api/v1/chat/completions`
**API Key:** `OPENROUTER_API_KEY` in `secrets/.env` (in your agent workspace)
**OpenRouter model ID:** `deepseek/deepseek-v3.2` or `openrouter/deepseek/deepseek-v3.2`
**Context:** 128K tokens
**Max output:** 8K tokens
**Prompt:** agent-prompts/analysis-agent-prompt.md
**Cost estimate:** ~$0.30-0.80 per book
**Expected output:** `analysis-notes.md` (3,000+ characters)

**What it analyzes (12 dimensions):**
1. True operating system (mechanism behind the methodology)
2. Root cause architecture (chain from symptom to root)
3. Amateur-to-Expert Gap (most critical - minimum 5 dimensions)
4. Failure pattern taxonomy (categorized by type)
5. Execution standard (pre-work, during, checkpoints, rules, definition of done)
6. Decision logic framework (minimum 8 decision rules)
7. Coaching framework architecture (3 phases with questions)
8. Voice and language architecture (10 overused words, 10 never-used words)
9. Scope and boundary analysis (where methodology ends)
10. Department and role application map
11. Routing intelligence (15 keyword triggers, scoring logic)
12. The single most important non-obvious insight

**Input to sub-agent:**
- Full content of analysis-agent-prompt.md
- Full extraction-notes.md content

**Chunking (for large extraction notes over 120K chars):**
- Split into overlapping chunks (3K char overlap)
- Analyze each chunk separately
- Final synthesis pass merges chunk analyses

**Output:** analysis-notes.md saved to persona folder

---

## Phase 3 - Synthesis (GPT-5.4 Codex + Fallback)

**PRIMARY Model:** `openai-codex/gpt-5.4` (via OpenAI OAuth)
**Route:** OpenClaw OAuth (ChatGPT subscription - NOT API key)
**API Type:** OpenAI Responses API (`/v1/responses`)
**Context:** 1M tokens (2x pricing past 272K context)
**Max output:** 128K tokens
**Prompt:** agent-prompts/synthesis-agent-prompt.md
**Cost estimate:** ~$2-5 per book (varies by length and context window used)
**Expected output:** `persona-blueprint.md` (10,000+ characters, all 14 sections)

**FALLBACK Model:** `kimi-k2.5` via Moonshot API
**Fallback triggers (ANY of these):**
- API error or rate limit (429)
- Timeout after 15 minutes
- Output under 5,000 characters (truncated)
- Any error message in the response

**What it synthesizes (14 sections):**
1. Author Intelligence
2. Core Methodology
3. Coaching Framework (3 phases: Assessment → Challenge → Support)
4. Agent Governance Framework (4A: Execution Standard, 4B: QC Protocol, 4C: Failure Patterns, 4D: Task Activation Language)
5. Foundational Principles
6. Problem-Solution Map
7. Trigger Detection System (Coaching Mode + Task Mode)
8. Voice and Language
9. Quote Library
10. Question Library
11. Tools, Exercises, and Execution Frameworks
12. Objections, Resistance, and Failure Modes
13. Session and Task Structure
14. Routing Rules and Scope Limits

**Input to sub-agent:**
- Full content of synthesis-agent-prompt.md
- extraction-notes.md content (up to 60K chars)
- analysis-notes.md content (up to 60K chars)
- SKILL.md blueprint specification (up to 30K chars)

**Output:** persona-blueprint.md saved to persona folder with header block

### Post-Synthesis: Automatic Re-Index (Phase 3 Completion)

After the persona-blueprint.md is written and saved, Phase 3 is NOT complete until the following re-index step runs:

```bash
# Re-index the Gemini collection with the new persona blueprint
python3 ~/.openclaw/workspace/scripts/gemini-indexer.py
```

**Why:** The blueprint must be indexed immediately so that persona matching (Skill 23 persona-matching-protocol.md) can discover this new persona via semantic search. Without re-indexing, the new persona exists on disk but is invisible to the matching system until a manual index run.

**Validation:** After gemini-indexer.py completes, confirm the new persona appears in search results:
```bash
gemini search "<persona name or key topic>" -c coaching-personas
```

**Phase 3 status in pipeline-status.json should only be set to COMPLETE after both the blueprint is saved AND the re-index succeeds.**

**Persona Matrix Update:** If `persona-matrix.md` exists in the workforce directory (`~/.openclaw/workspace/departments/`), re-run Layers 1-2 to update the pre-qualified persona pool. This ensures newly created personas are available for the 5-layer matching protocol. Run:
```bash
python3 ~/Downloads/openclaw-master-files/23-ai-workforce-blueprint/scripts/build-workforce.py --non-interactive --config-file workforce-config.json
```

### Post-Categorization: Automatic persona-categories.json Update

After the persona blueprint is written and its domain/perspective tags are determined during synthesis, automatically append the new persona entry to `persona-categories.json` (located in the Skill 22 folder):

```python
# After Phase 3 synthesis produces the blueprint and its tags:
# 1. Read the persona's domain tags, perspective tags, and custom tags from the blueprint
# 2. Generate the persona key: "<lastname>-<book-short-title>" (lowercase, hyphenated)
# 3. Append the entry to persona-categories.json
```

**Entry format** (matches existing schema):
```json
"<persona-key>": {
  "author": "Author Name",
  "book": "Book Title",
  "domain": ["tag1", "tag2"],
  "perspective": ["tag1"],
  "custom": ["tag1", "tag2"]
}
```

**Validation:**
- The new entry must use only tags from the existing `domainTags` and `perspectiveTags` arrays, or add new tags to those arrays if the persona introduces genuinely new categories.
- The JSON must remain valid after insertion.
- Run `python3 -c "import json; json.load(open('persona-categories.json'))"` to verify.

**This step runs BEFORE the re-index step above, so that persona-categories.json is up to date when the indexer runs.**

---

## Phase 4 - Gemini Engine Indexing

After Phase 3 completes for a book:

```bash
# If collection doesn't exist yet
  --name coaching-personas \
  --mask "**/*.md"

# Update index with new blueprint
python3 ~/.openclaw/workspace/scripts/gemini-indexer.py

# Generate vector embeddings
# Handled by gemini-indexer.py
```

---

## Parallelism Rules

- Maximum 7 books active simultaneously across all phases
- Books flow independently - no batch waiting
- As soon as Phase 1 completes → Phase 2 starts for that book immediately
- As soon as Phase 2 completes → Phase 3 starts for that book immediately
- Status tracked in pipeline-status.json after every phase

---

## Status File Format

```json
{
  "folder-name": {
    "title": "Book Title",
    "author": "Author Name",
    "phase1": "PENDING | IN_PROGRESS | COMPLETE | FAILED",
    "phase2": "PENDING | IN_PROGRESS | COMPLETE | FAILED",
    "phase3": "PENDING | IN_PROGRESS | COMPLETE | FAILED",
    "phase3_model_used": "gpt-5.3-codex | kimi-k2.5 (fallback)",
    "phase3_categories_updated": true,
    "phase3_reindexed": true,
    "google_embedding_2_indexed": true,
    "started": "March 7 at 3:30 PM",
    "completed": "March 7 at 3:52 PM",
    "errors": []
  }
}
```

---

## Time Estimates (7 parallel, continuous pipeline)

| Phase | Per Book | 7 Parallel Batch | Total (21 books) |
|-------|----------|-----------------|------------------|
| Text extraction | 5-200 sec | ~3 min | ~3 min (all parallel) |
| Phase 1 Kimi | 3-8 min | ~8 min | ~25 min |
| Phase 2 DeepSeek | 2-5 min | ~5 min | ~18 min |
| Phase 3 Codex | 5-12 min | ~12 min | ~40 min |
| Gemini Engine indexing | 1-2 min | ~2 min | ~5 min |
| **Total** | | | **~1.5 hours** |

With full 21 simultaneous: ~35-45 minutes total.
