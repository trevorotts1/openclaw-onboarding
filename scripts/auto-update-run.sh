#!/bin/bash
# auto-update-run.sh -- the locked part of one auto-update run (called by auto_update.py tick).
# Takes the SAME shared installation lease the operator's fleet roll takes (scripts/box-update-lock.sh,
# /tmp/openclaw-update.lock). A busy box is waited on for 30 minutes (poll every 30 seconds), then the
# run is recorded DEFERRED. Everything below runs as a child of this process, so update-skills.sh,
# fleet-refresh and Command Center's update.sh inherit the lease instead of fighting it.
{
set -u
SELF_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
ROOT="${OPENCLAW_ROOT:-}"
[ -n "$ROOT" ] || { if [ -d /data/.openclaw ]; then ROOT=/data/.openclaw; else ROOT="$HOME/.openclaw"; fi; }
LEASE="${OPENCLAW_UPDATE_LEASE:-/tmp/openclaw-update.lock}"
RUN_ID="${AUTO_UPDATE_RUN_ID:-auto-update-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
WAIT_SECONDS="${AUTO_UPDATE_LOCK_WAIT_SECONDS:-1800}"
POLL_SECONDS="${AUTO_UPDATE_LOCK_POLL_SECONDS:-30}"
export AUTO_UPDATE_RUN_ID="$RUN_ID"

HELPER=""
for h in "$SELF_DIR/box-update-lock.sh" "$ROOT/scripts/box-update-lock.sh"; do
  [ -f "$h" ] && { HELPER="$h"; break; }
done
if [ -z "$HELPER" ]; then
  echo "[auto-update] REFUSED: box-update-lock.sh is not on this box, so the shared lock cannot be taken; nothing changed"
  python3 "$SELF_DIR/auto_update.py" defer
  exit 75
fi
# shellcheck source=/dev/null
. "$HELPER"

waited=0
while :; do
  box_update_lock_acquire "$LEASE" "$RUN_ID" "auto-update" "$ROOT"
  rc=$?
  [ "$rc" -eq 0 ] && break
  if [ "$rc" -ne 3 ]; then
    echo "[auto-update] could not take the lock (rc=$rc); nothing changed"
    python3 "$SELF_DIR/auto_update.py" defer
    exit 75
  fi
  if [ "$waited" -ge "$WAIT_SECONDS" ]; then
    echo "[auto-update] the box lock stayed busy for ${WAIT_SECONDS}s: DEFERRED"
    python3 "$SELF_DIR/auto_update.py" defer
    exit 75
  fi
  sleep "$POLL_SECONDS"
  waited=$((waited + POLL_SECONDS))
done
trap 'box_update_lock_release' EXIT

python3 "$SELF_DIR/auto_update.py" run
exit $?
}
