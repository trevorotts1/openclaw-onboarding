# Anthology Writer (Skill 54) — Operator Instructions

## When to use
A multi-contributor anthology where each contributor needs ONE finished chapter
(2,000–3,500 words) in their own blended voice, plus tone doc, locked
title/subtitle, blurb, and outline. For a single-author book use **Skill 53
(Book Writer)** — the two share the tone core but are separate skills.

## One contributor, end to end
1. **Preflight the box** (resolve the client's own NON-Anthropic tiers).
   Choose one path:

   **Interactive** (guides the operator through each tier):
   ```
   bash 54-anthology-writer/preflight.sh --resolve --interactive --run-dir <RUN_DIR>
   ```
   Respond to each provider/model prompt. This writes a ready-to-run
   `model-map.json` into `<RUN_DIR>/` on the first pass. No manual editing
   required.

   **Fleet-installer / automation** (emits placeholders; CI-safe):
   ```
   bash 54-anthology-writer/preflight.sh --non-interactive --run-dir <RUN_DIR>
   ```
   This writes `model-map.json` into `<RUN_DIR>/` with `<CLIENT_PROVIDER_ID>`
   and `<CLIENT_MODEL>` placeholder values for each tier. After running, you
   must resolve the placeholders by either:
   - Running `preflight.sh --resolve --interactive` to fill them interactively, or
   - Hand-editing `model-map.json` to replace every `<CLIENT_PROVIDER_ID>` with
     a real provider id (e.g. `openrouter`, `ollama-cloud`) and every
     `<CLIENT_MODEL>` with a real model name for your box (e.g.
     `qwen/qwen3-coder`, `deepseek/deepseek-v4-pro`).
   
   In all cases, proceed to step 2 only after `model-map.json` is resolved.

2. **Fill intake** at `<RUN_DIR>/working/intake.json` from
   `intake/aw-intake-template.md` (4 required fields; `personal_stories` may be
   `N/A`; NEVER put an API key/token in intake).
3. **Author on the client's own providers** -- the upstream sub-agents execute
   the deterministic, ordered prompt-by-prompt execution contract below and drop
   every artifact into `<RUN_DIR>/working/`. This contract is the MINIMUM VIABLE
   STEP-3: an agent reading it immediately knows which prompt to run, for which
   tier, injecting which substitutions, writing to which path. The target is a
   future `dispatch_authoring.py` dispatcher script that consumes this contract
   declaratively; until that script ships, the documented contract is the single
   executable specification.

   **A. Avatar dossier (P0A-AVATAR: delegated to Skill 52 + aw-12 extraction).**
   The avatar handoff produces `working/avatar.md` BEFORE the tone authoring
   starts. Skill 54 DELEGATES to Skill 52 avatar-alchemist prompts aa-01..aa-03
   by path (NEVER copied), then runs aw-12 as a LIGHT-tier extraction step.
   See `ANTHOLOGY-MANIFEST.json` `avatar_handoff.authoring_sequence` for the
   exact ordering. Step 3 expects `working/avatar.md` to exist before the first
   LLM call in section B.

   | Stage | Prompt asset | Tier | Produces | Input substitutions |
   |---|---|---|---|---|
   | aa-01 | `../52-avatar-alchemist/prompts/01-avatar-questions-1-30/` (system.md + user.md, by path) | MID-WRITER | (internal) | intake questions 1-30 |
   | aa-02 | `../52-avatar-alchemist/prompts/02-avatar-questions-31-32/` (system.md + user.md, by path) | MID-WRITER | (internal) | intake questions 31-32; research pass (web-search tool) |
   | aa-03 | `../52-avatar-alchemist/prompts/03-rewrite-avatar/` (system.md + user.md, by path) | MID-WRITER | (internal) | aa-01 + aa-02 outputs |
   | aw-12 | `assets/prompts/12-primary-goal-extraction.md` | LIGHT | avatar.md (contributed) | aa-03 output via `{{niche_primary_goal}}` |
   | RESULT | -- | -- | `working/avatar.md` | the full avatar dossier, consumed by every tone + chapter stage below |

   **B. Blended tone (P2-TONE-AUTHOR: aw-01..aw-05, MID-WRITER).**
   Four individual tone-style analyses feed one blended synthesis. Produce
   `working/tone-doc.md` (the blended tone, >= 3,000 stripped words).

   NOTE: model-map.json is REQUIRED by P6; resolve before starting.

   | Stage | Prompt asset | Tier | Produces | Input substitutions |
   |---|---|---|---|---|
   | aw-01 | `prompts/04-tone-style-1/system.md` + `user.md` | MID-WRITER | (internal -- fed to aw-05) | `{{intake.tone_style_1}}`, avatar dossier |
   | aw-02 | `prompts/05-tone-style-2/system.md` + `user.md` | MID-WRITER | (internal -- fed to aw-05) | `{{intake.tone_style_2}}`, avatar dossier |
   | aw-03 | `prompts/06-tone-style-3/system.md` + `user.md` | MID-WRITER | (internal -- fed to aw-05) | `{{intake.tone_style_3}}`, avatar dossier |
   | aw-04 | `prompts/07-tone-style-4/system.md` + `user.md` | MID-WRITER | (internal -- fed to aw-05) | `{{intake.tone_style_4}}`, avatar dossier |
   | aw-05 | `prompts/08-blended-tone/system.md` + `user.md` | MID-WRITER | `working/tone-doc.md` | `{{artifact.04-tone-style-1}}` through `{{artifact.07-tone-style-4}}`, `{{intake.first_name}}` `{{intake.last_name}}`, avatar dossier |
   | RESULT | -- | -- | `working/tone-doc.md` | "The {First} {Last} Tone", >= 3,000 stripped words |

   **C. Title lock (P4-TITLE-LOCK: aw-06, MID-WRITER).**
   Lock the chapter title + subtitle before any prose is written. Produce
   `working/title.json` with non-empty `title` and `subtitle` fields.

   | Stage | Prompt asset | Tier | Produces | Input substitutions |
   |---|---|---|---|---|
   | aw-06 | `assets/prompts/06-suggested-titles.md` | MID-WRITER | `working/title.json` | `{{intake.anthology_title}}`, `{{intake.first_name}}` `{{intake.last_name}}`, `{{intake.chapter_premise}}`, `{{intake.subtitle_hint}}`, `{{artifact.tone_doc}}` |
   | RESULT | -- | -- | `working/title.json` | JSON with `title` + `subtitle`, locked byte-exact for downstream |

   **D. Outline, blurb, and chapter (P5-CHAPTER-AUTHOR: aw-07 MID-WRITER, aw-08 MID-WRITER, aw-09 HEAVY-WRITER).**
   Author in this order: blurb first (so it can inform the chapter's framing),
   then outline (so story placement is provable before prose), then chapter.

   | Stage | Prompt asset | Tier | Produces | Input substitutions |
   |---|---|---|---|---|
   | aw-07 | `assets/prompts/07-book-blurb.md` | MID-WRITER | `working/blurb.md` | `{{intake.anthology_title}}`, `{{artifact.title}}`, `{{intake.chapter_premise}}`, `{{artifact.tone_doc}}` |
   | aw-08 | `assets/prompts/08-create-outline.md` | MID-WRITER | `working/outline.md` | `{{artifact.title}}`, `{{intake.chapter_premise}}`, `{{intake.personal_stories}}`, `{{artifact.tone_doc}}` |
   | aw-09 | `assets/prompts/09-write-chapter.md` | HEAVY-WRITER | `working/chapter.md` | `{{intake.first_name}}` `{{intake.last_name}}`, `{{intake.anthology_title}}`, `{{intake.chapter_premise}}`, `{{intake.personal_stories}}`, `{{artifact.tone_doc}}`, `{{artifact.title}}`, `{{artifact.outline}}` |
   | RESULT | -- | -- | `working/blurb.md` + `working/outline.md` + `working/chapter.md` | blurb: 90-160 words; outline: 6-12 beats; chapter: 2,000-3,500 stripped words |

   **E. RUN-LEDGER.json -- record model provenance.**
   The ledger records every LLM stage that wrote an artifact, so the P6
   no-Anthropic gate (`aw_build_check.py`) can prove every resolved model id is
   NON-Anthropic. Write it alongside the artifacts as each stage completes.

   ```json
   {
     "run_id": "<uuid4>",
     "started_at": "<ISO-8601>",
     "skill": "anthology-writer",
     "anthology_title": "<from intake>",
     "contributor": "<First Last>",
     "rewrite_count": 0,
     "phases": [
       {
         "stage": "aa-01-avatar-questions-1-30",  "tier": "MID-WRITER",
         "prompt": "52-avatar-alchemist/prompts/01-avatar-questions-1-30",
         "model": "<resolved NON-Anthropic model id>",
         "input_artifacts": ["working/intake.json"],
         "output_artifact": null,
         "duration_ms": 0,
         "status": "ok"
       },
       { "stage": "aa-02-avatar-questions-31-32",  "tier": "MID-WRITER", "prompt": "52-avatar-alchemist/prompts/02-avatar-questions-31-32",  "model": "...", "input_artifacts": ["working/intake.json"], "output_artifact": null, "duration_ms": 0, "status": "ok" },
       { "stage": "aa-03-rewrite-avatar",           "tier": "MID-WRITER", "prompt": "52-avatar-alchemist/prompts/03-rewrite-avatar",           "model": "...", "input_artifacts": [],                        "output_artifact": null, "duration_ms": 0, "status": "ok" },
       { "stage": "aw-12-primary-goal-extraction",   "tier": "LIGHT",      "prompt": "assets/prompts/12-primary-goal-extraction.md",   "model": "...", "input_artifacts": [],                        "output_artifact": "working/avatar.md", "duration_ms": 0, "status": "ok" },
       { "stage": "aw-01-tone-style-1",              "tier": "MID-WRITER", "prompt": "prompts/04-tone-style-1",                        "model": "...", "input_artifacts": ["working/avatar.md", "working/intake.json"], "output_artifact": null, "duration_ms": 0, "status": "ok" },
       { "stage": "aw-02-tone-style-2",              "tier": "MID-WRITER", "prompt": "prompts/05-tone-style-2",                        "model": "...", "input_artifacts": ["working/avatar.md", "working/intake.json"], "output_artifact": null, "duration_ms": 0, "status": "ok" },
       { "stage": "aw-03-tone-style-3",              "tier": "MID-WRITER", "prompt": "prompts/06-tone-style-3",                        "model": "...", "input_artifacts": ["working/avatar.md", "working/intake.json"], "output_artifact": null, "duration_ms": 0, "status": "ok" },
       { "stage": "aw-04-tone-style-4",              "tier": "MID-WRITER", "prompt": "prompts/07-tone-style-4",                        "model": "...", "input_artifacts": ["working/avatar.md", "working/intake.json"], "output_artifact": null, "duration_ms": 0, "status": "ok" },
       { "stage": "aw-05-blended-tone",              "tier": "MID-WRITER", "prompt": "prompts/08-blended-tone",                        "model": "...", "input_artifacts": [],                        "output_artifact": "working/tone-doc.md",  "duration_ms": 0, "status": "ok" },
       { "stage": "aw-06-suggested-titles",          "tier": "MID-WRITER", "prompt": "assets/prompts/06-suggested-titles.md",          "model": "...", "input_artifacts": ["working/tone-doc.md"],   "output_artifact": "working/title.json",   "duration_ms": 0, "status": "ok" },
       { "stage": "aw-07-book-blurb",                "tier": "MID-WRITER", "prompt": "assets/prompts/07-book-blurb.md",                "model": "...", "input_artifacts": ["working/tone-doc.md", "working/title.json"], "output_artifact": "working/blurb.md", "duration_ms": 0, "status": "ok" },
       { "stage": "aw-08-create-outline",            "tier": "MID-WRITER", "prompt": "assets/prompts/08-create-outline.md",            "model": "...", "input_artifacts": ["working/tone-doc.md", "working/title.json"], "output_artifact": "working/outline.md", "duration_ms": 0, "status": "ok" },
       { "stage": "aw-09-write-chapter",             "tier": "HEAVY-WRITER","prompt": "assets/prompts/09-write-chapter.md",            "model": "...", "input_artifacts": ["working/tone-doc.md", "working/title.json", "working/outline.md"], "output_artifact": "working/chapter.md", "duration_ms": 0, "status": "ok" }
     ]
   }
   ```

   Fields:
   - `run_id` -- UUID v4, minted once at the start of step 3.
   - `started_at` -- ISO-8601 UTC timestamp.
   - `phases[].stage` -- the stage identifier (matches `ANTHOLOGY-MANIFEST.json` `tiers` and the prompt asset `# aw-NN` slug).
   - `phases[].tier` -- one of HEAVY-WRITER, MID-WRITER, LIGHT, RESEARCHER, IMAGE.
   - `phases[].prompt` -- relative path to the baked prompt asset.
   - `phases[].model` -- the RESOLVED NON-Anthropic model id (per-box, client's provider).
   - `phases[].input_artifacts` -- array of `<RUN_DIR>/working/` paths read before the call.
   - `phases[].output_artifact` -- `<RUN_DIR>/working/` path written after the call, or null for intermediate stages.
   - `phases[].duration_ms` -- wall-clock milliseconds for the LLM call.
   - `phases[].status` -- "ok" on success; "failed" or "degraded" on non-fatal issues.

   **F. Artifact summary -- the 7 artifacts produced in step 3:**
   `working/avatar.md`, `working/tone-doc.md`, `working/title.json`,
   `working/blurb.md`, `working/outline.md`, `working/chapter.md`,
   `working/RUN-LEDGER.json`.

   **G. Future target.** The `dispatch_authoring.py` dispatcher script will consume
   `ANTHOLOGY-MANIFEST.json` and this contract declaratively, running each stage on
   the client's own model-map resolved tiers. Until that script ships, the tables
   above are the minimum viable step-3 -- an agent reading them immediately knows
   which prompt to run, for which tier, injecting which substitutions, writing to
   which path.
4. **Run the engine THROUGH the one entry:**
   ```
   bash 54-anthology-writer/anthology-entry.sh --run-dir <RUN_DIR>
   ```
   It walks P0→P7 fail-closed and issues `delivery/PROCESS-CERTIFICATE.json` only
   on a full pass. Use `--plan` to see the phase plan; `--upto PHASE` to stop early.
5. **Deliver locally.** Assemble the labeled bundle in
   `~/Downloads/Anthology-<slug>-<MM-DD-YYYY>/`. No n8n / Airtable / Drive / Slack
   / Gmail. Any client notification rides the client's own gateway, silent by default.

## Guardrails (all fail-closed)
- No certificate = not done.
- The provers MEASURE the stripped text; a self-reported count is ignored.
- Every model id must be NON-Anthropic; the run ledger is checked (AF-AW-ANTHROPIC).
- A hand-rolled external uploader/notifier in the run dir aborts the run
  (AF-AW-ENTRY-BYPASS).
- **Subprocess timeout (AF-AW-PROVER-TIMEOUT):** every prover call has a 300s
  ceiling. A hung prover (deadlocked, infinite loop, stalled upstream model call)
  is killed and the phase fails closed with `AF-AW-PROVER-TIMEOUT`. The stderr
  message names the hung prover and offers clear diagnostic guidance. Timeouts are
  never re-launched — the operator must diagnose the hung prover before re-running.
  A prover that exits NONZERO (without timing out) IS retried automatically: up to
  3 attempts with 1s/2s backoff, then the phase fails closed.
- **Degraded handling:** if the NON-Anthropic upstream model is unreachable or
  returns an error, the authoring stage leaves no artifact; the corresponding QC
  phase sees a missing artifact and fails closed. The orchestrator never falls
  back to an alternate provider or retries automatically. Every behavior surface
  is deterministic and observable through the process manifest + run ledger.

## Command Center Board (optional)

The `mc_board.py` helper gives each run a Kanban card on the Command Center
board. It is **fail-soft**: every env var is OPTIONAL; absent base URL => board
disabled (clean no-op, run continues). The board is a VIEW, never a gate.

| Variable | Default | Purpose |
|---|---|---|
| `COMMAND_CENTER_URL` | (unset) | Base URL of the Command Center. Board disabled when unset. `MISSION_CONTROL_URL` is an accepted alias. |
| `MISSION_CONTROL_URL` | (unset) | Alias for `COMMAND_CENTER_URL`. |
| `CC_API_TOKEN` | (unset) | Long-lived bearer token for Authorization header. `MC_API_TOKEN` is an accepted alias. |
| `MC_API_TOKEN` | (unset) | Alias for `CC_API_TOKEN`. |
| `WEBHOOK_SECRET` | (unset) | HMAC-SHA256 secret for the `x-webhook-signature` header. `CC_WEBHOOK_SECRET` is an accepted alias. |
| `CC_WEBHOOK_SECRET` | (unset) | Alias for `WEBHOOK_SECRET`. |
| `CC_BOARD_TIMEOUT` | `8` | Per-request timeout in seconds (integer). |
| `CC_STATUS_PATH_TEMPLATE` | `/api/tasks/{id}` | Status-write URL path; must contain the literal `{id}`. |
| `CC_STATUS_METHOD` | `PATCH` | HTTP method for status writes. |
| `CC_TASK_PATH_TEMPLATE` | `/api/tasks/{id}` | Task-read URL path; must contain the literal `{id}`. |
| `MC_BOARD_EVIDENCE_BASE_DIR` | (unset) | Override run-evidence root for the `reconcile` sweep. |

At minimum set `COMMAND_CENTER_URL` to enable the board. With a secured
Command Center also set `CC_API_TOKEN` and `WEBHOOK_SECRET`.

## Verify / CI
```
bash 54-anthology-writer/verify.sh      # read-only, idempotent, exits nonzero on regression
bash 54-anthology-writer/verify-deps.sh # dependency check (python3)
```
