#!/usr/bin/env bash
# cc-closeout-task.sh — FIX-S36-06: Command Center Kanban card for the CLOSEOUT
# itself, keyed PER CLIENT SLUG.
#
# WHY THIS EXISTS:
#   The closeout builds a Command Center kanban in Step 1, then delivers 7
#   artifacts — but never landed a card on that board for its OWN progress. So a
#   STUCK closeout (held artifact, failed leg, gateway down) was board-INVISIBLE:
#   the operator had no card to see it hanging. This helper posts + advances a
#   single closeout card so the closeout is always visible and a block is loud.
#
# GRACEFUL-DEGRADING: like Skill 38's cc-task.sh it NEVER fails the caller and
# NEVER messages a client — every failure path prints ONE operator-only stderr
# line and exits 0. It NEVER self-advances to the done column (the independent
# Command Center auto-scorer is the only authority that promotes review -> done).
#
# SUBCOMMANDS
#   start   Create-or-reuse the per-client closeout card, then move it to
#           `in_progress` (closeout has started generating — pending -> generating).
#   review  Move the persisted card to `review` (all legs delivered + verified —
#           this is the gate BEFORE closeoutStatus=done). The CC auto-scorer, not
#           this script, promotes review -> the done column.
#   blocked [note]  Move the card to `blocked` with an operator note (a held
#           artifact / failed leg / gateway-down exit). Never sets done.
#
# KEYING: the card + its persisted id are keyed on the client slug so different
#   clients get DISTINCT cards. Slug source: $ZHC_CLOSEOUT_SLUG (else "default").
#   Persisted id file: $OC_ROOT/.zhc-closeout-cc-task-<slug>
#
# USAGE:
#   ZHC_CLOSEOUT_SLUG=acme cc-closeout-task.sh start
#   ZHC_CLOSEOUT_SLUG=acme cc-closeout-task.sh review
#   ZHC_CLOSEOUT_SLUG=acme cc-closeout-task.sh blocked "held: celebration_video"
#
# CONFIG (all optional except MC_API_TOKEN for a live post):
#   MISSION_CONTROL_URL   base URL (default http://localhost:4000)
#   MC_API_TOKEN          bearer token (command-center app/.env.local). Unset ->
#                         one stderr note + exit 0 (no-op).
#   MC_CLOSEOUT_AGENT_ID  optional agent UUID -> created_by/updated_by_agent_id.
#   MC_CLOSEOUT_SOP_ID    optional SOP UUID -> sop_id (leave-backlog Triad).
#   ZHC_CLOSEOUT_COMPANY  optional human company name for the card title.
#
# DEPENDENCY: curl only. bash-not-zsh: always invoke via `bash`.
#
# NOTE: `set -u -o pipefail` but intentionally NOT `-e` — we handle every rc
# ourselves so a Command Center hiccup can never abort the closeout.

set -uo pipefail

CMD="${1:-}"
[ "$#" -gt 0 ] && shift

BASE_URL="${MISSION_CONTROL_URL:-http://localhost:4000}"
BASE_URL="${BASE_URL%/}"
TOKEN="${MC_API_TOKEN:-}"

CREATOR_ID="${MC_CLOSEOUT_AGENT_ID:-}"
UPDATER_ID="${MC_CLOSEOUT_AGENT_ID:-}"
SOP_ID="${MC_CLOSEOUT_SOP_ID:-}"

if [ -d /data/.openclaw ]; then OC_ROOT="/data/.openclaw"; else OC_ROOT="$HOME/.openclaw"; fi

# Resolve the client slug from the environment (keeps the sole positional arg
# free to be the blocked-note). Any remaining positional is the blocked note.
SLUG="${ZHC_CLOSEOUT_SLUG:-}"
[ -n "$SLUG" ] || SLUG="default"
# sanitize to a filesystem/URL-safe token
SLUG="$(printf '%s' "$SLUG" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-*//; s/-*$//')"
[ -n "$SLUG" ] || SLUG="default"

COMPANY="${ZHC_CLOSEOUT_COMPANY:-$SLUG}"
ID_FILE="${ZHC_CLOSEOUT_CC_TASK_ID_FILE:-$OC_ROOT/.zhc-closeout-cc-task-$SLUG}"

# Operator-only stderr; NEVER a client channel. Never prints the token.
note() { echo "[zhc][cc-closeout-task][$SLUG] $*" >&2; }
# Graceful no-op: exactly one stderr note, then succeed (never fail the caller).
soft_out() { note "$*"; exit 0; }

[ -n "$CMD" ] || soft_out "usage: cc-closeout-task.sh {start|review|blocked} [slug] — no subcommand; no-op."
[ -n "$TOKEN" ] || soft_out "MC_API_TOKEN not set — Command Center card skipped (closeout continues normally)."
command -v curl >/dev/null 2>&1 || soft_out "curl not found — Command Center card skipped."

# Sets globals HTTP_CODE + RESP_BODY. Never prints the token. $1=method $2=path $3=body
HTTP_CODE=""
RESP_BODY=""
_api() {
  local method="$1" path="$2" body="${3:-}" out=""
  if [ -n "$body" ]; then
    out="$(curl -s -m 12 -w $'\n%{http_code}' -X "$method" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json" \
      --data "$body" "${BASE_URL}${path}" 2>/dev/null)" || out=""
  else
    out="$(curl -s -m 12 -w $'\n%{http_code}' -X "$method" \
      -H "Authorization: Bearer ${TOKEN}" \
      "${BASE_URL}${path}" 2>/dev/null)" || out=""
  fi
  HTTP_CODE="${out##*$'\n'}"
  RESP_BODY="${out%$'\n'*}"
  case "$HTTP_CODE" in ''|*[!0-9]*) HTTP_CODE="000" ;; esac
}

# JSON-escape a string for a double-quoted value (curl-only; no jq).
_json_escape() {
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr -d '\r\n\t'
}

_json_create() {
  local desc; desc="$(_json_escape "$1")"
  local title; title="$(_json_escape "ZHC Closeout — ${COMPANY}")"
  local extra=""
  [ -n "$SOP_ID" ]     && extra="${extra},\"sop_id\":\"${SOP_ID}\""
  [ -n "$CREATOR_ID" ] && extra="${extra},\"created_by_agent_id\":\"${CREATOR_ID}\""
  printf '{"title":"%s","description":"%s","priority":"high","department":"Operations"%s}' "$title" "$desc" "$extra"
}

# $1 = target column, $2 = optional note
_json_status() {
  local status="$1" n="${2:-}" nesc updater=""
  [ -n "$UPDATER_ID" ] && updater=",\"updated_by_agent_id\":\"${UPDATER_ID}\""
  if [ -n "$n" ]; then
    nesc="$(_json_escape "$n")"
    printf '{"status":"%s","note":"%s"%s}' "$status" "$nesc" "$updater"
  else
    printf '{"status":"%s"%s}' "$status" "$updater"
  fi
}

_extract_id() {
  printf '%s' "$1" | grep -oE '"id"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"([^"]+)"$/\1/'
}

_read_task_id() {
  [ -f "$ID_FILE" ] && head -1 "$ID_FILE" 2>/dev/null | tr -d '[:space:]'
}

# Create-or-reuse the per-client card; echoes the id (empty on soft failure).
_ensure_card() {
  local task_id; task_id="$(_read_task_id)"
  if [ -n "$task_id" ]; then
    printf '%s' "$task_id"; return 0
  fi
  local desc="ZeroHumanWorkforce closeout for ${COMPANY} — delivers the 7 closeout artifacts (Command Center, org-chart + flow infographics, celebration video, Notion page tree, 6-message Telegram sequence, n8n wire-up), each behind the 8.5 quality gate. Auto-created by run-closeout.sh."
  _api POST "/api/tasks" "$(_json_create "$desc")"
  case "$HTTP_CODE" in 2??) : ;; *) note "create card -> HTTP ${HTTP_CODE}; Command Center card skipped (closeout continues)."; return 1 ;; esac
  task_id="$(_extract_id "$RESP_BODY")"
  [ -n "$task_id" ] || { note "create card returned no id; Command Center card skipped."; return 1; }
  mkdir -p "$(dirname "$ID_FILE")" 2>/dev/null || true
  printf '%s\n' "$task_id" > "$ID_FILE" 2>/dev/null || true
  note "created closeout card ${task_id}."
  printf '%s' "$task_id"
}

cmd_start() {
  local task_id; task_id="$(_ensure_card)" || exit 0
  [ -n "$task_id" ] || exit 0
  _api PATCH "/api/tasks/${task_id}" "$(_json_status in_progress)"
  case "$HTTP_CODE" in
    2??) note "card ${task_id} -> in_progress (closeout generating)." ;;
    *)   note "PATCH in_progress -> HTTP ${HTTP_CODE} (card exists; transition deferred — supply MC_CLOSEOUT_SOP_ID/MC_CLOSEOUT_AGENT_ID for the leave-backlog Triad). Closeout continues." ;;
  esac
  exit 0
}

cmd_review() {
  local task_id; task_id="$(_read_task_id)"
  [ -n "$task_id" ] || soft_out "no persisted closeout card id (${ID_FILE}) — nothing to move to review. Skipped."
  _api PATCH "/api/tasks/${task_id}" "$(_json_status review)"
  case "$HTTP_CODE" in
    2??) note "card ${task_id} -> review (independent CC auto-scorer promotes review -> done; closeout never self-grades)." ;;
    *)   note "PATCH review -> HTTP ${HTTP_CODE}; Command Center card unchanged (closeout result unchanged)." ;;
  esac
  exit 0
}

cmd_blocked() {
  local blocknote="${1:-closeout blocked}"
  local task_id; task_id="$(_read_task_id)"
  # A block can occur before start ever ran (e.g. preflight failure) — create the
  # card so the block is still visible, then mark it blocked.
  [ -n "$task_id" ] || task_id="$(_ensure_card)" || exit 0
  [ -n "$task_id" ] || exit 0
  _api PATCH "/api/tasks/${task_id}" "$(_json_status blocked "$blocknote")"
  case "$HTTP_CODE" in
    2??) note "card ${task_id} -> blocked: ${blocknote}" ;;
    *)   note "PATCH blocked -> HTTP ${HTTP_CODE} (board may lack a blocked column); block noted operator-side: ${blocknote}" ;;
  esac
  exit 0
}

case "$CMD" in
  start)   cmd_start ;;
  review)  cmd_review ;;
  blocked) cmd_blocked "${1:-}" ;;
  *)       soft_out "unknown subcommand '${CMD}' (expected start|review|blocked); no-op." ;;
esac
