#!/usr/bin/env bash
# tests/rescue/RR-030/test_claim_unauthorized.sh   (RR plan fix F61)
#
# A box with a wrong slug or token used to poll forever, get 401, and log nothing. Now:
#   U1  a 401 claim writes state/rr-receiver/claim-unauthorized.json (names only) and ONE log line
#   U2  the token never appears in the json, the log, or stdout/stderr
#   U3  a second run within the hour: count goes up, NO new log line
#   U4  rr-readiness.sh reports claim_unauthorized (human line + json flag)
#   U5  rr-readiness.sh reports slug_mismatch when FLEET_STANDING_BOX_SLUG differs from RR_BOX_SLUG
#   U6  control: an accepted claim ("empty") clears the file, readiness reports no flag
#   U7  control: a 2xx body {"status":"unauthorized"} is also caught
# Drives the real scripts against a loopback stub. Offline.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; REPO="$(cd "$HERE/../../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }
. "$HERE/lib-w4-poll-harness.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr030-unauth-XXXXXX")"
trap 'w4_stop_receiver; rm -rf "$WORK"' EXIT
TOKEN="synthetic-token-not-a-credential"

echo "== F61: unauthorized claim leaves a trace =="
B="$WORK/b1"; mkdir -p "$B"
w4_start_receiver "$B" 401 '{"status":"unauthorized"}' || { bad "receiver stub did not start"; exit 1; }
w4_make_box "$B" "box-wrong-slug"
w4_run_poll "$B"; ST="$(w4_state "$B")"
[ "$W4_RC" -eq 0 ] && ok "U0 poll exits 0 (cron contract unchanged)" || bad "U0 rc=$W4_RC"
[ "$(w4_claims "$B")" -ge 1 ] && ok "control: the claim reached the stub" || bad "control: no claim reached the stub"
[ -f "$ST/claim-unauthorized.json" ] && ok "U1 claim-unauthorized.json written" || bad "U1 no claim-unauthorized.json"
J="$(cat "$ST/claim-unauthorized.json" 2>/dev/null)"
printf '%s' "$J" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["box_slug"]=="box-wrong-slug" and d["http"]=="401" and d["count"]==1 and d["class"]=="claim_unauthorized"' 2>/dev/null \
  && ok "U1 json names slug, http 401, count 1" || bad "U1 json content" "$J"
[ "$(grep -c 'claim-unauthorized slug=box-wrong-slug' "$ST/rescue-poll.log" 2>/dev/null)" = "1" ] && ok "U1 exactly one log line" || bad "U1 log lines" "$(cat "$ST/rescue-poll.log" 2>/dev/null)"
if grep -rqF "$TOKEN" "$ST" "$B/out" "$B/err" 2>/dev/null; then bad "U2 token leaked into state/log/output"; else ok "U2 token appears nowhere in state, log, stdout or stderr"; fi
w4_run_poll "$B"
[ "$(grep -c 'claim-unauthorized slug=' "$ST/rescue-poll.log" 2>/dev/null)" = "1" ] && ok "U3 second run within the hour: still one log line" || bad "U3 log lines" "$(grep -c 'claim-unauthorized' "$ST/rescue-poll.log")"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["count"]==2' "$ST/claim-unauthorized.json" 2>/dev/null && ok "U3 count advanced to 2" || bad "U3 count" "$(cat "$ST/claim-unauthorized.json")"
# age the hourly marker -> the next run logs again (proves the throttle is the only thing holding it back)
touch -t 202001010000 "$ST/claim-unauthorized.logged"; w4_run_poll "$B"
[ "$(grep -c 'claim-unauthorized slug=' "$ST/rescue-poll.log" 2>/dev/null)" = "2" ] && ok "U3 control: after the hour the line is logged again" || bad "U3 control" "$(grep -c 'claim-unauthorized' "$ST/rescue-poll.log")"

# readiness (uses the same box tree; descriptor + engine copied alongside)
cp "$REPO/65-rescue-receiver/rr-readiness.sh" "$B/.openclaw/skills/65-rescue-receiver/"
cp "$REPO/shared-utils/rr-readiness.sh" "$REPO/shared-utils/oc-env-descriptor.sh" "$B/.openclaw/skills/shared-utils/"
run_ready() {  # <root> [extra env assignments...] -- args
  local root="$1"; shift
  env HOME="$root" OC_CONFIG_ROOT="$root/.openclaw" PATH="$root/bin:$PATH" "$@" \
    bash "$root/.openclaw/skills/65-rescue-receiver/rr-readiness.sh" 2>&1
}
OUT="$(run_ready "$B")"
printf '%s\n' "$OUT" | grep -q 'FLAG claim_unauthorized http=401' && ok "U4 readiness human report: claim_unauthorized http=401" || bad "U4 human" "$OUT"
JOUT="$(env HOME="$B" OC_CONFIG_ROOT="$B/.openclaw" PATH="$B/bin:$PATH" bash "$B/.openclaw/skills/65-rescue-receiver/rr-readiness.sh" --json 2>/dev/null)"
printf '%s' "$JOUT" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); assert d["flags"]["claim_unauthorized"] is True and d["flags"]["slug_mismatch"] is False' 2>/dev/null \
  && ok "U4 readiness json: one valid object, flags.claim_unauthorized true" || bad "U4 json" "$JOUT"
printf '%s' "$JOUT$OUT" | grep -qF "$TOKEN" && bad "U4 readiness leaked the token" || ok "U4 readiness never prints the token"
OUT="$(run_ready "$B" FLEET_STANDING_BOX_SLUG=box-canonical-slug)"
printf '%s\n' "$OUT" | grep -q 'FLAG slug_mismatch enrolled=box-wrong-slug canonical=box-canonical-slug' && ok "U5 slug_mismatch reported (enrolled vs canonical)" || bad "U5" "$OUT"
OUT="$(run_ready "$B" FLEET_STANDING_BOX_SLUG=box-wrong-slug)"
printf '%s\n' "$OUT" | grep -q 'slug_mismatch' && bad "U5 control: equal slugs must not flag" "$OUT" || ok "U5 control: equal slugs raise no slug_mismatch"

# U6: the receiver accepts again -> record cleared
w4_stop_receiver; rm -f "$B/claims.log"
w4_start_receiver "$B" 200 '{"status":"empty"}' || bad "receiver restart"
w4_make_box "$B" "box-wrong-slug"; w4_run_poll "$B"
[ ! -f "$ST/claim-unauthorized.json" ] && ok "U6 an accepted claim clears claim-unauthorized.json" || bad "U6 file still present"
OUT="$(run_ready "$B")"; printf '%s\n' "$OUT" | grep -q 'claim_unauthorized' && bad "U6 readiness still flags" "$OUT" || ok "U6 readiness no longer flags"

# U7: 200 + {"status":"unauthorized"}
w4_stop_receiver; B2="$WORK/b2"; mkdir -p "$B2"
w4_start_receiver "$B2" 200 '{"status":"unauthorized"}'; w4_make_box "$B2" "box-body-unauth"; w4_run_poll "$B2"
[ -f "$(w4_state "$B2")/claim-unauthorized.json" ] && ok "U7 a 2xx body status=unauthorized is also recorded" || bad "U7"

echo; echo "RR-030 F61 claim-unauthorized: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ]
