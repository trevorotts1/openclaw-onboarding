#!/usr/bin/env bash
# Acceptance cases for scripts/ghl-client-emails.py, run against fake-ghl-api.py on an
# ephemeral loopback port. No real GoHighLevel call is possible: COUNCIL_GHL_API_BASE
# points at the fake and COUNCIL_GHL_ENV_FILE at a temp file. Addresses are made up.
#   bash scripts/tests/ghl-client-emails.test.sh      (exit 0 = all PASS)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$HERE/../ghl-client-emails.py"
FAKE="$HERE/fake-ghl-api.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ghl-emails-test.XXXXXX")"
TOKEN="pit-qc-GHL-TOKEN-0001"; LOC="LOC-test-1"
FAKE_PID=""; FAILS=0; N=0
stop_fake() { [ -z "$FAKE_PID" ] || { kill "$FAKE_PID" 2>/dev/null; wait "$FAKE_PID" 2>/dev/null; FAKE_PID=""; }; }
trap 'stop_fake; rm -rf "$WORK"' EXIT
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; FAILS=$((FAILS + 1)); }
check() { local d="$1"; shift; N=$((N + 1)); if "$@" >/dev/null 2>&1; then pass "$d"; else fail "$d"; fi; }

printf 'OTHER=1\n$(touch %s)\nexport GOHIGHLEVEL_API_KEY="%s"\n' "$WORK/pwned" "$TOKEN" > "$WORK/ghl.env"

fixture() {
  jq -cn --arg t "$TOKEN" --arg l "$LOC" '
    {token:$t, location:$l, fail:{}, contacts:([
      {id:"c1", firstName:"Jennifer", lastName:"Allen", email:"jen@example.test", phone:"+1 (555) 010-0001",
       additionalEmails:["jen.allen@example.test","jen+promo@example.test","team@blackceo.com","op@example.test","not-an-email"]},
      {id:"c2", firstName:"jennifer", lastName:"ALLEN", email:"jallen-alt@example.test", phone:"5550100001"},
      {id:"c3", firstName:"Jennifer", lastName:"Allen", email:"jallen-other@example.test", phone:"5550109999"},
      {id:"c4", firstName:"Jennifer", lastName:"Brown", email:"jbrown@example.test", phone:"5550100001"},
      {id:"c5", firstName:"Eddie", lastName:"Otts", email:"eddie@example.test", phone:"5550200002",
       companyName:"Eddie Otts Trading, LLC", additionalEmails:["eddie.trading@example.test"]},
      {id:"c6", firstName:"Ann", lastName:"Lee", email:"ann@example.test", phone:"5550300003", companyName:"Twin Peaks Consulting"},
      {id:"c7", firstName:"Bob", lastName:"Lee", email:"bob@example.test", phone:"5550300004", companyName:"The Twin Peaks"},
      {id:"c8", firstName:"Eddie", lastName:"Stranger", email:"stranger@example.test", phone:"5550900009", companyName:"Eddie Otts Trading Fans"}]
      + [range(0; 22) | {id:("f\(.)"), firstName:"Fan", lastName:"N\(.)", email:"fan\(.)@example.test", companyName:"Pager Works Fans"}]
      + [{id:"c9", firstName:"Pat", lastName:"Target", email:"target@example.test", companyName:"Pager Works Inc"}])}'
}
start_fake() {
  stop_fake
  LOG="$WORK/log.$N.$RANDOM"; : > "$LOG"
  local pf="$WORK/port.$RANDOM"
  python3 -I "$FAKE" --fixture "$1" --log "$LOG" --port-file "$pf" &
  FAKE_PID=$!
  local i; for i in $(seq 1 100); do [ -s "$pf" ] && break; sleep 0.05; done
  PORT="$(cat "$pf")"
}
run() {  # SLUG SEEDS_JSON [LOCATION] [ENV_FILE] -> $OUT (stdout+stderr)
  OUT="$WORK/out.$N.$RANDOM"
  jq -cn --arg s "$1" --argjson seeds "$2" --arg l "${3-$LOC}" '{slug:$s, seeds:$seeds, operator:["op@example.test"], location_id:$l}' \
    | env COUNCIL_GHL_API_BASE="http://127.0.0.1:$PORT" COUNCIL_GHL_ENV_FILE="${4-$WORK/ghl.env}" python3 -I "$HELPER" >"$OUT" 2>&1
}
res() { jq -c "$1" "$OUT"; }

echo "== 0. syntax and the control"
check "py_compile helper and fake" python3 -m py_compile "$HELPER" "$FAKE"
fixture > "$WORK/f.json"; start_fake "$WORK/f.json"
check "control: the fake really blocks the default Python user agent (403 1010)" bash -c "python3 -I -c \"
import urllib.request,urllib.error,sys
r=urllib.request.Request('http://127.0.0.1:$PORT/contacts/?locationId=$LOC&query=x', headers={'Authorization':'Bearer $TOKEN','Version':'2021-07-28'})
try: urllib.request.urlopen(r, timeout=5); sys.exit(1)
except urllib.error.HTTPError as e: sys.exit(0 if e.code == 403 else 1)\""

echo "== 1. seed email match, same name + same phone merged, nothing else"
run jennifer '["jen@example.test"]'
check "status ok" test "$(res .status)" = '"ok"'
check "adds the seed contact's other email and the same-name same-phone duplicate only" test "$(res .emails)" = '["jallen-alt@example.test","jen.allen@example.test"]'
check "same name but a different phone is not merged" bash -c "! grep -q jallen-other '$OUT'"
check "same first name (and same phone), different last name is never merged" bash -c "! grep -q jbrown '$OUT'"
check "plus-address, blackceo.com, operator, malformed and the seed itself are never returned" bash -c "! grep -Eq 'jen\\+promo|blackceo|op@|not-an-email|\"jen@' '$OUT'"
check "the env file is parsed, never executed" test ! -e "$WORK/pwned"
check "GET only" bash -c "! grep -qv '^GET ' '$LOG'"

echo "== 2. a host named after a business is matched by company name"
run eddie-otts-trading '[]'
check "company 'Eddie Otts Trading, LLC' matches slug eddie-otts-trading" test "$(res '[.status, .emails]')" = '["ok",["eddie.trading@example.test","eddie@example.test"]]'
check "a company that only contains the name ('... Fans') is not a match" bash -c "! grep -q stranger '$OUT'"
run eddie '[]'
check "first name alone never matches (slug eddie)" test "$(res '[.status, .emails]')" = '["none",[]]'
run jennifer-allen '[]'
check "full name alone never matches (slug jennifer-allen, no company)" test "$(res '[.status, .emails]')" = '["none",[]]'

echo "== 3. ambiguity adds nothing"
run twin-peaks '[]'
check "two people (different phones) under one company: ambiguous, no emails" test "$(res '[.status, .emails]')" = '["ambiguous",[]]'
run jennifer '["jen@example.test","jallen-other@example.test"]'
check "seeds landing on two contacts with different phones: ambiguous" test "$(res '[.status, .emails]')" = '["ambiguous",[]]'

echo "== 3b. a company match never stands in for a name match"
jq -c --arg t "$TOKEN" --arg l "$LOC" '{token:$t, location:$l, fail:{}, contacts:[
  {id:"n1", firstName:"Zed", lastName:"Quill", email:"zed@example.test", phone:"5550500001", companyName:"Ann LLC"},
  {id:"n2", firstName:"Karen", lastName:"Vaughn", email:"kv-other@example.test", phone:"5550500002", companyName:"Karen Vaughn"},
  {id:"n3", firstName:"Eddie", lastName:"Otts", email:"eddie@example.test", phone:"5550200002"},
  {id:"n4", email:"bookkeeper@example.test", companyName:"Eddie Otts Trading LLC"}]}' <<<null > "$WORK/fn.json"
start_fake "$WORK/fn.json"
run ann '[]'
check "one-word slug (a first name): company 'Ann LLC' is not a match" test "$(res '[.status, .emails]')" = '["none",[]]'
run karen-vaughn '[]'
check "a company that is only the contact's own full name is not a match" test "$(res '[.status, .emails]')" = '["none",[]]'
run eddie-otts-trading '["eddie@example.test"]'
check "a nameless company contact next to the seeded client: ambiguous, no emails" test "$(res '[.status, .emails]')" = '["ambiguous",[]]'

echo "== 4. paging"
start_fake "$WORK/f.json"
run pager-works '[]'
check "a match on page 2 is found (22 non-matching contacts first)" test "$(res '[.status, .emails]')" = '["ok",["target@example.test"]]'
check "...and the helper asked for page 2" grep -q 'page=2' "$LOG"

echo "== 5. no credentials or location: silent skip, zero requests"
start_fake "$WORK/f.json"
run jennifer '["jen@example.test"]' ""
check "no location id: skipped" test "$(res .status)" = '"skipped"'
run jennifer '["jen@example.test"]' "$LOC" "$WORK/missing.env"
check "no token: skipped" test "$(res .status)" = '"skipped"'
check "skipped runs sent zero requests" test ! -s "$LOG"

echo "== 6. retries once on 429; a persistent failure returns nothing"
fixture | jq -c '.fail["429_once"] = true' > "$WORK/f429.json"; start_fake "$WORK/f429.json"
run eddie-otts-trading '[]'
check "first request 429, retried: ok" test "$(res .status)" = '"ok"'
fixture | jq -c '.fail.always_500 = true' > "$WORK/f500.json"; start_fake "$WORK/f500.json"
run eddie-otts-trading '[]'
check "persistent 500: error, no emails" test "$(res '[.status, .emails]')" = '["error",[]]'
fixture | jq -c '.token = "pit-someone-else"' > "$WORK/fbad.json"; start_fake "$WORK/fbad.json"
run eddie-otts-trading '[]'
check "rejected token: error, no emails" test "$(res '[.status, .emails]')" = '["error",[]]'

echo "== 7. the token is never printed"
check "token in no output" bash -c "! grep -q 'GHL-TOKEN' '$WORK'/out.*"
check "token in no request log line" bash -c "! grep -q 'GHL-TOKEN' '$WORK'/log.*"

echo
if [ "$FAILS" = 0 ]; then echo "ALL $N CHECKS PASSED"; else echo "$FAILS of $N FAILED"; fi
[ "$FAILS" = 0 ]
