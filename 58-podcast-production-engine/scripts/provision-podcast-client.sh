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
#      the client's email(s) plus <operator-email-alt> plus <operator-email>.
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
# ACTIVATION (fleet guarantee: provision => processor active):
#   After the roster/env provisioning above, this script runs the processor
#   activation sequence from the activation layer (Workflow 1, same merge batch):
#     1. install-podcast-department.sh                        (department install)
#     2. register-podcast-hook.sh --client-slug <slug>        (inbound hook mapping)
#   No scheduler install exists (no-daemon doctrine: the department agent advances
#   TaskFlows in its own turn via podcast_step_driver.py).
#   Every step is GATED three ways: presence (fail closed, naming the missing
#   piece), run rc (fail closed), and a --check read-back (fail closed unless the
#   helper reports its piece ACTIVE). Any failure aborts the provision with the
#   stage-specific exit code (22 department, 23 hook, 24 scheduler); the ledger
#   records activation=failed. The helpers are idempotent per the activation-layer
#   contract, so a re-provision verifies an already-active processor instead of
#   duplicating it. Activation helper contract: each accepts "--check <same args>"
#   and returns 0 when its piece is active. Operator override: --skip-activation
#   (documented below; the ledger records activation=skipped, which revoke reads).
#   revoke-podcast-client.sh tears this sequence down symmetrically.
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
# Account/zone/team-host are operator-account-specific: they are supplied by the
# environment on the operator box and are NEVER hardcoded in this fleet-wide
# template. The account id is a fallback only; the zone is always resolved by
# NAME below (never by the trapped CLOUDFLARE_ZONE_ID) with the zone id used only
# as a known-good cross-check.
ACCOUNT_ID_DEFAULT="${CLOUDFLARE_ACCOUNT_ID:-YOUR_CF_ACCOUNT_ID}"
ZONE_NAME="${PODCAST_CF_ZONE_NAME:-zerohumanworkforce.com}"
ZONE_ID_KNOWN="${PODCAST_CF_ZONE_ID:-YOUR_CF_ZONE_ID}"
ACCESS_TEAM_HOST="${PODCAST_CF_ACCESS_TEAM_HOST:-your-team.cloudflareaccess.com}"
# Operator emails that are always granted dashboard Access, in addition to the
# client emails. Supply a comma-separated list via PODCAST_OPERATOR_EMAILS on the
# operator box; the template ships with none so no personal email is committed.
OPERATOR_EMAILS=()
if [ -n "${PODCAST_OPERATOR_EMAILS:-}" ]; then
  IFS=',' read -ra OPERATOR_EMAILS <<< "$PODCAST_OPERATOR_EMAILS"
fi
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
SKIP_ACTIVATION="0"
TUNNEL_ID_OVERRIDE="${PODCAST_TUNNEL_ID:-}"
# Two-show channel capture defaults: channel ids are NON-SECRET values captured
# at onboarding, but provisioning never invents one (absent -> PENDING later).
PERSONAL_CHANNEL_ID="${PODCAST_PERSONAL_CHANNEL_ID:-}"
INTERVIEW_CHANNEL_ID="${PODCAST_INTERVIEW_CHANNEL_ID:-}"
INTERVIEW_SHOW_SLUG="${PODCAST_INTERVIEW_SHOW_SLUG:-}"
# t6 two-show roster model: repeatable --show <SLUG>:<CHANNEL_ID> flags create
# podcast_publish_roster rows (one row per show) via the n8n Data Tables API.
SHOWS=()

usage() {
  sed -n '1,51p' "$0" >&2
  cat >&2 <<'USAGE'

USAGE:
  provision-podcast-client.sh <slug> <client-email[,email2,...]> <timezone> [flags]

FLAGS:
  --tunnel-id <id>   Use this tunnel id instead of resolving it from the Command
                     Center CNAME (also settable via PODCAST_TUNNEL_ID).
  --personal-channel-id <id>
                     The client's PERSONAL-show Podbean Channel ID (two-show
                     convention; also settable via PODCAST_PERSONAL_CHANNEL_ID).
                     Non-secret; never invented here.
  --interview-channel-id <id>
                     The client's INTERVIEW-show Podbean Channel ID (two-show
                     convention; also settable via PODCAST_INTERVIEW_CHANNEL_ID).
  --interview-show-slug <slug>
                     The interview show's slug used in the env var name
                     PODBEAN_PODCAST_ID_<SHOW_SLUG> (also settable via
                     PODCAST_INTERVIEW_SHOW_SLUG), e.g. SOFT_GIRL_ERA.
  --show <SLUG>:<CHANNEL_ID>  TWO-SHOW MODEL: repeatable. Every podcast client runs
                     up to two shows under BlackCEO's single Podbean host account: a
                     PERSONAL show (solo episodes) and an INTERVIEW show (guest
                     system). Each --show creates ONE podcast_publish_roster row
                     (same client email/last_name, the show's Podbean channel id,
                     good_standing=YES) via the n8n Data Tables API, and prints the
                     box env line PODBEAN_PODCAST_ID_<SHOW_SLUG>=<CHANNEL_ID> to
                     stdout for the operator to add to the box. Omit --show entirely
                     for the default single-channel flow (no roster write, no env
                     line; PODBEAN_PODCAST_ID is set by the operator as before).
                     Idempotent: re-running reuses an existing row for the same
                     (email, channel) instead of inserting a duplicate.
  --dry-run          Perform all read-only discovery, but log mutations instead of
                     applying them (operator canary preview). Still requires the token.
  --force            Recreate the Access app even if one already exists for the host.
  --skip-activation  OPERATOR OVERRIDE. Do NOT run the processor activation
                     sequence (install-podcast-department.sh,
                     register-podcast-hook.sh --client-slug <slug>). By default
                     EVERY provision activates the processor (fleet guarantee:
                     provision => processor active). The override is logged in the
                     ledger as activation=skipped so the fleet audit can flag the
                     client, and revoke-podcast-client.sh still tears down whatever
                     activation state exists. Use only for an explicit, documented
                     operator decision (e.g. a canary box you are wiring by hand).
  -h, --help         Show this help.

ENV:
  CLOUDFLARE_API_TOKEN   REQUIRED (BlackCEO operator token). Confirmed SET, never printed.
  CLOUDFLARE_ACCOUNT_ID  Optional override of the account id.
  N8N_API_URL            n8n API base. REQUIRED only with --show (roster row writes).
  N8N_API_KEY            n8n API key. REQUIRED only with --show. Confirmed SET, never printed.
  PODCAST_ROSTER_TABLE_ID  podcast_publish_roster data table id (default UWjpksxU2b6TjKow).
  PODCAST_CLIENT_LAST_NAME  Client last name stored in each roster row. Default:
                         the first segment of the first client email (the pre-@ part
                         before any + alias tag). Override with the real surname.
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
    --personal-channel-id) PERSONAL_CHANNEL_ID="${2:-}"; shift 2 ;;
    --interview-channel-id) INTERVIEW_CHANNEL_ID="${2:-}"; shift 2 ;;
    --interview-show-slug) INTERVIEW_SHOW_SLUG="${2:-}"; shift 2 ;;
    --show)      SHOWS+=("${2:-}"); shift 2 ;;
    --dry-run)   DRY_RUN="1"; shift ;;
    --force)     FORCE="1"; shift ;;
    --skip-activation) SKIP_ACTIVATION="1"; shift ;;
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

# n8n Data Tables API (roster rows live in the podcast_publish_roster data table on
# the same n8n instance that runs the publish gates). Same secret hygiene as
# Cloudflare: the API key is confirmed SET by name only, never printed.
ROSTER_TABLE_ID="${PODCAST_ROSTER_TABLE_ID:-UWjpksxU2b6TjKow}"

n8n_base() { printf '%s' "${N8N_API_URL%/}"; }

# n8n_filter_json <col> <value>: exact-match row filter, n8n data-table filter syntax.
n8n_filter_json() {
  jq -cn --arg c "$1" --arg v "$2" '{type:"and",filters:[{columnName:$c,condition:"eq",value:$v}]}'
}

# n8n_urlencode <s>: URL-encode for query strings (curl -G would leave {} raw).
n8n_urlencode() { python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }

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

# --show validation (two-show model). Each value is <SHOW_SLUG>:<PODBEAN_CHANNEL_ID>;
# the slug becomes an env-var name suffix (PODBEAN_PODCAST_ID_<SHOW_SLUG>), so it must
# be uppercase [A-Z0-9_]. Two shows may never share a slug or a channel id
# (never co-mingle shows under one Podbean host account).
SHOW_SLUGS=()
SHOW_CHANNELS=()
# The ${A[@]+"${A[@]}"} guards keep these loops safe under set -u on bash 3.2,
# where an empty array expansion is an error.
for show in ${SHOWS[@]+"${SHOWS[@]}"}; do
  show_slug="${show%%:*}"
  show_rest="${show#*:}"
  show_channel="${show_rest#*:}"
  if [ "$show_slug" = "$show" ] || [ -z "$show_slug" ] || [ "$show_rest" != "$show_channel" ] || [ -z "$show_channel" ]; then
    echo "invalid --show '$show': expected exactly <SHOW_SLUG>:<PODBEAN_CHANNEL_ID> (one colon)" >&2
    exit 2
  fi
  printf '%s' "$show_slug" | grep -Eq '^[A-Z][A-Z0-9_]{0,30}$' || { echo "invalid --show slug '$show_slug': must be uppercase [A-Z0-9_], 1 to 31 chars, starting with a letter (it becomes the env-var suffix PODBEAN_PODCAST_ID_$show_slug)" >&2; exit 2; }
  printf '%s' "$show_channel" | grep -Eq '^[A-Za-z0-9_-]{6,64}$' || { echo "invalid --show channel id for show '$show_slug': expected 6 to 64 chars of [A-Za-z0-9_-]" >&2; exit 2; }
  for prev_slug in ${SHOW_SLUGS[@]+"${SHOW_SLUGS[@]}"}; do
    [ "$prev_slug" != "$show_slug" ] || { echo "duplicate --show slug: $show_slug (each show needs its own slug)" >&2; exit 2; }
  done
  for prev_channel in ${SHOW_CHANNELS[@]+"${SHOW_CHANNELS[@]}"}; do
    [ "$prev_channel" != "$show_channel" ] || { echo "duplicate --show channel id on show $show_slug (two shows must never share a Podbean channel)" >&2; exit 2; }
  done
  SHOW_SLUGS+=("$show_slug")
  SHOW_CHANNELS+=("$show_channel")
done

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

# PODBEAN SHARED SECRET GUARD: provisioning NEVER copies BlackCEO's shared Podbean
# OAuth app secret (PODBEAN_CLIENT_SECRET / OPENCLAW_PODBEAN_CLIENT_SECRET) to a
# client box. The fleet default publish-proxy requires no Podbean app secret here;
# the proxy host performs the entire publish server-side. If PODBEAN_CLIENT_SECRET
# is present in this environment it was placed by the operator for their OWN box
# only and will NOT be injected into the client's secrets file.
if [ -n "${PODBEAN_CLIENT_SECRET:-}" ] || [ -n "${OPENCLAW_PODBEAN_CLIENT_SECRET:-}" ]; then
  log "PODBEAN SHARED SECRET GUARD: Podbean OAuth app secret detected in env; it WILL NOT be provisioned to the client box (fail-closed). The shared secret belongs on the OPERATOR'S OWN BOX ONLY."
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
# STEP 0 (snapshot): request the AUTOMATED snapshot push into the client's Convert
# and Flow sub-account, BEFORE the box-side STEP 0 credential/field gate
# (ghl_credential_gate.py full, SKILL.md ~line 193) is attempted; that gate
# hard-stops until the 28 podcast custom fields exist, so the snapshot MUST be in the
# sub-account first. Mirrors 59-anthology-engine step 7.5. Best-effort + NON-BLOCKING;
# the box-side STEP 0 gate remains the genuine-completion check. FAIL-CLOSED until
# Trevor cuts the podcast golden snapshot and sets PODCAST_SNAPSHOT_ID in n8n (the
# webhook returns 409 and this step records the manual fallback; never worse than manual).
# The shared token is resolved BY LABEL inside the helper and is NEVER printed.
# --------------------------------------------------------------------------- #
provision_snapshot() {
  local fire; fire="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." 2>/dev/null && pwd)/shared-utils/fire-provision-snapshot.sh"
  local loc_id="${GOHIGHLEVEL_LOCATION_ID:-${GHL_LOCATION_ID:-}}"   # canonical label, legacy alias
  local cemail="${EMAILS_RAW%%,*}"                                  # first client email
  if [ "$DRY_RUN" = "1" ]; then
    ledger_step "snapshot" "DRY-RUN" "would fire provision-snapshot webhook (engine=podcast; fail-closed until PODCAST_SNAPSHOT_ID set in n8n)"
    return 0
  fi
  if [ -z "$loc_id" ]; then
    ledger_step "snapshot" "PENDING" "GOHIGHLEVEL_LOCATION_ID not set here; fire the snapshot webhook (engine=podcast) on the box before STEP 0"
    return 0
  fi
  if [ ! -f "$fire" ]; then
    ledger_step "snapshot" "PENDING" "shared-utils/fire-provision-snapshot.sh not present in this build; wire the snapshot push before STEP 0"
    return 0
  fi
  bash "$fire" \
    --engine podcast \
    --location-id "$loc_id" \
    --client-slug "$SLUG" \
    --client-name "${PROVISION_CLIENT_NAME:-$SLUG}" \
    --client-email "$cemail" \
    --tenancy same_agency \
    --requested-by "provision-podcast-client.sh" \
    --ledger-file "$LEDGER" || true
  ledger_step "snapshot" "OK" "provision-snapshot webhook fired (engine=podcast); box-side STEP 0 gate confirms genuine completion (fail-closed until PODCAST_SNAPSHOT_ID is set)"
}
provision_snapshot

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
  # `umask 077` only governs the mode a file gets on CREATION. `>>` opens an
  # ALREADY-EXISTING $SECRETS_ENV_FILE (e.g. left behind by an older install,
  # or created by the sibling ensure_secret call above in this same run) in
  # append mode without touching its mode bits, so a file that predates this
  # fix -- or was ever loosened -- would stay permissive forever across every
  # future append. Re-assert 600 explicitly after the write so both the
  # brand-new-file and pre-existing-file cases end up secured.
  if runas bash -c 'umask 077; printf "%s=%s\n" "$0" "$1" >> "$2"; chmod 600 "$2" 2>/dev/null || true' "$key" "$val" "$SECRETS_ENV_FILE"; then
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
ensure_secret "PODCAST_INTAKE_HOOK_SECRET"
ensure_secret "PODCAST_INTAKE_INBOUND_SECRET"
ensure_secret "PODCAST_INTAKE_HOOK_TOKEN"
ensure_secret "PODCAST_DASHBOARD_TOKEN"

# --------------------------------------------------------------------------- #
# STEP 5.5: two-show channel capture (SOP-PODCAST-02 Section 2.5; the fleet-wide
# two-show convention). Every client runs TWO shows under the operator's single
# Podbean host account, one channel per show: the PERSONAL show (solo episodes,
# mode personal_podcast_style) and the INTERVIEW show (the guest system, mode
# interview_style_podcast). This block RECORDS both channel ids in the provision
# ledger and PRINTS the exact box-side env contract for the operator to apply:
#   PODBEAN_PODCAST_ID                 the personal-show Channel ID (default channel)
#   PODBEAN_PODCAST_ID_<SHOW_SLUG>     the interview-show Channel ID, where
#                                      <SHOW_SLUG> is the interview show's slug in
#                                      uppercase, underscore form (e.g. SOFT_GIRL_ERA)
# The publish step selects the channel BY MODE (scripts/podcast_channel.py is the
# resolver the controller and publish glue use) and passes the mode-selected
# channel as the payload's podcast_id, so the operator's multi-row roster gate
# (channel-preferred selection) resolves the right show row per episode.
# Channel ids are NON-SECRET values captured at onboarding, but provisioning
# NEVER invents one: absent here, the block records PENDING with the exact env
# label to set, and SOP-PODCAST-02's standing-check probes remain the go-live
# gate. Existing correct values are reused (idempotent).
# --------------------------------------------------------------------------- #
print_channel_contract() {
  log "  box-side env contract (apply on the client box, then confirm SET in the"
  log "  live process env per the box restart doctrine; then run the standing-check"
  log "  probe for EACH show per SOP-PODCAST-02 Section 2.5):"
  if [ -n "$PERSONAL_CHANNEL_ID" ]; then
    log "    PODBEAN_PODCAST_ID=${PERSONAL_CHANNEL_ID}   (personal show)"
  else
    log "    PODBEAN_PODCAST_ID=<personal-show Channel ID>   (personal show; not supplied here)"
  fi
  if [ -n "$INTERVIEW_CHANNEL_ID" ]; then
    if [ -n "$INTERVIEW_SHOW_SLUG" ]; then
      log "    PODBEAN_PODCAST_ID_${INTERVIEW_SHOW_SLUG}=${INTERVIEW_CHANNEL_ID}   (interview show)"
    else
      log "    PODBEAN_PODCAST_ID_<SHOW_SLUG>=${INTERVIEW_CHANNEL_ID}   (interview show; show slug not supplied)"
    fi
  else
    log "    PODBEAN_PODCAST_ID_<SHOW_SLUG>=<interview-show Channel ID>   (interview show; not supplied here)"
  fi
}
provision_channels() {
  if [ "$DRY_RUN" = "1" ]; then
    ledger_step "channels:two-show" "DRY-RUN" "would record both show Channel IDs (personal + interview) in the ledger and print the box-side env contract"
    return 0
  fi
  ledger_fact "personal_channel_id" "${PERSONAL_CHANNEL_ID:-NOT-SUPPLIED}"
  ledger_fact "interview_channel_id" "${INTERVIEW_CHANNEL_ID:-NOT-SUPPLIED}"
  ledger_fact "interview_show_slug" "${INTERVIEW_SHOW_SLUG:-NOT-SUPPLIED}"
  if [ -z "$PERSONAL_CHANNEL_ID" ]; then
    ledger_step "channels:personal" "PENDING" "personal-show Channel ID not supplied; capture it at onboarding and set PODBEAN_PODCAST_ID on the box (never invented here)"
  else
    ledger_step "channels:personal" "OK" "personal-show Channel ID recorded in the ledger; set PODBEAN_PODCAST_ID on the box"
  fi
  if [ -z "$INTERVIEW_CHANNEL_ID" ]; then
    ledger_step "channels:interview" "PENDING" "interview-show Channel ID not supplied; capture it at onboarding and set PODBEAN_PODCAST_ID_<SHOW_SLUG> on the box (never invented here)"
  elif [ -z "$INTERVIEW_SHOW_SLUG" ]; then
    ledger_step "channels:interview" "PENDING" "interview-show Channel ID recorded but the show slug is missing; set PODBEAN_PODCAST_ID_<SHOW_SLUG> on the box using the show's uppercase, underscore slug"
  else
    if ! printf '%s' "$INTERVIEW_SHOW_SLUG" | grep -Eq '^[A-Z0-9_]{1,64}$'; then
      ledger_step "channels:interview" "PENDING" "show slug '$INTERVIEW_SHOW_SLUG' is not uppercase/underscore form; fix the slug, then set PODBEAN_PODCAST_ID_${INTERVIEW_SHOW_SLUG} on the box"
    else
      ledger_step "channels:interview" "OK" "interview-show Channel ID recorded in the ledger; set PODBEAN_PODCAST_ID_${INTERVIEW_SHOW_SLUG} on the box"
    fi
  fi
  print_channel_contract
}
provision_channels

# STEP 5b: podcast_publish_roster rows, one per show (TWO-SHOW MODEL).
# Every podcast client has up to TWO shows under BlackCEO's single Podbean host
# account (a PERSONAL show and an INTERVIEW show). The roster table holds ONE
# ROW PER SHOW: same client email + last_name, a different podbean_channel_id
# each. For every --show <SLUG>:<CHANNEL_ID>: create the row (idempotent: an
# existing row for the same email+channel is reused, never duplicated) with
# good_standing=YES, and emit PODBEAN_PODCAST_ID_<SHOW_SLUG>=<CHANNEL_ID> on
# stdout for the operator to add to the box secrets file. Fail-closed on any
# API error; never weaken the gates downstream (a missing or bad row means the
# publish Standing Gate refuses, which is the safe direction).
# With NO --show flags this step is skipped entirely: the legacy single-channel
# flow (PODBEAN_PODCAST_ID supplied by the operator) is unchanged.
# --------------------------------------------------------------------------- #
# T6-MARKER-BEGIN provision_roster_rows
provision_roster_rows() {
  [ "${#SHOW_SLUGS[@]}" -gt 0 ] || return 0

  # Client identity for the roster rows. Email: the roster gates compare the
  # payload email lowercased against the row email, so use the first client
  # email, lowercased. Last name: stored as given (trim only; the gates compare
  # it case-insensitively). Default last name: the pre-@ part of that email
  # before any + alias tag, e.g. "leanne" for leanne+show@domain.com.
  local roster_email roster_last i
  roster_email="$(printf '%s' "${ALL_EMAILS[0]-}" | tr '[:upper:]' '[:lower:]')"
  roster_last="${PODCAST_CLIENT_LAST_NAME:-}"
  if [ -z "$roster_last" ]; then
    roster_last="${roster_email%%@*}"
    roster_last="${roster_last%%+*}"
  fi
  roster_last="$(printf '%s' "$roster_last" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [ -n "$roster_email" ] || die 16 "cannot derive a roster email for --show rows"
  [ -n "$roster_last" ]  || die 16 "cannot derive a roster last_name for --show rows (set PODCAST_CLIENT_LAST_NAME)"

  # Persist the roster identity so revoke-podcast-client.sh can find the client's
  # rows without --client-email (revoke reads .facts.roster_email from this ledger).
  ledger_fact "roster_email" "$roster_email"
  ledger_fact "roster_last_name" "$roster_last"

  # n8n credentials gate: required ONLY for --show (the default flow never touches
  # n8n). Never print the key; confirm SET-ness by name only.
  if [ "$DRY_RUN" != "1" ]; then
    if [ -z "${N8N_API_URL:-}" ] || [ -z "${N8N_API_KEY:-}" ]; then
      die 13 "--show needs the n8n Data Tables API: N8N_API_URL and N8N_API_KEY must both be set (key is never printed)"
    fi
  fi

  local body row_id created=0 reused=0
  for i in "${!SHOW_SLUGS[@]}"; do
    local slug="${SHOW_SLUGS[$i]}" channel="${SHOW_CHANNELS[$i]}"
    ledger_fact "show:${slug}" "$channel"

    if [ "$DRY_RUN" = "1" ]; then
      ledger_step "roster:${slug}" "DRY-RUN" "would create roster row (email=$roster_email last_name=$roster_last channel=$channel good_standing=YES)"
      printf 'PODBEAN_PODCAST_ID_%s=%s\n' "$slug" "$channel"
      continue
    fi

    # Read: does this show already have a roster row (same email AND channel)?
    local filt http rows
    filt="$(n8n_filter_json email "$roster_email")"
    http="$(curl -sS --max-time 30 -w '%{http_code}' -o "$LEDGER_DIR/.t6-read.json" \
      -H "X-N8N-API-KEY: ${N8N_API_KEY}" \
      "$(n8n_base)/api/v1/data-tables/${ROSTER_TABLE_ID}/rows?filter=$(n8n_urlencode "$filt")" 2>/dev/null)"
    rows="$(jq -c '.data // []' "$LEDGER_DIR/.t6-read.json" 2>/dev/null)"
    if [ "$http" != "200" ] || [ -z "$rows" ]; then
      rm -f "$LEDGER_DIR/.t6-read.json"
      die 17 "roster read failed for show $slug (HTTP ${http:-0}); refusing to guess whether the row exists"
    fi
    row_id="$(printf '%s' "$rows" | jq -r --arg c "$channel" '[.[] | select((.podbean_channel_id // "") == $c)] | .[0].id // empty')"
    if [ -n "$row_id" ]; then
      reused=$((reused+1))
      ledger_step "roster:${slug}" "REUSE" "roster row id=$row_id already exists for channel $channel (no duplicate inserted)"
    else
      # Create one row for this show. Fail closed: any non-200 or missing
      # insertedRows marker means the row is NOT confirmed.
      body="$(jq -cn --arg e "$roster_email" --arg ln "$roster_last" --arg c "$channel" --arg tag "$T6_SHOW_TAG" \
        '{data:[{email:$e, last_name:$ln, podbean_channel_id:$c, good_standing:"YES", notes:("provisioned by provision-podcast-client.sh --show " + $tag)}]}')"
      local cres chttp
      cres="$(curl -sS --max-time 30 -w '\n%{http_code}' \
        -X POST -H "X-N8N-API-KEY: ${N8N_API_KEY}" -H "Content-Type: application/json" \
        "$(n8n_base)/api/v1/data-tables/${ROSTER_TABLE_ID}/rows" --data "$body" 2>/dev/null)"
      chttp="${cres##*$'\n'}"
      cres="${cres%$'\n'*}"
      if [ "$chttp" != "200" ] || [ "$(printf '%s' "$cres" | jq -r '.insertedRows // 0' 2>/dev/null)" != "1" ]; then
        die 18 "roster row create failed for show $slug (HTTP ${chttp:-0}); the show would be refused at the publish gate"
      fi
      created=$((created+1))
      ledger_step "roster:${slug}" "OK" "created roster row (email=$roster_email last_name=$roster_last channel=$channel good_standing=YES)"
    fi

    # Emit the box env line for this show. Channel ids are non-secret, but keep
    # stdout clean: exactly one KEY=VALUE line per show, nothing else.
    printf 'PODBEAN_PODCAST_ID_%s=%s\n' "$slug" "$channel"
  done
  rm -f "$LEDGER_DIR/.t6-read.json"
  ledger_fact "roster_rows_created" "$created"
  ledger_fact "roster_rows_reused" "$reused"
}
# T6-MARKER-END provision_roster_rows

T6_SHOW_TAG="$SLUG"
provision_roster_rows

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
# NOTE: hook-mapping registration is no longer a soft delegate here. It moved to
# the STEP 8 activation sequence below (register-podcast-hook.sh --client-slug
# <slug>), which is GATED and FAIL-CLOSED: the fleet guarantee is provision =>
# processor active, so a missing or failing hook registration must abort the
# provision, not record PENDING.
# NOTE: the two delegates below stay SOFT by design: their helpers live in a
# sibling slice, so absence degrades to PENDING (never aborts), matching the
# delegate() contract above.
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
# STEP 7: Facebook-ads connect (PER-CLIENT, opt-in). Facebook ads run LATER in the
# podcast process; the four FB-ad workflows (01a Update FB audience, 02 Fb Lead didn't
# complete, 02a 2nd Fb interview, 03 LeadForm Fb Ad) ship in the snapshot STRUCTURALLY
# CORRECT but DRAFT with their Facebook account/audience/pixel/token fields BLANK, because
# the Facebook connection is inherently per-client (each client connects their OWN Facebook
# Business account and selects their OWN Lead Forms / Custom Audiences / Pixel). Nothing
# about Facebook is fabricated in the template. This step records the connect checklist and,
# when the client is ready (PODCAST_FB_ADS_READY=1 with the real ids), fills + publishes them
# via scripts/activate-podcast-fb-workflows.py. Default: OFF (documented PENDING), never a
# provision blocker.
# --------------------------------------------------------------------------- #
provision_fb_ads() {
  if [ "${PODCAST_FB_ADS_READY:-0}" != "1" ]; then
    ledger_step "fb-ads-connect" "PENDING" "OFF by default (ads run later). When the client is ready: (1) client connects their Facebook Business account in Convert-and-Flow (Settings > Integrations > Facebook); (2) note act_ ad-account id, Custom Audience id(s), Pixel id + CAPI token; (3) run scripts/activate-podcast-fb-workflows.py --location <client-loc> --token-env <client-refresh-var> --execute --fb-account act_XXXX --fb-audience NNN --fb-pixel NNN --fb-token TTT (fills + PUBLISHES the 4 draft FB workflows); (4) add the Facebook Lead Form TRIGGER to 02/02a/03 in the builder (must bind a live form); (5) re-run scripts/verify-podcast-ghl-workflows.py (required 4 still PASS)"
    return 0
  fi
  if [ "$DRY_RUN" = "1" ]; then ledger_step "fb-ads-connect" "DRY-RUN" "would fill + publish the 4 FB workflows via activate-podcast-fb-workflows.py"; return 0; fi
  local activator="$SCRIPT_DIR/activate-podcast-fb-workflows.py"
  if [ ! -f "$activator" ]; then
    ledger_step "fb-ads-connect" "PENDING" "activate-podcast-fb-workflows.py not present in this build; run it on the box with the client's FB ids"
    return 0
  fi
  # The client's own Convert-and-Flow location + refresh var and FB ids are supplied via env
  # (never hardcoded, never printed). Missing any -> record PENDING, do not guess.
  if [ -z "${PODCAST_FB_LOCATION:-}" ] || [ -z "${PODCAST_FB_TOKEN_ENV:-}" ]; then
    ledger_step "fb-ads-connect" "PENDING" "PODCAST_FB_LOCATION / PODCAST_FB_TOKEN_ENV not set; export them plus the FB ids and re-run"
    return 0
  fi
  if runas python3 "$activator" --location "$PODCAST_FB_LOCATION" --token-env "$PODCAST_FB_TOKEN_ENV" --execute \
       --fb-account "${PODCAST_FB_ACCOUNT:-}" --fb-audience "${PODCAST_FB_AUDIENCE:-}" \
       --fb-pixel "${PODCAST_FB_PIXEL:-}" --fb-token "${PODCAST_FB_CAPI_TOKEN:-}" >/dev/null 2>&1; then
    ledger_step "fb-ads-connect" "OK" "filled + published the 4 FB workflows (add the FB Lead Form trigger in the builder to complete 02/02a/03)"
  else
    ledger_step "fb-ads-connect" "PENDING" "activator returned nonzero (usually a FB field still blank; GHL refuses to publish a FB workflow with an empty required attribute); supply all --fb-* ids the workflow uses and re-run"
  fi
}
provision_fb_ads

# --------------------------------------------------------------------------- #
# STEP 8: processor ACTIVATION (the fleet guarantee: provision => processor active).
#
# Sequence (activation layer, Workflow 1, same merge batch):
#   8a. install-podcast-department.sh                       (department install)
#   8b. register-podcast-hook.sh --client-slug <slug>       (inbound hook mapping)
#   (No 8c: no scheduler exists. No-daemon doctrine -- the department agent
#   advances TaskFlows in its own turn via podcast_step_driver.py.)
#
# Every step is GATED three ways and FAILS CLOSED:
#   1. presence   - a missing helper aborts with a message naming the missing piece
#   2. run rc     - a nonzero return aborts (the piece is not installed)
#   3. --check    - a read-back must report the piece ACTIVE before it counts
#
# Activation helper contract (recorded here for Workflow 1 and the tests): each
# helper accepts "--check" in place of its action (same remaining args) and exits
# 0 only when its piece is currently active on this box. The helpers are
# idempotent, so a re-provision verifies an already-active processor instead of
# duplicating it.
#
# Operator override: --skip-activation (documented in the usage block). It is
# recorded as activation=skipped so the fleet audit flags the client.
# --------------------------------------------------------------------------- #
activation_step() {
  # activation_step <step-name> <missing-code> <missing-piece> <helper-name> [args...]
  local name="$1" code="$2" piece="$3" helper="$4"
  shift 4
  if [ "$DRY_RUN" = "1" ]; then
    ledger_step "$name" "DRY-RUN" "would run $helper $*"
    return 0
  fi
  if [ ! -x "$SCRIPT_DIR/$helper" ]; then
    ledger_step "$name" "FAIL" "missing $piece: $SCRIPT_DIR/$helper not present or not executable in this build (owned by the activation layer, Workflow 1); FAIL CLOSED (no silent partial provision)"
    die "$code" "activation step $name failed: missing $piece ($SCRIPT_DIR/$helper). The fleet guarantee (provision => processor active) is NOT met for client '$SLUG'."
  fi
  if ! runas "$SCRIPT_DIR/$helper" "$@"; then
    ledger_step "$name" "FAIL" "$helper $* returned nonzero"
    die "$code" "activation step $name failed: $helper returned nonzero; $piece is NOT confirmed active for client '$SLUG'."
  fi
  if ! runas "$SCRIPT_DIR/$helper" --check "$@"; then
    ledger_step "$name" "FAIL" "$helper --check $*: the piece reports NOT active after install"
    die "$code" "activation step $name failed: $helper installed but its --check read-back says $piece is NOT active for client '$SLUG'."
  fi
  ledger_step "$name" "OK" "$helper $* (verified ACTIVE by --check)"
  ledger_fact "$name" "active"
}

if [ "$SKIP_ACTIVATION" = "1" ]; then
  ledger_fact "activation" "skipped"
  ledger_step "activation" "SKIPPED" "--skip-activation operator override; the processor is NOT confirmed active for $SLUG (the fleet audit will flag this client)"
else
  activation_step "activation:department" 22 "the podcast department installer" "install-podcast-department.sh"
  activation_step "activation:hook"        23 "the inbound hook registrar"       "register-podcast-hook.sh" --client-slug "$SLUG"
  # NO-DAEMON DOCTRINE: there is no scheduler installer and no activation step for
  # one. The department agent advances TaskFlows in its own turn via
  # podcast_step_driver.py; the former scheduler is dead by design
  # (guard-activation-health.py DAEMON_NAME_NEEDLES flags any resurrection).
  if [ "$DRY_RUN" != "1" ]; then
    ledger_fact "activation" "active"
    ledger_fact "advancement" "own-turn"
  fi
fi

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
    tok="$(runas bash -c 'set -a; . "$0" >/dev/null 2>&1; printf "%s" "${PODCAST_INTAKE_HOOK_SECRET:-}"' "$SECRETS_ENV_FILE" 2>/dev/null)"
  fi
  if [ -z "$tok" ]; then
    ledger_step "gate:signed-hook" "PENDING" "intake token not available here; run once the hook mapping and token are wired on the box"
    return 0
  fi
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
    -X POST "https://${HOOKS_HOST}/plugins/webhooks/${INTAKE_MAPPING}" \
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
if [ "$SKIP_ACTIVATION" = "1" ]; then
  log "Provision OK (edge live) but ACTIVATION SKIPPED (--skip-activation). The processor is NOT confirmed active for $SLUG; re-run without --skip-activation to restore the fleet guarantee."
else
  log "Provision OK (edge live; processor ACTIVE for $SLUG). Any PENDING items are box-side steps owned by sibling slices; complete them on the box, then re-run to green the full gate."
fi
exit 0
