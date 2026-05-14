#!/usr/bin/env bash
# Skill 25 — Video Creator — Install QC
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
: "${KIE_API_KEY:=}"; : "${PIKA_API_KEY:=}"; : "${RUNWAY_API_KEY:=}"

echo ""
echo "═══ Skill 25 — Video Creator — Install QC ═══"
echo ""
assert "Skill 25 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/25-video-creator\" ]"
assert "FFmpeg installed" "command -v ffmpeg"
assert "ImageMagick installed" "command -v convert"
assert "At least one video-gen API key (KIE/Pika/Runway)" "[ -n \"$KIE_API_KEY\" ] || [ -n \"$PIKA_API_KEY\" ] || [ -n \"$RUNWAY_API_KEY\" ]"
assert "Python 3 installed" "command -v python3"
warn_only "ffprobe available" "command -v ffprobe"
warn_only "Skill 07 (KIE) installed if KIE chosen" "[ -z \"$KIE_API_KEY\" ] || [ -d \"$SKILLS_DIR_DEFAULT/07-kie-setup\" ]"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 25 QC FAILED"; exit 1; } || { green "Skill 25 QC PASS"; exit 0; }
