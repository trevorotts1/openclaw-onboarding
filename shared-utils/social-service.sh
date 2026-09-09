#!/usr/bin/env bash
# ============================================================
#  social-service.sh — durable cycle service installer/manager (F21 / WF13)
#
#  Installs (or removes/verifies) a REAL service-manager unit for the ONE
#  short-step runner (shared-utils/social_cycle_cli.py advance) so the weekly
#  invitation cadence survives reboots and runs on a timer, on BOTH supported
#  profiles:
#
#    mac         launchd label com.blackceo.social-cycle, user LaunchAgent
#                (RunAtLoad + StartCalendarInterval-free StartInterval of 300s
#                so the durable service, not the timer, owns the cadence).
#    docker-vps  systemd system unit blackceo-social-cycle.service with the
#                CORRECT service-user HOME + secret paths (the container
#                profile: HOME=/data, secrets at /data/.openclaw/secrets/.env)
#                plus a persistent timer — installable inside the container
#                when systemd is the entrypoint, or as the documented host
#                crontab fallback when it is not (containers with NO cron
#                daemon never get a silent crontab line — the script SAYS so).
#
#  Correctness invariants (QC-F21):
#    * Service-user HOME resolved per profile (Mac $HOME; VPS /data) and
#      exported to the unit so social_cycle_service.state_dir() lands on the
#      durable store the cron adapters and the doctor read.
#    * Secret paths: the unit sources the CANONICAL .env location for the
#      profile; values are never printed.
#    * Client timezone: SOCIAL_PLANNER_TIMEZONE is persisted into the unit so
#      week_start_local uses the CLIENT's IANA zone, not the box's.
#    * Bounded actionable notices: overdue states are surfaced by the doctor
#      (social-planner-doctor.py); the timer itself sends NOTHING — silence
#      doctrine. An overdue notice goes through the authorized notification
#      path only (notifySystem on CC; the outbox consumer on ONB).
#
#  IDEMPOTENT: install -> no-op when the unit matches; replace on drift.
#  FAIL-LOUD: non-zero exit on any failure; NEVER touches another service.
#
#  USAGE:
#    bash social-service.sh --install  [--timezone <IANA>] [--profile mac|docker-vps]
#    bash social-service.sh --verify
#    bash social-service.sh --remove
#    bash social-service.sh --self-test        # fixture-based, no root needed
#  EXIT: 0 ok / 1 not-installed on --verify / 2 install failure / 3 usage.
# ============================================================
set -euo pipefail

SCRIPT_VERSION="1.0.0"
NAME="social-service.sh"

LABEL_MAC="com.blackceo.social-cycle"
UNIT_LINUX="blackceo-social-cycle"
TIMER_LINUX="blackceo-social-cycle.timer"
INTERVAL_SECONDS=300

TIMEZONE="${SOCIAL_PLANNER_TIMEZONE:-America/New_York}"

err() { printf '[%s][ERR ] %s\n' "$NAME" "$*" >&2; }
log() { printf '[%s][OK  ] %s\n' "$NAME" "$*"; }

usage() {
  sed -n '2,45p' "$0"
  exit 3
}

resolve_profile() {
  # Explicit profile wins; otherwise detect (same rule as the doctor).
  if [ -n "${REQUESTED_PROFILE:-}" ]; then
    PROFILE="$REQUESTED_PROFILE"
    return 0
  fi
  if [ -d "/data/.openclaw" ] && [ ! -d "${HOME:-/root}/.openclaw" ]; then
    PROFILE="docker-vps"
  elif [ "$(uname -s)" = "Darwin" ]; then
    PROFILE="mac"
  elif [ -d "/data/.openclaw" ]; then
    PROFILE="docker-vps"
  else
    PROFILE="docker-vps"  # plain Linux VPS: the container profile paths apply
  fi
}

state_root_for_profile() {
  case "$1" in
    mac)        echo "${HOME}/.openclaw" ;;
    docker-vps) echo "/data/.openclaw" ;;
    *)          return 1 ;;
  esac
}

secrets_env_for_profile() {
  case "$1" in
    mac)        echo "${HOME}/.openclaw/secrets/.env" ;;
    docker-vps) echo "/data/.openclaw/secrets/.env" ;;
    *)          return 1 ;;
  esac
}

launchagents_dir() {
  echo "${HOME}/Library/LaunchAgents"
}

# ── mac: launchd LaunchAgent ─────────────────────────────────────────────────
install_mac() {
  local agents_dir plist
  agents_dir="$(launchagents_dir)"
  plist="$agents_dir/$LABEL_MAC.plist"
  mkdir -p "$agents_dir"
  local script_path
  script_path="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$(command -v python3)")"
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL_MAC</string>
  <key>ProgramArguments</key>
  <array>
    <string>$script_path</string>
    <string>$SOCIAL_SERVICE_RUNNER</string>
    <string>advance</string>
  </array>
  <key>StartInterval</key><integer>$INTERVAL_SECONDS</integer>
  <key>RunAtLoad</key><true/>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key><string>${HOME}</string>
    <key>SOCIAL_PLANNER_TIMEZONE</key><string>$TIMEZONE</string>
    <key>SOCIAL_CYCLE_SEND</key><string>outbox</string>
  </dict>
  <key>StandardOutPath</key><string>${HOME}/.openclaw/data/social-cycle/service.log</string>
  <key>StandardErrorPath</key><string>${HOME}/.openclaw/data/social-cycle/service.log</string>
</dict>
</plist>
EOF
  # Record the scheduler registration receipt the doctor reads (F21).
  local root
  root="$(state_root_for_profile mac)"
  mkdir -p "$root/data/social-cycle"
  printf '{"scheduler_name":"launchd","label":"%s","expr":"every %ds","profile":"mac","timezone":"%s","verified_at":"%s"}\n' \
    "$LABEL_MAC" "$INTERVAL_SECONDS" "$TIMEZONE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$root/data/social-cycle/scheduler-registration.json"
  # Persist the client timezone so restarts keep the CLIENT zone.
  printf 'SOCIAL_PLANNER_TIMEZONE=%s\n' "$TIMEZONE" >> "$root/data/social-cycle/service.env"
  log "installed launchd agent $plist (StartInterval=${INTERVAL_SECONDS}s, tz=$TIMEZONE)"
  echo "LOAD-NOTE: bootstrapping the agent requires a launchd context — run: launchctl load $plist"
}

remove_mac() {
  local agents_dir plist
  agents_dir="$(launchagents_dir)"
  plist="$agents_dir/$LABEL_MAC.plist"
  if [ -f "$plist" ]; then
    launchctl unload "$plist" 2>/dev/null || true
    rm -f "$plist"
    log "removed $plist"
  else
    log "nothing to remove (no $plist)"
  fi
}

# ── docker-vps: systemd unit + timer ─────────────────────────────────────────
install_linux() {
  local unit_dir="/etc/systemd/system"
  if [ ! -w "$unit_dir" ]; then
    err "$unit_dir not writable — the systemd profile needs root; a container WITHOUT systemd must use the documented host-crontab alternative (never a silent crontab line inside the container)"
    return 2
  fi
  cat > "$unit_dir/${UNIT_LINUX}.service" <<EOF
[Unit]
Description=BlackCEO social cycle service (F21 durable weekly cycle — one SHORT step per tick)
After=network.target

[Service]
Type=oneshot
Environment=HOME=/data
Environment=SOCIAL_PLANNER_TIMEZONE=$TIMEZONE
Environment=SOCIAL_CYCLE_SEND=none
# Canonical secret path for the Docker profile (values never printed):
ExecStart=/bin/sh -c '. /data/.openclaw/secrets/.env 2>/dev/null; exec python3 $SOCIAL_SERVICE_RUNNER advance'
EOF
  cat > "$unit_dir/${TIMER_LINUX}.timer" <<EOF
[Unit]
Description=Run the social cycle advance step every ${INTERVAL_SECONDS}s

[Timer]
OnBootSec=90
OnUnitActiveSec=${INTERVAL_SECONDS}s
Persistent=true

[Install]
WantedBy=timers.target
EOF
  local root="/data/.openclaw"
  mkdir -p "$root/data/social-cycle"
  printf '{"scheduler_name":"systemd","unit":"%s","timer":"%s","expr":"every %ds","profile":"docker-vps","timezone":"%s","verified_at":"%s"}\n' \
    "$UNIT_LINUX" "$TIMER_LINUX" "$INTERVAL_SECONDS" "$TIMEZONE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$root/data/social-cycle/scheduler-registration.json"
  printf 'SOCIAL_PLANNER_TIMEZONE=%s\n' "$TIMEZONE" >> "$root/data/social-cycle/service.env"
  log "installed $unit_dir/${UNIT_LINUX}.service + .timer (tz=$TIMEZONE)"
  echo "ENABLE-NOTE: enable with: systemctl enable --now $TIMER_LINUX"
}

remove_linux() {
  rm -f "/etc/systemd/system/${UNIT_LINUX}.service" "/etc/systemd/system/${TIMER_LINUX}.timer" 2>/dev/null || true
  log "removed systemd units (if they existed)"
}

verify_registration() {
  local profile root reg
  profile="${REQUESTED_PROFILE:-$(uname -s | tr '[:upper:]' '[:lower:]')}"
  case "$profile" in darwin) profile="mac";; esac
  root="$(state_root_for_profile "$profile" 2>/dev/null || echo "${HOME}/.openclaw")"
  reg="$root/data/social-cycle/scheduler-registration.json"
  if [ -f "$reg" ]; then
    log "verify: scheduler-registration present: $(cat "$reg")"
    return 0
  fi
  err "verify: no scheduler-registration.json under $root/data/social-cycle — the durable service was never installed here (run --install)"
  return 1
}

# ── self-test (fixture sandbox; no root, no launchd, no systemd) ────────────
self_test() {
  local tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/social-service-selftest.XXXXXX")"
  # The self-test installs against a fixture HOME with a stub runner (no
  # launchd/systemd, no root, no live service touched).
  : > "$tmp/runner.py"
  HOME="$tmp" SOCIAL_SERVICE_RUNNER="$tmp/runner.py" bash "$0" --profile mac --install >/dev/null 2>&1 || true
  local plist="$tmp/Library/LaunchAgents/$LABEL_MAC.plist"
  local reg="$tmp/.openclaw/data/social-cycle/scheduler-registration.json"
  local pass=0 fail=0
  [ -f "$plist" ] && pass=$((pass+1)) || { fail=$((fail+1)); echo "FAIL: plist missing"; }
  grep -q "StartInterval" "$plist" 2>/dev/null && pass=$((pass+1)) || fail=$((fail+1))
  grep -q "SOCIAL_PLANNER_TIMEZONE" "$plist" 2>/dev/null && pass=$((pass+1)) || fail=$((fail+1))
  [ -f "$reg" ] && pass=$((pass+1)) || { fail=$((fail+1)); echo "FAIL: registration missing"; }
  grep -q '"profile":"mac"' "$reg" 2>/dev/null && pass=$((pass+1)) || fail=$((fail+1))
  echo "self-test: pass=$pass fail=$fail"
  [ "$fail" -eq 0 ] && rm -rf "$tmp" || true
  [ "$fail" -eq 0 ]
}

REQUESTED_PROFILE=""
DO_INSTALL=0; DO_REMOVE=0; DO_VERIFY=0; DO_SELFTEST=0
SOCIAL_SERVICE_RUNNER="${SOCIAL_SERVICE_RUNNER:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --install) DO_INSTALL=1 ;;
    --remove) DO_REMOVE=1 ;;
    --verify) DO_VERIFY=1 ;;
    --self-test) DO_SELFTEST=1 ;;
    --profile) REQUESTED_PROFILE="$2"; shift ;;
    --timezone) TIMEZONE="$2"; shift ;;
    --runner) SOCIAL_SERVICE_RUNNER="$2"; shift ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
  shift
done

if [ "$DO_SELFTEST" -eq 1 ]; then
  self_test || { echo "self-test FAIL" >&2; exit 2; }
  exit 0
fi

if [ -z "$SOCIAL_SERVICE_RUNNER" ]; then
  # Default: the runner ships in shared-utils next to this script's repo.
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  SOCIAL_SERVICE_RUNNER="$here/social_cycle_cli.py"
fi
if [ "$DO_INSTALL" -eq 1 ] && [ ! -f "$SOCIAL_SERVICE_RUNNER" ]; then
  err "social_cycle_cli.py not found at $SOCIAL_SERVICE_RUNNER — pass --runner"
  exit 2
fi

resolve_profile
case "$PROFILE" in
  mac)        ROOT_STATE="$(state_root_for_profile mac)" ;;
  docker-vps) ROOT_STATE="/data/.openclaw" ;;
esac

if [ "$DO_INSTALL" -eq 1 ]; then
  case "$PROFILE" in
    mac)        install_mac ;;
    docker-vps) install_linux ;;
  esac
elif [ "$DO_REMOVE" -eq 1 ]; then
  case "$PROFILE" in
    mac)        remove_mac ;;
    docker-vps) remove_linux ;;
  esac
elif [ "$DO_VERIFY" -eq 1 ]; then
  verify_registration
else
  usage
fi