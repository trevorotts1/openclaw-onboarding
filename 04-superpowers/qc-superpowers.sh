#!/usr/bin/env bash
# Skill 04 — Superpowers — Install QC (coding discipline rules)
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
echo "═══ Skill 04 — Superpowers — Install QC ═══"
echo ""
assert "Skill 04 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/04-superpowers\" ]"
warn_only "Companion files preserved (git clone install, not curl)" "find \"$SKILLS_DIR_DEFAULT/04-superpowers\" -type f \\( -name '*.py' -o -name '*.js' -o -name 'brainstorm*' \\) 2>/dev/null | head -1 | grep -q ."
warn_only "AGENTS.md references superpowers" "grep -qiE 'superpowers|plan.before.build|prove.before.claim|brainstorm' \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
assert "Python 3 installed" "command -v python3"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 04 QC FAILED"; exit 1; } || { green "Skill 04 QC PASS"; exit 0; }
