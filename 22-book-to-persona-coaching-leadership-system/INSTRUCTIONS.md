# Book-to-Persona Coaching Leadership System — Execution Instructions

**Version:** v10.14.32 (YouTube/video pipeline rewrite — Track-I fix)
**Skill:** 22-book-to-persona-coaching-leadership-system
**Status:** Required runtime guide. Referenced from `SKILL.md` as part of the TYP read-order.

This file is the **execution guide** for an installed copy of Skill 22. `INSTALL.md` covers one-time installation. `SKILL.md` covers what the skill is. **This file covers how an agent actually runs it day-to-day.**

If you are still installing, stop here and finish `INSTALL.md` first. Come back here at runtime.

---

## What this skill does, in one sentence

Convert a coaching/leadership book (or YouTube video, or transcript) into a structured persona blueprint that can be assigned to AI agents and surfaced via semantic search.

The pipeline is **three phases over three model tiers**, with Gemini Engine indexing at the end.

---

## TYP Read-Order (mandatory before any execution)

You MUST read these files in this order, every time the skill runs. Skipping is an N4 violation.

1. `SKILL.md` — what the skill is and when it fires
2. **`INSTRUCTIONS.md` (this file)** — how to execute it
3. `INSTALL.md` — only re-read if a step refers back to install state
4. `QC.md` — runtime QC rubric (different from install QC)
5. `PIPELINE.md` — deep technical reference (read when troubleshooting)
6. `CORE_UPDATES.md` — what gets written to core .md files after persona generation
7. `GEMINI-RETRIEVAL-GUIDE.md` — how to surface the blueprint via semantic search
8. `GOOD-AND-BAD-EXAMPLES.md` — calibration examples

---

## Inputs supported

The skill accepts FOUR source types. Route via `scripts/add-persona-from-source.sh`.

| Source type | File / Identifier | Routes to |
|-------------|-------------------|-----------|
| Book (PDF, EPUB, MOBI, AZW, AZW3, KFX) | `~/Downloads/<file>` or absolute path | `pipeline/orchestrator.py` (extraction → analysis → synthesis) |
| YouTube video | `https://www.youtube.com/watch?v=...` | `scripts/add-persona-from-source.sh` → yt-dlp auto-subs → text → orchestrator |
| Local video file (mp4/mov/mkv/avi/webm) | absolute path | `scripts/add-persona-from-source.sh` → ffmpeg + whisper-cpp → text → orchestrator |
| Raw text / transcript | `.txt` file path | Direct to orchestrator, skipping extraction |
| Existing transcript URL | `https://...` | Fetch → text → orchestrator |

**N26 (Calibre auto-install):** PDF and EPUB use `pdfplumber` / `ebooklib` directly. MOBI/AZW/AZW3/KFX route through Calibre's `ebook-convert`. If Calibre is missing, `_find_calibre()` auto-installs it (Homebrew on Mac, apt-get + upstream installer fallback on Linux). The user never sees an "install Calibre manually" prompt.

**N32 (YouTube/video media tools — v10.14.32+):** YouTube and local-video sources go through `yt-dlp`, `whisper-cpp`, and `ffmpeg`. These are auto-installed by `install.sh` (Step 6.5) and backfilled by `update-skills.sh`. The YouTube branch tries auto-subs first (free, fast) and falls back to audio download + whisper transcription only if the video has no captions. **Pre-v10.14.32 every YouTube source bombed** — the old code shelled out to a non-existent `summarize` CLI. If you see "yt-dlp not installed" on a client box, re-run `update-skills.sh` first.

**Caller bash safety (v10.14.32):** `add-persona-from-source.sh` now uses `set -o pipefail` so failures inside the script can no longer be hidden by `| tee log` chains. If you wrap it in your own pipeline (`bash add-persona... | tee log`), use `${PIPESTATUS[0]}` to read the script's true exit code — `$?` will report `tee`'s status (always 0).

---

## The 3-phase pipeline

### Phase 1 — Extraction

**Goal:** Lift the book's structured content into `extraction-notes.md`: chapter outline, key frameworks, named techniques, quote bank, author voice characteristics, and stated philosophy.

**Model chain (N1: NO Anthropic):**
1. Ollama Cloud — latest Kimi (`ollama/kimi-k2.6` or newer)
2. OpenRouter — latest Kimi (`openrouter/moonshotai/kimi-k2.6`)
3. OpenRouter — DeepSeek V4 Pro (`openrouter/deepseek/deepseek-v4-pro`)
4. OpenRouter — Gemini 3.1 Pro (`openrouter/google/gemini-3.1-pro`)
5. OpenRouter — Gemini 3.1 Flash Lite (last-resort)
6. OAuth GPT (codex / chatgpt-cli) — emergency only

If none of these are available, **STOP** and ask the owner. Do not silently substitute a different model family. Anthropic is forbidden in this pipeline per N1.

**Inputs:** `<source>.txt`
**Output:** `personas/<persona-slug>/extraction-notes.md`
**Self-report:** Sub-agent reports exit code + token usage. NO self-QC (N5).

### Phase 2 — Analysis

**Goal:** Synthesize Phase 1's notes into a behavioral profile: how the author thinks, what they recommend, what they push back against, what their voice sounds like.

**Model chain:** Same as Phase 1.

**Inputs:** Phase 1's `extraction-notes.md`
**Output:** `personas/<persona-slug>/analysis-notes.md`

### Phase 3 — Synthesis

**Goal:** Produce the **persona blueprint** (`persona-blueprint.md`) — the canonical artifact that downstream consumers (persona-selector-v2.py, intelligence-resolver.ts) use.

**Model chain (Phase 3 prefers OAuth GPT):**
1. OAuth GPT (codex / chatgpt-cli)
2. Ollama Cloud — latest Kimi
3. OpenRouter — latest Kimi
4. OpenRouter — DeepSeek V4 Pro

**Inputs:** `extraction-notes.md` + `analysis-notes.md`
**Output:** `personas/<persona-slug>/persona-blueprint.md`

### Final step — Gemini Engine indexing

After Phase 3 writes the blueprint, **always** run:

```bash
# Section-level index of the new persona (the canonical build path — EMBED-5):
python3 ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/gemini-section-indexer.py --persona-id <persona-folder-slug>
# Then confirm counts + provider/model:
python3 ~/.openclaw/skills/shared-utils/embedding_engine.py --status
python3 ~/.openclaw/skills/shared-utils/embedding_engine.py --verify
```

This populates the `coaching-personas` collection so the persona becomes searchable. **Skipping this step is the most common cause of "the new persona isn't surfacing in the dashboard."**

---

## How to trigger this skill

### From the agent (single book ingestion):

```bash
bash ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/scripts/add-persona-from-source.sh \
  --source "~/Downloads/atomic-habits.epub" \
  --slug "clear-atomic-habits"
```

The script routes by extension, kicks off `pipeline/orchestrator.py`, and writes the persona to `personas/clear-atomic-habits/`.

### From the agent (batch ingest from a folder):

```bash
for f in ~/Downloads/coaching-books/*.{pdf,epub,mobi}; do
  slug=$(basename "$f" | sed -E 's/\.[^.]+$//' | tr '[:upper:] ' '[:lower:]-')
  bash ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/scripts/add-persona-from-source.sh \
    --source "$f" --slug "$slug"
done
```

### From the dashboard:

Skill 22 is wired to the Persona Library page. Drop a file in `~/.openclaw/inbox/personas/` and the watcher kicks the pipeline.

---

## Persona slug naming rules

- Lowercase, hyphen-separated
- Format: `<authorlastname>-<book-shortname>`
- Examples: `clear-atomic-habits`, `hormozi-100m-offers`, `cialdini-influence`
- One slug per book. If the same author has multiple books, each gets its own folder.

The slug becomes the directory name under `personas/`, the embedding key in the `coaching-personas` SQLite collection, and the `persona_id` value the dashboard's `persona-selector-v2.py` writes to `persona_assignment`.

---

## When to invoke this skill

**Always:**
- User uploads a coaching/leadership book or video
- User says "add this person as a persona"
- New persona request comes in via Telegram or the dashboard inbox

**Never:**
- For internal company documents (those go through Skill 23's department/role pipeline, not here)
- For a single quote or short excerpt (the pipeline needs at least a chapter-equivalent of source material)
- When the source is already a persona in `personas/` (check first via `ls personas/`)

---

## Output artifacts (where the work lands)

Every persona run produces:

```
personas/<slug>/
├── extraction-notes.md    # Phase 1 output
├── analysis-notes.md      # Phase 2 output
├── persona-blueprint.md   # Phase 3 output (canonical)
├── source-meta.json       # Origin + run history
└── citations.md           # Page/timestamp references for any direct quotes
```

After Gemini Engine indexing, the blueprint's section rows live in the ONE
canonical index (see docs/EMBEDDINGS.md — never any other path):
```
~/.openclaw/workspace/data/coaching-personas/gemini-index.sqlite
```

`persona-categories.json` and `PERSONA-ROUTER.md` (skill root) are also updated atomically so the selector can route to the new persona without a restart.

---

## PERSONA-INVENTORY HARD RULE (N16) — answer from the SET, never from qmd

When asked **"what / how many / which / new personas do I have?"**, the answer is
read ONLY from the SET file `persona-categories.json` (the matcher's ground truth):

```bash
python3 -c 'import json;d=json.load(open("persona-categories.json"));print(len(d["personas"]),"personas");print("\n".join(sorted(d["personas"])))'
```

**NEVER answer persona-inventory questions from `qmd` / the `coaching-personas`
collection.** `qmd` is a declared bin of this skill and is convenient to reach for
conversationally, but its collection is a cache that can be **frozen at a stale
snapshot** (it was pointed at the immutable skill-bundled `personas/` folder on
some boxes). That is exactly what produced the false **"no new personas since
March"** answer in June 2026 while the SET and the gemini index were already
current at 54. The install/update pipeline now repoints + re-indexes qmd at the
canonical store automatically (`reconcile_qmd_persona_index` in
`shared-utils/provision-persona-index.sh`), but the **SET is canonical for counts**
— always answer inventory from `persona-categories.json`.

To ADD a persona end-to-end (blueprint + SET + index + manifest + qmd + re-wire),
follow `../23-ai-workforce-blueprint/ADDING-PERSONAS.md` — skipping a step ships a
persona that is matchable-but-vector-less or one the agent never mentions.

---

## Failure modes and recovery

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| "Calibre not found" + auto-install fails | Linux box with no apt-get and no wget | Re-run with sudo, or install Calibre via your distro's package manager |
| Phase 1 stalls / never returns | Ollama Cloud quota exhausted | Set `OLLAMA_CLOUD_DISABLED=1` to force OpenRouter; check `~/.openclaw/credentials/` |
| `persona-blueprint.md` is empty or 200 chars | Phase 3 OAuth GPT was unavailable AND Kimi fallback silently no-op'd | Check `pipeline/run.log` for the actual failed model; resume with `--phase 3` |
| Embedding step errors with `GOOGLE_API_KEY missing` | Gemini key absent | Per N18 the script auto-falls-back to OpenAI `text-embedding-3-small`. If OPENAI_API_KEY also missing → set one in `~/.openclaw/credentials/` |
| Persona doesn't appear in dashboard | `coaching-personas` not re-indexed | Run `gemini-indexer.py --rebuild` |

---

## QC gate

After running the pipeline, dispatch a **different sub-agent** (N5) to run:

```bash
bash ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/qc-book-to-persona-coaching-leadership-system.sh
```

Pass requires score ≥ 8.5. Below 8.5 → loop back, fix specific failures, re-score (max 5 loops per N6).

---

## Cross-references

- `SKILL.md` — when this skill fires
- `INSTALL.md` — one-time setup
- `PIPELINE.md` — deep technical reference (model chains, retry logic, file paths)
- `GEMINI-RETRIEVAL-GUIDE.md` — how downstream consumers query the blueprint
- `GOOD-AND-BAD-EXAMPLES.md` — what a high-quality blueprint looks like vs. a degenerate one
- Skill 23 `INSTRUCTIONS.md` — how the workforce-build phase consumes these personas

---

*End of INSTRUCTIONS.md for Skill 22.*
