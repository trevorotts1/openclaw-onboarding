#!/usr/bin/env bash
# wait-gateway-owner-stale.sh -- pre-start wait for a dead Gateway's owner heartbeat to go stale.
#
# Why: OpenClaw 2026.10.1 keeps the Gateway owner heartbeat as the mtime of the lock files in
# <state>/tmp/openclaw-<uid>/ (state.<hash>.lock and gateway.state.lock, renewed every 15 s).
# After a fast `docker restart` (new PID namespace) the new Gateway sees a heartbeat younger
# than 90 s, cannot prove the old owner is dead and exits ("cannot verify Gateway ownership ...
# wait up to 90 seconds after its last heartbeat"). The Hostinger wrapper never retries, so the
# Gateway stays dead. Fix: before the wrapper starts, sleep until the newest lock file is older
# than 90 s (checked with a 2 s margin = 92), at most 120 s total.
# Fail-soft: always exits 0. Log: <state dir>/logs/wait-gateway-owner-stale.log
# Called from platform/vps/{hostinger,contabo}/container-startup.sh right before the final exec
# (needs no openclaw CLI: a CLI call with no gateway takes the offline maintenance lock).
# State dir: $OPENCLAW_ROOT (Contabo /home/node/.openclaw), else $OPENCLAW_DATA/.openclaw (Hostinger /data).
# Test overrides: GW_WAIT_LOCKDIR, GW_WAIT_STALE (seconds), GW_WAIT_CAP (seconds).
set -u
OC="${OPENCLAW_ROOT:-${OPENCLAW_DATA:-/data}/.openclaw}"
LOGS="$OC/logs"
LOG="$LOGS/wait-gateway-owner-stale.log"
LOCKDIR="${GW_WAIT_LOCKDIR:-$OC/tmp/openclaw-$(id -u)}"
STALE="${GW_WAIT_STALE:-92}"
CAP="${GW_WAIT_CAP:-120}"
mkdir -p "$LOGS" 2>/dev/null || true
log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG" 2>/dev/null || true; }

newest_mtime() {
  local n=0 f m
  for f in "$LOCKDIR"/*.lock; do
    [ -f "$f" ] || continue
    m=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null) || continue
    [ "$m" -gt "$n" ] && n=$m
  done
  echo "$n"
}

start=$(date +%s)
m=$(newest_mtime)
if [ "$m" -eq 0 ]; then
  log "no lock file in $LOCKDIR; no wait"
  exit 0
fi
age=$(( start - m ))
if [ "$age" -ge "$STALE" ]; then
  log "newest owner heartbeat is ${age}s old (>= ${STALE}); no wait"
  exit 0
fi
log "newest owner heartbeat is ${age}s old (< ${STALE}); waiting up to ${CAP}s"
while :; do
  sleep 3
  now=$(date +%s)
  m=$(newest_mtime)
  [ "$m" -eq 0 ] && { log "lock files gone after $(( now - start ))s; continue"; exit 0; }
  age=$(( now - m ))
  if [ "$age" -ge "$STALE" ]; then
    log "owner heartbeat now ${age}s old; waited $(( now - start ))s; continue"
    exit 0
  fi
  if [ $(( now - start )) -ge "$CAP" ]; then
    log "cap of ${CAP}s reached (heartbeat still ${age}s old, a live owner may still be renewing); continue anyway"
    exit 0
  fi
done
