#!/usr/bin/env bash
# RR-029 — result-v3 receiver boundary.
#
# Runs the shipped result builder, not a reimplementation. It proves that a
# nonempty prose reply becomes a conservative result, a partial result remains
# partial, an unsupported repaired claim is downgraded, and notification prose
# is never elevated to delivery without a receipt.

set -u
PASS=0
FAIL=0
ok() { PASS=$((PASS + 1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL $1 ${2:-}"; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
POLL="$REPO/65-rescue-receiver/rescue-poll.sh"
FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT

extract_fn() {
  # The result builder embeds Python dictionaries, whose closing braces are
  # column-zero too. Stop at the next section divider rather than treating a
  # Python brace as the shell function's closing brace.
  awk -v fn="$1" '
    $0 == fn "() {" { on=1; seen=1 }
    on && seen > 1 && /^# ---/ { exit }
    on { print; seen++ }
    END { if (!on) exit 1 }
  ' "$POLL"
}

{
  extract_fn _json_str
  extract_fn _rr_result_prompt
  extract_fn _rr_build_result
} > "$FIX/functions.sh"

bash -n "$FIX/functions.sh" && ok "extracted receiver functions parse" || bad "extracted receiver functions parse"

run_case() {
  local name="$1" reply="$2"
  cat > "$FIX/run.sh" <<'EOF'
set -u
source "$RR029_FUNCTIONS"
_TMP="$RR029_TMP"
mkdir -p "$_TMP"
INSTRUCTION_ID="instruction-1"
TICKET_ID="ticket-1"
INCIDENT_ID="incident-1"
ATTEMPT_ID="attempt-1"
ATTEMPT_REF="attempt-1"
ATTEMPT_GENERATION="2"
_op_id="op-1"
RR_RUNTIME_ID="runtime-1"
RR_BOX_SLUG="box-1"
_rr_build_result "$RR029_REPLY" 0 42 "safe reply excerpt"
cat "$RR_RESULT_JSON"
EOF
  RR029_FUNCTIONS="$FIX/functions.sh" RR029_TMP="$FIX/tmp-$name" RR029_REPLY="$reply" \
    bash "$FIX/run.sh"
}

fallback="$(run_case fallback 'The service answered, but I need more evidence.')"
python3 - "$fallback" <<'PY' >/dev/null 2>&1
import json, sys
d=json.loads(sys.argv[1])
assert d['repair_status'] == 'not_repaired'
assert d['verification_status'] == 'unverified'
assert d['remaining_blocker']['reason'] == 'structured_result_missing'
assert d['transport_receipt']['receipt_state'] == 'receipt_pending'
assert d['transport_receipt']['operation_id'] == 'op-1'
assert d['transport_receipt']['attempt_generation'] == 2
assert d['end_user_notification']['initial']['status'] == 'unavailable'
assert d['end_user_notification']['final']['status'] == 'unavailable'
assert len(d['outcome_digest']) == 64
PY
if [ "$?" -eq 0 ]; then ok "nonempty prose becomes unverified, not repaired"; else bad "fallback result" "$fallback"; fi

partial_reply=$'Work partly completed.\n```json\n{"repair_status":"partial","verification_status":"pending","evidence_refs":["pm2:restart:123"],"remaining_blocker":{"reason":"task_dispatch_still_blocked","owner":"operator","next_action":"inspect queue"},"end_user_notification":{"initial":{"status":"attempted","channel":"telegram"},"final":{"status":"delivered","channel":"telegram","message_receipt":"message-42"}}}\n```'
partial="$(run_case partial "$partial_reply")"
python3 - "$partial" <<'PY' >/dev/null 2>&1
import json, sys
d=json.loads(sys.argv[1])
assert d['repair_status'] == 'partial'
assert d['verification_status'] == 'pending'
assert d['remaining_blocker']['reason'] == 'task_dispatch_still_blocked'
assert 'pm2:restart:123' in d['evidence_refs']
assert d['end_user_notification']['initial']['status'] == 'attempted'
assert d['end_user_notification']['initial']['channel'] == 'telegram'
assert d['end_user_notification']['final'] == {'status':'unconfirmed', 'channel':'telegram', 'message_receipt':'message-42', 'failure_reason':'agent_reported_receipt_unverified'}
PY
if [ "$?" -eq 0 ]; then ok "partial repair and notification receipt are preserved"; else bad "partial result" "$partial"; fi

unverified_repaired=$'```json\n{"repair_status":"repaired","verification_status":"unverified","evidence_refs":["service:200"]}\n```'
downgraded="$(run_case repaired "$unverified_repaired")"
python3 - "$downgraded" <<'PY' >/dev/null 2>&1
import json, sys
d=json.loads(sys.argv[1])
assert d['repair_status'] == 'partial'
assert d['verification_status'] == 'unverified'
assert d['remaining_blocker']['reason'] == 'repaired_claim_missing_verification'
assert 'fix_card' not in d
PY
if [ "$?" -eq 0 ]; then ok "unverified repaired claim is downgraded to partial"; else bad "repaired downgrade" "$downgraded"; fi

verified_repaired=$'```json\n{"repair_status":"repaired","verification_status":"verified","evidence_refs":["dispatch:execution-7"],"fix_card":{"card_id":"pm2-restart","card_version":"1","scope_authorized":true},"acceptance_check":{"check_id":"task-dispatch","passed":true,"evidence_ref":"dispatch:execution-7"}}\n```'
repaired="$(run_case verified-repaired "$verified_repaired")"
python3 - "$repaired" <<'PY' >/dev/null 2>&1
import json, sys
d=json.loads(sys.argv[1])
assert d['repair_status'] == 'repaired'
assert d['acceptance_check'] == {'incident_id':'incident-1', 'attempt_id':'attempt-1', 'check_id':'task-dispatch', 'passed':True, 'evidence_ref':'dispatch:execution-7'}
PY
if [ "$?" -eq 0 ]; then ok "verified repair carries receiver-bound acceptance proof"; else bad "verified repaired result" "$repaired"; fi

prompt="$(source "$FIX/functions.sh"; _rr_result_prompt 'original coaching')"
if [[ "$prompt" == *'received/applying'* && "$prompt" == *'message_receipt'* && "$prompt" == *'agent-reported receipt remains unconfirmed'* ]]; then
  ok "prompt requests staged, receipt-backed communication"
else
  bad "prompt lacks notification honesty requirements" "$prompt"
fi

echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
