#!/usr/bin/env bash
# install-service-remediate.sh
# No-sudo installer for the Mac OpenClaw SERVICE self-heal + gateway watchdog.
#
# Installs:
#   1. remediate.sh              -> ~/.openclaw/service-env/remediate.sh        (chmod 700)
#   2. gateway-health-watchdog.sh -> ~/.openclaw/service-env/gateway-watchdog.sh (chmod 700)
#      NOTE the rename: remediate.sh delegates the gateway HEALTH leg to the file
#      named exactly `gateway-watchdog.sh` in this dir. Dropping the watchdog here
#      activates that delegation — no second LaunchAgent, no extra scheduler. The
#      existing com.openclaw.service-remediate agent (every 5 min) runs it.
#   3. com.openclaw.service-remediate LaunchAgent (StartInterval=300) that runs
#      remediate.sh every 5 minutes to re-bootstrap any booted-out gateway /
#      cloudflared LaunchAgent, kickstart any dead KeepAlive job, and delegate
#      the gateway HTTP-health probe to gateway-watchdog.sh.
#
# Run as the box's login user (no sudo):
#   bash install-service-remediate.sh
#
# Fully idempotent. Safe to re-run. Never edits config/creds. Never runs bare gws.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.openclaw.service-remediate"
SVC_DIR="$HOME/.openclaw/service-env"
DEST_SCRIPT="$SVC_DIR/remediate.sh"
SRC_SCRIPT="$HERE/remediate.sh"
# The watchdog ships as gateway-health-watchdog.sh and installs as
# gateway-watchdog.sh — the exact name remediate.sh delegates to.
SRC_WATCHDOG="$HERE/gateway-health-watchdog.sh"
DEST_WATCHDOG="$SVC_DIR/gateway-watchdog.sh"
TEMPLATE="$HERE/com.openclaw.service-remediate.plist.template"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_PATH="$HOME/Library/Logs/openclaw/service-remediate-agent.log"
INTERVAL="${REMEDIATE_INTERVAL:-300}"
UID_VAL="$(id -u)"

[[ -f "$SRC_SCRIPT" ]] || { echo "ERROR: $SRC_SCRIPT not found" >&2; exit 1; }
[[ -f "$TEMPLATE" ]]   || { echo "ERROR: $TEMPLATE not found" >&2; exit 1; }

# ---- 1) Install remediate.sh ------------------------------------------------
mkdir -p "$SVC_DIR" "$HOME/Library/Logs/openclaw"
cp "$SRC_SCRIPT" "$DEST_SCRIPT"
chmod 700 "$DEST_SCRIPT"
echo "Installed: $DEST_SCRIPT"

# ---- 1b) Install gateway-health watchdog (renamed to gateway-watchdog.sh) ----
# Optional: older bundles may not ship the watchdog. If absent, remediate.sh
# falls back to presence-only healing (no HTTP-health leg) — still functional.
if [[ -f "$SRC_WATCHDOG" ]]; then
  cp "$SRC_WATCHDOG" "$DEST_WATCHDOG"
  chmod 700 "$DEST_WATCHDOG"
  echo "Installed: $DEST_WATCHDOG (remediate.sh will delegate the gateway HTTP-health leg to it)"
else
  echo "NOTE: $SRC_WATCHDOG not in bundle — installing presence-only self-heal" >&2
  echo "      (gateway HTTP-health watchdog will be added on the next update)."   >&2
fi

# ---- 2) Stop existing agent if running (idempotent) -------------------------
if launchctl print "gui/${UID_VAL}/${LABEL}" >/dev/null 2>&1; then
  echo "Stopping existing $LABEL agent"
  launchctl bootout "gui/${UID_VAL}/${LABEL}" 2>/dev/null || true
fi

# ---- 3) Expand template + write plist ---------------------------------------
sed -e "s|__SCRIPT_PATH__|${DEST_SCRIPT}|g" \
    -e "s|__LOG_PATH__|${LOG_PATH}|g" \
    -e "s|__INTERVAL__|${INTERVAL}|g" \
    "$TEMPLATE" > "$PLIST_PATH"
echo "Wrote plist: $PLIST_PATH (interval=${INTERVAL}s)"

# ---- 4) Load the agent ------------------------------------------------------
launchctl bootstrap "gui/${UID_VAL}" "$PLIST_PATH"
echo "Bootstrapped $LABEL"

# ---- 5) Verify --------------------------------------------------------------
sleep 2
if launchctl print "gui/${UID_VAL}/${LABEL}" >/dev/null 2>&1; then
  echo "OK: $LABEL loaded. It runs remediate.sh every ${INTERVAL}s."
  echo "    Gateway health: delegated to $DEST_WATCHDOG (HTTP {\"ok\":true} probe + kickstart)."
  echo "Log: $HOME/Library/Logs/openclaw/service-remediate.log"
else
  echo "WARN: $LABEL not confirmed loaded." >&2
  echo "Check with:  launchctl print gui/${UID_VAL}/${LABEL}" >&2
  exit 1
fi
