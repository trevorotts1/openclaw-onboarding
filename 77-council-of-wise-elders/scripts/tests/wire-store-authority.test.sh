#!/usr/bin/env bash
# Skill 77 wire.sh store authority: a rewire must never re-point the live
# service at an empty default store (operator box, 2026-10-29: active.json said
# ~/.openclaw/council-data with 0 sessions while the running service held 9
# sessions / 1075 events in ~/Library/Application Support/wise-elders/service).
# With the service DOWN there is no open file to ask, so the previous launcher,
# the LaunchAgent WorkingDirectory and the service's own last front_door_started
# record are the witnesses. Runs wire.sh's section 5a in isolation with a fake
# lsof on PATH: no service, no network, no build, no node. bash 3.2 safe.
#   bash 77-council-of-wise-elders/scripts/tests/wire-store-authority.test.sh
set -u
WIRE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)/wire.sh"
T="$(mktemp -d "${TMPDIR:-/tmp}/wsa.XXXXXX")" || exit 2
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin"
# Fake lsof: -iTCP prints the listener pid, -p prints the open council.db path.
cat >"$T/bin/lsof" <<'LSOF'
#!/bin/sh
case "$*" in
  *-iTCP*) [ -n "${STUB_PID:-}" ] && printf '%s\n' "$STUB_PID"; exit 0 ;;
  *-p*)    [ -n "${STUB_DB:-}" ] && printf 'n%s\n' "$STUB_DB"; exit 0 ;;
esac
exit 1
LSOF
chmod +x "$T/bin/lsof"
# section 5a only, plus the few helpers it calls (say/jget/notready) and the
# paths the recorded-witness readers look at.
{
  echo 'say() { printf "COUNCIL_WIRE: %s\n" "$*"; }'
  echo 'notready() { say "NOT_READY $1 $2"; exit 0; }'
  echo 'jget() { sed -n "s/.*\"dataDir\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$1" 2>/dev/null | head -1; }'
  echo "OC=\"\$T/oc\"; P=\"\$T/oc/council-runtime\"; PORT=8787; DATA=\"\""
  echo 'PLIST="$T/oc/LaunchAgent.plist"; LOG="$T/oc/logs/council-service.log"'
  sed -n '/^# -* 5a\. durable store authority/,/^# -* 5\. build/p' "$WIRE" | sed '$d'
  echo 'printf "DATA=[%s] SRC=[%s]\n" "$DATA" "$DATA_SOURCE"'
} >"$T/sec5a.sh"

FAILS=0
# CASE_L / CASE_P / CASE_G: data dir each recorded witness names, or "-" for
# "that witness does not exist".
run() { # <name> <pid> <db> <recorded-dataDir|-> <want DATA|UNKNOWN> <want SRC> <expect STORE_SWITCH yes|no> [env...]
  local n="$1" pid="$2" db="$3" rec="$4" want="$5" wsrc="$6" wsw="$7"; shift 7
  rm -rf "$T/oc"; mkdir -p "$T/oc/council-runtime/bin" "$T/oc/logs"
  if [ "$rec" != "-" ]; then printf '{"dataDir":"%s"}\n' "$rec" >"$T/oc/council-runtime/active.json"; fi
  if [ "${CASE_L:--}" != "-" ]; then
    printf "#!/bin/sh\nCOUNCIL_SERVICE_DATA_DIR='%s'; export COUNCIL_SERVICE_DATA_DIR\n" "$CASE_L" \
      >"$T/oc/council-runtime/bin/council-service"
  fi
  if [ "${CASE_P:--}" != "-" ]; then
    {
      echo '<?xml version="1.0" encoding="UTF-8"?>'
      echo '<plist version="1.0"><dict>'
      echo "  <key>WorkingDirectory</key><string>$CASE_P</string>"
      echo '</dict></plist>'
    } >"$T/oc/LaunchAgent.plist"
  fi
  if [ "${CASE_G:--}" != "-" ]; then
    printf '{"event":"front_door_started","outcome":"ready","origin":"http://127.0.0.1:8787","port":8787,"blockers":[],"dataDir":"%s","pid":1}\n' "$CASE_G" \
      >"$T/oc/logs/council-service.log"
  fi
  local out; out="$(env PATH="$T/bin:$PATH" STUB_PID="$pid" STUB_DB="$db" T="$T" "$@" bash "$T/sec5a.sh" 2>&1)"
  local sw=no unk=no
  case "$out" in *STORE_SWITCH*) sw=yes ;; esac
  case "$out" in *STORE_AUTHORITY_UNKNOWN*) unk=yes ;; esac
  if [ "$want" = "UNKNOWN" ]; then
    if [ "$unk" = yes ] && [ "$sw" = no ]; then echo "PASS $n"; else echo "FAIL $n: $out"; FAILS=$((FAILS+1)); fi
    return
  fi
  if case "$out" in *"DATA=[$want] SRC=[$wsrc]"*) true ;; *) false ;; esac && [ "$sw" = "$wsw" ] && [ "$unk" = no ]; then
    echo "PASS $n"
  else
    echo "FAIL $n: $out"
    FAILS=$((FAILS+1))
  fi
}
reset_case() { CASE_L="-"; CASE_P="-"; CASE_G="-"; }

mkdir -p "$T/live" "$T/empty" "$T/nodb" "$T/plain" "$T/plain2"
: >"$T/live/council.db"
: >"$T/empty/council.db"
LIVE="$T/live"; EMPTY="$T/empty"; NODB="$T/nodb"; PLAIN="$T/plain"

reset_case; run "the live service's own store wins over active.json" 42 "$LIVE/council.db" "$EMPTY" "$LIVE" "live service store" no
reset_case; run "no running service: the recorded store is kept" "" "" "$EMPTY" "$EMPTY" "active.json" no
reset_case; run "nothing recorded: the default store (fresh install)" "" "" "-" "$T/oc/council-data" "default" no
reset_case; run "COUNCIL_DATA_DIR wins and the switch is announced" 42 "$LIVE/council.db" "$EMPTY" "$T/named" "COUNCIL_DATA_DIR" yes COUNCIL_DATA_DIR="$T/named"
reset_case; run "an explicit store equal to the live one is silent" 42 "$LIVE/council.db" "$EMPTY" "$LIVE" "COUNCIL_DATA_DIR" no COUNCIL_DATA_DIR="$LIVE"
reset_case; run "a listener without an open council.db falls back to active.json" 42 "" "$EMPTY" "$EMPTY" "active.json" no

# --- service DOWN: the recorded witnesses decide (the CTR-106 FAIL-1 case) ---
# NODB is the operator box's re-pointed default: the directory exists, the
# service never started on it, so it holds no council.db.
reset_case; CASE_L="$NODB"; CASE_P="$NODB"; CASE_G="$LIVE"
run "service down: the store the service last served beats a launcher+plist+active.json that all agree on the empty default" "" "" "$NODB" "$LIVE" "previous service log" no

reset_case; CASE_G="$LIVE"
run "service down: the service log alone is enough to keep the real store" "" "" "$NODB" "$LIVE" "previous service log" no

reset_case; CASE_L="$LIVE"
run "service down: the previous launcher's recorded store beats an empty active.json" "" "" "$NODB" "$LIVE" "previous launcher" no

reset_case; CASE_P="$LIVE"
run "service down: the LaunchAgent WorkingDirectory beats an empty active.json" "" "" "$NODB" "$LIVE" "LaunchAgent" no

reset_case; CASE_L="$NODB"
run "service down: one existing recorded dir with no council.db yet is kept, not replaced by the default" "" "" "-" "$NODB" "previous launcher" no

reset_case; CASE_L="$LIVE"; CASE_P="$EMPTY"
run "service down: two recorded dirs holding a store cannot be resolved" "" "" "-" "UNKNOWN" "" no

reset_case; CASE_L="$PLAIN"; CASE_P="$T/plain2"
run "service down: two recorded dirs with no store cannot be resolved" "" "" "-" "UNKNOWN" "" no
echo "wire-store-authority: $FAILS failed"
[ "$FAILS" = 0 ]
