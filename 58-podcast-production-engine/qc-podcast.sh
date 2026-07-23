#!/usr/bin/env bash
#
# qc-podcast.sh
# Podcast Production Engine (Skill 58) — Quality Control gate for the podcast
# production engine installation and key scripts.
#
# This QC gate checks that the critical production scripts exist, are executable,
# parse cleanly (bash -n), and that the gated integration test is present and
# refuses to run without explicit opt-in. It NEVER auto-runs the integration test.
#
# COVERAGE (one line each):
#   A1  podbean_publish.sh exists and passes bash -n
#   A2  generate_podcast_audio.sh exists and passes bash -n
#   A3  generate_cover.sh exists and passes bash -n
#   A4  provision-podcast-client.sh exists and passes bash -n
#   A5  revoke-podcast-client.sh exists and passes bash -n
#   B1  podcast_state.py exists and passes py_compile
#   B2  model_router.py exists and passes py_compile
#   B3  guard-cron-inventory.py exists and passes py_compile
#   I1  podbean-integration-test.sh exists and passes bash -n
#   I2  Integration test refuses unprompted run (opt-in guard)
#
set -euo pipefail

PASS=0; FAIL=0; WARN=0

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$SKILL_DIR/scripts"

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }

assert() {
  if eval "$2" >/dev/null 2>&1; then
    green "  [PASS] $1"
    PASS=$((PASS + 1))
  else
    red "  [FAIL] $1"
    FAIL=$((FAIL + 1))
  fi
}

echo ""
echo "============================================================"
echo "  Podcast Production Engine (Skill 58) — QC Gate"
echo "  Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "============================================================"
echo ""

# --------------------------------------------------- Section A: shell scripts --
echo "-- Section A: Shell scripts (bash -n) --"

SHELL_SCRIPTS=(
  "podbean_publish.sh"
  "generate_podcast_audio.sh"
  "generate_cover.sh"
  "provision-podcast-client.sh"
  "revoke-podcast-client.sh"
  "verify-t1-t9.sh"
)

for script in "${SHELL_SCRIPTS[@]}"; do
  path="$SCRIPTS_DIR/$script"
  assert "$script exists" "[ -f \"$path\" ]"
  if [ -f "$path" ]; then
    assert "$script bash -n" "bash -n \"$path\""
  fi
done

echo ""

# --------------------------------------------------- Section B: Python scripts --
echo "-- Section B: Python scripts (py_compile) --"

PYTHON_SCRIPTS=(
  "podcast_state.py"
  "model_router.py"
  "guard-cron-inventory.py"
)

for script in "${PYTHON_SCRIPTS[@]}"; do
  path="$SCRIPTS_DIR/$script"
  assert "$script exists" "[ -f \"$path\" ]"
  if [ -f "$path" ]; then
    assert "$script py_compile" "python3 -c 'import py_compile; py_compile.compile(\"$path\", doraise=True)'"
  fi
done

echo ""

# ----------------------------------------- Section I: Integration test (gated) --
echo "-- Section I: Podbean integration test (gated, NEVER auto-run) --"

INTEGRATION_TEST="$SCRIPTS_DIR/podbean-integration-test.sh"

assert "podbean-integration-test.sh exists" "[ -f \"$INTEGRATION_TEST\" ]"

if [ -f "$INTEGRATION_TEST" ]; then
  assert "podbean-integration-test.sh bash -n" "bash -n \"$INTEGRATION_TEST\""

  # Verify the opt-in guard: running without --run exits 0 with "SKIPPED".
  echo ""
  echo "  --- Opt-in guard probe: running without --run (should exit 0, not call API) ---"
  # Ensure no PODBEAN_INTEGRATION_TEST is set in the env for this probe.
  if ( unset PODBEAN_INTEGRATION_TEST 2>/dev/null; bash "$INTEGRATION_TEST" > /tmp/podbean-it-guard-out.txt 2>/dev/null ); then
    if grep -qi "SKIPPED" /tmp/podbean-it-guard-out.txt 2>/dev/null; then
      green "  [PASS] Integration test opt-in guard: exits 0 with SKIPPED when not opted in"
      PASS=$((PASS + 1))
    else
      yellow "  [WARN] Integration test exited 0 but did not print SKIPPED (possible output change)"
      WARN=$((WARN + 1))
    fi
  else
    l_exit_code=$?
    red "  [FAIL] Integration test opt-in guard: exited non-zero (${l_exit_code}) without --run flag"
    FAIL=$((FAIL + 1))
  fi
  rm -f /tmp/podbean-it-guard-out.txt

  echo ""
  echo "  NOTE: the integration test (scripts/podbean-integration-test.sh) is NEVER"
  echo "  auto-run by this QC gate. To execute it manually:"
  echo ""
  echo "    PODBEAN_INTEGRATION_TEST=1 bash scripts/podbean-integration-test.sh"
  echo "    # or"
  echo "    bash scripts/podbean-integration-test.sh --run"
  echo ""
  echo "  Ensure PODBEAN_PODCAST_ID points to a TEST channel before running."
  echo ""
fi

# ------------------------------------------------------------------- results --
echo "============================================================"
echo "  QC Gate result: $PASS passed | $FAIL failed | $WARN warnings"
echo "  Finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "============================================================"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
