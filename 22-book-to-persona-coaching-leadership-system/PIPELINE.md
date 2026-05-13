# PIPELINE.md - Full Technical Reference
## Book Intelligence Pipeline - 3-Phase Sub-Agent Architecture

---

## Architecture Overview

```
PDF → Text Extraction (pdfplumber, free) → .txt file
                                              ↓
                              Phase 1: Smart model selection (Extraction)
                              → shared-utils/select_model.py picks latest Kimi
                                (Ollama Cloud preferred → OpenRouter → OAuth GPT → DeepSeek V4+)
                                Anthropic FORBIDDEN. Stops & asks owner if no match.
                                    ↓ extraction-notes.md
                              Phase 2: Smart model selection (Analysis)
                                Same Kimi-first chain as Phase 1.
                                    ↓ analysis-notes.md
                              Phase 3: OAuth GPT preferred (Synthesis)
                                Latest Kimi as fallback. Never Anthropic.
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

## Phase 1 - Extraction (Smart Model Selection)

**Model selection is DYNAMIC.** No model is hardcoded in this skill. The agent calls `shared-utils/select_model.py` which walks `openclaw.json` and picks the best available model in this priority order:

1. **Ollama Cloud Kimi (Tier 1, PREFERRED)** — `ollama/kimi-k*:cloud`, highest version number wins. Cheap, smart, large context, no per-call cost beyond Ollama subscription.
2. **OpenRouter Kimi (Tier 2)** — `openrouter/moonshot/kimi-k*`, highest version. Per-token pricing.
3. **OAuth GPT (Tier 3)** — `codex/gpt-*` or `openai-codex/gpt-*`, highest version. Subscription cost, no per-call.
4. **DeepSeek V4+ (Tier 4)** — `ollama/deepseek-v*:cloud` preferred over `openrouter/deepseek/deepseek-v*`. Cheap, smart, large context.
5. **STOP and ask the owner (Tier 5)** — if none of the above are in the client's `openclaw.json`, the selector prompts: *"Which model should I use for Book-to-Persona Phase 1? Reply with the model ID."* The install continues without blocking; the skill is wired once the owner answers.

**ABSOLUTE RULE:** Never select Anthropic models (`anthropic/claude-*`). The selector filters them out at every tier.

**Auto-adapts to new versions:** When Ollama Kimi 2.7 or 3.0 ships and the client adds it, the selector automatically picks the higher version. No skill update needed.

**How to invoke from the install agent:**
```bash
python3 "$MASTER_FILES_DIR/../shared-utils/select_model.py" \
  --skill book-to-persona --purpose "Phase 1 extraction" --format id
# Exit 0 = model selected and printed on stdout
# Exit 2 = owner input required; the prompt is on stderr/stdout per --format
```

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
- A Kimi 2.6+ context window (262K tokens, 96K max output) safely handles this with room for the system prompt. If the selector lands on a DeepSeek V4 tier instead, the 128K context still handles most book chunks; very large books may need additional chunking — see "Chunking" below.

---

## Phase 2 - Analysis (Smart Model Selection)

**Model selection:** Same `shared-utils/select_model.py` chain as Phase 1 — latest Kimi (Ollama preferred → OpenRouter → OAuth GPT → DeepSeek V4+). Never Anthropic.

**Why this changed:** v9.5.0 retired the hardcoded `deepseek/deepseek-v3.2` Phase 2 model. The selector now picks whatever the client has, with the same Kimi-first priority — which gives better analysis output if a Kimi 2.6+ is available, and DeepSeek V4+ is still a reasonable fallback for clients without Kimi.

**Route + API key:** Depends on which model the selector picks. Ollama → local Ollama daemon. OpenRouter → `OPENROUTER_API_KEY` in `~/.openclaw/secrets/.env`. OAuth → OpenClaw OAuth (no API key needed).
**Context:** 128K–1M tokens depending on the selected model.
**Max output:** 8K–128K tokens depending on selection.
**Prompt:** agent-prompts/analysis-agent-prompt.md
**Cost estimate:** ~$0.30–$0.80 per book on DeepSeek V4; ~$0.20–$0.60 on Ollama Cloud Kimi; ~$1–$3 on OAuth GPT.
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

## Phase 3 - Synthesis (Smart Model Selection — OAuth GPT Preferred)

**Model selection:** `shared-utils/select_model.py` with `--purpose "Phase 3 synthesis"`. Phase 3 prefers OAuth GPT for the synthesis pass because subscription cost is zero per call. Selection priority:

1. **OAuth GPT (Tier 3, PREFERRED for Phase 3)** — `codex/gpt-*` or `openai-codex/gpt-*`, highest version available. Subscription-billed, no per-call charge.
2. **Ollama Cloud Kimi (Tier 1)** — `ollama/kimi-k*:cloud`, latest version. Used as fallback if no OAuth GPT.
3. **OpenRouter Kimi (Tier 2)** — `openrouter/moonshot/kimi-k*`.
4. **DeepSeek V4+ (Tier 4)** — last resort.
5. **STOP and ask owner** if nothing matches.

NEVER Anthropic.

**Route:** Depends on selected model. OAuth GPT uses OpenAI Responses API via OpenClaw OAuth (ChatGPT subscription, NOT API key). Ollama uses local Ollama daemon. OpenRouter uses `OPENROUTER_API_KEY`.
**Context:** 196K–1M tokens depending on selection.
**Max output:** 96K–128K tokens depending on selection.
**Prompt:** agent-prompts/synthesis-agent-prompt.md
**Cost estimate:** $0 per call on OAuth GPT (covered by subscription). ~$0.50–$1 per book on Ollama Cloud Kimi. ~$2–$5 per book on OpenRouter Kimi or DeepSeek V4.
**Expected output:** `persona-blueprint.md` (10,000+ characters, all 14 sections)

**Runtime fallback** (when the primary selection fails mid-execution): the selector re-runs with the failed model excluded, walking down the tier list. Same triggers as before:
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
    "phase3_model_used": "<actual model ID resolved by select_model.py, e.g. openai-codex/gpt-5.5 or ollama/kimi-k2.6:cloud>",
    "phase3_selector_tier": "1 | 2 | 3 | 4 | 5-owner-input",
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
| Phase 1 (selected model — typically Kimi) | 3-8 min | ~8 min | ~25 min |
| Phase 2 (selected model — typically Kimi or DeepSeek) | 2-5 min | ~5 min | ~18 min |
| Phase 3 (selected model — typically OAuth GPT) | 5-12 min | ~12 min | ~40 min |
| Gemini Engine indexing | 1-2 min | ~2 min | ~5 min |
| **Total** | | | **~1.5 hours** |

With full 21 simultaneous: ~35-45 minutes total.
