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

MCP tool calls **are available only in the orchestrating agent session**. Spawned sub-agents
receive NO injected MCP tools.

Two MCP surfaces exist and they are not the same catalog:

- **Official MCP (documented, Tier 1):** four tools — `list_locations`, `search_operations`,
  `describe_operation`, `execute_operation`. Contact lookup is `execute_operation` with the
  operation id `contacts.search` (or `contacts.get`), discovered through `search_operations`
  and schema-captured with `describe_operation`.
- **Transitional `/mcp/` registration:** per-operation names such as
  `contacts_get-contacts` / `contacts_search-contacts`. These are **UNVERIFIED** against the
  v2 catalog and are never presented as the documented interface.

**What this means in practice:**

- **Orchestrator:** may call `execute_operation` for `contacts.search` / `contacts.get`.
- **Sub-agent:** MUST use the Tier 0 CLI (`caf contacts search <query>`) or a raw
  HTTPS call to `services.leadconnectorhq.com`. Never assume MCP tools exist inside a
  sub-agent.

**Anti-patterns:**

- A sub-agent that calls any MCP tool (`execute_operation` or a legacy `contacts_*` name) —
  this will fail silently or return a tool-not-found error.
- An orchestrator that spawns a sub-agent and tells it "use the MCP to look up the
  contact" — the sub-agent cannot.
- Teaching `contacts_get-contacts` / `contacts_search-contacts` as the official catalog —
  the documented catalog is the four tools above.

**Correct pattern:**

```
Orchestrator: execute_operation {operationId: "contacts.search"} → pass contactId to sub-agent
Sub-agent:    call `caf contacts get <contactId>` (CLI) OR public REST (Tier 3)
```

---

## RULE 2: Lookup model: the client's choice, or their configured default model (direct, low-cost; never a metered `:cloud` model)

When the orchestrator calls the official MCP (`execute_operation` with `contacts.search` or
`contacts.get`) and a model inference step is needed to parse the result or decide the next
action:

- **Model:** the client's choice, or their configured default model, where it is a direct
  (non-`:cloud`) model. If neither is set, ask the client which model to use for lookups.
- **Recommendation:** a direct, cheap, fast model, NOT a `:cloud` metered model, because a
  contact lookup is a data-retrieval task, not a reasoning task.
- **Fallback:** any free/low-cost provider available in the session.
- **NEVER:** use a `:cloud` metered model for a cheap read-only lookup. Metered cloud
  models for lookups waste quota.

---

## RULE 3 — Raw HTTP fallback is public REST; Version is per operation

When neither the CLI (Tier 0) nor an MCP tool is available, the fallback (Tier 3) is the
**public REST API** at `https://services.leadconnectorhq.com`, authenticated with the
location PIT as `Authorization: Bearer $GOHIGHLEVEL_API_KEY`.

**The `Version` header is set per operation.** It is not one global value and must not be
hardcoded for all modules. The authoritative registry is the operation's official page
`https://marketplace.gohighlevel.com/docs/ghl/<module>/<operation-slug>/` (GHL modernization
contract ledger, 2026-10-18) — read the `Ver` column of the operation row
being called. `describe_operation` and `29-ghl-convert-and-flow/references/<module>.md`
are the live cross-checks.

| Operation family (examples) | Frozen Ver |
|---|---|
| `contacts.search`, `contacts.get` | `v3` |
| `conversations.messages.send`, `calendars.list` | `v3` |
| `products.*`, `invoices.*`, `payments/transactions`, `subscriptions.*`, `coupons.*` | `v3` (permitted rollback literal `2021-07-28` for payments) |
| `funnels.list`, `funnels.pages.list` | `v3` (alternate `2023-02-21`) |
| `social.accounts.list` … `social.oauth.accounts.list` | `2021-07-28` (alternate `v3`) |
| `social.statistics`, `social.queues.*`, `social.comments.*` | `v3` |
| `workflows.list`, `workflows.enroll`, `workflows.remove` | `v3` |
| `workflows.definition.*`, `workflows.status.publish` | `v4` — **staging-only**, disabled |

Sending the wrong version for an operation returns 400 or 401.

**Correct raw-HTTP example (contacts lookup):**

```bash
curl -sS -X POST "https://services.leadconnectorhq.com/contacts/search" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: v3" \
  -H "Content-Type: application/json" \
  -d '{"locationId":"'"$GOHIGHLEVEL_LOCATION_ID"'","limit":5}' \
  | python3 -m json.tool
```

**Historical note — the transitional `/mcp/` surface.** Before the v2 OAuth endpoints, raw
calls went to `https://services.leadconnectorhq.com/mcp/` with
`Accept: application/json, text/event-stream`, `locationId`, and a `Version` header.
That dual-Accept requirement belonged to that JSON-RPC surface and is **not** a REST
requirement. The endpoint is now transitional; per-operation tool names there are
UNVERIFIED as the v2 catalog. Do not teach the dual Accept header as a REST rule.

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

1. **Credential check:** verify `$GOHIGHLEVEL_API_KEY` (the Location PIT) and
   `$GOHIGHLEVEL_LOCATION_ID` are set and non-empty.

   In a SHELL SCRIPT, fail fast (operator-facing):

   ```bash
   [[ -z "$GOHIGHLEVEL_API_KEY" ]] && { echo "PREFLIGHT FAIL: GOHIGHLEVEL_API_KEY not set"; exit 1; }
   [[ -z "$GOHIGHLEVEL_LOCATION_ID" ]] && { echo "PREFLIGHT FAIL: GOHIGHLEVEL_LOCATION_ID not set"; exit 1; }
   ```

   **RUNTIME missing-credential grace (agent answering a request — NOT a script).**
   When the agent itself hits an empty `GOHIGHLEVEL_API_KEY` or `GOHIGHLEVEL_LOCATION_ID`
   while trying to serve a GHL request, it MUST **BLOCK and ask** — never silently no-op,
   never invent data, never claim the platform is "down." Name exactly what is missing and
   how to supply it (mirror the Firebase-token nudge in CORE_UPDATES.md). Say to the owner:

   > "I can't reach your GoHighLevel account yet — I'm missing your **[Private Integration
   > Token / Location ID — name whichever is empty]**. To add it: GHL → Settings →
   > Integrations → Private Integrations → create one named 'MCP Server Integration' with
   > the GHL scopes, copy the token (starts with `pit-`); and your Location ID from
   > Settings → Company → Locations (22 characters). Send both and I'll wire them in and
   > retry. Until then I can't run this request."

   This is the same discipline as the missing-Firebase-token case: **a missing credential
   BLOCKS with a named, actionable remediation — never a silent failure.** (A 429 is
   different: on a 429 you STOP and surface the reset time; you do NOT ask for credentials.)

2. **Rate-limit probe (before bulk ops only):** if the lookup is part of a batch or
   bulk operation, make ONE cheap probe call and read `X-RateLimit-Daily-Remaining`.
   If remaining < 1000, stop and surface the reset time to the owner.

   ```bash
   REMAINING=$(curl -sS -i "https://services.leadconnectorhq.com/products/?locationId=$GOHIGHLEVEL_LOCATION_ID&limit=1" \
     -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
     -H "Version: v3" \
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
| Tier 0: `caf contacts search/get` (CLI, works in orchestrator AND sub-agent) | Tier 1: official MCP `execute_operation` with `contacts.search` / `contacts.get` (ids discovered via `search_operations`, schema captured via `describe_operation`; the client's selected lookup model or configured default) | Tier 3: public REST: PIT bearer + the operation's own `Version` (`GU-004` §5) + no `grep -P` |

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
| Tier 0: Skill 44 internal Build API (Firebase token required — `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`) | Tier 4: Skill 6's GATED, MANAGED Automations builder (`06-ghl-install-pages/tools/ghl_workflow_builder.py` — routed through the `browser_manager.sh` singleton gateway, gates in `tools/gates.json` / `SELECTORS-LIVE-automations.md`) — only when the Firebase token is unread/misconfigured | Build-with-AI manual paste (skill 41 Layer 0) |

**Tier-4 workflow-build routing (P3-08 — corrected):** Tier-4 workflow BUILD does **NOT** freehand-navigate the Automations UI with bare agent-browser/Playwright and zero captured selectors — that violates Skill 6's own law ("NO invented CSS is shipped as fact"). It routes through Skill 6's **gated, managed** builder (the designated path, IMPLEMENTED): `06-ghl-install-pages/tools/ghl_workflow_builder.py`, which drives the Automations builder UI through the ONE `browser_manager.sh` singleton gateway (one session, lock=1, TTL, guaranteed teardown, reaper backstop — the same discipline every other Skill 6 builder uses), resolving its steps from the `automations_builder_gates` registry in `tools/gates.json`. Bare agent-browser at `app.gohighlevel.com` for workflow build is retired. *(Implementation status, P3-08: the HARNESS is built and unit-tested against a mocked gateway — `06-ghl-install-pages/tests/test_ghl_workflow_builder.py` proves a token-unset build drives the gated path, quotes the built workflow id, and tears the singleton session down with zero orphan engines; `python3 06-ghl-install-pages/tools/ghl_workflow_builder.py --selftest` is the runnable proof. The Automations step selectors ship `status: runtime` — the harness resolves them against the LIVE DOM via accessibility role/name find hints, per Skill 6's law they are NOT captured CSS asserted as fact; a live-capture hardening pass on the operator's own GHL location flips each to `captured` in `SELECTORS-LIVE-automations.md` (the same follow-on every runtime gate gets). The CI guard protecting this path is live — `06-ghl-install-pages/` and `44-convert-and-flow-operator/` are scan roots of `scripts/guard-agent-browser-managed.sh`. If a required gate is ever absent, the harness REFUSES (`MissingGateError`) rather than freehand-navigate. Skill 41 Layer 0 Build-with-AI paste remains the human-in-loop fallback when even the managed browser session cannot seed.)* **Token circularity (important):** Tier 4 only helps when the Firebase token is unread/misconfigured — the browser session it needs is seeded from the SAME Firebase refresh token whose absence triggers Tier 4. A GENUINELY dead/revoked/expired token does NOT route to Tier 4; it routes to `06-ghl-install-pages/tools/ghl_auth.py`'s gated Tier-2 email-2FA self-heal, which mints a fresh token so the next run is Tier 0 again. See `44-convert-and-flow-operator/SKILL.md` → "Workflow BUILD and EDIT" for the full token-circularity note. (Funnel PAGE content remains browser-only via Skill 6/03, unchanged.)

**Critical constraint — public API is read-only for workflows:**

The public API at `services.leadconnectorhq.com/workflows/` is **GET-only** for authoring
(`workflows.list`; `workflows.enroll` and `workflows.remove` are contact mutations, not
authoring). There is no verified `POST` to create or edit a workflow via public REST or
the official MCP. The frozen `workflows.definition.*` rows exist only at `v4`, which is
**staging-only and disabled**.

The **retired** community MCP historically shipped `ghl_create_workflow` /
`ghl_update_workflow_actions`. Those names are historical: they wrapped an undocumented
internal endpoint and were unverified. The transport is retired — do not route a build
through it, and do not treat those names as a build path.

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
  → (if caf unavailable) Tier 1 official MCP execute_operation (contacts.search / contacts.get; the client's selected lookup model or configured default)
  → (if MCP unavailable) Tier 3 public REST (PIT bearer + the operation's own Version + python3 parsing)

Task: workflow BUILD or EDIT
  → Tier 0 Skill 44 internal Build API (requires Firebase refresh token)
  → Token health check first (50-min cache; TOKEN_REFRESH_FAILED = stop and re-grab)
  → (if token UNREAD/misconfigured) Tier 4 = Skill 6 gated managed Automations
    builder (ghl_workflow_builder.py via browser_manager.sh) + owner nudge
  → (if token GENUINELY dead/revoked/expired) NOT Tier 4 — route to ghl_auth.py
    Tier-2 email-2FA self-heal, which mints a fresh token → next run is Tier 0

Task: funnel PAGE CONTENT deploy
  → Tier 4 browser (agent-browser FIRST, Playwright fallback) — always, no exception

Task: workflow READ / LIST / EXPORT / AUDIT
  → Tier 0 caf workflows list/get/export — ALWAYS start here
  → Escalate to Tier 1/3 only for what caf export cannot show (e.g. trigger-bucket state)

Task: product / invoice / subscription / billing
  → Tier 3 public REST with the frozen operation id (GU-004 §5: products.*, invoices.*, subscriptions.*, transactions.*, coupons.*)
  → Never Tier 1 for these — the documented official MCP catalog is four tools, none of them commerce operations
  → Voice AI / Phone System: no audited operation ids — report a capability gap; do not invent one
  → The retired community MCP is never a route
```

---

## RULE 7 — Disclosure header is mandatory on every GHL response

Every response that surfaces GHL data MUST open with the tier disclosure:

```
[GHL tier used: N — tool_name]
```

For lookup paths specifically:

- `[GHL tier used: 0 — convertandflow contacts search]`
- `[GHL tier used: 1 — execute_operation contacts.search]` (orchestrator MCP)
- `[GHL tier used: 3 (Tier 0 unavailable; Tier 1 N/A — sub-agent) — public REST POST /contacts/search]`

Missing disclosure = protocol violation.

---

## Anti-patterns (hard failures)

The following are HARD FAILURES. If you catch yourself doing any of these, stop and
correct before proceeding:

- **Sub-agent calling an MCP tool** — sub-agents have no MCP injection. Use `caf` or
  public REST instead.
- **Treating the transitional dual-Accept MCP rule as a REST rule** — public REST does not
  require `Accept: application/json, text/event-stream`. That rule belonged to the
  transitional `/mcp/` JSON-RPC surface, where omitting `text/event-stream` returned HTTP 406.
- **`grep -P` in any shell script on a Mac client** — BSD grep has no `-P`. Use
  `python3 -c "import json,sys; ..."` or `jq`.
- **Metered `:cloud` model for a contact lookup** — lookups are cheap data-retrieval
  tasks. Use the client's selected direct (non-metered) model, their configured default
  model, or an equivalent free model.
- **Routing a workflow BUILD through the retired community MCP** — the public `/workflows/`
  API is GET-only for authoring, and the community transport is retired. V4 workflow
  definition endpoints are staging-only and disabled. Use Skill 44 internal Build API.
- **Routing a lookup to Tier 4 (browser)** — the browser tier is for UI-only flows and
  workflow-build backstops. A contact lookup NEVER goes to the browser.
- **Skipping the fail-fast credential preflight** — if credentials are missing, the
  lookup will return an auth error that looks like a connectivity problem. Always check
  first.
- **A single global `Version` header** — version is per operation. Read the `Ver` column of
  the operation row on the operation's official page `https://marketplace.gohighlevel.com/docs/ghl/<module>/<operation-slug>/` (GHL modernization contract ledger, 2026-10-18). Do not hardcode one
  value for every module; wrong version causes intermittent 400/401. Check
  `29-ghl-convert-and-flow/references/<module>.md` too.

---

## Summary card (copy to AGENTS.md canonical state block)

```
GHL LOOKUP SOP (skill 36 / 2026-06-14):
- Lookup in orchestrator: Tier 0 caf → Tier 1 official MCP execute_operation (contacts.search / contacts.get; the client's selected lookup model or configured default) → Tier 3 public REST
- Sub-agent lookup: ONLY caf CLI or public REST — no MCP tools
- REST Version is PER OPERATION — read the "Ver" column on the operation's official page https://marketplace.gohighlevel.com/docs/ghl/<module>/<operation-slug>/ (GHL modernization contract ledger, 2026-10-18); never hardcode one value for all modules
- The dual Accept header belongs to the transitional /mcp/ surface only (missing text/event-stream there = HTTP 406), NOT to REST
- No grep -P on macOS — use python3 -c / jq
- Fail-fast preflight: check API_KEY + LOCATION_ID before any call
- BUILD = Skill 44 internal Build API (Firebase token) → Tier 4 = Skill 6 GATED managed builder (ghl_workflow_builder.py via browser_manager.sh), NOT bare agent-browser; genuinely dead token → ghl_auth.py Tier-2 self-heal, NOT Tier 4; NEVER build via MCP
- Funnel page content = browser-only (Tier 4) always
- No metered :cloud model for lookups: the client's selected direct model, their configured default, or a free fallback
- Disclosure required: [GHL tier used: N — tool_name]
- Community MCP is RETIRED: verify registration, unit, listener and env var are absent; never a route
Full ref: 36-ghl-mcp-setup/GHL-LOOKUP-SOP.md
```
