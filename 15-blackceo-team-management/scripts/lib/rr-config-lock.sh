#!/usr/bin/env bash
# rr-config-lock.sh — serialized access to the OpenClaw config for RR-032.
#
# WHY: the pre-RR-032 installer had no lock at all. Two operators (or an
# operator and a repair re-run) could both read openclaw.json, both mutate their
# own in-memory copy, and both write — last writer wins, first writer's change is
# silently lost. The RR-032 contract forbids that: a write must be CAS'd against
# the revision it was derived from, and it must be serialized.
#
# WHAT THIS IS NOT: `flock` does not exist on macOS. `shlock` exists on macOS but
# not on minimal Linux images. A mkdir-based lock with a stale-owner check works
# on both and needs no tool beyond coreutils/BSD base.
#
# Contract:
#   rr_config_lock <lockdir> [timeout_seconds]
#     -> 0 acquired, holder pid written to $lockdir/pid
#     -> 4 timeout (never blocks forever, never silently proceeds unlocked)
#   rr_config_unlock <lockdir>
#     -> removes the lock iff this process owns it
#
# Stale handling: a lock whose holder pid is gone is reclaimed by the next
# waiter. A lock older than RR_LOCK_STALE_SECONDS is reclaimed even if the pid
# is alive but the owner stopped making progress (defends against a crashed
# holder whose pid was recycled).

RR_LOCK_STALE_SECONDS="${RR_LOCK_STALE_SECONDS:-120}"

rr_config_unlock() {
  local lockdir="$1"
  local owner
  owner="$(cat "$lockdir/pid" 2>/dev/null || echo '')"
  if [ "$owner" = "$$" ]; then
    rm -rf "$lockdir"
  fi
}

_rr_lock_age() {
  local lockdir="$1" now mtime
  now="$(date +%s)"
  mtime="$(stat -f %m "$lockdir" 2>/dev/null || stat -c %Y "$lockdir" 2>/dev/null || echo 0)"
  echo $(( now - mtime ))
}

rr_config_lock() {
  local lockdir="$1" timeout="${2:-30}" waited=0 owner
  while ! mkdir "$lockdir" 2>/dev/null; do
    owner="$(cat "$lockdir/pid" 2>/dev/null || echo '')"
    if [ -n "$owner" ] && ! kill -0 "$owner" 2>/dev/null; then
      rm -rf "$lockdir"
      continue
    fi
    if [ "$(_rr_lock_age "$lockdir")" -gt "$RR_LOCK_STALE_SECONDS" ]; then
      rm -rf "$lockdir"
      continue
    fi
    if [ "$waited" -ge "$timeout" ]; then
      echo "rr_config_lock: timed out after ${timeout}s waiting for ${lockdir} (holder pid ${owner:-unknown})" >&2
      return 4
    fi
    sleep 1
    waited=$(( waited + 1 ))
  done
  printf '%s\n' "$$" > "$lockdir/pid"
  return 0
}
