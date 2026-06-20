#!/usr/bin/env bash
# test-verify-telegram-delivery.sh -- smoke test for the closeout delivery-
# confirmation gate (verify-telegram-delivery.sh).
#
# Proves the anti-faking contract:
#   CASE A: every required messageId IS present in the sent-registry -> PASS (rc 0)
#   CASE B: a required messageId is MISSING and recent             -> FAIL (rc 3)
#   CASE C: a required slot has NO captured messageId (send-failed)-> FAIL (rc 4)
#   CASE D: a required messageId is MISSING but AGED OUT past TTL  -> PASS (rc 0)
#   CASE E: phantom guard -- messagesDelivered with only send-failed
#           records (no real messageId) is NOT counted delivered    -> count 0
#   CASE F: registry FILE ABSENT (OpenClaw 2026.6.x migrated it away) +
#           all required ids gateway-confirmed in state             -> PASS (rc 0)
#   CASE G: registry ABSENT + a required slot genuinely undelivered -> FAIL (rc 4)
#   CASE H: registry ABSENT + a required slot has no record at all  -> FAIL (rc 4)
#   CASE I: registry ABSENT + ZHC_TG_REGISTRY_REQUIRED=1 (legacy)   -> ENV  (rc 7)
#
# No live OpenClaw install needed: drives the verifier via ZHC_STATE_FILE /
# ZHC_LOG_FILE / ZHC_TG_REGISTRY fixtures in a temp dir.
#
# EXIT CODES: 0 = all cases pass, 1 = verifier script missing, 3 = a case failed.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFY="$SCRIPT_DIR/verify-telegram-delivery.sh"

if [[ ! -f "$VERIFY" ]]; then
  echo "FAIL: verify-telegram-delivery.sh not found at $VERIFY" >&2
  exit 1
fi
command -v jq >/dev/null 2>&1 || { echo "FAIL: jq not installed" >&2; exit 1; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

CHAT="9999999999"
PASS=0
FAILED=0

now_s=$(date -u +%s)
recent_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# An ISO timestamp ~2 days in the past (older than the 1-day default TTL).
if date -u -d "@$((now_s - 172800))" +%Y-%m-%dT%H:%M:%SZ >/dev/null 2>&1; then
  old_iso=$(date -u -d "@$((now_s - 172800))" +%Y-%m-%dT%H:%M:%SZ)        # GNU
else
  old_iso=$(date -u -r "$((now_s - 172800))" +%Y-%m-%dT%H:%M:%SZ)         # BSD
fi
now_ms=$(( now_s * 1000 ))

# write_state <json-of-messagesDelivered-array>
write_state() {
  cat > "$TMP/state.json" <<EOF
{ "ownerChat": "$CHAT", "messagesDelivered": $1 }
EOF
}

# write_registry <json-object-of-messageId->ts>
write_registry() {
  cat > "$TMP/registry.json" <<EOF
{ "$CHAT": $1 }
EOF
}

run_case() {
  local name="$1" expect_rc="$2"
  local rc
  ZHC_STATE_FILE="$TMP/state.json" \
  ZHC_LOG_FILE="$TMP/verify.log" \
  ZHC_TG_REGISTRY="$TMP/registry.json" \
  ZHC_TG_REQUIRED_SLOTS="1,6,7" \
    bash "$VERIFY" >/dev/null 2>&1
  rc=$?
  if [[ "$rc" == "$expect_rc" ]]; then
    echo "  ✓ $name (rc=$rc as expected)"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $name -- expected rc=$expect_rc, got rc=$rc" >&2
    FAILED=$((FAILED + 1))
  fi
}

echo "[SMOKE TEST] verify-telegram-delivery.sh delivery-confirmation gate"

# CASE A: all required ids present -> PASS (rc 0)
write_state "[
  {\"n\":1,\"messageId\":\"1001\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"},
  {\"n\":6,\"messageId\":\"1006\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"},
  {\"n\":7,\"messageId\":\"1007\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"}
]"
write_registry "{ \"1001\": $now_ms, \"1006\": $now_ms, \"1007\": $now_ms }"
run_case "CASE A: all required messageIds present in registry -> PASS" 0

# CASE B: required id 6 missing + recent -> FAIL (rc 3)
write_state "[
  {\"n\":1,\"messageId\":\"2001\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"},
  {\"n\":6,\"messageId\":\"2006\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"},
  {\"n\":7,\"messageId\":\"2007\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"}
]"
write_registry "{ \"2001\": $now_ms, \"2007\": $now_ms }"
run_case "CASE B: required messageId missing + recent -> FAIL(3)" 3

# CASE C: required slot 7 has no messageId (send-failed) -> FAIL (rc 4)
write_state "[
  {\"n\":1,\"messageId\":\"3001\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"},
  {\"n\":6,\"messageId\":\"3006\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"},
  {\"n\":7,\"status\":\"send-failed\",\"reason\":\"no-messageId\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"}
]"
write_registry "{ \"3001\": $now_ms, \"3006\": $now_ms }"
run_case "CASE C: required slot has no captured messageId -> FAIL(4)" 4

# CASE D: required id 6 missing but AGED OUT past TTL -> PASS (rc 0)
write_state "[
  {\"n\":1,\"messageId\":\"4001\",\"chatId\":\"$CHAT\",\"ts\":\"$old_iso\"},
  {\"n\":6,\"messageId\":\"4006\",\"chatId\":\"$CHAT\",\"ts\":\"$old_iso\"},
  {\"n\":7,\"messageId\":\"4007\",\"chatId\":\"$CHAT\",\"ts\":\"$old_iso\"}
]"
# 4006 deliberately absent; it was sent 2 days ago > 1-day TTL -> aged-out, not a fail.
write_registry "{ \"4001\": $now_ms, \"4007\": $now_ms }"
run_case "CASE D: required messageId missing but aged-out past TTL -> PASS" 0

# CASE E: phantom-guard logic -- a delivered-array of ONLY send-failed records
# must not count as a real delivery. We assert the same jq the run-closeout guard
# uses returns 0 confirmed deliveries.
write_state "[
  {\"n\":1,\"status\":\"send-failed\",\"reason\":\"no-messageId\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"}
]"
real_count=$(jq -r '(.messagesDelivered // []) | map(select((.messageId // "") | tostring | length > 0)) | length' "$TMP/state.json")
if [[ "$real_count" == "0" ]]; then
  echo "  ✓ CASE E: phantom guard counts 0 real deliveries from send-failed-only records"
  PASS=$((PASS + 1))
else
  echo "  ✗ CASE E: expected 0 real deliveries, got $real_count" >&2
  FAILED=$((FAILED + 1))
fi

# ─────────────────────────────────────────────────────────────────────────────
# OpenClaw 2026.6.x DERIVED MODE: the gateway no longer writes the JSON sent-
# registry (it migrated into SQLite), so the registry FILE is absent. The gate
# must then confirm delivery from the gateway-confirmed messageIds already in
# state -- WITHOUT the env-var/manual workaround that was needed for a recent
# closeout, and while STILL failing on genuinely-undelivered slots.
# ─────────────────────────────────────────────────────────────────────────────

# run_case_noreg <name> <expect_rc> -- like run_case but points ZHC_TG_REGISTRY
# at a path that does NOT exist (simulates the migrated-away 2026.6.x registry).
run_case_noreg() {
  local name="$1" expect_rc="$2" rc
  rm -f "$TMP/registry.json"
  ZHC_STATE_FILE="$TMP/state.json" \
  ZHC_LOG_FILE="$TMP/verify.log" \
  ZHC_TG_REGISTRY="$TMP/does-not-exist-registry.json" \
  ZHC_TG_REQUIRED_SLOTS="1,6,7" \
    bash "$VERIFY" >/dev/null 2>&1
  rc=$?
  if [[ "$rc" == "$expect_rc" ]]; then
    echo "  ✓ $name (rc=$rc as expected)"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $name -- expected rc=$expect_rc, got rc=$rc" >&2
    FAILED=$((FAILED + 1))
  fi
}

# CASE F: registry FILE absent + all required slots have gateway-confirmed
# messageIds in state -> PASS (rc 0) WITHOUT any skip/workaround env var.
write_state "[
  {\"n\":1,\"messageId\":\"6001\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"},
  {\"n\":6,\"messageId\":\"6006\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"},
  {\"n\":7,\"messageId\":\"6007\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"}
]"
run_case_noreg "CASE F: registry absent (2026.6.x) + all ids confirmed in state -> PASS" 0

# CASE G: registry FILE absent + a required slot has NO messageId (genuine
# send failure) -> still FAIL (rc 4). Fail-loud preserved in derived mode.
write_state "[
  {\"n\":1,\"messageId\":\"7001\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"},
  {\"n\":6,\"messageId\":\"7006\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"},
  {\"n\":7,\"status\":\"send-failed\",\"reason\":\"no-messageId\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"}
]"
run_case_noreg "CASE G: registry absent + required slot never delivered -> FAIL(4)" 4

# CASE H: registry FILE absent + a required slot has no record AT ALL -> FAIL(4).
write_state "[
  {\"n\":1,\"messageId\":\"8001\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"},
  {\"n\":6,\"messageId\":\"8006\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"}
]"
run_case_noreg "CASE H: registry absent + required slot 7 has no record -> FAIL(4)" 4

# CASE I: legacy hard-require -- registry absent but ZHC_TG_REGISTRY_REQUIRED=1
# forces the old env-error (rc 7) so operators can opt back into strict behavior.
write_state "[
  {\"n\":1,\"messageId\":\"9001\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"},
  {\"n\":6,\"messageId\":\"9006\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"},
  {\"n\":7,\"messageId\":\"9007\",\"chatId\":\"$CHAT\",\"ts\":\"$recent_iso\"}
]"
rm -f "$TMP/registry.json"
ZHC_STATE_FILE="$TMP/state.json" \
ZHC_LOG_FILE="$TMP/verify.log" \
ZHC_TG_REGISTRY="$TMP/does-not-exist-registry.json" \
ZHC_TG_REQUIRED_SLOTS="1,6,7" \
ZHC_TG_REGISTRY_REQUIRED=1 \
  bash "$VERIFY" >/dev/null 2>&1
ical_rc=$?
if [[ "$ical_rc" == "7" ]]; then
  echo "  ✓ CASE I: registry absent + ZHC_TG_REGISTRY_REQUIRED=1 -> env-error(7) (rc=7 as expected)"
  PASS=$((PASS + 1))
else
  echo "  ✗ CASE I: expected rc=7, got rc=$ical_rc" >&2
  FAILED=$((FAILED + 1))
fi

echo "--------------------------------------------"
if [[ "$FAILED" -eq 0 ]]; then
  echo "[SMOKE TEST] RESULT: ✅ all $PASS cases passed"
  exit 0
fi
echo "[SMOKE TEST] RESULT: ❌ $FAILED case(s) failed ($PASS passed)" >&2
exit 3
