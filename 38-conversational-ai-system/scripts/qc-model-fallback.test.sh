#!/usr/bin/env bash
# qc-model-fallback.test.sh - negative + positive fixture tests for
# qc-model-fallback.sh (U-8 wiring + U-10 model-tier enum).
#
# Proves the gate:
#   * PASSES a playbook whose model-tier is one of the three enum values,
#   * treats a playbook with NO model-tier as inert (default; no failure),
#   * FAILS a playbook whose model-tier is out of enum, flagging the bad value.
#
# The static-wiring layer runs against the real skill tree either way; these
# fixtures exercise the U-10 model-tier enum branch.
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-model-fallback.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

verdict_of() {
  bash "$GATE" --dir "$1" --json 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null
}
exit_of() {
  local rc=0
  bash "$GATE" --dir "$1" >/dev/null 2>&1 || rc=$?
  echo "$rc"
}
json_of() {
  bash "$GATE" --dir "$1" --json 2>/dev/null
}

# --- GOOD fixture: valid model-tier + an inert (no-tier) playbook -> PASS. -----
G="$TMP/good/conversation-workflows"
mkdir -p "$G"
cat > "$G/reasoning.md" <<'EOF'
# Conversation Workflow: High-stakes qualification

model-tier: reasoning-max

## What the agent does

### Phase 1 - Qualify
tools: reference_documents
Qualify hard.

## On success
Booked.
EOF
cat > "$G/inert.md" <<'EOF'
# Conversation Workflow: Inert

### Phase 1 - Chat
tools: reference_documents
Chat.

## On success
Done.
EOF

[ "$(verdict_of "$G")" = "PASS" ] && ok "good fixture: verdict PASS" || bad "good fixture: expected PASS"
[ "$(exit_of "$G")" = "0" ] && ok "good fixture: exit 0" || bad "good fixture: expected exit 0"

# --- BAD fixture: out-of-enum model-tier -> FAIL. -----------------------------
B="$TMP/bad/conversation-workflows"
mkdir -p "$B"
cat > "$B/bogus-tier.md" <<'EOF'
# Conversation Workflow: Bogus Tier

model-tier: super-genius-9000

## What the agent does

### Phase 1 - Qualify
tools: reference_documents
Qualify.

## On success
Win.
EOF

[ "$(verdict_of "$B")" = "FAIL" ] && ok "bad fixture: verdict FAIL" || bad "bad fixture: expected FAIL"
[ "$(exit_of "$B")" = "1" ] && ok "bad fixture: exit 1" || bad "bad fixture: expected exit 1"

BJSON="$(json_of "$B")"
printf '%s' "$BJSON" | grep -q "super-genius-9000" && ok "bad fixture: flags the out-of-enum tier value" || bad "bad fixture: did not flag the bogus tier"

echo ""
echo "qc-model-fallback tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
