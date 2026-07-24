#!/usr/bin/env bash
# qc-agent.sh — Independent QC agent for OpenClaw skill installs.
#
# Wave 5.1 of the post-analysis remediation. Phase 13 identified the QC
# framework's core flaw: the installer scores its own work (self-referential
# blindness). This script is meant to be invoked AFTER a skill install by an
# independent QC sub-agent — it does NOT trust the installer's
# .onboarding-status file. It re-derives PASS/FAIL from its own checks.
#
# U122 (STAGE 1): per-skill warn visibility. The QC agent previously read ONLY
# the exit code of each per-skill qc-*.sh, inheriting the blindness of all 37
# warn-only checks. STAGE 1 parses the per-skill Result line to surface
# pass/fail/warn counts in the JSON report — without changing the agent's own
# pass/fail outcome (QC_FAIL_ON_WARN is NOT set). STAGE 2: fleet measurement.
#
# Usage:
#   bash scripts/qc-agent.sh <skill-folder-name>
#
# Example:
#   bash scripts/qc-agent.sh 23-ai-workforce-blueprint
#
# What it does:
#   1. Verifies the skill folder exists with required files (SKILL.md,
#      INSTALL.md, QC.md, qc-*.sh)
#   2. Runs the skill's qc-*.sh script (the mechanical-check script the
#      install agent wrote). Captures exit code and stderr/stdout. U122:
#      additionally parses the per-skill Result line for warn visibility.
#   3. Reads the QC.md rubric — checks the agent followed format (10-point
#      rubric, 5-loop retry cap, self-audit checklist present).
#   4. Reports a structured JSON result: {skill, pass, score_estimate,
#      script_exit, failures: [...], escalate: bool, skill_pass, skill_fail,
#      skill_warn}
#
# What it does NOT do:
#   - Score the rubric itself (that's the install agent's job)
#   - Trust the install agent's score (we just check the rubric is PRESENT
#     and the script EXITS ZERO — both must be true to pass)
#   - Need the install agent to set any flag file — purely external check.
#   - Fail on per-skill warnings in STAGE 1 (observation only)

set -u

SKILL="${1:-}"
if [ -z "$SKILL" ]; then
  echo "usage: $0 <skill-folder-name>"
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# U073 (STAGE 1): shared assert/warn/verdict helpers. U122: qc_parse_skill_verdict.
# shellcheck source=../lib-qc-shared.sh
. "$ROOT/lib-qc-shared.sh"

SKILL_DIR="$ROOT/$SKILL"

PASS=0
FAIL=0
FAILURES=()

red()    { printf "\033[31m%s\033[0m\n" "$1" >&2; }
green()  { printf "\033[32m%s\033[0m\n" "$1" >&2; }
yellow() { printf "\033[33m%s\033[0m\n" "$1" >&2; }
blue()   { printf "\033[34m%s\033[0m\n" "$1" >&2; }

check() {
  local id="$1"; local desc="$2"; local cmd="$3"
  if eval "$cmd" >/dev/null 2>&1; then
    green "  ✓ $id  $desc"
    PASS=$((PASS+1))
  else
    red "  ✗ $id  $desc"
    FAIL=$((FAIL+1))
    FAILURES+=("$id $desc")
  fi
}

blue "── QC Agent — $SKILL ──"

# 1. Skill folder exists with required files
check "1.1" "skill folder exists" "[ -d \"$SKILL_DIR\" ]"
check "1.2" "SKILL.md present"     "[ -f \"$SKILL_DIR/SKILL.md\" ]"
check "1.3" "INSTALL.md present"   "[ -f \"$SKILL_DIR/INSTALL.md\" ]"
check "1.4" "QC.md present"        "[ -f \"$SKILL_DIR/QC.md\" ]"

# Find the qc-*.sh script (skill name slug usually used)
QC_SCRIPT=""
for candidate in "$SKILL_DIR"/qc-*.sh "$ROOT/scripts/qc-${SKILL}.sh"; do
  if [ -f "$candidate" ]; then
    QC_SCRIPT="$candidate"
    break
  fi
done

check "1.5" "qc-*.sh script discovered" "[ -n \"$QC_SCRIPT\" ] && [ -f \"$QC_SCRIPT\" ]"

# 2. QC.md follows the v9.3.0 rubric format (10-point grid + self-audit + retry cap)
if [ -f "$SKILL_DIR/QC.md" ]; then
  check "2.1" "QC.md contains 10-point rubric" \
    "grep -q -E 'out of 10|10\\.0' \"$SKILL_DIR/QC.md\""
  check "2.2" "QC.md contains self-audit checklist" \
    "grep -q -i -E 'self.audit|self.check|self.audit checklist' \"$SKILL_DIR/QC.md\""
  check "2.3" "QC.md contains failure loop / retry cap" \
    "grep -q -i -E '5.loop|five.loop|retry cap|escalat' \"$SKILL_DIR/QC.md\""
fi

# 3. Run the qc-*.sh script and capture result. Exit ZERO is required.
SCRIPT_EXIT="n/a"
SKILL_PASS="n/a"
SKILL_FAIL="n/a"
SKILL_WARN="n/a"
if [ -n "$QC_SCRIPT" ] && [ -f "$QC_SCRIPT" ]; then
  blue "── Running $QC_SCRIPT ──"
  LOG_FILE="/tmp/qc-agent-${SKILL//\//_}.log"
  bash "$QC_SCRIPT" >"$LOG_FILE" 2>&1
  SCRIPT_EXIT=$?
  if [ $SCRIPT_EXIT -eq 0 ]; then
    green "  ✓ 3.1  qc-*.sh exited 0"
    PASS=$((PASS+1))
  else
    red "  ✗ 3.1  qc-*.sh exited $SCRIPT_EXIT  (log: $LOG_FILE)"
    FAIL=$((FAIL+1))
    FAILURES+=("qc script exited $SCRIPT_EXIT")
  fi
  # U122 (STAGE 1): parse per-skill Result line for warn visibility.
  if qc_parse_skill_verdict "$LOG_FILE"; then
    SKILL_PASS="$QC_SKILL_PASS"
    SKILL_FAIL="$QC_SKILL_FAIL"
    SKILL_WARN="$QC_SKILL_WARN"
    blue "  info per-skill counts — $SKILL_PASS passed | $SKILL_FAIL failed | $SKILL_WARN warnings (STAGE 1: observation only)"
  else
    yellow "  warn could not parse per-skill Result line from $LOG_FILE"
  fi
fi

# 4. Verify the install agent did NOT set .onboarding-status to PASS without
#    actually running the QC script. (Wave 5.1 — don't trust the file.)
STATUS_FILE="$ROOT/.onboarding-status"
if [ -f "$STATUS_FILE" ]; then
  if grep -q -E "PASS|pass|done" "$STATUS_FILE" 2>/dev/null && [ "$SCRIPT_EXIT" != "0" ]; then
    red "  ✗ 4.1  .onboarding-status claims PASS but qc-*.sh exited non-zero — install agent self-reported a falsely green state"
    FAIL=$((FAIL+1))
    FAILURES+=("install agent lied about status")
  else
    green "  ✓ 4.1  .onboarding-status not contradicting external check"
    PASS=$((PASS+1))
  fi
fi

blue ""
blue "════════════════════════════════════════════════════════════"

# Output structured JSON for the dispatcher / Telegram escalation
TOTAL=$((PASS + FAIL))
if [ $FAIL -eq 0 ]; then
  ESCALATE="false"
  RESULT="PASS"
else
  ESCALATE="true"
  RESULT="FAIL"
fi

FAILURES_JSON="[]"
if [ ${#FAILURES[@]} -gt 0 ]; then
  FAILURES_JSON="["
  for i in "${!FAILURES[@]}"; do
    sep=""
    [ $i -gt 0 ] && sep=","
    FAILURES_JSON+="${sep}\"${FAILURES[$i]//\"/\\\"}\""
  done
  FAILURES_JSON+="]"
fi

cat <<EOF
{
  "skill":         "$SKILL",
  "result":        "$RESULT",
  "checks_passed": $PASS,
  "checks_total":  $TOTAL,
  "script_exit":   "$SCRIPT_EXIT",
  "failures":      $FAILURES_JSON,
  "escalate":      $ESCALATE,
  "skill_pass":    "$SKILL_PASS",
  "skill_fail":    "$SKILL_FAIL",
  "skill_warn":    "$SKILL_WARN"
}
EOF

# Exit codes: 0 = PASS, 1 = FAIL (any check), 2 = misuse / can't find skill
# U073 (STAGE 1): verdict routed through the shared helper. QC_WARN stays 0
# (this agent has no warn-only checks) and QC_FAIL_ON_WARN is NOT set, so the
# exit code depends only on QC_FAIL — byte-for-byte the pre-U073 behavior.
QC_PASS=$PASS QC_FAIL=$FAIL QC_WARN=0
qc_verdict "qc-agent:$SKILL" >/dev/null
[ $FAIL -eq 0 ] && exit 0 || exit 1
