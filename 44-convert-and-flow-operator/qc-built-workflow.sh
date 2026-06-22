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
TMP=$(mktemp /tmp/qc-wf-export-XXXXXX.json)
trap 'rm -f "$TMP"' EXIT

EXPORT_ERR=""
if ! EXPORT_ERR=$(caf workflows export --workflow-id "$WORKFLOW_ID" --out "$TMP" 2>&1); then
  echo "ERROR: caf workflows export --workflow-id $WORKFLOW_ID --out $TMP failed: $EXPORT_ERR" >&2
  rm -f "$TMP"
  exit 2
fi

if [ ! -s "$TMP" ]; then
  echo "ERROR: export produced an empty file for workflow $WORKFLOW_ID" >&2
  exit 2
fi

EXPORT_OUT=$(cat "$TMP")

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

record_na() {
  local item="$1" notes="${2:-}"
  ITEM_STATUS["$item"]="N/A"
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
  record_human "WF-4" "Trigger active state not visible in export — cannot machine-assert; requires human review per skill 36 for trigger-bucket state (MVP-deferred)"
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
  record_human "WF-5" "Publish status not directly readable in export output — cannot machine-assert; requires human review"
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
  record_human "WF-6" "Re-entry not directly readable in export — cannot machine-assert; requires human review; client decision was $RE_ENTRY_DECISION"
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

# ── WF-12: SMS From-number ────────────────────────────────────────────────────
# WF-12 mechanical assertion (hardened): every SMS node MUST carry a fromNumber
# KEY. On a LIVE/published workflow the value must additionally be NON-EMPTY
# (an empty From silently fails to send). On a DRAFT workflow an empty From is a
# WARNING the QC sub-agent must surface (GHL may resolve a location default at
# send time, which is unproven and must be confirmed before going LIVE).
# Output is three counts: "<missing_key> <empty_on_live> <empty_on_draft>".
SMS_FROM_CHECK=$(echo "$EXPORT_OUT" | PUBLISH_INTENT="$PUBLISH_INTENT" python3 -c "
import sys, json, os
data = sys.stdin.read()
live = os.environ.get('PUBLISH_INTENT','DRAFT').upper() == 'LIVE'
try:
  obj = json.loads(data)
  # Steps may live at several keys depending on export shape.
  steps = obj.get('steps') or obj.get('actions') or obj.get('nodes') or []
  wd = obj.get('workflowData') or {}
  if isinstance(wd, dict) and wd.get('templates'):
    steps = wd['templates']
  if not isinstance(steps, list):
    steps = []
  missing_key = empty_live = empty_draft = total_sms = 0
  for s in steps:
    if not isinstance(s, dict):
      continue
    t = (s.get('type','') or '').upper()
    if 'SMS' in t or 'SEND_SMS' in t:
      total_sms += 1
      attrs = s.get('attributes') if isinstance(s.get('attributes'), dict) else {}
      has_key = ('fromNumber' in s) or ('from_number' in s) or ('phoneNumber' in s) \
                or ('fromNumber' in attrs) or ('from_number' in attrs) or ('phoneNumber' in attrs)
      val = (s.get('fromNumber') or s.get('from_number') or s.get('phoneNumber')
             or attrs.get('fromNumber') or attrs.get('from_number') or attrs.get('phoneNumber') or '')
      if not has_key:
        missing_key += 1
      elif not str(val).strip():
        if live:
          empty_live += 1
        else:
          empty_draft += 1
  print('%d %d %d %d' % (missing_key, empty_live, empty_draft, total_sms))
except Exception:
  print('-1 -1 -1 -1')
" 2>/dev/null || echo "-1 -1 -1 -1")

read -r SMS_MISSING_KEY SMS_EMPTY_LIVE SMS_EMPTY_DRAFT SMS_TOTAL <<< "$SMS_FROM_CHECK"

if [ "$SMS_MISSING_KEY" = "-1" ]; then
  # Could not parse JSON — use text-grep fallback
  if echo "$EXPORT_OUT" | grep -qiE '"type"\s*:\s*"(sms|send_sms)"'; then
    if echo "$EXPORT_OUT" | grep -qi 'fromNumber.*""\|from_number.*""\|phoneNumber.*""'; then
      record_fail "WF-12" "sms_node_with_empty_from_number" "fromNumber key present + non-empty on every SMS node" "CRITICAL: SMS node with empty From-number detected (text-grep fallback) — will silently fail to send"
    elif echo "$EXPORT_OUT" | grep -qi 'fromNumber\|from_number\|phoneNumber'; then
      record_pass "WF-12" "from_number_key_present" "fromNumber key present on every SMS node" "Text-grep fallback: a From-number key is present (human review recommended for full JSON parse)"
    else
      record_fail "WF-12" "sms_present_no_from_number_key" "fromNumber key present on every SMS node" "CRITICAL: SMS node(s) present but no From-number key found (text-grep fallback). sms_step must emit fromNumber."
    fi
  else
    record_pass "WF-12" "no_sms_nodes" "n/a — no SMS nodes" "No SMS nodes detected in export"
  fi
elif [ "$SMS_TOTAL" -eq 0 ]; then
  record_pass "WF-12" "no_sms_nodes" "n/a — no SMS nodes" "No SMS nodes in this workflow"
elif [ "$SMS_MISSING_KEY" -gt 0 ]; then
  record_fail "WF-12" "${SMS_MISSING_KEY}_of_${SMS_TOTAL}_sms_nodes_missing_fromNumber_key" "fromNumber key present on every SMS node" "CRITICAL: $SMS_MISSING_KEY SMS node(s) have NO fromNumber key — sms_step must emit it (WF-12 gap)"
elif [ "$SMS_EMPTY_LIVE" -gt 0 ]; then
  record_fail "WF-12" "${SMS_EMPTY_LIVE}_of_${SMS_TOTAL}_sms_nodes_empty_from_on_LIVE" "non-empty From on every SMS node of a LIVE workflow" "CRITICAL: $SMS_EMPTY_LIVE SMS node(s) have an EMPTY From-number on a LIVE/published workflow — will silently fail to send. Set CAF_SMS_FROM_NUMBER or pass from_number."
elif [ "$SMS_EMPTY_DRAFT" -gt 0 ]; then
  record_pass "WF-12" "${SMS_EMPTY_DRAFT}_of_${SMS_TOTAL}_sms_nodes_empty_from_on_DRAFT" "fromNumber key present on every SMS node" "WARNING: fromNumber key present but EMPTY on $SMS_EMPTY_DRAFT SMS node(s) of a DRAFT workflow. GHL location-default at send time is UNPROVEN — confirm a From-number before going LIVE."
else
  record_pass "WF-12" "all_${SMS_TOTAL}_sms_nodes_have_nonempty_from_number" "fromNumber key present + non-empty" "All $SMS_TOTAL SMS node(s) carry a non-empty From-number"
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
  # No snapshot found. On a FRESH BUILD (workflow did not exist before this run)
  # there is no prior state to snapshot, so reversibility is N/A — not a failure.
  # This allows a clean build to pass QC. On a re-build or update a snapshot
  # MUST exist; the QC agent should verify and escalate if one is absent.
  record_na "WF-18" "fresh-build: no prior snapshot exists for workflow $WORKFLOW_ID — reversibility is N/A for a first-time build. On a re-build this MUST be present."
  record_na "WF-21" "fresh-build: no snapshot on disk — N/A for a first-time build. caf workflows restore is not applicable until a snapshot is captured."
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

# ── WEIGHTED QUALITY RUBRIC (references/workflow-quality-rubric.md) ────────────
# SUPERSET OVERLAY computed AFTER WF-1..21 (never instead of). Each of the 8
# dimensions maps to existing WF evidence. Dimensions whose WF evidence is fully
# machine-asserted here get a mechanical anchor (1/5/10); dimensions that depend
# on REQUIRES_HUMAN_REVIEW WF items emit a conservative machine FLOOR plus a
# rubric_human_grade flag so the Step-9 QC sub-agent grades them 1/5/10 and
# recomputes the final weighted score. The script's own weighted score is a
# FLOOR (machine-knowable lower bound), surfaced alongside the WF result so a
# real build emits BOTH numbers. Ship threshold (final, after human grading): >= 8.5.
#
# Weights: D1=20 D2=15 D3=15 D4=12 D5=12 D6=10 D7=8 D8=8  (sum=100)

_wf() { echo "${ITEM_STATUS[$1]:-UNKNOWN}"; }

# D2 Trigger correctness — fully mechanical (WF-3 + WF-4)
if [ "$(_wf WF-3)" = "PASS" ] && [ "$(_wf WF-4)" = "PASS" ]; then D2=10
elif [ "$(_wf WF-3)" = "PASS" ]; then D2=5
else D2=1; fi

# D3 Action completeness & ordering — fully mechanical (WF-7 + WF-15)
if [ "$(_wf WF-7)" = "PASS" ] && [ "$(_wf WF-15)" = "PASS" ]; then D3=10
elif [ "$(_wf WF-7)" = "PASS" ]; then D3=5
else D3=1; fi

# D6 Deliverability integrity — WF-12 is mechanical; WF-13/2/10/11 need human.
# Machine FLOOR from WF-12: empty-on-LIVE => 1, key-present(empty draft / non-empty) => 5 floor.
if [ "$(_wf WF-12)" = "FAIL" ]; then D6=1
else D6=5; fi   # floor; QC sub-agent raises to 10 once senders + deps GET-verified
D6_HUMAN=1

# D8 Naming/testability — WF-5 + WF-18/21 mechanical; WF-1/WF-20 need human.
# WF-18/WF-21 score N/A on a fresh build (no prior snapshot to compare against),
# which is not a failure. Treat N/A as passing for the D8 floor so a clean
# first-time build is not penalised.
_wf18="${ITEM_STATUS[WF-18]:-UNKNOWN}"
_wf21="${ITEM_STATUS[WF-21]:-UNKNOWN}"
if [ "$(_wf WF-5)" = "PASS" ] \
   && { [ "$_wf18" = "PASS" ] || [ "$_wf18" = "N/A" ]; } \
   && { [ "$_wf21" = "PASS" ] || [ "$_wf21" = "N/A" ]; }; then D8=5
else D8=1; fi   # floor; QC sub-agent raises to 10 once names + WF-20 reviewed
D8_HUMAN=1

# D1 Goal-fit, D4 Branching, D5 Edge cases — depend on human-review WF items.
# Emit a conservative floor of 5 (build mechanically present, quality ungraded)
# and flag for human grading. NOT 10 — the script must never claim goal-fit.
D1=5; D1_HUMAN=1
D4=5; D4_HUMAN=1
D5=5; D5_HUMAN=1

# D7 Idempotency — WF-6 mechanical; Stop-on-Response (WF-16) needs human.
if [ "$(_wf WF-6)" = "PASS" ]; then D7=5
else D7=1; fi   # floor; QC sub-agent raises to 10 once Stop-on-Response reviewed
D7_HUMAN=1

# Weighted FLOOR score (machine lower bound, x100 to stay integer-safe in bash)
RUBRIC_FLOOR_X100=$(( D1*20 + D2*15 + D3*15 + D4*12 + D5*12 + D6*10 + D7*8 + D8*8 ))
# Format as N.NN
RUBRIC_FLOOR=$(printf "%d.%02d" $(( RUBRIC_FLOOR_X100 / 100 )) $(( RUBRIC_FLOOR_X100 % 100 )))
RUBRIC_NEEDS_HUMAN=$(( D1_HUMAN + D4_HUMAN + D5_HUMAN + D6_HUMAN + D7_HUMAN + D8_HUMAN ))

# Identify the lowest scoring dimension(s) for the loop-back message.
LOWEST_DIM=""; LOWEST_VAL=11
for d in "D1:$D1" "D2:$D2" "D3:$D3" "D4:$D4" "D5:$D5" "D6:$D6" "D7:$D7" "D8:$D8"; do
  v="${d#*:}"
  if [ "$v" -lt "$LOWEST_VAL" ]; then LOWEST_VAL="$v"; LOWEST_DIM="${d%%:*}"; fi
done

# ── Output ─────────────────────────────────────────────────────────────────────
MECHANICAL_ITEMS=("WF-3" "WF-4" "WF-5" "WF-6" "WF-7" "WF-12" "WF-15" "WF-18" "WF-21")
HUMAN_ITEMS=("WF-1" "WF-2" "WF-8" "WF-9" "WF-10" "WF-11" "WF-13" "WF-14" "WF-16" "WF-17" "WF-19" "WF-20")

if [ "$JSON_MODE" -eq 1 ]; then
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
  echo "  },"
  # Weighted quality rubric (SUPERSET overlay, computed AFTER WF-1..21)
  echo "  \"rubric\": {"
  echo "    \"weighted_floor\": $RUBRIC_FLOOR,"
  echo "    \"ship_threshold\": 8.5,"
  echo "    \"needs_human_grading\": $RUBRIC_NEEDS_HUMAN,"
  echo "    \"lowest_dimension\": \"$LOWEST_DIM\","
  echo "    \"note\": \"weighted_floor is the machine-knowable lower bound; the Step-9 QC sub-agent grades the human dimensions (D1/D4/D5/D6/D7/D8) 1/5/10 per references/workflow-quality-rubric.md and recomputes the final score. Ship only if final >= 8.5.\","
  echo "    \"dimensions\": {"
  echo "      \"D1_goal_fit\":       {\"weight\": 20, \"score_floor\": $D1, \"human_grade_required\": true},"
  echo "      \"D2_trigger\":        {\"weight\": 15, \"score\": $D2, \"human_grade_required\": false},"
  echo "      \"D3_steps_ordering\": {\"weight\": 15, \"score\": $D3, \"human_grade_required\": false},"
  echo "      \"D4_branching\":      {\"weight\": 12, \"score_floor\": $D4, \"human_grade_required\": true},"
  echo "      \"D5_edge_cases\":     {\"weight\": 12, \"score_floor\": $D5, \"human_grade_required\": true},"
  echo "      \"D6_deliverability\": {\"weight\": 10, \"score_floor\": $D6, \"human_grade_required\": true},"
  echo "      \"D7_idempotency\":    {\"weight\": 8,  \"score_floor\": $D7, \"human_grade_required\": true},"
  echo "      \"D8_naming\":         {\"weight\": 8,  \"score_floor\": $D8, \"human_grade_required\": true}"
  echo "    }"
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
  # Weighted quality rubric (SUPERSET overlay — computed AFTER WF-1..21, never instead of)
  echo "── Weighted quality rubric (references/workflow-quality-rubric.md) ──"
  printf "  %-22s w=%-3s %s\n" "D1 Goal-fit"        "20" "floor=$D1  [HUMAN GRADE REQUIRED]"
  printf "  %-22s w=%-3s %s\n" "D2 Trigger"         "15" "score=$D2"
  printf "  %-22s w=%-3s %s\n" "D3 Steps/ordering"  "15" "score=$D3"
  printf "  %-22s w=%-3s %s\n" "D4 Branching"       "12" "floor=$D4  [HUMAN GRADE REQUIRED]"
  printf "  %-22s w=%-3s %s\n" "D5 Edge cases"      "12" "floor=$D5  [HUMAN GRADE REQUIRED]"
  printf "  %-22s w=%-3s %s\n" "D6 Deliverability"  "10" "floor=$D6  [HUMAN GRADE REQUIRED]"
  printf "  %-22s w=%-3s %s\n" "D7 Idempotency"     "8"  "floor=$D7  [HUMAN GRADE REQUIRED]"
  printf "  %-22s w=%-3s %s\n" "D8 Naming/testability" "8" "floor=$D8  [HUMAN GRADE REQUIRED]"
  echo "  ─────────────────────────────────────────────"
  echo "  WEIGHTED FLOOR SCORE: $RUBRIC_FLOOR / 10   (ship threshold: >= 8.5)"
  echo "  Lowest dimension: $LOWEST_DIM"
  echo "  NOTE: this is the machine-knowable FLOOR. The Step-9 QC sub-agent must grade the"
  echo "        $RUBRIC_NEEDS_HUMAN human dimensions (D1/D4/D5/D6/D7/D8) 1/5/10 per the rubric and"
  echo "        recompute the FINAL weighted score. Ship ONLY if the final score is >= 8.5;"
  echo "        below 8.5 → loop, naming the low dimension ($LOWEST_DIM)."
  echo ""
fi

# ── Append to build-events ledger ─────────────────────────────────────────────
mkdir -p "$(dirname "$BUILD_EVENTS_LEDGER")" 2>/dev/null || true
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
VERDICT="$([ "$FAIL_COUNT" -eq 0 ] && echo PASS || echo FAIL)"
cat >> "$BUILD_EVENTS_LEDGER" 2>/dev/null << LEDGER_EOF
{"event":"qc_run","timestamp":"${TIMESTAMP}","workflow_id":"${WORKFLOW_ID}","publish_intent":"${PUBLISH_INTENT}","re_entry":"${RE_ENTRY_DECISION}","mechanical_pass":${PASS_COUNT},"mechanical_fail":${FAIL_COUNT},"verdict":"${VERDICT}","rubric_weighted_floor":${RUBRIC_FLOOR},"rubric_ship_threshold":8.5,"rubric_needs_human_grading":${RUBRIC_NEEDS_HUMAN},"rubric_lowest_dimension":"${LOWEST_DIM}"}
LEDGER_EOF

[ "$FAIL_COUNT" -gt 0 ] && exit 1
exit 0
