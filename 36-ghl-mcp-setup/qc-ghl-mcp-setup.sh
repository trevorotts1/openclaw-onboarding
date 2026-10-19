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
#   - Tier 2 (Community MCP) RETIRED: no process, no listener, no supervisor
#     registration (launchd / pm2 / systemd), no probe, no mcp.servers entry,
#     no @reboot resurrect entry, no lifecycle script that can restart it
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
# Shared credential lookup (INF002): location id under every name in every store; else the
# Convert and Flow private integration token -> its location through the GHL API; neither
# -> the skill installs with a note (below), never a failure.
for _g in "$(dirname "$0")/../shared-utils/ghl-creds.sh" "$HOME/.openclaw/skills/shared-utils/ghl-creds.sh" "/data/.openclaw/skills/shared-utils/ghl-creds.sh"; do
  [ -f "$_g" ] && { . "$_g"; break; }
done
set +u; command -v ghl_creds_resolve >/dev/null 2>&1 && ghl_creds_resolve; set -u
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
# v22.0.0 RETIREMENT LOCKS — the community MCP (Tier 2) is RETIRED. The old
# checks here asserted that the start script, the pin and the liveness probe
# SHIPPED and were hardened. In the retired world every one of those is a
# resurrection surface. Retirement is asserted explicitly: a lifecycle script is
# acceptable ONLY when it is absent, or when it carries the GHL_MCP_RETIRED
# refusal marker so it cannot start the service.
_S36_PIN=""
for c in "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
         "/data/.openclaw/onboarding/config/ghl-mcp-pin.env" \
         "$SKILL_DIR/../config/ghl-mcp-pin.env"; do
  [ -f "$c" ] && _S36_PIN="$c" && break
done

_S36_LIFECYCLE=""
for c in "$HOME/.openclaw/onboarding/scripts/ghl-mcp-autostart.sh" \
         "/data/.openclaw/onboarding/scripts/ghl-mcp-autostart.sh" \
         "$SKILL_DIR/../scripts/ghl-mcp-autostart.sh" \
         "$HOME/.openclaw/onboarding/scripts/ghl-mcp-probe.sh" \
         "/data/.openclaw/onboarding/scripts/ghl-mcp-probe.sh" \
         "$SKILL_DIR/../scripts/ghl-mcp-probe.sh" \
         "$HOME/.openclaw/onboarding/scripts/ghl-mcp-assert-runtime.sh" \
         "/data/.openclaw/onboarding/scripts/ghl-mcp-assert-runtime.sh" \
         "$SKILL_DIR/../scripts/ghl-mcp-assert-runtime.sh" \
         "$SKILL_DIR/../platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh"; do
  [ -f "$c" ] && _S36_LIFECYCLE="$_S36_LIFECYCLE
$c"
done
if [ -z "$_S36_LIFECYCLE" ]; then
  assert "community MCP lifecycle scripts are retired (no start/probe/assert script ships)" "true"
else
  _S36_ALL_INERT=0
  while IFS= read -r c; do
    [ -n "$c" ] || continue
    grep -q 'GHL_MCP_RETIRED' "$c" 2>/dev/null || _S36_ALL_INERT=1
  done <<EOF
$_S36_LIFECYCLE
EOF
  assert "every shipped community MCP lifecycle script is inert (carries GHL_MCP_RETIRED)" "[ \"$_S36_ALL_INERT\" -eq 0 ]"
  if [ "$_S36_ALL_INERT" -ne 0 ]; then
    while IFS= read -r c; do
      [ -n "$c" ] || continue
      grep -q 'GHL_MCP_RETIRED' "$c" 2>/dev/null || echo "    live lifecycle surface: $c"
    done <<EOF
$_S36_LIFECYCLE
EOF
  fi
fi
if [ -f "$_S36_PIN" ] && ! grep -qiE '^GHL_MCP_(RETIRED|STATUS)=.*(1|true|yes|retired)' "$_S36_PIN"; then
  warn_only "retired community MCP pin file is gone or marked retired (stale pin still ships: $_S36_PIN)" "false"
else
  assert "community MCP pin config is retired or absent" "true"
fi
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
# Neither a location id nor a pit- token exists (or the token's location is unreadable):
# the skill is installed, with ONE note naming what is needed. The checks below need an
# account, so they are skipped rather than failed.
if [ "${GHL_CREDS_STATUS:-}" = "missing" ] || [ "${GHL_CREDS_STATUS:-}" = "unresolved" ]; then
  yellow "  ⚠ WARN — $GHL_CREDS_NOTE"; WARN=$((WARN+1))
  echo ""
  echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
  [ $FAIL -gt 0 ] && { red "Skill 36 QC FAILED"; exit 1; } || { green "Skill 36 QC PASS (installed with a note)"; exit 0; }
fi
assert "GHL PIT set (any canonical alias)"         "[ -n \"$RESOLVED_PIT\" ]"
assert "GHL PIT starts with pit-"                 "[[ \"$RESOLVED_PIT\" == pit-* ]]"
assert "GOHIGHLEVEL_LOCATION_ID is set"            "[ -n \"$GOHIGHLEVEL_LOCATION_ID\" ]"
assert "Canonical secrets file exists"             "[ -f \"$SECRETS_ENV\" ]"
SEC_MODE=$(stat -c %a "$SECRETS_ENV" 2>/dev/null || stat -f %A "$SECRETS_ENV" 2>/dev/null)
assert "Secrets file is chmod 600"                 "[ \"$SEC_MODE\" = '600' ]"
warn_only "PIT mirrored in openclaw.json env.vars" "command -v openclaw && openclaw config get env.vars.GOHIGHLEVEL_API_KEY 2>/dev/null | grep -q 'pit-'"
warn_only "Location ID in openclaw.json env.vars"  "command -v openclaw && openclaw config get env.vars.GOHIGHLEVEL_LOCATION_ID 2>/dev/null | grep -q ."
assert "GHL_COMMUNITY_MCP_URL env var RETIRED (must not be set)" \
  "! { command -v openclaw >/dev/null 2>&1 && openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>/dev/null | grep -qE 'http://localhost:[0-9]+'; }"

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
echo "── Section D: Tier 2 (Community MCP) — RETIRED ──"
# v22.0.0: community MCP is RETIRED (operator decision). Section D no longer
# asserts a live service. It asserts the retired end state: no process, no
# listener, no supervisor registration, no mcp.servers entry, no probe, no
# resurrection hook. Every probe below is read-only.
S36_PORT=8765
if [ -n "${_S36_PIN:-}" ] && [ -f "${_S36_PIN:-}" ]; then
  _S36_PORT_FROM_PIN=$(sed -n 's/^GHL_MCP_PORT="\{0,1\}\([0-9][0-9]*\)"\{0,1\}.*/\1/p' "$_S36_PIN" | head -1)
  [ -n "$_S36_PORT_FROM_PIN" ] && S36_PORT="$_S36_PORT_FROM_PIN"
fi

# Retired process identity: the install dir, the launch wrapper, or the dist main.
_s36_process_running() {
  ps -A -o command= 2>/dev/null | grep -E '[g]hl-community-mcp'
}

# Listener on the configured port. rc 2 = cannot tell (no lsof and no ss).
_s36_port_listening() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$S36_PORT" -sTCP:LISTEN 2>/dev/null | grep -q .
  elif command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -qE "[:.]${S36_PORT}[[:space:]]"
  else
    return 2
  fi
}

# pm2 persistence: the dump is what `pm2 resurrect` restores. Its dump file is
# readable without spawning a daemon.
_s36_pm2_dump_registers() {
  local pm2home="${PM2_HOME:-$HOME/.pm2}"
  [ -f "$pm2home/dump.pm2" ] && grep -q 'ghl-community-mcp' "$pm2home/dump.pm2"
}

assert "ghl-community-mcp NOT registered in mcp.servers (RETIRED)" \
  "! { command -v openclaw >/dev/null 2>&1 && openclaw mcp list 2>/dev/null | grep -q 'ghl-community-mcp'; }"
assert "no ghl-community-mcp process is running (RETIRED)" "! _s36_process_running >/dev/null 2>&1"
if command -v lsof >/dev/null 2>&1 || command -v ss >/dev/null 2>&1; then
  assert "no listener on the retired community MCP port ($S36_PORT)" "! _s36_port_listening"
else
  warn_only "no listener on the retired community MCP port ($S36_PORT) — UNDETERMINED (neither lsof nor ss on PATH)" "false"
fi

if [ "${OPENCLAW_PLATFORM:-}" = "mac" ]; then
  assert "launchd job com.clawd.ghl-mcp is not loaded (RETIRED)" \
    "! launchctl print gui/$(id -u)/com.clawd.ghl-mcp >/dev/null 2>&1"
  assert "launchd plist com.clawd.ghl-mcp is removed (no RunAtLoad resurrection)" \
    "[ ! -f \"$HOME/Library/LaunchAgents/com.clawd.ghl-mcp.plist\" ]"
  assert "launchd probe com.clawd.ghl-mcp-probe is removed and not loaded (RETIRED)" \
    "[ ! -f \"$HOME/Library/LaunchAgents/com.clawd.ghl-mcp-probe.plist\" ] && ! launchctl print gui/$(id -u)/com.clawd.ghl-mcp-probe >/dev/null 2>&1"
  assert "com.clawd.ghl-mcp is not ENABLED in the launchd override database" \
    "! { command -v launchctl >/dev/null 2>&1 && launchctl print-disabled gui/$(id -u) 2>/dev/null | grep -q '\"com.clawd.ghl-mcp\" => enabled'; }"
else
  assert "pm2 dump no longer registers ghl-community-mcp (no @reboot resurrect)" \
    "! _s36_pm2_dump_registers"
  if command -v pm2 >/dev/null 2>&1 && [ -f "${PM2_HOME:-$HOME/.pm2}/pm2.pid" ] \
     && kill -0 "$(cat "${PM2_HOME:-$HOME/.pm2}/pm2.pid" 2>/dev/null)" 2>/dev/null; then
    assert "pm2 live process list does not contain ghl-community-mcp (RETIRED)" \
      "! { pm2 jlist 2>/dev/null | grep -q 'ghl-community-mcp'; }"
  else
    warn_only "live pm2 process list does not contain ghl-community-mcp — UNDETERMINED (no running pm2 daemon)" "false"
  fi
  if command -v systemctl >/dev/null 2>&1; then
    assert "systemd unit ghl-mcp is not enabled or active (RETIRED)" \
      "! systemctl is-enabled ghl-mcp 2>/dev/null | grep -qE '^enabled(-runtime)?$' && ! systemctl is-active ghl-mcp 2>/dev/null | grep -q '^active$'"
  else
    warn_only "systemd unit ghl-mcp is absent (RETIRED) — UNDETERMINED (no systemctl on PATH)" "false"
  fi
fi
assert "no @reboot resurrect cron entry for the community MCP (RETIRED)" \
  "! { command -v crontab >/dev/null 2>&1 && crontab -l 2>/dev/null | grep -qiE 'ghl-(community-)?mcp'; }"

# A stale env var is harmless only while nothing answers on it. If it survived
# the migration, the endpoint must still be dead.
S36_OLD_URL=""
if command -v openclaw >/dev/null 2>&1; then
  S36_OLD_URL=$(openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>/dev/null | tr -d '\n' | sed 's|/$||')
fi
assert "the legacy community MCP URL does not answer (RETIRED)" \
  "[ -z \"$S36_OLD_URL\" ] || ! curl -sS -m 5 \"$S36_OLD_URL/health\" 2>/dev/null | grep -q ."

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
