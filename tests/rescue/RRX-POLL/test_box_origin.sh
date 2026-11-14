#!/usr/bin/env bash
# tests/rescue/RRX-POLL/test_box_origin.sh   (RRX-001b)
#
# Deliver into the conversation the case came from, and leave a record the agent
# can read.
#   1  the box has an origin record for the ticket, the claim sends no origin and
#      says notify_authorized true: the owner message goes to the recorded
#      telegram account/target, and case-outcomes/<ticket>.json says
#      owner_notified true
#   2  no origin record and no server origin: nothing is sent, owner_notified
#      false, and no case-outcome file escapes the state folder
#   3  a ticket id containing "/" writes no file outside the state folder
#   4  the same claim WITHOUT notify_authorized (origin record still present)
#      sends nothing and records owner_notified false
# Loopback stub receiver + stub openclaw. Offline; synthetic ids.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }
. "$HERE/../RR-030/lib-w4-poll-harness.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rrx001b-box-XXXXXX")"
trap 'w4_stop_receiver; rm -rf "$WORK"' EXIT
MSG="$(w4_b64 'Do the simulated thing')"
OACCT="acct-synthetic"; OTARGET="999001"
case_claim() {  # <instruction_id> <ticket_id> <extra-json-members>
  printf '{"status":"instruction","instruction_id":"%s","idempotency_key":"idem-%s","ticket_id":"%s","agent_id":"main","session_key":"sess-%s","payload_b64":"%s","mode":"live","lease_seconds":900,"attempt_id":"tok-1","attempt_generation":1%s}' \
    "$1" "$1" "$2" "$1" "$MSG" "${3:-}"
}
origin_record() {  # <box root> <ticket>  -- the file rr_escalate.py writes
  local d="$1/.openclaw/state/rr-escalate/origins"
  mkdir -p "$d"
  printf '{"origin":{"channel":"telegram","account":"%s","target":"%s"}}\n' "$OACCT" "$OTARGET" > "$d/$2.json"
}
outcome_doc() {  # <box root> <ticket> -> JSON line or empty
  python3 -I - "$1/.openclaw/state/rr-receiver/case-outcomes/$2.json" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        d = json.load(fh)
    print(json.dumps(d, sort_keys=True))
except Exception:
    print("")
PY
}
outcome_field() {  # <box root> <ticket> <field>
  python3 -I - "$1/.openclaw/state/rr-receiver/case-outcomes/$2.json" "$3" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        d = json.load(fh)
    print(d.get(sys.argv[2]))
except Exception:
    print("")
PY
}
sent_count() { local n; n=$(grep -c '^CALL: message send ' "$1/agent-record.txt" 2>/dev/null); case "$n" in ''|*[!0-9]*) n=0;; esac; echo "$n"; }

echo "== RRX-001b: the box's own conversation record =="

# ---- 1: box origin, notify_authorized true -> delivered to that conversation --
B="$WORK/one"; mkdir -p "$B"
w4_start_receiver "$B" 200 "$(case_claim TEST-RRX001B-1 RR-000777 ',"notify_authorized":true')" \
  || { bad "1 receiver stub"; exit 1; }
w4_make_box "$B" "box-synthetic"
origin_record "$B" RR-000777
w4_run_poll "$B"
if grep -qF 'CALL: message send --json --channel telegram --account acct-synthetic --target 999001' "$B/agent-record.txt" 2>/dev/null; then
  ok "1 owner message sent to the recorded telegram account/target"
else
  bad "1 message send not called with the recorded origin" "$(cat "$B/agent-record.txt" 2>/dev/null)"
fi
if [ -n "$(outcome_doc "$B" RR-000777)" ]; then
  ok "1 case-outcomes/RR-000777.json exists and parses"
else
  bad "1 case-outcomes/RR-000777.json missing or unparsable"
fi
if [ "$(outcome_field "$B" RR-000777 owner_notified)" = "True" ]; then
  ok "1 owner_notified is true"
else
  bad "1 owner_notified is not true" "$(outcome_field "$B" RR-000777 owner_notified)"
fi
w4_stop_receiver

# ---- 2: no origin anywhere -> nothing sent, owner_notified false --------------
B="$WORK/two"; mkdir -p "$B"
w4_start_receiver "$B" 200 "$(case_claim TEST-RRX001B-2 RR-000778 ',"notify_authorized":true')" \
  || { bad "2 receiver stub"; exit 1; }
w4_make_box "$B" "box-synthetic"
w4_run_poll "$B"
if [ "$(sent_count "$B")" = "0" ]; then
  ok "2 no message send without any origin"
else
  bad "2 a message was sent with no origin"
fi
if [ "$(outcome_field "$B" RR-000778 owner_notified)" = "False" ]; then
  ok "2 owner_notified is false"
else
  bad "2 owner_notified is not false" "$(outcome_field "$B" RR-000778 owner_notified)"
fi
w4_stop_receiver

# ---- 3: a ticket id containing "/" writes no file outside the state folder ----
B="$WORK/three"; mkdir -p "$B"
w4_start_receiver "$B" 200 "$(case_claim TEST-RRX001B-3 'RR-9/../../escape-RR-000779' ',"notify_authorized":true')" \
  || { bad "3 receiver stub"; exit 1; }
w4_make_box "$B" "box-synthetic"
w4_run_poll "$B"
ESCAPED=$(python3 -I - "$B/.openclaw" <<'PY'
import os, sys
root = sys.argv[1]
state = os.path.join(root, "state", "rr-receiver")
hits = []
for base, _dirs, files in os.walk(root):
    for f in files:
        if "escape" in f:
            hits.append(os.path.join(base, f))
        if os.path.basename(base) == "case-outcomes":
            hits.extend(os.path.join(base, f) for f in files)
print("\n".join(hits))
PY
)
if [ -z "$ESCAPED" ]; then
  ok "3 a ticket id with / writes no file outside the state folder"
else
  bad "3 a ticket id with / escaped the state folder" "$ESCAPED"
fi
w4_stop_receiver

# ---- 4: origin record present, notify_authorized absent -> nothing sent ------
B="$WORK/four"; mkdir -p "$B"
w4_start_receiver "$B" 200 "$(case_claim TEST-RRX001B-4 RR-000780 '')" \
  || { bad "4 receiver stub"; exit 1; }
w4_make_box "$B" "box-synthetic"
origin_record "$B" RR-000780
w4_run_poll "$B"
if [ "$(sent_count "$B")" = "0" ]; then
  ok "4 no message send when notify_authorized is absent"
else
  bad "4 a message was sent without notify_authorized"
fi
if [ "$(outcome_field "$B" RR-000780 owner_notified)" = "False" ]; then
  ok "4 owner_notified is false without notify_authorized"
else
  bad "4 owner_notified is not false without notify_authorized" "$(outcome_field "$B" RR-000780 owner_notified)"
fi
w4_stop_receiver

echo; echo "RRX-001b box origin: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ]
