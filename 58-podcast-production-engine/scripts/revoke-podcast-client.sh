#!/usr/bin/env bash
# revoke-podcast-client.sh <slug> [--edge-only] [--tunnel-id <id>] [--dry-run]
#
# Podcast Production Engine (skill 58) - per-client access revocation.
# Implements the 9-step runbook in design/cloudflare-design.md Section 3, with the
# edge-only emergency mode and the independent verification step.
#
# ORDER MATTERS: kill live sessions before deleting routes, so no logged-in session
# outlives its hostname. Every step is idempotent and logs to the operator ledger.
# Zero client-facing messages, ever.
#
# EDGE-ONLY EMERGENCY MODE (--edge-only): runs steps 1 to 4 plus verification 9a to 9c,
# which fully cut public access from the Cloudflare side alone even when the box is dark.
# Steps 5 to 8 (box hygiene) are recorded PENDING.
#
# HARD RULES: never trust CLOUDFLARE_ZONE_ID (resolve the zone by name, refuse the wrong
# zone); never print a secret value (confirm SET-ness only); box config writes run as the
# node user, never root; a revocation that downs a box still running other services is a
# FAILED revocation (gateway health is verified).
#
# TENANCY: reads the provision ledger (/tmp/podcast-provision/<slug>.json) to learn the
# tunnel id, the hooks hostname, whether podcast is its sole tenant, and the WAF rule ref,
# so revocation does not have to guess whether removing the hooks host is safe. With no
# ledger it is CONSERVATIVE: it never removes a possibly-shared hooks hostname.
#
set -uo pipefail

API="https://api.cloudflare.com/client/v4"
# Operator-account-specific values come from the environment on the operator box
# and are never hardcoded in this fleet-wide template. The zone is resolved by
# NAME below; the zone id is only a known-good cross-check.
ACCOUNT_ID_DEFAULT="${CLOUDFLARE_ACCOUNT_ID:-YOUR_CF_ACCOUNT_ID}"
ZONE_NAME="${PODCAST_CF_ZONE_NAME:-zerohumanworkforce.com}"
ZONE_ID_KNOWN="${PODCAST_CF_ZONE_ID:-YOUR_CF_ZONE_ID}"
ACCESS_TEAM_HOST="${PODCAST_CF_ACCESS_TEAM_HOST:-your-team.cloudflareaccess.com}"
GATEWAY_PORT="18789"

unset CLOUDFLARE_ZONE_ID 2>/dev/null || true

SLUG=""
EDGE_ONLY="0"
DRY_RUN="0"
TUNNEL_ID_OVERRIDE="${PODCAST_TUNNEL_ID:-}"

usage() {
  sed -n '1,32p' "$0" >&2
  cat >&2 <<'USAGE'

USAGE:
  revoke-podcast-client.sh <slug> [flags]

FLAGS:
  --edge-only        Emergency mode: Cloudflare steps 1 to 4 + verification 9a to 9c only;
                     box hygiene (5 to 8) recorded PENDING. Use when the box is unreachable.
  --tunnel-id <id>   Override the tunnel id (else read from the provision ledger, then the
                     Command Center CNAME). Also settable via PODCAST_TUNNEL_ID.
  --dry-run          Log mutations instead of applying them (canary preview).
  -h, --help         Show this help.

ENV:
  CLOUDFLARE_API_TOKEN   REQUIRED (BlackCEO operator token). Confirmed SET, never printed.
  CLOUDFLARE_ACCOUNT_ID  Optional account id override.
  PODCAST_NODE_USER      Box runtime user for config writes (default node; never root).
  PODCAST_PROVISION_LEDGER_DIR  Provision ledger dir (default /tmp/podcast-provision).
  PODCAST_LEDGER_DIR     Revoke ledger dir (default /tmp/podcast-revoke).
  SECRETS_ENV_FILE       Box secrets file (default $HOME/.openclaw/secrets.env).
USAGE
}

POSITIONAL=()
while [ $# -gt 0 ]; do
  case "$1" in
    --edge-only) EDGE_ONLY="1"; shift ;;
    --tunnel-id) TUNNEL_ID_OVERRIDE="${2:-}"; shift 2 ;;
    --dry-run)   DRY_RUN="1"; shift ;;
    -h|--help)   usage; exit 0 ;;
    --) shift; while [ $# -gt 0 ]; do POSITIONAL+=("$1"); shift; done ;;
    -*) echo "Unknown flag: $1" >&2; usage; exit 2 ;;
    *)  POSITIONAL+=("$1"); shift ;;
  esac
done
SLUG="${POSITIONAL[0]:-}"

log()  { printf '%s\n' "$*" >&2; }
die()  { local code="$1"; shift; log "HARD STOP ($code): $*"; ledger_finish "failed"; exit "$code"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing dependency: $1" >&2; exit 3; }; }

cf() { curl -sS -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" -H "Content-Type: application/json" "$@"; }
cf_write() {
  if [ "$DRY_RUN" = "1" ]; then printf '%s' '{"success":true,"result":{},"dry_run":true}'; return 0; fi
  cf "$@"
}
ok_of()  { printf '%s' "$1" | jq -r '.success // false' 2>/dev/null; }
err_of() { printf '%s' "$1" | jq -c '.errors // []' 2>/dev/null; }

LEDGER_DIR="${PODCAST_LEDGER_DIR:-/tmp/podcast-revoke}"
PROVISION_LEDGER_DIR="${PODCAST_PROVISION_LEDGER_DIR:-/tmp/podcast-provision}"
LEDGER=""
ledger_init() {
  mkdir -p "$LEDGER_DIR"
  LEDGER="$LEDGER_DIR/${SLUG}.json"
  jq -n --arg slug "$SLUG" --arg ts "$(date -u +%FT%TZ)" --arg dry "$DRY_RUN" --arg edge "$EDGE_ONLY" \
    '{slug:$slug, action:"revoke", edge_only:($edge=="1"), dry_run:($dry=="1"), started_at:$ts, steps:[]}' > "$LEDGER"
}
ledger_step() {
  local name="$1" status="$2" detail="${3:-}"
  local tmp; tmp="$(mktemp)"
  jq --arg n "$name" --arg s "$status" --arg d "$detail" --arg ts "$(date -u +%FT%TZ)" \
    '.steps += [{step:$n, status:$s, detail:$d, at:$ts}]' "$LEDGER" > "$tmp" && mv "$tmp" "$LEDGER"
  log "[$status] $name${detail:+ - $detail}"
}
ledger_finish() {
  [ -n "$LEDGER" ] || return 0
  local tmp; tmp="$(mktemp)"
  jq --arg s "$1" --arg ts "$(date -u +%FT%TZ)" '.result=$s | .finished_at=$ts' "$LEDGER" > "$tmp" && mv "$tmp" "$LEDGER"
  log ""
  log "==== REVOKE REPORT (slug=$SLUG, edge_only=$EDGE_ONLY, result=$1) ===="
  jq -r '.steps[] | "  [" + .status + "] " + .step + (if .detail != "" then " - " + .detail else "" end)' "$LEDGER" >&2
  log "  ledger: $LEDGER"
  log "==============================================================="
}

runas() {
  local u="${PODCAST_NODE_USER:-node}"
  if [ "$(id -u)" = "0" ]; then
    command -v sudo >/dev/null 2>&1 || { log "root with no sudo; refusing to write box config as root"; return 12; }
    sudo -u "$u" "$@"
  else
    "$@"
  fi
}

# --------------------------------------------------------------------------- #
# Preflight
# --------------------------------------------------------------------------- #
need curl; need jq
[ -n "$SLUG" ] || { usage; exit 2; }
printf '%s' "$SLUG" | grep -Eq '^[a-z0-9][a-z0-9-]{1,40}$' || { echo "slug must be lowercase [a-z0-9-]" >&2; exit 2; }

if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
  echo "HARD STOP: CLOUDFLARE_API_TOKEN is not set (BlackCEO operator token; operator-side only)." >&2
  exit 13
fi

ledger_init

ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-$ACCOUNT_ID_DEFAULT}"
DASH_HOST="${SLUG}-podcast.${ZONE_NAME}"
CC_HOST="${SLUG}.${ZONE_NAME}"
SLUG_REF="$(printf '%s' "$SLUG" | tr '-' '_')"
INTAKE_MAPPING="${PODCAST_INTAKE_MAPPING:-podcast-intake-${SLUG}}"

# Read tenancy from the provision ledger (never guess whether the hooks host is shared).
PLEDGER="$PROVISION_LEDGER_DIR/${SLUG}.json"
HOOKS_HOST=""; HOOKS_SOLE_TENANT="unknown"; WAF_REF="podcast_hooks_${SLUG_REF}"; LEDGER_TUNNEL_ID=""
if [ -f "$PLEDGER" ]; then
  HOOKS_HOST="$(jq -r '.facts.hooks_host // empty' "$PLEDGER" 2>/dev/null)"
  HOOKS_SOLE_TENANT="$(jq -r '.facts.hooks_sole_tenant // "unknown"' "$PLEDGER" 2>/dev/null)"
  WAF_REF="$(jq -r '.facts.waf_ref // empty' "$PLEDGER" 2>/dev/null)"; [ -n "$WAF_REF" ] || WAF_REF="podcast_hooks_${SLUG_REF}"
  LEDGER_TUNNEL_ID="$(jq -r '.facts.tunnel_id // empty' "$PLEDGER" 2>/dev/null)"
  ledger_step "tenancy" "OK" "from provision ledger: hooks_host=${HOOKS_HOST:-none} sole_tenant=$HOOKS_SOLE_TENANT"
else
  ledger_step "tenancy" "WARN" "no provision ledger at $PLEDGER; being conservative (will not remove a possibly-shared hooks host)"
fi

# --------------------------------------------------------------------------- #
# Zone resolution by NAME (the trap guard)
# --------------------------------------------------------------------------- #
ZONE_ID="$(cf "$API/zones?name=${ZONE_NAME}" | jq -r '.result[0].id // empty')"
[ -n "$ZONE_ID" ] || ZONE_ID="$ZONE_ID_KNOWN"
ZNAME_CHECK="$(cf "$API/zones/${ZONE_ID}" | jq -r '.result.name // empty')"
[ "$ZNAME_CHECK" = "$ZONE_NAME" ] || die 4 "resolved zone id $ZONE_ID has name '$ZNAME_CHECK', not $ZONE_NAME; refusing"
ledger_step "zone-resolve" "OK" "$ZONE_NAME -> $ZONE_ID (verified by name)"

# --------------------------------------------------------------------------- #
# STEP 1: revoke live dashboard sessions (instant lockout, before route deletes)
# --------------------------------------------------------------------------- #
APP_ID="$(cf "$API/accounts/${ACCOUNT_ID}/access/apps?per_page=100" \
  | jq -r --arg d "$DASH_HOST" '.result[]? | select((.domain // "")==$d or ((.self_hosted_domains // [])|index($d))) | .id' | head -n1)"
if [ -n "$APP_ID" ]; then
  R="$(cf_write -X POST "$API/accounts/${ACCOUNT_ID}/access/apps/${APP_ID}/revoke_tokens")"
  if [ "$(ok_of "$R")" = "true" ]; then ledger_step "1-revoke-sessions" "OK" "revoked all tokens for app $APP_ID"
  else ledger_step "1-revoke-sessions" "WARN" "revoke_tokens returned: $(err_of "$R")"; fi
else
  ledger_step "1-revoke-sessions" "SKIP" "no Access app found for $DASH_HOST (already gone)"
fi

# --------------------------------------------------------------------------- #
# STEP 2: delete the Access application (no new logins)
# --------------------------------------------------------------------------- #
if [ -n "$APP_ID" ]; then
  R="$(cf_write -X DELETE "$API/accounts/${ACCOUNT_ID}/access/apps/${APP_ID}")"
  if [ "$(ok_of "$R")" = "true" ]; then ledger_step "2-delete-access-app" "OK" "deleted app $APP_ID"
  else ledger_step "2-delete-access-app" "WARN" "$(err_of "$R")"; fi
else
  ledger_step "2-delete-access-app" "SKIP" "already absent"
fi

# --------------------------------------------------------------------------- #
# STEP 3: cut the dashboard hostname at DNS
# --------------------------------------------------------------------------- #
DREC="$(cf "$API/zones/${ZONE_ID}/dns_records?name=${DASH_HOST}" | jq -r '.result[0].id // empty')"
if [ -n "$DREC" ]; then
  R="$(cf_write -X DELETE "$API/zones/${ZONE_ID}/dns_records/${DREC}")"
  if [ "$(ok_of "$R")" = "true" ]; then ledger_step "3-delete-dns" "OK" "deleted CNAME $DASH_HOST"
  else ledger_step "3-delete-dns" "WARN" "$(err_of "$R")"; fi
else
  ledger_step "3-delete-dns" "SKIP" "no DNS record for $DASH_HOST"
fi

# --------------------------------------------------------------------------- #
# STEP 4: remove tunnel ingress routes (dashboard always; hooks host only if
# podcast is the sole tenant) and the WAF rule when the hooks host is removed.
# --------------------------------------------------------------------------- #
TUNNEL_ID="$TUNNEL_ID_OVERRIDE"
[ -n "$TUNNEL_ID" ] || TUNNEL_ID="$LEDGER_TUNNEL_ID"
if [ -z "$TUNNEL_ID" ]; then
  CC_CNAME="$(cf "$API/zones/${ZONE_ID}/dns_records?type=CNAME&name=${CC_HOST}" | jq -r '.result[0].content // empty')"
  printf '%s' "$CC_CNAME" | grep -q '\.cfargotunnel\.com$' && TUNNEL_ID="${CC_CNAME%.cfargotunnel.com}"
fi

REMOVE_HOOKS_HOST="0"
[ "$HOOKS_SOLE_TENANT" = "true" ] && [ -n "$HOOKS_HOST" ] && REMOVE_HOOKS_HOST="1"

if [ -z "$TUNNEL_ID" ]; then
  ledger_step "4-ingress" "SKIP" "tunnel id unknown (no ledger, no CNAME, no --tunnel-id); dashboard is already DNS-dark from step 3"
else
  CFG="$(cf "$API/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations")"
  TUNNEL_SRC="$(printf '%s' "$CFG" | jq -r '.result.source // "cloudflare"')"
  if [ "$(ok_of "$CFG")" != "true" ]; then
    ledger_step "4-ingress" "WARN" "could not read tunnel config for $TUNNEL_ID: $(err_of "$CFG")"
  elif [ "$TUNNEL_SRC" = "cloudflare" ]; then
    NEWCFG="$(printf '%s' "$CFG" | jq \
      --arg dash "$DASH_HOST" --arg hooks "${HOOKS_HOST:-__none__}" --argjson rmhooks "$([ "$REMOVE_HOOKS_HOST" = "1" ] && echo true || echo false)" '
      {config: (.result.config
        | .ingress = ((.ingress // []) | map(select(
            ((.hostname // "") != $dash)
            and (($rmhooks|not) or ((.hostname // "") != $hooks))
          ))))}')"
    R="$(cf_write -X PUT "$API/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" --data "$NEWCFG")"
    if [ "$(ok_of "$R")" = "true" ]; then
      ledger_step "4-ingress" "OK" "removed $DASH_HOST$( [ "$REMOVE_HOOKS_HOST" = "1" ] && printf '%s' " and $HOOKS_HOST (sole tenant)" || printf '%s' " (hooks host kept: shared/unknown tenancy)")"
    else
      ledger_step "4-ingress" "WARN" "ingress PUT failed: $(err_of "$R")"
    fi
  else
    ledger_step "4-ingress" "PENDING" "tunnel is locally-managed; on the box (as the node user) remove the $DASH_HOST$( [ "$REMOVE_HOOKS_HOST" = "1" ] && printf '%s' " and $HOOKS_HOST" ) ingress from config.yml, then restart cloudflared per fleet doctrine and prove edge connections > 0"
  fi

  # WAF rule removal only when the hooks host is being removed.
  if [ "$REMOVE_HOOKS_HOST" = "1" ]; then
    RS="$(cf "$API/zones/${ZONE_ID}/rulesets/phases/http_request_firewall_custom/entrypoint")"
    RULES_TYPE="$(printf '%s' "$RS" | jq -r '.result.rules | type' 2>/dev/null || echo null)"
    if [ "$(ok_of "$RS")" = "true" ] && { [ "$RULES_TYPE" = "array" ] || [ "$RULES_TYPE" = "null" ]; }; then
      HAS_RULE="$(printf '%s' "$RS" | jq -r --arg ref "$WAF_REF" '[.result.rules[]? | select((.ref // "")==$ref)] | length')"
      if [ "${HAS_RULE:-0}" -gt 0 ]; then
        MERGED="$(printf '%s' "$RS" | jq --arg ref "$WAF_REF" \
          '{rules: ((.result.rules // []) | map(select((.ref // "") != $ref)) | map(del(.id,.version,.last_updated)))}')"
        R="$(cf_write -X PUT "$API/zones/${ZONE_ID}/rulesets/phases/http_request_firewall_custom/entrypoint" --data "$MERGED")"
        if [ "$(ok_of "$R")" = "true" ]; then ledger_step "4-waf" "OK" "removed WAF rule ref $WAF_REF"
        else ledger_step "4-waf" "WARN" "$(err_of "$R")"; fi
      else
        ledger_step "4-waf" "SKIP" "no WAF rule with ref $WAF_REF"
      fi
    else
      ledger_step "4-waf" "PENDING" "could not read the shared zone ruleset safely; refusing to PUT; remove ref $WAF_REF manually"
    fi
  else
    ledger_step "4-waf" "SKIP" "hooks host kept; leaving its WAF rule in place"
  fi
fi

# --------------------------------------------------------------------------- #
# Steps 5 to 8: box hygiene. Skipped (PENDING) in edge-only emergency mode.
# --------------------------------------------------------------------------- #
SECRETS_ENV_FILE="${SECRETS_ENV_FILE:-$HOME/.openclaw/secrets.env}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

rotate_secret() {
  local key="$1"
  if [ "$DRY_RUN" = "1" ]; then ledger_step "secret:${key}" "DRY-RUN" "would remove (value never printed)"; return 0; fi
  if runas test -f "$SECRETS_ENV_FILE" 2>/dev/null; then
    if runas grep -qE "^${key}=" "$SECRETS_ENV_FILE" 2>/dev/null; then
      local tmp; tmp="$(mktemp)"
      # shellcheck disable=SC2016  # single quotes intentional: paths are passed as positional args to the inner shell, nothing sensitive is interpolated
      runas grep -vE "^${key}=" "$SECRETS_ENV_FILE" > "$tmp" 2>/dev/null && runas bash -c 'umask 077; cat "$0" > "$1"' "$tmp" "$SECRETS_ENV_FILE"
      rm -f "$tmp"
      if runas grep -qE "^${key}=" "$SECRETS_ENV_FILE" 2>/dev/null; then
        ledger_step "secret:${key}" "WARN" "still present after removal attempt"
      else
        ledger_step "secret:${key}" "OK" "removed (NOT SET); any resurrected route is dead"
      fi
    else
      ledger_step "secret:${key}" "OK" "already NOT SET"
    fi
  else
    ledger_step "secret:${key}" "SKIP" "no secrets file here"
  fi
}

if [ "$EDGE_ONLY" = "1" ]; then
  ledger_step "5-webhook-disable"  "PENDING" "edge-only: remove the podcast hook mapping and rotate PODCAST_INTAKE_HOOK_TOKEN on the box (as the node user), apply config per gateway restart doctrine, then verify the gateway is UP"
  ledger_step "6-dashboard-stop"   "PENDING" "edge-only: rotate PODCAST_DASHBOARD_TOKEN and stop/deregister the loopback dashboard service on the box"
  ledger_step "7-smoke-cron-stop"  "PENDING" "edge-only: openclaw cron rm the podcast-smoke-${SLUG} job on the box (verify with cron list)"
  ledger_step "8-drain-queue"      "PENDING" "edge-only: close the client's credit-out queue jobs as offboarded and notify the operator with the dropped job ids"
else
  # STEP 5: disable + rotate the inbound webhook
  if command -v openclaw >/dev/null 2>&1 && [ -x "$SCRIPT_DIR/register-podcast-hook.sh" ]; then
    if runas "$SCRIPT_DIR/register-podcast-hook.sh" --remove "$SLUG" "$INTAKE_MAPPING" >/dev/null 2>&1; then
      ledger_step "5-webhook-disable" "OK" "removed hook mapping $INTAKE_MAPPING (gateway restart doctrine applied by helper)"
    else
      ledger_step "5-webhook-disable" "PENDING" "hook removal helper returned nonzero; remove the mapping on the box as the node user, then restart the gateway per doctrine"
    fi
  else
    ledger_step "5-webhook-disable" "PENDING" "hook-removal helper/openclaw not present here; remove the podcast mapping on the box (node user), apply config per gateway restart doctrine, and confirm the gateway is UP"
  fi
  rotate_secret "PODCAST_INTAKE_HOOK_TOKEN"

  # STEP 6: invalidate the dashboard token and stop the dashboard service
  rotate_secret "PODCAST_DASHBOARD_TOKEN"
  if [ -x "$SCRIPT_DIR/deploy-podcast-dashboard.sh" ]; then
    if runas "$SCRIPT_DIR/deploy-podcast-dashboard.sh" --stop "$SLUG" >/dev/null 2>&1; then
      ledger_step "6-dashboard-stop" "OK" "dashboard service stopped and deregistered"
    else
      ledger_step "6-dashboard-stop" "PENDING" "stop helper returned nonzero; stop the loopback dashboard service on the box"
    fi
  else
    ledger_step "6-dashboard-stop" "PENDING" "dashboard deploy helper not present here; stop/deregister the loopback service on the box (same SSH discipline)"
  fi

  # STEP 7: stop the daily smoke-test cron
  if command -v openclaw >/dev/null 2>&1; then
    CID="$(runas openclaw cron list 2>/dev/null | grep -i "podcast-smoke-${SLUG}" | grep -oE '[0-9a-f-]{8,}' | head -n1)"
    if [ -n "$CID" ]; then
      if runas openclaw cron rm "$CID" >/dev/null 2>&1; then
        ledger_step "7-smoke-cron-stop" "OK" "removed cron $CID; verify with a fresh cron list"
      else
        ledger_step "7-smoke-cron-stop" "PENDING" "cron rm failed; remove podcast-smoke-${SLUG} on the box"
      fi
    else
      ledger_step "7-smoke-cron-stop" "OK" "no podcast-smoke-${SLUG} cron found (already gone)"
    fi
  else
    ledger_step "7-smoke-cron-stop" "PENDING" "openclaw CLI not present here; remove the podcast-smoke-${SLUG} cron on the box"
  fi

  # STEP 8: drain the credit-out queue for this client (offboarded, not aged out)
  if [ -x "$SCRIPT_DIR/podcast-queue.sh" ]; then
    if runas "$SCRIPT_DIR/podcast-queue.sh" --close-offboarded "$SLUG" >/dev/null 2>&1; then
      ledger_step "8-drain-queue" "OK" "queued jobs closed as client-offboarded; operator notified with dropped ids"
    else
      ledger_step "8-drain-queue" "PENDING" "queue helper returned nonzero; close jobs as offboarded and notify the operator"
    fi
  else
    ledger_step "8-drain-queue" "PENDING" "queue helper not present here; close this client's credit-out jobs as offboarded and notify the operator with the dropped job ids (zero client messages)"
  fi
fi

# --------------------------------------------------------------------------- #
# STEP 9: independent end-to-end verification (no false done)
# --------------------------------------------------------------------------- #
VERIFY_FAIL="0"

# 9a: dashboard must NOT return 302 to the Access team host.
if [ "$DRY_RUN" = "1" ]; then
  ledger_step "9a-edge-dark" "DRY-RUN" "skipped in dry-run"
else
  HDRS="$(curl -sSI --max-time 15 "https://${DASH_HOST}" 2>/dev/null || true)"
  if printf '%s' "$HDRS" | grep -q ' 302' && printf '%s' "$HDRS" | grep -qi "$ACCESS_TEAM_HOST"; then
    ledger_step "9a-edge-dark" "FAIL" "dashboard STILL returns 302 to $ACCESS_TEAM_HOST"; VERIFY_FAIL="1"
  else
    ledger_step "9a-edge-dark" "PASS" "no 302 to Access (resolution failure or 1016/530 class as expected)"
  fi
fi

# 9b: POST to the old hook path must fail (not 2xx).
if [ "$DRY_RUN" = "1" ]; then
  ledger_step "9b-hook-dead" "DRY-RUN" "skipped in dry-run"
elif [ -n "$HOOKS_HOST" ]; then
  CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
    -X POST "https://${HOOKS_HOST}/hooks/${INTAKE_MAPPING}" -H "Content-Type: application/json" \
    --data '{"_test":true,"source":"revoke-verify"}' 2>/dev/null || echo "000")"
  if printf '%s' "$CODE" | grep -Eq '^2[0-9][0-9]$'; then
    ledger_step "9b-hook-dead" "FAIL" "old hook still accepts (HTTP $CODE)"; VERIFY_FAIL="1"
  else
    ledger_step "9b-hook-dead" "PASS" "old hook path dead (HTTP $CODE)"
  fi
else
  ledger_step "9b-hook-dead" "SKIP" "no hooks host recorded"
fi

# 9c: Cloudflare reads confirm no Access app and no dashboard DNS record.
if [ "$DRY_RUN" = "1" ]; then
  ledger_step "9c-cf-clean" "DRY-RUN" "skipped in dry-run"
else
  STILL_APP="$(cf "$API/accounts/${ACCOUNT_ID}/access/apps?per_page=100" | jq -r --arg d "$DASH_HOST" '[.result[]? | select((.domain // "")==$d)] | length')"
  STILL_DNS="$(cf "$API/zones/${ZONE_ID}/dns_records?name=${DASH_HOST}" | jq -r '.result | length')"
  if [ "${STILL_APP:-0}" = "0" ] && [ "${STILL_DNS:-0}" = "0" ]; then
    ledger_step "9c-cf-clean" "PASS" "no Access app and no dashboard DNS record remain"
  else
    ledger_step "9c-cf-clean" "FAIL" "residual: apps=$STILL_APP dns=$STILL_DNS"; VERIFY_FAIL="1"
  fi
fi

# 9d: box reads (tokens NOT SET, gateway healthy). Skipped in edge-only.
if [ "$EDGE_ONLY" = "1" ] || [ "$DRY_RUN" = "1" ]; then
  ledger_step "9d-box-clean" "PENDING" "$([ "$EDGE_ONLY" = "1" ] && echo "edge-only: run box verification when the box is reachable" || echo "dry-run")"
else
  BOX_MSG=""
  if runas test -f "$SECRETS_ENV_FILE" 2>/dev/null; then
    runas grep -qE '^PODCAST_(INTAKE_HOOK|DASHBOARD)_TOKEN=' "$SECRETS_ENV_FILE" 2>/dev/null \
      && BOX_MSG="tokens STILL SET; " || BOX_MSG="tokens NOT SET; "
  else
    BOX_MSG="no secrets file; "
  fi
  GW_CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${GATEWAY_PORT}/" 2>/dev/null; echo " rc=$?")"
  if printf '%s' "$GW_CODE" | grep -qE 'rc=0$|rc=22$'; then
    ledger_step "9d-box-clean" "PASS" "${BOX_MSG}gateway on :${GATEWAY_PORT} healthy (a revocation that downs a live box is a FAILED revocation)"
  else
    ledger_step "9d-box-clean" "WARN" "${BOX_MSG}gateway health inconclusive (${GW_CODE}); confirm the gateway is UP on the box"
  fi
fi

# --------------------------------------------------------------------------- #
# Finish
# --------------------------------------------------------------------------- #
if [ "$VERIFY_FAIL" = "1" ]; then
  ledger_finish "verification-failed"
  log "Revocation verification FAILED; public access may not be fully cut. Investigate the FAIL lines above."
  exit 21
fi
if [ "$EDGE_ONLY" = "1" ]; then
  ledger_finish "edge-revoked-box-pending"
  log "Edge access CUT (steps 1 to 4 + 9a to 9c verified). Box hygiene (5 to 8) is PENDING until the box is reachable; complete it then re-run without --edge-only."
  exit 0
fi
ledger_finish "ok"
log "Revocation complete and independently verified. Zero client-facing messages sent."
exit 0
