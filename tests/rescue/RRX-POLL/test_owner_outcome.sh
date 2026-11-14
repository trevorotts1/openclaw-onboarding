#!/usr/bin/env bash
# tests/rescue/RRX-POLL/test_owner_outcome.sh   (RRX-002)
#
# The owner reads the REAL outcome, in words Rescue Rangers wrote, chosen by the
# box only from verified facts.
#   A  an instruction carrying owner_message kind "owner_action", with an agent
#      reply that has no result JSON: the queued final message CARRIES the
#      owner's own wording and does not say "still working"
#   B  no owner_message: the plain "A person on the team now has it" message
#   C  an agent reply CLAIMING repaired with no receiver verification never
#      reaches the word "fixed"
# Loopback stub receiver + stub openclaw. Offline; synthetic ids.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }
. "$HERE/../RR-030/lib-w4-poll-harness.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rrx002-oo-XXXXXX")"
trap 'w4_stop_receiver; rm -rf "$WORK"' EXIT
MSG="$(w4_b64 'Do the simulated thing')"
ORIGIN=',"notification_origin":{"authorized":true,"channel":"telegram","account":"acct-synthetic","target":"999001"}'
claim_json() {  # <instruction_id> <extra-json-members>
  printf '{"status":"instruction","instruction_id":"%s","idempotency_key":"idem-%s","ticket_id":"T-%s","agent_id":"main","session_key":"sess-%s","payload_b64":"%s","mode":"live","lease_seconds":900,"attempt_id":"tok-1","attempt_generation":1%s}' \
    "$1" "$1" "$1" "$1" "$MSG" "${2:-}"
}
# The body the OWNER would read: the queued FINAL notification operation.
final_body() {  # <box root>
  python3 - "$(w4_state "$1")/notifications" <<'PY'
import json, os, sys
d = os.path.join(sys.argv[1], "operations")
bodies = []
try:
    names = sorted(os.listdir(d))
except Exception:
    names = []
for n in names:
    if not n.endswith(".json"):
        continue
    try:
        with open(os.path.join(d, n), encoding="utf-8") as fh:
            item = json.load(fh)
    except Exception:
        continue
    if item.get("stage") == "final":
        bodies.append(item.get("body") or "")
print(bodies[-1] if bodies else "")
PY
}

echo "== RRX-002: the owner reads the real outcome =="

# ---- A: the instruction's own words, for an action only the owner can take ---
B="$WORK/a"; mkdir -p "$B"
w4_start_receiver "$B" 200 "$(claim_json TEST-RRX002-A "$ORIGIN"',"owner_message":{"kind":"owner_action","text":"Open your billing page and add a payment card."}')" \
  || { bad "A receiver stub"; exit 1; }
w4_make_box "$B" "box-synthetic"
w4_run_poll "$B"
BODY="$(final_body "$B")"
case "$BODY" in
  *"Open your billing page and add a payment card."*) ok "A queued final message carries the owner's wording" ;;
  *) bad "A owner wording missing" "$BODY" ;;
esac
case "$BODY" in
  *[Ss]"till working"*) bad "A body still says 'still working'" "$BODY" ;;
  *) ok "A body does not say 'still working'" ;;
esac
w4_stop_receiver

# ---- B: no owner_message -> the plain "a person has it" message --------------
B="$WORK/b"; mkdir -p "$B"
w4_start_receiver "$B" 200 "$(claim_json TEST-RRX002-B "$ORIGIN")" || { bad "B receiver stub"; exit 1; }
w4_make_box "$B" "box-synthetic"
w4_run_poll "$B"
BODY="$(final_body "$B")"
case "$BODY" in
  *"A person on the team now has it"*) ok "B no owner_message -> 'A person on the team now has it'" ;;
  *) bad "B specialist follow-up wording missing" "$BODY" ;;
esac
case "$BODY" in
  *"Good news"*) bad "B claims a repair with no verification" "$BODY" ;;
  *) ok "B does not claim a repair" ;;
esac
w4_stop_receiver

# ---- C: a repaired CLAIM with no verification is never "fixed" ---------------
B="$WORK/c"; mkdir -p "$B"
w4_start_receiver "$B" 200 "$(claim_json TEST-RRX002-C "$ORIGIN")" || { bad "C receiver stub"; exit 1; }
w4_make_box "$B" "box-synthetic"
cat > "$B/bin/openclaw" <<'STUB'
#!/bin/bash
{ printf 'CALL: %s\n' "$(printf '%s' "$*" | tr '\n' ' ')"; } >> "$OPENCLAW_RECORD"
if [ "$1" = "agents" ] && [ "$2" = "list" ]; then printf '%s\n' '[{"id":"main","isDefault":true}]'; exit 0; fi
if [ "$1" = "agent" ]; then printf '%s\n' '{"result":{"payloads":[{"text":"I repaired it.\n```json\n{\"repair_status\":\"repaired\",\"verification_status\":\"unverified\"}\n```"}]}}'; exit 0; fi
printf '{}\n'; exit 0
STUB
chmod +x "$B/bin/openclaw"
w4_run_poll "$B"
BODY="$(final_body "$B")"
if grep -qi 'fixed' <<<"$BODY"; then
  bad "C unverified repair claim produced the word 'fixed'" "$BODY"
else
  ok "C unverified repair claim never produces the word 'fixed'"
fi
w4_stop_receiver

echo; echo "RRX-002 owner outcome: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ]
