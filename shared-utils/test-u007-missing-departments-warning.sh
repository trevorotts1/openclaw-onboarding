#!/usr/bin/env bash
# test-u007-missing-departments-warning.sh — U007 verification.
#
# Tests u007_missing_departments_warning() in update-skills.sh: when the
# departments/ directory is ABSENT but .workforce-build-state.json has
# interviewComplete=true, the role-staleness check used to skip SILENTLY (no
# departments to check against). U007 makes that anomaly loud.
#
# Usage:
#   bash shared-utils/test-u007-missing-departments-warning.sh
#
# Pass criteria (all must hold):
#   1. bash -n update-skills.sh passes (AC#1).
#   2. The function is actually invoked in the update flow (not dead code).
#   3. AC#2: missing departments/ + interviewComplete=true -> warning emitted,
#      naming the specific anomaly.
#   4. AC#3: departments/ present -> NO warning (behavior unchanged).
#   5. Edge: missing departments/ + interviewComplete=false -> NO warning.
#   6. Edge: missing departments/ + no state file -> NO warning, no crash.
#
# The function is extracted from update-skills.sh and exercised directly with a
# stubbed `jq`, so the test is hermetic (no real box, no real jq dependency) and
# does not run the full multi-thousand-line update flow.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/update-skills.sh"

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*" >&2; exit 1; }

# ─── GUARD 1: bash -n (AC#1) ─────────────────────────────────────────────────
bash -n "$SCRIPT" || fail "bash -n update-skills.sh failed (AC#1)"
pass "bash -n update-skills.sh passes (AC#1)"

# ─── GUARD 2: the function is wired into the update flow (not dead code) ─────
grep -q 'u007_missing_departments_warning "\${OC_WORKSPACE' "$SCRIPT" \
  || fail "u007_missing_departments_warning is defined but never called in the update flow"
pass "function is invoked in the update flow"

# ─── Extract the function under test ─────────────────────────────────────────
FUNC_SRC="$(sed -n '/^u007_missing_departments_warning() {/,/^}/p' "$SCRIPT")"
[ -n "$FUNC_SRC" ] || fail "could not extract u007_missing_departments_warning from update-skills.sh"

# ─── Hermetic harness: stub jq + temp workspaces ─────────────────────────────
TMPDIR_FIXTURE="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_FIXTURE"' EXIT
STUB_BIN="$TMPDIR_FIXTURE/bin"
mkdir -p "$STUB_BIN"
cat > "$STUB_BIN/jq" <<'STUB'
#!/usr/bin/env bash
# Stub: emit STUB_INTERVIEW_COMPLETE for the interviewComplete query, so the
# test does not depend on the real jq being installed.
printf '%s\n' "${STUB_INTERVIEW_COMPLETE:-false}"
STUB
chmod +x "$STUB_BIN/jq"
export PATH="$STUB_BIN:$PATH"

# Source the extracted function into this shell.
eval "$FUNC_SRC"

# ─── AC#2: missing departments/ + interviewComplete=true -> warning ──────────
ws1="$TMPDIR_FIXTURE/ws1"
mkdir -p "$ws1"
echo '{"interviewComplete": true}' > "$ws1/.workforce-build-state.json"
export STUB_INTERVIEW_COMPLETE=true
out="$(u007_missing_departments_warning "$ws1")"
echo "$out" | grep -qi "WARNING (U007)" || fail "AC#2: expected a U007 warning, got: '$out'"
echo "$out" | grep -qi "departments/ directory is MISSING" \
  || fail "AC#2: warning must name the missing-departments anomaly, got: '$out'"
echo "$out" | grep -qi "interviewComplete=true" \
  || fail "AC#2: warning must reference interviewComplete=true, got: '$out'"
pass "AC#2: missing departments/ + interviewComplete=true -> anomaly warning emitted"

# ─── AC#3: departments/ present -> NO warning (behavior unchanged) ───────────
ws2="$TMPDIR_FIXTURE/ws2"
mkdir -p "$ws2/departments"
echo '{"interviewComplete": true}' > "$ws2/.workforce-build-state.json"
export STUB_INTERVIEW_COMPLETE=true
out="$(u007_missing_departments_warning "$ws2")"
[ -z "$out" ] || fail "AC#3: expected NO warning when departments/ present, got: '$out'"
pass "AC#3: departments/ present -> no warning (behavior unchanged)"

# ─── Edge: missing departments/ + interviewComplete=false -> NO warning ──────
ws3="$TMPDIR_FIXTURE/ws3"
mkdir -p "$ws3"
echo '{"interviewComplete": false}' > "$ws3/.workforce-build-state.json"
export STUB_INTERVIEW_COMPLETE=false
out="$(u007_missing_departments_warning "$ws3")"
[ -z "$out" ] || fail "edge: expected NO warning when interview not complete, got: '$out'"
pass "edge: missing departments/ + interviewComplete=false -> no warning"

# ─── Edge: missing departments/ + no state file -> NO warning, no crash ──────
ws4="$TMPDIR_FIXTURE/ws4"
mkdir -p "$ws4"
out="$(u007_missing_departments_warning "$ws4")"
[ -z "$out" ] || fail "edge: expected NO warning when no state file, got: '$out'"
pass "edge: missing departments/ + no state file -> no warning, no crash"

echo ""
echo "All U007 tests passed."
