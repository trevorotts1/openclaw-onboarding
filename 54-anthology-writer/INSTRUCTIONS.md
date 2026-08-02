# Anthology Writer (Skill 54) — Operator Instructions

## When to use
A multi-contributor anthology where each contributor needs ONE finished chapter
(2,000–3,500 words) in their own blended voice, plus tone doc, locked
title/subtitle, blurb, and outline. For a single-author book use **Skill 53
(Book Writer)** — the two share the tone core but are separate skills.

## One contributor, end to end
1. **Preflight the box** (resolve the client's own NON-Anthropic tiers):
   ```
   bash 54-anthology-writer/preflight.sh --run-dir <RUN_DIR>
   ```
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
