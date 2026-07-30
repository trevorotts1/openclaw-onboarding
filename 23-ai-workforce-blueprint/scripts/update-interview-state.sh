#!/usr/bin/env bash
# Skill 23 interview state writer. Atomic-update .workforce-build-state.json
# after every answered question. Called from SKILL.md and INSTRUCTIONS.md
# per-question protocol. Added v10.15.1 (VPS) / v10.14.1 (Mac) to close the
# bug where lastQuestionNumber was stuck at 1 forever because no per-question
# writer existed.
set -euo pipefail

# Rate-limit gate (U056)
UPD_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$UPD_SCRIPT_DIR/lib-interview-rate-limit.sh"

# Resolve state file path (VPS: /data/.openclaw/workspace; Mac: $HOME/.openclaw/workspace)
if [ -d /data/.openclaw/workspace ]; then
  STATE_DIR=/data/.openclaw/workspace
elif [ -d "$HOME/.openclaw/workspace" ]; then
  STATE_DIR="$HOME/.openclaw/workspace"
else
  echo "ERROR: cannot find .openclaw/workspace directory" >&2
  exit 1
fi
STATE="$STATE_DIR/.workforce-build-state.json"

if [ ! -f "$STATE" ]; then
  echo "ERROR: state file does not exist at $STATE" >&2
  exit 1
fi

# ── Deferred-stamp spool (P0 fix) ─────────────────────────────────────────────
# A tripped rate limit must never silently discard the caller's progress
# stamp. Instead of exiting with nothing to show for it, a refused (non
# --complete) call is queued here durably, in the exact shape needed to
# replay it, and is applied automatically the next time ANY call for this
# workspace succeeds (or immediately via --drain-deferred). The client's
# actual answer text is not at risk from this script at all -- both known
# callers (SKILL.md's "write the answer to disk first" step, and the Command
# Center route's transcript append) write the transcript BEFORE this script
# ever runs -- so what this spool protects is the progress record
# (phase/question-number/asked-by/phases-complete) that this script owns.
DEFERRED_SPOOL="$STATE_DIR/.interview-state-deferred.jsonl"

# Apply one stamp to $STATE. Shared by the live (non --complete) path and by
# drain_deferred_stamps() replay, so the write shape can never drift between
# "answer this question live" and "replay a queued one" (byte-identical jq).
apply_interview_stamp() {
  local _state="$1" _phase="$2" _qnum="$3" _asked_by="$4" _phases_complete="$5"
  local _now _tmp
  _now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  _tmp="$_state.tmp.$$.$RANDOM"

  local -a _jq_args=()
  local _jq_filter='if .interviewProgress == null then .interviewProgress = {} else . end'

  if [ -n "$_phase" ]; then
    _jq_args+=(--arg phase "$_phase")
    _jq_filter+=' | .interviewProgress.lastQuestionPhase = $phase'
  fi
  if [ -n "$_qnum" ]; then
    _jq_args+=(--argjson qnum "$_qnum")
    _jq_filter+=' | .interviewProgress.lastQuestionNumber = $qnum'
  fi
  if [ -n "$_asked_by" ]; then
    _jq_args+=(--arg by "$_asked_by")
    _jq_filter+=' | .interviewProgress.lastQuestionAskedBy = $by'
  fi
  if [ -n "$_phases_complete" ]; then
    local _phases_json
    _phases_json=$(echo "$_phases_complete" | python3 -c "import sys, json; print(json.dumps([p.strip() for p in sys.stdin.read().split(',') if p.strip()]))")
    _jq_args+=(--argjson phases "$_phases_json")
    _jq_filter+=' | .interviewProgress.phasesComplete = $phases'
  fi
  _jq_args+=(--arg now "$_now")
  _jq_filter+=' | .interviewProgress.lastQuestionAt = $now'

  jq "${_jq_args[@]}" "$_jq_filter" "$_state" > "$_tmp"
  mv -f "$_tmp" "$_state"
}

# Replay every queued stamp this workspace's rate-limit budget currently has
# room for (oldest first -- the spool is append-only so file order IS
# chronological order). Entries still over budget stay queued; nothing is
# ever dropped by a drain. Best-effort: a corrupt line is skipped, not fatal.
drain_deferred_stamps() {
  [ -s "$DEFERRED_SPOOL" ] || return 0
  local _remaining
  _remaining="$(mktemp "${DEFERRED_SPOOL}.remain.XXXXXX" 2>/dev/null || printf '%s.remain.%s' "$DEFERRED_SPOOL" "$$")"
  : > "$_remaining"
  local _applied=0 _kept=0 _line _sess _dphase _dqnum _dby _dphases
  while IFS= read -r _line || [ -n "$_line" ]; do
    [ -n "$_line" ] || continue
    _sess="$(printf '%s' "$_line" | python3 -c "
import json, sys
try:
    print(json.loads(sys.stdin.read()).get('session') or '')
except Exception:
    print('')" 2>/dev/null || true)"
    if [ -n "$_sess" ] && check_interview_rate_limit "$_sess" 2>/dev/null; then
      _dphase="$(printf '%s' "$_line" | python3 -c "import json,sys
try: print(json.loads(sys.stdin.read()).get('phase') or '')
except Exception: print('')" 2>/dev/null || true)"
      _dqnum="$(printf '%s' "$_line" | python3 -c "import json,sys
try:
    v = json.loads(sys.stdin.read()).get('questionNumber')
    print(v if v is not None else '')
except Exception: print('')" 2>/dev/null || true)"
      _dby="$(printf '%s' "$_line" | python3 -c "import json,sys
try: print(json.loads(sys.stdin.read()).get('askedBy') or '')
except Exception: print('')" 2>/dev/null || true)"
      _dphases="$(printf '%s' "$_line" | python3 -c "import json,sys
try: print(json.loads(sys.stdin.read()).get('phasesComplete') or '')
except Exception: print('')" 2>/dev/null || true)"
      apply_interview_stamp "$STATE" "$_dphase" "$_dqnum" "$_dby" "$_dphases"
      _applied=$((_applied + 1))
      echo "interview-state drain: applied deferred stamp for session=$_sess (phase=$_dphase qnum=$_dqnum)" >&2
    else
      printf '%s\n' "$_line" >> "$_remaining"
      _kept=$((_kept + 1))
    fi
  done < "$DEFERRED_SPOOL"
  if [ -s "$_remaining" ]; then
    mv -f "$_remaining" "$DEFERRED_SPOOL"
  else
    rm -f "$_remaining" "$DEFERRED_SPOOL"
  fi
  if [ "$_applied" -gt 0 ] || [ "$_kept" -gt 0 ]; then
    echo "interview-state drain: applied=$_applied kept-queued=$_kept" >&2
  fi
}

# Queue a refused stamp durably (never silently dropped) and print a LOUD,
# plain-language explanation. check_interview_rate_limit() has already written
# its own "RATE-LIMIT: session ... Retry in Ns." line to stderr by the time
# this runs; this adds what that generic message can't know -- that nothing
# was lost, where it was queued, and how it comes back.
defer_stamp_and_report() {
  local _sess="$1" _phase="$2" _qnum="$3" _asked_by="$4" _phases="$5"
  local _queued_at
  _queued_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  python3 -c "
import json, sys
entry = {
    'queuedAt': sys.argv[1],
    'session': sys.argv[2],
    'phase': sys.argv[3] or None,
    'questionNumber': (int(sys.argv[4]) if sys.argv[4] else None),
    'askedBy': sys.argv[5] or None,
    'phasesComplete': sys.argv[6] or None,
}
with open(sys.argv[7], 'a') as f:
    f.write(json.dumps(entry) + '\n')
" "$_queued_at" "$_sess" "$_phase" "$_qnum" "$_asked_by" "$_phases" "$DEFERRED_SPOOL"
  {
    echo "This progress update was NOT lost: it is queued at $DEFERRED_SPOOL"
    echo "and will be applied automatically the next time any interview-state"
    echo "update for session $_sess succeeds, or immediately via:"
    echo "  update-interview-state.sh --drain-deferred"
    echo "The client's answer text is unaffected by this -- it is written to the"
    echo "transcript before this script ever runs. Retry after the window clears,"
    echo "or simply continue: the next successful call recovers this one too."
  } >&2
}

# Parse flags
PHASE=""
QNUM=""
ASKED_BY=""
PHASES_COMPLETE=""
COMPLETE=false
INDUSTRY_PACK_BLOB=""
SESSION_ID="${INTERVIEW_SESSION_ID:-}"
DRAIN_ONLY=false
while [ $# -gt 0 ]; do
  case "$1" in
    --phase) PHASE="$2"; shift 2 ;;
    --question-number) QNUM="$2"; shift 2 ;;
    --asked-by) ASKED_BY="$2"; shift 2 ;;
    --phases-complete) PHASES_COMPLETE="$2"; shift 2 ;;
    --complete) COMPLETE=true; shift ;;
    --industry-pack) INDUSTRY_PACK_BLOB="$2"; shift 2 ;;  # PRD-2.15: passthrough to record-industry-pack.sh
    --session-id) SESSION_ID="$2"; shift 2 ;;  # P0 fix: explicit stable session id, takes priority over --asked-by for the rate-limit key only (never for lastQuestionAskedBy)
    --drain-deferred) DRAIN_ONLY=true; shift ;;  # replay the deferred spool (see drain_deferred_stamps above), then exit if no other flags were given
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

# Opportunistic drain: every invocation flushes any earlier queued stamp for
# this workspace before doing its own work, so the very next successful call
# -- even an unrelated one -- recovers anything an earlier rate-limit trip
# queued, with zero extra operational awareness required.
drain_deferred_stamps

if [ "$DRAIN_ONLY" = true ] && [ -z "$PHASE" ] && [ -z "$QNUM" ] && [ "$COMPLETE" != true ] && [ -z "$INDUSTRY_PACK_BLOB" ]; then
  exit 0
fi

# Rate-limit check. interview_rate_limit_session_key() prefers an explicit
# --session-id, then a real (non-sentinel) --asked-by (preserving the
# authenticated Cf-Access/operator path's exact behavior), then falls back to
# the stable interviewSessionId in build-state -- so the shared
# "interview-web" literal the Command Center defaults to can never become the
# bucket key. See lib-interview-rate-limit.sh for the full incident writeup.
RL_SESSION="$(interview_rate_limit_session_key "${SESSION_ID:-}" "${ASKED_BY:-}")"
if [ "$COMPLETE" = true ]; then
  RL_MAX_SAVED="${INTERVIEW_RATE_LIMIT_MAX:-60}"
  INTERVIEW_RATE_LIMIT_MAX=3
  if ! check_interview_rate_limit "complete:${RL_SESSION}"; then
    INTERVIEW_RATE_LIMIT_MAX="${RL_MAX_SAVED}"
    echo "This --complete call is NOT queued for replay (completion intentionally" >&2
    echo "is not auto-replayed -- it would fire the QC gate / build-kick out of" >&2
    echo "band). Nothing else was written. Re-run --complete once the window" >&2
    echo "above clears." >&2
    exit 89
  fi
  INTERVIEW_RATE_LIMIT_MAX="${RL_MAX_SAVED}"
elif [ -n "$PHASE" ] || [ -n "$QNUM" ]; then
  if ! check_interview_rate_limit "$RL_SESSION"; then
    defer_stamp_and_report "$RL_SESSION" "$PHASE" "$QNUM" "$ASKED_BY" "$PHASES_COMPLETE"
    exit 89
  fi
fi

if [ "$COMPLETE" = true ]; then
  # --complete keeps its ORIGINAL combined atomic write (progress stamp +
  # completion/gate fields in ONE jq call) verbatim -- this branch is
  # deliberately NOT routed through apply_interview_stamp()/the deferred
  # spool (see the rate-limit check above: a --complete trip is reported but
  # not queued, since replaying it later would fire the QC gate / build-kick
  # out of band).
  NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  TMP="$STATE.tmp.$$"

  JQ_ARGS=()
  # Ensure interviewProgress exists as an object
  JQ_FILTER='if .interviewProgress == null then .interviewProgress = {} else . end'

  if [ -n "$PHASE" ]; then
    JQ_ARGS+=(--arg phase "$PHASE")
    JQ_FILTER+=' | .interviewProgress.lastQuestionPhase = $phase'
  fi
  if [ -n "$QNUM" ]; then
    JQ_ARGS+=(--argjson qnum "$QNUM")
    JQ_FILTER+=' | .interviewProgress.lastQuestionNumber = $qnum'
  fi
  if [ -n "$ASKED_BY" ]; then
    JQ_ARGS+=(--arg by "$ASKED_BY")
    JQ_FILTER+=' | .interviewProgress.lastQuestionAskedBy = $by'
  fi
  if [ -n "$PHASES_COMPLETE" ]; then
    PHASES_JSON=$(echo "$PHASES_COMPLETE" | python3 -c "import sys, json; print(json.dumps([p.strip() for p in sys.stdin.read().split(',') if p.strip()]))")
    JQ_ARGS+=(--argjson phases "$PHASES_JSON")
    JQ_FILTER+=' | .interviewProgress.phasesComplete = $phases'
  fi
  JQ_ARGS+=(--arg now "$NOW")
  JQ_FILTER+=' | .interviewProgress.lastQuestionAt = $now'

  # PRD-2.15: when marking complete, also set interviewQc.status="pending" so the
  # closeout SM and crons see a QC gate is owed. The QC gate (qc-interview-completion.py)
  # transitions this to "pass" / "needs-review" / "fail" when it runs.
  JQ_FILTER+=' | .interviewComplete = true | .interviewCompletedAt = $now'
  JQ_FILTER+=' | if .interviewQc == null then .interviewQc = {"status":"pending"} else .interviewQc.status = "pending" end'
  # PRD-3.3 R3.1 (auto-closeout): finishing the interview must DETERMINISTICALLY
  # advance the chain instead of waiting on a separate agent hand-write of the
  # build-state. Seed the library + closeout gate fields to "pending" the moment
  # --complete is written so the resume cron's library/closeout gates are armed
  # from the outset (a missing/non-"done" value is already treated as not-done).
  # We do NOT fabricate the departments[] array here - the canonical floor +
  # custom reconciliation is the agent's build step (build-workforce.py); seeding
  # a fake department list would be a lie. We DO ensure departments[] exists as an
  # array sentinel so the resume cron and watchdog parse it cleanly, and we record
  # buildKickRequestedAt so the kick below is idempotent and auditable.
  JQ_FILTER+=' | if .departments == null then .departments = [] else . end'
  JQ_FILTER+=' | if (.roleLibraryStatus == null) then .roleLibraryStatus = "pending" else . end'
  JQ_FILTER+=' | if (.sopLibraryStatus == null) then .sopLibraryStatus = "pending" else . end'
  JQ_FILTER+=' | if (.closeoutStatus == null) then .closeoutStatus = "pending" else . end'
  JQ_FILTER+=' | .buildKickRequestedAt = $now'

  jq "${JQ_ARGS[@]}" "$JQ_FILTER" "$STATE" > "$TMP"
  mv -f "$TMP" "$STATE"
else
  # Ordinary per-question stamp: the same write apply_interview_stamp() also
  # uses to replay a deferred entry, so the two paths can never drift.
  apply_interview_stamp "$STATE" "$PHASE" "$QNUM" "$ASKED_BY" "$PHASES_COMPLETE"
fi

echo "updated $STATE: phase=$PHASE qnum=$QNUM asked_by=$ASKED_BY complete=$COMPLETE"

# PRD-2.15 (v12.3.12): auto-run QC gate immediately on --complete so
# interviewQc.status transitions from "pending" to pass|needs-review|fail
# the moment the interview is marked done. This removes the "agent forgot to run
# QC" failure mode. Best-effort (non-fatal - the watchdog + resume cron will
# re-drive if QC is pending).
if [ "$COMPLETE" = true ]; then
  # Clear the interview-not-complete report throttle marker: the interview is now
  # complete, so the resume cron's next fire can re-report fresh if needed (it
  # won't, since the build will proceed). Matches the marker written by
  # report_interview_not_complete() in resume-workforce-build.sh.
  rm -f "$STATE_DIR/.workforce-interview-not-complete.reported" 2>/dev/null || true
  QC_SCRIPT="$(dirname "$0")/qc-interview-completion.py"
  if [ -f "$QC_SCRIPT" ]; then
    echo "auto-running QC gate (qc-interview-completion.py --write-state --state) post-complete..."
    # FIX (v12.4.x): --write-state is a flag; the state path MUST be passed via
    # --state. The prior form `--write-state "$STATE"` passed the path as a
    # positional, which argparse REJECTS ("unrecognized arguments") - so QC never
    # ran, interviewQc.status stayed "pending", and the whole auto-closeout chain
    # stalled silently. Verified against the script's argparse definition.
    if python3 "$QC_SCRIPT" --write-state --state "$STATE" 2>&1; then
      qc_result=$(jq -r '.interviewQc.status // "pending"' "$STATE" 2>/dev/null || echo "pending")
      echo "interviewQc.status after auto-QC: $qc_result"
    else
      echo "WARN: qc-interview-completion.py returned non-zero (non-fatal - interviewQc.status stays pending for watchdog/resume to retry)" >&2
    fi
  else
    echo "WARN: qc-interview-completion.py not found at $QC_SCRIPT - interviewQc.status remains pending" >&2
  fi
fi

# PRD-3.3 R3.1 (auto-closeout): KICK THE BUILD deterministically.
# Historically (diag/03 HOP 2) the build only started when the agent REMEMBERED
# to hand-write a build-state and self-dispatch. If the session ended after the
# owner's last answer (token limit / tool error / "felt done"), the whole build
# and closeout silently stranded. Now that --complete has marked interviewComplete
# and seeded the gate fields above, fire ONE internal [WORKFORCE-RESUME] self-ping
# so the agent starts the canonical floor + custom reconciliation build IMMEDIATELY
# instead of waiting up to 15 minutes for the resume cron. This is the state-driven
# trigger that closes the HOP-1 -> HOP-2 gap.
#
# Guards:
#  - Only when QC PASSED (qc_result=="pass"). A non-pass interview must NOT kick a
#    build; the QC-resume / watchdog lanes own that case. This mirrors run-closeout.sh's
#    hard gate so we never start a build on an unverified interview.
#  - Idempotent: skip if departments already have non-pending entries (build already
#    underway) so re-running --complete never double-dispatches into an active build.
#  - Best-effort, never fatal: if openclaw CLI is absent, the resume cron (every 15m)
#    is the recovery net and will dispatch the same self-ping on its next fire.
if [ "$COMPLETE" = true ]; then
  qc_for_kick=$(jq -r '.interviewQc.status // "pending"' "$STATE" 2>/dev/null || echo "pending")
  active_depts=$(jq -r '[.departments[]? | select(.status != "pending")] | length' "$STATE" 2>/dev/null || echo 0)
  if [ "$qc_for_kick" = "pass" ] && [ "${active_depts:-0}" = "0" ]; then
    if command -v openclaw >/dev/null 2>&1; then
      # Resolve a chat the bot can reply to: owner first, else operator escalation
      # chat IF configured. CO-MINGLING GUARD (v12.4.0): NO hardcoded personal
      # chat — if neither owner nor a configured operator chat is available, skip
      # the build-kick send (the resume cron's in-process exec still drives it).
      KICK_CHAT=$(jq -r '.ownerChat // empty' "$STATE" 2>/dev/null || true)
      if [ -z "$KICK_CHAT" ] || [ "$KICK_CHAT" = "null" ]; then
        KICK_CHAT="$(openclaw config get env.vars.OPERATOR_ESCALATION_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
        case "$KICK_CHAT" in ""|*"not found"*|*"Error"*) KICK_CHAT="" ;; esac
        if [ -z "$KICK_CHAT" ]; then
          KICK_CHAT="$(openclaw config get env.vars.OPERATOR_TELEGRAM_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
          case "$KICK_CHAT" in ""|*"not found"*|*"Error"*) KICK_CHAT="${OPERATOR_ESCALATION_CHAT_ID:-${OPERATOR_TELEGRAM_CHAT_ID:-}}" ;; esac
        fi
      fi
      KICK_AGENT=$(jq -r '.agentName // "the master orchestrator"' "$STATE" 2>/dev/null || echo "the master orchestrator")
      KICK_MSG="[WORKFORCE-RESUME] ${KICK_AGENT}: the interview is COMPLETE and the QC gate passed. Start the workforce build NOW per the Skill 23 Post-Interview Handoff Protocol - reconcile the canonical department floor with the owner's custom departments, write every planned department into .workforce-build-state.json as status=pending, then build them (build-workforce.py). roleLibraryStatus + sopLibraryStatus are already seeded pending; a SCRIPT will write buildCompletedAt + closeoutStatus when all departments + both libraries are done, and the closeout fires automatically. Do NOT message the owner - this is an internal build kick; the owner only hears from you when Skill 37 Step 6 delivers the celebration."
      if [ -z "$KICK_CHAT" ]; then
        echo "INFO: no owner chat and no operator escalation chat configured - build-kick send skipped (resume cron will drive the build in-process within 15m)" >&2
      elif openclaw message send --channel telegram -t "$KICK_CHAT" -m "$KICK_MSG" 2>&1; then
        echo "auto-closeout: dispatched [WORKFORCE-RESUME] build-kick to chat $KICK_CHAT"
      else
        echo "WARN: build-kick dispatch failed (non-fatal - resume cron will re-dispatch within 15m)" >&2
      fi
    else
      echo "INFO: openclaw CLI not on PATH - build-kick deferred to resume cron (interviewComplete + gate fields are seeded; cron will dispatch)" >&2
    fi
  elif [ "$qc_for_kick" != "pass" ]; then
    echo "INFO: build NOT kicked - interviewQc.status=$qc_for_kick (not pass). QC-resume/watchdog lanes own this; build kicks only on a passing interview." >&2
  else
    echo "INFO: build already underway (active departments present) - skipping build-kick to avoid double-dispatch" >&2
  fi
fi

# PRD-2.15: if --industry-pack blob file was passed AND industryPack not yet set, run recorder.
if [ -n "$INDUSTRY_PACK_BLOB" ] && [ -f "$INDUSTRY_PACK_BLOB" ]; then
  RECORDER_PATH="$(dirname "$0")/record-industry-pack.sh"
  if [ -f "$RECORDER_PATH" ]; then
    existing_slug=$(jq -r '.industryPack.slug // empty' "$STATE" 2>/dev/null || true)
    if [ -z "$existing_slug" ]; then
      bash "$RECORDER_PATH" --blob-file "$INDUSTRY_PACK_BLOB" --state "$STATE" \
        && echo "record-industry-pack ran from update-interview-state.sh" \
        || echo "WARN: record-industry-pack.sh failed (non-fatal)" >&2
    else
      echo "industryPack.slug already set ($existing_slug) - skipping record-industry-pack"
    fi
  fi
fi
