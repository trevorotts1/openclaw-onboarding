#!/usr/bin/env bash
# Skill 02 — Back Yourself Up Protocol (BYUP) — Install QC
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { if [ -d "/data/.openclaw" ]; then export WORKSPACE="/data/clawd" SKILLS_DIR_DEFAULT="/data/.openclaw/skills" OPENCLAW_PLATFORM="vps" BACKUP_DIR_DEFAULT="$HOME/openclaw-backups"; else export WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills" OPENCLAW_PLATFORM="mac" BACKUP_DIR_DEFAULT="$HOME/Downloads/openclaw-backups"; fi; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

echo ""
echo "═══ Skill 02 — Back Yourself Up Protocol — Install QC ═══"
echo ""
assert "BYUP folder present" "[ -d \"$SKILLS_DIR_DEFAULT/02-back-yourself-up-protocol\" ]"
assert "Backup directory writable" "mkdir -p \"$BACKUP_DIR_DEFAULT\" && [ -w \"$BACKUP_DIR_DEFAULT\" ]"
warn_only "Past openclaw.json backups (proves BYUP was used)" "ls $BACKUP_DIR_DEFAULT/openclaw.json* 2>/dev/null | head -1 | grep -q ."
warn_only "AGENTS.md references backup/BYUP discipline" "grep -qiE 'back.yourself.up|BYUP|backup.protocol' \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
TESTFILE="/tmp/byup-test-$$.txt"; echo "test" > "$TESTFILE"
warn_only "Backup destination is writable" "cp \"$TESTFILE\" \"$BACKUP_DIR_DEFAULT/byup-test-$$.txt\" && [ -f \"$BACKUP_DIR_DEFAULT/byup-test-$$.txt\" ]"
rm -f "$TESTFILE" "$BACKUP_DIR_DEFAULT/byup-test-$$.txt"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 02 QC FAILED"; exit 1; } || { green "Skill 02 QC PASS"; exit 0; }
