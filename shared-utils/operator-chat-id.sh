#!/usr/bin/env bash
# operator-chat-id.sh — resolve the operator ESCALATION Telegram chat ID.
#
# CO-MINGLING GUARD (v12.4.0):
#   This resolver NEVER bakes in a personal chat ID. The destination for
#   operator escalations/monitoring is OPT-IN and CONFIGURABLE. If no operator
#   escalation chat is configured, this returns the EMPTY STRING and every
#   caller MUST treat that as "escalation destination not configured" and NO-OP
#   the send (log only). A client box that ships without this env set will
#   therefore never proactively message any operator's personal Telegram.
#
# Source this file (or call it directly) to get $OPERATOR_CHAT_ID populated
# (possibly empty).
#
# Lookup order (first non-empty wins; ALL operator-supplied, none hardcoded):
#   1. env.vars.OPERATOR_ESCALATION_CHAT_ID   (openclaw config — primary, new)
#   2. env.vars.OPERATOR_TELEGRAM_CHAT_ID     (openclaw config — back-compat)
#   3. $OPERATOR_ESCALATION_CHAT_ID           (environment variable — primary)
#   4. $OPERATOR_TELEGRAM_CHAT_ID             (environment variable — back-compat)
#   5. $ZHC_OPERATOR_CHAT_ID                  (environment variable — closeout legacy)
#   6. "" (EMPTY — escalation no-ops; this is the safe default for client boxes)
#
# To OPT IN to operator escalation on a box (operator box, or a client that has
# explicitly authorized operator monitoring):
#   openclaw config set env.vars.OPERATOR_ESCALATION_CHAT_ID "<operator chat id>" --strict-json
#
# Usage:
#   source /path/to/shared-utils/operator-chat-id.sh
#   if [[ -n "$OPERATOR_CHAT_ID" ]]; then
#     openclaw message send --channel telegram --target "$OPERATOR_CHAT_ID" --message "..."
#   else
#     echo "operator escalation chat not configured — skipping send"
#   fi

set -u

_oc_cfg_get() {
  # Read an openclaw config key, returning empty on any error/"not found".
  local key="$1" v
  command -v openclaw >/dev/null 2>&1 || { printf '%s' ""; return 0; }
  # v16.2.13: `|| true` — `openclaw config get <absent-key>` exits non-zero on the
  # common "no operator chat configured" path (the documented safe default), and
  # `pipefail` adopts it; this plain reassignment (local was separate above) would
  # otherwise abort a caller that sources this under `set -e` + `inherit_errexit`
  # (or POSIX mode). Enforces the header's "returns empty on any error" contract.
  v="$(openclaw config get "$key" 2>/dev/null | tail -1 | tr -d '[:space:]' || true)"
  case "$v" in
    ""|*"not found"*|*"Error"*|*"undefined"*|null) v="" ;;
  esac
  printf '%s' "$v"
}

_oc_resolve_operator_chat_id() {
  local v
  v="$(_oc_cfg_get env.vars.OPERATOR_ESCALATION_CHAT_ID)"
  [[ -n "$v" ]] && { printf '%s' "$v"; return 0; }
  v="$(_oc_cfg_get env.vars.OPERATOR_TELEGRAM_CHAT_ID)"
  [[ -n "$v" ]] && { printf '%s' "$v"; return 0; }
  if [[ -n "${OPERATOR_ESCALATION_CHAT_ID:-}" ]]; then
    printf '%s' "$OPERATOR_ESCALATION_CHAT_ID"; return 0
  fi
  if [[ -n "${OPERATOR_TELEGRAM_CHAT_ID:-}" ]]; then
    printf '%s' "$OPERATOR_TELEGRAM_CHAT_ID"; return 0
  fi
  if [[ -n "${ZHC_OPERATOR_CHAT_ID:-}" ]]; then
    printf '%s' "$ZHC_OPERATOR_CHAT_ID"; return 0
  fi
  # No operator escalation chat configured — return empty (safe default).
  printf '%s' ""
}

OPERATOR_CHAT_ID="$(_oc_resolve_operator_chat_id)"
export OPERATOR_CHAT_ID

# If called directly (not sourced), print the resolved value (may be empty).
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "$OPERATOR_CHAT_ID"
fi
