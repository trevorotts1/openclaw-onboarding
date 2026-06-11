# modules.md - All 35 GHL Modules Overview

Base URL for all endpoints: `https://services.leadconnectorhq.com`

For full endpoint details, open:
`~/Downloads/openclaw-master-files/Convert and Flow - GoHighLevel API v2 Master Reference.md`

---

## High-Priority Modules (Most Used)

### contacts (32 endpoints)
Create, read, update, delete contacts. Add/remove tags. Manage tasks and notes. Add contacts to campaigns and workflows.

**Top endpoints:**
- `POST /contacts/search` - Search contacts with filters (preferred over deprecated GET /contacts/)
- `POST /contacts/` - Create contact
- `GET /contacts/{contactId}` - Get contact by ID
- `PUT /contacts/{contactId}` - Update contact
- `POST /contacts/{contactId}/tags` - Add tags
- `DELETE /contacts/{contactId}/tags` - Remove tags
- `POST /contacts/{contactId}/workflow/{workflowId}` - Add to workflow

**Scopes:** `contacts.readonly`, `contacts.write`
**Full detail:** `references/contacts.md`

---

### conversations (19 endpoints)
Search and manage conversations. Send SMS, email, WhatsApp, and other message types. Get message history.

**Top endpoints:**
- `GET /conversations/search` - Search conversations by locationId
- `POST /conversations/messages` - Send outbound message
- `GET /conversations/{conversationId}` - Get conversation by ID
- `GET /conversations/{conversationId}/messages` - Get message history
- `POST /conversations/messages/inbound` - Add inbound message record

**Scopes:** `conversations.readonly`, `conversations.write`, `conversations/message.readonly`, `conversations/message.write`
**Full detail:** `references/conversations.md`

---

### calendars (34 endpoints)
Manage calendars and appointments. Get free slots. Create/update bookings. Manage blocked times.

**Top endpoints:**
- `GET /calendars/` - Get all calendars for a location
- `GET /calendars/{calendarId}/free-slots` - Get available time slots
- `POST /calendars/events/appointments` - Create appointment
- `GET /calendars/events/appointments/{eventId}` - Get appointment
- `PUT /calendars/events/appointments/{eventId}` - Update appointment
- `GET /calendars/events` - Get all calendar events for date range

**Scopes:** `calendars.readonly`, `calendars.write`, `calendars/events.readonly`, `calendars/events.write`
**Full detail:** `references/calendars.md`

---

### locations (29 endpoints)
Sub-account configuration. Custom fields. Tags. Users. Pipeline settings.

**Top endpoints:**
- `GET /locations/{locationId}` - Get location details
- `PUT /locations/{locationId}` - Update location
- `GET /locations/search` - Search/list all locations
- `GET /locations/{locationId}/customFields` - Get custom fields
- `POST /locations/{locationId}/customFields` - Create custom field
- `GET /locations/{locationId}/tags` - Get tags for location

**Scopes:** `locations.readonly`, `locations.write`, `locations/customFields.readonly`, `locations/customFields.write`
**Full detail:** `references/locations.md`

---

### opportunities (10 endpoints)
Pipeline and deal management. Create, update, search, and delete opportunities.

**Top endpoints:**
- `GET /opportunities/search` - Search opportunities (supports filtering by pipeline, stage, status)
- `GET /opportunities/pipelines` - Get all pipelines for a location
- `POST /opportunities/` - Create opportunity
- `PUT /opportunities/{id}` - Update opportunity
- `GET /opportunities/{id}` - Get opportunity by ID

**Scopes:** `opportunities.readonly`, `opportunities.write`
**Full detail:** `references/opportunities.md`

---

## Secondary Modules

### invoices (41 endpoints)
Create, send, and manage invoices. Handle invoice items, schedules, and payment links.

**Key endpoints:** `GET /invoices/`, `POST /invoices/`, `POST /invoices/{invoiceId}/send`
**Scopes:** `invoices.readonly`, `invoices.write`

---

### social-media-posting (40 endpoints)
Schedule and publish posts to social media platforms. Manage accounts and post history.

**Key endpoints:** `GET /social-media-posting/`, `POST /social-media-posting/`
**Scopes:** `social-media-posting.readonly`, `social-media-posting.write`

---

### products (27 endpoints)
Manage products and prices. Supports physical, digital, and service products.

**Scopes:** `products.readonly`, `products.write`, `products/prices.readonly`, `products/prices.write`

---

### payments (24 endpoints)
Orders, transactions, subscriptions, and custom payment providers.

**Scopes:** `payments/orders.readonly`, `payments/orders.write`, `payments/transactions.readonly`

---

### saas-api (22 endpoints)
SaaS reseller operations. Manage sub-accounts at scale.

**Scopes:** `saas/company.readonly`, `saas/company.write`, `saas/location.readonly`, `saas/location.write`

---

### store (18 endpoints)
E-commerce store management. Products, collections, orders, shipping, coupons.

**Scopes:** `stores/product.readonly`, `stores/product.write`, `stores/order.readonly`, `stores/order.write`

---

### voice-ai (11 endpoints)
AI voice agent configuration and management.

**Scopes:** `voice-ai/agents.readonly`, `voice-ai/agents.write`

---

### associations (10 endpoints)
Manage associations between objects (relationships between contacts, deals, etc.).

**Scopes:** `associations.readonly`, `associations.write`

---

### objects (9 endpoints)
Custom object schema and record management.

**Scopes:** `objects/schema.readonly`, `objects/schema.write`, `objects/record.readonly`, `objects/record.write`

---

### custom-fields (8 endpoints)
Create and manage custom fields for contacts, opportunities, and other objects.

**Scopes:** `locations/customFields.readonly`, `locations/customFields.write`

---

### blogs (7 endpoints)
Blog post management. Authors and categories.

**Scopes:** `blogs.readonly`, `blogs.write`

---

### funnels (7 endpoints)
Funnel and page management.

**Scopes:** `funnels.readonly`, `funnels.write`

---

### marketplace (7 endpoints)
Marketplace app management.

**Scopes:** `marketplace.readonly`, `marketplace.write`

---

### medias (7 endpoints)
Media library management. Upload and retrieve media files.

**Key endpoint:** `POST /medias/upload-file` (multipart). **Deep reference:** `references/medias.md` (carved from the proven skill 28/35/37 implementations — endpoint, multipart fields, `parentId` folder caveat, CDN URL formats, retry pattern). This is the Tier-3 media path the router uses; the CLI has NO media commands so media NEVER routes to Tier 0.

**Scopes:** `medias.readonly`, `medias.write`

---

### users (7 endpoints)
User/team member management within a location.

**Scopes:** `users.readonly`, `users.write`

---

### links (6 endpoints)
URL redirect links management.

**Scopes:** `links.readonly`, `links.write`

---

### businesses (5 endpoints)
Business profile management.

**Scopes:** `businesses.readonly`, `businesses.write`

---

### custom-menus (5 endpoints)
Custom navigation menu management.

**Scopes:** `custom-menus.readonly`, `custom-menus.write`

---

### emails (5 endpoints)
Email template and schedule management.

**Scopes:** `emails/schedule.readonly`, `emails/schedule.write`

---

### proposals (4 endpoints)
Proposals and estimates management.

**Scopes:** `proposals-and-estimates.readonly`, `proposals-and-estimates.write`

---

### snapshots (4 endpoints)
Account snapshot management.

**Scopes:** `snapshots.readonly`

---

### forms (3 endpoints)
Form management and submission data.

**Scopes:** `forms.readonly`

---

### oauth (3 endpoints)
OAuth token management.

**Scopes:** `oauth.readonly`, `oauth.write`

---

### phone-system (2 endpoints)
Phone number management.

**Scopes:** `phone/number.readonly`, `phone/number.write`

---

### surveys (2 endpoints)
Survey data retrieval.

**Scopes:** `surveys.readonly`

---

### campaigns (1 endpoint)
Campaign retrieval.

**Scopes:** `campaigns.readonly`

---

### companies (1 endpoint)
Company-level management.

**Scopes:** `companies.readonly`, `companies.write`

---

### courses (1 endpoint)
Course management.

**Scopes:** `courses/readonly`

---

### email-isv (1 endpoint)
Email ISV (Independent Software Vendor) integration.

---

### workflows (1 endpoint)
Workflow retrieval.

**Scopes:** `workflows.readonly`
