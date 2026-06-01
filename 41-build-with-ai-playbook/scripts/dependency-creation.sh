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
  
  # Check if exists
  local existing
  existing=$(curl -sS "${HEADERS[@]}" "$BASE_URL/locations/$LOCATION_ID/tags?limit=100" | jq -r ".tags[]? | select(.name == \"$name\") | .id")
  
  if [[ -n "$existing" ]]; then
    echo "[skill 41] Tag '$name' already exists (id: $existing) -- skipping"
    return 0
  fi
  
  local resp
  resp=$(curl -sS -X POST "${HEADERS[@]}" "$BASE_URL/locations/$LOCATION_ID/tags" -d "{\"name\": \"$name\"}")
  
  local tag_id
  tag_id=$(echo "$resp" | jq -r '.id // empty')
  
  if [[ -n "$tag_id" ]]; then
    echo "[skill 41] Tag created: $name (id: $tag_id)"
    append_jsonl "dependency_created" "{\"object_type\":\"tag\",\"object_name\":\"$name\",\"zhc_prefixed\":true}"
  else
    echo "[skill 41] ERROR creating tag '$name': $resp"
    return 1
  fi
}

create_field() {
  local name="$1"
  local dtype="${2:-text}"
  echo "[skill 41] Creating custom field: $name (type: $dtype)"
  
  # Check if exists
  local existing
  existing=$(curl -sS "${HEADERS[@]}" "$BASE_URL/locations/$LOCATION_ID/customFields?limit=100" | jq -r ".customFields[]? | select(.name == \"$name\") | .id")
  
  if [[ -n "$existing" ]]; then
    echo "[skill 41] Custom field '$name' already exists (id: $existing) -- skipping"
    return 0
  fi
  
  local resp
  resp=$(curl -sS -X POST "${HEADERS[@]}" "$BASE_URL/locations/$LOCATION_ID/customFields" -d "{\"name\": \"$name\", \"dataType\": \"$dtype\", \"group\": \"contact\"}")
  
  local field_id
  field_id=$(echo "$resp" | jq -r '.id // empty')
  
  if [[ -n "$field_id" ]]; then
    echo "[skill 41] Custom field created: $name (id: $field_id)"
    append_jsonl "dependency_created" "{\"object_type\":\"field\",\"object_name\":\"$name\",\"zhc_prefixed\":true}"
  else
    echo "[skill 41] ERROR creating custom field '$name': $resp"
    return 1
  fi
}

create_value() {
  local name="$1"
  local val="$2"
  echo "[skill 41] Creating custom value: $name = $val"
  
  # Check if exists
  local existing
  existing=$(curl -sS "${HEADERS[@]}" "$BASE_URL/locations/$LOCATION_ID/customValues?limit=100" | jq -r ".customValues[]? | select(.name == \"$name\") | .id")
  
  if [[ -n "$existing" ]]; then
    echo "[skill 41] Custom value '$name' already exists (id: $existing) -- skipping"
    return 0
  fi
  
  local resp
  resp=$(curl -sS -X POST "${HEADERS[@]}" "$BASE_URL/locations/$LOCATION_ID/customValues" -d "{\"name\": \"$name\", \"value\": \"$val\"}")
  
  local value_id
  value_id=$(echo "$resp" | jq -r '.id // empty')
  
  if [[ -n "$value_id" ]]; then
    echo "[skill 41] Custom value created: $name (id: $value_id)"
    append_jsonl "dependency_created" "{\"object_type\":\"value\",\"object_name\":\"$name\",\"zhc_prefixed\":false}"
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
