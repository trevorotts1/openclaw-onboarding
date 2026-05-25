#!/usr/bin/env bash
# operator-chat-id.sh — resolve the operator's Telegram chat ID for cross-skill escalations.
#
# Source this file (or call it directly) to get $OPERATOR_CHAT_ID populated.
#
# Lookup order:
#   1. env.vars.OPERATOR_TELEGRAM_CHAT_ID from openclaw config
#   2. $OPERATOR_TELEGRAM_CHAT_ID environment variable
#   3. Hardcoded default 5252140759 (Trevor Otts) for back-compat
#
# This is a schema-compliant home for the value: env.vars accepts arbitrary
# string keys per the 2026.5.22 openclaw.json schema, validated end-to-end.
#
# Usage:
#   source /path/to/shared-utils/operator-chat-id.sh
#   echo "$OPERATOR_CHAT_ID"
#   openclaw message send --channel telegram --target "$OPERATOR_CHAT_ID" --message "..."

set -u

_oc_resolve_operator_chat_id() {
  local v
  v="$(openclaw config get env.vars.OPERATOR_TELEGRAM_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
  if [[ -n "${v:-}" && "$v" != *"not found"* && "$v" != *"Error"* ]]; then
    printf '%s' "$v"
    return 0
  fi
  if [[ -n "${OPERATOR_TELEGRAM_CHAT_ID:-}" ]]; then
    printf '%s' "$OPERATOR_TELEGRAM_CHAT_ID"
    return 0
  fi
  printf '%s' "5252140759"
}

OPERATOR_CHAT_ID="$(_oc_resolve_operator_chat_id)"
export OPERATOR_CHAT_ID

# If called directly (not sourced), print the resolved value.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "$OPERATOR_CHAT_ID"
fi
