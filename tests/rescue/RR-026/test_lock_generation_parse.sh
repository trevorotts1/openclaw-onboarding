#!/usr/bin/env bash
# tests/rescue/RR-026/test_lock_generation_parse.sh
#
# A poll that died holding the lock must not deadlock the return leg.
#
# THE DEFECT. rescue-poll.sh extracted the incumbent's lock generation with
# sed, which kept the JSON quotes of a STRING generation ('"83799"'). The
# supervisor compared that to '83799', refused the takeover as
# takeover_generation_mismatch, and the poll exited 0 silently -- every fire,
# forever. The lock record the supervisor writes always stores the generation
# as a string, so this was the normal case, not an edge case.
#
# Runs the REAL rescue-poll.sh against a loopback receiver stub (RR-025
# harness). A poll that got past the lock POSTs a claim; the stub logs it, so
# "claims >= 1" is the observable proof the takeover happened.
#   1. dead incumbent, STRING generation -> taken over, claim posted
#   2. dead incumbent, INT generation    -> taken over, claim posted
#   3. LIVE incumbent -> not taken, no claim, and the contention is logged
#      (lock-contended reason=... holder_gen=...) with a rejected/ marker,
#      instead of a silent exit.
set -u

if [ -n "${BASH_SOURCE:-}" ]; then _HERE_SRC="${BASH_SOURCE[0]}"; else _HERE_SRC="$0"; fi
HERE="$(cd "$(dirname "$_HERE_SRC")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
POLL="$REPO/65-rescue-receiver/rescue-poll.sh"
HELPER="$REPO/shared-utils/rescue-env.sh"
SUPERVISE="$REPO/shared-utils/rescue-supervise.py"
export POLL HELPER SUPERVISE
. "$REPO/tests/rescue/RR-025/lib-envelope-harness.sh"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rrlockgen.XXXXXX")"
DONE_FLAG=""
trap '[ -n "$DONE_FLAG" ] && rm -rf "$WORK"' EXIT
BASE_PORT=$(( 24000 + ($$ % 2000) ))
IDX=0

# run_case <name> <generation-shape: string|int> <incumbent: dead|live>
run_case() {
    IDX=$((IDX+1))
    CASE_ROOT="$WORK/$1"; PORT=$((BASE_PORT + IDX))
    mkdir -p "$CASE_ROOT"
    harness_make_box "$CASE_ROOT"
    harness_write_store "$CASE_ROOT" "$PORT"
    LOCK_DIR="$CASE_ROOT/.openclaw/state/rr-receiver/lock"
    sleep 300 </dev/null >/dev/null 2>&1 & STANDIN=$!
    python3 "$SUPERVISE" lock acquire --dir "$LOCK_DIR" --owner-token tok-old --owner-pid "$STANDIN" \
        --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
        --generation 4242 --operation-id box-synthetic --lease-seconds 900 >/dev/null 2>&1
    if [ "$2" = "int" ]; then
        python3 -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); d["generation"]=int(d["generation"]); json.dump(d,open(p,"w"))' \
            "$LOCK_DIR/lock.json"
    fi
    if [ "$3" = "dead" ]; then
        kill -9 "$STANDIN" 2>/dev/null; wait "$STANDIN" 2>/dev/null
    fi
    CLAIMS_LOG="$CASE_ROOT/claims.txt"
    # to a file, never $(...): the substitution would wait on the stub's stdout
    harness_start_receiver "$PORT" '{"status":"empty"}' "$CLAIMS_LOG" > "$CASE_ROOT/recv.pid"
    RECV="$(cat "$CASE_ROOT/recv.pid")"
    sleep 0.6
    OPENCLAW_RECORD="$CASE_ROOT/agent-record.txt" HOME="$CASE_ROOT" PATH="$CASE_ROOT/bin:$PATH" \
        RR_POLL_NO_JITTER=1 sh "$CASE_ROOT/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" \
        >"$CASE_ROOT/out" 2>"$CASE_ROOT/err"
    kill "$RECV" 2>/dev/null; wait "$RECV" 2>/dev/null
    [ "$3" = "live" ] && { kill -9 "$STANDIN" 2>/dev/null; wait "$STANDIN" 2>/dev/null; }
    CLAIMS=0
    [ -f "$CLAIMS_LOG" ] && CLAIMS=$(grep -c 'claim' "$CLAIMS_LOG" 2>/dev/null)
    case "$CLAIMS" in ''|*[!0-9]*) CLAIMS=0 ;; esac
    POLL_LOG="$CASE_ROOT/.openclaw/state/rr-receiver/rescue-poll.log"
}

echo "== RR-026: lock generation parse (string + int) and loud contention =="

run_case string-gen string dead
if [ "$CLAIMS" -ge 1 ] && grep -q 'lock-takeover prior_generation=4242' "$POLL_LOG" 2>/dev/null; then
    ok "dead incumbent with a STRING generation is taken over (claim posted, prior_generation=4242)"
else
    bad "dead incumbent with a STRING generation deadlocked the poll (claims=$CLAIMS)" "$(tail -3 "$POLL_LOG" 2>/dev/null)"
fi

run_case int-gen int dead
if [ "$CLAIMS" -ge 1 ]; then
    ok "dead incumbent with an INT generation is taken over (claim posted)"
else
    bad "dead incumbent with an INT generation deadlocked the poll (claims=$CLAIMS)"
fi

run_case live-owner string live
if [ "$CLAIMS" -eq 0 ]; then
    ok "a LIVE incumbent is never taken over (no claim posted)"
else
    bad "a live incumbent's lock was taken (claims=$CLAIMS)"
fi
if grep -q 'lock-contended reason=owner_running holder_gen=4242' "$POLL_LOG" 2>/dev/null \
   && [ -f "$CASE_ROOT/.openclaw/state/rr-receiver/rejected/lock-contended.json" ]; then
    ok "contention is logged (reason + holder_gen) and marked in rejected/, not a silent exit"
else
    bad "contention left no log line / marker" "$(tail -3 "$POLL_LOG" 2>/dev/null)"
fi

DONE_FLAG=1
echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
