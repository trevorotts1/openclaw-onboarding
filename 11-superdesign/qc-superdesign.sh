#!/usr/bin/env bash
# Skill 11 — Superdesign — Install QC
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
: "${ANTHROPIC_API_KEY:=}"; : "${OPENAI_API_KEY:=}"; : "${OPENROUTER_API_KEY:=}"

echo ""
echo "═══ Skill 11 — Superdesign — Install QC ═══"
echo ""
assert "Skill 11 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/11-superdesign\" ]"
assert "At least one LLM API key"   "[ -n \"$ANTHROPIC_API_KEY\" ] || [ -n \"$OPENAI_API_KEY\" ] || [ -n \"$OPENROUTER_API_KEY\" ]"
assert "Chrome installed"           "ls '/Applications/Google Chrome.app' 2>/dev/null || command -v google-chrome || command -v chromium"
assert "Node.js v16+ installed"     "node --version 2>/dev/null | grep -qE 'v(1[6-9]|[2-9][0-9])'"
assert "npm installed" "command -v npm"
warn_only "Superdesign plugin enabled in openclaw.json" "command -v openclaw && openclaw config get plugins.enabled 2>/dev/null | grep -qi 'superdesign'"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 11 QC FAILED"; exit 1; } || { green "Skill 11 QC PASS"; exit 0; }
