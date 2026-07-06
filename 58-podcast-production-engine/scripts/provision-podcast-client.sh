#!/usr/bin/env bash
# provision-podcast-client.sh <slug> <client-email[,email2,...]> <timezone>
#
# Podcast Production Engine (skill 58) - per-client Cloudflare provisioning.
# Implements design/cloudflare-design.md Sections 2 and 5 (BlackCEO-hosted, firm).
#
# WHAT THIS DOES (edge, owned and endpoint-verified against the live Cloudflare API):
#   1. Discovers the client's ONE existing named tunnel (never creates a second).
#   2. Adds ingress: <slug>-podcast -> http://localhost:4010 (dashboard, loopback),
#      and <slug>-hooks -> http://127.0.0.1:18789 (gateway) unless a hooks hostname
#      already routes to 18789 on this tunnel, in which case it is REUSED.
#   3. Creates proxied CNAME record(s) -> <tunnel-id>.cfargotunnel.com.
#   4. Creates the dashboard Access app "Podcast Dashboard - <slug>", allow-by-email:
#      the client's email(s) plus trevelynotts@gmail.com plus trevor@blackceo.com.
#   5. Adds a zone WAF custom rule (POST-to-/hooks only) ONLY when it creates a new,
#      podcast-sole hooks hostname. The shared zone ruleset is MERGED, never clobbered.
#   6. Runs the pass gate: 302-to-Access on the dashboard, a signed hook test POST,
#      a single smoke-test cron fire, and an Access allow-list read-back diff.
#
# WHAT THIS DELEGATES (box-side, owned by sibling slices; recorded PENDING when the
# helper or the OpenClaw CLI is not present so nothing is silently skipped):
#   - the OpenClaw inbound hook mapping (webhook-design.md; flat body, deliver false),
#   - the loopback dashboard service on 4010 (dashboard-design.md),
#   - the Convert and Flow custom-field write and the Command Center card,
#   - the daily smoke-test cron creation and first fire (furnace-design.md).
#
# HARD RULES honored here:
#   - Never trust CLOUDFLARE_ZONE_ID (it points at the wrong zone). Resolve by name and
#     refuse to run unless the resolved zone name is zerohumanworkforce.com.
#   - Never print a secret value. Tokens are confirmed SET by key name only.
#   - Config writes on the box run as the node user, never root.
#   - Zero client-facing messages. Operator-verbose only; a per-client ledger is written.
#   - Idempotent: safe to re-run; existing correct resources are reused, not duplicated.
#
set -uo pipefail

# --------------------------------------------------------------------------- #
# Constants (documented; the account id is correct, the zone id is the known-good
# cross-check for the name resolution, never a substitute for it).
# --------------------------------------------------------------------------- #
API="https://api.cloudflare.com/client/v4"
ACCOUNT_ID_DEFAULT="13f808b72eb78027a8046357c6cf1afa"
ZONE_NAME="zerohumanworkforce.com"
ZONE_ID_KNOWN="a9ecc0a067f52eaa4c59dc9b11d9dd55"
ACCESS_TEAM_HOST="sweet-wave-ca28.cloudflareaccess.com"
OPERATOR_EMAILS=("trevelynotts@gmail.com" "trevor@blackceo.com")
DASH_PORT="4010"
GATEWAY_PORT="18789"
SESSION_DURATION="24h"

# The CLOUDFLARE_ZONE_ID env var is a known trap on operator boxes. Neutralize it so
# no downstream code can accidentally pick it up.
unset CLOUDFLARE_ZONE_ID 2>/dev/null || true

# --------------------------------------------------------------------------- #
# Args and flags
# --------------------------------------------------------------------------- #
SLUG=""
EMAILS_RAW=""
CLIENT_TZ=""
DRY_RUN="0"
FORCE="0"
TUNNEL_ID_OVERRIDE="${PODCAST_TUNNEL_ID:-}"

usage() {
  sed -n '1,40p' "$0" >&2
  cat >&2 <<'USAGE'

USAGE:
  provision-podcast-client.sh <slug> <client-email[,email2,...]> <timezone> [flags]

FLAGS:
  --tunnel-id <id>   Use this tunnel id instead of resolving it from the Command
                     Center CNAME (also settable via PODCAST_TUNNEL_ID).
  --dry-run          Perform all read-only discovery, but log mutations instead of
                     applying them (operator canary preview). Still requires the token.
  --force            Recreate the Access app even if one already exists for the host.
  -h, --help         Show this help.

ENV:
  CLOUDFLARE_API_TOKEN   REQUIRED (BlackCEO operator token). Confirmed SET, never printed.
  CLOUDFLARE_ACCOUNT_ID  Optional override of the account id.
  PODCAST_INTAKE_MAPPING Optional hook mapping name (default podcast-intake-<slug>).
  PODCAST_NODE_USER      Box runtime user for config writes (default: node). Config is
                         never written as root.
  PODCAST_LEDGER_DIR     Ledger directory (default /tmp/podcast-provision).
  SECRETS_ENV_FILE       Box secrets file (default $HOME/.openclaw/secrets.env).
USAGE
}

POSITIONAL=()
while [ $# -gt 0 ]; do
  case "$1" in
    --tunnel-id) TUNNEL_ID_OVERRIDE="${2:-}"; shift 2 ;;
    --dry-run)   DRY_RUN="1"; shift ;;
    --force)     FORCE="1"; shift ;;
    -h|--help)   usage; exit 0 ;;
    --) shift; while [ $# -gt 0 ]; do POSITIONAL+=("$1"); shift; done ;;
    -*) echo "Unknown flag: $1" >&2; usage; exit 2 ;;
    *)  POSITIONAL+=("$1"); shift ;;
  esac
done
SLUG="${POSITIONAL[0]:-}"
EMAILS_RAW="${POSITIONAL[1]:-}"
CLIENT_TZ="${POSITIONAL[2]:-}"

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
log()  { printf '%s\n' "$*" >&2; }
die()  { local code="$1"; shift; log "HARD STOP ($code): $*"; ledger_finish "failed"; exit "$code"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing dependency: $1" >&2; exit 3; }; }

cf() { curl -sS -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" -H "Content-Type: application/json" "$@"; }

# cf_write: mutating Cloudflare call. In dry-run it is logged, not applied, and returns
# a synthetic success so the control flow can be exercised end to end on a canary.
cf_write() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '%s' '{"success":true,"result":{},"dry_run":true}'
    return 0
  fi
  cf "$@"
}

ok_of() { printf '%s' "$1" | jq -r '.success // false' 2>/dev/null; }
err_of() { printf '%s' "$1" | jq -c '.errors // []' 2>/dev/null; }

# Ledger (operator-verbose; also the tenancy record revoke reads back)
LEDGER_DIR="${PODCAST_LEDGER_DIR:-/tmp/podcast-provision}"
LEDGER=""
ledger_init() {
  mkdir -p "$LEDGER_DIR"
  LEDGER="$LEDGER_DIR/${SLUG}.json"
  jq -n --arg slug "$SLUG" --arg ts "$(date -u +%FT%TZ)" --arg dry "$DRY_RUN" \
    '{slug:$slug, action:"provision", dry_run:($dry=="1"), started_at:$ts, facts:{}, steps:[]}' \
    > "$LEDGER"
}
ledger_fact() {
  local tmp; tmp="$(mktemp)"
  jq --arg k "$1" --arg v "$2" '.facts[$k]=$v' "$LEDGER" > "$tmp" && mv "$tmp" "$LEDGER"
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
  log "==== PROVISION REPORT (slug=$SLUG, result=$1) ===="
  jq -r '.steps[] | "  [" + .status + "] " + .step + (if .detail != "" then " - " + .detail else "" end)' "$LEDGER" >&2
  log "  ledger: $LEDGER"
  log "================================================="
}

# runas: box-side config helper. Never runs config writes as root.
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
need curl; need jq; need openssl

[ -n "$SLUG" ] || { usage; exit 2; }
[ -n "$EMAILS_RAW" ] || { echo "missing client email(s)" >&2; usage; exit 2; }
[ -n "$CLIENT_TZ" ] || { echo "missing timezone" >&2; usage; exit 2; }
printf '%s' "$SLUG" | grep -Eq '^[a-z0-9][a-z0-9-]{1,40}$' || { echo "slug must be lowercase [a-z0-9-], 2 to 41 chars" >&2; exit 2; }

if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
  cat >&2 <<'ERR'
HARD STOP: CLOUDFLARE_API_TOKEN is not set.
This is BlackCEO's own operator token (Account: Access + Cloudflare Tunnel + Zone WAF,
Zone: DNS). It is operator-side only, never placed on a client box. The script is
forbidden from inventing it or borrowing another account's credential.
Resolution: source the operator secret store, then re-run.
ERR
  exit 13
fi

ledger_init
ledger_fact "timezone" "$CLIENT_TZ"

# Build the allow-list (client emails + the two operator emails), validated and deduped.
declare -a ALL_EMAILS=()
IFS=', ' read -r -a _client_emails <<< "$EMAILS_RAW"
for e in "${_client_emails[@]}" "${OPERATOR_EMAILS[@]}"; do
  [ -n "$e" ] || continue
  printf '%s' "$e" | grep -Eiq '^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$' || die 2 "invalid email in allow-list: $e"
  ALL_EMAILS+=("$e")
done
# dedup, preserve order (portable; avoids the bash-4-only mapfile builtin)
_dedup=()
while IFS= read -r _line; do [ -n "$_line" ] && _dedup+=("$_line"); done < <(printf '%s\n' "${ALL_EMAILS[@]}" | awk '!seen[$0]++')
ALL_EMAILS=("${_dedup[@]}")
INCLUDE_JSON="$(printf '%s\n' "${ALL_EMAILS[@]}" | jq -R '{email:{email:.}}' | jq -s '.')"
ledger_fact "allow_list_count" "${#ALL_EMAILS[@]}"

ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-$ACCOUNT_ID_DEFAULT}"
DASH_HOST="${SLUG}-podcast.${ZONE_NAME}"
HOOKS_HOST_NEW="${SLUG}-hooks.${ZONE_NAME}"
CC_HOST="${SLUG}.${ZONE_NAME}"
INTAKE_MAPPING="${PODCAST_INTAKE_MAPPING:-podcast-intake-${SLUG}}"
SLUG_REF="$(printf '%s' "$SLUG" | tr '-' '_')"

log "provision: slug=$SLUG dash=$DASH_HOST tz=$CLIENT_TZ dry_run=$DRY_RUN"

# --------------------------------------------------------------------------- #
# Zone resolution by NAME (the CLOUDFLARE_ZONE_ID trap guard)
# --------------------------------------------------------------------------- #
ZRESP="$(cf "$API/zones?name=${ZONE_NAME}")"
ZONE_ID="$(printf '%s' "$ZRESP" | jq -r '.result[0].id // empty')"
if [ -z "$ZONE_ID" ]; then
  log "zone list by name returned nothing; falling back to the known-good zone id and re-verifying its name"
  ZONE_ID="$ZONE_ID_KNOWN"
fi
ZNAME_CHECK="$(cf "$API/zones/${ZONE_ID}" | jq -r '.result.name // empty')"
[ "$ZNAME_CHECK" = "$ZONE_NAME" ] || die 4 "resolved zone id $ZONE_ID has name '$ZNAME_CHECK', not $ZONE_NAME; refusing to touch the wrong zone"
ledger_fact "zone_id" "$ZONE_ID"
ledger_step "zone-resolve" "OK" "zone $ZONE_NAME -> $ZONE_ID (verified by name)"

# --------------------------------------------------------------------------- #
# Tunnel discovery (the client's ONE existing tunnel; never create a second)
# --------------------------------------------------------------------------- #
TUNNEL_ID="$TUNNEL_ID_OVERRIDE"
if [ -z "$TUNNEL_ID" ]; then
  CC_CNAME="$(cf "$API/zones/${ZONE_ID}/dns_records?type=CNAME&name=${CC_HOST}" | jq -r '.result[0].content // empty')"
  if printf '%s' "$CC_CNAME" | grep -q '\.cfargotunnel\.com$'; then
    TUNNEL_ID="${CC_CNAME%.cfargotunnel.com}"
  fi
fi
[ -n "$TUNNEL_ID" ] || die 5 "could not resolve the client tunnel id from ${CC_HOST}; pass --tunnel-id <id> (the box's existing named tunnel)"
printf '%s' "$TUNNEL_ID" | grep -Eq '^[0-9a-f]{32}$|^[0-9a-f-]{36}$' || die 5 "resolved tunnel id '$TUNNEL_ID' does not look like a tunnel uuid"
ledger_fact "tunnel_id" "$TUNNEL_ID"

CFG="$(cf "$API/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations")"
[ "$(ok_of "$CFG")" = "true" ] || die 6 "could not read tunnel configuration for $TUNNEL_ID: $(err_of "$CFG")"
TUNNEL_SRC="$(printf '%s' "$CFG" | jq -r '.result.source // "cloudflare"')"
ledger_fact "tunnel_source" "$TUNNEL_SRC"
ledger_step "tunnel-discover" "OK" "tunnel=$TUNNEL_ID source=$TUNNEL_SRC"

# Reuse an existing hooks hostname if one already routes to the loopback gateway (18789).
EXISTING_HOOKS_HOST="$(printf '%s' "$CFG" | jq -r \
  '.result.config.ingress[]? | select((.service // "") | test(":'"$GATEWAY_PORT"'\\b|:'"$GATEWAY_PORT"'$")) | .hostname // empty' | head -n1)"
if [ -n "$EXISTING_HOOKS_HOST" ]; then
  HOOKS_HOST="$EXISTING_HOOKS_HOST"
  CREATE_HOOKS="false"       # reuse: do not add DNS/ingress/WAF for the hooks host
  HOOKS_SOLE_TENANT="false"  # shared with other inbound skills
  ledger_step "hooks-hostname" "REUSE" "reusing existing $HOOKS_HOST (routes to :$GATEWAY_PORT); adding only the podcast mapping and token"
else
  HOOKS_HOST="$HOOKS_HOST_NEW"
  CREATE_HOOKS="true"
  HOOKS_SOLE_TENANT="true"    # podcast created it and is its only tenant
  ledger_step "hooks-hostname" "CREATE" "will create $HOOKS_HOST (podcast sole tenant)"
fi
ledger_fact "hooks_host" "$HOOKS_HOST"
ledger_fact "hooks_sole_tenant" "$HOOKS_SOLE_TENANT"
ledger_fact "dash_host" "$DASH_HOST"
ledger_fact "intake_mapping" "$INTAKE_MAPPING"

# --------------------------------------------------------------------------- #
# STEP 1: tunnel ingress (remote-managed only; local-managed is box-side)
# --------------------------------------------------------------------------- #
if [ "$TUNNEL_SRC" = "cloudflare" ]; then
  PUT_BODY="$(printf '%s' "$CFG" | jq \
    --arg dash "$DASH_HOST" --arg dsvc "http://localhost:${DASH_PORT}" \
    --arg hooks "$HOOKS_HOST" --arg hsvc "http://127.0.0.1:${GATEWAY_PORT}" \
    --argjson create_hooks "$CREATE_HOOKS" '
    {config: (
      .result.config
      | (.ingress // []) as $ing
      | ($ing | map(select((.hostname // "") != $dash and ((.hostname // "") != $hooks or ($create_hooks|not))))) as $kept
      | ($kept | map(select(has("hostname")))) as $hosts
      | ($kept | map(select(has("hostname")|not))) as $catch
      | .ingress = (
          $hosts
          + [{hostname:$dash, service:$dsvc}]
          + (if $create_hooks then [{hostname:$hooks, service:$hsvc, path:"^/hooks/"}] else [] end)
          + (if ($catch|length) > 0 then $catch else [{service:"http_status:404"}] end)
        )
    )}')"
  IRESP="$(cf_write -X PUT "$API/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" --data "$PUT_BODY")"
  [ "$(ok_of "$IRESP")" = "true" ] || die 7 "ingress PUT failed: $(err_of "$IRESP")"
  ledger_step "ingress" "OK" "dashboard -> localhost:${DASH_PORT}$( [ "$CREATE_HOOKS" = "true" ] && printf '%s' "; hooks $HOOKS_HOST -> 127.0.0.1:${GATEWAY_PORT} (path ^/hooks/)" )"
else
  ledger_step "ingress" "PENDING" "tunnel is locally-managed (config.yml); operator must add on the box (as the node user): $DASH_HOST -> http://localhost:${DASH_PORT}$( [ "$CREATE_HOOKS" = "true" ] && printf '%s' "; $HOOKS_HOST -> http://127.0.0.1:${GATEWAY_PORT}" ), then restart cloudflared per fleet doctrine and re-run the gate"
fi

# --------------------------------------------------------------------------- #
# STEP 2: DNS CNAME(s) -> <tunnel-id>.cfargotunnel.com, proxied (edge; both modes)
# --------------------------------------------------------------------------- #
ensure_cname() {
  local host="$1"
  local expected="${TUNNEL_ID}.cfargotunnel.com"
  local existing rec_id content
  existing="$(cf "$API/zones/${ZONE_ID}/dns_records?name=${host}")"
  rec_id="$(printf '%s' "$existing" | jq -r '.result[0].id // empty')"
  content="$(printf '%s' "$existing" | jq -r '.result[0].content // empty')"
  if [ -n "$rec_id" ]; then
    if [ "$content" = "$expected" ]; then
      ledger_step "dns:${host}" "OK" "CNAME already correct -> $expected"
      return 0
    fi
    local r
    r="$(cf_write -X PUT "$API/zones/${ZONE_ID}/dns_records/${rec_id}" \
      --data "$(jq -n --arg n "$host" --arg c "$expected" '{type:"CNAME",name:$n,content:$c,proxied:true}')")"
    [ "$(ok_of "$r")" = "true" ] || { ledger_step "dns:${host}" "FAIL" "$(err_of "$r")"; return 1; }
    ledger_step "dns:${host}" "OK" "CNAME updated -> $expected"
  else
    local r
    r="$(cf_write -X POST "$API/zones/${ZONE_ID}/dns_records" \
      --data "$(jq -n --arg n "$host" --arg c "$expected" '{type:"CNAME",name:$n,content:$c,proxied:true}')")"
    [ "$(ok_of "$r")" = "true" ] || { ledger_step "dns:${host}" "FAIL" "$(err_of "$r")"; return 1; }
    ledger_step "dns:${host}" "OK" "CNAME created -> $expected (proxied)"
  fi
}
ensure_cname "$DASH_HOST" || die 8 "dashboard DNS failed"
if [ "$CREATE_HOOKS" = "true" ]; then ensure_cname "$HOOKS_HOST" || die 8 "hooks DNS failed"; fi

# --------------------------------------------------------------------------- #
# STEP 3: dashboard Access application (allow-by-email), idempotent
# --------------------------------------------------------------------------- #
APPS="$(cf "$API/accounts/${ACCOUNT_ID}/access/apps?per_page=100")"
APP_ID="$(printf '%s' "$APPS" | jq -r --arg d "$DASH_HOST" \
  '.result[]? | select((.domain // "")==$d or ((.self_hosted_domains // [])|index($d))) | .id' | head -n1)"

if [ -n "$APP_ID" ] && [ "$FORCE" = "1" ]; then
  cf_write -X DELETE "$API/accounts/${ACCOUNT_ID}/access/apps/${APP_ID}" >/dev/null
  ledger_step "access-app" "RECREATE" "deleted existing app $APP_ID (--force)"
  APP_ID=""
fi

if [ -n "$APP_ID" ]; then
  ledger_step "access-app" "REUSE" "existing app $APP_ID for $DASH_HOST"
else
  APP_BODY="$(jq -n --arg name "Podcast Dashboard - ${SLUG}" --arg dom "$DASH_HOST" \
    --arg sd "$SESSION_DURATION" --argjson inc "$INCLUDE_JSON" '
    {name:$name, domain:$dom, type:"self_hosted", session_duration:$sd,
     app_launcher_visible:false,
     policies:[{name:("Podcast Dashboard allow-list - " + $dom), decision:"allow", include:$inc}]}')"
  ARESP="$(cf_write -X POST "$API/accounts/${ACCOUNT_ID}/access/apps" --data "$APP_BODY")"
  [ "$(ok_of "$ARESP")" = "true" ] || die 9 "Access app create failed: $(err_of "$ARESP")"
  APP_ID="$(printf '%s' "$ARESP" | jq -r '.result.id // empty')"
  ledger_step "access-app" "OK" "created \"Podcast Dashboard - ${SLUG}\" id=${APP_ID:-dry-run} allow=${#ALL_EMAILS[@]} emails"
fi
[ -n "$APP_ID" ] && ledger_fact "access_app_id" "$APP_ID"

# --------------------------------------------------------------------------- #
# STEP 4: WAF POST-only rule on the hooks host (only for a new podcast-sole host).
# The zone entrypoint ruleset is SHARED by every client; GET, MERGE by ref, PUT.
# Never PUT a bare single-rule array (that would wipe the whole zone WAF).
# --------------------------------------------------------------------------- #
if [ "$CREATE_HOOKS" = "true" ]; then
  RS="$(cf "$API/zones/${ZONE_ID}/rulesets/phases/http_request_firewall_custom/entrypoint")"
  RULES_TYPE="$(printf '%s' "$RS" | jq -r '.result.rules | type' 2>/dev/null || echo "null")"
  if [ "$(ok_of "$RS")" = "true" ] && { [ "$RULES_TYPE" = "array" ] || [ "$RULES_TYPE" = "null" ]; }; then
    WAF_REF="podcast_hooks_${SLUG_REF}"
    WAF_EXPR="(http.host eq \"${HOOKS_HOST}\") and not (http.request.method eq \"POST\" and starts_with(http.request.uri.path, \"/hooks/\"))"
    MERGED="$(printf '%s' "$RS" | jq \
      --arg ref "$WAF_REF" --arg expr "$WAF_EXPR" --arg desc "Podcast hooks POST-only guard - ${SLUG}" '
      { rules: (
          ((.result.rules // []) | map(select((.ref // "") != $ref)) | map(del(.id,.version,.last_updated)))
          + [{expression:$expr, action:"block", description:$desc, ref:$ref, enabled:true}]
        )}')"
    WRESP="$(cf_write -X PUT "$API/zones/${ZONE_ID}/rulesets/phases/http_request_firewall_custom/entrypoint" --data "$MERGED")"
    if [ "$(ok_of "$WRESP")" = "true" ]; then
      ledger_step "waf" "OK" "POST-to-/hooks guard merged for $HOOKS_HOST (ref $WAF_REF)"
      ledger_fact "waf_ref" "$WAF_REF"
    else
      ledger_step "waf" "FAIL" "$(err_of "$WRESP"); hooks host left without the edge POST filter (route secret + ingress path scoping still apply)"
    fi
  else
    ledger_step "waf" "PENDING" "could not read the shared zone entrypoint ruleset safely; refusing to PUT (would risk clobbering other clients). Add the POST-only rule manually or re-run."
  fi
else
  ledger_step "waf" "SKIP" "hooks host reused/shared; not imposing a POST-only rule on a hostname other skills may use with other methods"
fi

# --------------------------------------------------------------------------- #
# STEP 5: box-side secrets (as the node user; confirmed SET, never printed)
# --------------------------------------------------------------------------- #
SECRETS_ENV_FILE="${SECRETS_ENV_FILE:-$HOME/.openclaw/secrets.env}"
ensure_secret() {
  local key="$1"
  if [ "$DRY_RUN" = "1" ]; then ledger_step "secret:${key}" "DRY-RUN" "would generate and store (value never printed)"; return 0; fi
  runas mkdir -p "$(dirname "$SECRETS_ENV_FILE")" 2>/dev/null || true
  if runas test -f "$SECRETS_ENV_FILE" && runas grep -qE "^${key}=" "$SECRETS_ENV_FILE" 2>/dev/null; then
    ledger_step "secret:${key}" "OK" "already SET (kept)"
    return 0
  fi
  local val; val="$(openssl rand -hex 32)"
  # shellcheck disable=SC2016  # single quotes intentional: the secret expands only inside the inner shell, never into the command string
  if runas bash -c 'umask 077; printf "%s=%s\n" "$0" "$1" >> "$2"' "$key" "$val" "$SECRETS_ENV_FILE"; then
    unset val
    if runas grep -qE "^${key}=" "$SECRETS_ENV_FILE" 2>/dev/null; then
      ledger_step "secret:${key}" "OK" "generated and SET (value never printed)"
    else
      ledger_step "secret:${key}" "FAIL" "write did not confirm SET"
    fi
  else
    unset val
    ledger_step "secret:${key}" "PENDING" "box not writable here (edge-only); generate on the box as the node user"
  fi
}
ensure_secret "PODCAST_INTAKE_HOOK_TOKEN"
ensure_secret "PODCAST_DASHBOARD_TOKEN"

# --------------------------------------------------------------------------- #
# STEP 6: delegated box-side wiring (owned by sibling slices). Invoke the helper
# when present; otherwise record PENDING so nothing is silently skipped.
# --------------------------------------------------------------------------- #
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

delegate() {
  local label="$1" helper="$2"; shift 2
  if [ "$DRY_RUN" = "1" ]; then ledger_step "$label" "DRY-RUN" "would run $helper"; return 0; fi
  if [ -x "$SCRIPT_DIR/$helper" ]; then
    if runas "$SCRIPT_DIR/$helper" "$@"; then ledger_step "$label" "OK" "$helper"; else ledger_step "$label" "FAIL" "$helper returned nonzero"; fi
  else
    ledger_step "$label" "PENDING" "$helper not present in this build (owned by a sibling slice); wire on the box"
  fi
}
delegate "hook-mapping"     "register-podcast-hook.sh"       "$SLUG" "$INTAKE_MAPPING"
delegate "dashboard-svc"    "deploy-podcast-dashboard.sh"    "$SLUG" "$DASH_PORT"
delegate "convertflow-card" "write-podcast-cf-field.sh"      "$SLUG" "https://${DASH_HOST}"

# smoke-test cron (furnace: exactly one per client, no-deliver, daily, founder-only)
provision_cron() {
  if [ "$DRY_RUN" = "1" ]; then ledger_step "smoke-cron" "DRY-RUN" "would add one daily 06:00 ${CLIENT_TZ} cron (--no-deliver)"; return 0; fi
  if command -v openclaw >/dev/null 2>&1 && [ -f "$SCRIPT_DIR/podcast-smoke-test.py" ]; then
    if runas openclaw cron add \
        --name "podcast-smoke-${SLUG}" \
        --schedule "0 6 * * *" --timezone "$CLIENT_TZ" \
        --command "python3 $SCRIPT_DIR/podcast-smoke-test.py $SLUG" \
        --no-deliver >/dev/null 2>&1; then
      # verify delivery mode is not announce (known CLI drift)
      if runas openclaw cron list 2>/dev/null | grep -A3 "podcast-smoke-${SLUG}" | grep -qi 'announce'; then
        ledger_step "smoke-cron" "FAIL" "created cron has announce delivery; must be no-deliver (would spam the client chat)"
      else
        ledger_step "smoke-cron" "OK" "one daily 06:00 ${CLIENT_TZ} cron, no-deliver"
      fi
    else
      ledger_step "smoke-cron" "PENDING" "openclaw cron add failed or unavailable here; create on the box"
    fi
  else
    ledger_step "smoke-cron" "PENDING" "openclaw CLI or podcast-smoke-test.py not present in this build; create the daily cron on the box (--no-deliver)"
  fi
}
provision_cron

# --------------------------------------------------------------------------- #
# PASS GATE
# --------------------------------------------------------------------------- #
GATE_HARD_FAIL="0"

# G1: dashboard returns 302 to the Access team host.
gate_302() {
  if [ "$DRY_RUN" = "1" ]; then ledger_step "gate:302-to-access" "DRY-RUN" "skipped in dry-run"; return 0; fi
  local i hdrs loc
  for i in 1 2 3 4 5; do
    hdrs="$(curl -sSI --max-time 15 "https://${DASH_HOST}" 2>/dev/null || true)"
    loc="$(printf '%s' "$hdrs" | tr -d '\r' | awk 'tolower($1)=="location:"{print $2}')"
    if printf '%s' "$hdrs" | grep -q ' 302' && printf '%s' "$loc" | grep -q "$ACCESS_TEAM_HOST"; then
      ledger_step "gate:302-to-access" "PASS" "302 -> $ACCESS_TEAM_HOST"
      return 0
    fi
    sleep $((i*5))
  done
  ledger_step "gate:302-to-access" "FAIL" "no 302 to $ACCESS_TEAM_HOST yet (DNS/ingress may still be propagating, or the tunnel is locally-managed)"
  GATE_HARD_FAIL="1"
}
gate_302

# G2: signed hook test POST (requires the box-side mapping + token; PENDING if not wired).
gate_hook() {
  if [ "$DRY_RUN" = "1" ]; then ledger_step "gate:signed-hook" "DRY-RUN" "skipped in dry-run"; return 0; fi
  local tok=""
  if runas test -f "$SECRETS_ENV_FILE" 2>/dev/null; then
    # shellcheck disable=SC2016  # single quotes intentional: sourced only inside the inner shell; the token is never interpolated into the command string
    tok="$(runas bash -c 'set -a; . "$0" >/dev/null 2>&1; printf "%s" "${PODCAST_INTAKE_HOOK_TOKEN:-}"' "$SECRETS_ENV_FILE" 2>/dev/null)"
  fi
  if [ -z "$tok" ]; then
    ledger_step "gate:signed-hook" "PENDING" "intake token not available here; run once the hook mapping and token are wired on the box"
    return 0
  fi
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
    -X POST "https://${HOOKS_HOST}/hooks/${INTAKE_MAPPING}" \
    -H "Authorization: Bearer ${tok}" -H "Content-Type: application/json" \
    --data '{"_test":true,"source":"provision-gate"}' 2>/dev/null || echo "000")"
  unset tok
  if printf '%s' "$code" | grep -Eq '^2[0-9][0-9]$'; then
    ledger_step "gate:signed-hook" "PASS" "signed test POST accepted (HTTP $code)"
  else
    ledger_step "gate:signed-hook" "PENDING" "hook not accepting yet (HTTP $code); confirm the mapping is registered on the box"
  fi
}
gate_hook

# G3: fire the smoke-test cron once.
gate_smoke() {
  if [ "$DRY_RUN" = "1" ]; then ledger_step "gate:smoke-fire" "DRY-RUN" "skipped in dry-run"; return 0; fi
  if command -v openclaw >/dev/null 2>&1 && [ -f "$SCRIPT_DIR/podcast-smoke-test.py" ]; then
    if runas python3 "$SCRIPT_DIR/podcast-smoke-test.py" "$SLUG" >/dev/null 2>&1; then
      ledger_step "gate:smoke-fire" "PASS" "smoke test ran once"
    else
      ledger_step "gate:smoke-fire" "FAIL" "smoke test returned nonzero"
    fi
  else
    ledger_step "gate:smoke-fire" "PENDING" "smoke test not present in this build; fire once after wiring"
  fi
}
gate_smoke

# G4: Access allow-list read-back diff (naming + exact email set).
gate_allowlist() {
  if [ "$DRY_RUN" = "1" ] || [ -z "$APP_ID" ]; then ledger_step "gate:allowlist-diff" "DRY-RUN" "skipped (dry-run or no app id)"; return 0; fi
  local pol got want
  pol="$(cf "$API/accounts/${ACCOUNT_ID}/access/apps/${APP_ID}/policies")"
  got="$(printf '%s' "$pol" | jq -r '[.result[]? | select(.decision=="allow") | .include[]? | .email.email // empty] | sort | unique | join(",")')"
  want="$(printf '%s\n' "${ALL_EMAILS[@]}" | sort | uniq | paste -sd, -)"
  if [ "$got" = "$want" ]; then
    ledger_step "gate:allowlist-diff" "PASS" "allow-list matches intended set (${#ALL_EMAILS[@]} emails)"
  else
    ledger_step "gate:allowlist-diff" "FAIL" "allow-list drift: got [$got] want [$want]"
    GATE_HARD_FAIL="1"
  fi
}
gate_allowlist

# --------------------------------------------------------------------------- #
# Finish
# --------------------------------------------------------------------------- #
if [ "$GATE_HARD_FAIL" = "1" ]; then
  ledger_finish "edge-incomplete"
  log "Provision finished with hard gate failures; see the report above. Box-side PENDING items are expected when running edge-first."
  exit 20
fi
ledger_finish "ok"
log "Provision OK (edge live). Any PENDING items are box-side steps owned by sibling slices; complete them on the box, then re-run to green the full gate."
exit 0
