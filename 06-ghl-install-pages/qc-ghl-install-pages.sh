#!/usr/bin/env bash
# Skill 06 — GHL Install Pages — Install QC (agent-browser PRIMARY + Playwright FALLBACK + GHL auth)
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
SK="$SKILLS_DIR_DEFAULT/06-ghl-install-pages"
assert "Skill 06 folder present" "[ -d \"$SK\" ]"
assert "v3.0 hardened reference present" "[ -f \"$SK/ghl-browser-builder-full.md\" ]"
assert "auth-seed module present"   "[ -f \"$SK/tools/seed-ghl-auth.py\" ]"
assert "auth-inject script present" "[ -f \"$SK/tools/inject-ghl-auth.sh\" ]"
assert "builder helper present"     "[ -f \"$SK/tools/ghl_builder.py\" ]"
assert "gate registry present"      "[ -f \"$SK/tools/gates.json\" ]"
# D8 contract: exactly 2 captured gates (login form + auth storage), 26 runtime snapshot-gates.
assert "gate registry has 2 captured gates"  "[ \"\$(python3 -c 'import json;print(sum(1 for g in json.load(open(\"$SK/tools/gates.json\"))[\"gates\"] if g.get(\"status\")==\"captured\"))' 2>/dev/null)\" = '2' ]"
assert "gate registry has 26 runtime gates"  "[ \"\$(python3 -c 'import json;print(sum(1 for g in json.load(open(\"$SK/tools/gates.json\"))[\"gates\"] if g.get(\"status\")==\"runtime\"))' 2>/dev/null)\" = '26' ]"
assert "builder helper parses clean" "python3 -c \"import ast;ast.parse(open('$SK/tools/ghl_builder.py').read())\""
assert "auth-seed module parses clean" "python3 -c \"import ast;ast.parse(open('$SK/tools/seed-ghl-auth.py').read())\""
assert "GHL agency/login email set"     "[ -n \"$GHL_AGENCY_EMAIL\" ] || [ -n \"$GHL_EMAIL\" ]"
assert "GHL agency/login password set"  "[ -n \"$GHL_AGENCY_PASSWORD\" ] || [ -n \"$GHL_PASSWORD\" ]"
assert "Secrets file chmod 600"         "[ \"\$(stat -f %A \"$SECRETS_ENV\" 2>/dev/null || stat -c %a \"$SECRETS_ENV\" 2>/dev/null)\" = '600' ]"
assert "Node.js installed" "command -v node"
assert "npm installed" "command -v npm"
warn_only "agent-browser installed (PRIMARY engine)" "command -v agent-browser || [ -x \"$HOME/.npm-global/bin/agent-browser\" ]"
warn_only "Playwright installed (FALLBACK)"   "npm list -g playwright 2>/dev/null | grep -q playwright || npm list playwright 2>/dev/null | grep -q playwright || command -v playwright"
warn_only "Firebase refresh token set (seeds logged-in session)" "[ -n \"\${GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN:-}\" ] || [ -n \"\${CAF_FIREBASE_REFRESH_TOKEN:-}\" ] || [ -n \"\${GHL_FIREBASE_REFRESH_TOKEN:-}\" ]"
warn_only "Chrome/Chromium present" "command -v chromium || command -v google-chrome || ls '/Applications/Google Chrome.app' 2>/dev/null"
warn_only "Client white-label URL stored" "grep -qiE 'app\\.gohighlevel\\.com|app\\.convertandflow\\.com|app\\.[a-z0-9]+\\.com' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"
assert "GHL password NOT in workspace .md files" "! grep -rE 'GHL_(AGENCY_)?PASSWORD\\s*=\\s*[A-Za-z0-9]' \"$WORKSPACE\"/*.md 2>/dev/null | grep -v 'XXX\\|xxx'"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 06 QC FAILED"; exit 1; } || { green "Skill 06 QC PASS"; exit 0; }
