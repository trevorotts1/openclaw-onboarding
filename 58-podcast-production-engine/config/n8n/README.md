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

This asset also closes two gaps that exist on the live full-publish workflow (see
"Operator: harden the live workflow" below): it **requires a shared-token auth
gate**, and it keeps the app credentials in n8n's **credential vault** instead of
plaintext in the workflow JSON.

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

## Operator: harden the live full-publish workflow (out of scope for the repo)

The live **"create podcast episode from openclaw"** (`/webhook/podbean-publish`)
has two gaps found during this build (fix in n8n, never in the repo):

1. **No auth gate** — anyone with the URL can POST and trigger a real publish to
   any `podcast_id`. Add a shared-token check like this broker's
   `X-Podbean-Broker-Token` / `$env.PODBEAN_BROKER_TOKEN` gate.
2. **Plaintext credentials** — the Podbean `client_id`/`client_secret` are literals
   in the workflow JSON (readable via the API). Move them into an n8n vault
   credential (as this broker does).
