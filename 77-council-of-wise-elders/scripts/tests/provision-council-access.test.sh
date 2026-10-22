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
      COUNCIL_EDGE_URL_TEMPLATE="${TEST_EDGE_TPL:-http://127.0.0.1:$PORT/edge/%s/}" \
      COUNCIL_EDGE_TRIES=2 COUNCIL_EDGE_SLEEP=0 \
      CLOUDFLARE_API_TOKEN="$TOKEN" CLOUDFLARE_ACCOUNT_ID=qc-acct CLOUDFLARE_ZONE_ID=wrong-zone \
      COUNCIL_TUNNEL_TOKEN_DIR="$TOKDIR" PATH="${TEST_PATH:-$PATH}" \
      COUNCIL_CONTAINER_HOSTS="${TEST_CONTAINER_HOSTS:-}" \
      COUNCIL_ACCESS_EXCLUDE="${TEST_EXCLUDE:-}" COUNCIL_ACCESS_ENV_FILE="${TEST_ENV_FILE:-/nonexistent}" \
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

echo "== 5b. edge gate asks the authoritative nameservers (stub dig + stub curl, no network)"
# Stub curl: API calls pass through to the real curl (the fake server); a call to
# https://*-council.* is the edge gate. Without --resolve it fails like a resolver
# holding a cached "no such name" (exit 6) unless STUB_SYS=ok; with --resolve it
# answers per STUB_EDGE (access | 200 | other). Stub dig: A/AAAA answers from any
# @server, the first STUB_DIG_EMPTY A (and AAAA) queries answer nothing; NS -> fallback-ns.example.
STUB="$WORK/stub"; mkdir -p "$STUB"
export STUB_REAL_CURL; STUB_REAL_CURL="$(command -v curl)"
export STUB_CURL_LOG="$WORK/stub-curl.log" STUB_DIG_LOG="$WORK/stub-dig.log" STUB_EDGE=access STUB_SYS=fail STUB_DIG_EMPTY=0
cat > "$STUB/curl" <<'STUBEOF'
#!/bin/bash
edge=""; for a in "$@"; do case "$a" in https://*-council.*) edge=1 ;; esac; done
[ -n "$edge" ] || exec "$STUB_REAL_CURL" "$@"
printf '%s\n' "$*" >> "$STUB_CURL_LOG"
case " $* " in *" --resolve "*) ;; *) [ "$STUB_SYS" = ok ] || { echo "curl: (6) Could not resolve host" >&2; exit 6; } ;; esac
case "$STUB_EDGE" in
  access) printf 'HTTP/2 302\r\nlocation: https://sweet-wave-ca28.cloudflareaccess.com/cdn-cgi/access/login/x\r\n\r\n' ;;
  200)    printf 'HTTP/2 200\r\ncontent-type: text/html\r\n\r\n' ;;
  other)  printf 'HTTP/2 302\r\nlocation: https://elsewhere.example.com/login\r\n\r\n' ;;
esac
STUBEOF
cat > "$STUB/dig" <<'STUBEOF'
#!/bin/bash
printf '%s\n' "$*" >> "$STUB_DIG_LOG"
case "$*" in
  *" NS "*) echo "fallback-ns.example." ;;
  *" A")    [ "$(grep -c ' A$' "$STUB_DIG_LOG")" -le "$STUB_DIG_EMPTY" ] || echo 104.16.1.1 ;;
  *" AAAA") [ "$(grep -c ' AAAA$' "$STUB_DIG_LOG")" -le "$STUB_DIG_EMPTY" ] || echo 2606:4700::1 ;;
esac
STUBEOF
chmod +x "$STUB/curl" "$STUB/dig"
# A PATH with every tool except dig, for the "dig missing" case.
FARM="$WORK/farm"; mkdir -p "$FARM"
for d in /opt/homebrew/bin /usr/local/bin /usr/bin /bin /usr/sbin /sbin; do
  [ -d "$d" ] || continue
  for f in "$d"/*; do b="${f##*/}"; [ "$b" = dig ] || [ -e "$FARM/$b" ] || ln -s "$f" "$FARM/$b"; done
done
NODIG="$WORK/nodig"; mkdir -p "$NODIG"; cp "$STUB/curl" "$NODIG/curl"
stub_reset() { : > "$STUB_CURL_LOG"; : > "$STUB_DIG_LOG"; }
PIN="--resolve qcbox-council.$Z:443:104.16.1.1,[2606:4700::1]"
NS_FIXTURE() { fixture qcbox | jq -c '.zone.name_servers = ["ns-a.example","ns-b.example"]'; }

NS_FIXTURE > "$WORK/f.json"; start_fake "$WORK/f.json"; stub_reset
TEST_PATH="$STUB:$PATH" TEST_EDGE_TPL="https://%s/" run_script qcbox.$Z --apply
check "auth: system resolver fails but --resolve to the authoritative answer passes (PROVISIONED)" test "$(last_line)" = "COUNCIL_ACCESS: qcbox.$Z PROVISIONED"
check "auth: curl was pinned to the A and AAAA answers" grep -qF -- "$PIN https://qcbox-council.$Z/" "$STUB_CURL_LOG"
check "auth: asked the zone's API name_servers, not the system resolver" bash -c "grep -qx '+short +norecurse +time=3 +tries=1 @ns-a.example qcbox-council.$Z A' '$STUB_DIG_LOG' && ! grep -q ' NS ' '$STUB_DIG_LOG'"
check "auth: the step line names the addresses and the server" grep -qF "edge gate try 1: qcbox-council.$Z -> 104.16.1.1,[2606:4700::1] (authoritative ns-a.example)" "$OUT"

fixture qcbox > "$WORK/f.json"; start_fake "$WORK/f.json"; stub_reset
TEST_PATH="$STUB:$PATH" TEST_EDGE_TPL="https://%s/" run_script qcbox.$Z --apply
check "no name_servers in the zone object: falls back to dig NS and still passes" bash -c "test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z PROVISIONED' && grep -q ' NS $Z\$' '$STUB_DIG_LOG' && grep -q '@fallback-ns.example qcbox-council.$Z A' '$STUB_DIG_LOG'"

NS_FIXTURE > "$WORK/f.json"; start_fake "$WORK/f.json"; stub_reset
STUB_DIG_EMPTY=2 TEST_PATH="$STUB:$PATH" TEST_EDGE_TPL="https://%s/" run_script qcbox.$Z --apply
check "retry re-queries: try 1 has no record yet (plain curl fails), try 2 is pinned and passes" bash -c "test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z PROVISIONED' && ! sed -n 1p '$STUB_CURL_LOG' | grep -q -- --resolve && sed -n 2p '$STUB_CURL_LOG' | grep -qF -- '$PIN'"
check "retry re-queries: both nameservers asked on try 1, asked again on try 2" test "$(grep -c ' A$' "$STUB_DIG_LOG")" = 3

NS_FIXTURE > "$WORK/f.json"; start_fake "$WORK/f.json"; stub_reset; cp "$STATE" "$WORK/orig-state.json"
STUB_EDGE=200 TEST_PATH="$STUB:$PATH" TEST_EDGE_TPL="https://%s/" run_script qcbox.$Z --apply
check "auth: a pinned 200 still fails the gate and rolls back" bash -c "tail -n1 '$OUT' | grep -q '^COUNCIL_ACCESS: qcbox.$Z FAILED edge gate failed (HTTP 200, Location none, pinned to 104.16.1.1,\[2606:4700::1\]); rolled back'"
check "auth: pinned 200: no council CNAME remains" test "$(state '[.dns[] | select(.name|test("-council."))] | length')" = 0
check "auth: every try asks the authoritative server again (2 tries, 2 A queries)" test "$(grep -c ' A$' "$STUB_DIG_LOG")" = 2

NS_FIXTURE > "$WORK/f.json"; start_fake "$WORK/f.json"; stub_reset
STUB_EDGE=other TEST_PATH="$STUB:$PATH" TEST_EDGE_TPL="https://%s/" run_script qcbox.$Z --apply
check "auth: a pinned 302 to a non-Access host still fails the gate" bash -c "tail -n1 '$OUT' | grep -q '^COUNCIL_ACCESS: qcbox.$Z FAILED edge gate failed (HTTP 302, Location https://elsewhere.example.com/login'"

NS_FIXTURE > "$WORK/f.json"; start_fake "$WORK/f.json"; stub_reset
check "the no-dig PATH really has no dig" bash -c "! PATH='$NODIG:$FARM' command -v dig"
STUB_SYS=ok TEST_PATH="$NODIG:$FARM" TEST_EDGE_TPL="https://%s/" run_script qcbox.$Z --apply
check "dig missing: falls back to plain curl and passes" bash -c "test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z PROVISIONED' && test -s '$STUB_CURL_LOG' && ! grep -q -- --resolve '$STUB_CURL_LOG'"
check "dig missing: the step line says the system resolver was used" grep -q "no authoritative answer for qcbox-council.$Z (dig or nameservers unavailable); using the system resolver" "$OUT"

NS_FIXTURE > "$WORK/f.json"; start_fake "$WORK/f.json"; stub_reset
STUB_SYS=ok COUNCIL_EDGE_RESOLVE=system TEST_PATH="$STUB:$PATH" TEST_EDGE_TPL="https://%s/" run_script qcbox.$Z --apply
check "COUNCIL_EDGE_RESOLVE=system: never runs dig, plain curl" bash -c "test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z PROVISIONED' && test ! -s '$STUB_DIG_LOG' && ! grep -q -- --resolve '$STUB_CURL_LOG'"
: > "$LOG"; COUNCIL_EDGE_RESOLVE=bogus run_script qcbox.$Z --apply
check "COUNCIL_EDGE_RESOLVE=bogus: exit 2 before any API request" bash -c "test '$RC' = 2 && test ! -s '$LOG' && grep -q 'COUNCIL_EDGE_RESOLVE must be auth or system' '$OUT'"

NS_FIXTURE > "$WORK/f.json"; start_fake "$WORK/f.json"; stub_reset
TEST_PATH="$STUB:$PATH" run_script qcbox.$Z --apply
check "non-https edge URL (fake-server mode): authoritative step skipped, dig never runs" bash -c "test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z PROVISIONED' && test ! -s '$STUB_DIG_LOG'"

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

fixture qcbox | jq -c '.tunnels["'$TID'"].config.ingress[0].service = "https://example.test:4000"' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "public CC origin: ORIGIN_NOT_LOOPBACK, zero writes, exit 0" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z ORIGIN_NOT_LOOPBACK.*https://example.test:4000'"
fixture qcbox | jq -c '.tunnels["'$TID'"].config.ingress[0].service = "http://127.0.0.1:4000"' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z
check "127.0.0.1 CC origin is loopback: PLANNED" bash -c "test '$RC' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z PLANNED'"

echo "== 6a. container shape WITH evidence (COUNCIL_CONTAINER_HOSTS): remote-managed CC tunnel, bridge origin, in-container connector"
# CSHAPE <service> : the four-container-host shape on qcbox
CSHAPE() { fixture qcbox | jq -c --arg svc "${1:-http://172.16.1.2:4000}" '.tunnels["'$TID'"].config.ingress[0].service = $svc'; }
TEST_CONTAINER_HOSTS=qcbox   # FIX 3: the explicit operator override is the evidence
CSHAPE > "$WORK/f.json"; start_fake "$WORK/f.json"; cp "$STATE" "$WORK/orig-state.json"
run_script qcbox.$Z
check "container (dry-run): exit 0, GET only, plans the dedicated council-qcbox tunnel" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && grep -q 'would create tunnel council-qcbox' '$OUT' && grep -q '\[plan\] PUT .*configurations' '$OUT'"
check "container (dry-run): plan holds the DNS record until the connector is up" bash -c "! grep -q 'dns_records' '$OUT' && grep -q '\[hold\] no DNS record' '$OUT'"
check "container (dry-run): names the container-connector requirement (INSIDE the client's container)" bash -c "grep -q '\[plan\] would create tunnel council-qcbox (remote-managed)' '$OUT' && tail -n1 '$OUT' | grep -q 'PLANNED dry-run: .*no DNS write until tunnel council-qcbox has an active connection, so apply ends CONNECTOR_PENDING' && grep -q 'connector must run INSIDE' '$OUT'"
run_script qcbox.$Z --apply
check "container (apply): exit 0, CONNECTOR_PENDING, no DNS write" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 3 && ! grep -Eq '^(POST|PUT|DELETE|PATCH) .*/dns_records' '$LOG' && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONNECTOR_PENDING'"
check "container (apply): no DNS record exists yet" test "$(state '[.dns[] | select(.name=="qcbox-council.'$Z'")] | length')" = 0
CTID="$(state '[.tunnels | to_entries[] | select(.value.name == "council-qcbox") | .key][0]' | tr -d '"')"
check "container: a remote-managed (config_src cloudflare) tunnel named council-qcbox was created" test -n "$CTID" -a "$CTID" != null -a "$(state '.tunnels["'$CTID'"].source')" = '"cloudflare"'
check "container: ingress route <slug>-council -> http://127.0.0.1:8787 (connector runs inside the container)" test "$(state '.tunnels["'$CTID'"].config.ingress')" = '[{"hostname":"qcbox-council.'$Z'","service":"http://127.0.0.1:8787"},{"service":"http_status:404"}]'
check "container: token file saved, mode 600, dir 700" bash -c "test \"\$(stat -f %Lp '$TOKDIR/council-qcbox.token')\" = 600 && test \"\$(stat -f %Lp '$TOKDIR')\" = 700"
check "container: the CC tunnel and its bridge rule were not touched" test "$(state '.tunnels["'$TID'"]')" = "$(jq -c '.tunnels["'$TID'"]' "$WORK/orig-state.json")"
check "container (apply): pending detail says the connector must run INSIDE the container" bash -c "tail -n1 '$OUT' | grep -q 'connector must run INSIDE the client'"
check "container (apply): the pending line names BOTH delivery paths exactly (in-container + host) plus the operator-side token" bash -c "tail -n1 '$OUT' | grep -qF 'the in-container path \$OPENCLAW_ROOT/secrets/tunnel-council.token' && tail -n1 '$OUT' | grep -qF '(OPENCLAW_ROOT resolves to /data/.openclaw or ~/.openclaw as wire.sh does)' && tail -n1 '$OUT' | grep -qF 'the host path ~/.openclaw/secrets/tunnel-council.token for host-run connectors' && tail -n1 '$OUT' | grep -q 'token saved operator side at'"
check "container (apply): the step line names the evidence (COUNCIL_CONTAINER_HOSTS)" grep -q 'COUNCIL_CONTAINER_HOSTS names qcbox' "$OUT"
check "container: Access app mirrors the CC allow list" test "$(state '[.apps[] | select(.domain=="qcbox-council.'$Z'")] | length')" = 1
jq -c --arg k "$CTID" '.tunnels[$k].conns = [{id:"cc1",is_pending_reconnect:false}]' "$STATE" > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "connector up (apply): exactly 1 write, the DNS POST -> PROVISIONED" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 1 && grep -Eq '^POST /client/v4/zones/zone-real/dns_records' '$LOG' && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z PROVISIONED'"
check "connector up: CNAME points at the container's council tunnel" test "$(state '.dns[] | select(.name=="qcbox-council.'$Z'") | [.content,.proxied] | join("|")')" = '"'$CTID'.cfargotunnel.com|true"'
TEST_CONTAINER_HOSTS=""

echo "== 6a2. container shape, non-4000 bridge port (Contabo 19003): only the local-managed path allows it"
CSHAPE "http://172.16.1.2:19003" > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "bridge origin on :19003, remote-managed: refused exactly as today (the port assert fires first), zero writes, no provisioning" bash -c "test '$(nonget_count)' = 0 && ! grep -q 'CONNECTOR_PENDING' '$OUT' && tail -n1 '$OUT' | grep -Eq 'qcbox.$Z (FAILED|ORIGIN_NOT_LOOPBACK)'"
CSHAPE "http://172.16.1.2:19003" | jq -c '.tunnels["'$TID'"] = {source:"local",config:{ingress:[{hostname:"qcbox.'$Z'",service:"http://172.16.1.2:19003"}]}}' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "bridge origin on :19003, local-managed: dedicated path unchanged (Contabo shape keeps working)" bash -c "test '$RC' = 0 && grep -q 'would create tunnel council-qcbox\|council-qcbox' '$OUT' && ! grep -q 'ORIGIN_NOT_LOOPBACK' '$OUT'"

echo "== 6a3. private-range boundary: 10.x and 192.168.x accepted, 172.32.x refused"
for svc in "http://10.0.0.5:4000" "http://192.168.1.20:4000" "http://host.docker.internal:4000" "http://172.20.0.4:4000" "http://172.31.0.4:4000"; do
  CSHAPE "$svc" > "$WORK/f.json"; start_fake "$WORK/f.json"
  run_script qcbox.$Z
  check "$svc bridge origin: dedicated path (no ORIGIN_NOT_LOOPBACK)" bash -c "test '$RC' = 0 && grep -q 'council-qcbox' '$OUT' && ! grep -q 'ORIGIN_NOT_LOOPBACK' '$OUT'"
done
for svc in "http://172.32.0.9:4000" "http://8.8.8.8:4000"; do
  CSHAPE "$svc" > "$WORK/f.json"; start_fake "$WORK/f.json"
  run_script qcbox.$Z --apply
  check "$svc (outside the private ranges): ORIGIN_NOT_LOOPBACK, zero writes" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z ORIGIN_NOT_LOOPBACK'"
done

echo "== 6a4. FIX 3: private-bridge :4000 WITHOUT container evidence takes the host-side dedicated path (ON THE HOST)"
CSHAPE > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "no evidence (apply): the dedicated path still runs, CONNECTOR_PENDING, zero DNS writes" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 3 && ! grep -Eq '^(POST|PUT|DELETE|PATCH) .*/dns_records' '$LOG' && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONNECTOR_PENDING'"
check "no evidence: the message says the connector runs ON THE HOST" bash -c "tail -n1 '$OUT' | grep -q 'The connector runs ON THE HOST'"
check "no evidence: the message never commands the in-container step" bash -c "! grep -q 'must run INSIDE' '$OUT'"
check "no evidence: both delivery paths still named exactly" bash -c "tail -n1 '$OUT' | grep -qF 'the in-container path \$OPENCLAW_ROOT/secrets/tunnel-council.token' && tail -n1 '$OUT' | grep -qF 'the host path ~/.openclaw/secrets/tunnel-council.token for host-run connectors'"
check "no evidence: the step line says the host-side fallback" grep -q 'no container evidence' "$OUT"
check "no evidence: the tunnel is still council-qcbox with the 8787 route (same writes as with evidence)" test "$(state '.tunnels | to_entries[] | select(.value.name == "council-qcbox") | .value.config.ingress')" = '[{"hostname":"qcbox-council.'$Z'","service":"http://127.0.0.1:8787"},{"service":"http_status:404"}]'
rm -f "$TOKDIR/council-qcbox.token"   # 6b expects a clean token dir

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
check "dry-run, token on disk: pending line says the token is saved" bash -c "tail -n1 '$OUT' | grep -q 'token saved operator side at'"
mv "$TOKDIR/council-qcbox.token" "$WORK/tok.bak"
run_script qcbox.$Z
check "dry-run, no token on disk: pending line says NOT saved, never 'token saved'" bash -c "tail -n1 '$OUT' | grep -q 'token NOT saved yet at .*--apply saves it' && ! tail -n1 '$OUT' | grep -q 'token saved operator side'"
mv "$WORK/tok.bak" "$TOKDIR/council-qcbox.token"
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

echo "== 6d2. FIX 1 ADOPT NOT CONFLICT: the council CNAME on a healthy tunnel already carrying the exact rule"
ADOPT="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
fixture qcbox | jq -c --arg z "$Z" --arg a "$ADOPT" '
  .tunnels["'$TID'"] = {name:"command-center",source:"local",config:null}
  | .tunnels[$a] = {name:"adopt-qcbox",source:"cloudflare",
      config:{ingress:[{hostname:("qcbox-council."+$z),service:"http://127.0.0.1:8787"},{service:"http_status:404"}]}}
  | .dns += [{id:"x-ad",type:"CNAME",name:("qcbox-council."+$z),content:($a+".cfargotunnel.com"),proxied:true}]
  | .apps += [{id:"app-co",name:"Council - qcbox",domain:("qcbox-council."+$z),type:"self_hosted",session_duration:"24h"}]
  | .policies["app-co"] = [{id:"pol-co",decision:"allow",include:[{email:{email:"qcbox@client.example"}},{email:{email:"operator@example.com"}}]}]' > "$WORK/f.json"
start_fake "$WORK/f.json"; cp "$STATE" "$WORK/adopt-state.json"
run_script qcbox.$Z
check "adopted (dry-run): exit 0, GET only, ALREADY_PROVISIONED naming the adopting tunnel" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q '^COUNCIL_ACCESS: qcbox.$Z ALREADY_PROVISIONED Council address already wired via tunnel adopt-qcbox'"
check "adopted (dry-run): no dedicated tunnel is re-planned (no 'would create tunnel')" bash -c "! grep -q 'would create tunnel' '$OUT'"
run_script qcbox.$Z --apply
check "adopted (apply): exit 0, ALREADY_PROVISIONED 'Council address already wired via tunnel adopt-qcbox'" bash -c "test '$RC' = 0 && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z ALREADY_PROVISIONED Council address already wired via tunnel adopt-qcbox'"
check "adopted: zero writes" test "$(nonget_count)" = 0
check "adopted: no council-qcbox tunnel was created and the DNS record kept its target" test "$(state '[.tunnels[] | select((.name // "") == "council-qcbox")] | length')" = 0 -a "$(state '.dns[] | select(.name=="qcbox-council.'$Z'") | .content')" = '"'$ADOPT'.cfargotunnel.com"'
check "adopted: the adopting tunnel's config was never written" test "$(state '.put_bodies | length')" = 0
check "adopted: no connector token was fetched or saved" bash -c "! grep -q '/token' '$LOG' && test ! -e '$TOKDIR/adopt-qcbox.token'"
check "adopted: the step line records the adoption" grep -q "adopted: tunnel adopt-qcbox already routes qcbox-council.$Z -> http://127.0.0.1:8787" "$OUT"

fixture qcbox | jq -c --arg z "$Z" --arg a "$ADOPT" '
  .tunnels["'$TID'"] = {name:"command-center",source:"local",config:null}
  | .tunnels[$a] = {name:"adopt-qcbox",source:"local",
      config:{ingress:[{hostname:("qcbox-council."+$z),service:"http://localhost:8787"},{service:"http_status:404"}]}}
  | .dns += [{id:"x-ad",type:"CNAME",name:("qcbox-council."+$z),content:($a+".cfargotunnel.com"),proxied:true}]
  | .apps += [{id:"app-co",name:"Council - qcbox",domain:("qcbox-council."+$z),type:"self_hosted",session_duration:"24h"}]
  | .policies["app-co"] = [{id:"pol-co",decision:"allow",include:[{email:{email:"qcbox@client.example"}},{email:{email:"operator@example.com"}}]}]' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "adopted (LOCAL-managed adopting tunnel, localhost:8787 equivalent form): same ALREADY_PROVISIONED, zero writes" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z ALREADY_PROVISIONED Council address already wired via tunnel adopt-qcbox'"

fixture qcbox | jq -c --arg z "$Z" --arg a "$ADOPT" '
  .tunnels[$a] = {name:"foreign-qcbox",source:"cloudflare",
      config:{ingress:[{hostname:("qcbox-council."+$z),service:"http://127.0.0.1:9999"},{service:"http_status:404"}]}}
  | .dns += [{id:"x-fr",type:"CNAME",name:("qcbox-council."+$z),content:($a+".cfargotunnel.com"),proxied:true}]' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "foreign CNAME (healthy tunnel WITHOUT the council rule): stays CONFLICT, zero writes, exit 1" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONFLICT'"
check "foreign CNAME: no adoption line in the output" bash -c "! grep -q ADOPTED '$OUT'"
check "foreign CNAME: no council-qcbox tunnel was created" test "$(state '[.tunnels[] | select((.name // "") == "council-qcbox")] | length')" = 0

echo "== 6d3. FIX 4: adoption needs the EXACT PATH-LESS rule on a healthy tunnel (no false blessing)"
fixture qcbox | jq -c --arg z "$Z" --arg a "$ADOPT" '
  .tunnels[$a] = {name:"adopt-qcbox",source:"cloudflare",
      config:{ingress:[{hostname:("qcbox-council."+$z),service:"http://127.0.0.1:8787",path:"^/chamber/"},{service:"http_status:404"}]}}
  | .dns += [{id:"x-ad",type:"CNAME",name:("qcbox-council."+$z),content:($a+".cfargotunnel.com"),proxied:true}]' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "path-scoped rule only (no path-less rule): NOT adopted, CONFLICT, zero writes" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONFLICT' && ! grep -q ADOPTED '$OUT'"

fixture qcbox | jq -c --arg z "$Z" --arg a "$ADOPT" '
  .tunnels[$a] = {name:"adopt-qcbox",source:"cloudflare",
      config:{ingress:[{hostname:("qcbox-council."+$z),service:"http://1:8787"},{service:"http_status:404"}]}}
  | .dns += [{id:"x-ad",type:"CNAME",name:("qcbox-council."+$z),content:($a+".cfargotunnel.com"),proxied:true}]' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "http://1:8787 (host '1', NOT loopback): NOT adopted, CONFLICT (the quoted IPv6 form is literal)" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONFLICT' && ! grep -q ADOPTED '$OUT'"

fixture qcbox | jq -c --arg z "$Z" --arg a "$ADOPT" '
  .tunnels[$a] = {name:"adopt-qcbox",source:"cloudflare",
      config:{ingress:[{hostname:("qcbox-council."+$z),service:"http://[::1]:8787"},{service:"http_status:404"}]}}
  | .dns += [{id:"x-ad",type:"CNAME",name:("qcbox-council."+$z),content:($a+".cfargotunnel.com"),proxied:true}]
  | .apps += [{id:"app-co",name:"Council - qcbox",domain:("qcbox-council."+$z),type:"self_hosted",session_duration:"24h"}]
  | .policies["app-co"] = [{id:"pol-co",decision:"allow",include:[{email:{email:"qcbox@client.example"}},{email:{email:"operator@example.com"}}]}]' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "http://[::1]:8787 (the real IPv6 loopback form): adopted, ALREADY_PROVISIONED, zero writes" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z ALREADY_PROVISIONED Council address already wired via tunnel adopt-qcbox'"

for dead in '{"status":"down"}' '{"deleted_at":"2026-10-01T00:00:00Z"}'; do
  fixture qcbox | jq -c --arg z "$Z" --arg a "$ADOPT" --argjson dead "$dead" '
    .tunnels[$a] = ({name:"adopt-qcbox",source:"cloudflare",
        config:{ingress:[{hostname:("qcbox-council."+$z),service:"http://127.0.0.1:8787"},{service:"http_status:404"}]}} + $dead)
    | .dns += [{id:"x-ad",type:"CNAME",name:("qcbox-council."+$z),content:($a+".cfargotunnel.com"),proxied:true}]' > "$WORK/f.json"
  start_fake "$WORK/f.json"
  run_script qcbox.$Z --apply
  check "stale rule on a dead tunnel ($dead): NOT adopted, CONFLICT, zero writes" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z CONFLICT' && ! grep -q ADOPTED '$OUT'"
done

fixture qcbox | jq -c '.apps += [{id:"app-old",name:"Council - qcbox",domain:"qcbox-council.'$Z'",type:"self_hosted",session_duration:"24h"}] | .policies["app-old"] = [{id:"po",decision:"allow",include:[{email:{email:"stranger@example.test"}}]}]' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "existing council app with a different email list is synced, not FAILED (exit 0, PROVISIONED)" bash -c "test '$RC' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z PROVISIONED .*added 2, removed 1 email(s)'"
check "...the stranger is gone and the council emails equal the CC emails" test "$(state '.policies["app-old"][0].include | map(.email.email) | sort')" = "$(state '.policies["app-cc-qcbox"][0].include | map(.email.email) | sort')"

fixture qcbox | jq -c '.policies["app-cc-qcbox"][0].include = [{everyone:{}}]' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "CC app that allows everyone is never copied" bash -c "test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'NOT_PROVISIONED'"

echo "== 6e. the Council login page follows the Command Center login page (SYNCED)"
# Start from the provisioned state of section 4: Council app 'Council - qcbox' equal to the CC app.
CAPP="$(jq -r '[.apps[] | select(.domain == "qcbox-council.'$Z'")][0].id' "$WORK/provisioned.json")"
CPOL="$(jq -r --arg a "$CAPP" '.policies[$a][0].id' "$WORK/provisioned.json")"
cc_emails() { state '[.policies["app-cc-qcbox"][] | select(.decision=="allow") | .include[] | .email.email // empty] | map(ascii_downcase) | sort'; }
co_emails() { state '[.policies["'$CAPP'"][] | select(.decision=="allow") | .include[] | .email.email // empty] | map(ascii_downcase) | sort'; }
only_council_put() { ! grep -Ev '^GET ' "$LOG" | grep -v "^PUT /client/v4/accounts/qc-acct/access/apps/$CAPP/policies/$CPOL\$"; }
jq -c '.policies["app-cc-qcbox"][0].include += [{email:{email:"new-one@example.test"}},{email:{email:"New-Two@example.test"}}]' "$WORK/provisioned.json" > "$WORK/f.json"
start_fake "$WORK/f.json"; cp "$STATE" "$WORK/orig-state.json"
run_script qcbox.$Z
check "sync add (dry-run): GET only, PLANNED, says it would add 2 and remove 0 (counts)" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z PLANNED .*would add 2 and remove 0 email(s) on the Council login page'"
run_script qcbox.$Z --apply
check "sync add (apply): SYNCED, exit 0, exactly 1 write" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 1 && tail -n1 '$OUT' | grep -q '^COUNCIL_ACCESS: qcbox.$Z SYNCED .*added 2, removed 0 email(s)'"
check "sync add: that write is the PUT of the Council app's own allow policy" only_council_put
check "sync add: Council emails now equal the CC emails" test "$(co_emails)" = "$(cc_emails)"
check "sync add: the Command Center app and policy are never written" test "$(state '[.apps[] | select(.id == "app-cc-qcbox")], .policies["app-cc-qcbox"]')" = "$(jq -c '[.apps[] | select(.id == "app-cc-qcbox")], .policies["app-cc-qcbox"]' "$WORK/orig-state.json")"
check "sync add: no routing write (tunnel config and DNS unchanged)" test "$(state '[.tunnels, .dns]')" = "$(jq -c '[.tunnels, .dns]' "$WORK/orig-state.json")"
check "sync add: no address in the output" bash -c "! grep -q '@' '$OUT'"
cp "$STATE" "$WORK/synced.json"; start_fake "$WORK/synced.json"
run_script qcbox.$Z --apply
check "after a sync the next run is ALREADY_PROVISIONED with zero writes" bash -c "test '$(nonget_count)' = 0 && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z ALREADY_PROVISIONED'"

jq -c '.policies["app-cc-qcbox"][0].include |= map(select(.email.email != "qcbox@client.example"))' "$WORK/provisioned.json" > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "sync remove (revocation on the CC page): SYNCED, removed 1, 1 write" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 1 && tail -n1 '$OUT' | grep -q 'qcbox.$Z SYNCED .*added 0, removed 1 email(s)'"
check "sync remove: the revoked email is gone from the Council page" test "$(co_emails)" = '["operator@example.com"]'

jq -c --arg a "$CAPP" '.policies[$a][0].include = [{service_token:{token_id:"st-9"}}] + .policies[$a][0].include
  | .policies["app-cc-qcbox"][0].include += [{service_token:{token_id:"st-cc"}},{email:{email:"late@example.test"}}]' "$WORK/provisioned.json" > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "service-token rules: a CC service token is no refusal; SYNCED" bash -c "test '$RC' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z SYNCED .*added 1, removed 0'"
check "service-token rule on the Council policy kept first, in place; CC token not copied" test "$(state '.policies["'$CAPP'"][0].include | map(keys[0]) | join(",")')" = '"service_token,email,email,email"' -a "$(state '.policies["'$CAPP'"][0].include[0].service_token.token_id')" = '"st-9"'
check "service-token case: PUT body carries no read-only field" test "$(state '[.put_bodies[] | keys[] | select(IN("id","created_at","updated_at","reusable","app_count","uid"))] | length')" = 0

jq -c '.policies["app-cc-qcbox"][0].include += [{email_domain:{domain:"example.test"}}]' "$WORK/provisioned.json" > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "CC email-domain rule: FAILED (exit 1), zero writes, reason named" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z FAILED .*email_domain rule(s); mirroring'"
jq -c '.policies["app-cc-qcbox"][0].include += [{group:{id:"g-1"}},{email:{email:"x@example.test"}}]' "$WORK/provisioned.json" > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z
check "CC group rule: FAILED in dry-run too, GET only" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'FAILED .*group rule(s)'"

jq -c --arg a "$CAPP" '(.apps[] | select(.id == $a) | .name) = "Someone else" | .policies["app-cc-qcbox"][0].include += [{email:{email:"x@example.test"}}]' "$WORK/provisioned.json" > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "Council app not named 'Council - qcbox': FAILED, zero writes" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q \"qcbox.$Z FAILED the Access app on qcbox-council.$Z is not the one this script makes\""
jq -c --arg a "$CAPP" '(.apps[] | select(.id == $a)) |= (.domain = "elsewhere.'$Z'" | .self_hosted_domains = ["qcbox-council.'$Z'"]) | .policies["app-cc-qcbox"][0].include += [{email:{email:"x@example.test"}}]' "$WORK/provisioned.json" > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "Council app on another domain: FAILED, zero writes" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z FAILED the Access app'"
jq -c --arg a "$CAPP" '.policies[$a][0].reusable = true | .policies["app-cc-qcbox"][0].include += [{email:{email:"x@example.test"}}]' "$WORK/provisioned.json" > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "Council allow policy reusable: FAILED, zero writes" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z FAILED .*no app-scoped allow policy'"
jq -c --arg a "$CAPP" '.policies[$a] += [{id:"pby",name:"Bypass",decision:"bypass",include:[{email:{email:"stray@example.test"}}]}] | .policies["app-cc-qcbox"][0].include += [{email:{email:"x@example.test"}}]' "$WORK/provisioned.json" > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "email the CC lacks on a non-allow (bypass) policy: FAILED, zero writes" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'FAILED .*policy \"Bypass\" (bypass)'"
jq -c --arg a "$CAPP" '.policies[$a][0].include += [{everyone:{}}] | .policies["app-cc-qcbox"][0].include += [{email:{email:"x@example.test"}}]' "$WORK/provisioned.json" > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "Council app that admits everyone is never left as is: FAILED, zero writes" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'FAILED .*the Council app admits everyone'"
jq -c '.policies["app-cc-qcbox"][0].exclude = [{email:{email:"qcbox@client.example"}}]' "$WORK/provisioned.json" > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "revocation by an exclude rule on the CC page: FAILED, zero writes (never ALREADY_PROVISIONED)" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z FAILED .*exclude/require rules differ'"
jq -c '.policies["app-cc-qcbox"][0].require = [{geo:{country_code:"US"}}] | .policies["app-cc-qcbox"][0].include += [{email:{email:"x@example.test"}}]' "$WORK/provisioned.json" > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "a require rule on the CC page the Council lacks: FAILED, zero writes, no email synced either" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z FAILED .*exclude/require rules differ'"
jq -c '.policies["app-cc-qcbox"][0].include += [{email:{email:"x@example.test"}}] | .fail.policy_update = true' "$WORK/provisioned.json" > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "refused policy PUT: FAILED, policy unchanged, no routing write" bash -c "test '$RC' = 1 && tail -n1 '$OUT' | grep -q 'FAILED Council allow policy update failed' && test '$(nonget_count)' = 1"

echo "== 6f. orphan records (the CNAME's tunnel or its configuration no longer exists)"
fixture qcbox | jq -c 'del(.tunnels["'$TID'"])' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "tunnel gone (HTTP 404): SKIPPED_ORPHAN, exit 0, zero writes, names the tunnel" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q '^COUNCIL_ACCESS: qcbox.$Z SKIPPED_ORPHAN .*tunnel $TID, which no longer exists (HTTP 404'"
fixture qcbox | jq -c '.tunnels["'$TID'"].config_missing = true' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "'Configuration for tunnel not found' on a HEALTHY tunnel: FAILED, never SKIPPED_ORPHAN, zero writes" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z FAILED could not read tunnel configuration for $TID (HTTP 404)' && ! grep -q SKIPPED_ORPHAN '$OUT'"
fixture qcbox | jq -c '.tunnels["'$TID'"].deleted_at = "2026-10-01T00:00:00Z" | .tunnels["'$TID'"].status = "down"' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z
check "deleted tunnel (dry-run): SKIPPED_ORPHAN, not TUNNEL_DOWN" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z SKIPPED_ORPHAN .*deleted at 2026-10-01'"
fixture qcbox | jq -c '.fail.tunnel_read = true' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "tunnel read 503 stays FAILED (exit 1), zero writes" bash -c "test '$RC' = 1 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z FAILED could not read tunnel $TID (HTTP 503)'"
fixture alpha beta | jq -c --arg z "$Z" '(.dns[] | select(.name == ("alpha."+$z)) | .content | sub("\\.cfargotunnel\\.com$"; "")) as $a | del(.tunnels[$a])' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script --all --apply
check "--all: the orphan is SKIPPED_ORPHAN, beta still PROVISIONED, exit 0" bash -c "test '$RC' = 0 && grep -q '^COUNCIL_ACCESS: alpha.$Z SKIPPED_ORPHAN' '$OUT' && grep -q '^COUNCIL_ACCESS: beta.$Z PROVISIONED' '$OUT' && test '$(nonget_count)' = 3"
run_script --all --json
check "--json carries the SKIPPED_ORPHAN entry with its detail" bash -c "jq -e '[.[] | select(.status == \"SKIPPED_ORPHAN\" and .cc_host == \"alpha.$Z\" and (.detail | test(\"no longer exists\")))] | length == 1' '$OUT'"

echo "== 6g. local-managed Command Center: ride the rescue tunnel on the same machine"
RTID="rrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrr"
MAC_FIXTURE() {  # the Mac shape: local CC tunnel reporting localhost:4000, remote rescue-qcbox with ssh, same origin address
  fixture qcbox | jq -c --arg z "$Z" --arg r "$RTID" '
    .tunnels["'$TID'"] = {name:"command-center",source:"local",
       config:{ingress:[{hostname:("qcbox."+$z),service:"http://localhost:4000"},{service:"http_status:404"}]},
       conns:[{id:"c1",is_pending_reconnect:false,origin_ip:"198.51.100.7"}]}
    | .tunnels[$r] = {name:"rescue-qcbox",source:"cloudflare",
       config:{ingress:[{hostname:("rescue-qcbox."+$z),service:"ssh://localhost:22"},{service:"http_status:404"}]},
       conns:[{id:"r1",is_pending_reconnect:false,origin_ip:"198.51.100.7"},{id:"r2",is_pending_reconnect:false,origin_ip:"198.51.100.7"}]}
    | .dns += [{id:"d-resc",type:"CNAME",name:("rescue-qcbox."+$z),content:($r+".cfargotunnel.com"),proxied:true}]'
}
MAC_FIXTURE > "$WORK/f.json"; start_fake "$WORK/f.json"; cp "$STATE" "$WORK/orig-state.json"
run_script qcbox.$Z
check "ride (dry-run): PLANNED, GET only, says rides rescue tunnel, plans no new tunnel and no token" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && tail -n1 '$OUT' | grep -q 'qcbox.$Z PLANNED .*rides rescue tunnel rescue-qcbox' && ! grep -q 'would create tunnel' '$OUT' && ! grep -q 'connector token' '$OUT'"
check "ride (dry-run): plans the ingress PUT on the rescue tunnel and the DNS write" bash -c "grep -q '\[plan\] PUT /accounts/qc-acct/cfd_tunnel/$RTID/configurations' '$OUT' && grep -q '\[plan\] POST /zones/zone-real/dns_records' '$OUT'"
run_script qcbox.$Z --apply
check "ride (apply): PROVISIONED 'rides rescue tunnel rescue-qcbox', exit 0, 3 writes" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 3 && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z PROVISIONED rides rescue tunnel rescue-qcbox'"
check "ride: rescue ingress keeps its ssh rule, gains qcbox-council -> 127.0.0.1:8787 before the catch-all" test "$(state '.tunnels["'$RTID'"].config.ingress')" = '[{"hostname":"rescue-qcbox.'$Z'","service":"ssh://localhost:22"},{"hostname":"qcbox-council.'$Z'","service":"http://127.0.0.1:8787"},{"service":"http_status:404"}]'
check "ride: proxied CNAME points at the rescue tunnel" test "$(state '.dns[] | select(.name=="qcbox-council.'$Z'") | [.content,.proxied] | join("|")')" = '"'$RTID'.cfargotunnel.com|true"'
check "ride: no tunnel created, the CC tunnel untouched, no connector token fetched" bash -c "test '$(state '.tunnels | length')' = 2 && test '$(state '.tunnels["'$TID'"]')' = '$(jq -c '.tunnels["'$TID'"]' "$WORK/orig-state.json")' && ! grep -q '/token' '$LOG' && ! grep -q 'connector token' '$OUT'"
check "ride: the Council Access app equals the CC app and the edge gate ran" bash -c "grep -q 'Council Access rules equal the Command Center rules' '$OUT' && grep -q '^GET /edge/qcbox-council.$Z/' '$LOG'"
cp "$STATE" "$WORK/rode.json"; start_fake "$WORK/rode.json"
run_script qcbox.$Z --apply
check "ride: second apply ALREADY_PROVISIONED, zero writes" bash -c "test '$(nonget_count)' = 0 && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z ALREADY_PROVISIONED rides rescue tunnel rescue-qcbox'"
MAC_FIXTURE | jq -c --arg z "$Z" '.tunnels["eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"] = {name:"rescue-qcboxer",source:"cloudflare",config:{ingress:[{hostname:("rescue-qcboxer."+$z),service:"ssh://localhost:22"}]}}' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z
check "rescue-qcboxer is another word, not a second candidate: still rides" bash -c "tail -n1 '$OUT' | grep -q 'rides rescue tunnel rescue-qcbox\$'"
fall_back() {  # desc, why-regex : the run planned the dedicated council-qcbox tunnel and said why it did not ride
  check "$1: falls back to the dedicated council-qcbox tunnel" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && grep -q 'would create tunnel council-qcbox' '$OUT' && ! grep -q 'rides rescue tunnel' '$OUT' && grep -q 'not riding a rescue tunnel: .*$2' '$OUT'"
}
MAC_FIXTURE | jq -c --arg z "$Z" '.tunnels["ffffffffffffffffffffffffffffffff"] = {name:"rescue-qcbox-2",source:"cloudflare",config:{ingress:[{hostname:("rescue-qcbox-2."+$z),service:"ssh://localhost:22"}]},conns:[{id:"x",origin_ip:"198.51.100.7"}]}' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z; fall_back "two rescue-qcbox* candidates" "2 tunnels named rescue-qcbox"
MAC_FIXTURE | jq -c '.tunnels["'$RTID'"].status = "degraded"' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z; fall_back "rescue tunnel not healthy" "is degraded, not healthy"
MAC_FIXTURE | jq -c '.tunnels["'$RTID'"].config.ingress[0].service = "http://localhost:8080"' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z; fall_back "rescue tunnel without an ssh:// rule" "no ssh:// rule"
MAC_FIXTURE | jq -c '.tunnels["'$TID'"].config.ingress[0].service = "http://localhost:19003"' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z; fall_back "Contabo-style CC rule on :19003" "localhost:19003"
MAC_FIXTURE | jq -c '.tunnels["'$RTID'"].conns = [{id:"r1",is_pending_reconnect:false,origin_ip:"203.0.113.9"}]' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z; fall_back "no overlapping connector origin address" "share no origin address"
MAC_FIXTURE | jq -c '.tunnels["'$TID'"].conns = [{id:"c1",is_pending_reconnect:false}]' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z; fall_back "CC connector reports no origin address" "share no origin address"
MAC_FIXTURE | jq -c '.tunnels["'$TID'"].config.ingress[0].service = "http://172.17.0.2:4000"' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z; fall_back "non-loopback CC origin" "172.17.0.2:4000 for qcbox"
MAC_FIXTURE | jq -c '.tunnels["'$RTID'"].source = "local"' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z; fall_back "rescue tunnel locally managed" "is locally managed"
MAC_FIXTURE | jq -c --arg z "$Z" '.dns += [{id:"xc",type:"CNAME",name:("qcbox-council."+$z),content:"cccccccccccccccccccccccccccccccc.cfargotunnel.com"}] | .tunnels["cccccccccccccccccccccccccccccccc"] = {name:"council-qcbox",source:"cloudflare",config:{ingress:[{hostname:("qcbox-council."+$z),service:"http://127.0.0.1:8787"},{service:"http_status:404"}]}}' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z
check "a council record already on the dedicated tunnel stays there (no ride, no CONFLICT)" bash -c "test '$RC' = 0 && ! grep -q 'rides rescue tunnel' '$OUT' && grep -q 'not riding a rescue tunnel: qcbox-council.$Z already points at' '$OUT' && ! grep -q CONFLICT '$OUT'"
MAC_FIXTURE | jq -c --arg z "$Z" '.tunnels["'$RTID'"].name = "rescue-qcbox-two" | .tunnels["'$RTID'"].config.ingress[0].hostname = ("rescue-qcbox-two."+$z)' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z; fall_back "another client's tunnel rescue-qcbox-two (ssh rule for rescue-qcbox-two, same address)" "no ssh:// rule for rescue-qcbox.$Z"
MAC_FIXTURE | jq -c '.edge["qcbox-council.'$Z'"] = {status:200} | .fail.config_read_after_put = true' > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "ride rollback whose configuration re-read fails: no second PUT, ROLLBACK INCOMPLETE, the rescue ssh rule kept" bash -c "test '$RC' = 1 && tail -n1 '$OUT' | grep -q 'ROLLBACK INCOMPLETE' && test \"\$(grep -c '^PUT .*/cfd_tunnel/$RTID/configurations' '$LOG')\" = 1 && test \"\$(jq -c '[.tunnels[\"$RTID\"].config.ingress[] | select(.service == \"ssh://localhost:22\")] | length' '$STATE')\" = 1"
fixture trevor | jq -c --arg z "$Z" --arg d "$DESK" --arg r "$RTID" '
  (.dns[] | select(.name == ("trevor."+$z)) | .content | sub("\\.cfargotunnel\\.com$"; "")) as $t
  | .tunnels[$t] = {name:"command-center",source:"local",config:{ingress:[{hostname:("trevor."+$z),service:"http://localhost:4000"}]},conns:[{id:"c",origin_ip:"198.51.100.7"}]}
  | .tunnels[$r] = {name:"rescue-trevor",source:"cloudflare",config:{ingress:[{hostname:("rescue-trevor."+$z),service:"ssh://localhost:22"}]},conns:[{id:"r",origin_ip:"198.51.100.7"}]}
  | .tunnels[$d] = {name:"council-desktop",source:"cloudflare",config:{ingress:[{hostname:("council."+$z),service:"http://127.0.0.1:8787"},{service:"http_status:404"}]}}' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_script trevor.$Z
check "COUNCIL_TUNNEL_OVERRIDES still wins for trevor over a matching rescue tunnel" bash -c "test '$RC' = 0 && grep -q 'rides its own remote-managed tunnel council-desktop' '$OUT' && ! grep -q 'rides rescue tunnel' '$OUT'"

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
check "monique (docker-bridge origin, remote-managed): the container shape reaches the dedicated path and ends CONNECTOR_PENDING" bash -c "grep -q '^COUNCIL_ACCESS: monique.$Z CONNECTOR_PENDING' '$OUT'"
check "convoplay (path rule first) is PROVISIONED" bash -c "grep -q '^COUNCIL_ACCESS: convoplay.$Z PROVISIONED' '$OUT'"
check "alpha and beta PROVISIONED; exit 0" bash -c "test '$RC' = 0 && grep -q '^COUNCIL_ACCESS: alpha.$Z PROVISIONED' '$OUT' && grep -q '^COUNCIL_ACCESS: beta.$Z PROVISIONED' '$OUT'"
check "exactly 12 writes (alpha 3, beta 3, convoplay 3, monique 3 app+tunnel+ingress, no DNS before its connector)" test "$(nonget_count)" = 12

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

echo "== 7e. FIX 2: COUNCIL_ACCESS_EXCLUDE is honored in single-host mode (silent skip, zero writes)"
fixture qcbox > "$WORK/f.json"; start_fake "$WORK/f.json"
TEST_EXCLUDE="qcbox.$Z" run_script qcbox.$Z --apply
check "excluded single host: exit 0, zero writes" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0"
check "excluded single host: silent (no COUNCIL_ACCESS line, not an alert)" bash -c "! grep -q '^COUNCIL_ACCESS:' '$OUT' && ! grep -Eq 'FAILED|CONFLICT|PLANNED|PROVISIONED' '$OUT'"
check "excluded single host: the summary line says hosts=0" grep -q 'hosts=0' "$OUT"
check "excluded single host: nothing in the fake state moved (no PUT/POST body, app count unchanged)" test "$(state '.put_bodies | length')" = 0 -a "$(state '.apps | length')" = 1
printf 'COUNCIL_ACCESS_EXCLUDE=%s\n' "qcbox.$Z" > "$WORK/excl.env"
start_fake "$WORK/f.json"
TEST_ENV_FILE="$WORK/excl.env" run_script qcbox.$Z --apply
check "excluded via the env-file line (same source as the wrapper and ensure): exit 0, zero writes, silent" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && ! grep -q '^COUNCIL_ACCESS:' '$OUT'"
start_fake "$WORK/f.json"
run_script qcbox.$Z
check "not excluded: the same single-host run still plans (sanity)" bash -c "test '$RC' = 0 && tail -n1 '$OUT' | grep -q '^COUNCIL_ACCESS: qcbox.$Z PLANNED'"

echo "== 8. zone is resolved by name, never from CLOUDFLARE_ZONE_ID"
fixture qcbox > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "first request is GET /zones?name=$Z" test "$(head -n1 "$LOG")" = "GET /client/v4/zones?name=$Z"
check "no request touches the wrong zone id" bash -c "! grep -q wrong-zone '$LOG'"
check "every zone-scoped request uses the id from the name lookup" bash -c "grep '/zones/' '$LOG' | grep -v '^GET /client/v4/zones?name=' | grep -qv '/zones/zone-real/' && exit 1; grep -q '/zones/zone-real/' '$LOG'"

echo "== 8b. regression guard: the four live container hosts keep ALREADY_PROVISIONED exactly as today"
# evelyn, bethune-publishing-house-inc, drstephaniebrown, monique: remote-managed CC
# tunnel with a private-bridge CC rule on :4000, an existing council-<slug> tunnel with
# the exact rule, its CNAME, and both Access apps. Two of them also carry a
# bridge-pattern sibling rule (evidence), two do not; the result line is identical.
container_live_fixture() {
  local out='{"token":"'"$TOKEN"'","account":"qc-acct","zone":{"id":"zone-real","name":"'"$Z"'"},"dns":[],"tunnels":{},"apps":[],"policies":{},"edge":{"default":{"status":302,"location":"https://sweet-wave-ca28.cloudflareaccess.com/cdn-cgi/access/login/x"}},"fail":{}}'
  local s i=0 ct kt sib
  for s in "$@"; do
    i=$((i + 1)); ct="$(printf 'c%031x' "$i")"; kt="$(printf 'k%031x' "$i")"; sib=0
    case "$s" in evelyn|monique) sib=1 ;; esac
    out="$(jq -c --arg s "$s" --arg ct "$ct" --arg kt "$kt" --arg z "$Z" --argjson sib "$sib" '
      .dns += [{id:("d-"+$s),type:"CNAME",name:($s+"."+$z),content:($ct+".cfargotunnel.com"),proxied:true},
               {id:("dc-"+$s),type:"CNAME",name:($s+"-council."+$z),content:($kt+".cfargotunnel.com"),proxied:true}]
      | .tunnels[$ct] = {source:"cloudflare",config:{ingress:(
          [{hostname:($s+"."+$z),service:"http://172.16.1.2:4000"}]
          + (if $sib == 1 then [{hostname:($s+"-hooks."+$z),service:"http://172.16.1.2:18789",path:"^/hooks/"}] else [] end)
          + [{service:"http_status:404"}])}}
      | .tunnels[$kt] = {name:("council-"+$s),source:"cloudflare",
          config:{ingress:[{hostname:($s+"-council."+$z),service:"http://127.0.0.1:8787"},{service:"http_status:404"}]}}
      | .apps += [{id:("app-cc-"+$s),name:("Command Center - "+$s),domain:($s+"."+$z),type:"self_hosted",session_duration:"24h"},
                  {id:("app-co-"+$s),name:("Council - "+$s),domain:($s+"-council."+$z),type:"self_hosted",session_duration:"24h"}]
      | .policies[("app-cc-"+$s)] = [{id:("pol-"+$s),name:"allow",decision:"allow",
          include:[{email:{email:($s+"@client.example")}},{email:{email:"operator@example.com"}}]}]
      | .policies[("app-co-"+$s)] = [{id:("polc-"+$s),name:"allow",decision:"allow",
          include:[{email:{email:($s+"@client.example")}},{email:{email:"operator@example.com"}}]}]' <<<"$out")"
  done
  printf '%s' "$out"
}
container_live_fixture evelyn bethune-publishing-house-inc drstephaniebrown monique > "$WORK/live.json"; start_fake "$WORK/live.json"
for s in evelyn bethune-publishing-house-inc drstephaniebrown monique; do
  run_script "$s.$Z" --apply
  check "$s: ALREADY_PROVISIONED exactly as today, zero writes" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 0 && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: $s.$Z ALREADY_PROVISIONED'"
done
start_fake "$WORK/live.json"
TEST_CONTAINER_HOSTS="evelyn,monique" run_script evelyn.$Z --apply
check "evelyn with COUNCIL_CONTAINER_HOSTS evidence: same ALREADY_PROVISIONED line" bash -c "test '$RC' = 0 && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: evelyn.$Z ALREADY_PROVISIONED'"

echo "== 8c. FIX W68: an existing council ingress rule keeps its own port (never rewritten)"
# (a) rule already at 8788 (a box whose client webhook owns 8787: the Council
# serves on 8788) is preserved byte-identical: no merge, no PUT, the port is the
# box's to own.
fixture qcbox | jq -c --arg z "$Z" --arg t "$TID" \
  '.tunnels[$t].config.ingress = (.tunnels[$t].config.ingress[0:-1] + [{hostname:("qcbox-council."+$z),service:"http://127.0.0.1:8788"}] + .tunnels[$t].config.ingress[-1:])' > "$WORK/f.json"; start_fake "$WORK/f.json"
cp "$STATE" "$WORK/w68-8788-orig.json"
run_script qcbox.$Z --apply
check "8788 rule: PROVISIONED (app+DNS created), exit 0" bash -c "test '$RC' = 0 && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z PROVISIONED'"
check "8788 rule: exactly 2 writes, zero PUTs (no ingress rewrite)" test "$(nonget_count)" = 2 -a "$(state '.put_bodies | length')" = 0
check "8788 rule: no configurations PUT in the log" bash -c "! grep -q 'PUT .*configurations' '$LOG'"
check "8788 rule: still serves http://127.0.0.1:8788" test "$(state '.tunnels["'$TID'"].config.ingress | map(select(.hostname=="qcbox-council.'$Z'")) | .[0].service')" = '"http://127.0.0.1:8788"'
check "8788 rule: whole ingress config byte-identical to pre-run" test "$(state '.tunnels["'$TID'"].config.ingress')" = "$(jq -c '.tunnels["'$TID'"].config.ingress' "$WORK/w68-8788-orig.json")"
check "8788 rule: output reports the rule preserved at its own port" bash -c "grep -q 'qcbox-council.$Z -> http://127.0.0.1:8788 preserved' '$OUT'"
check "8788 rule: Access app and CNAME still created" test "$(state '[.apps[] | select(.domain=="qcbox-council.'$Z'")]|length')" = 1 -a "$(state '[.dns[] | select(.name=="qcbox-council.'$Z'")]|length')" = 1

# (b) rule absent: created at the default COUNCIL_SERVICE (8787)
fixture qcbox > "$WORK/f.json"; start_fake "$WORK/f.json"
run_script qcbox.$Z --apply
check "missing rule: PROVISIONED, exit 0" bash -c "test '$RC' = 0 && test \"\$(tail -n1 '$OUT')\" = 'COUNCIL_ACCESS: qcbox.$Z PROVISIONED'"
check "missing rule: exactly 3 writes, exactly one PUT" test "$(nonget_count)" = 3 -a "$(state '.put_bodies | length')" = 1
check "missing rule: created at http://127.0.0.1:8787" test "$(state '.put_bodies[0].config.ingress | map(select(.hostname=="qcbox-council.'$Z'")) | .[0].service')" = '"http://127.0.0.1:8787"'

# (c) rule already at the default 8787: stays untouched
fixture qcbox | jq -c --arg z "$Z" --arg t "$TID" \
  '.tunnels[$t].config.ingress = (.tunnels[$t].config.ingress[0:-1] + [{hostname:("qcbox-council."+$z),service:"http://127.0.0.1:8787"}] + .tunnels[$t].config.ingress[-1:])' > "$WORK/f.json"; start_fake "$WORK/f.json"
cp "$STATE" "$WORK/w68-8787-orig.json"
run_script qcbox.$Z --apply
check "8787 rule: PROVISIONED (app+DNS), zero PUTs" bash -c "test '$RC' = 0 && test '$(nonget_count)' = 2 && test '$(state '.put_bodies | length')' = 0 && tail -n1 '$OUT' | grep -q '^COUNCIL_ACCESS: qcbox.$Z PROVISIONED'"
check "8787 rule: still serves http://127.0.0.1:8787, config byte-identical" test "$(state '.tunnels["'$TID'"].config.ingress')" = "$(jq -c '.tunnels["'$TID'"].config.ingress' "$WORK/w68-8787-orig.json")"
check "8787 rule: output reports it present" bash -c "grep -q 'ingress rule qcbox-council.$Z -> http://127.0.0.1:8787 present' '$OUT'"

echo "== 9. the token never leaks"
check "token appears in no case's stdout or stderr" bash -c "! grep -rq -- '$TOKEN' '$WORK/out'"
check "no temp file is left in the script's TMPDIR" test -z "$(ls -A "$SCRIPT_TMP")"
check "token appears in no file in the script's TMPDIR" bash -c "! grep -rq -- '$TOKEN' '$SCRIPT_TMP'"
check "no connector token appears in any case's stdout or stderr" bash -c "! grep -rq -- 'qc-tunnel-TOKEN' '$WORK/out'"
check "no email address appears in any case's stdout or stderr (sync reports counts only)" bash -c "! grep -rq '@' '$WORK/out'"

echo
if [ "$FAILS" = 0 ]; then echo "ALL $N CHECKS PASS"; exit 0; else echo "$FAILS of $N CHECKS FAILED"; exit 1; fi
