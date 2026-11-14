#!/usr/bin/env bash
# tests/rescue/RRX-RUNNER/test_step_gate.sh — RRX-015 step gate.
#
# RRX-015: no case moves a step without a real artifact, and the route is a
# recorded decision. This test drives the REAL gate (rr_step_gate.py) over its
# own command line — never a grep of its source:
#   1. the gate's own selftest (which includes the mismatched rule/route pair,
#      R3 with fix_ourselves, being refused),
#   2. one full happy path of the eight steps, recorded one at a time in a
#      temporary cases folder,
#   3. audit, which must print that the case is complete.
#
# Hermetic: one temp folder, no credential, no network, no live box.
set -u

if [ -n "${BASH_SOURCE:-}" ]; then _HERE_SRC="${BASH_SOURCE[0]}"; else _HERE_SRC="$0"; fi
HERE="$(cd "$(dirname "$_HERE_SRC")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
GATE="$REPO/23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/rr_step_gate.py"
RULES="$REPO/23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/decision-rules.json"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }

echo "== RRX-015: step gate, decision rule and audit =="

for f in "$GATE" "$RULES"; do
  if [ -f "$f" ]; then ok "present: $(basename "$f")"; else bad "present: $f"; fi
done
if [ "$FAIL" -ne 0 ]; then
  echo "FAIL: $FAIL failed, $PASS passed"
  exit 1
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rrx015-step-gate.XXXXXX")" || { echo "FAIL: cannot make a temp folder"; exit 1; }
trap 'rm -rf "$WORK"' EXIT

CASES="$WORK/cases"
TICKET="RR-015001"
mkdir -p "$CASES/$TICKET"
printf 'real evidence\n' > "$CASES/$TICKET/evidence.txt"

# ---------------------------------------------------------------------------
echo "-- selftest"
if python3 "$GATE" selftest > "$WORK/selftest.txt" 2>&1; then
  ok "selftest"
else
  bad "selftest" "$(cat "$WORK/selftest.txt")"
fi

# ---------------------------------------------------------------------------
# record_step N '<json body>' — exactly the runner's command, no shortcut.
record_step() {
  local n="$1" body="$2" src="$WORK/step-$1.json" out="$WORK/record-$1.txt"
  printf '%s\n' "$body" > "$src"
  if python3 "$GATE" record --cases-root "$CASES" --ticket "$TICKET" --step "$n" --from "$src" > "$out" 2>&1; then
    ok "step $n recorded"
  else
    bad "step $n recorded" "$(cat "$out")"
  fi
}

echo "-- eight-step happy path"
record_step 1 '{"ticket_id":"RR-015001","box_slug":"box-a","problem":"the gateway is not answering","received_at":"2026-11-12T10:00:00-05:00","payload_sha256":"2f8a1c"}'
record_step 2 '{"ticket_id":"RR-015001","box_slug":"box-a","cap_source":"rr_cap_counters","used_today":1,"cap_limit":25,"read_at":"2026-11-12T10:01:00-05:00"}'
record_step 3 '{"ticket_id":"RR-015001","severity":"P2","failure_class":"gateway-down","already_tried_reviewed":true,"evidence_files":["evidence.txt"]}'
record_step 4 '{"ticket_id":"RR-015001","route":"fix_ourselves","rule_id":"R4","reason":"the client agent cannot act: gateway down","one_way_door":false}'
record_step 5 '{"ticket_id":"RR-015001","route":"fix_ourselves","summary":"restarted the gateway process","evidence_files":["evidence.txt"]}'
record_step 6 '{"ticket_id":"RR-015001","check_id":"gateway-answers","result":"passed","evidence_files":["evidence.txt"]}'
record_step 7 '{"ticket_id":"RR-015001","outcome":"solved","owner_message":"We restarted your gateway and checked that it answers again.","delivery_receipt":"msg-1"}'
record_step 8 '{"ticket_id":"RR-015001","final_status":"closed","ledger_receipt":"row-1"}'

# ---------------------------------------------------------------------------
echo "-- audit"
if python3 "$GATE" audit --cases-root "$CASES" --ticket "$TICKET" > "$WORK/audit.txt" 2>&1; then
  case "$(cat "$WORK/audit.txt")" in
    *"the case is complete"*) ok "audit says the case is complete" ;;
    *) bad "audit says the case is complete" "$(cat "$WORK/audit.txt")" ;;
  esac
else
  bad "audit exits 0" "$(cat "$WORK/audit.txt")"
fi

# ---------------------------------------------------------------------------
echo
if [ "$FAIL" -eq 0 ]; then
  echo "PASS: $PASS checks"
  exit 0
fi
echo "FAIL: $FAIL failed, $PASS passed"
exit 1
