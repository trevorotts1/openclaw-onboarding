#!/bin/sh
# remediate.sh — Mac OpenClaw SERVICE self-heal.
#
# Purpose
#   Belt-and-suspenders over launchd's own KeepAlive: make sure the OpenClaw
#   gateway AND every cloudflared tunnel LaunchAgent are (a) still bootstrapped
#   into the user GUI domain and (b) actually running. launchd KeepAlive only
#   respawns a job that is still LOADED; a job that got booted-out (by an
#   installer, an `openclaw service` step, a crash during login, or a manual
#   `launchctl bootout`) silently stays down until something re-bootstraps it.
#   This script is that something.
#
#   COMPLEMENT to gateway-watchdog.sh:
#     - gateway-watchdog.sh  → HTTP health probe + kickstart of a hung gateway.
#     - remediate.sh         → presence/loaded/running self-heal for the gateway
#                              AND all cloudflared tunnels.
#   If gateway-watchdog.sh is present this script DELEGATES the gateway leg to it
#   (health logic lives in one place) and focuses on the tunnels.
#
# Behavior (idempotent, read-mostly, no destructive ops):
#   For each managed LaunchAgent label:
#     1. plist exists but job NOT loaded            → launchctl bootstrap.
#     2. job loaded, KeepAlive job has no PID        → launchctl kickstart -k.
#     3. job loaded, periodic (StartInterval) job    → OK (no persistent PID).
#     4. healthy                                     → log OK, do nothing.
#   Every action is logged. Exit 0 if everything ended healthy, else 1.
#
# Deploy: install-service-remediate.sh wires this to run every 5 minutes via a
# StartInterval LaunchAgent (com.openclaw.service-remediate). It can also run
# from cron:  */5 * * * * $HOME/.openclaw/service-env/remediate.sh >/dev/null 2>&1
#
# Safe to run repeatedly. Never edits a plist. Never touches client credentials.
set -u

UID_NUM="$(id -u)"
LA_DIR="$HOME/Library/LaunchAgents"
SVC_DIR="$HOME/.openclaw/service-env"
WATCHDOG="$SVC_DIR/gateway-watchdog.sh"
LOG_DIR="$HOME/Library/Logs/openclaw"
LOG="$LOG_DIR/service-remediate.log"

# Gateway label is handled specially (delegated to the watchdog when present).
GATEWAY_LABEL="ai.openclaw.gateway"

mkdir -p "$LOG_DIR"
ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*" >> "$LOG"; }

overall_rc=0

# is_loaded LABEL  → 0 if the job is bootstrapped in the GUI domain.
is_loaded() { launchctl print "gui/$UID_NUM/$1" >/dev/null 2>&1; }

# running_pid LABEL → echoes a numeric PID if the job has one, else nothing.
running_pid() {
  launchctl print "gui/$UID_NUM/$1" 2>/dev/null \
    | awk -F'=' '/^[[:space:]]*pid =/{gsub(/[^0-9]/,"",$2); print $2; exit}'
}

# heal_label LABEL PLIST  → bootstrap if absent, kickstart if a KeepAlive job is dead.
heal_label() {
  label="$1"; plist="$2"
  if [ ! -f "$plist" ]; then
    log "SKIP $label: no plist at $plist"
    return 0
  fi
  if ! is_loaded "$label"; then
    log "DOWN $label: not loaded -> launchctl bootstrap gui/$UID_NUM $plist"
    launchctl bootstrap "gui/$UID_NUM" "$plist" >>"$LOG" 2>&1
    rc=$?
    log "  bootstrap rc=$rc"
    [ "$rc" -eq 0 ] || overall_rc=1
    return 0
  fi
  pid="$(running_pid "$label")"
  if [ -z "$pid" ] || [ "$pid" = "0" ]; then
    # A missing PID is only a STALL for a long-running (KeepAlive) job. A
    # periodic StartInterval job legitimately has no PID between runs.
    if ! grep -q "KeepAlive" "$plist" 2>/dev/null; then
      log "OK $label (periodic/on-demand, no persistent pid)"
      return 0
    fi
    log "STALL $label: loaded but no running pid -> launchctl kickstart -k gui/$UID_NUM/$label"
    launchctl kickstart -k "gui/$UID_NUM/$label" >>"$LOG" 2>&1
    rc=$?
    log "  kickstart rc=$rc"
    [ "$rc" -eq 0 ] || overall_rc=1
    return 0
  fi
  log "OK $label (pid=$pid)"
}

# ---- 1) Gateway: delegate to the watchdog when available --------------------
if [ -x "$WATCHDOG" ] || [ -f "$WATCHDOG" ]; then
  log "gateway: delegating to gateway-watchdog.sh"
  sh "$WATCHDOG" >>"$LOG" 2>&1 || overall_rc=1
else
  heal_label "$GATEWAY_LABEL" "$LA_DIR/$GATEWAY_LABEL.plist"
fi

# ---- 2) All cloudflared tunnel LaunchAgents ---------------------------------
# Match the two naming conventions for a cloudflared connector agent:
#   com.cloudflared.*   (user-level `cloudflared tunnel run` agents)
#   com.cloudflare.*    (e.g. com.cloudflare.command-center)
found_any=0
for plist in "$LA_DIR"/com.cloudflared.*.plist "$LA_DIR"/com.cloudflare.*.plist; do
  [ -f "$plist" ] || continue
  found_any=1
  label="$(basename "$plist" .plist)"
  heal_label "$label" "$plist"
done
[ "$found_any" = "1" ] || log "note: no cloudflared tunnel LaunchAgents found in $LA_DIR"

if [ "$overall_rc" -eq 0 ]; then
  log "REMEDIATE DONE: all managed services healthy"
else
  log "REMEDIATE DONE: one or more services required action / failed (rc=1)"
fi
exit "$overall_rc"
