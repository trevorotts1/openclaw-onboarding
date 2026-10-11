# Drama Studio Mini-App — Deploy Files (U4)

Deploy-side files for the Drama Studio mini-app. **This unit ships files only.**
It performs no deployment: no `wrangler` call, no Cloudflare mutation, no bucket
or secret creation, no token use. The real deploy is a separate, later,
Trevor-authorized step (JOINT PLAN row "Deploy").

Reuses the Book Writer deploy pattern (`53-book-writer/mini-app/deploy/`).

| File | What |
|---|---|
| `deploy.sh` | resolve → zone guard → bucket → 45-day retention → two secrets → Worker deploy, with `--dry-run` and `--self-test` |
| `deploy.manifest.json` | the deploy contract: worker name, route host, bucket, retention, the two secret **names**, and the intended zone |
| `DEPLOY.md` | this file |

Ownership: U2 owns `mini-app/worker/` (service), U3 owns `mini-app/pages/`
(UI), U12 owns pairing/admin/key. **U4 owns `mini-app/deploy/` only.**

---

## 1. The trust layer

- **`worker/wrangler.toml` (U2) keeps every real id as `<PLACEHOLDER>`.** `deploy.sh`
  is the only thing that resolves them, at deploy time, into a **throwaway temp
  config** in `$TMPDIR` (deleted on exit) handed to `wrangler deploy --config`.
  The toml itself is never rewritten. Nothing real lands in git.
- **The token value is env-only.** `CLOUDFLARE_DRAMA_STUDIO_API_TOKEN` is
  forwarded to `CLOUDFLARE_API_TOKEN` per command. No token value is committed or
  printed.
- **Secret values are env-only.** The manifest lists the two secret **names**
  (`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`); the values are read from the
  environment and piped to `wrangler secret put` stdin. They are never echoed.
- **No real zone or account id is committed.** The guard's intended-account pin
  is supplied by the operator at deploy time (ids are public; secrets are not).

---

## 2. The zone guard

The studio deploys into the **BlackCEO Cloudflare account** only. The guard is a
hard, non-disableable gate that refuses any other zone:

1. **G1 (wrong zone name)** — the target zone name must equal the manifest's
   intended zone name (`zerohumanworkforce.com`). A different name is refused.
2. **G2 (foreign-zone landmine)** — the target zone id must not equal a known
   foreign zone id (`STUDIO_FOREIGN_ZONE_ID`, e.g. the `businessaftersixty.com`
   zone). Refused if equal.
3. **G3 (wrong account)** — when the intended account is pinned
   (`STUDIO_INTENDED_ACCOUNT_ID`), the target account id must equal it.
4. **G4 (unresolved)** — a live run must resolve a real zone id **and** account
   id. An empty "not found" is a **FAIL**, never a pass.

In `--dry-run` without a token nothing can be resolved, so the ids print as
`<unresolved>`, a warning states **no PASS is claimed**, and the plan continues
only because a dry-run performs no mutations. A dry-run **never** prints
`zone-guard: PASS` with unresolved ids.

Prove it offline: `./deploy.sh --self-test` (no token, no network) exercises the
refusals and confirms `--dry-run` is PLAN-only.

---

## 3. Usage

```sh
./deploy.sh --dry-run deploy        # validate + plan, no mutations
./deploy.sh --dry-run status
./deploy.sh --self-test             # offline guard proof
```

Live (token needed — **not part of this unit**):

```sh
export CLOUDFLARE_DRAMA_STUDIO_API_TOKEN="..."   # value from env only
export STUDIO_INTENDED_ACCOUNT_ID="<blackceo account id>"   # guard pin
./deploy.sh deploy                               # the real deploy
```

Optional env overrides (used to prove the guard):

- `STUDIO_ZONE_NAME` — target zone name (a different name is refused).
- `STUDIO_ZONE_ID` / `STUDIO_ACCOUNT_ID` — pin the target ids.
- `STUDIO_INTENDED_ACCOUNT_ID` — pin the intended BlackCEO account id.
- `STUDIO_FOREIGN_ZONE_ID` — the foreign zone id the landmine refuses.

---

## 4. Deploy flow (`deploy`)

1. **Preflight** — manifest + `deploy.sh` present, `npx` available; the U2 service
   config is reported honestly (required only for a live deploy).
2. **Resolve** — zone id + account id (live API, or supplied overrides).
3. **Zone guard** — the hard gate (section 2).
4. **R2 bucket** — create `zhw-drama-studio` if missing (idempotent).
5. **Retention** — 45-day lifecycle rule on the `projects/` prefix (scoped
   project-object retention).
6. **Secrets** — `wrangler secret put` the two `R2_*` secrets, values from env.
7. **Worker deploy** — `wrangler deploy` with the throwaway temp config.

The real deploy is the plan's separate "Deploy" row: *one bucket, two secrets,
scoped project-object 45-day retention; `deploy.sh --dry-run` then real deploy.*

---

## 5. Honesty contract

- `--dry-run` prints `PLAN` for every step and performs **zero** wrangler or API
  calls. It reports unresolved ids as `<unresolved>` and never claims a
  zone-guard PASS it could not prove.
- Every live step prints `STEP`; the final line says `DONE deploy` only after the
  real commands succeeded (or `DRY-RUN COMPLETE` with a no-mutation reminder).
- Secrets are never echoed. Zone/account ids are not secrets and are printed so
  an operator can audit which zone was resolved.
