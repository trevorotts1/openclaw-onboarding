#!/usr/bin/env bash
# Skill 02 — Back Yourself Up Protocol (BYUP) — Install QC
# PRD 1.9: added zero-human-company tree coverage check (QC fails if absent).
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills" BACKUP_DIR_DEFAULT="$HOME/Downloads/openclaw-backups"; }
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

# PRD 1.9: the BYUP backup set MUST include the zero-human-company tree.
# Detect the canonical company root via detect_platform.py (or fall back to
# ~/Downloads/openclaw-master-files/zero-human-company for Mac).
PYTHON="$(command -v python3 || command -v python || echo "")"
COMPANY_ROOT=""
if [ -n "$PYTHON" ]; then
  SHARED_UTILS="$SKILL_DIR/../shared-utils"
  COMPANY_ROOT="$($PYTHON 2>/dev/null - <<PYEOF
import sys, os
su = os.path.realpath("$SHARED_UTILS")
sys.path.insert(0, su)
try:
    from detect_platform import get_openclaw_paths
    p = get_openclaw_paths()
    print(p['company_root'])
except Exception:
    pass
PYEOF
)"
fi
if [ -z "$COMPANY_ROOT" ]; then
  if [ -d /data/.openclaw ]; then
    COMPANY_ROOT="/data/openclaw-master-files/zero-human-company"
  else
    COMPANY_ROOT="$HOME/Downloads/openclaw-master-files/zero-human-company"
  fi
fi

# Check that the BYUP instructions reference the zero-human-company tree.
assert "PRD 1.9: Skill 02 INSTRUCTIONS.md covers zero-human-company backup" \
  "grep -qE 'zero-human-company|openclaw-master-files' \"$SKILL_DIR/INSTRUCTIONS.md\" 2>/dev/null"

# If the company root already exists, check it is locally materialized (not iCloud-offloaded).
if [ -d "$COMPANY_ROOT" ]; then
  OFFLOADED=0
  command -v find >/dev/null 2>&1 && OFFLOADED=$(find "$COMPANY_ROOT" -name "*.icloud" 2>/dev/null | wc -l | tr -d ' ')
  warn_only "PRD 1.9: zero-human-company tree not iCloud-offloaded (no .icloud stubs)" "[ \"$OFFLOADED\" -eq 0 ]"
fi

echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 02 QC FAILED"; exit 1; } || { green "Skill 02 QC PASS"; exit 0; }
