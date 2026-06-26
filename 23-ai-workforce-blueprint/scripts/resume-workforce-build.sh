#!/usr/bin/env bash
# resume-workforce-build.sh - autonomous resume layer for Skill 23 builds
#
# Reads /data/.openclaw/workspace/.workforce-build-state.json. If the state
# shows pending or stale-building departments, sends a self-message via
# `openclaw message send` from the operator's chat (owner OR operator) to the
# bot's own chat so the agent gets invoked and continues the build.
#
# This is the ONLY autonomous-recovery layer in the workforce-build pipeline.
# If this script doesn't run on a cron, an interrupted build will sit forever.
#
# Idempotent. Safe to run every N minutes. Holds a 10-minute lockfile so it
# never double-fires while a build is actively running.

set -u

# ---- platform detection (vps default; mac override) ----
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[resume-workforce-build] no OpenClaw root found; aborting" >&2
  exit 0
fi

# v10.15.26 / v10.16.25: resolve this script's own dir so the BELT can run the
# sibling department-floor.py (on-disk HARD floor) before honoring a terminal
# build-state. Prefer BASH_SOURCE; fall back to the canonical install paths.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [[ -z "$SCRIPT_DIR" || ! -f "$SCRIPT_DIR/department-floor.py" ]]; then
  for _cand in \
    "$OC_ROOT/skills/23-ai-workforce-blueprint/scripts" \
    "$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts" \
    "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts"; do
    [[ -f "$_cand/department-floor.py" ]] && SCRIPT_DIR="$_cand" && break
  done
fi

STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
LOCK_FILE="$OC_ROOT/workspace/.workforce-build-state.lock"
LOG_FILE="$OC_ROOT/workspace/.workforce-build-state.log"
RUN_COUNT_FILE="$OC_ROOT/workspace/.workforce-build-resume-runs.count"
MAX_ATTEMPTS_DEFAULT=12
STALE_BUILDING_MINUTES=15

# ---- v14.1.5: DURABLE PARK state + consecutive-STUCK hard cap ----
# THE LOOP FIX. The old v10.15.18 "Rule 8 / NEVER STOP" accounting only SLOWED a
# stuck build to ~every 2h and re-fired it FOREVER (≈96 agent turns/day into the
# gateway's refusal — the token furnace that drained idle boxes). It is replaced
# by a real hard stop:
#   • PARK_DIR / BOX_PARK_MARKER are the SAME durable files the agent-browser
#     circuit-breaker (06-ghl-install-pages/tools/browser_manager.sh) and the
#     cron registrar (scripts/ensure-pipeline-crons.sh) read/write. Durable =
#     survives a reboot (lives in the box's OpenClaw state dir, NOT TMPDIR).
#   • After MAX_STUCK_FIRES CONSECUTIVE fires with ZERO build-state progress, this
#     cron PARKS the build (writes BOX_PARK_MARKER), escalates ONCE, and DISABLES
#     ITSELF (self_remove_cron). A PROGRESSING build never trips it — the counter
#     resets to 0 the instant the state fingerprint changes.
#   • Un-park is OPERATOR-ONLY (scripts/unpark-build.sh). Auto-resume never
#     happens silently.
PARK_DIR="$OC_ROOT/workspace/.park"
BOX_PARK_MARKER="$PARK_DIR/workforce-build.parked"
STUCK_COUNT_FILE="$OC_ROOT/workspace/.workforce-build-resume-stuck.count"
PROGRESS_FP_FILE="$OC_ROOT/workspace/.workforce-build-resume-progress.fp"
# Default 24 consecutive no-progress fires = 6h of literally-zero state change =
# unambiguously stuck. Override with WORKFORCE_RESUME_MAX_STUCK_FIRES (floor 2).
MAX_STUCK_FIRES="${WORKFORCE_RESUME_MAX_STUCK_FIRES:-24}"
case "$MAX_STUCK_FIRES" in ""|*[!0-9]*) MAX_STUCK_FIRES=24 ;; esac
[ "$MAX_STUCK_FIRES" -lt 2 ] 2>/dev/null && MAX_STUCK_FIRES=2

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG_FILE"
}

# Remote Rescue v1 - resolve the operator ESCALATION Telegram chat ID.
# CO-MINGLING GUARD (v12.4.0): destination is OPT-IN. NO hardcoded personal chat.
# Lookup: env.vars.OPERATOR_ESCALATION_CHAT_ID -> env.vars.OPERATOR_TELEGRAM_CHAT_ID
# -> $OPERATOR_ESCALATION_CHAT_ID -> $OPERATOR_TELEGRAM_CHAT_ID -> "" (no-op).
# Empty result = escalation destination not configured; callers MUST skip the send.
resolve_operator_chat_id() {
  local v=""
  if command -v openclaw >/dev/null 2>&1; then
    v="$(openclaw config get env.vars.OPERATOR_ESCALATION_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
    case "$v" in ""|*"not found"*|*"Error"*) v="" ;; esac
    if [[ -z "$v" ]]; then
      v="$(openclaw config get env.vars.OPERATOR_TELEGRAM_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
      case "$v" in ""|*"not found"*|*"Error"*) v="" ;; esac
    fi
  fi
  [[ -z "$v" && -n "${OPERATOR_ESCALATION_CHAT_ID:-}" ]] && v="$OPERATOR_ESCALATION_CHAT_ID"
  [[ -z "$v" && -n "${OPERATOR_TELEGRAM_CHAT_ID:-}" ]] && v="$OPERATOR_TELEGRAM_CHAT_ID"
  # No baked-in personal chat. Empty = no operator escalation configured.
  printf '%s' "$v"
}

# v10.14.36 - locate this cron's UUID by name so we can self-remove.
# OpenClaw doesn't pass a CRON_UUID env var, so we resolve by --name.
# Returns empty string if openclaw CLI is unavailable or the cron isn't listed.
find_self_cron_uuid() {
  command -v openclaw >/dev/null 2>&1 || { echo ""; return 0; }
  openclaw cron list 2>/dev/null \
    | awk '/workforce-build-resume/ { for (i=1;i<=NF;i++) if ($i ~ /^[0-9a-fA-F-]{8,}$/) { print $i; exit } }' \
    | head -1
}

# v10.14.36 - self-remove the workforce-build-resume cron. Tolerates missing
# UUID/CLI; logs whatever it can. Never errors out the script.
self_remove_cron() {
  local reason="$1"
  local uuid
  uuid=$(find_self_cron_uuid)
  if [[ -z "$uuid" ]]; then
    log "self_remove_cron($reason): could not resolve workforce-build-resume UUID - leaving cron in place"
    return 0
  fi
  log "self_remove_cron($reason): removing cron $uuid"
  if openclaw cron rm "$uuid" 2>>"$LOG_FILE"; then
    log "self_remove_cron($reason): removed $uuid"
    # Reset the run/stuck counters so a future (operator-un-parked) build starts
    # fresh. NEVER delete BOX_PARK_MARKER here — a park must persist until an
    # operator runs scripts/unpark-build.sh (auto-resume never happens silently).
    rm -f "$RUN_COUNT_FILE" "$STUCK_COUNT_FILE" "$PROGRESS_FP_FILE" 2>/dev/null || true
  else
    log "self_remove_cron($reason): openclaw cron rm $uuid FAILED - see errors above"
  fi
}

# ---- v10.14.36: BELT - explicit self-stop on terminal state ----
# v10.15.26 / v10.16.25 HARD FLOOR: a terminal state in the build-state JSON
# (status=done / closeoutStatus=done|sent) is NO LONGER trusted as proof on its
# own. A hand-seeded build-state (a 3-dept seeded fiction) used to flip the
# JSON to done and the cron would self-remove, leaving a HEAVILY-REDUCED
# workforce as the final result with the never-stop machinery quit. We now run
# department-floor.py against the REAL folders on disk: if the floor is NOT met
# (rc=3), we REFUSE to honor the terminal state, keep the cron alive, and drive
# the build to instantiate the missing mandatory/vertical departments. Only a
# terminal JSON state that ALSO passes the on-disk floor (or genuinely has no
# workforce / explicit declines) is allowed to self-remove the cron.
if [[ -f "$STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
  _build_status=$(jq -r '.status // ""' "$STATE_FILE" 2>/dev/null || echo "")
  _closeout_status=$(jq -r '.closeoutStatus // ""' "$STATE_FILE" 2>/dev/null || echo "")
  _build_completed_at=$(jq -r '.buildCompletedAt // ""' "$STATE_FILE" 2>/dev/null || echo "")
  case "$_build_status" in
    done|complete)
      _terminal=1 ;;
    failed)
      _terminal=1 ;;
    *)
      _terminal=0 ;;
  esac
  if (( _terminal == 0 )) && [[ -n "$_build_completed_at" ]]; then
    case "$_closeout_status" in
      done|sent) _terminal=1 ;;
    esac
  fi
  if (( _terminal == 1 )); then
    # HARD FLOOR guard: a 'done'/'complete'/'sent' terminal state must ALSO pass
    # the on-disk department floor before we self-remove. 'failed' is allowed to
    # self-remove regardless (it is an explicit non-completion the operator set).
    _allow_remove=1
    _floor_script="$SCRIPT_DIR/department-floor.py"
    if [[ "$_build_status" != "failed" ]] && [[ -f "$_floor_script" ]] && command -v python3 >/dev/null 2>&1; then
      python3 "$_floor_script" >/dev/null 2>&1
      _floor_rc=$?
      if [[ "$_floor_rc" == "3" ]]; then
        _allow_remove=0
        log "BELT: terminal JSON state (build_status=$_build_status, closeout=$_closeout_status) but DEPARTMENT FLOOR NOT MET on disk (department-floor.py rc=3). REFUSING to self-remove - a seeded/reduced build-state will not end the build. Driving the floor instead."
      fi
    fi
    if (( _allow_remove == 1 )); then
      log "BELT: terminal state detected + floor satisfied (build_status=$_build_status, closeout=$_closeout_status, completed=$_build_completed_at) - removing self-cron and exiting"
      self_remove_cron "terminal-state"
      exit 0
    fi
  fi
fi

# ---- v14.1.5: DURABLE PARK gate + consecutive-STUCK hard cap (THE LOOP FIX) ----
# Replaces the old v10.15.18 "Rule 8 / NEVER STOP" run-accounting, which only
# SLOWED a stuck build to ~every 2h and re-fired it FOREVER (the token furnace).
mkdir -p "$PARK_DIR" 2>/dev/null || true

park_is_set() { [[ -f "$BOX_PARK_MARKER" ]]; }

park_set() {
  # $1 = reason. Durable, human-readable park marker. Operator-cleared ONLY.
  mkdir -p "$PARK_DIR" 2>/dev/null || true
  printf 'PARKED %s host=%s reason=%s\nUn-park (operator only): run scripts/unpark-build.sh on this box.\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(hostname 2>/dev/null || echo box)" "$1" \
    > "$BOX_PARK_MARKER" 2>/dev/null || true
}

# Compact fingerprint of build PROGRESS. Deliberately EXCLUDES volatile fields
# (resumeAttempts, timestamps) that change every fire and would mask a stuck
# build. If it changes between fires, the build advanced and the stuck counter
# resets to 0; a progressing build therefore never trips the cap.
progress_fingerprint() {
  if command -v jq >/dev/null 2>&1 && [[ -f "$STATE_FILE" ]]; then
    jq -rS '[
      ((.departments // []) | map(((.id // .slug // "?")|tostring) + ":" + ((.status // "?")|tostring)) | sort | join(",")),
      (.roleLibraryStatus // "?"),
      (.sopLibraryStatus // "?"),
      (.commsAutomationStatus // "?"),
      (.closeoutStatus // "?"),
      (.buildCompletedAt // "?")
    ] | join("||")' "$STATE_FILE" 2>/dev/null || echo "jqerr"
  elif [[ -f "$STATE_FILE" ]]; then
    printf '%s|%s' "$(wc -c < "$STATE_FILE" 2>/dev/null | tr -d '[:space:]')" \
      "$(stat -c %Y "$STATE_FILE" 2>/dev/null || stat -f %m "$STATE_FILE" 2>/dev/null || echo 0)"
  else
    echo "nostate"
  fi
}

# (1) ALREADY PARKED → STOP unconditionally. The agent-browser breaker or a prior
#     stuck-cap wrote BOX_PARK_MARKER and no operator has un-parked. Do NOT resume;
#     remove the cron so future fires stop too. Un-park is operator-only.
if park_is_set; then
  log "PARKED: $BOX_PARK_MARKER present — build is intentionally parked. NOT resuming; removing the resume cron. Un-park is operator-only (scripts/unpark-build.sh)."
  echo "PARKED — build is parked ($BOX_PARK_MARKER). STOP: do NOT continue this resume; an operator must run scripts/unpark-build.sh. The resume cron is being removed."
  self_remove_cron "parked"
  exit 0
fi

# (2) CONSECUTIVE-STUCK hard cap — ONLY for an ACTIVE build (interview done AND
#     departments seeded). Pre-interview / pre-seed phases own their own nudge +
#     watchdog crons and must never be parked here.
_ic="false"; _ndept="0"
if command -v jq >/dev/null 2>&1 && [[ -f "$STATE_FILE" ]]; then
  _ic=$(jq -r '.interviewComplete // false' "$STATE_FILE" 2>/dev/null || echo false)
  _ndept=$(jq -r '(.departments // []) | length' "$STATE_FILE" 2>/dev/null || echo 0)
fi
if [[ "$_ic" == "true" ]] && [[ "${_ndept:-0}" =~ ^[0-9]+$ ]] && (( _ndept > 0 )); then
  _cur_fp="$(progress_fingerprint)"
  _prev_fp=""
  [[ -f "$PROGRESS_FP_FILE" ]] && _prev_fp="$(cat "$PROGRESS_FP_FILE" 2>/dev/null || echo '')"
  if [[ -n "$_prev_fp" && "$_cur_fp" == "$_prev_fp" ]]; then
    _stuck=0
    [[ -f "$STUCK_COUNT_FILE" ]] && _stuck=$(cat "$STUCK_COUNT_FILE" 2>/dev/null | tr -dc '0-9' | head -c 6)
    [[ -z "$_stuck" ]] && _stuck=0
    _stuck=$((_stuck + 1))
  else
    _stuck=0
  fi
  echo "$_stuck" > "$STUCK_COUNT_FILE" 2>/dev/null || true
  printf '%s' "$_cur_fp" > "$PROGRESS_FP_FILE" 2>/dev/null || true

  if (( _stuck >= MAX_STUCK_FIRES )); then
    log "STUCK-CAP: $_stuck consecutive cron fires with ZERO build-state progress (cap=$MAX_STUCK_FIRES). PARKING the build (durable) + escalating once, then DISABLING this cron (self-remove). Hard stop for a wedged build (replaces the old forever-firing furnace). Un-park is operator-only (scripts/unpark-build.sh)."
    park_set "stuck:${_stuck}-consecutive-fires-zero-progress"
    if command -v openclaw >/dev/null 2>&1; then
      _already_esc=$(jq -r '.stuckParkEscalated // false' "$STATE_FILE" 2>/dev/null || echo false)
      if [[ "$_already_esc" != "true" ]]; then
        _rr_webhook="${RESCUE_RANGERS_WEBHOOK_URL:-https://main.blackceoautomations.com/webhook/rescue-rangers}"
        if [[ -n "$_rr_webhook" ]] && command -v curl >/dev/null 2>&1; then
          _rr_msg="workforce-build-resume on $(hostname) made ZERO progress for ${_stuck} consecutive fires. Build PARKED + cron DISABLED (v14.1.5 hard stuck-cap). Investigate on the box, then un-park with scripts/unpark-build.sh. State: $STATE_FILE. OpenClaw: $(openclaw --version 2>/dev/null | head -1)"
          _rr_payload=$(jq -nc --arg c "$(hostname)" --arg a "main" --arg m "$_rr_msg" '{action:"escalate",client:$c,agent:$a,message:$m}' 2>/dev/null || echo '')
          [[ -n "$_rr_payload" ]] && curl -s -X POST "$_rr_webhook" -H "Content-Type: application/json" ${RESCUE_RANGERS_WEBHOOK_SECRET:+-H X-Rescue-Secret:${RESCUE_RANGERS_WEBHOOK_SECRET}} -d "$_rr_payload" >>"$LOG_FILE" 2>&1 || true
        fi
        _operator_chat="$(resolve_operator_chat_id)"
        if [[ -n "$_operator_chat" ]]; then
          openclaw message send --channel telegram -t "$_operator_chat" \
            -m "⛔ workforce-build-resume on $(hostname) PARKED + DISABLED after ${_stuck} consecutive no-progress fires (v14.1.5 hard stuck-cap). It will NOT re-fire until you un-park: scripts/unpark-build.sh. State: $STATE_FILE" >>"$LOG_FILE" 2>&1 || true
        fi
        _tmp_se=$(mktemp); jq '.stuckParkEscalated = true' "$STATE_FILE" > "$_tmp_se" 2>/dev/null && mv "$_tmp_se" "$STATE_FILE" || rm -f "$_tmp_se"
      fi
    fi
    echo "PARKED + DISABLED — ${_stuck} consecutive no-progress fires hit the hard cap ($MAX_STUCK_FIRES). The resume cron is removed; un-park is operator-only (scripts/unpark-build.sh). STOP."
    self_remove_cron "stuck-cap"
    exit 0
  fi
  if (( _stuck == 0 )); then
    log "stuck-watch: progress fingerprint CHANGED — build advanced; stuck counter reset to 0/$MAX_STUCK_FIRES."
  else
    log "stuck-watch: NO progress since last fire — stuck counter $_stuck/$MAX_STUCK_FIRES (parks + disables cron at the cap)."
  fi
else
  # No active build to be stuck on (pre-interview / pre-seed). Keep the counters
  # clean so a later real build starts fresh; never park this phase.
  rm -f "$STUCK_COUNT_FILE" "$PROGRESS_FP_FILE" 2>/dev/null || true
fi

# ---- v10.14.20: heal config before any gateway interaction ----
if command -v openclaw >/dev/null 2>&1; then
  openclaw doctor --fix >/dev/null 2>&1 || true
fi

# ---- preconditions ----
if [[ ! -f "$STATE_FILE" ]]; then
  log "no state file at $STATE_FILE - nothing to resume; exiting clean"
  exit 0
fi

if ! command -v jq >/dev/null 2>&1; then
  log "jq not installed - cannot parse state; exiting"
  exit 0
fi

if ! command -v openclaw >/dev/null 2>&1; then
  log "openclaw CLI not on PATH - cannot dispatch resume; exiting"
  exit 0
fi

# ---- lock (prevent concurrent self-pings) ----
if [[ -f "$LOCK_FILE" ]]; then
  lock_mtime=$(stat -c %Y "$LOCK_FILE" 2>/dev/null || stat -f %m "$LOCK_FILE" 2>/dev/null || echo 0)
  now=$(date +%s)
  lock_age=$(( now - lock_mtime ))
  if (( lock_age < 600 )); then
    log "lock held for ${lock_age}s (< 600s) - another resume in flight; exiting"
    exit 0
  fi
  log "stale lock (age ${lock_age}s) - clearing"
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# ---- read state ----
interview_complete=$(jq -r '.interviewComplete // false' "$STATE_FILE")
if [[ "$interview_complete" != "true" ]]; then
  # PRD-3.3 R3.2 (auto-closeout): RECOVER a finished-but-unflagged interview.
  # Prior behavior: this hard-exited the moment interviewComplete != true, which
  # made the ONLY recovery cron blind to an interview the owner genuinely finished
  # but whose interviewComplete flag the agent never wrote (HOP-1 miss, diag/03).
  # From that point the build never started and the owner got silence + a wrong
  # "finish your interview" nudge. Now: if the interview CONTENT looks complete
  # (a real lastQuestionAt exists, i.e. the interview was conducted) but the flag
  # is missing, run the QC gate against the transcript. The QC gate - not this
  # cron, and not the agent's memory - is the authority on "is the interview
  # actually complete." If QC returns pass, the content IS complete: set the flag
  # via the canonical writer (update-interview-state.sh --complete, which is
  # idempotent and also seeds the build + kicks it) and fall through to drive the
  # build. If QC is fail/needs-review/pending-after-run, do NOT force the flag -
  # leave it for the QC-resume / watchdog lanes (a half-interview must not be
  # promoted to a build). This NEVER fabricates answers; it only flips a flag the
  # owner's completed content already earned.
  last_q_at_unflagged=$(jq -r '.interviewProgress.lastQuestionAt // empty' "$STATE_FILE" 2>/dev/null || true)
  if [[ -z "$last_q_at_unflagged" || "$last_q_at_unflagged" == "null" ]]; then
    log "interview not yet complete and no lastQuestionAt - interview not started; nothing to recover"
    exit 0
  fi
  log "RECOVERY: interviewComplete!=true but interview content exists (lastQuestionAt=$last_q_at_unflagged) - running QC to decide if the owner actually finished (HOP-1 recovery)."
  _recover_qc_status="pending"
  QC_SCRIPT_RECOVER="${SCRIPT_DIR}/qc-interview-completion.py"
  if [[ -f "$QC_SCRIPT_RECOVER" ]] && command -v python3 >/dev/null 2>&1; then
    # --write-state is a flag; the state path goes via --state (the old
    # positional form was rejected by argparse and silently no-op'd QC).
    python3 "$QC_SCRIPT_RECOVER" --write-state --state "$STATE_FILE" >>"$LOG_FILE" 2>&1 || true
    _recover_qc_status=$(jq -r '.interviewQc.status // "pending"' "$STATE_FILE" 2>/dev/null || echo "pending")
    log "RECOVERY: QC verdict on unflagged interview = $_recover_qc_status"
  else
    log "RECOVERY: qc-interview-completion.py not found at $QC_SCRIPT_RECOVER - cannot verify completeness; leaving unflagged for the watchdog."
  fi
  if [[ "$_recover_qc_status" == "pass" ]]; then
    # Content verified complete. Promote via the canonical idempotent writer so the
    # same flag + gate-seeding + build-kick path runs as a normal --complete.
    COMPLETE_WRITER="${SCRIPT_DIR}/update-interview-state.sh"
    if [[ -f "$COMPLETE_WRITER" ]]; then
      log "RECOVERY: QC=pass - promoting interview to complete via update-interview-state.sh --complete (idempotent; seeds build + kicks it)."
      bash "$COMPLETE_WRITER" --complete >>"$LOG_FILE" 2>&1 || log "RECOVERY: update-interview-state.sh --complete returned non-zero (non-fatal; setting flag inline as fallback)."
    fi
    interview_complete=$(jq -r '.interviewComplete // false' "$STATE_FILE")
    if [[ "$interview_complete" != "true" ]]; then
      # Fallback: writer missing or failed - set the flag inline so we proceed.
      _now_rec=$(date -u +%Y-%m-%dT%H:%M:%SZ)
      _tmp_rec=$(mktemp)
      jq --arg now "$_now_rec" '.interviewComplete = true | .interviewCompletedAt = (.interviewCompletedAt // $now) | (if .departments == null then .departments = [] else . end) | (if .roleLibraryStatus == null then .roleLibraryStatus = "pending" else . end) | (if .sopLibraryStatus == null then .sopLibraryStatus = "pending" else . end)' "$STATE_FILE" > "$_tmp_rec" 2>/dev/null \
        && mv "$_tmp_rec" "$STATE_FILE" || rm -f "$_tmp_rec"
      interview_complete=$(jq -r '.interviewComplete // false' "$STATE_FILE")
      log "RECOVERY: set interviewComplete=true inline (fallback)."
    fi
    log "RECOVERY: interview promoted to complete - continuing into the normal resume/build path."
    # fall through - do NOT exit; the rest of this script now drives the build.
  else
    log "RECOVERY: QC=$_recover_qc_status (not pass) - NOT promoting. The owner-facing nudge / QC-resume / watchdog lanes own an unfinished or unverifiable interview. Exiting (nothing to resume yet)."
    exit 0
  fi
fi

# ---- PRD-2.15 (v12.3.12): QC-aware resume gate ----
# interviewComplete=true is necessary but not sufficient. The interviewQc gate
# must also be pass before build/closeout can proceed. If QC is pending (not yet
# run), try to run it inline. If it is fail|needs-review, fire a [QC-RESUME]
# self-ping and let the watchdog raise STUCK_QC_FAILED if it persists.
qc_status=$(jq -r '.interviewQc.status // "pending"' "$STATE_FILE" 2>/dev/null || echo "pending")
if [[ "$qc_status" != "pass" ]]; then
  QC_SCRIPT="${SCRIPT_DIR}/qc-interview-completion.py"
  if [[ "$qc_status" == "pending" ]] && [[ -f "$QC_SCRIPT" ]]; then
    log "[QC-RESUME] interviewQc.status=pending - running qc-interview-completion.py --write-state --state (best-effort)"
    # --write-state is a flag; the state path goes via --state (the old positional
    # form was rejected by argparse and silently no-op'd QC, stranding the gate).
    python3 "$QC_SCRIPT" --write-state --state "$STATE_FILE" >>"$LOG_FILE" 2>&1 || true
    qc_status=$(jq -r '.interviewQc.status // "pending"' "$STATE_FILE" 2>/dev/null || echo "pending")
    log "[QC-RESUME] interviewQc.status after QC run: $qc_status"
  fi
  if [[ "$qc_status" != "pass" ]]; then
    log "[QC-RESUME] interviewQc.status=$qc_status - cannot resume build until QC passes. Firing self-ping for agent to review QC."
    if command -v openclaw >/dev/null 2>&1; then
      _owner_chat=$(jq -r '.ownerChat // empty' "$STATE_FILE" 2>/dev/null || true)
      # Self-ping is INTERNAL (to agent, not owner). Use operator escalation path if available.
      _operator_chat=$(resolve_operator_chat_id 2>/dev/null || true)
      if [[ -n "$_operator_chat" ]]; then
        openclaw message send --channel telegram -t "$_operator_chat" \
          -m "⚠️ [QC-RESUME] interviewQc.status=${qc_status} on $(hostname) - build resume blocked until QC gate passes. State: $STATE_FILE" \
          >>"$LOG_FILE" 2>&1 || true
      fi
    fi
    exit 0
  fi
fi

# ---- v12.11.0 (fix/gate-and-resume-correctness): DISK-REALITY STALE-STATE RESET ----
# A department with status=done OR roleLibraryFilled=true OR sopLibraryFilled=true in
# the build-state JSON that has NO real how-to.md on disk (or only an empty/placeholder
# file) represents a FALSE terminal state — likely from a hand-seeded or corrupted
# build-state. Trusting it causes the resume to exit "nothing to do" and the real build
# never runs. This block scans every department claiming 'done' or library-filled and
# verifies on-disk reality before allowing those claims to stand.
#
# VERIFY contract: a department's how-to.md under departments/<id>/*/how-to.md must
#   exist AND be non-empty. If a dept's roles are completely absent or all stubs, the
#   state is STALE: reset status to "pending" and clear the library-filled flags so the
#   normal resume path picks it up and builds it for real.
#
# This check runs BEFORE pending_count so the corrected state is what drives
# everything below. It never promotes a pending→done; it only demotes false dones.
_WORKSPACE_ROOT_RESUME=$(jq -r '.workspaceRoot // empty' "$STATE_FILE" 2>/dev/null || true)
if [[ -z "$_WORKSPACE_ROOT_RESUME" || "$_WORKSPACE_ROOT_RESUME" == "null" ]]; then
  _WORKSPACE_ROOT_RESUME="$(dirname "$STATE_FILE")"
fi
_DEPTS_DIR_RESUME="$_WORKSPACE_ROOT_RESUME/departments"
_stale_reset_count=0

if command -v python3 >/dev/null 2>&1; then
  _stale_reset_output=$(python3 - "$STATE_FILE" "$_DEPTS_DIR_RESUME" <<'STALE_PY' 2>&1
import json, os, sys
from pathlib import Path

state_path = Path(sys.argv[1])
depts_dir  = Path(sys.argv[2])
HOW_TO_MIN = 256  # bytes — anything smaller is effectively empty/stub

try:
    state = json.loads(state_path.read_text(encoding="utf-8"))
except Exception as e:
    print(f"STALE_CHECK_ERROR: cannot read state: {e}", file=sys.stderr)
    sys.exit(0)

departments = state.get("departments", [])
if not isinstance(departments, list):
    sys.exit(0)

reset_ids = []
for dept in departments:
    dept_id = dept.get("id") or dept.get("slug", "")
    if not dept_id:
        continue
    status = dept.get("status", "")
    role_lib = dept.get("roleLibraryFilled", False)
    sop_lib  = dept.get("sopLibraryFilled", False)

    # Only audit departments that claim done or library-filled
    claims_done = (status == "done") or role_lib or sop_lib
    if not claims_done:
        continue

    # Check for at least one real how-to.md under departments/<id>/
    dept_dir = depts_dir / dept_id
    has_real_howto = False
    if dept_dir.is_dir():
        for role_dir in dept_dir.iterdir():
            if not role_dir.is_dir() or role_dir.name.startswith("."):
                continue
            how_to = role_dir / "how-to.md"
            if how_to.exists() and how_to.stat().st_size >= HOW_TO_MIN:
                content = how_to.read_text(encoding="utf-8", errors="replace")
                if "[PENDING" not in content:
                    has_real_howto = True
                    break

    if not has_real_howto:
        reset_ids.append(dept_id)

if not reset_ids:
    print("STALE_CHECK_CLEAN")
    sys.exit(0)

# Reset stale departments: status->pending, clear library-filled flags
changed = False
for dept in departments:
    dept_id = dept.get("id") or dept.get("slug", "")
    if dept_id in reset_ids:
        print(f"STALE_RESET: dept '{dept_id}' claims done/library-filled but has NO real how-to.md on disk — resetting to pending")
        dept["status"] = "pending"
        dept["roleLibraryFilled"] = False
        dept["sopLibraryFilled"] = False
        dept.pop("completedAt", None)
        changed = True

if changed:
    # Also unset top-level terminal signals if any dept was reset
    state.pop("buildCompletedAt", None)
    if state.get("closeoutStatus") not in ("done", "sent", "failed"):
        state.pop("closeoutStatus", None)
    state["roleLibraryStatus"] = "pending"
    state["sopLibraryStatus"]  = "pending"

    import tempfile
    tmp = state_path.with_suffix(f".stale_reset.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(state_path)
        print(f"STALE_RESET_WRITTEN: {len(reset_ids)} dept(s) reset to pending")
    except Exception as e:
        tmp.unlink(missing_ok=True)
        print(f"STALE_RESET_ERROR: could not write state: {e}", file=sys.stderr)
STALE_PY
  )
  # Log and count the stale resets
  while IFS= read -r _stale_line; do
    case "$_stale_line" in
      STALE_CHECK_CLEAN)
        log "STALE-CHECK: all 'done' departments verified against disk — state is clean" ;;
      STALE_RESET:*)
        log "STALE-CHECK [WARN]: $_stale_line"
        _stale_reset_count=$(( _stale_reset_count + 1 )) ;;
      STALE_RESET_WRITTEN:*)
        log "STALE-CHECK [ACTION]: $_stale_line - these departments will now be built for real" ;;
      STALE_RESET_ERROR:*)
        log "STALE-CHECK [ERROR]: $_stale_line" ;;
    esac
  done <<< "$_stale_reset_output"
  if (( _stale_reset_count > 0 )); then
    log "STALE-CHECK: reset $_stale_reset_count stale 'done' department(s) to pending — build will resume"
  fi
fi

pending_count=$(jq -r '[.departments[] | select(.status == "pending" or .status == "failed")] | length' "$STATE_FILE")
stale_building_count=$(jq --arg min "$STALE_BUILDING_MINUTES" -r '
  [.departments[]
    | select(.status == "building")
    | select(.lastAttemptAt != null)
    | select(((now - (.lastAttemptAt | fromdateiso8601)) / 60) > ($min | tonumber))
  ] | length
' "$STATE_FILE" 2>/dev/null || echo 0)

build_completed_at=$(jq -r '.buildCompletedAt // empty' "$STATE_FILE")
closeout_status=$(jq -r '.closeoutStatus // empty' "$STATE_FILE")
closeout_dirty=0
if [[ -n "$build_completed_at" ]]; then
  case "$closeout_status" in
    done|sent) closeout_dirty=0 ;;
    *) closeout_dirty=1 ;;
  esac
fi

# ---- v10.15.8: ROLE LIBRARY + SOP LIBRARY enforcement gate ----
# A workforce with ALL departments built but the role library NOT pulled into
# how-to.md (roleLibraryStatus != done) OR the SOP library NOT authored
# (sopLibraryStatus != done) is INCOMPLETE. Fire a [LIBRARY-RESUME] self-ping so
# the agent runs verify-library-gate.sh + re-pulls. Only relevant once all depts
# are done (no pending/stale) and BEFORE closeout owns the rest - the gate runs
# before the closeout gate. Last-night incident (multiple clients).
role_library_status=$(jq -r '.roleLibraryStatus // empty' "$STATE_FILE")
sop_library_status=$(jq -r '.sopLibraryStatus // empty' "$STATE_FILE")
done_count_now=$(jq -r '[.departments[] | select(.status == "done")] | length' "$STATE_FILE")
total_count_now=$(jq -r '.departments | length' "$STATE_FILE")
library_dirty=0
if (( pending_count == 0 )) && (( stale_building_count == 0 )) \
   && (( total_count_now > 0 )) && (( done_count_now == total_count_now )); then
  case "$role_library_status" in done) : ;; *) library_dirty=1 ;; esac
  case "$sop_library_status"  in done) : ;; *) library_dirty=1 ;; esac
fi

# ---- v10.15.9: ENFORCED cross-skill chain to Skill 38 (comms automations) ----
# When the built workforce includes a Communications, Sales, or Customer-Support
# department, the closeout MUST hand off to Skill 38 to scaffold the matching
# comms automations. Enforced the SAME way as the library gate: a state field
# (commsAutomationStatus) + this verify/resume dirty check, NOT prose. Dirty when
# all departments are done AND libraries are clean but commsAutomationStatus is
# neither 'done' nor 'not-applicable'. Fires AFTER libraries are clean (comms
# automations sit on top of a complete workforce) and may run alongside closeout.
comms_automation_status=$(jq -r '.commsAutomationStatus // "pending"' "$STATE_FILE")
comms_automation_dirty=0
if (( pending_count == 0 )) && (( stale_building_count == 0 )) && (( library_dirty == 0 )) \
   && (( total_count_now > 0 )) && (( done_count_now == total_count_now )); then
  case "$comms_automation_status" in
    done|not-applicable) comms_automation_dirty=0 ;;
    *) comms_automation_dirty=1 ;;
  esac
fi

# ---- PRD-3.3 R3.3 (auto-closeout): SCRIPT writes buildCompletedAt + closeoutStatus=pending ----
# This was HOP-4, the missing link (diag/03): NO script wrote buildCompletedAt -
# it was an agent hand-write, so if the agent's session ended after the last
# department finished, the build sat "done on disk" but never crossed into the
# closeout, and the owner got nothing. Now the cron itself writes it the moment
# the FULL completion contract is satisfied on the state:
#   - every department done (pending_count==0, stale_building_count==0, all done)
#   - roleLibraryStatus==done AND sopLibraryStatus==done (library_dirty==0)
#   - commsAutomationStatus terminal (done|not-applicable, comms_automation_dirty==0)
# Only then do we stamp buildCompletedAt + set closeoutStatus=pending (if not
# already terminal). This is the deterministic HOP-4 the chain was missing; it
# fires BEFORE the closeout_dirty recompute below so the SAME cron fire dispatches
# the [CLOSEOUT-RESUME] self-ping. The agent inline-write path still works and is
# idempotent (we only write when buildCompletedAt is empty), so this never
# double-writes or races an agent that got there first.
if (( pending_count == 0 )) && (( stale_building_count == 0 )) \
   && (( library_dirty == 0 )) && (( comms_automation_dirty == 0 )) \
   && (( total_count_now > 0 )) && (( done_count_now == total_count_now )) \
   && [[ -z "$build_completed_at" ]]; then
  log "AUTO-COMPLETE (HOP-4): all ${total_count_now} departments done + libraries done (role=$role_library_status sop=$sop_library_status) + comms-automations terminal ($comms_automation_status) but buildCompletedAt was unset - writing buildCompletedAt + closeoutStatus=pending so the closeout fires automatically (no agent hand-write required)."
  _now_bc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  _tmp_bc=$(mktemp)
  # Set buildCompletedAt; only set closeoutStatus=pending if it is not already a
  # later/terminal state (do not clobber generating/sent/done/partial/blocked-*).
  if jq --arg now "$_now_bc" '
        .buildCompletedAt = $now
        | (if ((.closeoutStatus // "") | IN("generating","partial","sent","done","failed","blocked-floor-incomplete","blocked-libraries-incomplete","blocked-interview-incomplete")) then . else .closeoutStatus = "pending" end)
      ' "$STATE_FILE" > "$_tmp_bc" 2>/dev/null; then
    mv "$_tmp_bc" "$STATE_FILE"
    # Refresh local copies so the dirty recompute below sees the new values.
    build_completed_at=$(jq -r '.buildCompletedAt // empty' "$STATE_FILE")
    closeout_status=$(jq -r '.closeoutStatus // empty' "$STATE_FILE")
    log "AUTO-COMPLETE (HOP-4): wrote buildCompletedAt=$build_completed_at, closeoutStatus=$closeout_status."
  else
    rm -f "$_tmp_bc"
    log "AUTO-COMPLETE (HOP-4): WARN - failed to write buildCompletedAt (non-fatal; will retry next fire)."
  fi
fi

# Recompute closeout_dirty now that HOP-4 may have just set buildCompletedAt, so
# this same fire can dispatch the [CLOSEOUT-RESUME] self-ping below.
closeout_dirty=0
if [[ -n "$build_completed_at" ]]; then
  case "$closeout_status" in
    done|sent) closeout_dirty=0 ;;
    *) closeout_dirty=1 ;;
  esac
fi

# B4: Ensure wiring_dirty is defined (set to 0 if not already computed above)
wiring_dirty=${wiring_dirty:-0}
total_attention=$(( pending_count + stale_building_count + library_dirty + wiring_dirty + comms_automation_dirty + closeout_dirty ))
if (( total_attention == 0 )); then
  done_count=$(jq -r '[.departments[] | select(.status == "done")] | length' "$STATE_FILE")
  total_count=$(jq -r '.departments | length' "$STATE_FILE")
  if (( done_count == total_count )) && (( total_count > 0 )); then
    log "ALL ${total_count} departments done + libraries done (role=$role_library_status sop=$sop_library_status) + comms-automations terminal (status=$comms_automation_status) + closeout terminal (status=$closeout_status) - nothing to do"
  else
    log "no pending/stale departments, comms-automations clean (status=$comms_automation_status), closeout clean (pending=$pending_count, stale=$stale_building_count, closeout=$closeout_status) - nothing to do"
  fi
  exit 0
fi

# ---- attempt cap (v10.15.18: escalate-and-CONTINUE, never hard-stop) ----
# PRIOR BEHAVIOR: at maxResumeAttempts the cron bailed and stopped self-pinging
# (exit 0, never to retry) - a half-built workforce then sat forever and the
# client never found out. Rule 8: NEVER STOP. We now escalate to the operator +
# Rescue Rangers ONCE at the cap, then KEEP RETRYING in slow-backoff. The cron
# only stops on a REAL terminal state (handled by the BELT check above).
attempts=$(jq -r '.resumeAttempts // 0' "$STATE_FILE")
max_attempts=$(jq -r ".maxResumeAttempts // $MAX_ATTEMPTS_DEFAULT" "$STATE_FILE")
if (( attempts >= max_attempts )); then
  _cap_already=$(jq -r '.resumeCapEscalated // false' "$STATE_FILE")
  if [[ "$_cap_already" != "true" ]]; then
    log "resumeAttempts ($attempts) >= maxResumeAttempts ($max_attempts) - escalating (operator + Rescue Rangers) and switching to slow-retry. NOT stopping (Rule 8)."
    _operator_chat="$(resolve_operator_chat_id)"
    _lib_note=""
    if (( library_dirty == 1 )); then
      _lib_note=" LIBRARIES NOT done (roleLibraryStatus=${role_library_status}, sopLibraryStatus=${sop_library_status}) - the role-library pull / SOP authoring keeps failing; run scripts/verify-library-gate.sh on $(hostname)."
    fi
    if [[ -n "$_operator_chat" ]]; then
      openclaw message send --channel telegram -t "$_operator_chat" \
        -m "⚠️ Workforce build slow: ${pending_count} pending, ${stale_building_count} stale after ${attempts} resume attempts.${_lib_note} Now in slow-retry (it does NOT stop). State: $STATE_FILE" 2>>"$LOG_FILE" || true
    fi
    # Escalate via the n8n Rescue Rangers webhook (NOT bot-to-bot Telegram).
    _rr_webhook="${RESCUE_RANGERS_WEBHOOK_URL:-https://main.blackceoautomations.com/webhook/rescue-rangers}"
    if [[ -n "$_rr_webhook" ]] && command -v curl >/dev/null 2>&1; then
      _rr_msg="workforce build on $(hostname) past ${attempts} resume attempts without completing.${_lib_note} Now slow-retrying (Rule 8 never-stop). Run scripts/verify-zhc-standard.sh on the box. State: $STATE_FILE. OpenClaw version: $(openclaw --version 2>/dev/null | head -1)"
      _rr_payload=$(jq -nc --arg c "$(hostname)" --arg a "main" --arg m "$_rr_msg" \
        '{action:"escalate",client:$c,agent:$a,message:$m}' 2>/dev/null)
      curl -s -X POST "$_rr_webhook" -H "Content-Type: application/json" ${RESCUE_RANGERS_WEBHOOK_SECRET:+-H X-Rescue-Secret:${RESCUE_RANGERS_WEBHOOK_SECRET}} -d "$_rr_payload" >>"$LOG_FILE" 2>&1 || true
    fi
    _tmp_cap=$(mktemp)
    jq '.resumeCapEscalated = true' "$STATE_FILE" > "$_tmp_cap" 2>/dev/null && mv "$_tmp_cap" "$STATE_FILE" || rm -f "$_tmp_cap"
  fi
  # Slow-backoff past the cap: act roughly every 2h (every 8th */15 fire) but
  # NEVER stop. The MAX_RUNS slow-mode above already throttles the overall cron;
  # here we just avoid spamming a self-ping every 15 min once we're past the cap.
  _attempts_over=$(( attempts - max_attempts ))
  if (( _attempts_over % 8 != 0 )); then
    log "slow-retry: attempt $attempts past cap - backoff skip this fire (will dispatch on the next ~2h boundary)."
    # still bump the counter so backoff advances
    _tmp_a=$(mktemp); jq ".resumeAttempts = $((attempts + 1))" "$STATE_FILE" > "$_tmp_a" && mv "$_tmp_a" "$STATE_FILE"
    exit 0
  fi
  log "slow-retry: attempt $attempts past cap - dispatching a resume self-ping (2h boundary)."
fi

# ---- v10.15.9: OPERATOR-FACING library-gate status surfacing (near-cap) ----
# A persistently-failing library pull would otherwise just keep self-pinging
# silently until the hard cap. When libraries are dirty AND we're within the
# last 2 attempts of the cap, emit ONE operator-facing status line so the
# stuck-library condition becomes visible BEFORE the cap is hit. Throttled to a
# single emission per build via .librariesNearCapNotified in the state file.
near_cap_threshold=$(( max_attempts - 2 ))
(( near_cap_threshold < 1 )) && near_cap_threshold=1
if (( library_dirty == 1 )) && (( attempts >= near_cap_threshold )); then
  already_notified=$(jq -r '.librariesNearCapNotified // false' "$STATE_FILE")
  if [[ "$already_notified" != "true" ]]; then
    _operator_chat="$(resolve_operator_chat_id)"
    _agent_name=$(jq -r '.agentName // "the workforce build"' "$STATE_FILE")
    _company=$(jq -r '.companyName // ""' "$STATE_FILE")
    STATUS_LINE="⚠️ Library gate not closing: ${_company:+$_company - }${_agent_name} has all departments done but roleLibraryStatus=${role_library_status} / sopLibraryStatus=${sop_library_status} after ${attempts}/${max_attempts} resume attempts. The role-library pull or SOP authoring keeps failing - it will hit the cap soon and stop retrying. Check scripts/verify-library-gate.sh on $(hostname). State: $STATE_FILE"
    log "OPERATOR-STATUS (near-cap, libraries dirty): $STATUS_LINE"
    if [[ -n "$_operator_chat" ]]; then
      openclaw message send --channel telegram -t "$_operator_chat" -m "$STATUS_LINE" 2>>"$LOG_FILE" || true
    fi
    # Mark notified so we surface this once, not on every remaining cycle.
    _tmp_notif=$(mktemp)
    jq '.librariesNearCapNotified = true' "$STATE_FILE" > "$_tmp_notif" && mv "$_tmp_notif" "$STATE_FILE"
  fi
fi

# ---- bump attempt counter atomically ----
tmp_state=$(mktemp)
jq ".resumeAttempts = $((attempts + 1))" "$STATE_FILE" > "$tmp_state" && mv "$tmp_state" "$STATE_FILE"

# ---- compose the resume message + dispatch ----
agent_name=$(jq -r '.agentName // "the master orchestrator"' "$STATE_FILE")
owner_chat=$(jq -r '.ownerChat // empty' "$STATE_FILE")
pending_list=$(jq -r '[.departments[] | select(.status == "pending" or .status == "failed") | .slug] | join(", ")' "$STATE_FILE")
stale_list=$(jq -r --arg min "$STALE_BUILDING_MINUTES" '
  [.departments[]
    | select(.status == "building")
    | select(.lastAttemptAt != null)
    | select(((now - (.lastAttemptAt | fromdateiso8601)) / 60) > ($min | tonumber))
    | .slug] | join(", ")
' "$STATE_FILE")

# Find a chat the bot CAN reply to. Priority: owner (already paired) > operator (Remote Rescue).
TARGET_CHAT=""
if [[ -n "$owner_chat" && "$owner_chat" != "null" ]]; then
  TARGET_CHAT="$owner_chat"
else
  TARGET_CHAT="$(resolve_operator_chat_id)"
fi

if [[ -z "$TARGET_CHAT" ]]; then
  log "no usable target chat (ownerChat or operator) - cannot dispatch resume"
  exit 0
fi

if (( library_dirty == 1 )) && (( closeout_dirty == 0 )); then
  # ROOT-CAUSE FIX (2026-06-18): a resume that (re)materializes role folders must
  # also refresh each department's ROSTER.md (the When-to Reference Map the
  # director agent reads). post-build-role-workspaces.py now refreshes ROSTER.md
  # per dept automatically, but run regenerate-dept-roster.py inline here as a
  # deterministic backstop so a partial/resume materialization can NEVER leave a
  # stale roster that under-reports the roles the agent actually has on disk.
  _roster_script="$SCRIPT_DIR/regenerate-dept-roster.py"
  if [[ -f "$_roster_script" ]]; then
    log "[ROSTER-RESUME] refreshing every department ROSTER.md from on-disk role folders"
    python3 "$_roster_script" >>"$LOG_FILE" 2>&1 || true
  fi
  msg="[LIBRARY-RESUME] ${agent_name}: every department is built but the ROLE LIBRARY and/or SOP LIBRARY are NOT populated (roleLibraryStatus=${role_library_status:-unset}, sopLibraryStatus=${sop_library_status:-unset}). The workforce is NOT complete until BOTH are done. Run scripts/verify-library-gate.sh to measure; if role library < 100% re-run scripts/post-build-role-workspaces.py (pulls how-to.md from templates/role-library/ AND refreshes each department's ROSTER.md from the role folders on disk); if SOPs have stubs re-run scripts/populate-sops-from-manifest.py. If any department's ROSTER.md under-reports its role folders, run scripts/regenerate-dept-roster.py to rebuild every roster from disk. Re-run verify-library-gate.sh until it exits 0 (roleLibraryStatus=done AND sopLibraryStatus=done) - ONLY THEN write buildCompletedAt + closeoutStatus=pending. Resume attempt $((attempts + 1)) of $max_attempts. Do NOT message the owner about this - the resume is internal."
# B4: [WIRING-RESUME] self-ping when wiring is dirty
elif (( wiring_dirty > 0 )); then
  log "[WIRING-RESUME] wiring_dirty=$wiring_dirty — one or more departments have wiringStatus!=done. Running verify-wiring.sh inline..."
  _wiring_script_b4="$SCRIPT_DIR/verify-wiring.sh"
  if [[ -f "$_wiring_script_b4" ]]; then
    bash "$_wiring_script_b4" --all >>"$LOG_FILE" 2>&1 || true
  fi
  msg="[WIRING-RESUME] ${agent_name}: wiring_dirty=$wiring_dirty — one or more department agents are not properly wired (registered/reachable/connected). verify-wiring.sh was run inline; check its output in the log. Fix any failed departments and re-run verify-wiring.sh until it exits 0. Resume attempt $((attempts + 1)) of $max_attempts. Do NOT message the owner — this is internal."
elif (( comms_automation_dirty == 1 )); then
  # v10.15.9: cross-skill chain to Skill 38 - fires AFTER libraries are clean.
  # A workforce that built a Communications / Sales / Customer-Support department
  # is NOT fully delivered until Skill 38 has scaffolded the matching comms
  # automations (THE TRINITY: playbook + Build-with-AI prompt + registry row).
  comms_depts=$(jq -r '(.commsAutomationDepartments // []) | join(", ")' "$STATE_FILE")
  msg="[COMMS-AUTOMATION-RESUME] ${agent_name}: all departments + libraries are done, but the comms-automation handoff to Skill 38 is incomplete (commsAutomationStatus=${comms_automation_status}). This workforce built a comms/sales/support department (${comms_depts:-communications/sales/customer-support}) - per the Skill 23 -> Skill 38 cross-skill chain, you MUST scaffold the matching conversational automations. DO THIS: (1) read ~/.openclaw/skills/38-conversational-ai-system/SKILL.md + protocols/conversation-workflows-protocol.md; (2) set commsAutomationStatus=scaffolding; (3) build at MINIMUM the appointment-booking starter via THE TRINITY - communications playbook + its Build-with-AI prompt + a registry row in the client's conversation-workflows/ (plus a pricing/FAQ or lead-followup playbook matching the department that triggered this); (4) run ~/.openclaw/skills/38-conversational-ai-system/scripts/qc-trinity-registry.sh - it must PASS (every registered workflow has its playbook + prompt); (5) ONLY THEN set commsAutomationStatus=done + commsAutomationVerifiedAt in .workforce-build-state.json. Resume attempt $((attempts + 1)) of $max_attempts. Do NOT message the owner about this - this is internal; the owner hears from you via Skill 37 Step 6 only."
elif (( closeout_dirty == 1 )) && (( pending_count == 0 )) && (( stale_building_count == 0 )); then
  # PRD-FINAL-PACKAGE Step 1 (v12.6.0): DETERMINISTIC in-process exec of run-closeout.sh.
  # This is the PRIMARY path. The self-ping below is SECONDARY (fallback only).
  # run-closeout.sh is idempotent -- a double-fire is safe.
  _CLOSEOUT_SCRIPT=""
  for _cand in \
    "$OC_ROOT/skills/37-zhc-closeout/scripts/run-closeout.sh" \
    "$HOME/.openclaw/skills/37-zhc-closeout/scripts/run-closeout.sh" \
    "/data/.openclaw/skills/37-zhc-closeout/scripts/run-closeout.sh"; do
    if [[ -f "$_cand" ]]; then
      _CLOSEOUT_SCRIPT="$_cand"
      break
    fi
  done
  if [[ -n "$_CLOSEOUT_SCRIPT" ]]; then
    log "HOP-4 (v12.6.0): in-process exec of run-closeout.sh (PRIMARY -- deterministic, no Telegram required)"
    # Fire detached so this cron returns immediately; run-closeout.sh runs in background.
    # nohup ensures it survives if the parent cron shell exits.
    nohup bash "$_CLOSEOUT_SCRIPT" >> "$LOG_FILE" 2>&1 &
    log "HOP-4: run-closeout.sh launched (pid=$!); self-ping follows as secondary nudge"
  else
    log "HOP-4: run-closeout.sh not found at any expected path -- falling back to self-ping only"
  fi
  msg="[CLOSEOUT-RESUME] ${agent_name}: workforce build is done (buildCompletedAt set) but closeout is incomplete (closeoutStatus=${closeout_status:-unset}). run-closeout.sh was launched in-process; this is a secondary nudge. If the closeout does not advance within 15 min, invoke scripts/run-closeout.sh manually. The script is idempotent - it picks up from the first un-completed step. Resume attempt $((attempts + 1)) of $max_attempts. Do NOT message the owner about this - the owner only hears from you when Skill 37 Step 6 fires."
else
  msg="[WORKFORCE-RESUME] ${agent_name}: continue the workforce build per the Post-Interview Handoff Protocol in Skill 23. Read .workforce-build-state.json. Pending: ${pending_list:-none}. Stale: ${stale_list:-none}. Closeout status: ${closeout_status:-unset}. Resume attempt $((attempts + 1)) of $max_attempts. Do NOT message the owner about this - the resume is internal. When all departments are done, set closeoutStatus=pending and either invoke ~/.openclaw/skills/37-zhc-closeout/scripts/run-closeout.sh inline OR exit and let the next cron fire pick up the closeout."
fi

log "dispatching resume to chat $TARGET_CHAT (attempt $((attempts + 1))/$max_attempts; pending='$pending_list'; stale='$stale_list'; library_dirty=$library_dirty roleLib='$role_library_status' sopLib='$sop_library_status'; comms_automation_dirty=$comms_automation_dirty comms_automation_status='$comms_automation_status'; closeout_dirty=$closeout_dirty closeout_status='$closeout_status')"
if openclaw message send --channel telegram -t "$TARGET_CHAT" -m "$msg" 2>>"$LOG_FILE"; then
  log "resume dispatch ok"
else
  log "resume dispatch FAILED (non-fatal: in-process exec already fired above if closeout_dirty)"
fi

exit 0
