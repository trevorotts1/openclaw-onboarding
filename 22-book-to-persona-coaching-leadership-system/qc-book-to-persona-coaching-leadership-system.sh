#!/usr/bin/env bash
# Skill 22 — Book-to-Persona Coaching Leadership System — Install QC (MAIN ORCHESTRATOR ONLY)
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
: "${GEMINI_API_KEY:=}"; : "${GOOGLE_API_KEY:=}"

echo ""
echo "═══ Skill 22 — Book-to-Persona Coaching Leadership — Install QC ═══"
echo ""
assert "Skill 22 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/22-book-to-persona-coaching-leadership-system\" ]"
assert "Skill 31 (Memory) installed FIRST" "[ -d \"$SKILLS_DIR_DEFAULT/31-upgraded-memory-system\" ]"
warn_only "coaching-personas folder exists (40 personas)" "[ -d \"$WORKSPACE/coaching-personas\" ] || find $HOME/Downloads ~/Downloads -maxdepth 4 -name 'coaching-personas' 2>/dev/null | head -1 | grep -q ."
warn_only "persona-categories.json present (12 domain + 6 perspective tags)" "find $HOME/Downloads ~/Downloads \"$WORKSPACE\" -maxdepth 5 -name 'persona-categories.json' 2>/dev/null | head -1 | grep -q ."
warn_only "PERSONA-ROUTER.md present" "find $HOME/Downloads ~/Downloads \"$WORKSPACE\" -maxdepth 5 -name 'PERSONA-ROUTER.md' 2>/dev/null | head -1 | grep -q ."
assert "Embedding API key (Gemini OR Google)" "[ -n \"$GEMINI_API_KEY\" ] || [ -n \"$GOOGLE_API_KEY\" ]"
warn_only "AGENTS.md notes 'Skill 22 MAIN ORCHESTRATOR ONLY'" "grep -qiE 'main orchestrator only|skill 22.*never delegate' \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 22 QC FAILED"; exit 1; } || { green "Skill 22 QC PASS"; exit 0; }
