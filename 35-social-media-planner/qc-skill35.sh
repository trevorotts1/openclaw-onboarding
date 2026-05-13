#!/usr/bin/env bash
# ============================================================
#  Skill 35 — Social Media Planner — Install QC Script (v2.0.0)
#  Exits 0 if all assertions pass. Non-zero = blocker.
# ============================================================

set -u
PASS=0; FAIL=0; WARN=0

# Source shared library if reachable
LIB="$(dirname "$0")/../lib-shared.sh"
[ -f "$LIB" ] || LIB="$HOME/.openclaw/skills/lib-shared.sh"
[ -f "$LIB" ] && source "$LIB"

# Fallback platform resolution if lib-shared not present
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() {
    if [ -d "/data/.openclaw" ]; then
      export OPENCLAW_PLATFORM="vps"
      export SECRETS_ENV="/data/.openclaw/secrets/.env"
      export WORKSPACE="/data/clawd"
    else
      export OPENCLAW_PLATFORM="mac"
      export SECRETS_ENV="$HOME/.openclaw/secrets/.env"
      export WORKSPACE="$HOME/clawd"
    fi
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

if [ -f "$SECRETS_ENV" ]; then
  set +u
  set -a
  . "$SECRETS_ENV" 2>/dev/null || true
  set +a
  set -u
fi
# Default unset vars to empty so set -u doesn't blow up
: "${GOHIGHLEVEL_API_KEY:=}"
: "${GOHIGHLEVEL_LOCATION_ID:=}"
: "${KIE_API_KEY:=}"
: "${FISH_AUDIO_API_KEY:=}"
: "${FISH_AUDIO_VOICE_ID:=}"
: "${PODBEAN_PODCAST_ID:=}"

echo ""
echo "═══════════════════════════════════════════════"
echo "  Skill 35 — Social Media Planner — Install QC"
echo "═══════════════════════════════════════════════"
echo "  Platform: ${OPENCLAW_PLATFORM:-unknown}"
echo "  Date:     $(date)"
echo ""

echo "── Section A: Prerequisites ──"
assert "Skill 01 (TYP) installed"   "[ -d \"$HOME/.openclaw/skills/01-teach-yourself-protocol\" ] || [ -d \"/data/.openclaw/skills/01-teach-yourself-protocol\" ]"
assert "Skill 02 (BYUP) installed"  "[ -d \"$HOME/.openclaw/skills/02-back-yourself-up-protocol\" ] || [ -d \"/data/.openclaw/skills/02-back-yourself-up-protocol\" ]"
assert "Skill 22 (Persona) installed" "[ -d \"$HOME/.openclaw/skills/22-book-to-persona-coaching-leadership-system\" ] || [ -d \"/data/.openclaw/skills/22-book-to-persona-coaching-leadership-system\" ]"
assert "Skill 31 (Memory) installed" "[ -d \"$HOME/.openclaw/skills/31-upgraded-memory-system\" ] || [ -d \"/data/.openclaw/skills/31-upgraded-memory-system\" ]"
warn_only "Skill 36 (GHL MCP) installed — recommended for MCP-first routing" \
  "[ -d \"$HOME/.openclaw/skills/36-ghl-mcp-setup\" ] || [ -d \"/data/.openclaw/skills/36-ghl-mcp-setup\" ]"

echo ""
echo "── Section B: GHL credentials (canonical names) ──"
assert "GOHIGHLEVEL_API_KEY (PIT) is set"     "[ -n \"${GOHIGHLEVEL_API_KEY:-}\" ]"
assert "GOHIGHLEVEL_API_KEY starts with pit-" "[[ \"${GOHIGHLEVEL_API_KEY:-}\" == pit-* ]]"
assert "GOHIGHLEVEL_LOCATION_ID is set"       "[ -n \"${GOHIGHLEVEL_LOCATION_ID:-}\" ]"
assert "GOHIGHLEVEL_LOCATION_ID is 18-24 chars"  "[ \"\${#GOHIGHLEVEL_LOCATION_ID}\" -ge 18 ] && [ \"\${#GOHIGHLEVEL_LOCATION_ID}\" -le 24 ]"
assert "Canonical secrets file exists"        "[ -f \"$SECRETS_ENV\" ]"
SEC_MODE=$(stat -f %A "$SECRETS_ENV" 2>/dev/null || stat -c %a "$SECRETS_ENV" 2>/dev/null)
assert "Secrets file is chmod 600"            "[ \"$SEC_MODE\" = '600' ]"
warn_only "Deprecated GHL_PRIVATE_TOKEN NOT in canonical secrets (should be migrated)" \
  "! grep -q '^GHL_PRIVATE_TOKEN=' \"$SECRETS_ENV\""

echo ""
echo "── Section C: GHL API access ──"
MCP_URL=""
if command -v openclaw >/dev/null 2>&1; then
  MCP_URL=$(openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>/dev/null | tr -d '\n' | sed 's|/$||')
fi
if [ -n "$MCP_URL" ] && curl -sS -m 5 "$MCP_URL/health" 2>/dev/null | grep -q "healthy"; then
  assert "Tier 2 (community MCP) reachable" "curl -sS -m 5 \"$MCP_URL/health\" | grep -q healthy"
  TEST=$(curl -sS -m 10 -X POST "$MCP_URL/execute" -H "Content-Type: application/json" \
    -d '{"name":"get_platform_accounts","arguments":{"limit":1}}' 2>/dev/null)
  warn_only "MCP get_platform_accounts returns data (any platform connected in GHL Social Planner)" \
    "echo \"$TEST\" | grep -qE '\"success\":\\s*true|\"result\"|accounts'"
else
  RESP=$(curl -sS -m 10 \
    -H "Authorization: Bearer ${GOHIGHLEVEL_API_KEY:-}" \
    -H "Version: 2021-07-28" \
    "https://services.leadconnectorhq.com/social-media-posting/oauth/${GOHIGHLEVEL_LOCATION_ID:-}/facebook/accounts" 2>/dev/null)
  warn_only "Direct API GHL Social Planner reachable (Facebook accounts endpoint)" \
    "echo \"$RESP\" | grep -qE 'accounts|results|\\[\\]'"
fi

echo ""
echo "── Section D: Required software ──"
assert "FFmpeg ≥4.0 installed"   "ffmpeg -version 2>/dev/null | head -1 | grep -qE 'ffmpeg version [4-9]'"
assert "ImageMagick installed"   "convert -version 2>/dev/null | grep -q 'ImageMagick'"
assert "Python 3 installed"      "python3 --version 2>/dev/null | grep -q 'Python 3'"

echo ""
echo "── Section E: Required additional credentials ──"
assert "KIE_API_KEY is set"               "[ -n \"${KIE_API_KEY:-}\" ]"
warn_only "FISH_AUDIO_API_KEY set (or podcast deferred)"  "[ -n \"${FISH_AUDIO_API_KEY:-}\" ] || grep -qi 'PODCAST_DEFERRED' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"
warn_only "FISH_AUDIO_VOICE_ID set (or podcast deferred)" "[ -n \"${FISH_AUDIO_VOICE_ID:-}\" ] || grep -qi 'PODCAST_DEFERRED' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"
warn_only "PODBEAN_PODCAST_ID set (or podcast deferred)"  "[ -n \"${PODBEAN_PODCAST_ID:-}\" ] || grep -qi 'PODCAST_DEFERRED' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"

echo ""
echo "── Section F: First-Run Protocol artifacts ──"
warn_only "Google Sheet URL stored in MEMORY.md" "grep -qE 'sheetUrl|docs.google.com/spreadsheets' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"
warn_only "Weekly action link stored in MEMORY.md" "grep -qiE 'SOCIAL_MEDIA_ACTION_LINK|weekly action link' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"
warn_only "Video preference stored in MEMORY.md" "grep -qiE 'VIDEO_PREFERENCE' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"

echo ""
echo "── Section G: Core .md wired ──"
warn_only "AGENTS.md has Social Media Planner section" "grep -qiE 'Social Media (Planner|Production)|Skill 35' \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
warn_only "TOOLS.md has GHL Social Planner reference"  "grep -qiE 'Social Planner|social-media-posting' \"$WORKSPACE/TOOLS.md\" 2>/dev/null"
warn_only "HEARTBEAT.md has Saturday theme request"    "grep -qiE 'Saturday.*theme|theme request' \"$WORKSPACE/HEARTBEAT.md\" 2>/dev/null"

echo ""
echo "── Section H: Security ──"
assert "PIT not present in any workspace .md file" "! grep -rE 'pit-[a-f0-9]{8}-[a-f0-9]{4}' \"$WORKSPACE\"/*.md 2>/dev/null | grep -v 'pit-XXX\\|pit-xxx\\|pit-x'"

echo ""
echo "═══════════════════════════════════════════════"
echo "  Result: $PASS passed | $FAIL failed | $WARN warnings"
echo "═══════════════════════════════════════════════"
SCORE=$(python3 -c "print(round(($PASS * 10) / ($PASS + $FAIL + 0.001), 1))" 2>/dev/null || echo "?")
echo "  Approx score: ${SCORE}/10 (excludes warnings)"
echo ""

if [ "$FAIL" -gt 0 ]; then
  red "Skill 35 install QC FAILED. Loop back, fix the failures, re-run."
  exit 1
elif [ "$WARN" -gt 3 ]; then
  yellow "Skill 35 install passed with multiple warnings. Review with the owner."
  exit 0
else
  green "Skill 35 install QC PASS."
  exit 0
fi
