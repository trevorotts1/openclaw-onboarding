#!/usr/bin/env bash
# qc-tool-gating.test.sh - negative + positive fixture tests for qc-tool-gating.sh.
#
# Proves the U-1 gate:
#   * PASSES a workflows dir whose playbook uses only in-vocabulary tools and
#     never gates off escalate_to_human, and
#   * FAILS a workflows dir whose playbook references an out-of-vocabulary tool
#     or attempts to disable escalate_to_human (the seeded bad fixture).
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-tool-gating.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

verdict_of() {
  bash "$GATE" --dir "$1" --json 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null
}
exit_of() {
  local rc=0
  bash "$GATE" --dir "$1" >/dev/null 2>&1 || rc=$?
  echo "$rc"
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- GOOD fixture: in-vocabulary tools, escalate intact -> PASS. ----------
G="$TMP/good/conversation-workflows"
mkdir -p "$G"
cat > "$G/registry.md" <<'EOF'
# Conversation Workflows Registry

## Active workflows

| ID | Name | OpenClaw playbook |
|---|---|---|
| appointment-booking | Booking | appointment-booking.md |
EOF
cat > "$G/appointment-booking.md" <<'EOF'
# Conversation Workflow: Appointment Booking

## What the agent does

### Phase 1 - Qualify
tools: update_tags, update_contact, reference_documents
Greet and qualify.

### Phase 2 - Close
tools: book_appointment, check_availability, update_tags, reference_documents
Book the appointment.

## On success
Confirm the booking.

## On escalation
Escalate to the operator.
EOF

[ "$(verdict_of "$G")" = "PASS" ] && ok "good fixture: verdict PASS" || bad "good fixture: expected PASS"
[ "$(exit_of "$G")" = "0" ] && ok "good fixture: exit 0" || bad "good fixture: expected exit 0"

# --- BAD fixture: out-of-vocab tool + escalate disabled -> FAIL. ----------
B="$TMP/bad/conversation-workflows"
mkdir -p "$B"
cat > "$B/registry.md" <<'EOF'
# Conversation Workflows Registry

## Active workflows

| ID | Name | OpenClaw playbook |
|---|---|---|
| rogue | Rogue | rogue.md |
EOF
cat > "$B/rogue.md" <<'EOF'
# Conversation Workflow: Rogue

## What the agent does

### Phase 1 - Qualify
tools: update_tags, warp_drive, reference_documents
disable-global: escalate_to_human
Do something the vocabulary does not allow.

## On success
Win.

## On escalation
Escalate.
EOF

[ "$(verdict_of "$B")" = "FAIL" ] && ok "bad fixture: verdict FAIL" || bad "bad fixture: expected FAIL"
[ "$(exit_of "$B")" = "1" ] && ok "bad fixture: exit 1" || bad "bad fixture: expected exit 1"

# The bad fixture must name BOTH the out-of-vocab tool and the escalate violation.
BJSON="$(bash "$GATE" --dir "$B" --json 2>/dev/null)"
printf '%s' "$BJSON" | grep -q "warp_drive" && ok "bad fixture: flags out-of-vocab tool" || bad "bad fixture: did not flag warp_drive"
printf '%s' "$BJSON" | grep -q "escalate_to_human" && ok "bad fixture: flags escalate gated off" || bad "bad fixture: did not flag escalate"

echo ""
echo "qc-tool-gating tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
