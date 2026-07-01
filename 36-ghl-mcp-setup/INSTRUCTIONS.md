# GHL MCP — How to Use It Day to Day

This document explains how to USE the 6-tier GHL access chain after setup is complete. If setup is not done yet, read INSTALL.md first.

After setup, your agent can route GHL requests through Tier 0 Convert and Flow CLI (skill 44 — PRIMARY), then Official MCP, Community MCP, raw API, agent-browser/Playwright, and Codex Computer Use — in that order of preference.

## The Cardinal Rule

**Try each tier in numerical order. Do NOT skip tiers.** This rule lives in the shared **AGENTS.md** as a 🔴 cardinal protocol (so every agent, including sub-agents, inherits it). Violating it is a documented past failure. The rule is binding.

## Disclosure Header Format — OPERATOR CHANNEL ONLY

This header is an internal audit trail for the OPERATOR. Every reply that surfaces
GHL / GoHighLevel / Convert and Flow / LeadConnector data **on the operator channel** MUST
begin with this header on its own line:

```
[GHL tier used: N — tool_name]
```

> **WE MOVE IN SILENCE — strip this header from CLIENT-FACING replies.** When the answer
> goes to a client (their Telegram, a coaching-persona reply, any customer-facing surface),
> do NOT emit the tier header — it leaks internal tier/tool/fallback plumbing the client
> should never see. Give the client just the result. The header is mandatory for the
> operator's audit and forbidden on the client's screen.

Examples:
- `[GHL tier used: 0 — convertandflow contacts list]`
- `[GHL tier used: 0 (workflow write, Firebase token healthy) — convertandflow workflows build]`
- `[GHL tier used: 1 — locations_get-location]`
- `[GHL tier used: 2 — ghl_list_products]`
- `[GHL tier used: 2 (Tier 1 lacked tool: products) — ghl_list_products]`
- `[GHL tier used: 3 (Tier 1+2 lacked tool: webhook_log) — raw API GET /hooks/]`

If you fall through tiers, the header must show the chain so the audit is complete.

## When to Use Which Tier

### Tier 1 — Official GHL MCP (`ghl-mcp`)

Use first when the task is in one of these domains:

| Domain | Example tools |
|---|---|
| Contacts | `contacts_get-contact`, `contacts_create-contact`, `contacts_search-contacts`, `contacts_upsert-contact`, `contacts_add-tags`, `contacts_remove-tags` |
| Conversations | `conversations_send-a-new-message`, `conversations_get-messages`, `conversations_search-conversation` |
| Opportunities | `opportunities_get-opportunity`, `opportunities_update-opportunity`, `opportunities_search-opportunity`, `opportunities_get-pipelines` |
| Calendars | `calendars_get-calendar-events`, `calendars_get-appointment-notes` |
| Locations | `locations_get-location`, `locations_get-custom-fields` |
| Blogs | `blogs_create-blog-post`, `blogs_update-blog-post`, `blogs_get-blog-post`, `blogs_get-blogs`, `blogs_check-url-slug-exists` |
| Emails | `emails_fetch-template`, `emails_create-template` |
| Social Media | `social-media-posting_create-post`, `social-media-posting_edit-post`, `social-media-posting_get-post`, `social-media-posting_get-posts`, `social-media-posting_get-account`, `social-media-posting_get-social-media-statistics` |
| Payments (read-only) | `payments_get-order-by-id`, `payments_list-transactions` |

**Total: 36 tools.**

### Tier 2 — Community GHL MCP (`ghl-community-mcp`)

Use when Tier 1 lacks the needed tool. Domains:

| Domain | Primary tools |
|---|---|
| Products | `ghl_list_products`, `ghl_get_product`, `ghl_create_product`, `ghl_update_product`, `ghl_delete_product`, `ghl_create_price`, `ghl_list_prices`, `ghl_create_product_collection`, `ghl_list_product_collections`, `ghl_list_inventory`, `ghl_bulk_edit_products` |
| Invoices | `list_invoices`, `get_invoice`, `create_invoice`, `update_invoice`, `delete_invoice`, `send_invoice`, `view_invoice`, `generate_invoice_number` |
| Recurring billing / subscriptions | `list_invoice_schedules`, `get_invoice_schedule`, `create_invoice_schedule`, `update_invoice_schedule`, `list_subscriptions`, `get_subscription_by_id`, `update_saas_subscription`, `rebilling_update` |
| Estimates | `list_estimates`, `create_estimate`, `send_estimate`, `create_invoice_from_estimate`, `generate_estimate_number` |
| Payments (full) | `list_orders`, `get_order_by_id`, `list_transactions`, `get_transaction_by_id`, `list_gateways`, `record_order_payment` |
| Coupons | `list_coupons`, `create_coupon`, `update_coupon`, `delete_coupon`, `get_coupon` |
| Voice AI | `create_voice_ai_agent`, `update_voice_ai_agent`, `list_voice_ai_agents`, `get_voice_ai_call_log` |
| Phone System | `ghl_buy_phone_number`, `ghl_list_phone_numbers`, `update_phone_number`, `ghl_get_call_recording`, `update_call_forwarding` |
| Agent Studio | `ghl_create_agent`, `ghl_update_agent`, `ghl_deploy_agent`, `ghl_list_agents` |
| Workflows (escalation/read only) | `ghl_list_workflows`, `ghl_get_workflow`, `ghl_trigger_workflow`, `ghl_publish_workflow`. **Workflow BUILD/EDIT is Tier 0 (Skill 44 Build API), NOT here** — `ghl_create_workflow` / `ghl_update_workflow_actions` exist in the fork (`src/tools/workflow-builder-tools.ts`) but wrap an undocumented internal endpoint and are unverified / likely produce non-functional shells. Do not build via MCP. |

**Total: 588 tools.** For anything not in this table, run live discovery:
```bash
curl $GHL_COMMUNITY_MCP_URL/tools | python3 -m json.tool
```

### Tier 3 — Direct REST API + skill 29 reference

Use only when neither MCP covers the call. Resolve which reference file to read:

```bash
# Identify domain from the task, then read the matching reference
ls "$MASTER_FILES_DIR/29-ghl-convert-and-flow/references/"
# contacts.md, conversations.md, opportunities.md, calendars.md, locations.md, payments.md, etc.
```

Then build the curl call:
```bash
curl -sS -X GET "https://services.leadconnectorhq.com/<endpoint>?locationId=$GOHIGHLEVEL_LOCATION_ID" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28"
```

Some modules use `Version: 2021-04-15`. Always check the reference file for the correct version header.

### Tier 4 — Browser (agent-browser FIRST, Playwright fallback) — skill 03

Use when the operation can only be done in the UI (no API endpoint exists) OR as
the no-token workflow-write backstop. Prefer skill 03's agent-browser with
ref-based accessibility snapshots (text) over screenshots; fall back to Playwright
`launchPersistentContext` only if agent-browser is unavailable. On Mac installs a
dead-Firebase-token event triggers the auto-re-grab recipe (Section 3B): read
`stsTokenManager.refreshToken` from the client's LOCAL logged-in browser profile
and refresh the secrets file. Write discipline parity: draft-only, location
whitelist, and the approval gate bind Tier 4 writes exactly as they bind Tier 0.

### Tier 5 — Codex Computer Use

Last resort. Route through `codex-computer-use` sub-agent with model `codex/gpt-5.5`. Default timeout 45 minutes.

## Verify-Before-Fallthrough Protocol

When a tier returns 404 / 502 / connection refused / "not found":

1. **Re-read the canonical state block in AGENTS.md.** Compare URL/port/path against what you actually called. If they don't match, fix and retry.
2. **Hit `/health`** for that tier:
   - Tier 1: `curl https://services.leadconnectorhq.com/mcp/ -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" ...`
   - Tier 2: `curl $GHL_COMMUNITY_MCP_URL/health`
3. If health passes, the server is fine — your call shape is wrong. Fix and retry.
4. If health fails, attempt recovery:
   - Tier 2 macOS: `launchctl kickstart gui/$(id -u)/com.clawd.ghl-mcp`
   - Tier 2 VPS: `pm2 restart ghl-community-mcp` (Docker/Hostinger canonical) — or `sudo systemctl restart ghl-mcp` on a non-container systemd box
5. Only after recovery fails, fall through to the next tier. The disclosure header must reflect the actual reason.

## 🔴 Rate-Limit Protocol — 429 is NOT a fallthrough trigger

GHL enforces per-location rate limits across ALL THREE tiers — they share the same backend bucket. Switching tiers does NOT bypass.

**Limits:** 100 req/10s burst | 200,000 req/day per location.

**Headers on every response:**
- `X-RateLimit-Remaining` (burst budget)
- `X-RateLimit-Daily-Remaining` (daily budget left)
- `X-RateLimit-Limit-Daily` (200000)
- `X-RateLimit-Daily-Reset` (seconds until reset)

**Pre-flight before bulk ops:**

```bash
# Cheap probe — read headers
curl -sS -i -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | grep -i "x-ratelimit-daily-remaining"
```

If `X-RateLimit-Daily-Remaining < 1000`: STOP. Compute reset time from `X-RateLimit-Daily-Reset` (seconds), surface to owner as "Rate limit nearly exhausted — back at HH:MM ET". Do NOT proceed.

**On 429 from any tier:**

1. Parse `X-RateLimit-Daily-Reset` (or `Retry-After` if present).
2. Compute clock time: `reset_time = now + reset_seconds`.
3. Surface to owner: "Rate limited — back at HH:MM ET (in X hours)."
4. **DO NOT retry blindly. DO NOT fall through to a different tier** (all three share the same quota).
5. Log the incident to MEMORY.md under "## Rate Limit Incidents".

**Batching rules:**
- Use `limit=100` on list endpoints, not many `limit=5` calls.
- Cache list results in MEMORY.md for ≥5 minutes; don't refetch per turn.
- Polling intervals ≥60 sec; non-critical ≥5 min.

**What burns quota fast (avoid):**
- Test loops during development that re-call live endpoints
- n8n workflows hitting GHL every few seconds
- Community MCP polling intervals set too tight
- Agent re-fetching the same products/contacts list every turn instead of caching

**Documented past failure:** 2026-05-13, BlackCEO location `[REDACTED]` burned all 200k daily calls. All three tiers returned the same underlying 429 simultaneously. Root cause was test loops + polling + per-turn re-fetches. Recovery: wait ~7 hours for daily reset; do NOT attempt workarounds.

## Anti-Patterns (DO NOT do these)

- ❌ "Tier 1 doesn't have X → I'll use Tier 3 because Tier 3 has X." → Wrong. Use Tier 2.
- ❌ Hardcoding a port number from session memory. → Always use `$GHL_COMMUNITY_MCP_URL`.
- ❌ "Tier 2 crashed earlier in this session → skip it." → Wrong. Restart and retry.
- ❌ "Tier 3 is faster / cleaner / I prefer raw API." → Personal preference is not a routing override.
- ❌ Skipping the disclosure header on a GHL response. → Required on every GHL-data response.
- ❌ "CLI covers it but I'll use an MCP." Wrong. Tier 0 first for every covered op.
- ❌ Jumping to Tier 4 (browser) for a workflow-write when the Firebase token is
  present and healthy. Tier 4 is the backstop ONLY when the token is genuinely
  unavailable.
- ❌ Using MCP tools (Tiers 1-2) to BUILD a GHL workflow. MCP covers contacts /
  conversations / calendar / tags reads and writes. Workflow creation and editing use
  Skill 44's internal Build API (Tier 0) or the Build-with-AI manual paste (fallback).
  These are orthogonal surfaces — see `38-conversational-ai-system/references/GHL_AI_LAYERS.md`.
- ❌ Calling an MCP tool (`ghl-mcp__*`) inside a spawned sub-agent. Sub-agents have no
  MCP tool injection. Lookups inside sub-agents MUST use `caf contacts search/get` (CLI)
  or raw HTTPS to `services.leadconnectorhq.com`. Never instruct a sub-agent to use MCP.
- ❌ Raw HTTP fallback with only `Accept: application/json`. The GHL hosted MCP endpoint
  requires BOTH `Accept: application/json, text/event-stream` AND `Version: 2021-07-28`.
  Missing `text/event-stream` returns HTTP 406 (content-negotiation failure, not auth).
- ❌ `grep -P` in any shell script on a Mac client box. BSD grep has no -P flag.
  Use `python3 -c "import json,sys; ..."` or `jq` for all JSON/SSE parsing.
- ❌ Metered `:cloud` model for a contact lookup. Use `deepseek-v4-flash` (direct) or
  any free fallback. Lookups are cheap data-retrieval — not reasoning tasks that justify
  metered quota burn.
- ❌ Routing a contact lookup to Tier 4 (browser). The browser tier is for UI-only flows
  and workflow-build backstops when the Firebase token is unavailable. Lookups never go
  to the browser.

## Common Cross-Tier Workflows

### Product → Invoice → Subscription (Tier 2 only)

```
ghl_create_product          → create the product record
  ↓
ghl_create_price            → attach pricing (set type=recurring, interval=month for subscriptions)
  ↓
ghl_update_product          → set status=active/live
  ↓
create_invoice              → create invoice linked to contact
  ↓
send_invoice                → deliver to client
  ↓
record_order_payment        → log payment received
```

For monthly subscriptions, after the price is created:
```
create_invoice_schedule           → define recurrence
  ↓
update_invoice_schedule           → activate it
  ↓
auto_payment_invoice_schedule     → enable auto-charge on file
```

### Contact lookup + payment history (Tier 1 + Tier 2)

```
Tier 1: contacts_search-contacts → find the contact
  ↓
Tier 2: list_transactions filtered by contactId → payment history
```

Disclosure: `[GHL tier used: 1+2 — contacts_search-contacts; list_transactions]`

### Social media post — AD-HOC interactive request only (Tier 1)

```
Tier 1: social-media-posting_create-post
  ↓
Body includes content, media URLs, platform targets, schedule
```

This Tier-1 path is for an AD-HOC, in-chat request ("post this to my socials").
Skill 35's scheduled 15+6 publishing pipeline is SEPARATE and self-contained — it
posts via its own verified direct-API path and is NOT routed through this MCP.

## Health Check Cheatsheet

```bash
# Tier 1 — verify auth
curl -sS -m 5 -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | grep "^data:" | head -1 | sed 's/^data: //' \
  | python3 -c "import json,sys; print('Tier 1 OK, tools:', len(json.load(sys.stdin).get('result',{}).get('tools',[])))"

# Tier 2 — verify server running
curl -sS -m 5 $GHL_COMMUNITY_MCP_URL/health

# Tier 2 service status
# macOS:
launchctl print gui/$(id -u)/com.clawd.ghl-mcp | grep -E "state|pid"
# VPS (pm2 canonical):
pm2 describe ghl-community-mcp
# Non-container Linux (systemd fallback):
systemctl status ghl-mcp
```

## Command Center hooks (Skill 32 board — operator visibility)

Skill 32 is the Command Center host; other skills DRIVE its board. Skill 36 emits status to
**Skill 32's existing board ingestion** — it does NOT build a parallel board, a second card
store, or its own UI.

Emit a card / status update at these moments:

- **Install start** — open/append a card: "GHL MCP setup — started (box, platform)".
- **Install complete** — move that card to done with the QC result (e.g. "qc-ghl-mcp-setup.sh
  exit 0; Tier 1 >=36 tools, Tier 2 >=500 on-demand").
- **Tier incident — 429 lockout** — status card: "GHL rate-limit lockout; daily reset ~HH:MM
  ET; all tiers share one bucket — paused" (matches the Rate-Limit Protocol above).
- **Tier incident — missing credential** — status card: "GHL blocked: missing PIT / Location
  ID (or Firebase token for builds) — owner asked to supply it" (matches the missing-cred
  grace in GHL-LOOKUP-SOP.md RULE 5 + CORE_UPDATES.md).

**How to emit (anti-fabrication — do NOT invent an endpoint):** use the ingestion mechanism
Skill 32 documents in `32-*/INSTALL.md` (its board ingestion / card API). Read that skill's
own docs for the exact call on this box; if Skill 32 is not installed, skip the hook (these
status emits are best-effort operator visibility, never a blocker for the GHL operation
itself). These cards are OPERATOR-facing only — like the tier header, they are not
client-facing (WE MOVE IN SILENCE).

## When Setup Is Done and Things Just Work

The disclosure header is your operator-channel audit trail. Every operator-channel response
with a tier header that matches the task domain is a passing case. Anything missing the
header (on the operator channel), or showing tier 3 when tier 0/1/2 should have served the
request, is a failure to investigate. (Client-facing replies carry no header by design.)
