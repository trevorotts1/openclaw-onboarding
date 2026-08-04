#!/usr/bin/env bash
# FROZEN SNAPSHOT — pre-fix shared-utils/operator-chat-id.sh, verbatim, as it
# stood on origin/main before the circular-alerting-dependency fix.
#
# THIS FILE IS NEVER SOURCED IN PRODUCTION. It exists solely so
# tests/unit/operator-chat-id-resolver.test.sh can prove its two headline
# assertions are non-vacuous: run the identical fixture/env against THIS frozen
# copy and confirm the historical bug (CLI-only lookup, no OPERATOR_HELP_CHAT_ID
# in the chain) really does resolve empty — i.e. the new assertions FAIL against
# this file and PASS against the current shared-utils/operator-chat-id.sh.
#
# Do not "fix" this file. Its entire value is being permanently, verifiably
# broken in the two ways the real resolver no longer is.
set -u

_oc_cfg_get() {
  local key="$1" v
  command -v openclaw >/dev/null 2>&1 || { printf '%s' ""; return 0; }
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
  printf '%s' ""
}

OPERATOR_CHAT_ID="$(_oc_resolve_operator_chat_id)"
export OPERATOR_CHAT_ID

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "$OPERATOR_CHAT_ID"
fi
