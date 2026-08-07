# Book Writer Mini-App — U18 Playwright e2e suite (T1–T10)

Headless, offline e2e battery for the mini-app SPA. It serves the **real**
production SPA (U05 `pages/index.html` + `pages/app.js`) through a local stub
Worker and drives every feature end-to-end in a real browser. A stub GHL
endpoint records every write keyed by `location_id`, so **browser-level
isolation** (T10) is PROVEN — alpha's answers never reach beta's location.

## What it covers

| Test | What it proves |
|------|----------------|
| T1 | Universal link `/<slug>/<phase>?tk=` opens the warm UI (render check) |
| T2 | Warm copy + exactly ONE question per screen |
| T3 | "Question 1 of N" progress rail renders |
| T4 | Typed answer submits and advances; mandatory questions gate the advance |
| T5 | Upload path: `.txt` file input → staged; PDF tab never fabricates a done |
| T6 | Recorder widget renders with permission/camera gates; graceful denial; granted tap → Stop |
| T7 | Answer-your-way tabs switch modes; editable transcript |
| T8 | Save & resume: reload → resume at the next-unanswered question |
| T9 | Completion screen + celebration after the last question |
| T10 | Two fake clients → answers land in the RIGHT client's stub GHL (isolation) |

## How it works

- `harness/server.mjs` — a stub Worker that mirrors the U02 route
  (`/<slug>/<phase>?tk=` → SPA + injected `bw-bootstrap`), serves the REAL page
  modules, and routes the SPA's API calls to the REAL Worker modules
  (`worker/src/answers.js`, `worker/src/save.js`, `worker/src/lib.js`) over an
  in-memory KV store. It also implements a stub GHL endpoint that records every
  contact/note write keyed by `location_id` and refuses any bearer token that
  does not match the payload's location.
- `fixtures/index.mjs` — the fictitious clients (alpha / beta / gate1), their
  KV binding rows (the SOLE destination authority), and the real U01 configs.
- `tests/` — the T1–T10 Playwright specs.
- `node harness/server.mjs --selftest` — harness self-test (boots the server,
  proves SPA serving, 401 misfit/missing-token, and the real U03 idempotency).

## Run

```sh
cd 53-book-writer/mini-app/e2e
npm install          # @playwright/test
npx playwright install chromium   # once (revision 1234, headless shell)
npm test            # npx playwright test (headless)
```

All tests are headless (no popups, no OS media devices — Chromium runs with a
fake media device for the recorder's granted path). No real client feed is ever
contacted: the stub GHL is the only transport.

## Constraints honored

- NO Anthropic ids anywhere.
- NO real creds / real hosts / real client names — only `FictitiousClient`-style
  alpha/beta/gate1 and local `127.0.0.1`.
- NO `{{...}}` placeholders in shipped code.
- Headless only.
