#!/usr/bin/env bash
# install-watchdog-agent.sh
# Bucket 2 / Layer D-nosudo -- no-sudo, remote-pushable.
# Installs com.clawd.tunnel-watchdog: a user LaunchAgent that fires every 5
# minutes to check that cloudflared is alive.
# If the connector is dead (user-scope): tries to kickstart it.
# If the connector is root-scope and down: logs ESCALATE for the operator to read.
# If TUNNEL_PUBLIC_URL is set: probes it for CF error 1033.
#
# Run as the box's login user (no sudo):
#   bash install-watchdog-agent.sh
#
# Fully idempotent.
set -euo pipefail

LABEL="com.clawd.tunnel-watchdog"
CLOUDFLARED_DIR="$HOME/.cloudflared"
SCRIPT_PATH="$CLOUDFLARED_DIR/tunnel-watchdog.sh"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_PATH="/tmp/clawd-tunnel-watchdog.log"
INTERVAL=300   # 5 minutes -- */5
UID_VAL="$(id -u)"

# ---- Stop current instance if running (idempotent) --------------------------
if launchctl print "gui/${UID_VAL}/${LABEL}" >/dev/null 2>&1; then
  echo "Stopping existing $LABEL agent"
  launchctl bootout "gui/${UID_VAL}/${LABEL}" 2>/dev/null || true
fi

# ---- Write the watchdog script ----------------------------------------------
mkdir -p "$CLOUDFLARED_DIR"
cat > "$SCRIPT_PATH" <<'WATCHDOG_SCRIPT'
#!/usr/bin/env bash
# tunnel-watchdog.sh -- runs at boot and every 5 min via launchd StartInterval.
# Checks cloudflared health; logs ESCALATE if root daemon is down.
set -uo pipefail

LOG="/tmp/clawd-tunnel-watchdog.log"
TS="$(date -u +%FT%TZ)"
PUBLIC_URL="${TUNNEL_PUBLIC_URL:-}"
DOWN=0

# ---- Check 1: Is a cloudflared process running? ----------------------------
if pgrep -f 'cloudflared.*tunnel' >/dev/null 2>&1; then
  echo "[$TS] cloudflared-process: OK" >> "$LOG"
else
  echo "[$TS] cloudflared-process: NOT FOUND" >> "$LOG"
  DOWN=1

  # Determine whether connector is user-scope (can kickstart) or root-scope (cannot).
  if launchctl print "gui/$(id -u)/com.cloudflare.cloudflared" >/dev/null 2>&1; then
    echo "[$TS] attempting kickstart: user-scope connector" >> "$LOG"
    launchctl kickstart "gui/$(id -u)/com.cloudflare.cloudflared" >> "$LOG" 2>&1 || true
  elif launchctl print "system/com.cloudflare.cloudflared" >/dev/null 2>&1; then
    echo "[$TS] ESCALATE: root connector com.cloudflare.cloudflared is down." >> "$LOG"
    echo "[$TS] ESCALATE: operator must run: sudo launchctl kickstart system/com.cloudflare.cloudflared" >> "$LOG"
    echo "[$TS] ESCALATE: or run: sudo bash harden-mac-tunnel.sh (hardening + restart)" >> "$LOG"
  else
    echo "[$TS] ESCALATE: no cloudflare launchd service found (neither user nor system scope)." >> "$LOG"
    echo "[$TS] ESCALATE: connector may not be installed. Run Skill-38 step 14 or harden-mac-tunnel.sh." >> "$LOG"
  fi
fi

# ---- Check 2: Optional public URL health probe ----------------------------
if [[ -n "$PUBLIC_URL" ]]; then
  HTTP_CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "$PUBLIC_URL" 2>/dev/null || echo '000')"
  case "$HTTP_CODE" in
    000) echo "[$TS] public-url-probe: TIMEOUT/NO-RESPONSE ($PUBLIC_URL)" >> "$LOG"; DOWN=1 ;;
    1033|530) echo "[$TS] public-url-probe: CF-1033 ($HTTP_CODE) -- tunnel has no origin ($PUBLIC_URL)" >> "$LOG"; DOWN=1 ;;
    5*) echo "[$TS] public-url-probe: 5xx ($HTTP_CODE) -- potential tunnel issue ($PUBLIC_URL)" >> "$LOG" ;;
    *) echo "[$TS] public-url-probe: OK ($HTTP_CODE) ($PUBLIC_URL)" >> "$LOG" ;;
  esac
fi

if [[ "$DOWN" -eq 0 ]]; then
  echo "[$TS] watchdog: all checks PASS" >> "$LOG"
fi
WATCHDOG_SCRIPT
chmod +x "$SCRIPT_PATH"
echo "Wrote watchdog script: $SCRIPT_PATH"

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
  <key>StartInterval</key>
  <integer>${INTERVAL}</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_PATH}</string>
  <key>StandardErrorPath</key>
  <string>${LOG_PATH}</string>
</dict>
</plist>
PLIST
echo "Wrote plist: $PLIST_PATH"

# ---- Load the agent ---------------------------------------------------------
launchctl bootstrap "gui/${UID_VAL}" "$PLIST_PATH"
echo "Bootstrapped $LABEL (interval=${INTERVAL}s)"

# ---- Verify load ------------------------------------------------------------
sleep 1
if launchctl print "gui/${UID_VAL}/${LABEL}" >/dev/null 2>&1; then
  echo "OK: $LABEL loaded."
  echo "Log: $LOG_PATH"
  echo ""
  echo "Set TUNNEL_PUBLIC_URL to enable public-URL health probes:"
  echo "  TUNNEL_PUBLIC_URL=https://openclaw.yourdomain.com bash install-watchdog-agent.sh"
else
  echo "WARN: $LABEL may not have loaded correctly." >&2
  echo "Check: launchctl print gui/$(id -u)/$LABEL" >&2
fi
