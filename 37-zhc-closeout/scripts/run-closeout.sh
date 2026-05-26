#!/usr/bin/env bash
# run-closeout.sh -- top-level orchestrator for Skill 37 ZHC Closeout.
#
# Reads .workforce-build-state.json and walks through the 6-step pipeline:
#   1. Skill 32 (Command Center)
#   2. Infographic #1 (Workforce Structure)
#   3. Infographic #2 (How Work Flows)
#   4. Celebration video (Veo 3.1)
#   5. Notion page tree (9 sections)
#   6. Telegram delivery (6 paced messages)
#
# Idempotent -- each step skips if its target URL field is already set.
# All steps write state atomically. The resume cron can pick up a stalled
# closeout at any point and continue from the first un-completed step.

set -u

# ---- platform detection (VPS first, Mac fallback) ----
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[run-closeout] no OpenClaw root found; aborting" >&2
  exit 1
fi

STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
LOG_FILE="$OC_ROOT/workspace/.zhc-closeout.log"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() {
  printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >> "$LOG_FILE"
  printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2"
}

state_get() {
  jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null
}

state_set() {
  # Usage: state_set '.field = value | .other = value'
  local tmp
  tmp=$(mktemp)
  if jq "$1" "$STATE_FILE" > "$tmp"; then
    mv "$tmp" "$STATE_FILE"
  else
    rm -f "$tmp"
    log "ERROR" "state_set failed for expr: $1"
    return 1
  fi
}

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

fail_closeout() {
  local reason="$1"
  log "ERROR" "marking closeout failed: $reason"
  state_set ".closeoutStatus = \"failed\" | .closeoutFailureReason = \"$reason\""
  exit 1
}

# ---- preflight ----
if [[ ! -f "$STATE_FILE" ]]; then
  log "ERROR" "no state file at $STATE_FILE -- nothing to close out"
  exit 1
fi
for cmd in jq curl openclaw; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log "ERROR" "preflight: missing required command: $cmd"
    state_set ".closeoutStatus = \"failed\" | .closeoutFailureReason = \"preflight: missing $cmd\""
    exit 1
  fi
done
if [[ -z "${KIE_API_KEY:-}" ]]; then
  fail_closeout "preflight: KIE_API_KEY env var not set"
fi
if [[ -z "${NOTION_API_TOKEN:-}" ]]; then
  fail_closeout "preflight: NOTION_API_TOKEN env var not set"
fi

build_completed_at=$(state_get '.buildCompletedAt')
if [[ -z "$build_completed_at" || "$build_completed_at" == "null" ]]; then
  log "INFO" "buildCompletedAt not set yet -- Skill 23 not done; nothing to do"
  exit 0
fi

closeout_status=$(state_get '.closeoutStatus')
if [[ "$closeout_status" == "done" || "$closeout_status" == "sent" ]]; then
  log "INFO" "closeoutStatus=$closeout_status -- already complete; nothing to do"
  exit 0
fi

# ---- transition pending → generating (idempotent) ----
if [[ "$closeout_status" != "generating" ]]; then
  state_set ".closeoutStatus = \"generating\" | .closeoutStartedAt = \"$(now_iso)\""
  log "INFO" "closeout started -- closeoutStatus transitioned to generating"
fi

# ----------------------------------------------------------------------
# STEP 1 -- Skill 32 (Command Center) -- v10.14.20: REAL 8-phase orchestrator
# ----------------------------------------------------------------------
# Through v10.14.19, this step invoked only materialize-dept-agents.sh (Phase 4
# of the INSTALL.md 8-phase plan) and then marked commandCenterStatus=done.
# Phases 6 (dashboard deploy on :4000), 6b (n8n webhook + cloudflared tunnel),
# 7 (verification) never ran on any client. That's why no BlackCEO Command
# Center dashboard came up + Trevor never got n8n notifications for completed
# builds. The closeout was claiming "done" on a 12.5%-complete install.
#
# v10.14.20: delegate to run-full-install.sh which runs all 8 phases in order
# with idempotent state checkpoints. Closeout still owns the failure path --
# if Skill 32's orchestrator marks commandCenterStatus=failed with a reason,
# we fail_closeout with the actual error so the resume cron can pick it up
# instead of cascading into infographic generation against a broken install.
log "INFO" "step=1 command-center: starting (delegating to run-full-install.sh)"
cc_status=$(state_get '.commandCenterStatus')
if [[ "$cc_status" == "done" ]]; then
  log "INFO" "step=1 command-center: already done -- skipping"
else
  # v10.14.17 schema extension carries these into state at interview time.
  COMPANY_NAME_CC=$(state_get '.companyName')
  OWNER_EMAIL_CC=$(state_get '.ownerEmail')
  COMPANY_DOMAIN_CC=$(state_get '.companyDomain')

  if [[ -z "$COMPANY_NAME_CC" ]]; then
    log "WARN" "step=1 command-center: companyName missing from state -- using slug fallback"
    COMPANY_NAME_CC="$(state_get '.companySlug')"
    [[ -z "$COMPANY_NAME_CC" ]] && COMPANY_NAME_CC="Unnamed Company"
  fi

  if [[ -z "$OWNER_EMAIL_CC" ]]; then
    if [[ -n "$COMPANY_DOMAIN_CC" ]]; then
      OWNER_EMAIL_CC="noreply@$COMPANY_DOMAIN_CC"
    else
      OWNER_EMAIL_CC="noreply@example.com"
    fi
    log "WARN" "step=1 command-center: ownerEmail missing from state -- using placeholder $OWNER_EMAIL_CC (will not block install)"
  fi

  # Derive a client slug for the tunnel subdomain -- prefer existing
  # companySlug field, fall back to a sanitized company name.
  CLIENT_SLUG_CC=$(state_get '.companySlug')
  if [[ -z "$CLIENT_SLUG_CC" ]]; then
    CLIENT_SLUG_CC=$(echo "$COMPANY_NAME_CC" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' | sed 's/--*/-/g; s/^-//; s/-$//')
    [[ -z "$CLIENT_SLUG_CC" ]] && CLIENT_SLUG_CC="client"
  fi

  RUN_FULL_INSTALL="$OC_ROOT/skills/32-command-center-setup/scripts/run-full-install.sh"
  if [[ ! -x "$RUN_FULL_INSTALL" ]]; then
    log "ERROR" "step=1 command-center: run-full-install.sh missing/not-executable at $RUN_FULL_INSTALL"
    state_set '.commandCenterStatus = "failed"'
    fail_closeout "Skill 32 run-full-install.sh not installed (re-run install.sh or update-skills.sh)"
  fi

  log "INFO" "step=1 command-center: invoking run-full-install.sh $CLIENT_SLUG_CC \"$COMPANY_NAME_CC\" $OWNER_EMAIL_CC"
  if ! bash "$RUN_FULL_INSTALL" "$CLIENT_SLUG_CC" "$COMPANY_NAME_CC" "$OWNER_EMAIL_CC" >>"$LOG_FILE" 2>&1; then
    # run-full-install.sh already wrote commandCenterFailureReason into state
    actual_reason=$(state_get '.commandCenterFailureReason')
    [[ -z "$actual_reason" ]] && actual_reason="run-full-install.sh exited non-zero (see $LOG_FILE)"
    log "ERROR" "step=1 command-center: $actual_reason"
    fail_closeout "Skill 32 orchestrator failed: $actual_reason"
  fi

  log "INFO" "step=1 command-center: done -- commandCenterUrl=$(state_get '.commandCenterUrl')"
fi

# ----------------------------------------------------------------------
# v10.X.4: step-level idempotency.
#
# Through v10.X.3 each step that failed called fail_closeout() and exited
# immediately, which is what blocked Notion + Telegram on the Evelyn run
# even though Notion was buildable. Now each step has its own try/catch,
# records STEP_<NAME>_STATUS = ok|failed|skipped, and run-closeout continues
# regardless. At the end we evaluate the matrix:
#
#   * If Inf1 OR Inf2 OR Telegram failed  -> closeoutStatus = failed
#   * If only Notion and/or Video failed  -> closeoutStatus = partial
#                                            (with closeoutPartialArtifacts)
#   * If 5/6 or 6/6 succeed               -> closeoutStatus = done
#
# The telegram step itself adapts: if Video failed, slot 4 sends a text-only
# "celebration video deferred" message instead of skipping silently.
# ----------------------------------------------------------------------

# Common helpers for step-level idempotency.
run_step() {
  # run_step <name> <script> [args...]
  local name="$1"; shift
  local script="$1"; shift
  log "INFO" "step=$name: starting ($script $*)"
  if bash "$script" "$@"; then
    eval "STEP_${name}_STATUS=ok"
    log "INFO" "step=$name: ok"
  else
    eval "STEP_${name}_STATUS=failed"
    log "ERROR" "step=$name: failed (see log)"
  fi
}

# Defaults so referencing an unset step does not trip set -u.
STEP_INF1_STATUS=skipped
STEP_INF2_STATUS=skipped
STEP_VIDEO_STATUS=skipped
STEP_NOTION_STATUS=skipped
STEP_TELEGRAM_STATUS=skipped

# ----------------------------------------------------------------------
# STEP 2 -- Infographic #1 (Workforce Structure)
# ----------------------------------------------------------------------
if [[ -n "$(state_get '.infographic1Url')" && "$(state_get '.infographic1Url')" != "null" ]]; then
  log "INFO" "step=2 infographic-1: already done -- skipping"
  STEP_INF1_STATUS=ok
else
  run_step INF1 "$SKILL_DIR/scripts/generate-infographics.sh" structure
fi

# ----------------------------------------------------------------------
# STEP 3 -- Infographic #2 (How Work Flows)
# ----------------------------------------------------------------------
if [[ -n "$(state_get '.infographic2Url')" && "$(state_get '.infographic2Url')" != "null" ]]; then
  log "INFO" "step=3 infographic-2: already done -- skipping"
  STEP_INF2_STATUS=ok
else
  run_step INF2 "$SKILL_DIR/scripts/generate-infographics.sh" workflow
fi

# ----------------------------------------------------------------------
# STEP 4 -- Celebration Video
# ----------------------------------------------------------------------
if [[ -n "$(state_get '.celebrationVideoUrl')" && "$(state_get '.celebrationVideoUrl')" != "null" ]]; then
  log "INFO" "step=4 celebration-video: already done -- skipping"
  STEP_VIDEO_STATUS=ok
else
  run_step VIDEO "$SKILL_DIR/scripts/generate-celebration-video.sh"
fi

# ----------------------------------------------------------------------
# STEP 5 -- Notion Page Tree
# ----------------------------------------------------------------------
if [[ -n "$(state_get '.notionRootPageUrl')" && "$(state_get '.notionRootPageUrl')" != "null" ]]; then
  log "INFO" "step=5 notion: already done -- skipping"
  STEP_NOTION_STATUS=ok
else
  run_step NOTION "$SKILL_DIR/scripts/create-notion-closeout.sh"
fi

# ----------------------------------------------------------------------
# STEP 6 -- Telegram Delivery
#
# Exports ZHC_VIDEO_STATUS to send-telegram-celebration.sh so slot 4 can
# substitute a text-only "video deferred" message when the video step failed.
# ----------------------------------------------------------------------
export ZHC_VIDEO_STATUS="$STEP_VIDEO_STATUS"
run_step TELEGRAM "$SKILL_DIR/scripts/send-telegram-celebration.sh"

# ----------------------------------------------------------------------
# Finalize -- evaluate step matrix
# ----------------------------------------------------------------------
critical_failed=()
soft_failed=()
[[ "$STEP_INF1_STATUS"     == "failed" ]] && critical_failed+=("infographic-1")
[[ "$STEP_INF2_STATUS"     == "failed" ]] && critical_failed+=("infographic-2")
[[ "$STEP_TELEGRAM_STATUS" == "failed" ]] && critical_failed+=("telegram")
[[ "$STEP_VIDEO_STATUS"    == "failed" ]] && soft_failed+=("celebration-video")
[[ "$STEP_NOTION_STATUS"   == "failed" ]] && soft_failed+=("notion")

if (( ${#critical_failed[@]} > 0 )); then
  reason="critical-failed: $(IFS=,; echo "${critical_failed[*]}")"
  [[ ${#soft_failed[@]} -gt 0 ]] && reason="$reason; soft-failed: $(IFS=,; echo "${soft_failed[*]}")"
  state_set ".closeoutStatus = \"failed\" | .closeoutFailureReason = \"$reason\" | .closeoutCompletedAt = \"$(now_iso)\""
  log "ERROR" "closeout finalize: $reason"
  exit 1
elif (( ${#soft_failed[@]} > 0 )); then
  partial=$(printf '%s\n' "${soft_failed[@]}" | jq -R . | jq -s .)
  state_set ".closeoutStatus = \"partial\" | .closeoutPartialArtifacts = $partial | .closeoutCompletedAt = \"$(now_iso)\""
  log "WARN" "closeout finalize: partial -- soft-failed: ${soft_failed[*]}"
  exit 0
else
  # ------------------------------------------------------------------
  # Phantom-closeout guard (v10.14.5).
  # A step can return ok while never having written its real artifact
  # (e.g. an upload helper that exits 0 on a soft error, or a telegram
  # send that logged but recorded zero delivered messages). Before we
  # are allowed to claim "done", assert the two load-bearing artifacts
  # actually exist in state:
  #   * infographic1Url is present and non-null
  #   * at least one telegram message was actually delivered
  #     (.messagesDelivered is a non-empty array)
  # If either is missing, record "partial" with a closeoutPartialReason
  # instead of falsely claiming a complete closeout.
  # ------------------------------------------------------------------
  guard_reasons=()

  inf1_url=$(state_get '.infographic1Url')
  if [[ -z "$inf1_url" || "$inf1_url" == "null" ]]; then
    guard_reasons+=("infographic1Url-missing")
  fi

  delivered_count=$(state_get '.messagesDelivered | length')
  if [[ -z "$delivered_count" || "$delivered_count" == "null" || "$delivered_count" == "0" ]]; then
    guard_reasons+=("telegram-no-messages-delivered")
  fi

  if (( ${#guard_reasons[@]} > 0 )); then
    greason="phantom-closeout-guard: $(IFS=,; echo "${guard_reasons[*]}")"
    state_set ".closeoutStatus = \"partial\" | .closeoutPartialReason = \"$greason\" | .closeoutCompletedAt = \"$(now_iso)\""
    log "WARN" "closeout finalize: guard blocked done -- $greason"
    exit 0
  fi

  state_set ".closeoutStatus = \"done\" | .closeoutCompletedAt = \"$(now_iso)\""
  log "INFO" "closeout complete -- closeoutStatus=done"
  exit 0
fi
