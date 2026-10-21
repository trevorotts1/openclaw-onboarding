#!/usr/bin/env bash
# Acceptance cases for scripts/provision-council-access.sh, run against
# fake-cloudflare-api.py on an ephemeral loopback port. No real Cloudflare call
# is possible: CF_API_BASE and the edge URL both point at the fake.
#   bash scripts/tests/provision-council-access.test.sh      (exit 0 = all PASS)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../provision-council-access.sh"
FAKE="$HERE/fake-cloudflare-api.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/council-access-test.XXXXXX")"
SCRIPT_TMP="$WORK/script-tmp"; mkdir -p "$SCRIPT_TMP" "$WORK/out"
TOKEN="qc-secret-TOKEN-123"
TOKDIR="$WORK/tunnel-tokens"   # the script's connector-token store; never the real one
export COUNCIL_TUNNEL_TOKEN_DIR="$TOKDIR"   # also covers every direct call below
FAKE_PID=""
FAILS=0; N=0

stop_fake() { [ -z "$FAKE_PID" ] || { kill "$FAKE_PID" 2>/dev/null; wait "$FAKE_PID" 2>/dev/null; FAKE_PID=""; }; }
trap 'stop_fake; rm -rf "$WORK"' EXIT

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; FAILS=$((FAILS + 1)); }
check() { # desc, then a command; PASS when it succeeds
  local d="$1"; shift; N=$((N + 1))
  if "$@" >/dev/null 2>&1; then pass "$d"; else fail "$d"; fi
}

TID="0123456789abcdef0123456789abcdef"
Z="zerohumanworkforce.com"

# fixture <slug>... : a zone with one provisionable Command Center per slug
fixture() {
  local out='{"token":"'"$TOKEN"'","account":"qc-acct","zone":{"id":"zone-real","name":"'"$Z"'"},"dns":[],"tunnels":{},"apps":[],"policies":{},"edge":{"default":{"status":302,"location":"https://sweet-wave-ca28.cloudflareaccess.com/cdn-cgi/access/login/x"}},"fail":{}}'
  local s tid i=0
  for s in "$@"; do
    i=$((i + 1)); tid="$(printf '%032x' "$((0x0123456789abcdef + i))")"; [ "$s" = qcbox ] && tid="$TID"
    out="$(jq -c --arg s "$s" --arg t "$tid" --arg z "$Z" --arg a "app-cc-$s" '
      .dns += [{id:("d-"+$s),type:"CNAME",name:($s+"."+$z),content:($t+".cfargotunnel.com"),proxied:true},
               {id:("dh-"+$s),type:"CNAME",name:($s+"-hooks."+$z),content:($t+".cfargotunnel.com"),proxied:true},
               {id:("dp-"+$s),type:"CNAME",name:($s+"-podcast."+$z),content:($t+".cfargotunnel.com"),proxied:true}]
      | .tunnels[$t] = {source:"cloudflare",config:{ingress:[
          {hostname:($s+"."+$z),service:"http://localhost:4000"},
          {hostname:($s+"-hooks."+$z),service:"http://127.0.0.1:18789",path:"^/hooks/"},
          {hostname:($s+"-podcast."+$z),service:"http://localhost:4010"},
          {service:"http_status:404"}]}}
      | .apps += [{id:$a,name:("Command Center - "+$s),domain:($s+"."+$z),type:"self_hosted",session_duration:"24h"}]
      | .policies[$a] = [{id:("pol-"+$s),name:"allow",decision:"allow",
          include:[{email:{email:($s+"@client.example")}},{email:{email:"operator@example.com"}}]}]' <<<"$out")"
  done
  printf '%s' "$out"
}

# start_fake <fixture-file> : sets PORT LOG STATE
start_fake() {
  stop_fake
  LOG="$WORK/log.$N.$RANDOM"; STATE="$WORK/state.$N.$RANDOM.json"; : > "$LOG"
  local pf="$WORK/port.$RANDOM"
  python3 -I "$FAKE" --fixture "$1" --log "$LOG" --port-file "$pf" --state-out "$STATE" &
  FAKE_PID=$!
  local i; for i in $(seq 1 400); do [ -s "$pf" ] && break; sleep 0.05; done
  PORT="$(cat "$pf")"
}

# run_script <args...> : stdout+stderr to $OUT, status to $RC. CLOUDFLARE_ZONE_ID is
# deliberately wrong to prove it is ignored.
run_script() {
  OUT="$WORK/out/case.$N.$RANDOM"
  env CF_API_BASE="http://127.0.0.1:$PORT/client/v4" \
      COUNCIL_EDGE_URL_TEMPLATE="http://127.0.0.1:$PORT/edge/%s/" \
      COUNCIL_EDGE_TRIES=2 COUNCIL_EDGE_SLEEP=0 \
      CLOUDFLARE_API_TOKEN="$TOKEN" CLOUDFLARE_ACCOUNT_ID=qc-acct CLOUDFLARE_ZONE_ID=wrong-zone \
      COUNCIL_TUNNEL_TOKEN_DIR="$TOKDIR" \
      TMPDIR="$SCRIPT_TMP" "$SCRIPT" "$@" >"$OUT" 2>&1
  RC=$?
}
state() { jq -c "$1" "$STATE"; }
last_line() { tail -n1 "$OUT"; }
only_gets() { ! grep -Ev '^GET ' "$LOG"; }
nonget_count() { grep -Evc '^GET ' "$LOG"; }

echo "== 1. syntax and bash-4 re-exec"
check "/bin/bash -n passes" /bin/bash -n "$SCRIPT"
check "re-exec guard present (same as provision-podcast-client.sh)" grep -q '_OC_BASH_REEXEC' "$SCRIPT"
# Under macOS /bin/bash 3.2 the script must hand off to bash >= 4 and still reach its env refusal (3).
env -u CLOUDFLARE_API_TOKEN -u CLOUDFLARE_ACCOUNT_ID /bin/bash "$SCRIPT" qcbox.$Z >"$WORK/out/reexec" 2>&1; RC=$?
check "runs from /bin/bash and refuses cleanly without credentials (exit 3)" test "$RC" = 3
check "refusal names the variables, never a value" grep -q 'CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID' "$WORK/out/reexec"

echo "== 2. dry-run sends GET only and prints the plan"
fixture qcbox > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z
check "dry-run exit 0" test "$RC" = 0
check "log has requests" test -s "$LOG"
check "log contains only GET lines" only_gets
check "plan printed (Access app, ingress, DNS)" bash -c "grep -q '\[plan\] POST /accounts/qc-acct/access/apps' '$OUT' && grep -q '\[plan\] PUT .*configurations' '$OUT' && grep -q '\[plan\] POST /zones/zone-real/dns_records' '$OUT'"
check "dry-run last line is PLANNED" bash -c "tail -n1 '$OUT' | grep -q '^COUNCIL_ACCESS: qcbox.$Z PLANNED'"
check "fake state untouched" test "$(state '.put_bodies | length')" = 0

echo "== 3. --apply order, rules, ingress merge"
cp "$STATE" "$WORK/orig-state.json"
run_script qcbox.$Z --apply
check "apply exit 0" test "$RC" = 0
check "last line is exactly PROVISIONED" test "$(last_line)" = "COUNCIL_ACCESS: qcbox.$Z PROVISIONED"
ln_app="$(grep -n '^POST /client/v4/accounts/qc-acct/access/apps' "$LOG" | head -1 | cut -d: -f1)"
ln_put="$(grep -n '^PUT /client/v4/accounts/qc-acct/cfd_tunnel/.*/configurations' "$LOG" | head -1 | cut -d: -f1)"
ln_dns="$(grep -n '^POST /client/v4/zones/zone-real/dns_records' "$LOG" | head -1 | cut -d: -f1)"
check "Access app POST, then tunnel PUT, then DNS POST" test -n "$ln_app" -a -n "$ln_put" -a -n "$ln_dns" -a "$ln_app" -lt "$ln_put" -a "$ln_put" -lt "$ln_dns"
check "exactly 3 writes" test "$(nonget_count)" = 3
ln_health="$(grep -n "^GET /client/v4/accounts/qc-acct/cfd_tunnel/$TID\$" "$LOG" | head -1 | cut -d: -f1)"
ln_conn="$(grep -n "^GET /client/v4/accounts/qc-acct/cfd_tunnel/$TID/connections\$" "$LOG" | head -1 | cut -d: -f1)"
ln_first_write="$(grep -Evn '^GET ' "$LOG" | head -1 | cut -d: -f1)"
check "remote path: tunnel health and connector read in this run before the first write and the DNS POST" test -n "$ln_health" -a -n "$ln_conn" -a -n "$ln_first_write" -a "$ln_health" -lt "$ln_first_write" -a "$ln_conn" -lt "$ln_first_write" -a "$ln_conn" -lt "$ln_dns"
CC_RULES="$(jq -c '.policies["app-cc-qcbox"] | [.[].include[]] | sort' "$STATE")"
NEW_RULES="$(jq -c '[.apps[] | select(.domain == "qcbox-council.'$Z'") | .id] as $i | .policies[$i[0]] | [.[].include[]] | sort' "$STATE")"
check "new app include rules equal the Command Center app's" test -n "$CC_RULES" -a "$CC_RULES" = "$NEW_RULES"
check "new app is self_hosted 'Council - qcbox' with the CC session_duration" test "$(state '.apps[] | select(.domain=="qcbox-council.'$Z'") | [.name,.type,.session_duration] | join("|")')" = '"Council - qcbox|self_hosted|24h"'
ORIG_ING="$(jq -c '.tunnels["'$TID'"].config.ingress' "$WORK/orig-state.json")"
NEW_ING="$(state '.put_bodies[0].config.ingress')"
check "PUT keeps qcbox, -hooks and -podcast rules byte-for-byte" test "$(jq -c '.[0:3]' <<<"$ORIG_ING")" = "$(jq -c '.[0:3]' <<<"$NEW_ING")"
check "PUT keeps qcbox -> http://localhost:4000" test "$(jq -r '.[0].service' <<<"$NEW_ING")" = "http://localhost:4000"
check "PUT adds qcbox-council -> http://127.0.0.1:8787" test "$(jq -c '.[3]' <<<"$NEW_ING")" = '{"hostname":"qcbox-council.'$Z'","service":"http://127.0.0.1:8787"}'
check "exactly one http_status:404 and it is last" test "$(jq '[.[] | select(.service=="http_status:404")] | length' <<<"$NEW_ING")" = 1 -a "$(jq -r '.[-1].service' <<<"$NEW_ING")" = "http_status:404"
check "proxied CNAME -> <tunnel>.cfargotunnel.com created" test "$(state '.dns[] | select(.name=="qcbox-council.'$Z'") | [.type,.content,.proxied] | join("|")')" = '"CNAME|'$TID'.cfargotunnel.com|true"'

echo "== 4. second --apply is a no-op"
cp "$STATE" "$WORK/provisioned.json"; start_fake "$WORK/provisioned.json"
run_script qcbox.$Z --apply
check "exit 0" test "$RC" = 0
check "zero non-GET requests" test "$(nonget_count)" = 0
check "prints ALREADY_PROVISIONED" test "$(last_line)" = "COUNCIL_ACCESS: qcbox.$Z ALREADY_PROVISIONED"

echo "== 5. rollback"
fixture qcbox | jq -c '.fail.dns_create = true' > "$WORK/f.json"; start_fake "$WORK/f.json"
cp "$STATE" "$WORK/orig-state.json"
run_script qcbox.$Z --apply
check "DNS create 500: exits non-zero" test "$RC" != 0
check "DNS create 500: prints FAILED" bash -c "tail -n1 '$OUT' | grep -q '^COUNCIL_ACCESS: qcbox.$Z FAILED'"
check "DNS create 500: final tunnel config equals the original" test "$(state '.tunnels["'$TID'"].config')" = "$(jq -c '.tunnels["'$TID'"].config' "$WORK/orig-state.json")"
check "DNS create 500: no council CNAME remains" test "$(state '[.dns[] | select(.name|test("-council."))] | length')" = 0
check "DNS create 500: Access app kept, rollback is a merge-PUT" test "$(state '[.apps[]|select(.domain|test("-council."))]|length')" = 1 -a "$(state '.put_bodies|length')" = 2

fixture qcbox | jq -c '.edge["qcbox-council.'$Z'"] = {status:200}' > "$WORK/f.json"; start_fake "$WORK/f.json"
cp "$STATE" "$WORK/orig-state.json"
run_script qcbox.$Z --apply
check "edge 200 without Access redirect: exits non-zero" test "$RC" != 0
check "edge 200 without Access redirect: prints FAILED" bash -c "tail -n1 '$OUT' | grep -q '^COUNCIL_ACCESS: qcbox.$Z FAILED'"
check "edge 200: final tunnel config equals the original" test "$(state '.tunnels["'$TID'"].config')" = "$(jq -c '.tunnels["'$TID'"].config' "$WORK/orig-state.json")"
check "edge 200: no council CNAME remains" test "$(state '[.dns[] | select(.name|test("-council."))] | length')" = 0

echo "== 6. refusals send zero writes"
fixture qcbox | jq -c '.apps = [] | .policies = {}' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "no CC Access app: NOT_PROVISIONED, zero writes, exit 0" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z NOT_PROVISIONED'"

fixture qcbox | jq -c '.dns = []' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "no CC CNAME: NOT_PROVISIONED, zero writes" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z NOT_PROVISIONED'"

fixture qcbox | jq -c '.tunnels["'$TID'"].status = "down"' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "down tunnel (apply): TUNNEL_DOWN, zero writes, exit 0" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z TUNNEL_DOWN'"
check "down tunnel: names the tunnel and its status" bash -c "tail -n1 '$OUT' | grep -q 'tunnel $TID for qcbox.$Z is down'"
check "down tunnel: no council app, CNAME or ingress written" test "$(state '[.apps[]|select(.domain|test("-council."))]|length')" = 0 -a "$(state '.put_bodies|length')" = 0
run_script qcbox.$Z
check "down tunnel (dry-run): TUNNEL_DOWN, not PLANNED" bash -c "test '$RC' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z TUNNEL_DOWN'"
fixture qcbox | jq -c '.tunnels["'$TID'"].status = "inactive"' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "inactive tunnel: TUNNEL_DOWN, zero writes" bash -c "test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z TUNNEL_DOWN'"

fixture qcbox | jq -c '.tunnels["'$TID'"].config.ingress[0].service = "http://172.16.1.2:4000"' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "docker-bridge CC origin: ORIGIN_NOT_LOOPBACK, zero writes, exit 0" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z ORIGIN_NOT_LOOPBACK.*172.16.1.2:4000'"
fixture qcbox | jq -c '.tunnels["'$TID'"].config.ingress[0].service = "http://127.0.0.1:4000"' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z
check "127.0.0.1 CC origin is loopback: PLANNED" bash -c "test '$RC' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z PLANNED'"

fixture qcbox | jq -c --arg z "$Z" '.tunnels["'$TID'"].config.ingress = [
    {hostname:("qcbox."+$z),path:"^/hooks",service:"http://127.0.0.1:18789"},
    {hostname:("qcbox."+$z),path:"/zhc-cohort*",service:"http://localhost:3457"}] + .tunnels["'$TID'"].config.ingress' > "$WORK/f.json"
start_fake "$WORK/f.json"; cp "$STATE" "$WORK/orig-state.json"
run_script qcbox.$Z --apply
check "path-scoped CC rules listed first: PROVISIONED, not FAILED" bash -c "test '$RC' = 0 && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z PROVISIONED'"
check "path-scoped CC rules first: PUT keeps all three CC rules in order" test "$(state '.put_bodies[0].config.ingress[0:3]')" = "$(jq -c '.tunnels["'$TID'"].config.ingress[0:3]' "$WORK/orig-state.json")"

echo "== 6b. local-managed Command Center tunnel: a dedicated council-<slug> tunnel"
fixture qcbox | jq -c '.tunnels["'$TID'"] = {source:"local",config:null}' > "$WORK/f.json"; start_fake "$WORK/f.json"
cp "$STATE" "$WORK/orig-state.json"
run_script qcbox.$Z
check "local tunnel (dry-run): exit 0, GET only, PLANNED" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z PLANNED'"
check "local tunnel (dry-run): prints 'would create tunnel council-qcbox' and the token save" bash -c "grep -q 'would create tunnel council-qcbox' '$OUT' && grep -q 'would save the connector token for council-qcbox' '$OUT'"
check "local tunnel (dry-run): plan lists app, tunnel and ingress writes" bash -c "grep -q '\[plan\] POST /accounts/qc-acct/access/apps' '$OUT' && grep -q '\[plan\] POST /accounts/qc-acct/cfd_tunnel\$' '$OUT' && grep -q '\[plan\] PUT .*configurations' '$OUT'"
check "local tunnel (dry-run): plans NO DNS write before a connector" bash -c "! grep -q 'dns_records' '$OUT'"
check "local tunnel (dry-run): says the DNS record is held until the connector is active" bash -c "grep -q '\[hold\] no DNS record for qcbox-council.$Z: tunnel council-qcbox has no active connection yet (zero DNS writes' '$OUT'"
check "local tunnel (dry-run): last line says apply ends CONNECTOR_PENDING" bash -c "tail -n1 '$OUT' | grep -q 'PLANNED dry-run: .*no DNS write until tunnel council-qcbox has an active connection, so apply ends CONNECTOR_PENDING'"
check "local tunnel (dry-run): no tunnel created, no token file" bash -c "test '$(state '.tunnels | length')' = 1 && test ! -e '$TOKDIR/council-qcbox.token'"
run_script qcbox.$Z --apply
check "local tunnel (apply): exit 0, CONNECTOR_PENDING" bash -c "test '$RC' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONNECTOR_PENDING'"
check "local tunnel (apply): exactly 3 writes (app, tunnel, ingress), no DNS write" bash -c "test '$(nonget_count)' = 3 && ! grep -Eq '^(POST|PUT|DELETE|PATCH) .*/dns_records' '$LOG'"
check "local tunnel (apply): no DNS record exists for the council host" test "$(state '[.dns[] | select(.name=="qcbox-council.'$Z'")] | length')" = 0
check "local tunnel (apply): the pending line says zero DNS writes" bash -c "tail -n1 '$OUT' | grep -q 'no DNS record created (zero DNS writes)'"
check "local tunnel (apply): no edge request for a host with no DNS record" bash -c "! grep -q '^GET /edge/' '$LOG'"
NEWT="$(state '[.tunnels | to_entries[] | select(.value.name == "council-qcbox") | .key][0]' | tr -d '"')"
check "a remote-managed tunnel named council-qcbox was created" test -n "$NEWT" -a "$NEWT" != null -a "$(state '.tunnels["'$NEWT'"].source')" = '"cloudflare"'
check "council-qcbox ingress: qcbox-council -> http://127.0.0.1:8787, then 404" test "$(state '.tunnels["'$NEWT'"].config.ingress')" = '[{"hostname":"qcbox-council.'$Z'","service":"http://127.0.0.1:8787"},{"service":"http_status:404"}]'
check "the local Command Center tunnel was not touched" test "$(state '.tunnels["'$TID'"]')" = "$(jq -c '.tunnels["'$TID'"]' "$WORK/orig-state.json")"
check "token file saved with mode 600 in a mode 700 dir" bash -c "test \"\$(stat -f %Lp '$TOKDIR/council-qcbox.token')\" = 600 && test \"\$(stat -f %Lp '$TOKDIR')\" = 700"
check "token file holds the connector token" test "$(cat "$TOKDIR/council-qcbox.token")" = "qc-tunnel-TOKEN-$NEWT"
check "connector token value appears in no output" bash -c "! grep -rq -- 'qc-tunnel-TOKEN' '$WORK/out'"
cp "$STATE" "$WORK/ded.json"; start_fake "$WORK/ded.json"
run_script qcbox.$Z --apply
check "second apply, still no connector: zero writes, CONNECTOR_PENDING, still no DNS record" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONNECTOR_PENDING' && test '$(state '[.dns[] | select(.name=="qcbox-council.'$Z'")] | length')' = 0"
run_script qcbox.$Z
check "dry-run, no connector, nothing else to write: CONNECTOR_PENDING, GET only" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONNECTOR_PENDING'"
jq -c '(.tunnels | to_entries[] | select(.value.name == "council-qcbox") | .key) as $k | .tunnels[$k].conns = [{id:"c1",is_pending_reconnect:false}]' "$WORK/ded.json" > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z
check "connector up (dry-run): plans exactly the DNS write, PLANNED" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && grep -q '\[plan\] POST /zones/zone-real/dns_records' '$OUT' && ! grep -q '\[hold\]' '$OUT' && test \"\$(grep -c '\[plan\]' '$OUT')\" = 1 && tail -n1 '$OUT' | grep -q 'qcbox.$Z PLANNED'"
run_script qcbox.$Z --apply
check "connector up (apply): PROVISIONED with exactly 1 write, the DNS POST" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 1 && grep -Eq '^POST /client/v4/zones/zone-real/dns_records$' '$LOG' && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z PROVISIONED'"
check "connector up: the connections read comes before the DNS POST" bash -c "c=\$(grep -n '^GET .*/cfd_tunnel/$NEWT/connections' '$LOG' | head -1 | cut -d: -f1); d=\$(grep -n '^POST .*/dns_records' '$LOG' | head -1 | cut -d: -f1); test -n \"\$c\" -a -n \"\$d\" && test \"\$c\" -lt \"\$d\""
check "connector up: proxied CNAME points at the council tunnel" test "$(state '.dns[] | select(.name=="qcbox-council.'$Z'") | [.content,.proxied] | join("|")')" = '"'$NEWT'.cfargotunnel.com|true"'
check "connector up: edge gate ran after the record exists" bash -c "grep -q '^GET /edge/qcbox-council.$Z/' '$LOG'"
cp "$STATE" "$WORK/ded-up.json"; start_fake "$WORK/ded-up.json"
run_script qcbox.$Z --apply
check "connector still up: ALREADY_PROVISIONED, zero writes" bash -c "test '$(nonget_count)' = 0 && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z ALREADY_PROVISIONED'"
jq -c --arg k "$NEWT" '.tunnels[$k].conns = []' "$WORK/ded-up.json" > "$WORK/f.json"; start_fake "$WORK/f.json"; cp "$STATE" "$WORK/orig-state.json"
run_script qcbox.$Z --apply
check "connector gone after the record exists: CONNECTOR_DOWN, zero writes, exit 0" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONNECTOR_DOWN.*nothing deleted'"
check "connector gone: the DNS record, app and tunnel are all kept" test "$(state '[.dns, .apps, .tunnels]')" = "$(jq -c '[.dns, .apps, .tunnels]' "$WORK/orig-state.json")"
run_script qcbox.$Z
check "connector gone (dry-run): CONNECTOR_DOWN, not PLANNED" bash -c "test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONNECTOR_DOWN'"
fixture qcbox | jq -c '.tunnels["'$TID'"] = {source:"local",config:null} | .fail.connections = true | .tunnels["c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0"] = {name:"council-qcbox",source:"cloudflare",config:null}' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "council tunnel connections unreadable: FAILED, zero writes" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z FAILED.*connections'"
fixture qcbox | jq -c '.tunnels["'$TID'"] = {source:"local",config:null} | .tunnels["cccccccccccccccccccccccccccccccc"] = {name:"council-qcbox",source:"local",config:null}' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "council tunnel itself local-managed: PENDING_LOCAL_TUNNEL, zero writes" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z PENDING_LOCAL_TUNNEL.*council-qcbox'"
check "council tunnel local-managed: no ingress lines and no instruction aimed at the box" bash -c "! grep -Eq 'hostname: |service: http|On the box|on the box|add the ingress' '$OUT'"
fixture qcbox | jq -c --arg z "$Z" '.tunnels["'$TID'"] = {source:"local",config:null} | .dns += [{id:"x9",type:"CNAME",name:("qcbox-council."+$z),content:"ffffffffffffffffffffffffffffffff.cfargotunnel.com"}]' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "local tunnel with a stray council CNAME: CONFLICT, zero writes" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONFLICT'"

echo "== 6c. COUNCIL_TUNNEL_OVERRIDES maps trevor to council-desktop"
DESK="dddddddddddddddddddddddddddddddd"
fixture trevor | jq -c --arg z "$Z" --arg d "$DESK" '
  (.dns[] | select(.name == ("trevor."+$z)) | .content | sub("\\.cfargotunnel\\.com$"; "")) as $t
  | .tunnels[$t] = {name:"command-center",source:"local",config:null}
  | .tunnels[$d] = {name:"council-desktop",source:"cloudflare",config:{ingress:[{hostname:("council."+$z),service:"http://127.0.0.1:8787"},{service:"http_status:404"}]}}' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script trevor.$Z
check "default override: dry-run plans no new tunnel for trevor" bash -c "test '$RC' = 0 && ! grep -q 'would create tunnel' '$OUT' && grep -q 'rides its own remote-managed tunnel council-desktop' '$OUT'"
run_script trevor.$Z --apply
check "override: PROVISIONED on council-desktop with 3 writes (app, ingress, DNS)" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 3 && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: trevor.$Z PROVISIONED'"
check "override: no tunnel named council-trevor exists" test "$(state '[.tunnels[] | select(.name == "council-trevor")] | length')" = 0
check "override: council-desktop keeps council.$Z and gains trevor-council" test "$(state '.tunnels["'$DESK'"].config.ingress | map(.hostname // "*") | join(",")')" = '"council.'$Z',trevor-council.'$Z',*"'
check "override: CNAME points at council-desktop" test "$(state '.dns[] | select(.name=="trevor-council.'$Z'") | .content')" = '"'$DESK'.cfargotunnel.com"'
check "override: token saved as council-desktop.token, mode 600" test "$(stat -f %Lp "$TOKDIR/council-desktop.token")" = 600
start_fake "$WORK/f.json"
OUT="$WORK/out/case.ovr"; env CF_API_BASE="http://127.0.0.1:$PORT/client/v4" CLOUDFLARE_API_TOKEN="$TOKEN" CLOUDFLARE_ACCOUNT_ID=qc-acct \
  COUNCIL_TUNNEL_OVERRIDES="" COUNCIL_TUNNEL_TOKEN_DIR="$TOKDIR" TMPDIR="$SCRIPT_TMP" "$SCRIPT" trevor.$Z >"$OUT" 2>&1
check "empty COUNCIL_TUNNEL_OVERRIDES: trevor would get council-trevor" grep -q 'would create tunnel council-trevor' "$OUT"

echo "== 6d. hostname length boundary (a DNS label is 63 characters at most)"
S55="$(printf 'a%.0s' $(seq 1 55))"; S56="$(printf 'b%.0s' $(seq 1 56))"
fixture "$S55" "$S56" > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script "$S55.$Z"
check "55-character slug (council label = 63): PLANNED" bash -c "test '$RC' = 0 && tail -n1 '$OUT' | grep -q '^COUNCIL_ACCESS: $S55.$Z PLANNED'"
check "55-character slug: council label is exactly 63 characters" test "$(printf '%s' "${S55}-council" | wc -c | tr -d ' ')" = 63
run_script "$S56.$Z" --apply
check "56-character slug (council label = 64): FAILED, zero writes" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q '^COUNCIL_ACCESS: $S56.$Z FAILED.*63-character'"

fixture qcbox | jq -c '.tunnels["'$TID'"].conns = []' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "connector down (apply): CONNECTOR_DOWN, zero writes, exit 0" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONNECTOR_DOWN'"
check "connector down: not reported as PROVISIONED/PLANNED" bash -c "! grep -Eq 'PROVISIONED|PLANNED' '$OUT'"
run_script qcbox.$Z
check "connector down (dry-run): CONNECTOR_DOWN, not PLANNED" bash -c "test '$RC' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONNECTOR_DOWN'"
fixture qcbox | jq -c '.tunnels["'$TID'"].conns = [{id:"c9",is_pending_reconnect:true}]' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "only a pending-reconnect connection counts as down" bash -c "test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONNECTOR_DOWN'"
fixture qcbox | jq -c '.fail.connections = true' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "connections endpoint error: FAILED, zero writes" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z FAILED'"
cp "$WORK/provisioned.json" "$WORK/f.json"; jq -c '.tunnels["'$TID'"].conns = []' "$WORK/provisioned.json" > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "already-provisioned host with a dead connector is CONNECTOR_DOWN, not ALREADY_PROVISIONED, zero writes" bash -c "test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONNECTOR_DOWN'"

fixture qcbox | jq -c '.dns += [{id:"x1",type:"CNAME",name:"qcbox-council.'$Z'",content:"ffffffffffffffffffffffffffffffff.cfargotunnel.com",proxied:true}]' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "council CNAME at another tunnel: CONFLICT, zero writes, exit 1" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONFLICT'"

fixture qcbox | jq -c '.apps += [{id:"app-old",name:"Council - qcbox",domain:"qcbox-council.'$Z'",type:"self_hosted",session_duration:"24h"}] | .policies["app-old"] = [{id:"po",decision:"allow",include:[{email:{email:"stranger@evil.example"}}]}]' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "existing council app with different rules: FAILED before any routing" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z FAILED'"

fixture qcbox | jq -c '.policies["app-cc-qcbox"][0].include = [{everyone:{}}]' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "CC app that allows everyone is never copied" bash -c "test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'NOT_PROVISIONED'"

echo "== 7. --all"
fixture alpha beta gamma | jq -c --arg z "$Z" '
  .dns += [{id:"c1",type:"CNAME",name:("council."+$z),content:"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee.cfargotunnel.com"},
           {id:"c2",type:"CNAME",name:("alpha-council."+$z),content:"00000000000000000123456789abcdf0.cfargotunnel.com"},
           {id:"c3",type:"CNAME",name:("www."+$z),content:"elsewhere.example.net"},
           {id:"c4",type:"A",name:("a."+$z),content:"192.0.2.1"}]' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script --all
check "--all dry-run exit 0, GET only" bash -c "test '$RC' = 0 && ! grep -Ev '^GET ' '$LOG'"
check "--all plans exactly the 3 Command Center hosts" test "$(grep '^COUNCIL_ACCESS:' "$OUT" | sed -E 's/^COUNCIL_ACCESS: ([^ ]+) .*/\1/' | sort | tr '\n' ' ')" = "alpha.$Z beta.$Z gamma.$Z "
check "--all prints one result line per host" test "$(grep -c '^COUNCIL_ACCESS:' "$OUT")" = 3
run_script --all --json
check "--json prints a JSON array" bash -c "jq -e 'length == 3 and all(.[]; .status == \"PLANNED\")' '$OUT'"

echo "== 7b. --all skips what is not a Command Center and stays quiet about it"
ATID="$(printf '%032x' "$((0x0123456789abcdef + 1))")"
fixture alpha beta | jq -c --arg z "$Z" --arg t "$ATID" '
  .dns += ([ "rescue-alpha", "alpha-gw", "alpha-webhook", "weird", "norule" ] | map({id:("x-"+.),type:"CNAME",name:(.+"."+$z),content:($t+".cfargotunnel.com"),proxied:true}))
  | .tunnels[$t].config.ingress = ([
      {hostname:("rescue-alpha."+$z),service:"ssh://localhost:22"},
      {hostname:("alpha-gw."+$z),service:"http://127.0.0.1:18789"},
      {hostname:("weird."+$z),service:"http://localhost:3000"}] + .tunnels[$t].config.ingress)' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script --all
check "--all with non-CC hosts: exit 0, GET only" bash -c "test '$RC' = 0 && ! grep -Ev '^GET ' '$LOG'"
for h in rescue-alpha alpha-gw alpha-webhook weird norule; do
  check "$h is SKIPPED_NOT_CC" bash -c "grep -q '^COUNCIL_ACCESS: $h.$Z SKIPPED_NOT_CC' '$OUT'"
done
check "skipped hosts are never provisioned or planned" bash -c "! grep -E '^COUNCIL_ACCESS: (rescue-alpha|alpha-gw|alpha-webhook|weird|norule)\.[^ ]* (PLANNED|PROVISIONED|FAILED)' '$OUT'"
check "the 2 real Command Centers are still PLANNED" test "$(grep -c '^COUNCIL_ACCESS: .* PLANNED' "$OUT")" = 2
check "skip reason names the wrong target" bash -c "grep -q 'weird.$Z SKIPPED_NOT_CC.*http://localhost:3000' '$OUT' && grep -q 'norule.$Z SKIPPED_NOT_CC.*no ingress rule' '$OUT'"
check "rescue host skip names its ssh:// service" bash -c "grep -q 'rescue-alpha.$Z SKIPPED_NOT_CC.*ssh://localhost:22' '$OUT'"
run_script --all --apply
check "--all --apply: only the 2 real Command Centers are written (6 writes)" test "$(nonget_count)" = 6
check "--all --apply: final exit 0 and no -council record for a skipped host" bash -c "test '$RC' = 0 && test '$(state '[.dns[]|select(.name|test("^(rescue-alpha|alpha-gw|alpha-webhook|weird|norule)-council"))]|length')' = 0"
run_script --all --json
check "--json carries SKIPPED_NOT_CC entries" bash -c "jq -e '[.[]|select(.status==\"SKIPPED_NOT_CC\")]|length == 5' '$OUT'"
fixture qcbox | jq -c '.tunnels["'$TID'"] = {source:"local",config:null}' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script --all
check "--all: a local-managed Command Center gets a dedicated tunnel plan, not skipped" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && grep -q 'qcbox.$Z PLANNED' '$OUT' && grep -q 'would create tunnel council-qcbox' '$OUT'"

echo "== 7c. --all classifies by service and names every skip"
ATID="$(printf '%032x' "$((0x0123456789abcdef + 1))")"; BTID="$(printf '%032x' "$((0x0123456789abcdef + 2))")"
LTID="llllllllllllllllllllllllllllllll"
fixture alpha beta monique convoplay | jq -c --arg z "$Z" --arg t "$ATID" --arg l "$LTID" '
  .dns += ([ "alpha-openclawdashboard", "flows", "n8n-star-bobatoon", "audio", "emptyhost" ] | map({id:("x-"+.),type:"CNAME",name:(.+"."+$z),content:($t+".cfargotunnel.com"),proxied:true}))
  | .dns += [{id:"x-lod",type:"CNAME",name:("beta-openclawdashboard."+$z),content:($l+".cfargotunnel.com"),proxied:true}]
  | .tunnels[$l] = {source:"local",config:null}
  | .tunnels[$t].config.ingress = ([
      {hostname:("alpha-openclawdashboard."+$z),service:"http://127.0.0.1:18789"},
      {hostname:("flows."+$z),service:"http://localhost:5678"},
      {hostname:("n8n-star-bobatoon."+$z),service:"http://localhost:5678"},
      {hostname:("audio."+$z),service:"http://localhost:8080"}] + .tunnels[$t].config.ingress)
  | (.dns[] | select(.name == ("monique."+$z)) | .content | sub("\\.cfargotunnel\\.com$"; "")) as $m
  | .tunnels[$m].config.ingress[0].service = "http://172.16.1.2:4000"
  | (.dns[] | select(.name == ("convoplay."+$z)) | .content | sub("\\.cfargotunnel\\.com$"; "")) as $c
  | .tunnels[$c].config.ingress = [{hostname:("convoplay."+$z),path:"^/hooks",service:"http://127.0.0.1:18789"}] + .tunnels[$c].config.ingress' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script --all --apply
for h in alpha-openclawdashboard flows n8n-star-bobatoon audio emptyhost beta-openclawdashboard; do
  check "$h is SKIPPED_NOT_CC and named in the output" bash -c "grep -q '^COUNCIL_ACCESS: $h.$Z SKIPPED_NOT_CC' '$OUT'"
done
check "skip reasons name the service (n8n :5678, empty ingress)" bash -c "grep -q 'flows.$Z SKIPPED_NOT_CC.*http://localhost:5678' '$OUT' && grep -q 'emptyhost.$Z SKIPPED_NOT_CC.*no ingress rule' '$OUT'"
check "an -openclawdashboard host on a local-managed tunnel is skipped, never given a tunnel" bash -c "grep -q 'beta-openclawdashboard.$Z SKIPPED_NOT_CC' '$OUT' && ! grep -q 'council-beta-openclawdashboard' '$OUT'"
check "no <x>-openclawdashboard-council record or council tunnel is ever created" test "$(state '[(.dns[] | select(.name|test("openclawdashboard-council"))), (.tunnels[] | select((.name // "")|test("openclawdashboard")))] | length')" = 0
check "monique (docker-bridge origin) reaches provisioning and is ORIGIN_NOT_LOOPBACK" bash -c "grep -q '^COUNCIL_ACCESS: monique.$Z ORIGIN_NOT_LOOPBACK' '$OUT'"
check "convoplay (path rule first) is PROVISIONED" bash -c "grep -q '^COUNCIL_ACCESS: convoplay.$Z PROVISIONED' '$OUT'"
check "alpha and beta PROVISIONED; exit 0" bash -c "test '$RC' = 0 && grep -q '^COUNCIL_ACCESS: alpha.$Z PROVISIONED' '$OUT' && grep -q '^COUNCIL_ACCESS: beta.$Z PROVISIONED' '$OUT'"
check "exactly 9 writes (3 hosts x 3)" test "$(nonget_count)" = 9

echo "== 7d. default excludes skip the test tenants"
fixture alpha acme-dental-c436 smoke probe > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script --all
check "default: only alpha is considered" test "$(grep '^COUNCIL_ACCESS:' "$OUT" | sed -E 's/^COUNCIL_ACCESS: ([^ ]+) .*/\1/' | tr '\n' ' ')" = "alpha.$Z "
run_script --all --json
check "default excludes never reach the JSON report" bash -c "jq -e 'map(.cc_host) == [\"alpha.$Z\"]' '$OUT'"
start_fake "$WORK/f.json"
OUT="$WORK/out/case.excl"; env CF_API_BASE="http://127.0.0.1:$PORT/client/v4" CLOUDFLARE_API_TOKEN="$TOKEN" CLOUDFLARE_ACCOUNT_ID=qc-acct \
  COUNCIL_ACCESS_EXCLUDE="council.$Z" COUNCIL_TUNNEL_TOKEN_DIR="$TOKDIR" TMPDIR="$SCRIPT_TMP" "$SCRIPT" --all >"$OUT" 2>&1
check "COUNCIL_ACCESS_EXCLUDE overrides the default" test "$(grep -c '^COUNCIL_ACCESS: .* PLANNED' "$OUT")" = 4
run_script rescue-alpha.$Z
check "explicit rescue- host is refused (exit 2)" test "$RC" = 2
run_script alpha-openclawdashboard.$Z
check "explicit -openclawdashboard host is refused (exit 2)" test "$RC" = 2

echo "== 8. zone is resolved by name, never from CLOUDFLARE_ZONE_ID"
fixture qcbox > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "first request is GET /zones?name=$Z" test "$(head -n1 "$LOG")" = "GET /client/v4/zones?name=$Z"
check "no request touches the wrong zone id" bash -c "! grep -q wrong-zone '$LOG'"
check "every zone-scoped request uses the id from the name lookup" bash -c "grep '/zones/' '$LOG' | grep -v '^GET /client/v4/zones?name=' | grep -qv '/zones/zone-real/' && exit 1; grep -q '/zones/zone-real/' '$LOG'"

echo "== 9. the token never leaks"
check "token appears in no case's stdout or stderr" bash -c "! grep -rq -- '$TOKEN' '$WORK/out'"
check "no temp file is left in the script's TMPDIR" test -z "$(ls -A "$SCRIPT_TMP")"
check "token appears in no file in the script's TMPDIR" bash -c "! grep -rq -- '$TOKEN' '$SCRIPT_TMP'"
check "no connector token appears in any case's stdout or stderr" bash -c "! grep -rq -- 'qc-tunnel-TOKEN' '$WORK/out'"

echo
if [ "$FAILS" = 0 ]; then echo "ALL $N CHECKS PASS"; exit 0; else echo "$FAILS of $N CHECKS FAILED"; exit 1; fi
