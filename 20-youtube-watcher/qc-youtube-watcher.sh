#!/usr/bin/env bash
# Skill 20 — YouTube Watcher — Install QC
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
: "${YOUTUBE_API_KEY:=}"; : "${GOOGLE_API_KEY:=}"

echo ""
echo "═══ Skill 20 — YouTube Watcher — Install QC ═══"
echo ""
assert "Skill 20 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/20-youtube-watcher\" ]"
warn_only "YouTube API access (YOUTUBE_API_KEY or GOOGLE_API_KEY)" "[ -n \"$YOUTUBE_API_KEY\" ] || [ -n \"$GOOGLE_API_KEY\" ]"
warn_only "MEMORY.md has watched-channels list" "grep -qiE 'youtube_watch|watched_channel|channel.*to.*watch' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"
warn_only "HEARTBEAT.md has YouTube watcher schedule" "grep -qiE 'youtube|watcher' \"$WORKSPACE/HEARTBEAT.md\" 2>/dev/null"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 20 QC FAILED"; exit 1; } || { green "Skill 20 QC PASS"; exit 0; }
