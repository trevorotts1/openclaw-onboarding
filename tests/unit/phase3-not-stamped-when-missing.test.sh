#!/usr/bin/env bash
# phase3-not-stamped-when-missing.test.sh — acceptance test for BU-103, Change 3.
#
# run-full-install.sh Phase 3 stamped commandCenterPhase3Done = true even when
# the departments folder it was supposed to materialize did not exist, so a run
# that had nothing to copy reported the phase done forever. This runs the REAL
# PHASE3 block (the text between `# >>> PHASE3-BEGIN` and `# <<< PHASE3-END`)
# with stub log / state_get / state_set:
#   case 1: the resolved folder is missing -> state_set is NEVER called with it;
#   case 2 (control): the folder exists -> it IS stamped.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh"
PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*" >&2; FAIL=$((FAIL+1)); }

BLOCK="$(sed -n '/^# >>> PHASE3-BEGIN$/,/^# <<< PHASE3-END$/p' "$SRC")"
[ -n "$BLOCK" ] || { echo "FAIL: PHASE3 block not found in run-full-install.sh"; exit 1; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/phase3.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
SET_LOG="$TMP/state-set.log"

run_block() {  # $1 = OC_ROOT for this run
  : > "$SET_LOG"
  OC_ROOT="$1" \
  SKILL_DIR="$TMP/no-such-skill" \
  LOG_FILE="$TMP/install.log" \
  STATE_FILE="$TMP/state.json" \
  BLOCK_B_UPDATE_ONLY=false \
  PHASE3_SET_LOG="$SET_LOG" \
  bash -c '
    log() { :; }
    state_get() { :; }
    state_set() { printf "%s\n" "$1" >> "$PHASE3_SET_LOG"; }
    '"$BLOCK"'
  '
}

echo "=== case 1: departments folder missing — flag must stay unset ==="
mkdir -p "$TMP/box-empty"
run_block "$TMP/box-empty"
GOT="$(cat "$SET_LOG")"
case "$GOT" in
  *commandCenterPhase3Done*) bad "stamped commandCenterPhase3Done with no departments folder: $GOT" ;;
  *)                         ok "commandCenterPhase3Done not written when the folder is missing" ;;
esac

echo "=== case 2 (control): departments folder exists — flag must be written ==="
mkdir -p "$TMP/box-full/workspace/departments/marketing"
run_block "$TMP/box-full"
GOT="$(cat "$SET_LOG")"
case "$GOT" in
  *commandCenterPhase3Done*) ok "commandCenterPhase3Done written when the folder exists" ;;
  *)                         bad "flag not written although the folder existed: $GOT" ;;
esac

echo
echo "passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ]
