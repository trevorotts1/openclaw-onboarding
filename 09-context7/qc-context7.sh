#!/usr/bin/env bash
# Skill 09 — Context7 — Install QC
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
: "${CONTEXT7_API_KEY:=}"

echo ""
echo "═══ Skill 09 — Context7 — Install QC ═══"
echo ""
assert "Skill 09 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/09-context7\" ]"
assert "CONTEXT7_API_KEY set" "[ -n \"$CONTEXT7_API_KEY\" ]"
warn_only "context7 MCP registered in openclaw" "command -v openclaw && openclaw mcp list 2>/dev/null | grep -qi 'context7'"
warn_only "TOOLS.md mentions context7" "grep -qi 'context7' \"$WORKSPACE/TOOLS.md\" 2>/dev/null"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 09 QC FAILED"; exit 1; } || { green "Skill 09 QC PASS"; exit 0; }
