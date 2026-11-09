#!/usr/bin/env bash
# =============================================================================
# gateway-tls-probe-family.test.sh
#
# THE DEFECT THIS LOCKS. With gateway.tls.enabled=true in openclaw.json the
# gateway answers https ONLY; an http:// probe gets an empty reply (curl 000).
# Every shipped gateway-liveness probe that hardcoded http://127.0.0.1:<port>/
# therefore read a healthy TLS gateway as dead, and each one acts on "dead":
#   * gateway-health-watchdog.sh  kickstarts the gateway (one Mac fleet box:
#                                  2234 failed probes, 1116 kickstarts, live
#                                  sessions dropped) - covered in depth by
#                                  roll-converges-gateway-watchdog.test.sh T14-T21
#   * install-host-watchdog-cron.sh  refuses to arm / arms a loop on a TLS VPS
#   * oc-atomic-upgrade.sh         _healthz_ok decides the stability window, so
#                                  every upgrade of a TLS box rolled back
#   * self-update.sh               healthz_ok writes needs_host_restart
#   * ghl-mcp-autostart.sh         gw_up / _ghl_gw_up gate every CLI call
#   * telegram-offset-healthcheck.sh  gateway_is_up gates getUpdates
#   * oc-env-descriptor.sh         ocd_app_ready is the triage readiness verdict
#
# For each probe the SAME four boxes are run through the REAL function lifted
# out of the shipped script:
#   A  TLS on  + gateway answers https only  -> UP   (the fix; -k, no http://)
#   B  TLS on  + gateway down                -> DOWN (a truly dead box still reads dead)
#   C  TLS off + gateway answers http only   -> UP   (unchanged behaviour)
#   D  TLS off + gateway answers https only  -> DOWN (control: the old http-only
#                                                    probe against a TLS gateway)
# Then the VPS host installer is driven whole, with docker / crontab / curl stubs.
#
# Hermetic: temp HOME / config, curl and docker stubs on PATH. No network, no
# gateway, no box is touched.
# =============================================================================
set -uo pipefail

REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ATOMIC="$REPO_ROOT/scripts/oc-atomic-upgrade.sh"
SELFUP="$REPO_ROOT/scripts/self-update.sh"
GHLMCP="$REPO_ROOT/scripts/ghl-mcp-autostart.sh"
TGHC="$REPO_ROOT/scripts/telegram-offset-healthcheck.sh"
DESC="$REPO_ROOT/shared-utils/oc-env-descriptor.sh"
HOSTINST="$REPO_ROOT/platform/vps/service-selfheal/install-host-watchdog-cron.sh"
for f in "$ATOMIC" "$SELFUP" "$GHLMCP" "$TGHC" "$DESC" "$HOSTINST"; do
  [ -f "$f" ] || { echo "FATAL: $f not found"; exit 2; }
done

PASS=0; FAIL=0
ok()  { printf '  PASS  %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
hdr() { printf '\n== %s\n' "$1"; }

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT

# self-update.sh is a /bin/sh file: dash on the CI runner, bash-in-sh-mode on a Mac.
# Prefer a real dash so a bashism cannot pass here and die on a client box.
POSIX_SH="$(command -v dash 2>/dev/null || echo sh)"

TLS_ON='{"gateway":{"port":19001,"tls":{"enabled":true}}}'
NO_TLS='{"gateway":{"port":19001}}'

# --- a gateway that answers on ONE scheme ------------------------------------
# https without -k fails the way a self-signed cert does (rc 60); the wrong
# scheme gets an empty reply (rc 52), which is what http:// against a TLS
# gateway returns. Matching requests get 200 and {"ok":true}.
make_curl() { # $1 dir  $2 https|http|none
  mkdir -p "$1"; : > "$1/curl.calls"
  cat > "$1/curl" <<CURLEOF
#!/bin/sh
echo "curl \$*" >> "$1/curl.calls"
url=""; k=0; o=""; w=""; prev=""
for a in "\$@"; do
  case "\$a" in -k) k=1 ;; http://*|https://*) url="\$a" ;; esac
  [ "\$prev" = "-o" ] && o="\$a"
  [ "\$prev" = "-w" ] && w="\$a"
  prev="\$a"
done
rc=52
case "\$url" in
  https://*) [ "$2" = "https" ] && { [ "\$k" = "1" ] && rc=0 || rc=60; } ;;
  http://*)  [ "$2" = "http" ] && rc=0 ;;
esac
code=000; body=""
if [ "\$rc" = "0" ]; then code=200; body='{"ok":true}'; fi
if [ -z "\$o" ] || [ "\$o" = "-" ]; then printf '%s' "\$body"; fi
if [ -n "\$w" ]; then pre="\${w%'%{http_code}'}"; printf '%s%s' "\$pre" "\$code"; fi
exit \$rc
CURLEOF
  chmod +x "$1/curl"
}

# --- lift one function (and only it) out of a shipped script -----------------
lift() { # $1 file  $2.. function names -> prints their bodies
  local f="$1"; shift
  local n
  for n in "$@"; do
    awk -v n="$n" '$0 ~ "^" n "\\(\\) \\{" {p=1} p{print} p && /^\}/ {exit}' "$f"
  done
}

# --- run one scenario ---------------------------------------------------------
# $1 label  $2 tls_cfg  $3 gateway mode  $4 expect up|down  $5 shell  $6 code
# The code reads $CFG (the openclaw.json path), $DIR (the scenario dir) and
# returns the probe's status.
scenario() {
  local label="$1" cfgtxt="$2" mode="$3" expect="$4" sh="$5" code="$6"
  local dir="$SANDBOX/$(printf '%s' "$label" | tr -c 'A-Za-z0-9' '_')"
  mkdir -p "$dir/bin" "$dir/root"
  printf '%s' "$cfgtxt" > "$dir/root/openclaw.json"
  make_curl "$dir/bin" "$mode"
  env -i HOME="$dir" PATH="$dir/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
      CFG="$dir/root/openclaw.json" DIR="$dir" ROOTD="$dir/root" REPO="$REPO_ROOT" \
      "$sh" -c "$code" >"$dir/out" 2>&1
  local rc=$?
  SC_CALLS="$(cat "$dir/bin/curl.calls")"
  SC_OUT="$(cat "$dir/out")"
  if [ "$expect" = "up" ]; then
    [ "$rc" -eq 0 ] && ok "$label: UP" || bad "$label: expected UP, got rc=$rc. out: $SC_OUT | curl: $SC_CALLS"
  else
    [ "$rc" -ne 0 ] && ok "$label: DOWN" || bad "$label: expected DOWN, got rc=0. curl: $SC_CALLS"
  fi
}

# The four boxes for one probe.
four() { # $1 name  $2 shell  $3 code
  local n="$1" sh="$2" code="$3"
  scenario "$n A tls-on + https-only gateway" "$TLS_ON" https up   "$sh" "$code"
  case "$SC_CALLS" in
    *" -k "*"https://127.0.0.1:19001/"*) ok "$n A: probed https://127.0.0.1:19001 with -k" ;;
    *) bad "$n A: no https -k probe on the configured port. curl: $SC_CALLS" ;;
  esac
  case "$SC_CALLS" in
    *" http://"*) bad "$n A: a plain http:// probe was issued against a TLS gateway. curl: $SC_CALLS" ;;
    *) ok "$n A: no http:// probe against a TLS gateway" ;;
  esac
  scenario "$n B tls-on + dead gateway"       "$TLS_ON" none  down "$sh" "$code"
  scenario "$n C tls-off + http-only gateway" "$NO_TLS" http  up   "$sh" "$code"
  case "$SC_CALLS" in
    *"https://"*|*" -k "*) bad "$n C: https or -k used without gateway.tls.enabled. curl: $SC_CALLS" ;;
    *) ok "$n C: plain http, no -k, as before" ;;
  esac
  scenario "$n D control: tls-off + https-only gateway" "$NO_TLS" https down "$sh" "$code"
}

# =============================================================================
hdr "1 - oc-atomic-upgrade.sh _healthz_ok (the stability window of an upgrade)"
FN="$(lift "$ATOMIC" _gateway_port _gateway_tls _healthz_ok)"
[ -n "$FN" ] && ok "1: _gateway_port, _gateway_tls and _healthz_ok lifted" || bad "1: could not lift the functions"
four "oc-atomic _healthz_ok" bash "$FN"'
OC_CONFIG="$CFG"; _healthz_ok'

hdr "2 - self-update.sh healthz_ok (rollback proof / needs_host_restart)"
FN="$(lift "$SELFUP" gateway_port gateway_tls healthz_ok)"
[ -n "$FN" ] && ok "2: gateway_port, gateway_tls and healthz_ok lifted" || bad "2: could not lift the functions"
four "self-update healthz_ok" "$POSIX_SH" "$FN"'
ROOT="$ROOTD"; healthz_ok'

hdr "3 - ghl-mcp-autostart.sh gw_up and _ghl_gw_up (gate every CLI call)"
FN="$(lift "$GHLMCP" _gw_tls_flag _ghl_gw_up gw_up)"
[ -n "$FN" ] && ok "3: _gw_tls_flag, _ghl_gw_up and gw_up lifted" || bad "3: could not lift the functions"
four "ghl-mcp gw_up" bash "$FN"'
OPENCLAW_CONFIG="$CFG"; gw_up'
four "ghl-mcp _ghl_gw_up" bash "$FN"'
OC_JSON="$CFG"; _ghl_gw_up'

hdr "4 - telegram-offset-healthcheck.sh gateway_is_up (gates getUpdates)"
FN="$(lift "$TGHC" detect_gateway_port gateway_is_up)"
[ -n "$FN" ] && ok "4: detect_gateway_port and gateway_is_up lifted" || bad "4: could not lift the functions"
# TGHC_GATEWAY_PORT pins the port so the openclaw CLI is never consulted.
four "telegram gateway_is_up" bash "$FN"'
CONFIG_FILE="$CFG"; TGHC_GATEWAY_PORT=19001; gateway_is_up'

hdr "5 - oc-env-descriptor.sh ocd_app_ready (the triage readiness verdict)"
four "descriptor ocd_app_ready" bash '. "$REPO/shared-utils/oc-env-descriptor.sh"
OCD_JSON="$CFG"; OCD_GATEWAY_PORT=19001; OC_APP_READY_ATTEMPTS=1; ocd_app_ready'

# An explicit OC_APP_READY_URL is the caller's: honoured as given, -k added only
# for a loopback https URL.
scenario "descriptor explicit https loopback URL" "$NO_TLS" https up bash '. "$REPO/shared-utils/oc-env-descriptor.sh"
OCD_JSON="$CFG"; OC_APP_READY_URL="https://127.0.0.1:19001/healthz"; OC_APP_READY_ATTEMPTS=1; ocd_app_ready'
case "$SC_CALLS" in *" -k "*"https://127.0.0.1:19001/healthz"*) ok "descriptor: -k added for a loopback https URL" ;; *) bad "descriptor: no -k on a loopback https URL. curl: $SC_CALLS" ;; esac

# =============================================================================
hdr "6 - install-host-watchdog-cron.sh arms a TLS VPS gateway (docker/crontab/curl stubs)"
run_installer() { # $1 label  $2 config text  $3 gateway mode
  local label="$1" cfgtxt="$2" mode="$3"
  local dir="$SANDBOX/inst_$label"
  mkdir -p "$dir/bin" "$dir/home"
  printf '%s' "$cfgtxt" > "$dir/container-openclaw.json"
  make_curl "$dir/bin" "$mode"
  cat > "$dir/bin/docker" <<DOCKEREOF
#!/bin/sh
case "\$1" in
  ps)      echo openclaw-t ;;
  inspect) echo node ;;
  port)    echo "0.0.0.0:19001" ;;
  exec)    shift; cmd="\$*"
           case "\$cmd" in
             *"gateway status"*)                     echo "Listening: 127.0.0.1:19001" ;;
             *"cat /data/.openclaw/openclaw.json"*)  cat "$dir/container-openclaw.json" ;;
           esac ;;
esac
exit 0
DOCKEREOF
  cat > "$dir/bin/crontab" <<CRONEOF
#!/bin/sh
case "\$1" in
  -l) [ -f "$dir/crontab" ] && cat "$dir/crontab"; exit 0 ;;
  -)  cat > "$dir/crontab"; exit 0 ;;
esac
exit 0
CRONEOF
  chmod +x "$dir/bin/docker" "$dir/bin/crontab"
  env -i HOME="$dir/home" PATH="$dir/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
      OPENCLAW_HOST_WATCHDOG_DIR="$dir/wd" \
      bash "$HOSTINST" >"$dir/out" 2>&1
  IRC=$?
  IOUT="$(cat "$dir/out")"
  ICRON="$(cat "$dir/crontab" 2>/dev/null || true)"
  ICALLS="$(cat "$dir/bin/curl.calls")"
}

run_installer tlsup "$TLS_ON" https
[ "$IRC" -eq 0 ] && ok "6A: a healthy TLS container is armed (rc 0)" || bad "6A: refused a healthy TLS gateway. rc=$IRC out: $IOUT"
case "$ICRON" in *"GATEWAY_WATCHDOG_TLS=1"*) ok "6A: the cron forwards GATEWAY_WATCHDOG_TLS=1 (the host has no config to read)" ;; *) bad "6A: cron line lacks GATEWAY_WATCHDOG_TLS=1: $ICRON" ;; esac
case "$ICRON" in *"GATEWAY_WATCHDOG_PORT=19001"*) ok "6A: the cron still forwards the resolved port" ;; *) bad "6A: cron lost the port: $ICRON" ;; esac
case "$ICALLS" in *" http://"*) bad "6A: pre-arm probe used http:// against a TLS gateway. curl: $ICALLS" ;; *) ok "6A: the pre-arm probe was https only" ;; esac

run_installer plain "$NO_TLS" http
[ "$IRC" -eq 0 ] && ok "6C: a plain-http container is armed (rc 0)" || bad "6C: refused a healthy http gateway. rc=$IRC out: $IOUT"
case "$ICRON" in *"GATEWAY_WATCHDOG_TLS"*) bad "6C: TLS var forwarded without gateway.tls.enabled: $ICRON" ;; *) ok "6C: no TLS var for a plain-http container" ;; esac

run_installer tlsdown "$TLS_ON" none
[ "$IRC" -ne 0 ] && ok "6B: a dead TLS container is NOT armed" || bad "6B: armed a cron against a dead gateway"
case "$IOUT" in *"https://127.0.0.1:19001/"*) ok "6B: the refusal names the https URL it probed" ;; *) bad "6B: refusal does not name https. out: $IOUT" ;; esac
[ -z "$ICRON" ] && ok "6B: no crontab entry written" || bad "6B: wrote a crontab entry: $ICRON"

# =============================================================================
hdr "7 - every file in the blast radius parses"
for f in "$ATOMIC" "$GHLMCP" "$TGHC" "$DESC" "$HOSTINST" "${BASH_SOURCE[0]}"; do
  bash -n "$f" 2>/dev/null && ok "7: bash -n $(basename "$f")" || bad "7: $(basename "$f") does not parse"
done
"$POSIX_SH" -n "$SELFUP" 2>/dev/null && ok "7: sh -n self-update.sh" || bad "7: self-update.sh does not parse under sh"

printf '\nResult: %d passed | %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
