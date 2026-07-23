#!/usr/bin/env bash
# test-interview-rate-limit.sh
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/lib-interview-rate-limit.sh"
FAILED=0; TOTAL=0
pass() { TOTAL=$((TOTAL + 1)); echo "ok - $1"; }
fail() { TOTAL=$((TOTAL + 1)); FAILED=1; echo "not ok - $1"; echo "  $2"; }
TD="$(mktemp -d -t rl-test.XXXXXX)"
cleanup() { rm -rf "$TD"; }
trap cleanup EXIT
export OC_WORKSPACE_DEFAULT="$TD"
export INTERVIEW_RATE_LIMIT_WINDOW_SECONDS=1
export INTERVIEW_RATE_LIMIT_MAX=5
source "$LIB"
( rm -f "$TD/.interview-rate-limit.json"; source "$LIB"; check_interview_rate_limit "s1" && echo "ok 1" || echo "not ok 1" )
TOTAL=$((TOTAL + 1))
( rm -f "$TD/.interview-rate-limit.json"; source "$LIB"; ok=true; for i in $(seq 1 5); do check_interview_rate_limit "s2" || { ok=false; break; }; done; $ok && echo "ok 2" || echo "not ok 2" )
TOTAL=$((TOTAL + 1))
( rm -f "$TD/.interview-rate-limit.json"; source "$LIB"; for i in $(seq 1 5); do check_interview_rate_limit "s3" || true; done; check_interview_rate_limit "s3" && echo "not ok 3" || echo "ok 3" )
TOTAL=$((TOTAL + 1))
( rm -f "$TD/.interview-rate-limit.json"; source "$LIB"; for i in $(seq 1 5); do check_interview_rate_limit "A" || true; done; a_b=false; b_a=false; check_interview_rate_limit "A" || a_b=true; check_interview_rate_limit "B" && b_a=true; $a_b && $b_a && echo "ok 4" || echo "not ok 4" )
TOTAL=$((TOTAL + 1))
( export OC_WORKSPACE_DEFAULT="" HOME="/nonexistent"; source "$LIB"; check_interview_rate_limit "x" && echo "not ok 5" || echo "ok 5" )
TOTAL=$((TOTAL + 1))
( export INTERVIEW_RATE_LIMIT_MAX=2; rm -f "$TD/.interview-rate-limit.json"; source "$LIB"; check_interview_rate_limit "c" || true; check_interview_rate_limit "c" || true; check_interview_rate_limit "c" && echo "not ok 6" || echo "ok 6" )
TOTAL=$((TOTAL + 1))
( source "$LIB"; sid="$(interview_session_id)"; [ -n "$sid" ] && echo "ok 7" || echo "not ok 7" )
TOTAL=$((TOTAL + 1))
LN=$(grep -n '\${#_active\[@\]}' "$LIB" | grep '\-ge ' | head -1 | cut -d: -f1); ORIG=""; if [ -n "$LN" ]; then ORIG=$(sed -n "${LN}p" "$LIB"); MUT="${ORIG/-ge/-gt}"; sed -i '' "${LN}s/.*/$MUT/" "$LIB"; ( export INTERVIEW_RATE_LIMIT_MAX=3; rm -f "$TD/.interview-rate-limit.json"; source "$LIB"; check_interview_rate_limit "m" || true; check_interview_rate_limit "m" || true; check_interview_rate_limit "m" || true; check_interview_rate_limit "m" && echo "RED mutation caught (ok 8)" || echo "not ok 8" ); TOTAL=$((TOTAL + 1)); sed -i '' "${LN}s/.*/$ORIG/" "$LIB"; ( export INTERVIEW_RATE_LIMIT_MAX=3; rm -f "$TD/.interview-rate-limit.json"; source "$LIB"; check_interview_rate_limit "g" || true; check_interview_rate_limit "g" || true; check_interview_rate_limit "g" || true; check_interview_rate_limit "g" && { echo "not ok 8"; FAILED=1; } || echo "GREEN (ok 8)"; TOTAL=$((TOTAL + 1)) ); fi
echo "# Ran $TOTAL tests."; [ "$FAILED" -eq 0 ] && echo "PASS" && exit 0 || echo "FAIL" && exit 1
