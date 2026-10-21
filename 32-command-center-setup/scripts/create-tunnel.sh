#!/bin/bash
# Phase 6b - Register Command Center and receive tunnel token in webhook response
# Usage: ./create-tunnel.sh <client-slug> <company-name> <contact-email>
# Exit codes (run-full-install.sh phase 6h maps them):
#   0  registered; 75 NOTHING was sent (prerequisite missing, n8n unreachable) —
#   retryable; 3 the webhook answered with a non-success body — terminal;
#   anything else: the request may have been sent — reconcile, never blind re-POST.

set -euo pipefail

CLIENT_SLUG="${1:?Usage: ./create-tunnel.sh <client-slug> <company-name> <contact-email>}"
COMPANY_NAME="${2:?Missing company name}"
CONTACT_EMAIL="${3:?Missing contact email}"
WEBHOOK_URL="https://main.blackceoautomations.com/webhook/command-center-register-v3"
# One home-path resolver: an explicit OPENCLAW_ROOT/OC_ROOT pin wins, else
# shared-utils/resolve-oc-root.sh decides (/data/.openclaw on VPS/Docker,
# $HOME/.openclaw on Mac) -- never a second inline copy of the rule.
_OC_RESOLVER="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../shared-utils" 2>/dev/null && pwd)/resolve-oc-root.sh"
if [[ -n "${OPENCLAW_ROOT:-${OC_ROOT:-}}" && -d "${OPENCLAW_ROOT:-${OC_ROOT:-}}" ]]; then
  OC_ROOT="${OPENCLAW_ROOT:-${OC_ROOT:-}}"
elif [[ -f "$_OC_RESOLVER" ]]; then
  # shellcheck source=/dev/null
  source "$_OC_RESOLVER"
  OC_ROOT="$(resolve_oc_root 2>/dev/null || true)"
  [[ -n "$OC_ROOT" ]] || OC_ROOT="${OPENCLAW_ROOT:-$HOME/.openclaw}"
else
  OC_ROOT="${OPENCLAW_ROOT:-$HOME/.openclaw}"
fi

: "${CC_TUNNEL_IDEMPOTENCY_KEY:?invoke through run-full-install.sh for a persistent installation-scoped request key}"
: "${CC_TUNNEL_EXPECTED_HOST:?invoke through run-full-install.sh for the registered client hostname}"

for _req in python3 curl; do
  command -v "$_req" >/dev/null 2>&1 || { echo "ERROR: $_req not found — nothing was sent; retry once it is installed" >&2; exit 75; }
done
# A non-root box (Docker as node) cannot write /usr/local/bin: install into the
# user-local bin and put it on PATH. Every failure here is pre-POST and retryable.
[[ -d "$HOME/.local/bin" ]] && PATH="$HOME/.local/bin:$PATH"
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found. Installing..."
  if command -v brew >/dev/null 2>&1; then
    brew install cloudflared || true
  else
    case "$(uname -m)" in aarch64|arm64) _cf_arch=arm64 ;; *) _cf_arch=amd64 ;; esac
    _cf_dir="${CLOUDFLARED_INSTALL_DIR:-/usr/local/bin}"
    [[ -w "$_cf_dir" ]] || { _cf_dir="$HOME/.local/bin"; mkdir -p "$_cf_dir" && PATH="$_cf_dir:$PATH"; }
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${_cf_arch}" -o "$_cf_dir/cloudflared.tmp" \
      && chmod +x "$_cf_dir/cloudflared.tmp" && mv "$_cf_dir/cloudflared.tmp" "$_cf_dir/cloudflared" \
      || rm -f "$_cf_dir/cloudflared.tmp"
  fi
fi
CLOUDFLARED_BIN="$(command -v cloudflared || true)"
if [[ -z "$CLOUDFLARED_BIN" ]]; then
  echo "ERROR: cloudflared is not installed and could not be installed — nothing was sent; retry" >&2
  exit 75
fi

echo "[1/5] Requesting tunnel from the operator's system..."
# Build the JSON body with python3 so embedded quotes/spaces/special chars in
# the company name or email are escaped correctly. The previous inline
# double-quoted heredoc-style body (-d "{"clientName":...}") collapsed the
# inner quotes under shell parsing and sent an empty/invalid body, which the
# non-idempotent webhook treated as a brand-new registration on every retry.
REQUEST_BODY=$(CLIENT_SLUG="$CLIENT_SLUG" COMPANY_NAME="$COMPANY_NAME" CONTACT_EMAIL="$CONTACT_EMAIL" \
  python3 -c 'import json,os; print(json.dumps({"clientName":os.environ["CLIENT_SLUG"],"companyName":os.environ["COMPANY_NAME"],"contactEmail":os.environ["CONTACT_EMAIL"]}))')
# A transport failure may occur after acceptance. Make exactly one request;
# persisted request state and authenticated readiness reconcile an ambiguous
# outcome before any further external creation. The server may use the stable
# idempotency key, but safety does not assume that it implements deduplication.
# The last output line is curl's own "<http code> <request-body bytes uploaded>".
# Nothing reached n8n when the transfer failed with 0 bytes uploaded (DNS,
# refused, connect timeout), or when the proxy answered with an origin-down
# page (502/503/52x/530, not a JSON body). Both are retryable (exit 75).
_attempt=1
_curl_rc=0
_out=$(curl -sS -m 30 --connect-timeout 15 -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: ${CC_TUNNEL_IDEMPOTENCY_KEY:?missing installation-scoped request key}" \
  -w '\n%{http_code} %{size_upload}' -d "$REQUEST_BODY" 2>/dev/null) || _curl_rc=$?
_meta=""; RESPONSE="$_out"
if [[ "$_out" == *$'\n'* ]]; then _meta="${_out##*$'\n'}"; RESPONSE="${_out%$'\n'*}"; fi
_http="${_meta%% *}"; _uploaded="${_meta##* }"
if [[ "$_curl_rc" -ne 0 ]] && [[ "$_curl_rc" =~ ^(6|7)$ || "$_uploaded" == "0" ]]; then
  echo "ERROR: tunnel registration webhook unreachable (curl exit $_curl_rc) — nothing was sent; retry is safe" >&2
  exit 75
fi
if [[ "$_curl_rc" -eq 0 && "$_http" =~ ^(502|503|521|522|523|530)$ ]] \
   && ! printf '%s' "$RESPONSE" | python3 -c 'import json,sys; json.load(sys.stdin)' >/dev/null 2>&1; then
  echo "ERROR: tunnel registration webhook origin is down (HTTP $_http) — not processed; retry is safe" >&2
  exit 75
fi
if [[ "$_curl_rc" -ne 0 || -z "$RESPONSE" ]]; then
  echo "ERROR: tunnel registration webhook unreachable after ${_attempt} attempt(s) (no response)" >&2
  echo "ESCALATE: message the operator with this client slug ($CLIENT_SLUG) and note the webhook" >&2
  echo "  at $WEBHOOK_URL did not respond. Do NOT attempt to create a Cloudflare tunnel any other" >&2
  echo "  way — do NOT run 'cloudflared tunnel login', do NOT create a Cloudflare account. The" >&2
  echo "  tunnel can only be issued by the operator's n8n system; reconcile the original request before any retry; wait for the operator to confirm" >&2
  echo "  the webhook is back up, then re-run this script." >&2
  exit 1
fi

STATUS=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
if [ "$STATUS" != "success" ]; then
  echo "ERROR: webhook failed" >&2
  echo "Registration returned a non-success status; response body withheld because it may contain credentials." >&2
  echo "ESCALATE: message the operator with this client slug ($CLIENT_SLUG) and the response body" >&2
  echo "  above. Do NOT attempt to create a Cloudflare tunnel any other way — do NOT run" >&2
  echo "  'cloudflared tunnel login', do NOT create a Cloudflare account." >&2
  exit 3
fi

TUNNEL_TOKEN=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnelToken'])")
SUBDOMAIN=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['subdomain'])")
if [[ -z "$TUNNEL_TOKEN" || "$SUBDOMAIN" != "$CC_TUNNEL_EXPECTED_HOST" ]]; then
  echo "ERROR: registration response does not match the requested client host; reconcile request before retry" >&2
  exit 3
fi

echo "[2/5] Saving client tunnel token to the selected installation secret files"
mkdir -p "$OC_ROOT"
# Legacy token location; never used as proof of a public origin
TMP_ENV=$(mktemp)
grep -v '^CLOUDFLARE_TUNNEL_TOKEN=' "$OC_ROOT"/.env 2>/dev/null > "$TMP_ENV" || true
echo "CLOUDFLARE_TUNNEL_TOKEN=$TUNNEL_TOKEN" >> "$TMP_ENV"
mv "$TMP_ENV" "$OC_ROOT"/.env
# Canonical secrets location (QC.md + qc-command-center-setup.sh read this one)
mkdir -p "$OC_ROOT"/secrets
TMP_SECRETS=$(mktemp)
grep -v '^CLOUDFLARE_TUNNEL_TOKEN=' "$OC_ROOT"/secrets/.env 2>/dev/null > "$TMP_SECRETS" || true
echo "CLOUDFLARE_TUNNEL_TOKEN=$TUNNEL_TOKEN" >> "$TMP_SECRETS"
mv "$TMP_SECRETS" "$OC_ROOT"/secrets/.env
chmod 600 "$OC_ROOT"/secrets/.env

echo "[3/5] Starting tunnel via PM2"
# The connector token is a bearer credential: never on argv (visible in ps).
# cloudflared reads it from a mode-600 file via --token-file (same flag the
# Mac tunnel daemon already uses); --token-file also takes precedence over a
# stale TUNNEL_TOKEN in the environment.
TOKEN_FILE="$OC_ROOT/secrets/tunnel-command-center.token"
( umask 077; mkdir -p "$(dirname "$TOKEN_FILE")" )
printf '%s' "$TUNNEL_TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"
TUNNEL_TOKEN=""
pm2 delete cloudflare-tunnel >/dev/null 2>&1 || true
pm2 start "$CLOUDFLARED_BIN tunnel run --token-file $TOKEN_FILE" --name cloudflare-tunnel >/dev/null
pm2 save >/dev/null

echo "[4/5] Waiting for tunnel to come online..."
sleep 15
# CC dashboard's authoritative local port. Single source of truth:
# shared-utils/cc-tunnel-ingress.sh (CC_INGRESS_PORT) and run-full-install.sh
# (DASHBOARD_PORT=4000). tests/unit/cc-tunnel-ingress-guard.test.sh asserts this
# literal stays equal to the lib's CC_INGRESS_PORT so the two can never drift.
# shellcheck source=/dev/null
if [[ -f "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../shared-utils" 2>/dev/null && pwd)/cc-tunnel-ingress.sh" ]]; then
  source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../shared-utils" 2>/dev/null && pwd)/cc-tunnel-ingress.sh"
fi
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
