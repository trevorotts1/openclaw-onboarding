#!/bin/bash
# Phase 6b - Register Command Center and receive tunnel token in webhook response
# Usage: ./create-tunnel.sh <client-slug> <company-name> <contact-email>

set -euo pipefail

CLIENT_SLUG="${1:?Usage: ./create-tunnel.sh <client-slug> <company-name> <contact-email>}"
COMPANY_NAME="${2:?Missing company name}"
CONTACT_EMAIL="${3:?Missing contact email}"
WEBHOOK_URL="https://main.blackceoautomations.com/webhook/command-center-register-v3"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found. Installing..."
  if command -v brew >/dev/null 2>&1; then
    brew install cloudflared
  else
    curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
    chmod +x /usr/local/bin/cloudflared
  fi
fi

echo "[1/5] Requesting tunnel from Trevor's system..."
# Build the JSON body with python3 so embedded quotes/spaces/special chars in
# the company name or email are escaped correctly. The previous inline
# double-quoted heredoc-style body (-d "{"clientName":...}") collapsed the
# inner quotes under shell parsing and sent an empty/invalid body, which the
# non-idempotent webhook treated as a brand-new registration on every retry.
REQUEST_BODY=$(CLIENT_SLUG="$CLIENT_SLUG" COMPANY_NAME="$COMPANY_NAME" CONTACT_EMAIL="$CONTACT_EMAIL" \
  python3 -c 'import json,os; print(json.dumps({"clientName":os.environ["CLIENT_SLUG"],"companyName":os.environ["COMPANY_NAME"],"contactEmail":os.environ["CONTACT_EMAIL"]}))')
# Retry ONLY on transport failure (curl error / empty response) with backoff, so
# a flaky network doesn't fail the whole install. We deliberately do NOT retry a
# RECEIVED non-success response: this registration webhook is non-idempotent, so
# re-POSTing after the server already answered could double-register a tunnel.
RESPONSE=""
_attempt=0
for _delay in 0 2 4; do
  [ "$_delay" -gt 0 ] && { echo "[1/5] webhook transport retry in ${_delay}s..."; sleep "$_delay"; }
  _attempt=$((_attempt+1))
  RESPONSE=$(curl -sS -m 30 -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "$REQUEST_BODY" 2>/dev/null) && [ -n "$RESPONSE" ] && break
done
if [ -z "$RESPONSE" ]; then
  echo "ERROR: tunnel registration webhook unreachable after ${_attempt} attempt(s) (no response)"
  exit 1
fi

STATUS=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
if [ "$STATUS" != "success" ]; then
  echo "ERROR: webhook failed"
  echo "$RESPONSE"
  exit 1
fi

TUNNEL_TOKEN=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnelToken'])")
SUBDOMAIN=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['subdomain'])")

echo "[2/5] Saving tunnel token to ~/.openclaw/secrets/.env (canonical) + ~/.openclaw/.env (legacy)"
mkdir -p ~/.openclaw
# Legacy location (kept so run-full-install.sh's subdomain-hint check still fires)
TMP_ENV=$(mktemp)
grep -v '^CLOUDFLARE_TUNNEL_TOKEN=' ~/.openclaw/.env 2>/dev/null > "$TMP_ENV" || true
echo "CLOUDFLARE_TUNNEL_TOKEN=$TUNNEL_TOKEN" >> "$TMP_ENV"
mv "$TMP_ENV" ~/.openclaw/.env
# Canonical secrets location (QC.md + qc-command-center-setup.sh read this one)
mkdir -p ~/.openclaw/secrets
TMP_SECRETS=$(mktemp)
grep -v '^CLOUDFLARE_TUNNEL_TOKEN=' ~/.openclaw/secrets/.env 2>/dev/null > "$TMP_SECRETS" || true
echo "CLOUDFLARE_TUNNEL_TOKEN=$TUNNEL_TOKEN" >> "$TMP_SECRETS"
mv "$TMP_SECRETS" ~/.openclaw/secrets/.env
chmod 600 ~/.openclaw/secrets/.env

echo "[3/5] Starting tunnel via PM2"
pm2 delete cloudflare-tunnel >/dev/null 2>&1 || true
pm2 start "cloudflared tunnel run --token $TUNNEL_TOKEN" --name cloudflare-tunnel >/dev/null
pm2 save >/dev/null

echo "[4/5] Waiting for tunnel to come online..."
sleep 15
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://$SUBDOMAIN" 2>/dev/null || echo "000")

echo "[5/5] Result"
echo "Subdomain: https://$SUBDOMAIN"
echo "HTTP: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
  echo "SUCCESS: Command Center is live"
else
  echo "WARNING: URL not live yet. Check: pm2 status cloudflare-tunnel"
fi
