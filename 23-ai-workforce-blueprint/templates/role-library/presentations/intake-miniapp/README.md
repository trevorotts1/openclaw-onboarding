# Presentation Intake mini-app

> **⚠️ DEPRECATED — 2026-08-19, D2/D3 reconciliation (see
> `CONTROL/MASTER-WORK-ORDER-20260818.md` Wave D).** The "primary intake
> surface" claim below predates evidence gathered on 2026-08-19: the app that
> is actually deployed, bridged, and referenced by this repo's own wiring is
> **`../intake/interview-app/`**, not this directory. Specifically —
> the deployed working copy's `intake_bridge.py` is a 19-line diff from
> `interview-app/bridge/intake_bridge.py` vs a 413-line diff from this
> directory's `bridge/intake_bridge.py`; `interview-app/README.md` names the
> deployed working copy as its own; and `DEPARTMENT-COUNTS-CANONICAL.md`
> cites `interview-app/` as "the deployed interview app." Full evidence in
> `../intake/interview-app/README.md`'s "D2/D3 reconciliation" section and
> `../intake/interview-app/deployed-r2/README.md`.
>
> **Not deleted** — Trevor's call, not made here (see the removal
> recommendation in `deployed-r2/README.md`). Two pieces of this app's code
> ARE exactly what production runs today: `worker/src/lib.js` (the
> `confirm_code` / session-API contract) and `pages/skip-defer.js` — both are
> already vendored byte-identical into
> `../intake/interview-app/deployed-r2/`, so nothing here is at risk of being
> lost if this directory is later removed.

The **primary intake surface** for a deck run: a hosted, one-question-per-screen
web form. Chat (the §3 `deck-intake-driver.py` turn-gate) remains the fallback.

## Why it exists

An LLM can compose two questions in one chat message; a form physically cannot.
This app renders **one question per screen** and the Worker API **rejects any
out-of-order answer**, so question-batching (`AF-INTAKE-BATCH`) is not merely
discouraged — it is impossible. It is a **front-end to the existing intake state
machine, not a second state machine**: every answer is replayed through
`deck-intake-driver.py`, so `intake_ledger.json`, the provers, Gate 0 and
`presentation-canonical-entry.sh`'s GATE 0 are all unchanged (the intake-ledger
check was relocated from the retired `deck-build-guard.sh`, U025).

## Pieces

| Path | What it is |
|---|---|
| `worker/src/index.js` | Cloudflare Worker — the API (mint / read / answer / poll / complete) |
| `worker/src/lib.js` | Pure, unit-tested logic (tokens, order-enforcement, validation) |
| `worker/schema.sql` | D1 schema (`sessions`, `answers`) |
| `worker/wrangler.toml` | Worker + D1 + route config — **domain placeholders, see DEPLOY.md** |
| `pages/index.html` | The one-question-per-screen UI (single static file, theme-aware) |
| `payload/build_questions_payload.py` | Generates `questions_payload` FROM the canonical intake JSONs |
| `bridge/intake_bridge.py` | Box-side: `mint` a session, `sync` answers into the driver |
| `test/` | Offline gates: `node --test` (worker) + `unittest` (payload, bridge) |

## Flow

```
Buddy/Director opens a run
  └─ box: build_questions_payload.py --set standard|signature --run-id R > payload.json
  └─ box: intake_bridge.py mint --worker-url … --run-id R --box-id B --questions payload.json
       → Worker mints a 128-bit capability token, returns https://intake.<domain>/s/<token>
  └─ box speaks the link (and optional 6-digit code) to the client in chat

Client opens the link
  └─ Pages UI: GET /api/sessions/<token>  → renders ONE question at a time
  └─ each answer: POST /api/sessions/<token>/answers   (server rejects out-of-order)
  └─ finishes: POST /api/sessions/<token>/complete

Box picks the answers up
  └─ intake_bridge.py sync --worker-url … --token <token> --run-dir <run> --question-set …
       → polls GET …/answers?since=<cursor>
       → replays each: deck-intake-driver.py --answer <id> "<text>"  then  --next
       → on completion: --complete   (standard)
                        --signature --record <record>   (signature → prove_sp_intake.py)

Post-form follow-up
  └─ Buddy reviews the answers and asks only genuine clarifiers (in chat, one at a
     time via the §3 driver), then runs the ECHO.
```

## Single source of truth

The app never hardcodes a question. `build_questions_payload.py` reads the
canonical JSONs and the UI renders their `prompt` / `help` / `kind` /
`allowed_values` / `value_labels` verbatim:

- standard → `../intake/deck-intake-questions.json`
- signature → `../../../../../51-signature-presentation/intake/sp-8-questions.json`
  (q1–q8 + the frame-selection question)

Edit the JSONs, not the app, to change what a client is asked.

## Auth model

- **Client endpoints** are gated by the **capability token** in the URL (128-bit,
  7-day expiry, single active session per run). No login. HTTPS only. No secrets
  in the page. An optional **6-digit confirmation code** (spoken in chat) can be
  required on top for high-trust clients.
- **Session mint** (`POST /api/sessions`) is gated by a box→worker bearer secret
  `INTAKE_ADMIN_TOKEN` so random visitors can't create sessions.

## Degradation

If the Worker is unreachable, `intake_bridge.py sync` exits non-zero and the box
falls back to the chat driver. The driver never depended on the app.

## Tests (offline)

```
node --test test/test_worker.mjs
python3 test/test_payload.py
python3 test/test_bridge.py
python3 payload/build_questions_payload.py --selftest
```

## Deploy

See `DEPLOY.md`. The production hosting **domain is the operator's Cloudflare
zone** — it is flagged, not guessed. Every zone/account/db id in `wrangler.toml`
is a `<PLACEHOLDER>` to fill in at deploy time.
