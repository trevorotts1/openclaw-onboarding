#!/bin/bash
# Phase 6b - Create Cloudflare Tunnel via API
# Usage: ./create-tunnel.sh <client-slug> <company-name> <contact-email>
# Example: ./create-tunnel.sh acme-dental "Acme Dental" "ops@acmedental.com"

set -euo pipefail

CLIENT_SLUG="${1:?Usage: ./create-tunnel.sh <client-slug> <company-name> <contact-email>}"
COMPANY_NAME="${2:?Missing company name}"
CONTACT_EMAIL="${3:?Missing contact email}"

TUNNEL_NAME="${CLIENT_SLUG}-command-center"
CF_ACCOUNT_ID="13f808b72eb78027a8046357c6cf1afa"
WEBHOOK_URL="https://main.blackceoautomations.com/webhook/command-center-register-v3"

# Step 1: Get token
CF_TOKEN=""
for envfile in ~/.openclaw/.env ~/.openclaw/secrets/.env; do
  if [ -f "$envfile" ]; then
    val=$(grep "^CLOUDFLARE_TUNNEL_TOKEN=" "$envfile" 2>/dev/null | cut -d= -f2-)
    if [ -n "$val" ]; then CF_TOKEN="$val"; break; fi
  fi
done
if [ -z "$CF_TOKEN" ]; then
  echo "ERROR: CLOUDFLARE_TUNNEL_TOKEN not found in any env file"
  exit 1
fi
echo "[1/7] Token loaded"

# Step 2: Generate secret
TUNNEL_SECRET=$(openssl rand -base64 32)
echo "[2/7] Secret generated"

# Step 3: Create tunnel via API
echo "[3/7] Creating tunnel..."
RESPONSE=$(curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/cfd_tunnel" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$TUNNEL_NAME\",\"tunnel_secret\":\"$TUNNEL_SECRET\",\"config_src\":\"local\"}")

SUCCESS=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('success','false'))")
if [ "$SUCCESS" != "True" ]; then
  echo "ERROR: Tunnel creation failed"
  echo "$RESPONSE" | python3 -m json.tool
  exit 1
fi

TUNNEL_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['id'])")
echo "  Tunnel ID: $TUNNEL_ID"

# Step 4: Save credentials
mkdir -p ~/.cloudflared
echo "$RESPONSE" | python3 -c "
import sys, json
r = json.load(sys.stdin)['result']['credentials_file']
json.dump(r, open('$HOME/.cloudflared/${TUNNEL_NAME}.json', 'w'), indent=2)
"
echo "[4/7] Credentials saved to ~/.cloudflared/${TUNNEL_NAME}.json"

# Step 5: Write config
cat > ~/.cloudflared/config-command-center.yml << EOF
tunnel: $TUNNEL_ID
credentials-file: $HOME/.cloudflared/${TUNNEL_NAME}.json
ingress:
  - hostname: ${CLIENT_SLUG}.zerohumanworkforce.com
    service: http://localhost:4000
  - service: http_status:404
EOF
echo "[5/7] Config written to ~/.cloudflared/config-command-center.yml"

# Step 6: Set up launchctl service for auto-restart
echo "[6/7] Setting up launchctl service..."

PLIST_PATH="$HOME/Library/LaunchAgents/com.cloudflare.${TUNNEL_NAME}.plist"
CONFIG_PATH="$HOME/.cloudflared/config-command-center.yml"

# Create LaunchAgent plist with KeepAlive for auto-restart
cat > "$PLIST_PATH" << PLIST_EOF
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
        <string>${TUNNEL_ID}</string>
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
PLIST_EOF

echo "  LaunchAgent created at: $PLIST_PATH"

# Unload if already loaded (to handle re-runs)
launchctl unload "$PLIST_PATH" 2>/dev/null || true

# Load the service
launchctl load "$PLIST_PATH"

sleep 3

# Check if tunnel is running
if launchctl list | grep -q "com.cloudflare.${TUNNEL_NAME}"; then
  echo "  Tunnel service loaded successfully"
else
  echo "WARNING: Service may not have loaded. Checking process..."
  if pgrep -f "cloudflared.*${TUNNEL_ID}" > /dev/null; then
    echo "  Tunnel process running (PID: $(pgrep -f "cloudflared.*${TUNNEL_ID}"))"
  else
    echo "ERROR: Tunnel failed to start. Check /tmp/cloudflared-${TUNNEL_NAME}.log"
    exit 1
  fi
fi

# Step 7: POST webhook
echo "[7/7] Registering with webhook..."
WEBHOOK_RESPONSE=$(curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "{\"clientName\":\"$CLIENT_SLUG\",\"tunnelId\":\"$TUNNEL_ID\",\"companyName\":\"$COMPANY_NAME\",\"contactEmail\":\"$CONTACT_EMAIL\"}")
echo "  Webhook response: $WEBHOOK_RESPONSE"

# Verify
echo ""
echo "Waiting 10 seconds for DNS..."
sleep 10
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://${CLIENT_SLUG}.zerohumanworkforce.com" 2>/dev/null || echo "000")
echo "URL check: https://${CLIENT_SLUG}.zerohumanworkforce.com -> $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
  echo "SUCCESS: Command Center is live at https://${CLIENT_SLUG}.zerohumanworkforce.com"
else
  echo "WARNING: Got $HTTP_CODE. DNS may still be propagating. Try again in a minute."
fi
