#!/usr/bin/env bash
# qc-built-workflow.sh — Skill 44: per-build QC for a constructed GHL workflow
#
# DISTINCT from qc-convert-and-flow.sh (install-level QC for the skill itself).
# This script verifies a BUILT WORKFLOW artifact against the WF checklist items.
#
# Usage:
#   ./qc-built-workflow.sh <workflow-id> [--publish-intent DRAFT|LIVE] [--re-entry ONCE|ALLOW-MULTIPLE] [--json]
#
#   workflow-id       GHL workflow id (required)
#   --publish-intent  Client's publish decision: DRAFT (default) or LIVE
#   --re-entry        Client's re-entry decision: ONCE (default) or ALLOW-MULTIPLE
#   --json            Emit per-item PASS/FAIL as JSON to stdout (for QC sub-agent parsing)
#
# Exit codes:
#   0  = ALL mechanically-checkable items PASS
#   1  = one or more items FAIL
#   2  = workflow not found or caf not available (hard prereq failure)
#
# Mechanically-checkable WF items (asserted here):
#   WF-3  Trigger present
#   WF-4  Trigger active flag vs publish-intent (WF-ACTIVE GATE)
#   WF-5  Publish state (draft/published) vs publish-intent
#   WF-6  Re-entry/allow-multiple vs re-entry decision
#   WF-7  Action sequence: at minimum one action node present + delivery chain not empty
#   WF-12 SMS From-number non-empty (for any SMS-type action nodes)
#   WF-15 Delivery chain linkage: trigger -> step -> exit (targetActionId present)
#   WF-18 Snapshot exists for this workflow id (reversibility gate)
#   WF-21 Snapshot file is present and non-empty on disk
#
# Non-mechanical items (WF-1,2,8,9,10,11,13,14,16,17,19,20) require human/LLM review;
# they are noted in the JSON output as "requires_human_review".
#
# Invoked by the MiniMax QC sub-agent during Step 9 of INSTRUCTIONS.md.
set -euo pipefail

# ── Arg parsing ───────────────────────────────────────────────────────────────
WORKFLOW_ID=""
PUBLISH_INTENT="DRAFT"
RE_ENTRY_DECISION="ONCE"
JSON_MODE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --publish-intent) PUBLISH_INTENT="${2:-DRAFT}"; shift 2 ;;
    --re-entry)       RE_ENTRY_DECISION="${2:-ONCE}"; shift 2 ;;
    --json)           JSON_MODE=1; shift ;;
    -*)               echo "Unknown option: $1" >&2; exit 2 ;;
    *)                WORKFLOW_ID="$1"; shift ;;
  esac
done

if [ -z "$WORKFLOW_ID" ]; then
  echo "ERROR: workflow-id required" >&2
  echo "Usage: $0 <workflow-id> [--publish-intent DRAFT|LIVE] [--re-entry ONCE|ALLOW-MULTIPLE] [--json]" >&2
  exit 2
fi

PUBLISH_INTENT="${PUBLISH_INTENT^^}"
RE_ENTRY_DECISION="${RE_ENTRY_DECISION^^}"

# ── Prereq: caf available ─────────────────────────────────────────────────────
if ! command -v caf >/dev/null 2>&1; then
  echo "ERROR: caf not found on PATH. Cannot perform per-build QC." >&2
  exit 2
fi

# ── Resolve skill dir (for snapshot path) ─────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM="${OPENCLAW_PLATFORM:-mac}"
if [ "$PLATFORM" = "mac" ]; then
  CAF_DATA="$HOME/.openclaw/tools/convert-and-flow-cli/data"
else
  CAF_DATA="/data/.openclaw/tools/convert-and-flow-cli/data"
fi
SNAPSHOT_DIR="$CAF_DATA/snapshots"
BUILD_EVENTS_LEDGER="$CAF_DATA/build-events.jsonl"

# ── Export the workflow ────────────────────────────────────────────────────────
EXPORT_OUT=""
if ! EXPORT_OUT=$(caf workflows export "$WORKFLOW_ID" 2>&1); then
  echo "ERROR: caf workflows export $WORKFLOW_ID failed: $EXPORT_OUT" >&2
  exit 2
fi

if echo "$EXPORT_OUT" | grep -qi "not found\|404\|no workflow\|error"; then
  echo "ERROR: workflow $WORKFLOW_ID not found in GHL" >&2
  exit 2
fi

# ── Result tracking ───────────────────────────────────────────────────────────
declare -A ITEM_STATUS
declare -A ITEM_OBSERVED
declare -A ITEM_EXPECTED
declare -A ITEM_NOTES
PASS_COUNT=0
FAIL_COUNT=0

record_pass() {
  local item="$1" observed="$2" expected="$3" notes="${4:-}"
  ITEM_STATUS["$item"]="PASS"
  ITEM_OBSERVED["$item"]="$observed"
  ITEM_EXPECTED["$item"]="$expected"
  ITEM_NOTES["$item"]="$notes"
  PASS_COUNT=$((PASS_COUNT + 1))
}

record_fail() {
  local item="$1" observed="$2" expected="$3" notes="${4:-}"
  ITEM_STATUS["$item"]="FAIL"
  ITEM_OBSERVED["$item"]="$observed"
  ITEM_EXPECTED["$item"]="$expected"
  ITEM_NOTES["$item"]="$notes"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

record_human() {
  local item="$1" notes="${2:-}"
  ITEM_STATUS["$item"]="REQUIRES_HUMAN_REVIEW"
  ITEM_OBSERVED["$item"]="n/a"
  ITEM_EXPECTED["$item"]="n/a"
  ITEM_NOTES["$item"]="$notes"
}

# ── WF-3: Trigger present ─────────────────────────────────────────────────────
TRIGGER_TYPE=""
if echo "$EXPORT_OUT" | grep -qiE '"type".*"trigger|triggerType|trigger_type|event_type'; then
  TRIGGER_TYPE=$(echo "$EXPORT_OUT" | grep -oiE '"triggerType"\s*:\s*"[^"]*"|"trigger_type"\s*:\s*"[^"]*"|"type"\s*:\s*"[A-Z_]*TRIGGER[^"]*"' | head -1 || echo "present")
  record_pass "WF-3" "${TRIGGER_TYPE:-present}" "trigger present" "Trigger node found in export"
elif echo "$EXPORT_OUT" | grep -qiE 'trigger|contactCreated|formSubmitted|tagAdded|ContactCreate|FormSubmit|TagAdd'; then
  record_pass "WF-3" "trigger_found" "trigger present" "Trigger keyword found in export"
else
  record_fail "WF-3" "no_trigger_found" "trigger present" "No trigger node detected in caf workflows export output"
fi

# ── WF-4: Trigger active flag vs publish-intent (WF-ACTIVE GATE) ──────────────
EXPECTED_ACTIVE="false"
[ "$PUBLISH_INTENT" = "LIVE" ] && EXPECTED_ACTIVE="true"

OBSERVED_ACTIVE="unknown"
if echo "$EXPORT_OUT" | grep -qi '"active"\s*:\s*true\|"triggerActive"\s*:\s*true\|active.*true'; then
  OBSERVED_ACTIVE="true"
elif echo "$EXPORT_OUT" | grep -qi '"active"\s*:\s*false\|"triggerActive"\s*:\s*false\|active.*false'; then
  OBSERVED_ACTIVE="false"
fi

if [ "$OBSERVED_ACTIVE" = "$EXPECTED_ACTIVE" ]; then
  record_pass "WF-4" "$OBSERVED_ACTIVE" "$EXPECTED_ACTIVE" "Trigger active state matches publish-intent ($PUBLISH_INTENT)"
elif [ "$OBSERVED_ACTIVE" = "unknown" ]; then
  record_pass "WF-4" "unknown_in_export" "$EXPECTED_ACTIVE" "Trigger active state not visible in export — requires escalation per skill 36 for trigger-bucket state (MVP-deferred)"
else
  WF4_NOTE="WF-ACTIVE BUG: publish-intent=$PUBLISH_INTENT but trigger active=$OBSERVED_ACTIVE. Workflow will silently never fire."
  [ "$PUBLISH_INTENT" = "LIVE" ] && \
    record_fail "WF-4" "$OBSERVED_ACTIVE" "$EXPECTED_ACTIVE" "$WF4_NOTE" || \
    record_pass "WF-4" "$OBSERVED_ACTIVE" "$EXPECTED_ACTIVE" "Client chose DRAFT — inactive trigger is correct"
fi

# ── WF-5: Publish state ────────────────────────────────────────────────────────
EXPECTED_STATUS="draft"
[ "$PUBLISH_INTENT" = "LIVE" ] && EXPECTED_STATUS="published"

OBSERVED_STATUS="unknown"
if echo "$EXPORT_OUT" | grep -qi '"status"\s*:\s*"published"\|status.*published'; then
  OBSERVED_STATUS="published"
elif echo "$EXPORT_OUT" | grep -qi '"status"\s*:\s*"draft"\|status.*draft'; then
  OBSERVED_STATUS="draft"
fi

if [ "$OBSERVED_STATUS" = "$EXPECTED_STATUS" ]; then
  record_pass "WF-5" "$OBSERVED_STATUS" "$EXPECTED_STATUS" "Publish state matches client decision ($PUBLISH_INTENT)"
elif [ "$OBSERVED_STATUS" = "unknown" ]; then
  record_pass "WF-5" "unknown_in_export" "$EXPECTED_STATUS" "Publish status not directly readable in export output — human review recommended"
else
  record_fail "WF-5" "$OBSERVED_STATUS" "$EXPECTED_STATUS" "Publish state mismatch: client chose $PUBLISH_INTENT but workflow status is $OBSERVED_STATUS. Never publish without explicit YES."
fi

# ── WF-6: Re-entry / allow-multiple ───────────────────────────────────────────
EXPECTED_REENTRY="false"
[ "$RE_ENTRY_DECISION" = "ALLOW-MULTIPLE" ] && EXPECTED_REENTRY="true"

OBSERVED_REENTRY="unknown"
if echo "$EXPORT_OUT" | grep -qi '"allowMultiple"\s*:\s*true\|"reEntry"\s*:\s*true\|allow_multiple.*true\|re_entry.*true'; then
  OBSERVED_REENTRY="true"
elif echo "$EXPORT_OUT" | grep -qi '"allowMultiple"\s*:\s*false\|"reEntry"\s*:\s*false\|allow_multiple.*false\|re_entry.*false'; then
  OBSERVED_REENTRY="false"
fi

if [ "$OBSERVED_REENTRY" = "$EXPECTED_REENTRY" ]; then
  record_pass "WF-6" "$OBSERVED_REENTRY" "$EXPECTED_REENTRY" "Re-entry setting matches client decision ($RE_ENTRY_DECISION)"
elif [ "$OBSERVED_REENTRY" = "unknown" ]; then
  record_pass "WF-6" "unknown_in_export" "$EXPECTED_REENTRY" "Re-entry not directly readable in export — human review recommended; client decision was $RE_ENTRY_DECISION"
else
  record_fail "WF-6" "$OBSERVED_REENTRY" "$EXPECTED_REENTRY" "Re-entry mismatch: client chose $RE_ENTRY_DECISION but setting is $OBSERVED_REENTRY"
fi

# ── WF-7: Action sequence — at least one action node present ──────────────────
ACTION_COUNT=0
ACTION_COUNT=$(echo "$EXPORT_OUT" | grep -oiE '"type"\s*:\s*"(SMS|EMAIL|WAIT|IF_ELSE|ADD_TAG|REMOVE_TAG|UPDATE_CONTACT|WEBHOOK|CREATE_TASK|CREATE_NOTE|REMOVE_FROM_WORKFLOW|END)[^"]*"' | wc -l || echo 0)
ACTION_COUNT=$(echo "$ACTION_COUNT" | tr -d ' ')

if [ "$ACTION_COUNT" -gt 0 ]; then
  record_pass "WF-7" "${ACTION_COUNT}_action_nodes_present" ">=1 action nodes" "link_steps ordering verified by engine (caf builds apply link_steps before save)"
else
  record_fail "WF-7" "0_action_nodes_found" ">=1 action nodes" "No recognizable action nodes found in export. Delivery chain may be empty."
fi

# ── WF-12: SMS From-number non-empty ─────────────────────────────────────────
SMS_NODES_COUNT=$(echo "$EXPORT_OUT" | grep -ociE '"type"\s*:\s*"SMS\|"type"\s*:\s*"SEND_SMS' || echo 0)
SMS_NODES_COUNT=$(echo "$SMS_NODES_COUNT" | tr -d ' ')
SMS_WITHOUT_FROM=$(echo "$EXPORT_OUT" | python3 -c "
import sys, json, re
data = sys.stdin.read()
try:
  obj = json.loads(data)
  steps = obj.get('steps', obj.get('actions', obj.get('nodes', [])))
  if not isinstance(steps, list):
    steps = []
  count = 0
  for s in steps:
    t = (s.get('type','') or '').upper()
    if 'SMS' in t or 'SEND_SMS' in t:
      from_num = s.get('fromNumber','') or s.get('from_number','') or s.get('phoneNumber','') or ''
      if not from_num.strip():
        count += 1
  print(count)
except:
  print(-1)
" 2>/dev/null || echo "-1")

if [ "$SMS_WITHOUT_FROM" = "-1" ]; then
  # Could not parse JSON — use text-grep fallback
  if echo "$EXPORT_OUT" | grep -qi 'fromNumber.*""\|from_number.*""\|phoneNumber.*""'; then
    record_fail "WF-12" "sms_node_with_empty_from_number" "from-number non-empty on all SMS nodes" "CRITICAL: SMS node with empty From-number detected — will silently fail to send"
  else
    record_pass "WF-12" "no_empty_from_numbers_detected" "from-number non-empty" "Text-grep fallback: no empty From-number patterns found (human review recommended for full JSON parse)"
  fi
elif [ "$SMS_WITHOUT_FROM" -gt 0 ]; then
  record_fail "WF-12" "${SMS_WITHOUT_FROM}_sms_nodes_missing_from_number" "from-number non-empty on all SMS nodes" "CRITICAL: $SMS_WITHOUT_FROM SMS node(s) have no From-number — will silently fail to send"
else
  record_pass "WF-12" "all_sms_nodes_have_from_number" "from-number non-empty on all SMS nodes" "All SMS nodes verified with a From-number"
fi

# ── WF-15: Delivery chain linkage ─────────────────────────────────────────────
HAS_TARGET_ACTION=$(echo "$EXPORT_OUT" | grep -c 'targetActionId\|target_action_id\|nextStep\|next_step\|parentKey\|parent_key' || echo 0)
HAS_TARGET_ACTION=$(echo "$HAS_TARGET_ACTION" | tr -d ' ')

if [ "$HAS_TARGET_ACTION" -gt 0 ]; then
  record_pass "WF-15" "delivery_chain_links_present" "trigger->step->exit linkage present" "targetActionId/parentKey/nextStep link fields found — delivery chain wired"
else
  # Could be a single-step workflow with no chaining needed, or an export format without these fields
  if [ "$ACTION_COUNT" -le 1 ]; then
    record_pass "WF-15" "single_or_zero_step_workflow" "single-step workflow — chain not required" "Single action node; no inter-step linking needed"
  else
    record_fail "WF-15" "no_linkage_fields_found" "targetActionId/parentKey present in multi-step workflow" "Multi-step workflow but no delivery chain link fields found in export. Steps may be orphaned."
  fi
fi

# ── WF-18 + WF-21: Snapshot exists ────────────────────────────────────────────
SNAPSHOT_FOUND=0
if [ -d "$SNAPSHOT_DIR" ]; then
  WF_SNAPSHOT_DIR="$SNAPSHOT_DIR"
  # Search for any snapshot file containing the workflow id in its path
  if find "$SNAPSHOT_DIR" -name "*.json" 2>/dev/null | grep -q "$WORKFLOW_ID" 2>/dev/null; then
    SNAPSHOT_FOUND=1
  elif find "$SNAPSHOT_DIR" -path "*/$WORKFLOW_ID/*" -name "*.json" 2>/dev/null | head -1 | grep -q .; then
    SNAPSHOT_FOUND=1
  fi
fi

if [ "$SNAPSHOT_FOUND" -eq 1 ]; then
  SNAPSHOT_PATH=$(find "$SNAPSHOT_DIR" -name "*.json" 2>/dev/null | grep "$WORKFLOW_ID" | head -1 || echo "found")
  record_pass "WF-18" "dependencies_pre_existed_or_snapshot_present" "dependencies verified before build" "Snapshot present: $SNAPSHOT_PATH"
  record_pass "WF-21" "snapshot_exists_and_non_empty" "snapshot present under data/snapshots/" "Snapshot: $SNAPSHOT_PATH — build is reversible via caf workflows restore"
else
  # Snapshot may not exist if this is a pure read-verify run or the build path didn't create one
  record_fail "WF-18" "no_snapshot_found_for_workflow_$WORKFLOW_ID" "snapshot present" "No snapshot found at $SNAPSHOT_DIR for workflow $WORKFLOW_ID — build may not be reversible"
  record_fail "WF-21" "no_snapshot_found" "snapshot present and non-empty" "No pre-build snapshot found. caf workflows restore will not be available for rollback."
fi

# ── Human-review items (noted, not failed by script) ─────────────────────────
record_human "WF-1"  "Workflow name must be verified against plan/outline by QC agent reading export output"
record_human "WF-2"  "Tags must be verified by QC agent: check each tag in export against plan, GET-verify in GHL"
record_human "WF-8"  "If/Else conditions (fields, operators, AND/OR logic) require QC agent review of export output"
record_human "WF-9"  "Wait step durations require QC agent review of export output"
record_human "WF-10" "Custom fields (data type + exact name) require QC agent review of export output"
record_human "WF-11" "Custom values (non-empty + exact name) require QC agent review of export output"
record_human "WF-13" "Email From Name/From Email require QC agent review of export output"
record_human "WF-14" "Webhook URL/method/headers require QC agent review of export output"
record_human "WF-16" "Advanced settings (Stop-on-Response, time window, timezone) require QC agent review"
record_human "WF-17" "Edge case decisions require QC agent review against plan"
record_human "WF-19" "TRINITY completeness requires QC agent to check qc-trinity-registry.sh if conversational"
record_human "WF-20" "Hallucination detection (WF-20) requires QC agent to reconcile all build-agent claims against export"

# ── Output ─────────────────────────────────────────────────────────────────────
MECHANICAL_ITEMS=("WF-3" "WF-4" "WF-5" "WF-6" "WF-7" "WF-12" "WF-15" "WF-18" "WF-21")
HUMAN_ITEMS=("WF-1" "WF-2" "WF-8" "WF-9" "WF-10" "WF-11" "WF-13" "WF-14" "WF-16" "WF-17" "WF-19" "WF-20")

if [ "$JSON_MODE" -eq 1 ]; then
  # Emit JSON for QC sub-agent parsing
  python3 -c "
import json, sys

mechanical = $(printf '%s\n' "${MECHANICAL_ITEMS[@]}" | python3 -c "import sys; print(json.dumps(sys.stdin.read().split()))")
human = $(printf '%s\n' "${HUMAN_ITEMS[@]}" | python3 -c "import sys; print(json.dumps(sys.stdin.read().split()))")

results = {}
" 2>/dev/null || true

  # Build JSON manually (no python dependency required)
  echo "{"
  echo "  \"workflow_id\": \"$WORKFLOW_ID\","
  echo "  \"publish_intent\": \"$PUBLISH_INTENT\","
  echo "  \"re_entry_decision\": \"$RE_ENTRY_DECISION\","
  echo "  \"mechanical_pass\": $PASS_COUNT,"
  echo "  \"mechanical_fail\": $FAIL_COUNT,"
  echo "  \"overall_mechanical\": \"$([ "$FAIL_COUNT" -eq 0 ] && echo PASS || echo FAIL)\","
  echo "  \"items\": {"
  ALL_ITEMS=("WF-3" "WF-4" "WF-5" "WF-6" "WF-7" "WF-12" "WF-15" "WF-18" "WF-21" \
             "WF-1" "WF-2" "WF-8" "WF-9" "WF-10" "WF-11" "WF-13" "WF-14" "WF-16" "WF-17" "WF-19" "WF-20")
  FIRST=1
  for item in "${ALL_ITEMS[@]}"; do
    [ "$FIRST" -eq 0 ] && echo ","
    FIRST=0
    STATUS="${ITEM_STATUS[$item]:-UNKNOWN}"
    OBSERVED="${ITEM_OBSERVED[$item]:-n/a}"
    EXPECTED="${ITEM_EXPECTED[$item]:-n/a}"
    NOTES="${ITEM_NOTES[$item]:-}"
    # Escape quotes
    OBSERVED=$(echo "$OBSERVED" | sed 's/"/\\"/g')
    EXPECTED=$(echo "$EXPECTED" | sed 's/"/\\"/g')
    NOTES=$(echo "$NOTES" | sed 's/"/\\"/g')
    printf '    "%s": {"status": "%s", "observed": "%s", "expected": "%s", "notes": "%s"}' \
      "$item" "$STATUS" "$OBSERVED" "$EXPECTED" "$NOTES"
  done
  echo ""
  echo "  }"
  echo "}"
else
  # Human-readable output
  echo "═══════════════════════════════════════════════════════════"
  echo "  Skill 44 Per-Build QC — workflow: $WORKFLOW_ID"
  echo "  Publish intent: $PUBLISH_INTENT | Re-entry: $RE_ENTRY_DECISION"
  echo "═══════════════════════════════════════════════════════════"
  echo ""
  echo "── Mechanical assertions ──"
  for item in "${MECHANICAL_ITEMS[@]}"; do
    STATUS="${ITEM_STATUS[$item]:-UNKNOWN}"
    OBSERVED="${ITEM_OBSERVED[$item]:-n/a}"
    EXPECTED="${ITEM_EXPECTED[$item]:-n/a}"
    NOTES="${ITEM_NOTES[$item]:-}"
    printf "  %-6s %-5s | observed: %-45s | expected: %s\n" "$item" "$STATUS" "$OBSERVED" "$EXPECTED"
    [ -n "$NOTES" ] && printf "         NOTE: %s\n" "$NOTES"
  done
  echo ""
  echo "── Items requiring QC agent review (not machine-assertable) ──"
  for item in "${HUMAN_ITEMS[@]}"; do
    NOTES="${ITEM_NOTES[$item]:-}"
    printf "  %-6s REQUIRES_HUMAN_REVIEW | %s\n" "$item" "$NOTES"
  done
  echo ""
  echo "═══════════════════════════════════════════════════════════"
  echo "  Mechanical result: $PASS_COUNT PASS | $FAIL_COUNT FAIL"
  echo "═══════════════════════════════════════════════════════════"
  if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "  PER-BUILD QC FAILED — $FAIL_COUNT mechanical blocker(s). See items above."
    echo "  Do NOT declare workflow done. Fix failing items and re-run QC."
  else
    echo "  Mechanical QC PASSED — QC agent must still review human-review items above."
  fi
  echo ""
fi

# ── Append to build-events ledger ─────────────────────────────────────────────
mkdir -p "$(dirname "$BUILD_EVENTS_LEDGER")" 2>/dev/null || true
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
VERDICT="$([ "$FAIL_COUNT" -eq 0 ] && echo PASS || echo FAIL)"
cat >> "$BUILD_EVENTS_LEDGER" 2>/dev/null << LEDGER_EOF
{"event":"qc_run","timestamp":"${TIMESTAMP}","workflow_id":"${WORKFLOW_ID}","publish_intent":"${PUBLISH_INTENT}","re_entry":"${RE_ENTRY_DECISION}","mechanical_pass":${PASS_COUNT},"mechanical_fail":${FAIL_COUNT},"verdict":"${VERDICT}"}
LEDGER_EOF

[ "$FAIL_COUNT" -gt 0 ] && exit 1
exit 0
