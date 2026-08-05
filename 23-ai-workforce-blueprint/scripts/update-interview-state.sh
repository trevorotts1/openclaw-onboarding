#!/usr/bin/env bash
# Skill 23 interview state writer. Atomic-update .workforce-build-state.json
# after every answered question. Called from SKILL.md and INSTRUCTIONS.md
# per-question protocol. Added v10.15.1 (VPS) / v10.14.1 (Mac) to close the
# bug where lastQuestionNumber was stuck at 1 forever because no per-question
# writer existed.
#
# EVIDENCE-GATED COMPLETION (2026-07-30 incident, a client Mac mini box /
# rescue-cassandra-henriquez): `--complete` used to write
# `.interviewComplete = true` UNCONDITIONALLY and only ran
# qc-interview-completion.py AFTERWARD, best-effort/non-fatal ("WARN ...
# non-fatal"). A 19-question interview with 5 missing mandatory fields was
# marked complete, the client was told she was finished, and interviewQc.status
# never resolved past "pending" (a separate bug: the auto-QC call passed no
# --transcript and the web path's encrypted-at-rest transcript wasn't found —
# fixed in PR #772 / commit 411cf502). Both defects together produced a false
# "you're done": the flag write had no evidence requirement, and the one check
# that could have caught it silently no-op'd.
#
# Fix: `--complete` now runs qc-interview-completion.py --write-state FIRST,
# BEFORE writing `.interviewComplete`. Exit 0 (PASS) or 2 (NEEDS-REVIEW) lets
# completion proceed (interviewQc.status is already written by that same run —
# it is NOT re-seeded to "pending" below). Exit 1 or 3 (error / HARD FAIL, e.g.
# question count outside 25-35, missing mandatory fields, or a
# lastQuestionNumber-vs-transcript disagreement > 3) REFUSES: interviewComplete
# is NEVER written, and the script exits 87 — the same code
# blackceo-command-center's POST /api/interview/complete route already expects
# and maps to a clean 409 `interview_pending` response (see src/lib/interview/
# seam.ts InterviewScriptError handling). A missing QC script is ALSO a refusal
# (fail-closed: absence of the evidence check is not permission to skip it).
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

# ── EVIDENCE GATE (2026-07-30 fix, a client Mac mini box / rescue-cassandra-henriquez) ──
# `--complete` used to write `.interviewComplete = true` UNCONDITIONALLY (see the
# write block below) and only ran qc-interview-completion.py AFTERWARD,
# best-effort/non-fatal ("WARN ... non-fatal - interviewQc.status stays pending").
# A 19-question interview with 5 missing mandatory fields (and a
# lastQuestionNumber frozen at 11 while the transcript held 19 Q/A blocks) was
# marked complete this way; the client was told she was finished. Nothing in the
# automated pipeline ever required the evidence to support the flag.
#
# Fix: run the SAME qc-interview-completion.py gate FIRST, before any write, and
# make its verdict authoritative over whether interviewComplete is written at all:
#   rc=0 (PASS) or rc=2 (NEEDS-REVIEW)  -> evidence supports completion; proceed.
#     interviewQc is already written by THIS run (--write-state), so the write
#     block below must NOT re-seed it to "pending".
#   rc=3 (HARD FAIL: count outside 25-35, missing mandatory fields, or a
#     lastQuestionNumber-vs-transcript disagreement > 3 questions) -> REFUSE.
#     interviewComplete is NEVER written. Exit 87 - the exact code
#     blackceo-command-center's POST /api/interview/complete route already
#     expects and maps to a clean 409 `interview_pending` response (see
#     src/lib/interview/seam.ts's InterviewScriptError handling) rather than a
#     generic crash.
#   rc=1 (script/transcript error - cannot verify) -> FAIL CLOSED the same way:
#     absence of evidence is not permission to mark complete. Exit 87.
#   QC script missing entirely -> ALSO a refusal (exit 87), for the same reason.
# This is the ONE chokepoint every --complete caller funnels through (the web
# Command Center route, the Telegram/SKILL.md agent protocol, and
# resume-workforce-build.sh's recovery-promotion path all call `--complete` on
# THIS script) — closing it here closes it for every caller, not just the one
# that fired in this incident.
if [ "$COMPLETE" = true ]; then
  QC_SCRIPT="$UPD_SCRIPT_DIR/qc-interview-completion.py"
  if [ ! -f "$QC_SCRIPT" ]; then
    echo "REFUSED: qc-interview-completion.py not found at $QC_SCRIPT - cannot verify question-count + mandatory-field evidence before marking complete. interviewComplete was NOT written. Repair the Skill 23 install and retry." >&2
    exit 87
  fi
  echo "evidence gate: running qc-interview-completion.py --write-state BEFORE marking complete (question count 25-35, mandatory fields, transcript/counter agreement)..."
  set +e
  QC_GATE_OUTPUT=$(python3 "$QC_SCRIPT" --write-state --state "$STATE" 2>&1)
  QC_GATE_RC=$?
  set -e
  echo "$QC_GATE_OUTPUT"
  if [ "$QC_GATE_RC" != "0" ] && [ "$QC_GATE_RC" != "2" ]; then
    echo "REFUSED: qc-interview-completion.py rc=$QC_GATE_RC (neither PASS nor NEEDS-REVIEW) - the answer evidence does not support completion. interviewComplete was NOT written (interviewQc above already carries the reasons for the owner/agent to fix and retry)." >&2
    exit 87
  fi
  echo "evidence gate: rc=$QC_GATE_RC - evidence supports completion; proceeding to write interviewComplete=true."
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

  # interviewQc is deliberately NOT (re-)seeded to "pending" here: the EVIDENCE
  # GATE above already ran qc-interview-completion.py --write-state and wrote the
  # real verdict (pass/needs-review) before this write block ever runs (a FAIL
  # or error already `exit 87`'d before reaching this point). Re-seeding to
  # "pending" here would silently clobber that fresh, authoritative verdict back
  # to an unresolved state — exactly the bug that let interviewQc.status sit at
  # "pending" forever while interviewComplete was already true.
  JQ_FILTER+=' | .interviewComplete = true | .interviewCompletedAt = $now'
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

# QC already ran BEFORE the write (the EVIDENCE GATE above) - interviewQc.status
# already reflects pass|needs-review the moment interviewComplete is written (a
# FAIL/error refused with exit 87 before any write happened, so this point is
# only ever reached with a verdict that supports completion). No second,
# post-hoc QC run is needed here anymore.
if [ "$COMPLETE" = true ]; then
  # Clear the interview-not-complete report throttle marker: the interview is now
  # complete, so the resume cron's next fire can re-report fresh if needed (it
  # won't, since the build will proceed). Matches the marker written by
  # report_interview_not_complete() in resume-workforce-build.sh.
  rm -f "$STATE_DIR/.workforce-interview-not-complete.reported" 2>/dev/null || true
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
#  - Only when QC is BUILD-ELIGIBLE. v21.x GATE-CONSISTENCY FIX: eligibility is
#    `pass` OR `needs-review`, not `pass` alone. The EVIDENCE GATE above already
#    treats qc rc=0 (pass) and rc=2 (needs-review) as "evidence supports
#    completion" - it writes interviewComplete=true, stamps interviewCompletedAt +
#    buildKickRequestedAt, and the client is told they are finished. But this kick
#    (and resume-workforce-build.sh, and run-closeout.sh) used to demand a strict
#    `pass`, and NOTHING anywhere promotes needs-review -> pass. So a needs-review
#    interview became a permanent silent strand: completion says yes, every build
#    lane says no, forever, with no client-visible signal. The gates now agree; the
#    QC notes ride along as advisory in .interviewQc for the operator. `fail` and
#    `pending` still block - the evidence gate above already refuses those (exit 87).
#  - Idempotent WITHOUT suppressing real kicks. v21.x KICK-SUPPRESSION FIX: the old
#    guard was `active_depts == 0`, where active_depts counted departments whose
#    status != "pending". Its INTENT was "do not double-dispatch into a build that is
#    already running", but the presence of department ENTRIES is the wrong proxy for
#    "a build is running". Observed on a real box: the interview was reopened and
#    re-completed while a prior partial build had already left 34 department entries
#    in the state, so active_depts=34 and the kick was NEVER dispatched - not delayed,
#    never sent. Any client whose interview is reopened or re-run on a box that
#    already carries departments silently gets no kick at all. That is the exact
#    "finished the interview, then nothing happened" strand, and reopened interviews
#    are common (the state schema even carries interviewReopenedAt/ReopenReason).
#    The kick is now suppressed only by ACTUAL build/run state:
#      (a) the build genuinely finished AND the closeout is terminal, or
#      (b) a resume/build turn is already IN FLIGHT - detected via the SAME durable
#          overlap marker resume-workforce-build.sh stamps on every dispatch
#          (.workforce-build-resume.inflight), which is the real "a turn is running"
#          signal and TTL-expires so a dead turn still recovers.
#  - Message content branches on buildType (PHASE 7, standard-first): a
#    standard-first box was PREBUILT before the interview, so it receives the
#    APPLY-THE-DIFF message (deprovision confirmed declines, materialize
#    customs, add declared verticals, personalize kept depts, register agents
#    for confirmed-kept depts). Every other box (legacy lane: buildType absent)
#    receives the ORIGINAL build-from-scratch message byte-identical.
#  - Best-effort, never fatal: if openclaw CLI is absent, the resume cron (every 15m)
#    is the recovery net and will dispatch the same self-ping on its next fire.
if [ "$COMPLETE" = true ]; then
  qc_for_kick=$(jq -r '.interviewQc.status // "pending"' "$STATE" 2>/dev/null || echo "pending")
  qc_kick_eligible=false
  case "$qc_for_kick" in pass|needs-review) qc_kick_eligible=true ;; esac

  kick_blocked_reason=""
  build_done_for_kick=$(jq -r '.buildCompletedAt // empty' "$STATE" 2>/dev/null || true)
  closeout_for_kick=$(jq -r '.closeoutStatus // empty' "$STATE" 2>/dev/null || true)
  if [ -n "$build_done_for_kick" ] && [ "$build_done_for_kick" != "null" ]; then
    case "$closeout_for_kick" in
      done|sent)
        kick_blocked_reason="build already complete (buildCompletedAt=$build_done_for_kick) and closeout is terminal (closeoutStatus=$closeout_for_kick) - nothing to kick"
        ;;
    esac
  fi
  if [ -z "$kick_blocked_reason" ]; then
    KICK_INFLIGHT_MARKER="$STATE_DIR/.workforce-build-resume.inflight"
    if [ -f "$KICK_INFLIGHT_MARKER" ]; then
      _kick_if_mtime=$(stat -c %Y "$KICK_INFLIGHT_MARKER" 2>/dev/null || stat -f %m "$KICK_INFLIGHT_MARKER" 2>/dev/null || echo 0)
      _kick_if_ttl_min="${WORKFORCE_RESUME_INFLIGHT_TTL_MINUTES:-20}"
      case "$_kick_if_ttl_min" in ''|*[!0-9]*) _kick_if_ttl_min=20 ;; esac
      [ "$_kick_if_ttl_min" -lt 5 ] 2>/dev/null && _kick_if_ttl_min=5
      _kick_if_age=$(( $(date -u +%s) - _kick_if_mtime ))
      if [ "$_kick_if_age" -lt $(( _kick_if_ttl_min * 60 )) ]; then
        kick_blocked_reason="a resume/build turn is already IN FLIGHT (overlap marker ${_kick_if_age}s old, TTL ${_kick_if_ttl_min}m) - not stacking a second turn"
      fi
    fi
  fi

  if [ "$qc_kick_eligible" = true ] && [ -z "$kick_blocked_reason" ]; then
    if command -v openclaw >/dev/null 2>&1; then
      # Resolve a chat the bot can reply to.
      #
      # v21.x CLIENT-LEAK FIX: this used to try .ownerChat FIRST. KICK_MSG below is
      # INTERNAL — it literally ends with "Do NOT message the owner - this is an
      # internal build kick" — and `openclaw message send --channel telegram -t
      # <chat>` DELIVERS to that chat. Owner-first therefore delivered our internal
      # build-kick instructions straight into the client's own Telegram thread, at
      # the exact moment they finished their interview.
      #
      # Operator escalation chat is now FIRST. .ownerChat remains a last-resort
      # fallback only, because on a box with no operator chat configured it is the
      # only route that reaches the agent at all, and dropping the kick there would
      # trade a visible leak for another silent strand. The fallback logs LOUDLY.
      # CO-MINGLING GUARD (v12.4.0): NO hardcoded personal chat.
      KICK_CHAT="$(openclaw config get env.vars.OPERATOR_ESCALATION_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
      case "$KICK_CHAT" in ""|*"not found"*|*"Error"*) KICK_CHAT="" ;; esac
      if [ -z "$KICK_CHAT" ]; then
        KICK_CHAT="$(openclaw config get env.vars.OPERATOR_TELEGRAM_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
        case "$KICK_CHAT" in ""|*"not found"*|*"Error"*) KICK_CHAT="${OPERATOR_ESCALATION_CHAT_ID:-${OPERATOR_TELEGRAM_CHAT_ID:-}}" ;; esac
      fi
      # NO .ownerChat fallback. It delivered internal build-kick text into the
      # client's own thread at the exact moment they finished their interview, and
      # it bought nothing: this is a Telegram SEND, and a send does not become an
      # inbound agent turn, so it could never actually start a build. We fail SAFE
      # -- skip the kick and let the resume cron drive -- rather than fall through
      # to the client.
      KICK_AGENT=$(jq -r '.agentName // "the master orchestrator"' "$STATE" 2>/dev/null || echo "the master orchestrator")
      # STANDARD-FIRST BRANCH (PHASE 7): a box with buildType=standard-first was
      # PREBUILT before the interview (prebuild-standard-workforce.sh), so the
      # interview EDITED the built set and the build-kick must APPLY THE DIFF -
      # never rebuild from scratch. Legacy boxes (absent buildType or any other
      # value) keep the ORIGINAL message byte-identical (rollback property 1).
      KICK_BUILD_TYPE=$(jq -r '.buildType // empty' "$STATE" 2>/dev/null || echo "")
      if [ "$KICK_BUILD_TYPE" = "standard-first" ]; then
        KICK_MSG="[WORKFORCE-RESUME] ${KICK_AGENT}: the interview is COMPLETE and the QC gate is build-eligible (interviewQc.status=${qc_for_kick}). This is a STANDARD-FIRST box: the canonical department floor was PREBUILT before the interview began (standardPrebuild), so do NOT build from scratch - APPLY THE DIFF the interview recorded, per the Skill 23 Post-Interview Handoff Protocol. Run the apply-standard-edits build (build-workforce.py --apply-standard-edits): (1) deprovision the CONFIRMED declines (scripts/retire-confirmed-decline.sh - archive to .retired/, NEVER delete, provenanced declines only), (2) materialize the custom departments the owner ADDED, (3) add the declared industry verticals, and (4) personalize the KEPT departments (no-clobber on owner-edited content) - then register the agents.list rows for every confirmed-kept department (the deferred Moment 3.5). Silence = KEEP: a department with no recorded decision stays exactly as prebuilt. If parts of the diff are ALREADY applied from a prior or partial run, do NOT start over - resume them: leave every finished department alone and drive the unfinished ones to done. roleLibraryStatus + sopLibraryStatus are already seeded pending; a SCRIPT will write buildCompletedAt + closeoutStatus when all departments + both libraries are done, and the closeout fires automatically. Do NOT message the owner - this is an internal build kick; the owner only hears from you when Skill 37 Step 6 delivers the celebration."
      else
        KICK_MSG="[WORKFORCE-RESUME] ${KICK_AGENT}: the interview is COMPLETE and the QC gate is build-eligible (interviewQc.status=${qc_for_kick}). Start the workforce build NOW per the Skill 23 Post-Interview Handoff Protocol - reconcile the canonical department floor with the owner's custom departments, write every planned department into .workforce-build-state.json as status=pending, then build them (build-workforce.py). If departments are ALREADY present from a prior or partial build, do NOT start over - resume them: leave every finished department alone and drive the unfinished ones to done. roleLibraryStatus + sopLibraryStatus are already seeded pending; a SCRIPT will write buildCompletedAt + closeoutStatus when all departments + both libraries are done, and the closeout fires automatically. Do NOT message the owner - this is an internal build kick; the owner only hears from you when Skill 37 Step 6 delivers the celebration."
      fi
      if [ -z "$KICK_CHAT" ] || [ "$KICK_CHAT" = "null" ]; then
        echo "INFO: no operator escalation chat configured - build-kick send SKIPPED rather than routed to the client (resume cron drives the build within 15m). Configure env.vars.OPERATOR_ESCALATION_CHAT_ID via scripts/configure-operator-telegram.sh to receive these." >&2
      elif openclaw message send --channel telegram -t "$KICK_CHAT" -m "$KICK_MSG" 2>&1; then
        echo "auto-closeout: dispatched [WORKFORCE-RESUME] build-kick to chat $KICK_CHAT"
      else
        echo "WARN: build-kick dispatch failed (non-fatal - resume cron will re-dispatch within 15m)" >&2
      fi
    else
      echo "INFO: openclaw CLI not on PATH - build-kick deferred to resume cron (interviewComplete + gate fields are seeded; cron will dispatch)" >&2
    fi
  elif [ "$qc_kick_eligible" != true ]; then
    echo "INFO: build NOT kicked - interviewQc.status=$qc_for_kick is not build-eligible (eligible: pass|needs-review). QC-resume/watchdog lanes own this." >&2
  else
    echo "INFO: build-kick skipped - $kick_blocked_reason" >&2
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
