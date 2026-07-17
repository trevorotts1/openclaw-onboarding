# Podbean Broker (n8n) — the Podbean credential broker for the podcast engine

`podbean-broker.workflow.json` is the n8n workflow that acts as the Podbean
**credential broker** for the Podcast Production Engine (Skill 58). BlackCEO HOSTS
every client's show under his ONE Podbean account, so the Podbean OAuth app
`client_id`/`client_secret` are BlackCEO's **single shared app** — never the
client's, never asked from the client. Those app credentials live **only** inside
n8n (as the `httpBasicAuth` credential on the `Podbean Token` node) and never
leave it. A client box holds only the broker webhook URL, a low-privilege shared
token, and the client's **Podbean Channel ID** (`podcast_id`). The broker mints a
Podbean access token **scoped to that Channel ID** and returns it; the box then
does its own upload + create-episode so it still captures the permalink
synchronously (Step 15/16). A compromised client box cannot leak the Podbean app
credentials because they were never there.

## Why this exists (and why not the other Podbean workflows)

Trevor's n8n already has a live Podbean workflow, **"create podcast episode from
openclaw"** (`POST /webhook/podbean-publish`), which injects his creds server-side
and publishes an episode from `podcast_id` + media URLs. That one is
**fire-and-forget**: it returns `200` immediately and emails the result — it does
**not** return the episode permalink synchronously. The Skill 58 engine needs the
permalink back at Step 15 to (a) write it to the GHL episode-URL field (which
field-triggers the downstream "podcast is completed" workflow at Step 16) and
(b) store it in the idempotency ledger. So Skill 58 uses a **token broker** (mint
a Channel-scoped token; the box keeps the synchronous publish), not the
full-publish proxy.

This asset also closes two gaps that used to exist on the live full-publish
workflow (see "Live full-publish workflow — sanitized export" below, which
records that those same two gaps are now independently closed on the live
workflow itself): it **requires a shared-token auth gate**, and it keeps the
app credentials in n8n's **credential vault** instead of plaintext in the
workflow JSON.

## Live full-publish workflow — sanitized export (read-only reference)

`podbean-publish.workflow.json` is a **sanitized, read-only reference export**
of the live full-publish workflow **"create podcast episode from openclaw"**
(id `TkL0rn2SH3q32SeB`, `POST /webhook/podbean-publish`). Unlike the broker
asset above, this workflow already exists and runs live on the instance; the
file in this repo is not something to import, it is a durable structural
record of what production runs, captured for audit and onboarding.

Captured state (live API re-read, published version pointer):
`activeVersionId` / `versionId` `e13b18be-2b37-49a8-b935-39a0520625bd`,
`updatedAt` `2026-07-16T14:29:30Z`, 51 nodes, 35 connections, `active: true`.

Sanitization applied before commit (spec `SKILL 58 PODBEAN SERVER-SIDE
PUBLISH — MASTER SPEC v1`, unit U12):

- `pinData` removed entirely. The live workflow's pinned example execution
  carried a real client's name, email, and Podbean channel id; none of that
  reaches this file.
- Every Gmail node's HTML message body (which is built from live-execution
  expressions only, never a literal) is replaced with a one-line placeholder
  comment in this export; the `sendTo` fields are kept because they are
  either an expression (`={{ ...client_email }}`, success/failure paths) or
  the operator's own address (refusal paths — never a client's).
- Credentials appear only as `{id, name}` reference pairs, exactly as the n8n
  API returns them — the API never serves credential secret values over
  these endpoints, so there was no value to strip: `Podcast Publish Gate`
  (`httpHeaderAuth`, id `8HTB7khC7fDcRVhN`) on the webhook node, and `Podbean
  BlackCEO (client_credentials)` (`httpBasicAuth`, id `EZApXhsHExXctBrB`) on
  the OAuth node. Neither credential's value is anywhere in this repository.
- `staticData`, `meta`, `shared` (project/owner metadata), `versionCounter`,
  `triggerCount`, and `sourceWorkflowId` were dropped as export noise with no
  audit value.
- Verified clean with `bash scripts/qc-assert-no-n8n-plaintext-secrets.sh`
  (no plaintext `client_id`/`client_secret` literals — this workflow's
  Podbean app credential is vaulted, not literal) and
  `bash scripts/qc-assert-no-client-names.sh` (no client names, no operator
  home path).

The companion gate-test workflow `Podbean Gate Test (TEMP - delete at
cutover)` (id `aN6MrIJ4zLeKS047`) referenced by earlier revisions of this
README as the header-auth pattern source has been deleted from the live
instance (confirmed `NOT_FOUND` on a fresh `GET`) now that its pattern is
live on the production workflow above.

## Import (manual — required)

The n8n management API key on this fleet has historically failed to authenticate
for writes (`AUTHENTICATION_ERROR`), so this workflow ships **validated offline**
but is **not** created on the instance. Import it by hand:

1. n8n → **Workflows → Import from File** → select
   `58-podcast-production-engine/config/n8n/podbean-broker.workflow.json`.
2. The webhook path is `podbean-broker`, so the production URL is
   `https://main.blackceoautomations.com/webhook/podbean-broker` — this is the
   value a client box stores as `PODBEAN_BROKER_WEBHOOK_URL` (not a secret).
3. Leave the workflow **inactive** until steps 4–6 are done.

## One-time credential + env setup (inside n8n only)

4. **Create the Podbean app credential (one-time).** The `Podbean Token` node
   references an **HTTP Basic Auth** credential with a placeholder id, named
   *"BlackCEO Podbean App (connect me)"*. Create it with **User =** BlackCEO's
   Podbean OAuth app `client_id`, **Password =** the app `client_secret`, and
   select it on the node. This is the credential that never leaves n8n. (Podbean's
   token endpoints accept HTTP Basic; the node calls `oauth/multiplePodcastsToken`
   so the returned token is scoped to the requested Channel ID.)
5. Set one n8n **environment variable** (Settings → Variables/Env, or the
   container env): `PODBEAN_BROKER_TOKEN` — the low-privilege shared token. It must
   equal the value a client box holds as `PODBEAN_BROKER_TOKEN`.
6. **Activate** the workflow.

## Contract

`POST` JSON to the webhook. Auth header `X-Podbean-Broker-Token: <token>` (body
`token` is also accepted). Dispatch is on the body field `action`.

**Implemented — `mint_token`:**

```
{ "action": "mint_token", "podcast_id": "<the client's Podbean Channel ID>" }
```

Response (200):

```
{ "ok": true, "action": "mint_token", "via": "n8n_broker",
  "podcast_id": "...", "access_token": "...", "expires_in": 604800 }
```

Behaviour: validates the shared token (bad/absent → `401`), requires `podcast_id`
(absent → `400`), then mints a Podbean token scoped to that Channel ID via the
vault credential and returns it. Podbean returning no token for the Channel ID →
`502 { "error": "token_mint_failed" }`. Any other `action` → `501`.

## Skill side

`scripts/podbean_publish.sh` speaks this contract. It runs in **broker mode** when
`PODBEAN_BROKER_WEBHOOK_URL` and `PODBEAN_BROKER_TOKEN` both resolve on the box
(fleet default): it POSTs `mint_token` with the client's Channel ID, uses the
returned Channel-scoped token for `uploadAuthorize` / PUT / create-episode, and
captures the permalink — no Podbean app secret is present on the box. When the
broker pair is absent it falls back to a **local** `client_credentials` mint,
which requires `PODBEAN_CLIENT_ID` / `PODBEAN_CLIENT_SECRET` and is intended only
for the operator's OWN box. The Podbean Channel ID (`PODBEAN_PODCAST_ID`) is
required in both modes and is the only per-client Podbean value.

Provisioning (`install.sh`): set `OPENCLAW_PODBEAN_BROKER_URL` +
`OPENCLAW_PODBEAN_BROKER_TOKEN` in the operator env to inject the broker pair onto
client boxes (no Podbean secret lands on them). The legacy `OPENCLAW_PODBEAN_CLIENT_ID`
/ `OPENCLAW_PODBEAN_CLIENT_SECRET` injection is kept for the operator's own box /
backward compatibility only.

## Repository secret-vaulting guard and offline transformer

Run the repository-wide static guard before committing an n8n workflow export:

```bash
bash scripts/qc-assert-no-n8n-plaintext-secrets.sh
```

It discovers every `*.workflow.json` file and rejects literal `client_id` /
`client_secret` assignments without printing the rejected value. The shipped
broker passes because `Podbean Token` uses an `httpBasicAuth` credential
reference with a placeholder ID.

For a workflow exported to a local file, the offline transformer removes
supported Code/Set/HTTP Request literals without accepting or displaying a
credential value:

```bash
python3 58-podcast-production-engine/scripts/vault_n8n_credential.py \
  /path/to/offline-export.workflow.json \
  "Podbean BlackCEO (client_credentials)" \
  --output /path/to/offline-export.vaulted.workflow.json
```

Code and Set assignments become `$env.PODBEAN_CLIENT_ID` /
`$env.PODBEAN_CLIENT_SECRET` references and are listed in the redacted report.
HTTP Request assignments are removed and the node receives the same placeholder
credential-reference shape used by the repository's broker assets. After an
import, replace the placeholder ID by selecting the named n8n credential on the
node. Re-run the static guard against the transformed export before import.

### OWED — live application was not done by this pass

This repository-only pass made no n8n API calls and did not read, export, modify,
or activate either live-only workflow. The later live operator must apply and
verify the vaulting by these workflow ID references:

- `BqRLOn8TP1wPaAzn` — `Podbean - GET CLIENT CHANNEL ID`
- `COfgxe6HXRcWOleV` — `Podbean Channel IDs to Google Doc`

For each ID, export the workflow through the authorized operator path, run the
offline transformer on that export, connect the existing named credential (or
set the reported deployment env references where a Code/Set node cannot consume
a credential directly), import it through the authorized operator path, and
verify that a fresh export passes the repository guard. That live application
and verification remain explicitly owed.

## Operator: live full-publish workflow hardening — CLOSED

Earlier revisions of this README flagged two gaps on the live **"create
podcast episode from openclaw"** (`/webhook/podbean-publish`) workflow. A
live API re-read on 2026-07-16 (see "Live full-publish workflow — sanitized
export" above) shows both are now closed on the live workflow itself, out of
band from this repository:

1. **Auth gate — CLOSED.** The webhook node now carries
   `authentication: headerAuth` with the `Podcast Publish Gate` credential
   (id `8HTB7khC7fDcRVhN`), the same header-auth pattern this broker uses.
   An unauthenticated POST no longer reaches the workflow.
2. **Plaintext credentials — CLOSED, for this workflow.** The Podbean OAuth
   node authenticates via the vaulted `httpBasicAuth` credential `Podbean
   BlackCEO (client_credentials)` (id `EZApXhsHExXctBrB`); no `client_id` /
   `client_secret` literal exists in this workflow's JSON.

This closure covers only `TkL0rn2SH3q32SeB`. The separate, pre-existing,
operator-deferred plaintext-credential debt inside workflows
`BqRLOn8TP1wPaAzn` and `COfgxe6HXRcWOleV` (see "OWED — live application was
not done by this pass" above) is unaffected and remains open; per standing
doctrine, agents must never read, quote, or export either workflow's Code
node contents.
