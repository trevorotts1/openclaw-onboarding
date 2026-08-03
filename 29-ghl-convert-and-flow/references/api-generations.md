# api-generations.md — Choosing the right API version

> **Read this before any GHL call.** It tells you which `Version` value to send, which
> values are merely *older* (fine) versus actually *wrong*, and which paths only exist under
> one version.
>
> **Verified 2026-08-03 against**, in order of authority:
> 1. **HighLevel's live docs** — `https://marketplace.gohighlevel.com/docs` (**highest**)
> 2. **Live read-only GET probes** against operator-owned sub-accounts (marked **PROVEN**)
> 3. The OpenAPI spec repo `GoHighLevel/highlevel-api-docs` (**lowest — it lags, see §0**)

---

## 0. ⚠ The spec repo lags the live docs — read this first

`GoHighLevel/highlevel-api-docs` is a **periodic dump, not a live mirror**:

| Fact | Value |
|---|---|
| Last commit to the whole repo | **2026-06-19** |
| Most `apps/*.json` last synced | **2026-05-01** |
| `saas-api.json` last synced | **2025-08-13** — ~12 months stale |
| `social-media-posting.json` last synced | **2025-08-11** |
| HighLevel's changelog runs through | **2026-07-30** |

**Consequence:** an endpoint or version can be live and documented on the docs site while the
spec repo still shows the old shape. **Never declare a fleet doc "wrong" on spec evidence
alone** — check `https://marketplace.gohighlevel.com/docs` for that endpoint under that
version first. Two "corrections" made against these skills on 2026-08-03 were artifacts of
exactly this lag and had to be reverted the same day (see §2).

---

## 1. There are FIVE concurrent versions — not "v2 and v3"

Source: `https://marketplace.gohighlevel.com/docs/Versioning/` (fetched 2026-08-03).

| Version | Release date | Supported until |
|---|---|---|
| **`v3`** | **June 11, 2026** | **TBD** |
| `2023-02-21` | February 21, 2023 | TBD |
| `2021-07-28` | July 28, 2021 | TBD |
| `2021-04-15` | April 15, 2021 | TBD |
| `legacy` | January 1, 2021 | TBD |

HighLevel's own words: *"The version is specified per-request using the `Version` request
header."* … *"When a new version is released, the previous version enters a maintenance
window — it continues to receive critical bug fixes and security patches but no new
features."*

**Four load-bearing facts:**

1. **No version has a published retirement date.** Every "Supported until" is **TBD**. There
   is **no forced migration and no deadline.** Do not tell a client their integration is
   about to break.
2. **An older version is not a bug.** `2023-02-21` and `2021-04-15` are first-class supported
   versions with complete documentation sets. A doc using one is making a *choice*, not an
   error.
3. **`v3` is the latest named version** — the docs site defaults to it and banner-marks older
   sets *"no longer actively maintained."* But **HighLevel publishes no GA/beta/preview
   label**, so do not write "v3 is GA" as if it were a quote.
4. **Nothing newer than v3 exists** as of 2026-08-03. (`v4` appears on the Versioning page
   only as a naming-format example, not in the supported-versions table.)

---

## 2. What the runtime actually does — PROVEN

Live read-only GETs, operator-owned sub-account, 2026-08-03.

| Sent | Result |
|---|---|
| No `Version` header | **401** — `"version header was not found."` |
| `Version: 2020-01-01` (unpublished) | **401** — `"version header is invalid"` |
| `2021-07-28` / `2021-04-15` / `2023-02-21` / `v3` on `GET /contacts/`, `/users/`, `/calendars/` | **200 on all four** |
| `2023-02-21` on `GET /saas-api/public-api/agency-plans/{companyId}` | **200** |

**Conclusions:**
- The header is **mandatory** and checked against the published set. Omitting or inventing
  one is a 401 — never a 400.
- **No endpoint was found that rejects `2021-04-15`.** The claim that a "wrong" Version
  header was causing live 400s on contacts/locations/opportunities/users/payments **is false
  and has been withdrawn.** Those references were standardised on `2021-07-28` for
  *consistency with the current pre-v3 spec*, not to fix an outage.
- **If you are chasing a real client failure, the Version header is probably not the cause.**
  Look at scopes, PIT-vs-OAuth, and location-vs-company token first.

**Where the version genuinely decides routing:** brand-new or renamed paths. See §4.

---

## 3. The Version is declared PER-OPERATION, not per-app

Any statement of the form "app X uses version Y" is an approximation. The clearest
counter-example is in the v3 set itself:

- **`ad-publishing-v3` — 95 operations: 94 declare `2021-07-28`, exactly one declares `v3`**
  (only `GET /ad-publishing/facebook/campaigns/{campaignId}/publishing-progress`). That file
  is the pre-v3 ad spec plus one new endpoint.
- **`phone-system-v3`** declares the parameter in lowercase as **`version`**, not `Version`.
  HTTP header names are case-insensitive (RFC 7230) so `Version: v3` still works.
- **`store` / `store-v3`** declare **no Version parameter at all** — in either generation.

**Operations that declare NO Version parameter** (sending one is harmless):
`POST /oauth/token` · all 18 `store` ops · all 5 `/marketplace/billing/charges*` ops ·
`GET /funnels/funnel/list`, `GET /funnels/page`, `GET /funnels/page/count` ·
`GET /conversations/messages/email/{id}`, `DELETE /conversations/messages/email/{id}/schedule`

### Pre-v3 defaults by app (41 published specs)

- **`2021-07-28` exclusively: 32 specs.** (33 *accept* it, counting `links`.)
- **`2021-04-15` exclusively: 7 specs** — agent-studio, calendars, conversation-ai,
  conversations, knowledge-base, saas-api, voice-ai.
- **Both: 1** — `links`.
- **Neither: 1** — `store`.

32 + 7 + 1 + 1 = 41 ✓

> Earlier revisions of this skill said "33 of 41". The precise phrasing is **"32 declare
> `2021-07-28` exclusively; 33 accept it."**

---

## 4. Generation-gated paths — where the header decides routing

Most established paths accept every published version (§2). **These do not** — the wrong
version returns `404 Cannot GET`.

| Path | `2021-07-28` | `v3` | Verdict |
|---|---|---|---|
| `GET /oauth/installedLocations` | **401** (exists, scope) | exists | v2 form works in BOTH |
| `GET /oauth/installed-locations` | **404 Cannot GET** | exists | **v3-ONLY** |
| `GET /brand-boards/locations/{locationId}/brand-voices` | **404 Cannot GET** | **200** | **v3-ONLY** |
| `GET /contacts/` | 200 | **200** | dropped from the v3 spec, still answering |
| `GET /users/` | 200 | **200** | dropped from the v3 spec, still answering |
| `GET /emails/builder` | 200 | **200** | dropped from the v3 spec, still answering |

All rows PROVEN by live GET, 2026-08-03.

**Rule:** a **renamed or brand-new** path needs its own version. An **existing** path keeps
working under every published version — including ones the v3 spec drops. Spec removal has
**not** been enforced at the runtime, but do not build on that.

---

## 5. The two OAuth renames

Both appear in the 2026-06-11 v3 changelog batch.

> **Do not claim HighLevel published deprecation guidance for these.** No migration guide
> exists. The phrase "removed without deprecation" is a changelog-diff label, not a HighLevel
> policy statement — and since **no version has a retirement date**, the old paths stay
> callable under their own version headers indefinitely.

### 5a. Mint a location token

| Version | Path |
|---|---|
| `2021-07-28` | `POST /oauth/locationToken` |
| `v3` | `POST /oauth/location-token` |

```bash
curl --request POST 'https://services.leadconnectorhq.com/oauth/locationToken' \
  -H 'Authorization: Bearer <AGENCY_ACCESS_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'companyId=<COMPANY_ID>' \
  --data-urlencode 'locationId=<LOCATION_ID>'
```
POST-only, so a read-only probe cannot confirm either form by GET.

### 5b. List installed locations — **PROVEN gated**

| Version | Path |
|---|---|
| `2021-07-28` | `GET /oauth/installedLocations` — also resolves under `v3` |
| `v3` | `GET /oauth/installed-locations` — **404 under `2021-07-28`** |

**Guidance:** stay on the camelCase forms; they work under every version. Move only when you
deliberately set `Version: v3` for the whole call. **Never mix a v3 path form with an older
version** — that is a hard 404.

### 5c. Also renamed
`DELETE /contacts/{contactId}/campaigns/removeAll` → `.../campaigns/remove-all`.

---

## 6. Capability that requires `Version: v3`

### 6a. Opportunities pipeline CRUD — **LIVE**
Documented on the live docs site under `Version: v3`. Absent from both spec files only
because the repo lags (announced 2026-06-26; specs synced 2026-05-01 / 2026-06-19).

```
POST   /opportunities/pipelines
GET    /opportunities/pipelines/{pipelineId}
PUT    /opportunities/pipelines/{pipelineId}
DELETE /opportunities/pipelines/{pipelineId}
```
Sources: `https://marketplace.gohighlevel.com/docs/ghl/opportunities/create-pipeline`,
`.../update-pipeline/index.html`, `.../delete-pipeline/index.html`.

**Semantics you must know before calling these:**
- **Create:** needs at least one stage. Pipeline names unique per location
  (case-insensitive); stage names unique within the pipeline. For manual win probability set
  `useOpportunityProbability: true` and give every stage a `stageWinProbability` (0–100) —
  miss one and the system silently falls back to auto-computed probabilities.
- **Update:** the `stages` array is a **complete replacement**. Include a stage's `id` to keep
  it; omit `id` to create a new one; omitting a stage **deletes** it. You cannot remove all
  stages. Opportunities in a deleted stage move to the lowest-ranked remaining stage.
- **Delete:** **permanently deletes the pipeline and every opportunity in it, at every
  stage. Irreversible.** Export first.

**PROVEN 2026-08-03:** `GET /opportunities/pipelines/{pipelineId}` returns 200 under both
`2021-07-28` and `v3`. The write operations were **not** probed — this audit made no write
calls against GoHighLevel.

### 6b. Calendars v3 — the Services / booking-catalog surface (41 → 59 ops)
The largest single capability addition in v3.
```
GET,POST,PUT,DELETE  /calendars/services/catalog[/{serviceId}]
GET,POST,PUT,DELETE  /calendars/services/bookings[/{bookingId}]
GET,POST,PUT,DELETE  /calendars/services/locations[/{serviceLocationId}]
GET,POST,PUT         /calendars/schedules/event-calendar/{calendarId}
```
Note the version flip: pre-v3 calendars is `2021-04-15`; **calendars-v3 is `v3` on all 59
operations.**

### 6c. Brand voices — PROVEN v3-only
```
GET,POST          /brand-boards/locations/{locationId}/brand-voices
DELETE,GET,PATCH  /brand-boards/locations/{locationId}/brand-voices/{brandVoiceId}
POST              /brand-boards/locations/{locationId}/brand-voices/{brandVoiceId}/default
```
200 under `v3`; **404 Cannot GET** under `2021-07-28`. brand-boards goes 5 → 11 ops.

### 6d. Social planner queues + comments (40 → 45 ops)
22 queue/comment operations. Queues: `POST /social-media-posting/category/queues`,
`/queues/available-categories`, `/queues/list`, `/queues/list/calendar`,
`GET,PUT /queues/{queueId}`, `POST /queues/{queueId}/items`,
`PUT,DELETE /queues/{queueId}/items/{itemId}`, `.../clone`, `.../reset`,
`POST /queues/{queueId}/slots`, `POST /queues/{queueId}/edit/{start|save|discard|calendar}`,
`DELETE /queues/{postId}/active-post`. Comments: `POST /comments/{platform}`,
`POST /comments/{platform}/list`, `POST,DELETE /comments/{platform}/{id}/like`.
v3 also collapses the seven per-platform OAuth routes into generic `{platform}` routes.

### 6e. Chat widget — v3-only app (8 ops, no pre-v3 spec)
```
POST /chat-widget/ · POST /chat-widget/clone · GET /chat-widget/list (needs limit + offset)
GET,PATCH,PUT /chat-widget/data/{locationId}/{id} · GET /chat-widget/public/config/{id}
DELETE /chat-widget/{locationId}/{id}
```

### 6f. Emails — 18-op rewrite (v2 had 5)
v3 drops the five `/emails/builder*` operations **and** `GET /emails/schedule`, replacing
them with `/emails/locations/{locationId}/campaigns/{emails,workflows,bulk-actions,stats}`
and `/emails/locations/{locationId}/templates[/folders,/import]`.

### 6g. SaaS and locations
`saas-v3` (25 ops) adds `allow-attach-rebilling/{locationId}` plus the two wallet-balance
endpoints. ⚠ The changelog calls `allow-attach-rebilling` a **GET**; the spec declares
**POST** — verify live. `locations-v3` (32 ops) adds
`GET /locations/{locationId}/conversationChannels/{type}` and
`GET,PUT /locations/{locationId}/permissions`.

---

## 7. Webhooks — three facts no skill documented

Source: `https://ideas.gohighlevel.com/changelog?labels=api`

- **Automated retries fire ONLY on HTTP 429** (10-minute intervals with jitter), added
  2025-09-23. **A receiver that returns 500 gets NO retry.** If your endpoint is down or
  erroring, the event is simply lost — build your own replay.
- **User lifecycle webhooks exist** — `user.created`, `user.updated`, `user.deleted`
  (2025-08-28). Relevant to any user-provisioning flow.
- **A Webhook Logs dashboard exists** — Developer Portal → Insights → Logs, 30-day
  retention (2025-11-13).

---

## 8. Decision rule

```
1. Need pipeline CRUD, calendar services, brand voices, social queues/comments,
   chat widget, the new emails surface, or a hyphenated /oauth/... path?
       -> Version: v3, and use the v3 path form.

2. SaaS?            -> 2023-02-21 (documented + proven). v3 is the deliberate
                       forward move; 2021-04-15 comes from a year-stale file.

3. POST /users/?    -> 2023-02-21 or 2021-07-28. Both documented, both work.

4. Everything else? -> 2021-07-28, EXCEPT agent-studio, calendars,
                       conversation-ai, conversations, knowledge-base,
                       saas-api and voice-ai, which are 2021-04-15.
                       links takes either. store declares none.

5. NEVER omit the header (401). NEVER invent a value (401).
6. NEVER pair a v3 path form with an older version (404 Cannot GET).
7. An older supported version is NOT a defect. Only a blanket
   "use value X for everything" rule is.
```
