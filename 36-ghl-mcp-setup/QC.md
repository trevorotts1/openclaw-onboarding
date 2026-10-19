# QC Checklist: GHL MCP Setup (Skill 36)

## 1. Purpose

Verifies that the GHL access chain is installed and routing correctly: Convert and Flow CLI (Tier 0, skill 44 — PRIMARY), Official MCP (Tier 1), REST API fallback (Tier 3), agent-browser/Playwright (Tier 4), Codex Computer Use (Tier 5). It also verifies that the **retired community MCP (Tier 2) is OFF** — absent registration, no loaded unit, no listener — and that the official connection and the custom courier MCP are preserved. Confirms the canonical-state block, disclosure protocol, and client-specific OAuth v2 endpoints are in place.

## 2. Installation Checks

- [ ] Skill folder exists with all 14 package files: SKILL.md, INSTALL.md, INSTRUCTIONS.md, EXAMPLES.md, GHL-LOOKUP-SOP.md, CORE_UPDATES.md, QC.md, CHANGELOG.md, skill-version.txt, ghl-mcp-setup-full.md, ghl-mcp-setup.skill, qc-ghl-mcp-setup.sh, wire.sh, PREREQS.json (a live install also creates a runtime `.wired-*` marker file)
- [ ] Platform detected correctly (macOS/Darwin → desktop, else VPS — via `uname -s`, NOT a quoted `[ -d "~/.openclaw" ]` test)
- [ ] `$CANONICAL_MASTER` resolves to a real openclaw-master-files folder
- [ ] Official MCP connection `ghl-mcp` present in `openclaw mcp list`; the custom courier MCP also present and untouched
- [ ] `ghl-community-mcp` (retired Tier 2) is **NOT** present in `openclaw mcp list`
- [ ] `GHL_COMMUNITY_MCP_URL` is **absent** from `openclaw.json` `env.vars`
- [ ] No required community repo tree. If a legacy tree exists at `~/mcp-servers/ghl-community-mcp` (Mac) or `/data/mcp-servers/ghl-community-mcp` (VPS) it is **archived** (path + digest recorded in the retirement receipt) and carries no unarchived secret-bearing `.env`. The historic pin `32628c979dd8f46e7952f85ce2d98f8028a26c32` is a rollback reference, not an install target.
- [ ] No retired lifecycle service loaded or enabled: launchd `com.clawd.ghl-mcp` is **not loaded and is disabled** (a `RunAtLoad=true` job that is merely stopped will reappear at login); pm2 has no `ghl-community-mcp`; `ghl-mcp.service` is not enabled
- [ ] No listener on `127.0.0.1:8765`
- [ ] Probe job (`com.clawd.ghl-mcp-probe` / `*/15` cron) removed or retirement-aware — it must not kickstart the retired service
- [ ] This document copied to `$MASTER_FILES_DIR/36-ghl-mcp-setup/`

## 3. Dependency Checks

- [ ] Skill 01 (Teach Yourself Protocol) installed
- [ ] Skill 02 (Back Yourself Up Protocol) installed
- [ ] Skill 05 (GHL Setup) installed AND credential path migrated to canonical (`~/.openclaw/secrets/.env` not `~/clawd/secrets/.env`)
- [ ] Skill 29 (GHL Convert and Flow) installed with `references/` subfolder populated
- [ ] Node.js ≥ 20 **only if** a retained surface declares it. It is not required by the required end state — it was required by the retired community MCP.
- [ ] curl and python3 available
- [ ] `lsof` available (used for the retirement no-listener check)
- [ ] An active GoHighLevel/Convert and Flow account with a PIT for REST (Tier 0/3) and an OAuth grant for the official MCP (Tier 1) — separate credential classes

## 4. Key Detection

The agent MUST find the canonical credentials by searching in this order:
- [ ] `$SECRETS_ENV` (canonical, platform-resolved)
- [ ] `openclaw.json` `env.vars.GOHIGHLEVEL_API_KEY` and `env.vars.GOHIGHLEVEL_LOCATION_ID`
- [ ] Legacy `$WORKSPACE/secrets/.env` (skill 05 pre-v2.0 location — must be migrated if found)
- [ ] `printenv | grep -iE "GHL|GOHIGH"`
- [ ] `~/.env`
- [ ] Repo-level env files in workspace
- [ ] Archived retired-community repo `.env` — evidence only; read key names, never values

QC fails if:
- The installer asks for credentials WITHOUT first searching all locations above
- An "API key" is requested instead of a "Private Integration Token (PIT)"
- Credentials are stored only to legacy location and not the canonical `~/.openclaw/secrets/.env`

## 5. Functional Checks

### Tier 1 — Official MCP

- [ ] The connection is registered for the client this box actually runs. The documented endpoints are `https://services.leadconnectorhq.com/mcp/anthropic/v2` (Claude) and `https://services.leadconnectorhq.com/mcp/openai/v2/` (ChatGPT/Codex); auth is **OAuth**
- [ ] `openclaw mcp show ghl-mcp` returns the gateway registration. A PIT bearer + `locationId`/`Version` header on the transitional `/mcp/` endpoint is recorded as a **transitional compatibility registration**, not as the documented auth path
- [ ] The four documented tool names are recorded: `list_locations`, `search_operations`, `describe_operation`, `execute_operation`
- [ ] A `tools/list` capture exists for this box (level-4 evidence). **No tool count is asserted** — a count is not an interface and is never parity proof
- [ ] A real read succeeds (e.g. `list_locations`) and is recorded
- [ ] The agent does not claim a Claude model routed through the OpenClaw gateway proves a Claude MCP client

### Four evidence levels for MCP — do not collapse them

| Level | What it means | Can this repo assert it? |
|---|---|---|
| **1. Documented endpoint** | Vendor docs publish the URL for a named client | **Yes** |
| **2. Documented catalog** | Vendor docs publish exactly four tool names | **Yes** — names only |
| **3. Account / tenant grant** | This account actually authorizes the connection and scopes | **No** — needs an authorized OAuth connect |
| **4. Actually observed on this box** | `tools/list` plus one real call, captured here | **No** — needs this box's receipt |

### Tier 2 — RETIRED Community MCP (verify OFF)

There is no healthy community MCP. The pass condition is **absence**:

- [ ] `ghl-community-mcp` is **NOT** registered (`openclaw mcp list`)
- [ ] No legacy install is being treated as healthy: no `dist/main.js` is being executed, no launchd/pm2/systemd unit is loaded or enabled, and no probe restarts it
- [ ] No listener on `127.0.0.1:8765`
- [ ] `GHL_COMMUNITY_MCP_URL` is absent
- [ ] Any archived tree uses the vetted pin `32628c979dd8f46e7952f85ce2d98f8028a26c32` and profile `curated` (43 crm tools, smoke `crm_list_workspaces`) **as a rollback reference only**
- [ ] No one "repairs" the retirement by rebuilding because a count looks low (the old 588 / 858 / 500 figures describe other profiles or history)
- [ ] If 8765 is occupied, the owner is identified and it is not killed on sight — the retired service is removed by its own unit/registration, not by killing whatever holds a port

### Core files

- [ ] AGENTS.md contains the "🔴 GHL Tier Escalation Protocol" section (relocated from SOUL.md in v1.1.0)
- [ ] SOUL.md is UNCHANGED — does NOT carry the legacy "🔴 GHL Tier Escalation Protocol" block
- [ ] AGENTS.md contains "Canonical current state" block with `$GHL_COMMUNITY_MCP_URL` reference
- [ ] AGENTS.md contains "Anti-patterns" block citing the port-hardcoding and tier-skip failures
- [ ] TOOLS.md contains "GHL MCPs (skill 36)" tool-name lookup table
- [ ] MEMORY.md contains "GHL MCP Setup — Installed [DATE]" record

### Behavior

- [ ] Test prompt #1: "What's my business name and main phone?" — reply opens with `[GHL tier used: 1 — list_locations]` (or the recorded operation name for this connection)
- [ ] Test prompt #2: "How many products do I have in my store?" — reply opens with Tier 0 or Tier 3, e.g. `[GHL tier used: 0 — convertandflow products list]` / `[GHL tier used: 3 — raw API GET /products/]`, and matches the real product count
- [ ] Test prompt #3: "How many recurring subscriptions are running?" — reply opens with `[GHL tier used: 3 — raw API GET /payments/subscriptions]`
- [ ] Test prompt #4 (trap): "Show me my last 5 payment transactions." — reply opens with `[GHL tier used: 3 — raw API GET /payments/transactions]`, not a Tier 2 tool
- [ ] Test prompt #5 (fall-through): "Pull my webhook delivery log for the last 24 hours." — reply shows the chain from Tier 1 to Tier 3: `[GHL tier used: 3 (Tier 1 lacked operation) — raw API GET /hooks/...]`
- [ ] No test produces a Tier 2 disclosure — that tier no longer exists

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
- Probes Tier 1 (official MCP) for reachability and records the tool names. **Do not assert a tool count** — the documented catalog is four tools and a count is not parity
- Verifies Tier 2 retirement: `ghl-community-mcp` absent from `mcp.servers`, no loaded/enabled unit (launchd / pm2 / systemd), no listener on `127.0.0.1:8765`, `GHL_COMMUNITY_MCP_URL` absent. **The script's legacy ">= 500 tools / supervised" assertions are superseded by W07's retirement update; a failure on those lines is the known-stale set and must never be fixed by reinstalling the service**
- Probes Tier 3 (direct REST) and reads `X-RateLimit-Daily-Remaining` — if low, surfaces reset clock time
- Asserts AGENTS.md / TOOLS.md / MEMORY.md contain the canonical state block + disclosure-header protocol, and that SOUL.md does NOT carry the legacy protocol (relocated to AGENTS.md in v1.1.0)
- Verifies secrets file is chmod 600 and the PIT never appears in any tracked .md file

## 7. QC Score

Score this skill from **0 to 10** after running the checks above.

Rubric:
- **10/10:** Bundled qc-ghl-mcp-setup.sh exits 0 with zero warnings; all 5 test prompts pass with correct disclosure headers.
- **8-9/10:** QC exits 0 but with warnings (e.g., skill 29 not yet installed, retirement receipt not yet filed). Behavior correct.
- **6-7/10:** Setup works but one or two non-critical items need cleanup (e.g., missing cross-reference in skill 05/29, README not updated, disclosure header missing on 1-2 test prompts).
- **0-5/10:** Community MCP still installed or running, credentials misplaced, official connection not registered, core .md files not wired, or test prompts producing wrong tier.

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
