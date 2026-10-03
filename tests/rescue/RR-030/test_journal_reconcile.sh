#!/usr/bin/env bash
# tests/rescue/RR-030/test_journal_reconcile.sh   (RR plan fix F62)
#
# A poll killed mid-turn used to re-run the same instruction blind. Now an instruction whose
# journal already holds an effect_started / effect_executed row for the SAME instruction_id (and no
# done record carries that operation) is NOT run again: ack failed, fail_reason interrupted_prior_attempt.
#   J1  seeded effect_started row for TEST-RR07-JR -> ZERO agent turns, a failed ack with the new reason
#   J2  the same holds for an effect_executed row
#   J3  control: a different instruction_id (row for another instruction) DOES run the agent
#   J4  control: a row that already has a done record (outcome recorded) does NOT block
#   J5  GC: an effect_started row older than 30 days moves to reconcile/ (never deleted); a fresh one stays
# Loopback stub receiver + stub openclaw that records every call. Offline; synthetic ids.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; REPO="$(cd "$HERE/../../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }
. "$HERE/lib-w4-poll-harness.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr030-jr-XXXXXX")"
trap 'w4_stop_receiver; rm -rf "$WORK"' EXIT
MSG="$(w4_b64 'Do the simulated thing')"
claim_json() {  # <instruction_id>
  printf '{"status":"instruction","instruction_id":"%s","idempotency_key":"idem-%s","ticket_id":"T-%s","agent_id":"main","session_key":"sess-%s","payload_b64":"%s","mode":"live","lease_seconds":900,"attempt_id":"tok-1","attempt_generation":1}' "$1" "$1" "$1" "$1" "$MSG"
}
OPFOR() { printf 'op_%s' "$(printf '%s' "rr-delivery|idem-$1|tok-1|1" | shasum -a 256 | cut -d' ' -f1)"; }
seed_row() {  # <root> <instruction_id> <phase> [op-override]
  local st; st="$(w4_state "$1")"; mkdir -p "$st/journal" "$st/done"
  local op="${4:-$(OPFOR "$2")}"
  printf '{"operation_id":"%s","phase":"%s","instruction_id":"%s","idempotency_key":"idem-%s","attempt_id":"tok-1","attempt_generation":"1","box_slug":"box-synthetic","receiver_version":"1.7.2","updated_at":"2026-09-17T00:00:00Z","extra":{}}\n' "$op" "$3" "$2" "$2" > "$st/journal/$op"
  echo "$op"
}
new_case() {  # <name> <claim-json>  -> sets B
  B="$WORK/$1"; mkdir -p "$B"; w4_stop_receiver
  w4_start_receiver "$B" 200 "$2" || { bad "$1 stub"; return 1; }
  w4_make_box "$B" "box-synthetic"
}
last_ack() { grep '"action":"ack"' "$B/claims.log" | tail -1; }

echo "== F62: an interrupted instruction is not run again =="
# control FIRST: the recorder can fire (no seeded row)
new_case ctl "$(claim_json TEST-RR07-CTL)"; w4_run_poll "$B"
[ "$(w4_agent_calls "$B/agent-record.txt")" -ge 1 ] && ok "control: clean instruction runs the agent ($(w4_agent_calls "$B/agent-record.txt") call)" || bad "control: no agent call, every zero below is vacuous"

new_case j1 "$(claim_json TEST-RR07-JR)"; seed_row "$B" TEST-RR07-JR effect_started >/dev/null; w4_run_poll "$B"
[ "$(w4_agent_calls "$B/agent-record.txt")" = "0" ] && ok "J1 effect_started row: ZERO agent turns" || bad "J1 agent ran" "$(grep '^CALL' "$B/agent-record.txt")"
A="$(last_ack)"
printf '%s' "$A" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); assert d["verdict"]=="failed" and d["fail_reason"]=="interrupted_prior_attempt" and d["instruction_id"]=="TEST-RR07-JR"' 2>/dev/null \
  && ok "J1 failed ack with fail_reason interrupted_prior_attempt for TEST-RR07-JR" || bad "J1 ack" "$A"
grep -q 'interrupted-prior-attempt instruction=TEST-RR07-JR' "$(w4_state "$B")/rescue-poll.log" && ok "J1 logged interrupted-prior-attempt" || bad "J1 log"

new_case j2 "$(claim_json TEST-RR07-JR2)"; seed_row "$B" TEST-RR07-JR2 effect_executed >/dev/null; w4_run_poll "$B"
{ [ "$(w4_agent_calls "$B/agent-record.txt")" = "0" ] && last_ack | grep -q interrupted_prior_attempt; } && ok "J2 effect_executed row: zero turns + interrupted ack" || bad "J2" "$(last_ack)"

new_case j3 "$(claim_json TEST-RR07-OTHER)"; seed_row "$B" TEST-RR07-UNRELATED effect_started >/dev/null; w4_run_poll "$B"
[ "$(w4_agent_calls "$B/agent-record.txt")" -ge 1 ] && ok "J3 control: a row for a DIFFERENT instruction does not block (exact match only)" || bad "J3 blocked wrongly"

# J4: row exists but the outcome was recorded (a done record carries the operation id) -> not "interrupted"
new_case j4 "$(claim_json TEST-RR07-DONE)"; OP="$(seed_row "$B" TEST-RR07-DONE effect_executed)"
printf '{"verdict":"delivered","exit_code":0,"reply_chars":5,"fail_reason":null,"elapsed_s":1,"operation_id":"%s","instruction_id":"TEST-RR07-DONE"}\n' "$OP" > "$(w4_state "$B")/done/legacy-name"
w4_run_poll "$B"
! grep -q interrupted_prior_attempt "$B/claims.log" 2>/dev/null && ok "J4 control: a row whose outcome is recorded is not treated as interrupted" || bad "J4 blocked wrongly"

# J5: GC
B="$WORK/j5"; mkdir -p "$B"; w4_make_box "$B"; ST="$(w4_state "$B")"; mkdir -p "$ST/journal"
OLD="$(seed_row "$B" TEST-RR07-OLD effect_started op_old_orphan)"; NEW="$(seed_row "$B" TEST-RR07-NEW effect_started op_new_orphan)"
touch -t 202001010000 "$ST/journal/op_old_orphan"
w4_stop_receiver; w4_start_receiver "$B" 200 '{"status":"empty"}'; w4_make_box "$B"; w4_run_poll "$B"
{ [ ! -f "$ST/journal/op_old_orphan" ] && [ -f "$ST/reconcile/journal-op_old_orphan" ]; } && ok "J5 30d+ effect_started row moved to reconcile/ (not deleted)" || bad "J5 old row" "$(ls "$ST/journal" "$ST/reconcile" 2>&1)"
[ -f "$ST/journal/op_new_orphan" ] && ok "J5 control: a fresh effect_started row stays in the journal" || bad "J5 fresh row removed"

echo; echo "RR-030 F62 journal reconcile: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ]
