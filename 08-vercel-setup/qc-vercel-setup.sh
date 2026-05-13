#!/usr/bin/env bash
# Skill 08 — Vercel Setup — Install QC
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
: "${VERCEL_TOKEN:=}"

echo ""
echo "═══ Skill 08 — Vercel Setup — Install QC ═══"
echo ""
assert "Skill 08 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/08-vercel-setup\" ]"
assert "Node.js installed" "command -v node"
assert "npm installed" "command -v npm"
assert "jq installed" "command -v jq"
assert "vercel CLI installed" "command -v vercel"
assert "VERCEL_TOKEN set" "[ -n \"$VERCEL_TOKEN\" ]"
TOKEN_TEST=$(curl -sS -m 10 -H "Authorization: Bearer $VERCEL_TOKEN" "https://api.vercel.com/v2/user" 2>/dev/null)
warn_only "Vercel token validates" "echo \"$TOKEN_TEST\" | grep -qE '\"user\"|\"username\"|\"email\"'"
warn_only "TOOLS.md references Vercel" "grep -qi 'vercel' \"$WORKSPACE/TOOLS.md\" 2>/dev/null"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 08 QC FAILED"; exit 1; } || { green "Skill 08 QC PASS"; exit 0; }
