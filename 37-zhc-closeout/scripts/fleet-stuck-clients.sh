#!/usr/bin/env bash
# fleet-stuck-clients.sh — PRD-2.15: operator surface for clients who are
# stuck BEFORE the closeout sweep can reach them.
#
# This is the MISSING SCREEN that answers "who is one step from their ZHC and
# stuck?" — the thing that was missing when a client sat for 9 days after Q22.
#
# fleet-sweep-closeouts.sh only checks clients whose buildCompletedAt is set.
# This script surfaces clients who NEVER MAKE IT that far: stalled interviews,
# failed QC, wedged builds, and blocked closeouts.
#
# Reuses the fleet-sweep-closeouts.sh box-manifest + SSH harness verbatim.
#
# USAGE:
#   fleet-stuck-clients.sh                      # report stuck clients
#   fleet-stuck-clients.sh --apply              # Telegram operator summary
#   fleet-stuck-clients.sh --local              # run against THIS box only
#   fleet-stuck-clients.sh --boxes-file <path>  # custom manifest
#   fleet-stuck-clients.sh --box <name>         # restrict to one box
#
# OUTPUT:
#   Table:
#     BOX            STAGE                 IDLE   QC      BLOCKERS
#     <client>       mid-interview(21/30)  9d     -       STUCK_MID_INTERVIEW
#
# EXIT CODES:
#   0  no stuck clients
#   1  fatal (manifest missing)
#   2  at least one stuck client (CI-visible)
#
# PRD-2.15 / v12.3.12
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WATCHDOG_SCRIPT="${SKILL_DIR%/*}/23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh"

# ---- flags ----
APPLY=0
LOCAL_MODE=0
BOX_FILTER=""
BOXES_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)       APPLY=1; shift ;;
    --local)       LOCAL_MODE=1; shift ;;
    --box)         BOX_FILTER="$2"; shift 2 ;;
    --boxes-file)  BOXES_FILE="$2"; shift 2 ;;
    --help|-h)
      sed -n '2,/^$/p' "$0" | head -40
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
  echo "[fleet-stuck-clients] no OpenClaw root found" >&2
  exit 1
fi

LOG_FILE="$OC_ROOT/workspace/.fleet-stuck-clients.log"

log() {
  printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" | tee -a "$LOG_FILE"
}

# ── Stuck class evaluation (token-free) ──────────────────────────────────────
# Args: state_json_string
# Returns: class|reason|idle_label via stdout as TAB-separated
compute_stuck_class() {
  local state_json="$1"
  python3 - <<PYEOF
import json, sys
from datetime import datetime, timezone

raw = """${state_json}"""
try:
    s = json.loads(raw)
except Exception:
    sys.exit(0)

import time
now = time.time()

def hours_since(ts):
    if not ts:
        return 0
    ts = str(ts).rstrip('Z')
    try:
        dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        return int((now - dt.timestamp()) / 3600)
    except:
        return 0

interview_complete = s.get('interviewComplete', False)
last_q_at = s.get('interviewProgress', {}).get('lastQuestionAt', '')
qc_status = (s.get('interviewQc') or {}).get('status', '')
build_done = s.get('buildCompletedAt', '')
closeout_st = s.get('closeoutStatus', '')
resume_att = s.get('resumeAttempts', 0) or 0
max_att = s.get('maxResumeAttempts', 0) or 0
q_count = (s.get('interviewProgress') or {}).get('questionCount', '?')

STUCK_INTERVIEW_DAYS = int('${ZHC_STUCK_INTERVIEW_DAYS:-5}')
STUCK_NOSTART_DAYS   = int('${ZHC_STUCK_NOSTART_DAYS:-3}')
STUCK_CLOSEOUT_HOURS = int('${ZHC_STUCK_CLOSEOUT_HOURS:-12}')

blockers = []
for b in (s.get('closeoutBlockers') or []):
    if not b.get('cleared', False):
        blockers.append(b.get('class', '?'))

if not interview_complete:
    if last_q_at:
        idle_h = hours_since(last_q_at)
        idle_d = idle_h // 24
        if idle_d >= STUCK_INTERVIEW_DAYS:
            stage = f"mid-interview({q_count}/30)"
            idle = f"{idle_d}d"
            bc = blockers or ["STUCK_MID_INTERVIEW"]
            print(f"STUCK_MID_INTERVIEW\t{stage}\t{idle}\t-\t{','.join(bc)}")
    else:
        # Never started — use state file age (we don't have it here, caller sets threshold)
        pass
elif qc_status in ('fail', 'needs-review'):
    bc = blockers or ["STUCK_QC_FAILED"]
    print(f"STUCK_QC_FAILED\tqc-failed\t—\t{qc_status}\t{','.join(bc)}")
elif not build_done:
    if max_att and resume_att >= max_att:
        bc = blockers or ["STUCK_PRE_CLOSEOUT"]
        print(f"STUCK_PRE_CLOSEOUT\tpre-closeout\tattempts={resume_att}\t{qc_status}\t{','.join(bc)}")
else:
    if closeout_st in ('blocked-floor-incomplete','blocked-libraries-incomplete',
                       'blocked-interview-incomplete','failed'):
        bc = blockers or [f"closeout:{closeout_st}"]
        print(f"STUCK_CLOSEOUT_BLOCKED\tcloseout-blocked\t—\t{qc_status}\t{','.join(bc)}")
PYEOF
}

# ── Local mode: run against THIS box ─────────────────────────────────────────
if [[ "$LOCAL_MODE" -eq 1 ]]; then
  LOCAL_STATE_FILE="${ZHC_STATE_FILE:-${OC_ROOT}/workspace/.workforce-build-state.json}"
  if [[ ! -f "$LOCAL_STATE_FILE" ]]; then
    echo "[fleet-stuck-clients] no state file at $LOCAL_STATE_FILE"
    exit 0
  fi
  STATE_JSON=$(cat "$LOCAL_STATE_FILE")
  RESULT=$(compute_stuck_class "$STATE_JSON")
  if [[ -n "$RESULT" ]]; then
    IFS=$'\t' read -r SCLASS STAGE IDLE QC BLOCKERS <<< "$RESULT"
    printf "%-18s %-25s %-8s %-10s %s\n" "BOX" "STAGE" "IDLE" "QC" "BLOCKERS"
    printf "%-18s %-25s %-8s %-10s %s\n" "local" "$STAGE" "$IDLE" "$QC" "$BLOCKERS"
    echo ""
    log "WARN" "local box is STUCK: $SCLASS"
    exit 2
  else
    echo "[fleet-stuck-clients] local box: no stuck condition"
    exit 0
  fi
fi

# ── Fleet mode: load box manifest ────────────────────────────────────────────
MANIFEST_FILE="${BOXES_FILE:-${FLEET_BOXES_FILE:-${OC_ROOT}/fleet/boxes.json}}"
if [[ ! -f "$MANIFEST_FILE" ]]; then
  log "ERROR" "box manifest not found: $MANIFEST_FILE (use --boxes-file or set FLEET_BOXES_FILE)"
  exit 1
fi

command -v jq >/dev/null 2>&1 || { log "ERROR" "jq not found"; exit 1; }

log "INFO" "loading manifest: $MANIFEST_FILE"

boxes_total=0
boxes_stuck=0
stuck_report=""
any_stuck=0

# Print header
printf "%-18s %-25s %-8s %-10s %s\n" "BOX" "STAGE" "IDLE" "QC" "BLOCKERS"
printf "%s\n" "$(printf '%.0s-' {1..80})"

# ── Iterate boxes ─────────────────────────────────────────────────────────────
while IFS= read -r box_entry; do
  box_name=$(echo "$box_entry" | jq -r '.name // empty')
  platform=$(echo "$box_entry" | jq -r '.platform // "vps"')
  ssh_target=$(echo "$box_entry" | jq -r '.ssh // empty')
  tunnel=$(echo "$box_entry" | jq -r '.tunnel // empty')

  [[ -z "$box_name" ]] && continue
  [[ -n "$BOX_FILTER" && "$box_name" != "$BOX_FILTER" ]] && continue

  boxes_total=$((boxes_total + 1))

  # ---- build SSH command ----
  SSH_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes)
  if [[ -n "$tunnel" ]]; then
    PROXY_CMD="/opt/homebrew/bin/cloudflared access ssh --hostname ${tunnel}"
    SSH_OPTS+=(-o "ProxyCommand=${PROXY_CMD}")
  fi

  if [[ "$platform" == "mac" ]]; then
    remote_state_path='$HOME/.openclaw/workspace/.workforce-build-state.json'
  else
    remote_state_path='/data/.openclaw/workspace/.workforce-build-state.json'
  fi

  # ---- read remote state ----
  state_json=""
  if [[ -n "$ssh_target" ]]; then
    state_json=$(ssh "${SSH_OPTS[@]}" "$ssh_target" "cat $remote_state_path" 2>/dev/null || true)
  fi

  if [[ -z "$state_json" ]]; then
    log "WARN" "[$box_name] could not read state (SSH failed or no state file)"
    continue
  fi

  RESULT=$(compute_stuck_class "$state_json")
  if [[ -n "$RESULT" ]]; then
    IFS=$'\t' read -r SCLASS STAGE IDLE QC BLOCKERS <<< "$RESULT"
    printf "%-18s %-25s %-8s %-10s %s\n" "$box_name" "$STAGE" "$IDLE" "$QC" "$BLOCKERS"
    boxes_stuck=$((boxes_stuck + 1))
    any_stuck=1
    stuck_report="${stuck_report}  ${box_name}: ${STAGE} [${SCLASS}]\n"
    log "WARN" "[$box_name] STUCK: $SCLASS — $STAGE idle=$IDLE"
  else
    log "INFO" "[$box_name] no stuck condition"
  fi

done < <(jq -c '.boxes[]' "$MANIFEST_FILE" 2>/dev/null || jq -c '.[]' "$MANIFEST_FILE" 2>/dev/null)

echo ""
log "INFO" "fleet-stuck scan complete: $boxes_stuck/$boxes_total boxes stuck"

# ── Operator Telegram summary (--apply mode) ─────────────────────────────────
# CO-MINGLING GUARD (v12.4.0): destination is OPT-IN. NO hardcoded personal chat.
if [[ "$APPLY" -eq 1 && "$any_stuck" -eq 1 ]]; then
  OPERATOR_CHAT="${OPERATOR_ESCALATION_CHAT_ID:-${ZHC_OPERATOR_CHAT_ID:-}}"
  summary_msg="🚨 ZHC Stuck-Client Scan
Boxes scanned:  $boxes_total
Stuck:          $boxes_stuck

$(printf '%b' "$stuck_report")
Run fleet-stuck-clients.sh for full details. These clients are NOT in the closeout sweep — they need operator action."

  if [[ -n "$OPERATOR_CHAT" ]] && command -v openclaw >/dev/null 2>&1; then
    openclaw message send --channel telegram --target "$OPERATOR_CHAT" \
      --message "$summary_msg" >/dev/null 2>&1 || true
    log "INFO" "Telegram operator summary sent (chat=$OPERATOR_CHAT)"
  else
    [[ -z "$OPERATOR_CHAT" ]] && log "INFO" "operator escalation chat not configured (OPERATOR_ESCALATION_CHAT_ID/ZHC_OPERATOR_CHAT_ID unset) — skipping stuck-client summary send"
  fi
fi

if [[ "$any_stuck" -eq 1 ]]; then
  exit 2
fi
exit 0
