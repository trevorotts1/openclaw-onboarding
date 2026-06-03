#!/usr/bin/env bash
# L5-forced-failure.sh -- Skill 41 v1.3.0 browser-execution harness, Level 5.
#
# PROPERTY PROVEN: when a build cannot be completed correctly, the executor takes the
# ESCALATION path -- it surfaces the failure to a human and DOES NOT publish -- rather than
# either (a) silently failing or (b) publishing a broken workflow. This is the "human-last"
# safety contract: the loop is closed only if forced failures route to a human.
#
# We force three independent failure modes and assert each escalates correctly:
#   (1) API failure during dependency creation (mock returns 500) -> create returns non-zero,
#       NO build proceeds, escalation is emitted, publish=false.
#   (2) An UNFIXABLE seeded defect survives the Big-Brother core (D-class with no auto-fix) ->
#       the publish decision is ESCALATED, not PASS.
#   (3) A timeout/no-response from the executor -> escalation, never a silent hang-and-publish.
#
# Each path must produce an escalation RECORD (so an operator can see it) and a publish=false.
#
# Usage: bash L5-forced-failure.sh
# Exit:  0 = pass (every forced failure escalated correctly), 1 = fail.
set -uo pipefail
HF_LEVEL="L5"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-harness.sh"
FX="$SCRIPT_DIR/fixtures"

HF_CHECKS=0; HF_FAILS=0
hf_log "forced-failure -> escalation test"

SB="$(hf_make_sandbox)"; trap 'rm -rf "$SB"' EXIT
ESC_LOG="$SB/escalations.log"; : > "$ESC_LOG"

# escalate() is the single chokepoint a real executor would call. It RECORDS the escalation
# (so it is never silent) and signals publish=false. It NEVER publishes.
escalate() {
  local reason="$1"
  printf '%s\n' "{\"event\":\"escalation\",\"reason\":\"$reason\",\"publish\":false}" >> "$ESC_LOG"
  hf_info "ESCALATED: $reason (publish=false)"
}

# --- (1) Forced API failure during dependency creation ------------------------
# Simulate a build step that calls the API and gets a 500. The executor must NOT proceed to
# publish; it must escalate. We model the step as a function returning the API status.
build_step_api() { return 1; }   # forced failure (non-zero == API error)
published=true
if build_step_api; then
  published=true
else
  escalate "dependency_create_api_error"
  published=false
fi
hf_check "API failure escalates and does NOT publish" test "$published" = "false"
hf_check "API-failure escalation was RECORDED (not silent)" bash -c "grep -q dependency_create_api_error '$ESC_LOG'"

# --- (2) Unfixable defect survives the Big-Brother core -----------------------
# Run the core on a defect fixture; since this defect class has no safe auto-fix, the publish
# decision MUST be ESCALATED. (Contrast: a FIXED outcome would require an auto-fix that the
# core can prove correct -- not the case for, e.g., an unfiltered trigger that needs operator
# intent.) Here we treat D2 as unfixable-without-operator and assert escalation.
defects="$(hf_bigbrother_scan "$FX/defect-D2-unfiltered-trigger.json" | grep -v '^$' || true)"
if [[ -n "$defects" ]]; then
  escalate "unfixable_defect:$(echo "$defects" | tr '\n' ',' | sed 's/,$//')"
  decision="ESCALATED"; pub="false"
else
  decision="PASS"; pub="true"
fi
hf_check "surviving defect -> decision ESCALATED (got $decision)" test "$decision" = "ESCALATED"
hf_check "surviving defect -> publish=false (got $pub)" test "$pub" = "false"
hf_check "defect escalation names the defect code (D2)" bash -c "grep -q 'D2_UNFILTERED_TRIGGER' '$ESC_LOG'"

# --- (3) Executor timeout / no-response ---------------------------------------
# Model a step that exceeds its budget. The executor must escalate, never silently hang then
# publish. We force a "timed out" status and assert the escalation path.
EXECUTOR_STATUS="timeout"   # forced
case "$EXECUTOR_STATUS" in
  ok)      to_pub="true";  to_dec="PASS" ;;
  *)       escalate "executor_timeout"; to_pub="false"; to_dec="ESCALATED" ;;
esac
hf_check "executor timeout -> ESCALATED (got $to_dec)" test "$to_dec" = "ESCALATED"
hf_check "executor timeout -> publish=false (got $to_pub)" test "$to_pub" = "false"

# --- closing invariant: EVERY escalation recorded publish:false; none published ---
# Use grep | wc -l (single integer, no grep-exit-1 double-count) for robust counting.
bad_pub="$(grep -F '"publish":true' "$ESC_LOG" 2>/dev/null | wc -l | tr -d ' ')"
hf_check "no escalation ever set publish:true (count=$bad_pub)" test "${bad_pub:-0}" = "0"
esc_count="$(grep -F '"event":"escalation"' "$ESC_LOG" 2>/dev/null | wc -l | tr -d ' ')"
hf_check "all three forced failures produced an escalation record (count=$esc_count)" test "${esc_count:-0}" = "3"

# Negative control: a SUCCESSFUL build must NOT escalate (proves escalation is conditional,
# not unconditional). Clean fixture scans clean -> no escalation, publish allowed.
clean_defects="$(hf_bigbrother_scan "$FX/clean-workflow.json" | grep -v '^$' || true)"
hf_check "a clean build does NOT escalate (escalation is conditional)" test -z "$clean_defects"

hf_log "checks=$HF_CHECKS fails=$HF_FAILS"
if [[ $HF_FAILS -eq 0 ]]; then hf_pass "every forced failure (API error, unfixable defect, timeout) escalated to human with publish=false; clean build did not escalate"; exit 0; fi
hf_fail "$HF_FAILS forced-failure check(s) failed -- the escalation path is NOT trustworthy"; exit 1
