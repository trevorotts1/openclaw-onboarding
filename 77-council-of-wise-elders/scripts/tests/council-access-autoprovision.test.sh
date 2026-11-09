#!/usr/bin/env bash
# Acceptance cases for scripts/council-access-autoprovision.sh and install-council-access-job.sh,
# run against fake-cloudflare-api.py on an ephemeral loopback port. No real Cloudflare call,
# no real LaunchAgent, no real state dir: everything points at a temp dir.
#   bash scripts/tests/council-access-autoprovision.test.sh      (exit 0 = all PASS)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$HERE/.."
JOB="$SCRIPTS/council-access-autoprovision.sh"
INSTALLER="$SCRIPTS/install-council-access-job.sh"
TEMPLATE="$SCRIPTS/../launchd/ai.blackceo.council-access-autoprovision.plist.template"
FAKE="$HERE/fake-cloudflare-api.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/council-autoprov-test.XXXXXX")"
SD="$WORK/state"           # the job's receipt dir
export COUNCIL_TUNNEL_TOKEN_DIR="$WORK/tunnel-tokens"   # connector tokens: never the real operator store
export COUNCIL_GHL_ENV_FILE="$WORK/no-ghl.env" COUNCIL_GHL_API_BASE="http://127.0.0.1:9" COUNCIL_GHL_LOCATION_ID=""   # never the real GoHighLevel
FAKE_PID=""; FAILS=0; N=0
TOKEN="qc-secret-TOKEN-456"
Z="zerohumanworkforce.com"

stop_fake() { [ -z "$FAKE_PID" ] || { kill "$FAKE_PID" 2>/dev/null; wait "$FAKE_PID" 2>/dev/null; FAKE_PID=""; }; }
trap 'stop_fake; rm -rf "$WORK"' EXIT
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; FAILS=$((FAILS + 1)); }
check() { local d="$1"; shift; N=$((N + 1)); if "$@" >/dev/null 2>&1; then pass "$d"; else fail "$d"; fi; }

# fixture <slug>... : a zone with one provisionable Command Center per slug (FIXTURE_OFFSET shifts tunnel ids)
fixture() {
  local out='{"token":"'"$TOKEN"'","account":"qc-acct","zone":{"id":"zone-real","name":"'"$Z"'"},"dns":[],"tunnels":{},"apps":[],"policies":{},"edge":{"default":{"status":302,"location":"https://sweet-wave-ca28.cloudflareaccess.com/cdn-cgi/access/login/x"}},"fail":{}}'
  local s tid i="${FIXTURE_OFFSET:-0}"
  for s in "$@"; do
    i=$((i + 1)); tid="$(printf '%032x' "$((0x0123456789abcdef + i))")"
    out="$(jq -c --arg s "$s" --arg t "$tid" --arg z "$Z" --arg a "app-cc-$s" '
      .dns += [{id:("d-"+$s),type:"CNAME",name:($s+"."+$z),content:($t+".cfargotunnel.com"),proxied:true},
               {id:("dh-"+$s),type:"CNAME",name:($s+"-hooks."+$z),content:($t+".cfargotunnel.com"),proxied:true}]
      | .tunnels[$t] = {source:"cloudflare",config:{ingress:[
          {hostname:($s+"."+$z),service:"http://localhost:4000"},
          {hostname:($s+"-hooks."+$z),service:"http://127.0.0.1:18789",path:"^/hooks/"},
          {service:"http_status:404"}]}}
      | .apps += [{id:$a,name:("Command Center - "+$s),domain:($s+"."+$z),type:"self_hosted",session_duration:"24h"}]
      | .policies[$a] = [{id:("pol-"+$s),name:"allow",decision:"allow",
          include:[{email:{email:($s+"@client.example")}},{email:{email:"operator@example.com"}}]}]' <<<"$out")"
  done
  printf '%s' "$out"
}

start_fake() {  # <fixture-file> : sets PORT LOG STATE
  stop_fake
  LOG="$WORK/log.$N.$RANDOM"; STATE="$WORK/state.$N.$RANDOM.json"; : > "$LOG"
  local pf="$WORK/port.$RANDOM"
  python3 -I "$FAKE" --fixture "$1" --log "$LOG" --port-file "$pf" --state-out "$STATE" &
  FAKE_PID=$!
  local i; for i in $(seq 1 400); do [ -s "$pf" ] && break; sleep 0.05; done
  PORT="$(cat "$pf")"
}

run_job() {  # <args...> : stdout+stderr to $OUT, status to $RC
  OUT="$WORK/out.$N.$RANDOM"
  env CF_API_BASE="http://127.0.0.1:$PORT/client/v4" \
      COUNCIL_EDGE_URL_TEMPLATE="http://127.0.0.1:$PORT/edge/%s/" COUNCIL_EDGE_TRIES=2 COUNCIL_EDGE_SLEEP=0 \
      CLOUDFLARE_API_TOKEN="$TOKEN" CLOUDFLARE_ACCOUNT_ID=qc-acct \
      COUNCIL_ACCESS_STATE_DIR="$SD" COUNCIL_ACCESS_ENV_FILE="$WORK/no-such-env" TMPDIR="$WORK" \
      COUNCIL_CC_EMAILS_FILE="${COUNCIL_CC_EMAILS_FILE:-$WORK/no-cc-emails}" COUNCIL_CC_OPERATOR_EMAILS="" \
      "$JOB" "$@" >"$OUT" 2>&1
  RC=$?
}
nonget_count() { grep -Evc '^GET ' "$LOG"; }
rcpt() { jq -c "$1" "$SD/last-run.json"; }
Q='"'

echo "== 1. syntax, plist"
check "bash -n job"       /bin/bash -n "$JOB"
check "bash -n installer" /bin/bash -n "$INSTALLER"
sed -e "s#__PROGRAM__#$JOB#g" -e "s#__HOME__#$HOME#g" -e "s#__LOG_DIR__#$WORK#g" "$TEMPLATE" > "$WORK/rendered.plist"
check "rendered plist passes plutil -lint" plutil -lint "$WORK/rendered.plist"
check "plist: StartInterval 1800, RunAtLoad, ProcessType Standard, --apply" bash -c "
  test \"\$(plutil -extract StartInterval raw '$WORK/rendered.plist')\" = 1800 &&
  test \"\$(plutil -extract RunAtLoad raw '$WORK/rendered.plist')\" = true &&
  test \"\$(plutil -extract ProcessType raw '$WORK/rendered.plist')\" = Standard &&
  test \"\$(plutil -extract ProgramArguments.2 raw '$WORK/rendered.plist')\" = --apply"
mkdir -p "$WORK/la"
COUNCIL_ACCESS_LAUNCH_DIR="$WORK/la" "$INSTALLER" > "$WORK/inst.out" 2>&1; IRC=$?
check "installer with no flag prints the plan and writes nothing" bash -c "test $IRC = 0 && grep -q 'launchctl bootstrap' '$WORK/inst.out' && test -z \"\$(ls -A '$WORK/la')\""

echo "== 2. dry-run writes nothing"
FIXTURE_OFFSET=0 fixture alpha beta > "$WORK/f.json"; start_fake "$WORK/f.json"
run_job
check "dry-run exit 0" test "$RC" = 0
check "dry-run sends GET only" test "$(nonget_count)" = 0
check "receipt says dry-run, 2 hosts PLANNED" test "$(rcpt '[.mode, .total, .counts.PLANNED]')" = '["dry-run",2,2]'
check "runs.log has one line" test "$(wc -l < "$SD/runs.log" | tr -d ' ')" = 1
check "lock released after the run" test ! -e "$SD/run.lock"
check "no operator email: the Access step refuses (exit 3), writes nothing, and the run still exits 0" test "$(rcpt '[.cc_access.ran, .cc_access.exit]')" = '[false,3]'

echo "== 3. apply: provisions a ready host, reports refusals, still exits 0"
FIXTURE_OFFSET=0 fixture alpha beta gamma | jq -c --arg z "$Z" --arg g "00000000000000000123456789abcdf2" '
  .apps |= map(select(.domain != ("beta."+$z)))                       # beta: Command Center has no login yet
  | .tunnels[$g] = {source:"local",config:null}' > "$WORK/f.json"          # gamma: locally managed tunnel
start_fake "$WORK/f.json"
run_job --apply
check "apply exit 0 though two hosts are not ready" test "$RC" = 0
check "6 writes: alpha 3, gamma 3 (app, dedicated council-gamma tunnel, ingress; no DNS before its connector)" test "$(nonget_count)" = 6
check "receipt counts: 1 provisioned, 1 not-provisioned, 1 connector-pending" test "$(rcpt '[.mode, .counts.PROVISIONED, .counts.NOT_PROVISIONED, .counts.CONNECTOR_PENDING, .counts.PENDING_LOCAL_TUNNEL, .counts.FAILED]')" = '["apply",1,1,1,0,0]'
check "receipt names each refusal with host and reason code" test "$(rcpt '[.refused[] | .host + "=" + .reason] | sort')" = '["beta.'$Z'=NOT_PROVISIONED","gamma.'$Z'=CONNECTOR_PENDING"]'
check "receipt lists alpha as provisioned" test "$(rcpt '.provisioned')" = '["alpha.'$Z'"]'
check "runs.log line carries host:REASON" bash -c "tail -n1 '$SD/runs.log' | grep -q 'beta.$Z:NOT_PROVISIONED' && tail -n1 '$SD/runs.log' | grep -q 'gamma.$Z:CONNECTOR_PENDING'"
check "gamma's connector token is in the test token dir, mode 600, never in output" bash -c "test \"\$(stat -f %Lp '$COUNCIL_TUNNEL_TOKEN_DIR/council-gamma.token')\" = 600 && ! grep -q 'qc-tunnel-TOKEN' '$OUT' '$SD/last-run.json' '$SD/runs.log'"

echo "== 4. second apply is a no-op"
cp "$STATE" "$WORK/after1.json"; start_fake "$WORK/after1.json"
run_job --apply
check "exit 0" test "$RC" = 0
check "zero non-GET requests" test "$(nonget_count)" = 0
check "alpha ALREADY_PROVISIONED, nothing newly provisioned" test "$(rcpt '[.counts.ALREADY_PROVISIONED, .counts.PROVISIONED]')" = '[1,0]'
check "refused hosts still reported (retried every run)" test "$(rcpt '.refused | length')" = 2
check "runs.log is append-only (3 lines so far)" test "$(wc -l < "$SD/runs.log" | tr -d ' ')" = 3

echo "== 5. a client added later is picked up by the next run, with no input"
cp "$STATE" "$WORK/after2.json"
FIXTURE_OFFSET=10 fixture delta > "$WORK/delta.json"
jq -s -c '.[0] as $d | .[1] | .dns += $d.dns | .apps += $d.apps | .tunnels += $d.tunnels | .policies += $d.policies' "$WORK/delta.json" "$WORK/after2.json" > "$WORK/f.json"
start_fake "$WORK/f.json"
run_job --apply
check "delta provisioned automatically; alpha, provisioned by an earlier run, is named in the address list too" test "$(rcpt '[.provisioned, .counts.ALREADY_PROVISIONED]')" = '[["alpha.'$Z'","delta.'$Z'"],1]'
check "exactly 3 writes (delta only)" test "$(nonget_count)" = 3

echo "== 5b. new reason codes are carried, named, and never fail the run"
FIXTURE_OFFSET=30 fixture up down bridge loc | jq -c --arg z "$Z" '
  (.dns[] | select(.name == ("up."+$z)) | .content | sub("\\.cfargotunnel\\.com$"; "")) as $u
  | (.dns[] | select(.name == ("down."+$z)) | .content | sub("\\.cfargotunnel\\.com$"; "")) as $d
  | (.dns[] | select(.name == ("bridge."+$z)) | .content | sub("\\.cfargotunnel\\.com$"; "")) as $b
  | (.dns[] | select(.name == ("loc."+$z)) | .content | sub("\\.cfargotunnel\\.com$"; "")) as $l
  | .dns += [{id:"x-od",type:"CNAME",name:("up-openclawdashboard."+$z),content:($u+".cfargotunnel.com"),proxied:true}]
  | .tunnels[$u].config.ingress = [{hostname:("up-openclawdashboard."+$z),service:"http://127.0.0.1:18789"}] + .tunnels[$u].config.ingress
  | .tunnels[$d].status = "down"
  | .tunnels[$b].config.ingress[0].service = "http://172.16.1.2:4000"
  | .tunnels[$l] = {source:"local",config:null}' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_job --apply
check "SKIPPED_NOT_CC + TUNNEL_DOWN + the container shape (bridge, remote-managed + 172.16.1.2:4000) + CONNECTOR_PENDING: exit 0" test "$RC" = 0 -a "$(rcpt '.exit')" = 0
check "receipt counts every new code" test "$(rcpt '[.counts.PROVISIONED, .counts.SKIPPED_NOT_CC, .counts.TUNNEL_DOWN, .counts.ORIGIN_NOT_LOOPBACK, .counts.CONNECTOR_PENDING]')" = '[1,1,1,0,2]'
check "receipt names the skipped host with its reason" test "$(rcpt '[.skipped[] | .host + "=" + .reason]')" = '["up-openclawdashboard.'$Z'=SKIPPED_NOT_CC"]'
check "receipt names each not-ready host with its reason code" test "$(rcpt '[.refused[] | .host + "=" + .reason] | sort')" = '["bridge.'$Z'=CONNECTOR_PENDING","down.'$Z'=TUNNEL_DOWN","loc.'$Z'=CONNECTOR_PENDING"]'
check "runs.log line carries skipped=1 and each host:REASON" bash -c "l=\"\$(tail -n1 '$SD/runs.log')\"; case \"\$l\" in *skipped=1*down.$Z:TUNNEL_DOWN*) ;; *) exit 1;; esac; case \"\$l\" in *bridge.$Z:CONNECTOR_PENDING*) ;; *) exit 1;; esac; case \"\$l\" in *loc.$Z:CONNECTOR_PENDING*) ;; *) exit 1;; esac"
check "writes only for up (3), loc (3) and bridge (3, the container shape's dedicated tunnel; no DNS before its connector): down got none" test "$(nonget_count)" = 9

echo "== 6. a real failure exits 1"
FIXTURE_OFFSET=0 fixture alpha | jq -c --arg z "$Z" '.dns += [{id:"x1",type:"CNAME",name:("alpha-council."+$z),content:"ffffffffffffffffffffffffffffffff.cfargotunnel.com",proxied:true}]' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_job --apply
check "CONFLICT exits 1, zero writes, reason in receipt" bash -c "test $RC = 1 && test $(nonget_count) = 0 && test \"\$(jq -c '[.refused[0].reason, .exit]' '$SD/last-run.json')\" = '[\"CONFLICT\",1]'"
FAKE_BAD_BASE="http://127.0.0.1:1/client/v4"
OUT="$WORK/out.api"; env CF_API_BASE="$FAKE_BAD_BASE" CLOUDFLARE_API_TOKEN="$TOKEN" CLOUDFLARE_ACCOUNT_ID=qc-acct COUNCIL_ACCESS_STATE_DIR="$SD" COUNCIL_ACCESS_ENV_FILE="$WORK/no-such-env" TMPDIR="$WORK" "$JOB" --apply >"$OUT" 2>&1; RC=$?
check "unreachable API exits 1 with an error receipt" bash -c "test $RC = 1 && test \"\$(jq -r .exit '$SD/last-run.json')\" = 1 && jq -e 'has(\"error\")' '$SD/last-run.json'"

echo "== 7. missing credentials exit 3 and print no value"
OUT="$WORK/out.cred"; env -u CLOUDFLARE_API_TOKEN -u CLOUDFLARE_ACCOUNT_ID COUNCIL_ACCESS_STATE_DIR="$SD" COUNCIL_ACCESS_ENV_FILE="$WORK/no-such-env" TMPDIR="$WORK" "$JOB" --apply >"$OUT" 2>&1; RC=$?
check "exit 3" test "$RC" = 3
check "message names only the variable names" grep -q 'CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must both be set' "$OUT"
check "error receipt written" test "$(jq -r .exit "$SD/last-run.json")" = 3
printf 'CLOUDFLARE_API_TOKEN=%s\nCLOUDFLARE_ACCOUNT_ID=qc-acct\n' "$TOKEN" > "$WORK/op.env"
FIXTURE_OFFSET=0 fixture alpha > "$WORK/f.json"; start_fake "$WORK/f.json"
OUT="$WORK/out.envfile"; env -u CLOUDFLARE_API_TOKEN -u CLOUDFLARE_ACCOUNT_ID CF_API_BASE="http://127.0.0.1:$PORT/client/v4" COUNCIL_ACCESS_STATE_DIR="$SD" COUNCIL_ACCESS_ENV_FILE="$WORK/op.env" TMPDIR="$WORK" "$JOB" >"$OUT" 2>&1; RC=$?
check "credentials load from the operator env file when the environment lacks them" test "$RC" = 0 -a "$(jq -r .total "$SD/last-run.json")" = 1

echo "== 8. lock"
mkdir "$SD/run.lock"
FIXTURE_OFFSET=0 fixture alpha > "$WORK/f.json"; start_fake "$WORK/f.json"
run_job --apply
check "fresh lock: skipped, exit 0, no requests" bash -c "test $RC = 0 && test ! -s '$LOG' && tail -n1 '$SD/runs.log' | grep -q 'skipped=locked'"
touch -t 202001010000 "$SD/run.lock"
run_job --apply
check "stale lock (older than 2h) is recovered and the run proceeds" bash -c "test $RC = 0 && test -s '$LOG' && test ! -e '$SD/run.lock'"

echo "== 8b. step 1: ensure-cc-access.sh runs before provisioning, new client needs no human step"
printf '{"operator":["ops@cx-test.example"],"clients":{"newbox":["owner-new@cx-test.example"]}}\n' > "$WORK/cc-emails.json"
export COUNCIL_CC_EMAILS_FILE="$WORK/cc-emails.json"
FIXTURE_OFFSET=20 fixture newbox noemail driftbox | jq -c --arg z "$Z" '
  .apps |= map(select(.domain == ("driftbox."+$z)))                          # newbox and noemail have no Command Center login yet
  | .idps = [{id:"idp-otp",type:"onetimepin",name:"otp"}]
  | .policies |= with_entries(select(.key == "app-cc-driftbox"))
  | .policies["app-cc-driftbox"][0].include += [{everyone:{}}]' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_job
check "dry-run: exit 0 and GET only" bash -c "test $RC = 0 && test $(nonget_count) = 0"
check "dry-run receipt: cc_access ran, 1 planned, 1 needs-email, 1 drift" test "$(rcpt '[.cc_access.ran, .cc_access.planned, (.cc_access.needs_email|length), (.cc_access.drift|length)]')" = '[true,1,1,1]'
check "cc-access receipts are written in the same state dir" bash -c "test -s '$SD/cc-access-last-run.json' && test -s '$SD/cc-access-runs.log'"
run_job --apply
check "apply: NEEDS_EMAIL and DRIFT are surfaced but the run exits 0" test "$RC" = 0
check "apply receipt: newbox app created, noemail needs an email, driftbox drift (not overwritten)" test "$(rcpt '[.cc_access.created, .cc_access.needs_email, .cc_access.drift]')" = '[1,["noemail.'$Z'"],["driftbox.'$Z'"]]'
check "runs.log line carries cc_reconciled=0 cc_needs_email=1 cc_drift=1" bash -c "tail -n1 '$SD/runs.log' | grep -q 'cc_reconciled=0 cc_needs_email=1 cc_drift=1'"
check "receipt carries the cc_access reconciled count" test "$(rcpt '.cc_access.reconciled')" = 0
check "the Access app write for newbox comes before newbox is provisioned" bash -c "
  a=\$(grep -n 'POST .*access/apps' '$LOG' | head -n1 | cut -d: -f1); d=\$(grep -n 'POST .*dns_records' '$LOG' | head -n1 | cut -d: -f1);
  test -n \"\$a\" && test -n \"\$d\" && test \"\$a\" -lt \"\$d\""
check "newbox is provisioned in that same run (no second step)" test "$(rcpt '.provisioned')" = '["newbox.'$Z'"]'
check "noemail is retried, not failed" test "$(rcpt '[.refused[] | select(.host == "noemail.'$Z'") | .reason]')" = '["NOT_PROVISIONED"]'
cp "$STATE" "$WORK/after-cc.json"; start_fake "$WORK/after-cc.json"
run_job --apply
check "second apply: zero writes (idempotent)" test "$(nonget_count)" = 0
unset COUNCIL_CC_EMAILS_FILE COUNCIL_CC_OPERATOR_EMAILS
printf '#!/usr/bin/env bash\necho boom >&2; exit 9\n' > "$WORK/crash.sh"; chmod +x "$WORK/crash.sh"
COUNCIL_ACCESS_ENSURE_CC="$WORK/crash.sh" run_job
check "a crashing Access step never fails the run; its exit shows in the receipt" test "$RC" = 0 -a "$(rcpt '[.cc_access.ran, .cc_access.exit]')" = '[false,9]'
COUNCIL_ACCESS_ENSURE_CC="$WORK/missing.sh" run_job
check "a missing Access step script never fails the run" test "$RC" = 0 -a "$(rcpt '.cc_access.exit')" = 127

echo "== 8c. SYNCED and SKIPPED_ORPHAN are carried as non-failures (the live case)"
FIXTURE_OFFSET=60 fixture alpha orph | jq -c --arg z "$Z" '(.dns[] | select(.name == ("orph."+$z)) | .content | sub("\\.cfargotunnel\\.com$"; "")) as $o | del(.tunnels[$o])' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_job --apply
check "orphan host: SKIPPED_ORPHAN counted and named under skipped; alpha provisioned; exit 0" bash -c "test $RC = 0 && test \"\$(jq -c '[.exit, .counts.PROVISIONED, .counts.SKIPPED_ORPHAN, [.skipped[] | .host + \"=\" + .reason]]' '$SD/last-run.json')\" = '[0,1,1,[\"orph.$Z=SKIPPED_ORPHAN\"]]'"
check "runs.log line carries orphans=1" bash -c "tail -n1 '$SD/runs.log' | grep -q ' orphans=1 '"
cp "$STATE" "$WORK/after-sync.json"; start_fake "$WORK/after-sync.json"
printf '{"operator":["ops-sync@example.test"],"clients":{}}\n' > "$WORK/cc-emails-sync.json"
COUNCIL_CC_EMAILS_FILE="$WORK/cc-emails-sync.json" run_job --apply
check "step 1 adds the operator to alpha's CC page (RECONCILED) and names the orphan; step 2 SYNCs the Council page; exit 0" bash -c "test $RC = 0 && test \"\$(jq -c '[.exit, .cc_access.reconciled, .cc_access.orphans, .counts.SYNCED, .synced, .counts.FAILED]' '$SD/last-run.json')\" = '[0,1,[\"orph.$Z\"],1,[\"alpha.$Z\"],0]'"
check "runs.log line carries synced=1 and cc_orphans=1" bash -c "tail -n1 '$SD/runs.log' | grep -q ' synced=1 ' && tail -n1 '$SD/runs.log' | grep -q ' cc_orphans=1 '"
check "the Council page now lets in exactly the CC page's emails" test "$(jq -c '[.apps[] | select(.domain == "alpha-council.'$Z'") | .id][0] as $c | [.policies[$c][].include[].email.email] | sort' "$STATE")" = "$(jq -c '[.policies["app-cc-alpha"][].include[].email.email] | sort' "$STATE")"
check "no address in the receipts or the job output" bash -c "! grep -q '@' '$SD/last-run.json' '$SD/runs.log' '$OUT'"

echo "== 8d. FIX 1: an adopted host (council CNAME on a healthy tunnel carrying the rule) is never bad"
ADOPT="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
FIXTURE_OFFSET=70 fixture adoptbox | jq -c --arg z "$Z" --arg a "$ADOPT" '
  .tunnels[$a] = {name:"adopt-adoptbox",source:"cloudflare",
      config:{ingress:[{hostname:("adoptbox-council."+$z),service:"http://127.0.0.1:8787"},{service:"http_status:404"}]}}
  | .dns += [{id:"x-ad",type:"CNAME",name:("adoptbox-council."+$z),content:($a+".cfargotunnel.com"),proxied:true}]
  | .apps += [{id:"app-co",name:"Council - adoptbox",domain:("adoptbox-council."+$z),type:"self_hosted",session_duration:"24h"}]
  | .policies["app-co"] = [{id:"pol-co",decision:"allow",include:[{email:{email:"adoptbox@client.example"}},{email:{email:"operator@example.com"}}]}]' > "$WORK/f.json"
start_fake "$WORK/f.json"
run_job --apply
check "adopted: wrapper exit 0 (ADOPTED is never counted bad)" test "$RC" = 0
check "adopted: counted ALREADY_PROVISIONED, zero writes, no refusals" bash -c "test \"\$(jq -c '[.exit, .counts.ALREADY_PROVISIONED, .counts.CONFLICT, .counts.FAILED, (.refused|length)]' '$SD/last-run.json')\" = '[0,1,0,0,0]' && test '$(nonget_count)' = 0"
check "adopted: no dedicated tunnel was planned or created" bash -c "! grep -Eq '^(POST|PUT|DELETE|PATCH) .*cfd_tunnel' '$LOG' && test \"\$(jq -c '[.tunnels[] | select((.name // \"\") == \"council-adoptbox\")] | length' '$STATE')\" = 0"

echo "== 8e. FIX 2: the env file's COUNCIL_ACCESS_EXCLUDE line is read even when the credentials are already exported"
printf 'COUNCIL_ACCESS_EXCLUDE=alpha.%s\n' "$Z" > "$WORK/op-excl.env"
FIXTURE_OFFSET=80 fixture alpha beta > "$WORK/f.json"; start_fake "$WORK/f.json"
OUT="$WORK/out.excl"; env CF_API_BASE="http://127.0.0.1:$PORT/client/v4" \
    COUNCIL_EDGE_URL_TEMPLATE="http://127.0.0.1:$PORT/edge/%s/" COUNCIL_EDGE_TRIES=2 COUNCIL_EDGE_SLEEP=0 \
    CLOUDFLARE_API_TOKEN="$TOKEN" CLOUDFLARE_ACCOUNT_ID=qc-acct \
    COUNCIL_ACCESS_STATE_DIR="$SD" COUNCIL_ACCESS_ENV_FILE="$WORK/op-excl.env" TMPDIR="$WORK" \
    COUNCIL_CC_EMAILS_FILE="$WORK/no-cc-emails" COUNCIL_CC_OPERATOR_EMAILS="" \
    "$JOB" --apply >"$OUT" 2>&1; RC=$?
check "credentials from the environment, exclude from the env file: alpha skipped, beta still provisioned" bash -c "test '$RC' = 0 && test \"\$(jq -c '[.total, .counts.PROVISIONED]' '$SD/last-run.json')\" = '[1,1]'"
check "the excluded host is silent (absent from receipt, log line and output)" bash -c "! grep -q 'alpha' '$SD/last-run.json' '$OUT' && ! tail -n1 '$SD/runs.log' | grep -q 'alpha'"
check "the excluded host got zero writes (exactly 3 writes, beta only)" test "$(nonget_count)" = 3

echo "== 9. the token never leaks"
check "token in no output, receipt or log" bash -c "! grep -rq -e '$TOKEN' '$WORK' --include='out*' --include='*.json' --include='*.log' --exclude='f.json' --exclude='after*' --exclude='delta.json' --exclude='state.*' --exclude='log.*'"
check "no temp file left behind by the job" bash -c "test -z \"\$(ls '$WORK' | grep council-autoprov)\""

echo
if [ "$FAILS" = 0 ]; then echo "ALL $N CHECKS PASS"; exit 0; else echo "$FAILS of $N CHECKS FAILED"; exit 1; fi
