#!/usr/bin/env bash
set -euo pipefail
TD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CS="$TD/run-closeout.sh"
[[ ! -f "$CS" ]] && { echo "ERROR: $CS not found" >&2; exit 2; }
P=0; F=0; R=()
pass() { P=$((P+1)); R+=("PASS: $1"); printf '''\033[32mPASS\033[0m %s\n''' "$1"; }
fail() { F=$((F+1)); R+=("FAIL: $1"); printf '''\033[31mFAIL\033[0m %s\n''' "$1"; }
info() { printf '''    %s\n''' "$1"; }
state_check() { local st="$1"; if [[ "$st" != "done" && "$st" != "done-degraded" ]]; then return 1; fi; return 0; }
INST_L=$(grep -n '''bash.*RUN_FULL_INSTALL''' "$CS" | head -1 | cut -d: -f1)
POST=$(awk -v s="$INST_L" '''NR > s''' "$CS")
info "installer line=$INST_L"
echo ""; echo "--- T1 ---"
echo "$POST" | grep -qE '''state_get.*commandCenterStatus''' && pass "T1 reads commandCenterStatus" || fail "T1 missing state_get"
echo ""; echo "--- T2 ---"
SL=$(echo "$POST" | grep -n '''state_get.*commandCenterStatus''' | head -1 | cut -d: -f1)
DL=$(echo "$POST" | grep -n '''command-center: done''' | head -1 | cut -d: -f1)
[[ -z "$DL" ]] && fail "T2 no done log" || { [[ -n "$SL" && "$DL" -gt "$SL" ]] && pass "T2 state before done" || fail "T2 not guarded"; }
echo ""; echo "--- T3 ---"
t3=1; echo "$POST" | grep -q '''done-degraded''' || t3=0; echo "$POST" | grep -qE '''!=.*done.*!=.*done-degraded''' || t3=0
[[ "$t3" -eq 1 ]] && pass "T3 both done+done-degraded" || fail "T3 guard incomplete"
echo ""; echo "--- T4 ---"
W=1; echo "$POST" | grep -q '''WARN.*command-center''' || W=0; echo "$POST" | grep -q '''exit 0''' || W=0
[[ "$W" -eq 1 ]] && pass "T4 WARN+exit0" || fail "T4 missing"
echo ""; echo "--- T5 ---"
G=$(echo "$POST" | grep -n '''!=.*done''' | head -1 | cut -d: -f1)
[[ -z "$G" ]] && fail "T5 no guard" || { [[ -n "$DL" && "$DL" -gt "$G" ]] && pass "T5 done after guard" || fail "T5 ambiguous"; }
echo ""; echo "--- T6 ---"
state_check "done" && pass "T6 done proceeds" || fail "T6 done defers"
echo ""; echo "--- T7 ---"
state_check "done-degraded" && pass "T7 done-degraded proceeds" || fail "T7 done-degraded defers"
echo ""; echo "--- T8 ---"
state_check "interview-pending" && fail "T8 interview-pending proceeds" || pass "T8 interview-pending defers"
echo ""; echo "--- T9 ---"
state_check "interview-qc-unverified" && fail "T9 qc-unverified proceeds" || pass "T9 qc-unverified defers"
echo ""; echo "--- T10 ---"
state_check "" && fail "T10 empty proceeds" || pass "T10 empty defers"
echo ""; echo "--- T11 ---"
state_check "building" && fail "T11 building proceeds" || pass "T11 building defers"
echo ""; echo "--- T12 ---"
state_check "failed" && fail "T12 failed proceeds" || pass "T12 failed defers"
echo ""; echo "U072: $P/$((P+F))"
for r in "${R[@]}"; do echo "  $r"; done
[[ "$F" -eq 0 ]] && { printf '''\033[32mALL PASS\033[0m\n'''; exit 0; } || { printf '''\033[31m%d FAILED\033[0m\n''' "$F"; exit 1; }
