# QC Checklist: GHL MCP Setup (Skill 36)

## 1. Purpose

Verifies that the 5-tier GHL access chain is fully installed and routing correctly: Official MCP (Tier 1), Community MCP (Tier 2), REST API fallback (Tier 3), Playwright (Tier 4), Codex Computer Use (Tier 5). Confirms the canonical-state block, env vars, disclosure protocol, and platform-aware lifecycle (launchd / systemd) are all in place.

## 2. Installation Checks

- [ ] Skill folder exists with all 10 files: SKILL.md, INSTALL.md, INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md, QC.md, CHANGELOG.md, skill-version.txt, ghl-mcp-setup-full.md, ghl-mcp-setup.skill
- [ ] Platform detected correctly (`/data/.openclaw` → VPS, else desktop)
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

## 6. Bundled QC Script — qc-ghl-setup.sh

Save the script below as `$MASTER_FILES_DIR/36-ghl-mcp-setup/qc-ghl-setup.sh`, chmod +x, and run it. Exit 0 = setup complete. Exit 1 = fix the failed items and re-run.

```bash
#!/bin/bash
# qc-ghl-setup.sh — Final QC for GHL MCP setup (skill 36)
set -u
FAIL=0; PASS=0; WARN=0

red()    { printf "\033[31m%s\033[0m\n" "$1"; }
green()  { printf "\033[32m%s\033[0m\n" "$1"; }
yellow() { printf "\033[33m%s\033[0m\n" "$1"; }

assert() {
  if eval "$2" >/dev/null 2>&1; then
    green "  ✓ PASS — $1"; PASS=$((PASS+1))
  else
    red "  ✗ FAIL — $1"; FAIL=$((FAIL+1))
  fi
}
warn_only() {
  if eval "$2" >/dev/null 2>&1; then
    green "  ✓ PASS — $1"; PASS=$((PASS+1))
  else
    yellow "  ⚠ WARN — $1"; WARN=$((WARN+1))
  fi
}

if [ -d "/data/.openclaw" ]; then
  PLATFORM=vps
  SECRETS_ENV=/data/.openclaw/secrets/.env
  CONFIG_JSON=/data/.openclaw/openclaw.json
  WORKSPACE=/data/clawd
else
  PLATFORM=desktop
  SECRETS_ENV=$HOME/.openclaw/secrets/.env
  CONFIG_JSON=$HOME/.openclaw/openclaw.json
  WORKSPACE=$HOME/clawd
fi

echo "═══════════════════════════════════════"
echo "  GHL MCP Setup — Final QC (skill 36)"
echo "═══════════════════════════════════════"
echo "Platform: $PLATFORM"
echo "Date:     $(date)"
echo ""

[ -f "$SECRETS_ENV" ] && set -a && source "$SECRETS_ENV" && set +a

# Locate master files
MASTER_FILES_DIR=""
for r in "$HOME/Downloads" "/data/Downloads" "/root/Downloads" "/data" "$HOME"; do
  [ -d "$r" ] || continue
  f=$(find "$r" -maxdepth 2 -type d \
    \( -iname "*openclaw*master*file*" -o -iname "*open*claw*master*file*" \) \
    ! -iname "*backup*" ! -iname "*.zip*" 2>/dev/null | head -1)
  [ -n "$f" ] && MASTER_FILES_DIR="$f" && break
done

echo "── Section A: Master files + platform ──"
assert "Master files folder located" "[ -n \"$MASTER_FILES_DIR\" ]"
warn_only "GHL skill 29 reference dir present" "find \"$MASTER_FILES_DIR\" -maxdepth 3 -type d -iname '*ghl*convert*flow*' 2>/dev/null | grep -q ."

echo ""
echo "── Section B: Credentials ──"
assert "GOHIGHLEVEL_API_KEY is set"               "[ -n \"${GOHIGHLEVEL_API_KEY:-}\" ]"
assert "GOHIGHLEVEL_API_KEY starts with pit-"     "[[ \"${GOHIGHLEVEL_API_KEY:-}\" == pit-* ]]"
assert "GOHIGHLEVEL_LOCATION_ID is set"           "[ -n \"${GOHIGHLEVEL_LOCATION_ID:-}\" ]"
assert "Canonical secrets file exists"            "[ -f \"$SECRETS_ENV\" ]"
assert "Secrets file is chmod 600"                "[ \"$(stat -f %A \"$SECRETS_ENV\" 2>/dev/null || stat -c %a \"$SECRETS_ENV\" 2>/dev/null)\" = '600' ]"
assert "PIT mirrored in openclaw.json env.vars"   "openclaw config get env.vars.GOHIGHLEVEL_API_KEY 2>/dev/null | grep -q 'pit-'"
assert "Location ID in openclaw.json env.vars"    "openclaw config get env.vars.GOHIGHLEVEL_LOCATION_ID 2>/dev/null | grep -q ."
assert "GHL_COMMUNITY_MCP_URL env var set"        "openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>/dev/null | grep -qE 'http://localhost:[0-9]+'"

echo ""
echo "── Section C: Tier 1 (Official MCP) ──"
assert "ghl-mcp registered" "openclaw mcp list 2>/dev/null | grep -q 'ghl-mcp$'"
T1_TOOLS=$(curl -sS -m 10 -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer ${GOHIGHLEVEL_API_KEY:-}" \
  -H "locationId: ${GOHIGHLEVEL_LOCATION_ID:-}" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' 2>/dev/null \
  | grep "^data:" | head -1 | sed 's/^data: //' \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("result",{}).get("tools",[])))' 2>/dev/null)
assert "Tier 1 tools/list returns 36" "[ \"$T1_TOOLS\" = '36' ]"

echo ""
echo "── Section D: Tier 2 (Community MCP) ──"
assert "ghl-community-mcp registered" "openclaw mcp list 2>/dev/null | grep -q 'ghl-community-mcp'"
URL=$(openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>/dev/null | tr -d '\n' | sed 's|/$||')
if [ "$PLATFORM" = "desktop" ]; then
  assert "launchd service running" "launchctl print gui/$(id -u)/com.clawd.ghl-mcp 2>/dev/null | grep -q 'state = running'"
else
  assert "systemd service running"  "systemctl is-active ghl-mcp 2>/dev/null | grep -q '^active$'"
fi
T2_HEALTH=$(curl -sS -m 5 "$URL/health" 2>/dev/null)
assert "Tier 2 /health responds healthy" "echo \"$T2_HEALTH\" | grep -q '\"status\":\"healthy\"'"
warn_only "Tier 2 reports >=500 tools" "echo \"$T2_HEALTH\" | python3 -c 'import json,sys; print(json.load(sys.stdin).get(\"tools\",0)>=500)' 2>/dev/null | grep -q True"
T2_CALL=$(curl -sS -m 10 -X POST "$URL/execute" -H "Content-Type: application/json" \
  -d '{"name":"ghl_list_products","arguments":{"limit":1}}' 2>/dev/null)
assert "Tier 2 ghl_list_products returns data" "echo \"$T2_CALL\" | grep -qE '\"success\":\\s*true|\"result\"'"

echo ""
echo "── Section E: Core .md files wired ──"
assert "SOUL.md has Tier Escalation Protocol"     "[ -f \"$WORKSPACE/SOUL.md\" ] && grep -q 'Tier Escalation Protocol' \"$WORKSPACE/SOUL.md\""
assert "AGENTS.md has canonical state block"      "[ -f \"$WORKSPACE/AGENTS.md\" ] && grep -qE 'CANONICAL|Canonical' \"$WORKSPACE/AGENTS.md\""
assert "AGENTS.md references GHL_COMMUNITY_MCP_URL" "grep -q 'GHL_COMMUNITY_MCP_URL' \"$WORKSPACE/AGENTS.md\""
assert "TOOLS.md has GHL MCP tool table"          "[ -f \"$WORKSPACE/TOOLS.md\" ] && grep -q 'ghl-community-mcp\\|ghl_list_products' \"$WORKSPACE/TOOLS.md\""
assert "MEMORY.md has skill 36 install record"    "[ -f \"$WORKSPACE/MEMORY.md\" ] && grep -qE 'GHL MCP Setup|skill 36|ghl-community-mcp' \"$WORKSPACE/MEMORY.md\""

echo ""
echo "── Section F: Doc archived to master files ──"
assert "Full reference copied" "find \"$MASTER_FILES_DIR\" -maxdepth 3 -name 'ghl-mcp-setup-full.md' 2>/dev/null | grep -q ."

echo ""
echo "── Section G: Security ──"
assert "PIT not in workspace .md files"  "! grep -rE 'pit-[a-f0-9]{8}-[a-f0-9]{4}' \"$WORKSPACE\"/*.md 2>/dev/null | grep -v 'pit-XXX\\|pit-x'"

echo ""
echo "═══════════════════════════════════════"
echo "  Result: $PASS passed | $FAIL failed | $WARN warnings"
echo "═══════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  red "SETUP NOT COMPLETE. Fix failures and re-run."
  exit 1
elif [ "$WARN" -gt 0 ]; then
  yellow "Setup complete with warnings — review with client."
  exit 0
else
  green "All checks pass. Setup COMPLETE."
  exit 0
fi
```

## 7. QC Score

Score this skill from **0 to 10** after running the checks above.

Rubric:
- **10/10:** Bundled qc-ghl-setup.sh exits 0 with zero warnings; all 5 test prompts pass with correct disclosure headers.
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
