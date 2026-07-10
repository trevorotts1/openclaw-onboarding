#!/usr/bin/env bash
# fire-provision-snapshot.sh — fire the snapshot-provisioning webhook (Skill 58/59).
#
# Called by the per-client provisioners (provision-anthology-client.sh step 7.5,
# provision-podcast-client.sh) to request an AUTOMATED snapshot push into the
# client's Convert and Flow sub-account via the n8n "Snapshot Provisioner
# (Podcast + Anthology)" workflow. This helper only FIRES and RECORDS; it never
# blocks on completion. Genuine completion is gated box-side afterward:
#   - anthology: anthology_snapshot.py verify-imported (client's own PIT), re-fired
#     by the onboarding-resume cron until the assets materialize (~20 min).
#   - podcast:   ghl_credential_gate.py full (STEP 0), same idea.
#
# HARD RULES honored:
#   - The shared token is resolved BY LABEL from the OPERATOR env and is NEVER printed.
#   - Location ids are masked on the operator surface (payload carries the full id).
#   - Non-blocking + fail-open: if the webhook is unconfigured / unreachable / non-2xx,
#     print the MANUAL-IMPORT fallback and record it in the ledger. The pipeline must
#     NEVER make onboarding worse than the pre-automation manual path.
#   - No client-facing output here (operator-verbose only). The client "ready" email
#     is sent by the n8n workflow AFTER the 20-min settle, never by this script.
#
# Labels resolved from the operator env (SET on the operator side; provisioning runs
# are operator-driven):
#   PROVISION_SNAPSHOT_WEBHOOK_URL  e.g. https://main.blackceoautomations.com/webhook/provision-snapshot
#   PROVISION_SNAPSHOT_TOKEN        shared secret sent as the X-Provision-Token header
#
# Usage:
#   fire-provision-snapshot.sh \
#     --engine anthology|podcast --location-id <id> --client-slug <slug> \
#     --client-name "<name>" --client-email <email[,email2]> \
#     [--tenancy same_agency|cross_agency] [--requested-by <who>] \
#     [--idempotency-key <key>] [--ledger-file <path>] [--dry-run]
#
# Exit: always 0 (advisory). The caller keeps its own completion gate.
set -uo pipefail

ENGINE=""; LOCATION_ID=""; CLIENT_SLUG=""; CLIENT_NAME=""; CLIENT_EMAIL=""
TENANCY=""; REQUESTED_BY=""; IDEMPOTENCY_KEY=""; LEDGER_FILE=""; DRY_RUN="0"

while [ $# -gt 0 ]; do
  case "$1" in
    --engine)         ENGINE="${2:-}"; shift 2 ;;
    --location-id)    LOCATION_ID="${2:-}"; shift 2 ;;
    --client-slug)    CLIENT_SLUG="${2:-}"; shift 2 ;;
    --client-name)    CLIENT_NAME="${2:-}"; shift 2 ;;
    --client-email)   CLIENT_EMAIL="${2:-}"; shift 2 ;;
    --tenancy)        TENANCY="${2:-}"; shift 2 ;;
    --requested-by)   REQUESTED_BY="${2:-}"; shift 2 ;;
    --idempotency-key) IDEMPOTENCY_KEY="${2:-}"; shift 2 ;;
    --ledger-file)    LEDGER_FILE="${2:-}"; shift 2 ;;
    --dry-run)        DRY_RUN="1"; shift ;;
    *) echo "[fire-provision-snapshot] unknown arg: $1" >&2; shift ;;
  esac
done

log() { echo "[fire-provision-snapshot] $*" >&2; }

mask_loc() {
  local v="${1:-}"; local n=${#v}
  if [ -z "$v" ]; then printf 'NOT SET'; elif [ "$n" -le 6 ]; then printf '...(masked)'; else printf '...%s' "${v: -6}"; fi
}

# Record a one-line snapshot outcome into the caller's per-client ledger (best-effort).
record() {
  local state="$1" detail="${2:-}"
  [ -n "$LEDGER_FILE" ] || return 0
  if command -v jq >/dev/null 2>&1 && [ -f "$LEDGER_FILE" ]; then
    local tmp; tmp="$(mktemp 2>/dev/null)" || return 0
    jq --arg s "$state" --arg d "$detail" --arg ts "$(date -u +%FT%TZ)" \
       '.snapshot = {state:$s, detail:$d, at:$ts}' "$LEDGER_FILE" > "$tmp" 2>/dev/null \
       && mv "$tmp" "$LEDGER_FILE" 2>/dev/null || rm -f "$tmp" 2>/dev/null
  else
    printf '%s snapshot=%s %s\n' "$(date -u +%FT%TZ)" "$state" "$detail" >> "${LEDGER_FILE}.snapshot.log" 2>/dev/null || true
  fi
}

manual_fallback() {
  local why="$1"
  log "MANUAL FALLBACK ($why): the automated snapshot push was NOT fired."
  log "  OPERATOR: import the ${ENGINE} snapshot into the client's OWN Convert and Flow"
  log "            location (Settings -> Snapshots -> Import/Load), then let the box-side"
  log "            verify (${ENGINE} verify gate) confirm completion as usual."
  record "manual-fallback" "$why"
}

# --- validate inputs (advisory: a missing field just routes to manual fallback) ---
missing=""
[ -n "$ENGINE" ] || missing="$missing engine"
[ -n "$LOCATION_ID" ] || missing="$missing location_id"
[ -n "$CLIENT_SLUG" ] || missing="$missing client_slug"
[ -n "$CLIENT_NAME" ] || missing="$missing client_name"
[ -n "$CLIENT_EMAIL" ] || missing="$missing client_email"
if [ -n "$missing" ]; then
  log "missing required field(s):$missing — cannot fire; routing to manual fallback."
  manual_fallback "missing-fields"
  exit 0
fi
case "$ENGINE" in anthology|podcast) : ;; *) log "engine must be anthology|podcast (got '$ENGINE')"; manual_fallback "bad-engine"; exit 0 ;; esac

# --- resolve the webhook URL + token BY LABEL from the operator env (never printed) ---
URL="${PROVISION_SNAPSHOT_WEBHOOK_URL:-}"
TOKEN="${PROVISION_SNAPSHOT_TOKEN:-}"
if [ -z "$URL" ] || [ -z "$TOKEN" ]; then
  log "PROVISION_SNAPSHOT_WEBHOOK_URL = $( [ -n "$URL" ] && echo SET || echo 'NOT SET' ); PROVISION_SNAPSHOT_TOKEN = $( [ -n "$TOKEN" ] && echo SET || echo 'NOT SET' ) (values never printed)"
  manual_fallback "webhook-unconfigured"
  exit 0
fi

# --- build the payload (jq if present; else a safe here-string) ---
if command -v jq >/dev/null 2>&1; then
  PAYLOAD="$(jq -nc \
    --arg engine "$ENGINE" --arg location_id "$LOCATION_ID" --arg client_slug "$CLIENT_SLUG" \
    --arg client_name "$CLIENT_NAME" --arg client_email "$CLIENT_EMAIL" \
    --arg tenancy "$TENANCY" --arg requested_by "${REQUESTED_BY:-fire-provision-snapshot.sh}" \
    --arg idempotency_key "$IDEMPOTENCY_KEY" \
    '{engine:$engine, location_id:$location_id, client_slug:$client_slug, client_name:$client_name, client_email:$client_email}
     + (if $tenancy=="" then {} else {tenancy:$tenancy} end)
     + {requested_by:$requested_by}
     + (if $idempotency_key=="" then {} else {idempotency_key:$idempotency_key} end)')"
else
  PAYLOAD="{\"engine\":\"$ENGINE\",\"location_id\":\"$LOCATION_ID\",\"client_slug\":\"$CLIENT_SLUG\",\"client_name\":\"$CLIENT_NAME\",\"client_email\":\"$CLIENT_EMAIL\",\"requested_by\":\"${REQUESTED_BY:-fire-provision-snapshot.sh}\"}"
fi

log "firing snapshot provision: engine=$ENGINE client_slug=$CLIENT_SLUG location=$(mask_loc "$LOCATION_ID")${TENANCY:+ tenancy=$TENANCY}"

if [ "$DRY_RUN" = "1" ]; then
  log "(dry-run) would POST to the provision-snapshot webhook (token sent as X-Provision-Token, never printed)"
  record "dry-run" "would-fire engine=$ENGINE"
  exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
  log "curl not available"; manual_fallback "no-curl"; exit 0
fi

BODY_FILE="$(mktemp 2>/dev/null)"
HTTP_CODE="$(curl -sS -m 30 -o "${BODY_FILE:-/dev/null}" -w '%{http_code}' \
  -X POST "$URL" \
  -H 'Content-Type: application/json' \
  -H "X-Provision-Token: ${TOKEN}" \
  --data "$PAYLOAD" 2>/dev/null || echo '000')"

ACK=""
[ -n "$BODY_FILE" ] && [ -f "$BODY_FILE" ] && ACK="$(head -c 600 "$BODY_FILE" 2>/dev/null)"
[ -n "$BODY_FILE" ] && rm -f "$BODY_FILE" 2>/dev/null || true

case "$HTTP_CODE" in
  2[0-9][0-9])
    log "webhook accepted (HTTP $HTTP_CODE). ack: ${ACK}"
    log "snapshot push requested via pipeline — the box-side verify gate confirms genuine completion (~20 min)."
    record "webhook-accepted" "http=$HTTP_CODE ack=$(printf '%s' "$ACK" | tr -d '\n' | head -c 200)"
    ;;
  409)
    log "webhook returned 409 (HTTP $HTTP_CODE): ${ACK}"
    log "  (podcast: PODCAST_SNAPSHOT_ID is not set yet in n8n — fail-closed by design.)"
    record "webhook-409" "$(printf '%s' "$ACK" | tr -d '\n' | head -c 200)"
    manual_fallback "webhook-409-not-configured"
    ;;
  000)
    log "webhook unreachable"
    manual_fallback "webhook-unreachable"
    ;;
  *)
    log "webhook returned non-2xx (HTTP $HTTP_CODE): ${ACK}"
    manual_fallback "webhook-http-$HTTP_CODE"
    ;;
esac

exit 0
