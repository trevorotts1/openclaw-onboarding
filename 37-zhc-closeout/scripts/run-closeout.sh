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

# ---- v10.x: ZHC-STANDARD PREFLIGHT (libraries must be REAL on disk) -------
# buildCompletedAt alone is not proof: an agent could have written it while the
# role/SOP libraries are empty/thin. Re-verify the disk substance via Skill 23's
# verify-zhc-standard.sh (the single source of truth) BEFORE generating ANY
# closeout artifact. If the role/SOP library is not substantive, REFUSE to
# close out and let the resume cron re-fire the library build — never deliver a
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
  # rc 4 = role library not done, rc 5 = SOP library not done. Both block closeout.
  if [[ "$ZHC_STD_RC" == "4" || "$ZHC_STD_RC" == "5" ]]; then
    log "ERROR" "ZHC-standard preflight FAILED (rc=$ZHC_STD_RC): role/SOP library not substantive on disk. REFUSING to close out an empty workforce. The resume cron will re-fire the library build."
    state_set ".closeoutStatus = \"blocked-libraries-incomplete\" | .closeoutBlockReason = \"verify-zhc-standard rc=$ZHC_STD_RC (role/SOP library not substantive)\""
    exit 0
  fi
  log "INFO" "ZHC-standard preflight rc=$ZHC_STD_RC (libraries verified substantive enough to close out)"
else
  log "WARN" "verify-zhc-standard.sh not found -- proceeding on buildCompletedAt alone (older Skill 23 bundle)"
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
STEP_VIDEO_STATUS=skipped
STEP_NOTION_STATUS=skipped
STEP_TELEGRAM_STATUS=skipped
GATE_INF1_RESULT=held
GATE_INF2_RESULT=held
GATE_NOTION_RESULT=held

# ----------------------------------------------------------------------
# STEP 2 -- Infographic #1 (Workforce Structure)
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

  state_set ".closeoutStatus = \"done\" | .closeoutCompletedAt = \"$(now_iso)\""
  log "INFO" "closeout complete -- closeoutStatus=done"
  exit 0
fi
