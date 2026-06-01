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

create_tag() {
  local name="$1"
  echo "[skill 41] Creating tag: $name"

  # Fix 5a: enforce ZHC- prefix at runtime
  if [[ "$name" != ZHC-* ]]; then
    echo "[skill 41] ERROR: tag name must start with 'ZHC-' (got: '$name')"
    exit 1
  fi

  # Fix 3: paginated existence check -- loop until a page returns fewer than limit
  local existing="" page=1 limit=100
  while true; do
    local page_resp page_ids page_count
    page_resp=$(curl -sS "${HEADERS[@]}" "$BASE_URL/locations/$LOCATION_ID/tags?limit=${limit}&page=${page}")
    page_ids=$(echo "$page_resp" | jq -r ".tags[]? | select(.name == $(jq -rn --arg n "$name" '$n')) | .id")
    if [[ -n "$page_ids" ]]; then
      existing="$page_ids"
      break
    fi
    page_count=$(echo "$page_resp" | jq '.tags | length // 0')
    if (( page_count < limit )); then break; fi
    (( page++ ))
  done

  if [[ -n "$existing" ]]; then
    echo "[skill 41] Tag '$name' already exists (id: $existing) -- skipping"
    return 0
  fi

  # Fix 1: build request body with jq to prevent injection
  local body
  body=$(jq -nc --arg name "$name" '{name:$name}')
  local resp
  resp=$(curl -sS -X POST "${HEADERS[@]}" "$BASE_URL/locations/$LOCATION_ID/tags" -d "$body")

  local tag_id
  tag_id=$(echo "$resp" | jq -r '.id // empty')

  if [[ -n "$tag_id" ]]; then
    echo "[skill 41] Tag created: $name (id: $tag_id)"
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

  # Fix 3: paginated existence check
  local existing="" page=1 limit=100
  while true; do
    local page_resp page_ids page_count
    page_resp=$(curl -sS "${HEADERS[@]}" "$BASE_URL/locations/$LOCATION_ID/customFields?limit=${limit}&page=${page}")
    page_ids=$(echo "$page_resp" | jq -r ".customFields[]? | select(.name == $(jq -rn --arg n "$name" '$n')) | .id")
    if [[ -n "$page_ids" ]]; then
      existing="$page_ids"
      break
    fi
    page_count=$(echo "$page_resp" | jq '.customFields | length // 0')
    if (( page_count < limit )); then break; fi
    (( page++ ))
  done

  if [[ -n "$existing" ]]; then
    echo "[skill 41] Custom field '$name' already exists (id: $existing) -- skipping"
    return 0
  fi

  # Fix 1: build request body with jq to prevent injection
  local body
  body=$(jq -nc --arg name "$name" --arg dtype "$dtype" '{name:$name,dataType:$dtype,group:"contact"}')
  local resp
  resp=$(curl -sS -X POST "${HEADERS[@]}" "$BASE_URL/locations/$LOCATION_ID/customFields" -d "$body")

  local field_id
  field_id=$(echo "$resp" | jq -r '.id // empty')

  if [[ -n "$field_id" ]]; then
    echo "[skill 41] Custom field created: $name (id: $field_id)"
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

  # Fix 3: paginated existence check
  local existing="" page=1 limit=100
  while true; do
    local page_resp page_ids page_count
    page_resp=$(curl -sS "${HEADERS[@]}" "$BASE_URL/locations/$LOCATION_ID/customValues?limit=${limit}&page=${page}")
    page_ids=$(echo "$page_resp" | jq -r ".customValues[]? | select(.name == $(jq -rn --arg n "$name" '$n')) | .id")
    if [[ -n "$page_ids" ]]; then
      existing="$page_ids"
      break
    fi
    page_count=$(echo "$page_resp" | jq '.customValues | length // 0')
    if (( page_count < limit )); then break; fi
    (( page++ ))
  done

  if [[ -n "$existing" ]]; then
    echo "[skill 41] Custom value '$name' already exists (id: $existing) -- skipping"
    return 0
  fi

  # Fix 1: build request body with jq to prevent injection
  local body
  body=$(jq -nc --arg name "$name" --arg val "$val" '{name:$name,value:$val}')
  local resp
  resp=$(curl -sS -X POST "${HEADERS[@]}" "$BASE_URL/locations/$LOCATION_ID/customValues" -d "$body")

  local value_id
  value_id=$(echo "$resp" | jq -r '.id // empty')

  if [[ -n "$value_id" ]]; then
    echo "[skill 41] Custom value created: $name (id: $value_id)"
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
