#!/usr/bin/env bash
# Skill 03 — Agent Browser — Install QC
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

echo ""
echo "═══ Skill 03 — Agent Browser — Install QC ═══"
echo ""
assert "Skill 03 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/03-agent-browser\" ]"
assert "Node.js installed" "command -v node"
assert "npm installed" "command -v npm"
assert "agent-browser CLI on PATH" "command -v agent-browser || npm list -g --depth=0 2>/dev/null | grep -q agent-browser"
warn_only "agent-browser --help responds" "agent-browser --help 2>&1 | grep -qiE 'agent.browser|usage|command'"
warn_only "TOOLS.md references agent-browser" "grep -qiE 'agent.browser' \"$WORKSPACE/TOOLS.md\" 2>/dev/null"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 03 QC FAILED"; exit 1; } || { green "Skill 03 QC PASS"; exit 0; }
