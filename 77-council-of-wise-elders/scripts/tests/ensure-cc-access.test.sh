#!/usr/bin/env bash
# Acceptance cases for scripts/ensure-cc-access.sh, run against fake-cloudflare-api.py
# on an ephemeral loopback port. No real Cloudflare call is possible: CF_API_BASE points
# at the fake and the state dir / emails file live in a temp dir.
#   bash scripts/tests/ensure-cc-access.test.sh      (exit 0 = all PASS)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../ensure-cc-access.sh"
FAKE="$HERE/fake-cloudflare-api.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/cc-access-test.XXXXXX")"
mkdir -p "$WORK/out" "$WORK/tmp" "$WORK/state"
TOKEN="qc-secret-TOKEN-123"
FAKE_PID=""; FAILS=0; N=0
stop_fake() { [ -z "$FAKE_PID" ] || { kill "$FAKE_PID" 2>/dev/null; wait "$FAKE_PID" 2>/dev/null; FAKE_PID=""; }; }
trap 'stop_fake; rm -rf "$WORK"' EXIT
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; FAILS=$((FAILS + 1)); }
check() { local d="$1"; shift; N=$((N + 1)); if "$@" >/dev/null 2>&1; then pass "$d"; else fail "$d"; fi; }

Z="zerohumanworkforce.com"
OP="ops@cx-test.example"
OP2="ops2@cx-test.example"

# Emails file: operator list, a file email for newbox + driftbox + okbox, a placeholder for phbox.
cat > "$WORK/emails.json" <<JSON
{"operator":["$OP"],"clients":{"newbox":["owner-new@cx-test.example"],"driftbox":["owner-drift@cx-test.example"],
 "okbox":["owner-ok@cx-test.example"],"phbox":["pending+phbox@cx-test.example"]}}
JSON

# fixture: remote tunnel CC hosts (no app) newbox noemail phbox rescbox; driftbox/okbox/openbox have apps;
# localbox rides a locally managed tunnel; newbox-gw style hosts are not on :4000.
fixture() {
  local out='{"token":"'"$TOKEN"'","account":"qc-acct","zone":{"id":"zone-real","name":"'"$Z"'"},"dns":[],"tunnels":{},"apps":[],"policies":{},"idps":[{"id":"idp-otp","type":"onetimepin","name":"otp"},{"id":"idp-goog","type":"google","name":"g"}],"fail":{}}'
  local s i=0 tid src
  for s in newbox noemail phbox rescbox driftbox okbox openbox localbox; do
    i=$((i + 1)); tid="$(printf '%032x' "$((0x0123456789abcdef + i))")"; src=cloudflare; [ "$s" = localbox ] && src=local
    out="$(jq -c --arg s "$s" --arg t "$tid" --arg z "$Z" --arg src "$src" '
      .dns += [{id:("d-"+$s),type:"CNAME",name:($s+"."+$z),content:($t+".cfargotunnel.com"),proxied:true},
               {id:("dg-"+$s),type:"CNAME",name:($s+"-gw."+$z),content:($t+".cfargotunnel.com"),proxied:true},
               {id:("dr-"+$s),type:"CNAME",name:("rescue-"+$s+"."+$z),content:($t+".cfargotunnel.com"),proxied:true}]
      | .tunnels[$t] = {source:$src,config:{ingress:[
          {hostname:($s+"."+$z),service:"http://localhost:4000"},
          {hostname:($s+"-gw."+$z),service:"http://127.0.0.1:18789"},
          {hostname:("rescue-"+$s+"."+$z),service:"ssh://localhost:22"},
          {service:"http_status:404"}]}}' <<<"$out")"
  done
  jq -c --arg z "$Z" '
    .apps += [
      {id:"app-drift",name:"x",domain:("driftbox."+$z),type:"self_hosted",session_duration:"24h"},
      {id:"app-ok",name:"y",domain:("okbox."+$z),type:"self_hosted",session_duration:"720h"},
      {id:"app-open",name:"z",domain:("openbox."+$z),type:"self_hosted",session_duration:"24h"},
      {id:"app-resc",name:"r",domain:("rescue-rescbox."+$z),type:"self_hosted",session_duration:"4320h"}]
    | .policies["app-drift"] = [{id:"p1",name:"Allowed users",decision:"allow",include:[{email:{email:"ops@cx-test.example"}},{email:{email:"someone-else@cx-test.example"}}]}]
    | .policies["app-ok"] = [{id:"p2",name:"Allowed users",decision:"allow",include:[{email:{email:"ops@cx-test.example"}},{email:{email:"ops2@cx-test.example"}},{email:{email:"owner-ok@cx-test.example"}}]}]
    | .policies["app-open"] = [{id:"p3",name:"Allowed users",decision:"allow",include:[{everyone:{}}]}]
    | .policies["app-resc"] = [{id:"p4",name:"Rescue",decision:"allow",include:[{email:{email:"ops@cx-test.example"}},{email:{email:"owner-resc@cx-test.example"}}]}]' <<<"$out"
}

start_fake() {
  stop_fake
  LOG="$WORK/log.$N.$RANDOM"; STATE="$WORK/state.$N.$RANDOM.json"; : > "$LOG"
  local pf="$WORK/port.$RANDOM"
  python3 -I "$FAKE" --fixture "$1" --log "$LOG" --port-file "$pf" --state-out "$STATE" &
  FAKE_PID=$!
  local i; for i in $(seq 1 100); do [ -s "$pf" ] && break; sleep 0.05; done
  PORT="$(cat "$pf")"
}
run_script() {
  OUT="$WORK/out/case.$N.$RANDOM"
  env CF_API_BASE="http://127.0.0.1:$PORT/client/v4" COUNCIL_ACCESS_STATE_DIR="$WORK/state" \
      COUNCIL_CC_EMAILS_FILE="$WORK/emails.json" COUNCIL_CC_OPERATOR_EMAILS="${OPEMAILS-}" \
      CLOUDFLARE_API_TOKEN="$TOKEN" CLOUDFLARE_ACCOUNT_ID=qc-acct CLOUDFLARE_ZONE_ID=wrong-zone \
      COUNCIL_ACCESS_ENV_FILE=/nonexistent TMPDIR="$WORK/tmp" "$SCRIPT" "$@" >"$OUT" 2>&1
  RC=$?
}
state() { jq -c "$1" "$STATE"; }
only_gets() { ! grep -Ev '^GET ' "$LOG"; }
nonget_count() { grep -Evc '^GET ' "$LOG"; }
line_has() { grep -q "^CC_ACCESS: $1.$Z $2" "$OUT"; }
app_count() { state "[.apps[] | select(.domain == \"$1.$Z\")] | length"; }

echo "== 1. syntax, re-exec, refusals"
check "/bin/bash -n passes" /bin/bash -n "$SCRIPT"
env -u CLOUDFLARE_API_TOKEN -u CLOUDFLARE_ACCOUNT_ID COUNCIL_ACCESS_ENV_FILE=/nonexistent /bin/bash "$SCRIPT" >"$WORK/out/noenv" 2>&1; RC=$?
check "from /bin/bash 3.2 re-execs and refuses without credentials (exit 3)" test "$RC" = 3
fixture > "$WORK/f.json"; start_fake "$WORK/f.json"
OPEMAILS="" ; echo '{}' > "$WORK/empty.json"
env CF_API_BASE="http://127.0.0.1:$PORT/client/v4" COUNCIL_ACCESS_STATE_DIR="$WORK/state" COUNCIL_CC_EMAILS_FILE="$WORK/empty.json" \
    CLOUDFLARE_API_TOKEN="$TOKEN" CLOUDFLARE_ACCOUNT_ID=qc-acct "$SCRIPT" --apply >"$WORK/out/noop" 2>&1; RC=$?
check "no operator email configured: exit 3" test "$RC" = 3
check "...and zero requests reached the API" test ! -s "$LOG"

echo "== 2. dry-run (operator email from env + file)"
OPEMAILS="$OP2"
run_script
check "dry-run exit 0" test "$RC" = 0
check "log contains only GET lines" only_gets
check "newbox PLANNED (known email)" line_has newbox PLANNED
check "rescbox PLANNED (client email read from its rescue app)" line_has rescbox PLANNED
check "noemail: NEEDS_EMAIL" line_has noemail NEEDS_EMAIL
check "phbox: placeholder pending+ email is NEEDS_EMAIL" line_has phbox NEEDS_EMAIL
check "driftbox: DRIFT" line_has driftbox DRIFT
check "openbox (everyone rule): DRIFT" line_has openbox DRIFT
check "okbox: ALREADY_PRESENT" line_has okbox ALREADY_PRESENT
check "localbox (local tunnel) not listed, -gw and rescue hosts not listed" bash -c "! grep -E '^CC_ACCESS: (localbox|[a-z]+-gw|rescue-)' '$OUT'"
check "summary counts skipped hosts" grep -Eq 'skipped=[1-9]' "$OUT"
check "receipts written in the state dir" test -s "$WORK/state/cc-access-last-run.json" -a -s "$WORK/state/cc-access-runs.log"
check "receipt lists needs_email hosts and counts" test "$(jq -c '[.counts.NEEDS_EMAIL, .counts.PLANNED, (.needs_email|length)] | join(",")' "$WORK/state/cc-access-last-run.json")" = '"2,2,2"'

echo "== 3. --apply creates only what is safe"
start_fake "$WORK/f.json"
run_script --apply
check "apply exit 0" test "$RC" = 0
check "newbox CREATED" line_has newbox CREATED
check "rescbox CREATED" line_has rescbox CREATED
check "exactly 2 writes (one POST per creatable host), all POST apps" bash -c "test \"$(nonget_count)\" = 2 && ! grep -Ev '^GET |^POST /client/v4/accounts/qc-acct/access/apps' '$LOG'"
check "newbox app: self_hosted, 720h, 'Command Center - newbox', OTP + Google" test "$(state '.apps[] | select(.domain=="newbox.'$Z'") | [.name,.type,.session_duration,(.allowed_idps|join("+"))] | join("|")')" = '"Command Center - newbox|self_hosted|720h|idp-otp+idp-goog"'
check "newbox allow policy is 'Allowed users', allow, no require" test "$(state '.policies[.apps[] | select(.domain=="newbox.'$Z'") | .id][0] | [.name,.decision,(.require // "none" | tostring)] | join("|")')" = '"Allowed users|allow|none"'
check "newbox allow-list is exactly operator(env+file) + owner" test "$(state '.policies[.apps[] | select(.domain=="newbox.'$Z'") | .id][0].include | map(.email.email) | sort')" = '["ops2@cx-test.example","ops@cx-test.example","owner-new@cx-test.example"]'
check "rescbox allow-list is operator + the rescue app owner email" test "$(state '.policies[.apps[] | select(.domain=="rescbox.'$Z'") | .id][0].include | map(.email.email) | sort')" = '["ops2@cx-test.example","ops@cx-test.example","owner-resc@cx-test.example"]'
check "no created policy contains everyone or a service token" test "$(state '[.policies[][] | .include[]? | keys[]] | map(select(. != "email" and . != "everyone")) | length')" = 0 -a "$(state '[.policies[] | .[] | select(.id|startswith("pol-")) | .include[] | keys[]] | unique')" = '["email"]'
check "NEEDS_EMAIL hosts got no app (noemail, phbox)" test "$(app_count noemail)" = 0 -a "$(app_count phbox)" = 0
check "DRIFT apps untouched (still 24h, still the original policy)" test "$(state '[.apps[] | select(.id=="app-drift" or .id=="app-open")] | map(.session_duration) | unique')" = '["24h"]' -a "$(state '.policies["app-drift"][0].include | length')" = 2
check "no app for the local-tunnel host, -gw or rescue hosts" test "$(app_count localbox)" = 0 -a "$(state '[.apps[] | select(.domain | test("-gw\\.")) ] | length')" = 0

echo "== 4. second --apply is a no-op"
cp "$STATE" "$WORK/after.json"; start_fake "$WORK/after.json"
run_script --apply
check "second run exit 0" test "$RC" = 0
check "second run sends zero writes" test "$(nonget_count)" = 0
check "newbox now ALREADY_PRESENT" line_has newbox ALREADY_PRESENT
check "rescbox now ALREADY_PRESENT" line_has rescbox ALREADY_PRESENT
check "NEEDS_EMAIL is retried (noemail still NEEDS_EMAIL)" line_has noemail NEEDS_EMAIL

echo "== 5. nothing sensitive printed"
all_out="$(cat "$WORK"/out/case.* "$WORK/state/cc-access-last-run.json" "$WORK/state/cc-access-runs.log")"
check "no email address appears in any output or receipt" bash -c "! grep -q '@' <<<\"\$1\"" _ "$all_out"
check "token value never printed" bash -c "! grep -q 'qc-secret-TOKEN' <<<\"\$1\"" _ "$all_out"

start_fake "$WORK/f.json"; run_script --json
check "--json output is a valid host array and email-free" bash -c "jq -e 'type == \"array\" and length > 0' '$OUT' >/dev/null && ! grep -q '@' '$OUT'"

echo "== 6. failure paths write nothing wrong"
fixture | jq -c '.fail.app_create = true' > "$WORK/f6.json"; start_fake "$WORK/f6.json"
run_script --apply
check "app create failure: FAILED, exit 1" bash -c "grep -q '^CC_ACCESS: newbox.$Z FAILED' '$OUT' && test '$RC' = 1"
check "no app created on failure" test "$(app_count newbox)" = 0
fixture | jq -c '.idps = []' > "$WORK/f7.json"; start_fake "$WORK/f7.json"
run_script --apply
check "no One-Time PIN IdP: every create FAILED and zero writes" bash -c "grep -q '^CC_ACCESS: newbox.$Z FAILED.*One-Time PIN' '$OUT' && grep -q '^CC_ACCESS: rescbox.$Z FAILED' '$OUT' && test \"$(nonget_count)\" = 0"
check "open (everyone) app reported as non-email rule drift" grep -q "^CC_ACCESS: openbox.$Z DRIFT.*non-email" "$OUT"

echo "== 7. the rescue-app email source and the env file cannot be abused"
fixture | jq -c '.policies["app-resc"][0].include += [{everyone:{}}]' > "$WORK/f8.json"; start_fake "$WORK/f8.json"
run_script --apply
check "rescue app that also admits everyone is not a verified email source: NEEDS_EMAIL, no app" bash -c "grep -q '^CC_ACCESS: rescbox.$Z NEEDS_EMAIL.*non-email' '$OUT' && test \"$(app_count rescbox)\" = 0"
printf 'CLOUDFLARE_API_TOKEN="%s"\nCLOUDFLARE_ACCOUNT_ID=qc-acct\nX=1 touch %s\n$(touch %s)\n' "$TOKEN" "$WORK/pwned1" "$WORK/pwned2" > "$WORK/op.env"
start_fake "$WORK/f.json"
env -u CLOUDFLARE_API_TOKEN -u CLOUDFLARE_ACCOUNT_ID CF_API_BASE="http://127.0.0.1:$PORT/client/v4" COUNCIL_ACCESS_STATE_DIR="$WORK/state" \
    COUNCIL_CC_EMAILS_FILE="$WORK/emails.json" COUNCIL_ACCESS_ENV_FILE="$WORK/op.env" TMPDIR="$WORK/tmp" "$SCRIPT" >"$WORK/out/case.envfile" 2>&1; RC=$?
check "credentials load from the env file (dry-run exit 0, GET only)" bash -c "test '$RC' = 0 && grep -q '^CC_ACCESS: newbox.$Z PLANNED' '$WORK/out/case.envfile'"
check "the env file is parsed, never executed" test ! -e "$WORK/pwned1" -a ! -e "$WORK/pwned2"
check "env-file run printed no token" bash -c "! grep -q 'qc-secret-TOKEN' '$WORK/out/case.envfile'"

echo
if [ "$FAILS" = 0 ]; then echo "ALL $N CHECKS PASSED"; else echo "$FAILS of $N FAILED"; fi
[ "$FAILS" = 0 ]
