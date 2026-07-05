#!/usr/bin/env bash
# qc-workflow-exits.test.sh - negative + positive fixture tests for
# qc-workflow-exits.sh.
#
# Proves the U-2 gate:
#   * PASSES a workflows dir whose exit rules use valid actions and whose route
#     targets are present in registry.md, and
#   * FAILS a workflows dir whose exit rule routes to a target absent from
#     registry.md (the seeded bad fixture), and also on a route with no target.
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-workflow-exits.sh"

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

# --- GOOD fixture: route target present in registry -> PASS. --------------
G="$TMP/good/conversation-workflows"
mkdir -p "$G"
cat > "$G/registry.md" <<'EOF'
# Conversation Workflows Registry

## Active workflows

| ID | Name | OpenClaw playbook |
|---|---|---|
| qualify | Qualify | qualify.md |
| support-intake | Support intake | support-intake.md |
EOF
cat > "$G/qualify.md" <<'EOF'
# Conversation Workflow: Qualify

## What the agent does

### Phase 1 - Qualify
tools: update_tags, reference_documents
Qualify the lead.

## Exit rules

exit-when-tag: already-booked, action: end, closing: none
exit-when-tag: talk-to-human, action: handoff
exit-when-tag: switch-to-support, action: route, target: support-intake

## On success
Win.

## On escalation
Escalate.
EOF
printf '# support intake\n' > "$G/support-intake.md"

[ "$(verdict_of "$G")" = "PASS" ] && ok "good fixture: verdict PASS" || bad "good fixture: expected PASS"
[ "$(exit_of "$G")" = "0" ] && ok "good fixture: exit 0" || bad "good fixture: expected exit 0"

# --- BAD fixture: route to a target absent from registry + a targetless route + bad action -> FAIL. ---
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
tools: reference_documents
Qualify.

## Exit rules

exit-when-tag: switch-to-support, action: route, target: nonexistent-playbook
exit-when-tag: half-baked, action: route
exit-when-tag: bad-tag, action: teleport

## On success
Win.

## On escalation
Escalate.
EOF

[ "$(verdict_of "$B")" = "FAIL" ] && ok "bad fixture: verdict FAIL" || bad "bad fixture: expected FAIL"
[ "$(exit_of "$B")" = "1" ] && ok "bad fixture: exit 1" || bad "bad fixture: expected exit 1"

BJSON="$(bash "$GATE" --dir "$B" --json 2>/dev/null)"
printf '%s' "$BJSON" | grep -q "nonexistent-playbook" && ok "bad fixture: flags absent route target" || bad "bad fixture: did not flag absent target"
printf '%s' "$BJSON" | grep -q "requires a target" && ok "bad fixture: flags targetless route" || bad "bad fixture: did not flag targetless route"
printf '%s' "$BJSON" | grep -q "teleport" && ok "bad fixture: flags invalid action" || bad "bad fixture: did not flag invalid action"

echo ""
echo "qc-workflow-exits tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
