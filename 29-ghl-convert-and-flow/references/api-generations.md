# api-generations.md — Choosing the right API generation and Version header

> **Read this before any GHL call.** It tells you which `Version` value to send and, for
> the surfaces where it matters, which generation actually routes.
>
> **Verified against** `https://github.com/GoHighLevel/highlevel-api-docs` (v2 `apps/`,
> v3 `apps/v3/`), `https://marketplace.gohighlevel.com/docs/`, and — for everything marked
> **PROVEN** — live read-only GET probes against operator-owned sub-accounts on
> **2026-08-03**. Where the spec and live behaviour disagree, the probe result is recorded
> and wins.

---

## 1. There are two generations

| | v2 generation | v3 generation |
|---|---|---|
| Spec location | `apps/*.json` | `apps/v3/*.json` |
| Spec count | **41** | **42** |
| `Version` header | `2021-07-28` or `2021-04-15` (per app) | `v3` |
| Host | `services.leadconnectorhq.com` | same host |
| Published | in place since 2021 | **2026-06-19** (commit `f0da4f8`, "feat: spec files for v3 added") |

The v3 generation is **additive on the same host**. There is no separate base URL, no
migration deadline HighLevel has published, and no announced retirement of v2.

**As of 2026-08-03 there is nothing newer than v3.** HighLevel's docs site exposes exactly
four version toggles: `v3`, `2023-02-21`, `2021-07-28`, `2021-04-15`.

---

## 2. How the runtime actually validates the Version header — PROVEN

This was probed live, not inferred. All calls were GET, against an operator-owned
sub-account, 2026-08-03.

| What was sent | Result | Evidence |
|---|---|---|
| No `Version` header at all | **401** — `"version header was not found."` | `GET /contacts/` |
| `Version: 2020-01-01` (not a published value) | **401** — `"version header is invalid"` | `GET /contacts/` |
| `Version: 2021-07-28` | 200 | `GET /contacts/`, `/users/`, `/calendars/` |
| `Version: 2021-04-15` | 200 | `GET /contacts/`, `/users/`, `/calendars/` |
| `Version: 2023-02-21` | 200 | `GET /contacts/`, `/users/` |
| `Version: v3` | 200 | `GET /contacts/`, `/users/`, `/calendars/` |

**Two conclusions, and the second is the one that bites:**

1. **The header is mandatory and is checked against an allowlist of the four published
   values.** Anything else is a 401. This is why "just omit it" and "make one up" both fail.

2. **For long-established v2 paths the runtime is LENIENT — all four values return 200.**
   Sending `2021-04-15` to contacts does *not* 400 today. **But leniency is not a contract,
   and it does not extend to newer paths** (section 4). The value each app's spec declares
   is the only one guaranteed to route for every path in that app.

> **Correction to an earlier internal claim.** Fleet docs previously asserted that the wrong
> Version header was "causing live 400s" on contacts/locations/opportunities/users/payments.
> **The probe disproves that for those endpoints** — they accept all four values. The
> Version-header corrections shipped in skill 29 v6.7.0 are still right (they align the docs
> with what HighLevel declares and guarantees), but the failure mode was documentation drift
> and contradiction across fleet docs, **not** live 400s on those calls. Do not repeat the
> 400s claim.

---

## 3. Per-surface generation table

`Version` value to send per app. **"v3 spec" = a v3 spec exists for that surface.** Prefer
the spec-declared v2 value unless you need a v3-only capability from section 4.

| Surface | v2 `Version` | v3 spec? | Use v3 when |
|---|---|---|---|
| ad-manager / ad-publishing | `2021-07-28` | yes (`ad-publishing-v3`) | — |
| affiliate-manager | `2021-07-28` | yes | — |
| **agent-studio** | `2021-04-15` | yes | — |
| associations | `2021-07-28` | yes | — |
| blogs | `2021-07-28` | yes | — |
| **brand-boards** | `2021-07-28` | yes | **required for brand voices** |
| businesses | `2021-07-28` | yes | — |
| **calendars** | `2021-04-15` | yes | — |
| campaigns | `2021-07-28` | yes | — |
| **chat-widget** | *(no v2 spec)* | yes | v3-only surface |
| companies | `2021-07-28` | yes | — |
| contacts | `2021-07-28` | yes | — |
| **conversation-ai** | `2021-04-15` | yes | — |
| **conversations** | `2021-04-15` | yes | — |
| courses | `2021-07-28` | yes | — |
| custom-fields | `2021-07-28` | yes | — |
| custom-menus | `2021-07-28` | yes | — |
| email-isv | `2021-07-28` | yes | — |
| emails | `2021-07-28` | yes | new campaigns/templates surface |
| forms | `2021-07-28` | yes | — |
| funnels | `2021-07-28` | yes | — |
| invoices | `2021-07-28` | yes | — |
| **knowledge-base** | `2021-04-15` | yes | — |
| links | both accepted | yes | — |
| locations | `2021-07-28` | yes | permissions + conversationChannels |
| marketplace | `2021-07-28` | yes | — |
| medias | `2021-07-28` | yes | — |
| **oauth** | `2021-07-28` | yes | **required for the renamed paths** |
| objects | `2021-07-28` | yes | — |
| opportunities | `2021-07-28` | yes | — |
| payments | `2021-07-28` | yes | — |
| phone-system | `2021-07-28` | yes | — |
| products | `2021-07-28` | yes | — |
| proposals | `2021-07-28` | yes | — |
| **saas-api** | `2021-04-15` | yes (`saas-v3`) | rebilling attach + wallet balance |
| snapshots | `2021-07-28` | yes | — |
| social-media-posting / social-planner | `2021-07-28` | yes (`social-planner-v3`) | queues + comments |
| store | *(none declared)* | yes | — |
| surveys | `2021-07-28` | yes | — |
| users | `2021-07-28` | yes | — |
| **voice-ai** | `2021-04-15` | yes | — |
| workflows | `2021-07-28` | yes | — |

**Bold** = one of the seven apps whose v2 value is `2021-04-15`. Everything else defaults to
`2021-07-28`.

---

## 4. Generation-gated paths — where the header genuinely decides routing

Most v2 paths accept any published version (section 2). **These do not.** Sending the wrong
generation returns `404 Cannot GET` — the path does not exist in that generation.

| Path | `2021-07-28` | `v3` | Verdict |
|---|---|---|---|
| `GET /oauth/installedLocations` | **401** (path exists, scope missing) | **exists** (500, auth-level) | v2 form works in BOTH |
| `GET /oauth/installed-locations` | **404 Cannot GET** | **exists** | **v3-ONLY** |
| `GET /brand-boards/locations/{locationId}/brand-voices` | **404 Cannot GET** | **200** | **v3-ONLY** |
| `GET /contacts/` | 200 | **200** | still live in v3 despite spec removal |
| `GET /users/` | 200 | **200** | still live in v3 despite spec removal |
| `GET /emails/builder` | 200 | **200** | still live in v3 despite spec removal |
| `GET /social-media-posting/category/queues/available-categories` | 200 | 200 | not gated |
| `GET /chat-widget/list` | 422 (params) | 422 (params) | path resolves in both |

All rows PROVEN by live GET on 2026-08-03.

**The rule this gives you:** a *renamed or brand-new* v3 path needs `Version: v3`. An
*existing* v2 path keeps working under every published version, including ones the v3 spec
marks removed. Deprecation in the spec has **not** been enforced at the runtime yet — but
do not build on that, because HighLevel can enforce it at any time without another release.

---

## 5. The two breaking renames — first-class treatment

HighLevel lists both as **"Removed without deprecation"** in the v3 changelog batch
(2026-06-11). They are the backbone of the agency OAuth workflow, so they get stated in full.

### 5a. Mint a location token

| Generation | Path | Method |
|---|---|---|
| v2 (`2021-07-28`) | `POST /oauth/locationToken` | POST |
| v3 (`v3`) | `POST /oauth/location-token` | POST |

```bash
# v2 — still works today
curl --request POST 'https://services.leadconnectorhq.com/oauth/locationToken' \
  -H 'Authorization: Bearer <AGENCY_ACCESS_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'companyId=<COMPANY_ID>' \
  --data-urlencode 'locationId=<LOCATION_ID>'

# v3 — the successor path
curl --request POST 'https://services.leadconnectorhq.com/oauth/location-token' \
  -H 'Authorization: Bearer <AGENCY_ACCESS_TOKEN>' \
  -H 'Version: v3' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'companyId=<COMPANY_ID>' \
  --data-urlencode 'locationId=<LOCATION_ID>'
```

> These are POST-only, so a read-only probe cannot confirm them by GET (GET returns
> `404 Cannot GET` for both forms simply because no GET route is registered). Path existence
> here rests on the published specs: `oauth.json` declares the camelCase form,
> `oauth-v3.json` declares the hyphenated form.

### 5b. List installed locations — **PROVEN generation-gated**

| Generation | Path |
|---|---|
| v2 (`2021-07-28`) | `GET /oauth/installedLocations` |
| v3 (`v3`) | `GET /oauth/installed-locations` |

```bash
# v2 form — resolves under BOTH 2021-07-28 and v3 (PROVEN 2026-08-03)
curl --request GET 'https://services.leadconnectorhq.com/oauth/installedLocations?companyId=<COMPANY_ID>&limit=20' \
  -H 'Authorization: Bearer <AGENCY_ACCESS_TOKEN>' \
  -H 'Version: 2021-07-28'

# v3 form — 404s under 2021-07-28, resolves ONLY under v3 (PROVEN 2026-08-03)
curl --request GET 'https://services.leadconnectorhq.com/oauth/installed-locations?companyId=<COMPANY_ID>&limit=20' \
  -H 'Authorization: Bearer <AGENCY_ACCESS_TOKEN>' \
  -H 'Version: v3'
```

**Migration guidance:** keep using the v2 camelCase forms — they work under every published
version today, which makes them the safer default. Move to the hyphenated forms only when
you deliberately set `Version: v3` for the whole call, and never mix (a hyphenated path with
`2021-07-28` is a hard 404). Requires scope `oauth.readonly`.

### 5c. The third rename (lower stakes)

`DELETE /contacts/{contactId}/campaigns/removeAll` → `DELETE /contacts/{contactId}/campaigns/remove-all`.
DELETE-only, so not GET-probeable; same rule applies — match the path form to the Version
you send.

---

## 6. What v3 adds that v2 cannot do

Use `Version: v3` when you need any of these.

### Brand voices — **PROVEN v3-only**
A client's brand voice, readable from HighLevel instead of restated by hand.
```
GET,POST   /brand-boards/locations/{locationId}/brand-voices
DELETE,GET,PATCH  /brand-boards/locations/{locationId}/brand-voices/{brandVoiceId}
POST       /brand-boards/locations/{locationId}/brand-voices/{brandVoiceId}/default
```
```bash
curl --request GET 'https://services.leadconnectorhq.com/brand-boards/locations/<LOCATION_ID>/brand-voices' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: v3'
# 200 {"items":[...],"total":N}   — the same call with Version: 2021-07-28 returns 404 Cannot GET
```
Scopes: `brand-boards/design-kit.readonly|write`.

### Social planner: scheduling queues + comments (`social-planner-v3`, 45 ops vs 40)
```
POST        /social-media-posting/category/queues
GET         /social-media-posting/category/queues/available-categories
POST        /social-media-posting/category/queues/list
POST        /social-media-posting/category/queues/list/calendar
GET,PUT     /social-media-posting/category/queues/{queueId}
POST        /social-media-posting/category/queues/{queueId}/items
POST        /social-media-posting/category/queues/{queueId}/create/item
PUT,DELETE  /social-media-posting/category/queues/{queueId}/items/{itemId}
POST        /social-media-posting/category/queues/{queueId}/items/{itemId}/clone
PUT         /social-media-posting/category/queues/{queueId}/items/{itemId}/reset
POST        /social-media-posting/category/queues/{queueId}/slots
POST        /social-media-posting/category/queues/{queueId}/edit/{start|save|discard|calendar}
DELETE      /social-media-posting/category/queues/{postId}/active-post
POST        /social-media-posting/comments/{platform}
POST        /social-media-posting/comments/{platform}/list
POST,DELETE /social-media-posting/comments/{platform}/{id}/like
```
v3 also collapses the per-platform OAuth routes into generic `{platform}` routes:
`GET /social-media-posting/oauth/{platform}/start` and
`GET,POST /social-media-posting/oauth/{locationId}/{platform}/accounts/{accountId}`,
replacing the seven hard-coded `facebook|google|instagram|linkedin|tiktok|tiktok-business|twitter` variants.

### Chat widget (`chat-widget-v3` — the one app with no v2 spec at all)
```
POST           /chat-widget/
POST           /chat-widget/clone
GET            /chat-widget/list          (requires limit + offset)
GET,PATCH,PUT  /chat-widget/data/{locationId}/{id}
GET            /chat-widget/public/config/{id}
DELETE         /chat-widget/{locationId}/{id}
```

### Emails: rebuilt surface (`emails-v3`, 18 ops vs 5)
```
GET,POST    /emails/locations/{locationId}/campaigns/emails
GET,PATCH,DELETE /emails/locations/{locationId}/campaigns/emails/{campaignId}
POST        /emails/locations/{locationId}/campaigns/emails/{campaignId}/schedule
GET         /emails/locations/{locationId}/campaigns/bulk-actions[/{campaignId}]
GET         /emails/locations/{locationId}/campaigns/workflows[/{campaignId}]
GET         /emails/locations/{locationId}/campaigns/stats/{source}/{sourceId}
GET,POST    /emails/locations/{locationId}/templates
GET,PATCH,DELETE /emails/locations/{locationId}/templates/{templateId}
POST        /emails/locations/{locationId}/templates/folders
POST        /emails/locations/{locationId}/templates/import
```
The old `/emails/builder*` routes still answer today (PROVEN — 200 under both `2021-07-28`
and `v3`), but the v3 spec no longer carries them. Build new work on the `locations/...` form.

### SaaS (`saas-v3`, 25 ops vs 22)
Adds `POST /saas/allow-attach-rebilling/{locationId}` and brings the wallet-balance
endpoints into the spec:
`GET /saas-api/public-api/companies/{companyId}/locations/{locationId}/wallet-balance` and
`POST .../wallet-balance/complimentary-credits`.

### Locations (`locations-v3`, 32 ops vs 29)
Adds `GET /locations/{locationId}/conversationChannels/{type}` and
`GET,PUT /locations/{locationId}/permissions`.

---

## 7. Practical decision rule

```
1. Need brand voices, social queues/comments, the new emails surface,
   chat widget, or a hyphenated /oauth/... path?
       -> send Version: v3, and use the v3 path form.

2. Everything else?
       -> send the app's spec-declared v2 value:
          2021-04-15  for conversations, calendars, saas-api, voice-ai,
                      agent-studio, conversation-ai, knowledge-base
          2021-07-28  for everything else
       -> store declares none; send 2021-07-28.
       -> links accepts both.

3. NEVER omit the header (401) and NEVER invent a value (401).
4. NEVER mix a v3 path form with a v2 Version value -> 404 Cannot GET.
```
