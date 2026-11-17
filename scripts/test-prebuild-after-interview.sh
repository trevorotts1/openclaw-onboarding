#!/usr/bin/env bash
# test-prebuild-after-interview.sh — BU-55 acceptance gate.
#
# The prebuild can finish AFTER the interview; the "on first answer" deferral
# is retired. EXACTLY the three cases the build spec names:
#
#   C1  interviewComplete=true with a FAILED foundation (.status="failed")
#       + consent + --apply  -> exit 0 and standardPrebuild.status == "done".
#   C2  interviewComplete=true with the foundation already DONE -> exit 4
#       (nothing left to prebuild).
#   C3  a fresh state run with --standard-first-onboarding on-first-answer
#       -> exit 0, departments exist on disk, and the state records
#          standardFirstOnboarding="at-onboarding" (the retired flag does not
#          defer anything).
#
# HERMETIC: sandboxed $HOME, scratch company dir, scratch build-state. Writes
# NOTHING under the real ~/.openclaw, ~/clawd, or any live Command Center db
# (same explicit-signal-only discipline as test-prebuild-standard.sh).
#
# STANDARD_FIRST_ONBOARDING=1 arms the rollback flag the driver requires;
# OPENCLAW_PLATFORM defaults to the host platform for deterministic resolution.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DRIVER="$REPO_ROOT/scripts/prebuild-standard-workforce.sh"

export STANDARD_FIRST_ONBOARDING=1
export OPENCLAW_PLATFORM="${OPENCLAW_PLATFORM:-mac}"

PASS=0
FAIL=0
good() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL: $1" >&2; }

if [ ! -f "$DRIVER" ]; then
  bad "driver not found at $DRIVER"
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

CONSENT="$TMP/consent.json"
printf '{"decision":"prebuild","source":"operator-prebuild","decidedAt":"2026-08-04T12:00:00Z","decidedBy":"test-operator","sessionId":"sess-test"}\n' > "$CONSENT"

new_case() {  # $1 = case tag -> sets SANDBOX_HOME/COMPANY/STATE and makes dirs
  SANDBOX_HOME="$TMP/$1/home"
  COMPANY="$SANDBOX_HOME/clawd/zero-human-company/scratch-after-interview"
  STATE="$TMP/$1/state.json"
  mkdir -p "$COMPANY/departments" "$TMP/$1"
}

run_driver() {
  HOME="$SANDBOX_HOME" bash "$DRIVER" "$@"
}

# ── C1: finished interview, failed foundation -> completes ───────────────────
new_case c1
printf '{"buildType":"standard-first","interviewComplete":true,"standardPrebuild":{"status":"failed"}}\n' > "$STATE"
run_driver --operator-consent-file "$CONSENT" \
  --departments-dir "$COMPANY/departments" --company-slug "scratch-after-interview" \
  --build-state-file "$STATE" --apply --json \
  > "$TMP/c1.json" 2>"$TMP/c1.err"
RC=$?
STATUS=$(python3 -c "import json;sp=json.load(open('$STATE')).get('standardPrebuild');print(sp.get('status') if isinstance(sp,dict) else None)" 2>/dev/null)
if [ "$RC" -eq 0 ] && [ "$STATUS" = "done" ]; then
  good "C1: failed foundation completes after the interview (rc=0, status=done)"
else
  bad "C1: expected rc=0 + status=done, got rc=$RC status=$STATUS (see $TMP/c1.err)"
fi

# ── C2: finished interview, foundation already done -> refuse ────────────────
new_case c2
printf '{"buildType":"standard-first","interviewComplete":true,"standardPrebuild":{"status":"done"}}\n' > "$STATE"
run_driver --operator-consent-file "$CONSENT" \
  --departments-dir "$COMPANY/departments" --company-slug "scratch-after-interview" \
  --build-state-file "$STATE" --apply --json \
  > "$TMP/c2.json" 2>"$TMP/c2.err"
RC=$?
if [ "$RC" -eq 4 ]; then
  good "C2: refuses when the foundation is already done (rc=4)"
else
  bad "C2: expected rc=4, got $RC (see $TMP/c2.err)"
fi

# ── C3: retired on-first-answer flag -> prebuilds now ────────────────────────
new_case c3
printf '{}\n' > "$STATE"
run_driver --operator-consent-file "$CONSENT" \
  --departments-dir "$COMPANY/departments" --company-slug "scratch-after-interview" \
  --build-state-file "$STATE" --standard-first-onboarding on-first-answer --apply --json \
  > "$TMP/c3.json" 2>"$TMP/c3.err"
RC=$?
N_DEPTS=$(find "$COMPANY/departments" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
TIMING=$(python3 -c "import json;print(json.load(open('$STATE')).get('standardFirstOnboarding'))" 2>/dev/null)
if [ "$RC" -eq 0 ] && [ "$N_DEPTS" -ge 1 ] && [ "$TIMING" = "at-onboarding" ]; then
  good "C3: retired on-first-answer prebuilds now (rc=0, $N_DEPTS dept dirs, timing=at-onboarding)"
else
  bad "C3: expected rc=0 + dept dirs + timing=at-onboarding, got rc=$RC dirs=$N_DEPTS timing=$TIMING (see $TMP/c3.err)"
fi

echo "=============================================="
echo "test-prebuild-after-interview.sh: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
