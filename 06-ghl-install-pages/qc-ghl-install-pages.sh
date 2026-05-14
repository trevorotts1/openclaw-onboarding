#!/usr/bin/env bash
# Skill 06 — GHL Install Pages — Install QC (Playwright + GHL login)
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
: "${GHL_AGENCY_EMAIL:=}"; : "${GHL_AGENCY_PASSWORD:=}"; : "${GHL_EMAIL:=}"; : "${GHL_PASSWORD:=}"

echo ""
echo "═══ Skill 06 — GHL Install Pages — Install QC ═══"
echo ""
assert "Skill 06 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/06-ghl-install-pages\" ]"
assert "ghl-install-pages-full.md present" "[ -f \"$SKILLS_DIR_DEFAULT/06-ghl-install-pages/ghl-install-pages-full.md\" ]"
assert "GHL agency/login email set"     "[ -n \"$GHL_AGENCY_EMAIL\" ] || [ -n \"$GHL_EMAIL\" ]"
assert "GHL agency/login password set"  "[ -n \"$GHL_AGENCY_PASSWORD\" ] || [ -n \"$GHL_PASSWORD\" ]"
assert "Secrets file chmod 600"         "[ \"\$(stat -f %A \"$SECRETS_ENV\" 2>/dev/null || stat -c %a \"$SECRETS_ENV\" 2>/dev/null)\" = '600' ]"
assert "Node.js installed" "command -v node"
assert "npm installed" "command -v npm"
warn_only "Playwright installed"   "npm list -g playwright 2>/dev/null | grep -q playwright || npm list playwright 2>/dev/null | grep -q playwright || command -v playwright"
warn_only "Chrome/Chromium present" "command -v chromium || command -v google-chrome || ls '/Applications/Google Chrome.app' 2>/dev/null"
warn_only "Client white-label URL stored" "grep -qiE 'app\\.gohighlevel\\.com|app\\.convertandflow\\.com|app\\.[a-z0-9]+\\.com' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"
assert "GHL password NOT in workspace .md files" "! grep -rE 'GHL_(AGENCY_)?PASSWORD\\s*=\\s*[A-Za-z0-9]' \"$WORKSPACE\"/*.md 2>/dev/null | grep -v 'XXX\\|xxx'"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 06 QC FAILED"; exit 1; } || { green "Skill 06 QC PASS"; exit 0; }
