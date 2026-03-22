# PIPELINE.md - Full Technical Reference
## Book Intelligence Pipeline - 3-Phase Sub-Agent Architecture

---

## Architecture Overview

```
PDF → Text Extraction (pdfplumber, free) → .txt file
                                              ↓
                              Phase 1: kimi-k2.5 via api.moonshot.ai/v1 (Extraction)
                                    ↓ extraction-notes.md
                              Phase 2: deepseek/deepseek-v3.2 via OpenRouter (Analysis)
                                    ↓ analysis-notes.md
                              Phase 3: openai-codex/gpt-5.4 via OAuth (Synthesis) ← fallback: kimi-k2.5
                                    ↓ persona-blueprint.md
                              Phase 3.5: Categorization (automatic)
                                    ↓ persona-categories.json updated
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

## Phase 1 - Extraction (Kimi K2.5)

**Model:** `kimi-k2.5` (via Moonshot API)
**Route:** `https://api.moonshot.ai/v1` (direct API)
**API Key:** `MOONSHOT_API_KEY` in `~/clawd/secrets/.env`
**Fallback:** `openrouter/moonshotai/kimi-k2.5` (if content filter triggers)
**Context:** 262K tokens
**Max output:** 96K tokens
**Temperature:** 1.0 (MUST be exactly 1.0)
**Prompt:** agent-prompts/extraction-agent-prompt.md
**Cost estimate:** ~$0.50-1.50 per book (varies by length)
**Expected output:** `extraction-notes.md` (5,000+ characters)

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
**API Key:** `OPENROUTER_API_KEY` in `~/clawd/secrets/.env`
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

---

## Phase 4 - Gemini Engine Indexing

After Phase 3 completes for a book:

```bash
# If collection doesn't exist yet
  --name coaching-personas \
  --mask "**/*.md"

# Update index with new blueprint
python3 ~/clawd/scripts/gemini-indexer.py

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
    "google_embedding_2_indexed": true,
    "started": "March 7 at 3:30 PM",
    "completed": "March 7 at 3:52 PM",
    "errors": []
  }
}
```

---

## Phase 3.5: Categorization (Automatic)

After a persona blueprint is generated, automatically tag it in persona-categories.json.

**Location:** `[master-files]/coaching-personas/persona-categories.json`
**Cost:** Zero - no API call needed. Tags are determined from the persona blueprint content.
**Time:** Under 1 second per persona

**Tag System:**
- 12 domain tags: Marketing, Sales, Leadership, Finance, Operations, Communication, Copywriting, Mindset, Productivity/Systems, Coaching, Strategy/Innovation, Personal Development
- 6 perspective tags: African American experience, Women's challenges, Men's challenges, Family/relationships, Faith/spirituality, Love/romantic relationships

**How tags are determined:**
1. Read the persona blueprint sections (especially "Core Topics", "Key Frameworks", "Target Audience")
2. Match keywords against domain tag definitions
3. Match author bio and book themes against perspective tags
4. Assign all relevant tags (a persona can have multiple domain and perspective tags)

**Schema per entry:**
```json
{
  "slug": "hormozi-100m-offers",
  "author": "Alex Hormozi",
  "book": "$100M Offers",
  "domain_tags": ["Sales", "Marketing", "Strategy/Innovation"],
  "perspective_tags": [],
  "business_stage": "growth",
  "ideal_user": "business owners scaling past $1M"
}
```

**Integration with Skill 23:**
- Skill 23 reads persona-categories.json to build governing-personas.md per department
- Domain tags determine which personas are relevant to which department
- This file is the bridge between Skill 22 (persona creation) and Skill 23 (company building)

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
