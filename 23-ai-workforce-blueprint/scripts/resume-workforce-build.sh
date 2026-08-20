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
#
# AI WORKFORCE STANDARD-FIRST (2026-08-04) AWARENESS:
#   • Departments with status "prebuilt" (written by the standard prebuild
#     driver, buildType=standard-first) are NOT counted as pending-build and
#     never appear in a [WORKFORCE-RESUME] dispatch (build-dirtiness counts
#     only non-prebuilt pending/failed/stale-building departments).
#   • HOP-4 (the buildCompletedAt writer) gains one standard-first conjunct:
#     confirmationsComplete must be true (every prebuilt department
#     confirmed-or-declined). The legacy contract is unchanged.
#   • A PARTIAL prebuild (standardPrebuild.status pending|failed, interview
#     not complete) gets a [STANDARD-PREBUILD-RESUME] self-ping lane with the
#     same anti-overlap discipline as the resume dispatch.
#   • HOP-1 recovery is unchanged by construction: the prebuild writes no
#     interviewProgress.lastQuestionAt, so it can never be read as interview
#     content.
#   • Legacy lane (buildType absent) is byte-identical to pre-change behavior.

set -u

# ─── Durable jq resolution (2026-08-17) ──────────────────────────────────────
# The OpenClaw container image does not ship jq, and a jq installed with the
# distro package manager VANISHES on container recreate — the documented
# failure that silently killed owner nudges (fix/jq-hard-dep) and, under
# `set -euo pipefail`, aborts this script outright with rc 127.
#
# ~/.openclaw is a persistent bind mount on container boxes, so a static jq
# kept at ~/.openclaw/bin/jq survives recreate. Prefer PATH's jq when present;
# otherwise fall back to the persistent copy. Prepending a PATH entry cannot
# change any filter's semantics, which is why this is done here rather than by
# hand-translating ~80 jq expressions.
if ! command -v jq >/dev/null 2>&1; then
  for _oc_jq_dir in "${HOME:-/root}/.openclaw/bin" /data/.openclaw/bin; do
    if [ -x "$_oc_jq_dir/jq" ]; then
      PATH="$_oc_jq_dir:$PATH"
      export PATH
      break
    fi
  done
  unset _oc_jq_dir
fi
# ─────────────────────────────────────────────────────────────────────────────


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
# v21.x: SEND count is OBSERVABILITY ONLY and gates nothing. Kept strictly separate
# from RUN_COUNT_FILE (the turn-driven furnace ceiling) so a successful outbound
# send can never again be mistaken for a triggered agent turn. See the dispatch
# result handling at the end of this file.
SEND_COUNT_FILE="$OC_ROOT/workspace/.workforce-build-resume-sends.count"
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
# v14.x: MONOTONIC progress high-water mark + dispatch-overlap marker.
# PROGRESS_HWM_FILE holds the highest progress SCORE ever observed for this build
# (see progress_score). The stuck counter resets ONLY when the score EXCEEDS this
# high-water mark, so status OSCILLATION (a fingerprint that churns without net
# forward motion) can no longer reset the stuck-cap. The mark NEVER decreases.
PROGRESS_HWM_FILE="$OC_ROOT/workspace/.workforce-build-resume-progress.hwm"
# INFLIGHT_MARKER is stamped at every successful dispatch. A resume self-ping fires
# an async agentTurn that can run for minutes, but this script exits ~1s after the
# send and drops its lock — so without this marker the next */15 fire stacks a
# SECOND overlapping turn (the overlap furnace). A fresh marker blocks a new
# dispatch; it TTL-expires so a genuinely-dead turn still recovers.
INFLIGHT_MARKER="$OC_ROOT/workspace/.workforce-build-resume.inflight"
# Default 24 consecutive no-progress fires = 6h of literally-zero state change =
# unambiguously stuck. Override with WORKFORCE_RESUME_MAX_STUCK_FIRES (floor 2).
MAX_STUCK_FIRES="${WORKFORCE_RESUME_MAX_STUCK_FIRES:-24}"
case "$MAX_STUCK_FIRES" in ""|*[!0-9]*) MAX_STUCK_FIRES=24 ;; esac
[ "$MAX_STUCK_FIRES" -lt 2 ] 2>/dev/null && MAX_STUCK_FIRES=2

# v14.x: ABSOLUTE ceiling on TOTAL resume self-pings dispatched for ONE build,
# independent of progress. The consecutive-stuck cap resets on every real advance,
# so a build that crawls forward just under it could otherwise self-ping forever
# (a slow furnace). At this ceiling we PARK + escalate + self-remove exactly like
# the stuck-cap. Counted in RUN_COUNT_FILE (reset by self_remove_cron). Default 240
# (≈ a very generous slow build); override WORKFORCE_RESUME_MAX_TOTAL_PINGS (floor 24).
MAX_TOTAL_RESUME_PINGS="${WORKFORCE_RESUME_MAX_TOTAL_PINGS:-240}"
case "$MAX_TOTAL_RESUME_PINGS" in ""|*[!0-9]*) MAX_TOTAL_RESUME_PINGS=240 ;; esac
[ "$MAX_TOTAL_RESUME_PINGS" -lt 24 ] 2>/dev/null && MAX_TOTAL_RESUME_PINGS=24

# v14.x: dispatch-overlap TTL (minutes). A new resume self-ping is blocked while
# the in-flight marker is younger than this. Sized to outlast a normal resume
# agentTurn yet still recover from a dead one. Override
# WORKFORCE_RESUME_INFLIGHT_TTL_MINUTES (floor 5).
RESUME_INFLIGHT_TTL_MINUTES="${WORKFORCE_RESUME_INFLIGHT_TTL_MINUTES:-20}"
case "$RESUME_INFLIGHT_TTL_MINUTES" in ""|*[!0-9]*) RESUME_INFLIGHT_TTL_MINUTES=20 ;; esac
[ "$RESUME_INFLIGHT_TTL_MINUTES" -lt 5 ] 2>/dev/null && RESUME_INFLIGHT_TTL_MINUTES=5

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG_FILE"
}

# === U110-OPTOUT-SYNC-BEGIN (E5-5/G2d) ===
# U108 built department-optout-sync.py (the department-optout CONTRACT-FILE
# writer) but its own CHANGELOG entry (v20.0.61) explicitly named the gap:
# "provisioning caller-wiring ... routed, not fixed here (owned by U110)".
# With no caller, provisioning/department-optout.json was NEVER produced on a
# real box - the Command Center board (U110's own CC leg) reads a file nobody
# writes. THIS is that caller. resume-workforce-build.sh is the one durable,
# recurring provisioning-flow driver on every box (its own header: "the ONLY
# autonomous-recovery layer in the workforce-build pipeline"), so it is fired
# unconditionally on every tick, BEFORE any of the terminal/parked/stuck-cap
# early-exit branches below - an opt-out recorded via record-dept-decision.sh
# at any point during or after the build is reflected promptly, not only at
# the very end. `mkdir -p` the workspace dir first: department-optout-sync.py
# resolves its own output path the SAME way OC_ROOT is resolved above
# (/data/.openclaw/workspace, then ~/.openclaw/workspace) but only checks
# existence - never creates it - so a not-yet-materialized workspace dir on a
# brand-new box would otherwise make it fall back to a repo-relative path
# (wrong for a real box; its own module docstring calls that fallback
# "CI-only"). Fire-and-forget by design: exit 0 (synced) and exit 1 (synced,
# but >=1 floor decline UNCONFIRMED - never silently honored, still written)
# are both success; this call is a best-effort refresh, never a build
# blocker. No --state/--out override is passed so the script's own default
# resolution (identical to OC_ROOT's) is what runs in production.
mkdir -p "$OC_ROOT/workspace" 2>/dev/null || true
DEPT_OPTOUT_SYNC_SCRIPT="$SCRIPT_DIR/department-optout-sync.py"
if [[ -f "$DEPT_OPTOUT_SYNC_SCRIPT" ]] && command -v python3 >/dev/null 2>&1; then
  python3 "$DEPT_OPTOUT_SYNC_SCRIPT" >>"$LOG_FILE" 2>&1 \
    && log "department-optout-sync: refreshed provisioning/department-optout.json" \
    || log "department-optout-sync: exited non-zero (anomalies are still written to the file, never a build blocker - see log above)"
else
  log "department-optout-sync: script not found or python3 unavailable - provisioning/department-optout.json NOT refreshed this tick"
fi
# === U110-OPTOUT-SYNC-END ===

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
    # Reset the run/stuck counters + progress high-water mark + in-flight marker so a
    # future (operator-un-parked) build starts fresh. NEVER delete BOX_PARK_MARKER
    # here — a park must persist until an operator runs scripts/unpark-build.sh
    # (auto-resume never happens silently).
    rm -f "$RUN_COUNT_FILE" "$SEND_COUNT_FILE" "$STUCK_COUNT_FILE" "$PROGRESS_FP_FILE" \
          "$PROGRESS_HWM_FILE" "$INFLIGHT_MARKER" 2>/dev/null || true
  else
    log "self_remove_cron($reason): openclaw cron rm $uuid FAILED - see errors above"
  fi
}

# ─── report_interview_not_complete: throttled operator-facing "not done yet" report ──
# Surfaces the gate REASON to the operator so they know why no CC/build is happening,
# WITHOUT hammering: at most one message per REPORT_THROTTLE_HOURS (default 24h),
# tracked by a durable marker. NEVER auto-creates departments; this is report-only.
# Distinct from the internal self-pings (lines below) which say "Do NOT message the
# owner" — those are build nudges. This is the ONE operator-facing "not done yet"
# surface, throttled so the cron never spams.
REPORT_THROTTLE_HOURS="${WORKFORCE_INTERVIEW_REPORT_THROTTLE_HOURS:-24}"
INTERVIEW_REPORT_MARKER="$OC_ROOT/workspace/.workforce-interview-not-complete.reported"
report_interview_not_complete() {
  local detail="${1:-not complete}"
  # Throttle: skip if we reported within the window.
  if [[ -f "$INTERVIEW_REPORT_MARKER" ]]; then
    local age_h
    age_h=$(( ( $(date -u +%s) - $(stat -f %m "$INTERVIEW_REPORT_MARKER" 2>/dev/null || stat -c %Y "$INTERVIEW_REPORT_MARKER" 2>/dev/null || echo 0) ) / 3600 ))
    [[ "$age_h" -lt "$REPORT_THROTTLE_HOURS" ]] && { log "interview-report: throttled (${age_h}h < ${REPORT_THROTTLE_HOURS}h)"; return 0; }
  fi
  local msg="[INTERVIEW-GATE] AI Workforce interview not completed yet (${detail}). The Command Center / zero-human company is gated until the interview is complete — no departments are being built. Finish the interview to proceed."
  # Route to the operator via the existing resolver (env.vars.OPERATOR_ESCALATION_CHAT_ID
  # -> env.vars.OPERATOR_TELEGRAM_CHAT_ID -> ""). Mirrors the dispatch idiom used
  # elsewhere in this file (openclaw message send --channel telegram -t <chat> -m <msg>).
  local _esc_chat
  _esc_chat="$(resolve_operator_chat_id)"
  if [[ -n "$_esc_chat" ]] && command -v openclaw >/dev/null 2>&1; then
    openclaw message send --channel telegram -t "$_esc_chat" -m "$msg" >>"$LOG_FILE" 2>&1 \
      || log "interview-report: operator message send failed (non-fatal)"
  else
    log "interview-report: no operator escalation chat configured — logged only (non-fatal)"
  fi
  touch "$INTERVIEW_REPORT_MARKER"
  log "interview-report: reported '${detail}' to operator (throttled ${REPORT_THROTTLE_HOURS}h)"
}

# ---- STATUS VOCABULARY NORMALIZER (the ONE normalization point) ----
# The contract word is "done": resume-prompt.txt says "done", and EVERY counter in
# this file, in closeout-readiness-watchdog.sh and in run-closeout.sh compares
# `== "done"`. Agents routinely write "complete" instead. Observed on a box where
# every one of its 34 departments sat at status:"complete": each checker counted
# done=0, so the library gate never armed, HOP-4 could never stamp buildCompletedAt,
# and the build could not cross into the closeout - silently, forever.
#
# The alternative fix - teaching a dozen scattered jq filters to also accept
# "complete" - drifts the instant somebody adds a thirteenth counter. Instead we
# normalize ONCE, here, BEFORE any consumer reads the state: synonyms are rewritten
# to the contract word in the state file itself, so every downstream reader (this
# script, the watchdog, the closeout, the Command Center) sees a single vocabulary.
#
# Idempotent and cheap: it writes only when a value actually changed. Runs before
# the BELT because the BELT is the first state reader. The write is atomic
# (mktemp + mv), matching the other pre-lock state writes in this file.
normalize_status_vocabulary() {
  command -v jq >/dev/null 2>&1 || return 0
  [[ -f "$STATE_FILE" ]] || return 0
  local _tmp
  _tmp=$(mktemp) || return 0
  if jq '
        def norm: if . == "complete" or . == "completed" then "done" else . end;
        (.status? | strings) |= norm
        | (.roleLibraryStatus? | strings) |= norm
        | (.sopLibraryStatus? | strings) |= norm
        | (.commsAutomationStatus? | strings) |= norm
        | (.closeoutStatus? | strings) |= norm
        | (.departments? | arrays) |= map(
            if type == "object" then ((.status? | strings) |= norm) else . end
          )
      ' "$STATE_FILE" > "$_tmp" 2>/dev/null && [[ -s "$_tmp" ]]; then
    if cmp -s "$_tmp" "$STATE_FILE"; then
      rm -f "$_tmp"
    else
      mv "$_tmp" "$STATE_FILE"
      log "VOCAB-NORMALIZE: rewrote 'complete'/'completed' status value(s) to the contract word 'done' (departments and/or the library/comms/closeout/top-level status fields). Every counter in this pipeline compares == \"done\"; the synonym made them all read zero."
    fi
  else
    rm -f "$_tmp"
  fi
}
normalize_status_vocabulary

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
#
# v21.x CONTRACT GUARD (THE KILLER, fixed): a top-level `.status` of done/complete
# is NOT, on its own, proof that the delivery contract closed - and it never was.
# NO script in this repository writes a top-level `.status="done"`; agents improvise
# it, and they have written it while `sopLibraryStatus`/`roleLibraryStatus` were
# still `failed` and `buildCompletedAt` was empty. The old code honored that word
# (guarded ONLY by the on-disk department floor) and self-removed the cron minutes
# after an interview completed - killing the [LIBRARY-RESUME] repair lane AND HOP-4
# (the buildCompletedAt writer, below) permanently, on a box whose libraries had
# failed. The build then sat forever with no autonomous recovery layer, which is
# exactly the "client finishes the interview and hears nothing for days" strand.
# It is also stable against a roll: even when ensure-pipeline-crons.sh re-registers
# the cron, the old belt removed it again on the next fire.
#
# The contract closes on ONE signal only: `closeoutStatus` in done|sent - the
# terminal state a SCRIPT owns (37-zhc-closeout/scripts/run-closeout.sh), not one an
# agent can improvise. `failed` remains an explicit operator stop and still
# self-removes. The on-disk department-floor guard below is UNCHANGED and still
# applies on top of this.
if [[ -f "$STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
  _build_status=$(jq -r '.status // ""' "$STATE_FILE" 2>/dev/null || echo "")
  _closeout_status=$(jq -r '.closeoutStatus // ""' "$STATE_FILE" 2>/dev/null || echo "")
  _build_completed_at=$(jq -r '.buildCompletedAt // ""' "$STATE_FILE" 2>/dev/null || echo "")
  _role_lib_belt=$(jq -r '.roleLibraryStatus // ""' "$STATE_FILE" 2>/dev/null || echo "")
  _sop_lib_belt=$(jq -r '.sopLibraryStatus // ""' "$STATE_FILE" 2>/dev/null || echo "")
  _contract_open_reason=""
  case "$_build_status" in
    done|complete)
      # Honor the agent-written word ONLY when the script-owned closeout agrees.
      case "$_closeout_status" in
        done|sent)
          _terminal=1 ;;
        *)
          _terminal=0
          _contract_open_reason="build .status='$_build_status' but closeoutStatus='${_closeout_status:-unset}' (not done|sent), buildCompletedAt='${_build_completed_at:-unset}', roleLibraryStatus='${_role_lib_belt:-unset}', sopLibraryStatus='${_sop_lib_belt:-unset}'"
          ;;
      esac
      ;;
    failed)
      _terminal=1 ;;
    *)
      _terminal=0 ;;
  esac
  if (( _terminal == 0 )) && [[ -n "$_build_completed_at" ]]; then
    case "$_closeout_status" in
      done|sent) _terminal=1; _contract_open_reason="" ;;
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
  elif [[ -n "$_contract_open_reason" ]]; then
    log "BELT: REFUSING to treat this build as terminal - $_contract_open_reason. No script in this pipeline writes a top-level .status of done/complete (an agent did); the delivery contract closes ONLY on closeoutStatus=done|sent. Keeping the resume cron ALIVE and falling through so the [LIBRARY-RESUME] repair lane and the HOP-4 buildCompletedAt writer keep driving this build to completion."
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

# MONOTONIC progress SCORE — a single non-decreasing integer that only RISES when
# the build genuinely advances: a department reaches done, a library/comms/closeout
# gate closes, or the build completes. Status OSCILLATION (a dept flapping
# building<->pending, a fingerprint that churns without net forward motion) does
# NOT raise it. Used as a high-water mark so the stuck-cap can no longer be defeated
# by churn: the stuck counter resets ONLY when this score EXCEEDS the stored mark.
progress_score() {
  if command -v jq >/dev/null 2>&1 && [[ -f "$STATE_FILE" ]]; then
    jq -r '
      ([.departments[]? | select(.status == "done")] | length)
      + (if ((.roleLibraryStatus // "") == "done") then 1 else 0 end)
      + (if ((.sopLibraryStatus // "") == "done") then 1 else 0 end)
      + (if ((.commsAutomationStatus // "") | IN("done","not-applicable")) then 1 else 0 end)
      + (if ((.closeoutStatus // "") | IN("done","sent")) then 1 else 0 end)
      + (if ((.buildCompletedAt // "") != "") then 1 else 0 end)
    ' "$STATE_FILE" 2>/dev/null || echo 0
  else
    echo 0
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
  _cur_fp="$(progress_fingerprint)"            # human-readable only (logged below)
  # MONOTONIC high-water-mark stuck detection (v14.x). The OLD logic reset the stuck
  # counter on ANY fingerprint change, so a build whose status OSCILLATED (the
  # fingerprint churned A->B->A->B...) never accrued stuck and the cap was defeated.
  # Now the reset is gated on a non-decreasing progress SCORE beating its high-water
  # mark; oscillation that makes no NET forward progress keeps incrementing stuck.
  _cur_score="$(progress_score)"
  case "$_cur_score" in ""|*[!0-9]*) _cur_score=0 ;; esac
  _prev_hwm=""
  [[ -f "$PROGRESS_HWM_FILE" ]] && _prev_hwm=$(cat "$PROGRESS_HWM_FILE" 2>/dev/null | tr -dc '0-9' | head -c 9)
  if [[ -z "$_prev_hwm" ]]; then
    # First active-build observation — establish the high-water mark; no stuck yet.
    _stuck=0
    echo "$_cur_score" > "$PROGRESS_HWM_FILE" 2>/dev/null || true
  elif (( _cur_score > _prev_hwm )); then
    # GENUINE forward progress — raise the (monotonic) high-water mark, reset stuck.
    _stuck=0
    echo "$_cur_score" > "$PROGRESS_HWM_FILE" 2>/dev/null || true
  else
    # No NET progress beyond the high-water mark (score flat, or dropped and came
    # back via oscillation). The mark is NEVER lowered here. Count this as stuck.
    _stuck=0
    [[ -f "$STUCK_COUNT_FILE" ]] && _stuck=$(cat "$STUCK_COUNT_FILE" 2>/dev/null | tr -dc '0-9' | head -c 6)
    [[ -z "$_stuck" ]] && _stuck=0
    _stuck=$((_stuck + 1))
  fi
  echo "$_stuck" > "$STUCK_COUNT_FILE" 2>/dev/null || true
  printf '%s' "$_cur_fp" > "$PROGRESS_FP_FILE" 2>/dev/null || true

  if (( _stuck >= MAX_STUCK_FIRES )); then
    log "STUCK-CAP: $_stuck consecutive cron fires with ZERO build-state progress (cap=$MAX_STUCK_FIRES). PARKING the build (durable) + escalating once, then DISABLING this cron (self-remove). Hard stop for a wedged build (replaces the old forever-firing furnace). Un-park is operator-only (scripts/unpark-build.sh)."
    park_set "stuck:${_stuck}-consecutive-fires-zero-progress"
    if command -v openclaw >/dev/null 2>&1; then
      _already_esc=$(jq -r '.stuckParkEscalated // false' "$STATE_FILE" 2>/dev/null || echo false)
      if [[ "$_already_esc" != "true" ]]; then
        _rr_webhook="${RESCUE_RANGERS_WEBHOOK_URL:-https://main.blackceoautomations.com/webhook/rr-v2-intake}"
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
    log "stuck-watch: progress score ${_cur_score} >= high-water mark — build advanced (mark raised); stuck counter reset to 0/$MAX_STUCK_FIRES."
  else
    log "stuck-watch: NO net progress (score ${_cur_score} <= high-water ${_prev_hwm:-?}; fingerprint may have churned) — stuck counter $_stuck/$MAX_STUCK_FIRES (parks + disables cron at the cap)."
  fi
else
  # No active build to be stuck on (pre-interview / pre-seed). Keep the counters +
  # high-water mark clean so a later real build starts fresh; never park this phase.
  rm -f "$STUCK_COUNT_FILE" "$PROGRESS_FP_FILE" "$PROGRESS_HWM_FILE" 2>/dev/null || true
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

# ---- AI Workforce standard-first (2026-08-04): PARTIAL-PREBUILD repair lane ----
# Under buildType=standard-first the operator-triggered prebuild driver
# (prebuild-standard-workforce.sh) materializes the canonical department floor
# from templates/role-library/ BEFORE the interview. If that prebuild session
# dies MID-materialization (e.g. 15 departments materialized, 14 pending), the
# state carries standardPrebuild.status == "pending" (or "failed") — a
# condition no other lane can see: the interview is not complete, so the normal
# build lanes below never run, and without this lane the partial prebuild would
# sit forever (a new flavor of the exact silent-strand failure mode this script
# exists to prevent). This is the partial-prebuild resume mechanism: it fires a
# [STANDARD-PREBUILD-RESUME] self-ping so the prebuild driver re-runs. The
# driver itself is idempotent (additive-only, skip-existing, no-clobber — the
# materialize-missing-departments.py safety contract), so a re-run completes
# only the missing departments.
#
# PLACEMENT: runs AFTER the park gate + preconditions + lock and BEFORE the
# read-state / HOP-1 recovery block, so a PARKED box never dispatches and this
# lane is serialized against the normal resume dispatch by the same lockfile.
# It exits here: a partial prebuild is NOT a post-interview build (no pending
# departments for the agent to build, no closeout to drive), and the standard
# lanes below assume an interview-complete build and must never misfire on
# pre-interview state.
#
# LEGACY LANES UNTOUCHED: the lane is gated on buildType == "standard-first".
# Every existing box has buildType absent (= legacy) and falls straight through
# with ZERO other behavior changed (rollback property 1: the legacy lane stays
# byte-identical). The prebuild writes NO interviewProgress.lastQuestionAt, so
# this lane can never be mistaken for interview progress, and the HOP-1
# recovery path below cannot misfire on a prebuilt-but-uninterviewed box.
_build_type_sf=$(jq -r '.buildType // empty' "$STATE_FILE" 2>/dev/null || echo "")
if [[ "$_build_type_sf" == "standard-first" ]]; then
  _prebuild_status=$(jq -r '.standardPrebuild.status // empty' "$STATE_FILE" 2>/dev/null || echo "")
  _pb_ic=$(jq -r '.interviewComplete // false' "$STATE_FILE" 2>/dev/null || echo false)
  # A PARTIAL prebuild (status "done" is handled by the prebuilt-aware
  # counting further down; an interview that is already complete means the
  # apply-diff build owns the state from here on).
  if { [[ "$_prebuild_status" == "pending" || "$_prebuild_status" == "failed" ]]; } \
     && [[ "$_pb_ic" != "true" ]]; then
    _pb_marker="$OC_ROOT/workspace/.standard-prebuild-resume.inflight"
    _pb_dispatch_ok=1
    if [[ -f "$_pb_marker" ]]; then
      _pb_mtime=$(stat -c %Y "$_pb_marker" 2>/dev/null || stat -f %m "$_pb_marker" 2>/dev/null || echo 0)
      _pb_age=$(( $(date +%s) - _pb_mtime ))
      # Same 20-minute overlap window the resume dispatch uses
      # (RESUME_INFLIGHT_TTL_MINUTES): a prebuild re-run can take minutes, and
      # a */15 fire must not stack a second overlapping re-run.
      _pb_ttl=$(( RESUME_INFLIGHT_TTL_MINUTES * 60 ))
      if (( _pb_age < _pb_ttl )); then
        _pb_dispatch_ok=0
        log "STANDARD-PREBUILD-RESUME: in-flight marker is ${_pb_age}s old (< ${_pb_ttl}s TTL) - a prebuild re-run is likely still running; SKIPPING this fire."
      fi
    fi
    if (( _pb_dispatch_ok == 1 )); then
      _pb_total=$(jq -r '(.standardPrebuild.prebuiltDepartments // .departments // []) | length' "$STATE_FILE" 2>/dev/null || echo "?")
      _pb_done=$(jq -r '[.departments[]? | select(.status == "prebuilt")] | length' "$STATE_FILE" 2>/dev/null || echo "?")
      log "STANDARD-PREBUILD-RESUME: buildType=standard-first, standardPrebuild.status=${_prebuild_status} (partial prebuild: ${_pb_done:-?}/${_pb_total:-?} departments materialized) - dispatching a [STANDARD-PREBUILD-RESUME] self-ping to re-run the idempotent prebuild driver."
      _pb_chat="$(resolve_operator_chat_id)"
      if [[ -n "$_pb_chat" ]] && command -v openclaw >/dev/null 2>&1; then
        _pb_msg="[STANDARD-PREBUILD-RESUME] the standard prebuild on $(hostname) is INCOMPLETE (standardPrebuild.status=${_prebuild_status}, ${_pb_done:-?}/${_pb_total:-?} departments materialized). Re-run scripts/prebuild-standard-workforce.sh (idempotent: additive-only, skip-existing, no-clobber per the materialize-missing-departments.py safety contract) to finish materializing the remaining departments from templates/role-library/. Do NOT message the owner about this - the prebuild is internal."
        if openclaw message send --channel telegram -t "$_pb_chat" -m "$_pb_msg" >>"$LOG_FILE" 2>&1; then
          date -u +%Y-%m-%dT%H:%M:%SZ > "$_pb_marker" 2>/dev/null || true
          log "STANDARD-PREBUILD-RESUME: dispatched (in-flight marker set, TTL ${RESUME_INFLIGHT_TTL_MINUTES}m)."
        else
          log "STANDARD-PREBUILD-RESUME: dispatch FAILED (non-fatal; will retry on the next fire)."
        fi
      else
        log "STANDARD-PREBUILD-RESUME: no operator escalation chat configured or openclaw CLI missing - logged only; will retry on the next fire. Configure env.vars.OPERATOR_ESCALATION_CHAT_ID (scripts/configure-operator-telegram.sh)."
      fi
    fi
    exit 0
  fi
fi

# ---- read state ----
interview_complete=$(jq -r '.interviewComplete // false' "$STATE_FILE")
if [[ "$interview_complete" != "true" ]]; then
  # STANDARD-FIRST NOTE (2026-08-04): this HOP-1 recovery is UNCHANGED by
  # design. The standard prebuild writes NO interviewProgress.lastQuestionAt
  # (it writes only its own namespaced standardPrebuild state block), so a
  # prebuilt-but-uninterviewed box still takes the "no lastQuestionAt -
  # interview not started" branch below and this recovery path can never
  # misfire on prebuild state. tests/unit/standard-first-cron-awareness.test.sh
  # (HOP1_NO_MISFIRE) pins that behavior.
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
    # Standard-first accuracy: on a prebuilt box the foundation already EXISTS,
    # so the operator report must not claim "no departments are being built".
    _ns_detail="not started"
    if [[ "$(jq -r '.buildType // empty' "$STATE_FILE" 2>/dev/null)" == "standard-first" ]] \
       && [[ "$(jq -r '.standardPrebuild.status // empty' "$STATE_FILE" 2>/dev/null)" == "done" ]]; then
      _ns_detail="not started (standard-first: foundation pre-built, awaiting the owner's interview review)"
    fi
    report_interview_not_complete "$_ns_detail"   # throttled operator-facing report
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
  # D9 FIX: promote on `pass` OR `needs-review`, not `pass` alone.
  # This was the last gate in the chain still demanding a strict `pass`, and it
  # is the RECOVERY lane — the net that catches an interview whose content is
  # complete but whose flag never got written. Every other gate had already been
  # reconciled to "pass OR needs-review" (see the v21.x GATE-CONSISTENCY FIX in
  # update-interview-state.sh: the evidence gate treats QC rc=0 and rc=2 alike,
  # writes interviewComplete, and kicks the build for both). NOTHING anywhere
  # promotes needs-review -> pass. So a needs-review interview arriving here was
  # refused by the one lane that existed to rescue it, and then refused again on
  # every subsequent cron fire — a permanent silent strand for a client who had
  # actually finished. `fail` and `pending` still block: --complete's own
  # evidence gate refuses those with exit 87, so a bad interview cannot be
  # promoted through this path either way.
  if [[ "$_recover_qc_status" == "pass" || "$_recover_qc_status" == "needs-review" ]]; then
    # Content verified complete. Promote via the canonical idempotent writer so the
    # same flag + gate-seeding + build-kick path runs as a normal --complete.
    COMPLETE_WRITER="${SCRIPT_DIR}/update-interview-state.sh"
    if [[ -f "$COMPLETE_WRITER" ]]; then
      log "RECOVERY: QC=$_recover_qc_status (build-eligible) - promoting interview to complete via update-interview-state.sh --complete (idempotent; seeds build + kicks it)."
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
    report_interview_not_complete "in progress (qc=$_recover_qc_status)"   # throttled operator-facing report
    exit 0
  fi
fi

# ---- PRD-2.15 (v12.3.12): QC-aware resume gate ----
# interviewComplete=true is necessary but not sufficient. The interviewQc gate
# must also be BUILD-ELIGIBLE before build/closeout can proceed. If QC is pending
# (not yet run), try to run it inline. If it is not build-eligible, fire a
# [QC-RESUME] self-ping and let the watchdog raise STUCK_QC_FAILED if it persists.
#
# v21.x GATE-CONSISTENCY FIX (the `needs-review` dead-end): build eligibility is
# `pass` OR `needs-review`, not `pass` alone. update-interview-state.sh's evidence
# gate ALREADY rules that qc rc=0 (pass) and rc=2 (needs-review) both mean "the
# evidence supports completion" - it writes interviewComplete=true, stamps
# interviewCompletedAt + buildKickRequestedAt, and tells the client they are
# finished. But this lane (and the build-kick, and run-closeout.sh) demanded a
# strict `pass`, and NOTHING anywhere ever promotes needs-review -> pass. The two
# gates disagreed, so a needs-review interview became a permanent, silent terminal
# strand: completion says yes, every build lane says no, forever, with no
# client-visible signal. Making the gates agree is the fix; the QC notes ride along
# as advisory (they are already recorded in .interviewQc for the operator). `fail`
# and `pending` still block - those are genuine "evidence does not support it".
qc_status=$(jq -r '.interviewQc.status // "pending"' "$STATE_FILE" 2>/dev/null || echo "pending")
_qc_build_eligible() { case "${1:-}" in pass|needs-review) return 0 ;; *) return 1 ;; esac; }
if ! _qc_build_eligible "$qc_status"; then
  QC_SCRIPT="${SCRIPT_DIR}/qc-interview-completion.py"
  if [[ "$qc_status" == "pending" ]] && [[ -f "$QC_SCRIPT" ]]; then
    log "[QC-RESUME] interviewQc.status=pending - running qc-interview-completion.py --write-state --state (best-effort)"
    # --write-state is a flag; the state path goes via --state (the old positional
    # form was rejected by argparse and silently no-op'd QC, stranding the gate).
    python3 "$QC_SCRIPT" --write-state --state "$STATE_FILE" >>"$LOG_FILE" 2>&1 || true
    qc_status=$(jq -r '.interviewQc.status // "pending"' "$STATE_FILE" 2>/dev/null || echo "pending")
    log "[QC-RESUME] interviewQc.status after QC run: $qc_status"
  fi
  if ! _qc_build_eligible "$qc_status"; then
    log "[QC-RESUME] interviewQc.status=$qc_status - not build-eligible (eligible: pass|needs-review). Firing self-ping for agent to review QC."
    if command -v openclaw >/dev/null 2>&1; then
      _owner_chat=$(jq -r '.ownerChat // empty' "$STATE_FILE" 2>/dev/null || true)
      # Self-ping is INTERNAL (to agent, not owner). Use operator escalation path if available.
      _operator_chat=$(resolve_operator_chat_id 2>/dev/null || true)
      if [[ -n "$_operator_chat" ]]; then
        openclaw message send --channel telegram -t "$_operator_chat" \
          -m "⚠️ [QC-RESUME] interviewQc.status=${qc_status} on $(hostname) - build resume blocked until the QC gate is build-eligible (pass or needs-review). State: $STATE_FILE" \
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

    # AI WORKFORCE STANDARD-FIRST (2026-08-04): a department at status
    # "prebuilt" is a legitimate prebuild deliverable, NOT a stale claim.
    # Auditing it here could demote it to "pending" (its how-to.md is a
    # library-sourced token-fill that may legitimately read small/stub), which
    # would then count it as pending-build and violate the "prebuilt is never
    # pending" guarantee. Skip it.
    if status == "prebuilt":
        continue

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

# NO-LASTATTEMPTAT VISIBILITY GAP FIX: a department can end up at
# status=="building" with NO lastAttemptAt at all (e.g. the DEFECT #5 honesty
# floor in refresh-build-state-from-index.py demotes a false "done" back to
# "building" but only ever touches rolesPlanned/rolesDone/status/updatedAt --
# it never stamps lastAttemptAt, because as far as that script knows no real
# attempt has started). Such an entry used to be invisible to BOTH checks
# below: not "pending"/"failed" (so absent from pending_count/pending_list),
# and excluded from stale_building_count by its own `lastAttemptAt != null`
# filter (nothing to compare "older than N minutes" against). With every
# OTHER department done, pending_count==0 AND stale_building_count==0 made
# total_attention==0 further down, so the cron logged "nothing to do" and
# exited clean every 15 minutes forever -- the exact silent-strand failure
# mode this file exists to prevent (see the Rule-8 NEVER-STOP comments
# throughout). Fail toward VISIBILITY: a "building" dept with a missing
# timestamp was never actually attempted (there is nothing to time out), so
# it belongs in the PENDING lane, not the stale-timeout lane -- it is picked
# up, named in the [WORKFORCE-RESUME] ping, and (re)started exactly like any
# other pending department, per resume-prompt.txt/INSTRUCTIONS.md's own build
# step ("flip status to building and set lastAttemptAt to now" before work
# begins). This never double-counts: stale_building_count still requires
# lastAttemptAt to exist, so a genuinely timed-out attempt is never claimed by
# both lanes at once.
#
# AI WORKFORCE STANDARD-FIRST (2026-08-04): departments with status "prebuilt"
# are NOT counted as pending-build, by construction: these selectors match ONLY
# the statuses pending/failed/building, and the vocabulary normalizer above
# never rewrites "prebuilt" into any of them. A prebuilt department (its files
# materialized from the canonical library by the prebuild driver, awaiting the
# owner's interview review) therefore never enters pending_count,
# stale_building_count, or either dispatch list below — build-dirtiness counts
# ONLY non-prebuilt pending/failed/stale-building departments.
# tests/unit/standard-first-cron-awareness.test.sh pins this. The completion-
# contract change that actually moves the needle for standard-first boxes is
# the HOP-4 amendment further down: the legacy "every department done"
# contract can never be satisfied while departments legitimately sit at
# "prebuilt", so HOP-4 gains a standard-first disjunct (all non-prebuilt depts
# done + prebuilt depts confirmed-or-declined).
pending_count=$(jq -r '
  [.departments[]
    | select((.status == "pending" or .status == "failed")
             or (.status == "building" and .lastAttemptAt == null))
  ] | length
' "$STATE_FILE")
stale_building_count=$(jq --arg min "$STALE_BUILDING_MINUTES" -r '
  [.departments[]
    | select(.status == "building")
    | select(.lastAttemptAt != null)
    | select(((now - (.lastAttemptAt | fromdateiso8601)) / 60) > ($min | tonumber))
  ] | length
' "$STATE_FILE" 2>/dev/null || echo 0)

# Standard-first prebuilt counters (always 0 on legacy boxes).
prebuilt_count=$(jq -r '[.departments[]? | select(.status == "prebuilt")] | length' "$STATE_FILE" 2>/dev/null || echo 0)
# "Confirmed or declined" decisions for prebuilt departments are recorded by
# the interview review board (record-dept-decision.sh) as provenanced decline
# records; KEEP is implicit (no record). prebuilt_decided_count therefore
# counts ONLY the prebuilt departments carrying a provenanced decline — the
# ones the apply-diff build will archive. A confirmationsComplete=true state
# flag is the authoritative "every prebuilt dept was reviewed" signal (see the
# HOP-4 standard-first completion contract below); this count is diagnostic.
prebuilt_decided_count=$(jq -r '
  [((.standardPrebuild.prebuiltDepartments // [])[]) as $p
    | (($p.decision // "") | ascii_downcase) as $d
    | select(($d == "decline" or $d == "declined" or $d == "remove")
             and (($p.provenance // "") != ""))
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
confirmations_complete=$(jq -r '.confirmationsComplete // false' "$STATE_FILE" 2>/dev/null || echo false)
build_type=$(jq -r '.buildType // empty' "$STATE_FILE" 2>/dev/null || echo "")
done_count_now=$(jq -r '[.departments[] | select(.status == "done")] | length' "$STATE_FILE")
total_count_now=$(jq -r '.departments | length' "$STATE_FILE")
# Standard-first completion helper: every non-prebuilt department done AND
# every prebuilt department confirmed-or-declined. On legacy boxes the right
# conjunct is trivially true (prebuilt_count is 0), so callers stay
# byte-identical for legacy state. The confirmationsComplete flag is written by
# the apply-diff build once the owner's review of the prebuilt set is recorded
# (KEEP is implicit; only provenanced declines carry a record).
_sf_depts_settled=0
if (( prebuilt_count > 0 )); then
  if [[ "$confirmations_complete" == "true" ]]; then
    _sf_depts_settled=1
  fi
else
  _sf_depts_settled=1
fi
_sf_all_nonprebuilt_done=0
if (( total_count_now > 0 )) \
   && (( done_count_now + prebuilt_count == total_count_now )); then
  _sf_all_nonprebuilt_done=1
fi
library_dirty=0
if (( pending_count == 0 )) && (( stale_building_count == 0 )) \
   && (( total_count_now > 0 )) \
   && { (( done_count_now == total_count_now )) \
        || { [[ "$build_type" == "standard-first" ]] \
             && (( _sf_all_nonprebuilt_done == 1 )) && (( _sf_depts_settled == 1 )); }; }; then
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
   && (( total_count_now > 0 )) \
   && { (( done_count_now == total_count_now )) \
        || { [[ "$build_type" == "standard-first" ]] \
             && (( _sf_all_nonprebuilt_done == 1 )) && (( _sf_depts_settled == 1 )); }; }; then
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
#
# AI WORKFORCE STANDARD-FIRST (2026-08-04): the completion contract gains ONE
# extra conjunct in standard-first mode - confirmationsComplete must be true,
# i.e. every prebuilt department is confirmed-or-declined (a
# confirmationsComplete flag written by the apply-diff build once the owner's
# review decisions are recorded; KEEP is implicit, provenanced declines carry
# the record). The full standard-first contract is therefore: all NON-prebuilt
# departments done + prebuilt departments confirmed-or-declined + libraries
# done + comms terminal. The legacy contract (every department done) is
# UNCHANGED - it is the first disjunct below, and on legacy boxes buildType is
# never "standard-first".
if (( pending_count == 0 )) && (( stale_building_count == 0 )) \
   && (( library_dirty == 0 )) && (( comms_automation_dirty == 0 )) \
   && (( total_count_now > 0 )) \
   && { (( done_count_now == total_count_now )) \
        || { [[ "$build_type" == "standard-first" ]] \
             && (( _sf_all_nonprebuilt_done == 1 )) && (( _sf_depts_settled == 1 )); }; } \
   && [[ -z "$build_completed_at" ]]; then
  log "AUTO-COMPLETE (HOP-4): all ${total_count_now} departments done (standard-first: ${prebuilt_count} prebuilt confirmed-or-declined, confirmationsComplete=$confirmations_complete) + libraries done (role=$role_library_status sop=$sop_library_status) + comms-automations terminal ($comms_automation_status) but buildCompletedAt was unset - writing buildCompletedAt + closeoutStatus=pending so the closeout fires automatically (no agent hand-write required)."
  _now_bc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  _tmp_bc=$(mktemp)
  # Set buildCompletedAt; only set closeoutStatus=pending if it is not already a
  # later/terminal state (do not clobber generating/sent/done/partial/blocked-*).
  if jq --arg now "$_now_bc" '
        .buildCompletedAt = $now
        | (if ((.closeoutStatus // "") | IN("generating","partial","sent","done","failed","blocked-floor-incomplete","blocked-libraries-incomplete","blocked-interview-incomplete","blocked-qc-pending")) then . else .closeoutStatus = "pending" end)
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
    _rr_webhook="${RESCUE_RANGERS_WEBHOOK_URL:-https://main.blackceoautomations.com/webhook/rr-v2-intake}"
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

# ---- v14.x: ABSOLUTE total-resume-ping ceiling (FURNACE HARD STOP) ----
# Independent of the consecutive-stuck cap (which resets on every real advance): even
# a build that crawls forward just under the stuck cap must not self-ping forever. We
# count EVERY dispatch in RUN_COUNT_FILE; at the ceiling we PARK (durable) + escalate
# once + self-remove the cron — the same hard stop as the stuck-cap. This is checked
# BEFORE bumping attempts / dispatching so the furnace can never light again.
_total_pings=0
[[ -f "$RUN_COUNT_FILE" ]] && _total_pings=$(cat "$RUN_COUNT_FILE" 2>/dev/null | tr -dc '0-9' | head -c 9)
[[ -z "$_total_pings" ]] && _total_pings=0
if (( _total_pings >= MAX_TOTAL_RESUME_PINGS )); then
  log "PING-CEILING: $_total_pings total resume self-pings dispatched for this build (ceiling=$MAX_TOTAL_RESUME_PINGS). PARKING (durable) + escalating once, then DISABLING this cron. Absolute furnace stop independent of progress. Un-park is operator-only (scripts/unpark-build.sh)."
  park_set "ping-ceiling:${_total_pings}-total-resume-pings"
  if command -v openclaw >/dev/null 2>&1; then
    _pc_esc=$(jq -r '.pingCeilingEscalated // false' "$STATE_FILE" 2>/dev/null || echo false)
    if [[ "$_pc_esc" != "true" ]]; then
      _rr_webhook="${RESCUE_RANGERS_WEBHOOK_URL:-https://main.blackceoautomations.com/webhook/rr-v2-intake}"
      if [[ -n "$_rr_webhook" ]] && command -v curl >/dev/null 2>&1; then
        _rr_msg="workforce-build-resume on $(hostname) hit the ABSOLUTE ping ceiling: ${_total_pings} total resume self-pings (cap ${MAX_TOTAL_RESUME_PINGS}). Build PARKED + cron DISABLED (v14.x). Investigate on the box, then un-park with scripts/unpark-build.sh. State: $STATE_FILE."
        _rr_payload=$(jq -nc --arg c "$(hostname)" --arg a "main" --arg m "$_rr_msg" '{action:"escalate",client:$c,agent:$a,message:$m}' 2>/dev/null || echo '')
        [[ -n "$_rr_payload" ]] && curl -s -X POST "$_rr_webhook" -H "Content-Type: application/json" ${RESCUE_RANGERS_WEBHOOK_SECRET:+-H X-Rescue-Secret:${RESCUE_RANGERS_WEBHOOK_SECRET}} -d "$_rr_payload" >>"$LOG_FILE" 2>&1 || true
      fi
      _operator_chat="$(resolve_operator_chat_id)"
      [[ -n "$_operator_chat" ]] && openclaw message send --channel telegram -t "$_operator_chat" \
        -m "⛔ workforce-build-resume on $(hostname) PARKED + DISABLED after ${_total_pings} total resume self-pings (absolute ceiling ${MAX_TOTAL_RESUME_PINGS}). It will NOT re-fire until you un-park: scripts/unpark-build.sh. State: $STATE_FILE" >>"$LOG_FILE" 2>&1 || true
      _tmp_pc=$(mktemp); jq '.pingCeilingEscalated = true' "$STATE_FILE" > "$_tmp_pc" 2>/dev/null && mv "$_tmp_pc" "$STATE_FILE" || rm -f "$_tmp_pc"
    fi
  fi
  echo "PARKED + DISABLED — ${_total_pings} total resume pings hit the absolute ceiling ($MAX_TOTAL_RESUME_PINGS). The resume cron is removed; un-park is operator-only (scripts/unpark-build.sh). STOP."
  self_remove_cron "ping-ceiling"
  exit 0
fi

# ---- v14.x: DISPATCH-OVERLAP gate (durable in-flight marker) ----
# The async agentTurn a resume self-ping triggers can run for minutes; this script
# drops its lock ~1s after the send, so without this gate the next */15 fire stacks a
# second overlapping turn (the overlap furnace). Refuse to dispatch while a FRESH
# in-flight marker exists; the marker TTL-expires so a genuinely-dead turn still
# recovers. No attempt bump / no ping count on a skipped fire — this is a no-op cycle.
if [[ -f "$INFLIGHT_MARKER" ]]; then
  _if_mtime=$(stat -c %Y "$INFLIGHT_MARKER" 2>/dev/null || stat -f %m "$INFLIGHT_MARKER" 2>/dev/null || echo 0)
  _if_age=$(( $(date +%s) - _if_mtime ))
  _if_ttl=$(( RESUME_INFLIGHT_TTL_MINUTES * 60 ))
  if (( _if_age < _if_ttl )); then
    log "IN-FLIGHT: previous resume agentTurn marker is ${_if_age}s old (< ${_if_ttl}s TTL) — a resume turn is likely still running. SKIPPING dispatch this fire to avoid overlapping agentTurns (no attempt bump). Will dispatch once the marker expires or the agent clears it ($INFLIGHT_MARKER)."
    exit 0
  fi
  log "IN-FLIGHT: marker is ${_if_age}s old (>= ${_if_ttl}s TTL) — prior resume turn presumed finished/dead; proceeding with a fresh dispatch."
fi

# ---- v14.x: RATE-LIMIT / DISPATCH-ERROR BACKOFF (Fix C-iii, fix/industry-gate-and-idempotent-crons) ----
# A dispatch failure below used to just log "resume dispatch FAILED" and let the
# NEXT */15 fire retry at the SAME fixed interval — even if the failure was a
# genuine gateway rate-limit / refusal (429, "context too large", overloaded,
# quota). Retrying an active rate-limit at the fixed cadence just tightens the
# retry loop instead of backing off (resume-prompt.txt's own Rule 8 already asks
# agents to "back off ~2 hours" on a 429/timeout — this makes that mechanical
# instead of only advisory prose). RATE_LIMIT_STATE_FILE holds
# {consecutiveFailures, nextAllowedEpoch}: exponential backoff
# (RATE_LIMIT_BASE_MINUTES * 2^failures, capped at RATE_LIMIT_MAX_MINUTES),
# reset to zero on the next successful dispatch. Uses raw epoch seconds (no
# `date -d`/`date -v` portability split needed between Linux/macOS).
RATE_LIMIT_STATE_FILE="$OC_ROOT/workspace/.workforce-build-resume-ratelimit.json"
RATE_LIMIT_BASE_MINUTES="${WORKFORCE_RESUME_RATELIMIT_BASE_MINUTES:-15}"
RATE_LIMIT_MAX_MINUTES="${WORKFORCE_RESUME_RATELIMIT_MAX_MINUTES:-240}"
_rl_now_epoch=$(date -u +%s)
_rl_next_allowed_epoch=0
if [[ -f "$RATE_LIMIT_STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
  _rl_next_allowed_epoch=$(jq -r '.nextAllowedEpoch // 0' "$RATE_LIMIT_STATE_FILE" 2>/dev/null)
  case "$_rl_next_allowed_epoch" in ''|*[!0-9]*) _rl_next_allowed_epoch=0 ;; esac
fi
if [[ "$_rl_next_allowed_epoch" -gt "$_rl_now_epoch" ]]; then
  _rl_wait_s=$(( _rl_next_allowed_epoch - _rl_now_epoch ))
  log "RATE-LIMIT BACKOFF: a prior dispatch hit a rate-limit/error signal; next dispatch not allowed for another ${_rl_wait_s}s (widened interval, no attempt bump this fire). See $RATE_LIMIT_STATE_FILE."
  exit 0
fi

# ---- bump attempt counter atomically ----
tmp_state=$(mktemp)
jq ".resumeAttempts = $((attempts + 1))" "$STATE_FILE" > "$tmp_state" && mv "$tmp_state" "$STATE_FILE"

# ---- compose the resume message + dispatch ----
agent_name=$(jq -r '.agentName // "the master orchestrator"' "$STATE_FILE")
# Read for diagnostics ONLY. NEVER a dispatch target: everything composed below is
# internal traffic and must not reach the client. See the routing block below.
owner_chat=$(jq -r '.ownerChat // empty' "$STATE_FILE")
# Mirrors the pending_count selection above (see the NO-LASTATTEMPTAT
# VISIBILITY GAP FIX comment there): a "building" dept with no lastAttemptAt
# is named here too, so the [WORKFORCE-RESUME] ping actually tells the agent
# which department to (re)start instead of silently omitting it.
# Standard-first note: "prebuilt" departments are excluded from both dispatch
# lists by construction (see the pending_count/stale_building_count comment) -
# these selectors match ONLY the pending/failed/building vocabulary, which a
# prebuilt department never carries.
pending_list=$(jq -r '
  [.departments[]
    | select((.status == "pending" or .status == "failed")
             or (.status == "building" and .lastAttemptAt == null))
    | .slug] | join(", ")
' "$STATE_FILE")
stale_list=$(jq -r --arg min "$STALE_BUILDING_MINUTES" '
  [.departments[]
    | select(.status == "building")
    | select(.lastAttemptAt != null)
    | select(((now - (.lastAttemptAt | fromdateiso8601)) / 60) > ($min | tonumber))
    | .slug] | join(", ")
' "$STATE_FILE")

# Find a chat the bot CAN reply to.
#
# v21.x CLIENT-LEAK FIX: the priority used to be owner-FIRST. Every message
# composed below is INTERNAL - each one literally ends with "Do NOT message the
# owner about this - the resume is internal" - and `openclaw message send
# --channel telegram -t <chat>` DELIVERS to that chat. Owner-first therefore meant
# clients were receiving our internal build-repair instructions in their own
# Telegram thread, verbatim, every time the recovery lane fired.
#
# Operator escalation chat is now FIRST. The owner chat is kept ONLY as a
# last-resort fallback, because on a box with no operator chat configured it is
# the sole route that reaches the agent at all - and stranding the build there
# would just trade a visible leak for another silent strand. When we do fall back
# we log it LOUDLY so the fix is to configure OPERATOR_ESCALATION_CHAT_ID (see
# scripts/configure-operator-telegram.sh), not to accept the leak.
TARGET_CHAT="$(resolve_operator_chat_id)"

# NOTE: no owner-chat fallback, and NO early exit here. Both were wrong:
#
#   * Falling back to .ownerChat delivered internal build-repair text to the client
#     and bought nothing. This dispatch is a Telegram SEND, and a send does not
#     become an inbound agent turn (see the dispatch-result handling at the end of
#     this file), so the fallback could never actually advance a build -- it was
#     pure client-facing noise for zero functional gain.
#   * Exiting here when no chat is configured also skipped the message-composition
#     block below, and that block is where the closeout branch performs the
#     DETERMINISTIC in-process exec of run-closeout.sh -- the one part of this lane
#     that genuinely works without Telegram. A box with no operator chat therefore
#     never ran its closeout. The send is now gated at the send itself, so the
#     in-process exec always gets its chance.

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

if [[ -z "$TARGET_CHAT" ]]; then
  log "no operator escalation chat configured - SKIPPING the internal self-ping rather than sending it to the client. Any in-process work above (e.g. the run-closeout.sh exec) already fired. Configure env.vars.OPERATOR_ESCALATION_CHAT_ID (scripts/configure-operator-telegram.sh) to receive these."
  exit 0
fi

log "dispatching resume to chat $TARGET_CHAT (attempt $((attempts + 1))/$max_attempts; pending='$pending_list'; stale='$stale_list'; library_dirty=$library_dirty roleLib='$role_library_status' sopLib='$sop_library_status'; comms_automation_dirty=$comms_automation_dirty comms_automation_status='$comms_automation_status'; closeout_dirty=$closeout_dirty closeout_status='$closeout_status')"
_dispatch_out=$(openclaw message send --channel telegram -t "$TARGET_CHAT" -m "$msg" 2>&1)
_dispatch_rc=$?
printf '%s\n' "$_dispatch_out" >> "$LOG_FILE"
if [[ "$_dispatch_rc" -eq 0 ]]; then
  # ---- v21.x FALSE-SUCCESS FIX: rc=0 is a SEND, not a TURN ----
  # `openclaw message send` returning 0 means the OUTBOUND message was accepted by
  # the channel. It does NOT mean an inbound agent turn was enqueued, and it never
  # did: the send path returns after handing the message to the channel plugin,
  # inbound arrives on a SEPARATE ingress queue, Telegram does not hand a bot its
  # own messages back as updates, and OpenClaw filters own-messages core-side.
  # OpenClaw's own docs/cli/cron.md also states that command cron jobs do not start
  # an isolated agent turn.
  #
  # Treating rc=0 as "a resume turn was triggered" therefore made this lane
  # SUPPRESS ITS OWN RETRIES on a success that produced nothing:
  #   * the in-flight overlap marker blocked the next */15 fire for 20 minutes,
  #     waiting for a turn that was never going to arrive; and
  #   * the absolute ping ceiling advanced on every no-op send, so after
  #     MAX_TOTAL_RESUME_PINGS the build was PARKED and this cron REMOVED ITSELF -
  #     a hard stop earned entirely by dispatches that never ran anything.
  # Both mechanisms exist to bound real agent-turn overlap, so both must be driven
  # by evidence that a turn RAN, not by evidence that a message was SENT.
  #
  # We still count sends, but into a clearly-named counter that gates NOTHING, so
  # the dispatch history stays observable without being mistaken for turn activity.
  # Boundedness is unaffected: the progress-driven consecutive-stuck cap
  # (MAX_STUCK_FIRES, resets only on genuine forward progress) still parks a wedged
  # build, and at */15 it fires long before the old ping ceiling would have.
  #
  # WORKFORCE_RESUME_SEND_IMPLIES_TURN=1 restores the historical behavior. It is the
  # switch the deterministic-exec follow-up should flip (or replace with a real
  # ingress check) once a dispatch genuinely produces a turn again.
  _total_sends=0
  [[ -f "$SEND_COUNT_FILE" ]] && _total_sends=$(cat "$SEND_COUNT_FILE" 2>/dev/null | tr -dc '0-9' | head -c 9)
  [[ -z "$_total_sends" ]] && _total_sends=0
  _total_sends=$(( _total_sends + 1 ))
  echo "$_total_sends" > "$SEND_COUNT_FILE" 2>/dev/null || true
  # A successful dispatch clears any prior rate-limit backoff (fresh start).
  rm -f "$RATE_LIMIT_STATE_FILE" 2>/dev/null || true
  if [[ "${WORKFORCE_RESUME_SEND_IMPLIES_TURN:-0}" == "1" ]]; then
    _total_pings=$(( ${_total_pings:-0} + 1 ))
    echo "$_total_pings" > "$RUN_COUNT_FILE" 2>/dev/null || true
    date -u +%Y-%m-%dT%H:%M:%SZ > "$INFLIGHT_MARKER" 2>/dev/null || true
    log "resume dispatch ok (WORKFORCE_RESUME_SEND_IMPLIES_TURN=1: counted as a turn - total resume pings this build: $_total_pings/$MAX_TOTAL_RESUME_PINGS; in-flight marker set, TTL ${RESUME_INFLIGHT_TTL_MINUTES}m; rate-limit backoff cleared)"
  else
    log "resume dispatch ok - OUTBOUND SEND accepted (send #$_total_sends for this build). This is NOT proof an agent turn ran: no in-flight marker set and the ping ceiling was NOT advanced, so the next scheduled fire is free to retry. Progress is bounded by the stuck-cap (${_stuck:-0}/$MAX_STUCK_FIRES at last check), not by this send. Rate-limit backoff cleared."
  fi
else
  log "resume dispatch FAILED rc=$_dispatch_rc (non-fatal: in-process exec already fired above if closeout_dirty)"
  # RATE-LIMIT/ERROR BACKOFF: widen the next-allowed dispatch time (exponential,
  # capped) instead of letting the next */15 fire retry at the same cadence.
  case "$_dispatch_out" in
    *"429"*|*"rate limit"*|*"Rate limit"*|*"Rate Limit"*|*"rate-limit"*|*"Rate-Limit"*|*"too many requests"*|*"Too Many Requests"*|*"context too large"*|*"Context too large"*|*"quota"*|*"Quota"*|*"overloaded"*|*"Overloaded"*|*"503"*|*"529"*)
      _rl_prev=0
      if [[ -f "$RATE_LIMIT_STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
        _rl_prev=$(jq -r '.consecutiveFailures // 0' "$RATE_LIMIT_STATE_FILE" 2>/dev/null)
        case "$_rl_prev" in ''|*[!0-9]*) _rl_prev=0 ;; esac
      fi
      _rl_fail=$(( _rl_prev + 1 ))
      _rl_shift=$_rl_fail
      (( _rl_shift > 8 )) && _rl_shift=8   # cap the exponent (2^8 * base already exceeds the minutes cap)
      _rl_minutes=$(( RATE_LIMIT_BASE_MINUTES * (1 << _rl_shift) ))
      (( _rl_minutes > RATE_LIMIT_MAX_MINUTES )) && _rl_minutes=$RATE_LIMIT_MAX_MINUTES
      _rl_next_epoch=$(( _rl_now_epoch + _rl_minutes * 60 ))
      if command -v jq >/dev/null 2>&1; then
        jq -n --argjson n "$_rl_fail" --argjson e "$_rl_next_epoch" --arg m "$_rl_minutes" \
          '{consecutiveFailures:$n, nextAllowedEpoch:$e, backoffMinutes:($m|tonumber)}' \
          > "$RATE_LIMIT_STATE_FILE" 2>/dev/null || true
      fi
      log "RATE-LIMIT/ERROR signal detected in dispatch output (consecutive=$_rl_fail) — WIDENING next dispatch to ${_rl_minutes}m out, NOT re-firing at the fixed */15 interval. State: $RATE_LIMIT_STATE_FILE"
      ;;
  esac
fi

exit 0
