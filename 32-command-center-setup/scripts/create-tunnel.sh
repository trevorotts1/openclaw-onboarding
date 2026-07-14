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

echo "[1/5] Requesting tunnel from the operator's system..."
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
  echo "ERROR: tunnel registration webhook unreachable after ${_attempt} attempt(s) (no response)" >&2
  echo "ESCALATE: message the operator with this client slug ($CLIENT_SLUG) and note the webhook" >&2
  echo "  at $WEBHOOK_URL did not respond. Do NOT attempt to create a Cloudflare tunnel any other" >&2
  echo "  way — do NOT run 'cloudflared tunnel login', do NOT create a Cloudflare account. The" >&2
  echo "  tunnel can only be issued by the operator's n8n system; wait for the operator to confirm" >&2
  echo "  the webhook is back up, then re-run this script." >&2
  exit 1
fi

STATUS=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
if [ "$STATUS" != "success" ]; then
  echo "ERROR: webhook failed" >&2
  echo "$RESPONSE" >&2
  echo "ESCALATE: message the operator with this client slug ($CLIENT_SLUG) and the response body" >&2
  echo "  above. Do NOT attempt to create a Cloudflare tunnel any other way — do NOT run" >&2
  echo "  'cloudflared tunnel login', do NOT create a Cloudflare account." >&2
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
# CC dashboard's authoritative local port. Single source of truth:
# shared-utils/cc-tunnel-ingress.sh (CC_INGRESS_PORT) and run-full-install.sh
# (DASHBOARD_PORT=4000). tests/unit/cc-tunnel-ingress-guard.test.sh asserts this
# literal stays equal to the lib's CC_INGRESS_PORT so the two can never drift.
CC_INGRESS_PORT="${CC_INGRESS_PORT:-4000}"
LOCAL_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${CC_INGRESS_PORT}" 2>/dev/null || echo "000")
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://$SUBDOMAIN" 2>/dev/null || echo "000")
# Retry/backoff the PUBLIC probe before trusting a bad code: cloudflared commonly
# returns 502/1033 for the first several seconds after `tunnel run` while the
# edge connection is still warming up, and a single probe here would false-flag
# that transient blip as the wrong-port/no-route condition and hard-fail
# provisioning. Only keep treating it as wrong-port if it is STILL failing after
# retrying — a persistent 1303/502/etc still falls through to the exit-7 branch
# below unchanged.
if echo "$LOCAL_CODE" | grep -qE '^(200|301|302|307|404)$' && echo "$HTTP_CODE" | grep -qE '^(502|1033|1303|530|503)$'; then
  for _wdelay in 4 4 4; do
    echo "[4/5] public probe returned $HTTP_CODE (possible warm-up blip); retrying in ${_wdelay}s..." >&2
    sleep "$_wdelay"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://$SUBDOMAIN" 2>/dev/null || echo "000")
    echo "$HTTP_CODE" | grep -qE '^(502|1033|1303|530|503)$' || break
  done
fi

echo "[5/5] Result"
echo "Subdomain: https://$SUBDOMAIN"
echo "Local CC (http://localhost:${CC_INGRESS_PORT}): $LOCAL_CODE"
echo "Public HTTP: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
  echo "SUCCESS: Command Center is live"
elif echo "$LOCAL_CODE" | grep -qE '^(200|301|302|307|404)$' && echo "$HTTP_CODE" | grep -qE '^(502|1033|1303|530|503)$'; then
  # The dashboard IS up locally on :4000 but the public URL fails at the edge.
  # This is the wrong-port / no-route signature: the tunnel's ingress for this
  # host was clobbered by a full-replace PUT from a sibling service sharing the
  # box's tunnel (gateway :18789 / podcast :4010) so it now points at the wrong
  # localhost port or has no rule at all. Fail LOUD — do NOT report a soft warning.
  echo "ERROR: TUNNEL INGRESS WRONG-PORT / NO-ROUTE detected." >&2
  echo "  The Command Center is UP locally (:${CC_INGRESS_PORT} returned $LOCAL_CODE) but the public link returns $HTTP_CODE." >&2
  echo "  Cause: this box's tunnel ingress for ${SUBDOMAIN} is not routing to http://localhost:${CC_INGRESS_PORT}" >&2
  echo "         (a full-replace ingress PUT from a sibling service on the shared tunnel dropped/repointed the CC rule)." >&2
  echo "  Operator repair: PUT the CC host back to http://localhost:${CC_INGRESS_PORT} via GET->merge->PUT" >&2
  echo "                   (see n8n-workflows/command-center-register-v4.md and shared-utils/cc-tunnel-ingress.sh)." >&2
  exit 7
else
  echo "WARNING: URL not live yet (local=$LOCAL_CODE public=$HTTP_CODE). Check: pm2 status cloudflare-tunnel" >&2
fi
