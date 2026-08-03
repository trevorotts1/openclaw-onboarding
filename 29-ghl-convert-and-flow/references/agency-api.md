# agency-api.md — Agency-level (company-scoped) GoHighLevel API Reference

> **Scope of this file:** operations that act at the AGENCY/company level rather than inside
> a single sub-account — OAuth token management, sub-account provisioning, the SaaS
> configurator and billing, agency users, companies, and snapshots.
>
> **This file is the repo-managed source of truth for agency-level API guidance.** A file
> named `GoHighLevel-Agency-API-Reference.md` may exist on a box under
> `~/Downloads/openclaw-master-files/apis/`. That copy is **agent-authored TYP content with
> no repo source** — it is not published by `update-skills.sh` and it carries three known
> errors this file corrects (SaaS Version, the MCP section, and no v3 awareness). **Where
> the two disagree, this file wins.**
>
> **Verified against** `https://github.com/GoHighLevel/highlevel-api-docs` (`apps/oauth.json`,
> `saas-api.json`, `users.json`, `locations.json`, `companies.json`, `snapshots.json`,
> `marketplace.json`, and the `apps/v3/` equivalents), plus live read-only GET probes against
> operator-owned accounts, all on **2026-08-03**.

---

## 1. Global rules

**Base URL:** `https://services.leadconnectorhq.com` — same host for both generations.

### Version header — CORRECTED

| Surface | Correct `Version` |
|---|---|
| locations, oauth, users, companies, snapshots, marketplace | `2021-07-28` |
| **SaaS (all `/saas/*` and `/saas-api/*`)** | **`2021-04-15`** |
| any v3 path form | `v3` |

> **Correction.** Older agency documentation stated *"Every SaaS endpoint uses: 2023-02-21"*
> and repeated `Version: 2023-02-21` across all thirteen SaaS examples. **`saas-api.json`
> publishes exactly one enum for all 22 SaaS operations: `2021-04-15`.** `2023-02-21` appears
> nowhere in that spec.
>
> **PROVEN 2026-08-03:** `GET /saas-api/public-api/agency-plans/{companyId}` returns **200
> under `Version: 2023-02-21`** against a live agency token. So existing `2023-02-21` SaaS
> code is **not broken** and does not need an emergency change — HighLevel accepts all four
> published version strings on established paths. Use `2021-04-15` for new work because it
> is the documented value and the only one guaranteed to route for every SaaS path.

Omitting the header is a **401** (`"version header was not found."`); an unpublished value
is a **401** (`"version header is invalid"`). Both PROVEN live.

Full generation rules and the per-surface table: **`references/api-generations.md`**.

### Agency token vs location token
- An **agency (company-scoped) PIT or OAuth token** reaches `/locations/*` provisioning,
  `/saas/*`, `/users/*` at agency level, `/companies/*`, `/snapshots/*` and `/oauth/*`.
- A **location-scoped PIT** cannot perform agency operations, and an agency PIT **401s on
  media uploads**. Mint the right one for the job.
- Some agency calls need a **location token minted from the agency token** — see §2.2.

### Plan requirements
Sub-account creation and the SaaS configurator require the agency to be on **Agency Pro**.
Under a lower plan these endpoints return 403 regardless of scopes.

### Rate limits
100 requests / 10 seconds burst and 200,000 / day, **per app per resource** (location or
company). Response headers (all six confirmed live 2026-08-03):
`X-RateLimit-Limit-Daily`, `X-RateLimit-Daily-Remaining`, `X-RateLimit-Interval-Milliseconds`,
`X-RateLimit-Max`, `X-RateLimit-Remaining`, **`X-RateLimit-Daily-Reset`**.

> `X-RateLimit-Daily-Reset` is **not** in HighLevel's published header list but **is** sent
> on live responses — confirmed by direct observation 2026-08-03. Skills 36 and 44 rely on
> it; that reliance is sound.

**All tiers share one bucket.** Switching from MCP to REST does not buy more quota.

---

## 2. Authentication and token management

### 2.1 Get / refresh an access token
```
POST /oauth/token          Version: 2021-07-28
```
Form-encoded: `client_id`, `client_secret`, `grant_type`, `code` (or `refresh_token`),
`user_type`, `redirect_uri`. Response carries `access_token` (24h) and `refresh_token`
(1 year, rotates on use — persist the new one every time).

> **v3 changes the body to camelCase**: `clientId`, `clientSecret`, `grantType`,
> `refreshToken`; the response field becomes `accessToken`, and the `Version` header becomes
> **required** on this call.

### 2.2 Mint a location token from an agency token — **PATH RENAMED IN v3**

| Generation | Path | `Version` |
|---|---|---|
| v2 | `POST /oauth/locationToken` | `2021-07-28` |
| v3 | `POST /oauth/location-token` | `v3` |

```bash
curl --request POST 'https://services.leadconnectorhq.com/oauth/locationToken' \
  -H 'Authorization: Bearer <AGENCY_ACCESS_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'companyId=<COMPANY_ID>' \
  --data-urlencode 'locationId=<LOCATION_ID>'
```
HighLevel lists the old path as **removed without deprecation** in v3. The v2 form still
works today. **Never pair a hyphenated path with a v2 Version — that is a hard 404.**

### 2.3 List installed locations — **PATH RENAMED IN v3, and this one is PROVEN gated**

| Generation | Path | Behaviour (PROVEN 2026-08-03) |
|---|---|---|
| v2 | `GET /oauth/installedLocations` | resolves under **both** `2021-07-28` and `v3` |
| v3 | `GET /oauth/installed-locations` | **404 `Cannot GET` under `2021-07-28`**; resolves only under `v3` |

```bash
curl --request GET \
  'https://services.leadconnectorhq.com/oauth/installedLocations?companyId=<COMPANY_ID>&limit=20' \
  -H 'Authorization: Bearer <AGENCY_ACCESS_TOKEN>' \
  -H 'Version: 2021-07-28'
```
Scope: `oauth.readonly`. **Recommendation:** stay on the camelCase form — it is the only one
that works under every published version.

---

## 3. Sub-account (location) management — `Version: 2021-07-28`

| Operation | Call |
|---|---|
| Search / list | `GET /locations/search?companyId=&limit=&skip=` |
| Get one | `GET /locations/{locationId}` |
| Create | `POST /locations/` (accepts `snapshotId` — see §6) |
| Update | `PUT /locations/{locationId}` |
| Delete | `DELETE /locations/{locationId}?deleteTwilioAccount=` |

Scopes: `locations.readonly`, `locations.write`.

> **v3 adds** `GET /locations/{locationId}/conversationChannels/{type}` and
> `GET,PUT /locations/{locationId}/permissions` (32 ops vs 29). Require `Version: v3`.

---

## 4. SaaS configurator and billing — `Version: 2021-04-15`

All 22 operations. Requires Agency Pro.

| Operation | Call |
|---|---|
| Pause / unpause a sub-account | `POST /saas/pause/{locationId}` — body `{"paused": true\|false}` |
| Enable SaaS for one sub-account | `POST /saas/enable-saas/{locationId}` |
| Bulk enable | `POST /saas/bulk-enable-saas` |
| Disable SaaS | `POST /saas/bulk-disable-saas` |
| Update rebilling | `POST /saas/update-rebilling` |
| Agency plans | `GET /saas-api/public-api/agency-plans/{companyId}` |
| One SaaS plan | `GET /saas-api/public-api/saas-plan/{planId}` |
| Location subscription | `GET /saas-api/public-api/location-subscription/{locationId}` |
| Update subscription | `POST /saas-api/public-api/update-saas-subscription/{locationId}` |
| SaaS locations (paginated) | `GET /saas-api/public-api/locations?companyId=` |
| Locations by Stripe ID | `GET /saas-api/public-api/locations-by-stripe-id` |
| Wallet balance | `GET /saas-api/public-api/companies/{companyId}/locations/{locationId}/wallet-balance` |
| Complimentary credits | `POST .../wallet-balance/complimentary-credits` |

Scopes: `saas/location.read`, `saas/location.write`, `saas/company.write`.

> **Unpausing.** There is no separate resume endpoint. `POST /saas/pause/{locationId}` takes
> a `paused` boolean, so sending `"paused": false` is the obvious unpause. **This is
> untested** — it was not probed, because this audit made no write calls. Verify with one
> controlled call before relying on it. Do not document it as confirmed.

> **v3 (`saas-v3`, 25 ops)** adds `POST /saas/allow-attach-rebilling/{locationId}` and brings
> the two wallet-balance endpoints into the spec.

---

## 5. Agency users — `Version: 2021-07-28`

| Operation | Call |
|---|---|
| List | `GET /users/?locationId=` |
| Search | `GET /users/search` |
| Filter by email | `POST /users/search/filter-by-email` |
| Create | `POST /users/` |
| Get / update / delete | `GET,PUT,DELETE /users/{userId}` |

Scopes: `users.readonly`, `users.write`.

> **Correction.** Skill 44 previously taught `Version: 2023-02-21` for `POST /users/`.
> `users.json` declares **`2021-07-28`** for all seven user operations. Corrected in skill 44
> v1.3.15. (PROVEN 2026-08-03: `GET /users/` returns 200 under all four published versions,
> so the old value was not failing — it simply was not the documented one.)
>
> **v3 drops `GET /users/`** in favour of `GET /users/search`. PROVEN: `GET /users/` still
> returns 200 under `Version: v3` today; do not rely on that persisting.

---

## 6. Companies and snapshots — `Version: 2021-07-28`

**Companies:** `GET /companies/{companyId}` — scope `companies.readonly`.

**Snapshots** (4 ops, scope `snapshots.readonly`) — the missing half of the provisioning
flow. Sub-account create accepts a `snapshotId`, and these are how you find one and confirm
it loaded:

| Operation | Call |
|---|---|
| List snapshots | `GET /snapshots/?companyId=` |
| Share link | `POST /snapshots/share/link` |
| Load status | `GET /snapshots/snapshot-status/{snapshotId}` |
| Load status for one location | `GET /snapshots/snapshot-status/{snapshotId}/location/{locationId}` |

**Marketplace billing** (scopes `charges.readonly|write`):
`GET,POST /marketplace/billing/charges`, `GET /marketplace/billing/charges/has-funds`,
`DELETE,GET /marketplace/billing/charges/{chargeId}`,
`DELETE,GET /marketplace/app/{appId}/installations`,
`GET /marketplace/app/{appId}/rebilling-config/location/{locationId}`.

---

## 7. Known limitations — do not assume otherwise

- **Workflows are read-only.** `GET /workflows/` is the ONLY workflow operation in **both**
  the v2 and v3 specs. There is no public create/edit endpoint. Workflow builds go through
  the internal Firebase-token path documented in skill 44 — that architecture remains
  necessary and correct.
- **The public API cannot create a location** in the way skill 44 needs; create-location uses
  the internal `backend.leadconnectorhq.com` path with a Firebase ID token, not a Bearer PIT.
- **Opportunities pipeline writes** are announced but absent from both published specs.
  `GET /opportunities/pipelines/{pipelineId}` is **PROVEN live** despite being undocumented;
  the write operations were not probed. See `references/opportunities.md`.
- **Agency PITs 401 on media uploads** — use a location PIT (`references/medias.md`).

---

## 8. MCP at the agency level — CORRECTED

> **Correction.** Older agency documentation stated that the official MCP *"has no
> agency-level tools"* and that a unified orchestrator with OAuth was *"a roadmap to grow it
> toward 250 or more tools ... but no agency tools exist today."* **That roadmap shipped.**

HighLevel now publishes two official MCP endpoints:

| | `/mcp/{client}/v2` — **recommended** | `/mcp/` — the original endpoint |
|---|---|---|
| URL | `https://services.leadconnectorhq.com/mcp/anthropic/v2` (Claude, live today) | `https://services.leadconnectorhq.com/mcp/` |
| Coverage | the full operation catalog — hundreds of operations across **40 domains** | a focused set of core tools, narrower scope |
| Shape | **6 unified meta-tools** | one tool per operation |
| Auth | OAuth (recommended) or PIT | OAuth or PIT |
| **Agency** | **connect once, work across many sub-accounts**; `list_locations` enumerates them | one sub-account per connection |

The 6 meta-tools: `search`, `fetch`, `search_operations`, `describe_operation`,
`execute_operation`, `list_locations`.

**So agency-level MCP tooling now exists** — `list_locations` plus agency-wide connections.
For agency work, prefer `/mcp/anthropic/v2`.

Accuracy notes: HighLevel does **not** label `/mcp/` "legacy" — its wording is "the original
endpoint", and it remains supported for any non-Claude MCP client. HighLevel publishes **no
fixed tool count** for it, so do not cite one. The dual-`Accept` requirement
(`application/json, text/event-stream`) is documented for the original endpoint only.

Full guidance: skill 36 (`36-ghl-mcp-setup/SKILL.md` → "Which official MCP endpoint").
Source: `https://marketplace.gohighlevel.com/docs/other/mcp` (verified 2026-08-03).

---

## 9. Sources

- OpenAPI specs (v2): `https://github.com/GoHighLevel/highlevel-api-docs/tree/main/apps`
- OpenAPI specs (v3): `https://github.com/GoHighLevel/highlevel-api-docs/tree/main/apps/v3`
- OAuth flow, rate limits, token lifetimes:
  `https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/docs/oauth/Authorization.md`
- Scopes: `https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/docs/oauth/Scopes.md`
- MCP: `https://marketplace.gohighlevel.com/docs/other/mcp`
- Changelog: `https://marketplace.gohighlevel.com/docs/Changelog/`
- Live read-only GET probes against operator-owned accounts, 2026-08-03 (no write calls made).
