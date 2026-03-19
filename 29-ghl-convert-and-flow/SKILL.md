# GHL API Skill - GoHighLevel / Convert and Flow API v2

> **TYP Note:** This skill pack replaces direct use of the 430K master reference.
> NEVER paste the master reference into context or core files.
> ALWAYS read the appropriate `references/*.md` file at query time.

---

## What Is This Skill?

GoHighLevel (GHL) - also branded as **Convert and Flow** for white-label deployments - is an all-in-one CRM, marketing automation, and sales platform. The GHL API v2 gives programmatic access to contacts, conversations, pipelines, calendars, payments, users, and more.

This skill pack provides:
- Domain-specific reference files carved from the 413-endpoint master reference
- Workflow instructions for building and executing GHL API calls efficiently
- Environment setup guide with smoke tests
- Real-world examples for common GHL tasks

**Master reference (do NOT load into context):**
`$HOME/Downloads/openclaw-master-files/Convert and Flow - GoHighLevel API v2 Master Reference.md`

---

## Quick Reference

| Item | Value |
|------|-------|
| Base URL | `https://services.leadconnectorhq.com` |
| Auth method | Bearer token (Private Integration Token) |
| Auth header | `Authorization: Bearer <GHL_API_KEY>` |
| Version header | `Version: 2021-04-15` (required on most calls) |
| Content-Type | `application/json` |
| Total endpoints | 413 across 35 modules |
| API key type | Private Integration Token (OAuth2 Bearer) |
| Deprecated | API keys are deprecated - use Private Integration Tokens only |

### Rate Limits

GHL enforces per-location rate limits. General guidance from the master reference:
- Respect 429 responses and back off with exponential retry
- Batch contact imports instead of looping single creates
- Read-heavy operations (GET) have higher limits than writes

### Required Headers (every call)

```
Authorization: Bearer <GHL_API_KEY>
Version: 2021-04-15
Content-Type: application/json
```

---

## Trigger Map - Which File to Read

When a user asks a GHL question, identify the domain and read the matching reference file.
**Never guess at endpoint syntax. Always read the reference file first.**

| User Question Domain | Read This File |
|---------------------|---------------|
| Contacts - create, search, update, delete, tags, DND, tasks, notes | `references/contacts.md` |
| Conversations - list, read, create | `references/conversations.md` |
| Messages - send SMS, email, IG, FB, reply to thread | `references/conversations.md` |
| Opportunities - pipeline stages, create, update, close | `references/opportunities.md` |
| Calendars - create calendar, manage availability | `references/calendars.md` |
| Appointments - book, reschedule, cancel, get slots | `references/calendars.md` |
| Campaigns - campaign triggers | `references/campaigns.md` |
| Workflows - automation, workflow list | `references/campaigns.md` |
| Locations - sub-account info, tags, custom fields | `references/locations.md` |
| Payments - orders, transactions, payment integrations | `references/payments.md` |
| Invoices - create invoice, send, mark paid, void | `references/payments.md` |
| Subscriptions - create, cancel, manage | `references/payments.md` |
| Phone numbers - search, purchase, configure | `references/phone-numbers.md` |
| Users - add user, update role, permissions | `references/users.md` |
| Webhooks - event types, payload structure, setup | `references/webhooks.md` |

---

## Gemini Engine-First Workflow

This skill uses a **read-first, no-memorize** approach to keep context lean.

### The 4-Step Pattern

```
Step 1 - Identify domain from user question
         ("add a contact" -> contacts domain)

Step 2 - Read the reference file (NOT the 430K master)
         read references/contacts.md

Step 3 - Find the exact endpoint, params, and cURL template

Step 4 - Build and execute the API call with real values
```

### What NOT to Do

- Do NOT open or read the 430K master reference file unless the domain file is missing an endpoint
- Do NOT copy endpoint docs into AGENTS.md, TOOLS.md, MEMORY.md, or any core file
- Do NOT memorize endpoint syntax - read it fresh from the reference file each time
- Do NOT invent parameters - use only what is documented in the reference file

---

## Skill File Map

```
29-ghl-api/
  SKILL.md              - This file. Overview, trigger map, quick ref.
  INSTALL.md            - Env var setup, TYP read order, smoke test.
  INSTRUCTIONS.md       - Step-by-step usage workflows.
  EXAMPLES.md           - Real-world GHL examples with full cURL.
  CORE_UPDATES.md       - Exact text to add to TOOLS.md and MEMORY.md only.
  references/
    contacts.md         - 32 endpoints for contact management
    conversations.md    - 48 endpoints for conversations and messages
    opportunities.md    - Opportunities and pipeline endpoints
    calendars.md        - 34 endpoints for calendars and appointments
    campaigns.md        - Campaign triggers + workflows
    locations.md        - 29 endpoints for location/sub-account management
    payments.md         - 65 combined endpoints: invoices + payments
    phone-numbers.md    - Phone number search, buy, configure
    users.md            - User CRUD and permissions
    webhooks.md         - Webhook events, payload structure, setup guide
```

---

## Safety Rules for This Skill

1. **Phone number removal is TREVOR-ONLY.** Read phone data freely, but never release or remove numbers autonomously. Flag to Trevor.
2. **Billing/payment actions are TREVOR-ONLY.** Do not charge cards, cancel subscriptions, or void invoices without explicit instruction.
3. **Never expose GHL_API_KEY in logs, messages, or documents.** Treat it like a password.
4. **Test in staging first.** GHL does not have a sandbox - destructive actions (delete contact, void invoice) are irreversible.

---

## Module Stats (from master reference)

| Module | Endpoint Count |
|--------|---------------|
| invoices | 41 |
| social-media-posting | 40 |
| calendars | 34 |
| contacts | 32 |
| locations | 29 |
| products | 27 |
| payments | 24 |
| saas-api | 22 |
| opportunities | (see references/opportunities.md) |
| conversations | (see references/conversations.md) |
| workflows | (see references/campaigns.md) |
| users | (see references/users.md) |
| phone-system | (see references/phone-numbers.md) |

Total: 413 endpoints, 35 modules, 106 unique permission scopes.
