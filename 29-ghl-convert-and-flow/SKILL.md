---
name: ghl-convert-and-flow
description: Domain-specific reference files for the GoHighLevel (Convert and Flow) API v2 — Tier 3 direct REST API access covering contacts, conversations, pipelines, calendars, payments, and more. Use after Tier 0 (Convert and Flow CLI, skill 44) and the Tier 1/2 MCPs per skill 36's 6-tier escalation rules.
---

> **GHL PIT aliases:** `GOHIGHLEVEL_API_KEY` is the preferred name; 10 additional aliases resolve the same LOCATION PIT. See **`TERMINOLOGY.md`** (repo root) for the canonical alias set and backend-equivalence notes (Convert & Flow / leadconnectorhq.com = one platform).

# GHL API Skill - GoHighLevel / Convert and Flow API v2

> **TYP Note:** This skill pack replaces direct use of the 430K master reference.
> NEVER paste the master reference into context or core files.
> ALWAYS read the appropriate `references/*.md` file at query time.

> **Tier in the access chain (introduced by skill 36):** This skill is **Tier 3** — direct REST API. The agent must try **Tier 0 (Convert and Flow CLI, skill 44)** FIRST for every operation the CLI covers, then **Tier 1 (Official MCP, `ghl-mcp`)** for blogs/CLI gaps, then **Tier 2 (Community MCP, `ghl-community-mcp`, 588 tools, on-demand via curl)** before falling here. Use this skill's `references/[module].md` files only when no higher tier covers the call (and for media uploads — see `references/medias.md`). See skill 36 (`36-ghl-mcp-setup`) for the full 6-tier escalation rules.

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
| Version header | Per-operation. `2021-07-28` pre-v3 default; `v3` is latest; five versions supported — see "Version Header Rule" |
| Content-Type | `application/json` |
| Total endpoints | 576 across 41 published app specs (v2 generation) |
| API key | IS the Private Integration Token (`pit-` prefix); no separate "API key" type exists |

### Rate Limits

GHL enforces per-location rate limits. General guidance from the master reference:
- Respect 429 responses and back off with exponential retry
- Batch contact imports instead of looping single creates; single generic add/save goes to POST /contacts/upsert (match keys + supplied fields only, never a tags array); POST /contacts/ is for an explicitly requested NEW record only
- Read-heavy operations (GET) have higher limits than writes

### Required Headers (every call)

```
Authorization: Bearer $GOHIGHLEVEL_API_KEY
Version: 2021-07-28
Content-Type: application/json
```

### Version Header Rule (read this before every call)

**HighLevel runs FIVE concurrently-supported versions**, selected per-request. Every one is
"Supported until: **TBD**" — no retirement dates, no forced migration
(`https://marketplace.gohighlevel.com/docs/Versioning/`).

| Version | Released | Supported until |
|---|---|---|
| `v3` | June 11, 2026 | TBD |
| `2023-02-21` | February 21, 2023 | TBD |
| `2021-07-28` | July 28, 2021 | TBD |
| `2021-04-15` | April 15, 2021 | TBD |
| `legacy` | January 1, 2021 | TBD |

**Which one to send** — the value is declared **per-operation**, not per-app:

```
Version: v3           ← the latest named version. REQUIRED for: opportunities
                        pipeline CRUD, calendar services, brand voices, social
                        planner queues/comments, chat-widget, the new emails
                        surface, and the hyphenated /oauth/... paths.

Version: 2023-02-21   ← SaaS endpoints, and POST /users/. Both documented and
                        working. Do NOT "correct" these to something older.

Version: 2021-07-28   ← the pre-v3 default: 32 of the 41 published specs declare
                        it exclusively (33 accept it, counting links).

Version: 2021-04-15   ← ONLY: agent-studio, calendars, conversation-ai,
                        conversations, knowledge-base, saas-api, voice-ai.

links accepts 2021-04-15 AND 2021-07-28.  store declares no Version parameter.
phone-system-v3 names the parameter lowercase `version` (headers are
case-insensitive, so `Version: v3` still works).
```

**An older supported version is NOT a defect.** Only a blanket "use one value for
everything" rule is — that is what this skill previously taught and what is now fixed.

**What live probing proved (2026-08-03).** Omitting the header is a **401** (`"version
header was not found."`); an unpublished value is a **401** (`"version header is invalid"`).
But `GET /contacts/`, `/users/` and `/calendars/` return **200 under all four** published
version strings. **No endpoint was found that rejects `2021-04-15`** — so the earlier claim
that a wrong Version header was causing live 400s is **false and withdrawn**. If you are
chasing a real client failure, check scopes, PIT-vs-OAuth, and location-vs-company token
first. Where the version *does* decide routing is brand-new and renamed paths:
`/brand-boards/.../brand-voices` and `/oauth/installed-locations` hard-404 unless you send
`Version: v3`.

> ⚠ **The GitHub spec repo lags the live docs** — last commit 2026-06-19, most specs synced
> 2026-05-01, `saas-api.json` 2025-08-13, while the changelog runs to 2026-07-30. Check
> `https://marketplace.gohighlevel.com/docs` before calling any doc wrong.

**Full per-operation table, generation-gated paths, v3 capability and the probe evidence:
`references/api-generations.md`.**

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
`Version: 2021-07-28` (see `references/medias.md`) — which is also the default for every
other app except the seven listed in "Version Header Rule" above. Confirm the Version
header per-app; do not blanket-change it.

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
| AI Agent Studio - create/version/publish/execute an agent | `references/agent-studio.md` |
| Voice AI - agents, actions, call logs, transcripts | `references/voice-ai.md` |
| Conversation AI - agents, actions, follow-up settings | `references/conversation-ai.md` |
| Knowledge Base - crawler, FAQs, training an agent on client content | `references/knowledge-base.md` |
| Ads - Facebook/Google/LinkedIn campaigns, adsets, reporting | `references/ad-publishing.md` |
| Anything else (store, snapshots, proposals, brand voices, chat widget, marketplace billing) | `references/modules.md` |
| **Which Version header / v2 vs v3 / a 404 on a path you expected** | `references/api-generations.md` |
| **Agency-level: OAuth tokens, sub-account provisioning, SaaS billing, agency users, snapshots** | `references/agency-api.md` |

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
    auth.md             - PIT + OAuth, the Version-header rule, all 130 scopes, the v3 generation
    api-generations.md  - v2 vs v3, per-surface Version table, generation-gated paths, live-probe evidence
    agency-api.md       - Agency/company-scoped API: OAuth, provisioning, SaaS billing, users, snapshots
    modules.md          - All 41 modules, verified op counts, v3-only surfaces
    contacts.md         - 32 endpoints for contact management
    conversations.md    - 29 endpoints for conversations and messages (Version 2021-04-15)
    opportunities.md    - 12 opportunity + pipeline endpoints
    calendars.md        - 41 endpoints for calendars and appointments (Version 2021-04-15)
    campaigns.md        - Campaign triggers + workflows (read-only)
    locations.md        - 29 endpoints for location/sub-account management
    payments.md         - Combined invoices + payments
    phone-numbers.md    - Phone number search, buy, configure
    users.md            - User CRUD and permissions
    webhooks.md         - Webhook events, payload structure, setup guide
    medias.md           - Media Library upload (Tier-3 only; LOCATION PIT, Version 2021-07-28)
    agent-studio.md     - 11 endpoints, AI agent lifecycle (Version 2021-04-15)
    voice-ai.md         - 11 endpoints, Voice AI agents/actions/call logs (Version 2021-04-15)
    conversation-ai.md  - 12 endpoints, conversational agent config (Version 2021-04-15)
    knowledge-base.md   - 14 endpoints, crawler + FAQs (Version 2021-04-15)
    ad-publishing.md    - 94 endpoints, Facebook/Google/LinkedIn ads
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

## Module Stats (counted from the published OpenAPI specs, 2026-08-03)

Operation counts are method+path pairs read out of each app's spec — not estimates.

| Module | Endpoint Count | Version header |
|--------|---------------|----------------|
| ad-manager | 94 | `2021-07-28` |
| invoices | 42 | `2021-07-28` |
| calendars | 41 | `2021-04-15` |
| social-media-posting | 40 | `2021-07-28` |
| contacts | 32 | `2021-07-28` |
| conversations | 29 | `2021-04-15` |
| locations | 29 | `2021-07-28` |
| products | 27 | `2021-07-28` |
| payments | 23 | `2021-07-28` |
| saas-api | 22 | `2021-04-15` |
| store | 18 | *(none declared)* |
| knowledge-base | 14 | `2021-04-15` |
| conversation-ai | 12 | `2021-04-15` |
| opportunities | 12 | `2021-07-28` |
| agent-studio | 11 | `2021-04-15` |
| voice-ai | 11 | `2021-04-15` |
| associations | 10 | `2021-07-28` |
| marketplace | 9 | `2021-07-28` |
| objects | 9 | `2021-07-28` |
| custom-fields | 8 | `2021-07-28` |
| blogs / funnels / medias | 7 each | `2021-07-28` |
| users | 7 | `2021-07-28` |
| links | 6 | both accepted |
| brand-boards / businesses / custom-menus | 5 each | `2021-07-28` |
| emails | 5 | `2021-07-28` |
| affiliate-manager / phone-system / proposals / snapshots | 4 each | `2021-07-28` |
| forms | 3 | `2021-07-28` |
| oauth | 3 | `2021-07-28` |
| surveys | 2 | `2021-07-28` |
| campaigns / companies / courses / email-isv / workflows | 1 each | `2021-07-28` |

Total: **576 operations across 41 published v2 app specs**, and **118 distinct permission
scopes** declared in those specs (130 when unioned with `docs/oauth/Scopes.md`). A second
generation — **42 v3 specs, `Version: v3`** — was published 2026-06-19; see
`references/auth.md` → "The v3 generation".

Source: `https://github.com/GoHighLevel/highlevel-api-docs/tree/main/apps` (enumerated 2026-08-03).
