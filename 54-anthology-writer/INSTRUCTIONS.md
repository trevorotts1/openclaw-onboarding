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
3. **Author on the client's own providers** (upstream sub-agents write the
   artifacts into `<RUN_DIR>/working/`): `tone-doc.md`, `title.json`,
   `outline.md`, `chapter.md`, and a `RUN-LEDGER.json` recording the resolved
   NON-Anthropic model per stage.
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

## Verify / CI
```
bash 54-anthology-writer/verify.sh      # read-only, idempotent, exits nonzero on regression
bash 54-anthology-writer/verify-deps.sh # dependency check (python3)
```
