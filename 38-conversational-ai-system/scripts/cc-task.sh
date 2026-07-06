#!/usr/bin/env bash
# cc-task.sh — Command Center Kanban task-lifecycle reporting for the Skill 38
# install/QC flow. GRACEFUL-DEGRADING: it never fails the caller and never
# messages a client — every failure path prints ONE operator-only stderr line
# and exits 0.
#
# SUBCOMMANDS
#   start   Create-or-reuse the Skill-38 install task, then move it to
#           `in_progress` (install has started).
#   review  Move the persisted task to `review` (QC passed). The independent
#           Command Center auto-scorer is the ONLY authority that advances
#           review -> the done column — the builder NEVER self-grades (the CC API
#           rejects a builder self-advance with 403). So this only ever sets
#           `review`; it never sets the done status.
#   fail    Move the persisted task to `blocked` (QC failed / a gate blocked the
#           install), with an optional reason as $2. A blocked card is NEVER
#           auto-promoted to done — it makes the failure VISIBLE on the board
#           instead of stranding the card at in_progress forever (FIX-XC-06). A
#           fixed re-run re-opens it (start -> in_progress).
#
# CONFIG (all optional except MC_API_TOKEN for a live post):
#   MISSION_CONTROL_URL   base URL (default http://localhost:4000)
#   MC_API_TOKEN          bearer token (from command-center app/.env.local). If
#                         unset -> one stderr note + exit 0 (no-op).
#   MC_SKILL38_AGENT_ID   optional agent UUID -> created_by_agent_id +
#                         updated_by_agent_id on transitions (for a live board).
#   MC_SKILL38_SOP_ID     optional SOP UUID -> sop_id (part of the leave-backlog
#                         Triad). Omitted if unset (the API keeps the card in
#                         backlog until the Triad is satisfied — still graceful).
#
# The task id is persisted to $HOME/.openclaw/.skill-38-cc-task-id (VPS: under
# /data/.openclaw) so re-runs reuse the same card (idempotent).
#
# DEPENDENCY: curl only. bash-not-zsh: always invoke via `bash`.
#
# NOTE: `set -u -o pipefail` but intentionally NOT `-e` — we handle every rc
# ourselves so a Command Center hiccup can never abort the install.

set -uo pipefail

CMD="${1:-}"
REASON="${2:-}"   # optional free-text reason for the `fail` subcommand

BASE_URL="${MISSION_CONTROL_URL:-http://localhost:4000}"
BASE_URL="${BASE_URL%/}"
TOKEN="${MC_API_TOKEN:-}"

CREATOR_ID="${MC_SKILL38_AGENT_ID:-}"   # created_by_agent_id (UUID) if supplied
UPDATER_ID="${MC_SKILL38_AGENT_ID:-}"   # updated_by_agent_id (UUID) if supplied
SOP_ID="${MC_SKILL38_SOP_ID:-}"         # sop_id (UUID) if supplied

if [ -d /data/.openclaw ]; then OC_ROOT="/data/.openclaw"; else OC_ROOT="$HOME/.openclaw"; fi
ID_FILE="${SKILL38_CC_TASK_ID_FILE:-$OC_ROOT/.skill-38-cc-task-id}"

# Operator-only stderr; NEVER a client channel. Never prints the token.
note() { echo "[skill38][cc-task] $*" >&2; }

# Graceful no-op: exactly one stderr note, then succeed (never fail the caller).
soft_out() { note "$*"; exit 0; }

[ -n "$CMD" ] || soft_out "usage: cc-task.sh {start|review|fail [reason]} — no subcommand; no-op."
[ -n "$TOKEN" ] || soft_out "MC_API_TOKEN not set — Command Center reporting skipped (install continues normally)."
command -v curl >/dev/null 2>&1 || soft_out "curl not found — Command Center reporting skipped."

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

# Build the create-task JSON body (curl-only; no jq).
_json_create() {
  local desc="$1" extra=""
  [ -n "$SOP_ID" ]     && extra="${extra},\"sop_id\":\"${SOP_ID}\""
  [ -n "$CREATOR_ID" ] && extra="${extra},\"created_by_agent_id\":\"${CREATOR_ID}\""
  printf '{"title":"Skill 38 — Conversational AI System install","description":"%s","priority":"medium","department":"Communications"%s}' "$desc" "$extra"
}

# Build a status-transition JSON body. $1 = target column (in_progress | review | blocked).
_json_status() {
  if [ -n "$UPDATER_ID" ]; then
    printf '{"status":"%s","updated_by_agent_id":"%s"}' "$1" "$UPDATER_ID"
  else
    printf '{"status":"%s"}' "$1"
  fi
}

# Build a status-transition body carrying a note. $1 = status, $2 = note text.
# Minimal JSON-escaping of the note (backslash + double-quote) so a reason with
# quotes cannot break the body (curl-only; no jq).
_json_status_note() {
  local status="$1" note_txt="$2" extra=""
  [ -n "$UPDATER_ID" ] && extra=",\"updated_by_agent_id\":\"${UPDATER_ID}\""
  note_txt="${note_txt//\\/\\\\}"; note_txt="${note_txt//\"/\\\"}"
  printf '{"status":"%s","note":"%s"%s}' "$status" "$note_txt" "$extra"
}

# Extract the first "id":"<value>" from a JSON blob (curl-only; no jq).
_extract_id() {
  printf '%s' "$1" | grep -oE '"id"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"([^"]+)"$/\1/'
}

# Extract the first "status":"<value>" from a JSON blob (curl-only; no jq).
_extract_status() {
  printf '%s' "$1" | grep -oE '"status"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"([^"]+)"$/\1/'
}

cmd_start() {
  local task_id=""
  [ -f "$ID_FILE" ] && task_id="$(head -1 "$ID_FILE" 2>/dev/null | tr -d '[:space:]')"

  if [ -z "$task_id" ]; then
    local desc="Skill 38 (Conversational AI System) install — scaffolds the GHL conversational brain: hooks.mappings, communication playbooks, runtime crons, and the mechanical QC gate. Auto-created by scripts/00-verify-prerequisites.sh."
    _api POST "/api/tasks" "$(_json_create "$desc")"
    case "$HTTP_CODE" in
      2??) : ;;
      *) soft_out "create task -> HTTP ${HTTP_CODE}; Command Center reporting skipped (install continues)." ;;
    esac
    task_id="$(_extract_id "$RESP_BODY")"
    [ -n "$task_id" ] || soft_out "create task returned no id; Command Center reporting skipped."
    mkdir -p "$(dirname "$ID_FILE")" 2>/dev/null || true
    printf '%s\n' "$task_id" > "$ID_FILE" 2>/dev/null || true
    note "created install task ${task_id}."
  else
    note "reusing persisted install task ${task_id}."
  fi

  # GET-before-PATCH: never REGRESS a card the independent QC scorer already advanced.
  # A re-run of the install must not drag a `review`/`done` card back to in_progress
  # (or re-open it); only fresh/blocked/backlog cards move to in_progress here.
  _api GET "/api/tasks/${task_id}" ""
  local cur_status=""
  cur_status="$(_extract_status "$RESP_BODY")"
  case "$cur_status" in
    review|done)
      note "task ${task_id} already at '${cur_status}' — not regressing to in_progress (GET-before-PATCH guard). Install continues."
      exit 0 ;;
  esac

  _api PATCH "/api/tasks/${task_id}" "$(_json_status in_progress)"
  case "$HTTP_CODE" in
    2??) note "task ${task_id} -> in_progress." ;;
    *)   note "PATCH in_progress -> HTTP ${HTTP_CODE} (card exists; transition deferred — supply MC_SKILL38_SOP_ID/MC_SKILL38_AGENT_ID for the leave-backlog Triad). Install continues." ;;
  esac
  exit 0
}

cmd_review() {
  local task_id=""
  [ -f "$ID_FILE" ] && task_id="$(head -1 "$ID_FILE" 2>/dev/null | tr -d '[:space:]')"
  [ -n "$task_id" ] || soft_out "no persisted CC task id (${ID_FILE}) — nothing to move to review. Skipped."

  _api PATCH "/api/tasks/${task_id}" "$(_json_status review)"
  case "$HTTP_CODE" in
    2??) note "task ${task_id} -> review (independent CC auto-scorer promotes review to the done column; the builder never self-grades)." ;;
    *)   note "PATCH review -> HTTP ${HTTP_CODE}; Command Center reporting skipped (QC result unchanged)." ;;
  esac
  exit 0
}

# Move the persisted task to `blocked` (QC failed / a gate blocked the install) so
# the failure is VISIBLE on the board and the card is NEVER stranded at in_progress
# or (wrongly) marked done. FIX-XC-06. FAIL-SOFT: always exits 0.
cmd_fail() {
  local task_id="" reason="${REASON:-mechanical QC failed}"
  [ -f "$ID_FILE" ] && task_id="$(head -1 "$ID_FILE" 2>/dev/null | tr -d '[:space:]')"
  [ -n "$task_id" ] || soft_out "no persisted CC task id (${ID_FILE}) — nothing to mark blocked. Skipped."

  _api PATCH "/api/tasks/${task_id}" "$(_json_status_note blocked "$reason")"
  case "$HTTP_CODE" in
    2??) note "task ${task_id} -> blocked (${reason}). A blocked card is never auto-promoted to done; fix and re-run 'start' to re-open it." ;;
    *)   note "PATCH blocked -> HTTP ${HTTP_CODE}; Command Center reporting skipped (QC result unchanged)." ;;
  esac
  exit 0
}

case "$CMD" in
  start)  cmd_start ;;
  review) cmd_review ;;
  fail)   cmd_fail ;;
  *)      soft_out "unknown subcommand '${CMD}' (expected start|review|fail); no-op." ;;
esac
