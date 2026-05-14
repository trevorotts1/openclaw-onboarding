#!/usr/bin/env bash
# Skill 29 — GHL Convert and Flow API — Install QC (Tier 3 reference)
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export SECRETS_ENV="$HOME/.openclaw/secrets/.env" WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${GOHIGHLEVEL_API_KEY:=}"; : "${GOHIGHLEVEL_LOCATION_ID:=}"

echo ""
echo "═══ Skill 29 — GHL Convert and Flow API — Install QC ═══"
echo ""
assert "Skill 29 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/29-ghl-convert-and-flow\" ]"
assert "GOHIGHLEVEL_API_KEY (PIT) set"  "[ -n \"$GOHIGHLEVEL_API_KEY\" ]"
assert "Value starts with pit-"         "[[ \"$GOHIGHLEVEL_API_KEY\" == pit-* ]]"
assert "GOHIGHLEVEL_LOCATION_ID set"    "[ -n \"$GOHIGHLEVEL_LOCATION_ID\" ]"
assert "references/ subfolder present (Tier 3 lookup files)" "[ -d \"$SKILLS_DIR_DEFAULT/29-ghl-convert-and-flow/references\" ]"
warn_only "Master reference file in master-files folder" \
  "find $HOME/Downloads ~/Downloads -maxdepth 4 -name '*GoHighLevel*Master Reference*.md' -o -name '*Convert and Flow*Master Reference*.md' 2>/dev/null | head -1 | grep -q ."
warn_only "SKILL.md identifies this as Tier 3" "grep -qiE 'tier 3|tier.*36|skill 36' \"$SKILLS_DIR_DEFAULT/29-ghl-convert-and-flow/SKILL.md\" 2>/dev/null"
warn_only "jq installed" "command -v jq"
assert "Python 3 installed" "command -v python3"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 29 QC FAILED"; exit 1; } || { green "Skill 29 QC PASS"; exit 0; }
