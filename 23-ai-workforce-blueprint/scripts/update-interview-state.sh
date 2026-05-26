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
while [ $# -gt 0 ]; do
  case "$1" in
    --phase) PHASE="$2"; shift 2 ;;
    --question-number) QNUM="$2"; shift 2 ;;
    --asked-by) ASKED_BY="$2"; shift 2 ;;
    --phases-complete) PHASES_COMPLETE="$2"; shift 2 ;;
    --complete) COMPLETE=true; shift ;;
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
  JQ_FILTER+=' | .interviewComplete = true | .interviewCompletedAt = $now'
fi

jq "${JQ_ARGS[@]}" "$JQ_FILTER" "$STATE" > "$TMP"
mv -f "$TMP" "$STATE"

echo "updated $STATE: phase=$PHASE qnum=$QNUM asked_by=$ASKED_BY complete=$COMPLETE"
