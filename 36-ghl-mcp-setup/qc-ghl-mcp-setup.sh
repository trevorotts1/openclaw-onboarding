#!/usr/bin/env bash
# ============================================================
#  Skill 36 — GHL MCP Setup — Install QC Script
#  (version reported at runtime from skill-version.txt — no hardcoded literal; FIX-XC-13a)
#  Standalone bespoke validator for the 6-tier GHL access chain (Tier 0 = Convert and Flow CLI, skill 44).
#  Exits 0 if all assertions pass. Non-zero = blocker.
#
#  Tests:
#   - Master files folder located (fuzzy match)
#   - GHL credentials (PIT canonical name + format + chmod 600)
#   - Tier 1 (Official MCP) registered + tools/list returns >=36
#   - Tier 2 (Community MCP) NOT registered (on-demand curl) + service supervised
#     (launchd on Mac / pm2 on VPS, systemd fallback) +
#     /health returns >=500 tools + real-data tool call works
#   - Core .md files wired (SOUL/AGENTS/TOOLS/MEMORY)
#   - Master-files reference doc archived
#   - Security: PIT not leaked into workspace .md files
# ============================================================

set -u
PASS=0; FAIL=0; WARN=0

SKILL_DIR="$(dirname "$0")"

# Live skill version — read from the canonical source, never a literal (FIX-XC-13a).
SKILL_VERSION="unknown"
if [ -f "$SKILL_DIR/skill-version.txt" ]; then
  SKILL_VERSION="$(tr -d '[:space:]' < "$SKILL_DIR/skill-version.txt" 2>/dev/null || echo unknown)"
  [ -z "$SKILL_VERSION" ] && SKILL_VERSION="unknown"
fi

LIB="$SKILL_DIR/../lib-shared.sh"
[ -f "$LIB" ] || LIB="$HOME/.openclaw/skills/lib-shared.sh"
[ -f "$LIB" ] && source "$LIB"

if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() {
    # Canonical Mac paths
    export SECRETS_ENV="$HOME/.openclaw/secrets/.env"
    export CONFIG_JSON="$HOME/.openclaw/openclaw.json"
    export WORKSPACE="$HOME/clawd"
    [ ! -d "$WORKSPACE" ] && WORKSPACE="$HOME/.openclaw/workspace"
    export SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"
  }
fi
resolve_platform_paths

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

# Load creds safely
if [ -f "$SECRETS_ENV" ]; then
  set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u
fi
: "${GOHIGHLEVEL_API_KEY:=}"
: "${GOHIGHLEVEL_LOCATION_ID:=}"
# Derive platform if unset — prevents 'OPENCLAW_PLATFORM: unbound variable' crash under set -u
: "${OPENCLAW_PLATFORM:=$([ "$(uname -s)" = "Darwin" ] && echo mac || echo linux)}"
# 11-alias fallback resolver — passes on pre-v12 boxes where the PIT is stored under a legacy name
RESOLVED_PIT="${GOHIGHLEVEL_API_KEY:-${GHL_API_KEY:-${GHL_PIT:-${GHL_TOKEN:-${GHL_PRIVATE_INTEGRATION_TOKEN:-${PRIVATE_INTEGRATION_TOKEN:-${GHL_PRIVATE_TOKEN:-${PIT_TOKEN:-${GHL_PIT_TOKEN:-${GOHIGHLEVEL_LOCATION_PIT:-${GHL_LOCATION_PIT:-}}}}}}}}}}}"

echo ""
echo "═══════════════════════════════════════════════"
echo "  Skill 36 — GHL MCP Setup — Final QC (${SKILL_VERSION})"
echo "═══════════════════════════════════════════════"
echo "  Platform: ${OPENCLAW_PLATFORM:-unknown}"
echo "  Date:     $(date)"
echo ""

# ----------------------------------------------------------
# Section 0: Offline structural QC (SK1-73) — no live GHL required
# ----------------------------------------------------------
# Sections A–H below are LIVE-ONLY: every meaningful assert needs a live box
# (resolved creds, a running/supervised MCP, curl to leadconnectorhq.com, and the
# workspace core .md files). On a fresh clone / CI / offline box they ALL FAIL,
# so the QC gives ZERO signal about the SKILL's own shipped correctness. This
# section validates the skill's COMMITTED artifacts, which are always co-located
# with this QC script — so it runs on ANY box (offline included) AND still PASSES
# on a healthy client box (no false FAIL), while catching a regression in the
# shipped skill (e.g. a dropped SK1-69 pin or a committed real PIT) that the
# live sections could never see.
echo "── Section 0: Offline structural QC (no live GHL required) ──"
assert "skill-version.txt present and non-empty"        "[ -s \"$SKILL_DIR/skill-version.txt\" ]"
assert "INSTALL.md present"                             "[ -f \"$SKILL_DIR/INSTALL.md\" ]"
assert "SKILL.md present"                               "[ -f \"$SKILL_DIR/SKILL.md\" ]"
assert "scripts/cc-task.sh present (final CC hook)"     "[ -f \"$SKILL_DIR/scripts/cc-task.sh\" ]"
# SK1-72 regression lock: the installer must refuse to persist a placeholder PIT.
assert "INSTALL.md carries the placeholder-credential refusal guard (SK1-72)" \
  "grep -qiE 'pit-XXXX|placeholder' \"$SKILL_DIR/INSTALL.md\""
# Security (offline): no REAL PIT literal committed into the skill's own tree.
# The hex class matches only a real-looking PIT — `pit-XXXX` placeholders (X's,
# not hex) never match, so example text is not flagged.
assert "no real PIT literal committed in skill files" \
  "! grep -rIqE 'pit-[a-f0-9]{8}-[a-f0-9]{4}' \"$SKILL_DIR\""
# SK1-69 regression lock: the community-MCP start script pins a git SHA before
# start (supply-chain). Check whichever co-located copy is shipped; if none is
# present next to this skill (fleet layout varies), warn rather than false-FAIL.
_S36_START=""
for c in "$SKILL_DIR/../platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh" \
         "$SKILL_DIR/platform/vps/start-ghl-mcp-server.sh" \
         "$SKILL_DIR/scripts/start-ghl-mcp-server.sh"; do
  [ -f "$c" ] && _S36_START="$c" && break
done
if [ -n "$_S36_START" ]; then
  assert "community-MCP start script pins a git SHA before start (SK1-69)" \
    "grep -qE 'git -C .* checkout .*GHL_MCP_VETTED_COMMIT' \"$_S36_START\""
else
  warn_only "community-MCP start script co-located for SHA-pin check (SK1-69)" "false"
fi

# v21.5.0 regression locks — the five installer diseases behind the 2026-08-02/03
# outage (2 days of 30s agent-init stalls against a server that was UP the whole
# time). Each lock is offline/static: it checks the SHIPPED wiring, not the box.
_S36_PIN=""
for c in "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
         "/data/.openclaw/onboarding/config/ghl-mcp-pin.env" \
         "$SKILL_DIR/../config/ghl-mcp-pin.env"; do
  [ -f "$c" ] && _S36_PIN="$c" && break
done
_S36_AUTOSTART=""
for c in "$HOME/.openclaw/onboarding/scripts/ghl-mcp-autostart.sh" \
         "/data/.openclaw/onboarding/scripts/ghl-mcp-autostart.sh" \
         "$SKILL_DIR/../scripts/ghl-mcp-autostart.sh"; do
  [ -f "$c" ] && _S36_AUTOSTART="$c" && break
done
_S36_PROBE=""
for c in "$HOME/.openclaw/onboarding/scripts/ghl-mcp-probe.sh" \
         "/data/.openclaw/onboarding/scripts/ghl-mcp-probe.sh" \
         "$SKILL_DIR/../scripts/ghl-mcp-probe.sh"; do
  [ -f "$c" ] && _S36_PROBE="$c" && break
done
if [ -n "$_S36_PIN" ]; then
  assert "pin config declares a FULL 40-char vetted commit (never a branch/short SHA)" \
    "grep -qE '^GHL_MCP_VETTED_COMMIT=\"[0-9a-f]{40}\"' \"$_S36_PIN\""
  assert "pin config declares an explicit GHL_TOOL_PROFILE (never the 858-tool default)" \
    "grep -qE '^GHL_MCP_TOOL_PROFILE=' \"$_S36_PIN\""
else
  warn_only "config/ghl-mcp-pin.env co-located for the pin/profile check" "false"
fi
if [ -n "$_S36_AUTOSTART" ]; then
  assert "autostart never 'git pull's the third-party MCP (floating checkout)" \
    "! sed 's/#.*$//' \"$_S36_AUTOSTART\" | grep -qE 'git .*pull'"
  assert "autostart sets GHL_TOOL_PROFILE in the launchd plist it writes" \
    "grep -qF '<key>GHL_TOOL_PROFILE</key>' \"$_S36_AUTOSTART\""
  assert "autostart writes a CRASH-ONLY KeepAlive (no unconditional KeepAlive=true)" \
    "! grep -qF '<key>KeepAlive</key><true/>' \"$_S36_AUTOSTART\" && grep -qF '<key>SuccessfulExit</key><false/>' \"$_S36_AUTOSTART\""
  assert "autostart verifies the built dist contains the MCP transport wiring" \
    "grep -qF 'connect(transport)' \"$_S36_AUTOSTART\""
else
  warn_only "scripts/ghl-mcp-autostart.sh co-located for the install-hygiene checks" "false"
fi
assert "liveness probe ships (scripts/ghl-mcp-probe.sh)" "[ -n \"$_S36_PROBE\" ]"
echo ""

# ----------------------------------------------------------
# Section A: Master files + platform
# ----------------------------------------------------------
echo "── Section A: Master files + platform ──"

# Fuzzy locator (mirrors lib-shared.sh)
MASTER_FILES_DIR=""
for r in "$HOME/Downloads" "~/Downloads" "/root/Downloads" "/data" "$HOME"; do
  [ -d "$r" ] || continue
  f=$(find "$r" -maxdepth 2 -type d \
    \( -iname "*openclaw*master*file*" -o -iname "*open*claw*master*file*" \) \
    ! -iname "*backup*" ! -iname "*.zip*" 2>/dev/null | head -1)
  [ -n "$f" ] && MASTER_FILES_DIR="$f" && break
done

assert "Master files folder located"               "[ -n \"$MASTER_FILES_DIR\" ]"
warn_only "Skill 29 (GHL Convert and Flow) reference dir present" \
  "find \"$MASTER_FILES_DIR\" -maxdepth 3 -type d -iname '*ghl*convert*flow*' 2>/dev/null | grep -q ."

echo ""
echo "── Section B: Credentials (PIT — NOT API key) ──"
assert "GHL PIT set (any canonical alias)"         "[ -n \"$RESOLVED_PIT\" ]"
assert "GHL PIT starts with pit-"                 "[[ \"$RESOLVED_PIT\" == pit-* ]]"
assert "GOHIGHLEVEL_LOCATION_ID is set"            "[ -n \"$GOHIGHLEVEL_LOCATION_ID\" ]"
assert "Canonical secrets file exists"             "[ -f \"$SECRETS_ENV\" ]"
SEC_MODE=$(stat -c %a "$SECRETS_ENV" 2>/dev/null || stat -f %A "$SECRETS_ENV" 2>/dev/null)
assert "Secrets file is chmod 600"                 "[ \"$SEC_MODE\" = '600' ]"
warn_only "PIT mirrored in openclaw.json env.vars" "command -v openclaw && openclaw config get env.vars.GOHIGHLEVEL_API_KEY 2>/dev/null | grep -q 'pit-'"
warn_only "Location ID in openclaw.json env.vars"  "command -v openclaw && openclaw config get env.vars.GOHIGHLEVEL_LOCATION_ID 2>/dev/null | grep -q ."
assert "GHL_COMMUNITY_MCP_URL env var set"         "command -v openclaw && openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>/dev/null | grep -qE 'http://localhost:[0-9]+'"

echo ""
echo "── Section B2: GHL rate-limit budget check (NEW: 2026-05-13 incident response) ──"
# Rate-limit headers only appear on direct API responses (Tier 3 endpoints),
# NOT on the Official MCP SSE wrapper. So we probe the locations endpoint directly.
# All three tiers share the same backend bucket — switching tiers doesn't bypass.
RL_RAW=$(curl -sS -i -m 10 "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28" 2>/dev/null | tr -d '\r')
RL_DAILY_REMAINING=$(echo "$RL_RAW" | grep -i "^x-ratelimit-daily-remaining:" | awk -F': ' '{print $2}' | tr -d '[:space:]')
RL_DAILY_RESET_MS=$(echo "$RL_RAW" | grep -i "^x-ratelimit-daily-reset:" | awk -F': ' '{print $2}' | tr -d '[:space:]')
RL_BURST_REMAINING=$(echo "$RL_RAW" | grep -i "^x-ratelimit-remaining:" | awk -F': ' '{print $2}' | tr -d '[:space:]')
if [ -n "$RL_DAILY_REMAINING" ]; then
  echo "  Daily quota remaining: $RL_DAILY_REMAINING / 200000"
  echo "  Burst (10s window) remaining: ${RL_BURST_REMAINING:-?} / 100"
  if [ -n "$RL_DAILY_RESET_MS" ] && [ "$RL_DAILY_RESET_MS" -gt 0 ] 2>/dev/null; then
    RESET_HRS=$(python3 -c "print(round($RL_DAILY_RESET_MS / 1000 / 3600, 1))" 2>/dev/null)
    RESET_CLOCK=$(python3 -c "
import time
t = time.time() + ($RL_DAILY_RESET_MS / 1000)
print(time.strftime('%-I:%M %p %Z', time.localtime(t)))
" 2>/dev/null)
    echo "  Daily quota resets in: ~${RESET_HRS} hours (around ${RESET_CLOCK})"
  fi
  warn_only "GHL daily quota > 5000 (safe for bulk ops)" "[ \"$RL_DAILY_REMAINING\" -gt 5000 ]"
  assert "GHL daily quota > 100 (any GHL op possible at all)" "[ \"$RL_DAILY_REMAINING\" -gt 100 ]"
else
  yellow "  ⚠ Could not read rate-limit headers (token may be invalid or network issue)"; WARN=$((WARN+1))
fi

echo ""
echo "── Section C: Tier 1 (Official MCP) ──"
assert "ghl-mcp registered in openclaw mcp list" "command -v openclaw && openclaw mcp list 2>/dev/null | grep -q 'ghl-mcp$'"
T1_TOOLS=$(curl -sS -m 10 -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' 2>/dev/null \
  | grep "^data:" | head -1 | sed 's/^data: //' \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("result",{}).get("tools",[])))' 2>/dev/null)
assert "Tier 1 tools/list returns >= 36 tools" "[ \"${T1_TOOLS:-0}\" -ge 36 ]"

echo ""
echo "── Section D: Tier 2 (Community MCP) ──"
# BUG-1 fix: resolve the on-demand Tier 2 URL BEFORE any assert that uses it. It was
# previously used by the /tools assert one line ABOVE its own assignment, so under
# `set -u` the first reference threw "URL: unbound variable" → spurious FAIL every run.
# BUG-2 fix: guard `openclaw` presence with a SEPARATE test. The old capture was
# URL=$(command -v openclaw && openclaw config get ...), which prepended the binary
# path (stdout of `command -v`) onto the URL → "/opt/.../openclaw\nhttp://localhost:8765"
# → the /tools, /health and /execute probes all hit a broken URL → spurious FAIL.
URL=""
if command -v openclaw >/dev/null 2>&1; then
  URL=$(openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>/dev/null | tr -d '\n' | sed 's|/$||')
fi
assert "ghl-community-mcp NOT registered in mcp.servers (Tier 2 is on-demand curl)" "! { command -v openclaw >/dev/null 2>&1 && openclaw mcp list 2>/dev/null | grep -q 'ghl-community-mcp'; }"
assert "Tier 2 /tools curl returns the tool surface on-demand" "[ -n \"$URL\" ] && curl -sS -m 8 \"$URL/tools\" 2>/dev/null | grep -qE 'ghl_list_products|\"tools\"'"
# BUG-3 / D5-ii fix: the VPS canonical supervisor is pm2 (Hostinger Docker has NO
# systemd), so a systemctl-only check FAILED on a healthy Docker VPS. Check pm2 first,
# fall back to systemd for non-container Linux.
if [ "${OPENCLAW_PLATFORM:-}" = "mac" ]; then
  assert "launchd service is running" "launchctl print gui/$(id -u)/com.clawd.ghl-mcp 2>/dev/null | grep -q 'state = running'"
  # CRASH-ONLY: main.js exits 1 when GHL rejects the PIT at boot, so an
  # unconditional KeepAlive turns a rotated token into a relaunch loop every
  # ThrottleInterval seconds. The installed plist must use the KeepAlive dict.
  assert "launchd plist is CRASH-ONLY (KeepAlive dict, not an unconditional true)" \
    "! grep -A1 '<key>KeepAlive</key>' \"$HOME/Library/LaunchAgents/com.clawd.ghl-mcp.plist\" 2>/dev/null | grep -q '<true/>'"
  warn_only "periodic liveness probe installed (com.clawd.ghl-mcp-probe)" \
    "launchctl print gui/$(id -u)/com.clawd.ghl-mcp-probe >/dev/null 2>&1"
else
  assert "Tier 2 server supervised (pm2 ghl-community-mcp, or systemd ghl-mcp fallback)" "{ command -v pm2 >/dev/null 2>&1 && pm2 jlist 2>/dev/null | grep -q 'ghl-community-mcp'; } || systemctl is-active ghl-mcp 2>/dev/null | grep -q '^active$'"
fi
T2_HEALTH=$(curl -sS -m 5 "$URL/health" 2>/dev/null)
assert "Tier 2 /health responds healthy" "echo \"$T2_HEALTH\" | grep -q '\"status\":\"healthy\"'"

# ── LIVENESS (v21.5.0) — /health is served by express BEFORE the MCP transport
# is wired, so a stale/deaf dist returns {"status":"healthy"} while every agent
# init burns the full 30s connectionTimeoutMs. That is exactly what happened on
# 2026-08-01/02. The only real liveness test is a JSON-RPC round trip.
assert "Tier 2 ANSWERS JSON-RPC (alive, not merely listening)" \
  "curl -sS -m 10 -X POST \"$URL/mcp\" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\",\"capabilities\":{},\"clientInfo\":{\"name\":\"qc\",\"version\":\"1\"}}}' 2>/dev/null | grep -q serverInfo"

# ── TOOL PROFILE (v21.5.0) — the upstream default is `full` (858 tools). The
# expected count is whatever the configured profile implies, NOT a fixed >=500:
# a correctly-configured `curated` box serves ~43 and the old >=500 check would
# have called that a problem while a mis-set `full` box passed.
T2_TOOLS=$(printf '%s' "$T2_HEALTH" | sed -n 's/.*"tools":[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)
S36_PROFILE="curated"; S36_MIN=1; S36_MAX=200
if [ -n "${_S36_PIN:-}" ]; then
  S36_PROFILE=$(sed -n 's/^GHL_MCP_TOOL_PROFILE="\([a-z]*\)".*/\1/p' "$_S36_PIN" | head -1)
  S36_MIN=$(sed -n 's/^GHL_MCP_EXPECT_MIN_TOOLS="\([0-9]*\)".*/\1/p' "$_S36_PIN" | head -1)
  S36_MAX=$(sed -n 's/^GHL_MCP_EXPECT_MAX_TOOLS="\([0-9]*\)".*/\1/p' "$_S36_PIN" | head -1)
  : "${S36_PROFILE:=curated}"; : "${S36_MIN:=1}"; : "${S36_MAX:=200}"
fi
echo "  Tier 2 tool surface: ${T2_TOOLS:-?} tools (profile=${S36_PROFILE}, expected ${S36_MIN}..${S36_MAX})"
assert "Tier 2 tool count matches the configured GHL_TOOL_PROFILE (${S36_PROFILE})" \
  "[ -n \"$T2_TOOLS\" ] && [ \"$T2_TOOLS\" -ge \"$S36_MIN\" ] && [ \"$T2_TOOLS\" -le \"$S36_MAX\" ]"
# v21.5.0: the smoke tool must EXIST inside the configured profile. Measured on
# 2026-08-03: under GHL_TOOL_PROFILE=curated the server exposes 43 crm_* tools
# and NO ghl_* tools at all — so the historic hardcoded `ghl_list_products` call
# fails on a correctly-configured curated box. The tool name is a parameter now.
S36_SMOKE_TOOL="crm_list_workspaces"
if [ -n "${_S36_PIN:-}" ]; then
  S36_SMOKE_TOOL=$(sed -n 's/^GHL_MCP_SMOKE_TOOL="\([A-Za-z0-9_]*\)".*/\1/p' "$_S36_PIN" | head -1)
  : "${S36_SMOKE_TOOL:=crm_list_workspaces}"
fi
assert "Tier 2 smoke tool ${S36_SMOKE_TOOL} is present in the ${S36_PROFILE} profile" \
  "curl -sS -m 8 \"$URL/tools\" 2>/dev/null | grep -q \"$S36_SMOKE_TOOL\""
T2_CALL=$(curl -sS -m 10 -X POST "$URL/execute" -H "Content-Type: application/json" \
  -d "{\"name\":\"${S36_SMOKE_TOOL}\",\"arguments\":{}}" 2>/dev/null)
assert "Tier 2 ${S36_SMOKE_TOOL} returns real data" "echo \"$T2_CALL\" | grep -qE '\"success\":\\s*true|\"result\"|\"content\"'"

echo ""
echo "── Section E: Core .md files wired ──"
assert "AGENTS.md has Tier Escalation Protocol (relocated from SOUL.md)" "[ -f \"$WORKSPACE/AGENTS.md\" ] && grep -q 'Tier Escalation Protocol' \"$WORKSPACE/AGENTS.md\""
assert "SOUL.md does NOT carry the legacy skill-36 Tier Escalation Protocol" "[ ! -f \"$WORKSPACE/SOUL.md\" ] || ! grep -q '🔴 GHL Tier Escalation Protocol' \"$WORKSPACE/SOUL.md\""
assert "AGENTS.md has canonical state block"  "[ -f \"$WORKSPACE/AGENTS.md\" ] && grep -qE 'CANONICAL|Canonical' \"$WORKSPACE/AGENTS.md\""
assert "AGENTS.md references GHL_COMMUNITY_MCP_URL" "grep -q 'GHL_COMMUNITY_MCP_URL' \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
assert "TOOLS.md has GHL MCP tool reference" "[ -f \"$WORKSPACE/TOOLS.md\" ] && grep -qE 'ghl-community-mcp|ghl_list_products' \"$WORKSPACE/TOOLS.md\""
assert "MEMORY.md has GHL MCP install record" "[ -f \"$WORKSPACE/MEMORY.md\" ] && grep -qE 'GHL MCP Setup|skill 36|ghl-community-mcp' \"$WORKSPACE/MEMORY.md\""

echo ""
echo "── Section F: Doc archived to master files ──"
assert "ghl-mcp-setup-full.md copied to master files folder" "find \"$MASTER_FILES_DIR\" -maxdepth 3 -name 'ghl-mcp-setup-full.md' 2>/dev/null | grep -q ."

echo ""
echo "── Section H: Tier 0 (Convert and Flow CLI, skill 44) ──"
SKILL44_PRESENT="[ -d \"$MASTER_FILES_DIR/44-convert-and-flow-operator\" ] || [ -d \"$SKILLS_DIR_DEFAULT/44-convert-and-flow-operator\" ] || [ -d \"$HOME/.openclaw/tools/convert-and-flow-cli\" ]"
if eval "$SKILL44_PRESENT" 2>/dev/null; then
  assert "caf wrapper resolves on PATH"                       "command -v caf >/dev/null 2>&1 || command -v convertandflow >/dev/null 2>&1"
  assert "caf doctor exits green"                             "caf doctor >/dev/null 2>&1"
else
  warn_only "caf wrapper resolves on PATH (skill 44 not yet installed)"   "command -v caf >/dev/null 2>&1 || command -v convertandflow >/dev/null 2>&1"
  warn_only "caf doctor exits green (skill 44 not yet installed)"         "caf doctor >/dev/null 2>&1"
fi
assert "AGENTS.md tier table shows Tier 0 = SKILL 44"        "grep -qE '\\| 0 \\|.*SKILL 44' \"$WORKSPACE/AGENTS.md\""
assert "AGENTS.md disclosure recognizes Tier 0 format"       "grep -q 'GHL tier used: 0' \"$WORKSPACE/AGENTS.md\""

echo ""
echo "── Section G: Security ──"
assert "PIT NOT exposed in any workspace .md file" "! grep -rE 'pit-[a-f0-9]{8}-[a-f0-9]{4}' \"$WORKSPACE\"/*.md 2>/dev/null | grep -v 'pit-XXX\\|pit-xxx\\|pit-x'"
warn_only "PIT NOT in ghl-mcp stdout log" "! grep -qE 'pit-[a-f0-9]{8}-[a-f0-9]{4}' \"$HOME/Library/Logs/ghl-mcp/stdout.log\" 2>/dev/null"

echo ""
echo "═══════════════════════════════════════════════"
echo "  Result: $PASS passed | $FAIL failed | $WARN warnings"
echo "═══════════════════════════════════════════════"
SCORE=$(python3 -c "print(round(($PASS * 10) / ($PASS + $FAIL + 0.001), 1))" 2>/dev/null || echo "?")
echo "  Approx score: ${SCORE}/10 (excludes warnings)"
echo ""

if [ "$FAIL" -gt 0 ]; then
  red "Skill 36 install QC FAILED. Fix failures and re-run."
  exit 1
elif [ "$WARN" -gt 3 ]; then
  yellow "Skill 36 install passed with multiple warnings. Review with the owner."
  exit 0
else
  green "Skill 36 install QC PASS."
  # Command Center: move the install card to `review` (fail-soft; never blocks
  # the PASS). The independent CC auto-scorer — not this script — promotes
  # review -> done. See scripts/cc-task.sh (FIX-S36-01).
  bash "$SKILL_DIR/scripts/cc-task.sh" review || true
  exit 0
fi
