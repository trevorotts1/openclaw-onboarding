#!/usr/bin/env bash
# install-tunnel-run-agent.sh
# Layer B-nosudo -- install a user-level `cloudflared tunnel run` LaunchAgent
# with KeepAlive so the tunnel PROCESS auto-restarts if it exits. No sudo.
#
# Use this on Macs where cloudflared runs as a named-tunnel USER agent (config
# file + credentials JSON) rather than the root connector daemon. For the root
# daemon path use harden-mac-tunnel.sh (Layers A+B, sudo).
#
# Usage:
#   bash install-tunnel-run-agent.sh <tunnel-name> [config-path]
#     <tunnel-name>  short name -> label becomes com.cloudflared.<tunnel-name>
#     [config-path]  default: ~/.cloudflared/config-<tunnel-name>.yml
#
# Fully idempotent. Safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$HERE/com.clawd.tunnel-run.plist.template"

NAME="${1:-}"
[[ -n "$NAME" ]] || { echo "ERROR: tunnel-name required. Usage: $0 <tunnel-name> [config-path]" >&2; exit 1; }

CLOUDFLARED="$(command -v cloudflared || echo /opt/homebrew/bin/cloudflared)"
CONFIG_PATH="${2:-$HOME/.cloudflared/config-${NAME}.yml}"
LABEL="com.cloudflared.${NAME}"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_PATH="$HOME/.openclaw/logs/cloudflared-${NAME}.log"
UID_VAL="$(id -u)"

[[ -f "$TEMPLATE" ]]    || { echo "ERROR: $TEMPLATE not found" >&2; exit 1; }
[[ -x "$CLOUDFLARED" ]] || { echo "ERROR: cloudflared not found at $CLOUDFLARED" >&2; exit 1; }
[[ -f "$CONFIG_PATH" ]] || { echo "ERROR: tunnel config not found: $CONFIG_PATH" >&2; exit 1; }
grep -qiE '^tunnel:' "$CONFIG_PATH" || {
  echo "ERROR: $CONFIG_PATH has no 'tunnel:' key — the run command needs the id from config." >&2; exit 1; }

mkdir -p "$HOME/.openclaw/logs"

# ---- Stop existing agent if running (idempotent) ----------------------------
if launchctl print "gui/${UID_VAL}/${LABEL}" >/dev/null 2>&1; then
  echo "Stopping existing $LABEL agent"
  launchctl bootout "gui/${UID_VAL}/${LABEL}" 2>/dev/null || true
fi

# ---- Expand template + write plist ------------------------------------------
sed -e "s|__LABEL__|${LABEL}|g" \
    -e "s|__CLOUDFLARED__|${CLOUDFLARED}|g" \
    -e "s|__CONFIG_PATH__|${CONFIG_PATH}|g" \
    -e "s|__LOG_PATH__|${LOG_PATH}|g" \
    "$TEMPLATE" > "$PLIST_PATH"
echo "Wrote plist: $PLIST_PATH"

# ---- Load + verify the tunnel comes up --------------------------------------
launchctl bootstrap "gui/${UID_VAL}" "$PLIST_PATH"
echo "Bootstrapped $LABEL"

RUNNING_PID=""
for _ in 1 2 3 4 5 6 7 8; do
  sleep 2
  RUNNING_PID="$(launchctl print "gui/${UID_VAL}/${LABEL}" 2>/dev/null \
                 | awk -F'=' '/^[[:space:]]*pid =/{gsub(/[^0-9]/,"",$2); print $2; exit}')"
  [[ "$RUNNING_PID" =~ ^[0-9]+$ && "$RUNNING_PID" != "0" ]] && break
  RUNNING_PID=""
done

if [[ -n "$RUNNING_PID" ]]; then
  echo "OK: $LABEL running with PID=$RUNNING_PID (KeepAlive=true; auto-restarts on exit)"
  echo "Log: $LOG_PATH"
else
  echo "WARN: $LABEL loaded but no stable PID within 16s — check the config/credentials." >&2
  echo "  tail -20 $LOG_PATH" >&2
  echo "  launchctl print gui/${UID_VAL}/${LABEL}" >&2
  exit 1
fi
