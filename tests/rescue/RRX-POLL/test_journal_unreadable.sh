#!/usr/bin/env bash
# tests/rescue/RRX-POLL/test_journal_unreadable.sh   (RRX-010)
#
# One corrupt journal file must never keep the box dark for ever, and it must
# never read as "no earlier attempt".
#   U1  an unreadable journal row makes the answer UNDETERMINED: the poll still
#       CLAIMS the instruction and sends NO acknowledgement, and it says so
#   U2  the unreadable journal file is MOVED to <state>/reconcile/journal-op_x
#       (never deleted, never a done file) with one log line per file
#   U3  a second run against the same stub adds NO second journal-undetermined
#       line: the journal is readable again
# Loopback stub receiver + stub openclaw. Offline; synthetic ids.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }
. "$HERE/../RR-030/lib-w4-poll-harness.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rrx010-ju-XXXXXX")"
trap 'w4_stop_receiver; rm -rf "$WORK"' EXIT
MSG="$(w4_b64 'Do the simulated thing')"
claim_json() {  # <instruction_id>
  printf '{"status":"instruction","instruction_id":"%s","idempotency_key":"idem-%s","ticket_id":"T-%s","agent_id":"main","session_key":"sess-%s","payload_b64":"%s","mode":"live","lease_seconds":900,"attempt_id":"tok-1","attempt_generation":1}' "$1" "$1" "$1" "$1" "$MSG"
}
count_in() {  # <pattern> <file>
  local n; n=$(grep -c -- "$1" "$2" 2>/dev/null)
  case "$n" in ''|*[!0-9]*) n=0 ;; esac
  echo "$n"
}

echo "== RRX-010: an unreadable journal never reads as 'no earlier attempt' =="

B="$WORK/ju"; mkdir -p "$B"
w4_start_receiver "$B" 200 "$(claim_json TEST-RRX010-UNREAD)" || { bad "receiver stub"; exit 1; }
w4_make_box "$B" "box-synthetic"
ST="$(w4_state "$B")"
mkdir -p "$ST/journal" "$ST/done"
printf '{broken' > "$ST/journal/op_x"

w4_run_poll "$B"
LOG="$ST/rescue-poll.log"

# U1: claimed, not acknowledged, and the poll says why.
[ "$(count_in '"action":"claim"' "$B/claims.log")" -ge 1 ] \
  && ok "U1 claimed the instruction" || bad "U1 no claim" "$(cat "$B/claims.log" 2>/dev/null)"
[ "$(count_in '"action":"ack"' "$B/claims.log")" -eq 0 ] \
  && ok "U1 sent NO acknowledgement for an undetermined turn" || bad "U1 acked anyway" "$(grep '"action":"ack"' "$B/claims.log" 2>/dev/null)"
[ "$(count_in 'journal-undetermined' "$LOG")" -ge 1 ] \
  && ok "U1 logged journal-undetermined" || bad "U1 no journal-undetermined log line" "$(cat "$LOG" 2>/dev/null)"
[ "$(w4_agent_calls "$B/agent-record.txt")" = "0" ] \
  && ok "U1 control: no agent turn ran" || bad "U1 agent ran on an unreadable journal"

# U2: the corrupt row is moved aside, never deleted.
[ -f "$ST/reconcile/journal-op_x" ] \
  && ok "U2 corrupt journal row moved to reconcile/journal-op_x" || bad "U2 row not quarantined" "$(ls "$ST/journal" "$ST/reconcile" 2>&1)"
[ ! -f "$ST/journal/op_x" ] \
  && ok "U2 corrupt journal row is no longer in the journal" || bad "U2 row still in the journal"
[ "$(count_in 'journal-quarantined file=op_x' "$LOG")" -ge 1 ] \
  && ok "U2 logged journal-quarantined file=op_x" || bad "U2 no quarantine log line"

# U3: the next run reads a readable journal and stays quiet about it.
BEFORE="$(count_in 'journal-undetermined' "$LOG")"
w4_run_poll "$B"
AFTER="$(count_in 'journal-undetermined' "$LOG")"
[ "$BEFORE" = "$AFTER" ] \
  && ok "U3 second run adds no second journal-undetermined line ($AFTER)" || bad "U3 undetermined repeated" "before=$BEFORE after=$AFTER"

echo; echo "RRX-010 unreadable journal: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ]
