#!/usr/bin/env bash
# Skill 05 — GHL Setup — Install QC (PIT, NOT API key)
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { if [ -d "/data/.openclaw" ]; then export SECRETS_ENV="/data/.openclaw/secrets/.env" CONFIG_JSON="/data/.openclaw/openclaw.json" WORKSPACE="/data/clawd" SKILLS_DIR_DEFAULT="/data/.openclaw/skills" OPENCLAW_PLATFORM="vps"; else export SECRETS_ENV="$HOME/.openclaw/secrets/.env" CONFIG_JSON="$HOME/.openclaw/openclaw.json" WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills" OPENCLAW_PLATFORM="mac"; fi; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${GOHIGHLEVEL_API_KEY:=}"; : "${GOHIGHLEVEL_LOCATION_ID:=}"

echo ""
echo "═══ Skill 05 — GHL Setup — Install QC ═══"
echo ""
assert "Skill 05 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/05-ghl-setup\" ]"
assert "GOHIGHLEVEL_API_KEY (PIT) set"            "[ -n \"$GOHIGHLEVEL_API_KEY\" ]"
assert "Value starts with pit- (confirms PIT)"    "[[ \"$GOHIGHLEVEL_API_KEY\" == pit-* ]]"
assert "GOHIGHLEVEL_LOCATION_ID set"              "[ -n \"$GOHIGHLEVEL_LOCATION_ID\" ]"
assert "Location ID 18-24 chars"                  "[ \"\${#GOHIGHLEVEL_LOCATION_ID}\" -ge 18 ] && [ \"\${#GOHIGHLEVEL_LOCATION_ID}\" -le 24 ]"
assert "Secrets file chmod 600"                   "[ \"\$(stat -f %A \"$SECRETS_ENV\" 2>/dev/null || stat -c %a \"$SECRETS_ENV\" 2>/dev/null)\" = '600' ]"
RESP=$(curl -sS -m 10 -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" -H "Version: 2021-07-28" \
  "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID" 2>/dev/null)
assert "Location endpoint returns valid id"       "echo \"$RESP\" | grep -qE '\"id\"\\s*:\\s*\"[A-Za-z0-9]'"
warn_only "Location returns business name"        "echo \"$RESP\" | grep -qE '\"name\"\\s*:\\s*\"[^\"]+\"'"
warn_only "Core files teach GHL aliases"          "grep -qE 'GHL|GoHighLevel|Convert and Flow' \"$WORKSPACE/AGENTS.md\" \"$WORKSPACE/TOOLS.md\" 2>/dev/null"
warn_only "Core files clarify PIT not API key"    "grep -qiE 'Private Integration Token|PIT' \"$WORKSPACE/AGENTS.md\" \"$WORKSPACE/TOOLS.md\" \"$WORKSPACE/MEMORY.md\" 2>/dev/null"
assert "PIT NOT exposed in workspace .md files"   "! grep -rE 'pit-[a-f0-9]{8}-[a-f0-9]{4}' \"$WORKSPACE\"/*.md 2>/dev/null | grep -v 'pit-XXX\\|pit-xxx\\|pit-x'"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 05 QC FAILED"; exit 1; } || { green "Skill 05 QC PASS"; exit 0; }
