# GHL MCP — How to Use It Day to Day

This document explains how to USE the GHL access chain after setup is complete. If setup is not done yet, read INSTALL.md first.

After setup, your agent can route GHL requests through Tier 0 Convert and Flow CLI (skill 44 — PRIMARY), then Official MCP, raw API, agent-browser/Playwright, and Codex Computer Use — in that order of preference. The self-hosted community MCP (the old Tier 2) is **retired**: it is not installed, not a fallback, and its absence is the expected end state.

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

**Documented catalog — exactly four tools:** `list_locations`, `search_operations`,
`describe_operation`, `execute_operation`. The documented endpoints are client-specific and
use **OAuth**:

| Client | Endpoint | Auth |
|---|---|---|
| Claude Code / Claude MCP client | `https://services.leadconnectorhq.com/mcp/anthropic/v2` | OAuth |
| ChatGPT / Codex / OpenAI clients | `https://services.leadconnectorhq.com/mcp/openai/v2/` | OAuth |
| OpenClaw gateway / legacy `/mcp/` registration | `https://services.leadconnectorhq.com/mcp/` | **transitional**; PIT bearer is an unverified compatibility mode |

The per-operation names in the table below come from the **transitional `/mcp/` endpoint**,
not from the documented four-tool catalog. They are **UNVERIFIED** as current catalog and may
not exist on a client-specific v2 connection. Do not delete them from the reference — but
never cite them as the official catalog. Discover the real operation set with
`search_operations` and inspect it with `describe_operation`.

Use Tier 1 first when the task is in one of these domains:

| Domain | Example tools (legacy `/mcp/` surface — UNVERIFIED as v2 catalog) |
|---|---|
| Contacts | `contacts_get-contact`, `contacts_create-contact`, `contacts_search-contacts`, `contacts_upsert-contact`, `contacts_add-tags`, `contacts_remove-tags` |

**CONTACT WRITE ROUTING (binding).** Generic "add/save this person" is NOT a
create. Route contact writes: Tier 0 `caf contacts upsert` FIRST (match keys
email and/or phone, supplied fields only, tags via `caf contacts add-tag`;
`--create-new-if-duplicate-allowed` only on explicit new-record request);
explicit "create a NEW contact" → `caf contacts create`; known contactId →
`caf contacts update <id>` with non-tag fields only (`--tag` is refused
destructive — PUT replaces the whole set). Same rule binds Tier 3 raw API
(POST /contacts/upsert default, POST /contacts/ explicit-new only). On the
transitional `/mcp/` surface the corresponding names are `contacts_upsert-contact`
and `contacts_create-contact` — **UNVERIFIED** as current catalog (the documented
catalog publishes only the four tools above). HighLevel's Upsert endpoint resolves
create-vs-update per the Location-level Allow Duplicate Contact configuration
and its matching priority. Verify every write: capture the contact ID, read the
record back, confirm intended fields.
| Conversations | `conversations_send-a-new-message`, `conversations_get-messages`, `conversations_search-conversation` |
| Opportunities | `opportunities_get-opportunity`, `opportunities_update-opportunity`, `opportunities_search-opportunity`, `opportunities_get-pipelines` |
| Calendars | `calendars_get-calendar-events`, `calendars_get-appointment-notes` |
| Locations | `locations_get-location`, `locations_get-custom-fields` |
| Blogs | `blogs_create-blog-post`, `blogs_update-blog-post`, `blogs_get-blog-post`, `blogs_get-blogs`, `blogs_check-url-slug-exists` |
| Emails | `emails_fetch-template`, `emails_create-template` |
| Social Media | `social-media-posting_create-post`, `social-media-posting_edit-post`, `social-media-posting_get-post`, `social-media-posting_get-posts`, `social-media-posting_get-account`, `social-media-posting_get-social-media-statistics` |
| Payments (read-only) | `payments_get-order-by-id`, `payments_list-transactions` |

**No tool count is a contract.** The documented catalog is four tools. Counts from the
transitional endpoint are observations, not an interface — never gate a decision on one.

### Four evidence levels for MCP — do not collapse them

| Level | What it means | Can this repo assert it? |
|---|---|---|
| **1. Documented endpoint** | Vendor docs publish the URL for a named client | **Yes** |
| **2. Documented catalog** | Vendor docs publish exactly four tool names | **Yes** — names only |
| **3. Account / tenant grant** | This account actually authorizes the connection and scopes | **No** — needs an authorized OAuth connect |
| **4. Actually observed on this box** | `tools/list` plus one real call, captured here | **No** — needs the box's own receipt |

### Tier 2 — RETIRED community GHL MCP (`ghl-community-mcp`)

The community MCP is **not installed, not required, and not a fallback**. Do not call it, do
not probe it, do not restart it, and do not rebuild it because a count looks low. Use Tier 0
(CLI) or Tier 3 (REST) for anything the official MCP does not cover.

The table below is **historical**: it records the retired transport's tool names so a
migration can map intent to a live route. Every name is **UNVERIFIED** against any current
upstream, and none is a valid call path. The last vetted profile was `curated` (43 crm tools),
so under that profile most `ghl_*` names below did not even exist — the 588 figure described a
different profile and proves nothing.

| Domain | Historical tool names (RETIRED — map to Tier 0/3) |
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

**Retirement check (the only valid Tier 2 operation):**

```bash
openclaw mcp list | grep -w ghl-community-mcp || echo "registration: absent"
lsof -nP -iTCP:8765 -sTCP:LISTEN 2>/dev/null | grep -q LISTEN && echo "LISTENER STILL PRESENT" || echo "listener: absent"
```

Expected: no registration, no listener. The old `curl $GHL_COMMUNITY_MCP_URL/tools` discovery
is gone with the service — there is no `$GHL_COMMUNITY_MCP_URL` in the required end state.

### Tier 3 — Direct REST API + skill 29 reference

Use when the official MCP does not cover the call. Resolve which reference file to read:

```bash
# Identify domain from the task, then read the matching reference
ls "$MASTER_FILES_DIR/29-ghl-convert-and-flow/references/"
# contacts.md, conversations.md, opportunities.md, calendars.md, locations.md, payments.md, etc.
```

Then build the curl call. **The `Version` header is selected per operation, never globally.**
The literal below is an example only — copy the literal from the operation's reference page or
skill 29 reference row:

```bash
curl -sS -X GET "https://services.leadconnectorhq.com/<endpoint>?locationId=$GOHIGHLEVEL_LOCATION_ID" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: <per-operation literal>"
```

Documented supported versions include `v3`, `2023-02-21`, `2021-07-28`, `2021-04-15`, and
`legacy`; `v4` workflow contracts are staging-only evidence and are not on the production
supported list. There is no global header rule and no default — a missing literal is a
contract question to settle from the page, never a value to guess.

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

1. **Re-read the canonical state block in AGENTS.md.** Compare endpoint / transport / credential class against what you actually called. If they don't match, fix and retry.
2. **Separate auth from transport before declaring a tier dead.**
   - Tier 1: 401/403 is an OAuth grant or scope problem, not an outage. 406 is `Accept` negotiation (documented for the transitional `/mcp/` endpoint). DNS/TLS/timeout is transport. Re-authorize in the client and record a fresh `tools/list` capture.
   - Tier 3: re-check the per-operation `Version` literal, the PIT class, and the rate-limit headers.
3. **Tier 2 is retired — there is nothing to recover.** Do not start it, probe it, or restart it to test it.
4. Only after call shape and auth are ruled out, fall through to the next tier. The disclosure header must reflect the actual reason.

## 🔴 Rate-Limit Protocol — 429 is NOT a fallthrough trigger

The documented per-location rate limits belong to the **REST API**. HighLevel publishes **no
rate limits for the MCP endpoints**. Assume one shared backend bucket, so switching routes
does not create capacity and 429 is never a fallthrough trigger.

**Documented REST limits:** 100 req/10s burst | 200,000 req/day per location.

**Headers on REST responses:**
- `X-RateLimit-Remaining` (burst budget)
- `X-RateLimit-Daily-Remaining` (daily budget left)
- `X-RateLimit-Limit-Daily` (200000)
- `X-RateLimit-Daily-Reset` (seconds until reset)

**Pre-flight before bulk ops:**

```bash
# Cheap probe — a REST read, because the documented rate-limit headers are REST headers.
# Use a known Tier 3 read from skill 29's reference and its own Version literal.
curl -sS -i -X GET "https://services.leadconnectorhq.com/<documented-read-operation>" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: <per-operation literal>" \
  | grep -i "x-ratelimit-daily-remaining"
```

If `X-RateLimit-Daily-Remaining < 1000`: STOP. Compute reset time from `X-RateLimit-Daily-Reset` (seconds), surface to owner as "Rate limit nearly exhausted — back at HH:MM ET". Do NOT proceed.

**On 429 from any surface:**

1. Parse `X-RateLimit-Daily-Reset` (or `Retry-After` if present).
2. Compute clock time: `reset_time = now + reset_seconds`.
3. Surface to owner: "Rate limited — back at HH:MM ET (in X hours)."
4. **DO NOT retry blindly. DO NOT fall through to a different tier** (all surfaces share the same backend bucket).
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

- ❌ "Tier 1 doesn't have X → I'll use Tier 3 because Tier 3 has X." → Wrong reasoning. Use Tier 3 because Tier 1 does not cover the operation, not because REST "has" it. Tier 2 is retired and is never the answer.
- ❌ Hardcoding a port number from session memory. → There is no community URL env var any more; the required state is no listener on 8765.
- ❌ "The community MCP crashed earlier in this session → restart it." → Wrong. It is retired. Do not start it.
- ❌ "Tier 3 is faster / cleaner / I prefer raw API." → Personal preference is not a routing override.
- ❌ Skipping the disclosure header on an operator-channel GHL response. → Required there; stripped from client-facing replies.
- ❌ "CLI covers it but I'll use an MCP." Wrong. Tier 0 first for every covered op.
- ❌ Jumping to Tier 4 (browser) for a workflow-write when the Firebase token is
  present and healthy. Tier 4 is the backstop ONLY when the token is genuinely
  unavailable.
- ❌ Using any MCP tool to BUILD a GHL workflow. The official MCP documents workflow
  lookup plus contact enrollment/removal only; it has no authoring tool. Workflow creation
  and editing use Skill 44's internal Build API (Tier 0) or the Build-with-AI manual paste
  (fallback). These are orthogonal surfaces — see `38-conversational-ai-system/references/GHL_AI_LAYERS.md`.
- ❌ Calling an MCP tool (`ghl-mcp__*`) inside a spawned sub-agent. Sub-agents have no
  MCP tool injection. Lookups inside sub-agents MUST use `caf contacts search/get` (CLI)
  or raw HTTPS to `services.leadconnectorhq.com`. Never instruct a sub-agent to use MCP.
- ❌ Raw HTTP to the transitional `/mcp/` endpoint with only `Accept: application/json`.
  That endpoint requires BOTH `Accept: application/json, text/event-stream`; missing
  `text/event-stream` returns HTTP 406 (content-negotiation failure, not auth). Do not
  assume that rule carries to the v2 client endpoints without a capture, and do not add a
  global `Version` header — the version is per operation, and the MCP endpoints document none.
- ❌ `grep -P` in any shell script on a Mac client box. BSD grep has no -P flag.
  Use `python3 -c "import json,sys; ..."` or `jq` for all JSON/SSE parsing.
- ❌ Metered `:cloud` model for a contact lookup. Use the client's selected direct
  (non-metered) model, their configured default model, or any free fallback. Lookups are
  cheap data-retrieval, not reasoning tasks that justify metered quota burn.
- ❌ Routing a contact lookup to Tier 4 (browser). The browser tier is for UI-only flows
  and workflow-build backstops when the Firebase token is unavailable. Lookups never go
  to the browser.

## Common Cross-Tier Workflows

### Product → Invoice → Subscription (Tier 0 CLI first, else Tier 3 REST)

The retired community tool names in this flow are historical; the route is Tier 0 where the
CLI covers it, otherwise Tier 3 REST.

```
products.create         → create the product record            POST /products/
  ↓
products.prices.create  → attach pricing                       POST /products/{productId}/price
  ↓
products.update         → set status=active/live               PUT  /products/{productId}
  ↓
invoices.create         → create invoice linked to contact      POST /invoices/
  ↓
invoices.send           → deliver to client                     POST /invoices/{invoiceId}/send
  ↓
orders.recordPayment    → log payment received                  POST /payments/orders/{orderId}/record-payment
```

For monthly subscriptions, after the price is created:
```
invoices.schedules.create   → define recurrence     POST /invoices/schedule
  ↓
(recurrence is activated by the documented schedule payload; no community
 auto_payment_invoice_schedule tool exists any more)
```

Every write above is approval-gated and needs a read-back.

### Contact lookup + payment history (Tier 1 + Tier 3)

```
Tier 1: discovery tool for the contact operation (UNVERIFIED legacy name: contacts_search-contacts)
  ↓
Tier 3: GET /payments/transactions filtered by contactId → payment history
```

Disclosure: `[GHL tier used: 3 (Tier 1 lacked operation: transactions.list) — raw API GET /payments/transactions]`

### Social media post — AD-HOC interactive request only (Tier 1)

```
Tier 1: the social-media-posting operation exposed by this connection
        (legacy name `social-media-posting_create-post` is UNVERIFIED)
  ↓
Body includes content, media URLs, platform targets, schedule
```

This Tier-1 path is for an AD-HOC, in-chat request ("post this to my socials").
Skill 35's scheduled 15+6 publishing pipeline is SEPARATE and self-contained — it
posts via its own verified direct-API path and is NOT routed through this MCP.

## Health Check Cheatsheet

```bash
# Tier 1 — documented client path: authorize OAuth in the client, then record tools/list.
# The four documented names are the assertion; a count is not.
#   list_locations, search_operations, describe_operation, execute_operation

# Tier 1 — transitional /mcp/ reachability check (names, not a count)
curl -sS -m 5 -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | grep "^data:" | head -1 | sed 's/^data: //' \
  | python3 -c "import json,sys; print('transitional /mcp/ tools:', [t.get('name') for t in json.load(sys.stdin).get('result',{}).get('tools',[])])"

# Tier 2 — RETIRED. The healthy state is ABSENT, not running:
openclaw mcp list | grep -w ghl-community-mcp || echo "registration: absent"
# macOS:
launchctl print gui/$(id -u)/com.clawd.ghl-mcp >/dev/null 2>&1 && echo "STILL LOADED" || echo "launchd: not loaded"
# VPS (pm2 canonical):
pm2 describe ghl-community-mcp 2>/dev/null || echo "pm2: absent"
# Non-container Linux (systemd):
systemctl is-enabled ghl-mcp 2>/dev/null || echo "systemd: no unit"
# Port:
lsof -nP -iTCP:8765 -sTCP:LISTEN 2>/dev/null | grep -q LISTEN && echo "LISTENER STILL PRESENT" || echo "listener: absent"
```

## Command Center hooks (Skill 32 board — operator visibility)

Skill 32 is the Command Center host; other skills DRIVE its board. Skill 36 emits status to
**Skill 32's existing board ingestion** — it does NOT build a parallel board, a second card
store, or its own UI.

Emit a card / status update at these moments:

- **Install start** — open/append a card: "GHL MCP setup — started (box, platform)". Emitted by
  `scripts/cc-task.sh start` from INSTALL.md's Autonomous Setup Execution (Pre-Action 0.5).
- **Install complete** — move that card to `review` with the QC result (e.g. "qc-ghl-mcp-setup.sh
  exit 0; official MCP connection present; community MCP verified absent"). Emitted by `scripts/cc-task.sh review`
  from the QC PASS branch. The **independent Command Center auto-scorer is the only authority
  that promotes review → done** — the builder never self-grades.
- **Tier incident — 429 lockout** — status card: "GHL rate-limit lockout; daily reset ~HH:MM
  ET; all tiers share one bucket — paused" (matches the Rate-Limit Protocol above).
- **Tier incident — missing credential** — status card: "GHL blocked: missing PIT / Location
  ID (or Firebase token for builds) — owner asked to supply it" (matches the missing-cred
  grace in GHL-LOOKUP-SOP.md RULE 5 + CORE_UPDATES.md).

**How to emit (anti-fabrication — do NOT invent an endpoint):** the two lifecycle moments
(install start / complete) are implemented by the skill's own fail-soft helper
`scripts/cc-task.sh` (`start` and `review` subcommands), which posts to the Command Center
task API (`MISSION_CONTROL_URL` /api/tasks, bearer `MC_API_TOKEN`). It is graceful-degrading:
with no token or an unreachable board it prints ONE operator-only stderr note and exits 0 —
it never blocks or fails the GHL operation. The two runtime tier-incident cards are
best-effort operator notes; emit them via the same helper contract (or Skill 32's documented
board ingestion if you carry richer incident metadata) and skip silently if the board is
unavailable. These cards are OPERATOR-facing only — like the tier header, they are not
client-facing (WE MOVE IN SILENCE).

## When Setup Is Done and Things Just Work

The disclosure header is your operator-channel audit trail. Every operator-channel response
with a tier header that matches the task domain is a passing case. Anything missing the
header (on the operator channel), or showing tier 3 when tier 0/1/2 should have served the
request, is a failure to investigate. (Client-facing replies carry no header by design.)
