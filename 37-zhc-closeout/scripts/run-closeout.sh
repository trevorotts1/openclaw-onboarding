#!/usr/bin/env bash
# run-closeout.sh -- top-level orchestrator for Skill 37 ZHC Closeout.
#
# PRD-2.8: GATED PIPELINE. Every step is a gate. The pipeline does not advance
# until each gate passes the 8.5 quality gate + delivery verification.
#
# Reads .workforce-build-state.json and walks through the 7-step pipeline:
#   1. Skill 32 (Command Center)
#   2. Infographic #1 (Workforce Structure) -- org-chart connector-tree ASSERTED
#   3. Infographic #2 (How Work Flows)
#   4. Celebration video (Gemini Omni / Veo fallback)
#   5. Notion page tree (9 sections)
#   5.5. GHL media upload (conditional)
#   6. Telegram delivery (6 paced messages) + delivery confirmation gate
#   6.5. n8n wire-up (optional, non-blocking)
#   7. Operator summary
#
# PRD-2.8 ADDITIONS vs prior versions:
#   • PRE-FLIGHT: validates KIE_API_KEY, NOTION_API_TOKEN, AND Telegram gateway
#     health (openclaw gateway status) before ANY generation. Fails LOUD at start.
#   • closeoutDeliverables: 7 explicit per-leg fields written as each step completes.
#   • Org-chart QC: qc-assert-org-chart-connector-tree.sh is INVOKED (not just
#     documented) after Step 2 to assert connector lines, not a card grid.
#   • n8n wiring step: wire-n8n-closeout.sh fires at Step 6.5 (soft-fail OK).
#   • Dedicated closeout resume cron registered at start (resume-closeout-cron.sh),
#     separate from the build-resume cron; self-removes on completion.
#   • Resume cron UUID written to state (.closeoutResumeUuid) for loop-registry.
#
# Idempotent -- each step skips if its target URL field is already set.
# All steps write state atomically. The dedicated closeout-resume cron fires
# every 15 min until all 7 closeoutDeliverables legs are done or waived.

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

STATE_FILE="${ZHC_STATE_FILE:-${OC_ROOT}/workspace/.workforce-build-state.json}"
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
# ---- PRD-2.15 (v12.3.12): EARLY interviewQc check (before API-key preflight) ----
# If the interview QC hasn't passed, refuse immediately - no point checking API keys
# for a closeout we're about to refuse. This is a cheap token-free read.
_early_qc=$(jq -r '.interviewQc.status // empty' "$STATE_FILE" 2>/dev/null || true)
_early_build_done=$(jq -r '.buildCompletedAt // empty' "$STATE_FILE" 2>/dev/null || true)
if [[ -n "$_early_build_done" && "$_early_build_done" != "null" && "$_early_qc" != "pass" ]]; then
  # QC script search (best-effort, non-fatal if absent)
  _EARLY_QC_SCRIPT=""
  for _cand in \
    "${SKILL_DIR%/*}/23-ai-workforce-blueprint/scripts/qc-interview-completion.py" \
    "$OC_ROOT/skills/23-ai-workforce-blueprint/scripts/qc-interview-completion.py" \
    "$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-interview-completion.py" \
    "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-interview-completion.py"; do
    [[ -f "$_cand" ]] && _EARLY_QC_SCRIPT="$_cand" && break
  done
  if [[ -n "$_EARLY_QC_SCRIPT" ]]; then
    # --write-state is a flag; the state path goes via --state (the old positional
    # form was rejected by argparse and silently no-op'd this QC re-check).
    python3 "$_EARLY_QC_SCRIPT" --write-state --state "$STATE_FILE" >>"$LOG_FILE" 2>&1 || true
    _early_qc=$(jq -r '.interviewQc.status // empty' "$STATE_FILE" 2>/dev/null || true)
  fi
  if [[ "$_early_qc" != "pass" ]]; then
    _early_block_reason="interviewQc.status=${_early_qc} (not pass) - refusing to close out an unverified interview."
    log "ERROR" "BLOCKED (interviewQc gate): $_early_block_reason"
    _tmp_s=$(mktemp)
    jq ".closeoutStatus = \"blocked-interview-incomplete\" | .closeoutBlockReason = \"$_early_block_reason\"" \
      "$STATE_FILE" > "$_tmp_s" && mv "$_tmp_s" "$STATE_FILE" || rm -f "$_tmp_s"
    _TS_EARLY=$(now_iso)
    _tmp_b=$(mktemp)
    jq "
      .closeoutBlockers = (
        (.closeoutBlockers // [])
        | map(select(.class != \"STUCK_QC_FAILED\"))
        | . + [{\"class\":\"STUCK_QC_FAILED\",\"reason\":\"$_early_block_reason\",\"since\":\"$_TS_EARLY\",\"escalatedAt\":null,\"cleared\":false}]
      )
    " "$STATE_FILE" > "$_tmp_b" && mv "$_tmp_b" "$STATE_FILE" || rm -f "$_tmp_b"
    _OP_CHAT="${OPERATOR_TELEGRAM_CHAT_ID:-5252140759}"
    if command -v openclaw >/dev/null 2>&1 && [[ "${ZHC_SKIP_TG_PREFLIGHT:-0}" != "1" ]]; then
      openclaw message send --channel telegram -t "$_OP_CHAT" \
        -m "🚨 ZHC BLOCKED [STUCK_QC_FAILED] interviewQc.status=${_early_qc} - closeout refused for $(jq -r '.companyName // empty' "$STATE_FILE" 2>/dev/null). State: $STATE_FILE" \
        >>"$LOG_FILE" 2>&1 || true
    fi
    exit 0  # never fail-hard; watchdog + resume cron drive it
  fi
fi

if [[ -z "${KIE_API_KEY:-}" ]]; then
  fail_closeout "preflight: KIE_API_KEY env var not set"
fi
if [[ -z "${NOTION_API_TOKEN:-}" ]]; then
  fail_closeout "preflight: NOTION_API_TOKEN env var not set"
fi

# PRD-2.8: TELEGRAM GATEWAY PREFLIGHT -- fail LOUD before any generation if
# the gateway is unreachable. Sending 6 celebration messages to a client
# against a non-functional gateway is the definition of "silent mid-way fail."
# Skip this check when ZHC_SKIP_TG_PREFLIGHT=1 (e.g. unit tests).
if [[ "${ZHC_SKIP_TG_PREFLIGHT:-0}" != "1" ]]; then
  log "INFO" "preflight: checking Telegram gateway health"
  tg_gateway_ok=0
  if command -v openclaw >/dev/null 2>&1; then
    gw_status_output=$(openclaw gateway status 2>&1 || true)
    if printf '%s' "$gw_status_output" | grep -qiE '"status"\s*:\s*"(ok|running|healthy)"|gateway.*(running|ok|healthy)|status.*ok'; then
      tg_gateway_ok=1
      log "INFO" "preflight: Telegram gateway healthy"
    else
      # Try a lighter check: can we reach the gateway process at all?
      if openclaw gateway status 2>/dev/null | grep -qi 'running\|online\|ok'; then
        tg_gateway_ok=1
        log "INFO" "preflight: Telegram gateway reachable (running)"
      fi
    fi
  fi
  if [[ "$tg_gateway_ok" -eq 0 ]]; then
    fail_closeout "preflight: Telegram gateway not reachable or not healthy -- cannot deliver celebration messages; resolve gateway before retrying"
  fi
fi

build_completed_at=$(state_get '.buildCompletedAt')
if [[ -z "$build_completed_at" || "$build_completed_at" == "null" ]]; then
  log "INFO" "buildCompletedAt not set yet -- Skill 23 not done; nothing to do"
  exit 0
fi

# ---- PRD-2.15 (v12.3.12): interviewQc HARD GATE --------------------------------
# The schema's own TODO (build-state-schema.json:506): run-closeout.sh should
# gate on interviewQc.status != 'pass' before proceeding. This wires that gate.
# A premature/seeded buildCompletedAt can no longer slip a half-interview into
# a celebration (e.g. Beverly at 21/30 with no QC run = REFUSED, not silently ignored).
# Gate is placed BEFORE the expensive generation preflight (KIE/Notion/TG checks)
# so a stalled interview is surfaced immediately without requiring API keys.
_qc_status=$(state_get '.interviewQc.status')
if [[ "$_qc_status" != "pass" ]]; then
  # Try to (re)compute it autonomously before deciding
  _QC_SCRIPT=""
  for _cand in \
    "${SKILL_DIR%/*}/23-ai-workforce-blueprint/scripts/qc-interview-completion.py" \
    "$OC_ROOT/skills/23-ai-workforce-blueprint/scripts/qc-interview-completion.py" \
    "$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-interview-completion.py" \
    "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-interview-completion.py"; do
    [[ -f "$_cand" ]] && _QC_SCRIPT="$_cand" && break
  done
  if [[ -n "$_QC_SCRIPT" ]]; then
    log "INFO" "interviewQc.status=${_qc_status} - running qc-interview-completion.py --write-state --state (best-effort)"
    # --write-state is a flag; the state path goes via --state (the old positional
    # form was rejected by argparse and silently no-op'd this QC re-check).
    python3 "$_QC_SCRIPT" --write-state --state "$STATE_FILE" >>"$LOG_FILE" 2>&1 || true
    _qc_status=$(state_get '.interviewQc.status')
    log "INFO" "interviewQc.status after inline QC run: ${_qc_status}"
  fi
fi
if [[ "$_qc_status" != "pass" ]]; then
  _block_reason="interviewQc.status=${_qc_status} (not pass) - refusing to close out an unverified interview. Run qc-interview-completion.py and ensure status=pass."
  log "ERROR" "BLOCKED: $_block_reason"
  state_set ".closeoutStatus = \"blocked-interview-incomplete\" | .closeoutBlockReason = \"$_block_reason\""
  # Write closeoutBlockers entry so the operator surface (fleet-stuck-clients.sh) shows it
  _TS=$(now_iso)
  state_set "
    .closeoutBlockers = (
      (.closeoutBlockers // [])
      | map(select(.class != \"STUCK_QC_FAILED\"))
      | . + [{\"class\":\"STUCK_QC_FAILED\",\"reason\":\"$_block_reason\",\"since\":\"$_TS\",\"escalatedAt\":null,\"cleared\":false}]
    )
  " || true
  # Escalate operator via Telegram (non-fatal)
  _OPERATOR_CHAT="${OPERATOR_TELEGRAM_CHAT_ID:-5252140759}"
  if command -v openclaw >/dev/null 2>&1 && [[ "${ZHC_SKIP_TG_PREFLIGHT:-0}" != "1" ]]; then
    openclaw message send --channel telegram -t "$_OPERATOR_CHAT" \
      -m "🚨 ZHC BLOCKED [STUCK_QC_FAILED] interviewQc.status=${_qc_status} - closeout refused for $(state_get '.companyName'). Verify interview + run QC. State: $STATE_FILE" \
      >>"$LOG_FILE" 2>&1 || true
  fi
  exit 0  # never fail-hard; watchdog + resume cron drive it
fi
log "INFO" "interviewQc.status=pass - gate cleared"

# ---- v10.x: ZHC-STANDARD PREFLIGHT (libraries must be REAL on disk) -------
# buildCompletedAt alone is not proof: an agent could have written it while the
# role/SOP libraries are empty/thin. Re-verify the disk substance via Skill 23's
# verify-zhc-standard.sh (the single source of truth) BEFORE generating ANY
# closeout artifact. If the role/SOP library is not substantive, REFUSE to
# close out and let the resume cron re-fire the library build - never deliver a
# celebration for an empty workforce.
ZHC_STD_SCRIPT=""
for cand in \
  "$OC_ROOT/skills/23-ai-workforce-blueprint/scripts/verify-zhc-standard.sh" \
  "$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/verify-zhc-standard.sh" \
  "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/verify-zhc-standard.sh"; do
  [[ -f "$cand" ]] && ZHC_STD_SCRIPT="$cand" && break
done
if [[ -n "$ZHC_STD_SCRIPT" ]]; then
  bash "$ZHC_STD_SCRIPT" >> "$LOG_FILE" 2>&1
  ZHC_STD_RC=$?
  # v10.x HARD FLOOR: rc 3 = department floor not met ON DISK (fewer than the 16
  # mandatory + industry vertical-pack departments, minus explicit declines -
  # measured against real folders, NOT the build-state JSON). rc 4 = role library
  # not done, rc 5 = SOP library not done. ALL THREE block closeout so a
  # HEAVILY-REDUCED workforce (Cassandra 3-dept / Kofi-style 6-dept / a seeded
  # build-state fiction) can never reach a celebration. The resume cron keeps
  # driving (never-stop) until the floor is instantiated + the libraries fill.
  if [[ "$ZHC_STD_RC" == "3" ]]; then
    log "ERROR" "ZHC-standard preflight FAILED (rc=3): DEPARTMENT FLOOR NOT MET ON DISK. The 16 mandatory + matched vertical-pack departments are not all present as real folders (and were not explicitly declined). REFUSING to close out a HEAVILY-REDUCED workforce. The resume cron will re-fire the department floor + the build."
    state_set ".closeoutStatus = \"blocked-floor-incomplete\" | .closeoutBlockReason = \"verify-zhc-standard rc=3 (department floor not met on disk)\""
    exit 0
  fi
  if [[ "$ZHC_STD_RC" == "4" || "$ZHC_STD_RC" == "5" ]]; then
    log "ERROR" "ZHC-standard preflight FAILED (rc=$ZHC_STD_RC): role/SOP library not substantive on disk. REFUSING to close out an empty workforce. The resume cron will re-fire the library build."
    state_set ".closeoutStatus = \"blocked-libraries-incomplete\" | .closeoutBlockReason = \"verify-zhc-standard rc=$ZHC_STD_RC (role/SOP library not substantive)\""
    exit 0
  fi
  log "INFO" "ZHC-standard preflight rc=$ZHC_STD_RC (department floor + libraries verified substantive enough to close out)"
else
  log "WARN" "verify-zhc-standard.sh not found -- proceeding on buildCompletedAt alone (older Skill 23 bundle)"
fi

# B5: HARD verify-wiring.sh precondition — wiring must be done before closeout
VERIFY_WIRING_SCRIPT=""
for _vw_cand in \
  "$OC_ROOT/skills/23-ai-workforce-blueprint/scripts/verify-wiring.sh" \
  "$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/verify-wiring.sh" \
  "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/verify-wiring.sh"; do
  [[ -f "$_vw_cand" ]] && VERIFY_WIRING_SCRIPT="$_vw_cand" && break
done
if [[ -n "$VERIFY_WIRING_SCRIPT" ]]; then
  bash "$VERIFY_WIRING_SCRIPT" --all >> "$LOG_FILE" 2>&1
  VERIFY_WIRING_RC=$?
  if [[ "$VERIFY_WIRING_RC" != "0" ]]; then
    log "ERROR" "verify-wiring.sh preflight FAILED (rc=$VERIFY_WIRING_RC): one or more departments are not properly registered/reachable. REFUSING to close out an unwired workforce. The resume cron will re-fire wiring."
    state_set ".closeoutStatus = \"blocked-wiring-incomplete\" | .closeoutBlockReason = \"verify-wiring.sh rc=$VERIFY_WIRING_RC (registration/reachability not verified)\""
    exit 0
  fi
  log "INFO" "verify-wiring.sh preflight rc=$VERIFY_WIRING_RC (wiring verified)"
else
  log "WARN" "verify-wiring.sh not found — proceeding without wiring check (older Skill 23 bundle)"
fi

# B6: HARD verify-routing.sh precondition — routing must be clean before closeout.
# A box with a broken routing defect (CEO builds inline instead of routing to departments)
# MUST NOT close out — the workforce is not operational. Wires apply-routing-fix.sh as
# the remediation path. Exit-0 on failure (same pattern as B5) so the resume cron re-fires.
# Skip via ZHC_SKIP_ROUTING_PREFLIGHT=1 in unit-test environments.
if [[ "${ZHC_SKIP_ROUTING_PREFLIGHT:-0}" != "1" ]]; then
  VERIFY_ROUTING_SCRIPT=""
  for _vr_cand in \
    "${SKILL_DIR%/*}/scripts/verify-routing.sh" \
    "$OC_ROOT/skills/scripts/verify-routing.sh" \
    "$HOME/.openclaw/skills/scripts/verify-routing.sh" \
    "/data/.openclaw/skills/scripts/verify-routing.sh"; do
    [[ -f "$_vr_cand" ]] && VERIFY_ROUTING_SCRIPT="$_vr_cand" && break
  done
  # Fallback: search from onboarding dir peer-location
  if [[ -z "$VERIFY_ROUTING_SCRIPT" ]]; then
    _vr_peer="${SKILL_DIR%/*}/scripts/verify-routing.sh"
    [[ -f "$_vr_peer" ]] && VERIFY_ROUTING_SCRIPT="$_vr_peer"
  fi
  if [[ -n "$VERIFY_ROUTING_SCRIPT" ]]; then
    bash "$VERIFY_ROUTING_SCRIPT" >> "$LOG_FILE" 2>&1
    VERIFY_ROUTING_RC=$?
    if [[ "$VERIFY_ROUTING_RC" != "0" ]]; then
      log "ERROR" "verify-routing.sh preflight FAILED (rc=$VERIFY_ROUTING_RC): routing defect detected — CEO master agent is missing one or more routing-fix layers. REFUSING to close out a box with broken routing. Fix: run scripts/apply-routing-fix.sh then retry closeout."
      state_set ".closeoutStatus = \"blocked-routing-defect\" | .closeoutBlockReason = \"verify-routing.sh rc=$VERIFY_ROUTING_RC (routing defect present — run apply-routing-fix.sh)\""
      exit 1
    fi
    log "INFO" "verify-routing.sh preflight rc=$VERIFY_ROUTING_RC (routing verified clean)"
  else
    log "WARN" "verify-routing.sh not found — skipping routing check (ensure openclaw-onboarding is up to date)"
  fi
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

# PRD-2.8: REGISTER the DEDICATED CLOSEOUT RESUME CRON (loop registry entry).
# This is a SEPARATE cron from workforce-build-resume (Skill 23). It fires every
# 15 min, checks all 7 closeoutDeliverables legs, and self-removes when done.
# Idempotent: skip if .closeoutResumeUuid is already set in state.
existing_cron_uuid=$(state_get '.closeoutResumeUuid')
if [[ -z "$existing_cron_uuid" || "$existing_cron_uuid" == "null" ]]; then
  RESUME_CRON_SCRIPT="$SKILL_DIR/scripts/resume-closeout-cron.sh"
  if [[ -f "$RESUME_CRON_SCRIPT" ]] && command -v openclaw >/dev/null 2>&1; then
    log "INFO" "registering dedicated closeout-resume cron (PRD-2.8 loop registry)"
    cron_register_output=$(openclaw cron add \
      --name "closeout-resume" \
      --schedule "*/15 * * * *" \
      --command "bash $RESUME_CRON_SCRIPT" \
      --json 2>>"$LOG_FILE" || true)
    cron_uuid=$(printf '%s' "$cron_register_output" | jq -r '.uuid // .id // empty' 2>/dev/null || true)
    if [[ -n "$cron_uuid" && "$cron_uuid" != "null" ]]; then
      state_set ".closeoutResumeUuid = \"$cron_uuid\" | .closeoutResumeRegisteredAt = \"$(now_iso)\""
      log "INFO" "closeout-resume cron registered: uuid=$cron_uuid (loop-registry: resume-closeout-cron)"
    else
      log "WARN" "could not register closeout-resume cron (openclaw cron add returned no UUID) -- resume will fall back to workforce-build-resume cron"
    fi
  else
    log "WARN" "resume-closeout-cron.sh or openclaw CLI not found -- skipping cron registration"
  fi
else
  log "INFO" "closeout-resume cron already registered (uuid=$existing_cron_uuid) -- skipping re-registration"
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

# ----------------------------------------------------------------------
# THE 8.5 QUALITY GATE (MANDATORY) -- see QUALITY-GATE.md
#
# Systemic requirement: no closeout artifact (org chart, flow diagram, Notion
# closeout doc) may be delivered to the client until the running agent has
# RATED it 1-10 and it scores >= ZHC_QUALITY_MIN (default 8.5) AND passes its
# QC checks. Below the bar => iterate/regenerate and re-rate, up to
# ZHC_QUALITY_MAX_ATTEMPTS (default 3). If it still cannot pass, HOLD the
# artifact (do NOT deliver it) and flag for human review. NEVER ship subpar.
#
# The agent that runs this skill is the rater + QC. The artifact-generating
# scripts (generate-infographics.sh) are deterministic enough to regenerate;
# the rating itself is performed by the agent against the rubric in
# QUALITY-GATE.md. This block enforces the LOOP + HOLD mechanics so a subpar
# artifact can never silently flow into the delivery (Telegram / media library
# / GHL / Drive) step.
# ----------------------------------------------------------------------
ZHC_QUALITY_MIN="${ZHC_QUALITY_MIN:-8.5}"
ZHC_QUALITY_MAX_ATTEMPTS="${ZHC_QUALITY_MAX_ATTEMPTS:-3}"

# rate_meets_gate <score> -> returns 0 if score >= ZHC_QUALITY_MIN
rate_meets_gate() {
  awk -v s="$1" -v min="$ZHC_QUALITY_MIN" 'BEGIN { exit !(s+0 >= min+0) }'
}

# read the agent-supplied rating for an artifact from the state file. The agent
# writes its honest 1-10 score (against the QUALITY-GATE.md rubric) plus a
# one-line justification into state before re-invoking the gate. Field shape:
#   .qualityRatings.<artifact> = { score: <num>, qc: "pass"|"fail", note: "..." }
# If unrated, returns empty so the gate forces a (re)generate+rate cycle.
gate_get_score() { state_get ".qualityRatings.${1}.score"; }
gate_get_qc()    { state_get ".qualityRatings.${1}.qc"; }

# generate_rate_gate <artifact-key> <step-name> <generator-script> [args...]
#
# Runs the artifact generator, then enforces the gate. Loop:
#   generate -> (agent rates+QCs into state) -> if score >= MIN AND qc==pass:
#   deliver-eligible; else iterate (regenerate) up to ZHC_QUALITY_MAX_ATTEMPTS.
# On exhaustion: mark the artifact HELD (qualityHeld[] += key) so the delivery
# steps skip it and the operator can review, rather than shipping below 8.5.
#
# Sets GATE_<STEPNAME>_RESULT = pass|held and STEP_<STEPNAME>_STATUS = ok|failed.
generate_rate_gate() {
  local key="$1"; shift
  local name="$1"; shift
  local script="$1"; shift

  local attempt=0 score qc
  while (( attempt < ZHC_QUALITY_MAX_ATTEMPTS )); do
    attempt=$((attempt + 1))
    log "INFO" "gate[$key]: generate attempt $attempt/$ZHC_QUALITY_MAX_ATTEMPTS ($script $*)"
    if bash "$script" "$@"; then
      eval "STEP_${name}_STATUS=ok"
    else
      eval "STEP_${name}_STATUS=failed"
      log "ERROR" "gate[$key]: generator failed on attempt $attempt (see log)"
      # a generator hard-failure is not a rating failure; let the step matrix
      # handle it. Stop the gate loop -- there is nothing to rate.
      eval "GATE_${name}_RESULT=held"
      state_set ".qualityHeld = ((.qualityHeld // []) + [\"$key\"] | unique)" || true
      return 0
    fi

    # The agent MUST now self-rate this artifact 1-10 against QUALITY-GATE.md
    # and QC it, writing .qualityRatings.<key>.{score,qc,note} into state.
    score=$(gate_get_score "$key")
    qc=$(gate_get_qc "$key")
    if [[ -z "$score" ]]; then
      log "WARN" "gate[$key]: artifact NOT YET RATED by agent. Agent must self-rate 1-10 against QUALITY-GATE.md and write .qualityRatings.$key.{score,qc,note} before delivery. Holding pending rating."
      eval "GATE_${name}_RESULT=held"
      state_set ".qualityHeld = ((.qualityHeld // []) + [\"$key\"] | unique)" || true
      return 0
    fi

    if rate_meets_gate "$score" && [[ "$qc" == "pass" ]]; then
      log "INFO" "gate[$key]: PASS (score=$score >= $ZHC_QUALITY_MIN, qc=$qc) -- deliver-eligible"
      eval "GATE_${name}_RESULT=pass"
      state_set ".qualityHeld = ((.qualityHeld // []) - [\"$key\"])" || true
      return 0
    fi

    log "WARN" "gate[$key]: BELOW GATE (score=$score, min=$ZHC_QUALITY_MIN, qc=$qc) on attempt $attempt -- iterate + regenerate + re-rate"
    # clear the stale rating so the next loop forces a fresh self-rate
    state_set "del(.qualityRatings.${key})" || true
  done

  log "ERROR" "gate[$key]: could not reach $ZHC_QUALITY_MIN after $ZHC_QUALITY_MAX_ATTEMPTS attempts -- HOLDING (not delivering) + flagging for human review"
  eval "GATE_${name}_RESULT=held"
  state_set ".qualityHeld = ((.qualityHeld // []) + [\"$key\"] | unique) | .closeoutHoldReason = \"quality-gate: $key below $ZHC_QUALITY_MIN after $ZHC_QUALITY_MAX_ATTEMPTS attempts\"" || true
  # escalate to operator -- a held artifact needs a human, do not ship subpar
  if [[ -f "$OC_ROOT/skills/shared-utils/operator-chat-id.sh" ]]; then
    # shellcheck disable=SC1091
    source "$OC_ROOT/skills/shared-utils/operator-chat-id.sh" 2>/dev/null || true
    if [[ -n "${OPERATOR_CHAT_ID:-}" ]]; then
      openclaw message send --channel telegram --target "$OPERATOR_CHAT_ID" \
        --message "Quality gate HOLD: closeout artifact '$key' could not reach $ZHC_QUALITY_MIN/10 after $ZHC_QUALITY_MAX_ATTEMPTS attempts. NOT delivered. State: $STATE_FILE" >/dev/null 2>&1 || true
    fi
  fi
  return 0
}

# Defaults so referencing an unset step does not trip set -u.
STEP_INF1_STATUS=skipped
STEP_INF2_STATUS=skipped
STEP_VISUAL_STATUS=skipped
STEP_VIDEO_STATUS=skipped
STEP_NOTION_STATUS=skipped
STEP_TELEGRAM_STATUS=skipped
GATE_INF1_RESULT=held
GATE_INF2_RESULT=held
GATE_NOTION_RESULT=held

# ----------------------------------------------------------------------
# STEP 2.0 -- Visual Intelligence Set (PRD step 3, v12.6.0)
# Generates the full set of 3-30 images using generate-visual-intelligence.sh.
# Writes .visualIntelligenceUrls (array) + .infographic1Url + .infographic2Url
# (backward compat). If already populated (>= 3 URLs), skips.
# This step REPLACES the old separate infographic-1 / infographic-2 steps as
# the primary generation path. The individual steps 2 and 3 still run as
# a fallback safety net for the specific QC-gated org-chart assertion.
# ----------------------------------------------------------------------
VISUAL_INTEL_SCRIPT="$SKILL_DIR/scripts/generate-visual-intelligence.sh"
existing_vi_count=$(state_get '.visualIntelligenceUrls | length' 2>/dev/null || echo "0")
[[ -z "$existing_vi_count" || "$existing_vi_count" == "null" ]] && existing_vi_count=0
if [[ "$existing_vi_count" -ge 3 ]]; then
  log "INFO" "step=2.0 visual-intelligence: already has $existing_vi_count images -- skipping"
  STEP_VISUAL_STATUS=ok
elif [[ -x "$VISUAL_INTEL_SCRIPT" || -f "$VISUAL_INTEL_SCRIPT" ]]; then
  log "INFO" "step=2.0 visual-intelligence: generating image set"
  if bash "$VISUAL_INTEL_SCRIPT" 2>>"$LOG_FILE"; then
    STEP_VISUAL_STATUS=ok
    log "INFO" "step=2.0 visual-intelligence: complete"
  else
    STEP_VISUAL_STATUS=failed
    log "WARN" "step=2.0 visual-intelligence: failed (non-critical -- individual infographic steps will run as fallback)"
  fi
else
  log "WARN" "step=2.0 visual-intelligence: generate-visual-intelligence.sh not found -- falling back to individual infographic steps"
  STEP_VISUAL_STATUS=skipped
fi

# Write set-level deliverable to state
if [[ "$STEP_VISUAL_STATUS" == "ok" ]]; then
  vi_urls=$(state_get '.visualIntelligenceUrls')
  state_set ".closeoutDeliverables.visualIntelligenceUrls = $vi_urls" 2>/dev/null || true
fi

# ----------------------------------------------------------------------
# STEP 2 -- Infographic #1 (Workforce Structure)
# PRD-2.8: after the 8.5 quality gate passes, ASSERT the connector-tree
# requirement programmatically via qc-assert-org-chart-connector-tree.sh.
# This is NOT just documentation - it is a hard check.
# ----------------------------------------------------------------------
if [[ -n "$(state_get '.infographic1Url')" && "$(state_get '.infographic1Url')" != "null" && "$(gate_get_score org_chart)" != "" ]] && rate_meets_gate "$(gate_get_score org_chart)" && [[ "$(gate_get_qc org_chart)" == "pass" ]]; then
  log "INFO" "step=2 infographic-1: already done + gate-passed -- skipping"
  STEP_INF1_STATUS=ok
  GATE_INF1_RESULT=pass
else
  # RATE + QC + 8.5 GATE: generate the org chart, then the agent must self-rate
  # it 1-10 against the Org Chart rubric in QUALITY-GATE.md (visible connector
  # lines / true reporting tree is the #1 requirement) and QC it. Loops until
  # >= ZHC_QUALITY_MIN or HOLDS for human review. Below 8.5 is never delivered.
  generate_rate_gate org_chart INF1 "$SKILL_DIR/scripts/generate-infographics.sh" structure
fi

# PRD-2.8: ORG-CHART CONNECTOR-TREE ASSERTION (runs AFTER gate passes).
# The 8.5 gate alone is agent-self-rated. This is a PROGRAMMATIC assertion
# that the rendered HTML actually has connector lines (not a card grid).
# On failure: regenerate (clear gate score so the loop re-runs) then re-assert.
# If assertion still fails after ZHC_QUALITY_MAX_ATTEMPTS, HOLD the artifact.
if [[ "$GATE_INF1_RESULT" == "pass" ]]; then
  # ZHC_ORGCHART_QC_SCRIPT env override allows test harnesses to inject a stub.
  ORG_CHART_QC_SCRIPT="${ZHC_ORGCHART_QC_SCRIPT:-${SKILL_DIR}/scripts/qc-assert-org-chart-connector-tree.sh}"
  if [[ -x "$ORG_CHART_QC_SCRIPT" || -f "$ORG_CHART_QC_SCRIPT" ]]; then
    log "INFO" "step=2 org-chart connector-tree assertion (PRD-2.8)"
    ct_rc=0
    bash "$ORG_CHART_QC_SCRIPT" >>"$LOG_FILE" 2>&1 || ct_rc=$?
    if [[ "$ct_rc" -eq 0 ]]; then
      log "INFO" "step=2 org-chart connector-tree ASSERTED (pass)"
    elif [[ "$ct_rc" -eq 3 ]]; then
      # PRD-2.15 (v12.3.12): rc=3 means NO artifact (no HTML/PNG rendered - Playwright crash,
      # missing Chromium, or fresh-VPS). This is NOT inconclusive - it is a HARD operator-visible
      # HOLD. The prior "proceed on agent rating" was the exact silent failure mode that let Beverly
      # get a green while Playwright had never run. Changed from WARN+proceed to ERROR+escalate.
      _inf1_fail_reason="playwright-rc3: org-chart renderer returned no HTML/PNG artifact (Playwright crash or Chromium missing on this host)"
      log "ERROR" "step=2 org-chart rc=3 - NO artifact rendered. Classifying as HARD HOLD (not inconclusive). Reason: $_inf1_fail_reason"
      GATE_INF1_RESULT=held
      STEP_INF1_STATUS=failed
      state_set ".infographic1FailureReason = \"$_inf1_fail_reason\"" || true
      state_set ".closeoutLegStatus.org_chart = \"failed:playwright-missing\"" || true
      # Write closeoutBlockers entry
      _TS_INF=$(now_iso)
      state_set "
        .closeoutBlockers = (
          (.closeoutBlockers // [])
          | map(select(.class != \"org-chart-not-rendered\"))
          | . + [{\"class\":\"org-chart-not-rendered\",\"reason\":\"$_inf1_fail_reason\",\"since\":\"$_TS_INF\",\"escalatedAt\":\"$_TS_INF\",\"cleared\":false}]
        )
      " || true
      # Operator escalation
      _OP_CHAT="${OPERATOR_TELEGRAM_CHAT_ID:-5252140759}"
      if command -v openclaw >/dev/null 2>&1 && [[ "${ZHC_SKIP_TG_PREFLIGHT:-0}" != "1" ]]; then
        openclaw message send --channel telegram -t "$_OP_CHAT" \
          -m "🚨 ZHC HOLD [org-chart-not-rendered] $(state_get '.companyName'): org-chart Playwright returned rc=3 (no artifact). Install Chromium or use ZHC_ORGCHART_FALLBACK=1. State: $STATE_FILE" \
          >>"$LOG_FILE" 2>&1 || true
      fi
    else
      log "ERROR" "step=2 org-chart connector-tree ASSERTION FAILED (rc=$ct_rc) -- card-grid anti-pattern detected. Clearing gate score so generate_rate_gate regenerates."
      # Clear the gate score to force a regeneration attempt
      state_set "del(.qualityRatings.org_chart)" || true
      GATE_INF1_RESULT=held
      STEP_INF1_STATUS=failed
      # Attempt one more regeneration cycle
      log "INFO" "step=2 re-running generate_rate_gate after connector-tree failure"
      generate_rate_gate org_chart INF1 "$SKILL_DIR/scripts/generate-infographics.sh" structure
      if [[ "$GATE_INF1_RESULT" == "pass" ]]; then
        ct_rc2=0
        bash "$ORG_CHART_QC_SCRIPT" >>"$LOG_FILE" 2>&1 || ct_rc2=$?
        if [[ "$ct_rc2" -eq 0 ]]; then
          log "INFO" "step=2 org-chart connector-tree ASSERTED on second attempt (pass)"
        else
          log "ERROR" "step=2 org-chart connector-tree still FAILS after second attempt -- HOLDING artifact for human review"
          GATE_INF1_RESULT=held
          state_set ".qualityHeld = ((.qualityHeld // []) + [\"org_chart_connector_tree\"] | unique)" || true
        fi
      fi
    fi
  else
    log "WARN" "step=2 qc-assert-org-chart-connector-tree.sh not found at $ORG_CHART_QC_SCRIPT -- connector-tree check skipped (install may be stale)"
  fi
fi

# PRD-2.8: write closeoutDeliverables.infographic1Url when this step passes
if [[ "$GATE_INF1_RESULT" == "pass" ]]; then
  inf1_url=$(state_get '.infographic1Url')
  state_set ".closeoutDeliverables.infographic1Url = \"$inf1_url\"" || true
fi

# ----------------------------------------------------------------------
# STEP 3 -- Infographic #2 (How Work Flows)
# ----------------------------------------------------------------------
if [[ -n "$(state_get '.infographic2Url')" && "$(state_get '.infographic2Url')" != "null" && "$(gate_get_score flow_diagram)" != "" ]] && rate_meets_gate "$(gate_get_score flow_diagram)" && [[ "$(gate_get_qc flow_diagram)" == "pass" ]]; then
  log "INFO" "step=3 infographic-2: already done + gate-passed -- skipping"
  STEP_INF2_STATUS=ok
  GATE_INF2_RESULT=pass
else
  # RATE + QC + 8.5 GATE: generate the flow diagram, then the agent must
  # self-rate it 1-10 against the Flow Diagram rubric in QUALITY-GATE.md
  # (industry-specific imagery, no gift box, branded) and QC it. Loops until
  # >= ZHC_QUALITY_MIN or HOLDS for human review. Below 8.5 is never delivered.
  generate_rate_gate flow_diagram INF2 "$SKILL_DIR/scripts/generate-infographics.sh" workflow
fi

# PRD-2.8: write closeoutDeliverables.infographic2Url when step passes
if [[ "$GATE_INF2_RESULT" == "pass" ]]; then
  inf2_url=$(state_get '.infographic2Url')
  state_set ".closeoutDeliverables.infographic2Url = \"$inf2_url\"" || true
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

# PRD-2.8: write closeoutDeliverables.celebrationVideoUrl when step succeeds
if [[ "$STEP_VIDEO_STATUS" == "ok" ]]; then
  video_url=$(state_get '.ghlVideoPublicUrl // .celebrationVideoUrl')
  state_set ".closeoutDeliverables.celebrationVideoUrl = \"$video_url\"" || true
fi

# ----------------------------------------------------------------------
# STEP 5 -- Notion Page Tree
# ----------------------------------------------------------------------
if [[ -n "$(state_get '.notionRootPageUrl')" && "$(state_get '.notionRootPageUrl')" != "null" && "$(gate_get_score closeout_docs)" != "" ]] && rate_meets_gate "$(gate_get_score closeout_docs)" && [[ "$(gate_get_qc closeout_docs)" == "pass" ]]; then
  log "INFO" "step=5 notion: already done + gate-passed -- skipping"
  STEP_NOTION_STATUS=ok
  GATE_NOTION_RESULT=pass
else
  # RATE + QC + 8.5 GATE: build the Notion closeout doc, then the agent must
  # self-rate it 1-10 against the Docs rubric in QUALITY-GATE.md (all 9 doctrine
  # sections, real client-specific content, no placeholders, DMAIC applied to
  # this client, AND every canonical + custom department represented -- cross-
  # checked against departments.json / build-state canonicalReconciliation) and
  # QC it. Loops until >= ZHC_QUALITY_MIN or HOLDS for human review. Below 8.5
  # is never delivered.
  generate_rate_gate closeout_docs NOTION "$SKILL_DIR/scripts/create-notion-closeout.sh"
fi

# PRD-2.8: write closeoutDeliverables.notionTreeUrl when notion step passes
if [[ "$GATE_NOTION_RESULT" == "pass" ]]; then
  notion_url=$(state_get '.notionRootPageUrl')
  state_set ".closeoutDeliverables.notionTreeUrl = \"$notion_url\"" || true
fi

# ----------------------------------------------------------------------
# STEP 5.5 -- GHL media-library upload (conditional) -- v10.x
#
# Moved BEFORE the Telegram step (v10.x) so the shareable media-library link is
# in state (.ghlMediaLibraryUrl) when the celebration messages are composed.
# Uploads the gate-passed closeout media (real local files only) to the client's
# Convert and Flow / GHL media library. Skips gracefully when GHL is absent or
# the LOCATION PIT does not verify. Never blocks closeout.
# ----------------------------------------------------------------------
if [[ -x "$SKILL_DIR/scripts/upload-ghl-media.sh" ]]; then
  bash "$SKILL_DIR/scripts/upload-ghl-media.sh" || log "WARN" "ghl-media upload step returned non-zero (non-fatal)"
fi

# ----------------------------------------------------------------------
# STEP 6 -- Telegram Delivery
#
# Exports ZHC_VIDEO_STATUS to send-telegram-celebration.sh so slot 4 can
# substitute a text-only "video deferred" message when the video step failed.
# ----------------------------------------------------------------------
export ZHC_VIDEO_STATUS="$STEP_VIDEO_STATUS"
# v10.x: expose the GHL media-library shareable link to the Telegram step so it
# can include it in the closeout message sequence.
export ZHC_GHL_MEDIA_URL="$(state_get '.ghlMediaLibraryUrl')"
# 8.5 GATE enforcement on delivery: any artifact that did not clear the gate is
# HELD and must NOT be delivered to the client. Export the per-artifact gate
# results + the held list so the Telegram step skips held artifacts (it sends a
# "being finalized" placeholder for a held item instead of shipping subpar work).
export ZHC_GATE_ORG_CHART="$GATE_INF1_RESULT"
export ZHC_GATE_FLOW_DIAGRAM="$GATE_INF2_RESULT"
export ZHC_GATE_CLOSEOUT_DOCS="$GATE_NOTION_RESULT"
export ZHC_QUALITY_HELD="$(state_get '.qualityHeld | join(",")')"
if [[ -n "$ZHC_QUALITY_HELD" ]]; then
  log "WARN" "delivery: artifacts HELD by quality gate (not delivered): $ZHC_QUALITY_HELD"
fi
run_step TELEGRAM "$SKILL_DIR/scripts/send-telegram-celebration.sh"

# PRD-2.8: write closeoutDeliverables.telegramSequenceSent and ccUrlDelivered
# after the Telegram step. These are written here (not in send-telegram-celebration.sh)
# so the single-source-of-truth state writes stay in run-closeout.sh.
if [[ "$STEP_TELEGRAM_STATUS" == "ok" ]]; then
  cc_url_state=$(state_get '.commandCenterUrl')
  cc_delivered="false"
  [[ -n "$cc_url_state" && "$cc_url_state" != "null" ]] && cc_delivered="true"
  state_set \
    ".closeoutDeliverables.telegramSequenceSent = true | .closeoutDeliverables.ccUrlDelivered = $cc_delivered" || true
fi

# PRD-FINAL-PACKAGE (v12.6.0) STANDING RULE:
# When a client's Command Center link exists, write that CC link into the
# client's AGENTS.md + TOOLS.md so every agent knows the CC URL.
_cc_url_for_write=$(state_get '.commandCenterUrl')
if [[ -n "$_cc_url_for_write" && "$_cc_url_for_write" != "null" && "$_cc_url_for_write" =~ ^https?:// ]]; then
  _agent_dir="${OC_ROOT}/agents/main"
  if [[ -d "$_agent_dir" ]]; then
    for _core_file in "$_agent_dir/AGENTS.md" "$_agent_dir/TOOLS.md"; do
      if [[ -f "$_core_file" ]]; then
        # Only write if CC URL is not already present in the file
        if ! grep -qF "$_cc_url_for_write" "$_core_file" 2>/dev/null; then
          _cc_block="
## Command Center
URL: $_cc_url_for_write
This is the client's live Command Center dashboard. Use this URL when the owner asks
for their dashboard link, when confirming closeout delivery, or when directing them
to check task status. Written by run-closeout.sh at closeout time.
"
          printf '%s\n' "$_cc_block" >> "$_core_file"
          log "INFO" "wrote commandCenterUrl to $_core_file (standing rule: CC link in AGENTS.md + TOOLS.md)"
        else
          log "INFO" "commandCenterUrl already in $_core_file -- skipping write"
        fi
      fi
    done
  else
    log "WARN" "agent dir $_agent_dir not found -- cannot write CC URL to AGENTS.md / TOOLS.md"
  fi
fi

# ----------------------------------------------------------------------
# STEP 6.5 -- n8n wire-up (PRD-2.8, optional, non-blocking)
# Notifies the client's n8n webhook that the ZHC build + closeout is complete.
# Runs AFTER Telegram delivery (the owner has their celebration already; n8n is
# operator plumbing). Failure marks .n8nStatus = "failed" (soft) and moves on.
# ----------------------------------------------------------------------
STEP_N8N_STATUS=skipped
N8N_WIRE_SCRIPT="$SKILL_DIR/scripts/wire-n8n-closeout.sh"
if [[ -f "$N8N_WIRE_SCRIPT" ]]; then
  run_step N8N "$N8N_WIRE_SCRIPT"
  STEP_N8N_STATUS="${STEP_N8N_STATUS:-skipped}"
fi

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
[[ "${STEP_N8N_STATUS:-skipped}" == "failed" ]] && soft_failed+=("n8n")
# Visual intelligence set failure is soft -- the individual infographics serve as fallback
[[ "$STEP_VISUAL_STATUS"   == "failed" ]] && soft_failed+=("visual-intelligence-set")

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

  # Count ONLY messages that carry a real (non-empty) messageId -- a bare slot
  # record with status:"send-failed" must not satisfy the guard.
  delivered_count=$(state_get '(.messagesDelivered // []) | map(select((.messageId // "") | tostring | length > 0)) | length')
  if [[ -z "$delivered_count" || "$delivered_count" == "null" || "$delivered_count" == "0" ]]; then
    guard_reasons+=("telegram-no-messages-delivered")
  fi

  if (( ${#guard_reasons[@]} > 0 )); then
    greason="phantom-closeout-guard: $(IFS=,; echo "${guard_reasons[*]}")"
    state_set ".closeoutStatus = \"partial\" | .closeoutPartialReason = \"$greason\" | .closeoutCompletedAt = \"$(now_iso)\""
    log "WARN" "closeout finalize: guard blocked done -- $greason"
    exit 0
  fi

  # ------------------------------------------------------------------
  # TELEGRAM DELIVERY CONFIRMATION GATE (anti-faking, the load-bearing layer).
  #
  # The phantom guard above only proves we *recorded* messageIds. It does NOT
  # prove the gateway actually delivered them -- `openclaw message send` can
  # exit 0 (and even hand back a messageId) while the message never reaches
  # Telegram (silent offset-corruption; fresh-VPS "scope upgrade pending
  # approval"). So before we may write closeoutStatus=done, cross-check every
  # required captured messageId against the gateway sent-registry via
  # verify-telegram-delivery.sh. If ANY required id is missing-and-recent (or a
  # required slot never produced an id), this FAILS the closeout with a
  # telegram-unconfirmed reason and the recurring resume cron retries -- we
  # never claim done on an unconfirmed delivery.
  # ------------------------------------------------------------------
  VERIFY_TG="$SKILL_DIR/scripts/verify-telegram-delivery.sh"
  if [[ -x "$VERIFY_TG" || -f "$VERIFY_TG" ]]; then
    if bash "$VERIFY_TG" >>"$LOG_FILE" 2>&1; then
      log "INFO" "closeout finalize: telegram delivery CONFIRMED against sent-registry"
    else
      tg_rc=$?
      # Pull the first unconfirmed slot for a precise reason string.
      bad_slot=$(state_get '.telegramDeliveryVerification.results | map(select(.required == true and (.verdict | startswith("fail")))) | (.[0].n // "?")')
      reason="telegram-unconfirmed: msg ${bad_slot} (verify rc=$tg_rc; messageId not present in gateway sent-registry)"
      state_set ".closeoutStatus = \"failed\" | .closeoutFailureReason = \"$reason\" | .closeoutCompletedAt = \"$(now_iso)\""
      log "ERROR" "closeout finalize: $reason -- resume cron will retry (never-stop)"
      exit 1
    fi
  else
    log "WARN" "closeout finalize: verify-telegram-delivery.sh not found at $VERIFY_TG -- cannot confirm delivery against registry; refusing to claim done"
    state_set ".closeoutStatus = \"failed\" | .closeoutFailureReason = \"telegram-unconfirmed: verifier missing\" | .closeoutCompletedAt = \"$(now_iso)\""
    exit 1
  fi

  # NOTE (v10.x): the GHL media-library upload now runs at STEP 5.5 (BEFORE the
  # Telegram step) so the shareable .ghlMediaLibraryUrl is in state in time to be
  # included in the client's celebration messages. It is no longer invoked here.

  # ------------------------------------------------------------------
  # Operator success summary -- v10.x.
  # Sends Trevor a single Telegram message (via the OpenClaw gateway) with LINKS
  # to every delivered artifact: dashboard, both infographics, celebration video,
  # Notion closeout page (+ Drive/GHL where present). Idempotent.
  # ------------------------------------------------------------------
  ZHC_OPERATOR_CHAT_ID="${ZHC_OPERATOR_CHAT_ID:-5252140759}"
  export ZHC_OPERATOR_CHAT_ID
  if [[ -x "$SKILL_DIR/scripts/send-operator-summary.sh" ]]; then
    bash "$SKILL_DIR/scripts/send-operator-summary.sh" || log "WARN" "operator-summary step returned non-zero (non-fatal)"
  fi

  # PRD-2.8: write any remaining closeoutDeliverables leg flags before done.
  # telegramSequenceSent and ccUrlDelivered were written in Step 6 above.
  # Ensure all fields are set. n8nWired is already set by wire-n8n-closeout.sh.
  final_n8n=$(state_get '.closeoutDeliverables.n8nWired // empty')
  if [[ -z "$final_n8n" || "$final_n8n" == "null" ]]; then
    # n8n was skipped (no N8N_WEBHOOK_URL) but field must be explicit
    state_set '.closeoutDeliverables.n8nWired = "skipped"' || true
  fi

  # PRD-2.8: SELF-REMOVE the dedicated closeout-resume cron (kill condition met).
  resume_cron_uuid=$(state_get '.closeoutResumeUuid')
  if [[ -n "$resume_cron_uuid" && "$resume_cron_uuid" != "null" ]] && command -v openclaw >/dev/null 2>&1; then
    log "INFO" "self-removing closeout-resume cron $resume_cron_uuid (loop-registry kill condition: done)"
    openclaw cron rm "$resume_cron_uuid" 2>>"$LOG_FILE" || log "WARN" "closeout-resume cron rm failed (tolerated)"
    state_set 'del(.closeoutResumeUuid) | .closeoutResumeRegisteredAt = null' || true
  fi

  # v12.3.10: SELF-REMOVE the interview-nudge cron (interviewComplete=true kill condition).
  # Primary: keyed on .interviewNudgeUuid recorded at install time.
  # Fallback: name-scan for boxes installed before UUID recording (e.g. Talaya).
  nudge_cron_uuid=$(state_get '.interviewNudgeUuid')
  if [[ -n "$nudge_cron_uuid" && "$nudge_cron_uuid" != "null" ]] && command -v openclaw >/dev/null 2>&1; then
    log "INFO" "self-removing interview-nudge cron $nudge_cron_uuid (interviewComplete=true, closeout done)"
    openclaw cron rm "$nudge_cron_uuid" 2>>"$LOG_FILE" || log "WARN" "interview-nudge cron rm failed (tolerated)"
    state_set 'del(.interviewNudgeUuid) | .interviewNudgeRegisteredAt = null' || true
  fi
  # Fallback scan: remove any interview-nudge cron registered without a recorded UUID
  if command -v openclaw >/dev/null 2>&1; then
    scan_uuid=$(openclaw cron list 2>/dev/null \
      | awk '/interview-nudge/ { for (i=1;i<=NF;i++) if ($i ~ /^[0-9a-fA-F-]{8,}$/) { print $i; exit } }' \
      | head -1 || true)
    if [[ -n "$scan_uuid" ]]; then
      log "INFO" "fallback-scan removing interview-nudge cron $scan_uuid (no recorded UUID)"
      openclaw cron rm "$scan_uuid" 2>>"$LOG_FILE" || log "WARN" "fallback interview-nudge cron rm failed (tolerated)"
    fi
  fi
  # Loop-registry hygiene
  if [[ -f "$SKILL_DIR/../scripts/loop-registry.sh" ]]; then
    LOOP_REGISTRY_FILE="$(dirname "$LOG_FILE")/.loop-registry.json" \
    # shellcheck disable=SC1090
    source "$SKILL_DIR/../scripts/loop-registry.sh" 2>/dev/null || true
    LOOP_REGISTRY_FILE="$(dirname "$LOG_FILE")/.loop-registry.json" \
    lr_kill "interview-nudge" 2>/dev/null || true
  fi

  state_set ".closeoutStatus = \"done\" | .closeoutCompletedAt = \"$(now_iso)\""
  log "INFO" "closeout complete -- closeoutStatus=done (PRD-2.8: all 7 closeoutDeliverables legs written, resume cron removed)"
  exit 0
fi
