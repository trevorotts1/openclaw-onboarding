#!/usr/bin/env bash
# tests/unit/no-cron-doctor-fix.test.sh
#
# D02 regression guard: the three onboarding cron scripts must NEVER run
# `openclaw doctor --fix`. On OpenClaw 2026.10.x it needs exclusive state
# ownership (refuses with "state database is busy" while the gateway is up) and,
# when it does get ownership (gateway booting/down), it takes the offline
# maintenance lock and rewrites config. Cron fires every 15-30 minutes on every
# box, and on Docker boxes `sh -lc` resolves an old image-baked CLI as well.
#
# BEHAVIORAL: runs each real script in an isolated HOME with a fake `openclaw`
# first on PATH that logs argv, then asserts the log has no `doctor` line.
# CONTROL: with the same HOME/PATH, a direct `openclaw` call must land in the
# log (the stub shadows any real CLI), and the script must exit 0 -- a pass with
# a broken instrument or a crashed script would prove nothing. Before the fix the
# very same fixtures logged `openclaw doctor --fix` for all three scripts.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

run_script() {  # $1=label  $2=script path relative to repo
  local label="$1" script="$2" w
  w="$(mktemp -d "${TMPDIR:-/tmp}/no-cron-doctor.XXXXXX")"
  mkdir -p "$w/home/.openclaw/workspace" "$w/bin"
  printf '%s\n' '#!/usr/bin/env bash' 'echo "openclaw $*" >> "$CALL_LOG"' 'exit 0' > "$w/bin/openclaw"
  chmod +x "$w/bin/openclaw"
  # Fixtures: a client build identity (past the "no identity" early exit) and an
  # onboarding state with interview complete.
  printf '%s\n' '{"clientSlug":"acme"}' > "$w/home/.openclaw/workspace/.workforce-build-state.json"
  printf '%s\n' '{"skills":{},"interviewComplete":true}' > "$w/home/.openclaw/workspace/.onboarding-state.json"
  : > "$w/calls.log"
  local rc ctl
  ( cd "$w" && HOME="$w/home" PATH="$w/bin:$PATH" CALL_LOG="$w/calls.log" openclaw control-probe ) >/dev/null 2>&1
  ctl="$(grep -c '^openclaw control-probe' "$w/calls.log")"
  : > "$w/calls.log"
  ( cd "$w" && HOME="$w/home" PATH="$w/bin:$PATH" CALL_LOG="$w/calls.log" \
      timeout 90 bash "$REPO_ROOT/$script" </dev/null >"$w/out" 2>&1 ); rc=$?
  if [[ "$ctl" != 1 ]]; then
    fail "$label: CONTROL -- fake openclaw is not first on PATH, so the doctor check proves nothing"
  elif (( rc != 0 )); then
    fail "$label: CONTROL -- script exited $rc (expected 0): $(tail -3 "$w/out")"
  elif grep -q '^openclaw doctor' "$w/calls.log"; then
    fail "$label: cron script ran 'openclaw $(grep '^openclaw doctor' "$w/calls.log" | head -1 | cut -d' ' -f2-)'"
  else
    pass "$label: exit 0, $(wc -l < "$w/calls.log" | tr -d ' ') openclaw calls, no doctor call"
  fi
  rm -rf "$w"
}

echo "=== no-cron-doctor-fix.test.sh ==="
run_script "resume-workforce-build.sh"    "23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
run_script "watchdog-onboarding-loop.sh"  "scripts/watchdog-onboarding-loop.sh"
run_script "resume-onboarding.sh"         "scripts/resume-onboarding.sh"

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
(( FAIL == 0 ))
