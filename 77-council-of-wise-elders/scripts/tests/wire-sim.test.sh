#!/usr/bin/env bash
# Skill 77 wire.sh simulation: runs the provisioner against temp HOMEs on spare
# ports and proves the Mac (launchd), VPS (pm2), adoption, not-ready, shim and
# public-origin behaviours. Cleans up every process, LaunchAgent and temp dir.
#
#   bash 77-council-of-wise-elders/scripts/tests/wire-sim.test.sh
#
# Env: COUNCIL_SIM_PORT_BASE (default 8950; uses base+3..base+6),
#      COUNCIL_SIM_TMP (parent for the temp dir; keep it short, pm2 sockets
#      are limited to ~100 characters).
# bash 3.2 safe. Needs node 22.13+/24+ and npm (the first build downloads or
# reuses the npm cache). Mac cases need a logged-in GUI session; they are
# skipped (reported SKIP) otherwise. VPS cases need pm2 and are skipped without it.

set -u
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
WIRE="$SKILL/wire.sh"
BASE="${COUNCIL_SIM_PORT_BASE:-8950}"
PM="$((BASE+3))"; PV="$((BASE+4))"; PB="$((BASE+5))"; PX="$((BASE+6))"
T="$(mktemp -d "${COUNCIL_SIM_TMP:-${TMPDIR:-/tmp}}/cwsim.XXXXXX")" || exit 2
LABELS=""; PM2_HOMES=""; PIDS=""
FAILS=0; PASSES=0
UIDN="$(id -u)"

cleanup() {
  for l in $LABELS; do launchctl bootout "gui/$UIDN/$l" >/dev/null 2>&1; done
  for h in $PM2_HOMES; do PM2_HOME="$h" "${PM2BIN:-pm2}" kill >/dev/null 2>&1; done
  for p in $PIDS; do kill "$p" >/dev/null 2>&1; wait "$p" 2>/dev/null; done
  rm -rf "$T"
}
trap cleanup EXIT

ok()   { PASSES=$((PASSES+1)); echo "PASS $1"; }
bad()  { FAILS=$((FAILS+1)); echo "FAIL $1"; }
check() { # <name> <command...>
  local n="$1"; shift
  if "$@" >/dev/null 2>&1; then ok "$n"; else bad "$n"; fi
}
has() { case "$1" in *"$2"*) return 0 ;; esac; return 1; }
jget() { node -e 'try{const v=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"))[process.argv[2]];if(v!=null)process.stdout.write(String(v))}catch(e){}' "$1" "$2"; }
healthy() { curl -fsS -m 3 "http://127.0.0.1:$1/api/council/health" 2>/dev/null | grep -q '"ok":true'; }
wait_healthy() { local i=0; while [ "$i" -lt "$2" ]; do healthy "$1" && return 0; sleep 1; i=$((i+1)); done; return 1; }
mac_pid() { launchctl print "gui/$UIDN/$1" 2>/dev/null | awk '/^\tpid = /{print $3}'; }
tree_state() { git -C "$SKILL" status --porcelain -- . 2>/dev/null | sort; }

TREE_BEFORE="$(tree_state)"

# ------------------------------------------------------------------ Mac cases
if [ "$(uname -s)" = "Darwin" ] && launchctl print "gui/$UIDN" >/dev/null 2>&1; then
  H="$T/mac"; L="ai.blackceo.council-service.sim$$"; LABELS="$LABELS $L"
  mkdir -p "$H/.openclaw"; echo '{"sim":true}' >"$H/.openclaw/openclaw.json"
  OCSHA="$(shasum -a 256 "$H/.openclaw/openclaw.json")"
  mac() { env HOME="$H" OPENCLAW_ROOT="$H/.openclaw" COUNCIL_SERVICE_PORT="$PM" COUNCIL_SERVICE_LABEL="$L" "$@"; }

  OUT="$(mac /bin/bash "$WIRE" --idempotent 2>&1)"; RC=$?
  echo "$OUT"
  [ "$RC" = 0 ] && has "$OUT" "COUNCIL_WIRE: READY" && ok "mac first run READY rc=0" || bad "mac first run READY rc=0"
  check "mac active.json + service.json exist" test -f "$H/.openclaw/council-runtime/active.json" -a -f "$H/.openclaw/council-runtime/service.json"
  check "mac plist lints" plutil -lint "$H/Library/LaunchAgents/$L.plist"
  check "mac /status answers" curl -fsS -m 3 "http://127.0.0.1:$PM/status"
  check "mac health ok" healthy "$PM"
  [ "$(jget "$H/.openclaw/council-runtime/service.json" public_origin)" = "" ] && ok "mac public_origin null without build-state" || bad "mac public_origin null without build-state"
  PID1="$(mac_pid "$L")"

  OUT="$(mac /bin/bash "$WIRE" --idempotent 2>&1)"; RC=$?
  echo "$OUT"
  [ "$RC" = 0 ] && has "$OUT" "COUNCIL_WIRE: NOOP" && [ "$(mac_pid "$L")" = "$PID1" ] && ok "mac second run NOOP same pid" || bad "mac second run NOOP same pid"

  kill "$PID1" 2>/dev/null; i=0; PID2=""
  while [ "$i" -lt 20 ]; do sleep 1; PID2="$(mac_pid "$L")"; [ -n "$PID2" ] && [ "$PID2" != "$PID1" ] && healthy "$PM" && break; i=$((i+1)); done
  [ -n "$PID2" ] && [ "$PID2" != "$PID1" ] && healthy "$PM" && ok "mac KeepAlive restarts after kill" || bad "mac KeepAlive restarts after kill"

  # launcher content (case 11)
  NODEX="$(jget "$H/.openclaw/council-runtime/active.json" nodeExecutable)"
  REL="$(jget "$H/.openclaw/council-runtime/active.json" releasePath)"
  LC="$(cat "$H/.openclaw/council-runtime/bin/council-service")"
  has "$LC" "$NODEX" && has "$LC" "$REL/node_modules/tsx/dist/cli.mjs" && ! has "$LC" "/usr/bin/env node" && ! has "$LC" "node_modules/.bin/tsx" && ok "launcher bakes absolute node + tsx cli" || bad "launcher bakes absolute node + tsx cli"

  # shim (case 9)
  SH="$H/.local/bin/blackceo-council"
  [ "$(sed -n 2p "$SH")" = "# managed-by: 77-council-of-wise-elders/wire.sh" ] && ok "shim marker" || bad "shim marker"
  RT="$("$SH" routes --json 2>&1)"
  has "$RT" "harness_defaults" && ok "shim routes answers from the service" || bad "shim routes answers from the service"

  # public origin (case 10): re-run with the build-state file
  mkdir -p "$H/.openclaw/workspace"
  echo '{"commandCenterUrl":"https://qcbox.zerohumanworkforce.com"}' >"$H/.openclaw/workspace/.workforce-build-state.json"
  OUT="$(mac env COUNCIL_PUBLIC_ORIGIN_SKIP_PROBE=1 /bin/bash "$WIRE" --idempotent 2>&1)"; echo "$OUT"
  [ "$(jget "$H/.openclaw/council-runtime/service.json" public_origin)" = "https://qcbox-council.zerohumanworkforce.com" ] && grep -q "WISE_ELDERS_PUBLIC_ORIGIN='https://qcbox-council.zerohumanworkforce.com'" "$SH" && ok "public origin from hostname rule" || bad "public origin from hostname rule"

  # release change: scratch copy of the skill with one runtime source edit
  SC="$T/skillcopy"; mkdir -p "$SC"; cp -R "$SKILL/." "$SC/"
  echo "// sim edit $$" >>"$SC/runtime/src/service/identity.ts"
  REL1="$(jget "$H/.openclaw/council-runtime/service.json" release_id)"
  OUT="$(mac /bin/bash "$SC/wire.sh" --idempotent 2>&1)"; RC=$?
  echo "$OUT"
  PID3="$(mac_pid "$L")"
  [ "$RC" = 0 ] && [ "$(jget "$H/.openclaw/council-runtime/service.json" release_id)" != "$REL1" ] && [ "$PID3" != "$PID2" ] && healthy "$PM" && ok "release change: new release_id, new pid, healthy" || bad "release change: new release_id, new pid, healthy"
  [ "$(shasum -a 256 "$H/.openclaw/openclaw.json")" = "$OCSHA" ] && ok "openclaw.json untouched" || bad "openclaw.json untouched"

  # adoption (case 7) with a foreign shim pre-seeded (case 9): service on $PM is running
  A="$T/adopt"; mkdir -p "$A/.openclaw" "$A/.local/bin"; printf '#!/bin/sh\necho foreign\n' >"$A/.local/bin/blackceo-council"
  FSUM="$(shasum -a 256 "$A/.local/bin/blackceo-council")"
  OUT="$(env HOME="$A" OPENCLAW_ROOT="$A/.openclaw" COUNCIL_SERVICE_PORT="$PM" COUNCIL_SERVICE_LABEL="$L.other" /bin/bash "$WIRE" --idempotent 2>&1)"; RC=$?
  echo "$OUT"
  [ "$RC" = 0 ] && has "$OUT" "COUNCIL_WIRE: ADOPTED_EXISTING" && ok "adopts a running Council" || bad "adopts a running Council"
  [ ! -e "$A/Library/LaunchAgents/$L.other.plist" ] && ! launchctl print "gui/$UIDN/$L.other" >/dev/null 2>&1 && ok "adoption creates no plist or job" || bad "adoption creates no plist or job"
  has "$OUT" "SHIM_KEPT_EXISTING" && [ "$(shasum -a 256 "$A/.local/bin/blackceo-council")" = "$FSUM" ] && ok "foreign shim kept byte-for-byte" || bad "foreign shim kept byte-for-byte"
else
  echo "SKIP mac cases (not Darwin or no GUI session)"
fi

# ---------------------------------------------------------- not-ready (case 8)
N="$T/nr"; mkdir -p "$N/.openclaw"
printf '#!/bin/sh\necho v20.11.0\n' >"$T/fakenode"; chmod +x "$T/fakenode"
OUT="$(env HOME="$N" OPENCLAW_ROOT="$N/.openclaw" COUNCIL_NODE="$T/fakenode" /bin/bash "$WIRE" 2>&1)"; RC=$?
[ "$RC" = 0 ] && has "$OUT" "NOT_READY NODE_TOO_OLD" && ok "NODE_TOO_OLD exit 0" || bad "NODE_TOO_OLD exit 0"

python3 -m http.server "$PX" --bind 127.0.0.1 >/dev/null 2>&1 & PIDS="$PIDS $!"
sleep 1
OUT="$(env HOME="$N" OPENCLAW_ROOT="$N/.openclaw" COUNCIL_SERVICE_PORT="$PX" COUNCIL_SERVICE_LABEL="ai.blackceo.council-service.nr$$" /bin/bash "$WIRE" 2>&1)"; RC=$?
[ "$RC" = 0 ] && has "$OUT" "NOT_READY PORT_IN_USE" && ok "PORT_IN_USE exit 0, nothing started" || bad "PORT_IN_USE exit 0, nothing started"

OUT="$(env HOME="$N" OPENCLAW_ROOT="$N/.openclaw" COUNCIL_WIRE_PLATFORM=vps COUNCIL_PM2="$T/no-such-pm2" /bin/bash "$WIRE" 2>&1)"; RC=$?
[ "$RC" = 0 ] && has "$OUT" "NOT_READY NO_PM2" && ok "NO_PM2 exit 0" || bad "NO_PM2 exit 0"

printf '#!/bin/sh\nexit 1\n' >"$T/badnpm"; chmod +x "$T/badnpm"
mkdir -p "$T/bf/.openclaw"
OUT="$(env HOME="$T/bf" OPENCLAW_ROOT="$T/bf/.openclaw" COUNCIL_SERVICE_PORT="$PB" COUNCIL_SERVICE_LABEL="ai.blackceo.council-service.bf$$" COUNCIL_NPM="$T/badnpm" /bin/bash "$WIRE" 2>&1)"; RC=$?
[ "$RC" = 1 ] && has "$OUT" "NOT_READY RUNTIME_BUILD_FAILED" && ok "RUNTIME_BUILD_FAILED exits 1 (only non-zero case)" || bad "RUNTIME_BUILD_FAILED exits 1 (only non-zero case)"

# ------------------------------------------------------------------ VPS (case 6)
PM2BIN="${COUNCIL_PM2:-$(command -v pm2 2>/dev/null)}"
if [ -n "$PM2BIN" ] && [ -x "$PM2BIN" ]; then
  V="$T/data"; mkdir -p "$V/.openclaw"; APP="council-sim$$"; PM2_HOMES="$V/.pm2"
  vps() { env -u PM2_HOME HOME="$V" OPENCLAW_ROOT="$V/.openclaw" PM2_HOME="$V/.pm2" COUNCIL_WIRE_PLATFORM=vps COUNCIL_PM2="$PM2BIN" COUNCIL_PM2_APP="$APP" COUNCIL_SERVICE_PORT="$PV" NODE_ENV=production "$@"; }
  OUT="$(vps /bin/bash "$WIRE" --idempotent 2>&1)"; RC=$?
  echo "$OUT"
  [ "$RC" = 0 ] && has "$OUT" "COUNCIL_WIRE: READY" && ok "vps READY with NODE_ENV=production (dev deps forced)" || bad "vps READY with NODE_ENV=production (dev deps forced)"
  PP="$(PM2_HOME="$V/.pm2" "$PM2BIN" pid "$APP" 2>/dev/null | tail -1 | tr -dc 0-9)"
  [ -n "$PP" ] && [ "$PP" != 0 ] && ok "vps pm2 app online" || bad "vps pm2 app online"
  grep -q "$APP" "$V/.pm2/dump.pm2" 2>/dev/null && ok "vps dump.pm2 lists the app" || bad "vps dump.pm2 lists the app"
  OUT="$(vps /bin/bash "$WIRE" --idempotent 2>&1)"; has "$OUT" "COUNCIL_WIRE: NOOP" && ok "vps second run NOOP" || bad "vps second run NOOP"
  PM2_HOME="$V/.pm2" "$PM2BIN" kill >/dev/null 2>&1; sleep 1
  PM2_HOME="$V/.pm2" "$PM2BIN" resurrect >/dev/null 2>&1
  wait_healthy "$PV" 45 && ok "vps app answers after pm2 kill + resurrect" || bad "vps app answers after pm2 kill + resurrect"
  PM2_HOME="$V/.pm2" "$PM2BIN" kill >/dev/null 2>&1
  ! healthy "$PV" && ok "vps stopped after cleanup" || bad "vps stopped after cleanup"
else
  echo "SKIP vps cases (pm2 not found)"
fi

# --------------------------------------------------------------- skill folder
[ "$(tree_state)" = "$TREE_BEFORE" ] && ok "nothing written inside the skill folder" || bad "nothing written inside the skill folder"

echo "wire-sim: $PASSES passed, $FAILS failed"
[ "$FAILS" = 0 ]
