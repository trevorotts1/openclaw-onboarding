# auth.md - Authentication Reference

---

## Auth Methods

### Private Integration Token (PREFERRED)

The recommended auth method for Convert and Flow. Create a token in GHL with specific scopes.

**Header format:**
```
Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>
```

**Token format:** Starts with `pit-`

**Environment variable:** `$GOHIGHLEVEL_API_KEY`, stored in `~/.openclaw/secrets/.env` (chmod 600). The resolver in SKILL.md "Credentials" maps legacy aliases (`GHL_API_KEY`, `GHL_PRIVATE_INTEGRATION_TOKEN`, `PRIVATE_INTEGRATION_TOKEN`, `GHL_PRIVATE_TOKEN`) onto it and fails loud if unset. Use a **LOCATION-scoped** token — an agency PIT 401s on media.

**Where to create:** GHL > Settings > Integrations > Private Integrations > + Add Integration

**Scopes:** You select which scopes to grant at creation time. The token only has access to what you selected. You can add scopes later by editing the integration.

**Persistence:** Tokens do not expire automatically. Revoke them in GHL if compromised.

---

### OAuth Access Token

Used when building apps that act on behalf of GHL users (third-party integrations, marketplace apps).

**Header format:**
```
Authorization: Bearer <OAUTH_ACCESS_TOKEN>
```

**Flow:** Standard OAuth 2.0 authorization code flow.

**Authorization URL — note the `/v2/` segment.** HighLevel moved the authorization URLs to
`/v2/` on 2026-05-27. A URL without `/v2/` is the old form.

```
# Standard:
https://marketplace.gohighlevel.com/v2/oauth/chooselocation?
  response_type=code&
  redirect_uri=https://myapp.com/oauth/callback/gohighlevel&
  client_id=CLIENT_ID&
  scope=conversations/message.readonly conversations/message.write

# White-labelled agency — THIS IS THE ONE Convert and Flow uses:
https://marketplace.leadconnectorhq.com/v2/oauth/chooselocation?
  response_type=code&
  redirect_uri=https://myapp.com/oauth/callback/gohighlevel&
  client_id=CLIENT_ID&
  scope=...
```

Convert and Flow is a white-labelled agency, so the `marketplace.leadconnectorhq.com`
host is the correct one for our own consent flow — not `marketplace.gohighlevel.com`.

- Token URL: `https://services.leadconnectorhq.com/oauth/token`
- Scopes must be declared in your app's marketplace listing
- Append `&loginWindowOpenMode=self` to force the consent login into the SAME tab.
  Without it, a user who is not already signed in gets a new tab (the default).

**Refresh:** access tokens are valid for **24 hours**; refresh tokens are valid for **1 year**
and rotate on each use (the replacement is also good for a year). Store the refresh token
securely and persist the new one every time you refresh.

**Official SDKs.** HighLevel publishes JS/TS, Python and PHP SDKs that handle the OAuth 2.0
dance (token exchange, refresh, retry) for you. Prefer them over hand-rolled OAuth when
building an integration.

**Source:** `https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/docs/oauth/Authorization.md`
(verified 2026-08-03).

---

### API Keys (DEPRECATED)

API keys are no longer supported for new integrations. If you have old code using `Authorization: Bearer <API_KEY>`, migrate to Private Integration Token.

---

## Version Header

Always include this header. **Omitting it is a 401**, not a 400 (`"version header was not
found."`), and an unpublished value is also a 401 (`"version header is invalid"`) — both
PROVEN live 2026-08-03. The value to send is **per-app**, taken from the `Version` enum that
each app's OpenAPI spec publishes:

```
Version: 2021-07-28   ← pre-v3 DEFAULT — 32 of the 41 specs exclusively (33 accept it).
                        contacts, locations, opportunities, users, payments, campaigns,
                        phone-system, medias, invoices, products, workflows, blogs,
                        forms, funnels, objects, associations, social-media-posting,
                        marketplace, snapshots, proposals, brand-boards, ad-manager,
                        businesses, companies, courses, custom-fields, custom-menus,
                        emails, email-isv, surveys, affiliate-manager, oauth.

Version: 2021-04-15   ← ONLY these seven:
                        conversations, calendars, saas-api, voice-ai, agent-studio,
                        conversation-ai, knowledge-base.

Version: v3           ← the latest named version (released June 11, 2026).
Version: 2023-02-21   ← supported; documented for SaaS and POST /users/.
Version: legacy       ← supported (2021-01-01).

links   accepts BOTH 2021-04-15 and 2021-07-28.
store   declares no Version parameter at all.
```

**Do not blanket-apply either value.** Earlier revisions of this skill taught `2021-04-15`
globally; that was inverted.

**Live-probe finding (2026-08-03) — read before you repeat the old warning.** The header is
mandatory (omitted → `401 "version header was not found."`; unpublished value → `401
"version header is invalid"`), but established v2 paths accept **all four** published values
and return 200. The wrong value was therefore not producing 400s on contacts/users/calendars.
It still matters, because genuinely new v3 paths are generation-gated and hard-404 under a v2
Version. Details, per-surface table and evidence: **`references/api-generations.md`**.

### Version values you may see in fleet docs — and why most of them are FINE

**HighLevel runs FIVE concurrently-supported versions**, every one of them "Supported
until: **TBD**" with no retirement date published
(`https://marketplace.gohighlevel.com/docs/Versioning/`):

| Version | Released | Supported until |
|---|---|---|
| `v3` | **June 11, 2026** | TBD |
| `2023-02-21` | February 21, 2023 | TBD |
| `2021-07-28` | July 28, 2021 | TBD |
| `2021-04-15` | April 15, 2021 | TBD |
| `legacy` | January 1, 2021 | TBD |

So a doc using an older published version is **not automatically wrong**. Most endpoints are
documented under several versions, and all five are accepted.

| Value seen | Verdict |
|---|---|
| `2023-02-21` for SaaS | **CORRECT — do not change it.** HighLevel publishes a complete SaaS documentation set under `2023-02-21` (`https://marketplace.gohighlevel.com/docs/2023-02-21/ghl/saas/saas/index.html`). **PROVEN live 2026-08-03:** `GET /saas-api/public-api/agency-plans/{companyId}` returns 200 under it. The GitHub `saas-api.json` says `2021-04-15`, but that file was last synced **2025-08-13** — the stalest in the repo. |
| `2023-02-21` for `POST /users/` | **CORRECT — do not change it.** Documented verbatim at `https://marketplace.gohighlevel.com/docs/2023-02-21/ghl/users/create-user/index.html`. PROVEN live: `GET /users/` returns 200 under it. `2021-07-28` is *also* valid for the same endpoint. Both are fine. |
| `2021-04-15` for contacts/locations/users/payments/campaigns/phone-numbers | **Not an error, but standardise anyway.** `2021-04-15` is supported and HighLevel publishes a full Contacts surface under it. Those references now use `2021-07-28` because that is the current pre-v3 value in each app's spec — a consistency choice, **not** a bug fix. PROVEN live: all four versions return 200 on these endpoints. |
| `2021-04-15` stated as a blanket rule "on all calls" | **Genuinely wrong** — the value is per-operation. That is the defect this file fixes. |

> ⚠ **Standing warning: the GitHub spec repo lags the live docs.**
> `GoHighLevel/highlevel-api-docs` is a periodic dump — last repo commit **2026-06-19**, most
> `apps/*.json` synced **2026-05-01**, `saas-api.json` synced **2025-08-13** — while
> HighLevel's changelog runs to 2026-07-30. **Before declaring any fleet doc "wrong", check
> `https://marketplace.gohighlevel.com/docs` for that endpoint under that version.** Several
> earlier "corrections" against these skills turned out to be artifacts of that lag.

---

## The v3 version (released 2026-06-11)

**42 v3 app specs** live at
`https://github.com/GoHighLevel/highlevel-api-docs/tree/main/apps/v3`, on the same host
(`services.leadconnectorhq.com`). HighLevel's Versioning page gives the **release date as
June 11, 2026** (2026-06-19 is merely when the spec files were committed to GitHub).

> ⚠ **Not every v3 spec means `Version: v3`.** `ad-publishing-v3` has 95 operations of which
> **94 still declare `2021-07-28`**. The version is per-OPERATION. `phone-system-v3` names the
> parameter lowercase `version`; `store-v3` declares none.
>
> HighLevel publishes **no GA/beta/preview label** for v3 — do not write "v3 is GA" as a quote.

**This is forward-guidance, not a break.** Every pre-v3 path still works today, and **no
version has a published retirement date** — every one is "Supported until: TBD". There is no
deadline and no forced migration. Adopt v3 where it gives you capability you need.

**The two renames that will bite** — the core of the agency OAuth workflow. (HighLevel
published **no** migration guide for these; "removed without deprecation" is a changelog-diff
label, not a HighLevel policy statement.)

| Operation | v2 (still live) | v3 |
|---|---|---|
| Mint a location token | `POST /oauth/locationToken` | `POST /oauth/location-token` |
| List installed locations | `GET /oauth/installedLocations` | `GET /oauth/installed-locations` |

Other v3 changes worth knowing before you migrate:

- **OAuth token body goes camelCase** — `clientId`, `clientSecret`, `grantType`,
  `refreshToken`; the response field becomes `accessToken`. The `Version` header becomes
  **required** on the token call.
- **`GET /contacts/` is dropped from the v3 spec** — use `POST /contacts/search`.
  *(PROVEN 2026-08-03: it still returns 200 under `Version: v3` today. The spec removal has
  not been enforced at the runtime — do not rely on that lasting.)*
- **`GET /users/` is dropped from the v3 spec** — use `GET /users/search`.
  *(PROVEN 2026-08-03: also still returns 200 under `Version: v3`.)*
- `DELETE /contacts/{id}/campaigns/removeAll` → `.../campaigns/remove-all`.
- The `/emails/builder*` surface (5 ops) is **superseded** by
  `/emails/locations/{locationId}/campaigns/*` and `/emails/locations/{locationId}/templates/*`
  (18 ops). *(PROVEN 2026-08-03: `/emails/builder` still returns 200 under both
  `2021-07-28` and `v3`; build new work on the `locations/...` form regardless.)*
- Per-platform social OAuth paths collapse into generic `{platform}` paths.

**v3-only capability** (does not exist in v2 — requires `Version: v3`): chat-widget,
social planner scheduling queues + the comments API, brand voices, and the rebuilt
emails surface.

---

## All Scopes (142)

**Read this before ticking boxes on a PIT.** A wrong scope *name* fails exactly like a
missing one — 401/403 with an otherwise-valid token.

**There are three sources and they are DISJOINT. None is complete.**

| Source | Distinct scopes |
|---|---|
| Pre-v3 specs (`apps/*.json` `security` blocks) | **118** |
| v3 specs (`apps/v3/*.json`) | **127** |
| `docs/oauth/Scopes.md` | **91** |
| **True union — what a PIT can actually be granted** | **142** |

- **11 scopes exist ONLY in `Scopes.md`, in no spec at all:** `courses.write`,
  `funnels/funnel.readonly`, `funnels/page.readonly`, `funnels/pagecount.readonly`,
  `saas/location.read`, `saas/location.write`, `snapshots.readonly`,
  `socialplanner/account.write`, `socialplanner/csv.readonly`, `socialplanner/oauth.write`,
  `socialplanner/tag.readonly`
- **13 scopes are NEW in v3:** `chat-widget.readonly|write`, `emails/campaigns.readonly|write`,
  `emails/stats.readonly`, `emails/templates.readonly|write`, `lc-email.readonly`,
  `locations/write`, `saas/company.read|write`, `socialplanner/category.write`,
  `socialplanner/statistics.readonly`
- **4 scopes are DROPPED in v3:** `emails/builder.readonly|write`, `emails/schedule.readonly`,
  `socialplanner/oauth.readonly`
- `Scopes.md` has no rows at all for voice-ai, agent-studio, conversation-ai, knowledge-base,
  brand-boards, ad-publishing, phone-system, associations or custom-menus.
- Seven apps declare no scopes in their spec: courses, email-isv, knowledge-base, proposals,
  saas-api, snapshots, store.

> **`pipelines.create` is NOT an OAuth scope.** The 2026-06-15 changelog added it as an enum
> value in the `scopes` **response property** of the `/users/*` endpoints — a user-permission
> value in a response body. It appears in no `security` block anywhere. Do not put it on a PIT.

**Sources (verified 2026-08-03):** per-spec `security` blocks under
`https://github.com/GoHighLevel/highlevel-api-docs/tree/main/apps` and `.../apps/v3`, plus
`https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/docs/oauth/Scopes.md`

### Names that changed — old value → correct value

These nine families were wrong in earlier revisions of this file. If you have a PIT minted
against the old names, re-tick it:

| Was documented as | Actual scope name(s) |
|---|---|
| `blogs.readonly`, `blogs.write` | `blogs/list.readonly`, `blogs/posts.readonly`, `blogs/post.write`, `blogs/post-update.write`, `blogs/check-slug.readonly`, `blogs/author.readonly`, `blogs/category.readonly` |
| `social-media-posting.readonly|write` | the `socialplanner/*` family (see below) |
| `phone/number.readonly`, `phone/number.write` | `phonenumbers.read`, `phonenumbers.write`, `numberpools.read` |
| `custom-menus.readonly|write` | `custom-menu-link.readonly`, `custom-menu-link.write` |
| `marketplace.readonly|write` | `charges.readonly`, `charges.write`, `marketplace-installer-details.readonly`, `marketplace-external-auth-migration.write` |
| `voice-ai/agents.readonly|write` | `voice-ai-agents.readonly`, `voice-ai-agents.write` — hyphens, **not** a slash |
| `courses/readonly` | `courses.write` |
| `saas/location.readonly` | `saas/location.read` |
| `funnels/pageCount.readonly` | `funnels/pagecount.readonly` — lowercase `c` |

⚠ The `stores/*` scopes this file used to list (`stores/collection.*`, `stores/product.*`,
`stores/shipping.*`, `stores/order.*`, `stores/coupon.*`) are **unverified** — neither
`store.json` nor `Scopes.md` declares any store scope. They have been removed rather than
left to look authoritative. Store operations are reached via `products/*` scopes in
practice; confirm live before relying on a store-specific scope name.

Also removed: `marketing.readonly|write`, `proposals-and-estimates.*`, `blogs/author.write`,
`blogs/category.write`, `emails/schedule.write`, `funnels.readonly|write`,
`funnels/page.write`, `locations/tasks.write`, `locations/templates.write`,
`companies.write`, `saas/company.readonly`, `payments/orders` variants that do not exist —
none of these appear in either source.

### Contact Scopes
- `contacts.readonly` - Read contacts, search, get by ID
- `contacts.write` - Create, update, delete contacts; manage tags, tasks, notes

### Conversation Scopes
- `conversations.readonly` - Read conversations, search
- `conversations.write` - Create/update conversations
- `conversations/message.readonly` - Read messages
- `conversations/message.write` - Send messages, add inbound/outbound
- `conversations/livechat.write` - Live chat message actions

### Calendar Scopes
- `calendars.readonly` - Get calendars, free slots
- `calendars.write` - Create, update, delete calendars
- `calendars/events.readonly` - Get appointments, events, blocked slots
- `calendars/events.write` - Create/update appointments, block slots
- `calendars/groups.readonly` - Read calendar groups
- `calendars/groups.write` - Create/update/delete calendar groups
- `calendars/resources.readonly` - Read equipment/room resources
- `calendars/resources.write` - Manage equipment/room resources

### Opportunity Scopes
- `opportunities.readonly` - Search opportunities, get pipelines
- `opportunities.write` - Create, update, delete opportunities

### Location (Sub-Account) Scopes
- `locations.readonly` - Get location details, custom fields, tags
- `locations.write` - Update location settings
- `locations.internal-access-only` - Internal-access-only operations
- `locations/customFields.readonly`
- `locations/customFields.write`
- `locations/customValues.readonly`
- `locations/customValues.write`
- `locations/tags.readonly`
- `locations/tags.write`
- `locations/tasks.readonly`
- `locations/templates.readonly`

### User Scopes
- `users.readonly` - Get users, team members
- `users.write` - Create, update, delete users

### Business Scopes
- `businesses.readonly`
- `businesses.write`

### Company Scopes
- `companies.readonly`

### Invoice + Estimate Scopes
- `invoices.readonly`
- `invoices.write`
- `invoices/estimate.readonly`
- `invoices/estimate.write`
- `invoices/schedule.readonly`
- `invoices/schedule.write`
- `invoices/template.readonly`
- `invoices/template.write`

### Payment Scopes
- `payments/orders.readonly`
- `payments/orders.write`
- `payments/orders.collectPayment` - Collect payment on an order
- `payments/transactions.readonly`
- `payments/subscriptions.readonly`
- `payments/coupons.readonly`
- `payments/coupons.write`
- `payments/integration.readonly`
- `payments/integration.write`
- `payments/custom-provider.readonly`
- `payments/custom-provider.write`

### Product Scopes
- `products.readonly`
- `products.write`
- `products/prices.readonly`
- `products/prices.write`
- `products/collection.readonly`
- `products/collection.write`

### Blog Scopes
- `blogs/list.readonly` - List blog sites
- `blogs/posts.readonly` - Read blog posts
- `blogs/post.write` - Create a blog post
- `blogs/post-update.write` - Update a blog post
- `blogs/check-slug.readonly` - Slug availability check
- `blogs/author.readonly`
- `blogs/category.readonly`

### Email Scopes
- `emails/builder.readonly`
- `emails/builder.write`
- `emails/schedule.readonly`

### Social Planner Scopes
> The API family is named `socialplanner`, NOT `social-media-posting`.
- `socialplanner/account.readonly`
- `socialplanner/account.write`
- `socialplanner/post.readonly`
- `socialplanner/post.write`
- `socialplanner/category.readonly`
- `socialplanner/tag.readonly`
- `socialplanner/csv.readonly`
- `socialplanner/csv.write`
- `socialplanner/oauth.readonly`
- `socialplanner/oauth.write`

### Ad Publishing Scopes
- `adPublishing.readonly` - Read campaigns, adsets, ads, reporting (Facebook/Google/LinkedIn)
- `adPublishing.write` - Create/update/publish/pause ads and campaigns

### AI Scopes
- `agent-studio.readonly` - Read AI Agent Studio agents
- `agent-studio.write` - Create/update/publish/execute/delete agents
- `conversation-ai.readonly` - Read Conversation AI agents + actions
- `conversation-ai.write` - Manage Conversation AI agents, actions, follow-up settings
- `voice-ai-agents.readonly`
- `voice-ai-agents.write`
- `voice-ai-agent-goals.readonly`
- `voice-ai-agent-goals.write`
- `voice-ai-dashboard.readonly` - Voice AI call logs and transcripts

### Brand Board Scopes
- `brand-boards/design-kit.readonly`
- `brand-boards/design-kit.write`

### Forms Scopes
- `forms.readonly`
- `forms.write`

### Funnel Scopes
- `funnels/funnel.readonly`
- `funnels/page.readonly`
- `funnels/pagecount.readonly`
- `funnels/redirect.readonly`
- `funnels/redirect.write`

### Workflow Scopes
- `workflows.readonly` - Read only. There is no workflow write scope because there is no
  workflow write endpoint (see `references/campaigns.md`).

### Campaign Scopes
- `campaigns.readonly`

### Survey Scopes
- `surveys.readonly`

### Course Scopes
- `courses.write`

### Media Scopes
- `medias.readonly`
- `medias.write`

### Link Scopes
- `links.readonly`
- `links.write`

### Snapshot Scopes
- `snapshots.readonly`

### Object Scopes
- `objects/record.readonly`
- `objects/record.write`
- `objects/schema.readonly`
- `objects/schema.write`

### Association Scopes
- `associations.readonly`
- `associations.write`
- `associations/relation.readonly`
- `associations/relation.write`

### Custom Menu Scopes
- `custom-menu-link.readonly`
- `custom-menu-link.write`

### Custom Field Scopes
> Custom fields use the `locations/customFields.*` scopes listed under Location Scopes.

### Phone System Scopes
- `phonenumbers.read`
- `phonenumbers.write`
- `numberpools.read`

### SaaS Scopes
- `saas/location.read`
- `saas/location.write`
- `saas/company.write`

### OAuth / Marketplace Scopes
- `oauth.readonly`
- `oauth.write`
- `charges.readonly` - Marketplace billing charges
- `charges.write`
- `marketplace-installer-details.readonly`
- `marketplace-external-auth-migration.write`

### Affiliate Manager Scopes
- `affiliate-manager.readonly`

### v3-only Scopes (require `Version: v3` surfaces)
- `chat-widget.readonly`
- `chat-widget.write`
- `emails/campaigns.readonly`
- `emails/campaigns.write`
- `emails/stats.readonly`
- `emails/templates.readonly`
- `emails/templates.write`
- `lc-email.readonly`
- `locations/write`
- `saas/company.read`
- `saas/company.write`
- `socialplanner/category.write`
- `socialplanner/statistics.readonly`

---

## Scope Rules

1. Read-only scopes (`*.readonly`) allow GET requests only
2. Write scopes (`*.write`) allow POST, PUT, PATCH, DELETE
3. Some write scopes implicitly include read access - check each endpoint in the master reference
4. If a call returns 401 despite a valid token, you are missing the required scope
5. Add scopes by editing the integration in GHL - you do NOT need to regenerate the token
