#!/usr/bin/env bash
# Tests for scripts/verify-council-box.sh. Uses a fixture OPENCLAW_ROOT in a
# temp dir, python3 stub HTTP servers on ephemeral ports, and stub node,
# launchctl and pm2 executables. Touches no real service, port 8787 or box.
# Exit 0 when every case passes.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFY="$HERE/../verify-council-box.sh"
command -v python3 >/dev/null 2>&1 || { echo "FAIL python3 required"; exit 2; }
REAL_NODE="$(command -v node)" || { echo "FAIL node required"; exit 2; }
NODE_DIR="$(dirname "$REAL_NODE")"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/verify-council-box-test.XXXXXX")"
PIDFILE="$WORK/pids" # start_server runs in a command substitution, so pids go to a file, not a variable
: > "$PIDFILE"
cleanup() {
  for p in $(cat "$PIDFILE" 2>/dev/null); do kill "$p" 2>/dev/null; done
  rm -rf "$WORK"
}
trap cleanup EXIT

FAILS=0
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; FAILS=$((FAILS + 1)); }

# ---- stub HTTP server: serve.py <portfile> <mode> <routes-json-file> ----
cat > "$WORK/serve.py" <<'PY'
import http.server, sys, json
portfile, mode, routes = sys.argv[1], sys.argv[2], sys.argv[3]
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if mode == "service":
            if self.path == "/status":
                self.send_response(200); self.end_headers(); self.wfile.write(b"<html>ok</html>")
            elif self.path == "/api/council/routes":
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(open(routes, "rb").read())
            else:
                self.send_response(404); self.end_headers()
        elif mode == "public-frontdoor":
            # copies runtime/src/service/front-door.ts: / redirects to /chamber/, no auth anywhere
            if self.path == "/":
                self.send_response(302); self.send_header("Location", "/chamber/"); self.end_headers()
            else:
                self.send_response(200); self.end_headers(); self.wfile.write(b"open")
        elif mode == "public-open":
            self.send_response(200); self.end_headers(); self.wfile.write(b"chamber")
        elif mode == "public-access":
            self.send_response(302); self.send_header("Location", "https://acme.cloudflareaccess.com/cdn-cgi/access/login/x"); self.end_headers()
        else:
            self.send_response(302); self.send_header("Location", "https://example.invalid/login"); self.end_headers()
s = http.server.HTTPServer(("127.0.0.1", 0), H)
open(portfile, "w").write(str(s.server_port))
s.serve_forever()
PY

start_server() { # mode routes-file -> echoes "<pid> <port>"
  local pf="$WORK/port.$$.$RANDOM"
  python3 "$WORK/serve.py" "$pf" "$1" "${2:-/dev/null}" >/dev/null 2>&1 &
  local pid=$!
  echo "$pid" >> "$PIDFILE"
  local i=0
  while [ ! -s "$pf" ] && [ $i -lt 100 ]; do sleep 0.1; i=$((i + 1)); done
  echo "$pid $(cat "$pf")"
}

ROUTES_OK="$WORK/routes-ok.json"
ROUTES_BAD="$WORK/routes-bad.json"
echo '{"routes":[{"route_id":"claude-nine","provider_slug":"claude-code","kind":"cli","composable":true,"failure_code":null,"default_for":[]},{"route_id":"deepseek","composable":false}],"harness_defaults":{}}' > "$ROUTES_OK"
echo '{"routes":[{"route_id":"deepseek","composable":false},{"route_id":"other","usable":false}],"harness_defaults":{}}' > "$ROUTES_BAD"

# ---- fixture builder: mkfix <name> <manager> <port> <public_origin|""> ----
mkfix() {
  local d="$WORK/$1" mgr="$2" port="$3" pub="$4"
  mkdir -p "$d/root/council-runtime/bin" "$d/bin"
  cat > "$d/bin/node-stub" <<EOF
#!/bin/sh
[ -f "$d/verify-fail" ] && { echo "FAIL verify-release: stub says no"; exit 1; }
echo "PASS verify-release: stub"
exit 0
EOF
  chmod +x "$d/bin/node-stub"
  printf '{"releaseId":"rel1","releasePath":"%s/rel1","nodeExecutable":"%s/bin/node-stub","dataDir":"%s/root/council-data"}\n' "$d" "$d" "$d" > "$d/root/council-runtime/active.json"
  local pubjson="null"; [ -n "$pub" ] && pubjson="\"$pub\""
  printf '{"schema":"council-service/v1","port":%s,"origin":"http://127.0.0.1:%s","public_origin":%s,"manager":"%s","name":"council-svc","release_id":"rel1"}\n' "$port" "$port" "$pubjson" "$mgr" > "$d/root/council-runtime/service.json"
  printf '#!/bin/sh\nexit 0\n' > "$d/root/council-runtime/bin/blackceo-council"
  chmod +x "$d/root/council-runtime/bin/blackceo-council"
  echo "$d"
}

# run <fixture> [args]: sets OUT and RC; PATH is controlled so the real box shim is never found
run() {
  local d="$1"; shift
  mkdir -p "$d/tmp"
  OUT="$(OPENCLAW_ROOT="$d/root" TMPDIR="$d/tmp" PATH="$d/bin:$NODE_DIR:/usr/bin:/bin" /bin/bash "$VERIFY" "$@" 2>&1)"
  RC=$?
  LAST="$(printf '%s\n' "$OUT" | tail -n 1)"
}

expect() { # name expected-last-line expected-rc
  if [ "$LAST" = "$2" ] && [ "$RC" -eq "$3" ]; then pass "$1"
  else fail "$1 (got rc=$RC last='$LAST', wanted rc=$3 last='$2')"; printf '%s\n' "$OUT" | sed 's/^/    /'; fi
}

# 1. external manager, one usable route, no public origin
set -- $(start_server service "$ROUTES_OK"); SPID=$1; SPORT=$2
F="$(mkfix c1 external "$SPORT" "")"
run "$F"
expect "external + usable route + public_origin null -> DEGRADED PUBLIC_ORIGIN_UNSET" "COUNCIL_BOX: DEGRADED PUBLIC_ORIGIN_UNSET" 0
case "$OUT" in *"claude-nine=usable"*"deepseek=unusable"*) pass "route ids and usable flags are printed" ;; *) fail "route ids and usable flags are printed"; echo "$OUT" ;; esac

# 2. read-only: nothing under the fixture or the temp dir changes during a run
sleep 1; touch "$WORK/marker"; sleep 1
run "$F"
CHANGED="$(find "$F" "$WORK/serve.py" -newer "$WORK/marker" 2>/dev/null | grep -v "^$F/tmp$" || true)"
if [ -z "$CHANGED" ] && [ -z "$(ls -A "$F/tmp")" ]; then pass "verifier writes nothing (find -newer marker is empty, TMPDIR empty)"
else fail "verifier writes nothing"; echo "$CHANGED"; ls -A "$F/tmp"; fi

# 3. --json: first line is JSON, last line is the COUNCIL_BOX line
run "$F" --json
FIRST="$(printf '%s\n' "$OUT" | head -n 1)"
if printf '%s' "$FIRST" | "$REAL_NODE" -e 'const j=JSON.parse(require("fs").readFileSync(0,"utf8"));process.exit(j.status==="DEGRADED"&&j.checks.length>3&&j.routes.length===2?0:1)' \
   && [ "$LAST" = "COUNCIL_BOX: DEGRADED PUBLIC_ORIGIN_UNSET" ]; then pass "--json emits a JSON line then the COUNCIL_BOX line"
else fail "--json emits a JSON line then the COUNCIL_BOX line"; echo "$OUT"; fi

# 4. stopped stub
kill "$SPID" 2>/dev/null; wait "$SPID" 2>/dev/null
run "$F"
expect "stopped stub -> NOT_READY SERVICE_DOWN" "COUNCIL_BOX: NOT_READY SERVICE_DOWN PUBLIC_ORIGIN_UNSET" 1
case "$OUT" in *"NOT_READY SERVICE_DOWN"*) ;; esac

# 5. missing active.json
F3="$(mkfix c3 external 1 "")"; rm "$F3/root/council-runtime/active.json"
run "$F3"
expect "missing active.json -> NOT_READY RUNTIME_MISSING" "COUNCIL_BOX: NOT_READY RUNTIME_MISSING" 1

# 6. all routes unusable
set -- $(start_server service "$ROUTES_BAD"); BPORT=$2
F4="$(mkfix c4 external "$BPORT" "")"
run "$F4"
expect "all routes unusable -> NOT_READY NO_USABLE_ROUTE" "COUNCIL_BOX: NOT_READY NO_USABLE_ROUTE PUBLIC_ORIGIN_UNSET" 1

# 7. release unverified
set -- $(start_server service "$ROUTES_OK"); OPORT=$2
F5="$(mkfix c5 external "$OPORT" "")"; : > "$F5/verify-fail"
run "$F5"
expect "failed release verification -> NOT_READY RELEASE_UNVERIFIED" "COUNCIL_BOX: NOT_READY RELEASE_UNVERIFIED PUBLIC_ORIGIN_UNSET" 1

# 8. public origin answering 200 (gate open)
set -- $(start_server public-open); P200=$2
F6="$(mkfix c6 external "$OPORT" "http://127.0.0.1:$P200")"
run "$F6"
expect "public_origin answering 200 -> NOT_READY ACCESS_GATE_OPEN" "COUNCIL_BOX: NOT_READY ACCESS_GATE_OPEN" 1

# 8b. open address whose / answers 302 to its own /chamber/ (the real front door) is still open
set -- $(start_server public-frontdoor); PFD=$2
F6B="$(mkfix c6b external "$OPORT" "http://127.0.0.1:$PFD")"
run "$F6B"
expect "public_origin open, / answers 302 to /chamber/ -> NOT_READY ACCESS_GATE_OPEN" "COUNCIL_BOX: NOT_READY ACCESS_GATE_OPEN" 1

# 9. public origin 302 to cloudflareaccess.com passes, box is READY
set -- $(start_server public-access); P302=$2
F7="$(mkfix c7 external "$OPORT" "http://127.0.0.1:$P302")"
run "$F7"
expect "public_origin 302 to cloudflareaccess.com -> READY" "COUNCIL_BOX: READY" 0
case "$OUT" in *"PASS access-gate"*) pass "access-gate check line passes" ;; *) fail "access-gate check line passes"; echo "$OUT" ;; esac

# 10. public origin redirecting elsewhere -> DEGRADED ACCESS_GATE_MISSING
set -- $(start_server public-other); POTH=$2
F8="$(mkfix c8 external "$OPORT" "http://127.0.0.1:$POTH")"
run "$F8"
expect "public_origin 302 elsewhere -> DEGRADED ACCESS_GATE_MISSING" "COUNCIL_BOX: DEGRADED ACCESS_GATE_MISSING" 0

# 11. CLI shim missing
F9="$(mkfix c9 external "$OPORT" "http://127.0.0.1:$P302")"; rm "$F9/root/council-runtime/bin/blackceo-council"
run "$F9"
expect "no CLI shim -> DEGRADED CLI_SHIM_MISSING" "COUNCIL_BOX: DEGRADED CLI_SHIM_MISSING" 0

# 12. launchd manager (stub launchctl)
F10="$(mkfix c10 launchd "$OPORT" "http://127.0.0.1:$P302")"
printf '#!/bin/sh\necho "state = running"\n' > "$F10/bin/launchctl"; chmod +x "$F10/bin/launchctl"
run "$F10"
expect "launchd job running -> READY" "COUNCIL_BOX: READY" 0
printf '#!/bin/sh\necho "state = waiting"\n' > "$F10/bin/launchctl"
run "$F10"
expect "launchd job not running -> NOT_READY SERVICE_NOT_REGISTERED" "COUNCIL_BOX: NOT_READY SERVICE_NOT_REGISTERED" 1

# 13. pm2 manager (stub pm2): app online without a tunnel, then with one
F11="$(mkfix c11 pm2 "$OPORT" "http://127.0.0.1:$P302")"
sed -i.bak 's/council-svc/council-of-wise-elders/' "$F11/root/council-runtime/service.json"; rm -f "$F11/root/council-runtime/service.json.bak"
printf '#!/bin/sh\necho '"'"'[{"name":"council-of-wise-elders","pm2_env":{"status":"online"}}]'"'"'\n' > "$F11/bin/pm2"; chmod +x "$F11/bin/pm2"
run "$F11"
expect "pm2 app online, no cloudflared -> DEGRADED TUNNEL_NOT_IN_CONTAINER" "COUNCIL_BOX: DEGRADED TUNNEL_NOT_IN_CONTAINER" 0
printf '#!/bin/sh\necho '"'"'[{"name":"council-of-wise-elders","pm2_env":{"status":"online"}},{"name":"cloudflared","pm2_env":{"status":"online"}}]'"'"'\n' > "$F11/bin/pm2"
run "$F11"
expect "pm2 app and cloudflared online -> READY" "COUNCIL_BOX: READY" 0
printf '#!/bin/sh\necho "[]"\n' > "$F11/bin/pm2"
run "$F11"
expect "pm2 app absent -> NOT_READY SERVICE_NOT_REGISTERED" "COUNCIL_BOX: NOT_READY SERVICE_NOT_REGISTERED TUNNEL_NOT_IN_CONTAINER" 1

# 14. Council connector (token file present; the verifier only test -f's it)
mkdir -p "$F11/root/secrets"; printf 'x' > "$F11/root/secrets/tunnel-council.token"; chmod 600 "$F11/root/secrets/tunnel-council.token"
printf '#!/bin/sh\necho '"'"'[{"name":"council-of-wise-elders","pm2_env":{"status":"online"}},{"name":"cloudflared-council","pm2_env":{"status":"online"}}]'"'"'\n' > "$F11/bin/pm2"
run "$F11"
expect "pm2 + cloudflared-council online -> READY (relieves TUNNEL_NOT_IN_CONTAINER)" "COUNCIL_BOX: READY" 0
case "$OUT" in *"PASS tunnel: pm2 jlist lists cloudflared-council"*"PASS council-connector"*) pass "tunnel and council-connector lines name cloudflared-council" ;; *) fail "tunnel and council-connector lines name cloudflared-council"; echo "$OUT" ;; esac
printf '#!/bin/sh\necho '"'"'[{"name":"council-of-wise-elders","pm2_env":{"status":"online"}},{"name":"cloudflared","pm2_env":{"status":"online"}}]'"'"'\n' > "$F11/bin/pm2"
run "$F11"
expect "token present, cloudflared-council absent -> DEGRADED COUNCIL_CONNECTOR_DOWN" "COUNCIL_BOX: DEGRADED COUNCIL_CONNECTOR_DOWN" 0
printf '#!/bin/sh\necho '"'"'[{"name":"council-of-wise-elders","pm2_env":{"status":"online"}},{"name":"cloudflared-council","pm2_env":{"status":"stopped"}}]'"'"'\n' > "$F11/bin/pm2"
run "$F11"
expect "cloudflared-council stopped -> DEGRADED TUNNEL_NOT_IN_CONTAINER COUNCIL_CONNECTOR_DOWN" "COUNCIL_BOX: DEGRADED TUNNEL_NOT_IN_CONTAINER COUNCIL_CONNECTOR_DOWN" 0

# 15. launchd: service running, Council connector label checked separately
mkdir -p "$F10/root/secrets"; printf 'x' > "$F10/root/secrets/tunnel-council.token"
printf '#!/bin/sh\ncase "$2" in */ai.blackceo.council-tunnel) echo "state = waiting" ;; *) echo "state = running" ;; esac\n' > "$F10/bin/launchctl"
run "$F10"
expect "launchd service up, council-tunnel not running -> DEGRADED COUNCIL_CONNECTOR_DOWN" "COUNCIL_BOX: DEGRADED COUNCIL_CONNECTOR_DOWN" 0
printf '#!/bin/sh\necho "state = running"\n' > "$F10/bin/launchctl"
run "$F10"
expect "launchd service and council-tunnel running -> READY" "COUNCIL_BOX: READY" 0
rm -rf "$F10/root/secrets"
run "$F10"
case "$OUT" in *"SKIP council-connector"*) pass "absent token file -> council-connector SKIP" ;; *) fail "absent token file -> council-connector SKIP"; echo "$OUT" ;; esac

if [ "$FAILS" -eq 0 ]; then echo "verify-council-box tests: PASS"; exit 0; fi
echo "verify-council-box tests: $FAILS FAILED"; exit 1
