# Book Writer Mini-App — Deploy / Rollback / Config-Flip (U19)

The operator's single entry point for deploying the Book Writer mini-app edge to
Cloudflare. Everything here is executed by **`deploy/deploy.sh`** through
**`npx wrangler`**, authenticated by the operator's own
**`CLOUDFLARE_ZHW_APPS_API_TOKEN`** (token **name only** in comments — the
**value** is always read from the environment, never committed).

> Read `worker/wrangler.toml` and `worker/schema.sql` first — they are the
> contract this script resolves.

---

## 1. What actually gets deployed

| Layer | What | Where it lives |
|---|---|---|
| Worker code | `book-writer-mini-app` (U02 core, single engine) | `worker/src/` → uploaded via `npx wrangler deploy` |
| Route | `bookwriter.zerohumanworkforce.com/*` | `wrangler.toml` `routes` |
| R2 bucket | `zhw-bookwriter` | created idempotently |
| R2 app shell | `app/<version>/index.html` + `app/<version>/app.js` | versioned, immutable per version |
| R2 pointer | `app/latest` = `{"version": "<version>"}` | the **config flip** atomic unit |
| R2 phase configs | `config/<slug>/<phase>.json` (incl. `P0-INTAKE:full.json` / `P0-INTAKE:4x3x3.json`) | data, never code |
| KV namespace | `bw_bindings` | created idempotently, seeded idempotently |
| KV seed | `reg:fake-alpha`, `reg:fake-beta`, `reg:fake-gate1` registry markers | per-client rows land on the box (U12), never here |
| Secrets | `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | via `wrangler secret put` (stdin), never in the repo |

### The trust layer

- **`wrangler.toml` keeps every real id as `<PLACEHOLDER>`.** `deploy.sh` is the
  only thing that resolves them, at deploy time, into a **throwaway temp config
  in `/tmp`** (deleted on exit) that is handed to `wrangler deploy --config`.
  **`wrangler.toml` itself is never rewritten.** Nothing real lands in git.
- **The token value is env-only.** `CLOUDFLARE_ZHW_APPS_API_TOKEN` is forwarded
  to `CLOUDFLARE_API_TOKEN` (wrangler's native auth var) per command. No key is
  embedded anywhere in this tree.
- **The edge is a DUMB RELAY.** It holds zero client GHL credentials. The KV
  binding row is the **sole** destination authority (master-plan section 3).
  No Anthropic ids, no `{{...}}`, no client keys anywhere.

---

## 2. The ZONE LANDMINE (read this before anything else)

**`zerohumanworkforce.com` is a DIFFERENT Cloudflare zone from
`businessaftersixty.com`.** Their zone ids are different. **Never** reuse
`CLOUDFLARE_ZONE_ID` (or any id that resolves to the businessaftersixty.com
zone) for a `*.zerohumanworkforce.com` binding.

`deploy.sh` **enforces this as a hard, non-disableable gate**:

1. It resolves the **literal** zone id for `zerohumanworkforce.com` from the
   Cloudflare API (token already in the environment).
2. It also resolves the zone id for `businessaftersixty.com`.
3. It **refuses to run** (exit non-zero) if:
   - the zerohumanworkforce.com id **equals** the businessaftersixty.com id
     (the landmine itself), **or**
   - either id cannot be resolved to a real value (an empty "not found" is a
     **FAIL**, never a pass — we cannot prove we are NOT on the wrong zone
     without knowing both ids).

In `--dry-run` without a token nothing can be resolved, so the script prints
the ids as **`<unresolved>`**, prints a warning that **no PASS is claimed**, and
continues the plan only because a dry-run performs no mutations. A dry-run
**never** prints `zone-guard: PASS` with unresolved ids.

> Verifying the guard: `./deploy.sh --self-test` (offline) proves the guard
> refuses when both ids are pinned equal, and that `--dry-run` is PLAN-only and
> never fabricates a PASS.

---

## 3. Usage

All commands accept `--dry-run` first:

```sh
./deploy.sh --dry-run deploy        # validate + plan, no mutations
./deploy.sh --dry-run status
./deploy.sh --dry-run flip v1
./deploy.sh --dry-run rollback
```

Live (token needed):

```sh
export CLOUDFLARE_ZHW_APPS_API_TOKEN="..."          # value from env only
./deploy.sh deploy [VERSION]                        # full provision + deploy
./deploy.sh status                                  # active app version
./deploy.sh flip <VERSION>                          # activate an R2 app version
./deploy.sh rollback [VERSION]                      # flip back to previous
```

Optional env overrides (for testing only):

- `ZONE_ID_ZHW` / `ZONE_ID_BAS` — pin the two zone ids (used to prove the guard).
- `CLOUDFLARE_ACCOUNT_ID` — pin the account id instead of deriving it from the zone.
- `VERSION_SUFFIX` — append a label to the generated version id.

---

## 4. Deploy flow (`deploy`)

1. **Preflight** — files present, `npx` available, token set (live only).
2. **Resolve** — account id + both zone ids (live API, or overrides).
3. **Zone-landmine guard** — hard gate (section 2).
4. **R2 bucket** — create `zhw-bookwriter` if missing (idempotent).
5. **KV namespace** — create `bw_bindings` if missing; the id is captured from
   the API/wrangler output and kept in the process (never written to git).
6. **R2 app bundle** — upload `app/<version>/index.html` + `app/<version>/app.js`.
7. **R2 phase configs** — upload every `configs/*.json` to
   `config/<slug>/<phase>.json` for the marker slugs (`fake-alpha`,
   `fake-beta`, `fake-gate1`). `P0-INTAKE-full.json` → `P0-INTAKE:full.json`,
   `P0-INTAKE-4x3x3.json` → `P0-INTAKE:4x3x3.json` (matches `configObjectPath`
   in `worker/src/lib.js`).
8. **KV seed** — write the `reg:*` registry markers (idempotent put).
9. **Secrets** — `wrangler secret put` the three `R2_*` secrets **only if** their
   env vars are set; an unset secret is reported as an honest skip (the Worker
   fails closed on media upload until set).
10. **Config flip** — write `app/latest` = `{"version": "<version>"}` and append
    the version to `app/versions.json` (the rollback index).
11. **Worker deploy** — `wrangler deploy` with the throwaway temp config.

---

## 5. Rollback

Rollback is a **config flip only** — no Worker code change, no recompile,
instant. The Worker reads the `app/latest` pointer on every request
(`loadAppShell` in `worker/src/lib.js`).

```sh
./deploy.sh rollback          # flip app/latest back to the previous version
./deploy.sh rollback v20260807-103000   # flip to a specific version
```

`app/versions.json` is the deploy-side index `rollback` reads to find the
previous version. Because the pointer flip is atomic (one R2 object write), a
rollback cannot land mid-request.

---

## 6. How to verify

**After a deploy:**

```sh
./deploy.sh status                 # shows the active app/<version> from app/latest
curl -i https://bookwriter.zerohumanworkforce.com/api/answers -X POST
# expect 400/401 (missing/bad token) — the Worker is alive and fail-closed
```

**A phase link returns the SPA + injected config** (with a real token binding):

```sh
curl -i "https://bookwriter.zerohumanworkforce.com/<slug>/<phase>?tk=<token>"
# expect 200 text/html, <script id="bw-bootstrap"> with data-config/data-context
```

**After a rollback/flip:** repeat `status` and the phase-link curl — the served
shell should be the target version. Because `Cache-Control: no-store` is set on
the response, there is no CDN cache to bust.

---

## 7. Honesty contract (no fabricated output)

- `--dry-run` prints `PLAN` for every step and performs **zero** wrangler or API
  calls. It reports unresolved ids as `<unresolved>` and never claims a
  zone-guard PASS it could not prove.
- Every live step prints `STEP`; the final line says `DONE deploy <version>`
  only after the real commands succeeded (or `DRY-RUN COMPLETE` with a
  no-mutation reminder).
- Secrets are never echoed. Zone ids are not secrets and are printed so an
  operator can audit which zones were resolved.
