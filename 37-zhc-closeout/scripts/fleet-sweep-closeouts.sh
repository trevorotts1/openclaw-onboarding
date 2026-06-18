#!/usr/bin/env bash
# fleet-sweep-closeouts.sh — PRD-2.8: fleet sweep to verify + re-deliver missing
# closeouts for already-built clients.
#
# Mirrors the fleet-refresh.sh architecture (dry-run default, --apply opt-in).
# For each client box in the fleet, reads the build-state file and reports:
#   • Whether build is complete (buildCompletedAt set)
#   • closeoutStatus and per-deliverable (closeoutDeliverables) completion
#   • Which legs are missing and need re-run
#
# In --apply mode: for each client whose closeout is incomplete, SSH into the box
# and invoke run-closeout.sh (idempotent). Each box's outcome is isolated.
#
# BOX MANIFEST (--boxes-file): same format as fleet-refresh.sh.
# If no manifest is given, reads FLEET_BOXES_FILE env or defaults to
# ~/.openclaw/fleet/boxes.json (Trevor's standard fleet manifest location).
#
# USAGE:
#   fleet-sweep-closeouts.sh                      # dry-run report (safe)
#   fleet-sweep-closeouts.sh --apply              # re-run missing closeout legs
#   fleet-sweep-closeouts.sh --boxes-file <path>  # custom box manifest
#   fleet-sweep-closeouts.sh --box <name>         # restrict to one box
#   fleet-sweep-closeouts.sh --report-json <path> # write JSON report to file
#   fleet-sweep-closeouts.sh --local              # run against THIS box only
#
# OUTPUT:
#   Per-box table in dry-run. JSON report to --report-json or stdout with --json.
#   Telegram summary to operator (ZHC_OPERATOR_CHAT_ID, default 5252140759)
#   when --apply completes.
#
# EXIT CODES:
#   0  all boxes complete or waived
#   1  fatal (manifest missing, SSH issues)
#   2  at least one box has an incomplete closeout (non-zero = CI-visible)
#
# PRD-2.8 / v11.10.0
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---- flags ----
APPLY=0
LOCAL_MODE=0
BOX_FILTER=""
BOXES_FILE=""
REPORT_JSON_FILE=""
JSON_OUTPUT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)        APPLY=1; shift ;;
    --local)        LOCAL_MODE=1; shift ;;
    --box)          BOX_FILTER="$2"; shift 2 ;;
    --boxes-file)   BOXES_FILE="$2"; shift 2 ;;
    --report-json)  REPORT_JSON_FILE="$2"; shift 2 ;;
    --json)         JSON_OUTPUT=1; shift ;;
    --help|-h)
      sed -n '/#.*/p' "$0" | head -40
      exit 0 ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

# ---- platform detection ----
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[fleet-sweep-closeouts] no OpenClaw root found" >&2
  exit 1
fi

LOG_FILE="$OC_ROOT/workspace/.fleet-sweep-closeouts.log"

log() {
  printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" | tee -a "$LOG_FILE"
}

# ---- closeout leg definitions (the 7 PRD-2.8 fields) ----
# Each entry: "state_field:label"
# An empty or null value means the leg is incomplete.
DELIVERABLE_CHECKS=(
  ".infographic1Url:infographic1"
  ".infographic2Url:infographic2"
  ".celebrationVideoUrl:celebrationVideo"
  ".notionRootPageUrl:notionTree"
  ".closeoutDeliverables.telegramSequenceSent:telegramSequence"
  ".closeoutDeliverables.ccUrlDelivered:ccUrl"
  ".closeoutDeliverables.n8nWired:n8nWired"
)

# ---- helper: check one state file, return JSON summary ----
check_state_file() {
  local state_file="$1"
  local box_name="$2"

  if [[ ! -f "$state_file" ]]; then
    jq -n --arg b "$box_name" '{"box": $b, "status": "no-state-file", "legs": {}}'
    return
  fi

  command -v jq >/dev/null 2>&1 || { echo '{"error":"jq not found"}'; return; }

  build_completed=$(jq -r '.buildCompletedAt // empty' "$state_file" 2>/dev/null)
  closeout_status=$(jq -r '.closeoutStatus // "not-set"' "$state_file" 2>/dev/null)

  if [[ -z "$build_completed" || "$build_completed" == "null" ]]; then
    # PRD-2.15 (v12.3.12): "build not complete" is NOT always benign. If the interview
    # is stalled or QC has failed, classify it as stuck-pre-closeout so the operator
    # can act — don't silently skip it as if it just needs more time.
    _interview_complete=$(jq -r '.interviewComplete // false' "$state_file" 2>/dev/null)
    _interview_stalled=$(jq -r '.interviewStalled // false' "$state_file" 2>/dev/null)
    _qc_st=$(jq -r '.interviewQc.status // "pending"' "$state_file" 2>/dev/null)
    _resume_att=$(jq -r '.resumeAttempts // 0' "$state_file" 2>/dev/null)
    _max_att=$(jq -r '.maxResumeAttempts // 0' "$state_file" 2>/dev/null)
    _stuck_reason=""
    if [[ "$_interview_stalled" == "true" ]]; then
      _stuck_reason="interview-stalled"
    elif [[ "$_qc_st" == "fail" || "$_qc_st" == "needs-review" ]]; then
      _stuck_reason="qc-${_qc_st}"
    elif [[ "$_interview_complete" != "true" ]]; then
      _stuck_reason="interview-in-progress"
    elif [[ "$_max_att" -gt 0 && "$_resume_att" -ge "$_max_att" ]]; then
      _stuck_reason="resume-cap-hit"
    fi
    if [[ -n "$_stuck_reason" && "$_stuck_reason" != "interview-in-progress" ]]; then
      jq -n --arg b "$box_name" --arg r "$_stuck_reason" \
        '{"box": $b, "status": "stuck-pre-closeout", "stuckReason": $r, "legs": {}}'
    else
      jq -n --arg b "$box_name" '{"box": $b, "status": "build-not-complete", "legs": {}}'
    fi
    return
  fi

  # Check each leg
  legs_json="{}"
  all_done=1
  missing_legs=()

  for check in "${DELIVERABLE_CHECKS[@]}"; do
    field="${check%%:*}"
    label="${check##*:}"

    value=$(jq -r "$field // empty" "$state_file" 2>/dev/null)

    # Determine if complete: non-empty, non-null, not "false"
    leg_done=0
    if [[ -n "$value" && "$value" != "null" && "$value" != "false" ]]; then
      leg_done=1
    fi

    # n8nWired can be "skipped" (operator waived it) — treat as done
    if [[ "$label" == "n8nWired" && ( "$value" == "skipped" || "${value}" == "true" || "${value}" == "1" ) ]]; then
      leg_done=1
    fi

    if [[ "$leg_done" -eq 0 ]]; then
      all_done=0
      missing_legs+=("$label")
    fi

    legs_json=$(printf '%s' "$legs_json" | jq \
      --arg l "$label" --arg v "${value:-null}" --argjson done "$leg_done" \
      '.[$l] = {"value": $v, "done": $done}')
  done

  overall="complete"
  if [[ "$all_done" -eq 0 ]]; then
    overall="incomplete"
  fi
  if [[ "$closeout_status" == "done" && "$all_done" -eq 0 ]]; then
    # closeoutStatus says done but deliverable fields are missing → ghost closeout
    overall="ghost-complete"
  fi

  missing_json=$(printf '%s\n' "${missing_legs[@]:-}" | jq -R . | jq -s .)
  jq -n \
    --arg b "$box_name" \
    --arg status "$overall" \
    --arg cs "$closeout_status" \
    --arg bc "$build_completed" \
    --argjson legs "$legs_json" \
    --argjson missing "$missing_json" \
    '{
      box: $b,
      status: $status,
      closeoutStatus: $cs,
      buildCompletedAt: $bc,
      legs: $legs,
      missingLegs: $missing
    }'
}

# ---- LOCAL MODE: just check this box ----
if [[ "$LOCAL_MODE" -eq 1 ]]; then
  # Allow ZHC_STATE_FILE override for tests / non-standard installs
  STATE_FILE="${ZHC_STATE_FILE:-$OC_ROOT/workspace/.workforce-build-state.json}"
  log "INFO" "local mode: checking $STATE_FILE"

  result=$(check_state_file "$STATE_FILE" "local")
  echo "$result" | jq .

  overall=$(printf '%s' "$result" | jq -r '.status')
  missing=$(printf '%s' "$result" | jq -r '.missingLegs | join(", ")')

  if [[ "$overall" == "complete" ]]; then
    log "INFO" "LOCAL BOX: closeout COMPLETE (all 7 legs done)"
    exit 0
  fi

  log "WARN" "LOCAL BOX: closeout INCOMPLETE -- missing: $missing"

  if [[ "$APPLY" -eq 1 ]]; then
    log "INFO" "applying: invoking run-closeout.sh"
    if [[ -x "$SCRIPT_DIR/run-closeout.sh" ]]; then
      bash "$SCRIPT_DIR/run-closeout.sh"
    else
      log "ERROR" "run-closeout.sh not found at $SCRIPT_DIR/run-closeout.sh"
      exit 1
    fi
  else
    log "INFO" "dry-run -- pass --apply to re-run missing legs"
  fi

  exit 2
fi

# ---- FLEET MODE: load box manifest ----
if [[ -z "$BOXES_FILE" ]]; then
  BOXES_FILE="${FLEET_BOXES_FILE:-$HOME/.openclaw/fleet/boxes.json}"
fi

if [[ ! -f "$BOXES_FILE" ]]; then
  log "ERROR" "fleet boxes manifest not found at $BOXES_FILE"
  log "ERROR" "Create it as a JSON array of box objects (see fleet-refresh.sh for format)"
  log "ERROR" "Or use --local to check just this box"
  exit 1
fi

command -v jq >/dev/null 2>&1 || { log "ERROR" "jq required"; exit 1; }

box_count=$(jq 'length' "$BOXES_FILE")
log "INFO" "fleet sweep: $box_count boxes in manifest$(if [[ -n "$BOX_FILTER" ]]; then echo " (filtered to: $BOX_FILTER)"; fi)"
[[ "$APPLY" -eq 0 ]] && log "INFO" "DRY-RUN mode -- pass --apply to re-run missing closeout legs"

# ---- per-box sweep ----
report_json="[]"
any_incomplete=0
boxes_checked=0
boxes_complete=0
boxes_incomplete=0
boxes_no_build=0
boxes_ghost=0
boxes_stuck=0

while IFS= read -r box_json; do
  box_name=$(printf '%s' "$box_json" | jq -r '.name // "unknown"')

  # Apply box filter
  if [[ -n "$BOX_FILTER" && "$box_name" != "$BOX_FILTER" ]]; then
    continue
  fi

  boxes_checked=$((boxes_checked + 1))
  platform=$(printf '%s' "$box_json" | jq -r '.platform // "vps"')
  ssh_target=$(printf '%s' "$box_json" | jq -r '.ssh_target // empty')
  cf_tunnel_id=$(printf '%s' "$box_json" | jq -r '.cf_tunnel_id // empty')
  cf_access_prefix=$(printf '%s' "$box_json" | jq -r '.cf_access_env_prefix // empty')

  log "INFO" "[$box_name] checking closeout status..."

  # ---- resolve state file path on this box ----
  if [[ -z "$ssh_target" ]]; then
    log "WARN" "[$box_name] no ssh_target in manifest -- skipping"
    result=$(jq -n --arg b "$box_name" '{"box": $b, "status": "no-ssh-target"}')
    report_json=$(printf '%s' "$report_json" | jq ". + [$result]")
    continue
  fi

  # ---- build SSH command ----
  SSH_CMD="ssh"
  SSH_OPTS=("-o" "StrictHostKeyChecking=no" "-o" "ConnectTimeout=15" "-o" "BatchMode=yes")

  # Cloudflare Access service token injection
  if [[ -n "$cf_access_prefix" ]]; then
    CLIENT_ID_VAR="${cf_access_prefix}_SVC_CLIENT_ID"
    CLIENT_SECRET_VAR="${cf_access_prefix}_SVC_CLIENT_SECRET"
    client_id="${!CLIENT_ID_VAR:-}"
    client_secret="${!CLIENT_SECRET_VAR:-}"
    if [[ -n "$client_id" && -n "$client_secret" ]]; then
      SSH_OPTS+=("-o" "ProxyCommand=/opt/homebrew/bin/cloudflared access ssh --hostname %h")
      SSH_CMD="CF_ACCESS_CLIENT_ID=$client_id CF_ACCESS_CLIENT_SECRET=$client_secret ssh"
    fi
  fi

  # Resolve state file path based on platform
  if [[ "$platform" == "mac" ]]; then
    remote_state_path='$HOME/.openclaw/workspace/.workforce-build-state.json'
  else
    remote_state_path='/data/.openclaw/workspace/.workforce-build-state.json'
  fi

  # ---- fetch state file via SSH ----
  state_content=""
  fetch_rc=0
  state_content=$(eval "$SSH_CMD" "${SSH_OPTS[@]}" "$ssh_target" \
    "cat $remote_state_path 2>/dev/null || echo 'NOT_FOUND'" 2>>"$LOG_FILE") || fetch_rc=$?

  if [[ "$fetch_rc" -ne 0 || "$state_content" == "NOT_FOUND" || -z "$state_content" ]]; then
    log "WARN" "[$box_name] could not fetch state file (rc=$fetch_rc or NOT_FOUND)"
    result=$(jq -n --arg b "$box_name" '{"box": $b, "status": "ssh-failed-or-no-state"}')
    report_json=$(printf '%s' "$report_json" | jq ". + [$result]")
    continue
  fi

  # ---- write to tmp and analyze ----
  tmp_state=$(mktemp)
  printf '%s' "$state_content" > "$tmp_state"

  result=$(check_state_file "$tmp_state" "$box_name")
  rm -f "$tmp_state"

  overall=$(printf '%s' "$result" | jq -r '.status')
  missing=$(printf '%s' "$result" | jq -r '.missingLegs | join(", ")')
  cs=$(printf '%s' "$result" | jq -r '.closeoutStatus')

  case "$overall" in
    complete)
      log "INFO" "[$box_name] closeout COMPLETE (closeoutStatus=$cs, all 7 legs done)"
      boxes_complete=$((boxes_complete + 1)) ;;
    incomplete)
      log "WARN" "[$box_name] closeout INCOMPLETE (closeoutStatus=$cs, missing: $missing)"
      boxes_incomplete=$((boxes_incomplete + 1))
      any_incomplete=1 ;;
    ghost-complete)
      log "ERROR" "[$box_name] GHOST closeout (closeoutStatus=done but deliverable fields missing: $missing)"
      boxes_ghost=$((boxes_ghost + 1))
      any_incomplete=1 ;;
    build-not-complete)
      log "INFO" "[$box_name] build not complete yet -- skipping closeout check"
      boxes_no_build=$((boxes_no_build + 1)) ;;
    stuck-pre-closeout)
      _stuck_r=$(printf '%s' "$result" | jq -r '.stuckReason // "unknown"')
      log "WARN" "[$box_name] STUCK PRE-CLOSEOUT (reason: $_stuck_r) -- surfacing for operator; run fleet-stuck-clients.sh for details"
      boxes_stuck=$((boxes_stuck + 1))
      any_incomplete=1 ;;
    *)
      log "WARN" "[$box_name] unexpected status: $overall"
  esac

  report_json=$(printf '%s' "$report_json" | jq ". + [$result]")

  # ---- apply: re-run missing legs via SSH ----
  if [[ "$APPLY" -eq 1 && ( "$overall" == "incomplete" || "$overall" == "ghost-complete" ) ]]; then
    log "INFO" "[$box_name] APPLYING: invoking run-closeout.sh via SSH"

    if [[ "$platform" == "mac" ]]; then
      remote_skill_path='$HOME/.openclaw/skills/37-zhc-closeout/scripts/run-closeout.sh'
    else
      remote_skill_path='/data/.openclaw/skills/37-zhc-closeout/scripts/run-closeout.sh'
    fi

    apply_rc=0
    eval "$SSH_CMD" "${SSH_OPTS[@]}" "$ssh_target" \
      "bash $remote_skill_path >> ${remote_state_path%/*}/.zhc-closeout.log 2>&1" \
      >>"$LOG_FILE" 2>&1 || apply_rc=$?

    if [[ "$apply_rc" -eq 0 ]]; then
      log "INFO" "[$box_name] run-closeout.sh completed (rc=0)"
    else
      log "WARN" "[$box_name] run-closeout.sh returned rc=$apply_rc (may still be in progress -- cron will pick up)"
    fi
    result=$(printf '%s' "$result" | jq --argjson rc "$apply_rc" '. + {"applyRc": $rc}')
    report_json=$(printf '%s' "$report_json" | jq ".[length-1] = $result")
  fi

done < <(jq -c '.[]' "$BOXES_FILE")

# ---- summary ----
log "INFO" "fleet sweep summary: checked=$boxes_checked complete=$boxes_complete incomplete=$boxes_incomplete ghost=$boxes_ghost no-build=$boxes_no_build stuck-pre-closeout=$boxes_stuck"

# ---- write JSON report ----
summary_json=$(jq -n \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --argjson checked "$boxes_checked" \
  --argjson complete "$boxes_complete" \
  --argjson incomplete "$boxes_incomplete" \
  --argjson ghost "$boxes_ghost" \
  --argjson no_build "$boxes_no_build" \
  --argjson applied "$APPLY" \
  --argjson boxes "$report_json" \
  '{
    sweepAt: $ts,
    dryRun: ($applied == 0),
    summary: {
      checked: $checked,
      complete: $complete,
      incomplete: $incomplete,
      ghostComplete: $ghost,
      buildNotComplete: $no_build
    },
    boxes: $boxes
  }')

if [[ -n "$REPORT_JSON_FILE" ]]; then
  printf '%s\n' "$summary_json" > "$REPORT_JSON_FILE"
  log "INFO" "JSON report written to $REPORT_JSON_FILE"
fi

if [[ "$JSON_OUTPUT" -eq 1 ]]; then
  printf '%s\n' "$summary_json"
fi

# ---- operator Telegram summary (apply mode only) ----
# CO-MINGLING GUARD (v12.4.0): destination is OPT-IN. NO hardcoded personal chat.
if [[ "$APPLY" -eq 1 && "$any_incomplete" -eq 1 ]]; then
  OPERATOR_CHAT="${OPERATOR_ESCALATION_CHAT_ID:-${ZHC_OPERATOR_CHAT_ID:-}}"
  summary_msg="🔄 ZHC Closeout Fleet Sweep APPLIED
Boxes checked: $boxes_checked
Complete:       $boxes_complete
Incomplete:     $boxes_incomplete (re-run triggered)
Ghost complete: $boxes_ghost
Build pending:  $boxes_no_build
Stuck pre-close: $boxes_stuck (run fleet-stuck-clients.sh for details)
run-closeout.sh was invoked on each incomplete box. Cron will pick up any remaining legs within 15 min."

  if [[ -n "$OPERATOR_CHAT" ]] && command -v openclaw >/dev/null 2>&1; then
    openclaw message send --channel telegram --target "$OPERATOR_CHAT" \
      --message "$summary_msg" >/dev/null 2>&1 || true
  else
    [[ -z "$OPERATOR_CHAT" ]] && log "INFO" "operator escalation chat not configured (OPERATOR_ESCALATION_CHAT_ID/ZHC_OPERATOR_CHAT_ID unset) — skipping fleet-sweep summary send"
  fi
fi

# ---- final exit ----
if [[ "$any_incomplete" -eq 1 ]]; then
  exit 2
fi
exit 0
