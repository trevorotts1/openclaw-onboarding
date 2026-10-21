#!/usr/bin/env bash
# Council of Wise Elders (77): box verifier. Answers one question for the
# fleet roll: can the client on THIS box actually use the Council?
#
# Read-only: it writes no file, starts and stops no process, and only issues
# GET requests. (The release check runs install-runtime.mjs --verify-release,
# whose node probe makes and removes one temp directory under the OS temp
# dir; nothing else is touched.) bash 3.2 safe: only constructs that
# bash 3.2 already has.
#
# Usage: verify-council-box.sh [--json]
#   OPENCLAW_ROOT = $OPENCLAW_ROOT, else /data/.openclaw (when it exists),
#   else ~/.openclaw. P = $OPENCLAW_ROOT/council-runtime, written by wire.sh.
#
# Checks, in order (each negative line says what was checked and how):
#   1. P/active.json exists                    else NOT_READY RUNTIME_MISSING
#   2. <nodeExecutable> install-runtime.mjs --verify-release <releasePath>
#      --prefix P passes                       else NOT_READY RELEASE_UNVERIFIED
#   3. P/service.json exists and the manager (launchd: launchctl print;
#      pm2: pm2 jlist) shows the job running   else NOT_READY SERVICE_NOT_REGISTERED
#      (manager "external" skips the manager check)
#   4. GET http://127.0.0.1:<port>/status      else NOT_READY SERVICE_DOWN
#   5. GET /api/council/routes lists a usable route
#                                              else NOT_READY NO_USABLE_ROUTE
#   6. blackceo-council resolves               else DEGRADED CLI_SHIM_MISSING
#   7. public_origin set                       else DEGRADED PUBLIC_ORIGIN_UNSET
#      GET <public_origin>/status without following redirects: a 3xx to
#      *.cloudflareaccess.com passes; 200 is NOT_READY ACCESS_GATE_OPEN (a
#      security failure); anything else is DEGRADED ACCESS_GATE_MISSING
#   8. pm2 boxes only: pm2 jlist lists a cloudflared app (the Council's own
#      connector cloudflared-council counts)  else DEGRADED TUNNEL_NOT_IN_CONTAINER
#   9. only when <OPENCLAW_ROOT>/secrets/tunnel-council.token exists (test -f,
#      never read): the Council connector runs (Mac: launchctl print
#      gui/<uid>/ai.blackceo.council-tunnel; VPS: pm2 jlist cloudflared-council)
#                                              else DEGRADED COUNCIL_CONNECTOR_DOWN
#
# Last line: COUNCIL_BOX: READY|DEGRADED|NOT_READY <codes>
# Exit: 0 READY or DEGRADED, 1 NOT_READY, 2 tooling error (unresolvable node
# or curl, unreadable or unparsable receipt). A tooling error prints
# "COUNCIL_BOX: UNDETERMINED <reason>" as the last line.
# With --json, human lines are replaced by one compact JSON line followed by
# the COUNCIL_BOX line.

set -u

JSON=0
case "${1:-}" in
  "") ;;
  --json) JSON=1 ;;
  *) echo "Usage: $0 [--json]" >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "${OPENCLAW_ROOT:-}" ]; then
  ROOT="$OPENCLAW_ROOT"
elif [ -d /data/.openclaw ]; then
  ROOT=/data/.openclaw
else
  ROOT="$HOME/.openclaw"
fi
P="$ROOT/council-runtime"

NOT_READY_CODES=""
DEGRADED_CODES=""
TAB=$'\t'
NL=$'\n'
RECORDS=""          # tab separated: result, check, detail (one per line, for --json)
ROUTES_JSON="[]"

say() { [ "$JSON" -eq 1 ] || echo "$*"; }
record() { # result check detail
  RECORDS="${RECORDS}$1${TAB}$2${TAB}$3${NL}"
  say "$1 $2: $3"
}
nr() { NOT_READY_CODES="$NOT_READY_CODES $1"; record "FAIL" "$2" "$3 [NOT_READY $1]"; }
dg() { DEGRADED_CODES="$DEGRADED_CODES $1"; record "WARN" "$2" "$3 [DEGRADED $1]"; }
ok() { record "PASS" "$1" "$2"; }
skip() { record "SKIP" "$1" "$2"; }

json_line() { # prints the compact JSON summary line
  printf '%s' "$RECORDS" | "$NODE" -e '
    const lines = require("fs").readFileSync(0, "utf8").split("\n").filter(Boolean);
    const checks = lines.map((l) => { const [result, check, detail] = l.split("\t"); return { result, check, detail }; });
    const arg = (i) => process.argv[i];
    console.log(JSON.stringify({
      schema: "council-box/v1", root: arg(1), status: arg(2),
      codes: arg(3).split(" ").filter(Boolean), checks, routes: JSON.parse(arg(4)),
    }));' "$ROOT" "$1" "$2" "$ROUTES_JSON"
}

finish() {
  local status codes
  if [ -n "$NOT_READY_CODES" ]; then status=NOT_READY; codes="$NOT_READY_CODES$DEGRADED_CODES"
  elif [ -n "$DEGRADED_CODES" ]; then status=DEGRADED; codes="$DEGRADED_CODES"
  else status=READY; codes=""; fi
  codes="${codes# }"
  if [ "$JSON" -eq 1 ] && [ -n "${NODE:-}" ]; then json_line "$status" "$codes"; fi
  echo "COUNCIL_BOX: $status${codes:+ $codes}"
  [ "$status" = NOT_READY ] && exit 1
  exit 0
}

tooling() {
  echo "COUNCIL_BOX: UNDETERMINED $1"
  exit 2
}

# ---- tool resolution (exit 2 when the instrument itself is broken) ----
CURL="$(command -v curl 2>/dev/null || true)"
[ -n "$CURL" ] || tooling "TOOLING_ERROR curl not found on PATH; no HTTP check was possible"

say "Council box verifier: OPENCLAW_ROOT=$ROOT prefix=$P"

# ---- 1. active.json ----
if [ ! -f "$P/active.json" ]; then
  nr RUNTIME_MISSING "runtime-receipt" "no file at $P/active.json (checked with test -f); wire.sh has not built a release on this box"
  finish
fi

NODE="$(command -v node 2>/dev/null || true)"
if [ -z "$NODE" ]; then
  for c in /opt/homebrew/bin/node /usr/local/bin/node /usr/bin/node; do
    [ -x "$c" ] && NODE="$c" && break
  done
fi
[ -n "$NODE" ] || tooling "TOOLING_ERROR node not found on PATH or in /opt/homebrew/bin, /usr/local/bin, /usr/bin; cannot parse $P/active.json"

jget() { # file key -> value ("" for null or missing); exit 3 on unreadable or bad JSON
  "$NODE" -e '
    let j; try { j = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8")); } catch (e) { process.exit(3); }
    const v = j[process.argv[2]];
    process.stdout.write(v === null || v === undefined ? "" : String(v));' "$1" "$2"
}

RELEASE_PATH="$(jget "$P/active.json" releasePath)" || tooling "TOOLING_ERROR could not read or parse $P/active.json"
NODE_EXE="$(jget "$P/active.json" nodeExecutable)" || tooling "TOOLING_ERROR could not read or parse $P/active.json"
RELEASE_ID="$(jget "$P/active.json" releaseId)"
ok "runtime-receipt" "$P/active.json present, release ${RELEASE_ID:-unknown}"

# ---- 2. release verification ----
INSTALLER="$SCRIPT_DIR/install-runtime.mjs"
if [ -z "$RELEASE_PATH" ] || [ -z "$NODE_EXE" ]; then
  nr RELEASE_UNVERIFIED "release" "active.json lacks releasePath or nodeExecutable (read with node JSON.parse)"
elif [ ! -x "$NODE_EXE" ]; then
  nr RELEASE_UNVERIFIED "release" "nodeExecutable $NODE_EXE from active.json is not executable (checked with test -x)"
else
  VOUT="$("$NODE_EXE" "$INSTALLER" --verify-release "$RELEASE_PATH" --prefix "$P" 2>&1)"
  VRC=$?
  if [ "$VRC" -eq 0 ]; then
    ok "release" "$NODE_EXE install-runtime.mjs --verify-release passed for $RELEASE_PATH"
  else
    nr RELEASE_UNVERIFIED "release" "$NODE_EXE install-runtime.mjs --verify-release $RELEASE_PATH exited $VRC: $(printf '%s' "$VOUT" | tail -n 1)"
  fi
fi

# ---- 3. service receipt and manager ----
if [ ! -f "$P/service.json" ]; then
  nr SERVICE_NOT_REGISTERED "service-receipt" "no file at $P/service.json (checked with test -f); no service was registered"
  finish
fi
PORT="$(jget "$P/service.json" port)" || tooling "TOOLING_ERROR could not read or parse $P/service.json"
MANAGER="$(jget "$P/service.json" manager)"
SVC_NAME="$(jget "$P/service.json" name)"
PUBLIC_ORIGIN="$(jget "$P/service.json" public_origin)"
case "$PORT" in ''|*[!0-9]*) nr SERVICE_NOT_REGISTERED "service-receipt" "$P/service.json has no numeric port"; finish ;; esac

PM2_STATE=""
pm2_state() { # sets PM2_STATE = "app|noapp tunnel|notunnel council|nocouncil"
  local list=""
  if command -v pm2 >/dev/null 2>&1; then list="$(pm2 jlist 2>/dev/null)"; fi
  PM2_STATE="$(printf '%s' "$list" | "$NODE" -e '
    let l = []; try { l = JSON.parse(require("fs").readFileSync(0, "utf8")); } catch (e) {}
    const on = (f) => l.some((a) => f(a.name || "") && a.pm2_env && a.pm2_env.status === "online");
    console.log((on((n) => n === process.argv[1]) ? "app" : "noapp") + " " + (on((n) => /cloudflared/.test(n)) ? "tunnel" : "notunnel")
      + " " + (on((n) => n === "cloudflared-council") ? "council" : "nocouncil"));' "$SVC_NAME")"
}

case "$MANAGER" in
  launchd)
    if ! command -v launchctl >/dev/null 2>&1; then
      nr SERVICE_NOT_REGISTERED "service-manager" "manager is launchd but launchctl is not on PATH"
    else
      LOUT="$(launchctl print "gui/$(id -u)/$SVC_NAME" 2>&1)"
      if printf '%s' "$LOUT" | grep -q 'state = running'; then
        ok "service-manager" "launchctl print gui/$(id -u)/$SVC_NAME shows state = running"
      else
        nr SERVICE_NOT_REGISTERED "service-manager" "launchctl print gui/$(id -u)/$SVC_NAME did not show state = running"
      fi
    fi ;;
  pm2)
    pm2_state
    case "$PM2_STATE" in
      "app "*) ok "service-manager" "pm2 jlist shows $SVC_NAME online" ;;
      *) nr SERVICE_NOT_REGISTERED "service-manager" "pm2 jlist did not show an online app named $SVC_NAME (pm2 on PATH: $(command -v pm2 >/dev/null 2>&1 && echo yes || echo no))" ;;
    esac ;;
  external) skip "service-manager" "manager is external; no launchd or pm2 check" ;;
  *) nr SERVICE_NOT_REGISTERED "service-manager" "$P/service.json manager is '${MANAGER}', expected launchd, pm2 or external" ;;
esac

# ---- 4. GET /status ----
http() { # url -> sets HCODE, HBODY, HREDIR; never follows redirects
  local out
  out="$("$CURL" -s --noproxy '*' --max-time 8 -o - -w '\n%{http_code} %{redirect_url}' "$1" 2>/dev/null)"
  HCODE="$(printf '%s' "$out" | tail -n 1 | cut -d' ' -f1)"
  HREDIR="$(printf '%s' "$out" | tail -n 1 | cut -s -d' ' -f2-)"
  HBODY="$(printf '%s' "$out" | sed '$d')"
  [ -n "$HCODE" ] || HCODE=000
}
BASE="http://127.0.0.1:$PORT"
http "$BASE/status"
case "$HCODE" in
  2??)
    ok "service-status" "GET $BASE/status answered $HCODE"
    # ---- 5. routes ----
    http "$BASE/api/council/routes"
    if [ "${HCODE#2}" = "$HCODE" ]; then
      nr NO_USABLE_ROUTE "routes" "GET $BASE/api/council/routes answered $HCODE, expected 200"
    else
      RT="$(printf '%s' "$HBODY" | "$NODE" -e '
        let j = {}; try { j = JSON.parse(require("fs").readFileSync(0, "utf8")); } catch (e) {}
        const rs = Array.isArray(j.routes) ? j.routes : [];
        const usable = (r) => r.usable === true || (r.usable === undefined && r.composable === true);
        process.stdout.write(JSON.stringify(rs.map((r) => ({ id: r.route_id || r.id || "?", usable: usable(r) }))));')"
      [ -n "$RT" ] && ROUTES_JSON="$RT"
      NUSABLE="$(printf '%s' "$ROUTES_JSON" | "$NODE" -e 'const r=JSON.parse(require("fs").readFileSync(0,"utf8"));console.log(r.filter(x=>x.usable).length)')"
      LIST="$(printf '%s' "$ROUTES_JSON" | "$NODE" -e 'const r=JSON.parse(require("fs").readFileSync(0,"utf8"));console.log(r.map(x=>x.id+"="+(x.usable?"usable":"unusable")).join(", ")||"none")')"
      if [ "$NUSABLE" -ge 1 ] 2>/dev/null; then
        ok "routes" "GET /api/council/routes lists $NUSABLE usable route(s): $LIST"
      else
        nr NO_USABLE_ROUTE "routes" "GET /api/council/routes lists no usable route (routes: $LIST)"
      fi
    fi ;;
  *)
    nr SERVICE_DOWN "service-status" "GET $BASE/status answered $HCODE (000 means no connection) with curl --max-time 8"
    skip "routes" "not checked because the service did not answer" ;;
esac

# ---- 6. CLI shim ----
if command -v blackceo-council >/dev/null 2>&1; then
  ok "cli-shim" "blackceo-council resolves at $(command -v blackceo-council)"
elif [ -x "$P/bin/blackceo-council" ]; then
  ok "cli-shim" "$P/bin/blackceo-council is executable (not on PATH)"
else
  dg CLI_SHIM_MISSING "cli-shim" "blackceo-council is not on PATH and $P/bin/blackceo-council is not executable (checked with command -v and test -x)"
fi

# ---- 7. public origin and Access gate ----
if [ -z "$PUBLIC_ORIGIN" ]; then
  dg PUBLIC_ORIGIN_UNSET "public-origin" "public_origin is null in $P/service.json; the client has no chamber link yet (operator runs provision-council-access.sh --apply)"
else
  # Probe /status, not /: the service answers / with a 302 to its own /chamber/,
  # which an open address would return too. /status is always a 2xx when open.
  GATE_URL="${PUBLIC_ORIGIN%/}/status"
  http "$GATE_URL"
  REDIR_HOST="$(printf '%s' "$HREDIR" | sed -e 's#^[a-zA-Z]*://##' -e 's#[/:?].*$##')"
  PUB_HOST="$(printf '%s' "$PUBLIC_ORIGIN" | sed -e 's#^[a-zA-Z]*://##' -e 's#[/:?].*$##')"
  case "$HCODE" in
    301|302|303|307|308)
      case "$REDIR_HOST" in
        *.cloudflareaccess.com) ok "access-gate" "GET $GATE_URL answered $HCODE to $REDIR_HOST (Cloudflare Access sign-in)" ;;
        "$PUB_HOST") nr ACCESS_GATE_OPEN "access-gate" "GET $GATE_URL answered $HCODE to its own host $PUB_HOST with no Access sign-in: the chamber is open to the internet" ;;
        *) dg ACCESS_GATE_MISSING "access-gate" "GET $GATE_URL answered $HCODE to '${REDIR_HOST}', not *.cloudflareaccess.com" ;;
      esac ;;
    2??) nr ACCESS_GATE_OPEN "access-gate" "GET $GATE_URL answered $HCODE with no Access sign-in: the chamber is open to the internet" ;;
    *) dg ACCESS_GATE_MISSING "access-gate" "GET $GATE_URL answered $HCODE, expected a 3xx to *.cloudflareaccess.com (000 means no connection)" ;;
  esac
fi

# ---- 8. VPS only: the tunnel must run inside the container ----
if [ "$MANAGER" = pm2 ]; then
  case "$PM2_STATE" in
    *" council") ok "tunnel" "pm2 jlist lists cloudflared-council (the Council's own connector) online" ;;
    *" tunnel "*) ok "tunnel" "pm2 jlist lists a cloudflared app online" ;;
    *) dg TUNNEL_NOT_IN_CONTAINER "tunnel" "pm2 jlist lists no online cloudflared app; a host-side connector cannot reach the container loopback" ;;
  esac
fi

# ---- 9. the Council's own connector (only for a box given a council-<slug> tunnel) ----
TUN_TF="$ROOT/secrets/tunnel-council.token"
if [ ! -f "$TUN_TF" ]; then
  skip "council-connector" "no $TUN_TF (checked with test -f); the Council rides the Command Center tunnel"
else
  CONN_MGR="$MANAGER"
  if [ "$CONN_MGR" = external ]; then
    if [ "$(uname -s 2>/dev/null)" = Darwin ]; then CONN_MGR=launchd; else CONN_MGR=pm2; fi
  fi
  if [ "$CONN_MGR" = launchd ]; then
    if command -v launchctl >/dev/null 2>&1 && launchctl print "gui/$(id -u)/ai.blackceo.council-tunnel" 2>&1 | grep -q 'state = running'; then
      ok "council-connector" "launchctl print gui/$(id -u)/ai.blackceo.council-tunnel shows state = running"
    else
      dg COUNCIL_CONNECTOR_DOWN "council-connector" "$TUN_TF exists but launchctl print gui/$(id -u)/ai.blackceo.council-tunnel did not show state = running"
    fi
  else
    [ -n "$PM2_STATE" ] || pm2_state
    case "$PM2_STATE" in
      *" council") ok "council-connector" "pm2 jlist shows cloudflared-council online" ;;
      *) dg COUNCIL_CONNECTOR_DOWN "council-connector" "$TUN_TF exists but pm2 jlist did not show cloudflared-council online" ;;
    esac
  fi
fi

finish
