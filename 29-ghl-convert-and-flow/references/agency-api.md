# agency-api.md — agency/company-scoped operations

> Scope: OAuth token management, sub-account provisioning, SaaS configuration/billing, agency users, companies, snapshots and marketplace billing. This file is the repo-managed source of truth for agency guidance; a box-local `GoHighLevel-Agency-API-Reference.md` is agent-authored and is not a repo source.

## Owner facts vs measured entitlements

Trevor owns the HighLevel agency and states he has **Agency Pro**. Record that as an owner-supplied account fact. It is not a measured entitlement of every staff user or client account. No customer plan or service is secretly activated because of this fact.

## Token and tenant

- Agency PIT/OAuth reaches `/locations/*` provisioning, `/saas/*`, agency `/users/*`, `/companies/*`, `/snapshots/*`, `/oauth/*`.
- Location PIT cannot perform agency operations.
- Agency PIT 401s on media; use a location PIT for media and course content.
- Do not cross token contexts to make a failing call pass.

## Operations (check the registry row for the exact literal)

| Operation | Call | Version | Scope |
|---|---|---|---|
| Get/refresh token | `POST /oauth/token` | row (`2021-07-28`; v3 camelCase body) | OAuth app |
| Mint location token | `POST /oauth/locationToken` (v2) / `location-token` (v3) | matching literal | `oauth.write` |
| List installed locations | `GET /oauth/installedLocations` (works both) / `installed-locations` (v3 only) | matching literal | `oauth.readonly` |
| Locations search/get/update | `GET /locations/...`, `PUT /locations/{id}` | `2021-07-28` | `locations.readonly|write` |
| Create location | internal `POST backend.leadconnectorhq.com/locations/` with `token-id` | `2021-07-28` | Firebase; not a PIT |
| Add user | `POST /users/` (agency PIT) | registry row (`2021-07-28` on the current row; `2023-02-21` is also documented historically) | `users.write` |
| SaaS configurator/billing | `/saas/*`, `/saas-api/*` | `2023-02-21` (deliberate forward move: `v3`) | `saas/*` |
| Companies | `GET /companies/{companyId}` | `2021-07-28` | `companies.readonly` |
| Snapshots | `GET /snapshots/`, status, share link | `2021-07-28` | `snapshots.readonly` |
| Marketplace billing | `/marketplace/billing/charges*` | `2021-07-28` | `charges.*` |

**Create location is the one operation with no public equivalent.** It uses the internal Firebase id-token (`token-id: <id-token>`), never `Authorization: Bearer`. The official public API cannot create a location. The OAuth marketplace-app route is a dead end (`error.noAppVersionIdFound`); do not use it for provisioning.

**`companyId` is the agency Firestore document id**, not the UI `relationNumber`.

## Agency Pro gating

Sub-account creation and the SaaS configurator require Agency Pro. Under a lower plan they return 403 regardless of scopes. That is an account fact, not a code bug.

## SaaS split

The live SaaS docs publish parallel `-deprecated` and current forms for several endpoints. Check which URL maps to which. Unpause: `POST /saas/pause/{locationId}` accepts `"paused": false`; this is a reasoned candidate, not a proven operation — verify before relying on it.

## Rate limits

Per app per resource: 100 requests / 10 seconds and 200,000 / day. Headers observed: `X-RateLimit-Limit-Daily`, `X-RateLimit-Daily-Remaining`, `X-RateLimit-Interval-Milliseconds`, `X-RateLimit-Max`, `X-RateLimit-Remaining`, `X-RateLimit-Daily-Reset`. All tiers share one bucket; switching transport does not buy quota.

## MCP at agency level

The client-specific hosted MCP endpoints exist and an agency-scoped connection can enumerate locations. `list_locations` is the operation; agency MCP does not make a beta-gated public operation production-ready.

## Known limitations

- A workflow definition write remains beta/staging; the internal Firebase path is the proven fallback.
- Opportunities pipeline writes are registry rows; delete is an irreversible cascade.
- The public API cannot create a location.
- Do not promise SaaS, snapshot or marketplace behavior that the tenant's plan/scope has not proven.
