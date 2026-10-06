#!/usr/bin/env bash
# tests/rescue/RR-030/test_rr03_local_flag.sh   (RR plan fix F66)
#
# RR-03 fixes for "gateway down" would be delivered THROUGH the gateway: `openclaw agent` runs via
# the Gateway unless --local (embedded agent) is passed. An instruction_id starting "rr03-" must
# add --local; any other instruction must not.
#   L1  rr03-* instruction, supervised path   -> argv contains --local
#   L2  rr02-* instruction, supervised path   -> argv has no --local
#   L3  rr03-* instruction, degraded path (no supervisor on the box) -> --local present
#   L4  rr02-* instruction, degraded path     -> no --local
#   L5  "xrr03-..." (prefix must be at the start) -> no --local
# The stub openclaw records its argv. Offline: loopback receiver only.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; REPO="$(cd "$HERE/../../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }
. "$HERE/lib-w4-poll-harness.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr030-local-XXXXXX")"
trap 'w4_stop_receiver; rm -rf "$WORK"' EXIT
MSG="$(w4_b64 'Restart the gateway process')"
claim_json() {
  printf '{"status":"instruction","instruction_id":"%s","idempotency_key":"idem-%s","ticket_id":"T-%s","agent_id":"main","session_key":"sess-%s","payload_b64":"%s","mode":"live","lease_seconds":900,"attempt_id":"tok-1","attempt_generation":1}' "$1" "$1" "$1" "$1" "$MSG"
}
run_case() {  # <name> <instruction_id> [nosupervisor]
  B="$WORK/$1"; mkdir -p "$B"; w4_stop_receiver
  w4_start_receiver "$B" 200 "$(claim_json "$2")" || { bad "$1 stub"; return 1; }
  w4_make_box "$B" "box-synthetic"
  [ "${3:-}" = "nosupervisor" ] && rm -f "$B/.openclaw/skills/shared-utils/rescue-supervise.py"
  w4_run_poll "$B"
  AGENT_LINE="$(grep '^CALL: agent ' "$B/agent-record.txt" 2>/dev/null | head -1)"
}
echo "== F66: rr03- instructions run the agent with --local =="
run_case a rr03-gw-restart-1
[ -n "$AGENT_LINE" ] && ok "control: the agent turn was recorded" || bad "control: no agent call recorded"
case " $AGENT_LINE " in *" --local "*) ok "L1 rr03- (supervised): --local present" ;; *) bad "L1" "$AGENT_LINE" ;; esac
run_case b rr02-coach-1
[ -n "$AGENT_LINE" ] || bad "L2 control: no agent call"
case " $AGENT_LINE " in *" --local "*) bad "L2 rr02- got --local" "$AGENT_LINE" ;; *) ok "L2 rr02- (supervised): no --local" ;; esac
# L3/L4: the degraded branch of _rr_supervised_agent (no supervisor on the box). A full run never
# reaches it today: _try_lock fails closed first when rescue-supervise.py is absent. So drive the
# SHIPPED function itself (extracted by name) with _RR_SUPERVISE empty and a recording openclaw.
extract_fn() {
  local sl el
  sl="$(grep -n "^$1()" "$W4_POLL" | head -1 | cut -d: -f1)"; [ -n "$sl" ] || return 1
  el="$(awk -v s="$sl" 'NR>=s && /^}/ {print NR; exit}' "$W4_POLL")"; sed -n "${sl},${el}p" "$W4_POLL"
}
degraded_argv() {  # <instruction_id> -> the recorded openclaw argv line
  local d="$WORK/deg-$1"; mkdir -p "$d/tmp" "$d/bin"
  cat > "$d/bin/openclaw" <<'STUB'
#!/bin/bash
printf 'CALL: %s\n' "$(printf '%s' "$*" | tr '\n' ' ')" >> "$DEG_RECORD"
printf '{"result":{"payloads":[{"text":"ok"}]}}\n'
STUB
  chmod +x "$d/bin/openclaw"
  { extract_fn _rr_supervised_agent
    echo '_rr_persist_outcome() { :; }'
    echo 'rescue_env_scrub() { "$@"; }'
  } > "$d/fn.sh"
  DEG_RECORD="$d/record" INSTRUCTION_ID="$1" _TMP="$d/tmp" _OC_BIN="$d/bin/openclaw" _RR_SUPERVISE="" \
    SESSION_KEY="sess-deg" MSG="do the thing" bash -c '. "$0"; _rr_supervised_agent main 60000' "$d/fn.sh" >/dev/null 2>&1
  grep '^CALL: agent ' "$d/record" 2>/dev/null | head -1
}
AGENT_LINE="$(degraded_argv rr03-gw-restart-2)"
[ -n "$AGENT_LINE" ] && ok "control: degraded path recorded an agent call" || bad "control: degraded path made no agent call"
case " $AGENT_LINE " in *" --local "*) ok "L3 rr03- (degraded, no supervisor): --local present" ;; *) bad "L3" "$AGENT_LINE" ;; esac
AGENT_LINE="$(degraded_argv rr02-coach-2)"
{ [ -n "$AGENT_LINE" ] && case " $AGENT_LINE " in *" --local "*) false ;; *) true ;; esac; } && ok "L4 rr02- (degraded): no --local" || bad "L4" "$AGENT_LINE"
run_case e xrr03-not-a-prefix
{ [ -n "$AGENT_LINE" ] && case " $AGENT_LINE " in *" --local "*) false ;; *) true ;; esac; } && ok "L5 prefix must be at the start (xrr03-... gets no --local)" || bad "L5" "$AGENT_LINE"
# the message text and session key still travel as ONE argv element each (flag added, nothing re-split)
run_case f rr03-argv-check
printf '%s' "$AGENT_LINE" | grep -q -- '--agent main --session-key sess-rr03-argv-check --message' && ok "L6 agent/session-key/message argv unchanged" || bad "L6" "$AGENT_LINE"

echo; echo "RR-030 F66 rr03 --local flag: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ]
