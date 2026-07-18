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
and publishes an episode from `podcast_id` + media URLs. That one now responds
**synchronously**, in the same request/response cycle — it is no longer
fire-and-forget. Proven live on 2026-07-17: a refusal request to the endpoint
completed in 0.947615 seconds total and returned a fully structured JSON error
body in that same response, and a successful live publish that same night
returned its result in the publish call's own response, shaped
`{"status":"published","permalink_url":"https://automationhackswithblackceo.podbean.com/e/...","episode_id":"DK23M1B13D56","episode_number":5}`
— the working public link comes back synchronously, in the publish call itself,
not in a follow-up email (a second, independent publish that night returned the
same shape). The Skill 58 engine needs the permalink back at Step 15 to (a)
write it to the GHL episode-URL field (which field-triggers the downstream
"podcast is completed" workflow at Step 16) and (b) store it in the idempotency
ledger. So Skill 58 uses a **token broker** (mint a Channel-scoped token; the
box keeps the synchronous publish), not the full-publish proxy.

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

## Canonical publish path (GK-D4/D19 — Trevor-ratified 2026-07-16)

There are two live n8n workflows that can each call the real Podbean publish API
against BlackCEO's shared Podbean account:

- **`TkL0rn2SH3q32SeB`** — **"create podcast episode from openclaw"**
  (`POST /webhook/podbean-publish`), described above. **This is the single
  canonical publish path.** As of tag `v20.0.43` (GK-05/U67) its live graph
  carries an idempotency ledger (lookup → in-flight → completed/failed/refused,
  with an idempotent-replay short-circuit before any Podbean call), a
  standing-gate identity check (roster lookup by email, refuses and notifies
  before any publish work begins), and a media preflight (`HEAD` on both the
  audio and image URLs, refuses before the OAuth/upload/publish chain runs).
  This is the ONLY path the Skill 58 engine's Step 15 (and this repo's
  `podbean_publish.sh` broker-mode client, above) is ever wired to call.
- **`COfgxe6HXRcWOleV`** — **"Podbean Channel IDs to Google Doc."** This
  workflow's stated purpose (per its name and the Google-Doc/Google-Sheets
  export nodes in its graph) is unrelated to episode publishing, but it also
  contains its **own independent, ungoverned Podbean publish chain** — OAuth,
  audio/image upload, `Publish Episode` — behind an entry-point node that is an
  `executeWorkflowTrigger`, meaning any other n8n workflow's "Execute Workflow"
  node, or a manual trigger click in the n8n UI, can fire a real publish through
  it at any time, with none of the three governance layers above. That is a
  live double-publish risk on a real client's public podcast feed, not a
  theoretical one — it is a second real path to the same account. **It is
  deactivated (`active: false`) as of 2026-07-16, and permanently so by
  ruling — never deleted.** Deactivation is reversible; deletion is not, and
  reversibility is the point of deactivating instead. **Deactivation alone
  does not make this workflow "retired" in every sense — see "Deactivation
  semantics and the live caller" immediately below before treating this
  vector as closed.**

### Deactivation semantics and the live caller (repo-half correction, 2026-07-16)

**This section corrects the earlier "it is retired" framing above.** The prior
pass documented the double-publish vector correctly, in its own words — any
Execute-Workflow node or a manual UI trigger can fire `COfgxe6HXRcWOleV`'s own
ungoverned Podbean publish chain — and then concluded "it is retired" without
reconciling that vector against what `active: false` actually blocks. The
semantics are now settled, proved from this instance's own n8n 2.29.10 source
plus a live read (stated here, not re-litigated):

- **Production-mode Execute-Workflow calls load the PUBLISHED version and
  throw `"Workflow is not active and cannot be executed."`** when no
  published version exists. Evidence: `packages/cli/src/workflow-execute-additional-data.ts`
  (line 297, and lines 190–231 for the load path), `packages/cli/src/executions/execution.utils.ts`,
  `ExecuteWorkflow.node.ts` (passes the parent's own execution mode through to
  the call), and migration `1763048000000-ActivateExecuteWorkflowTriggerWorkflows`.
- **Manual and chat-triggered executions load the DRAFT**, regardless of the
  `active` flag.

**Therefore three things are true at once, not one:**

1. **The retired pipeline is blocked for production.** With `active: false`,
   `COfgxe6HXRcWOleV` has no published version, so a *production-mode*
   Execute-Workflow call into it now throws instead of silently publishing —
   a real, if incidental, mitigation of the production vector.
2. **The active caller's podcast branch is now a production-error landmine,
   not a silent double-publisher.** `yXKQg61bbA0ufJ1L` ("Social media in a box
   part 4 — Image generator & Social media poster"), `active: true`, carries a
   node named **"Trigger podcast creator workflow 8"** whose `workflowId`
   targets `COfgxe6HXRcWOleV` directly, and is itself invoked by
   `w6w48NI48EkcdPg2` ("Social media in a box part 3 — Content Writer"), also
   active. If that chain's podcast branch is reached in production mode, it
   now **fails with the throw above** rather than publishing a second episode
   — a production error, not a leak, but still an unhandled break in a live
   workflow this pass never touched, tested, or disclosed to that workflow's
   owner. **This node's disposition — sever it, or re-govern the sub-workflow
   and re-activate it — is live work, gated on the operator's decision (goal
   §5 Q1) and tracked as `K6-U74-r2`. It is explicitly out of scope for this
   repo-only pass and was NOT changed here.**
3. **The manual-mode ungoverned-publish hole is still open.**
   `COfgxe6HXRcWOleV`'s draft was never deleted — all 57 nodes and its full,
   ungoverned OAuth → upload → `Publish Episode` chain are intact. A human
   clicking "Execute workflow" in the n8n UI, or any chat-triggered execution,
   loads that draft and can still fire a real publish to BlackCEO's Podbean
   account with none of the canonical path's governance. `active: false` does
   not touch this path at all.

**Net effect on BINARY acceptance clause 2** ("the non-canonical one is
retired or re-scoped with its relationship written down"): the relationship
is now written down precisely; "retired" is accurate for the *production*
vector only, and was inaccurate as the blanket claim made above before this
correction. Full closure of clause 2 requires disposing of the caller node
and/or the manual-mode reachability — that is `K6-U74-r2`, blocked on the
operator (goal §5 Q1), not this pass.

**Why keep it instead of deleting it.** Preserving a deactivated workflow costs
nothing and keeps its node graph available for reference or future audit; deleting
it would foreclose that option irreversibly for no operational gain. **Why it lost
and the other won:** `COfgxe6HXRcWOleV` had gone dormant (no code change since
2026-04-13, last execution 2026-07-05, and its complete execution history — 4 runs
total — was 2 successes and 2 errors) with a structurally reachable
`executeWorkflowTrigger` entry point and zero governance on its publish chain,
while `TkL0rn2SH3q32SeB` is the actively maintained, gated, furnace-governed path
the engine already depends on, hardened the same week this ruling was made.

**The decision record.** This ruling resolves the decision named **GK-D4** ("which
podcast pipeline is canonical," per U74's own spec) and **D19** (U74/GK-12's
ledger-row decision number, "Canonicalize the podcast pipeline... kill the
double-publish risk") — two labels for the same question, per master spec line
371's own decision crosswalk table, which equates them outright. Trevor's
ratification, the live evidence behind it, and the full reasoning are recorded
**in this repo, on this branch,** in
`ledgers/ratified-decisions-2026-07-16-GK-D4-D19.md` — a verbatim excerpt of
the ratification, kept alongside this README so the pointer cannot dangle if
this branch merges on its own. That excerpt is sourced from commit `41d2d1f9`
on branch `chore/ratified-decisions-2026-07-16-d12-d4` (cited there for
provenance/audit); that branch also carries six unrelated decision records
(D12, D15 ×3, D20/U65 closure) not reproduced here, and lands separately via
the repo's serial merge-writer. If that fuller ledger lands first, the two
files will overlap on this section's content (not conflict on meaning) and
the merge-writer can fold this excerpt away at that point.
**Someone reading this file in six months:** if you are wondering why two
Podbean-publishing workflows exist on this n8n instance, that excerpt is the
full "why." The answer to "which one fires" is more precise than "only one,
permanently": in **production mode**, only `TkL0rn2SH3q32SeB` can complete a
publish — `COfgxe6HXRcWOleV` now throws instead. In **manual/chat mode**,
`COfgxe6HXRcWOleV`'s draft is still fully reachable and still ungoverned; see
"Deactivation semantics and the live caller" above for what remains open and
why that gap is tracked as `K6-U74-r2`, not closed by this ruling.

**Unchanged by this ruling.** Per the separate, already-closed `D-U65` ruling in
the same ledger, the Podbean OAuth plaintext credentials inside both
`BqRLOn8TP1wPaAzn` and `COfgxe6HXRcWOleV` remain **NEVER-PRINT, NEVER-VAULT,
NEVER-ROTATE** — permanent and closed, and untouched by this pass. This ruling
is only about which workflow can fire **in production**, never about the
credential inside either one — and, per the correction above, it does not by
itself resolve manual/chat-mode reachability either.

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

**Status update, 2026-07-16 — both dispositions have since been superseded by
explicit operator ruling, recorded in
`ledgers/ratified-decisions-2026-07-16-GK-D4-D19.md` (this branch; see "The
decision record" above for why it lives here instead of the ledger branch),
and the "owed" vaulting above is not being carried forward for either ID:**

- `BqRLOn8TP1wPaAzn` — per ruling **`D-U65`**, this plaintext credential is
  **closed / won't-do, permanently.** Trevor decided it stays in plaintext; do
  not propose vaulting it, do not re-open this.
- `COfgxe6HXRcWOleV` — per ruling **`GK-D4` / `D19`** (see "Canonical publish
  path" and "Deactivation semantics and the live caller" above), this workflow
  is **deactivated** (`active: false`, 2026-07-16), which blocks
  production-mode reachability but **not** manual/chat-mode reachability — so
  vaulting is not moot on the grounds that "it no longer fires" (it still can,
  manually). Vaulting was nonetheless not attempted here, independent of that
  reachability question, because the plaintext credential inside it is
  covered by the same `D-U65` NEVER-VAULT, NEVER-PRINT, NEVER-ROTATE ruling
  above, which this pass did not touch, re-open, or reinterpret.

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
