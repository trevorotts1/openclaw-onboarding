#!/usr/bin/env bash
# Skill 19 — Humanizer — Install QC
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { if [ -d "/data/.openclaw" ]; then export WORKSPACE="/data/clawd" SKILLS_DIR_DEFAULT="/data/.openclaw/skills" OPENCLAW_PLATFORM="vps"; else export WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills" OPENCLAW_PLATFORM="mac"; fi; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

echo ""
echo "═══ Skill 19 — Humanizer — Install QC ═══"
echo ""
assert "Skill 19 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/19-humanizer\" ]"
warn_only "AGENTS.md or SOUL.md bans em dashes" "grep -qE 'em dash|—' \"$WORKSPACE/AGENTS.md\" \"$WORKSPACE/SOUL.md\" 2>/dev/null"
warn_only "AGENTS.md or SOUL.md bans AI-tell phrases" "grep -qiE 'as an AI|large language model|AI tell|humaniz' \"$WORKSPACE/AGENTS.md\" \"$WORKSPACE/SOUL.md\" 2>/dev/null"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 19 QC FAILED"; exit 1; } || { green "Skill 19 QC PASS"; exit 0; }
