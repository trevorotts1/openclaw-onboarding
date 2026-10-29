#!/usr/bin/env bash
# managed-by: 77-council-of-wise-elders/wire.sh
#
# Skill 77 (Council of Wise Elders) box provisioner. update-skills.sh runs this
# as `bash wire.sh --idempotent` after every full sync (and install.sh runs it
# on a fresh install). It:
#   1. builds the Council runtime into $OPENCLAW_ROOT/council-runtime (the
#      installer is a no-op when nothing changed),
#   2. keeps the Council service running (Mac: LaunchAgent, VPS: pm2 app) and
#      restarts it when the release changes,
#   3. puts the blackceo-council CLI on PATH for the box's agent,
#   4. when the operator delivered <OPENCLAW_ROOT>/secrets/tunnel-council.token
#      (a box whose Command Center tunnel is local-managed gets its own
#      remote-managed council-<slug> tunnel), keeps that tunnel's connector
#      running: Mac LaunchAgent ai.blackceo.council-tunnel, VPS pm2 app
#      cloudflared-council, `cloudflared tunnel run --token-file <file>`. It is
#      restarted only when the token file or the cloudflared path changes; the
#      Command Center's own connector is never touched; the token value is
#      never printed or logged. No token file = no-op (most boxes),
#   5. verifies the copy the runtime RESOLVER selects
#      (scripts/selected-tree-gate.mjs): competing copies are reported loudly
#      and a stale, contract-drifted or executable-less selected copy exits 1,
#      so no roll reports success after updating only an unused directory. On a
#      box with several copies the gate is given the folder the OpenClaw agent
#      resolver serves (COUNCIL_AGENT_SKILL_DIR, else asked of the resolver).
# It writes nothing inside the skill folder and touches no credential, model,
# openclaw.json, AGENTS.md, gateway or Command Center.
#
# One typed line is printed:
#   COUNCIL_WIRE: READY|NOOP|ADOPTED_EXISTING|DEFERRED_NO_GUI|NOT_READY <CODE> <detail>
# plus, only when the connector token file exists, one line before it:
#   COUNCIL_CONNECTOR: READY|NOOP|DEFERRED_NO_GUI|NOT_READY <CODE> <detail>
# The store decision is announced on its own lines, and only when it needs
# saying: COUNCIL_WIRE: STORE_AUTHORITY_RESOLVED <dir> (<source>; ...) when the
# store this run will keep differs from what active.json recorded,
# STORE_SWITCH <live> -> <new> when a running service is being moved, and
# NOT_READY STORE_AUTHORITY_UNKNOWN|STORE_AUTHORITY_MISMATCH when the history
# cannot be resolved or the installer did not record the chosen store.
# --connector-only runs the connector step and exits 0 (no build, no service).
# Exit 0 for every state except RUNTIME_BUILD_FAILED (exit 1), so a transient
# npm failure withholds the .wired sentinel and the next roll retries.
#
# Env: COUNCIL_WIRE_PLATFORM (mac|vps) COUNCIL_NODE COUNCIL_NPM COUNCIL_PM2
#      COUNCIL_SERVICE_PORT (8787) COUNCIL_SERVICE_LABEL (ai.blackceo.council-service)
#      COUNCIL_PM2_APP (council-of-wise-elders) OPENCLAW_ROOT CC_PUBLIC_URL
#      MC_TENANT_PUBLIC_URL COUNCIL_PUBLIC_ORIGIN (the chamber link origin; wins
#      over every derived source) COUNCIL_DATA_DIR (the store to keep; default is
#      the live service's open council.db, else the store the previous launcher,
#      LaunchAgent or service log names) COUNCIL_CLOUDFLARED (absolute
#      cloudflared path)
#      COUNCIL_AGENT_SKILL_DIR (skill folder the agent resolves) COUNCIL_OPENCLAW
#      (openclaw CLI path) OPENCLAW_AGENT_ID (agent the resolver is asked for)
#
# bash 3.2 safe (macOS system bash): no bash-4-only features.

set -u

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
MARK="managed-by: 77-council-of-wise-elders/wire.sh"

CONNECTOR_ONLY=0
for _a in "$@"; do
  case "$_a" in --idempotent) ;; --connector-only) CONNECTOR_ONLY=1 ;; *) ;; esac
done

say()      { printf 'COUNCIL_WIRE: %s\n' "$*"; }
notready() { say "NOT_READY $1 $2"; exit 0; }
sq()       { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
xe()       { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }

# ---------------------------------------------------------------- 1. platform
PLATFORM="${COUNCIL_WIRE_PLATFORM:-}"
if [ -z "$PLATFORM" ]; then
  case "$(uname -s 2>/dev/null)" in
    Darwin) PLATFORM=mac ;;
    Linux)  PLATFORM=vps ;;
    *)      PLATFORM="" ;;
  esac
fi
case "$PLATFORM" in
  mac|vps) ;;
  *) notready UNSUPPORTED_PLATFORM "platform '${PLATFORM:-$(uname -s 2>/dev/null)}' is not mac or vps" ;;
esac
[ "$(id -u)" = "0" ] && notready RUNNING_AS_ROOT "refusing to provision the Council service as root; run as the box login user"

HOME="${HOME:-$(cd ~ 2>/dev/null && pwd)}"
if [ -n "${OPENCLAW_ROOT:-}" ]; then OC="$OPENCLAW_ROOT"
elif [ -d /data/.openclaw ]; then OC=/data/.openclaw
else OC="$HOME/.openclaw"; fi
P="$OC/council-runtime"
# Resolved in section 5a from the database the live service actually has open,
# so a rewire can never re-point the service at an empty default store.
DATA=""
LOGDIR="$OC/logs"
LOG="$LOGDIR/council-service.log"
PORT="${COUNCIL_SERVICE_PORT:-8787}"
LABEL="${COUNCIL_SERVICE_LABEL:-ai.blackceo.council-service}"
PM2_APP="${COUNCIL_PM2_APP:-council-of-wise-elders}"
UID_N="$(id -u)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
ORIGIN="http://127.0.0.1:$PORT"
TUN_TF="$OC/secrets/tunnel-council.token"
TUN_LABEL=ai.blackceo.council-tunnel
TUN_APP=cloudflared-council
TUN_PLIST="$HOME/Library/LaunchAgents/$TUN_LABEL.plist"
TUN_LOG="$LOGDIR/council-tunnel.log"
TUN_STATE="$P/council-tunnel.state"
TUN_CFG="$P/council-tunnel.yml"

# ------------------------------------------------------------------- 2. node
node_version_ok() { # <node> ; prints the version, returns 0 when supported
  local v major minor
  v="$("$1" --version 2>/dev/null | head -1 | tr -d 'v\r ')" || return 1
  [ -n "$v" ] || return 1
  printf '%s' "$v"
  major="${v%%.*}"; minor="${v#*.}"; minor="${minor%%.*}"
  case "$major$minor" in *[!0-9]*|"") return 1 ;; esac
  [ "$major" -ge 24 ] && return 0
  [ "$major" -eq 22 ] && [ "$minor" -ge 13 ] && return 0
  return 1
}

NODE=""; FOUND=""
if [ -n "${COUNCIL_NODE:-}" ]; then
  _cands="$COUNCIL_NODE"
else
  _cands="$(command -v node 2>/dev/null)
/opt/homebrew/opt/node@24/bin/node
/opt/homebrew/opt/node@26/bin/node
/opt/homebrew/opt/node@22/bin/node
/opt/homebrew/bin/node
/usr/local/bin/node
/usr/bin/node"
fi
_ifs="$IFS"; IFS='
'
for _c in $_cands; do
  IFS="$_ifs"
  [ -n "$_c" ] && [ -x "$_c" ] || continue
  if _v="$(node_version_ok "$_c")"; then NODE="$_c"; break; fi
  FOUND="$FOUND ${_c}=${_v:-unknown}"
done
IFS="$_ifs"
[ -n "$NODE" ] || notready NODE_TOO_OLD "need Node 22.13+ or 24+; found:${FOUND:- none}"

if [ -n "${COUNCIL_NPM:-}" ]; then NPM="$COUNCIL_NPM"
elif [ -x "$(dirname "$NODE")/npm" ]; then NPM="$(dirname "$NODE")/npm"
else NPM="$(command -v npm 2>/dev/null || true)"; fi
[ -n "$NPM" ] && [ -x "$NPM" ] || notready NO_NPM "no npm next to $NODE or on PATH"

# ------------------------------------------------------------ tiny json tools
jget() { # <file> <key>
  "$NODE" -e 'try{const v=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"))[process.argv[2]];if(v!=null)process.stdout.write(String(v))}catch(e){}' "$1" "$2" 2>/dev/null
}
envget() { # <env file> <KEY> : the value of one key only (never prints other lines)
  "$NODE" -e 'try{let r="";for(const l of require("fs").readFileSync(process.argv[1],"utf8").split(/\r?\n/)){const m=l.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);if(m&&m[1]===process.argv[2])r=m[2].trim().replace(/^(["\x27])(.*)\1$/,"$2")}process.stdout.write(r)}catch(e){}' "$1" "$2" 2>/dev/null
}
sha_file() {
  "$NODE" -e 'const c=require("crypto"),f=require("fs");process.stdout.write(c.createHash("sha256").update(f.readFileSync(process.argv[1])).digest("hex"))' "$1"
}
tcp_open() { # <port>
  "$NODE" -e 'const s=require("net").connect({host:"127.0.0.1",port:+process.argv[1]},()=>process.exit(0));s.on("error",()=>process.exit(1));setTimeout(()=>process.exit(1),2000)' "$1" >/dev/null 2>&1
}
council_health() { # prints body, returns 0 when a Council answers ok
  local b
  b="$(curl -fsS -m 3 "$ORIGIN/api/council/health" 2>/dev/null)" || return 1
  case "$b" in *'"api_version"'*) printf '%s' "$b"; case "$b" in *'"ok":true'*) return 0 ;; esac ;; esac
  return 1
}
is_council() { # a Council identifies itself even when not yet ok
  local b
  b="$(curl -fsS -m 3 "$ORIGIN/api/council/health" 2>/dev/null)" || return 1
  case "$b" in *'"api_version"'*) return 0 ;; esac
  return 1
}

# ------------------------------------------------------------------ 3. VPS pm2
PM2=""
if [ "$PLATFORM" = "vps" ]; then
  if [ -z "${PM2_HOME:-}" ] && [ -d "$OC/.pm2" ]; then export PM2_HOME="$OC/.pm2"; fi
  if [ -n "${COUNCIL_PM2:-}" ]; then
    [ -x "$COUNCIL_PM2" ] && PM2="$COUNCIL_PM2"
  else
    for _c in "$(command -v pm2 2>/dev/null)" "$OC/npm-global/bin/pm2" "$OC/../.npm-global/bin/pm2" "$HOME/.npm-global/bin/pm2" "$("$NPM" root -g 2>/dev/null)/pm2/bin/pm2"; do
      if [ -n "$_c" ] && [ -x "$_c" ]; then PM2="$_c"; break; fi
    done
  fi
  [ -n "$PM2" ] || notready NO_PM2 "pm2 not found (COUNCIL_PM2, PATH, $OC/npm-global/bin, $HOME/.npm-global/bin, npm root -g)"
fi

pm2_pid() { # [app] ; prints the app's pid digits, or empty when the app is unknown
  "$PM2" pid "${1:-$PM2_APP}" 2>/dev/null | tail -1 | tr -dc '0-9'
}
mac_loaded() { launchctl print "gui/$UID_N/${1:-$LABEL}" >/dev/null 2>&1; }
mac_gui()    { launchctl print "gui/$UID_N" >/dev/null 2>&1; }

# ------------------------------------------- 3b. Council tunnel connector
# Only for a box the operator gave a dedicated council-<slug> tunnel (its
# Command Center tunnel is local-managed). Never touches the Command Center
# connector; never prints, logs or passes the token value on argv.
csay() { printf 'COUNCIL_CONNECTOR: %s\n' "$*"; }
tun_cloudflared() { # absolute cloudflared path, or rc 1
  local c
  if [ -n "${COUNCIL_CLOUDFLARED:-}" ]; then
    [ -x "$COUNCIL_CLOUDFLARED" ] && { printf '%s' "$COUNCIL_CLOUDFLARED"; return 0; }
    return 1
  fi
  for c in "$(command -v cloudflared 2>/dev/null)" /opt/homebrew/bin/cloudflared /usr/local/bin/cloudflared /usr/bin/cloudflared "$OC/bin/cloudflared"; do
    case "$c" in /*) [ -x "$c" ] && { printf '%s' "$c"; return 0; } ;; esac
  done
  return 1
}
council_connector() {
  [ -f "$TUN_TF" ] || return 0
  chmod 600 "$TUN_TF" 2>/dev/null
  if [ ! -r "$TUN_TF" ] || [ ! -s "$TUN_TF" ]; then
    csay "NOT_READY TOKEN_UNREADABLE $TUN_TF is empty or unreadable; nothing started"; return 0
  fi
  local cf fp prev pchanged=0 changed=0 pid i _n
  cf="$(tun_cloudflared)" || { csay "NOT_READY NO_CLOUDFLARED cloudflared not found (COUNCIL_CLOUDFLARED, PATH, /opt/homebrew/bin, /usr/local/bin, /usr/bin, $OC/bin); nothing started"; return 0; }
  fp="$(sha_file "$TUN_TF") $cf"           # token fingerprint + binary; never the token
  mkdir -p "$P" "$LOGDIR" 2>/dev/null
  prev="$(cat "$TUN_STATE" 2>/dev/null)"
  # Own config: without --config cloudflared loads ~/.cloudflared/config.yml,
  # which on these boxes is the Command Center's local-managed tunnel config.
  [ "$(cat "$TUN_CFG" 2>/dev/null)" = "no-autoupdate: true" ] || printf 'no-autoupdate: true\n' >"$TUN_CFG"
  if [ "$PLATFORM" = "mac" ]; then
    mkdir -p "$(dirname "$TUN_PLIST")"
    cat >"$TUN_PLIST.tmp.$$" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$(xe "$TUN_LABEL")</string>
  <key>ProgramArguments</key>
  <array><string>$(xe "$cf")</string><string>tunnel</string><string>--config</string><string>$(xe "$TUN_CFG")</string><string>--no-autoupdate</string><string>--protocol</string><string>http2</string><string>run</string><string>--token-file</string><string>$(xe "$TUN_TF")</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>EnvironmentVariables</key><dict><key>TUNNEL_TOKEN</key><string></string></dict>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProcessType</key><string>Standard</string>
  <key>StandardOutPath</key><string>$(xe "$TUN_LOG")</string>
  <key>StandardErrorPath</key><string>$(xe "$TUN_LOG")</string>
</dict>
</plist>
PL
    if ! plutil -lint "$TUN_PLIST.tmp.$$" >/dev/null 2>&1; then
      rm -f "$TUN_PLIST.tmp.$$"; csay "NOT_READY CONNECTOR_START_FAILED generated $TUN_LABEL plist failed plutil -lint"; return 0
    fi
    if [ -f "$TUN_PLIST" ] && cmp -s "$TUN_PLIST.tmp.$$" "$TUN_PLIST"; then rm -f "$TUN_PLIST.tmp.$$"
    else mv -f "$TUN_PLIST.tmp.$$" "$TUN_PLIST"; pchanged=1; fi
    if ! mac_gui; then
      csay "DEFERRED_NO_GUI LaunchAgent $TUN_LABEL is written and loads at the next login"; return 0
    fi
    if ! mac_loaded "$TUN_LABEL"; then
      launchctl bootstrap "gui/$UID_N" "$TUN_PLIST" >>"$TUN_LOG" 2>&1 || { csay "NOT_READY CONNECTOR_START_FAILED launchctl bootstrap failed for $TUN_LABEL"; return 0; }
      changed=1
    elif [ "$pchanged" = 1 ]; then
      launchctl bootout "gui/$UID_N/$TUN_LABEL" >>"$TUN_LOG" 2>&1
      i=0; while mac_loaded "$TUN_LABEL" && [ "$i" -lt 20 ]; do sleep 0.5; i=$((i+1)); done
      launchctl bootstrap "gui/$UID_N" "$TUN_PLIST" >>"$TUN_LOG" 2>&1 || { csay "NOT_READY CONNECTOR_START_FAILED launchctl bootstrap failed for $TUN_LABEL after plist change"; return 0; }
      changed=1
    elif [ "$fp" != "$prev" ]; then
      launchctl kickstart -k "gui/$UID_N/$TUN_LABEL" >>"$TUN_LOG" 2>&1
      changed=1
    fi
  else
    pid="$(pm2_pid "$TUN_APP")"
    if [ -z "$pid" ] || [ "$pid" = "0" ] || [ "$fp" != "$prev" ]; then
      [ -n "$pid" ] && "$PM2" delete "$TUN_APP" >>"$LOGDIR/council-pm2.log" 2>&1
      # TUNNEL_TOKEN= : an inherited TUNNEL_TOKEN (box .env) beats --token-file
      # and would run the Command Center tunnel here instead of the Council's.
      env TUNNEL_TOKEN= "$PM2" start "$cf" --name "$TUN_APP" --interpreter none --time --output "$TUN_LOG" --error "$TUN_LOG" \
        -- tunnel --config "$TUN_CFG" --no-autoupdate --protocol http2 run --token-file "$TUN_TF" >>"$LOGDIR/council-pm2.log" 2>&1 \
        || { csay "NOT_READY CONNECTOR_START_FAILED pm2 start $TUN_APP failed (see $LOGDIR/council-pm2.log)"; return 0; }
      "$PM2" save >>"$LOGDIR/council-pm2.log" 2>&1
      changed=1
    fi
  fi
  ( umask 077; printf '%s\n' "$fp" >"$TUN_STATE.tmp.$$" ) && mv -f "$TUN_STATE.tmp.$$" "$TUN_STATE"
  if [ "$PLATFORM" = "mac" ]; then _n="launchd $TUN_LABEL"; else _n="pm2 $TUN_APP"; fi
  if [ "$changed" = 1 ]; then csay "READY $_n started with token file $TUN_TF"; else csay "NOOP $_n already running with the same token"; fi
}
council_connector
[ "$CONNECTOR_ONLY" = 1 ] && exit 0

# ------------------------------------------- 4. who owns the port (before build)
OURS=0
if [ "$PLATFORM" = "mac" ]; then mac_loaded && OURS=1
else [ -n "$(pm2_pid)" ] && OURS=1; fi

ADOPT=0
if [ "$OURS" = "0" ]; then
  if is_council; then ADOPT=1
  elif tcp_open "$PORT"; then notready PORT_IN_USE "127.0.0.1:$PORT is held by something that is not a Council service; set COUNCIL_SERVICE_PORT"
  fi
fi

# ------------------------------------------------- 5a. durable store authority
# The store is the council SQLite database the LIVE service has open, and that
# is the only witness that cannot drift. Observed on the operator box
# 2026-10-29: active.json had been re-pointed at an empty
# ~/.openclaw/council-data while the running service kept serving
# ~/Library/Application Support/wise-elders/service (9 sessions, 1075 events,
# 426 jobs). Wiring from active.json alone would have stranded all of it.
#
# With the service DOWN there is no open file to ask, and active.json alone is
# NOT evidence: every earlier version of this script wrote active.json and the
# generated launcher from its own default, so launcher, LaunchAgent and
# active.json can agree on the same WRONG directory. The witnesses that do
# survive a stopped service are the ones the previous run actually used: the
# generated launcher's COUNCIL_SERVICE_DATA_DIR line, the LaunchAgent's
# WorkingDirectory, and the service's own last front_door_started record
# (service-launch.mjs prints the dataDir it served). All three are PARSED AS
# TEXT - the launcher is never sourced, never executed.
#
# Resolution: COUNCIL_DATA_DIR (explicit) -> the live listener's open council.db
# -> the one recorded directory that holds a council.db -> the one recorded
# directory that exists (a fresh install before its first service start) ->
# $OC/council-data. Two or more recorded directories that hold a store, or
# several that exist with no store among them, is history that cannot be
# resolved: NOT_READY STORE_AUTHORITY_UNKNOWN, never a silent guess. Nothing is
# copied, migrated, initialised or deleted, and no store is created here.
# ponytail: the live store is measured from the listener's open DB with lsof.
# Upgrade path is the service recording its own dataDir in service.json at
# startup (writer is runtime-owned).
live_store() { # prints the data dir of the council.db the $PORT listener holds
  local _pid _f
  command -v lsof >/dev/null 2>&1 || return 1
  _pid="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1)"
  [ -n "$_pid" ] || return 1
  _f="$(lsof -p "$_pid" -Fn 2>/dev/null | sed -n 's/^n\(.*\/council\.db\)$/\1/p' | head -1)"
  [ -n "$_f" ] && [ -f "$_f" ] || return 1
  dirname "$_f"
}
# The data dir the launcher this script generated last time records. Text only:
# the launcher is never sourced, evaluated or executed. Section 7 emits exactly
# one line, COUNCIL_SERVICE_DATA_DIR=<sq DATA_DIR>; export COUNCIL_SERVICE_DATA_DIR
# so the value is ONE single-quoted shell word, and sq() writes an apostrophe
# inside it as '\'' . That shape is decoded here (spaces and apostrophes
# included) and nothing else is: an unquoted, double-quoted, differently
# exported, empty or relative value returns 2, so the caller can fail closed
# instead of silently dropping this witness. No expansion is possible or done.
launcher_data_dir() {
  local v u _l
  v="$(sed -n "s/^COUNCIL_SERVICE_DATA_DIR=\(.*\); export COUNCIL_SERVICE_DATA_DIR\$/X\1/p" "$P/bin/council-service" 2>/dev/null | head -1)"
  if [ -z "$v" ]; then
    # No line in the generated shape. A line that still starts with the
    # assignment is a launcher this parser does not understand: refuse it (2)
    # instead of reporting "this witness says nothing" (1).
    _l="$(sed -n '/^COUNCIL_SERVICE_DATA_DIR=/p' "$P/bin/council-service" 2>/dev/null | head -1)"
    [ -n "$_l" ] && return 2
    return 1
  fi
  v="${v#X}"
  case "$v" in \'*\') ;; *) return 2 ;; esac
  v="${v#\'}"; v="${v%\'}"
  case "$v" in *"'"*)
    u="$(printf '%s' "$v" | sed "s/'\\\\''//g")"
    case "$u" in *"'"*) return 2 ;; esac
    v="$(printf '%s' "$v" | sed "s/'\\\\''/'/g")"
  ;; esac
  case "$v" in /?*) printf '%s' "$v" ;; *) return 2 ;; esac
}
# The data dir the LaunchAgent was started in (pm2 twin uses the same value).
plist_data_dir() {
  local v
  [ -f "${PLIST:-}" ] || return 1
  v="$(sed -n 's/.*<key>WorkingDirectory<\/key>[[:space:]]*<string>\(.*\)<\/string>.*/\1/p' "$PLIST" 2>/dev/null | head -1)"
  [ -n "$v" ] || return 1
  v="$(printf '%s' "$v" | sed -e 's/&lt;/</g' -e 's/&gt;/>/g' -e 's/&amp;/\&/g')"
  printf '%s' "$v"
}
# The data dir the service itself reported on its last successful start.
log_data_dir() {
  local v
  [ -f "${LOG:-}" ] || return 1
  v="$(sed -n 's/.*"event":"front_door_started".*"dataDir":"\([^"]*\)".*/\1/p' "${LOG:-}" 2>/dev/null | tail -1)"
  [ -n "$v" ] && printf '%s' "$v"
}
src_of() { # <dir> : names the FIRST witness that recorded it
  [ -n "$1" ] || return 0
  [ -n "$LIVE_DATA" ] && [ "$1" = "$LIVE_DATA" ] && { printf 'live service store'; return 0; }
  [ -n "$LOG_DATA" ] && [ "$1" = "$LOG_DATA" ] && { printf 'previous service log'; return 0; }
  [ -n "$LAUNCHER_DATA" ] && [ "$1" = "$LAUNCHER_DATA" ] && { printf 'previous launcher'; return 0; }
  [ -n "$PLIST_DATA" ] && [ "$1" = "$PLIST_DATA" ] && { printf 'LaunchAgent'; return 0; }
  [ -n "$RECORDED_DATA" ] && [ "$1" = "$RECORDED_DATA" ] && { printf 'active.json'; return 0; }
  printf 'default'
}
LIVE_DATA="$(live_store 2>/dev/null)" || LIVE_DATA=""
LAUNCHER_DATA="$(launcher_data_dir 2>/dev/null)"; LAUNCHER_RC=$?
LAUNCHER_DATA_UNCERTAIN=0
[ "$LAUNCHER_RC" = 0 ] || LAUNCHER_DATA=""
[ "$LAUNCHER_RC" = 2 ] && LAUNCHER_DATA_UNCERTAIN=1
PLIST_DATA="$(plist_data_dir 2>/dev/null)" || PLIST_DATA=""
LOG_DATA="$(log_data_dir 2>/dev/null)" || LOG_DATA=""
RECORDED_DATA="$(jget "$P/active.json" dataDir)"
DATA=""; DATA_SOURCE=""
if [ -n "${COUNCIL_DATA_DIR:-}" ]; then
  DATA="$COUNCIL_DATA_DIR"; DATA_SOURCE="COUNCIL_DATA_DIR"
elif [ -n "$LIVE_DATA" ]; then
  DATA="$LIVE_DATA"; DATA_SOURCE="live service store"
else
  _stores=""; _n_store=0; _store=""; _dirs=""; _n_dir=0; _dir=""; _seen=""
  _nl="
"
  for _c in "$LOG_DATA" "$LAUNCHER_DATA" "$PLIST_DATA" "$RECORDED_DATA"; do
    [ -n "$_c" ] || continue
    case "$_seen" in *"$_nl$_c$_nl"*) continue ;; esac
    _seen="$_seen$_nl$_c$_nl"
    [ -d "$_c" ] || continue
    if [ -f "$_c/council.db" ]; then
      _n_store=$((_n_store+1)); _store="$_c"
      [ -z "$_stores" ] && _stores="$_c" || _stores="$_stores, $_c"
    else
      _n_dir=$((_n_dir+1)); [ -n "$_dir" ] || _dir="$_c"
      [ -z "$_dirs" ] && _dirs="$_c" || _dirs="$_dirs, $_c"
    fi
  done
  if [ "$_n_store" -gt 1 ]; then
    notready STORE_AUTHORITY_UNKNOWN "several recorded directories hold a council.db ($_stores) and no live service names one; refusing to guess - set COUNCIL_DATA_DIR to the store to keep"
  elif [ "$_n_store" = 1 ]; then
    DATA="$_store"; DATA_SOURCE="$(src_of "$_store")"
  elif [ "$_n_dir" -gt 1 ]; then
    notready STORE_AUTHORITY_UNKNOWN "several recorded data directories exist and none holds a council.db ($_dirs); refusing to guess - set COUNCIL_DATA_DIR"
  elif [ "$_n_dir" = 1 ]; then
    DATA="$_dir"; DATA_SOURCE="$(src_of "$_dir")"
  elif [ "$LAUNCHER_DATA_UNCERTAIN" = 1 ]; then
    notready STORE_AUTHORITY_UNKNOWN "the launcher this script wrote last time ($P/bin/council-service) records COUNCIL_SERVICE_DATA_DIR in a shape that cannot be parsed safely, no other witness names a store and no recorded data directory exists; falling back to $OC/council-data would be a guess - set COUNCIL_DATA_DIR to the store to keep"
  else
    DATA="$OC/council-data"; DATA_SOURCE="default"
  fi
fi
# An explicit COUNCIL_DATA_DIR still wins, but a store-less explicit choice next
# to a recorded store is never allowed to pass unseen.
if [ -n "${COUNCIL_DATA_DIR:-}" ] && [ ! -f "$DATA/council.db" ]; then
  for _c in "$LIVE_DATA" "$LOG_DATA" "$LAUNCHER_DATA" "$PLIST_DATA" "$RECORDED_DATA"; do
    [ -n "$_c" ] && [ "$_c" != "$DATA" ] && [ -f "$_c/council.db" ] && {
      say "STORE_AUTHORITY_NOTICE COUNCIL_DATA_DIR=$DATA holds no council.db while $_c does; the explicit choice still wins and nothing is copied"
      break
    }
  done
fi
if [ "$DATA" != "${RECORDED_DATA:-}" ] && { [ -n "$RECORDED_DATA" ] || [ "$DATA_SOURCE" != "default" ]; }; then
  say "STORE_AUTHORITY_RESOLVED $DATA ($DATA_SOURCE; active.json recorded ${RECORDED_DATA:-nothing})"
fi
if [ -n "$LIVE_DATA" ] && [ "$DATA" != "$LIVE_DATA" ]; then
  say "STORE_SWITCH $LIVE_DATA -> $DATA ($DATA_SOURCE); sessions in the live store stay there, nothing is migrated or copied"
fi

# ------------------------------------------------------------------- 5. build
mkdir -p "$LOGDIR" "$P" 2>/dev/null
PREV_REL="$(jget "$P/active.json" releaseId)"
BLOG="$LOGDIR/council-install.log"
bounded() { # 900 s ceiling: perl alarm (bash 3.2 / macOS), else timeout, else none
  if command -v perl >/dev/null 2>&1; then perl -e 'alarm shift; exec @ARGV or exit 127' 900 "$@"
  elif command -v timeout >/dev/null 2>&1; then timeout 900 "$@"
  else "$@"; fi
}
( unset NODE_ENV npm_config_production npm_config_omit NPM_CONFIG_PRODUCTION NPM_CONFIG_OMIT
  PATH="$(dirname "$NODE"):$PATH"; export PATH
  npm_config_include=dev; export npm_config_include
  bounded "$NODE" "$SKILL_DIR/scripts/install-runtime.mjs" --idempotent \
    --prefix "$P" --data-dir "$DATA" --node-executable "$NODE" --npm-executable "$NPM" ) >"$BLOG" 2>&1
_rc=$?
if [ "$_rc" -ne 0 ] || [ ! -f "$P/active.json" ]; then
  say "NOT_READY RUNTIME_BUILD_FAILED rc=$_rc; last lines of $BLOG:"
  tail -n 15 "$BLOG" 2>/dev/null
  exit 1
fi
REL_ID="$(jget "$P/active.json" releaseId)"
REL_PATH="$(jget "$P/active.json" releasePath)"
NODE_EXE="$(jget "$P/active.json" nodeExecutable)"
DATA_DIR="$(jget "$P/active.json" dataDir)"
if [ -z "$REL_ID" ] || [ ! -f "$REL_PATH/scripts/service-launch.mjs" ] || [ ! -f "$REL_PATH/node_modules/tsx/dist/cli.mjs" ] || [ ! -f "$REL_PATH/dist/blackceo-council.mjs" ] || [ -z "$NODE_EXE" ]; then
  say "NOT_READY RUNTIME_BUILD_FAILED active.json does not describe a usable release (id=$REL_ID path=$REL_PATH; the release must carry dist/blackceo-council.mjs)"
  exit 1
fi
# The launcher and the LaunchAgent are generated from DATA_DIR (the store
# active.json records). If the installer did not record the store resolved in
# 5a - a NOOP that ignored --data-dir - the service would be started on a
# DIFFERENT store than the one this run decided is authoritative. That is a
# silent store switch, so it is refused here, before any launcher is written.
if [ "${DATA_DIR:-}" != "$DATA" ]; then
  say "NOT_READY STORE_AUTHORITY_MISMATCH active.json records '${DATA_DIR:-none}' but the authoritative store is '$DATA' ($DATA_SOURCE); refusing to generate a launcher on a different store - nothing copied, nothing migrated"
  exit 0
fi
# Installer truth: verify the ACTUAL entry point the shim execs -- byte hash
# against the release's artifact receipt, plus a parse-level load check.
# Never 'ready' from SKILL.md presence or source match alone: a missing or
# unloadable entry is a visible NOT_READY with an actionable error, and an
# old bundle is never silently treated as the installed one.
ENTRY="$REL_PATH/dist/blackceo-council.mjs"
EXP_SHA="$("$NODE" -e 'try{const r=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"));const e=(r.entries||[]).find(x=>x.path===process.argv[2]);if(e)process.stdout.write(e.sha256)}catch(e){}' "$P/receipts/$REL_ID.artifact.json" "dist/blackceo-council.mjs" 2>/dev/null)"
GOT_SHA="$(sha_file "$ENTRY")"
if [ -z "$EXP_SHA" ] || [ "$EXP_SHA" != "$GOT_SHA" ]; then
  say "NOT_READY RUNTIME_BUILD_FAILED entry point hash mismatch for $ENTRY (receipt ${EXP_SHA:-missing} != installed ${GOT_SHA:-missing}); previous files preserved, nothing switched"
  exit 1
fi
if ! "$NODE_EXE" --check "$ENTRY" >/dev/null 2>&1; then
  say "NOT_READY RUNTIME_BUILD_FAILED entry point $ENTRY does not load (node --check failed); previous files preserved, nothing switched"
  exit 1
fi
# --------------------------------- 5c. durable front door (CTR-103)
# The installed `council-ask` must NEVER exec a path inside the skill checkout
# that ran this wiring: that checkout may be a lane worktree or a temporary
# clone that post-merge hygiene deletes. Copy the front door and its one helper
# into $P/frontdoor/<release-id>/ (immutable, versioned, never deleted) and bake
# THAT path into the shim. Not inside the release dir: a release is hash-covered
# by its artifact receipt, and install-runtime refuses an "unexpected generated
# file" there. The copy is load-checked before any shim is written.
ASK_ENTRY="$(bash "$SKILL_DIR/scripts/install-front-door.sh" "$P" "$REL_ID" "$SKILL_DIR" "$NODE_EXE" 2>&1)"
_ask_rc=$?
if [ "$_ask_rc" -ne 0 ] || [ ! -f "$ASK_ENTRY" ]; then
  notready FRONTDOOR_INSTALL_FAILED "durable front door not installed (rc=$_ask_rc): ${ASK_ENTRY:-no detail}"
fi

CHANGED=0
[ "$REL_ID" != "$PREV_REL" ] && CHANGED=1

# --------------------------------------- 5b. selected-tree gate (truth rule)
# verify-what-the-resolver-selects (scripts/selected-tree-gate.mjs): the
# update must verify the copy the runtime RESOLVER selects (its
# install-record, else the install-time resolver order), never just the
# directory it happens to have written. Competing copies are reported
# loudly; a stale, contract-drifted or executable-less SELECTED copy fails
# here and exits 1, so update-skills.sh withholds the .wired sentinel and no
# roll reports success after updating only an unused directory.
# On a box with more than one copy the gate needs agent-resolver evidence:
# COUNCIL_AGENT_SKILL_DIR=<the path the agent resolves> (for OpenClaw the
# shadowing root, e.g. ~/.agents/skills/council-of-wise-elders) when the caller
# sets it. A roll has no caller to set it, so when the gate answers "agent
# selection unproven" and no variable was given, ask the real OpenClaw resolver
# (scripts/agent-resolver-evidence.mjs: `openclaw skills info ... --json`) and
# run the SAME gate again with that answer. The gate is not relaxed: it still
# verifies the named copy and still rejects evidence that contradicts the live
# install-record. No resolver answer leaves the selection unproven and this
# step refuses - by design.
GT_RC=0
GT_ARGS=(--skill-dir "$SKILL_DIR" --prefix "$P" --home "$HOME")
if [ -n "${COUNCIL_AGENT_SKILL_DIR:-}" ]; then
  GT_ARGS+=(--agent-selected "$COUNCIL_AGENT_SKILL_DIR" --agent-source "COUNCIL_AGENT_SKILL_DIR")
fi
GT_OUT="$( "$NODE" "$SKILL_DIR/scripts/selected-tree-gate.mjs" "${GT_ARGS[@]}" 2>&1 )" || GT_RC=$?
if [ "$GT_RC" -ne 0 ] && [ -z "${COUNCIL_AGENT_SKILL_DIR:-}" ] \
   && printf '%s\n' "$GT_OUT" | grep -q 'agent selection unproven'; then
  AG_DIR="$( "$NODE" "$SKILL_DIR/scripts/agent-resolver-evidence.mjs" --config "$OC/openclaw.json" 2>/dev/null )" || AG_DIR=""
  if [ -n "$AG_DIR" ]; then
    GT_RC=0
    GT_OUT="$( "$NODE" "$SKILL_DIR/scripts/selected-tree-gate.mjs" "${GT_ARGS[@]}" \
      --agent-selected "$AG_DIR" --agent-source "openclaw skills info council-of-wise-elders" 2>&1 )" || GT_RC=$?
  fi
fi
[ -n "$GT_OUT" ] && printf '%s\n' "$GT_OUT"
if [ "$GT_RC" -ne 0 ]; then
  say "NOT_READY TREE_GATE the copy the resolver selects failed verification (lines above); success is withheld"
  exit 1
fi

# ---------------------------------------------- 6. public origin (hostname rule)
# Every source below is populated at INSTALL time (the Command Center ships first,
# locked to /interview, so the interview never gates the link): the process env,
# the Command Center app's own .env.local (written by interview-launch.py), then
# the launch state's seeded commandCenterUrl. First non-empty wins.
CC_APP="${CC_APP_DIR:-$HOME/projects/command-center}"
CC_URL="${CC_PUBLIC_URL:-${MC_TENANT_PUBLIC_URL:-}}"
if [ -z "$CC_URL" ]; then CC_URL="$(envget "$CC_APP/.env.local" CC_PUBLIC_URL)"; fi
if [ -z "$CC_URL" ]; then CC_URL="$(envget "$CC_APP/.env.local" MC_TENANT_PUBLIC_URL)"; fi
if [ -z "$CC_URL" ]; then CC_URL="$(jget "$OC/workspace/.workforce-build-state.json" commandCenterUrl)"; fi
# COUNCIL_PUBLIC_ORIGIN is the operator's direct answer and wins over every
# derived source: a box can serve two Council hostnames (the operator Mac
# serves council. and trevor-council.zerohumanworkforce.com today), and this
# script must never pick between them by guessing.
PUBLIC="${COUNCIL_PUBLIC_ORIGIN:-}"
PUBLIC_SOURCE=""
[ -n "$PUBLIC" ] && PUBLIC_SOURCE="COUNCIL_PUBLIC_ORIGIN"
if [ -n "$CC_URL" ]; then
  _h="${CC_URL#*://}"; _h="${_h%%/*}"; _h="${_h%%:*}"
  case "$_h" in
    ''|localhost|localhost.*|'['*) ;;          # never localhost or an IPv6 literal
    *[!0-9.]*) case "$_h" in *.*) [ -z "$PUBLIC" ] && { PUBLIC="https://${_h%%.*}-council.${_h#*.}"; PUBLIC_SOURCE="command center host"; } ;; esac ;;  # not an IPv4 literal
  esac
fi
if [ -z "$PUBLIC" ]; then
  PUBLIC="$(jget "$P/service.json" public_origin)"
  [ -n "$PUBLIC" ] && PUBLIC_SOURCE="service.json"
fi
# Never bake an origin no client can open: loopback is the box's own screen,
# and the reserved documentation TLDs (example.com, .example, .test, .invalid)
# are fixtures. The operator box's service.json carried
# "https://fixed.example.com" on 2026-10-29, which made the chamber link a dead
# URL in the reply. A rejected origin is dropped, never "repaired" by guessing.
if [ -n "$PUBLIC" ]; then
  _h2="${PUBLIC#*://}"; _h2="${_h2%%/*}"; _h2="${_h2%%:*}"; _h2="$(printf '%s' "$_h2" | tr '[:upper:]' '[:lower:]')"
  case "$_h2" in
    # Apex AND subdomains: "example.com" alone is a fixture just as much as
    # "x.example.com" (council-entry.mjs rejects the first; the probe usually
    # drops the apex anyway, but not with COUNCIL_PUBLIC_ORIGIN_SKIP_PROBE=1).
    ''|localhost|*.localhost|127.*|0.0.0.0|'['*|::1|example.com|example.net|example.org|example|test|invalid|*.example.com|*.example.net|*.example.org|*.example|*.test|*.invalid)
      say "PUBLIC_ORIGIN_REJECTED $PUBLIC ($PUBLIC_SOURCE: loopback or documentation host, not a client link)"
      PUBLIC="" ;;
  esac
fi
# The candidate is always baked into the shim; the CLI re-checks it at convene time.
CANDIDATE="$PUBLIC"
# Keep the candidate only if it answers like a Cloudflare Access login (302/303 to
# *.cloudflareaccess.com); otherwise a dead link would reach clients as chamber_url.
if [ -n "$PUBLIC" ] && [ "${COUNCIL_PUBLIC_ORIGIN_SKIP_PROBE:-0}" != 1 ]; then
  _pr="$(curl -s -o /dev/null -m 8 -w '%{http_code} %{redirect_url}' "$PUBLIC/status" 2>/dev/null)" || true
  _pc="${_pr%% *}"; _pl="${_pr#* }"; _ph="${_pl#*://}"; _ph="${_ph%%/*}"; _ph="${_ph%%:*}"
  case "$_pc:$_ph" in
    302:*.cloudflareaccess.com|303:*.cloudflareaccess.com) ;;
    *) say "PUBLIC_ORIGIN_UNVERIFIED $PUBLIC code=${_pc:-000}"; PUBLIC="" ;;
  esac
fi

# ------------------------------------------------- 7. generated launcher + shim
mkdir -p "$P/bin"
PATHV="$HOME/.local/bin:$HOME/.npm-global/bin:/data/.npm-global/bin:$OC/npm-global/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
LAUNCHER="$P/bin/council-service"
{
  printf '#!/bin/sh\n# %s\n' "$MARK"
  printf 'HOME=%s; export HOME\n' "$(sq "$HOME")"
  printf 'OPENCLAW_ROOT=%s; export OPENCLAW_ROOT\n' "$(sq "$OC")"
  printf 'PATH=%s; export PATH\n' "$(sq "$PATHV")"
  printf 'COUNCIL_SERVICE_PORT=%s; export COUNCIL_SERVICE_PORT\n' "$(sq "$PORT")"
  printf 'COUNCIL_SERVICE_DATA_DIR=%s; export COUNCIL_SERVICE_DATA_DIR\n' "$(sq "$DATA_DIR")"
  printf 'cd %s 2>/dev/null || true\n' "$(sq "$DATA_DIR")"
  printf 'exec %s %s %s\n' "$(sq "$NODE_EXE")" "$(sq "$REL_PATH/node_modules/tsx/dist/cli.mjs")" "$(sq "$REL_PATH/scripts/service-launch.mjs")"
} >"$LAUNCHER.tmp.$$" && chmod 755 "$LAUNCHER.tmp.$$" && mv -f "$LAUNCHER.tmp.$$" "$LAUNCHER"

SHIM="$P/bin/blackceo-council"
{
  printf '#!/bin/sh\n# %s\n' "$MARK"
  printf 'WISE_ELDERS_SERVICE_ORIGIN=%s; export WISE_ELDERS_SERVICE_ORIGIN\n' "$(sq "$ORIGIN")"
  printf 'WISE_ELDERS_SERVICE_JSON=%s; export WISE_ELDERS_SERVICE_JSON\n' "$(sq "$P/service.json")"
  printf 'WISE_ELDERS_OPENCLAW_ROOT=%s; export WISE_ELDERS_OPENCLAW_ROOT\n' "$(sq "$OC")"
  [ -n "$CANDIDATE" ] && printf 'WISE_ELDERS_PUBLIC_CANDIDATE=%s; export WISE_ELDERS_PUBLIC_CANDIDATE\n' "$(sq "$CANDIDATE")"
  [ -n "$PUBLIC" ] && printf 'WISE_ELDERS_PUBLIC_ORIGIN=%s; export WISE_ELDERS_PUBLIC_ORIGIN\n' "$(sq "$PUBLIC")"
  printf 'exec %s %s "$@"\n' "$(sq "$NODE_EXE")" "$(sq "$REL_PATH/dist/blackceo-council.mjs")"
} >"$SHIM.tmp.$$" && chmod 755 "$SHIM.tmp.$$" && mv -f "$SHIM.tmp.$$" "$SHIM"

# The documented front door. One command that proves the service authority,
# opens a NEW session for an explicit ask, reads sessions from the SERVICE
# (never the CLI's local store) and always emits the chamber link + desktop
# pop. Same env as the CLI shim, plus the CLI itself so the entry command
# never has to guess which shim to delegate convening to.
ASK_SHIM="$P/bin/council-ask"
{
  printf '#!/bin/sh\n# %s\n' "$MARK"
  printf 'WISE_ELDERS_SERVICE_ORIGIN=%s; export WISE_ELDERS_SERVICE_ORIGIN\n' "$(sq "$ORIGIN")"
  printf 'WISE_ELDERS_SERVICE_JSON=%s; export WISE_ELDERS_SERVICE_JSON\n' "$(sq "$P/service.json")"
  printf 'WISE_ELDERS_OPENCLAW_ROOT=%s; export WISE_ELDERS_OPENCLAW_ROOT\n' "$(sq "$OC")"
  printf 'COUNCIL_CLI=%s; export COUNCIL_CLI\n' "$(sq "$SHIM")"
  [ -n "$CANDIDATE" ] && printf 'WISE_ELDERS_PUBLIC_CANDIDATE=%s; export WISE_ELDERS_PUBLIC_CANDIDATE\n' "$(sq "$CANDIDATE")"
  [ -n "$PUBLIC" ] && printf 'WISE_ELDERS_PUBLIC_ORIGIN=%s; export WISE_ELDERS_PUBLIC_ORIGIN\n' "$(sq "$PUBLIC")"
  printf 'exec %s %s "$@"\n' "$(sq "$NODE_EXE")" "$(sq "$ASK_ENTRY")"
} >"$ASK_SHIM.tmp.$$" && chmod 755 "$ASK_SHIM.tmp.$$" && mv -f "$ASK_SHIM.tmp.$$" "$ASK_SHIM"

LSHA="$(sha_file "$LAUNCHER")"
PREV_SHA="$(jget "$P/service.json" launcher_sha256)"

link_shim() { # <bin dir> <name> <src> : symlink unless a foreign file owns the name
  local d="$1" n="$2" src="$3" t="$1/$2"
  mkdir -p "$d" 2>/dev/null || return 0
  if [ -e "$t" ] || [ -L "$t" ]; then
    head -n 5 "$t" 2>/dev/null | grep -qF "$MARK" || { say "SHIM_KEPT_EXISTING $t"; return 0; }
  fi
  ln -sfn "$src" "$t" 2>/dev/null || true
}
link_shims() {
  local _d
  for _d in "$HOME/.local/bin"; do
    link_shim "$_d" blackceo-council "$SHIM"
    link_shim "$_d" council-ask "$ASK_SHIM"
  done
  if [ "$PLATFORM" = "vps" ]; then
    for _d in /data/.npm-global/bin "$HOME/.npm-global/bin"; do
      if [ -d "$_d" ] && [ -w "$_d" ]; then
        link_shim "$_d" blackceo-council "$SHIM"
        link_shim "$_d" council-ask "$ASK_SHIM"
        break
      fi
    done
  fi
}

write_service_json() { # <manager> <name> <launcher sha to record>
  S_PORT="$PORT" S_ORIGIN="$ORIGIN" S_PUBLIC="$PUBLIC" S_MANAGER="$1" S_NAME="$2" S_REL="$REL_ID" S_SHA="$3" S_OUT="$P/service.json" \
  "$NODE" -e '
    const e=process.env,fs=require("fs");
    const o={schema:"council-service/v1",port:Number(e.S_PORT),origin:e.S_ORIGIN,public_origin:e.S_PUBLIC||null,
      manager:e.S_MANAGER,name:e.S_NAME,release_id:e.S_REL,launcher_sha256:e.S_SHA,updated_at:new Date().toISOString()};
    const t=e.S_OUT+".tmp."+process.pid;fs.writeFileSync(t,JSON.stringify(o,null,2)+"\n");fs.renameSync(t,e.S_OUT);'
}

# ---------------------------------------------------------------- adoption
if [ "$ADOPT" = "1" ]; then
  link_shims
  write_service_json external external "$LSHA"
  say "ADOPTED_EXISTING a Council already answers on $ORIGIN and is not managed by this script; left untouched (release $REL_ID built, CLI shim installed)"
  exit 0
fi

# -------------------------------------------------------------- 8. run service
MANAGER=""; NAME=""
if [ "$PLATFORM" = "mac" ]; then
  MANAGER=launchd; NAME="$LABEL"
  PLIST_CHANGED=0
  mkdir -p "$(dirname "$PLIST")"
  {
    cat <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$(xe "$LABEL")</string>
  <key>ProgramArguments</key>
  <array><string>/bin/sh</string><string>$(xe "$LAUNCHER")</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>WorkingDirectory</key><string>$(xe "$DATA_DIR")</string>
  <key>StandardOutPath</key><string>$(xe "$LOG")</string>
  <key>StandardErrorPath</key><string>$(xe "$LOG")</string>
</dict>
</plist>
PL
  } >"$PLIST.tmp.$$"
  if ! plutil -lint "$PLIST.tmp.$$" >/dev/null 2>&1; then
    rm -f "$PLIST.tmp.$$"
    notready SERVICE_UNHEALTHY "generated LaunchAgent plist failed plutil -lint"
  fi
  if [ -f "$PLIST" ] && cmp -s "$PLIST.tmp.$$" "$PLIST"; then rm -f "$PLIST.tmp.$$"
  else mv -f "$PLIST.tmp.$$" "$PLIST"; PLIST_CHANGED=1; fi

  if ! mac_gui; then
    link_shims
    write_service_json launchd "$NAME" "$LSHA"
    say "DEFERRED_NO_GUI no GUI login session for uid $UID_N; LaunchAgent $LABEL is written and loads at the next login (release $REL_ID)"
    exit 0
  fi
  if ! mac_loaded; then
    launchctl bootstrap "gui/$UID_N" "$PLIST" >>"$LOG" 2>&1 || notready SERVICE_UNHEALTHY "launchctl bootstrap failed for $LABEL"
    CHANGED=1
  elif [ "$PLIST_CHANGED" = "1" ]; then
    launchctl bootout "gui/$UID_N/$LABEL" >>"$LOG" 2>&1
    _i=0; while mac_loaded && [ "$_i" -lt 20 ]; do sleep 0.5; _i=$((_i+1)); done
    launchctl bootstrap "gui/$UID_N" "$PLIST" >>"$LOG" 2>&1 || notready SERVICE_UNHEALTHY "launchctl bootstrap failed for $LABEL after plist change"
    CHANGED=1
  elif [ "$LSHA" != "$PREV_SHA" ]; then
    launchctl kickstart -k "gui/$UID_N/$LABEL" >>"$LOG" 2>&1
    CHANGED=1
  fi
else
  MANAGER=pm2; NAME="$PM2_APP"
  _pid="$(pm2_pid)"
  if [ -z "$_pid" ]; then
    "$PM2" start "$LAUNCHER" --name "$PM2_APP" --interpreter /bin/sh --time --cwd "$DATA_DIR" --output "$LOG" --error "$LOG" >>"$LOGDIR/council-pm2.log" 2>&1
    CHANGED=1
  elif [ "$LSHA" != "$PREV_SHA" ] || [ "$_pid" = "0" ]; then
    "$PM2" restart "$PM2_APP" --update-env >>"$LOGDIR/council-pm2.log" 2>&1
    CHANGED=1
  fi
  [ "$CHANGED" = "1" ] && "$PM2" save >>"$LOGDIR/council-pm2.log" 2>&1
fi

# ------------------------------------------------------------------ 9. health
HEALTHY=0
_i=0
while [ "$_i" -lt 45 ]; do
  if council_health >/dev/null; then HEALTHY=1; break; fi
  sleep 1; _i=$((_i+1))
done

link_shims

if [ "$HEALTHY" != "1" ]; then
  write_service_json "$MANAGER" "$NAME" ""
  say "NOT_READY SERVICE_UNHEALTHY $ORIGIN did not answer within 45s (release $REL_ID, manager $MANAGER); last 20 log lines of $LOG:"
  tail -n 20 "$LOG" 2>/dev/null
  exit 0
fi

write_service_json "$MANAGER" "$NAME" "$LSHA"
if [ "$CHANGED" = "1" ]; then _state=READY; else _state=NOOP; fi
say "$_state release=$REL_ID port=$PORT manager=$MANAGER name=$NAME public_origin=${PUBLIC:-none}"
exit 0
