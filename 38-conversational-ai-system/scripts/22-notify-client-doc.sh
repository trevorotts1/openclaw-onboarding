#!/usr/bin/env bash
# 22-notify-client-doc.sh
# Skill 38 — MANDATORY Telegram delivery of the client's setup doc LINK.
#
# THE RULE (un-skippable, HARD BLOCK): the install is NOT complete — every QC gate
# exits non-zero — until the client doc was BOTH (1) created (Quick Start + 23-key
# body + split Authorization key/value + playbooks/trigger/I-Do-You-Do + VPS-vs-Mac
# + the How-to-test section; enforced by qc-reference-sheet.sh --require-manual-fill)
# AND (2) DELIVERED to the client via Telegram (this script + qc-notify-client-doc.sh).
# Every client gets their link via Telegram, no matter what. This is a GATED,
# machine-enforced step, not optional prose.
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
#       and takes the MOST-FREQUENT NON-OPERATOR id. This is a hard-won live-client lesson:
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
#   OPERATOR_TELEGRAM_CHAT_ID (optional) the operator's chat id — EXCLUDED from
#                             transcript discovery so the client doc is never sent
#                             to the operator. When UNSET this script cross-checks
#                             the shared resolver shared-utils/operator-chat-id.sh
#                             (OPERATOR_ESCALATION_CHAT_ID / OPERATOR_TELEGRAM_CHAT_ID
#                             config + env / ZHC_OPERATOR_CHAT_ID). If it STILL
#                             cannot resolve the operator id AND discovery is the
#                             path (no CLIENT_TELEGRAM_CHAT_ID), the discovered
#                             "most-frequent" chat could BE the operator — so the
#                             script FAILS LOUDLY and requires an explicit ack
#                             (SKILL38_ACK_OPERATOR_CHAT_UNSET=1) to proceed.
#   SKILL38_ACK_OPERATOR_CHAT_UNSET=1  (optional) operator ack that discovery may
#                             run with NO operator id to exclude (e.g. a box with
#                             no operator paired). Without it, an unresolved
#                             operator id on the discovery path is a hard failure.
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
OPERATOR_TELEGRAM_CHAT_ID="${OPERATOR_TELEGRAM_CHAT_ID:-}"
DOC_LINK="${DOC_LINK:-}"

# ---- cross-check the OPERATOR chat id via the shared resolver (FIX-S36-08) ----
# The operator id is what transcript discovery EXCLUDES so the client doc is never
# sent to the operator. If OPERATOR_TELEGRAM_CHAT_ID was not passed directly, fall
# back to the fleet-standard resolver shared-utils/operator-chat-id.sh (which reads
# OPERATOR_ESCALATION_CHAT_ID / OPERATOR_TELEGRAM_CHAT_ID from openclaw config or
# env, plus ZHC_OPERATOR_CHAT_ID). This never bakes in a personal id — it returns
# empty when nothing is configured, and the discovery guard below handles that.
if [ -z "$OPERATOR_TELEGRAM_CHAT_ID" ]; then
  if [ -d /data/.openclaw ]; then _OC_ROOT="/data/.openclaw"; else _OC_ROOT="$HOME/.openclaw"; fi
  for _op_util in \
    "$_OC_ROOT/skills/shared-utils/operator-chat-id.sh" \
    "$SCRIPT_DIR/../../shared-utils/operator-chat-id.sh" \
    "$SCRIPT_DIR/../shared-utils/operator-chat-id.sh"; do
    if [ -f "$_op_util" ]; then
      OPERATOR_CHAT_ID=""
      # shellcheck disable=SC1090
      source "$_op_util" 2>/dev/null || true
      if [ -n "${OPERATOR_CHAT_ID:-}" ]; then
        OPERATOR_TELEGRAM_CHAT_ID="$OPERATOR_CHAT_ID"
        echo "[22-notify-client-doc] resolved operator chat id via $_op_util (excluded from discovery)." >&2
        break
      fi
    fi
  done
fi

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

# ---- transcript-based chat discovery (a hard-won live-client lesson) ----
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
  # FIX-S36-08: only apply the exclusion when the operator id is NON-EMPTY.
  # `grep -vxF ""` matches only empty lines, so with an empty operator id it
  # excludes NOTHING — meaning the most-frequent chat could be the operator's.
  # The unset-operator case is gated LOUDLY before discovery is ever called, so
  # here we simply skip the filter safely when there is no operator id to drop.
  local filtered
  if [ -n "$OPERATOR_TELEGRAM_CHAT_ID" ]; then
    filtered="$(printf '%s\n' "$ids" | grep -vxF "$OPERATOR_TELEGRAM_CHAT_ID")"
  else
    filtered="$ids"
  fi
  local best
  best="$(
    printf '%s\n' "$filtered" \
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
  # DISCOVERY PATH — the operator id is what we exclude. If it is unresolved
  # (FIX-S36-08), discovery could pick the OPERATOR's own chat and we would then
  # send the client doc to the operator while recording clientDocDelivered=true.
  # Refuse to guess: warn LOUDLY and require an explicit operator ack to proceed.
  if [ -z "$OPERATOR_TELEGRAM_CHAT_ID" ]; then
    {
      echo ""
      echo "================================================================================"
      echo "  [22-notify-client-doc] *** OPERATOR CHAT ID UNRESOLVED — DISCOVERY UNSAFE ***"
      echo "================================================================================"
      echo "  No CLIENT_TELEGRAM_CHAT_ID was provided, so the client chat is discovered from"
      echo "  the transcripts — but the OPERATOR chat id could NOT be resolved (env unset AND"
      echo "  shared-utils/operator-chat-id.sh returned empty). Discovery cannot exclude the"
      echo "  operator, so the 'most-frequent' chat it picks MIGHT BE THE OPERATOR — which"
      echo "  would send the client's setup doc to the operator while marking it delivered."
      echo ""
      echo "  RESOLVE ONE of the following, then re-run:"
      echo "    1. Provide the client id directly:  CLIENT_TELEGRAM_CHAT_ID=<id>"
      echo "    2. Configure the operator id so it can be excluded:"
      echo "         openclaw config set env.vars.OPERATOR_ESCALATION_CHAT_ID \"<operator id>\" --strict-json"
      echo "       (or export OPERATOR_TELEGRAM_CHAT_ID=<id>)"
      echo "    3. If this box genuinely has NO operator paired and discovery is safe,"
      echo "       ACKNOWLEDGE explicitly:  SKILL38_ACK_OPERATOR_CHAT_UNSET=1"
      echo "================================================================================"
      echo ""
    } >&2
    if [ "${SKILL38_ACK_OPERATOR_CHAT_UNSET:-0}" != "1" ]; then
      if [ "$PRINT_CHAT_ONLY" != "1" ]; then
        write_state "clientDocDelivered" "false"
        write_state "clientDocDeliveryError" "operator-chat-id-unresolved-no-ack"
      fi
      echo "[22-notify-client-doc] *** REFUSING to discover a client chat without a known operator id to exclude. Set CLIENT_TELEGRAM_CHAT_ID, configure the operator id, or pass SKILL38_ACK_OPERATOR_CHAT_UNSET=1 to acknowledge. ***" >&2
      exit 1
    fi
    echo "[22-notify-client-doc] SKILL38_ACK_OPERATOR_CHAT_UNSET=1 — proceeding with UN-EXCLUDED discovery (operator id unknown; acknowledged)." >&2
  fi
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
