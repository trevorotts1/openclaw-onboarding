#!/usr/bin/env bash
# tests/unit/episode-idempotency-guard.test.sh
#
# U034 -- Episode-number server-side idempotency guard tests.
# Proves the guard block in podbean_publish.sh correctly:
#   1. exits 2 when the Podbean API count differs from --roster-episode-count
#   2. proceeds normally (no exit 2) when the counts match
#   3. dies on invalid (non-integer) --roster-episode-count input
#
# This test replicates the guard logic inline -- mocking http_request,
# json_field, log, and die -- so it exercises the exact comparison and exit
# contract without needing real Podbean credentials or network.

set -euo pipefail
cd "$(dirname "$0")/../.."

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# ---- helpers (mock the functions the guard depends on) ----
log()    { echo "[LOG] $*"; }
die()    { echo "FATAL: $*"; exit 1; }

http_request() {
  printf '%s' "${MOCK_BODY:-}"
  return "${MOCK_RC:-0}"
}

json_field() {
  python3 -c "import sys,json; print(json.load(sys.stdin).get(sys.argv[1],''))" "$1" 2>/dev/null
}

# ---- guard logic (identical to production, substituting mocked deps) ----
run_guard() {
  RESP_BODY="$(http_request GET "https://api.podbean.com/v1/episodes")"
  EPISODE_COUNT="$(printf '%s' "$RESP_BODY" | json_field count)"
  [[ "$EPISODE_COUNT" =~ ^[0-9]+$ ]] || EPISODE_COUNT=0
  EPISODE_NUMBER=$(( EPISODE_COUNT + 1 ))

  if [ -n "$ROSTER_EPISODE_COUNT" ]; then
    [[ "$ROSTER_EPISODE_COUNT" =~ ^[0-9]+$ ]] || die "--roster-episode-count must be a non-negative integer, got: ${ROSTER_EPISODE_COUNT}"
    if [ "$EPISODE_COUNT" != "$ROSTER_EPISODE_COUNT" ]; then
      log "EPISODE-NUMBER CONFLICT: Podbean API reports ${EPISODE_COUNT} episode(s), but the local roster expects ${ROSTER_EPISODE_COUNT}. Refusing to publish -- a duplicate episode number would result."
      exit 2
    fi
  fi
  echo "PROCEED"
}

# ---- T1: Count mismatch -> exit 2 ----
echo "--- T1: Count mismatch ---"
MOCK_BODY='{"count":5}'
MOCK_RC=0
out=$(ROSTER_EPISODE_COUNT=3 run_guard 2>&1) && rc=$? || rc=$?
if [ "$rc" -eq 2 ]; then
  pass "T1: mismatch exit code is 2"
else
  fail "T1: expected exit 2, got $rc. Output: $out"
fi
if echo "$out" | grep -q "EPISODE-NUMBER CONFLICT"; then
  pass "T1b: conflict message emitted"
else
  fail "T1b: missing conflict message. Output: $out"
fi

# ---- T2: Count match -> proceeds (no exit 2) ----
echo "--- T2: Count match ---"
MOCK_BODY='{"count":5}'
MOCK_RC=0
out=$(ROSTER_EPISODE_COUNT=5 run_guard 2>&1) || true
if echo "$out" | grep -q "PROCEED"; then
  pass "T2: matching counts proceed"
else
  fail "T2: should have proceeded, got: $out"
fi

# ---- T3: Empty ROSTER_EPISODE_COUNT -> skips guard ----
echo "--- T3: No roster count (skip guard) ---"
MOCK_BODY='{"count":7}'
MOCK_RC=0
out=$(ROSTER_EPISODE_COUNT="" run_guard 2>&1) || true
if echo "$out" | grep -q "PROCEED"; then
  pass "T3: empty roster count skips guard"
else
  fail "T3: should have skipped guard, got: $out"
fi

# ---- T4: Zero episodes -> zero count matches ----
echo "--- T4: Zero episodes match ---"
MOCK_BODY='{"count":0}'
MOCK_RC=0
out=$(ROSTER_EPISODE_COUNT=0 run_guard 2>&1) || true
if echo "$out" | grep -q "PROCEED"; then
  pass "T4: zero count matches roster"
else
  fail "T4: expected PROCEED, got: $out"
fi

# ---- T5: Zero API count vs nonzero roster ----
echo "--- T5: Zero API count vs nonzero roster ---"
MOCK_BODY='{"count":0}'
MOCK_RC=0
out=$(ROSTER_EPISODE_COUNT=2 run_guard 2>&1) && rc=$? || rc=$?
if [ "$rc" -eq 2 ]; then
  pass "T5: zero vs nonzero mismatch exits 2"
else
  fail "T5: expected exit 2, got $rc. Output: $out"
fi

# ---- T6: Non-integer roster count -> die (exit 1) ----
echo "--- T6: Non-integer roster count ---"
MOCK_BODY='{"count":0}'
MOCK_RC=0
out=$(ROSTER_EPISODE_COUNT="not-a-number" run_guard 2>&1) && rc=$? || rc=$?
if [ "$rc" -eq 1 ]; then
  pass "T6: non-integer roster dies with exit 1"
else
  fail "T6: expected exit 1, got $rc. Output: $out"
fi
if echo "$out" | grep -q "non-negative integer"; then
  pass "T6b: validation message emitted"
else
  fail "T6b: missing validation message. Output: $out"
fi

# ---- T7: Missing count field -> defaults to 0 ----
echo "--- T7: Missing count field -> defaults to 0 ---"
MOCK_BODY='{"other":"data"}'
MOCK_RC=0
out=$(ROSTER_EPISODE_COUNT=0 run_guard 2>&1) || true
if echo "$out" | grep -q "PROCEED"; then
  pass "T7: missing count defaults to 0, matches roster 0"
else
  fail "T7: expected PROCEED, got: $out"
fi

# ---- Summary ----
echo ""
echo "========================"
echo "Results: $PASS passed, $FAIL failed"
echo "========================"
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
