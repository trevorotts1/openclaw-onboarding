#!/usr/bin/env bash
# tests/rescue/RR-030/test_mc_route_escalation.sh   (RR plan fix F71)
#
# When Command Center task routing fails, mc-route.sh tells the CEO to say "escalating to the
# operator" but nothing escalated. With MC_ROUTE_RR_ESCALATE=1 it now files ONE Rescue Rangers
# admission from the box (background, bounded), carrying a fixed reason class and an hourly event
# id, never the owner's words. mc-route still exits 1 exactly as before.
#   M1  flag OFF (default): exit 1, ESCALATE_TO_OPERATOR printed, ZERO admission calls
#   M2  flag ON: exit 1 (unchanged) and exactly ONE admission reaches the stub
#   M3  the admission names the box by FLEET_STANDING_BOX_SLUG, says why in plain words, and
#       contains NONE of the owner's words (title or description)
#   M4  the same failure again in the same hour: still ONE admission (hourly fold)
#   M5  a DIFFERENT reason class is a new event: a second admission with a different operation_id
#   M6  flag ON but no FLEET_STANDING_BOX_SLUG: nothing is sent (never the hostname)
#   M7  mc-route returns promptly (the admission never blocks the caller)
#   M8  the three embedded copies are still byte-identical (delegates to the sync test)
# HERMETIC: the admission URL is a loopback stub (rescue_admission.py's default URL is the LIVE
# webhook, so the test refuses to run without the override), proxies point at a dead port, HOME and
# EWS_STATE_DIR are temp dirs, credentials are synthetic.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; REPO="$(cd "$HERE/../../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }
. "$HERE/lib-w4-poll-harness.sh"
MC="$REPO/scripts/mc-route.sh"; [ -f "$MC" ] || { echo "FATAL: $MC missing"; exit 2; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr030-mcroute-XXXXXX")"
trap 'w4_stop_receiver; rm -rf "$WORK"' EXIT
mkdir -p "$WORK/home" "$WORK/state" "$WORK/ews"

# loopback admission stub: accepts everything, logs each body
w4_start_receiver "$WORK" 200 '{"accepted":true,"ticketId":"T-STUB-F71","status":"accepted"}' || { bad "stub did not start"; exit 1; }
STUB_URL="http://127.0.0.1:$W4_PORT/webhook-stub"
case "$STUB_URL" in http://127.0.0.1:*) ok "safety: admission URL is loopback ($STUB_URL)" ;; *) bad "safety: URL not loopback"; exit 1 ;; esac

OWNER_TITLE="Refund the Zebra Quartz order"
OWNER_WORDS="please refund the zebra quartz order for Pat Example and email pat@example.invalid"
RC=0; SECS=0; OUT=""
run_mc() {  # <env assignments...> -- <mc-route args...>
  local envs=() a
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do envs+=("$1"); shift; done; shift
  local t0 t1; t0=$(date +%s)
  OUT="$(env HOME="$WORK/home" PATH="$PATH" HTTP_PROXY=http://127.0.0.1:1 HTTPS_PROXY=http://127.0.0.1:1 NO_PROXY=127.0.0.1,localhost \
        MC_ROUTE_STATE_DIR="$WORK/state" MC_ROUTE_MAX_RETRIES=0 MC_ROUTE_INGEST_URL="http://127.0.0.1:1/api/tasks/ingest" \
        RESCUE_RANGERS_WEBHOOK_URL="$STUB_URL" RESCUE_RANGERS_WEBHOOK_SECRET="synthetic-not-a-credential" EWS_STATE_DIR="$WORK/ews" \
        "${envs[@]}" bash "$MC" "$@" 2>&1)"
  RC=$?; t1=$(date +%s); SECS=$((t1 - t0))
}
wait_claims() {  # <want> -> waits up to 15s for the stub to have >= want bodies
  local i=0; while [ "$(w4_claims "$WORK")" -lt "$1" ] && [ $i -lt 150 ]; do sleep 0.1; i=$((i+1)); done
}

echo "== F71: a failed routing files one Rescue Rangers admission =="
# M1: flag off
run_mc FLEET_STANDING_BOX_SLUG=box-synthetic-f71 -- task "$OWNER_TITLE" "$OWNER_WORDS"
[ "$RC" -eq 1 ] && printf '%s' "$OUT" | grep -q 'ESCALATE_TO_OPERATOR' && ok "M1 flag off: exit 1 + ESCALATE_TO_OPERATOR (unchanged)" || bad "M1 rc=$RC" "$OUT"
sleep 3
[ "$(w4_claims "$WORK")" = "0" ] && ok "M1 flag off: ZERO admission calls" || bad "M1 admission sent with the flag off"

# M2/M3
run_mc FLEET_STANDING_BOX_SLUG=box-synthetic-f71 MC_ROUTE_RR_ESCALATE=1 -- task "$OWNER_TITLE" "$OWNER_WORDS"
[ "$RC" -eq 1 ] && printf '%s' "$OUT" | grep -q 'ESCALATE_TO_OPERATOR' && ok "M2 flag on: mc-route still exits 1 with ESCALATE_TO_OPERATOR" || bad "M2 rc=$RC" "$OUT"
wait_claims 1
[ "$(w4_claims "$WORK")" = "1" ] && ok "M2 exactly ONE admission reached the stub" || bad "M2 admissions=$(w4_claims "$WORK")" "$(cat "$WORK/claims.log" 2>/dev/null | cut -c1-200)"
BODY="$(head -1 "$WORK/claims.log" 2>/dev/null)"
printf '%s' "$BODY" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); assert d["boxName"]=="box-synthetic-f71" and d["source"]=="mc-route" and "could not be reached" in d["problem"] and d["operation_id"]' 2>/dev/null \
  && ok "M3 names the box by slug, source mc-route, plain-words reason, has an operation_id" || bad "M3 body" "$BODY"
if printf '%s' "$BODY" | grep -qiE 'zebra|quartz|pat@example|Pat Example'; then bad "M3 the owner's words leaked into the admission" "$BODY"; else ok "M3 none of the owner's words are in the admission"; fi
OP1="$(printf '%s' "$BODY" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["operation_id"])' 2>/dev/null)"

# M4: same class, same hour -> folded locally, still one
run_mc FLEET_STANDING_BOX_SLUG=box-synthetic-f71 MC_ROUTE_RR_ESCALATE=1 -- task "A different job entirely" "other words"
sleep 3
[ "$(w4_claims "$WORK")" = "1" ] && ok "M4 same failure class in the same hour: still ONE admission (outage cannot page per message)" || bad "M4 admissions=$(w4_claims "$WORK")"

# M5: different class (empty task) -> second event
run_mc FLEET_STANDING_BOX_SLUG=box-synthetic-f71 MC_ROUTE_RR_ESCALATE=1 -- task ""
wait_claims 2
[ "$(w4_claims "$WORK")" = "2" ] && ok "M5 a different reason class is a new event (second admission)" || bad "M5 admissions=$(w4_claims "$WORK")"
OP2="$(sed -n 2p "$WORK/claims.log" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["operation_id"])' 2>/dev/null)"
{ [ -n "$OP1" ] && [ -n "$OP2" ] && [ "$OP1" != "$OP2" ]; } && ok "M5 and it has a different operation_id" || bad "M5 op ids" "$OP1 / $OP2"

# M6: no slug -> nothing
BEFORE="$(w4_claims "$WORK")"
rm -f "$WORK"/state/rr-escalated-*
run_mc MC_ROUTE_RR_ESCALATE=1 FLEET_STANDING_BOX_SLUG= -- task "$OWNER_TITLE" "$OWNER_WORDS"
sleep 3
[ "$RC" -eq 1 ] && [ "$(w4_claims "$WORK")" = "$BEFORE" ] && ok "M6 no FLEET_STANDING_BOX_SLUG: exit 1, nothing sent (never the hostname)" || bad "M6 rc=$RC admissions=$(w4_claims "$WORK") before=$BEFORE"

# M7: prompt return
run_mc FLEET_STANDING_BOX_SLUG=box-synthetic-f71 MC_ROUTE_RR_ESCALATE=1 -- task "Quick" "check"
[ "$SECS" -le 20 ] && ok "M7 mc-route returned in ${SECS}s (admission is backgrounded)" || bad "M7 took ${SECS}s"

# M8: byte-identity of the three copies
if bash "$REPO/tests/unit/mc-route-heredoc-sync.test.sh" >/dev/null 2>&1; then ok "M8 the three embedded copies of mc-route.sh are byte-identical"; else bad "M8 heredoc sync test fails"; fi

echo; echo "RR-030 F71 mc-route escalation: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ]
