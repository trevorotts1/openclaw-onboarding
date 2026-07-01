---
name: ghl-convert-and-flow
description: Domain-specific reference files for the GoHighLevel (Convert and Flow) API v2 — Tier 3 direct REST API access covering contacts, conversations, pipelines, calendars, payments, and more. Use after Tier 0 (Convert and Flow CLI, skill 44) and the Tier 1/2 MCPs per skill 36's 6-tier escalation rules.
---

> **GHL PIT aliases:** `GOHIGHLEVEL_API_KEY` is the preferred name; 10 additional aliases resolve the same LOCATION PIT. See **`TERMINOLOGY.md`** (repo root) for the canonical alias set and backend-equivalence notes (Convert & Flow / leadconnectorhq.com = one platform).

# GHL API Skill - GoHighLevel / Convert and Flow API v2

> **TYP Note:** This skill pack replaces direct use of the 430K master reference.
> NEVER paste the master reference into context or core files.
> ALWAYS read the appropriate `references/*.md` file at query time.

> **Tier in the access chain (introduced by skill 36):** This skill is **Tier 3** — direct REST API. The agent must try **Tier 0 (Convert and Flow CLI, skill 44)** FIRST for every operation the CLI covers, then **Tier 1 (Official MCP, `ghl-mcp`, 36 tools)** for blogs/CLI gaps, then **Tier 2 (Community MCP, `ghl-community-mcp`, 588 tools, on-demand via curl)** before falling here. Use this skill's `references/[module].md` files only when no higher tier covers the call (and for media uploads — see `references/medias.md`). See skill 36 (`36-ghl-mcp-setup`) for the full 6-tier escalation rules.

---

## What Is This Skill?

**GHL = Convert & Flow = Go High Level** — one white-label platform. The default app URL is `app.convertandflow.com`; the underlying API backend is `services.leadconnectorhq.com`. The "API key" IS the Private Integration Token (`pit-` prefix) — there are no separate legacy API keys; that term is retired. The GHL API v2 gives programmatic access to contacts, conversations, pipelines, calendars, payments, users, and more.

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
| Auth header | `Authorization: Bearer $GOHIGHLEVEL_API_KEY` |
| Version header | `Version: 2021-04-15` (required on most calls) |
| Content-Type | `application/json` |
| Total endpoints | 413 across 35 modules |
| API key | IS the Private Integration Token (`pit-` prefix); no separate "API key" type exists |

### Rate Limits

GHL enforces per-location rate limits. General guidance from the master reference:
- Respect 429 responses and back off with exponential retry
- Batch contact imports instead of looping single creates
- Read-heavy operations (GET) have higher limits than writes

### Required Headers (every call)

```
Authorization: Bearer $GOHIGHLEVEL_API_KEY
Version: 2021-04-15
Content-Type: application/json
```

---

## Credentials (canonical names + resolver)

This skill reads the **location** Private Integration Token (the "API key" IS the PIT, `pit-` prefix). The unified **11-alias GHL LOCATION-PIT resolver** below maps the canonical name plus 10 legacy aliases to a single value — agency PITs and the Firebase-refresh path are separate and not included in this set. Canonical env-var names (matching `~/.openclaw/secrets/.env`, `PREREQS.json`, and the bundled QC script):

| Variable | Purpose |
|----------|---------|
| `GOHIGHLEVEL_API_KEY` | Location-scoped Private Integration Token (starts with `pit-`) |
| `GOHIGHLEVEL_LOCATION_ID` | Sub-account (location) ID |

Every runnable example uses `$GOHIGHLEVEL_API_KEY` / `$GOHIGHLEVEL_LOCATION_ID`. Load them —
and **fail loud rather than fire an empty `Authorization: Bearer `** — with this single
resolver. It accepts legacy aliases so older setups keep working:

```bash
# Canonical GHL credential resolver — source secrets, map legacy aliases, fail loud.
[ -f ~/.openclaw/secrets/.env ] && { set -a; . ~/.openclaw/secrets/.env; set +a; }   # VPS/container: vars already in env
: "${GOHIGHLEVEL_API_KEY:=${GHL_API_KEY:-${GHL_PIT:-${GHL_TOKEN:-${GHL_PRIVATE_INTEGRATION_TOKEN:-${PRIVATE_INTEGRATION_TOKEN:-${GHL_PRIVATE_TOKEN:-${PIT_TOKEN:-${GHL_PIT_TOKEN:-${GOHIGHLEVEL_LOCATION_PIT:-${GHL_LOCATION_PIT:-}}}}}}}}}}}}"
: "${GOHIGHLEVEL_LOCATION_ID:=${GHL_LOCATION_ID:-}}"
__miss=""
[ -z "${GOHIGHLEVEL_API_KEY:-}" ]     && __miss="$__miss GOHIGHLEVEL_API_KEY"
[ -z "${GOHIGHLEVEL_LOCATION_ID:-}" ] && __miss="$__miss GOHIGHLEVEL_LOCATION_ID"
if [ -n "$__miss" ]; then
  echo "BLOCKED — GHL credential(s) not resolved:$__miss" >&2
  echo "  Add to ~/.openclaw/secrets/.env (chmod 600):" >&2
  echo "    GOHIGHLEVEL_API_KEY=pit-...          # LOCATION-scoped PIT (an agency PIT 401s on media)" >&2
  echo "    GOHIGHLEVEL_LOCATION_ID=<location id>" >&2
  echo "  Mint a LOCATION PIT: GHL Settings > Integrations > Private Integrations." >&2
  return 1 2>/dev/null || exit 1
fi
```

Never print the token value — names only. Media uploads require a **location** PIT and use
`Version: 2021-07-28` (see `references/medias.md`); all other endpoints default to
`Version: 2021-04-15`. Confirm the Version header per-endpoint; do not blanket-change it.

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
    medias.md           - Media Library upload (Tier-3 only; LOCATION PIT, Version 2021-07-28)
```

---

## Safety Rules for This Skill

1. **Phone number removal is TREVOR-ONLY.** Read phone data freely, but never release or remove numbers autonomously. Flag to Trevor.
2. **Billing/payment actions are TREVOR-ONLY.** Do not charge cards, cancel subscriptions, or void invoices without explicit instruction.
3. **Never expose `GOHIGHLEVEL_API_KEY` in logs, messages, or documents.** Treat it like a password.
4. **Test in staging first.** GHL does not have a sandbox - destructive actions (delete contact, void invoice) are irreversible.

---

## Caller Contract: Command Center + Verify-in-UI

Skill 29 is a **library**. It owns no Command Center (Skill 32) board and no coaching
persona — do not bolt either into it. Caller skills (for example 35/37/47/48) are
responsible for writing task/progress state to the Skill 32 Command Center Kanban.

After any **write**, surface a one-line "verify in Convert and Flow UI" pointer so the
client can confirm the result behind us:

| Write | Verify in the Convert and Flow UI |
|-------|-----------------------------------|
| Contact create/update | Contacts → the record shows the tags/notes/tasks |
| SMS / email send | that contact's Conversation thread |
| Opportunity create/move | the pipeline board at the right stage |
| Invoice create/send | Payments → Invoices (the client receives it) |
| Media upload | Media Library; the returned `url` opens WITHOUT a login |

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
