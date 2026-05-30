#!/usr/bin/env bash
# 26-verify-pixel-prerequisites.sh — ZHC Pixel (Feature 49) scope precheck.
#
# Inspects the operator's Cloudflare API token via the API and HALTS with a clear
# message if the scopes the per-client pixel DEPLOY needs are missing:
#
#   • Pages:Edit            (host the rendered pixel JS on a CF Pages project)
#   • Workers Scripts:Edit  (optional edge batching / rate-limit Worker)
#   • Workers Routes:Edit   (bind the Worker to pixel.<CLIENT_DOMAIN>/*)
#
# These are the SAME scopes Feature 52 needs. On a missing scope the precheck points
# the operator to the token-instructions Google Doc's "Cloudflare Pages/Workers
# permissions" section:
#   https://docs.google.com/document/d/1A_U-H-MMLh2mQ_zhzLxK_tKmFyPNb7i0FNvxjJ4SVpo/edit
#
# It also confirms the deploy's OTHER prerequisites: an existing tunnel (Step 1) and an
# identified domain. DO NOT attempt a live per-client deploy without scopes — the code
# ships, the deploy is GATED (owner directive).
#
# On full pass it records ZHC_PIXEL_SCOPES_OK=1 in the run-state so
# 29-deploy-pixel-cloudflare.sh will proceed.
#
# UNIVERSAL. BASH only. Never echoes the CF token.
# Exit codes: 0 = all prerequisites present (deploy may proceed);
#             10 = CF token missing; 11 = token invalid;
#             12 = one or more required scopes missing;
#             13 = no existing tunnel; 14 = no domain identified.
set -uo pipefail

API="https://api.cloudflare.com/client/v4"
TOKEN_DOC="https://docs.google.com/document/d/1A_U-H-MMLh2mQ_zhzLxK_tKmFyPNb7i0FNvxjJ4SVpo/edit"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# -------- Master files dir + run-state --------
MASTER_FILES_POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
if [ -z "${MASTER_FILES_DIR:-}" ] && [ -f "$MASTER_FILES_POINTER" ]; then
  MASTER_FILES_DIR="$(head -n1 "$MASTER_FILES_POINTER")"
fi
SECRETS_ENV_FILE="${SECRETS_ENV_FILE:-$HOME/.openclaw/secrets.env}"
[ -f "$SECRETS_ENV_FILE" ] && { set -a; . "$SECRETS_ENV_FILE"; set +a; } || true
RUN_STATE="${RUN_STATE_FILE:-${MASTER_FILES_DIR:-$HOME/.openclaw}/.skill38-run-state.env}"
[ -f "$RUN_STATE" ] && { set -a; . "$RUN_STATE"; set +a; } || true

upsert_state() {
  local k="$1" v="$2"
  [ -f "$RUN_STATE" ] || : > "$RUN_STATE"
  if grep -qE "^${k}=" "$RUN_STATE" 2>/dev/null; then
    local tmp; tmp="$(mktemp)"; grep -vE "^${k}=" "$RUN_STATE" > "$tmp"; mv "$tmp" "$RUN_STATE"
  fi
  printf '%s=%s\n' "$k" "$v" >> "$RUN_STATE"
}

PASS=0; FAIL=0
ok()  { echo "  [PASS] $*"; PASS=$((PASS+1)); }
bad() { echo "  [FAIL] $*"; FAIL=$((FAIL+1)); }

echo "=== ZHC Pixel (F49) prerequisite precheck ==="

# -------- 1. CF token present --------
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
  cat >&2 <<ERR

HARD STOP — CLOUDFLARE_API_TOKEN is not set.
The ZHC Pixel deploy needs the operator's own Cloudflare API token (it is the SAME
token that built the tunnel in Step 1, but it must ALSO carry Pages/Workers scopes).
Add it to $SECRETS_ENV_FILE and re-run. See the token-instructions doc:
  $TOKEN_DOC
ERR
  exit 10
fi
command -v curl >/dev/null 2>&1 || { echo "missing dep: curl" >&2; exit 1; }
command -v jq   >/dev/null 2>&1 || { echo "missing dep: jq"   >&2; exit 1; }

cf() { curl -sS -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" "$@"; }

# -------- 2. Token valid --------
VERIFY="$(cf "$API/user/tokens/verify" || true)"
if [ "$(printf '%s' "$VERIFY" | jq -r '.success // false')" != "true" ]; then
  echo "" >&2
  echo "HARD STOP — the Cloudflare token did not verify (GET /user/tokens/verify)." >&2
  printf '%s\n' "$VERIFY" | jq -r '.errors // []' >&2 2>/dev/null || true
  echo "Re-create the token per: $TOKEN_DOC" >&2
  exit 11
fi
ok "CF token verifies"

# -------- 3. Required scopes present --------
# We probe the EFFECTIVE permission by hitting a representative endpoint for each
# scope. A 200/expected JSON = scope present; a 403/authentication error = missing.
# (Reading the token's own permission-group list is unreliable across token types;
# probing the actual capability is the ground-truth check.)
ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-}"
if [ -z "$ACCOUNT_ID" ]; then
  ACCOUNT_ID="$(cf "$API/accounts" | jq -r '.result[0].id // empty')"
fi
if [ -z "$ACCOUNT_ID" ]; then
  bad "could not resolve a Cloudflare account id from this token"
else
  ok "account id resolved"
fi

probe_scope() {
  # $1 = human name, $2 = API path (GET), records into missing list on 403/!success
  local name="$1" path="$2"
  local resp code
  resp="$(cf -o /dev/null -w '%{http_code}' "$API$path" 2>/dev/null || echo 000)"
  code="$resp"
  case "$code" in
    200|404) ok "scope present: $name (probe $path -> HTTP $code)"; return 0 ;;
    403)     bad "scope MISSING: $name (probe $path -> HTTP 403 forbidden)"; return 1 ;;
    *)       bad "scope INDETERMINATE: $name (probe $path -> HTTP $code) — treat as missing"; return 1 ;;
  esac
}

MISSING_SCOPES=()
if [ -n "$ACCOUNT_ID" ]; then
  # Pages:Edit — listing the account's Pages projects requires Pages read/edit.
  probe_scope "Pages:Edit"           "/accounts/$ACCOUNT_ID/pages/projects?per_page=1"  || MISSING_SCOPES+=("Pages:Edit")
  # Workers Scripts:Edit — listing Worker scripts requires Workers Scripts read/edit.
  probe_scope "Workers Scripts:Edit" "/accounts/$ACCOUNT_ID/workers/scripts?per_page=1" || MISSING_SCOPES+=("Workers Scripts:Edit")
fi
# Workers Routes:Edit is ZONE-scoped. Probe via the zone if we can resolve it.
ZONE_ID="${CLOUDFLARE_ZONE_ID:-}"
if [ -z "$ZONE_ID" ] && [ -n "${CLIENT_DOMAIN:-}" ]; then
  ZONE_ID="$(cf "$API/zones?name=${CLIENT_DOMAIN}" | jq -r '.result[0].id // empty')"
fi
if [ -n "$ZONE_ID" ]; then
  probe_scope "Workers Routes:Edit" "/zones/$ZONE_ID/workers/routes" || MISSING_SCOPES+=("Workers Routes:Edit")
else
  echo "  [WARN] no zone id (set CLOUDFLARE_ZONE_ID or CLIENT_DOMAIN) — cannot probe Workers Routes:Edit; the deploy will re-check at run time" >&2
fi

# -------- 4. Existing tunnel (Step 1) --------
if [ -n "${CLOUDFLARE_TUNNEL_ID:-}" ]; then
  ok "existing tunnel detected (CLOUDFLARE_TUNNEL_ID set)"
else
  bad "no existing tunnel — run scripts/13-create-cloudflare-tunnel.sh first (the pixel rides the client's EXISTING tunnel)"
  TUNNEL_MISSING=1
fi

# -------- 5. Domain identified --------
if [ -n "${CLIENT_DOMAIN:-}" ] || [ -n "${ZHC_PIXEL_HOSTNAME:-}" ] || [ -n "${PIXEL_HOSTNAME:-}" ]; then
  ok "domain identified (CLIENT_DOMAIN / PIXEL_HOSTNAME present)"
else
  bad "no domain identified — set CLIENT_DOMAIN=<CLIENT_DOMAIN> (the pixel host will be pixel.<CLIENT_DOMAIN>)"
  DOMAIN_MISSING=1
fi

echo ""
echo "=== precheck summary: PASS=$PASS FAIL=$FAIL ==="

# -------- Decide --------
if [ "${#MISSING_SCOPES[@]}" -gt 0 ]; then
  cat >&2 <<ERR

HARD STOP — the Cloudflare token is MISSING required scope(s) for the ZHC Pixel deploy:
  ${MISSING_SCOPES[*]}

These are the SAME scopes Feature 52 needs. Add them to the token (or re-create it):
  Account -> Cloudflare Pages          -> Edit
  Account -> Workers Scripts           -> Edit
  Zone    -> Workers Routes            -> Edit

Step-by-step (incl. the "Cloudflare Pages/Workers permissions" section):
  $TOKEN_DOC

The pixel CODE is installed and the JS can still be rendered (27-render-pixel-js.sh) and
the hook configured (28-configure-pixel-hook.sh). Only the live Cloudflare DEPLOY
(29-deploy-pixel-cloudflare.sh) is gated until the scopes are present. NOTHING fails
silently.
ERR
  upsert_state "ZHC_PIXEL_SCOPES_OK" "0"
  exit 12
fi

if [ "${TUNNEL_MISSING:-0}" = "1" ]; then upsert_state "ZHC_PIXEL_SCOPES_OK" "0"; exit 13; fi
if [ "${DOMAIN_MISSING:-0}" = "1" ]; then upsert_state "ZHC_PIXEL_SCOPES_OK" "0"; exit 14; fi

if [ "$FAIL" -eq 0 ]; then
  upsert_state "ZHC_PIXEL_SCOPES_OK" "1"
  echo "RESULT: PASS — all prerequisites present. 29-deploy-pixel-cloudflare.sh may proceed." >&2
  exit 0
else
  upsert_state "ZHC_PIXEL_SCOPES_OK" "0"
  echo "RESULT: FAIL — $FAIL prerequisite(s) missing (see above). Deploy is GATED." >&2
  exit 12
fi
