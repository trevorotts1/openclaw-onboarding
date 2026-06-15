# GHL Contact Lookup — Authoritative SOP

**Scope:** This document covers the decision rules, failure modes, and mandatory contract
for GHL contact lookups and the broader two-axis routing decision between READ and BUILD
paths. It is the single source of truth for any agent performing a GHL contact lookup
or routing a funnel/workflow build request.

**Companion docs:**
- `36-ghl-mcp-setup/INSTRUCTIONS.md` — tier-by-tier day-to-day usage
- `36-ghl-mcp-setup/EXAMPLES.md` — working curl examples with the correct headers
- `38-conversational-ai-system/references/GHL_AI_LAYERS.md` — Layer 0/1/2 build-vs-runtime routing
- `44-convert-and-flow-operator/SKILL.md` — Tier 0 CLI surface and Firebase token model
- `29-ghl-convert-and-flow/references/campaigns.md` — proof that `/workflows/` is read-only

---

## RULE 1 — MCP tools live in the ORCHESTRATOR only

MCP tool calls (`ghl-mcp__contacts_get-contacts`, `ghl-mcp__contacts_search-contacts`,
and all `ghl-mcp__*` / Tier 2 community tools) **are available only in the orchestrating
agent session**. Spawned sub-agents receive NO injected MCP tools.

**What this means in practice:**

- **Orchestrator:** may call `contacts_get-contacts` directly as an MCP tool.
- **Sub-agent:** MUST use the Tier 0 CLI (`caf contacts search <query>`) or a raw
  HTTPS call to `services.leadconnectorhq.com`. Never assume MCP tools exist inside a
  sub-agent.

**Anti-patterns:**

- A sub-agent that calls `ghl-mcp__contacts_get-contacts` — this will fail silently or
  return a tool-not-found error.
- An orchestrator that spawns a sub-agent and tells it "use the MCP to look up the
  contact" — the sub-agent cannot.

**Correct pattern:**

```
Orchestrator: call contacts_get-contacts (MCP tool) → pass contactId to sub-agent
Sub-agent:    call `caf contacts get <contactId>` (CLI) OR raw HTTPS (Tier 3)
```

---

## RULE 2 — Lookup model: deepseek-v4-flash (direct) primary; free fallback

When the orchestrator calls the official MCP (`contacts_get-contacts`,
`contacts_search-contacts`) and a model inference step is needed to parse the result or
decide the next action:

- **Primary model:** `deepseek-v4-flash` (direct, cheap, fast — NOT a `:cloud` metered
  model).
- **Fallback:** any free/low-cost provider available in the session.
- **NEVER:** use a `:cloud` metered model (e.g. `deepseek-v4-pro:cloud`,
  `ollama-cloud/...`) for a cheap read-only lookup. A contact lookup is not a reasoning
  task — it is a data-retrieval task. Metered cloud models for lookups waste quota.

---

## RULE 3 — Raw HTTP fallback MUST carry BOTH headers

When neither the CLI (Tier 0) nor an MCP tool is available and a raw-HTTP fallback is
required (Tier 3), the request to `https://services.leadconnectorhq.com/mcp/` **MUST**
send both of the following headers:

```
Accept: application/json, text/event-stream
Version: 2021-07-28
```

**Why both are mandatory:**

- The GHL hosted MCP endpoint uses HTTP content negotiation. If the `Accept` header
  does NOT include `text/event-stream`, the server returns **HTTP 406 Not Acceptable**.
  This is not an auth error — it is a content-negotiation error. Sending only
  `Accept: application/json` is the documented failure mode.
- The `Version` header selects the API contract. Omitting it or sending the wrong
  version for the module returns 400 or 401.

**Correct raw-HTTP example (contacts lookup):**

```bash
curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"contacts_get-contacts","arguments":{"limit":5}}}' \
  | grep "^data:" | head -1 | sed 's/^data: //' | python3 -m json.tool
```

**Per-module Version header reference:**

| Module | Version header value |
|---|---|
| contacts, locations, blogs, social, opportunities | `2021-07-28` |
| conversations, calendars, payments | `2021-04-15` |

When in doubt, check the authoritative reference in
`29-ghl-convert-and-flow/references/<module>.md`. Do not hardcode a single version for
all modules — version drift causes intermittent 400/401 errors.

---

## RULE 4 — Never use `grep -P` on macOS

BSD grep (the default `grep` on macOS / Mac mini installs) does not support the `-P`
(Perl regex) flag. Any command using `grep -P` will exit with an error on a Mac client
box.

**Replacement patterns:**

```bash
# WRONG on macOS:
grep -P '"id"\s*:\s*"([^"]+)"'

# CORRECT — use python3 to parse JSON:
python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('id',''))"

# CORRECT — use jq if installed:
jq -r '.id // empty'

# CORRECT — use plain grep + sed if a simple pattern is enough:
grep '"id"' | sed 's/.*"id": *"\([^"]*\)".*/\1/'
```

All GHL API response parsing in shell scripts MUST use `python3 -m json.tool`,
`python3 -c "import json,sys; ..."`, or `jq`. Never `grep -P`.

---

## RULE 5 — Fail-fast preflight before any lookup

Before executing a contact lookup (any tier), run the fail-fast preflight in this order:

1. **Credential check:** verify `$GOHIGHLEVEL_API_KEY` and `$GOHIGHLEVEL_LOCATION_ID`
   are set and non-empty.

   ```bash
   [[ -z "$GOHIGHLEVEL_API_KEY" ]] && { echo "PREFLIGHT FAIL: GOHIGHLEVEL_API_KEY not set"; exit 1; }
   [[ -z "$GOHIGHLEVEL_LOCATION_ID" ]] && { echo "PREFLIGHT FAIL: GOHIGHLEVEL_LOCATION_ID not set"; exit 1; }
   ```

2. **Rate-limit probe (before bulk ops only):** if the lookup is part of a batch or
   bulk operation, make ONE cheap probe call and read `X-RateLimit-Daily-Remaining`.
   If remaining < 1000, stop and surface the reset time to the owner.

   ```bash
   REMAINING=$(curl -sS -i -X POST "https://services.leadconnectorhq.com/mcp/" \
     -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
     -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
     -H "Version: 2021-07-28" \
     -H "Accept: application/json, text/event-stream" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
     | grep -i "x-ratelimit-daily-remaining" | head -1 \
     | python3 -c "import sys; line=sys.stdin.read(); print(line.split(':')[1].strip() if ':' in line else '999999')")
   [[ "$REMAINING" -lt 1000 ]] && { echo "PREFLIGHT FAIL: Daily quota nearly exhausted ($REMAINING remaining). Stopping."; exit 1; }
   ```

3. **Tier 0 CLI availability check (when using caf):**

   ```bash
   command -v caf >/dev/null 2>&1 || { echo "PREFLIGHT WARN: caf not found — falling to Tier 1 MCP"; }
   ```

Single ad-hoc lookups (non-bulk) may skip the rate-limit probe but MUST always run
the credential check.

---

## RULE 6 — Two-axis routing: READ vs BUILD

The two most common GHL routing errors are (a) trying to BUILD through an MCP and
(b) routing a READ through Tier 4 (browser). This section states the authoritative
decision table.

### READ path (contact lookup, data retrieval, list operations)

| Primary | Fallback | Last resort |
|---|---|---|
| Tier 0: `caf contacts search/get` (CLI, works in orchestrator AND sub-agent) | Tier 1: orchestrator MCP `contacts_get-contacts` / `contacts_search-contacts` (deepseek-v4-flash, dual Accept header, Version: 2021-07-28) | Tier 3: raw HTTPS — mandatory dual Accept + correct Version header + no `grep -P` |

**Why Tier 0 CLI is preferred for lookups:**

The `caf` CLI is a subprocess — it runs identically in the orchestrator AND in spawned
sub-agents. It sidesteps the entire class of MCP-not-in-sub-agent / HTTP 406 / SSE
parsing / `grep -P` failures. When the CLI is installed and healthy, use it.

When the CLI is unavailable (not installed, `caf doctor` fails), fall to the
orchestrator MCP path. Never route a lookup to Tier 4 (browser) — that tier is for
UI-only flows and workflow-build backstops only.

### BUILD path (workflow create/edit, funnel page content)

| Primary | Backstop | Human-in-loop fallback |
|---|---|---|
| Tier 0: Skill 44 internal Build API (Firebase token required — `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`) | Tier 4: agent-browser → Playwright at `app.gohighlevel.com` (skill 03) — only when Firebase token is genuinely unavailable | Build-with-AI manual paste (skill 41 Layer 0) |

**Critical constraint — public API is read-only for workflows:**

The public API at `services.leadconnectorhq.com/workflows/` is **GET-only** — there is
no `POST` endpoint to create or edit a workflow via the public REST API or any MCP.
The community MCP advertises `ghl_create_workflow` / `ghl_update_workflow_actions`, but
those likely wrap an undocumented internal endpoint that may produce empty or
non-functional shells. Do NOT rely on community MCP workflow tools as a build path.

The ONLY verified programmatic workflow build path is Skill 44's internal Build API
(`backend.leadconnectorhq.com`, authed with a Firebase ID token derived from the
refresh token). See `44-convert-and-flow-operator/tools/engine/` for the implementation.

**Funnel page content is browser-only:**

There is no public API endpoint that creates funnel page content. Funnel page buildout
is always Tier 4 (agent-browser / Playwright via skill 06 and skill 03). This is not a
fallback — it is the ONLY path for page content.

### Decision table

```
Task: contact lookup
  → Tier 0 caf contacts search/get
  → (if caf unavailable) Tier 1 MCP in orchestrator (deepseek-v4-flash)
  → (if MCP unavailable) Tier 3 raw HTTPS (dual Accept + correct Version + python3 parsing)

Task: workflow BUILD or EDIT
  → Tier 0 Skill 44 internal Build API (requires Firebase refresh token)
  → Token health check first (50-min cache; TOKEN_REFRESH_FAILED = stop and re-grab)
  → (if no token) Tier 4 agent-browser / Playwright backstop + owner nudge

Task: funnel PAGE CONTENT deploy
  → Tier 4 browser (agent-browser FIRST, Playwright fallback) — always, no exception

Task: workflow READ / LIST / EXPORT / AUDIT
  → Tier 0 caf workflows list/get/export — ALWAYS start here
  → Escalate to Tier 1/2/3 only for what caf export cannot show (e.g. trigger-bucket state)

Task: product / invoice / subscription / billing / Voice AI / Phone System
  → Tier 2 community MCP (on-demand curl to $GHL_COMMUNITY_MCP_URL)
  → Never Tier 1 for these — the official MCP has no tools for them
```

---

## RULE 7 — Disclosure header is mandatory on every GHL response

Every response that surfaces GHL data MUST open with the tier disclosure:

```
[GHL tier used: N — tool_name]
```

For lookup paths specifically:

- `[GHL tier used: 0 — convertandflow contacts search]`
- `[GHL tier used: 1 — contacts_get-contacts]` (orchestrator MCP)
- `[GHL tier used: 3 (Tier 0 unavailable; Tier 1 N/A — sub-agent) — raw HTTPS GET /contacts/]`

Missing disclosure = protocol violation.

---

## Anti-patterns (hard failures)

The following are HARD FAILURES. If you catch yourself doing any of these, stop and
correct before proceeding:

- **Sub-agent calling an MCP tool** — sub-agents have no MCP injection. Use `caf` or
  raw HTTPS instead.
- **Raw HTTP without dual Accept** — missing `text/event-stream` in Accept causes HTTP
  406. Both values in the Accept header are mandatory.
- **`grep -P` in any shell script on a Mac client** — BSD grep has no `-P`. Use
  `python3 -c "import json,sys; ..."` or `jq`.
- **Metered `:cloud` model for a contact lookup** — lookups are cheap data-retrieval
  tasks. Use `deepseek-v4-flash` (direct) or equivalent free model.
- **Routing a workflow BUILD through the community MCP** — the public `/workflows/` API
  is read-only. The community MCP's `ghl_create_workflow` is unverified and likely
  non-functional. Use Skill 44 internal Build API.
- **Routing a lookup to Tier 4 (browser)** — the browser tier is for UI-only flows and
  workflow-build backstops. A contact lookup NEVER goes to the browser.
- **Skipping the fail-fast credential preflight** — if credentials are missing, the
  lookup will return an auth error that looks like a connectivity problem. Always check
  first.
- **Version header mismatch** — conversations/calendars/payments use `Version:
  2021-04-15`; contacts/locations/blogs use `Version: 2021-07-28`. Wrong version causes
  intermittent 400/401. Check `29-ghl-convert-and-flow/references/<module>.md`.

---

## Summary card (copy to AGENTS.md canonical state block)

```
GHL LOOKUP SOP (skill 36 / 2026-06-14):
- Lookup in orchestrator: Tier 0 caf → Tier 1 MCP (deepseek-v4-flash, dual Accept, Version: 2021-07-28) → Tier 3 raw HTTPS
- Sub-agent lookup: ONLY caf CLI or raw HTTPS — no MCP tools
- Raw HTTP: MUST include BOTH "Accept: application/json, text/event-stream" AND "Version: 2021-07-28" — missing text/event-stream = HTTP 406
- No grep -P on macOS — use python3 -c / jq
- Fail-fast preflight: check API_KEY + LOCATION_ID before any call
- BUILD = Skill 44 internal Build API (Firebase token) → Tier 4 browser backstop; NEVER build via MCP
- Funnel page content = browser-only (Tier 4) always
- No metered :cloud model for lookups — deepseek-v4-flash direct or free fallback
- Disclosure required: [GHL tier used: N — tool_name]
Full ref: 36-ghl-mcp-setup/GHL-LOOKUP-SOP.md
```
