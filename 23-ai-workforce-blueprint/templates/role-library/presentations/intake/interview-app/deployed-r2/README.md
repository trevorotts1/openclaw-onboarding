# Deployed R2 worker — reconciliation landing (D2, 2026-08-19)

**This directory is the exact source of the Cloudflare Worker that is actually
live at the presentation-interview public endpoint today.** It was landed here
by copying (byte-identical, verified by `diff`) from the working copy at
`~/Downloads/GAUNTLET-LOOP-WORK/LOOP2B-INTERVIEW-APP/deploy/`, per Wave D /
Unit D2 of `CONTROL/MASTER-WORK-ORDER-20260818.md`: "GitHub is source of
truth. Live-ahead code gets merged INTO git, never the reverse."

**Confirmed live at time of write:** a read-only `GET /healthz` on 2026-08-19
returned `HTTP 200 {"status":"ok","service":"presentation-intake","ttl_days":7}`
— matching FABLE-TRUTH §3's 2026-08-18 probe exactly.

## Why this exists as its own directory instead of replacing `../worker/`

`../worker/` (the parent `interview-app`'s own worker) is a **D1-backed**
design: `[[d1_databases]]`, `env.DB.prepare(...)`. FABLE-TRUTH §3 records that
**D1 was never provisionable with the available API token's scopes**, so what
actually got deployed is a **different, R2-backed build** — not `../worker/`
verbatim, and not `../../intake-miniapp/worker/` verbatim either. It is a
genuine hybrid of both repo apps plus new single-worker plumbing neither app
had. This directory preserves that hybrid exactly as it runs, rather than
overwriting `../worker/`'s D1 design (which remains the forward-looking target
for whenever D1 becomes provisionable — see "Recommendation" below).

## What is actually in this directory, and where each piece came from

| File | Verified relationship |
|---|---|
| `src/index.js` | **New.** Header comment self-identifies as the mini-app ("Presentation intake mini-app"). Session API shape (mint/get/answer/poll/complete, `confirm_code`, `sixDigitCode`) matches `../../intake-miniapp/worker/src/index.js`'s contract. `/api/intake`, `/api/intake/list`, `/api/dept-start` (including the literal default description string `"Intake captured by the Presentation Interview app."`) are near-verbatim from `../worker/src/index.js`. Static-asset serving (`env.ASSETS`) and R2 storage (`env.STORE`, key-prefix scheme) exist in **neither** repo app — this part is genuinely new, written for the single-worker deploy. |
| `src/lib.js` | **Byte-identical** to `../../intake-miniapp/worker/src/lib.js` (verified: `diff` returns nothing). Confirmed by its own header comment: "This is the SAME contract the repo's intake-miniapp uses." |
| `public/index.html` | Byte-identical to the Downloads working copy's `app/index.html`, which is an **older snapshot** of `../pages/index.html` (interview-app's UI) — specifically, it predates the fix that stopped `payload()` from hardcoding `presentation_type: "from_scratch"` and that added the `presentation_type` intake question (order 0). **The current `../pages/index.html` in this repo is ahead of what's deployed.** If this worker is ever redeployed, `../pages/index.html` should replace this file first — that is a deploy decision for Trevor, not made here. |
| `public/skip-defer.js` | Byte-identical to `../../intake-miniapp/pages/skip-defer.js` (verified: `diff` returns nothing). |
| `wrangler.toml` | **Rewritten for this landing** — same shape as the deployed config (single-worker, `[assets]` block, `[[r2_buckets]]` binding `STORE`/`presentation-intake`), but **`account_id` and the route's zone/domain are parameterized as `<PLACEHOLDER_CF_ACCOUNT_ID>` / `<PLACEHOLDER_FLEET_DOMAIN>`**, matching the convention already used in `../worker/wrangler.toml` and `../../intake-miniapp/worker/wrangler.toml`. The real values live only in the Downloads working copy's `deploy/wrangler.toml` and were never read into or copied out of this repo. |
| `package.json` | **New**, written for this landing (deploy scripts for the R2/static-assets build; no D1 create/schema steps since this variant has none). |

## What was deliberately NOT copied here

- `deploy/.wrangler/` (build cache) — not source, not copied.
- `deploy/package-lock.json` (1,497 lines) — regenerable from `package.json`; the sibling apps in this repo don't carry lockfiles either, so this follows existing convention.
- The real `account_id` / route / zone values — never left the Downloads working copy or entered this repo. `wrangler.toml` above states the shape only.

## Secrets

Confirmed by grep on every file in this directory: **no account ids, API tokens, or keys are present** (see D2 verification report in the parent unit's final message for the exact grep command and "clean" result).

## Recommendation for Trevor (not executed here — see `../README.md` and `../../intake-miniapp/README.md`)

Once D1 becomes provisionable, `../worker/` (the D1 design) is the intended
long-term contract per its own docstring. Until then, **this directory is the
one that matches production** and should be treated as canonical for any
operational question ("what does the live worker actually do"). Do not deploy
from this directory without Trevor's explicit go — this landing is
GIT-DIRECTION ONLY (deployed → git), not the reverse.
