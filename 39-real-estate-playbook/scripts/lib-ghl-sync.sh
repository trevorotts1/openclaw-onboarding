#!/usr/bin/env bash
# lib-ghl-sync.sh — Skill 39 fail-soft GoHighLevel + Command-Center write layer.
#
# Sourced or called. Turns the prose-only GHL "dependency" into real, deterministic,
# SAFE writes through the Tier-0 convert-and-flow CLI (caf) and the Command Center
# Kanban API — every call an HONEST no-op when its credential is absent.
#
#   ghl_tag         <contact_ref> <tag> [tag...]
#       -> caf contacts add-tag <contact_ref> <tag...>   (apply ZHC RE tags)
#   ghl_opportunity create <pipeline_id> <stage_id> <name> <contact_id> [value]
#   ghl_opportunity move   <opportunity_id> <stage_id> [status]
#       -> caf opportunities create|update               (real pipeline placement)
#   ghl_book        <calendar_id> <contact_id> <slot_id> <start_iso> <end_iso> [title]
#       -> caf calendars book                            (GHL-native showing + reminders)
#   cc_move         <task_id> <status> [agent_id]
#       -> PATCH {MISSION_CONTROL_URL:-http://localhost:4000}/api/tasks/{id}
#
# DESIGN — fail-soft, honest, never fabricated:
#   * GHL writes run through caf ($HOME/.openclaw/tools/convert-and-flow-cli/caf),
#     which is Tier-0 / draft-only / safe-by-default. A write is ARMED only when a
#     GoHighLevel credential is EXPORTED in the environment: canonical
#     GOHIGHLEVEL_API_KEY (preferred), or the CAF_API_KEY / GHL_API_KEY aliases caf
#     also honors. If caf is missing OR no credential is exported, the call prints
#     ONE "[skill 39][ghl] honest-gap: ..." line, appends a ghl_sync event
#     (available:false) via lib-re-events.sh, and returns 0 — it NEVER fakes success.
#   * cc_move PATCHes the Command Center task with Authorization: Bearer
#     $MC_API_TOKEN. When MC_API_TOKEN is unset, the column is invalid, or the board
#     is unreachable, it is an honest no-op — NO PATCH is sent.
#   * SELF-GRADE GUARD: a builder may NOT promote its OWN task to done (the
#     independent dept-QC scorer owns review->done — enforced server-side too).
#     cc_move sends NO PATCH when status=done unless it can PROVE the acting agent
#     is NOT the task builder (created_by_agent_id, fetched from the board). When
#     the builder cannot be confirmed, it refuses (fail-safe — never self-promotes).
#
# Never prints a secret value. UNIVERSAL: no client/personal data. bash (not zsh).
# OS-aware via the helpers it calls. Requires curl + jq for live calls (both
# degrade to an honest no-op when absent). set -uo pipefail (fail-soft, not -e).

set -uo pipefail

GHL_P="[skill 39][ghl]"
CC_P="[skill 39][cc]"

_LIB_GHL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
LIB_RE_EVENTS="$_LIB_GHL_DIR/lib-re-events.sh"

# --------------------------------------------------------------------------- #
# internal helpers
# --------------------------------------------------------------------------- #

# Resolve the caf binary: PATH first, then the canonical install location.
_caf_bin() {
  if command -v caf >/dev/null 2>&1; then command -v caf; return 0; fi
  local fallback="$HOME/.openclaw/tools/convert-and-flow-cli/caf"
  [ -x "$fallback" ] && { printf '%s' "$fallback"; return 0; }
  return 1
}

# A GoHighLevel credential is ARMED only when exported in the environment.
# Canonical name first; the two aliases caf also resolves are accepted.
_ghl_creds_present() {
  [ -n "${GOHIGHLEVEL_API_KEY:-}" ] || [ -n "${CAF_API_KEY:-}" ] || [ -n "${GHL_API_KEY:-}" ]
}

# Append one PII-free ghl_sync event through the centralized contract helper.
# _sync_event <source> <action> <true|false> [reason]
_sync_event() {
  local src="${1:-caf}" action="${2:-}" available="${3:-false}" reason="${4:-}"
  [ -f "$LIB_RE_EVENTS" ] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  case "$available" in true|false) ;; *) available="false" ;; esac
  local payload
  payload="$(jq -cn \
    --arg src "$src" \
    --arg action "$action" \
    --argjson available "$available" \
    --arg reason "$reason" \
    '{lead_ref:"n/a", source:$src, action:$action, available:$available}
       + (if $reason == "" then {} else {reason:$reason} end)' 2>/dev/null)" || return 0
  [ -n "$payload" ] || return 0
  bash "$LIB_RE_EVENTS" re_event ghl_sync "$payload" >/dev/null 2>&1 || true
  return 0
}

# GET the task and return its builder id (created_by_agent_id) or "".
# Used only by the cc_move done self-grade guard. Never raises.
_cc_task_builder() { # base task_id -> created_by_agent_id (or "")
  local base="$1" task_id="$2" json builder=""
  command -v curl >/dev/null 2>&1 || { printf ''; return 0; }
  json="$(curl -sS --connect-timeout 5 --max-time 12 \
    -H "Authorization: Bearer ${MC_API_TOKEN:-}" \
    "$base/api/tasks/$task_id" 2>/dev/null)" || { printf ''; return 0; }
  [ -n "$json" ] || { printf ''; return 0; }
  if command -v jq >/dev/null 2>&1; then
    builder="$(printf '%s' "$json" | jq -r '.created_by_agent_id // empty' 2>/dev/null || printf '')"
  fi
  printf '%s' "${builder:-}"
}

# --------------------------------------------------------------------------- #
# public: GHL writes via caf (Tier-0, draft-only, safe-by-default)
# --------------------------------------------------------------------------- #

# Apply one or more ZHC RE tags to a GHL contact.
ghl_tag() {
  local contact_ref="${1:-}"
  shift 2>/dev/null || true
  local tags=( "$@" )
  if [ -z "$contact_ref" ] || [ "${#tags[@]}" -eq 0 ]; then
    echo "$GHL_P usage: ghl_tag <contact_ref> <tag> [tag...]" >&2
    return 2
  fi
  local caf
  if ! caf="$(_caf_bin)"; then
    echo "$GHL_P honest-gap: caf CLI not found — tag(s) '${tags[*]}' NOT applied (no fabrication). Install convert-and-flow-cli to enable GHL tagging."
    _sync_event caf tag false caf-missing
    return 0
  fi
  if ! _ghl_creds_present; then
    echo "$GHL_P honest-gap: no GoHighLevel credential exported (set GOHIGHLEVEL_API_KEY) — tag(s) '${tags[*]}' NOT applied (no fabrication)."
    _sync_event caf tag false no-credential
    return 0
  fi
  if "$caf" contacts add-tag "$contact_ref" "${tags[@]}" >/dev/null 2>&1; then
    echo "$GHL_P applied tag(s) '${tags[*]}' to the contact via caf"
    _sync_event caf tag true ""
    return 0
  fi
  echo "$GHL_P honest-gap: caf contacts add-tag failed for '${tags[*]}' (credential / contact id / safety-gate) — NOT applied (no fabrication)."
  _sync_event caf tag false caf-error
  return 0
}

# Place / move a qualified lead in a real GHL pipeline stage.
ghl_opportunity() {
  local sub="${1:-}"
  shift 2>/dev/null || true
  case "$sub" in
    create|move) ;;
    *) echo "$GHL_P usage: ghl_opportunity {create <pipeline_id> <stage_id> <name> <contact_id> [value] | move <opportunity_id> <stage_id> [status]}" >&2
       return 2 ;;
  esac
  local caf
  if ! caf="$(_caf_bin)"; then
    echo "$GHL_P honest-gap: caf CLI not found — opportunity '$sub' NOT performed (no fabrication)."
    _sync_event caf opportunity false caf-missing
    return 0
  fi
  if ! _ghl_creds_present; then
    echo "$GHL_P honest-gap: no GoHighLevel credential exported (set GOHIGHLEVEL_API_KEY) — opportunity '$sub' NOT performed (no fabrication)."
    _sync_event caf opportunity false no-credential
    return 0
  fi
  local rc=1
  if [ "$sub" = "create" ]; then
    local pipeline_id="${1:-}" stage_id="${2:-}" name="${3:-}" contact_id="${4:-}" value="${5:-}"
    if [ -z "$pipeline_id" ] || [ -z "$stage_id" ] || [ -z "$name" ] || [ -z "$contact_id" ]; then
      echo "$GHL_P usage: ghl_opportunity create <pipeline_id> <stage_id> <name> <contact_id> [value]" >&2
      return 2
    fi
    if [ -n "$value" ]; then
      "$caf" opportunities create --pipeline-id "$pipeline_id" --stage-id "$stage_id" --name "$name" --contact-id "$contact_id" --value "$value" >/dev/null 2>&1 && rc=0 || rc=1
    else
      "$caf" opportunities create --pipeline-id "$pipeline_id" --stage-id "$stage_id" --name "$name" --contact-id "$contact_id" >/dev/null 2>&1 && rc=0 || rc=1
    fi
  else
    local opp_id="${1:-}" stage_id="${2:-}" status="${3:-}"
    if [ -z "$opp_id" ] || [ -z "$stage_id" ]; then
      echo "$GHL_P usage: ghl_opportunity move <opportunity_id> <stage_id> [status]" >&2
      return 2
    fi
    if [ -n "$status" ]; then
      "$caf" opportunities update "$opp_id" --stage-id "$stage_id" --status "$status" >/dev/null 2>&1 && rc=0 || rc=1
    else
      "$caf" opportunities update "$opp_id" --stage-id "$stage_id" >/dev/null 2>&1 && rc=0 || rc=1
    fi
  fi
  if [ "$rc" -eq 0 ]; then
    echo "$GHL_P opportunity '$sub' performed via caf"
    _sync_event caf opportunity true ""
  else
    echo "$GHL_P honest-gap: caf opportunities '$sub' failed (credential / id / safety-gate) — NOT performed (no fabrication)."
    _sync_event caf opportunity false caf-error
  fi
  return 0
}

# Book a showing as a GHL-native calendar appointment (carries native reminders).
ghl_book() {
  local calendar_id="${1:-}" contact_id="${2:-}" slot_id="${3:-}" start="${4:-}" end="${5:-}" title="${6:-}"
  if [ -z "$calendar_id" ] || [ -z "$contact_id" ] || [ -z "$slot_id" ] || [ -z "$start" ] || [ -z "$end" ]; then
    echo "$GHL_P usage: ghl_book <calendar_id> <contact_id> <slot_id> <start_iso> <end_iso> [title]" >&2
    return 2
  fi
  local caf
  if ! caf="$(_caf_bin)"; then
    echo "$GHL_P honest-gap: caf CLI not found — showing NOT booked (no fabrication)."
    _sync_event caf book false caf-missing
    return 0
  fi
  if ! _ghl_creds_present; then
    echo "$GHL_P honest-gap: no GoHighLevel credential exported (set GOHIGHLEVEL_API_KEY) — showing NOT booked (no fabrication)."
    _sync_event caf book false no-credential
    return 0
  fi
  local rc=1
  if [ -n "$title" ]; then
    "$caf" calendars book --calendar-id "$calendar_id" --contact-id "$contact_id" --slot-id "$slot_id" --start "$start" --end "$end" --title "$title" >/dev/null 2>&1 && rc=0 || rc=1
  else
    "$caf" calendars book --calendar-id "$calendar_id" --contact-id "$contact_id" --slot-id "$slot_id" --start "$start" --end "$end" >/dev/null 2>&1 && rc=0 || rc=1
  fi
  if [ "$rc" -eq 0 ]; then
    echo "$GHL_P showing booked via caf (GHL-native appointment + reminders)"
    _sync_event caf book true ""
  else
    echo "$GHL_P honest-gap: caf calendars book failed (credential / slot id / safety-gate) — showing NOT booked (no fabrication)."
    _sync_event caf book false caf-error
  fi
  return 0
}

# --------------------------------------------------------------------------- #
# public: Command Center Kanban move
# --------------------------------------------------------------------------- #

cc_move() {
  local task_id="${1:-}" status="${2:-}" agent_id="${3:-}"
  if [ -z "$task_id" ] || [ -z "$status" ]; then
    echo "$CC_P usage: cc_move <task_id> <status> [agent_id]" >&2
    return 2
  fi
  case "$status" in
    backlog|in_progress|review|done) ;;
    *) echo "$CC_P honest no-op: invalid status '$status' (allowed: backlog,in_progress,review,done) — NO PATCH sent."
       _sync_event command-center cc_move false invalid-status
       return 0 ;;
  esac
  if [ -z "${MC_API_TOKEN:-}" ]; then
    echo "$CC_P honest no-op: MC_API_TOKEN unset — Command Center card NOT moved to '$status' (NO PATCH)."
    _sync_event command-center cc_move false no-token
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "$CC_P honest no-op: curl not on PATH — Command Center card NOT moved to '$status' (NO PATCH)."
    _sync_event command-center cc_move false no-curl
    return 0
  fi
  local base
  base="${MISSION_CONTROL_URL:-http://localhost:4000}"
  base="${base%/}"

  # SELF-GRADE GUARD: a builder never promotes its OWN task to done. NO PATCH is
  # sent unless the acting agent is PROVEN to differ from the task builder.
  if [ "$status" = "done" ]; then
    local builder
    builder="$(_cc_task_builder "$base" "$task_id")"
    if [ -z "$builder" ]; then
      echo "$CC_P honest no-op: cannot confirm the builder of task '$task_id' (board unreachable or field absent) — refusing self-promotion to done (NO PATCH)."
      _sync_event command-center cc_move false done-builder-unknown
      return 0
    fi
    if [ -n "$agent_id" ] && [ "$agent_id" = "$builder" ]; then
      echo "$CC_P honest no-op: acting agent is the task builder — a builder never self-PATCHes its own task to done (independent QC owns review->done). NO PATCH."
      _sync_event command-center cc_move false done-self-grade
      return 0
    fi
  fi

  # Perform the PATCH (fail-soft).
  local body http
  body="$(jq -cn --arg s "$status" --arg a "$agent_id" \
    'if $a == "" then {status:$s} else {status:$s, updated_by_agent_id:$a} end' 2>/dev/null)" \
    || body="{\"status\":\"$status\"}"
  http="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 12 \
    -X PATCH "$base/api/tasks/$task_id" \
    -H "Authorization: Bearer $MC_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data "$body" 2>/dev/null)" || http="000"
  case "$http" in
    200|201|204)
      echo "$CC_P moved task '$task_id' -> '$status' (HTTP $http)"
      _sync_event command-center cc_move true ""
      ;;
    *)
      echo "$CC_P honest no-op: Command Center PATCH '$task_id' -> '$status' returned HTTP $http (board unreachable or rejected) — state unchanged (no fabrication)."
      _sync_event command-center cc_move false "http-$http"
      ;;
  esac
  return 0
}

# --------------------------------------------------------------------------- #
# direct-invocation dispatch (sourced use is unaffected)
# --------------------------------------------------------------------------- #
if [ "${BASH_SOURCE[0]:-}" = "${0:-}" ]; then
  cmd="${1:-}"
  shift 2>/dev/null || true
  case "$cmd" in
    ghl_tag)         ghl_tag "$@" ;;
    ghl_opportunity) ghl_opportunity "$@" ;;
    ghl_book)        ghl_book "$@" ;;
    cc_move)         cc_move "$@" ;;
    -h|--help|help)  sed -n '1,60p' "$0" ;;
    *) echo "usage: $0 {ghl_tag|ghl_opportunity|ghl_book|cc_move} ..." >&2; exit 2 ;;
  esac
fi
