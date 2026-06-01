#!/usr/bin/env bash
# resume-workforce-build.sh — autonomous resume layer for Skill 23 builds
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
# v10.14.36 — defense-in-depth max-runs cap.
# After 24 fires (6h at 15-min intervals) the cron auto-removes itself
# regardless of state. A workforce build that hasn't completed in 6 hours
# is stuck; the cron is no longer useful, kill it.
MAX_RUNS_BEFORE_SELF_REMOVE=24

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG_FILE"
}

# Remote Rescue v1 — resolve the operator's Telegram chat ID for escalations.
# Lookup order: env.vars.OPERATOR_TELEGRAM_CHAT_ID -> $OPERATOR_TELEGRAM_CHAT_ID
# -> $OPENCLAW_TREVOR_CHAT (legacy) -> hardcoded 5252140759 (Trevor default).
resolve_operator_chat_id() {
  local v=""
  if command -v openclaw >/dev/null 2>&1; then
    v="$(openclaw config get env.vars.OPERATOR_TELEGRAM_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
    case "$v" in
      ""|*"not found"*|*"Error"*) v="" ;;
    esac
  fi
  if [[ -z "$v" && -n "${OPERATOR_TELEGRAM_CHAT_ID:-}" ]]; then
    v="$OPERATOR_TELEGRAM_CHAT_ID"
  fi
  if [[ -z "$v" && -n "${OPENCLAW_TREVOR_CHAT:-}" ]]; then
    v="$OPENCLAW_TREVOR_CHAT"
  fi
  if [[ -z "$v" ]]; then
    v="5252140759"
  fi
  printf '%s' "$v"
}

# v10.14.36 — locate this cron's UUID by name so we can self-remove.
# OpenClaw doesn't pass a CRON_UUID env var, so we resolve by --name.
# Returns empty string if openclaw CLI is unavailable or the cron isn't listed.
find_self_cron_uuid() {
  command -v openclaw >/dev/null 2>&1 || { echo ""; return 0; }
  openclaw cron list 2>/dev/null \
    | awk '/workforce-build-resume/ { for (i=1;i<=NF;i++) if ($i ~ /^[0-9a-fA-F-]{8,}$/) { print $i; exit } }' \
    | head -1
}

# v10.14.36 — self-remove the workforce-build-resume cron. Tolerates missing
# UUID/CLI; logs whatever it can. Never errors out the script.
self_remove_cron() {
  local reason="$1"
  local uuid
  uuid=$(find_self_cron_uuid)
  if [[ -z "$uuid" ]]; then
    log "self_remove_cron($reason): could not resolve workforce-build-resume UUID — leaving cron in place"
    return 0
  fi
  log "self_remove_cron($reason): removing cron $uuid"
  if openclaw cron rm "$uuid" 2>>"$LOG_FILE"; then
    log "self_remove_cron($reason): removed $uuid"
    rm -f "$RUN_COUNT_FILE" 2>/dev/null || true
  else
    log "self_remove_cron($reason): openclaw cron rm $uuid FAILED — see errors above"
  fi
}

# ---- v10.14.36: BELT — explicit self-stop on terminal state ----
# v10.15.26 / v10.16.25 HARD FLOOR: a terminal state in the build-state JSON
# (status=done / closeoutStatus=done|sent) is NO LONGER trusted as proof on its
# own. A hand-seeded build-state (Cassandra's 3-dept fiction) used to flip the
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
        log "BELT: terminal JSON state (build_status=$_build_status, closeout=$_closeout_status) but DEPARTMENT FLOOR NOT MET on disk (department-floor.py rc=3). REFUSING to self-remove — a seeded/reduced build-state will not end the build. Driving the floor instead."
      fi
    fi
    if (( _allow_remove == 1 )); then
      log "BELT: terminal state detected + floor satisfied (build_status=$_build_status, closeout=$_closeout_status, completed=$_build_completed_at) — removing self-cron and exiting"
      self_remove_cron "terminal-state"
      exit 0
    fi
  fi
fi

# ---- v10.15.18: NEVER-STOP run accounting (Rule 8) ----
# PRIOR BEHAVIOR (v10.14.36): after MAX_RUNS_BEFORE_SELF_REMOVE the cron
# auto-REMOVED itself — a stall trap that let a half-built workforce sit forever
# while the client never found out. Rule 8 forbids stopping: the only legitimate
# terminal state is a REAL completion (build done + closeout confirmed), which is
# handled by the BELT terminal-state check above (self_remove_cron). When we
# instead just hit the run cap WITHOUT completing, we ESCALATE to Rescue Rangers
# (once) and KEEP RETRYING in a slow-backoff posture — we never self-remove on a
# run count.
mkdir -p "$(dirname "$RUN_COUNT_FILE")" 2>/dev/null || true
_run_count=0
if [[ -f "$RUN_COUNT_FILE" ]]; then
  _run_count=$(cat "$RUN_COUNT_FILE" 2>/dev/null | tr -dc '0-9' | head -c 6)
  [[ -z "$_run_count" ]] && _run_count=0
fi
_run_count=$((_run_count + 1))
echo "$_run_count" > "$RUN_COUNT_FILE" 2>/dev/null || true
if (( _run_count > MAX_RUNS_BEFORE_SELF_REMOVE )); then
  # Backoff: only ACT every Nth fire past the cap so we slow down (preserving
  # tokens / avoiding 429 churn) but NEVER stop. With a */15 cron, acting every
  # 8th fire ≈ once every 2 hours (the spec's 2h-backoff-retry).
  _over=$(( _run_count - MAX_RUNS_BEFORE_SELF_REMOVE ))
  if (( _over % 8 != 1 )); then
    log "NEVER-STOP: run #$_run_count past cap ($MAX_RUNS_BEFORE_SELF_REMOVE) — in 2h-backoff slow mode, skipping this fire (will act on the next 2h boundary). NOT self-removing."
    exit 0
  fi
  log "NEVER-STOP: run #$_run_count past cap — slow-retry fire. Escalating to Rescue Rangers (once) and continuing; will NOT self-remove on run count."
  if command -v openclaw >/dev/null 2>&1; then
    _already_escalated=$(jq -r '.rescueRangersEscalated // false' "$STATE_FILE" 2>/dev/null)
    if [[ "$_already_escalated" != "true" ]]; then
      _rr_chat="${RESCUE_RANGERS_HELP_CHAT_ID:-}"
      if [[ -n "$_rr_chat" ]]; then
        openclaw message send --channel telegram -t "$_rr_chat" \
          -m "🆘 [Rescue Rangers] workforce-build-resume on $(hostname) has run $_run_count times without reaching a real completion. roleLibraryStatus=${role_library_status:-unset}, sopLibraryStatus=${sop_library_status:-unset}. Now in 2h-backoff slow-retry (NOT stopped — Rule 8). Run scripts/verify-zhc-standard.sh + verify-library-gate.sh on the box. State: $STATE_FILE" 2>>"$LOG_FILE" || true
      fi
      _operator_chat="$(resolve_operator_chat_id)"
      if [[ -n "$_operator_chat" ]]; then
        openclaw message send --channel telegram -t "$_operator_chat" \
          -m "⚠️ workforce-build-resume on $(hostname) hit $_run_count runs without completing — escalated to Rescue Rangers and switched to 2h-backoff slow-retry. It will KEEP retrying until libraries + closeout are real (it does NOT stop). State: $STATE_FILE" 2>>"$LOG_FILE" || true
      fi
      _tmp_esc=$(mktemp)
      jq '.rescueRangersEscalated = true' "$STATE_FILE" > "$_tmp_esc" 2>/dev/null && mv "$_tmp_esc" "$STATE_FILE" || rm -f "$_tmp_esc"
    fi
  fi
  # fall through and keep working — do NOT self_remove_cron on a run count
fi

# ---- v10.14.20: heal config before any gateway interaction ----
if command -v openclaw >/dev/null 2>&1; then
  openclaw doctor --fix >/dev/null 2>&1 || true
fi

# ---- preconditions ----
if [[ ! -f "$STATE_FILE" ]]; then
  log "no state file at $STATE_FILE — nothing to resume; exiting clean"
  exit 0
fi

if ! command -v jq >/dev/null 2>&1; then
  log "jq not installed — cannot parse state; exiting"
  exit 0
fi

if ! command -v openclaw >/dev/null 2>&1; then
  log "openclaw CLI not on PATH — cannot dispatch resume; exiting"
  exit 0
fi

# ---- lock (prevent concurrent self-pings) ----
if [[ -f "$LOCK_FILE" ]]; then
  lock_mtime=$(stat -c %Y "$LOCK_FILE" 2>/dev/null || stat -f %m "$LOCK_FILE" 2>/dev/null || echo 0)
  now=$(date +%s)
  lock_age=$(( now - lock_mtime ))
  if (( lock_age < 600 )); then
    log "lock held for ${lock_age}s (< 600s) — another resume in flight; exiting"
    exit 0
  fi
  log "stale lock (age ${lock_age}s) — clearing"
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# ---- read state ----
interview_complete=$(jq -r '.interviewComplete // false' "$STATE_FILE")
if [[ "$interview_complete" != "true" ]]; then
  log "interview not yet complete — nothing to resume"
  exit 0
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
# are done (no pending/stale) and BEFORE closeout owns the rest — the gate runs
# before the closeout gate. Last-night incident (Kofi/Teresa/Evelyn/Maria/Lyric).
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

total_attention=$(( pending_count + stale_building_count + library_dirty + comms_automation_dirty + closeout_dirty ))
if (( total_attention == 0 )); then
  done_count=$(jq -r '[.departments[] | select(.status == "done")] | length' "$STATE_FILE")
  total_count=$(jq -r '.departments | length' "$STATE_FILE")
  if (( done_count == total_count )) && (( total_count > 0 )); then
    log "ALL ${total_count} departments done + libraries done (role=$role_library_status sop=$sop_library_status) + comms-automations terminal (status=$comms_automation_status) + closeout terminal (status=$closeout_status) — nothing to do"
  else
    log "no pending/stale departments, comms-automations clean (status=$comms_automation_status), closeout clean (pending=$pending_count, stale=$stale_building_count, closeout=$closeout_status) — nothing to do"
  fi
  exit 0
fi

# ---- attempt cap (v10.15.18: escalate-and-CONTINUE, never hard-stop) ----
# PRIOR BEHAVIOR: at maxResumeAttempts the cron bailed and stopped self-pinging
# (exit 0, never to retry) — a half-built workforce then sat forever and the
# client never found out. Rule 8: NEVER STOP. We now escalate to the operator +
# Rescue Rangers ONCE at the cap, then KEEP RETRYING in slow-backoff. The cron
# only stops on a REAL terminal state (handled by the BELT check above).
attempts=$(jq -r '.resumeAttempts // 0' "$STATE_FILE")
max_attempts=$(jq -r ".maxResumeAttempts // $MAX_ATTEMPTS_DEFAULT" "$STATE_FILE")
if (( attempts >= max_attempts )); then
  _cap_already=$(jq -r '.resumeCapEscalated // false' "$STATE_FILE")
  if [[ "$_cap_already" != "true" ]]; then
    log "resumeAttempts ($attempts) >= maxResumeAttempts ($max_attempts) — escalating (operator + Rescue Rangers) and switching to slow-retry. NOT stopping (Rule 8)."
    _operator_chat="$(resolve_operator_chat_id)"
    _lib_note=""
    if (( library_dirty == 1 )); then
      _lib_note=" LIBRARIES NOT done (roleLibraryStatus=${role_library_status}, sopLibraryStatus=${sop_library_status}) — the role-library pull / SOP authoring keeps failing; run scripts/verify-library-gate.sh on $(hostname)."
    fi
    if [[ -n "$_operator_chat" ]]; then
      openclaw message send --channel telegram -t "$_operator_chat" \
        -m "⚠️ Workforce build slow: ${pending_count} pending, ${stale_building_count} stale after ${attempts} resume attempts.${_lib_note} Now in slow-retry (it does NOT stop). State: $STATE_FILE" 2>>"$LOG_FILE" || true
    fi
    _rr_chat="${RESCUE_RANGERS_HELP_CHAT_ID:-}"
    if [[ -n "$_rr_chat" ]]; then
      openclaw message send --channel telegram -t "$_rr_chat" \
        -m "🆘 [Rescue Rangers] workforce build on $(hostname) past ${attempts} resume attempts without completing.${_lib_note} Now slow-retrying (Rule 8 never-stop). Run scripts/verify-zhc-standard.sh on the box. State: $STATE_FILE" 2>>"$LOG_FILE" || true
    fi
    _tmp_cap=$(mktemp)
    jq '.resumeCapEscalated = true' "$STATE_FILE" > "$_tmp_cap" 2>/dev/null && mv "$_tmp_cap" "$STATE_FILE" || rm -f "$_tmp_cap"
  fi
  # Slow-backoff past the cap: act roughly every 2h (every 8th */15 fire) but
  # NEVER stop. The MAX_RUNS slow-mode above already throttles the overall cron;
  # here we just avoid spamming a self-ping every 15 min once we're past the cap.
  _attempts_over=$(( attempts - max_attempts ))
  if (( _attempts_over % 8 != 0 )); then
    log "slow-retry: attempt $attempts past cap — backoff skip this fire (will dispatch on the next ~2h boundary)."
    # still bump the counter so backoff advances
    _tmp_a=$(mktemp); jq ".resumeAttempts = $((attempts + 1))" "$STATE_FILE" > "$_tmp_a" && mv "$_tmp_a" "$STATE_FILE"
    exit 0
  fi
  log "slow-retry: attempt $attempts past cap — dispatching a resume self-ping (2h boundary)."
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
    STATUS_LINE="⚠️ Library gate not closing: ${_company:+$_company — }${_agent_name} has all departments done but roleLibraryStatus=${role_library_status} / sopLibraryStatus=${sop_library_status} after ${attempts}/${max_attempts} resume attempts. The role-library pull or SOP authoring keeps failing — it will hit the cap soon and stop retrying. Check scripts/verify-library-gate.sh on $(hostname). State: $STATE_FILE"
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
  log "no usable target chat (ownerChat or operator) — cannot dispatch resume"
  exit 0
fi

if (( library_dirty == 1 )) && (( closeout_dirty == 0 )); then
  msg="[LIBRARY-RESUME] ${agent_name}: every department is built but the ROLE LIBRARY and/or SOP LIBRARY are NOT populated (roleLibraryStatus=${role_library_status:-unset}, sopLibraryStatus=${sop_library_status:-unset}). The workforce is NOT complete until BOTH are done. Run scripts/verify-library-gate.sh to measure; if role library < 100% re-run scripts/post-build-role-workspaces.py (pulls how-to.md from templates/role-library/); if SOPs have stubs re-run scripts/populate-sops-from-manifest.py. Re-run verify-library-gate.sh until it exits 0 (roleLibraryStatus=done AND sopLibraryStatus=done) — ONLY THEN write buildCompletedAt + closeoutStatus=pending. Resume attempt $((attempts + 1)) of $max_attempts. Do NOT message the owner about this — the resume is internal."
elif (( comms_automation_dirty == 1 )); then
  # v10.15.9: cross-skill chain to Skill 38 — fires AFTER libraries are clean.
  # A workforce that built a Communications / Sales / Customer-Support department
  # is NOT fully delivered until Skill 38 has scaffolded the matching comms
  # automations (THE TRINITY: playbook + Build-with-AI prompt + registry row).
  comms_depts=$(jq -r '(.commsAutomationDepartments // []) | join(", ")' "$STATE_FILE")
  msg="[COMMS-AUTOMATION-RESUME] ${agent_name}: all departments + libraries are done, but the comms-automation handoff to Skill 38 is incomplete (commsAutomationStatus=${comms_automation_status}). This workforce built a comms/sales/support department (${comms_depts:-communications/sales/customer-support}) — per the Skill 23 -> Skill 38 cross-skill chain, you MUST scaffold the matching conversational automations. DO THIS: (1) read ~/.openclaw/skills/38-conversational-ai-system/SKILL.md + protocols/conversation-workflows-protocol.md; (2) set commsAutomationStatus=scaffolding; (3) build at MINIMUM the appointment-booking starter via THE TRINITY — communications playbook + its Build-with-AI prompt + a registry row in the client's conversation-workflows/ (plus a pricing/FAQ or lead-followup playbook matching the department that triggered this); (4) run ~/.openclaw/skills/38-conversational-ai-system/scripts/qc-trinity-registry.sh — it must PASS (every registered workflow has its playbook + prompt); (5) ONLY THEN set commsAutomationStatus=done + commsAutomationVerifiedAt in .workforce-build-state.json. Resume attempt $((attempts + 1)) of $max_attempts. Do NOT message the owner about this — this is internal; the owner hears from you via Skill 37 Step 6 only."
elif (( closeout_dirty == 1 )) && (( pending_count == 0 )) && (( stale_building_count == 0 )); then
  msg="[CLOSEOUT-RESUME] ${agent_name}: workforce build is done (buildCompletedAt set) but closeout is incomplete (closeoutStatus=${closeout_status:-unset}). Read /data/.openclaw/skills/37-zhc-closeout/INSTRUCTIONS.md and invoke scripts/run-closeout.sh. The script is idempotent — it picks up from the first un-completed step. Resume attempt $((attempts + 1)) of $max_attempts. Do NOT message the owner about this — the owner only hears from you when Skill 37 Step 6 fires."
else
  msg="[WORKFORCE-RESUME] ${agent_name}: continue the workforce build per the Post-Interview Handoff Protocol in Skill 23. Read .workforce-build-state.json. Pending: ${pending_list:-none}. Stale: ${stale_list:-none}. Closeout status: ${closeout_status:-unset}. Resume attempt $((attempts + 1)) of $max_attempts. Do NOT message the owner about this — the resume is internal. When all departments are done, set closeoutStatus=pending and either invoke ~/.openclaw/skills/37-zhc-closeout/scripts/run-closeout.sh inline OR exit and let the next cron fire pick up the closeout."
fi

log "dispatching resume to chat $TARGET_CHAT (attempt $((attempts + 1))/$max_attempts; pending='$pending_list'; stale='$stale_list'; library_dirty=$library_dirty roleLib='$role_library_status' sopLib='$sop_library_status'; comms_automation_dirty=$comms_automation_dirty comms_automation_status='$comms_automation_status'; closeout_dirty=$closeout_dirty closeout_status='$closeout_status')"
if openclaw message send --channel telegram -t "$TARGET_CHAT" -m "$msg" 2>>"$LOG_FILE"; then
  log "resume dispatch ok"
else
  log "resume dispatch FAILED — see errors above"
fi

exit 0
