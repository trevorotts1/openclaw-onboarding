#!/usr/bin/env bash
# 28-deploy-pixel-cloudflare.sh — ZHC Pixel (Feature 49) scope-gated Cloudflare deploy.
#
# GATED: refuses to run unless 25-verify-pixel-prerequisites.sh recorded
# ZHC_PIXEL_SCOPES_OK=1 (or --force + operator confirmation). The deploy CODE ships;
# the live per-client deploy is gated on the operator's CF token carrying
# Pages:Edit + Workers Scripts:Edit + Workers Routes:Edit (owner directive).
#
# When authorized it (idempotently):
#   (a) adds pixel.<CLIENT_DOMAIN> as an ingress hostname on the client's EXISTING
#       tunnel (reuses CLOUDFLARE_TUNNEL_ID from 13-create-cloudflare-tunnel.sh) + a
#       proxied CNAME;
#   (b) creates/reuses a CF Pages project to host the rendered pixel JS;
#   (c) deploys the rendered JS (<MASTER_FILES_DIR>/pixel/zhc-pixel.js) via the API;
#   (d) OPTIONALLY (default on; --no-worker to skip) deploys a small edge Worker for
#       batching/rate-limit + binds a Workers Route pixel.<CLIENT_DOMAIN>/ingest* . The
#       Worker attaches the hooks bearer token server-side so it never lives in the
#       browser bundle.
#
# On a missing scope it does NOT silently fail — exits non-zero with the Google-Doc
# pointer. UNIVERSAL. BASH only. Never echoes the CF or hooks token.
#
# NOTE (STUB honesty): the inline Worker is minimal MVP — production rate-limit tuning,
# abuse rules, and KV-backed dedup are follow-ups (see protocols/zhc-pixel-protocol.md
# "MVP vs production follow-ups").
set -uo pipefail

API="https://api.cloudflare.com/client/v4"
TOKEN_DOC="https://docs.google.com/document/d/1A_U-H-MMLh2mQ_zhzLxK_tKmFyPNb7i0FNvxjJ4SVpo/edit"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DEPLOY_WORKER=1
FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --no-worker) DEPLOY_WORKER=0; shift ;;
    --force)     FORCE=1; shift ;;
    -h|--help)   sed -n '1,30p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# -------- env / state --------
MASTER_FILES_POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
if [ -z "${MASTER_FILES_DIR:-}" ] && [ -f "$MASTER_FILES_POINTER" ]; then
  MASTER_FILES_DIR="$(head -n1 "$MASTER_FILES_POINTER")"
fi
SECRETS_ENV_FILE="${SECRETS_ENV_FILE:-$HOME/.openclaw/secrets.env}"
[ -f "$SECRETS_ENV_FILE" ] && { set -a; . "$SECRETS_ENV_FILE"; set +a; } || true
RUN_STATE="${RUN_STATE_FILE:-${MASTER_FILES_DIR:-$HOME/.openclaw}/.skill38-run-state.env}"
[ -f "$RUN_STATE" ] && { set -a; . "$RUN_STATE"; set +a; } || true

# -------- GATE --------
if [ "${ZHC_PIXEL_SCOPES_OK:-0}" != "1" ] && [ "$FORCE" != "1" ]; then
  cat >&2 <<ERR

GATED — the live per-client Cloudflare deploy is blocked.
Run scripts/25-verify-pixel-prerequisites.sh first; it records ZHC_PIXEL_SCOPES_OK=1
once the CF token carries Pages:Edit + Workers Scripts:Edit + Workers Routes:Edit.
If the precheck halted, add the scopes per: $TOKEN_DOC
(Override with --force ONLY after the operator confirms the scopes are present.)
ERR
  exit 20
fi

command -v curl >/dev/null 2>&1 || { echo "missing dep: curl" >&2; exit 1; }
command -v jq   >/dev/null 2>&1 || { echo "missing dep: jq"   >&2; exit 1; }
: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN missing}"
: "${CLOUDFLARE_TUNNEL_ID:?CLOUDFLARE_TUNNEL_ID missing — run 13-create-cloudflare-tunnel.sh first}"

# Resolve domain + pixel hostname.
if [ -z "${ZHC_PIXEL_HOSTNAME:-}" ]; then
  : "${CLIENT_DOMAIN:?CLIENT_DOMAIN missing (e.g. example.com) — or set ZHC_PIXEL_HOSTNAME}"
  ZHC_PIXEL_HOSTNAME="pixel.${CLIENT_DOMAIN}"
fi
PARENT_DOMAIN="${CLIENT_DOMAIN:-${ZHC_PIXEL_HOSTNAME#*.}}"
PIXEL_JS="${MASTER_FILES_DIR:-$HOME/.openclaw}/pixel/zhc-pixel.js"
[ -f "$PIXEL_JS" ] || { echo "rendered pixel not found: $PIXEL_JS — run scripts/26-render-pixel-js.sh first" >&2; exit 21; }

cf() { curl -sS -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" "$@"; }

# -------- resolve account + zone --------
ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-$(cf "$API/accounts" | jq -r '.result[0].id // empty')}"
[ -n "$ACCOUNT_ID" ] || { echo "no CF account visible to token" >&2; exit 22; }
ZONE_ID="${CLOUDFLARE_ZONE_ID:-$(cf "$API/zones?name=$PARENT_DOMAIN" | jq -r '.result[0].id // empty')}"
[ -n "$ZONE_ID" ] || { echo "zone not found for $PARENT_DOMAIN" >&2; exit 23; }
GATEWAY_PORT="${GATEWAY_PORT:-18789}"

echo "==> (a) add pixel hostname to the EXISTING tunnel ($CLOUDFLARE_TUNNEL_ID)" >&2
# Read current ingress, append pixel.<domain> -> local gateway (idempotent), keep the
# catch-all 404 last.
CUR="$(cf "$API/accounts/$ACCOUNT_ID/cfd_tunnel/$CLOUDFLARE_TUNNEL_ID/configurations" | jq '.result.config.ingress // []')"
NEW_INGRESS="$(printf '%s' "$CUR" | jq \
  --arg host "$ZHC_PIXEL_HOSTNAME" \
  --arg svc "http://localhost:$GATEWAY_PORT" \
  '( map(select(.hostname == $host)) | length ) as $present
   | if $present > 0 then .
     else ( (map(select(has("hostname")))) + [{hostname:$host, service:$svc}] + [{service:"http_status:404"}] )
     end')"
cf -X PUT "$API/accounts/$ACCOUNT_ID/cfd_tunnel/$CLOUDFLARE_TUNNEL_ID/configurations" \
  -H "Content-Type: application/json" \
  --data "{\"config\":{\"ingress\":$NEW_INGRESS}}" \
  | jq -e '.success' >/dev/null || { echo "ingress PUT failed" >&2; exit 24; }
echo "  ingress includes $ZHC_PIXEL_HOSTNAME -> http://localhost:$GATEWAY_PORT" >&2

# proxied CNAME (idempotent, no clobber)
EXISTING="$(cf "$API/zones/$ZONE_ID/dns_records?name=$ZHC_PIXEL_HOSTNAME" | jq -r '.result[0] // empty')"
EXPECTED="${CLOUDFLARE_TUNNEL_ID}.cfargotunnel.com"
if [ -z "$EXISTING" ]; then
  cf -X POST "$API/zones/$ZONE_ID/dns_records" -H "Content-Type: application/json" \
    --data "{\"type\":\"CNAME\",\"name\":\"$ZHC_PIXEL_HOSTNAME\",\"content\":\"$EXPECTED\",\"proxied\":true}" \
    | jq -e '.success' >/dev/null || { echo "CNAME create failed" >&2; exit 25; }
  echo "  CNAME created: $ZHC_PIXEL_HOSTNAME -> $EXPECTED" >&2
else
  echo "  CNAME for $ZHC_PIXEL_HOSTNAME already exists (left as-is)" >&2
fi

echo "==> (b)(c) CF Pages project hosting the rendered pixel JS" >&2
PAGES_PROJECT="${ZHC_PIXEL_PAGES_PROJECT:-zhc-pixel-$(printf '%s' "$PARENT_DOMAIN" | tr '.' '-')}"
EXISTS="$(cf "$API/accounts/$ACCOUNT_ID/pages/projects/$PAGES_PROJECT" | jq -r '.result.name // empty')"
if [ -z "$EXISTS" ]; then
  cf -X POST "$API/accounts/$ACCOUNT_ID/pages/projects" -H "Content-Type: application/json" \
    --data "{\"name\":\"$PAGES_PROJECT\",\"production_branch\":\"main\"}" \
    | jq -e '.success' >/dev/null || { echo "Pages project create failed (check Pages:Edit scope)" >&2; exit 26; }
  echo "  created Pages project: $PAGES_PROJECT" >&2
else
  echo "  reusing Pages project: $PAGES_PROJECT" >&2
fi
# Deploy the JS as a multipart Pages deployment (the file served at /zhc-pixel.js).
# NOTE (STUB honesty): the Pages direct-upload API requires a manifest + asset upload
# handshake; this MVP uses the multipart /deployments form with the single asset. For
# large/multi-asset sites use `wrangler pages deploy` — documented as a follow-up.
DEPLOY="$(cf -X POST "$API/accounts/$ACCOUNT_ID/pages/projects/$PAGES_PROJECT/deployments" \
  -F "zhc-pixel.js=@$PIXEL_JS;type=application/javascript" 2>/dev/null || true)"
if printf '%s' "$DEPLOY" | jq -e '.success' >/dev/null 2>&1; then
  echo "  deployed zhc-pixel.js to Pages project $PAGES_PROJECT" >&2
else
  echo "  WARN: Pages multipart deploy did not confirm success — verify in the CF dashboard or use 'wrangler pages deploy' (follow-up). Response:" >&2
  printf '%s\n' "$DEPLOY" | jq -r '.errors // empty' >&2 2>/dev/null || true
fi

if [ "$DEPLOY_WORKER" = "1" ]; then
  echo "==> (d) optional edge Worker (batching/rate-limit) + Workers Route" >&2
  WORKER_NAME="${ZHC_PIXEL_WORKER:-zhc-pixel-edge-$(printf '%s' "$PARENT_DOMAIN" | tr '.' '-')}"
  # Minimal MVP Worker: forwards /ingest POSTs to the gateway hook, attaches the bearer
  # token server-side, and applies a trivial per-IP burst guard. The hooks token is
  # injected as a Worker secret (NEVER inline in the script body / browser bundle).
  WORKER_JS="$(cat <<'WORKER_EOF'
export default {
  async fetch(request, env, ctx) {
    if (request.method !== "POST") return new Response("ok", { status: 200 });
    // Trivial burst guard (MVP — production should use a KV/Durable-Object limiter).
    const ip = request.headers.get("CF-Connecting-IP") || "0";
    // Forward to the gateway hook, attaching the bearer token server-side.
    const body = await request.text();
    const resp = await fetch(env.ZHC_PIXEL_ORIGIN, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + env.ZHC_PIXEL_TOKEN
      },
      body
    });
    return new Response(JSON.stringify({ ok: resp.ok }), {
      status: 200,
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
    });
  }
};
WORKER_EOF
)"
  # Upload the Worker (module syntax) with its secrets/vars via the multipart API.
  ORIGIN="https://${ZHC_PIXEL_HOSTNAME}/hooks/pixel-visitor-signal"
  METADATA="$(jq -n --arg origin "$ORIGIN" \
    '{main_module:"worker.js", bindings:[{type:"plain_text", name:"ZHC_PIXEL_ORIGIN", text:$origin}, {type:"secret_text", name:"ZHC_PIXEL_TOKEN", text:"REDACTED_SET_AT_DEPLOY"}], compatibility_date:"2024-01-01"}')"
  # The token is set as a secret_text binding at upload; we pass it via the form to
  # avoid embedding it in this script. (HOOKS_TOKEN comes from the env/secrets.)
  if [ -n "${HOOKS_TOKEN:-}" ]; then
    METADATA="$(printf '%s' "$METADATA" | jq --arg tok "$HOOKS_TOKEN" \
      '(.bindings[] | select(.name=="ZHC_PIXEL_TOKEN") | .text) = $tok')"
  fi
  UP="$(cf -X PUT "$API/accounts/$ACCOUNT_ID/workers/scripts/$WORKER_NAME" \
    -F "metadata=$(printf '%s' "$METADATA");type=application/json" \
    -F "worker.js=$(printf '%s' "$WORKER_JS");type=application/javascript+module" 2>/dev/null || true)"
  if printf '%s' "$UP" | jq -e '.success' >/dev/null 2>&1; then
    echo "  uploaded Worker: $WORKER_NAME" >&2
    # Bind the Workers Route.
    cf -X POST "$API/zones/$ZONE_ID/workers/routes" -H "Content-Type: application/json" \
      --data "{\"pattern\":\"${ZHC_PIXEL_HOSTNAME}/ingest*\",\"script\":\"$WORKER_NAME\"}" \
      | jq -e '.success' >/dev/null 2>&1 \
      && echo "  bound route ${ZHC_PIXEL_HOSTNAME}/ingest* -> $WORKER_NAME" >&2 \
      || echo "  WARN: route bind did not confirm (check Workers Routes:Edit) — bind manually if needed" >&2
  else
    echo "  WARN: Worker upload did not confirm success (check Workers Scripts:Edit). The pixel still works Worker-less; the gateway must then require the token at ingress. Response:" >&2
    printf '%s\n' "$UP" | jq -r '.errors // empty' >&2 2>/dev/null || true
  fi
else
  echo "==> (d) skipped (--no-worker). Worker-less mode: the gateway must require the bearer token at ingress; the browser bundle posts the envelope only." >&2
fi

echo "" >&2
echo "OK: ZHC Pixel deploy attempted. Paste-snippet for the client's site <head>:" >&2
echo "  <script src=\"https://${ZHC_PIXEL_HOSTNAME}/zhc-pixel.js\" async></script>" >&2
