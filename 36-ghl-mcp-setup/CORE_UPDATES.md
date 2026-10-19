# GHL MCP Setup — Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

---

## CREDENTIAL STORAGE — AUTHORITATIVE RULE

**This skill updates the canonical credential location for GHL.** Skill 05 (older versions) pointed to `~/clawd/secrets/.env`. As of skill 36 v1.0.0 and aligned with the agent's current AGENTS.md operating rules:

- **macOS canonical:** `~/.openclaw/secrets/.env`
- **VPS canonical:** `~/.openclaw/secrets/.env`
- **Secondary mirror:** `openclaw.json` `env.vars` (gateway reads from here at runtime)

Env var names: `GOHIGHLEVEL_API_KEY` (the Location PIT — legacy variable name kept for backwards compatibility) and `GOHIGHLEVEL_LOCATION_ID`.

If credentials still live at `~/clawd/secrets/.env`, migrate them to the canonical location during this skill's install (Action 2 of INSTALL.md).

All runtime code, API calls, and skill references must read from the canonical secrets path. The retired community MCP's `.env` (`~/mcp-servers/ghl-community-mcp/.env` or `/data/mcp-servers/...` on VPS) must not be created, refreshed, or copied. If a legacy tree is archived, archive a redacted manifest (key names only), never the secret-bearing `.env`.

---

## SOUL.md — NO UPDATE NEEDED

The GHL tier-escalation protocol is OPERATING LAW, not identity/personality, so
it lives in the SHARED AGENTS.md (see above) where sub-agents — including the
convert-and-flow-agent — actually inherit it. In the multi-agent model every
agent has its OWN SOUL.md but shares AGENTS.md + TOOLS.md; a protocol in the main
agent's SOUL.md never reaches sub-agents. SOUL.md is therefore left byte-identical
by this skill (matches the fleet convention skills 05/06/38/39/41 already state).

---

## AGENTS.md — UPDATE REQUIRED

Add this section. Adapt aliases to client white-label brand:

```
## GHL / [Client white-label] access order (skill 36)

[GHL, GoHighLevel, Go High Level, LeadConnector, {client name}] refer to the same platform.

### 🟢 Canonical current state — override stale session memory

| Fact | Current canonical value |
|---|---|
| Official MCP (Claude client) | `https://services.leadconnectorhq.com/mcp/anthropic/v2` — OAuth |
| Official MCP (ChatGPT/Codex) | `https://services.leadconnectorhq.com/mcp/openai/v2/` — OAuth |
| Transitional registration | `openclaw mcp set ghl-mcp` against the original `/mcp/` endpoint. Supported during migration; not the documented auth path |
| Documented catalog | Exactly four tools: `list_locations`, `search_operations`, `describe_operation`, `execute_operation` |
| Community MCP (old Tier 2) | **RETIRED.** Required state: no `ghl-community-mcp` registration, no loaded/enabled unit, no listener on `127.0.0.1:8765`, no `GHL_COMMUNITY_MCP_URL` |
| Retirement guard | A `RunAtLoad=true` job that is merely stopped is NOT retired; unload **and** disable it, and remove/make retirement-aware the probe |
| Name collision | The official `mcp.servers` entry is `ghl-mcp`; the retired community **systemd unit** is also `ghl-mcp`. Never act on the bare string |
| Preserved | Official MCP connection, **custom courier MCP**, shared credentials, customer data |
| Credentials | `~/.openclaw/secrets/.env`. `GOHIGHLEVEL_API_KEY` (location PIT — REST only), `GOHIGHLEVEL_LOCATION_ID`. Official MCP uses OAuth, not the PIT. |
| Tier 0 CLI | `caf` / `convertandflow` / `ghl` wrapper at `~/.openclaw/tools/convert-and-flow-cli/`; health = `caf doctor`. Owned by SKILL 44. |

## 🔴 GHL Tier Escalation Protocol

When asked to do anything involving GHL / GoHighLevel / Convert and Flow / LeadConnector / [client white-label name]:

1. **Tier order is binding. Do not skip tiers.** Workflow operations — **BUILD, MODIFY, and REVIEW/inspect/audit** — ALWAYS start at Tier 0 (caf). A REVIEW begins with `caf workflows export` (read); escalate to Tier 1/3 ONLY for the specific pieces export cannot return (trigger-bucket state, products/store/Voice-AI objects). For all other ops: Try Tier 0 FIRST for every operation the CLI covers. Fall to Tier 1 (official MCP `ghl-mcp`) for blogs and CLI gaps. Fall to Tier 3 (API + skill 29) for products/subscriptions/estimates/store/coupons/Voice AI/Phone System/Agent Studio and anything else the official MCP does not cover. Fall to Tier 4 (agent-browser, skill 03) or Tier 5 (Codex Computer Use) only as the UI-only / no-token backstop. **Tier 2 (community MCP) is retired — it is never a route.**

2. **The community service is OFF by design.** There is no `$GHL_COMMUNITY_MCP_URL` in the required end state. Do not start, probe, restart, or rebuild `ghl-community-mcp`; verify absence instead (no registration, no unit, no listener on `127.0.0.1:8765`).

3. **Session memory is not authoritative — the canonical state block in AGENTS.md is.** Before declaring a tier dead, re-read the canonical state block and verify your actual call matches. If you get 404 / connection refused, first hypothesis is "I used the wrong URL," not "the server is broken."

4. **Required disclosure — OPERATOR CHANNEL ONLY:** on the operator channel, prefix your final answer with `[GHL tier used: N — tool_name]` (include the chain if you fell through). Missing disclosure on the operator channel = protocol violation. **On any CLIENT-FACING reply, STRIP this header** (WE MOVE IN SILENCE) — it leaks internal tier/tool plumbing; the client sees only the result. See "Mandatory disclosure format" below.

5. **"It looked broken earlier" is not an excuse.** If a tier failed in earlier session work, attempt it fresh. Tier 1 recovery is a re-authorized OAuth connection plus a recorded `tools/list`, never a community-service restart. Tier 2 has nothing to recover — it is retired.

Full reference: [MASTER_FILES_FOLDER]/36-ghl-mcp-setup/ghl-mcp-setup-full.md

### Token-aware routing (skill 44 / Tier 0)

- Standard operations need only the PIT every client has — they ALWAYS run Tier 0.
- **Missing PIT or Location ID (GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_LOCATION_ID empty) at
  runtime -> BLOCK, do not silently no-op.** Name which one is missing and tell the owner
  exactly how to supply it: "I'm missing your GoHighLevel Private Integration Token /
  Location ID — Settings > Integrations > Private Integrations to create the PIT (starts
  with `pit-`), and Settings > Company > Locations for the 22-char Location ID. Send both
  and I'll wire them in and retry." Never invent data, never claim the platform is down.
  (Same discipline as the Firebase case below.)
- Workflow create/edit needs the Firebase refresh token:
  - present + healthy -> Tier 0 builds the workflow directly.
  - missing or dead -> reads/enrolls fall through Tiers 1-3; the BUILD falls to
    Tier 4 (agent-browser) as last resort, and the owner is nudged:
    "I need you to grab the Convert and Flow token to build workflows directly."
  - Never a silent failure.

### Rate-limit rule (binding on every tier, Tier 0 inherits verbatim)

- All tiers share ONE GHL backend bucket (documented production failure 2026-05-13).
- On a 429: read X-RateLimit-Daily-Reset, surface the reset time in plain English,
  and NEVER fall through tiers. A missing token falls through; a 429 does NOT, on
  any tier.

## GHL / Convert and Flow access order (skill 36)

| Tier | Path | Owning skill | Use for | Credential |
|---|---|---|---|---|
| 0 | Convert and Flow CLI (caf / convertandflow / ghl) | SKILL 44 | Everything the CLI covers: contacts, opportunities, calendars, conversations, documents, payments, forms, social, locations, workflows (list/get/export/REVIEW/inspect/audit). Tier 0 (caf) owns workflow build/edit/review — MCP workflow tools are escalation-only. | PIT (standard ops); Firebase token (workflow writes) |
| 1 | Official GHL MCP (`ghl-mcp`; client-specific OAuth v2 endpoints; four documented tools) | registered by SKILL 36 | Blogs; fallback for CLI gaps | **OAuth** (PIT bearer is an unverified compatibility mode) |
| 2 | **RETIRED — community GHL MCP** | none; verify absent | Nothing. Not a route. | n/a |
| 3 | Direct REST API | SKILL 29 | Products, subscriptions, estimates, store, coupons, Voice AI, Phone System, Agent Studio; anything no MCP covers; media uploads (POST /medias/upload-file) | PIT |
| 4 | Browser: agent-browser (Vercel) FIRST, Playwright fallback | SKILL 03 | UI-only flows; workflow-write backstop when no token; Mac token auto-re-grab recipe | Persistent logged-in profile |
| 5 | Codex Computer Use | codex sub-agent | Last resort, approval-gated, read-only by default | n/a |

Rules: Tier 0 first for covered ops. Media never routes to Tier 0. On 429: stop and surface reset time, never fall through. Missing Firebase token: fall through for reads, Tier 4 backstop for the build, auto-re-grab on Mac / owner nudge on VPS. Skill 35's internal pipeline is exempt. Quota pre-check before bulk writes on every tier. All surfaces share one backend bucket; the documented 100/10s and 200,000/day limits are REST's, and MCP publishes none.

### Four evidence levels for MCP — do not collapse them

| Level | What it means | Can this repo assert it? |
|---|---|---|
| **1. Documented endpoint** | Vendor docs publish the URL for a named client | **Yes** |
| **2. Documented catalog** | Vendor docs publish exactly four tool names | **Yes** — names only |
| **3. Account / tenant grant** | This account actually authorizes the connection and scopes | **No** — needs an authorized OAuth connect |
| **4. Actually observed on this box** | `tools/list` plus one real call, captured here | **No** — needs this box's receipt |

### Anti-patterns (documented past failures)

- ❌ "Tier 1 doesn't have X → Tier 3." Wrong reasoning. Use Tier 3 because Tier 1 does not cover the operation, not because REST "has" it. Tier 2 is retired and is never the answer.
- ❌ Hardcoding port 8000 or any literal port for Tier 2. There is no community URL any more; the required state is no listener on 8765.
- ❌ Restarting the community service because it "crashed earlier." It is retired. Do not start it.
- ❌ "CLI covers it but I'll use an MCP." Wrong. Tier 0 first for every covered op.
- ❌ Jumping to Tier 4 (browser) for a workflow-write when the Firebase token is
  present and healthy. Tier 4 is the backstop ONLY when the token is genuinely
  unavailable.
- ❌ "They said review the workflow → I will use a big MCP." Wrong. Review = Tier 0 `caf workflows export` first; escalate only for what export cannot show (e.g. trigger-bucket state). The retired community MCP is never a workflow-review route, and a tool count is never parity proof.
- ❌ Sub-agent calling an MCP tool. Sub-agents have no MCP injection — use `caf` CLI or raw HTTPS.
- ❌ Raw HTTP to the transitional `/mcp/` endpoint without the dual Accept header. Missing `text/event-stream` in Accept causes HTTP 406 (content-negotiation failure, NOT auth). Both values mandatory there: `Accept: application/json, text/event-stream`. Do not assume it transfers to the v2 client endpoints unverified, and do not add a global `Version` header.
- ❌ Using `grep -P` on a Mac client box. BSD grep has no -P flag. Use `python3 -c "import json,sys; ..."` or `jq`.
- ❌ Metered `:cloud` model for a contact lookup. Use the client's selected direct (non-metered) model, their configured default model, or a free fallback. Recommendation: a cheap, fast direct model, because lookups are cheap data-retrieval, not reasoning tasks.
- ❌ Building a workflow via any MCP. The official catalog has no authoring tool; `GET /workflows/` is a read. The retired community `ghl_create_workflow` was unverified. Use Skill 44 internal Build API.
- ❌ Routing a contact lookup to Tier 4 (browser). Browser = UI-only flows and workflow-build backstops only.

### GHL Lookup SOP — summary (2026-06-14)

```
- Lookup in orchestrator: Tier 0 caf → Tier 1 official MCP (OAuth connection; the client's selected lookup model or configured default) → Tier 3 raw HTTPS. Tier 2 is retired.
- Sub-agent lookup: ONLY caf CLI or raw HTTPS — MCP tools are NOT available in sub-agents
- Raw HTTP (transitional /mcp/ only): MUST send BOTH "Accept: application/json, text/event-stream" — missing text/event-stream = HTTP 406. Version is per operation, never a global default; the MCP endpoints document none.
- No grep -P on macOS — use python3 -c / jq
- Fail-fast preflight: verify GOHIGHLEVEL_API_KEY + GOHIGHLEVEL_LOCATION_ID before any call
- BUILD path: Skill 44 internal Build API (Firebase token) → Tier 4 browser backstop; NEVER build via any MCP
- Funnel page content: browser-only (Tier 4) — always, no exception
- No metered :cloud model for lookups: the client's selected direct model, their configured default, or a free fallback only
Full ref: [MASTER_FILES_FOLDER]/36-ghl-mcp-setup/GHL-LOOKUP-SOP.md
```

### Mandatory disclosure format — OPERATOR CHANNEL ONLY

The `[GHL tier used: N — tool_name]` header is an internal audit trail for the OPERATOR.
Prefix every GHL response **in the operator channel** with it. If you fell through tiers,
include the chain. Tier 0 format: `[GHL tier used: 0 — convertandflow <command>]`; on
fall-through show the chain, e.g. `[GHL tier used: 4 (Tier 0 build blocked: no Firebase
token) — agent-browser]`. Missing disclosure on the operator channel = protocol violation.

**WE MOVE IN SILENCE — strip this header from CLIENT-FACING replies.** When the reply goes
to a client (their Telegram, a coaching-persona reply, any customer-facing surface), do NOT
emit the tier header — it leaks internal plumbing (which tier/tool/fallback) the client
should never see. Answer with just the result. The header is for the operator's audit, not
the client's screen.

Full reference: [MASTER_FILES_FOLDER]/36-ghl-mcp-setup/ghl-mcp-setup-full.md
```

---

## TOOLS.md — UPDATE REQUIRED

Add this section (replace any prior "GHL MCP" section from skill 05/29):

```
## GHL MCP surfaces (skill 36)

Retained MCP surfaces:
- **`ghl-mcp`** — official connection. Documented endpoints are client-specific and use OAuth:
  Claude `https://services.leadconnectorhq.com/mcp/anthropic/v2`;
  ChatGPT/Codex `https://services.leadconnectorhq.com/mcp/openai/v2/`.
  Documented catalog: exactly four tools — `list_locations`, `search_operations`,
  `describe_operation`, `execute_operation`. A Claude model routed through OpenClaw is not
  proof of a Claude MCP client.
- **Custom courier MCP** — preserved; out of scope for skill 36.
- **`ghl-community-mcp`** — **RETIRED**. Required state: absent registration, no loaded or
  enabled unit, no listener on `127.0.0.1:8765`, no `GHL_COMMUNITY_MCP_URL`. Never restart,
  probe, or rebuild it.

Evidence levels: this repo asserts the documented endpoint and documented catalog (levels
1–2). Account grant and on-box observation (levels 3–4) live only in the box's own receipt.

Intent → route (historical tool ids are **UNVERIFIED**; operations on the official connection
are discovered with `search_operations`):

| Domain | Route | Historical tool names (not a catalog) |
|---|---|---|
| Contacts | Tier 0 CLI, else Tier 1 / Tier 3 | `contacts_get-contact`, `contacts_create-contact`, `contacts_search-contacts`, `contacts_upsert-contact` — generic add/save routes to upsert, explicit new-record only to create |
| Contacts (advanced) | Tier 3 REST | `search_contacts`, `bulk_update_contact_tags`, `get_duplicate_contact` |
| Products | Tier 0 CLI, else Tier 3 REST | `ghl_list_products`, `ghl_create_product`, `ghl_create_price`, `ghl_update_product` |
| Invoices | Tier 3 REST | `list_invoices`, `create_invoice`, `send_invoice`, `void_invoice` |
| Subscriptions | Tier 3 REST | `list_invoice_schedules`, `create_invoice_schedule` |
| Estimates | Tier 3 REST | `list_estimates`, `create_estimate`, `send_estimate` |
| Calendars | Tier 1 / Tier 3 | `calendars_get-calendar-events`, `calendars_get-appointment-notes` |
| Blogs | Tier 1 | `blogs_create-blog-post`, `blogs_update-blog-post` |
| Social Media | Tier 1 / Tier 3 | `social-media-posting_create-post`, `social-media-posting_get-account` |
| Voice AI / Phone | Tier 3 REST | `create_voice_ai_agent`, `ghl_buy_phone_number`, `ghl_list_phone_numbers` |
| Agent Studio | Tier 3 REST | `ghl_create_agent`, `ghl_deploy_agent`, `ghl_list_agents` |
| Workflows (read: list/get/export) | **Tier 0 (caf) first** | `caf workflows list/get/export` — **Tier 0 (caf) owns workflow build/edit/review**; escalate only for what `caf workflows export` cannot show (e.g. trigger-bucket state) |

There is no community `/tools` endpoint to discover against. For the official connection,
discover operations with `search_operations` and inspect them with `describe_operation`.

Version note: the `Version` header is chosen per operation from the operation page (documented
values include `v3`, `2023-02-21`, `2021-07-28`, `2021-04-15`, `legacy`). There is no global
header rule. `v4` workflow contracts are staging-only evidence.

Full reference: [MASTER_FILES_FOLDER]/36-ghl-mcp-setup/ghl-mcp-setup-full.md
```

---

## MEMORY.md — UPDATE REQUIRED

```
## GHL MCP Setup — Installed [DATE]

MCP surfaces (skill 36):

1. **Official GHL MCP** (`ghl-mcp`) — documented endpoints `https://services.leadconnectorhq.com/mcp/anthropic/v2` (Claude) and `https://services.leadconnectorhq.com/mcp/openai/v2/` (ChatGPT/Codex), **OAuth**. Documented catalog: four tools (`list_locations`, `search_operations`, `describe_operation`, `execute_operation`). The original `/mcp/` registration is transitional.

2. **Custom courier MCP** — preserved; not managed by skill 36.

3. **Community GHL MCP** (`ghl-community-mcp`) — **RETIRED [DATE]**. Verified off: no registration, no loaded/enabled unit, no listener on `127.0.0.1:8765`, no `GHL_COMMUNITY_MCP_URL`. Do not reinstall or rebuild it. Historical rollback reference only: mirror `trevorotts1/ghl-community-mcp-mirror`, pin `32628c979dd8f46e7952f85ce2d98f8028a26c32`, profile `curated` (43 crm tools, smoke `crm_list_workspaces`); restoration requires an explicit operator decision.

Credentials: `~/.openclaw/secrets/.env` on Mac and VPS. `GOHIGHLEVEL_API_KEY` (location PIT — REST only), `GOHIGHLEVEL_LOCATION_ID`. Official MCP uses OAuth, not the PIT.

Tier escalation: Convert and Flow CLI (Tier 0, skill 44) → Official MCP (Tier 1) → REST API + skill 29 (Tier 3) → agent-browser/Playwright (Tier 4, skill 03) → Codex Computer Use (Tier 5). Tier 2 is retired.

Disclosure header required on operator-channel GHL responses only: `[GHL tier used: N — tool_name]`.

Full reference: [MASTER_FILES_FOLDER]/36-ghl-mcp-setup/ghl-mcp-setup-full.md
QC script: [MASTER_FILES_FOLDER]/36-ghl-mcp-setup/qc-ghl-mcp-setup.sh
```

---

## IDENTITY.md — NO UPDATE NEEDED

---

## HEARTBEAT.md — NO UPDATE NEEDED

---

## USER.md — NO UPDATE NEEDED

(Unless the client has a white-label brand name worth documenting there — in which case add a single line like "Convert and Flow = our white-label name for GHL".)
