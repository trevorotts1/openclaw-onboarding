#!/usr/bin/env bash
# =============================================================================
# 58-PODCAST-PRODUCTION-ENGINE :: INSTALL-PODCAST-SCHEDULER (act-4)
# -----------------------------------------------------------------------------
# THE CONTROLLER IS THE PROCESSOR; THE SCHEDULER IS ITS HEARTBEAT.
#
# Activates the heartbeat that runs podcast_controller.py --once every five
# minutes. Intake plus publish already work; the gap this closes: queued flows
# never ran the 18 steps because no scheduler drove the processor.
#
# WHAT GETS INSTALLED (platform idiom, ONE entry PER BOX):
#   macOS   : launchd user agent (config/launchd template rendered into
#             ~/Library/LaunchAgents/com.openclaw.podcast-scheduler.plist,
#             bootstrapped into the user's gui domain; OpenClaw itself runs as
#             a launchd user service, so this matches the box idiom)
#   Linux   : repo config/cron.d/podcast-scheduler copied to /etc/cron.d/ and
#             the runner copied to /usr/local/bin/podcast-scheduler-runner.sh
#             (same shape as config/cron.d/qmd-orphan-sweep)
#   fallback: one line in the runtime user's crontab (no root required)
#
# The installed entry always invokes podcast_scheduler_runner.sh; the runner
# sources the podcast env and runs podcast_controller.py --once. This installer
# NEVER registers an openclaw cron job: the per-client once-daily furnace law
# (guard-cron-inventory.py) governs openclaw client crons only; this box-level
# tick is recognized by name 'podcast-scheduler' and excluded from the
# per-client census. Nothing here is client-scoped, so churn leaves nothing
# client-shaped behind (the revocation SOP removes the box tick only when the
# engine itself leaves the box).
#
# IDEMPOTENT by construction: re-running converges on the same state (existing
# identical artifacts are left untouched; a changed runner is replaced; the
# launchd agent is bootout-then-bootstrap). Safe to run at provisioning, after
# an update, or twice by accident.
#
# SECRETS: this script reads and references env file PATHS only (labels and
# locations). It never prints, copies, or moves a secret VALUE.
#
# USAGE:
#   install-podcast-scheduler.sh [--check] [--force MODE]
#     MODE: launchd | cron.d | usercrontab (default: autodetect)
#     --check : report installed/absent, exit 0 when the heartbeat is active
#               (read-only; used by verification and the activation audit)
# ENV (test seams, all optional):
#   PODCAST_SCHEDULER_ROOT   redirect install targets under this prefix
#                            (etc/cron.d, usr/local/bin; skips ownership ops)
#   PODCAST_NODE_USER        runtime user for the cron.d user field
#                            (default node; the cron entry never runs the
#                            controller as root, config writes are node-owned)
#   PODCAST_SCHEDULER_FORCE  same as --force MODE
# EXIT: 0 installed/verified / 2 cannot install / 3 usage.
# =============================================================================
PODCAST_INSTALL_SCHEDULER_VERSION="v1.0.0"
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNNER_SRC="$SCRIPT_DIR/podcast_scheduler_runner.sh"
CRON_SRC="$(cd "$SKILL_DIR/.." && pwd)/config/cron.d/podcast-scheduler"
PLIST_TEMPLATE="$SKILL_DIR/config/launchd/com.openclaw.podcast-scheduler.plist.template"
PLIST_LABEL="com.openclaw.podcast-scheduler"

RUNNER_BASENAME="podcast-scheduler-runner.sh"
NODE_USER="${PODCAST_NODE_USER:-node}"
FORCE_MODE="${PODCAST_SCHEDULER_FORCE:-}"
CHECK_ONLY=0
PREFIX="${PODCAST_SCHEDULER_ROOT:-}"

log() { printf '[install-podcast-scheduler] %s\n' "$*"; }
die() { printf '[install-podcast-scheduler] FATAL: %s\n' "$*" >&2; exit 2; }

usage() {
  grep '^#' "$0" | sed -n '2,50p' | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK_ONLY=1 ;;
    --force) shift; FORCE_MODE="${1:-}"; [ -n "$FORCE_MODE" ] || usage 3 ;;
    -h|--help) usage 0 ;;
    *) printf '[install-podcast-scheduler] unknown arg: %s\n' "$1" >&2; usage 3 ;;
  esac
  shift
done

[ -f "$RUNNER_SRC" ] || die "runner missing: $RUNNER_SRC"

detect_mode() {
  if [ -n "$FORCE_MODE" ]; then printf '%s' "$FORCE_MODE"; return; fi
  if [ "$(uname -s)" = "Darwin" ] && command -v launchctl >/dev/null 2>&1; then
    printf 'launchd'; return
  fi
  if [ -n "$PREFIX" ] || { [ "$(id -u)" = "0" ] && [ -d /etc/cron.d ]; }; then
    printf 'cron.d'; return
  fi
  printf 'usercrontab'
}

files_identical() { cmp -s "$1" "$2" 2>/dev/null; }

install_cron_d() {
  local bindir crondir
  if [ -n "$PREFIX" ]; then
    bindir="$PREFIX/usr/local/bin"; crondir="$PREFIX/etc/cron.d"
  else
    bindir="/usr/local/bin"; crondir="/etc/cron.d"
    [ "$(id -u)" = "0" ] || die "cron.d mode needs root (or PODCAST_SCHEDULER_ROOT); try --force usercrontab"
  fi
  mkdir -p "$bindir" "$crondir"
  # Runner: replace only on change (idempotent; never churn an identical file).
  if [ ! -f "$bindir/$RUNNER_BASENAME" ] || ! files_identical "$RUNNER_SRC" "$bindir/$RUNNER_BASENAME"; then
    cp "$RUNNER_SRC" "$bindir/$RUNNER_BASENAME"
    chmod 755 "$bindir/$RUNNER_BASENAME"
    log "installed runner: $bindir/$RUNNER_BASENAME"
  else
    log "runner already current: $bindir/$RUNNER_BASENAME"
  fi
  # cron.d entry: the user field follows the box's runtime user.
  if [ ! -f "$crondir/podcast-scheduler" ] || ! grep -q "$bindir/$RUNNER_BASENAME" "$crondir/podcast-scheduler" 2>/dev/null; then
    sed "s|^\\*/5 \\* \\* \\* \\* .*|*/5 * * * * $NODE_USER $bindir/$RUNNER_BASENAME|" "$CRON_SRC" > "$crondir/podcast-scheduler"
    chmod 644 "$crondir/podcast-scheduler"
    log "installed cron entry: $crondir/podcast-scheduler (every 5 min, user $NODE_USER)"
  else
    log "cron entry already current: $crondir/podcast-scheduler"
  fi
}

install_launchd() {
  [ "$(uname -s)" = "Darwin" ] || die "launchd mode is macOS only"
  [ -f "$PLIST_TEMPLATE" ] || die "plist template missing: $PLIST_TEMPLATE"
  local agents_dir plist home_dir uid
  home_dir="$(eval echo "~$NODE_USER" 2>/dev/null || echo "$HOME")"
  [ -d "$home_dir" ] || home_dir="$HOME"
  agents_dir="$home_dir/Library/LaunchAgents"
  plist="$agents_dir/$PLIST_LABEL.plist"
  mkdir -p "$agents_dir"
  sed -e "s|PODCAST_SCHEDULER_RUNNER_PATH|$RUNNER_SRC|g" \
      -e "s|PODCAST_SCHEDULER_HOME|$home_dir|g" \
      "$PLIST_TEMPLATE" > "$plist"
  log "rendered launch agent: $plist"
  uid="$(id -u)"
  # Idempotent reload: bootout (ignore absent), then bootstrap.
  launchctl bootout "gui/$uid/$PLIST_LABEL" >/dev/null 2>&1 || true
  if launchctl bootstrap "gui/$uid" "$plist" >/dev/null 2>&1; then
    log "launchd agent active: $PLIST_LABEL (StartInterval 300s)"
  elif launchctl load "$plist" >/dev/null 2>&1; then
    log "launchd agent active (legacy load): $PLIST_LABEL"
  else
    die "launchctl could not load $plist (run as the runtime user)"
  fi
}

install_usercrontab() {
  command -v crontab >/dev/null 2>&1 || die "crontab not available; install via cron.d or launchd"
  local line
  line="*/5 * * * * $RUNNER_SRC"
  if crontab -l 2>/dev/null | grep -qF "$RUNNER_SRC"; then
    log "usercrontab entry already present for $RUNNER_SRC"
    return
  fi
  { crontab -l 2>/dev/null || true; printf '%s\n' "$line"; } | crontab -
  log "installed usercrontab entry (every 5 min): $line"
}

check_mode() {
  local mode; mode="$(detect_mode)"
  case "$mode" in
    launchd)
      if launchctl list 2>/dev/null | grep -q "$PLIST_LABEL"; then
        log "CHECK: heartbeat ACTIVE ($PLIST_LABEL)"; exit 0
      fi
      log "CHECK: heartbeat NOT ACTIVE (launchd agent absent)"; exit 1 ;;
    cron.d)
      local crondir="/etc/cron.d"; [ -n "$PREFIX" ] && crondir="$PREFIX/etc/cron.d"
      if [ -f "$crondir/podcast-scheduler" ]; then
        log "CHECK: heartbeat ACTIVE ($crondir/podcast-scheduler)"; exit 0
      fi
      log "CHECK: heartbeat NOT ACTIVE (no $crondir/podcast-scheduler)"; exit 1 ;;
    usercrontab)
      if crontab -l 2>/dev/null | grep -qF "$RUNNER_SRC"; then
        log "CHECK: heartbeat ACTIVE (usercrontab)"; exit 0
      fi
      log "CHECK: heartbeat NOT ACTIVE (no usercrontab entry)"; exit 1 ;;
  esac
}

if [ "$CHECK_ONLY" = "1" ]; then check_mode; fi

MODE="$(detect_mode)"
log "activating heartbeat via: $MODE (processor: podcast_controller.py --once)"
chmod 755 "$RUNNER_SRC"
case "$MODE" in
  launchd)     install_launchd ;;
  cron.d)      install_cron_d ;;
  usercrontab) install_usercrontab ;;
  *) usage 3 ;;
esac
log "done: the controller is the processor; the scheduler is its heartbeat."
exit 0
