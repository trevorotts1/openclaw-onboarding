#!/usr/bin/env bash
# resume-onboarding.sh — v10.16.0  (NUDGE LIFECYCLE: escalate→dormant→re-arm + credit-backoff)
#
# Autonomous resume layer for SKILL ONBOARDING (the install/wire/QC pipeline),
# modeled on resume-workforce-build.sh. Reads
#   ~/.openclaw/workspace/.onboarding-state.json
# and, while ANY non-archived skill is still pending|downloaded|wired|qc-failed,
# self-pings the agent (via `openclaw message send`) to activate + verify those
# skills. It is the ONLY autonomous-recovery layer for onboarding — without it,
# an interrupted onboarding (or one that an over-eager agent self-declared
# "done") sits forever with un-registered skills.
#
# NEVER-STOP (Rule 8): this cron does NOT exit on a self-declared "done". It
# exits ONLY when the VERIFICATION GATE passes (every skill qc-passed, or an
# explicit interview-pending park). It runs the gate itself (sourcing
# onboarding-state.sh) — it does not trust prose or a hand-flipped flag.
#
# INTERVIEW_PENDING is a LEGITIMATE park, not terminal "done": a skill waiting on
# owner input is re-pinged to the OWNER on backoff (so the owner is reminded),
# and counts toward gate-success only when explicitly parked.
#
# Idempotent. Safe every */15. 10-min lockfile. Escalates to Rescue Rangers +
# operator once at the run cap, then slow-retries (2h backoff) — never stops.
#
# ── NUDGE LIFECYCLE (built on top of PR #181 gates) ──────────────────────────
# State file: $WS/.onboarding-nudge-state  (plain key=value, no model read)
#   nudge_attempts=N          — number of model nudges fired so far
#   last_nudge_ts=EPOCH       — Unix timestamp of last nudge sent
#   dormant=true|false        — if true: no autonomous nudge; wait for re-arm
#   credit_fail_ts=EPOCH      — set on 402/429; enters dormant until re-arm
#   credit_notified=true      — credit-failure notification already sent once
#
# SCHEDULE (owner-idle before interview completes):
#   Attempt 1  — after  15 min idle  (900s)
#   Attempt 2  — after   2 h idle    (7200s from attempt 1)
#   Attempt 3  — after ~24 h idle    (86400s from attempt 2)
#   Attempt 4  — after ~24 h idle    (86400s from attempt 3)
#   → DORMANT  — zero autonomous model calls until owner re-engages
#
# RE-ARM: $WS/.onboarding-nudge-rearm touch file. Created by the incoming-
# message hook (see install.sh). When present, dormant=false, attempts reset.
#
# CREDIT BACKOFF: if openclaw message send exits non-zero AND the output
# contains "402" or "429" (or env ONBOARDING_LAST_SEND_RC is set to those),
# set dormant=true + credit_fail_ts + notify operator ONCE. No retry storm.
#
# CHEAP-CHECK RULE: every cron fire reads the nudge state file (no model call).
# A model call happens ONLY when nudge_schedule_due() returns 0.
# Most cron fires exit at the cheap check.

set -u

# ── platform + paths ─────────────────────────────────────────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[resume-onboarding] no OpenClaw root found; aborting" >&2
  exit 0
fi

# Resolve this script's dir so it can source the gate library sibling.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
GATE_LIB=""
# PRD 2.1 unified: canonical lib is lib-onboarding-state.sh at repo root,
# with scripts/onboarding-state.sh as a compat shim. Search canonical first.
for _cand in \
  "$(cd "$SCRIPT_DIR/.." 2>/dev/null && pwd || echo "")/lib-onboarding-state.sh" \
  "$SCRIPT_DIR/onboarding-state.sh" \
  "$OC_ROOT/scripts/onboarding-state.sh" \
  "$OC_ROOT/onboarding/scripts/onboarding-state.sh" \
  "$HOME/.openclaw/scripts/onboarding-state.sh"; do
  [[ -n "$_cand" && -f "$_cand" ]] && GATE_LIB="$_cand" && break
done

WS="$OC_ROOT/workspace"
STATE_FILE="$WS/.onboarding-state.json"
LOCK_FILE="$WS/.onboarding-resume.lock"
LOG_FILE="$WS/.onboarding-resume.log"
RUN_COUNT_FILE="$WS/.onboarding-resume-runs.count"
SHARED_DISPATCH_LOCK="$WS/.onboarding-dispatch.lock"   # shared with watchdog
MAX_RUNS_BEFORE_ESCALATE=24   # 6h at */30 (widened cron) — then escalate + slow-retry

# ── nudge lifecycle state file (plain key=value, NO model read) ──────────────
NUDGE_STATE_FILE="$WS/.onboarding-nudge-state"
NUDGE_REARM_FILE="$WS/.onboarding-nudge-rearm"
# Nudge schedule: minimum seconds since last nudge before the NEXT attempt fires.
# Attempt 1: 15 min from cold start; 2: 2h; 3: 24h; 4: 24h → DORMANT.
NUDGE_SCHEDULE=(900 7200 86400 86400)   # indexed 0..3; attempt N uses index N-1
MAX_NUDGE_ATTEMPTS=4

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG_FILE"; }

# ── nudge state helpers (pure file I/O — zero model calls) ───────────────────
nudge_get() {
  # nudge_get KEY → prints value or "" if unset/file missing
  local key="$1" val=""
  [[ -f "$NUDGE_STATE_FILE" ]] && val="$(grep "^${key}=" "$NUDGE_STATE_FILE" 2>/dev/null | head -1 | cut -d= -f2-)" || true
  printf '%s' "$val"
}
nudge_set() {
  # nudge_set KEY VALUE — update or append key=value in the state file
  local key="$1" value="$2"
  mkdir -p "$WS" 2>/dev/null || true
  if [[ -f "$NUDGE_STATE_FILE" ]] && grep -q "^${key}=" "$NUDGE_STATE_FILE" 2>/dev/null; then
    # Update in-place (portable sed — works on both GNU and BSD/Mac)
    local tmp
    tmp="$(mktemp)"
    sed "s|^${key}=.*|${key}=${value}|" "$NUDGE_STATE_FILE" > "$tmp" 2>/dev/null && mv "$tmp" "$NUDGE_STATE_FILE" || rm -f "$tmp"
  else
    printf '%s=%s\n' "$key" "$value" >> "$NUDGE_STATE_FILE" 2>/dev/null || true
  fi
}
nudge_enter_dormant() {
  local reason="$1"
  nudge_set dormant true
  log "NUDGE-LIFECYCLE: entering DORMANT (${reason}). No autonomous model calls until owner re-engages."
}
nudge_rearm() {
  # Called when owner engagement is detected (touch file present).
  nudge_set dormant false
  nudge_set nudge_attempts 0
  nudge_set last_nudge_ts 0
  nudge_set credit_fail_ts 0
  nudge_set credit_notified false
  rm -f "$NUDGE_REARM_FILE" 2>/dev/null || true
  log "NUDGE-LIFECYCLE: re-armed — attempts reset, dormant cleared."
}
nudge_schedule_due() {
  # Returns 0 (due) or 1 (not yet due / dormant / beyond max).
  # PURE file read — zero model calls.
  local dormant attempts last_ts now gap required_gap attempt_idx
  dormant="$(nudge_get dormant)"
  [[ "$dormant" == "true" ]] && return 1

  attempts="$(nudge_get nudge_attempts)"; attempts="${attempts:-0}"
  (( attempts >= MAX_NUDGE_ATTEMPTS )) && {
    nudge_enter_dormant "max-attempts-reached (${attempts}/${MAX_NUDGE_ATTEMPTS})"
    return 1
  }

  last_ts="$(nudge_get last_nudge_ts)"; last_ts="${last_ts:-0}"
  now="$(date +%s)"
  gap=$(( now - last_ts ))

  attempt_idx="$attempts"   # attempts=0 → index 0 (first nudge)
  (( attempt_idx >= ${#NUDGE_SCHEDULE[@]} )) && attempt_idx=$(( ${#NUDGE_SCHEDULE[@]} - 1 ))
  required_gap="${NUDGE_SCHEDULE[$attempt_idx]}"

  if (( gap >= required_gap )); then
    return 0  # nudge is due
  else
    log "NUDGE-LIFECYCLE: not due yet (attempt ${attempts}, gap ${gap}s < required ${required_gap}s)"
    return 1
  fi
}
nudge_record_sent() {
  local now; now="$(date +%s)"
  local attempts; attempts="$(nudge_get nudge_attempts)"; attempts="${attempts:-0}"
  nudge_set nudge_attempts $(( attempts + 1 ))
  nudge_set last_nudge_ts "$now"
  log "NUDGE-LIFECYCLE: nudge attempt $(( attempts + 1 )) recorded at ${now}"
}
nudge_handle_credit_failure() {
  # Call when model send fails with 402/429.
  local now; now="$(date +%s)"
  local already_notified; already_notified="$(nudge_get credit_notified)"
  nudge_set credit_fail_ts "$now"
  nudge_enter_dormant "credit-failure-402/429"
  if [[ "$already_notified" != "true" ]]; then
    nudge_set credit_notified true
    local op; op="$(resolve_operator_chat_id)"
    if [[ -n "$op" ]] && command -v openclaw >/dev/null 2>&1; then
      openclaw message send --channel telegram -t "$op" \
        -m "⚠️ [ONBOARDING] $(hostname): model call returned 402/429 (payment/quota). Entering DORMANT — will NOT retry autonomously. Onboarding resumes when the owner sends any message. Check billing/quota." \
        2>>"$LOG_FILE" || true
      log "NUDGE-LIFECYCLE: credit-failure operator notification sent to $op"
    fi
  fi
}

# ── operator chat resolver (Remote Rescue) — operator account, NOT client ────
resolve_operator_chat_id() {
  local v=""
  if command -v openclaw >/dev/null 2>&1; then
    v="$(openclaw config get env.vars.OPERATOR_HELP_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
    case "$v" in ""|*"not found"*|*"Error"*) v="" ;; esac
    if [[ -z "$v" ]]; then
      v="$(openclaw config get env.vars.OPERATOR_TELEGRAM_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
      case "$v" in ""|*"not found"*|*"Error"*) v="" ;; esac
    fi
  fi
  [[ -z "$v" && -n "${OPERATOR_HELP_CHAT_ID:-}" ]] && v="$OPERATOR_HELP_CHAT_ID"
  [[ -z "$v" ]] && v="5252140759"
  printf '%s' "$v"
}

# ── find + self-remove this cron by name (only on REAL gate-pass) ────────────
find_self_cron_uuid() {
  command -v openclaw >/dev/null 2>&1 || { echo ""; return 0; }
  openclaw cron list 2>/dev/null \
    | awk '/onboarding-resume/ { for (i=1;i<=NF;i++) if ($i ~ /^[0-9a-fA-F-]{8,}$/) { print $i; exit } }' \
    | head -1
}
self_remove_cron() {
  local reason="$1" uuid
  uuid="$(find_self_cron_uuid)"
  if [[ -z "$uuid" ]]; then
    log "self_remove_cron($reason): could not resolve onboarding-resume UUID — leaving cron in place"
    return 0
  fi
  log "self_remove_cron($reason): removing cron $uuid"
  if openclaw cron rm "$uuid" 2>>"$LOG_FILE"; then
    log "self_remove_cron($reason): removed $uuid"
    rm -f "$RUN_COUNT_FILE" 2>/dev/null || true
  else
    log "self_remove_cron($reason): openclaw cron rm $uuid FAILED"
  fi
}

mkdir -p "$WS" 2>/dev/null || true

# ── preconditions ────────────────────────────────────────────────────────────
if [[ ! -f "$STATE_FILE" ]]; then
  log "no state file at $STATE_FILE — nothing to resume; exiting clean"
  exit 0
fi
if ! command -v openclaw >/dev/null 2>&1; then
  log "openclaw CLI not on PATH — cannot dispatch resume; exiting"
  exit 0
fi

# ── NUDGE LIFECYCLE: re-arm check (CHEAP — pure file read, NO model call) ────
# If the re-arm touch file exists, the owner sent a message since we went
# dormant. Reset the attempt counter and wake up the lifecycle.
if [[ -f "$NUDGE_REARM_FILE" ]]; then
  log "NUDGE-LIFECYCLE: re-arm file detected — resetting lifecycle and clearing dormant."
  nudge_rearm
fi

# ── NUDGE LIFECYCLE: dormant/schedule gate (CHEAP — no model call) ───────────
# After the re-arm check above, determine whether a nudge is due this cycle.
# If not due, exit immediately — the cron fire costs nothing.
# NOTE: this gate is ONLY applied pre-interview (while owner-idle nudges are
# the purpose of this cron). Post-interview the resume work runs normally; the
# nudge lifecycle does not gate post-interview resume dispatches.
_wf_state_pre="$WS/.workforce-build-state.json"
_interview_complete_pre="false"
[[ -f "$_wf_state_pre" ]] && _interview_complete_pre="$(jq -r '.interviewComplete // false' "$_wf_state_pre" 2>/dev/null || echo false)"

if [[ "$_interview_complete_pre" != "true" ]]; then
  # Pre-interview: apply nudge lifecycle schedule gate.
  if ! nudge_schedule_due; then
    # Not due yet or DORMANT — cheap exit, zero model calls.
    _d="$(nudge_get dormant)"; _a="$(nudge_get nudge_attempts)"
    log "NUDGE-LIFECYCLE: pre-interview gate — dormant=${_d:-false}, attempts=${_a:-0}. No model call this cycle."
    exit 0
  fi
  log "NUDGE-LIFECYCLE: pre-interview nudge DUE (attempt $(( $(nudge_get nudge_attempts) + 1 ))/${MAX_NUDGE_ATTEMPTS})"
fi

# ── heal config before any gateway interaction ──────────────────────────────
openclaw doctor --fix >/dev/null 2>&1 || true

# ── FURNACE GATE: check interview state before any model call ────────────────
# If the interview hasn't started yet (Skill 23 is still pending/not reached),
# this cron should NOT hammer the model every 30 min. The watchdog-onboarding-loop
# handles early-wave skill installation. We only need to fire if:
#   (a) interview is complete (post-interview: legitimate resume work), OR
#   (b) Skill 23 is interview-pending or qc-passed (interview in progress or done)
# For anything earlier than that, apply a hard backoff: only fire once per 2 hours.
_wf_state="$WS/.workforce-build-state.json"
_interview_complete="false"
[[ -f "$_wf_state" ]] && _interview_complete="$(jq -r '.interviewComplete // false' "$_wf_state" 2>/dev/null || echo false)"

_skill23_status="pending"
if [[ -f "$STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
  _skill23_status="$(jq -r '.skills."23-ai-workforce-blueprint".status // "pending"' "$STATE_FILE" 2>/dev/null || echo pending)"
fi

if [[ "$_interview_complete" != "true" ]]; then
  # Interview not complete. Only proceed if Skill 23 is in-progress/parked.
  if [[ "$_skill23_status" != "interview-pending" && "$_skill23_status" != "qc-passed" ]]; then
    # Skill 23 not yet reached — early-wave install still in progress.
    # Apply a 2-hour backoff: only fire a model call if last fire was > 7200s ago.
    _BACKOFF_TS_FILE="$WS/.onboarding-resume-backoff.ts"
    _now_ts=$(date +%s)
    _last_fire=0
    [[ -f "$_BACKOFF_TS_FILE" ]] && _last_fire="$(cat "$_BACKOFF_TS_FILE" 2>/dev/null | tr -dc '0-9' || echo 0)"
    _gap=$(( _now_ts - _last_fire ))
    if (( _gap < 7200 )); then
      log "FURNACE-GATE: Skill 23 not yet reached (status=${_skill23_status}), interview not started, last fire ${_gap}s ago (<7200). Backoff — no model call this cycle."
      exit 0
    fi
    log "FURNACE-GATE: Skill 23 not yet reached but ${_gap}s since last fire (>=7200) — allowing one nudge fire."
    echo "$_now_ts" > "$_BACKOFF_TS_FILE" 2>/dev/null || true
  else
    log "FURNACE-GATE: Skill 23 status=${_skill23_status}, interview pending/in-progress — proceeding normally."
  fi
else
  log "FURNACE-GATE: interview complete — proceeding normally."
fi

# ── SHARED DISPATCH LOCK: dedup with watchdog-onboarding-loop ────────────────
# If the watchdog dispatched a model call within the last 8 min, skip this fire.
# Both crons check this file so they never double-fire in the same window.
_now_ts=$(date +%s)
if [[ -f "$SHARED_DISPATCH_LOCK" ]]; then
  _sdl_mtime=$(stat -c %Y "$SHARED_DISPATCH_LOCK" 2>/dev/null || stat -f %m "$SHARED_DISPATCH_LOCK" 2>/dev/null || echo 0)
  _sdl_age=$(( _now_ts - _sdl_mtime ))
  if (( _sdl_age < 480 )); then
    log "SHARED-DISPATCH-LOCK: another dispatch fired ${_sdl_age}s ago (<480) — skipping this fire to avoid double model call."
    exit 0
  fi
fi

# ── BELT: only a REAL gate-pass is terminal ──────────────────────────────────
# Run the verification gate. If it passes, onboarding is genuinely complete →
# self-remove. We do NOT trust any self-declared "done" or a hand-edited state.
GATE_RC=1
GATE_HUMAN=""
if [[ -n "$GATE_LIB" ]]; then
  # shellcheck disable=SC1090
  source "$GATE_LIB" 2>/dev/null || true
  if command -v obs_gate_summary >/dev/null 2>&1; then
    GATE_HUMAN="$(obs_gate_summary 2>/dev/null | grep '^GATE-HUMAN:' | sed 's/^GATE-HUMAN: //')"
    if obs_gate_summary >/dev/null 2>&1; then GATE_RC=0; fi
  fi
else
  log "gate library not found — falling back to JSON status scan (no live skills-info check)"
fi

# Fallback gate when the library is unavailable: every skill must be qc-passed
# or interview-pending in the JSON.
if [[ -z "$GATE_LIB" ]] && command -v python3 >/dev/null 2>&1; then
  GATE_RC=$(STATE_FILE="$STATE_FILE" python3 - <<'PYEOF'
import json, os, sys
try:
    s = json.load(open(os.environ["STATE_FILE"]))
except Exception:
    print(1); sys.exit(0)
sk = s.get("skills", {})
bad = [k for k, v in sk.items() if v.get("status") not in ("qc-passed", "interview-pending")]
print(0 if (sk and not bad) else 1)
PYEOF
)
fi

if [[ "$GATE_RC" == "0" ]]; then
  log "VERIFICATION GATE PASSED (${GATE_HUMAN:-all skills qc-passed/parked}) — onboarding complete; self-removing cron"
  self_remove_cron "gate-passed"
  exit 0
fi

# ── NEVER-STOP run accounting ────────────────────────────────────────────────
_run_count=0
[[ -f "$RUN_COUNT_FILE" ]] && _run_count="$(tr -dc '0-9' < "$RUN_COUNT_FILE" | head -c 6)"
[[ -z "$_run_count" ]] && _run_count=0
_run_count=$((_run_count + 1))
echo "$_run_count" > "$RUN_COUNT_FILE" 2>/dev/null || true

if (( _run_count > MAX_RUNS_BEFORE_ESCALATE )); then
  _over=$(( _run_count - MAX_RUNS_BEFORE_ESCALATE ))
  if (( _over % 8 != 1 )); then
    log "NEVER-STOP: run #$_run_count past cap — 2h-backoff slow mode, skipping this fire. NOT self-removing."
    exit 0
  fi
  # escalate once
  _already="$(command -v jq >/dev/null 2>&1 && jq -r '.resumeEscalated // false' "$STATE_FILE" 2>/dev/null || echo false)"
  if [[ "$_already" != "true" ]]; then
    _op="$(resolve_operator_chat_id)"
    [[ -n "$_op" ]] && openclaw message send --channel telegram -t "$_op" \
      -m "⚠️ onboarding-resume on $(hostname) hit $_run_count runs without the verification gate passing (${GATE_HUMAN:-skills still un-verified}). Now slow-retrying (it does NOT stop). State: $STATE_FILE" 2>>"$LOG_FILE" || true
    # Escalate via the n8n Rescue Rangers webhook (NOT bot-to-bot Telegram —
    # bots can't read other bots, so the old group post never reached the rescue agent).
    _rr_webhook="${RESCUE_RANGERS_WEBHOOK_URL:-https://main.blackceoautomations.com/webhook/rescue-rangers}"
    if [[ -n "$_rr_webhook" ]] && command -v curl >/dev/null 2>&1; then
      _rr_msg="onboarding on $(hostname) past $_run_count resume runs without a gate-pass. Run scripts/onboarding-state.sh -> obs_gate_summary on the box. State: $STATE_FILE. OpenClaw version: $(openclaw --version 2>/dev/null | head -1)"
      _rr_payload=$(jq -nc --arg c "$(hostname)" --arg a "main" --arg m "$_rr_msg" \
        '{action:"escalate",client:$c,agent:$a,message:$m}' 2>/dev/null)
      curl -s -X POST "$_rr_webhook" -H "Content-Type: application/json" -d "$_rr_payload" >>"$LOG_FILE" 2>&1 || true
    fi
    if command -v jq >/dev/null 2>&1; then
      _tmp="$(mktemp)"; jq '.resumeEscalated = true' "$STATE_FILE" > "$_tmp" 2>/dev/null && mv "$_tmp" "$STATE_FILE" || rm -f "$_tmp"
    fi
  fi
  log "NEVER-STOP: run #$_run_count past cap — slow-retry fire; continuing (NOT self-removing)."
fi

# ── lock (no double self-ping) ───────────────────────────────────────────────
if [[ -f "$LOCK_FILE" ]]; then
  lock_mtime="$(stat -c %Y "$LOCK_FILE" 2>/dev/null || stat -f %m "$LOCK_FILE" 2>/dev/null || echo 0)"
  now="$(date +%s)"; age=$(( now - lock_mtime ))
  if (( age < 600 )); then
    log "lock held ${age}s (<600) — another resume in flight; exiting"
    exit 0
  fi
  log "stale lock (age ${age}s) — clearing"
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# ── compute the work list (pending/downloaded/wired/qc-failed) ───────────────
WORK_LIST=""
PARK_LIST=""
if command -v python3 >/dev/null 2>&1; then
  WORK_LIST="$(STATE_FILE="$STATE_FILE" python3 - <<'PYEOF'
import json, os
try:
    s = json.load(open(os.environ["STATE_FILE"]))
except Exception:
    s = {"skills": {}}
bad = [k for k, v in s.get("skills", {}).items()
       if v.get("status") in ("pending", "downloaded", "wired", "qc-failed", "unknown")]
print(", ".join(sorted(bad)))
PYEOF
)"
  PARK_LIST="$(STATE_FILE="$STATE_FILE" python3 - <<'PYEOF'
import json, os
try:
    s = json.load(open(os.environ["STATE_FILE"]))
except Exception:
    s = {"skills": {}}
park = [k for k, v in s.get("skills", {}).items() if v.get("status") == "interview-pending"]
print(", ".join(sorted(park)))
PYEOF
)"
fi

if [[ -z "$WORK_LIST" && -z "$PARK_LIST" ]]; then
  log "no un-verified skills found but gate did not pass — re-running gate next cycle"
  exit 0
fi

# ── target chat: owner (paired) preferred; else operator (Remote Rescue) ─────
owner_chat=""
if command -v jq >/dev/null 2>&1; then
  owner_chat="$(jq -r '.ownerChat // empty' "$STATE_FILE" 2>/dev/null)"
fi
TARGET_CHAT="$owner_chat"
[[ -z "$TARGET_CHAT" || "$TARGET_CHAT" == "null" ]] && TARGET_CHAT="$(resolve_operator_chat_id)"
[[ -z "$TARGET_CHAT" ]] && { log "no usable target chat — cannot dispatch"; exit 0; }

# ── INTERVIEW_PENDING owner re-ping (legitimate park, on backoff) ────────────
# Re-ping the OWNER about parked skills periodically (every 4th fire ≈ hourly)
# so a real owner-input wait is not silently forgotten. NOT treated as failure.
if [[ -n "$PARK_LIST" ]] && (( _run_count % 4 == 0 )); then
  openclaw message send --channel telegram -t "$TARGET_CHAT" \
    -m "👋 Quick reminder: these are ready as soon as you have a moment to answer a couple of questions — ${PARK_LIST}. No rush; just don't want them to stall." 2>>"$LOG_FILE" || true
  log "re-pinged owner about INTERVIEW_PENDING parks: $PARK_LIST"
fi

# ── dispatch the resume self-ping (internal — drives activation + gate) ──────
msg="[ONBOARDING-RESUME] The skill onboarding is NOT verified-complete. These skills are not yet qc-passed: ${WORK_LIST:-none}. ${PARK_LIST:+(parked awaiting owner input: ${PARK_LIST}.) }DO THIS: (1) source the gate library ~/.openclaw/scripts/onboarding-state.sh; (2) for EACH not-passed skill folder under ~/.openclaw/skills/: read SKILL.md+INSTALL.md+CORE_UPDATES.md, EXECUTE INSTALL.md activation (read ≠ execute), merge CORE_UPDATES surgically, then run obs_verify_skill <folder> and loop activate→verify until it returns qc-passed; (3) a skill that genuinely needs owner input may be parked via obs_set_status <folder> interview-pending (then ask the owner) — that is the ONLY non-passed terminal state; (4) when obs_gate_summary returns success, remove the UPDATE PENDING flag from AGENTS.md and tell the owner the HONEST count. Do NOT report installed/done/onboarded for any skill that is not qc-passed. This resume is internal — keep owner messages to plain-English progress only. Run #$_run_count."

_SEND_OUT="$(mktemp)"
_SEND_RC=0
openclaw message send --channel telegram -t "$TARGET_CHAT" -m "$msg" >"$_SEND_OUT" 2>&1 || _SEND_RC=$?

if [[ "$_SEND_RC" -eq 0 ]]; then
  log "dispatched ONBOARDING-RESUME self-ping to $TARGET_CHAT (work: ${WORK_LIST:-none}; park: ${PARK_LIST:-none})"
  # Stamp shared dispatch lock so watchdog backs off in the same window.
  touch "$SHARED_DISPATCH_LOCK" 2>/dev/null || true
  # Record the nudge in the lifecycle state (pre-interview only — post-interview
  # resume dispatches are normal work, not owner-nudges, and should not count).
  if [[ "$_interview_complete_pre" != "true" ]]; then
    nudge_record_sent
    _attempts_now="$(nudge_get nudge_attempts)"
    if (( _attempts_now >= MAX_NUDGE_ATTEMPTS )); then
      nudge_enter_dormant "max-attempts-${_attempts_now}-reached — box going quiet until owner re-engages"
    fi
  fi
else
  _SEND_CONTENT="$(cat "$_SEND_OUT" 2>/dev/null || true)"
  log "FAILED to dispatch resume self-ping to $TARGET_CHAT (rc=${_SEND_RC}): ${_SEND_CONTENT}"
  # Credit-failure backoff: 402 (payment required) or 429 (rate/quota limit).
  # Enter DORMANT immediately and notify operator ONCE. No retry storm.
  if [[ "$_SEND_CONTENT" == *"402"* || "$_SEND_CONTENT" == *"429"* || \
        "${ONBOARDING_LAST_SEND_RC:-}" == "402" || "${ONBOARDING_LAST_SEND_RC:-}" == "429" ]]; then
    nudge_handle_credit_failure
    log "NUDGE-LIFECYCLE: credit-failure detected — dormant entered; no further autonomous retries."
  fi
fi
rm -f "$_SEND_OUT" 2>/dev/null || true
exit 0
