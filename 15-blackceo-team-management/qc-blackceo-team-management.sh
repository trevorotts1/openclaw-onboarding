#!/usr/bin/env bash
# Skill 15 — BlackCEO Team Management — Install QC
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { if [ -d "/data/.openclaw" ]; then export SECRETS_ENV="/data/.openclaw/secrets/.env" WORKSPACE="/data/clawd" SKILLS_DIR_DEFAULT="/data/.openclaw/skills" OPENCLAW_PLATFORM="vps"; else export SECRETS_ENV="$HOME/.openclaw/secrets/.env" WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills" OPENCLAW_PLATFORM="mac"; fi; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${CLIENT_ID:=}"

echo ""
echo "═══ Skill 15 — BlackCEO Team Management — Install QC ═══"
echo ""
assert "Skill 15 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/15-blackceo-team-management\" ]"
assert "CLIENT_ID env OR stored in MEMORY.md" \
  "[ -n \"$CLIENT_ID\" ] || grep -qE 'CLIENT_ID|owner.*telegram|telegram.*owner' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"
warn_only "TEAM_MEMBER_*_ID values present (not placeholders)" \
  "env | grep -E '^TEAM_MEMBER_[0-9]+_ID=[0-9]{7,}' | grep -vE '_ID=1234567890|_ID=0000' | head -1 | grep -q ."
warn_only "AGENTS.md references team management" "grep -qiE 'team management|TEAM_MEMBER' \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
warn_only "Python 3 installed" "command -v python3"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 15 QC FAILED"; exit 1; } || { green "Skill 15 QC PASS"; exit 0; }
