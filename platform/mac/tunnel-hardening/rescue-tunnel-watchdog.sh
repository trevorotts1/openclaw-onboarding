#!/usr/bin/env bash
# =============================================================================
# rescue-tunnel-watchdog.sh
# Layer E: the reboot-stale RESCUE tunnel watchdog (root LaunchDaemon).
# =============================================================================
#
# THE DEFECT THIS EXISTS FOR
#
# The rescue cloudflared connector on a client Mac is installed by an operator
# runbook, not by this repo, under a per-box label `com.blackceo.rescue-<slug>`.
# After a reboot the connector can come back holding a STALE cached edge
# address and spend the rest of its life dialing the LAN router
# (192.168.x.x:7844, or any RFC1918 address on port 7844) instead of a
# Cloudflare edge. It never registers a tunnel connection, and because the
# process is ALIVE, launchd KeepAlive keeps the useless thing running forever.
#
# Every watchdog this repo already ships is blind to that state:
#   * platform/mac/tunnel-hardening/install-watchdog-agent.sh checks only
#     `pgrep -f 'cloudflared.*tunnel'`. The stale connector IS running, so it
#     reports OK, and it only knows the label com.cloudflare.cloudflared.
#   * platform/mac/service-selfheal/remediate.sh covers gui/ LaunchAgents only.
#   * harden-mac-tunnel.sh targets the cloudflared plist alone.
#
# "Alive" is not "registered". This watchdog is the missing leg: it reads the
# connector's own log and acts only on the POSITIVE evidence of the stale
# state, namely repeated RFC1918:7844 dial targets with zero registrations.
#
# SECOND LEG: sshd
#
# The same reboot sometimes comes back with Remote Login off in the launchd
# system domain, which locks the operator out of the box entirely.
#
#   NOTE, and this is the trap: `Disabled` = true inside
#   /System/Library/LaunchDaemons/ssh.plist is APPLE'S SHIPPED DEFAULT MARKER.
#   It is true on boxes where Remote Login is ON. It is NOT the authoritative
#   state and reading it produces a false positive every time.
#   `launchctl print-disabled system` is the authoritative view, and it is the
#   only thing this script reads.
#
# CONTRACT
#   * Never `set -e`. A watchdog must never be the thing that takes a box down.
#   * Acts ONLY on positive confirmation. A count that does not parse as an
#     all-digit integer is reported `undetermined` and nothing happens. An
#     absent or unreadable log is `undetermined`, never "healthy" and never
#     "stale": absence is not evidence.
#   * A kick is rate limited by a durable cooldown stamp, so a genuinely broken
#     box can never become a restart storm.
#   * Read-mostly. It never edits a plist, a config or a credential, and it
#     never prints a secret.
#
# OVERRIDES (fixtures and tests use these; a live box needs none)
#   RESCUE_LABEL                   pin the daemon label explicitly. Accepts
#                                  com.cloudflare.cloudflared for boxes where
#                                  that slot IS the rescue tunnel.
#   RESCUE_WATCHDOG_DAEMON_DIR     default /Library/LaunchDaemons
#   RESCUE_WATCHDOG_LOG_DIR        default /Library/Logs
#   RESCUE_WATCHDOG_STATE_DIR      default /var/db/blackceo
#   RESCUE_WATCHDOG_WINDOW_LINES   default 200
#   RESCUE_WATCHDOG_COOLDOWN       default 600 (seconds)
#   RESCUE_WATCHDOG_LAN_THRESHOLD  default 5
#   RESCUE_WATCHDOG_SKIP_SSHD      1 = skip the sshd leg
#
# Exit codes: always 0 on a clean pass (acted, held, or undetermined).
#             1 only when a heal action was attempted and FAILED, so a
#             supervising reader can alert without this script aborting a box.
# =============================================================================
set -uo pipefail

DAEMON_DIR="${RESCUE_WATCHDOG_DAEMON_DIR:-/Library/LaunchDaemons}"
LOG_DIR="${RESCUE_WATCHDOG_LOG_DIR:-/Library/Logs}"
STATE_DIR="${RESCUE_WATCHDOG_STATE_DIR:-/var/db/blackceo}"
WINDOW_LINES="${RESCUE_WATCHDOG_WINDOW_LINES:-200}"
COOLDOWN_SECS="${RESCUE_WATCHDOG_COOLDOWN:-600}"
LAN_THRESHOLD="${RESCUE_WATCHDOG_LAN_THRESHOLD:-5}"
SSHD_LABEL="com.openssh.sshd"
STAMP="$STATE_DIR/rescue-watchdog.last-kick"
RC=0

# A malformed tunable falls back to its default rather than to a surprise.
case "$WINDOW_LINES"  in ''|*[!0-9]*) WINDOW_LINES=200 ;; esac
case "$COOLDOWN_SECS" in ''|*[!0-9]*) COOLDOWN_SECS=600 ;; esac
case "$LAN_THRESHOLD" in ''|*[!0-9]*) LAN_THRESHOLD=5 ;; esac

log() { printf '[%s] rescue-tunnel-watchdog: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }
now() { date +%s; }

# ---- 1. Resolve the rescue daemon label -------------------------------------
# An explicit RESCUE_LABEL wins. Otherwise take the FIRST
# com.blackceo.rescue-*.plist in the daemon dir. The glob is checked for a real
# file because an unmatched glob in bash stays literal.
LABEL="${RESCUE_LABEL:-}"
if [ -z "$LABEL" ]; then
  for _cand in "$DAEMON_DIR"/com.blackceo.rescue-*.plist; do
    [ -f "$_cand" ] || continue
    _base="${_cand##*/}"
    LABEL="${_base%.plist}"
    break
  done
fi
if [ -z "$LABEL" ]; then
  log "no-rescue-daemon: no RESCUE_LABEL pinned and no ${DAEMON_DIR}/com.blackceo.rescue-*.plist on this box; nothing to watch"
  exit 0
fi
log "label=$LABEL window=${WINDOW_LINES} threshold=${LAN_THRESHOLD} cooldown=${COOLDOWN_SECS}s"

if [ "$(id -u 2>/dev/null || echo 1)" != "0" ]; then
  log "note: not running as root; launchctl system-domain actions will be refused by launchd and reported as failures, not as facts about the box"
fi

# ---- 2. Count the evidence, or say undetermined ------------------------------
# A private-range dial TARGET on the cloudflared control port. Anchored on a
# non-digit/non-dot boundary so 110.x or 1172.x can never read as RFC1918.
LAN_RE='(^|[^0-9.])(192\.168\.[0-9]{1,3}\.[0-9]{1,3}|10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3}):7844'
REG_RE='Registered tunnel connection'

# count_in <file> <extended-regex>
# Prints an all-digit count on stdout and returns 0, or prints NOTHING and
# returns 1 when the count could not be established. A MISSING file is 0
# (nothing observed in it); an UNREADABLE file is a failure, never a zero.
# grep rc 1 = no match (a real zero); rc >= 2 = error (never a zero).
count_in() {
  _ci_file="$1"; _ci_re="$2"
  if [ ! -e "$_ci_file" ]; then printf '0\n'; return 0; fi
  if [ ! -r "$_ci_file" ]; then return 1; fi
  _ci_win="$(tail -n "$WINDOW_LINES" "$_ci_file" 2>/dev/null)" || return 1
  _ci_n="$(printf '%s\n' "$_ci_win" | grep -c -E "$_ci_re" 2>/dev/null)"
  _ci_rc=$?
  case "$_ci_rc" in
    0|1) : ;;
    *)   return 1 ;;
  esac
  # Strip any surrounding whitespace, then demand all digits. A non-integer is
  # a failed measurement, not a zero.
  _ci_n="$(printf '%s' "$_ci_n" | tr -d '[:space:]')"
  case "$_ci_n" in
    ''|*[!0-9]*) return 1 ;;
  esac
  printf '%s\n' "$_ci_n"
  return 0
}

ERR_LOG="$LOG_DIR/${LABEL}.err.log"
OUT_LOG="$LOG_DIR/${LABEL}.out.log"

# At least ONE of the two logs has to actually exist, or there is nothing to
# read and the state is undetermined by definition.
if [ ! -e "$ERR_LOG" ] && [ ! -e "$OUT_LOG" ]; then
  log "undetermined: neither $ERR_LOG nor $OUT_LOG exists, so nothing was measured; no action taken (absence is not evidence of health OR of staleness)"
  exit 0
fi

LAN_ERRS=""
REGISTERED=""
_lan_a="$(count_in "$ERR_LOG" "$LAN_RE")" || _lan_a=""
_lan_b="$(count_in "$OUT_LOG" "$LAN_RE")" || _lan_b=""
_reg_a="$(count_in "$ERR_LOG" "$REG_RE")" || _reg_a=""
_reg_b="$(count_in "$OUT_LOG" "$REG_RE")" || _reg_b=""

if [ -n "$_lan_a" ] && [ -n "$_lan_b" ]; then LAN_ERRS=$(( _lan_a + _lan_b )); fi
if [ -n "$_reg_a" ] && [ -n "$_reg_b" ]; then REGISTERED=$(( _reg_a + _reg_b )); fi

# POSITIVE CONFIRMATION ONLY. Both counts must be all-digit integers before a
# single launchctl call is made.
_ok=1
case "${LAN_ERRS:-x}"   in ''|*[!0-9]*) _ok=0 ;; esac
case "${REGISTERED:-x}" in ''|*[!0-9]*) _ok=0 ;; esac
if [ "$_ok" != "1" ]; then
  log "undetermined: could not establish integer counts from the log window (err_log=$ERR_LOG out_log=$OUT_LOG lan=${LAN_ERRS:-unreadable} registered=${REGISTERED:-unreadable}); no action taken"
  exit 0
fi

log "measured lan_dials=$LAN_ERRS registered=$REGISTERED (last ${WINDOW_LINES} lines of each log)"

# ---- 3. The stale-connector decision ----------------------------------------
if [ "$LAN_ERRS" -ge "$LAN_THRESHOLD" ] && [ "$REGISTERED" -eq 0 ]; then
  _last=""
  if [ -r "$STAMP" ]; then _last="$(tr -d '[:space:]' < "$STAMP" 2>/dev/null)"; fi
  case "${_last:-x}" in ''|*[!0-9]*) _last="" ;; esac
  _age=""
  if [ -n "$_last" ]; then _age=$(( $(now) - _last )); fi
  if [ -n "$_age" ] && [ "$_age" -lt "$COOLDOWN_SECS" ]; then
    log "HOLD: stale connector confirmed (lan_dials=$LAN_ERRS registered=0) but the last kick was ${_age}s ago, inside the ${COOLDOWN_SECS}s cooldown; not kicking again"
  else
    log "STALE: $LABEL is alive but has NEVER registered (lan_dials=$LAN_ERRS registered=0). A stale cached edge address does not recover on its own and no amount of waiting fixes it. Kicking."
    if launchctl kickstart -k "system/${LABEL}" >/dev/null 2>&1; then
      log "KICKED: launchctl kickstart -k system/${LABEL} rc=0"
      mkdir -p "$STATE_DIR" 2>/dev/null || true
      if now > "$STAMP" 2>/dev/null; then
        chmod 0644 "$STAMP" 2>/dev/null || true
        log "cooldown stamp written: $STAMP"
      else
        log "WARN: cooldown stamp $STAMP could not be written; the next pass may kick again sooner than ${COOLDOWN_SECS}s"
      fi
    else
      log "KICK FAILED: launchctl kickstart -k system/${LABEL} returned non-zero. Check: sudo launchctl print system/${LABEL}"
      RC=1
    fi
  fi
else
  log "OK: no stale-connector signature (needs lan_dials >= ${LAN_THRESHOLD} AND registered == 0)"
fi

# ---- 4. sshd leg -------------------------------------------------------------
# `launchctl print-disabled system` is the authoritative view. The Disabled key
# inside /System/Library/LaunchDaemons/ssh.plist is Apple's shipped default
# marker and is true even on boxes where Remote Login is ON, so it is never read
# here.
if [ "${RESCUE_WATCHDOG_SKIP_SSHD:-0}" = "1" ]; then
  log "sshd: leg skipped (RESCUE_WATCHDOG_SKIP_SSHD=1)"
  exit "$RC"
fi

_pd="$(launchctl print-disabled system 2>/dev/null)"
_pd_rc=$?
if [ "$_pd_rc" -ne 0 ] || [ -z "$_pd" ]; then
  log "sshd: undetermined, 'launchctl print-disabled system' produced no readable output (rc=$_pd_rc); NOT touching Remote Login on a guess"
  exit "$RC"
fi

if printf '%s\n' "$_pd" | grep -q -E "\"${SSHD_LABEL}\"[[:space:]]*=>[[:space:]]*(disabled|true)"; then
  log "sshd: ${SSHD_LABEL} is DISABLED in the launchd system domain (authoritative view). Enabling."
  _en_rc=0
  launchctl enable "system/${SSHD_LABEL}" >/dev/null 2>&1 || _en_rc=$?
  if [ "$_en_rc" -eq 0 ]; then
    log "sshd: launchctl enable system/${SSHD_LABEL} rc=0"
  else
    log "sshd: launchctl enable system/${SSHD_LABEL} FAILED rc=$_en_rc"
    RC=1
  fi
  _ks_rc=0
  launchctl kickstart -k "system/${SSHD_LABEL}" >/dev/null 2>&1 || _ks_rc=$?
  if [ "$_ks_rc" -eq 0 ]; then
    log "sshd: launchctl kickstart -k system/${SSHD_LABEL} rc=0"
  else
    log "sshd: launchctl kickstart -k system/${SSHD_LABEL} FAILED rc=$_ks_rc"
    RC=1
  fi
  # Prove it the way a positive is proved: a real connection attempt.
  if command -v nc >/dev/null 2>&1; then
    if nc -z 127.0.0.1 22 >/dev/null 2>&1; then
      log "sshd: VERIFIED, a listener answered on 127.0.0.1:22 (nc -z)"
    else
      log "sshd: NOT VERIFIED, nothing answered on 127.0.0.1:22 after the enable+kickstart. Remote Login is still down."
      RC=1
    fi
  else
    log "sshd: listener check UNDETERMINED, nc is not on PATH so no connection attempt was made"
  fi
else
  log "sshd: ${SSHD_LABEL} is not listed as disabled in the launchd system domain; left alone"
fi

exit "$RC"
