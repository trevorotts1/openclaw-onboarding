#!/usr/bin/env bash
# =============================================================================
# 58-PODCAST-PRODUCTION-ENGINE :: PODCAST SCHEDULER RUNNER (act-4)
# -----------------------------------------------------------------------------
# THE CONTROLLER IS THE PROCESSOR; THE SCHEDULER IS ITS HEARTBEAT.
#
# podcast_controller.py is the production processor: the one program that runs
# the 18-step pipeline over queued TaskFlows (the flows the intake layer
# creates, whose flow key IS the job_key; wiring.json session_binding). A
# processor with no heartbeat never runs, which is exactly the failure the
# activation ticket describes: intake lands, flows queue, nothing processes.
#
# This runner IS that heartbeat. It is the ONLY thing the OS scheduler
# (config/cron.d/podcast-scheduler on Linux, the launchd agent template in
# config/launchd/ on macOS) invokes. One tick does exactly three things:
#
#   1. source the podcast env (secrets env file; labels upstream, values never
#      printed here), so the controller sees PODCAST_GATEWAY_URL, the route
#      id, the session key, PODCAST_DB_PATH and friends exactly as provisioned;
#   2. take a portable single-instance lock (a stale tick must never overlap a
#      fresh one; episode production is minutes-long, the tick is 5 minutes);
#   3. run: python3 podcast_controller.py --once
#
# The exit code of the controller is the exit code of the tick. A missing
# controller is logged and exits 0 ON PURPOSE: the heartbeat stays green while
# the processor slice has not landed on this box yet, and flips to real work
# the moment it does, with zero reconfiguration. This runner never registers
# an openclaw cron job, never emits anything client-facing, and never prints a
# secret value (SET-ness and behavior only, per the silence doctrine).
#
# Furnace reconciliation (binding): guard-cron-inventory.py enforces EXACTLY
# ONE recurring job PER CLIENT (the daily smoke test), no heartbeat entry, no
# queue poller. This scheduler violates none of it, because it is not a
# per-client openclaw cron at all: it is ONE OS-level entry PER BOX, installed
# by install-podcast-scheduler.sh, with no delivery mode to announce and no
# client identity to orphan at churn. The guard recognizes it by name
# (podcast-scheduler) and excludes it from the per-client census; a departed
# client leaves the box-level tick behind with zero client crons, which is the
# clean-churn posture the furnace law wants. The runner's own lock bounds the
# overlap risk the cadence implies: at most one processor pass at a time.
#
# ENV (all optional; absent values degrade to labeled no-ops, never a crash):
#   PODCAST_ENV_FILE            explicit secrets env file to source (first hit)
#   PODCAST_CONTROLLER_PATH     controller location (default: this dir's
#                               podcast_controller.py)
#   PODCAST_SCHEDULER_PYTHON    interpreter (default python3)
#   PODCAST_SCHEDULER_LOG       log path (default ~/.openclaw/podcast-scheduler.log)
#   PODCAST_SCHEDULER_LOCKDIR   lock dir (default ${TMPDIR:-/tmp}/podcast-scheduler.lock.<uid>)
#   PODCAST_SCHEDULER_DRY_RUN=1 log the tick, touch nothing, exit 0
#
# USAGE:
#   podcast_scheduler_runner.sh            one tick (what the cron entry calls)
#   podcast_scheduler_runner.sh --dry-run  prove the wiring without running it
#
# EXIT: the controller's exit code / 0 when the controller is absent (logged)
#       or on dry-run.
# =============================================================================
PODCAST_SCHEDULER_RUNNER_VERSION="v1.0.0"
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTROLLER="${PODCAST_CONTROLLER_PATH:-$HERE/podcast_controller.py}"
PY="${PODCAST_SCHEDULER_PYTHON:-python3}"
LOG="${PODCAST_SCHEDULER_LOG:-$HOME/.openclaw/podcast-scheduler.log}"
LOCKDIR="${PODCAST_SCHEDULER_LOCKDIR:-${TMPDIR:-/tmp}/podcast-scheduler.lock.$(id -u)}"
LOCK_STALE_MIN=15

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() {
  mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2" >> "$LOG" 2>/dev/null || true
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2"
}

if [ "${1:-}" = "--dry-run" ] || [ "${PODCAST_SCHEDULER_DRY_RUN:-0}" = "1" ]; then
  log "DRY" "tick ok: controller=$CONTROLLER python=$PY (nothing executed)"
  exit 0
fi

# --- 1. source the podcast env (the heartbeat carries the provisioned env) ---
ENV_CANDIDATES=(
  "$HOME/.openclaw/secrets.env"
  "$HOME/.openclaw/secrets/.env"
  "/data/.openclaw/secrets.env"
  "/data/.openclaw/secrets/.env"
  "$HOME/clawd/secrets/.env"
)
if [ -n "${PODCAST_ENV_FILE:-}" ]; then
  ENV_CANDIDATES=("$PODCAST_ENV_FILE" "${ENV_CANDIDATES[@]}")
fi
for f in "${ENV_CANDIDATES[@]}"; do
  if [ -f "$f" ]; then
    # shellcheck disable=SC1090  # provisioned env store; sourced, never printed
    set +u; set -a; . "$f" 2>/dev/null || true; set +a; set -u
    break
  fi
done

# --- 2. single-instance lock (at most one processor pass at a time) ----------
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  # Reclaim a stale lock left behind by a crashed tick, then retry once.
  if [ -d "$LOCKDIR" ] && [ -n "$(find "$LOCKDIR" -maxdepth 0 -mmin +"$LOCK_STALE_MIN" 2>/dev/null)" ]; then
    rmdir "$LOCKDIR" 2>/dev/null || true
    if ! mkdir "$LOCKDIR" 2>/dev/null; then
      log "SKIP" "another tick is active; this one yields"
      exit 0
    fi
  else
    log "SKIP" "another tick is active; this one yields"
    exit 0
  fi
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT

# --- 3. run the production processor ------------------------------------------
if [ ! -f "$CONTROLLER" ]; then
  log "WAIT" "controller not present yet ($CONTROLLER); heartbeat stays green"
  exit 0
fi
rc=0
"$PY" "$CONTROLLER" --once || rc=$?
if [ "$rc" -eq 0 ]; then
  log "OK" "tick complete: controller ran clean"
else
  log "WARN" "controller exit=$rc (will retry on the next tick)"
fi
exit "$rc"
