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
- Authorization URL: `https://marketplace.gohighlevel.com/oauth/chooselocation`
- Token URL: `https://services.leadconnectorhq.com/oauth/token`
- Scopes must be declared in your app's marketplace listing

**Refresh:** OAuth tokens expire and must be refreshed. Store the refresh token securely.

---

### API Keys (DEPRECATED)

API keys are no longer supported for new integrations. If you have old code using `Authorization: Bearer <API_KEY>`, migrate to Private Integration Token.

---

## Version Header

Most endpoints require the version header:
```
Version: 2021-04-15
```

Always include this header. Missing it causes 400 errors on many endpoints.

Media Library upload (`references/medias.md`) uses `Version: 2021-07-28`. Confirm the exact Version per-endpoint against the reference file; do not blanket-change it.

---

## All 106 Scopes

### Contact Scopes
- `contacts.readonly` - Read contacts, search, get by ID
- `contacts.write` - Create, update, delete contacts; manage tags, tasks, notes

### Conversation Scopes
- `conversations.readonly` - Read conversations, search
- `conversations.write` - Create/update conversations
- `conversations/message.readonly` - Read messages
- `conversations/message.write` - Send messages, add inbound/outbound

### Calendar Scopes
- `calendars.readonly` - Get calendars, free slots
- `calendars.write` - Create, update, delete calendars
- `calendars/events.readonly` - Get appointments, events, blocked slots
- `calendars/events.write` - Create/update appointments, block slots

### Opportunity Scopes
- `opportunities.readonly` - Search opportunities, get pipelines
- `opportunities.write` - Create, update, delete opportunities

### Location Scopes
- `locations.readonly` - Get location details, custom fields, tags
- `locations.write` - Update location settings
- `locations/customFields.readonly`
- `locations/customFields.write`
- `locations/customValues.readonly`
- `locations/customValues.write`
- `locations/tags.readonly`
- `locations/tags.write`
- `locations/templates.readonly`
- `locations/templates.write`
- `locations/tasks.readonly`
- `locations/tasks.write`

### User Scopes
- `users.readonly` - Get users, team members
- `users.write` - Create, update, delete users

### Business Scopes
- `businesses.readonly`
- `businesses.write`

### Invoice Scopes
- `invoices.readonly`
- `invoices.write`

### Payment Scopes
- `payments/orders.readonly`
- `payments/orders.write`
- `payments/transactions.readonly`
- `payments/subscriptions.readonly`
- `payments/custom-provider.readonly`
- `payments/custom-provider.write`

### Product Scopes
- `products.readonly`
- `products.write`
- `products/prices.readonly`
- `products/prices.write`

### Blog Scopes
- `blogs.readonly`
- `blogs.write`
- `blogs/author.readonly`
- `blogs/author.write`
- `blogs/category.readonly`
- `blogs/category.write`

### Email/Marketing Scopes
- `emails/schedule.readonly`
- `emails/schedule.write`
- `marketing.readonly`
- `marketing.write`

### Social Media Scopes
- `social-media-posting.readonly`
- `social-media-posting.write`

### Forms Scopes
- `forms.readonly`
- `forms.write`

### Funnel Scopes
- `funnels.readonly`
- `funnels.write`
- `funnels/page.readonly`
- `funnels/page.write`
- `funnels/pageCount.readonly`

### Workflow Scopes
- `workflows.readonly`

### Campaign Scopes
- `campaigns.readonly`

### Survey Scopes
- `surveys.readonly`

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
- `custom-menus.readonly`
- `custom-menus.write`

### Store Scopes
- `stores/collection.readonly`
- `stores/collection.write`
- `stores/product.readonly`
- `stores/product.write`
- `stores/shipping.readonly`
- `stores/shipping.write`
- `stores/order.readonly`
- `stores/order.write`
- `stores/coupon.readonly`
- `stores/coupon.write`

### Company Scopes
- `companies.readonly`
- `companies.write`

### Phone System Scopes
- `phone/number.readonly`
- `phone/number.write`

### SaaS Scopes
- `saas/company.readonly`
- `saas/company.write`
- `saas/location.readonly`
- `saas/location.write`

### OAuth/Marketplace Scopes
- `oauth.readonly`
- `oauth.write`
- `marketplace.readonly`
- `marketplace.write`

### Voice AI Scopes
- `voice-ai/agents.readonly`
- `voice-ai/agents.write`

### Course Scopes
- `courses/readonly`

### Proposal Scopes
- `proposals-and-estimates.readonly`
- `proposals-and-estimates.write`

---

## Scope Rules

1. Read-only scopes (`*.readonly`) allow GET requests only
2. Write scopes (`*.write`) allow POST, PUT, PATCH, DELETE
3. Some write scopes implicitly include read access - check each endpoint in the master reference
4. If a call returns 401 despite a valid token, you are missing the required scope
5. Add scopes by editing the integration in GHL - you do NOT need to regenerate the token
