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

## SOUL.md — UPDATE REQUIRED

This skill adds a cardinal behavioral rule. Append after any existing 🔴 protocols:

```
## 🔴 GHL Tier Escalation Protocol

When asked to do anything involving GHL / GoHighLevel / Convert and Flow / LeadConnector / [client white-label name]:

1. **Tier order is binding. Do not skip tiers.** Try Tier 1 (official MCP `ghl-mcp`) first. Fall to Tier 2 (community MCP `ghl-community-mcp`) if Tier 1 lacks the tool. Fall to Tier 3 (API + skill 29) only if neither MCP covers it. Fall to Tier 4 (Playwright) or Tier 5 (Codex Computer Use) only if Tier 3 fails fresh.

2. **Always use `$GHL_COMMUNITY_MCP_URL`** in shell commands for Tier 2. Never type a literal port number. Hardcoded ports from session memory have caused documented failures.

3. **Session memory is not authoritative — the canonical state block in AGENTS.md is.** Before declaring a tier dead, re-read the canonical state block and verify your actual call matches. If you get 404 / connection refused, first hypothesis is "I used the wrong URL," not "the server is broken."

4. **Required disclosure on every GHL response:** prefix your final answer with `[GHL tier used: N — tool_name]`. If you fell through tiers, include the chain. Missing disclosure = protocol violation.

5. **"It looked broken earlier" is not an excuse.** If a tier crashed in earlier session work, attempt it fresh. Recover with `launchctl kickstart gui/$(id -u)/com.clawd.ghl-mcp` (Mac) or `sudo systemctl restart ghl-mcp` (Linux) before falling through.

Full reference: [MASTER_FILES_FOLDER]/36-ghl-mcp-setup/ghl-mcp-setup-full.md
```

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

### Tier order (try in sequence; do not skip)

- **Tier 1:** `ghl-mcp` — 36 tools (contacts, calendars, conversations, opportunities, social media, blogs, emails, locations, read-only payments)
- **Tier 2:** `ghl-community-mcp` — 588 tools (products, invoices, billing, subscriptions, estimates, store, coupons, Voice AI, Phone System, Agent Studio, workflows)
- **Tier 3:** REST API + skill 29 references at `~/Downloads/openclaw-master-files/29-ghl-convert-and-flow/references/[module].md`
- **Tier 4:** Playwright browser, `launchPersistentContext`
- **Tier 5:** Codex Computer Use, `codex/gpt-5.5`, 45-min default timeout

### Anti-patterns (documented past failures)

- ❌ "Tier 1 doesn't have X → Tier 3." Wrong. Use Tier 2.
- ❌ Hardcoding port 8000 or any literal port for Tier 2. Always `$GHL_COMMUNITY_MCP_URL`.
- ❌ Skipping Tier 2 because it crashed earlier. Restart and retry.

### Mandatory disclosure format

Every GHL response prefix: `[GHL tier used: N — tool_name]`. If fell through: include chain.

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

5-tier escalation: MCP official → MCP community → REST API + skill 29 → Playwright → Codex Computer Use.

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
