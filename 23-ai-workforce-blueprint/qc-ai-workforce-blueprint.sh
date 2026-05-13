#!/usr/bin/env bash
# Skill 23 — AI Workforce Blueprint — Install QC (MAIN ORCHESTRATOR ONLY)
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
echo "═══ Skill 23 — AI Workforce Blueprint — Install QC ═══"
echo ""
assert "Skill 23 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/23-ai-workforce-blueprint\" ]"
assert "Skill 22 (Persona) installed FIRST" "[ -d \"$SKILLS_DIR_DEFAULT/22-book-to-persona-coaching-leadership-system\" ]"
warn_only "Interview state evidence (A/B/C): answers, departments, or ORG-CHART" \
  "[ -f \"$WORKSPACE/workforce-interview-answers.md\" ] || [ -d \"$WORKSPACE/departments\" ] || [ -f \"$WORKSPACE/ORG-CHART.md\" ]"
warn_only "departments/ folder OR ORG-CHART.md exists (STATE C — complete)" "[ -d \"$WORKSPACE/departments\" ] || [ -f \"$WORKSPACE/ORG-CHART.md\" ]"
warn_only "company-config.json present" "[ -f \"$WORKSPACE/company-config.json\" ] || find \"$WORKSPACE\" -maxdepth 3 -name 'company-config.json' 2>/dev/null | head -1 | grep -q ."
warn_only "AGENTS.md notes 'Skill 23 MAIN ORCHESTRATOR ONLY'" "grep -qiE 'skill 23.*main orchestrator|workforce.*main orchestrator' \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
assert "Python 3 installed" "command -v python3"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 23 QC FAILED"; exit 1; } || { green "Skill 23 QC PASS"; exit 0; }
