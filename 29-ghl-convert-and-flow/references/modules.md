# modules.md - All 41 GHL Modules Overview

Base URL for all endpoints: `https://services.leadconnectorhq.com`

**41 published pre-v3 app specs, 576 operations.** Scopes: 118 in the pre-v3 specs, 127 in v3, **142 across all sources** (see `references/auth.md`). A second
generation — **42 v3 specs, `Version: v3`** — shipped 2026-06-19; see `references/auth.md`
→ "The v3 generation". Endpoint counts and scope names below are read out of the specs at
`https://github.com/GoHighLevel/highlevel-api-docs/tree/main/apps` (enumerated 2026-08-03),
not estimated.

> **Version is per-OPERATION, and FIVE versions are supported concurrently** (`v3`,
> `2023-02-21`, `2021-07-28`, `2021-04-15`, `legacy` — all "Supported until: TBD").
> `2021-07-28` is the pre-v3 default. The ONLY apps on
> `2021-04-15` are: conversations, calendars, saas-api, voice-ai, agent-studio,
> conversation-ai, knowledge-base. `links` accepts both; `store` declares none.
> Full rule: `references/auth.md` → "Version Header".

---

## High-Priority Modules (Most Used)

### contacts (32 endpoints) — `2021-07-28`
Create, read, update, delete contacts. Add/remove tags. Manage tasks and notes. Add contacts to campaigns and workflows.

**Top endpoints:**
- `POST /contacts/search` - Search contacts with filters. **Required in v3** — `GET /contacts/` was removed in the v3 generation.
- `POST /contacts/` - Create contact (explicit NEW record only)
- `POST /contacts/upsert` - Create-or-update in one call (DEFAULT for generic add/save; resolves per Location-level Allow Duplicate Contact configuration)
- `GET /contacts/{contactId}` - Get contact by ID
- `PUT /contacts/{contactId}` - Update contact
- `POST /contacts/{contactId}/tags` - Add tags
- `DELETE /contacts/{contactId}/tags` - Remove tags
- `POST /contacts/{contactId}/workflow/{workflowId}` - Add to workflow
- `GET /contacts/search/duplicate` - Duplicate lookup
- `POST /contacts/bulk/tags/update/{type}` - Bulk tag update
- `POST /contacts/bulk/business` - Bulk business assignment
- `POST,DELETE /contacts/{contactId}/followers` - Manage followers

**Scopes:** `contacts.readonly`, `contacts.write`
**Full detail:** `references/contacts.md`

---

### conversations (29 endpoints) — `2021-04-15`
Search and manage conversations. Send SMS, email, WhatsApp, and other message types. Get message history.

**Top endpoints:**
- `GET /conversations/search` - Search conversations by locationId
- `POST /conversations/messages` - Send outbound message
- `GET /conversations/{conversationId}` - Get conversation by ID
- `GET /conversations/{conversationId}/messages` - Get message history
- `POST /conversations/messages/inbound` - Add inbound message record
- `GET /conversations/messages/export` - Export messages
- `POST /conversations/messages/review-reply` - Review reply
- 3-step upload flow: `/upload/initiate` → `/upload` → `/upload/complete`
- `GET,POST /conversations/preferences/custom-subtypes`
- `GET /conversations/preferences/unsubscriptions/status`

**Scopes:** `conversations.readonly`, `conversations.write`, `conversations/message.readonly`, `conversations/message.write`, `conversations/livechat.write`
**Full detail:** `references/conversations.md`

---

### calendars (41 pre-v3 endpoints; **59 in v3**) — `2021-04-15` / `v3`
Manage calendars and appointments. Get free slots. Create/update bookings. Manage blocked times, groups, resources and schedules.

**Top endpoints:**
- `GET /calendars/` - Get all calendars for a location
- `GET /calendars/{calendarId}/free-slots` - Get available time slots
- `POST /calendars/events/appointments` - Create appointment
- `GET /calendars/events/appointments/{eventId}` - Get appointment
- `PUT /calendars/events/appointments/{eventId}` - Update appointment
- `GET /calendars/events` - Get all calendar events for date range
- `POST /calendars/groups/validate-slug` - Validate a group slug
- `GET,POST /calendars/resources/{resourceType}` - Rooms/equipment
- `/calendars/schedules*` - Schedule management

**Scopes:** `calendars.readonly`, `calendars.write`, `calendars/events.readonly`, `calendars/events.write`, `calendars/groups.readonly`, `calendars/groups.write`, `calendars/resources.readonly`, `calendars/resources.write`
**Full detail:** `references/calendars.md`

> **v3 adds an entire Services / booking-catalog surface (41 → 59 ops)** — the largest single
> capability addition in v3. Requires `Version: v3` (calendars-v3 is `v3` on all 59 ops):
> `GET,POST,PUT,DELETE /calendars/services/catalog[/{serviceId}]`,
> `.../services/bookings[/{bookingId}]`, `.../services/locations[/{serviceLocationId}]`,
> `GET,POST,PUT /calendars/schedules/event-calendar/{calendarId}`.

---

### locations (29 endpoints) — `2021-07-28`
Sub-account configuration. Custom fields. Tags. Users. Pipeline settings. Tasks.

**Top endpoints:**
- `GET /locations/{locationId}` - Get location details
- `PUT /locations/{locationId}` - Update location
- `GET /locations/search` - Search/list all locations
- `GET /locations/{locationId}/customFields` - Get custom fields
- `POST /locations/{locationId}/customFields` - Create custom field
- `POST /locations/{locationId}/customFields/upload` - Bulk upload custom fields
- `GET /locations/{locationId}/tags` - Get tags for location
- `POST /locations/{locationId}/tasks/search` - Search tasks
- `POST /locations/{locationId}/recurring-tasks` (+ CRUD) - Recurring tasks

**Scopes:** `locations.readonly`, `locations.write`, `locations/customFields.readonly`, `locations/customFields.write`, `locations/customValues.*`, `locations/tags.*`, `locations/tasks.readonly`, `locations/templates.readonly`
**Full detail:** `references/locations.md`

---

### opportunities (12 endpoints) — `2021-07-28`
Pipeline and deal management. Create, update, search, and delete opportunities.

**Top endpoints:**
- `POST /opportunities/search` - Search opportunities (filter by pipeline, stage, status)
- `GET /opportunities/pipelines` - Get all pipelines for a location — **read-only**
- `POST /opportunities/` - Create opportunity
- `POST /opportunities/upsert` - Create-or-update
- `PUT /opportunities/{id}` - Update opportunity
- `PUT /opportunities/{id}/status` - Change status
- `GET /opportunities/{id}` - Get opportunity by ID
- `POST,DELETE /opportunities/{id}/followers` - Manage followers

> **Pipeline CRUD is LIVE under `Version: v3`** — `POST /opportunities/pipelines`,
> `GET/PUT/DELETE /opportunities/pipelines/{pipelineId}`. Documented on HighLevel's live docs
> site; absent from the spec files only because the repo lags. Update replaces the whole
> `stages` array; delete is an **irreversible cascade** that removes every opportunity in the
> pipeline. See `references/opportunities.md`.

**Scopes:** `opportunities.readonly`, `opportunities.write`
**Full detail:** `references/opportunities.md`

---

## AI Modules

### ad-manager / ad-publishing (94 endpoints; 95 in v3) — `2021-07-28`
The largest single surface in the API. Facebook, Google and LinkedIn campaigns, adsets, ads, custom audiences, pixels, lead forms, reporting, targeting search, keyword ideas.

**Key endpoints:** `PUT /ad-publishing/facebook/campaigns`, `POST /ad-publishing/facebook/campaigns/{campaignId}/publish|pause|resume|duplicate`, `PUT /ad-publishing/facebook/adsets`, `PUT /ad-publishing/facebook/ads-v2`, `GET /ad-publishing/facebook/reporting`, `GET,POST /ad-publishing/facebook/page/{pageId}/forms`, `PUT /ad-publishing/google/ads`, `POST /ad-publishing/google/keyword-ideas`, `PUT /ad-publishing/linkedin/ads`
**Scopes:** `adPublishing.readonly`, `adPublishing.write`
**Full detail:** `references/ad-publishing.md`

> **Version is per-operation here.** `ad-publishing-v3` has 95 ops of which **94 still
> declare `2021-07-28`** — only `GET /ad-publishing/facebook/campaigns/{campaignId}/publishing-progress`
> is `v3`. Do not assume the v3 file means `Version: v3`.

---

### knowledge-base (14 endpoints) — `2021-04-15`
Knowledge bases, web crawler, and FAQs. Feeds both Conversation AI and Voice AI — this is how you train an agent on the client's own content.

**Key endpoints:** `GET,POST /knowledge-bases/`, `DELETE,GET,POST /knowledge-bases/crawler`, `GET /knowledge-bases/crawler/status`, `POST /knowledge-bases/crawler/train`, `GET,POST /knowledge-bases/faqs`
**Scopes:** none declared in the spec — grant broadly and verify live.
**Full detail:** `references/knowledge-base.md`

---

### conversation-ai (12 endpoints) — `2021-04-15`
Configures the conversational agent itself: agents, agent actions, follow-up settings. This is the API layer behind the conversational-AI system.

**Key endpoints:** `POST /conversation-ai/agents`, `GET /conversation-ai/agents/search`, `DELETE,GET,PUT /conversation-ai/agents/{agentId}`, `POST /conversation-ai/agents/{agentId}/actions`, `PATCH /conversation-ai/agents/{agentId}/followup-settings`, `GET /conversation-ai/generations`
**Scopes:** `conversation-ai.readonly`, `conversation-ai.write`
**Full detail:** `references/conversation-ai.md`

---

### agent-studio (11 endpoints) — `2021-04-15`
Full AI agent lifecycle: create, version, publish, execute, delete.

**Key endpoints:** `GET,POST /agent-studio/agent`, `PATCH /agent-studio/agent/versions/{versionId}`, `POST /agent-studio/agent/versions/{versionId}/publish`, `DELETE,GET,PATCH /agent-studio/agent/{agentId}`, `POST /agent-studio/agent/{agentId}/execute`, `GET /agent-studio/public-api/agents`
**Scopes:** `agent-studio.readonly`, `agent-studio.write`
**Full detail:** `references/agent-studio.md`

---

### voice-ai (11 endpoints) — `2021-04-15`
Voice AI agents, agent **actions**, and the call-log/transcript dashboard.

**Key endpoints:** `POST /voice-ai/actions`, `DELETE,GET,PUT /voice-ai/actions/{actionId}`, `GET,POST /voice-ai/agents`, `DELETE,GET,PATCH /voice-ai/agents/{agentId}`, `GET /voice-ai/dashboard/call-logs`, `GET /voice-ai/dashboard/call-logs/{callId}`
**Scopes:** `voice-ai-agents.readonly`, `voice-ai-agents.write`, `voice-ai-agent-goals.readonly`, `voice-ai-agent-goals.write`, `voice-ai-dashboard.readonly`
**Full detail:** `references/voice-ai.md`

---

## Secondary Modules

### invoices (42 endpoints) — `2021-07-28`
Create, send, and manage invoices. Handle invoice items, schedules, templates, and the full **estimate** surface.

**Key endpoints:** `GET /invoices/`, `POST /invoices/`, `POST /invoices/{invoiceId}/send`, `POST /invoices/estimate`, `/invoices/estimate/list`, `/invoices/estimate/template*`, `POST /invoices/estimate/{estimateId}/invoice`
**Scopes:** `invoices.readonly`, `invoices.write`, `invoices/estimate.readonly|write`, `invoices/schedule.readonly|write`, `invoices/template.readonly|write`

---

### social-media-posting (40 endpoints) — `2021-07-28`
Schedule and publish posts to social platforms. Manage accounts and post history.

**Key endpoints:** `GET /social-media-posting/`, `POST /social-media-posting/`
**Scopes:** `socialplanner/account.readonly|write`, `socialplanner/post.readonly|write`, `socialplanner/category.readonly`, `socialplanner/tag.readonly`, `socialplanner/csv.readonly|write`, `socialplanner/oauth.readonly|write`

> **v3 adds 5 more ops (45 total) — `Version: v3` required.** Two new capabilities:
> - **Scheduling queues:** `POST /social-media-posting/category/queues`, `/queues/available-categories`, `/queues/list`, `/queues/list/calendar`, `GET,PUT /queues/{queueId}`, `POST /queues/{queueId}/items`, `PUT,DELETE /queues/{queueId}/items/{itemId}`, `POST /queues/{queueId}/items/{itemId}/clone`, `PUT .../reset`, `POST /queues/{queueId}/slots`, `POST /queues/{queueId}/edit/{start|save|discard|calendar}`, `DELETE /queues/{postId}/active-post`
> - **Comments API:** `POST /social-media-posting/comments/{platform}`, `POST /comments/{platform}/list`, `POST,DELETE /comments/{platform}/{id}/like`
>
> v3 also collapses the per-platform OAuth paths (`/oauth/facebook/start`, `/oauth/google/start`, …) into generic `{platform}` paths: `GET /social-media-posting/oauth/{platform}/start` and `GET,POST /oauth/{locationId}/{platform}/accounts/{accountId}`.
> Source: `https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/apps/v3/social-planner-v3.json`

---

### products (27 endpoints) — `2021-07-28`
Manage products, prices and collections. Physical, digital, and service products.

**Scopes:** `products.readonly`, `products.write`, `products/prices.readonly|write`, `products/collection.readonly|write`

---

### payments (23 endpoints) — `2021-07-28`
Orders, transactions, subscriptions, coupons, integrations and custom payment providers.

**Scopes:** `payments/orders.readonly|write`, `payments/orders.collectPayment`, `payments/transactions.readonly`, `payments/subscriptions.readonly`, `payments/coupons.readonly|write`, `payments/integration.readonly|write`, `payments/custom-provider.readonly|write`

---

### saas-api (22 endpoints) — `2023-02-21`
SaaS reseller operations. Manage sub-accounts at scale, rebilling, pause/unpause.

> **Use `2023-02-21`.** HighLevel publishes a full SaaS documentation set under it and it is
> a supported version; PROVEN live 2026-08-03. `saas-api.json` says `2021-04-15`, but that
> file was last synced **2025-08-13** — the stalest in the spec repo. The deliberate forward
> move is `v3`.
> **Deprecated/current split:** the live SaaS docs publish two parallel sets; eleven endpoints
> exist in both a `-deprecated` and a current form. Check which your URL maps to.
> **Unpause:** there is no documented resume endpoint, but `POST /saas/pause/{locationId}` takes a `paused` boolean in the body, so sending `"paused": false` is the obvious unpause candidate — **untested; verify before relying on it.**
> v3 adds `POST /saas/allow-attach-rebilling/{locationId}` and moves the wallet-balance endpoints into the spec (25 ops).

**Scopes:** `saas/location.read`, `saas/location.write`, `saas/company.write` (v3 adds `saas/company.read`)

---

### store (18 endpoints) — *no Version parameter declared*
Shipping carriers, shipping zones, shipping rates, and store settings.

**Key endpoints:** `GET,POST /store/shipping-carrier`, `DELETE,GET,PUT /store/shipping-carrier/{shippingCarrierId}`, `GET,POST /store/shipping-zone`, `POST /store/shipping-zone/shipping-rates`, `GET,POST /store/shipping-zone/{shippingZoneId}/shipping-rate`, `GET,POST /store/store-setting`
**Scopes:** none declared in either the spec or `docs/oauth/Scopes.md`. The `stores/*` names older docs listed are **unverified** — confirm live.

---

### associations (10 endpoints) — `2021-07-28`
Manage associations between objects (relationships between contacts, deals, etc.).

**Scopes:** `associations.readonly`, `associations.write`, `associations/relation.readonly`, `associations/relation.write`

---

### marketplace (9 endpoints) — `2021-07-28`
App installations, rebilling config, and **marketplace billing charges**.

**Key endpoints:** `DELETE,GET /marketplace/app/{appId}/installations`, `GET /marketplace/app/{appId}/rebilling-config/location/{locationId}`, `GET,POST /marketplace/billing/charges`, `GET /marketplace/billing/charges/has-funds`, `DELETE,GET /marketplace/billing/charges/{chargeId}`, `POST /marketplace/external-auth/migration`
**Scopes:** `charges.readonly`, `charges.write`, `marketplace-installer-details.readonly`, `marketplace-external-auth-migration.write`, `oauth.readonly`, `oauth.write`

---

### objects (9 endpoints) — `2021-07-28`
Custom object schema and record management.

**Scopes:** `objects/schema.readonly`, `objects/schema.write`, `objects/record.readonly`, `objects/record.write`

---

### custom-fields (8 endpoints) — `2021-07-28`
Create and manage custom fields for contacts, opportunities, and other objects.

**Scopes:** `locations/customFields.readonly`, `locations/customFields.write`

---

### blogs (7 endpoints) — `2021-07-28`
Blog post management. Authors and categories.

**Scopes:** `blogs/list.readonly`, `blogs/posts.readonly`, `blogs/post.write`, `blogs/post-update.write`, `blogs/check-slug.readonly`, `blogs/author.readonly`, `blogs/category.readonly`

---

### funnels (7 endpoints) — `2021-07-28`
Funnel and page management, redirects, page counts.

**Scopes:** `funnels/funnel.readonly`, `funnels/page.readonly`, `funnels/pagecount.readonly`, `funnels/redirect.readonly`, `funnels/redirect.write`

---

### medias (7 endpoints) — `2021-07-28`
Media library management. Upload and retrieve media files.

**Key endpoint:** `POST /medias/upload-file` (multipart). **Deep reference:** `references/medias.md` (carved from the proven skill 28/35/37 implementations — endpoint, multipart fields, `parentId` folder caveat, CDN URL formats, retry pattern). This is the Tier-3 media path the router uses; the CLI has NO media commands so media NEVER routes to Tier 0.

**Scopes:** `medias.readonly`, `medias.write`

---

### users (7 endpoints) — `2021-07-28`
User/team member management within a location.

**Key endpoints:** `GET,POST /users/`, `GET /users/search`, `POST /users/search/filter-by-email`, `DELETE,GET,PUT /users/{userId}`
> `POST /users/` is documented under **both** `2023-02-21` and `2021-07-28`. Both work. Skill 44 uses `2023-02-21`; neither is a defect.
> In v3, `GET /users/` is removed — use `GET /users/search`.

**Scopes:** `users.readonly`, `users.write`

---

### links (6 endpoints) — accepts **both** `2021-04-15` and `2021-07-28`
URL redirect links management.

**Scopes:** `links.readonly`, `links.write`

---

### brand-boards (5 endpoints) — `2021-07-28`
Brand design kits — colours, fonts, logos held at the sub-account level.

**Key endpoints:** `POST /brand-boards/`, `GET /brand-boards/{locationId}`, `DELETE,GET,PATCH /brand-boards/{locationId}/{id}`
**Scopes:** `brand-boards/design-kit.readonly`, `brand-boards/design-kit.write`

> **v3 adds Brand Voices (`Version: v3`)** — a client's brand voice can be read from
> HighLevel instead of restated by hand, which matters directly for brand-consistency work:
> `GET,POST /brand-boards/locations/{locationId}/brand-voices`,
> `DELETE,GET,PATCH /brand-boards/locations/{locationId}/brand-voices/{brandVoiceId}`,
> `POST .../brand-voices/{brandVoiceId}/default`

---

### businesses (5 endpoints) — `2021-07-28`
Business profile management.

**Scopes:** `businesses.readonly`, `businesses.write`

---

### custom-menus (5 endpoints) — `2021-07-28`
Custom navigation menu management.

**Scopes:** `custom-menu-link.readonly`, `custom-menu-link.write`

---

### emails (5 endpoints) — `2021-07-28`
Email builder templates and schedules.

**Scopes:** `emails/builder.readonly`, `emails/builder.write`, `emails/schedule.readonly`

> **v3 replaces this surface wholesale (18 ops, `Version: v3`).** `/emails/builder*` is gone; use `/emails/locations/{locationId}/campaigns/*` (emails, workflows, bulk-actions, stats, schedule) and `/emails/locations/{locationId}/templates/*` (list, get, create, update, delete, folders, import).

---

### affiliate-manager (4 endpoints) — `2021-07-28`
Affiliates, commissions, payouts.

**Scopes:** `affiliate-manager.readonly`

---

### phone-system (4 endpoints) — `2021-07-28`
Phone number pools, search, and purchase.

**Key endpoints:** `GET /phone-system/number-pools`, `GET /phone-system/numbers/location/{locationId}`, `GET /phone-system/numbers/location/{locationId}/available`, `POST /phone-system/numbers/location/{locationId}/purchase`
**Scopes:** `phonenumbers.read`, `phonenumbers.write`, `numberpools.read`
**Full detail:** `references/phone-numbers.md`

---

### proposals (4 endpoints) — `2021-07-28`
Proposals and estimates documents.

**Key endpoints:** `GET /proposals/document`, `POST /proposals/document/send`, `GET /proposals/templates`, `POST /proposals/templates/send`
**Scopes:** none declared in the spec. (The `proposals-and-estimates.*` names older docs listed do not appear in either source.) The estimate surface itself lives in `invoices.json` — see **invoices**.

---

### snapshots (4 endpoints) — `2021-07-28`
Account snapshot management — directly useful for the agency onboarding flow, which sets `snapshotId` on location create but needs these to list snapshots and check load status.

**Key endpoints:** `GET /snapshots/`, `POST /snapshots/share/link`, `GET /snapshots/snapshot-status/{snapshotId}`, `GET /snapshots/snapshot-status/{snapshotId}/location/{locationId}`
**Scopes:** `snapshots.readonly`

---

### forms (3 endpoints) — `2021-07-28`
Form management and submission data.

**Scopes:** `forms.readonly`, `forms.write`

---

### oauth (3 endpoints) — `2021-07-28`
OAuth token management.

**Key endpoints:** `POST /oauth/token`, `POST /oauth/locationToken`, `GET /oauth/installedLocations`
> **In v3 the last two are renamed and the old paths removed without deprecation:** `POST /oauth/location-token` and `GET /oauth/installed-locations`. The v2 paths still work under `2021-07-28`. See `references/auth.md` → "The v3 generation".

**Scopes:** `oauth.readonly`, `oauth.write`

---

### surveys (2 endpoints) — `2021-07-28`
Survey data retrieval.

**Scopes:** `surveys.readonly`

---

### campaigns (1 endpoint) — `2021-07-28`
Campaign retrieval (`GET /campaigns/`).

**Scopes:** `campaigns.readonly`
**Full detail:** `references/campaigns.md`

---

### companies (1 endpoint) — `2021-07-28`
Company-level management.

**Scopes:** `companies.readonly`

---

### courses (1 endpoint) — `2021-07-28`
Course management.

**Scopes:** `courses.write`

---

### email-isv (1 endpoint) — `2021-07-28`
Email verification (`POST /email/verify`).

---

### workflows (1 endpoint) — `2021-07-28`
Workflow retrieval — **`GET /workflows/` is the ONLY operation, in both the v2 and v3 specs.**
There is no POST/PUT/PATCH/DELETE for workflows in any published generation. Contact↔workflow
membership writes DO exist (`POST`/`DELETE /contacts/{contactId}/workflow/{workflowId}`).

**Scopes:** `workflows.readonly`
**Full detail:** `references/campaigns.md`

---

## v3-only modules (require `Version: v3`)

### chat-widget (8 endpoints) — v3 only, no v2 equivalent
Page-level chat widget as a managed asset — create, clone, configure, delete.

**Key endpoints:** `POST /chat-widget/`, `POST /chat-widget/clone`, `GET /chat-widget/list`, `GET,PATCH,PUT /chat-widget/data/{locationId}/{id}`, `GET /chat-widget/public/config/{id}`, `DELETE /chat-widget/{locationId}/{id}`
**Source:** `https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/apps/v3/chat-widget-v3.json`

---

### Other v3 additions
- **locations-v3 (32 ops)** adds `GET /locations/{locationId}/conversationChannels/{type}` and `GET,PUT /locations/{locationId}/permissions`.
- **social-planner-v3 (45 ops)** — queues + comments, see **social-media-posting** above.
- **brand-boards-v3 (11 ops)** — brand voices, see **brand-boards** above.
- **emails-v3 (18 ops)** — rebuilt surface, see **emails** above.
- **saas-v3 (25 ops)** — see **saas-api** above.
