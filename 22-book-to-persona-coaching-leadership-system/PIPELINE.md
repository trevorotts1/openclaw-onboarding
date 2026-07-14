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
                                    ↓ persona-blueprint.md  (distilled two-sided persona)
                              Phase 3b: Same chain as Phase 3 (Playbook Appendix)
                                Preserves the book's reusable copy/funnel assets at full fidelity.
                                Quality floor enforced; fail-loud; no fabrication.
                                    ↓ PLAYBOOK-APPENDIX.md  (full-fidelity reusable asset library)
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

1. **Ollama Cloud DeepSeek V4-pro or latest (Tier 1, PREFERRED)** — `ollama/deepseek-v4-pro:cloud` or higher version. 1M context window, subscription-billed, smartest for long-context book extraction.
2. **Ollama Cloud Kimi 2.6 or latest (Tier 2, PREFERRED)** — `ollama/kimi-k2.6:cloud` or higher version. 262K context, subscription-billed, smartest for compact extraction.
3. **OpenRouter DeepSeek V4-pro or latest (Tier 3, FALLBACK)** — `openrouter/deepseek/deepseek-v4-pro` or higher. Same DeepSeek V4-pro model, per-token billed. Used only when Ollama Cloud DeepSeek V4-pro is unavailable.
4. **OpenRouter Kimi 2.6 or latest (Tier 4, FALLBACK)** — `openrouter/moonshot/kimi-k2.6` or higher. Same Kimi model, per-token billed. Used only when Ollama Cloud Kimi is unavailable.
5. **OAuth GPT (Tier 5, LAST RESORT)** — `codex/gpt-*` or `openai-codex/gpt-*`, highest version. ChatGPT subscription, no per-call cost. Used when neither Ollama Cloud nor OpenRouter has Kimi or DeepSeek V*-pro.
6. **STOP and ask the owner (Tier 6)** — if none of the above are in the client's `openclaw.json`, the selector prompts: *"Which model should I use for Book-to-Persona Phase 1? Reply with the model ID."* The install continues without blocking; the skill is wired once the owner answers.

**The rule in plain English:** prefer Ollama DeepSeek V4-pro or Kimi 2.6 (or whatever the latest version of each is). If the client doesn't have Ollama Cloud, fall back to the OpenRouter version of THE SAME MODEL (DeepSeek V4-pro / Kimi 2.6). Never default to a different model just because OpenRouter is configured — same model family, different route.

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

**What it extracts (30 items):**
- Coaching lens (items 1-11): Author background, central problem, root cause, full methodology,
  principles, transformation arc, coaching questions, tools/exercises, objection handling,
  author voice, direct quotes
- Governance lens (items 12-20): Execution system, quality bar, non-negotiable rules,
  failure patterns, decision logic, self-review protocol, definition of done,
  amateur-to-expert gap, professional application
- Playbook Asset Lens (items 21-30): headline/hook/subject formulas, page-by-page funnel/page
  recipes, sequences, sales/objection/follow-up/discovery scripts, email scripts & sequences,
  frameworks/models/templates with steps, brand-voice & brand-building language patterns,
  offer/guarantee/CTA/bonus language, verbatim swipe file, and an asset coverage self-report —
  each captured as PATTERN + worked EXAMPLE + SOURCE (depth preserved, never summarized away)

**Input to sub-agent:**
- Full content of extraction-agent-prompt.md (system instructions)
- Full book text (up to 200,000 characters)

**Output:** extraction-notes.md saved to persona folder

**Large book handling:**
- Books over 200,000 characters: pass first 200,000 chars (covers most books)
- A Kimi 2.6+ context window (262K tokens, 96K max output) safely handles this with room for the system prompt. If the selector lands on a DeepSeek V4 tier instead, the 128K context still handles most book chunks; very large books may need additional chunking — see "Chunking" below.

---

## Phase 2 - Analysis (Smart Model Selection)

**Model selection:** Same `shared-utils/select_model.py` chain as Phase 1. Priority: Ollama Cloud DeepSeek V4-pro (1M context, smartest for analysis) → Ollama Cloud Kimi 2.6 → OpenRouter DeepSeek V4-pro → OpenRouter Kimi 2.6 → OAuth GPT. Never Anthropic.

**Why this changed:** v10.2.0 made the priority explicit at the model-family level — DeepSeek V4-pro is the preferred Phase 2 model (1M context handles full-book analysis without chunking), and Kimi 2.6 is the smart-extraction alternate. Both come from Ollama Cloud first; the same models from OpenRouter only fire when the Ollama copy isn't configured. v9.5.0 had already retired the hardcoded `deepseek/deepseek-v3.2` Phase 2 model — v10.2.0 just makes the Ollama-first preference for the new DeepSeek V4-pro and Kimi 2.6 explicit.

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
- Timeout — Phase 1/2 use 30-minute HTTP timeouts; Phase 3 uses 60 min. Sub-agents that wrap these phases must allow ≥ 30 minutes wall time (60 preferred) to avoid premature kills (v9.5.2)
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

## Phase 3b - Playbook Appendix (Smart Model Selection — same chain as Phase 3)

**Why it exists:** the 14-section blueprint DISTILLS a whole book into a governance + coaching persona. That distillation is exactly why funnel/website copy driven by the blueprint came out too concise — the book's actual reusable assets (the formulas, scripts, page recipes, swipe copy, brand-voice machinery) were compressed away. Phase 3b fixes that by emitting a mandatory companion, `PLAYBOOK-APPENDIX.md`, that PRESERVES those assets at full fidelity so copy specialists write rich, brand-building copy.

**Model selection:** same `resolve_phase_model("phase3", …)` chain as synthesis (OAuth GPT preferred → Ollama Cloud → OpenRouter; never Anthropic).
**Prompt:** `agent-prompts/playbook-appendix-prompt.md`
**Input to sub-agent:** the appendix prompt + extraction-notes.md (up to 90K chars; focus items 21-30) + analysis-notes.md (up to 60K chars; focus Dimension 13).
**Output:** `PLAYBOOK-APPENDIX.md` saved to the persona folder (alongside persona-blueprint.md).

**What it produces (8 sections A-H, each asset as Pattern + Worked example + Source):**
- A. Headline, Hook & Subject-Line Formula Bank (≥ 12 for asset-rich books)
- B. Funnel & Page Recipes — page-by-page (the FULL recipe set; every page/funnel type)
- C. Script Bank — sales / objection / follow-up / discovery / close (≥ 10)
- D. Email & Sequence Bank (≥ 1 complete sequence, every email spelled out)
- E. Frameworks, Models & Templates — with all steps (the FULL framework set)
- F. Brand Voice & Brand-Building Language Patterns (≥ 15)
- G. Swipe File — strongest verbatim examples (≥ 20)
- H. Asset Coverage Map & Gaps (the honesty ledger; absent categories marked ABSENT)

**Quality floor (enforced in the orchestrator — `_validate_appendix` + `APPENDIX_*` constants):**
- HARD gate (fail-loud → `phase3b: FAILED`): file present + non-empty, all 8 sections A-H, Coverage Map present, ≥ 6,000 chars.
- SOFT targets (logged as warnings; one stricter retry): ≥ 12,000 chars and ≥ 12 Pattern/Worked-example blocks for asset-rich books.
- NO fabrication: a memoir / non-commercial book legitimately marks categories ABSENT in the Coverage Map and passes as `COMPLETE_WITH_WARNINGS` rather than inventing assets to hit a count.

**Status:** `phase3b` in pipeline-status.json — `COMPLETE`, `COMPLETE_WITH_WARNINGS`, or `FAILED`. The appendix is non-fatal to Phase 3 (the blueprint still ships) but is mandatory for a fully DONE persona.

### Post-Synthesis: Automatic Re-Index (Phase 3 Completion)

After the persona-blueprint.md is written and saved, Phase 3 is NOT complete until the following re-index step runs:

```bash
# Re-index the Gemini collection with the new persona blueprint
python3 ~/.openclaw/scripts/gemini-indexer.py
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

After the persona blueprint is written and its domain/perspective tags are determined during synthesis, automatically append the new persona entry to `persona-categories.json`.

**Canonical location (PRD 2.7):** `<workspace>/data/coaching-personas/persona-categories.json`
(VPS: `/data/.openclaw/workspace/data/coaching-personas/persona-categories.json`;
Mac: `~/.openclaw/workspace/data/coaching-personas/persona-categories.json`).
The `22-book-to-persona-coaching-leadership-system/persona-categories.json` in the skill folder is the **shipped seed only** — it is copied to the canonical location on first run and is READ-ONLY thereafter. All writes go to the canonical path via `get_openclaw_paths()["persona_categories"]`.

```python
# After Phase 3 synthesis produces the blueprint and its tags:
# 1. Read the persona's domain tags, perspective tags, and custom tags from the blueprint
# 2. Generate the persona key: "<lastname>-<book-short-title>" (lowercase, hyphenated)
# 3. Append the entry to persona-categories.json
```

**Entry format** (matches existing schema — the last four fields are the v1.3
additive duality-tag layer, see below; all four are OPTIONAL):
```json
"<persona-key>": {
  "author": "Author Name",
  "book": "Book Title",
  "domain": ["tag1", "tag2"],
  "perspective": ["tag1"],
  "custom": ["tag1", "tag2"],
  "audiences": ["tag1"],
  "topics": ["tag1", "tag2"],
  "voice_style": {"summary": "..."},
  "usable_as": ["topic", "task"]
}
```

**Validation:**
- The new entry must use only tags from the existing `domainTags` and `perspectiveTags` arrays, or add new tags to those arrays if the persona introduces genuinely new categories.
- The JSON must remain valid after insertion.
- Run `python3 -c "import sys; sys.path.insert(0,'shared-utils'); from detect_platform import get_openclaw_paths; p=get_openclaw_paths()['persona_categories']; import json; json.load(open(p)); print('OK:', p)"` to verify.

**This step runs BEFORE the re-index step above, so that persona-categories.json is up to date when the indexer runs.**

### Post-Categorization: Duality-Tag Enrichment (audiences / topics / voice_style / usable_as / emotional_register / audience_resonance / conversion_style)

**Why:** the Skill-23 voice-first AUDIENCE+TOPIC blend matcher (`23-ai-workforce-blueprint/scripts/persona_blend.py`) picks a job's VOICE by reasoning over the WHOLE catalog through the four v1.3 additive fields below, plus (schema 1.4, unit A-U3) three additive SCALAR fields — `emotional_register`, `audience_resonance`, `conversion_style` — that let the Section-B Quality-Control judge score whether the copy actually hit the right register. Before the v1.3 step existed, NOTHING in the pipeline ever wrote the four fields for a newly-synthesized persona — only the one-time 2026-07-09 backfill (schema 1.2 → 1.3, all 99 personas, see `CHANGELOG.md`) carried them, which froze the matcher's candidate universe at those 99 personas forever. A-U3 repeats the same one-time-backfill-plus-live-pipeline pattern for the three v1.4 fields (`pipeline/backfill-schema14-registers.py`, all 99 personas, schema 1.3 → 1.4).

**How it works (fully automated — no manual step required):**

1. `_synthesis_system()` in `pipeline/orchestrator.py` dynamically appends the LIVE `audienceTags[]`/`topicTags[]` controlled vocabulary — and, since A-U3, the LIVE `emotionalRegisterTags[]`/`audienceResonanceTags[]`/`conversionStyleTags[]` vocabulary — (read fresh from the canonical `persona-categories.json` at synthesis time) to the Phase-3 system prompt, so the model can propose duality tags **vocab-first** — chosen FROM the existing vocabulary, not invented. When a given vocab is empty (a pre-enrichment catalog, or the first-ever persona on a fresh box) its block is omitted and the model is instructed to leave the corresponding field(s) empty.
2. Per `agent-prompts/synthesis-agent-prompt.md`, the synthesis model appends an OPTIONAL `## Duality Tags` heading + fenced ` ```json ` object to `persona-blueprint.md`, after the 14 mandatory sections, carrying `audiences[]`, `topics[]`, `voice_style{summary(required), tone[], devices[], cadence, signature_moves[], avoid[]}`, `usable_as[]`, and (A-U3) `emotional_register`, `audience_resonance`, `conversion_style` (each a single string, vocab-first).
3. `_append_persona_to_categories()` (Phase 6, same step as the domain/perspective write above) parses that block (`_parse_duality_tags_block`) and, when present, gates it (`_validate_duality_tags`) through the **same authoritative validator** the Skill-23 matcher enforces at read-time: `persona_blend.validate_catalog_tags`. One rulebook, imported directly (`23-ai-workforce-blueprint/scripts/persona_blend.py`) — never re-implemented, so the write-time gate can never drift from the read-time contract. A local structural fallback (list-shape + `usable_as` enum + `voice_style.summary` required + non-empty-string scalars) covers the rare case where skill 23 isn't installed alongside skill 22 on a given box.

**Additive, never-to-zero contract (fail LOUD, never fail silent, never block core routing):**
- **No block present** → NO-OP. The persona registers exactly as before this feature (domain/perspective/custom only) — not a failure, matches `persona_blend.validate_catalog_tags`'s own pre-enrichment semantics.
- **Block present and well-formed** → all seven fields present in the block (`audiences`/`topics`/`voice_style`/`usable_as`/`emotional_register`/`audience_resonance`/`conversion_style`) are written onto the entry; a one-line confirmation is printed naming the counts/values.
- **Block present but malformed** (bad JSON, an audience/topic tag or emotional_register/audience_resonance/conversion_style value that isn't already a vocab member, a non-enum `usable_as` value, a `voice_style` missing its required `summary`, or a non-empty-string violation on a scalar field) → the gate REJECTS the WHOLE block (all-or-nothing — never a half-valid write, even when only one of the seven fields is the offender): a loud diagnostic is printed naming every offending field, the folder is recorded in the module-level `_DUALITY_TAG_WRITE_FAILURES` list (`pipeline_had_duality_tag_failures()`), and every duality field is **omitted**. Core `domain`/`perspective` registration is completely unaffected (this failure mode is deliberately kept separate from `PHASE6_CATEGORIES_EXIT_CODE` / F1.4's auto-repair path, which governs the load-bearing routing fields, not this optional enrichment layer).

**Publish path:** `pipeline/persona_fleet.py`'s `sync_categories` (used by `publish-personas-to-fleet.sh`) carries all seven fields through workspace→repo unchanged when present (four since v6.17.0, three more since A-U3), and preserves any repo-side enrichment a sync doesn't itself supply — so a publish run can never silently strip duality enrichment landed by this step.

---

## Phase 4 - Gemini Engine Indexing

After Phase 3 completes for a book:

```bash
# If collection doesn't exist yet
  --name coaching-personas \
  --mask "**/*.md"

# Update index with new blueprint
python3 ~/.openclaw/scripts/gemini-indexer.py

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

---

## Orphan-safe launching (NOTE v17.0.24) — never leave a detached build billing :cloud

A book build is often launched DETACHED (an agent copies `orchestrator.py` to
`orchestrator_<slug>.py` and runs it in the background). If the launching
agent/workflow is stopped mid-run, the stop reaps the agent but **not** the
detached Python child — it reparents to launchd/init and keeps making `:cloud`
calls until it finishes, billing the client. `pipeline/orphan_guard.py` (linked
by every orchestrator copy at `main()` startup) plus two helper scripts make
that structurally impossible.

**ALWAYS launch a detached/background build through the launcher** (never a bare
`python3 orchestrator_<slug>.py &`):

```bash
# single persona (backgrounded, fully reapable):
pipeline/run-orchestrator.sh --single-book --slug <slug> &
# full batch:
pipeline/run-orchestrator.sh &
```

The launcher runs the child in its OWN process group, writes a per-run liveness
lockfile, tags the run (`OPENCLAW_RUN_ID`), and on exit/interrupt does a TARGETED
reap of exactly that run's group. Even if the launcher itself is `kill -9`'d, the
orchestrator's built-in watchdog self-terminates within one interval because its
recorded parent pid is gone.

**Stop hook / cleanup** — reap orphans without ever a blind `pkill`:

```bash
pipeline/reap-orchestrators.sh --sweep        # reap every run whose parent is DEAD (safe cron/stop-hook payload)
pipeline/reap-orchestrators.sh --run RUN_ID   # reap exactly one run
```

Self-defense armed automatically by `orchestrator.py` (all honour env overrides):

| Guard | Behaviour | Env override (default) |
|-------|-----------|------------------------|
| Parent-liveness | self-exit the instant `OPENCLAW_PARENT_PID` is gone | — |
| Liveness lock | self-exit when `OPENCLAW_RUN_LOCKFILE` is removed | — |
| Max runtime | hard wall-clock ceiling → self-exit | `OPENCLAW_MAX_RUNTIME_SEC` (6h) |
| Watchdog cadence | liveness poll interval (a THREAD, fires even during a long provider await) | `OPENCLAW_WATCHDOG_INTERVAL_SEC` (30s) |
| Process-group reap | child + its subprocesses (Phase-5 indexer) die as a unit | `OPENCLAW_ORCH_DETACH=1` (set by launcher) |
| Single-run lock | a second orchestrator for the same slug is refused (exit 4) | — |

Per-run pidfiles live under `<workspace>/data/coaching-personas/.pipeline-runs/`
(or `OPENCLAW_RUN_DIR`). Regression lock: `tests/unit/orphan-process-prevention.test.sh`.

With full 21 simultaneous: ~35-45 minutes total.

---

## Adding books → publishing personas to the fleet (the ONE command)

**The pipeline is a WORKSPACE-only writer.** A book build writes the new persona
(blueprint + `persona-categories.json` entry) ONLY under
`<workspace>/data/coaching-personas/`. It never touches the repo. Four coupled
artifacts have to move together before a persona actually ships fleet-wide:

| # | Artifact | Where |
|---|----------|-------|
| a | blueprint dir | `22-…/personas/<slug>/persona-blueprint.md` (repo) |
| b | SET entry | `22-…/persona-categories.json` (repo seed) |
| c | manifest | `shared-utils/prebuilt-index/INDEX-MANIFEST.json` (`persona_count`, `canonical_persona_count`, `chunk_count`, `sha256`, `release_tag`, `persona_set_md5`) |
| d | release asset | `gemini-index.sqlite.gz` GitHub Release (the embeddings clients download) |

Historically (a)+(b) were a hand edit and (c)+(d) a *separate* hand run of
`build-and-publish.sh`, so the workspace/asset advanced while the repo library
lagged — the N38 count triad went red at CI/roll and a roll could ship the OLD
count until someone manually caught the repo up. **That divergence is now
structurally impossible.**

### The ONE command

```bash
# On the OPERATOR box (has the workspace + a Gemini key + gh auth):
22-book-to-persona-coaching-leadership-system/pipeline/publish-personas-to-fleet.sh
```

From the current **workspace** persona set it does ALL FOUR in one atomic,
re-runnable pass:

1. copies each workspace `persona-blueprint.md` into the repo blueprint dir,
   **sanitized** of operator-local absolute paths (only the shippable file);
2. merges the workspace entries into `persona-categories.json` with
   **controlled-vocabulary** tag validation (`domain` ⊆ `domainTags`,
   `perspective` ⊆ `perspectiveTags`, kebab-case `custom`);
3. delegates to `shared-utils/prebuilt-index/build-and-publish.sh` to
   incrementally (HASH-SKIP — no furnace) embed the delta, recompute
   counts/sha256/`persona_set_md5`, bump the manifest, and publish the release
   asset;
4. **refuses to complete** (nonzero exit, snapshot **rolled back** — no
   half-committed state) unless the N38 count triad *and* the published asset's
   sha256 all agree at the same **N**.

Then review the diff and `git add` the three repo paths + commit. It is
**idempotent**: re-running with nothing new is a no-op (no re-embed, no re-tag).

Flags: `--no-asset` (hermetic — sync repo + manifest COUNT fields only, skip the
embed/publish; used by tests and to stage a repo catch-up), `--dry-run` (prove
the math, no upload), `--workspace DIR` / `--repo ROOT` overrides.

### The guards that make it un-forgettable

- **Terminal pipeline phase** — `add-persona-from-source.sh` writes a
  `.fleet-publish-pending.json` marker + prints a LOUD banner after every add.
- **Early divergence guard** — `pipeline/assert-personas-published.sh` compares
  workspace ↔ repo ↔ manifest and errors with the exact remediation command;
  `--repo-only` runs the hermetic triad. Wired into the **pre-commit hook**
  (blocks a commit that bumps one half without the others) and the
  **`update-skills.sh` pre-roll** path (a roll refuses to provision a
  stale/divergent library).
- **CI** — `persona-set-asset-consistency-guard.yml` + `qc-static.yml` enforce
  the same triad at the PR boundary (unchanged).

Regression lock: `tests/unit/publish-personas-to-fleet.test.sh`.
