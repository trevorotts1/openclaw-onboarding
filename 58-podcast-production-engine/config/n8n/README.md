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

## Status update (publish-proxy fix): a third, now-preferred transport exists

`podbean_publish.sh` (Step 15) as of the publish-proxy fix supports THREE
transports, tried in this precedence order: **publish-proxy** (new, fleet
default), then **broker** (this document's asset), then **local** (operator-box
fallback). Proxy mode POSTs a JSON payload (contract v2: identity, title,
description, `audio_url`/`image_url`, `idempotency_key`, ...) to
`https://main.blackceoautomations.com/webhook/podbean-publish` with an
`X-Podcast-Publish-Token` header and expects a **synchronous** response carrying
the permalink - resolving the exact gap the next paragraph describes. The repo
leg (the script's payload builder, response handling, retry/idempotency logic,
and `install.sh` provisioning of `PODBEAN_PUBLISH_WEBHOOK_URL` +
`PODBEAN_PUBLISH_TOKEN`) is built and covered by
`58-podcast-production-engine/scripts/tests/test_podbean_publish_proxy.py`.

**Not yet true on the live n8n side** (separate, n8n-only units, not done by this
pass): the live workflow `TkL0rn2SH3q32SeB` does not yet require the
`X-Podcast-Publish-Token` header, does not yet understand contract v2's fields,
does not yet run the good-standing/identity gate, and still responds
fire-and-forget (no synchronous permalink). Do **not** provision
`PODBEAN_PUBLISH_TOKEN` on a real client box and expect a real publish to
succeed until those n8n-side units land - until then, leave proxy-mode
provisioning off and every box keeps using broker/local exactly as before (the
precedence check requires BOTH `PODBEAN_PUBLISH_WEBHOOK_URL` and
`PODBEAN_PUBLISH_TOKEN` to be set, so an unprovisioned box is entirely
unaffected by this fix).

## Why the broker asset exists (and why not the live full-publish workflow, historically)

Trevor's n8n already has a live Podbean workflow, **"create podcast episode from
openclaw"** (`POST /webhook/podbean-publish`), which injects his creds server-side
and publishes an episode from `podcast_id` + media URLs. Historically that one was
**fire-and-forget**: it returns `200` immediately and emails the result - it did
**not** return the episode permalink synchronously. The Skill 58 engine needs the
permalink back at Step 15 to (a) write it to the GHL episode-URL field (which
field-triggers the downstream "podcast is completed" workflow at Step 16) and
(b) store it in the idempotency ledger. So Skill 58 used a **token broker** (mint
a Channel-scoped token; the box keeps the synchronous publish) instead of the
full-publish proxy. The publish-proxy fix above is what finally resolves this by
adding a synchronous response to the proxy path (once the matching n8n-side unit
lands) - until then, the broker (or local) transport is what actually runs on any
box that is not proxy-provisioned.

This asset also closes two gaps that exist on the live full-publish workflow (see
"Operator: finish the live full-publish workflow" below): it **requires a
shared-token auth gate**, and it keeps the app credentials in n8n's **credential
vault** instead of plaintext in the workflow JSON.

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

## Operator: finish the live full-publish workflow (n8n-only, out of scope for the repo)

The live **"create podcast episode from openclaw"** (`/webhook/podbean-publish`,
workflow `TkL0rn2SH3q32SeB`) needs the following before the repo's new
publish-proxy transport (above) can be provisioned on any real box. None of this
is a repo change; it is entirely n8n-side (workflow edits + n8n data tables +
live proof), tracked as separate units:

1. **No auth gate today** - anyone with the URL can POST and trigger a real
   publish to any `podcast_id`. Add an `httpHeaderAuth` credential
   (`X-Podcast-Publish-Token`) on the webhook node, mirroring this broker's
   `X-Podbean-Broker-Token` gate (the live workflow `aN6MrIJ4zLeKS047` already
   demonstrates this exact pattern).
2. **No contract v2 support today** - the guard node only reads the legacy
   seven fields; it does not require `contract_version`, `client_last_name`, or
   `idempotency_key`, and does not run a good-standing/identity gate.
3. **Fire-and-forget response today** - the webhook returns `200` immediately
   with no permalink; it needs a `Respond to Webhook` node wired after episode
   creation (and after each refusal path) so `podbean_publish.sh`'s proxy mode
   gets the synchronous JSON it already parses.
4. **Plaintext credentials on two SIBLING workflows** - `BqRLOn8TP1wPaAzn` and
   `COfgxe6HXRcWOleV` still carry the Podbean `client_id`/`client_secret` as
   literals (Trevor has ratified leaving these as-is; do not vault or print
   them). `TkL0rn2SH3q32SeB` itself already uses a vaulted `httpBasicAuth`
   credential for its own Podbean OAuth mint, so this item does not block
   provisioning proxy mode.

Full detail (payload contract, good-standing/identity gate design, data table
schema, and the numbered n8n-side units): see the master spec this fix
implements, section 1.4 and Section 5 Phase 1-2 (kept outside this repo per the
runtime-data rule; ask the operator for the current spec location).
