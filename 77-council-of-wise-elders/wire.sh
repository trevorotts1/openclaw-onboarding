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
#      never printed or logged. No token file = no-op (most boxes).
# It writes nothing inside the skill folder and touches no credential, model,
# openclaw.json, AGENTS.md, gateway or Command Center.
#
# One typed line is printed:
#   COUNCIL_WIRE: READY|NOOP|ADOPTED_EXISTING|DEFERRED_NO_GUI|NOT_READY <CODE> <detail>
# plus, only when the connector token file exists, one line before it:
#   COUNCIL_CONNECTOR: READY|NOOP|DEFERRED_NO_GUI|NOT_READY <CODE> <detail>
# --connector-only runs the connector step and exits 0 (no build, no service).
# Exit 0 for every state except RUNTIME_BUILD_FAILED (exit 1), so a transient
# npm failure withholds the .wired sentinel and the next roll retries.
#
# Env: COUNCIL_WIRE_PLATFORM (mac|vps) COUNCIL_NODE COUNCIL_NPM COUNCIL_PM2
#      COUNCIL_SERVICE_PORT (8787) COUNCIL_SERVICE_LABEL (ai.blackceo.council-service)
#      COUNCIL_PM2_APP (council-of-wise-elders) OPENCLAW_ROOT CC_PUBLIC_URL
#      MC_TENANT_PUBLIC_URL COUNCIL_CLOUDFLARED (absolute cloudflared path)
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
DATA="$OC/council-data"
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
if [ -z "$REL_ID" ] || [ ! -f "$REL_PATH/scripts/service-launch.mjs" ] || [ ! -f "$REL_PATH/node_modules/tsx/dist/cli.mjs" ] || [ -z "$NODE_EXE" ]; then
  say "NOT_READY RUNTIME_BUILD_FAILED active.json does not describe a usable release (id=$REL_ID path=$REL_PATH)"
  exit 1
fi
CHANGED=0
[ "$REL_ID" != "$PREV_REL" ] && CHANGED=1

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
PUBLIC=""
if [ -n "$CC_URL" ]; then
  _h="${CC_URL#*://}"; _h="${_h%%/*}"; _h="${_h%%:*}"
  case "$_h" in
    ''|localhost|localhost.*|'['*) ;;          # never localhost or an IPv6 literal
    *[!0-9.]*) case "$_h" in *.*) PUBLIC="https://${_h%%.*}-council.${_h#*.}" ;; esac ;;  # not an IPv4 literal
  esac
fi
if [ -z "$PUBLIC" ]; then PUBLIC="$(jget "$P/service.json" public_origin)"; fi
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

LSHA="$(sha_file "$LAUNCHER")"
PREV_SHA="$(jget "$P/service.json" launcher_sha256)"

link_shim() { # <bin dir> : symlink our shim unless a foreign file owns the name
  local d="$1" t="$1/blackceo-council"
  mkdir -p "$d" 2>/dev/null || return 0
  if [ -e "$t" ] || [ -L "$t" ]; then
    head -n 5 "$t" 2>/dev/null | grep -qF "$MARK" || { say "SHIM_KEPT_EXISTING $t"; return 0; }
  fi
  ln -sfn "$SHIM" "$t" 2>/dev/null || true
}
link_shims() {
  link_shim "$HOME/.local/bin"
  if [ "$PLATFORM" = "vps" ]; then
    for _d in /data/.npm-global/bin "$HOME/.npm-global/bin"; do
      if [ -d "$_d" ] && [ -w "$_d" ]; then link_shim "$_d"; break; fi
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
