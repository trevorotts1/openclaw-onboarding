#!/usr/bin/env bash
# verify-telegram-delivery.sh -- cross-check that the messageIds captured by
# send-telegram-celebration.sh are ACTUALLY present in the gateway sent-registry.
#
# WHY (anti-faking, the load-bearing layer):
#   `openclaw message send` can exit 0 -- and even hand back a messageId -- while
#   the message never truly lands (silent Telegram-offset-corruption; fresh-VPS
#   "scope upgrade pending approval"). The single ground-truth the gateway keeps
#   is its sent-registry:
#       agents/main/sessions/sessions.json.telegram-sent-messages.json
#   a map  { "<chatId>": { "<messageId>": <ts-ms>, ... }, ... }.
#   A messageId we sent seconds/minutes ago MUST appear under the owner's chatId
#   there. This script requires that for EVERY required deliverable. No "done"
#   is allowed until each required messageId is confirmed present.
#
# Registry rotation is supported only by an exact durable receipt recorded by
# this verifier while the authoritative registry entry was present.
# Bare old success flags and captured IDs never establish delivery.
#
# REQUIRED DELIVERABLES (default): slots 1, 6, 7 -- the three text messages that
#   MUST land for a usable closeout (announcement + Command Center URL + bookmark
#   hint). Media slots (2/3/4) and the Notion slot (5) are conditional (skipped
#   when their URL is missing) so they are verified-if-present but not required.
#   Override with ZHC_TG_REQUIRED_SLOTS="1,6,7".
#
# Delivery authority is the matching gateway JSON registry or the supported
# Telegram SQLite plugin-state entry. Expired unknown IDs, failed sends, wrong
# scopes/chats and unavailable authority remain pending. See GATEWAY-RECEIPTS.md.
# Exit 0 verified, 3 registry mismatch, 4 absent send, 7 capability unavailable.

set -u

if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  OC_ROOT=""
fi

# STATE_FILE / LOG_FILE / REGISTRY all accept env overrides so the smoke test
# (and any harness) can run against a temp fixture with no real .openclaw install.
STATE_FILE="${ZHC_STATE_FILE:-$OC_ROOT/workspace/.workforce-build-state.json}"
LOG_FILE="${ZHC_LOG_FILE:-$OC_ROOT/workspace/.zhc-closeout.log}"
# The gateway sent-registry. Allow override for tests.
REGISTRY="${ZHC_TG_REGISTRY:-$OC_ROOT/agents/main/sessions/sessions.json.telegram-sent-messages.json}"

# The gateway scopes migrated records by the EXACT session store path. Defaults
# apply only to the real own installation. Fixture/state/registry overrides must
# explicitly opt into their own SQLite database; never fall through to live data.
if [[ -z "${ZHC_STATE_FILE:-}" && -z "${ZHC_TG_REGISTRY:-}" && -n "$OC_ROOT" ]]; then
  export ZHC_TG_STATE_DB="${ZHC_TG_STATE_DB:-$OC_ROOT/state/openclaw.sqlite}"
fi
if [[ -n "${ZHC_TG_STATE_DB:-}" && -z "${ZHC_TG_SESSION_STORE:-}" && "$REGISTRY" == *.telegram-sent-messages.json ]]; then
  export ZHC_TG_SESSION_STORE="${REGISTRY%.telegram-sent-messages.json}"
fi

if [[ -z "$OC_ROOT" && ( -z "${ZHC_STATE_FILE:-}" || -z "${ZHC_TG_REGISTRY:-}" ) ]]; then
  echo "[verify-telegram] no OpenClaw root and no ZHC_STATE_FILE/ZHC_TG_REGISTRY override" >&2
  exit 7
fi
TTL_SEC="${ZHC_TG_REGISTRY_TTL_SEC:-86400}"
REQUIRED_SLOTS="${ZHC_TG_REQUIRED_SLOTS:-1,6,7}"

log() {
  printf '%s [%-5s] step=verify-telegram %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >> "$LOG_FILE" 2>/dev/null || true
  printf '%s [%-5s] step=verify-telegram %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2"
}

command -v jq >/dev/null 2>&1 || { log "ERROR" "jq not installed"; exit 7; }
[[ -f "$STATE_FILE" ]] || { log "ERROR" "no state file at $STATE_FILE"; exit 7; }

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../23-ai-workforce-blueprint/scripts" && pwd)/lib-workforce-state.sh" || exit 7
# Invalidate the current claim before I/O; the separate immutable receipt ledger
# survives so an observed historical send remains provable after registry rotation.
workforce_state_set "$STATE_FILE" '.telegramDeliveryVerification.status = "pending" | .telegramDeliveryVerification.rc = 7' || exit 7
"$WORKFORCE_PYTHON" "$(dirname "${BASH_SOURCE[0]}")/verify_delivery_receipts.py" "$STATE_FILE" "$REGISTRY" "$REQUIRED_SLOTS"
exit "$?"
