#!/usr/bin/env bash
# Skill 30 — Fish Audio API Reference — Install QC
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
: "${FISH_AUDIO_API_KEY:=}"; : "${FISH_AUDIO_VOICE_ID:=}"

echo ""
echo "═══ Skill 30 — Fish Audio API Reference — Install QC ═══"
echo ""
assert "Skill 30 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/30-fish-audio-api-reference\" ]"
assert "FISH_AUDIO_API_KEY set" "[ -n \"$FISH_AUDIO_API_KEY\" ]"
assert "FISH_AUDIO_VOICE_ID set" "[ -n \"$FISH_AUDIO_VOICE_ID\" ]"
KEY_TEST=$(curl -sS -m 10 -H "Authorization: Bearer $FISH_AUDIO_API_KEY" "https://api.fish.audio/wallet/self/api-credit" 2>/dev/null)
warn_only "Fish Audio API responds (credit endpoint)" "echo \"$KEY_TEST\" | grep -qE 'credit|balance|user|wallet'"
warn_only "Master ref doc present in master-files" "find $HOME/Downloads ~/Downloads -maxdepth 4 -iname '*fish*audio*' 2>/dev/null | head -1 | grep -q ."
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 30 QC FAILED"; exit 1; } || { green "Skill 30 QC PASS"; exit 0; }
