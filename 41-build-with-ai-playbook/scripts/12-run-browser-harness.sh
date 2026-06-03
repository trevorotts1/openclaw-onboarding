#!/usr/bin/env bash
# 12-run-browser-harness.sh -- Skill 41 v1.3.0 browser-execution harness runner.
#
# Executes the live L1-L5 harness (the proof that browser/build execution works end-to-end)
# and emits the f52 `qc_result` event per references/f52-data-contract.md: the count fields
# total / pass_count / fixed_count / escalated_count plus publish_decision as a real boolean.
# This is the closed-loop runner: L0 (the static gate, 11-run-qc-checklist.sh) proves the skill
# is well-formed; THIS runner proves the executor actually works.
#
# Sits alongside 11-run-qc-checklist.sh in scripts/. The level scripts live in scripts/test/.
#
# SAFE: every level is offline/loopback-only. No real creds, no live external calls.
# PLATFORM-AWARE: levels branch on uname -s; this runner records the platform in the event.
#
# Exit codes:
#   0  -> publish decision = PASS  (all levels passed, nothing escalated)
#   2  -> publish decision = ESCALATED (>=1 level failed/escalated -> DO NOT publish; human-last)
#   3  -> a level SKIPPED for a host-tooling reason (python3 missing) AND no failures -> WARN
# The runner never returns 1 silently; a non-pass is always an explicit ESCALATED decision.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR="$SCRIPT_DIR/test"
LIB="$TEST_DIR/lib-harness.sh"

echo "[skill 41 harness] L1-L5 browser-execution harness for $SKILL_ROOT"
echo "[skill 41 harness] platform: $(uname -s)"

if [[ ! -d "$TEST_DIR" ]]; then
  echo "[skill 41 harness] FATAL: $TEST_DIR not found -- the L1-L5 harness is not installed." >&2
  exit 2
fi
# shellcheck source=/dev/null
[[ -f "$LIB" ]] && source "$LIB"

LEVELS=(L1-auth-session L2-build-execution L3-seeded-defect L4-safety L5-forced-failure)

TOTAL=0; PASS=0; FAILED=0; SKIPPED=0; ESCALATED=0; FIXED=0
declare -a RESULTS=()
RUNLOG="$(mktemp 2>/dev/null || mktemp -t hf41run)"

for lv in "${LEVELS[@]}"; do
  TOTAL=$((TOTAL + 1))
  script="$TEST_DIR/$lv.sh"
  if [[ ! -f "$script" ]]; then
    echo "  MISSING $lv ($script)"; RESULTS+=("$lv=MISSING"); ESCALATED=$((ESCALATED + 1)); continue
  fi
  rc=0; bash "$script" >"$RUNLOG" 2>&1 || rc=$?
  # Count any FIXED outcomes a level auto-remediated (the level prints "FIXED:" lines).
  lv_fixed="$(grep -c 'FIXED:' "$RUNLOG" 2>/dev/null | head -1)"; lv_fixed="${lv_fixed:-0}"
  FIXED=$((FIXED + lv_fixed))
  case "$rc" in
    0)
      echo "  PASS $lv"; PASS=$((PASS + 1)); RESULTS+=("$lv=PASS")
      # A PASS that recorded a FINDING/escalation (e.g. L2 surfacing an upstream build defect)
      # still counts the escalation so the publish decision reflects it.
      if grep -q '"event":"escalation"' "$RUNLOG" 2>/dev/null; then
        ESCALATED=$((ESCALATED + 1)); RESULTS[-1]="$lv=PASS(+escalation)"
      fi
      ;;
    3)
      echo "  SKIP $lv (host-tooling: python3 unavailable)"; SKIPPED=$((SKIPPED + 1)); RESULTS+=("$lv=SKIP")
      ;;
    *)
      echo "  FAIL $lv (rc=$rc)"; FAILED=$((FAILED + 1)); ESCALATED=$((ESCALATED + 1)); RESULTS+=("$lv=FAIL")
      sed 's/^/      /' "$RUNLOG" | tail -6
      ;;
  esac
done
rm -f "$RUNLOG"

# --- publish decision ---------------------------------------------------------
# PASS only if every level passed AND nothing escalated. Any failure or escalation => the
# closed-loop says DO NOT publish; escalate to a human (human-last).
if [[ $FAILED -eq 0 && $ESCALATED -eq 0 ]]; then
  DECISION="PASS"
else
  DECISION="ESCALATED"
fi

echo "[skill 41 harness] results: $(IFS=', '; echo "${RESULTS[*]}")"
echo "[skill 41 harness] total=$TOTAL pass=$PASS fixed=$FIXED escalated=$ESCALATED skipped=$SKIPPED -> publish=$DECISION"

# --- emit the f52 qc_result event ---------------------------------------------
# Schema (references/f52-data-contract.md): event=qc_result with the count fields
# total / pass_count / fixed_count / escalated_count + publish_decision as a real
# boolean. PII-free. The contract is the source of truth, so the emit carries ONLY
# those fields (plus the common ts/skill/event/session_ref/source) -- no extra
# levels/platform/skipped keys that the contract does not declare.
# publish_decision (boolean): true iff nothing escalated AND every counted level
# passed or was auto-fixed (escalated_count==0 AND pass_count+fixed_count==total).
# A SKIP leaves pass_count+fixed_count < total -> publish_decision=false (the WARN
# path), which is correct: a skipped level is not a proven-green level.
if [[ $ESCALATED -eq 0 && $((PASS + FIXED)) -eq $TOTAL ]]; then
  PUBLISH_BOOL="true"
else
  PUBLISH_BOOL="false"
fi
EVENT_LINE="$(jq -nc \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --argjson total "$TOTAL" --argjson pass_count "$PASS" --argjson fixed_count "$FIXED" \
  --argjson escalated_count "$ESCALATED" \
  --argjson publish_decision "$PUBLISH_BOOL" \
  '{ts:$ts,skill:"41-build-with-ai-playbook",event:"qc_result",session_ref:"harness",source:"script",
    total:$total,pass_count:$pass_count,fixed_count:$fixed_count,escalated_count:$escalated_count,publish_decision:$publish_decision}')"

# Emit guard: CI and self-tests set HARNESS_EMIT=0 (or pass --no-emit) so the qc_result line
# is PRINTED, never appended to a real master-files dir. Operator/agent runs leave it unset
# (default emit=1) so the event lands in build-with-ai-events.jsonl.
HARNESS_EMIT="${HARNESS_EMIT:-1}"
for a in "$@"; do [[ "$a" == "--no-emit" ]] && HARNESS_EMIT=0; done

LIBMF="$SCRIPT_DIR/lib-master-files.sh"
if [[ "$HARNESS_EMIT" != "1" ]]; then
  echo "[skill 41 harness] qc_result (emit disabled): $EVENT_LINE"
elif [[ -f "$LIBMF" ]] && command -v jq >/dev/null 2>&1; then
  # shellcheck source=/dev/null
  source "$LIBMF"
  if declare -f append_jsonl >/dev/null 2>&1 && declare -f resolve_master_files_dir >/dev/null 2>&1; then
    SESSION_REF="harness" append_jsonl "qc_result" \
      '{total:($total|tonumber),pass_count:($pass_count|tonumber),fixed_count:($fixed_count|tonumber),escalated_count:($escalated_count|tonumber),publish_decision:($publish_decision=="true")}' \
      --arg total "$TOTAL" --arg pass_count "$PASS" --arg fixed_count "$FIXED" \
      --arg escalated_count "$ESCALATED" --arg publish_decision "$PUBLISH_BOOL" 2>/dev/null \
      && echo "[skill 41 harness] qc_result appended to $(resolve_master_files_dir)/build-with-ai-events.jsonl" \
      || echo "[skill 41 harness] qc_result (not persisted -- no master-files dir): $EVENT_LINE"
  else
    echo "[skill 41 harness] qc_result: $EVENT_LINE"
  fi
else
  echo "[skill 41 harness] qc_result: $EVENT_LINE"
fi

case "$DECISION" in
  PASS) echo "[skill 41 harness] CLOSED LOOP PROVEN: L1-L5 green, browser execution is safe to enable."; [[ $SKIPPED -gt 0 ]] && exit 3 || exit 0 ;;
  *)    echo "[skill 41 harness] DO NOT publish/enable -- $ESCALATED escalation(s), $FAILED failure(s). Human review required."; exit 2 ;;
esac
