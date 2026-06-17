#!/usr/bin/env bash
# install-keepalive-agent.sh
# Bucket 2 / Layer C -- no-sudo, remote-pushable.
# Installs com.clawd.tunnel-keepalive: a user LaunchAgent that pings the
# Cloudflare edge every 20s to keep the UDP/QUIC NAT mapping alive.
# Works even when the root daemon is still on QUIC (safe net until sudo harden).
#
# Replaces com.zhc.tunnel-keepalive (legacy label) so there is never two
# simultaneous keepalive agents running.
#
# Run as the box's login user (no sudo):
#   bash install-keepalive-agent.sh
#
# Fully idempotent.
set -euo pipefail

LABEL="com.clawd.tunnel-keepalive"
LEGACY_LABEL="com.zhc.tunnel-keepalive"
CLOUDFLARED_DIR="$HOME/.cloudflared"
SCRIPT_PATH="$CLOUDFLARED_DIR/nat-keepalive.sh"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_PATH="/tmp/clawd-tunnel-keepalive.log"
# CF edge host for the keepalive ping (overridable via env)
KEEPALIVE_HOST="${KEEPALIVE_HOST:-region1.v2.argotunnel.com}"
KEEPALIVE_PORT="${KEEPALIVE_PORT:-7844}"
UID_VAL="$(id -u)"

# ---- Remove legacy com.zhc.tunnel-keepalive if present ----------------------
LEGACY_PLIST="$HOME/Library/LaunchAgents/${LEGACY_LABEL}.plist"
if launchctl print "gui/${UID_VAL}/${LEGACY_LABEL}" >/dev/null 2>&1; then
  echo "Booting out legacy agent: $LEGACY_LABEL"
  launchctl bootout "gui/${UID_VAL}/${LEGACY_LABEL}" 2>/dev/null || true
fi
if [[ -f "$LEGACY_PLIST" ]]; then
  echo "Removing legacy plist: $LEGACY_PLIST"
  rm -f "$LEGACY_PLIST"
fi

# ---- Stop current instance if running (idempotent) --------------------------
if launchctl print "gui/${UID_VAL}/${LABEL}" >/dev/null 2>&1; then
  echo "Stopping existing $LABEL agent"
  launchctl bootout "gui/${UID_VAL}/${LABEL}" 2>/dev/null || true
fi

# ---- Write the keepalive script ---------------------------------------------
mkdir -p "$CLOUDFLARED_DIR"
cat > "$SCRIPT_PATH" <<'KEEPALIVE_SCRIPT'
#!/usr/bin/env bash
# nat-keepalive.sh -- runs forever, pings CF edge every 20s.
# Keeps UDP/QUIC NAT mapping warm so cloudflared stays connected.
# Override targets via env: KEEPALIVE_HOST, KEEPALIVE_PORT
set -euo pipefail

HOST="${KEEPALIVE_HOST:-region1.v2.argotunnel.com}"
PORT="${KEEPALIVE_PORT:-7844}"
INTERVAL=20

echo "[$(date -u +%FT%TZ)] nat-keepalive starting (host=$HOST port=$PORT interval=${INTERVAL}s)"

while true; do
  # Primary: TCP connect to the argotunnel edge (keeps the mapping warm)
  if nc -z -w3 "$HOST" "$PORT" 2>/dev/null; then
    STATUS="ok"
  else
    # Fallback: HTTP ping to the CF CDN trace endpoint
    if curl -s -o /dev/null --max-time 5 https://cloudflare.com/cdn-cgi/trace 2>/dev/null; then
      STATUS="ok-http-fallback"
    else
      STATUS="unreachable"
    fi
  fi
  echo "[$(date -u +%FT%TZ)] edge-ping $STATUS"
  sleep "$INTERVAL"
done
KEEPALIVE_SCRIPT
chmod +x "$SCRIPT_PATH"
echo "Wrote keepalive script: $SCRIPT_PATH"

# ---- Write the LaunchAgent plist --------------------------------------------
cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${SCRIPT_PATH}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_PATH}</string>
  <key>StandardErrorPath</key>
  <string>${LOG_PATH}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>KEEPALIVE_HOST</key>
    <string>${KEEPALIVE_HOST}</string>
    <key>KEEPALIVE_PORT</key>
    <string>${KEEPALIVE_PORT}</string>
  </dict>
</dict>
</plist>
PLIST
echo "Wrote plist: $PLIST_PATH"

# ---- Load the agent ---------------------------------------------------------
launchctl bootstrap "gui/${UID_VAL}" "$PLIST_PATH"
echo "Bootstrapped $LABEL"

# ---- Verify a running PID ---------------------------------------------------
sleep 2
RUNNING_PID=""
RUNNING_PID="$(launchctl print "gui/${UID_VAL}/${LABEL}" 2>/dev/null \
               | grep -E 'pid =' | awk '{print $NF}' || echo '')"

if [[ "$RUNNING_PID" =~ ^[0-9]+$ ]] && [[ "$RUNNING_PID" != "0" ]]; then
  echo "OK: $LABEL running with PID=$RUNNING_PID"
  echo "Log: $LOG_PATH"
  echo ""
  echo "Verify keepalive is ticking (wait ~20s):"
  echo "  tail -5 $LOG_PATH"
else
  echo "WARN: $LABEL loaded but PID not confirmed yet." >&2
  echo "Check with:  launchctl print gui/$(id -u)/$LABEL" >&2
fi
