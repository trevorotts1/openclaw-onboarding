#!/bin/bash
# Sets up Cloudflare tunnel as a launchctl service (auto-restart if it dies)
# Usage: ./setup-tunnel-daemon.sh <tunnel-uuid> <config-path>

TUNNEL_UUID="${1}"
CONFIG_PATH="${2:-$HOME/.cloudflared/config-command-center.yml}"
TUNNEL_NAME="command-center"

if [ -z "$TUNNEL_UUID" ]; then
  echo "ERROR: Tunnel UUID is required"
  echo "Usage: $0 <tunnel-uuid> [config-path]"
  echo "Find your tunnel UUID: cloudflared tunnel list"
  exit 1
fi

PLIST_PATH="$HOME/Library/LaunchAgents/com.cloudflare.${TUNNEL_NAME}.plist"

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cloudflare.${TUNNEL_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/cloudflared</string>
        <string>tunnel</string>
        <string>--config</string>
        <string>${CONFIG_PATH}</string>
        <string>run</string>
        <string>${TUNNEL_UUID}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/cloudflared-${TUNNEL_NAME}.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/cloudflared-${TUNNEL_NAME}.log</string>
</dict>
</plist>
EOF

echo "Plist created at: $PLIST_PATH"

# Unload if already loaded
launchctl unload "$PLIST_PATH" 2>/dev/null

# Load the service
launchctl load "$PLIST_PATH" 2>&1

echo "Tunnel daemon loaded. It auto-restarts if it dies."
echo "Check status: ps aux | grep ${TUNNEL_UUID}"
