#!/usr/bin/env bash
# 22-notify-client-doc.sh
# Skill 38 — MANDATORY Telegram delivery of the client's setup doc LINK.
#
# THE RULE (un-skippable): the install is NOT complete until the client has been
# SENT their Quick-Start / Notion doc LINK via Telegram. Every client gets their
# link via Telegram, no matter what. The operator is tired of repeating this — so
# it is a GATED, machine-enforced step, not optional prose.
#
# WHAT THIS SCRIPT DOES
#   (a) Resolves the client's Telegram chat id. PREFERRED source: the CLIENT_TELEGRAM_CHAT_ID
#       env (when the operator already captured it). When that is missing/empty, it
#       DISCOVERS the chat id by GREPPING THE TRANSCRIPTS — agents/*/sessions/*.jsonl —
#       for every shape a paired chat appears in:
#         "chat":{"id":<n>        (Telegram update envelope)
#         telegram:direct:<n>     (OpenClaw session key)
#         "chatId":<n>            (some gateway log lines)
#         "from":{"id":<n>        (Telegram message author)
#       and takes the MOST-FREQUENT NON-OPERATOR id. This is the Teresa lesson:
#       reading sessions.json keys alone MISSES paired chats — the source of truth
#       is the transcripts.
#   (b) Sends the doc LINK to that chat via the OpenClaw gateway
#       (`openclaw message send --channel telegram -t <chat>`). NEVER curl direct
#       to api.telegram.org.
#   (c) If NO chat is found (and none was provided), it FLAGS LOUDLY: a stderr
#       banner + a manifest/state field `clientDocDelivered=false` written to the
#       run-state file, and EXITS NON-ZERO so the install is marked incomplete.
#       It NEVER silently skips.
#
# On a successful send it records `clientDocDelivered=true` (+ the chat id and the
# delivered link) so QC and the run manifest can audit it.
#
# OS-aware via uname -s. set -euo pipefail. bash -n clean. No python under this
# file is needed; the discovery is pure grep/awk/sort so qc-static's
# claude-/anthropic .py ban does not apply (and there is no .py here anyway).
#
# Usage:
#   DOC_LINK="https://notion.so/..." CLIENT_TELEGRAM_CHAT_ID=123 bash scripts/22-notify-client-doc.sh
#   DOC_LINK="https://notion.so/..." bash scripts/22-notify-client-doc.sh   # discover chat from transcripts
#   bash scripts/22-notify-client-doc.sh --print-chat                       # only resolve+print the chat id
#
# Env:
#   DOC_LINK                  (required unless --print-chat) the link to deliver
#   CLIENT_TELEGRAM_CHAT_ID   (optional) preferred chat id; skips discovery when set+non-empty
#   CLIENT_FIRST_NAME         (optional, default "there")
#   OPERATOR_TELEGRAM_CHAT_ID (optional, default 5252140759 — Trevor) — excluded from discovery
#   OPENCLAW_DATA_DIR         (optional) override the OpenClaw data dir to scan/resolve from
#   MASTER_FILES_DIR          (optional) where the run-state file is written
#   RUN_STATE_FILE            (optional) explicit path to the run-state file
#   CLIENT_DOC_STATE_ONLY=1   (optional) write state + flag but skip the actual send (used by tests)

set -euo pipefail

OS_NAME="$(uname -s 2>/dev/null || echo unknown)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PRINT_CHAT_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --print-chat) PRINT_CHAT_ONLY=1; shift ;;
    -h|--help) sed -n '1,52p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

CLIENT_TELEGRAM_CHAT_ID="${CLIENT_TELEGRAM_CHAT_ID:-}"
CLIENT_FIRST_NAME="${CLIENT_FIRST_NAME:-there}"
OPERATOR_TELEGRAM_CHAT_ID="${OPERATOR_TELEGRAM_CHAT_ID:-5252140759}"
DOC_LINK="${DOC_LINK:-}"

# ---- resolve the OpenClaw data dir we scan for transcripts ----
resolve_data_dir() {
  if [ -n "${OPENCLAW_DATA_DIR:-}" ] && [ -d "${OPENCLAW_DATA_DIR}" ]; then
    printf '%s\n' "$OPENCLAW_DATA_DIR"; return 0
  fi
  for d in "$HOME/.openclaw" "/data/.openclaw" "/root/.openclaw"; do
    if [ -d "$d/agents" ]; then printf '%s\n' "$d"; return 0; fi
  done
  # last resort: a bare ~/.openclaw even without agents/ yet
  printf '%s\n' "$HOME/.openclaw"
}
DATA_DIR="$(resolve_data_dir)"

# ---- run-state file (records clientDocDelivered) ----
if [ -n "${RUN_STATE_FILE:-}" ]; then
  STATE_FILE="$RUN_STATE_FILE"
elif [ -n "${MASTER_FILES_DIR:-}" ]; then
  STATE_FILE="$MASTER_FILES_DIR/.skill38-run-state.env"
else
  STATE_FILE="$DATA_DIR/.skill38-run-state.env"
fi

write_state() {
  # write_state <key> <value> — idempotent upsert into the run-state env file
  local key="$1" val="$2" dir
  dir="$(dirname "$STATE_FILE")"
  mkdir -p "$dir" 2>/dev/null || true
  if [ -f "$STATE_FILE" ] && grep -q "^${key}=" "$STATE_FILE" 2>/dev/null; then
    grep -v "^${key}=" "$STATE_FILE" > "$STATE_FILE.tmp" 2>/dev/null || true
    mv "$STATE_FILE.tmp" "$STATE_FILE"
  fi
  printf '%s=%s\n' "$key" "$val" >> "$STATE_FILE"
}

# ---- transcript-based chat discovery (the Teresa lesson) ----
# Greps agents/*/sessions/*.jsonl for every shape a chat id appears in, drops the
# operator id, and returns the MOST-FREQUENT remaining id. sessions.json keys
# alone miss paired chats, so we scan the transcripts.
discover_chat_from_transcripts() {
  local agents_dir="$DATA_DIR/agents"
  [ -d "$agents_dir" ] || return 1

  # Collect every candidate id across all four shapes, one per line.
  local ids
  ids="$(
    find "$agents_dir" -type f -name '*.jsonl' -path '*/sessions/*' -print0 2>/dev/null \
      | xargs -0 grep -hoE \
          '"chat":\{"id":-?[0-9]+|telegram:direct:-?[0-9]+|"chatId":-?[0-9]+|"from":\{"id":-?[0-9]+' \
          2>/dev/null \
      | grep -oE -- '-?[0-9]+' \
      | grep -E '^-?[0-9]+$'
  )"
  [ -n "$ids" ] || return 1

  # Drop the operator id, tally, take the most frequent.
  local best
  best="$(
    printf '%s\n' "$ids" \
      | grep -vxF "$OPERATOR_TELEGRAM_CHAT_ID" \
      | sort \
      | uniq -c \
      | sort -rn \
      | awk 'NR==1{print $2}'
  )"
  [ -n "$best" ] || return 1
  printf '%s\n' "$best"
}

# ---- resolve the chat id: env first, then transcript discovery ----
RESOLVED_CHAT=""
CHAT_SOURCE=""
if [ -n "$CLIENT_TELEGRAM_CHAT_ID" ] && [ "$CLIENT_TELEGRAM_CHAT_ID" != "0" ]; then
  RESOLVED_CHAT="$CLIENT_TELEGRAM_CHAT_ID"
  CHAT_SOURCE="env(CLIENT_TELEGRAM_CHAT_ID)"
else
  if DISC="$(discover_chat_from_transcripts)"; then
    RESOLVED_CHAT="$DISC"
    CHAT_SOURCE="transcripts($DATA_DIR/agents/*/sessions/*.jsonl)"
  fi
fi

if [ "$PRINT_CHAT_ONLY" = "1" ]; then
  if [ -n "$RESOLVED_CHAT" ]; then
    printf '%s\n' "$RESOLVED_CHAT"
    exit 0
  fi
  echo "[22-notify-client-doc] NO client Telegram chat id found (env empty + no transcript match)" >&2
  exit 1
fi

# ---- the LOUD failure path: no chat found ----
if [ -z "$RESOLVED_CHAT" ]; then
  write_state "clientDocDelivered" "false"
  write_state "clientDocDeliveryError" "no-telegram-chat-id-resolved"
  {
    echo ""
    echo "================================================================================"
    echo "  [22-notify-client-doc] *** INSTALL INCOMPLETE — CLIENT DOC NOT DELIVERED ***"
    echo "================================================================================"
    echo "  Could NOT resolve the client's Telegram chat id:"
    echo "    - CLIENT_TELEGRAM_CHAT_ID env was empty/0, AND"
    echo "    - no non-operator chat id was found in the transcripts under"
    echo "      $DATA_DIR/agents/*/sessions/*.jsonl"
    echo ""
    echo "  EVERY client gets their setup-doc link via Telegram — NO MATTER WHAT."
    echo "  This step is NOT skippable. Provide CLIENT_TELEGRAM_CHAT_ID and re-run, or"
    echo "  have the client message the bot once so a transcript exists to discover from."
    echo ""
    echo "  State written: clientDocDelivered=false  ($STATE_FILE)"
    echo "================================================================================"
    echo ""
  } >&2
  exit 1
fi

# ---- DOC_LINK required for an actual send ----
if [ -z "$DOC_LINK" ]; then
  write_state "clientDocDelivered" "false"
  write_state "clientDocDeliveryError" "no-doc-link-provided"
  echo "[22-notify-client-doc] *** INSTALL INCOMPLETE *** DOC_LINK is required (the link to deliver to the client). State: clientDocDelivered=false" >&2
  exit 1
fi

# ---- compose the client message (link prominently at the top) ----
TMP_MSG="$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/.skill38-client-doc-msg.$$")"
cleanup() { [ -f "$TMP_MSG" ] && rm -f "$TMP_MSG"; }
trap cleanup EXIT
{
  printf 'Hi %s — your conversational AI setup doc is ready. Here is your link:\n\n' "$CLIENT_FIRST_NAME"
  printf '    %s\n\n' "$DOC_LINK"
  printf 'Everything you need to wire it up (the webhook URL, the Build-with-AI prompt you paste into Convert and Flow Automations, and the verification checklist) is on that page with one-click copy buttons. Anything you do not understand: screenshot it and message me.\n'
} > "$TMP_MSG"

# ---- CLIENT_DOC_STATE_ONLY: record + exit (tests / dry-run) ----
if [ "${CLIENT_DOC_STATE_ONLY:-0}" = "1" ]; then
  write_state "clientDocDelivered" "true"
  write_state "clientDocChatId" "$RESOLVED_CHAT"
  write_state "clientDocLink" "$DOC_LINK"
  echo "[22-notify-client-doc] (state-only) clientDocDelivered=true chat=$RESOLVED_CHAT source=$CHAT_SOURCE"
  exit 0
fi

# ---- send via the OpenClaw gateway (NEVER curl api.telegram.org) ----
if ! command -v openclaw >/dev/null 2>&1; then
  write_state "clientDocDelivered" "false"
  write_state "clientDocDeliveryError" "openclaw-cli-not-on-path"
  echo "[22-notify-client-doc] *** INSTALL INCOMPLETE *** openclaw CLI not on PATH — cannot send the client doc link via Telegram. State: clientDocDelivered=false" >&2
  exit 1
fi

set +e
SEND_OUT="$(openclaw message send --channel telegram -t "$RESOLVED_CHAT" --file "$TMP_MSG" 2>&1)"
SEND_RC=$?
set -e

if [ "$SEND_RC" -ne 0 ]; then
  write_state "clientDocDelivered" "false"
  write_state "clientDocDeliveryError" "telegram-send-failed-rc-$SEND_RC"
  {
    echo "[22-notify-client-doc] *** INSTALL INCOMPLETE *** Telegram send to chat $RESOLVED_CHAT FAILED (rc=$SEND_RC)."
    echo "  openclaw output: $SEND_OUT"
    echo "  State: clientDocDelivered=false"
  } >&2
  exit 1
fi

write_state "clientDocDelivered" "true"
write_state "clientDocChatId" "$RESOLVED_CHAT"
write_state "clientDocLink" "$DOC_LINK"
echo "[22-notify-client-doc] clientDocDelivered=true  chat=$RESOLVED_CHAT  source=$CHAT_SOURCE  link=$DOC_LINK"
exit 0
