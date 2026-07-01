#!/usr/bin/env bash
# lib-command-center.sh -- Skill 41 Build With AI Playbook Generator
#
# Best-effort Command Center (mission-control Kanban) reflection. The skill creates
# GHL dependencies, builds + verifies a workflow, and logs to build-with-ai-events.jsonl;
# this helper ADDITIONALLY moves the operator's Kanban card across columns as the build
# progresses so the board reflects real work. It is a SILENT NO-OP when the Command
# Center is unreachable (client VPSes may not run it) and NEVER fatal -- it never blocks
# a build, never writes the CC database (HTTP only), and never prints the auth token.
#
# Source it, do not execute it:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib-command-center.sh"
#
# Contract (mirrors scripts/lib-master-files.sh helper style):
#   cc_url                       -> echoes the base URL.
#   cc_available                 -> 0 if /api/health answers, else nonzero; prints nothing.
#   cc_move_task <id> <st> <ag>  -> PATCHes /api/tasks/<id>; best-effort, operator-only stderr.
#
# Env:
#   MISSION_CONTROL_URL  base URL          (default http://localhost:4000)
#   MC_API_TOKEN         bearer token      (sent ONLY in the Authorization header)

# cc_url -- base URL of the Command Center, env-overridable.
cc_url() {
  echo "${MISSION_CONTROL_URL:-http://localhost:4000}"
}

# cc_status_valid <status> -- 0 if the status is a known Kanban column, else 1.
cc_status_valid() {
  case "${1:-}" in
    backlog|inbox|planning|in_progress|assigned|review|testing|blocked|pending_dispatch|done)
      return 0 ;;
    *) return 1 ;;
  esac
}

# cc_available -- health probe. Returns curl's status; prints nothing. Short timeout so a
# missing Command Center never stalls a build.
cc_available() {
  curl -fsS --max-time 3 "$(cc_url)/api/health" >/dev/null 2>&1
}

# cc_move_task <task_id> <status> <agent_id>
#   Moves a Command Center card to <status>. Best-effort and fail-soft:
#     - empty task_id            -> no-op, return 0 (nothing to move)
#     - status not a valid column-> stderr "bad status", return 2
#     - status == done           -> refuse; done is owned by CC's QC scorer, return 3
#     - Command Center down       -> silent no-op, return 0
#     - PATCH non-2xx / transport -> operator-only WARNING to stderr, return 0 (never fatal)
#   The bearer token is passed ONLY inside the Authorization header; it is never echoed.
cc_move_task() {
  local task_id="${1:-}" status="${2:-}" agent_id="${3:-}"

  # Nothing to move -- silent success (best-effort).
  [[ -z "$task_id" ]] && return 0

  if ! cc_status_valid "$status"; then
    echo "[skill 41][cc] bad status: '$status' (not a Kanban column) -- card not moved" >&2
    return 2
  fi

  if [[ "$status" == "done" ]]; then
    echo "[skill 41][cc] refusing 'done': review->done is set by the Command Center QC scorer, not the builder" >&2
    return 3
  fi

  # Health-gated: if the Command Center is not reachable, do nothing (silent no-op).
  cc_available || return 0

  local url body out http_code
  url="$(cc_url)/api/tasks/${task_id}"
  body="$(jq -nc --arg s "$status" --arg a "$agent_id" '{status:$s, updated_by_agent_id:$a}')"

  # Token only ever appears here, by name, inside the header argument.
  local args=(-sS -X PATCH --max-time 8 -w $'\n%{http_code}'
    -H "Authorization: Bearer ${MC_API_TOKEN:-}"
    -H "Content-Type: application/json"
    -d "$body")

  if ! out="$(curl "${args[@]}" "$url" 2>/dev/null)"; then
    echo "[skill 41][cc] WARNING: PATCH ${url} transport error -- card not moved (non-fatal)" >&2
    return 0
  fi

  http_code="${out##*$'\n'}"
  if [[ "$http_code" =~ ^2[0-9][0-9]$ ]]; then
    echo "[skill 41][cc] task ${task_id} -> ${status} (HTTP ${http_code})" >&2
  else
    echo "[skill 41][cc] WARNING: task ${task_id} -> ${status} failed (HTTP ${http_code}) -- non-fatal" >&2
  fi
  return 0
}
