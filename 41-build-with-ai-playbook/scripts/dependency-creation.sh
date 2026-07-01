#!/usr/bin/env bash
# dependency-creation.sh -- Skill 41 Build With AI Playbook Generator
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-master-files.sh"

# Args: object_type object_name [data_type for fields] [value for values]
OBJECT_TYPE="${1:-}"
OBJECT_NAME="${2:-}"
DATA_TYPE="${3:-}"
VALUE="${4:-}"

if [[ -z "$OBJECT_TYPE" || -z "$OBJECT_NAME" ]]; then
  echo "Usage: $0 <object_type> <object_name> [data_type] [value]"
  echo "  object_type: tag | field | value"
  echo "  object_name: the name to create"
  echo "  data_type: required for 'field' (text, number, date, dropdown)"
  echo "  value: required for 'value'"
  exit 1
fi

LOCATION_ID="${GOHIGHLEVEL_LOCATION_ID:-}"
API_KEY="${GOHIGHLEVEL_API_KEY:-}"

if [[ -z "$LOCATION_ID" || -z "$API_KEY" ]]; then
  echo "[skill 41] ERROR: GOHIGHLEVEL_LOCATION_ID and GOHIGHLEVEL_API_KEY must be set"
  exit 1
fi

BASE_URL="https://services.leadconnectorhq.com"
HEADERS=(-H "Authorization: Bearer $API_KEY" -H "Version: 2021-07-28" -H "Content-Type: application/json")

# ─── Durability knobs (overridable by env; sensible defaults) ────────────────
# P1 hardening: every GHL call now has a connect+overall timeout, retries with
# exponential backoff on 429/5xx + transport errors, and captures the HTTP status
# code (curl -w) instead of trusting an opaque body. Matches dependency-creation
# -protocol.md "Error handling" (429 back off + retry; 5xx retry) and
# "Verification after creation" (GET the object back; retry once after 2s).
GHL_CONNECT_TIMEOUT="${GHL_CONNECT_TIMEOUT:-10}"   # seconds to establish the TCP/TLS connection
GHL_MAX_TIME="${GHL_MAX_TIME:-25}"                 # seconds ceiling for the whole request
GHL_MAX_RETRIES="${GHL_MAX_RETRIES:-4}"            # total attempts on retryable failures
GHL_RETRY_BASE_DELAY="${GHL_RETRY_BASE_DELAY:-2}"  # first backoff (s); doubles each retry

# ghl_request <METHOD> <URL> [<body>]
#   Performs a hardened GHL REST call. Captures the HTTP status via `-w '%{http_code}'`,
#   retries (exponential backoff) on transport errors / HTTP 429 / HTTP 5xx, and stops
#   immediately on a non-retryable 4xx. On a 2xx it prints ONLY the response body to
#   stdout and returns 0. On exhaustion/4xx it prints the last body to stdout, a
#   diagnostic to stderr, and returns 1. curl is invoked WITHOUT -f so 4xx/5xx bodies
#   are preserved for the caller to inspect (and so status capture works).
ghl_request() {
  local method="$1" url="$2" body="${3:-}"
  local attempt=0 delay="$GHL_RETRY_BASE_DELAY"
  local out http_code resp curl_rc
  while :; do
    attempt=$((attempt + 1))
    local args=(-sS -X "$method" \
      --connect-timeout "$GHL_CONNECT_TIMEOUT" --max-time "$GHL_MAX_TIME" \
      -w $'\n%{http_code}' "${HEADERS[@]}")
    [[ -n "$body" ]] && args+=(-d "$body")

    if out="$(curl "${args[@]}" "$url" 2>/dev/null)"; then
      curl_rc=0
    else
      curl_rc=$?
    fi

    if [[ "$curl_rc" -ne 0 ]]; then
      # Transport-level failure (timeout, DNS, reset) -- retryable, no body/status.
      http_code="000"; resp=""
    else
      http_code="${out##*$'\n'}"   # last line is the status appended by -w
      resp="${out%$'\n'*}"         # everything before the final newline is the body
    fi

    # Success path.
    if [[ "$http_code" =~ ^2[0-9][0-9]$ ]]; then
      printf '%s' "$resp"
      return 0
    fi

    # Retryable: transport error (000), rate limit (429), or server error (5xx).
    if [[ "$http_code" == "000" || "$http_code" == "429" || "$http_code" =~ ^5[0-9][0-9]$ ]]; then
      if (( attempt >= GHL_MAX_RETRIES )); then
        echo "[skill 41] ERROR: $method $url failed after $attempt attempt(s) (last HTTP $http_code)" >&2
        printf '%s' "$resp"
        return 1
      fi
      echo "[skill 41] $method $url -> HTTP $http_code; retry $attempt/$((GHL_MAX_RETRIES - 1)) in ${delay}s" >&2
      sleep "$delay"
      delay=$((delay * 2))
      continue
    fi

    # Non-retryable 4xx (400/401/403/409/...). Surface and stop.
    echo "[skill 41] ERROR: $method $url failed (HTTP $http_code) -- non-retryable" >&2
    printf '%s' "$resp"
    return 1
  done
}

# find_object_id <list_base_url> <array_key> <name>
#   Paginated existence lookup (Fix 3 preserved): walks ?page=N until a page returns
#   fewer than `limit` rows, matching on .name == <name>. Uses the hardened ghl_request
#   for every page GET. Prints the matching id (or empty) to stdout. Returns 0 when the
#   listing completed (found or genuinely absent) and 1 when a page GET could not be
#   confirmed after retries, so callers can distinguish "absent" from "unknown".
find_object_id() {
  local list_base="$1" array_key="$2" name="$3"
  local page=1 limit=100
  while :; do
    local page_resp page_id page_count
    if ! page_resp="$(ghl_request GET "${list_base}?limit=${limit}&page=${page}")"; then
      echo ""    # could not confirm this page
      return 1
    fi
    page_id="$(echo "$page_resp" | jq -r --arg n "$name" --arg k "$array_key" \
      '((.[$k] // [])[]? | select(.name == $n) | .id)' 2>/dev/null | head -n1 || true)"
    if [[ -n "$page_id" ]]; then
      echo "$page_id"
      return 0
    fi
    page_count="$(echo "$page_resp" | jq -r --arg k "$array_key" '((.[$k] // []) | length)' 2>/dev/null || echo 0)"
    [[ "$page_count" =~ ^[0-9]+$ ]] || page_count=0
    if (( page_count < limit )); then break; fi
    page=$((page + 1))
  done
  echo ""
  return 0
}

# verify_created <list_base_url> <array_key> <name> <kind>
#   GET-back verification (dependency-creation-protocol.md "Verification after creation"):
#   confirm the just-created object is now listed; retry once after 2s; if still not found,
#   surface to the operator (WARNING to stderr) but do NOT fail -- the POST already returned
#   an id, so a missed read-back is eventual-consistency, not a creation failure.
verify_created() {
  local list_base="$1" array_key="$2" name="$3" kind="$4"
  local seen
  seen="$(find_object_id "$list_base" "$array_key" "$name")" || true
  if [[ -z "$seen" ]]; then
    sleep 2
    seen="$(find_object_id "$list_base" "$array_key" "$name")" || true
  fi
  if [[ -z "$seen" ]]; then
    echo "[skill 41] WARNING: created $kind '$name' but GET-back verification did not find it -- please check manually" >&2
  else
    echo "[skill 41] Verified $kind '$name' via GET-back (id: $seen)"
  fi
}

create_tag() {
  local name="$1"
  echo "[skill 41] Creating tag: $name"

  # Fix 5a: enforce ZHC- prefix at runtime
  if [[ "$name" != ZHC-* ]]; then
    echo "[skill 41] ERROR: tag name must start with 'ZHC-' (got: '$name')"
    exit 1
  fi

  # Fix 3: paginated existence check (now via hardened, retrying GET)
  local existing
  existing="$(find_object_id "$BASE_URL/locations/$LOCATION_ID/tags" tags "$name")" || \
    echo "[skill 41] WARNING: existence pre-check for tag '$name' could not be confirmed -- proceeding to create" >&2

  if [[ -n "$existing" ]]; then
    echo "[skill 41] Tag '$name' already exists (id: $existing) -- skipping"
    return 0
  fi

  # Fix 1: build request body with jq to prevent injection
  local body
  body=$(jq -nc --arg name "$name" '{name:$name}')
  local resp
  if ! resp="$(ghl_request POST "$BASE_URL/locations/$LOCATION_ID/tags" "$body")"; then
    echo "[skill 41] ERROR creating tag '$name': $resp"
    return 1
  fi

  local tag_id
  tag_id=$(echo "$resp" | jq -r '.id // empty')

  if [[ -n "$tag_id" ]]; then
    echo "[skill 41] Tag created: $name (id: $tag_id)"
    # GET-back verify per protocol (non-fatal belt-and-suspenders)
    verify_created "$BASE_URL/locations/$LOCATION_ID/tags" tags "$name" "tag"
    # Fix 5b: zhc_prefixed computed dynamically; Fix 1: jq-built JSONL
    local zhc_prefixed
    [[ "$name" == ZHC-* ]] && zhc_prefixed=true || zhc_prefixed=false
    append_jsonl "dependency_created" \
      '{object_type:"tag",object_name:$obj_name,zhc_prefixed:($zhc_p=="true")}' \
      --arg obj_name "$name" \
      --arg zhc_p "$zhc_prefixed"
  else
    echo "[skill 41] ERROR creating tag '$name': $resp"
    return 1
  fi
}

create_field() {
  local name="$1"
  local dtype="${2:-text}"
  echo "[skill 41] Creating custom field: $name (type: $dtype)"

  # Fix 5a: enforce ZHC_ prefix at runtime
  if [[ "$name" != ZHC_* ]]; then
    echo "[skill 41] ERROR: custom field name must start with 'ZHC_' (got: '$name')"
    exit 1
  fi

  # Fix 3: paginated existence check (now via hardened, retrying GET)
  local existing
  existing="$(find_object_id "$BASE_URL/locations/$LOCATION_ID/customFields" customFields "$name")" || \
    echo "[skill 41] WARNING: existence pre-check for custom field '$name' could not be confirmed -- proceeding to create" >&2

  if [[ -n "$existing" ]]; then
    echo "[skill 41] Custom field '$name' already exists (id: $existing) -- skipping"
    return 0
  fi

  # Fix 1: build request body with jq to prevent injection
  local body
  body=$(jq -nc --arg name "$name" --arg dtype "$dtype" '{name:$name,dataType:$dtype,group:"contact"}')
  local resp
  if ! resp="$(ghl_request POST "$BASE_URL/locations/$LOCATION_ID/customFields" "$body")"; then
    echo "[skill 41] ERROR creating custom field '$name': $resp"
    return 1
  fi

  local field_id
  field_id=$(echo "$resp" | jq -r '.id // empty')

  if [[ -n "$field_id" ]]; then
    echo "[skill 41] Custom field created: $name (id: $field_id)"
    # GET-back verify per protocol (non-fatal belt-and-suspenders)
    verify_created "$BASE_URL/locations/$LOCATION_ID/customFields" customFields "$name" "custom field"
    # Fix 5b: zhc_prefixed computed dynamically; Fix 1: jq-built JSONL
    local zhc_prefixed
    [[ "$name" == ZHC_* ]] && zhc_prefixed=true || zhc_prefixed=false
    append_jsonl "dependency_created" \
      '{object_type:"field",object_name:$obj_name,zhc_prefixed:($zhc_p=="true")}' \
      --arg obj_name "$name" \
      --arg zhc_p "$zhc_prefixed"
  else
    echo "[skill 41] ERROR creating custom field '$name': $resp"
    return 1
  fi
}

create_value() {
  local name="$1"
  local val="$2"
  echo "[skill 41] Creating custom value: $name = $val"

  # Fix 3: paginated existence check (now via hardened, retrying GET)
  local existing
  existing="$(find_object_id "$BASE_URL/locations/$LOCATION_ID/customValues" customValues "$name")" || \
    echo "[skill 41] WARNING: existence pre-check for custom value '$name' could not be confirmed -- proceeding to create" >&2

  if [[ -n "$existing" ]]; then
    echo "[skill 41] Custom value '$name' already exists (id: $existing) -- skipping"
    return 0
  fi

  # Fix 1: build request body with jq to prevent injection
  local body
  body=$(jq -nc --arg name "$name" --arg val "$val" '{name:$name,value:$val}')
  local resp
  if ! resp="$(ghl_request POST "$BASE_URL/locations/$LOCATION_ID/customValues" "$body")"; then
    echo "[skill 41] ERROR creating custom value '$name': $resp"
    return 1
  fi

  local value_id
  value_id=$(echo "$resp" | jq -r '.id // empty')

  if [[ -n "$value_id" ]]; then
    echo "[skill 41] Custom value created: $name (id: $value_id)"
    # GET-back verify per protocol (non-fatal belt-and-suspenders)
    verify_created "$BASE_URL/locations/$LOCATION_ID/customValues" customValues "$name" "custom value"
    # Fix 1: jq-built JSONL; zhc_prefixed:false is correct for values (Fix 5c -- no change)
    append_jsonl "dependency_created" \
      '{object_type:"value",object_name:$obj_name,zhc_prefixed:false}' \
      --arg obj_name "$name"
  else
    echo "[skill 41] ERROR creating custom value '$name': $resp"
    return 1
  fi
}

case "$OBJECT_TYPE" in
  tag)
    create_tag "$OBJECT_NAME"
    ;;
  field)
    if [[ -z "$DATA_TYPE" ]]; then
      echo "[skill 41] ERROR: data_type required for field creation"
      exit 1
    fi
    create_field "$OBJECT_NAME" "$DATA_TYPE"
    ;;
  value)
    if [[ -z "$VALUE" ]]; then
      echo "[skill 41] ERROR: value required for custom value creation"
      exit 1
    fi
    create_value "$OBJECT_NAME" "$VALUE"
    ;;
  *)
    echo "[skill 41] ERROR: unknown object_type '$OBJECT_TYPE'. Use: tag | field | value"
    exit 1
    ;;
esac
