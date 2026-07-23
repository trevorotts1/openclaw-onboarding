#!/usr/bin/env bash
set -uo pipefail
TD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CS="$TD/run-closeout.sh"
[[ ! -f "$CS" ]] && exit 2
P=0; F=0; R=()
pass() { P=$((P+1)); R+=("PASS: $1"); printf '\033[32mPASS\033[0m %s\n' "$1"; }
fail() { F=$((F+1)); R+=("FAIL: $1"); printf '\033[31mFAIL\033[0m %s\n' "$1"; }
L=$(grep -n 'bash.*RUN_FULL_INSTALL' "$CS" | head -1 | cut -d: -f1)
T="$(awk -v s="$L" 'NR > s' "$CS")"
echo "Line $L"
echo ""; echo "--- T1 ---"
echo "$T" | grep -qE "state_get.*commandCenterStatus" && pass "T1 reads commandCenterStatus" || fail "T1 missing state_get"
echo ""; echo "--- T2 ---"
SL=$(echo "$T" | grep -n "state_get.*commandCenterStatus" | head -1 | cut -d: -f1)
DL=$(echo "$T" | grep -n "command-center: done" | head -1 | cut -d: -f1)
[[ -z "$DL" ]] && fail "T2 no done log" || { [[ -n "$SL" && "$DL" -gt "$SL" ]] && pass "T2 guarded" || fail "T2 not guarded"; }
echo ""; echo "--- T3 ---"
echo "$T" | grep -q "done-degraded" && pass "T3a done-degraded" || fail "T3a missing done-degraded"
echo "$T" | grep -qE '!=.*"done".*!=.*"done-degraded"' && pass "T3b guard both" || fail "T3b guard incomplete"
echo ""; echo "--- T4 ---"
W=1; echo "$T" | grep -q "WARN.*command-center" || W=0; echo "$T" | grep -qE "exit 0" || W=0
[[ "$W" -eq 1 ]] && pass "T4 WARN+exit0" || fail "T4 missing"
echo ""; echo "--- T5 mut ---"
G=$(echo "$T" | grep -n '!=.*"done"' | head -1 | cut -d: -f1)
[[ -z "$G" ]] && fail "T5 no guard" || { [[ -n "$DL" && "$DL" -gt "$G" ]] && pass "T5 done after guard" || fail "T5 ambiguous"; }
echo ""; echo "--- T6 edge ---"
echo "$T" | grep -qE "exit 0" && pass "T6 exit 0" || fail "T6 no exit"
echo ""; echo "U072: $P/$((P+F))"; for r in "${R[@]}"; do echo "  $r"; done
[[ "$F" -eq 0 ]] && { printf '\033[32mALL PASS\033[0m\n'; exit 0; } || { printf '\033[31m%d FAILED\033[0m\n' "$F"; exit 1; }
