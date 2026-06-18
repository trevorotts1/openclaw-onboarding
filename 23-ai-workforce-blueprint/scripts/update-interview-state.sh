#!/usr/bin/env bash
# Skill 23 interview state writer. Atomic-update .workforce-build-state.json
# after every answered question. Called from SKILL.md and INSTRUCTIONS.md
# per-question protocol. Added v10.15.1 (VPS) / v10.14.1 (Mac) to close the
# bug where lastQuestionNumber was stuck at 1 forever because no per-question
# writer existed.
set -euo pipefail

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

# Parse flags
PHASE=""
QNUM=""
ASKED_BY=""
PHASES_COMPLETE=""
COMPLETE=false
INDUSTRY_PACK_BLOB=""
while [ $# -gt 0 ]; do
  case "$1" in
    --phase) PHASE="$2"; shift 2 ;;
    --question-number) QNUM="$2"; shift 2 ;;
    --asked-by) ASKED_BY="$2"; shift 2 ;;
    --phases-complete) PHASES_COMPLETE="$2"; shift 2 ;;
    --complete) COMPLETE=true; shift ;;
    --industry-pack) INDUSTRY_PACK_BLOB="$2"; shift 2 ;;  # PRD-2.15: passthrough to record-industry-pack.sh
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

# Build the jq patch fragment
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

if [ "$COMPLETE" = true ]; then
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
fi

jq "${JQ_ARGS[@]}" "$JQ_FILTER" "$STATE" > "$TMP"
mv -f "$TMP" "$STATE"

echo "updated $STATE: phase=$PHASE qnum=$QNUM asked_by=$ASKED_BY complete=$COMPLETE"

# PRD-2.15 (v12.3.12): auto-run QC gate immediately on --complete so
# interviewQc.status transitions from "pending" to pass|needs-review|fail
# the moment the interview is marked done. This removes the "agent forgot to run
# QC" failure mode. Best-effort (non-fatal - the watchdog + resume cron will
# re-drive if QC is pending).
if [ "$COMPLETE" = true ]; then
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
