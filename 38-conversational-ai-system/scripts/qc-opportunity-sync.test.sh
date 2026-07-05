#!/usr/bin/env bash
# qc-opportunity-sync.test.sh - negative + positive fixture tests for
# qc-opportunity-sync.sh (U-13 pipeline stage-map validation).
#
# Proves the gate:
#   * PASSES a playbook whose stage-map names all exist in the declared pipeline,
#   * FAILS a playbook whose stage-map names a stage absent from the pipeline, and
#     a playbook whose declared pipeline id is absent from the caf export,
#   * treats a playbook with no pipeline/stage-map as inert (no failure).
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-opportunity-sync.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PIPE_EXPORT="$TMP/pipe.json"
cat > "$PIPE_EXPORT" <<'EOF'
{"pipelines": [{"id": "PIPE_A", "stages": [
  {"name": "New Lead"},
  {"name": "Qualified"},
  {"name": "Appointment Booked"},
  {"name": "Needs Human"}
]}]}
EOF

verdict_of() {
  bash "$GATE" --dir "$1" --pipelines-export "$PIPE_EXPORT" --json 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null
}
exit_of() {
  local rc=0
  bash "$GATE" --dir "$1" --pipelines-export "$PIPE_EXPORT" >/dev/null 2>&1 || rc=$?
  echo "$rc"
}
json_of() {
  bash "$GATE" --dir "$1" --pipelines-export "$PIPE_EXPORT" --json 2>/dev/null
}

# --- GOOD fixture: every stage-map name is in the pipeline -> PASS. -----------
G="$TMP/good/conversation-workflows"
mkdir -p "$G"
cat > "$G/qualify.md" <<'EOF'
# Conversation Workflow: Qualify

declares
pipeline: PIPE_A
stage-map: phase 1: New Lead, phase 3: Qualified, win: Appointment Booked, exit talk-to-human: Needs Human

## What the agent does

### Phase 1 - Qualify
tools: update_tags, reference_documents
Qualify.

## Exit rules

exit-when-tag: talk-to-human, action: handoff

## On success
Booked.

## On escalation
Escalate.
EOF
# A playbook with no pipeline is inert and must not fail.
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

# --- BAD fixture: bogus stage name + unknown pipeline -> FAIL. ----------------
B="$TMP/bad/conversation-workflows"
mkdir -p "$B"
cat > "$B/bogus-stage.md" <<'EOF'
# Conversation Workflow: Bogus Stage

declares
pipeline: PIPE_A
stage-map: phase 1: New Lead, win: Nonexistent Stage

## What the agent does

### Phase 1 - Qualify
tools: reference_documents
Qualify.

## On success
Win.
EOF
cat > "$B/unknown-pipeline.md" <<'EOF'
# Conversation Workflow: Unknown Pipeline

declares
pipeline: PIPE_GHOST
stage-map: phase 1: New Lead

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
printf '%s' "$BJSON" | grep -q "Nonexistent Stage" && ok "bad fixture: flags stage absent from pipeline" || bad "bad fixture: did not flag bogus stage"
printf '%s' "$BJSON" | grep -q "PIPE_GHOST" && ok "bad fixture: flags pipeline absent from export" || bad "bad fixture: did not flag unknown pipeline"

echo ""
echo "qc-opportunity-sync tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
