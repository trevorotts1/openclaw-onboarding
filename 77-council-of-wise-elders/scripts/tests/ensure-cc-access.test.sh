#!/usr/bin/env bash
# Acceptance cases for scripts/ensure-cc-access.sh, run against fake-cloudflare-api.py
# on an ephemeral loopback port. No real Cloudflare call is possible: CF_API_BASE points
# at the fake and the state dir / emails file live in a temp dir.
#   bash scripts/tests/ensure-cc-access.test.sh      (exit 0 = all PASS)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../ensure-cc-access.sh"
FAKE="$HERE/fake-cloudflare-api.py"
FAKE_GHL="$HERE/fake-ghl-api.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/cc-access-test.XXXXXX")"
mkdir -p "$WORK/out" "$WORK/tmp" "$WORK/state"
TOKEN="qc-secret-TOKEN-123"
FAKE_PID=""; GHL_PID=""; FAILS=0; N=0
# GoHighLevel: never the real token file or API. Sections 1-7 run with no GHL configuration (silent skip).
export COUNCIL_GHL_ENV_FILE="$WORK/no-ghl.env" COUNCIL_GHL_API_BASE="http://127.0.0.1:9" COUNCIL_GHL_LOCATION_ID=""
stop_fake() { [ -z "$FAKE_PID" ] || { kill "$FAKE_PID" 2>/dev/null; wait "$FAKE_PID" 2>/dev/null; FAKE_PID=""; }; }
stop_ghl() { [ -z "$GHL_PID" ] || { kill "$GHL_PID" 2>/dev/null; wait "$GHL_PID" 2>/dev/null; GHL_PID=""; }; }
trap 'stop_fake; stop_ghl; rm -rf "$WORK"' EXIT
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; FAILS=$((FAILS + 1)); }
check() { local d="$1"; shift; N=$((N + 1)); if "$@" >/dev/null 2>&1; then pass "$d"; else fail "$d"; fi; }

Z="zerohumanworkforce.com"
OP="ops@cx-test.example"
OP2="ops2@cx-test.example"

# Emails file: operator list, a file email for newbox + driftbox + okbox, a placeholder for phbox.
cat > "$WORK/emails.json" <<JSON
{"operator":["$OP"],"clients":{"newbox":["owner-new@cx-test.example"],"driftbox":["owner-drift@cx-test.example"],
 "okbox":["owner-ok@cx-test.example"],"phbox":["pending+phbox@cx-test.example"],"localbox":["owner-local@cx-test.example"]}}
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
check "driftbox (allow-list lacks an operator and the client email): PLANNED to add 2, counts only" line_has driftbox "PLANNED dry-run: would add 2 email(s) (1 operator, 1 client"
check "openbox (everyone rule): DRIFT" line_has openbox DRIFT
check "okbox: ALREADY_PRESENT" line_has okbox ALREADY_PRESENT
check "localbox (local tunnel, readable :4000 rule) PLANNED like any Command Center; -gw and rescue hosts not listed" bash -c "grep -q '^CC_ACCESS: localbox.$Z PLANNED' '$OUT' && ! grep -E '^CC_ACCESS: ([a-z]+-gw|rescue-)' '$OUT'"
check "summary counts skipped hosts" grep -Eq 'skipped=[1-9]' "$OUT"
check "no GoHighLevel configuration: one 'ghl: skipped' counts line, no failure" test "$(grep -c '^ghl: skipped (no credentials/location)$' "$OUT")" = 1
check "receipts written in the state dir" test -s "$WORK/state/cc-access-last-run.json" -a -s "$WORK/state/cc-access-runs.log"
check "receipt lists needs_email hosts and counts" test "$(jq -c '[.counts.NEEDS_EMAIL, .counts.PLANNED, (.needs_email|length)] | join(",")' "$WORK/state/cc-access-last-run.json")" = '"2,4,2"'

echo "== 3. --apply creates only what is safe"
start_fake "$WORK/f.json"
run_script --apply
check "apply exit 0" test "$RC" = 0
check "localbox CREATED (local tunnel proven by its own :4000 rule)" line_has localbox CREATED
check "newbox CREATED" line_has newbox CREATED
check "rescbox CREATED" line_has rescbox CREATED
check "exactly 4 writes: one POST per creatable host + one PUT to driftbox's allow policy" bash -c "test \"$(nonget_count)\" = 4 && ! grep -Ev '^GET |^POST /client/v4/accounts/qc-acct/access/apps\$|^PUT /client/v4/accounts/qc-acct/access/apps/app-drift/policies/p1\$' '$LOG'"
check "driftbox RECONCILED" line_has driftbox RECONCILED
check "driftbox: every original rule kept in order, the 2 missing emails appended" test "$(state '.policies["app-drift"][0].include | map(.email.email)')" = '["ops@cx-test.example","someone-else@cx-test.example","ops2@cx-test.example","owner-drift@cx-test.example"]'
check "receipt counts RECONCILED and names the host" test "$(jq -c '[.counts.RECONCILED, .reconciled]' "$WORK/state/cc-access-last-run.json")" = '[1,["driftbox.'$Z'"]]'
check "runs.log line carries reconciled=1" bash -c "tail -n1 '$WORK/state/cc-access-runs.log' | grep -q 'reconciled=1'"
check "newbox app: self_hosted, 720h, 'Command Center - newbox', OTP + Google" test "$(state '.apps[] | select(.domain=="newbox.'$Z'") | [.name,.type,.session_duration,(.allowed_idps|join("+"))] | join("|")')" = '"Command Center - newbox|self_hosted|720h|idp-otp+idp-goog"'
check "newbox allow policy is 'Allowed users', allow, no require" test "$(state '.policies[.apps[] | select(.domain=="newbox.'$Z'") | .id][0] | [.name,.decision,(.require // "none" | tostring)] | join("|")')" = '"Allowed users|allow|none"'
check "newbox allow-list is exactly operator(env+file) + owner" test "$(state '.policies[.apps[] | select(.domain=="newbox.'$Z'") | .id][0].include | map(.email.email) | sort')" = '["ops2@cx-test.example","ops@cx-test.example","owner-new@cx-test.example"]'
check "rescbox allow-list is operator + the rescue app owner email" test "$(state '.policies[.apps[] | select(.domain=="rescbox.'$Z'") | .id][0].include | map(.email.email) | sort')" = '["ops2@cx-test.example","ops@cx-test.example","owner-resc@cx-test.example"]'
check "no created policy contains everyone or a service token" test "$(state '[.policies[][] | .include[]? | keys[]] | map(select(. != "email" and . != "everyone")) | length')" = 0 -a "$(state '[.policies[] | .[] | select(.id|startswith("pol-")) | .include[] | keys[]] | unique')" = '["email"]'
check "NEEDS_EMAIL hosts got no app (noemail, phbox)" test "$(app_count noemail)" = 0 -a "$(app_count phbox)" = 0
check "DRIFT app untouched (openbox: still 24h, still only the everyone rule); apps themselves never edited" test "$(state '[.apps[] | select(.id=="app-drift" or .id=="app-open")] | map(.session_duration) | unique')" = '["24h"]' -a "$(state '.policies["app-open"]')" = '[{"id":"p3","name":"Allowed users","decision":"allow","include":[{"everyone":{}}]}]'
check "local-tunnel host gets its login page; -gw and rescue hosts get none" test "$(app_count localbox)" = 1 -a "$(state '[.apps[] | select(.domain | test("-gw\\.")) ] | length')" = 0

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
check "no One-Time PIN IdP: every create FAILED and no POST (reconcile needs no IdP)" bash -c "grep -q '^CC_ACCESS: newbox.$Z FAILED.*One-Time PIN' '$OUT' && grep -q '^CC_ACCESS: rescbox.$Z FAILED' '$OUT' && ! grep -q '^POST ' '$LOG'"
check "open (everyone) app reported as non-email rule drift" grep -q "^CC_ACCESS: openbox.$Z DRIFT.*non-email" "$OUT"

echo "== 6b. orphan records: the tunnel or its configuration no longer exists"
T1="$(printf '%032x' "$((0x0123456789abcdef + 1))")"; T2="$(printf '%032x' "$((0x0123456789abcdef + 2))")"; T3="$(printf '%032x' "$((0x0123456789abcdef + 3))")"
OPEMAILS="$OP2"
fixture | jq -c --arg a "$T1" --arg b "$T2" --arg c "$T3" '.tunnels[$a].config_missing = true | .tunnels[$a].status = "inactive" | del(.tunnels[$b]) | .tunnels[$c].deleted_at = "2026-10-01T00:00:00Z"' > "$WORK/f6b.json"
start_fake "$WORK/f6b.json"
run_script --apply
check "orphans: exit 0 (no FAILED)" test "$RC" = 0
check "'Configuration for tunnel not found' (newbox): SKIPPED_ORPHAN" line_has newbox "SKIPPED_ORPHAN .*tunnel $T1, whose configuration no longer exists (HTTP 404"
check "tunnel gone (noemail): SKIPPED_ORPHAN" line_has noemail "SKIPPED_ORPHAN .*tunnel $T2"
check "deleted tunnel (phbox): SKIPPED_ORPHAN" line_has phbox "SKIPPED_ORPHAN"
check "orphans got no app; the other hosts still ran (rescbox + localbox CREATED, driftbox RECONCILED: 3 writes)" bash -c "test '$(app_count newbox)' = 0 && grep -q '^CC_ACCESS: rescbox.$Z CREATED' '$OUT' && grep -q '^CC_ACCESS: localbox.$Z CREATED' '$OUT' && test '$(nonget_count)' = 3"
# each orphan tunnel also carries the box's -gw and rescue- records: 3 tunnels x 3 records
check "receipt counts and names every orphan record (3 tunnels x 3 records)" test "$(jq -c '[.counts.SKIPPED_ORPHAN, ([.orphans[].host | select(IN("newbox.'$Z'","noemail.'$Z'","phbox.'$Z'"))] | sort)]' "$WORK/state/cc-access-last-run.json")" = '[9,["newbox.'$Z'","noemail.'$Z'","phbox.'$Z'"]]'
check "runs.log line carries orphans=9" bash -c "tail -n1 '$WORK/state/cc-access-runs.log' | grep -q ' orphans=9 '"
fixture | jq -c --arg a "$T1" '.tunnels[$a].config_missing = true' > "$WORK/f6d.json"; start_fake "$WORK/f6d.json"
run_script --apply
check "configuration 404 on a HEALTHY tunnel: FAILED, never SKIPPED_ORPHAN, no write for newbox" bash -c "test '$RC' = 1 && grep -q '^CC_ACCESS: newbox.$Z FAILED .*but the tunnel is healthy: not an orphan' '$OUT' && ! grep -q '^CC_ACCESS: newbox.$Z SKIPPED_ORPHAN' '$OUT' && test '$(app_count newbox)' = 0"
fixture | jq -c '.fail.tunnel_read = true' > "$WORK/f6c.json"; start_fake "$WORK/f6c.json"
run_script --apply
check "configuration read 503 stays FAILED (exit 1), never SKIPPED_ORPHAN, zero writes" bash -c "test '$RC' = 1 && grep -q '^CC_ACCESS: newbox.$Z FAILED could not read tunnel configuration for $T1 (HTTP 503)' '$OUT' && ! grep -q SKIPPED_ORPHAN '$OUT' && test '$(nonget_count)' = 0"

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

echo "== 8. reconcile edge cases + GoHighLevel lookup (fake GHL API)"
GTOK="pit-qc-GHL-TOKEN-0002"
printf 'GOHIGHLEVEL_API_KEY=%s\n' "$GTOK" > "$WORK/ghl.env"
jq -cn --arg t "$GTOK" '{token:$t, location:"LOC-qc-9", contacts:[
  {id:"g1", firstName:"Eddie", lastName:"Otts", email:"eddie@example.test", phone:"5550200002", companyName:"Eddie Otts Trading LLC"},
  {id:"g2", firstName:"Tok", lastName:"Owner", email:"owner-tok@cx-test.example", phone:"5550400004", additionalEmails:["owner-tok2@example.test"]},
  {id:"g3", firstName:"Ann", lastName:"Lee", email:"ann@example.test", phone:"5550300003", companyName:"Twin Peaks"},
  {id:"g4", firstName:"Bob", lastName:"Lee", email:"bob@example.test", phone:"5550300004", companyName:"Twin Peaks Inc"}]}' > "$WORK/ghl.json"
GLOG="$WORK/ghl.log"; : > "$GLOG"
python3 -I "$FAKE_GHL" --fixture "$WORK/ghl.json" --log "$GLOG" --port-file "$WORK/ghl.port" & GHL_PID=$!
for i in $(seq 1 100); do [ -s "$WORK/ghl.port" ] && break; sleep 0.05; done
cat > "$WORK/emails8.json" <<JSON
{"operator":["$OP"],"clients":{"tokbox":["owner-tok@cx-test.example"]},"ghl":{"location_id":"LOC-qc-9"}}
JSON
fixture8() {
  local out='{"token":"'"$TOKEN"'","account":"qc-acct","zone":{"id":"zone-real","name":"'"$Z"'"},"dns":[],"tunnels":{},"apps":[],"policies":{},"idps":[{"id":"idp-otp","type":"onetimepin","name":"otp"}],"fail":{}}'
  local s i=40 tid
  for s in tokbox reusebox nonidbox eddie-otts-trading twin-peaks; do
    i=$((i + 1)); tid="$(printf '%032x' "$((0x0123456789abcdef + i))")"
    out="$(jq -c --arg s "$s" --arg t "$tid" --arg z "$Z" '
      .dns += [{id:("d-"+$s),type:"CNAME",name:($s+"."+$z),content:($t+".cfargotunnel.com"),proxied:true}]
      | .tunnels[$t] = {source:"cloudflare",config:{ingress:[{hostname:($s+"."+$z),service:"http://localhost:4000"},{service:"http_status:404"}]}}' <<<"$out")"
  done
  jq -c --arg z "$Z" '
    .apps += [{id:"app-tok",name:"t",domain:("tokbox."+$z),type:"self_hosted"},
              {id:"app-reuse",name:"u",domain:("reusebox."+$z),type:"self_hosted"},
              {id:"app-nonid",name:"n",domain:("nonidbox."+$z),type:"self_hosted"}]
    | .policies["app-tok"] = [
        {id:"pt1",name:"Allowed users",decision:"allow",precedence:1,reusable:false,created_at:"2026-01-01T00:00:00Z",updated_at:"2026-01-02T00:00:00Z",
         session_duration:"24h",require:[],exclude:[{email:{email:"banned@cx-test.example"}}],
         include:[{email:{email:"OPS@cx-test.example"}},{service_token:{token_id:"st-1"}},{email_domain:{domain:"partner.example"}}]},
        {id:"pt2",name:"Machines",decision:"non_identity",precedence:2,reusable:false,include:[{service_token:{token_id:"st-2"}}]}]
    | .policies["app-reuse"] = [{id:"pr1",name:"Shared",decision:"allow",precedence:1,reusable:true,app_count:4,include:[{email:{email:"ops@cx-test.example"}}]}]
    | .policies["app-nonid"] = [{id:"pn1",name:"Machines",decision:"non_identity",precedence:1,include:[{service_token:{token_id:"st-3"}}]}]' <<<"$out"
}
run8() {
  OUT="$WORK/out/case.$N.$RANDOM"
  env CF_API_BASE="http://127.0.0.1:$PORT/client/v4" COUNCIL_ACCESS_STATE_DIR="$WORK/state" COUNCIL_CC_EMAILS_FILE="$WORK/emails8.json" \
      COUNCIL_CC_OPERATOR_EMAILS="$OP2" COUNCIL_GHL_ENV_FILE="$WORK/ghl.env" COUNCIL_GHL_API_BASE="http://127.0.0.1:$(cat "$WORK/ghl.port")" \
      CLOUDFLARE_API_TOKEN="$TOKEN" CLOUDFLARE_ACCOUNT_ID=qc-acct COUNCIL_ACCESS_ENV_FILE=/nonexistent TMPDIR="$WORK/tmp" "$SCRIPT" "$@" >"$OUT" 2>&1
  RC=$?
}
fixture8 > "$WORK/f8r.json"; start_fake "$WORK/f8r.json"
run8
check "dry-run: exit 0, GET only on Cloudflare and on GoHighLevel" bash -c "test '$RC' = 0 && ! grep -Ev '^GET ' '$LOG' && ! grep -Ev '^GET ' '$GLOG'"
check "dry-run: tokbox would add 3 (operator ops2, file owner, GoHighLevel duplicate email), counts only" line_has tokbox "PLANNED dry-run: would add 3 email(s) (1 operator, 2 client; client source: file+ghl)"
check "dry-run: business-named host matched by company name in GoHighLevel" line_has eddie-otts-trading "PLANNED .*client source: ghl"
check "reusable allow policy: DRIFT" line_has reusebox "DRIFT .*reusable"
check "only a non_identity policy: DRIFT (no allow policy)" line_has nonidbox "DRIFT .*no allow policy"
check "two people under one company: NEEDS_EMAIL, nothing added" line_has twin-peaks NEEDS_EMAIL
check "ghl counts line: 2 matched, 1 ambiguous" grep -q '^ghl: matched=2 none=0 ambiguous=1 errors=0' "$OUT"
check "the GoHighLevel helper asked for the configured location only" bash -c "grep -q 'locationId=LOC-qc-9' '$GLOG' && ! grep -v 'locationId=LOC-qc-9' '$GLOG'"
start_fake "$WORK/f8r.json"
run8 --apply
check "apply exit 0" test "$RC" = 0
check "tokbox RECONCILED" line_has tokbox RECONCILED
check "tokbox: email (original case), service token and domain rules kept in order; 3 emails appended" test "$(state '.policies["app-tok"][0].include')" = '[{"email":{"email":"OPS@cx-test.example"}},{"service_token":{"token_id":"st-1"}},{"email_domain":{"domain":"partner.example"}},{"email":{"email":"ops2@cx-test.example"}},{"email":{"email":"owner-tok2@example.test"}},{"email":{"email":"owner-tok@cx-test.example"}}]'
check "tokbox: name, decision, precedence, exclude, require, session untouched; non_identity policy untouched" test "$(state '[.policies["app-tok"][0] | .name, .decision, .precedence, .exclude, .require, .session_duration, .reusable, .created_at] + [.policies["app-tok"][1]]')" = '["Allowed users","allow",1,[{"email":{"email":"banned@cx-test.example"}}],[],"24h",false,"2026-01-01T00:00:00Z",{"id":"pt2","name":"Machines","decision":"non_identity","precedence":2,"reusable":false,"include":[{"service_token":{"token_id":"st-2"}}]}]'
check "PUT body carries no read-only field" test "$(state '[.put_bodies[] | keys[] | select(IN("id","created_at","updated_at","reusable","app_count","uid"))] | length')" = 0
check "writes: one PUT (tokbox) + one POST (eddie-otts-trading); reusable, non_identity, ambiguous hosts untouched" bash -c "test \"\$(grep -Ev '^GET ' '$LOG' | sort | tr '\n' '|')\" = 'POST /client/v4/accounts/qc-acct/access/apps|PUT /client/v4/accounts/qc-acct/access/apps/app-tok/policies/pt1|'"
check "reusable policy untouched" test "$(state '.policies["app-reuse"][0].include | length')" = 1
check "eddie-otts-trading app lets in the operators and the GoHighLevel client email" test "$(state '.policies[.apps[] | select(.domain=="eddie-otts-trading.'$Z'") | .id][0].include | map(.email.email) | sort')" = '["eddie@example.test","ops2@cx-test.example","ops@cx-test.example"]'
check "no app for the ambiguous host" test "$(app_count twin-peaks)" = 0
cp "$STATE" "$WORK/after8.json"; start_fake "$WORK/after8.json"
run8 --apply
check "second apply: zero writes, tokbox ALREADY_PRESENT" bash -c "test \"$(nonget_count)\" = 0 && grep -q '^CC_ACCESS: tokbox.$Z ALREADY_PRESENT$' '$OUT'"
fixture8 | jq -c '.fail.policy_update = true' > "$WORK/f8f.json"; start_fake "$WORK/f8f.json"
run8 --apply
check "a refused policy update is FAILED (exit 1), policy unchanged" bash -c "test '$RC' = 1 && grep -q '^CC_ACCESS: tokbox.$Z FAILED' '$OUT' && test \"\$(jq -c '.policies[\"app-tok\"][0].include | length' '$STATE')\" = 3"
all8="$(cat "$WORK"/out/case.* "$WORK/state/cc-access-last-run.json" "$WORK/state/cc-access-runs.log")"
check "no email address and no GoHighLevel or Cloudflare token in any output or receipt" bash -c "! grep -Eq '@|GHL-TOKEN|qc-secret-TOKEN' <<<\"\$1\"" _ "$all8"
stop_ghl

echo "== 9. FIX 2: the same exclude source (the env-file line), even with the credentials exported"
printf 'COUNCIL_ACCESS_EXCLUDE=newbox.%s\n' "$Z" > "$WORK/excl.env"
fixture > "$WORK/f9.json"; start_fake "$WORK/f9.json"
env CF_API_BASE="http://127.0.0.1:$PORT/client/v4" COUNCIL_ACCESS_STATE_DIR="$WORK/state" \
    COUNCIL_CC_EMAILS_FILE="$WORK/emails.json" COUNCIL_CC_OPERATOR_EMAILS="$OP2" \
    CLOUDFLARE_API_TOKEN="$TOKEN" CLOUDFLARE_ACCOUNT_ID=qc-acct CLOUDFLARE_ZONE_ID=wrong-zone \
    COUNCIL_ACCESS_ENV_FILE="$WORK/excl.env" TMPDIR="$WORK/tmp" "$SCRIPT" --apply >"$WORK/out/case.excl" 2>&1; RC=$?
check "excluded host newbox: silent (no CC_ACCESS line at all), zero writes to it, no app" bash -c "test '$RC' = 0 && ! grep -q 'newbox' '$WORK/out/case.excl' && test \"$(app_count newbox)\" = 0"
check "excluded host newbox: not one write was for it (only rescbox + localbox CREATED + driftbox RECONCILED)" test "$(nonget_count)" = 3
check "the run still proceeds for the others (rescbox CREATED)" bash -c "grep -q '^CC_ACCESS: rescbox.$Z CREATED' '$WORK/out/case.excl'"
check "the excluded host is absent from the receipt" bash -c "! grep -q 'newbox' '$WORK/state/cc-access-last-run.json'"

echo
if [ "$FAILS" = 0 ]; then echo "ALL $N CHECKS PASSED"; else echo "$FAILS of $N FAILED"; fi
[ "$FAILS" = 0 ]
