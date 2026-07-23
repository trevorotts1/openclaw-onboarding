#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOSEOUT_SCRIPT="$SCRIPT_DIR/run-closeout.sh"
[[ ! -f "$CLOSEOUT_SCRIPT" ]] && echo "FATAL: run-closeout.sh not found" >&2 && exit 2
PASS=0; FAILED=0; RESULTS=()
pass() { PASS=$((PASS+1)); RESULTS+=("PASS: $1"); printf '\033[32mPASS\033[0m %s\n' "$1"; }
fail() { FAILED=$((FAILED+1)); RESULTS+=("FAIL: $1"); printf '\033[31mFAIL\033[0m %s\n' "$1"; }
LINE=$(grep -n 'bash.*RUN_FULL_INSTALL' "$CLOSEOUT_SCRIPT" | head -1 | cut -d: -f1)
POST="$(awk -v start="$LINE" 'NR > start' "$CLOSEOUT_SCRIPT")"
echo "Installer at line $LINE"
printf '\n--- T1: reads state contract ---\n'
echo "$POST" | grep -qE "state_get.*commandCenterStatus" && pass "T1: reads commandCenterStatus from state" || fail "T1: missing state_get for commandCenterStatus"
printf '\n--- T2: done log guarded by state check ---\n'
SL=$(echo "$POST" | grep -n "state_get.*commandCenterStatus" | head -1 | cut -d: -f1)
DL=$(echo "$POST" | grep -n "command-center: done" | head -1 | cut -d: -f1)
[[ -z "$DL" ]] && fail "T2: NO 'done' log found" || { [[ "$DL" -gt "$SL" ]] && pass "T2: done log after state_get -- guarded" || fail "T2: done log NOT guarded (SL=$SL DL=$DL)"; }
printf '\n--- T3: done AND done-degraded both recognized as terminal ---\n'
echo "$POST" | grep -q "done-degraded" && pass "T3a: done-degraded referenced in guard" || fail "T3a: done-degraded missing"
echo "$POST" | grep -qE '!=.*"done".*!=.*"done-degraded"|!=.*"done-degraded".*!=.*"done"' && pass "T3b: guard uses double-negation allowing both done and done-degraded" || fail "T3b: guard pattern missing"
printf '\n--- T4: non-terminal statuses produce WARN + clean exit 0 ---\n'
w=0; e=0
grep -q "WARN.*command-center" <<< "$POST" && w=1
grep -qE "exit 0" <<< "$POST" && e=1
[[ "$w" -eq 1 && "$e" -eq 1 ]] && pass "T4: WARN log AND exit 0 both in non-terminal path" || fail "T4: missing WARN (w=$w) or exit 0 (e=$e)"
printf '\n--- T5 (mutation-sensitive): done log NOT unconditional after exit 0 ---\n'
GL=$(echo "$POST" | grep -n '!=.*"done"' | head -1 | cut -d: -f1)
[[ -z "$GL" ]] && fail "T5: no guard -- removing it would make done log unconditional" || { [[ "$DL" -gt "$GL" ]] && pass "T5: done log is after guard line -- not unconditional" || fail "T5: done log position ambiguous (GL=$GL DL=$DL)"; }
printf '\n--- T6 (edge case): exit 0 for resume cron retry ---\n'
echo "$POST" | grep -qE "exit 0" && pass "T6: exit 0 present for resume cron retry" || fail "T6: no exit 0 in post-installer code"
printf '\nU072: %d pass, %d fail\n' "$PASS" "$FAILED"
for r in "${RESULTS[@]}"; do printf '  %s\n' "$r"; done
[[ "$FAILED" -eq 0 ]] && printf '\033[32mALL PASS\033[0m\n' && exit 0
printf '\033[31m%d FAILED\033[0m\n' "$FAILED"
exit 1
