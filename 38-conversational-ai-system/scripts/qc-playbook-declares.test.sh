#!/usr/bin/env bash
# qc-playbook-declares.test.sh - negative + positive fixture tests for
# qc-playbook-declares.sh (U-9 declares cross-validation + U-12 calendar ids).
#
# Proves the gate:
#   * PASSES a playbook whose declares block fully resolves (tools in phase lines,
#     exits in Exit rules, ZHC_ fields in crm-field-mappings, calendar ids in the
#     caf export),
#   * FAILS a playbook whose declares dangles (tool not in any phase, exit not in
#     Exit rules, ZHC_ field not in mappings, calendar id absent from the export),
#   * WARNS (does not FAIL) a legacy playbook that carries no declares block.
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-playbook-declares.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Shared cross-file inputs.
CAL_EXPORT="$TMP/cal.json"
cat > "$CAL_EXPORT" <<'EOF'
{"calendars": [{"id": "CAL_REAL", "name": "Consultation"}]}
EOF
CRM="$TMP/crm-field-mappings.md"
cat > "$CRM" <<'EOF'
# CRM field mappings

| value captured | GHL field name | field id |
|---|---|---|
| Budget | ZHC_budget_range | abc123 |
EOF

verdict_of() {
  bash "$GATE" --dir "$1" --calendars-export "$CAL_EXPORT" --crm-fields "$CRM" --json 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null
}
exit_of() {
  local rc=0
  bash "$GATE" --dir "$1" --calendars-export "$CAL_EXPORT" --crm-fields "$CRM" >/dev/null 2>&1 || rc=$?
  echo "$rc"
}
json_of() {
  bash "$GATE" --dir "$1" --calendars-export "$CAL_EXPORT" --crm-fields "$CRM" --json 2>/dev/null
}

# --- GOOD fixture: every declared reference resolves -> PASS. -----------------
G="$TMP/good/conversation-workflows"
mkdir -p "$G"
cat > "$G/qualify.md" <<'EOF'
# Conversation Workflow: Qualify

model-tier: realtime-standard

declares
tools-used: book_appointment, update_tags
exits-used: talk-to-human
fields-used: contact.email, ZHC_budget_range
calendars: default: CAL_REAL, on-site estimate: if ZHC-service-area-confirmed then CAL_REAL else CAL_REAL

## What the agent does

### Phase 1 - Qualify
tools: update_tags, reference_documents
Qualify the lead.

### Phase 4 - Close
tools: book_appointment, update_tags, reference_documents
Close.

## Exit rules

exit-when-tag: talk-to-human, action: handoff

## On success
Booked.

## On escalation
Escalate.
EOF

[ "$(verdict_of "$G")" = "PASS" ] && ok "good fixture: verdict PASS" || bad "good fixture: expected PASS"
[ "$(exit_of "$G")" = "0" ] && ok "good fixture: exit 0" || bad "good fixture: expected exit 0"

# --- BAD fixture: four dangling declares references -> FAIL. ------------------
B="$TMP/bad/conversation-workflows"
mkdir -p "$B"
cat > "$B/rogue.md" <<'EOF'
# Conversation Workflow: Rogue

declares
tools-used: book_appointment, send_invoice
exits-used: ghost-tag
fields-used: ZHC_missing_field
calendars: default: CAL_REAL, estimate: CAL_MISSING

## What the agent does

### Phase 1 - Qualify
tools: update_tags, reference_documents
Qualify.

## Exit rules

exit-when-tag: talk-to-human, action: handoff

## On success
Win.

## On escalation
Escalate.
EOF

[ "$(verdict_of "$B")" = "FAIL" ] && ok "bad fixture: verdict FAIL" || bad "bad fixture: expected FAIL"
[ "$(exit_of "$B")" = "1" ] && ok "bad fixture: exit 1" || bad "bad fixture: expected exit 1"

BJSON="$(json_of "$B")"
printf '%s' "$BJSON" | grep -q "does not appear in any phase tools line" && ok "bad fixture: flags dangling tool" || bad "bad fixture: did not flag dangling tool"
printf '%s' "$BJSON" | grep -q "ghost-tag" && ok "bad fixture: flags dangling exit" || bad "bad fixture: did not flag dangling exit"
printf '%s' "$BJSON" | grep -q "ZHC_missing_field" && ok "bad fixture: flags missing CRM field" || bad "bad fixture: did not flag missing CRM field"
printf '%s' "$BJSON" | grep -q "CAL_MISSING" && ok "bad fixture: flags absent calendar id" || bad "bad fixture: did not flag absent calendar id"

# --- LEGACY fixture: no declares block -> WARN, not FAIL. ---------------------
L="$TMP/legacy/conversation-workflows"
mkdir -p "$L"
cat > "$L/legacy.md" <<'EOF'
# Conversation Workflow: Legacy

## What the agent does

### Phase 1 - Qualify
tools: update_tags, reference_documents
Qualify.

## Exit rules

exit-when-tag: talk-to-human, action: handoff

## On success
Win.

## On escalation
Escalate.
EOF

[ "$(verdict_of "$L")" = "PASS" ] && ok "legacy fixture: verdict PASS (WARN only)" || bad "legacy fixture: expected PASS"
[ "$(exit_of "$L")" = "0" ] && ok "legacy fixture: exit 0" || bad "legacy fixture: expected exit 0"
LJSON="$(json_of "$L")"
printf '%s' "$LJSON" | grep -q "no declares block" && ok "legacy fixture: warns on missing declares block" || bad "legacy fixture: did not warn"

echo ""
echo "qc-playbook-declares tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
