#!/usr/bin/env bash
# 13-create-cloudflare-tunnel.sh
# Step 1 — Create the Cloudflare tunnel via API (playbook v5.14 lines 923-993).
# Idempotent. Never echoes the connector token to stdout.
set -euo pipefail

API="https://api.cloudflare.com/client/v4"
SECRETS_ENV_FILE="${SECRETS_ENV_FILE:-$HOME/.openclaw/secrets.env}"
GATEWAY_PORT="${GATEWAY_PORT:-18789}"

# ---- Rule 13 token gate ------------------------------------------------------
if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  cat >&2 <<'ERR'
HARD STOP — Rule 13 (operator-supplied secret missing).

CLOUDFLARE_API_TOKEN is not set in the environment. The agent is forbidden
from inventing, guessing, or pulling this value from any other account.
The operator must paste the token they generated under their own Cloudflare
dashboard (https://dash.cloudflare.com/profile/api-tokens), per the
"agent suggests, operator decides" rule.

See references/fleet-onboarding-tunnel-provisioning-field-guide.md for the exact scopes the
token needs (Account: Cloudflare Tunnel:Edit, Zone: DNS:Edit on the parent
zone).

Resolution:
  1. Operator creates the token in their Cloudflare dashboard.
  2. Operator appends it to SECRETS_ENV_FILE.
  3. Re-run:  source "$SECRETS_ENV_FILE" && ./13-create-cloudflare-tunnel.sh
ERR
  exit 13
fi

# ---- Helpers -----------------------------------------------------------------
cf() { curl -sS -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" "$@"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing dep: $1" >&2; exit 1; }; }
need curl; need jq

append_secret() {
  local k="$1" v="$2"
  [[ -f "$SECRETS_ENV_FILE" ]] || { mkdir -p "$(dirname "$SECRETS_ENV_FILE")"; : > "$SECRETS_ENV_FILE"; chmod 600 "$SECRETS_ENV_FILE"; }
  if grep -qE "^${k}=" "$SECRETS_ENV_FILE" 2>/dev/null; then
    echo "  (kept existing ${k} in $SECRETS_ENV_FILE)" >&2
  else
    printf '%s=%s\n' "$k" "$v" >> "$SECRETS_ENV_FILE"
    echo "  saved ${k} → $SECRETS_ENV_FILE" >&2
  fi
}

# ---- Resolve required inputs -------------------------------------------------
ROUTE_ID="${ROUTE_ID:-${HOOK_NAME:-ghl-inbound}}"

if [[ -z "${PUBLIC_HOSTNAME:-}" ]]; then
  printf "PUBLIC_HOSTNAME (subdomain, e.g. claw.mydomain.com): " >&2
  read -r PUBLIC_HOSTNAME
fi
[[ "$PUBLIC_HOSTNAME" == *.*.* ]] || { echo "PUBLIC_HOSTNAME must be a subdomain (>= 2 dots). STOP." >&2; exit 2; }
PARENT_DOMAIN="${PUBLIC_HOSTNAME#*.}"

# ---- A. Resolve account id ---------------------------------------------------
if [[ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then
  ACCOUNT_ID="$(cf "$API/accounts" | jq -r '.result[0].id // empty')"
  [[ -n "$ACCOUNT_ID" ]] || { echo "no Cloudflare accounts visible to this token" >&2; exit 3; }
  CLOUDFLARE_ACCOUNT_ID="$ACCOUNT_ID"
fi
echo "ACCOUNT_ID=$CLOUDFLARE_ACCOUNT_ID" >&2

# ---- B. Resolve zone id ------------------------------------------------------
ZONE_ID="$(cf "$API/zones?name=$PARENT_DOMAIN" | jq -r '.result[0].id // empty')"
[[ -n "$ZONE_ID" ]] || { echo "zone not found for $PARENT_DOMAIN (is the domain in this Cloudflare account?)" >&2; exit 4; }
echo "ZONE_ID=$ZONE_ID" >&2

# ---- C. Find-or-create tunnel (idempotent) -----------------------------------
TUNNEL_NAME="openclaw-${ROUTE_ID}"
TUNNEL_ID="$(cf "$API/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel?name=$TUNNEL_NAME&is_deleted=false" \
  | jq -r '.result[0].id // empty')"
if [[ -n "$TUNNEL_ID" ]]; then
  echo "reusing existing tunnel: $TUNNEL_NAME ($TUNNEL_ID)" >&2
else
  TUNNEL_ID="$(cf -X POST "$API/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel" \
    -H "Content-Type: application/json" \
    --data "{\"name\":\"$TUNNEL_NAME\",\"config_src\":\"cloudflare\"}" \
    | jq -r '.result.id // empty')"
  [[ -n "$TUNNEL_ID" ]] || { echo "tunnel creation failed" >&2; exit 5; }
  echo "created tunnel: $TUNNEL_NAME ($TUNNEL_ID)" >&2
fi

# ---- D. Fetch connector token (NEVER echoed to stdout) -----------------------
TUNNEL_TOKEN="$(cf "$API/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel/$TUNNEL_ID/token" | jq -r '.result // empty')"
[[ -n "$TUNNEL_TOKEN" ]] || { echo "could not fetch connector token" >&2; exit 6; }
echo "connector token retrieved (redacted; length=${#TUNNEL_TOKEN})" >&2

# ---- E. Set ingress (GET -> MERGE -> PUT; never a full-replace) ---------------
# ROOT-CAUSE FIX (wrong-port / CF 1303 on the Command Center): the fleet runs ONE
# tunnel per box carrying multiple ingress hostnames on a SINGLE ingress array
# (CC dashboard -> :4000, this gateway host -> :18789, podcast -> :4010). CF's PUT
# /configurations REPLACES the whole array. The previous full-replace here PUT
# only [{PUBLIC_HOSTNAME -> :18789}, {404}], which — whenever this box's gateway
# host shares the tunnel that also serves the Command Center — DELETED the CC's
# "<client>.zerohumanworkforce.com -> http://localhost:4000" rule. That produced
# CF 1303 (no route) for the CC link, or a 502 if a still-routed host got
# re-pointed at :18789. We now GET the current config and MERGE: keep every
# existing hostname rule, (re)write only OUR host, keep exactly one catch-all
# last. Then a fail-loud guard refuses to PUT any config that would leave a CC
# hostname on a non-:4000 port.
CUR_CFG="$(cf "$API/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel/$TUNNEL_ID/configurations")"
[ "$(printf '%s' "$CUR_CFG" | jq -r '.success // false')" = "true" ] \
  || { echo "could not read current tunnel ingress (GET /configurations failed)" >&2; exit 7; }

# Merge OUR host -> gateway port, preserving all sibling rules and a single 404 last.
PUT_BODY="$(printf '%s' "$CUR_CFG" | jq \
  --arg host "$PUBLIC_HOSTNAME" --arg svc "http://localhost:$GATEWAY_PORT" '
  (.result.config // .config // {}) as $cfg
  | ($cfg.ingress // []) as $ing
  | ($ing | map(select(has("hostname") and (.hostname != $host)))) as $hosts
  | {config: ($cfg | .ingress = (
        $hosts + [{hostname:$host, service:$svc}] + [{service:"http_status:404"}]
      ))}')"

# GUARD: never PUT a config in which a Command Center dashboard host points
# anywhere other than :4000. A CC dashboard host is a "<slug>.zerohumanworkforce.com"
# host that is NOT a known sibling service host (the gateway "…-hooks" on :18789 or
# the podcast "…-podcast" board on :4010) — slugs may themselves contain hyphens, so
# we identify CC hosts by EXCLUDING the sibling suffixes, not by a hyphen pattern.
# If the GET returned such a CC rule, the merge preserves it; if some prior clobber
# already broke it, we refuse to compound the damage and tell the operator to repair.
CC_PORT_EXPECTED="4000"
CC_DRIFT="$(printf '%s' "$PUT_BODY" | jq -r --arg p "$CC_PORT_EXPECTED" '
  (.config.ingress // [])
  | map(select(.hostname != null))
  | map(select(.hostname | endswith(".zerohumanworkforce.com")))
  | map(select(.hostname | (endswith("-hooks.zerohumanworkforce.com")
                            or endswith("-podcast.zerohumanworkforce.com")) | not))
  | map(select((.service // "") | test(":" + $p + "$") | not))
  | map(.hostname + " -> " + (.service // "")) | join("; ")')"
if [ -n "$CC_DRIFT" ]; then
  echo "CC-INGRESS-GUARD FAIL: refusing to PUT — a Command Center host would be on a non-:${CC_PORT_EXPECTED} port: $CC_DRIFT" >&2
  echo "  The CC public link would 502 / CF-1303. Repair the CC ingress (-> http://localhost:${CC_PORT_EXPECTED}) before re-running." >&2
  exit 7
fi

cf -X PUT "$API/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel/$TUNNEL_ID/configurations" \
  -H "Content-Type: application/json" \
  --data "$PUT_BODY" \
  | jq -r '.success' | grep -q true || { echo "ingress PUT failed" >&2; exit 7; }
echo "ingress configured (merged): $PUBLIC_HOSTNAME → http://localhost:$GATEWAY_PORT (sibling rules preserved)" >&2

# ---- F. CNAME with PROD-clobber guard ----------------------------------------
EXISTING="$(cf "$API/zones/$ZONE_ID/dns_records?name=$PUBLIC_HOSTNAME" | jq -r '.result[0] // empty')"
if [[ -n "$EXISTING" ]]; then
  EXISTING_CONTENT="$(printf '%s' "$EXISTING" | jq -r '.content')"
  EXPECTED="${TUNNEL_ID}.cfargotunnel.com"
  if [[ "$EXISTING_CONTENT" == "$EXPECTED" ]]; then
    echo "CNAME already correct ($PUBLIC_HOSTNAME → $EXPECTED)" >&2
  else
    echo "REFUSING to clobber existing record at $PUBLIC_HOSTNAME (content=$EXISTING_CONTENT)." >&2
    echo "Re-run with FORCE_CNAME=1 and operator confirmation if this is safe." >&2
    if [[ "${FORCE_CNAME:-0}" != "1" ]]; then exit 8; fi
    REC_ID="$(printf '%s' "$EXISTING" | jq -r '.id')"
    cf -X PUT "$API/zones/$ZONE_ID/dns_records/$REC_ID" \
      -H "Content-Type: application/json" \
      --data "{\"type\":\"CNAME\",\"name\":\"$PUBLIC_HOSTNAME\",\"content\":\"$EXPECTED\",\"proxied\":true}" \
      | jq -r '.success' | grep -q true || { echo "CNAME update failed" >&2; exit 9; }
  fi
else
  cf -X POST "$API/zones/$ZONE_ID/dns_records" \
    -H "Content-Type: application/json" \
    --data "{\"type\":\"CNAME\",\"name\":\"$PUBLIC_HOSTNAME\",\"content\":\"${TUNNEL_ID}.cfargotunnel.com\",\"proxied\":true}" \
    | jq -r '.success' | grep -q true || { echo "CNAME create failed" >&2; exit 10; }
  echo "CNAME created: $PUBLIC_HOSTNAME → ${TUNNEL_ID}.cfargotunnel.com (proxied)" >&2
fi

# ---- Persist secrets ---------------------------------------------------------
append_secret "CLOUDFLARE_TUNNEL_ID" "$TUNNEL_ID"
append_secret "CLOUDFLARE_TUNNEL_TOKEN" "$TUNNEL_TOKEN"
append_secret "CLOUDFLARE_ACCOUNT_ID" "$CLOUDFLARE_ACCOUNT_ID"
append_secret "CLOUDFLARE_ZONE_ID" "$ZONE_ID"
append_secret "PUBLIC_HOSTNAME" "$PUBLIC_HOSTNAME"
append_secret "ROUTE_ID" "$ROUTE_ID"

echo "OK: Cloudflare tunnel ready. Next: scripts/14-install-cloudflared-service.sh" >&2
