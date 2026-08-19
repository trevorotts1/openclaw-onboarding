# Presentation Interview app — deployable source + question wiring

The **Presentation Interview app**: a Cloudflare-hosted intake frontend that asks
12 intake questions one at a time (7-9 core, hard cap 20), shows a segmented
**"Question N of 12"** progress bar, captures a **logo** ("no logo on file —
provide one or build without?") and **image links**, and on **Submit** stores the
answers on the box and **pushes them to the presentation department** (starting
the kanban flow — no shortcuts).

This directory is the deployable source + question wiring that lives in the repo.
The working copy lives at `Downloads/GAUNTLET-LOOP-WORK/LOOP2B-INTERVIEW-APP/app`.

## Question wiring (the single source of truth)

Edit the canonical JSONs, not the app, to change what a client is asked:

- `../deck-intake-questions.json` (v1.3.0) — the deck-intake question bank. Now
  includes the **new upsell yes-no questions**: `want_sales_checkout` (order 7.6,
  "Do you need me to create a sales page and a checkout page...?") and
  `want_vsl_page` (order 7.7, "Would you like a VSL page...?") plus their
  declined-reason follow-ups and `waiver_field_mapping` entries. It also carries
  the speech-speed question `speech_speed_preference` (order 7.5).
- `../upsell-questions.json` — the standalone upsell question set (signature-mode
  loading). Same definitions as the orders 7.6/7.61/7.7/7.71 entries in
  deck-intake-questions.json.

`payload/build_questions_payload.py` selects the curated 12-question set by id
(`DEFAULT_CURATED`) and projects the UI fields from these canonical files. The
app's `questions.json` is a snapshot of that projection.

## Files

| Path | What it is |
|---|---|
| `pages/index.html` | The one-question-per-screen UI (single static file, brand-locked) |
| `pages/questions.json` | The curated question set snapshot |
| `worker/src/index.js` | Cloudflare Worker — session API + `/api/intake` (+ `/api/intake/list`) + `/api/dept-start` |
| `worker/src/lib.js` | Pure, unit-tested logic (ordering, validation, progress) |
| `worker/schema.sql` | D1 schema (`sessions`, `answers`, `intakes`) |
| `worker/wrangler.toml` | Worker + D1 + route config — **domain placeholders** |
| `payload/build_questions_payload.py` | Generates the curated payload FROM the canonical JSONs |
| `bridge/intake_writer.py` | Box-side: assemble dept-format `intake.json` + completed ledger |
| `bridge/intake_bridge.py` | Box-side: pull a finished intake, stamp the run dir, start the dept |
| `test/` | Offline gates |

## Submit trigger

On Submit the app builds a dept-format intake record and:
1. **stores the answers** — POST to the Worker `/api/intake` (or a client-side
   `intake-<session>.json` download when no sink is wired);
2. **triggers the department** — `bridge/intake_bridge.py ingest` stamps the run
   dir (`working/copy/intake.json` + `working/interview/intake_ledger.json` +
   `working/interview/intake_transcript.json` — the GATE 0b conversation trace)
   and calls `cc_board.ingest_deck_task` → Command Center kanban card
   (`department_slug: presentations`), OR the Worker `/api/dept-start` POSTs
   `/api/tasks/ingest` directly.

No shortcuts: the deck can only build through
`presentation-canonical-entry.sh`'s governed gates (GATE 0 intake ledger, GATE 0b
intake trace, GATE 1 deps, GATE 2 bypass-scan, GATE 3 version/hash pin).

## Box-side intake poll cron

The box discovers finished intakes by polling the Worker's
`GET /api/intake/list` (admin-auth; returns stored session metadata), then
ingests each session once via `bridge/intake_bridge.py poll`:

```bash
python3 bridge/intake_bridge.py poll \
  --worker-url "https://presentation-interview.<FLEET_DOMAIN>" \
  --run-dir "<presentations-runs-dir>" \
  --poll-ledger "<ledger-path>/processed.txt" \
  --per-session-dirs
```

`poll` fetches the list, ingests each not-yet-processed session (writes
`working/copy/intake.json` + `working/interview/intake_ledger.json` via
`intake_writer.py`, then calls `cc_board.ingest_deck_task` → Command Center
kanban card), and records the session id in the ledger so the next poll skips
it (idempotent). A failed ingest is NOT marked processed and is retried on the
next poll.

Box env requirements (sourced from `~/.openclaw/secrets/.env`):
- `INTAKE_ADMIN_TOKEN` — box→worker auth; MUST match the Worker secret.
- `MISSION_CONTROL_URL` / `COMMAND_CENTER_URL` — CC board base URL (cc_board).
- `WEBHOOK_SECRET` / `CC_WEBHOOK_SECRET` — HMAC signing for cc_board.

Suggested cron (every 5 min):
```
*/5 * * * * /bin/bash $HOME/<bridge-dir>/poll.sh >> $HOME/<bridge-dir>/logs/poll.log 2>&1
```

The Worker's `/api/dept-start` fallback is only used when the box is not in
the loop — the box-side `poll` is the primary path (it reaches the local CC
board directly).

## Tests (offline)

```
node --test test/test_worker.mjs
python3 test/test_intake_writer.py
python3 test/test_payload.py
python3 payload/build_questions_payload.py --selftest
```

## Deploy

See the `intake-miniapp` DEPLOY.md (same Worker + D1 + Pages pattern). Fill the
`<PLACEHOLDER>` tokens in `worker/wrangler.toml` at deploy time. Suggested host:
`presentation-interview.<FLEET_DOMAIN>`. Secrets: `INTAKE_ADMIN_TOKEN`,
`COMMAND_CENTER_URL`, `CC_DEPT_START_TOKEN`.

## D2/D3 reconciliation — canonical status (added 2026-08-19)

**This directory (`intake/interview-app/`) is the evidence-based canonical
intake app, not `../../intake-miniapp/`.** Per Wave D / Units D2+D3 of
`CONTROL/MASTER-WORK-ORDER-20260818.md`, quoting the evidence:

1. **The bridge script actually running in production** (the Downloads working
   copy's `app/intake_bridge.py`) is a 19-line diff from this directory's
   `bridge/intake_bridge.py`, versus a 413-line diff from
   `../../intake-miniapp/bridge/intake_bridge.py` — i.e. it descends from
   *this* app, not the mini-app.
2. **This app's own working-copy pointer** (line 11 above) already names
   `Downloads/GAUNTLET-LOOP-WORK/LOOP2B-INTERVIEW-APP/app` as its deployed
   copy — a first-party claim the mini-app's README does not make about itself
   against the same working copy.
3. **The repo's own wiring references this app**, not the mini-app:
   `DEPARTMENT-COUNTS-CANONICAL.md` cites `DEPT/intake/interview-app/` as "the
   deployed interview app" and names `intake/interview-app/bridge/intake_bridge.py`
   as the module `cc_board.ingest_deck_task()` is reached through.

`../../intake-miniapp/README.md`'s self-description as "the primary intake
surface" predates this evidence and is now marked deprecated there, pointing
back here — see that file. It is **not deleted**; some of its files (the
session-API contract with `confirm_code`, and `pages/skip-defer.js`) are
exactly what production actually runs — see `deployed-r2/README.md` below.

**`deployed-r2/`** (new, landed 2026-08-19): the actual R2-backed single-worker
source that is live today, since D1 was never provisionable. It is a hybrid —
session-API shape from `intake-miniapp`, `/api/intake` + `/api/dept-start` from
this app's `worker/`, plus new static-asset + R2 plumbing neither app had. Full
file-by-file provenance and the removal recommendation for the mini-app are in
`deployed-r2/README.md`. **Nothing in this repo was deployed as part of this
landing — direction is deployed → git only.**
