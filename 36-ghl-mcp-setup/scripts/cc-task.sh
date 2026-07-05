#!/usr/bin/env bash
# cc-task.sh — Command Center Kanban task-lifecycle reporting for the Skill 36
# (GHL MCP Setup) install/QC flow. GRACEFUL-DEGRADING: it never fails the caller
# and never messages a client — every failure path prints ONE operator-only
# stderr line and exits 0. Modeled byte-for-byte on 38's scripts/cc-task.sh so
# the two skills drive the SAME Command Center board with one shared contract.
#
# WHY THIS EXISTS
#   INSTRUCTIONS.md documents four operator-visibility "emit" moments (install
#   start, install complete, 429 lockout, missing-credential) but shipped NO
#   implementing script — so the board never actually moved. This helper is the
#   implementation for the two lifecycle moments an install can drive
#   deterministically (start + complete); the two runtime tier-incident cards
#   stay best-effort operator notes per INSTRUCTIONS.md.
#
# SUBCOMMANDS
#   start   Create-or-reuse the Skill-36 install task, then move it to
#           `in_progress` (install has started). Wired into INSTALL.md's
#           Autonomous Setup Execution (first action).
#   review  Move the persisted task to `review` (QC passed). The independent
#           Command Center auto-scorer is the ONLY authority that advances
#           review -> the done column — the builder NEVER self-grades (the CC API
#           rejects a builder self-advance with 403). So this only ever sets
#           `review`; it never sets the done status. Wired into the
#           qc-ghl-mcp-setup.sh PASS branch.
#
# CONFIG (all optional except MC_API_TOKEN for a live post):
#   MISSION_CONTROL_URL   base URL (default http://localhost:4000)
#   MC_API_TOKEN          bearer token (from command-center app/.env.local). If
#                         unset -> one stderr note + exit 0 (no-op).
#   MC_SKILL36_AGENT_ID   optional agent UUID -> created_by_agent_id +
#                         updated_by_agent_id on transitions (for a live board).
#   MC_SKILL36_SOP_ID     optional SOP UUID -> sop_id (part of the leave-backlog
#                         Triad). Omitted if unset (the API keeps the card in
#                         backlog until the Triad is satisfied — still graceful).
#
# The task id is persisted to $HOME/.openclaw/.skill-36-cc-task-id (VPS: under
# /data/.openclaw) so re-runs reuse the same card (idempotent).
#
# DEPENDENCY: curl only. bash-not-zsh: always invoke via `bash`.
#
# NOTE: `set -u -o pipefail` but intentionally NOT `-e` — we handle every rc
# ourselves so a Command Center hiccup can never abort the install.

set -uo pipefail

CMD="${1:-}"

BASE_URL="${MISSION_CONTROL_URL:-http://localhost:4000}"
BASE_URL="${BASE_URL%/}"
TOKEN="${MC_API_TOKEN:-}"

CREATOR_ID="${MC_SKILL36_AGENT_ID:-}"   # created_by_agent_id (UUID) if supplied
UPDATER_ID="${MC_SKILL36_AGENT_ID:-}"   # updated_by_agent_id (UUID) if supplied
SOP_ID="${MC_SKILL36_SOP_ID:-}"         # sop_id (UUID) if supplied

if [ -d /data/.openclaw ]; then OC_ROOT="/data/.openclaw"; else OC_ROOT="$HOME/.openclaw"; fi
ID_FILE="${SKILL36_CC_TASK_ID_FILE:-$OC_ROOT/.skill-36-cc-task-id}"

# Operator-only stderr; NEVER a client channel. Never prints the token.
note() { echo "[skill36][cc-task] $*" >&2; }

# Graceful no-op: exactly one stderr note, then succeed (never fail the caller).
soft_out() { note "$*"; exit 0; }

[ -n "$CMD" ] || soft_out "usage: cc-task.sh {start|review} — no subcommand; no-op."
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
  printf '{"title":"Skill 36 — GHL MCP Setup install","description":"%s","priority":"medium","department":"Operations"%s}' "$desc" "$extra"
}

# Build a status-transition JSON body. $1 = target column (in_progress | review).
_json_status() {
  if [ -n "$UPDATER_ID" ]; then
    printf '{"status":"%s","updated_by_agent_id":"%s"}' "$1" "$UPDATER_ID"
  else
    printf '{"status":"%s"}' "$1"
  fi
}

# Extract the first "id":"<value>" from a JSON blob (curl-only; no jq).
_extract_id() {
  printf '%s' "$1" | grep -oE '"id"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"([^"]+)"$/\1/'
}

cmd_start() {
  local task_id=""
  [ -f "$ID_FILE" ] && task_id="$(head -1 "$ID_FILE" 2>/dev/null | tr -d '[:space:]')"

  if [ -z "$task_id" ]; then
    local desc="Skill 36 (GHL MCP Setup) install — registers the 6-tier GoHighLevel access chain (Tier 0 Convert and Flow CLI, Tier 1 Official MCP, Tier 2 Community MCP on-demand, Tier 3 REST, Tier 4 browser, Tier 5 Computer Use) and wires the tier-escalation protocol into the core .md files. Auto-created by INSTALL.md's Autonomous Setup Execution."
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

  _api PATCH "/api/tasks/${task_id}" "$(_json_status in_progress)"
  case "$HTTP_CODE" in
    2??) note "task ${task_id} -> in_progress." ;;
    *)   note "PATCH in_progress -> HTTP ${HTTP_CODE} (card exists; transition deferred — supply MC_SKILL36_SOP_ID/MC_SKILL36_AGENT_ID for the leave-backlog Triad). Install continues." ;;
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

case "$CMD" in
  start)  cmd_start ;;
  review) cmd_review ;;
  *)      soft_out "unknown subcommand '${CMD}' (expected start|review); no-op." ;;
esac
