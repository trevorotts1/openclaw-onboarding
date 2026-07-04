#!/usr/bin/env bash
# tests/unit/bounded-resume-cron.test.sh
#
# CI guard: verifies that the onboarding-resume cron mechanism is bounded and
# self-deleting rather than a perpetual token furnace.
#
# Assertion groups:
#   (1) MAX_RUNS_CAP        -- MAX_RUNS_BEFORE_ESCALATE is defined and <= 10
#   (2) HARD_STOP_DELETE    -- past the cap the script calls self_remove_cron + exit 0, not a slow-retry loop
#   (3) NO_FURNACE_LANGUAGE -- resume-onboarding-prompt.txt does NOT contain
#                             "NEVER STOP", "DO NOT ASK PERMISSION", or "EXECUTE IMMEDIATELY"
#   (4) NO_FURNACE_AGENTS_TEMPLATE -- UPDATE PENDING template in install.sh and
#                             update-skills.sh does NOT contain "DO NOT ASK PERMISSION"
#                             or "EXECUTE IMMEDIATELY" in the injected flag block
#   (5) SELF_REMOVE_ON_GATE -- self_remove_cron is called on gate-pass path in resume-onboarding.sh
#   (6) CRON_INTERVAL       -- onboarding-resume cron is registered at */30 (reasonable; not */5 or */1)
#   (7) SINGLE_MODEL        -- resume-onboarding-prompt.txt does NOT instruct fan-out
#                             across "all configured models" or spawn multiple subagents
#
# Exit 0 = all checks pass. Exit 1 = one or more checks failed (CI FAIL).
#
# v12.6.1 / fix/bound-onboarding-resume-furnace

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

RESUME_SH="$REPO_ROOT/scripts/resume-onboarding.sh"
RESUME_PROMPT="$REPO_ROOT/scripts/resume-onboarding-prompt.txt"
INSTALL_SH="$REPO_ROOT/install.sh"
UPDATE_SH="$REPO_ROOT/update-skills.sh"
# v17.0.21: install_onboarding_resume_cron() moved to a shared lib sourced by
# BOTH install.sh and update-skills.sh, so the cron's registration (interval,
# name) now lives here. The interval check (6) scans this file too.
RESUME_CRON_LIB="$REPO_ROOT/lib-onboarding-resume-cron.sh"

echo "=== bounded-resume-cron.test.sh ==="
echo ""

# ---------------------------------------------------------------------------
# (1) MAX_RUNS_CAP: MAX_RUNS_BEFORE_ESCALATE defined and <= 10
# ---------------------------------------------------------------------------
echo "--- (1) MAX_RUNS_CAP: hard cap defined and <= 10 ---"

if [[ ! -f "$RESUME_SH" ]]; then
  fail "1a: resume-onboarding.sh not found at $RESUME_SH"
else
  cap_line="$(grep 'MAX_RUNS_BEFORE_ESCALATE=' "$RESUME_SH" | grep -v '^[[:space:]]*#' | head -1 || true)"
  if [[ -z "$cap_line" ]]; then
    fail "1a: MAX_RUNS_BEFORE_ESCALATE not defined in resume-onboarding.sh"
  else
    cap_val="$(echo "$cap_line" | sed 's/.*MAX_RUNS_BEFORE_ESCALATE=[[:space:]]*//' | grep -o '^[0-9]*' || true)"
    if [[ -z "$cap_val" ]]; then
      fail "1b: MAX_RUNS_BEFORE_ESCALATE value is not a plain integer (got: $cap_line)"
    elif (( cap_val > 10 )); then
      fail "1b: MAX_RUNS_BEFORE_ESCALATE=$cap_val exceeds safe limit of 10 (token furnace risk)"
    else
      pass "1b: MAX_RUNS_BEFORE_ESCALATE=$cap_val (within safe limit of 10)"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# (2) HARD_STOP_DELETE: past cap the script calls self_remove_cron and exits 0,
#     NOT a slow-retry/perpetual-loop path
# ---------------------------------------------------------------------------
echo ""
echo "--- (2) HARD_STOP_DELETE: cap branch calls self_remove_cron + exit 0 ---"

if [[ -f "$RESUME_SH" ]]; then
  # The block that fires when _run_count > MAX_RUNS_BEFORE_ESCALATE must contain
  # self_remove_cron and MUST NOT contain a comment/label saying "NOT self-removing"
  # or "slow-retry" or "never stops".
  cap_block="$(awk '/\(\( _run_count > MAX_RUNS_BEFORE_ESCALATE \)\)/,/^fi$/' "$RESUME_SH" 2>/dev/null | head -60 || true)"

  if [[ -z "$cap_block" ]]; then
    fail "2a: could not extract cap branch from resume-onboarding.sh (pattern not found)"
  else
    if echo "$cap_block" | grep -q 'self_remove_cron'; then
      pass "2a: cap branch calls self_remove_cron"
    else
      fail "2a: cap branch does NOT call self_remove_cron -- cron will never self-delete on hard cap"
    fi

    # These phrases indicate the old perpetual-loop behavior: continuing to dispatch
    # after the cap rather than self-deleting. The negative phrase "No perpetual slow-retry"
    # is fine (it documents the absence of the pattern).
    if echo "$cap_block" | grep -qiE 'NOT self.remov|now slow.retry|never stop.*continu|slow mode.*continuing'; then
      fail "2b: cap branch contains perpetual-loop language (slow-retry/never-stop/NOT-self-removing)"
    else
      pass "2b: cap branch has no perpetual-loop language"
    fi

    if echo "$cap_block" | grep -q 'exit 0'; then
      pass "2c: cap branch exits 0 after escalation (bounded)"
    else
      fail "2c: cap branch does not exit 0 -- may fall through to another dispatch"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# (3) NO_FURNACE_LANGUAGE: resume-onboarding-prompt.txt must not contain
#     the imperative language that drove unbounded autonomous loops
# ---------------------------------------------------------------------------
echo ""
echo "--- (3) NO_FURNACE_LANGUAGE: prompt file lacks unbounded-loop imperatives ---"

if [[ ! -f "$RESUME_PROMPT" ]]; then
  fail "3a: resume-onboarding-prompt.txt not found at $RESUME_PROMPT"
else
  for pattern in "NEVER STOP" "DO NOT ASK PERMISSION" "EXECUTE IMMEDIATELY" "NEVER-STOP"; do
    if grep -qi "$pattern" "$RESUME_PROMPT"; then
      fail "3-$(echo $pattern | tr ' ' '-'): resume-onboarding-prompt.txt contains forbidden phrase: '$pattern'"
    else
      pass "3-$(echo $pattern | tr ' ' '-'): prompt does not contain '$pattern'"
    fi
  done
fi

# ---------------------------------------------------------------------------
# (4) NO_FURNACE_AGENTS_TEMPLATE: UPDATE PENDING blocks in install.sh and
#     update-skills.sh must not inject "DO NOT ASK PERMISSION" or
#     "EXECUTE IMMEDIATELY" into AGENTS.md
# ---------------------------------------------------------------------------
echo ""
echo "--- (4) NO_FURNACE_AGENTS_TEMPLATE: UPDATE PENDING heredoc lacks furnace imperatives ---"

check_update_pending_block() {
  local file="$1"
  local fname
  fname=$(basename "$file")

  # Extract the heredoc / cat block that writes the UPDATE PENDING section.
  # Look for text between the heredoc marker and FLAGCONTENT closing tag.
  local block
  block="$(awk '/FLAGCONTENT$/,/^FLAGCONTENT$/' "$file" 2>/dev/null | head -80 || true)"

  if [[ -z "$block" ]]; then
    # Try alternative: grep context around UPDATE PENDING header
    block="$(grep -A 5 'UPDATE PENDING' "$file" 2>/dev/null | head -20 || true)"
  fi

  for pattern in "DO NOT ASK PERMISSION" "EXECUTE IMMEDIATELY"; do
    if echo "$block" | grep -qi "$pattern"; then
      fail "4-$fname-$(echo $pattern | tr ' ' '-'): $fname UPDATE PENDING block contains '$pattern'"
    else
      pass "4-$fname-$(echo $pattern | tr ' ' '-'): $fname UPDATE PENDING block does not contain '$pattern'"
    fi
  done
}

[[ -f "$INSTALL_SH" ]] && check_update_pending_block "$INSTALL_SH" || fail "4-install.sh: not found"
[[ -f "$UPDATE_SH" ]] && check_update_pending_block "$UPDATE_SH" || fail "4-update-skills.sh: not found"

# ---------------------------------------------------------------------------
# (5) SELF_REMOVE_ON_GATE: gate-pass path calls self_remove_cron
# ---------------------------------------------------------------------------
echo ""
echo "--- (5) SELF_REMOVE_ON_GATE: gate-pass path calls self_remove_cron ---"

if [[ -f "$RESUME_SH" ]]; then
  gate_block="$(awk '/GATE_RC.*==.*0/,/exit 0/' "$RESUME_SH" 2>/dev/null | head -10 || true)"
  if echo "$gate_block" | grep -q 'self_remove_cron'; then
    pass "5a: gate-pass block calls self_remove_cron before exit 0"
  else
    fail "5a: gate-pass block does NOT call self_remove_cron -- cron persists after gate passes"
  fi
fi

# ---------------------------------------------------------------------------
# (6) CRON_INTERVAL: cron is registered at */30 or longer -- not a high-frequency furnace
# ---------------------------------------------------------------------------
echo ""
echo "--- (6) CRON_INTERVAL: cron registered at */30 or longer ---"

# Scan BOTH install.sh and the shared resume-cron lib (the cron registration
# now lives in the lib; install.sh only sources+calls it). At least one file
# must carry an onboarding-resume interval line, and every such line must be
# */15 or slower.
_interval_seen=0
for _f in "$INSTALL_SH" "$RESUME_CRON_LIB"; do
  [[ -f "$_f" ]] || continue
  interval_lines="$(grep "onboarding-resume" "$_f" | grep '\*/[0-9]' || true)"
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    _interval_seen=1
    interval="$(echo "$line" | grep -o '\*/[0-9]*' | head -1 || true)"
    val="$(echo "$interval" | grep -o '[0-9]*' || true)"
    if [[ -z "$val" ]]; then
      pass "6: could not parse interval from line ($(basename "$_f")); skipping: $line"
    elif (( val < 15 )); then
      fail "6: onboarding-resume cron interval $interval in $(basename "$_f") is faster than */15 -- high-frequency furnace risk"
    else
      pass "6: onboarding-resume cron interval $interval in $(basename "$_f") (>= */15, safe)"
    fi
  done <<< "$interval_lines"
done
if [[ "$_interval_seen" -eq 0 ]]; then
  fail "6: no onboarding-resume interval line found in install.sh or lib-onboarding-resume-cron.sh -- cron registration missing?"
fi

# ---------------------------------------------------------------------------
# (7) SINGLE_MODEL: prompt does not instruct fan-out across all models or
#     spawning 5+ subagents
# ---------------------------------------------------------------------------
echo ""
echo "--- (7) SINGLE_MODEL: prompt does not instruct multi-model fan-out ---"

if [[ -f "$RESUME_PROMPT" ]]; then
  # Each pattern below: a positive instruction to fan-out. Prohibitions ("Do NOT fan-out")
  # are desirable and must not trip the check.
  # Strategy: check for lines that contain the pattern WITHOUT a preceding "NOT" or "Do NOT".
  check_no_positive_fanout() {
    local pattern="$1" label="$2"
    # Find lines with the pattern, then exclude lines that have NOT/Do NOT nearby (within the same line).
    local hits
    hits="$(grep -iE "$pattern" "$RESUME_PROMPT" | grep -viE 'do not|NOT spawn|NOT fan|avoid|prohibit' || true)"
    if [[ -n "$hits" ]]; then
      fail "7-${label}: resume prompt appears to instruct fan-out (check for false-positive): $(echo "$hits" | head -1)"
    else
      pass "7-${label}: prompt does not instruct '$pattern' (or only prohibits it)"
    fi
  }

  check_no_positive_fanout "fan.out across all" "fan-out-across-all"
  check_no_positive_fanout "spawn.*across.*all.*model" "spawn-across-all-models"
  check_no_positive_fanout "use all configured models" "use-all-configured-models"
  check_no_positive_fanout "5\+ subagents" "5plus-subagents"
  check_no_positive_fanout "spawn 5 subagents" "spawn-5-subagents"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi

echo "PASS: all bounded-resume-cron checks pass"
exit 0
