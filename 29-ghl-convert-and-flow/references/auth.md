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
Version: 2021-07-28   ← DEFAULT — 33 of the 41 published v2 app specs.
                        contacts, locations, opportunities, users, payments, campaigns,
                        phone-system, medias, invoices, products, workflows, blogs,
                        forms, funnels, objects, associations, social-media-posting,
                        marketplace, snapshots, proposals, brand-boards, ad-manager,
                        businesses, companies, courses, custom-fields, custom-menus,
                        emails, email-isv, surveys, affiliate-manager, oauth.

Version: 2021-04-15   ← ONLY these seven:
                        conversations, calendars, saas-api, voice-ai, agent-studio,
                        conversation-ai, knowledge-base.

Version: v3           ← the v3 generation (see below).

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

### Known-wrong Version values still circulating in older fleet docs

If you find any of these, they are wrong — this table is the authority:

| Seen in older docs | Correct value | Why |
|---|---|---|
| `2023-02-21` for SaaS endpoints | `2021-04-15` | `saas-api.json` publishes exactly one enum for all 22 SaaS ops: `2021-04-15`; `2023-02-21` appears nowhere in that spec. **PROVEN 2026-08-03: `GET /saas-api/public-api/agency-plans/{companyId}` returns 200 under `2023-02-21`**, so the old value does still work — it is simply not the documented one. Prefer `2021-04-15`; do not treat existing `2023-02-21` SaaS code as broken. |
| `2023-02-21` for `POST /users/` | `2021-07-28` | `users.json` declares `2021-07-28` for all 7 user operations. |
| `2021-04-15` for payments | `2021-07-28` | `payments.json` declares `2021-07-28`. |
| `2021-04-15` "on all calls" | per-app, see above | Inverted global rule. |

---

## The v3 generation (published 2026-06-19)

A second API generation exists. **42 v3 app specs** live at
`https://github.com/GoHighLevel/highlevel-api-docs/tree/main/apps/v3`, all declaring the
literal header value `Version: v3`, on the same host (`services.leadconnectorhq.com`).

**This is forward-guidance, not a break.** Every v2 path below still works today under
`Version: 2021-07-28`. Nothing in this skill needs to change to keep working. Plan the
migration; do not scramble.

**The two renames that will bite** — HighLevel lists both as *removed without deprecation*
in v3, and they are the core of the agency OAuth workflow:

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

## All Scopes (130)

**Read this before ticking boxes on a PIT.** A wrong scope *name* fails exactly like a
missing one — 401/403 with an otherwise-valid token — so the names below are taken
verbatim from the source, not paraphrased.

- **118** distinct scopes are declared in the `security` blocks of the published app specs.
- **130** is the union of those with `docs/oauth/Scopes.md`.
- The two sources disagree; where they do, **the spec files are more current**.
  `docs/oauth/Scopes.md` has no rows at all for voice-ai, agent-studio, conversation-ai,
  knowledge-base, brand-boards, ad-publishing, phone-system, associations or custom-menus.
- Seven apps declare **no** scopes in their spec: courses, email-isv, knowledge-base,
  proposals, saas-api, snapshots, store. Where `Scopes.md` covers them (courses, saas,
  snapshots) its names are used below; knowledge-base, proposals, store and email-isv have
  no published scope names in either source.

**Sources (verified 2026-08-03):** per-spec `security` blocks under
`https://github.com/GoHighLevel/highlevel-api-docs/tree/main/apps`, plus
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

---

## Scope Rules

1. Read-only scopes (`*.readonly`) allow GET requests only
2. Write scopes (`*.write`) allow POST, PUT, PATCH, DELETE
3. Some write scopes implicitly include read access - check each endpoint in the master reference
4. If a call returns 401 despite a valid token, you are missing the required scope
5. Add scopes by editing the integration in GHL - you do NOT need to regenerate the token
