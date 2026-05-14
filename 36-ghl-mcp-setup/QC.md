# QC Checklist: GHL MCP Setup (Skill 36)

## 1. Purpose

Verifies that the 5-tier GHL access chain is fully installed and routing correctly: Official MCP (Tier 1), Community MCP (Tier 2), REST API fallback (Tier 3), Playwright (Tier 4), Codex Computer Use (Tier 5). Confirms the canonical-state block, env vars, disclosure protocol, and platform-aware lifecycle (launchd / systemd) are all in place.

## 2. Installation Checks

- [ ] Skill folder exists with all 10 files: SKILL.md, INSTALL.md, INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md, QC.md, CHANGELOG.md, skill-version.txt, ghl-mcp-setup-full.md, ghl-mcp-setup.skill
- [ ] Platform detected correctly (`~/.openclaw` → VPS, else desktop)
- [ ] `$CANONICAL_MASTER` resolves to a real openclaw-master-files folder
- [ ] OpenClaw MCP entries `ghl-mcp` AND `ghl-community-mcp` both present in `openclaw mcp list`
- [ ] Env var `GHL_COMMUNITY_MCP_URL` is set in `openclaw.json` `env.vars`
- [ ] Repo `~/mcp-servers/ghl-community-mcp` (Mac) or `/data/mcp-servers/ghl-community-mcp` (VPS) is cloned, has `.git`, has `dist/main.js`
- [ ] `.env` exists in MCP repo with `chmod 600`, contains `GHL_API_KEY` + `GHL_LOCATION_ID` + `MCP_SERVER_PORT`
- [ ] Lifecycle service installed: launchd plist (macOS) at `~/Library/LaunchAgents/com.clawd.ghl-mcp.plist` OR systemd unit (Linux) at `/etc/systemd/system/ghl-mcp.service`
- [ ] Service is currently running (launchd `state = running` OR systemd `active (running)`)
- [ ] This document copied to `$MASTER_FILES_DIR/36-ghl-mcp-setup/`

## 3. Dependency Checks

- [ ] Skill 01 (Teach Yourself Protocol) installed
- [ ] Skill 02 (Back Yourself Up Protocol) installed
- [ ] Skill 05 (GHL Setup) installed AND credential path migrated to canonical (`~/.openclaw/secrets/.env` not `~/clawd/secrets/.env`)
- [ ] Skill 29 (GHL Convert and Flow) installed with `references/` subfolder populated
- [ ] Node.js ≥ 20 available (`node --version`)
- [ ] curl and python3 available
- [ ] `lsof` available (used for port collision check)
- [ ] An active GoHighLevel/Convert and Flow account with PIT that has all required scopes

## 4. Key Detection

The agent MUST find the canonical credentials by searching in this order:
- [ ] `$SECRETS_ENV` (canonical, platform-resolved)
- [ ] `openclaw.json` `env.vars.GOHIGHLEVEL_API_KEY` and `env.vars.GOHIGHLEVEL_LOCATION_ID`
- [ ] Legacy `$WORKSPACE/secrets/.env` (skill 05 pre-v2.0 location — must be migrated if found)
- [ ] `printenv | grep -iE "GHL|GOHIGH"`
- [ ] `~/.env`
- [ ] Repo-level env files in workspace
- [ ] Existing MCP server repo `.env`

QC fails if:
- The installer asks for credentials WITHOUT first searching all locations above
- An "API key" is requested instead of a "Private Integration Token (PIT)"
- Credentials are stored only to legacy location and not the canonical `~/.openclaw/secrets/.env`

## 5. Functional Checks

### Tier 1 — Official MCP

- [ ] `openclaw mcp show ghl-mcp` returns the streamable-http config with PIT + locationId headers
- [ ] `tools/list` call returns 36 tools
- [ ] `locations_get-location` call returns real location data (name, address, email, phone)
- [ ] Agent recognizes Tier 1 is **stateless** (no `Mcp-Session-Id` header issued)

### Tier 2 — Community MCP

- [ ] `openclaw mcp show ghl-community-mcp` returns the `localhost:PORT/mcp` config
- [ ] `curl $GHL_COMMUNITY_MCP_URL/health` returns `{"status":"healthy","tools":NNN}` where NNN >= 500
- [ ] `curl $GHL_COMMUNITY_MCP_URL/tools` returns a tools array with at least 500 entries
- [ ] `POST $GHL_COMMUNITY_MCP_URL/execute` with `{"name":"ghl_list_products","arguments":{"limit":1}}` returns real product data
- [ ] If the port appears wrong, hitting it returns NOT Cognee's response (which is `{"status":"ready","version":"0.5.3-local"}`)

### Core files

- [ ] SOUL.md contains "🔴 GHL Tier Escalation Protocol" section
- [ ] AGENTS.md contains "Canonical current state" block with `$GHL_COMMUNITY_MCP_URL` reference
- [ ] AGENTS.md contains "Anti-patterns" block citing the port-hardcoding and tier-skip failures
- [ ] TOOLS.md contains "GHL MCPs (skill 36)" tool-name lookup table
- [ ] MEMORY.md contains "GHL MCP Setup — Installed [DATE]" record

### Behavior

- [ ] Test prompt #1: "What's my business name and main phone?" — reply opens with `[GHL tier used: 1 — locations_get-location]`
- [ ] Test prompt #2: "How many products do I have in my store?" — reply opens with `[GHL tier used: 2 — ghl_list_products]` and answer matches real product count
- [ ] Test prompt #3: "How many recurring subscriptions are running?" — reply opens with `[GHL tier used: 2 — list_invoice_schedules]`
- [ ] Test prompt #4 (trap): "Show me my last 5 payment transactions." — reply opens with `[GHL tier used: 2 — list_transactions]` (NOT Tier 1's read-only payments)
- [ ] Test prompt #5 (fall-through): "Pull my webhook delivery log for the last 24 hours." — if neither MCP has it, reply shows chain: `[GHL tier used: 3 (Tier 1+2 lacked tool) — raw API GET /hooks/...]`

### Security

- [ ] PIT NOT present in cleartext in any `.md` file in the workspace
- [ ] PIT NOT present in `~/Library/Logs/ghl-mcp/stdout.log` or systemd journal
- [ ] Secrets file is `chmod 600`
- [ ] No PIT in commit history of any local repo

## 6. Bundled QC Script — qc-ghl-mcp-setup.sh

The script ships in this skill folder as `qc-ghl-mcp-setup.sh` — single source of truth. Do NOT extract it from this document. Earlier versions of this skill embedded a copy of the script here; that copy is gone to prevent drift (the standalone has rate-limit probe logic and other v9.3.5+ additions that an embedded copy would silently lose).

To run it:

```bash
# Master files folder on Mac (where install.sh placed the skill)
MASTER_FILES_DIR=$HOME/Downloads/openclaw-master-files

chmod +x "$MASTER_FILES_DIR/36-ghl-mcp-setup/qc-ghl-mcp-setup.sh"
bash    "$MASTER_FILES_DIR/36-ghl-mcp-setup/qc-ghl-mcp-setup.sh"
```

Exit code 0 = setup complete. Any non-zero exit = fix the failed items and re-run.

The script:
- Uses canonical Mac paths (`~/.openclaw/...`, `~/Downloads/...`)
- Reads `GOHIGHLEVEL_API_KEY` + `GOHIGHLEVEL_LOCATION_ID` from `~/.openclaw/secrets/.env` (canonical) or `~/clawd/secrets/.env` (legacy)
- Probes Tier 1 (official MCP) for 36 tools
- Probes Tier 2 (community MCP) on `$GHL_COMMUNITY_MCP_URL` for the full tool count
- Probes Tier 3 (direct REST) and reads `X-RateLimit-Daily-Remaining` — if low, surfaces reset clock time
- Asserts SOUL.md / AGENTS.md / TOOLS.md / MEMORY.md contain the canonical state block + disclosure-header protocol
- Verifies secrets file is chmod 600 and the PIT never appears in any tracked .md file

## 7. QC Score

Score this skill from **0 to 10** after running the checks above.

Rubric:
- **10/10:** Bundled qc-ghl-mcp-setup.sh exits 0 with zero warnings; all 5 test prompts pass with correct disclosure headers.
- **8-9/10:** QC exits 0 but with warnings (e.g., tool count slightly below 588, skill 29 not yet installed). Behavior correct.
- **6-7/10:** Setup works but one or two non-critical items need cleanup (e.g., missing cross-reference in skill 05/29, README not updated, disclosure header missing on 1-2 test prompts).
- **0-5/10:** Tier 2 not running, credentials misplaced, MCPs not registered, core .md files not wired, or test prompts producing wrong tier.

Record:
- **QC Score:** ____ / 10
- **Status:** Pass / Needs Fix / Blocked
- **Notes:** ____________________________________________

## 8. QC Loop Rule

- Run at most **5 total QC/fix rounds** for this skill.
- After each failed round:
  1. Record exactly which checklist items or QC script assertions failed.
  2. Apply the smallest targeted fix.
  3. Re-run only the failed checks (or the full script if dependency chain).
- If the skill still fails after the **5th round**, stop and escalate. Common escalation causes:
  - launchd / systemd unit file references the wrong node path → fix path, retry
  - PIT lacks required scopes → ask client to add scopes
  - Port collision the agent didn't catch → manually find a free port, update `.env` AND `GHL_COMMUNITY_MCP_URL`
