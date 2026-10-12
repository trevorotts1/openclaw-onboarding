# Drama Studio Mini-App — Deploy Files (U4)

Deploy-side files for the Drama Studio mini-app. **This unit ships files only.**
It performs no deployment: no `wrangler` call, no Cloudflare mutation, no bucket
or secret creation, no token use. The real deploy is a separate, later,
Trevor-authorized step (JOINT PLAN row "Deploy").

Reuses the Book Writer deploy pattern (`53-book-writer/mini-app/deploy/`).

| File | What |
|---|---|
| `deploy.sh` | resolve → zone guard → **read-only scope preflight** → bucket → 45-day retention → KV namespace → secrets → Worker deploy → DNS, each on its own token, with `--dry-run` and `--self-test` |
| `deploy.manifest.json` | the deploy contract: worker name, absolute service entry, route host, bucket, KV binding, retention, the required/optional secret **names**, and the intended zone |
| `DEPLOY.md` | this file |

Ownership: U2 owns `mini-app/worker/` (service), U3 owns `mini-app/pages/`
(UI), U12 owns pairing/admin/key. **U4 owns `mini-app/deploy/` only.**

---

## 1. The trust layer

- **`worker/wrangler.toml` (U2) keeps every real id as `<PLACEHOLDER>`.** `deploy.sh`
  is the only thing that resolves them, at deploy time, into a **throwaway temp
  config** in `$TMPDIR` (deleted on exit) handed to `wrangler deploy --config`.
  The toml itself is never rewritten. Nothing real lands in git.
- **Token values are env-only.** `CLOUDFLARE_DRAMA_STUDIO_API_TOKEN` is the
  **deploy token**: it is forwarded to `CLOUDFLARE_API_TOKEN` per command and
  covers account/zone resolution, the zone guard, R2, the secrets and the Worker
  deploy. `STUDIO_KV_DNS_API_TOKEN` is a **second, optional** token covering the
  KV-namespace and the DNS steps; unset or empty it falls back to the deploy
  token. No token value is committed or printed — only variable **names** and
  HTTP status codes.
- **Secret values are env-only.** The manifest lists the secret **names** and
  marks each required or optional. **Required** — the service README bindings
  `DS_ENROLLMENT_SECRET`, `DS_ADMIN_KEY`, `R2_ACCOUNT_ID` — must be set in the
  environment or the deploy fails closed. **Optional** — `R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY` — are skipped with a warning when absent. Values are
  read from the environment and piped to `wrangler secret put` stdin; they are
  never echoed.
  - **R2 S3 keys deferred until presign ships; needs a token with "API Tokens
    Write".** The service does not read `R2_ACCESS_KEY_ID` /
    `R2_SECRET_ACCESS_KEY` at runtime (presign is future), so the deploy plans
    and succeeds without them.
- **No real zone or account id is committed.** The guard's intended-account pin
  is supplied by the operator at deploy time (ids are public; secrets are not).

> **Token scope — the step-to-token table.** One token that can do everything is
> not required, and the deploy must not discover a missing scope *after* it has
> already written to R2.
>
> | Step | Token variable | Scope it needs |
> |---|---|---|
> | account + zone resolution, zone guard | `CLOUDFLARE_DRAMA_STUDIO_API_TOKEN` | Workers + zone read |
> | R2 bucket, R2 45-day lifecycle | `CLOUDFLARE_DRAMA_STUDIO_API_TOKEN` | R2 buckets read/write |
> | secrets, Worker deploy (`wrangler`) | `CLOUDFLARE_DRAMA_STUDIO_API_TOKEN` | Workers scripts + secrets write |
> | KV namespace (list + create) | `STUDIO_KV_DNS_API_TOKEN`, else the deploy token | KV namespaces read/write |
> | DNS record (list + create) | `STUDIO_KV_DNS_API_TOKEN`, else the deploy token | zone DNS records read/write |
>
> Measured read-only on 2026-10-12 (HTTP codes only, never a value): the
> operator's Workers/R2 token answers 200 for Workers scripts, Worker secrets,
> R2 buckets **and** the R2 lifecycle GET, but 401 for KV namespaces and 403 for
> zone DNS records; the operator's KV/DNS token answers 200 for KV namespaces
> and zone DNS records but 403 for R2. That split is why the two variables
> exist.

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

Live (tokens needed — **not part of this unit**):

```sh
export CLOUDFLARE_DRAMA_STUDIO_API_TOKEN="..."   # deploy token, from env only
export STUDIO_KV_DNS_API_TOKEN="..."             # OPTIONAL KV/DNS token, from env only
export STUDIO_INTENDED_ACCOUNT_ID="<blackceo account id>"   # guard pin
./deploy.sh --dry-run deploy                     # runs the read-only preflight
./deploy.sh deploy                               # the real deploy
```

Optional env override: `STUDIO_KV_DNS_API_TOKEN` — when the manifest's
`env.kv_dns_token_var` names a different variable, that name is used instead; the
value is always read from the environment.

Optional env overrides (used to prove the guard):

- `STUDIO_ZONE_NAME` — target zone name (a different name is refused).
- `STUDIO_ZONE_ID` / `STUDIO_ACCOUNT_ID` — pin the target ids.
- `STUDIO_INTENDED_ACCOUNT_ID` — pin the intended BlackCEO account id.
- `STUDIO_FOREIGN_ZONE_ID` — the foreign zone id the landmine refuses.

---

## 4. Per-step token + read-only scope preflight

Before the first write, `deploy.sh` probes **every step's scope with that step's
assigned token** — `GET` only, never a mutation:

| Probe | Token |
|---|---|
| Workers scripts list | deploy token |
| Worker secrets list (only when the Worker already exists) | deploy token |
| R2 buckets list | deploy token |
| R2 lifecycle `GET` (only when the bucket already exists) | deploy token |
| KV namespaces list | KV/DNS token, else the deploy token |
| zone DNS records list | KV/DNS token, else the deploy token |

Any non-200 **fails the deploy before any mutation**, with **one** line naming
the step and the variable, for example:

```
FATAL preflight: kv-namespace needs a token with KV namespaces read/write; STUDIO_KV_DNS_API_TOKEN (falling back to CLOUDFLARE_DRAMA_STUDIO_API_TOKEN) got HTTP 401
```

That is the live defect this protects against: a token without KV scope used to
surface only *after* the bucket and the lifecycle rule had already been written.
No token value is ever printed — a variable **name** and an HTTP code are.

`--dry-run` with a deploy token set runs the same read-only preflight and prints
its result; `--dry-run` with no token plans it (`PLAN` per probe, no call at all).

Operator recipe:

1. Deploy token (`CLOUDFLARE_DRAMA_STUDIO_API_TOKEN`) from the operator's
   **Workers/R2** token.
2. KV/DNS token (`STUDIO_KV_DNS_API_TOKEN`) from the operator's **KV/DNS** token.
3. `./deploy.sh --dry-run deploy` — the preflight tells you immediately whether
   either token is short a scope.
4. Then the real, Trevor-authorized `./deploy.sh deploy`.

Neither token is created, rotated or modified by this repository, and no value is
ever written to a file.

---

## 5. Deploy flow (`deploy`)

1. **File preflight** — manifest + `deploy.sh` present, `npx` available; the U2
   service config is reported honestly (required only for a live deploy).
2. **Resolve** — zone id + account id. The account is resolved **independently**
   of the zone: a supplied `STUDIO_ZONE_ID` never skips account resolution, so
   the live G4 guard always has a real account id.
3. **Zone guard** — the hard gate (section 2).
4. **Scope preflight** — the read-only probe (section 4). Runs before any write.
5. **R2 bucket** — create `zhw-drama-studio` if missing (idempotent).
6. **Retention** — 45-day lifecycle rule on the `projects/` prefix (scoped
   project-object retention).
7. **KV namespace** — find `DS_STUDIO` by title; create it only if absent. Its id
   is resolved into the throwaway config, so no `<PLACEHOLDER_KV_*>` id reaches
   `wrangler`. Runs on the KV/DNS token.
8. **Secrets** — `wrangler secret put` the required names (`DS_ENROLLMENT_SECRET`,
   `DS_ADMIN_KEY`, `R2_ACCOUNT_ID`), values from env; optional `R2_*` S3 keys are
   skipped when absent.
9. **Worker deploy** — `wrangler deploy` with the throwaway temp config. Because
   that config is written into `$TMPDIR`, `main` is rewritten to the **absolute**
   path of `mini-app/service/src/index.js`, so the entrypoint always resolves.
10. **DNS** — ensure a **proxied** CNAME `studio.zerohumanworkforce.com ->
    zerohumanworkforce.com` exists in the guarded zone, created only if absent.
    Runs on the KV/DNS token and refuses any zone but the guarded BlackCEO zone.

The real deploy is the plan's separate "Deploy" row: *one bucket, one KV
namespace, two secrets, scoped project-object 45-day retention; `deploy.sh
--dry-run` then real deploy.*

---

## 6. Honesty contract

- `--dry-run` prints `PLAN` for every step, makes **zero** wrangler calls and
  performs **zero** mutations. With a deploy token in the environment it also runs
  the read-only scope preflight (`GET` only) and prints its result; with no token
  it plans the preflight. A probe answering non-200 fails the run — in
  `--dry-run` too — naming the step and the variable. It reports unresolved ids as
  `<unresolved>` and never claims a zone-guard PASS it could not prove.
- Every live step prints `STEP`; the final line says `DONE deploy` only after the
  real commands succeeded (or `DRY-RUN COMPLETE` with a no-mutation reminder).
- Secrets are never echoed. Zone/account ids are not secrets and are printed so
  an operator can audit which zone was resolved.
