#!/usr/bin/env bash
# Skill 77 wire.sh Council tunnel connector (step 3b), run with
# --connector-only against stubs: a fake cloudflared, launchctl and pm2 on
# PATH (nothing is loaded, started or contacted), a temp HOME and
# OPENCLAW_ROOT. Proves: absent token = quiet no-op; token present starts the
# connector once; second run is a no-op; a token change restarts only the
# Council connector; the Command Center connector is never touched; the token
# value never appears in output, logs, plist or state.
#   bash 77-council-of-wise-elders/scripts/tests/wire-connector.test.sh
# bash 3.2 safe. Needs node; the Mac cases need plutil (macOS) and are
# reported SKIP elsewhere.
set -u
WIRE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)/wire.sh"
NODE="$(command -v node)" || { echo "FAIL node required"; exit 2; }
T="$(mktemp -d "${TMPDIR:-/tmp}/wcon.XXXXXX")" || exit 2
trap 'rm -rf "$T"' EXIT
FAILS=0
ok()  { echo "PASS $1"; }
bad() { echo "FAIL $1"; FAILS=$((FAILS+1)); }
has() { case "$1" in *"$2"*) return 0 ;; esac; return 1; }
TOKEN1="tokA-$$-not-a-real-token-eyJhIjoiMSJ9"
TOKEN2="tokB-$$-not-a-real-token-eyJhIjoiMiJ9"
CCTOKEN="ccTok-$$-inherited-command-center-token" # a box .env TUNNEL_TOKEN in wire.sh's env

S="$T/stub"; mkdir -p "$S/bin" "$S/state"
LOGF="$S/calls.log"; : >"$LOGF"
printf '#!/bin/sh\necho "fake cloudflared must never run: $*" >&2; exit 99\n' >"$S/bin/cloudflared"
printf '#!/bin/sh\nexit 0\n' >"$S/bin/npm"
cat >"$S/bin/launchctl" <<EOF
#!/bin/sh
echo "launchctl \$*" >>"$LOGF"
case "\$1" in
  print) case "\$2" in gui/*/*) [ -f "$S/state/ld.\${2##*/}" ] && { echo "state = running"; exit 0; }; exit 113 ;; esac ;;
  bootstrap) touch "$S/state/ld.\$(basename "\$3" .plist)" ;;
  bootout) rm -f "$S/state/ld.\${2##*/}" ;;
esac
exit 0
EOF
cat >"$S/bin/pm2" <<EOF
#!/bin/sh
echo "pm2 \$*" >>"$LOGF"
[ "\$1" = start ] && echo "pm2-start-env TUNNEL_TOKEN=[\${TUNNEL_TOKEN-unset}]" >>"$LOGF"
case "\$1" in
  pid) [ -f "$S/state/pm2.\$2" ] && cat "$S/state/pm2.\$2"; exit 0 ;;
  start) n=""; while [ \$# -gt 0 ]; do [ "\$1" = --name ] && n="\$2"; shift; done; echo 4242 >"$S/state/pm2.\$n" ;;
  delete) rm -f "$S/state/pm2.\$2" ;;
esac
exit 0
EOF
chmod +x "$S/bin/"*
SPATH="$S/bin:$PATH"
# Instrument control: the stubs, not the real tools, must resolve.
[ "$(PATH="$SPATH" command -v launchctl)" = "$S/bin/launchctl" ] && [ "$(PATH="$SPATH" command -v pm2)" = "$S/bin/pm2" ] \
  || { echo "FAIL stubs do not shadow the real launchctl/pm2; refusing to run"; exit 2; }

mode_of() { stat -f %Lp "$1" 2>/dev/null || stat -c %a "$1"; }
no_token_anywhere() { # <home> : the token value appears nowhere but the token file
  ! grep -rqsF -e "$TOKEN1" -e "$TOKEN2" --exclude=tunnel-council.token "$1" "$LOGF" "$S/all-output"
}

case_platform() { # <mac|vps>
  local pf="$1" H="$T/$1" OC CNT OUT RC TF
  OC="$H/.openclaw"; TF="$OC/secrets/tunnel-council.token"; mkdir -p "$OC"
  : >"$LOGF"; rm -f "$S/state/"*
  # the Command Center connector is already running and must stay untouched
  touch "$S/state/ld.com.cloudflare.cloudflared"; echo 777 >"$S/state/pm2.cloudflare-tunnel"
  w() { local o r
    o="$(env PATH="$SPATH" HOME="$H" TUNNEL_TOKEN="$CCTOKEN" OPENCLAW_ROOT="$OC" COUNCIL_WIRE_PLATFORM="$pf" COUNCIL_NODE="$NODE" \
          COUNCIL_NPM="$S/bin/npm" COUNCIL_PM2="$S/bin/pm2" COUNCIL_CLOUDFLARED="$S/bin/cloudflared" \
          /bin/bash "$WIRE" --idempotent --connector-only 2>&1)"; r=$?
    printf '%s\n' "$o" >>"$S/all-output"; printf '%s' "$o"; return "$r"; }
  starts() { grep -cE 'launchctl (bootstrap|kickstart)|pm2 (start|delete)' "$LOGF"; }

  OUT="$(w)"; RC=$?
  [ "$RC" = 0 ] && [ -z "$OUT" ] && [ "$(starts)" = 0 ] && [ ! -e "$H/Library/LaunchAgents/ai.blackceo.council-tunnel.plist" ] \
    && ok "$pf absent token: quiet no-op" || bad "$pf absent token: quiet no-op ($OUT)"

  mkdir -p "$OC/secrets"; printf '%s' "$TOKEN1" >"$TF"; chmod 644 "$TF"
  OUT="$(w)"; RC=$?; echo "$OUT"
  [ "$RC" = 0 ] && has "$OUT" "COUNCIL_CONNECTOR: READY" && [ "$(starts)" = 1 ] && ok "$pf token present: started once" || bad "$pf token present: started once"
  [ "$(mode_of "$TF")" = 600 ] && ok "$pf token file tightened to 600" || bad "$pf token file tightened to 600"
  if [ "$pf" = mac ]; then
    PL="$H/Library/LaunchAgents/ai.blackceo.council-tunnel.plist"
    plutil -lint "$PL" >/dev/null 2>&1 && grep -q '<string>Standard</string>' "$PL" && ! grep -q Background "$PL" \
      && grep -q "<string>$S/bin/cloudflared</string>" "$PL" && grep -q '<string>--token-file</string>' "$PL" \
      && ok "mac plist: Standard, absolute cloudflared, --token-file" || bad "mac plist: Standard, absolute cloudflared, --token-file"
    grep -q "<string>--config</string><string>$OC/council-runtime/council-tunnel.yml</string>" "$PL" \
      && grep -q '<key>TUNNEL_TOKEN</key><string></string>' "$PL" \
      && ok "mac plist: own --config, TUNNEL_TOKEN blanked" || bad "mac plist: own --config, TUNNEL_TOKEN blanked"
  else
    grep -q "pm2 start $S/bin/cloudflared --name cloudflared-council .*-- tunnel .*run --token-file $TF" "$LOGF" \
      && ok "vps pm2 cloudflared-council runs tunnel run --token-file" || bad "vps pm2 cloudflared-council runs tunnel run --token-file"
    grep -q -- "-- tunnel --config $OC/council-runtime/council-tunnel.yml " "$LOGF" && grep -q 'pm2-start-env TUNNEL_TOKEN=\[\]' "$LOGF" \
      && ! grep -qF "$CCTOKEN" "$LOGF" && ok "vps pm2: own --config, inherited TUNNEL_TOKEN blanked" || bad "vps pm2: own --config, inherited TUNNEL_TOKEN blanked"
  fi

  CNT="$(starts)"; OUT="$(w)"; RC=$?
  [ "$RC" = 0 ] && has "$OUT" "COUNCIL_CONNECTOR: NOOP" && [ "$(starts)" = "$CNT" ] && ok "$pf second run: no restart" || bad "$pf second run: no restart ($OUT)"

  printf '%s' "$TOKEN2" >"$TF"; CNT="$(starts)"; OUT="$(w)"; RC=$?
  if [ "$pf" = mac ]; then
    tail -n 5 "$LOGF" | grep -q "launchctl kickstart -k gui/$(id -u)/ai.blackceo.council-tunnel" && ok "mac token change: kickstart council connector" || bad "mac token change: kickstart council connector"
  else
    tail -n 5 "$LOGF" | grep -q "pm2 delete cloudflared-council" && [ -f "$S/state/pm2.cloudflared-council" ] && ok "vps token change: council connector replaced" || bad "vps token change: council connector replaced"
  fi
  [ "$RC" = 0 ] && has "$OUT" "COUNCIL_CONNECTOR: READY" && [ "$(starts)" -gt "$CNT" ] && ok "$pf token change: READY" || bad "$pf token change: READY ($OUT)"

  ! grep -qE 'com\.cloudflare|cloudflare-tunnel' "$LOGF" && [ -f "$S/state/ld.com.cloudflare.cloudflared" ] && [ "$(cat "$S/state/pm2.cloudflare-tunnel")" = 777 ] \
    && ok "$pf Command Center connector never touched" || bad "$pf Command Center connector never touched"
  no_token_anywhere "$H" && ok "$pf token value never in output, logs, plist or state" || bad "$pf token value never in output, logs, plist or state"
}

if command -v plutil >/dev/null 2>&1; then case_platform mac; else echo "SKIP mac cases (no plutil)"; fi
case_platform vps

echo "wire-connector: $FAILS failed"; [ "$FAILS" = 0 ]
