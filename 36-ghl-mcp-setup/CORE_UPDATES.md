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

All runtime code, API calls, and skill references must read from the canonical secrets path. The community MCP at `~/mcp-servers/ghl-community-mcp/.env` (or `/data/mcp-servers/...` on VPS) gets a copy of the PIT for its own runtime — that copy stays in sync via the install script.

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
| Community MCP base URL env var | `$GHL_COMMUNITY_MCP_URL` (always use this, never hardcode a port) |
| Health probe | `curl $GHL_COMMUNITY_MCP_URL/health` |
| MCP endpoint | `$GHL_COMMUNITY_MCP_URL/mcp` (streamable-http) |
| REST execute (debug) | `POST $GHL_COMMUNITY_MCP_URL/execute` with `{"name":"tool","arguments":{...}}` |
| Live tool discovery | `curl $GHL_COMMUNITY_MCP_URL/tools` |
| Lifecycle | macOS: launchd `~/Library/LaunchAgents/com.clawd.ghl-mcp.plist`. Linux: systemd `ghl-mcp.service`. |
| Restart | macOS: `launchctl kickstart gui/$(id -u)/com.clawd.ghl-mcp`. Linux: `sudo systemctl restart ghl-mcp`. |
| Credentials | `~/.openclaw/secrets/.env` (Mac) / `~/.openclaw/secrets/.env` (VPS). Env vars: `GOHIGHLEVEL_API_KEY` (PIT), `GOHIGHLEVEL_LOCATION_ID`. |
| Tier 0 CLI | `caf` / `convertandflow` / `ghl` wrapper at `~/.openclaw/tools/convert-and-flow-cli/`; health = `caf doctor`. Owned by SKILL 44. |

## 🔴 GHL Tier Escalation Protocol

When asked to do anything involving GHL / GoHighLevel / Convert and Flow / LeadConnector / [client white-label name]:

1. **Tier order is binding. Do not skip tiers.** Try Tier 0 (Convert and Flow CLI, skill 44) FIRST for every operation the CLI covers. Fall to Tier 1 (official MCP `ghl-mcp`) for blogs and CLI gaps. Fall to Tier 2 (community MCP `ghl-community-mcp`, on-demand via curl) for products/subscriptions/estimates/store/coupons/Voice AI/Phone System/Agent Studio. Fall to Tier 3 (API + skill 29) only if neither MCP covers it. Fall to Tier 4 (agent-browser, skill 03) or Tier 5 (Codex Computer Use) only as the UI-only / no-token backstop.

2. **Always use `$GHL_COMMUNITY_MCP_URL`** in shell commands for Tier 2. Never type a literal port number. Hardcoded ports from session memory have caused documented failures.

3. **Session memory is not authoritative — the canonical state block in AGENTS.md is.** Before declaring a tier dead, re-read the canonical state block and verify your actual call matches. If you get 404 / connection refused, first hypothesis is "I used the wrong URL," not "the server is broken."

4. **Required disclosure on every GHL response:** prefix your final answer with `[GHL tier used: N — tool_name]`. If you fell through tiers, include the chain. Missing disclosure = protocol violation.

5. **"It looked broken earlier" is not an excuse.** If a tier crashed in earlier session work, attempt it fresh. Recover with `launchctl kickstart gui/$(id -u)/com.clawd.ghl-mcp` (Mac) or `sudo systemctl restart ghl-mcp` (Linux) before falling through.

Full reference: [MASTER_FILES_FOLDER]/36-ghl-mcp-setup/ghl-mcp-setup-full.md

### Token-aware routing (skill 44 / Tier 0)

- Standard operations need only the PIT every client has — they ALWAYS run Tier 0.
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
| 0 | Convert and Flow CLI (caf / convertandflow / ghl) | SKILL 44 | Everything the CLI covers: contacts, opportunities, calendars, conversations, documents, payments, forms, social, locations, workflows | PIT (standard ops); Firebase token (workflow writes) |
| 1 | Official GHL MCP (ghl-mcp) | registered by SKILL 36 | Blogs; fallback for CLI gaps | PIT |
| 2 | Community GHL MCP, ON-DEMAND via curl | installed by SKILL 36 | Products, subscriptions, estimates, store, coupons, Voice AI, Phone System, Agent Studio | PIT |
| 3 | Direct REST API | SKILL 29 | Anything no MCP covers; media uploads (POST /medias/upload-file) | PIT |
| 4 | Browser: agent-browser (Vercel) FIRST, Playwright fallback | SKILL 03 | UI-only flows; workflow-write backstop when no token; Mac token auto-re-grab recipe | Persistent logged-in profile |
| 5 | Codex Computer Use | codex sub-agent | Last resort, approval-gated, read-only by default | n/a |

Rules: Tier 0 first for covered ops. Media never routes to Tier 0. On 429: stop and surface reset time, never fall through. Missing Firebase token: fall through for reads, Tier 4 backstop for the build, auto-re-grab on Mac / owner nudge on VPS. Skill 35's internal pipeline is exempt. Quota pre-check before bulk writes on every tier. Before any bulk write on any tier, run the quota pre-check; all tiers share one daily bucket.

### Anti-patterns (documented past failures)

- ❌ "Tier 1 doesn't have X → Tier 3." Wrong. Use Tier 2.
- ❌ Hardcoding port 8000 or any literal port for Tier 2. Always `$GHL_COMMUNITY_MCP_URL`.
- ❌ Skipping Tier 2 because it crashed earlier. Restart and retry.
- ❌ "CLI covers it but I'll use an MCP." Wrong. Tier 0 first for every covered op.
- ❌ Jumping to Tier 4 (browser) for a workflow-write when the Firebase token is
  present and healthy. Tier 4 is the backstop ONLY when the token is genuinely
  unavailable.

### Mandatory disclosure format

Every GHL response prefix: `[GHL tier used: N — tool_name]`. If fell through: include chain. Tier 0 format: `[GHL tier used: 0 — convertandflow <command>]`; on fall-through show the chain, e.g. `[GHL tier used: 4 (Tier 0 build blocked: no Firebase token) — agent-browser]`.

Full reference: [MASTER_FILES_FOLDER]/36-ghl-mcp-setup/ghl-mcp-setup-full.md
```

---

## TOOLS.md — UPDATE REQUIRED

Add this section (replace any prior "GHL MCP" section from skill 05/29):

```
## GHL MCPs (skill 36)

Two MCPs registered:
- **`ghl-mcp`** — official, hosted, 36 tools, stateless protocol
- **`ghl-community-mcp`** — local, 588 tools, BusyBee3333 2026 fork

Base URL env var: `$GHL_COMMUNITY_MCP_URL` (always reference this — never hardcode port).

Common tool name lookup:

| Domain | Tier | Tools |
|---|---|---|
| Contacts (basic) | 1 | `contacts_get-contact`, `contacts_create-contact`, `contacts_search-contacts`, `contacts_upsert-contact` |
| Contacts (advanced) | 2 | `search_contacts`, `bulk_update_contact_tags`, `get_duplicate_contact` |
| Products | 2 | `ghl_list_products`, `ghl_create_product`, `ghl_create_price`, `ghl_update_product` |
| Invoices | 2 | `list_invoices`, `create_invoice`, `send_invoice`, `void_invoice` |
| Subscriptions | 2 | `list_invoice_schedules`, `create_invoice_schedule`, `auto_payment_invoice_schedule` |
| Estimates | 2 | `list_estimates`, `create_estimate`, `send_estimate` |
| Calendars | 1 | `calendars_get-calendar-events`, `calendars_get-appointment-notes` |
| Blogs | 1 | `blogs_create-blog-post`, `blogs_update-blog-post` |
| Social Media | 1 | `social-media-posting_create-post`, `social-media-posting_get-account` |
| Voice AI / Phone | 2 | `create_voice_ai_agent`, `ghl_buy_phone_number`, `ghl_list_phone_numbers` |
| Agent Studio | 2 | `ghl_create_agent`, `ghl_deploy_agent`, `ghl_list_agents` |

For anything not above: `curl $GHL_COMMUNITY_MCP_URL/tools | python3 -m json.tool` for live discovery.

Full reference: [MASTER_FILES_FOLDER]/36-ghl-mcp-setup/ghl-mcp-setup-full.md
```

---

## MEMORY.md — UPDATE REQUIRED

```
## GHL MCP Setup — Installed [DATE]

Two MCP servers configured (skill 36):

1. **Official GHL MCP** (`ghl-mcp`) — `https://services.leadconnectorhq.com/mcp/`, 36 tools, stateless.

2. **Community GHL MCP** (`ghl-community-mcp`) — BusyBee3333 2026 fork, 588 tools. Local at `$GHL_COMMUNITY_MCP_URL`. Runs via launchd (macOS) or systemd (Linux). Repo at `~/mcp-servers/ghl-community-mcp/` (Mac) or `/data/mcp-servers/ghl-community-mcp/` (VPS).

Credentials: `~/.openclaw/secrets/.env` (Mac) / `~/.openclaw/secrets/.env` (VPS). Env vars: `GOHIGHLEVEL_API_KEY` (PIT), `GOHIGHLEVEL_LOCATION_ID`.

6-tier escalation: Convert and Flow CLI (Tier 0, skill 44) → MCP official (Tier 1) → MCP community on-demand (Tier 2) → REST API + skill 29 (Tier 3) → agent-browser/Playwright (Tier 4, skill 03) → Codex Computer Use (Tier 5).

Disclosure header required on every GHL response: `[GHL tier used: N — tool_name]`.

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
