#!/usr/bin/env bash
# Skill 32 — Command Center Setup — Install QC (Next.js dashboard)
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { if [ -d "/data/.openclaw" ]; then export SECRETS_ENV="/data/.openclaw/secrets/.env" WORKSPACE="/data/clawd" SKILLS_DIR_DEFAULT="/data/.openclaw/skills" OPENCLAW_PLATFORM="vps" CC_PORT=4000; else export SECRETS_ENV="$HOME/.openclaw/secrets/.env" WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills" OPENCLAW_PLATFORM="mac" CC_PORT=3000; fi; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${CLOUDFLARE_TUNNEL_TOKEN:=}"; : "${TUNNEL_TOKEN:=}"

echo ""
echo "═══ Skill 32 — Command Center Setup — Install QC ═══"
echo ""
assert "Skill 32 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/32-command-center-setup\" ]"
assert "Skill 23 (Workforce — provides ORG-CHART CC reads) installed" "[ -d \"$SKILLS_DIR_DEFAULT/23-ai-workforce-blueprint\" ]"
warn_only "Command Center repo cloned locally" "find $HOME /data -maxdepth 4 -type d -name 'blackceo-command-center' 2>/dev/null | head -1 | grep -q ."
warn_only "package.json exists in CC repo"     "find $HOME /data -maxdepth 4 -path '*blackceo-command-center/package.json' 2>/dev/null | head -1 | grep -q ."
assert "Node.js installed" "command -v node"
assert "npm installed" "command -v npm"
warn_only "PM2 installed" "command -v pm2"
warn_only "cloudflared installed (Mac only — VPS skip)" "[ \"$OPENCLAW_PLATFORM\" = 'vps' ] || command -v cloudflared"
warn_only "Cloudflare tunnel token present" "[ -n \"$CLOUDFLARE_TUNNEL_TOKEN\" ] || [ -n \"$TUNNEL_TOKEN\" ]"
warn_only "Port ${CC_PORT} reachable (CC running locally)" "curl -sS -m 3 http://localhost:${CC_PORT}/ -o /dev/null -w '%{http_code}' 2>/dev/null | grep -qE '^(200|301|302|404|307)'"
assert "Python 3 installed" "command -v python3"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 32 QC FAILED"; exit 1; } || { green "Skill 32 QC PASS"; exit 0; }
