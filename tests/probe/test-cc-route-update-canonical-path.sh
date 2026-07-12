#!/usr/bin/env bash
# ============================================================
#  test-cc-route-update-canonical-path.sh — P1-07 (c)2 regression lock
#
#  Proves cc_route_update_through_canonical_path() (D5's build+restart step,
#  32-command-center-setup/scripts/run-full-install.sh) actually:
#    (A) routes tier 1 through the freshly-pulled CC's own update.sh, and
#    (B) on the oldest boxes (neither update.sh nor atomic-deploy.sh present,
#        tier 3), snapshots .next BEFORE building and REVERTS it when the
#        post-update BUILD_ID+health assertion fails — never leaves a
#        half-updated CC standing.
#
#  This extracts the ACTUAL function bodies from run-full-install.sh (not a
#  reimplementation) via line-range sed, so a future edit to the real
#  function is exercised by this test, not a stale copy of it.
#
#  Nothing here touches a real box, real pm2, or the real network — pm2/curl
#  are stubbed on PATH inside an isolated temp sandbox.
#
#  EXIT CODES: 0 all passed, 1 one or more failed.
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC="$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh"
FAIL_COUNT=0
PASS_COUNT=0

_pass() { echo "  PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
_fail() { echo "  FAIL: $1" >&2; FAIL_COUNT=$((FAIL_COUNT + 1)); }
_section() { echo ""; echo "=== $1 ==="; }

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT

# ---- extract the real function bodies by anchor, not a hardcoded line range
# (line numbers drift; anchors on the function's own `^name() {` / next
# top-level marker do not). ----
UNIT="$SANDBOX/unit-under-test.sh"
_extract() {
  local start_pat="$1" end_pat="$2"
  awk "/$start_pat/{flag=1} flag{print} /$end_pat/{if(flag && \$0 !~ /$start_pat/) exit}" "$SRC"
}

{
  echo '#!/usr/bin/env bash'
  awk '/^cc_pm2_start_canonical\(\) \{/{flag=1} flag{print} /^}/{if(flag){print ""; exit}}' "$SRC"
  awk '/^_cc_mtime\(\) \{/{print; exit}' "$SRC"
  echo ""
  awk '/^cc_ensure_fresh_build\(\) \{/{flag=1} flag{print} flag && /^}/{exit}' "$SRC"
  echo ""
  awk '/^_cc_resolve_bash4\(\) \{/{flag=1} flag{print} flag && /^}/{exit}' "$SRC"
  echo ""
  awk '/^cc_route_update_through_canonical_path\(\) \{/{flag=1} flag{print} flag && /^}/{exit}' "$SRC"
} > "$UNIT"

if ! bash -n "$UNIT"; then
  _fail "extracted unit-under-test.sh has a syntax error — extraction anchors likely drifted from the source"
  echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
  exit 1
fi
_pass "extracted cc_route_update_through_canonical_path + deps from the real run-full-install.sh, syntax OK"

# Guard against a VACUOUS extraction: an empty (or anchor-drifted) file is
# STILL valid bash syntax (bash -n passes on an empty script), which would
# let every scenario below pass trivially off a missing function (RC=127 is
# non-zero; a function that never runs never touches .next either) — see the
# P1-07 fix-loop finding #3. Fail loudly here, before any scenario runs, if
# the function definition did not actually land in the extracted unit.
if ! grep -q '^cc_route_update_through_canonical_path() {' "$UNIT"; then
  _fail "extracted unit-under-test.sh does NOT define cc_route_update_through_canonical_path — extraction anchors drifted (vacuous extraction); every downstream scenario assertion would be meaningless"
  echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
  exit 1
fi
_pass "extracted unit defines cc_route_update_through_canonical_path (not a vacuous extraction)"

# ---- shared fakes: log/state_set/pm2/curl/npm, isolated per scenario ----
_new_sandbox_box() {
  local box="$1"
  rm -rf "$box"; mkdir -p "$box/bin" "$box/dashboard"
  DASHBOARD_DIR="$box/dashboard"
  DASHBOARD_PORT=4000
  CC_PM2_NAME="blackceo-command-center"
  LOG_FILE="$box/install.log"
  STATE_FILE="$box/state.json"
  echo '{}' > "$STATE_FILE"
  : > "$box/state-calls.log"
  : > "$box/pm2-calls.log"
}

# fake `log` + `state_set` (the real ones live outside the extracted unit)
log() { printf '[%s] %s\n' "$1" "$2" >> "$LOG_FILE"; }
state_set() { printf '%s\n' "$1" >> "$SANDBOX_STATE_CALLS"; }

_write_fake_bins() {
  local bindir="$1" health_code="$2"
  cat > "$bindir/pm2" <<EOF
#!/usr/bin/env bash
echo "pm2 \$*" >> "$SANDBOX_PM2_CALLS"
if [ "\$1" = "restart" ]; then exit 0; fi
if [ "\$1" = "delete" ]; then exit 0; fi
if [ "\$1" = "save" ]; then exit 0; fi
if [ "\$1" = "start" ]; then exit 0; fi
if [ "\$1" = "list" ]; then echo "$CC_PM2_NAME"; exit 0; fi
exit 0
EOF
  chmod +x "$bindir/pm2"
  cat > "$bindir/curl" <<EOF
#!/usr/bin/env bash
# emulate: curl -fsS -o /dev/null -w '%{http_code}' <url>
printf '%s' "$health_code"
[ "$health_code" = "200" ] && exit 0 || exit 22
EOF
  chmod +x "$bindir/curl"
  cat > "$bindir/npm" <<'EOF'
#!/usr/bin/env bash
# emulate a REAL `npm run build`: a real Next.js build CLOBBERS .next (wipes
# the old bundle, including whatever markers lived in it, and writes a fresh
# BUILD_ID). This is deliberate, not incidental — it is what makes the
# tier-3 "old marker restored" assertion in Scenario B mean something: if
# npm were a no-op that never touched .next (as a prior version of this
# stub was), the assertion would pass whether or not the revert code path
# actually ran. cc_ensure_fresh_build (the caller) invokes this via
# `cd "$dir" && npm run build`, so $PWD is the checkout being built.
if [ "$1" = "run" ] && [ "$2" = "build" ]; then
  rm -rf .next
  mkdir -p .next
  date +%s > .next/BUILD_ID
fi
exit 0
EOF
  chmod +x "$bindir/npm"
}

# ─── Scenario A: tier 1 — update.sh present in the freshly-pulled checkout ──
_section "Scenario A — tier 1 routes through the freshly-pulled CC's own update.sh"
BOXA="$SANDBOX/boxA"; _new_sandbox_box "$BOXA"
SANDBOX_STATE_CALLS="$BOXA/state-calls.log"
SANDBOX_PM2_CALLS="$BOXA/pm2-calls.log"
_write_fake_bins "$BOXA/bin" "200"
mkdir -p "$DASHBOARD_DIR/.next"
cat > "$DASHBOARD_DIR/update.sh" <<'EOF'
#!/usr/bin/env bash
# fake update.sh: proves it was invoked with CC_APP_DIR pointed at the
# freshly-pulled checkout, then produces a fresh BUILD_ID. Writes its
# call-log next to the checkout (not into a var only the outer test knows)
# so it works purely from the env vars update.sh is actually invoked with.
echo "invoked CC_APP_DIR=$CC_APP_DIR CC_PORT=$CC_PORT" >> "$(dirname "$CC_APP_DIR")/update-sh-calls.log"
sleep 1
date +%s > "$CC_APP_DIR/.next/BUILD_ID"
exit 0
EOF
chmod +x "$DASHBOARD_DIR/update.sh"

source "$UNIT"
PATH="$BOXA/bin:$PATH" cc_route_update_through_canonical_path
RC=$?
if [ "$RC" -eq 0 ] && [ -f "$BOXA/update-sh-calls.log" ] && grep -q "CC_APP_DIR=$DASHBOARD_DIR" "$BOXA/update-sh-calls.log"; then
  _pass "tier 1: update.sh invoked with CC_APP_DIR=freshly-pulled checkout, function returned 0 (green)"
else
  _fail "tier 1 did not invoke update.sh correctly (rc=$RC); update-sh-calls.log: $(cat "$BOXA/update-sh-calls.log" 2>/dev/null || echo MISSING)"
fi
if grep -q '"true"\|true' "$SANDBOX_STATE_CALLS" 2>/dev/null && grep -q "commandCenterLastUpdateVerified" "$SANDBOX_STATE_CALLS" 2>/dev/null; then
  _pass "tier 1: state_set stamped commandCenterLastUpdateVerified = true"
else
  _fail "tier 1: state_set was not called with the expected verified=true stamp: $(cat "$SANDBOX_STATE_CALLS" 2>/dev/null)"
fi

# ─── Scenario B: THE FAIL-FIRST CASE — tier 3 (no update.sh, no
# atomic-deploy.sh) with a build that reports success but health check FAILS.
# This is EXACTLY the old bug class (D5's original bare `cc_ensure_fresh_build`
# + `pm2 restart` had NO health check and NO rollback at all — a broken build
# shipped straight to production). Proves this against the PRE-FIX shape too:
# with the old code (no post-check / no snapshot-revert), this scenario would
# leave the box on a build that never got verified healthy. With the fix,
# the function must detect the failed health check and revert .next to the
# pre-update snapshot. ───────────────────────────────────────────────────────
_section "Scenario B — tier 3 (legacy fallback) reverts .next when the post-update health check fails"
BOXB="$SANDBOX/boxB"; _new_sandbox_box "$BOXB"
SANDBOX_STATE_CALLS="$BOXB/state-calls.log"
SANDBOX_PM2_CALLS="$BOXB/pm2-calls.log"
_write_fake_bins "$BOXB/bin" "503"   # health check FAILS — server unhealthy after the "build"

# Simulate a box with a PRIOR good build (this is what must be preserved).
mkdir -p "$DASHBOARD_DIR/.next"
echo "OLD_BUILD_ID_MARKER" > "$DASHBOARD_DIR/.next/BUILD_ID"
echo "old-build-canary-file" > "$DASHBOARD_DIR/.next/CANARY_MARKER_OLD"

# `npm run build` is invoked BY cc_ensure_fresh_build via `( cd "$dir" && npm
# run build ... )`; our fake npm (shared _write_fake_bins, above) emulates a
# REAL build: it CLOBBERS .next — deletes CANARY_MARKER_OLD and the old
# BUILD_ID, then writes a brand-new BUILD_ID with a fresh mtime — before
# exiting 0. This is deliberate: it means the "old marker restored" assertion
# below can ONLY pass if the tier-3 revert genuinely runs and copies the
# pre-update snapshot back — a no-op npm (which never touches .next) would
# let that assertion pass whether or not the revert code executed, which is
# exactly the gap the P1-07 fix-loop judge found. Force a source file newer
# than .next/BUILD_ID so cc_ensure_fresh_build decides a rebuild is needed
# and calls `npm run build`.
mkdir -p "$DASHBOARD_DIR/src"
sleep 1
touch "$DASHBOARD_DIR/src/marker.ts"

if ! declare -F cc_route_update_through_canonical_path >/dev/null 2>&1; then
  _fail "tier 3: cc_route_update_through_canonical_path is not a defined function before invocation — sourcing $UNIT failed silently"
fi
source "$UNIT"
if ! declare -F cc_route_update_through_canonical_path >/dev/null 2>&1; then
  _fail "tier 3: cc_route_update_through_canonical_path was NOT defined after sourcing $UNIT — a missing/renamed function would make every RC-based assertion below pass vacuously (RC=127 is non-zero; a never-run function never touches .next)"
fi
PATH="$BOXB/bin:$PATH" cc_route_update_through_canonical_path
RC=$?

if [ "$RC" -ne 0 ]; then
  _pass "tier 3: function correctly reports non-zero when health check fails post-update"
else
  _fail "tier 3: function reported success (rc=0) despite a failing health check — regression of the P1-07 invariant"
fi

# Tighten: require the function's OWN tier-3 revert log line, not just RC!=0
# and a surviving marker file — a missing function (RC=127, .next untouched
# because npm was never invoked at all) must NOT be able to masquerade as a
# pass on these lines. With the clobbering npm fake above, CANARY_MARKER_OLD
# only exists post-call if the revert genuinely restored the snapshot.
if grep -q "tier-3 post-update assertion FAILED" "$LOG_FILE" 2>/dev/null \
   && grep -q "reverted .next to the pre-update snapshot" "$LOG_FILE" 2>/dev/null; then
  _pass "tier 3: log confirms the tier-3 revert code path actually executed (BUILD_ID/health assertion failed -> manual revert ran)"
else
  _fail "tier 3: expected tier-3 revert log lines not found in $LOG_FILE — the revert code path may not have run at all: $(cat "$LOG_FILE" 2>/dev/null)"
fi

if [ -f "$DASHBOARD_DIR/.next/CANARY_MARKER_OLD" ] \
   && [ "$(cat "$DASHBOARD_DIR/.next/CANARY_MARKER_OLD" 2>/dev/null)" = "old-build-canary-file" ] \
   && [ "$(cat "$DASHBOARD_DIR/.next/BUILD_ID" 2>/dev/null)" = "OLD_BUILD_ID_MARKER" ]; then
  _pass "tier 3: .next was reverted to the EXACT pre-update snapshot (old marker + old BUILD_ID content both restored byte-for-byte) — never left half-updated"
else
  _fail "tier 3: pre-update snapshot was NOT genuinely restored — CANARY_MARKER_OLD/BUILD_ID missing or content mismatched (npm's fake build clobbers .next, so this can only pass if the revert really ran): marker=$(cat "$DASHBOARD_DIR/.next/CANARY_MARKER_OLD" 2>/dev/null || echo MISSING) build_id=$(cat "$DASHBOARD_DIR/.next/BUILD_ID" 2>/dev/null || echo MISSING)"
fi

if grep -q "commandCenterLastUpdateVerified" "$SANDBOX_STATE_CALLS" 2>/dev/null && grep -qi "false" "$SANDBOX_STATE_CALLS" 2>/dev/null; then
  _pass "tier 3: state_set stamped commandCenterLastUpdateVerified = false on the failed assertion"
else
  _fail "tier 3: state_set did not stamp verified=false on failure: $(cat "$SANDBOX_STATE_CALLS" 2>/dev/null)"
fi

# ─── Scenario C: THE FAIL-FIRST CASE FOR THE FINAL ASSERTION — tier 1,
# update.sh reports success and the server answers healthy (200), but
# BUILD_ID does NOT postdate the pull (update.sh internally rolled back to
# the prior build after detecting a bad new one — a real, legitimate
# atomic-deploy.sh outcome). Against the PRE-FIX final assertion (health==200
# alone -> verified=true), this scenario stamps verified=true even though the
# update did NOT take effect — exactly the P1-07 fix-loop judge's finding #1.
# The fixed final assertion requires BUILD_ID_mtime > pull_ts AND health==200
# for verified=true, so this must stamp false and return 1. ─────────────────
_section "Scenario C — tier 1, healthy on the PRIOR build (rolled back) must NOT stamp verified=true"
BOXC="$SANDBOX/boxC"; _new_sandbox_box "$BOXC"
SANDBOX_STATE_CALLS="$BOXC/state-calls.log"
SANDBOX_PM2_CALLS="$BOXC/pm2-calls.log"
_write_fake_bins "$BOXC/bin" "200"   # server answers healthy...

# Pre-existing BUILD_ID from a PRIOR (older) deploy — this is what must
# survive untouched: update.sh, below, simulates an internal rollback by
# never writing a new one.
mkdir -p "$DASHBOARD_DIR/.next"
echo "PRIOR_BUILD_ID_UNTOUCHED" > "$DASHBOARD_DIR/.next/BUILD_ID"
sleep 1   # guarantee the function's pull_ts (captured at call time, below) postdates this BUILD_ID's mtime

cat > "$DASHBOARD_DIR/update.sh" <<'EOF'
#!/usr/bin/env bash
# fake update.sh simulating atomic-deploy.sh's OWN internal rollback: the new
# build failed its health check, atomic-deploy.sh rolled back to the prior
# (already-healthy) build, and update.sh exits 0 ("no half-updated CC" was
# honored) WITHOUT touching BUILD_ID — the prior build is still what's live.
echo "invoked (simulating internal rollback, BUILD_ID untouched)" >> "$(dirname "$CC_APP_DIR")/update-sh-calls.log"
exit 0
EOF
chmod +x "$DASHBOARD_DIR/update.sh"

if ! declare -F cc_route_update_through_canonical_path >/dev/null 2>&1; then
  _fail "scenario C: cc_route_update_through_canonical_path is not a defined function before invocation — sourcing $UNIT failed silently"
fi
source "$UNIT"
PATH="$BOXC/bin:$PATH" cc_route_update_through_canonical_path
RC=$?

if [ "$RC" -ne 0 ]; then
  _pass "scenario C: function correctly reports non-zero — healthy-on-the-prior-build is not a fresh, verified update"
else
  _fail "scenario C: function reported success (rc=0) despite BUILD_ID not postdating the pull — the update did NOT take effect and this must not read as green"
fi

if [ "$(cat "$DASHBOARD_DIR/.next/BUILD_ID" 2>/dev/null)" = "PRIOR_BUILD_ID_UNTOUCHED" ]; then
  _pass "scenario C: BUILD_ID confirmed untouched by update.sh (genuinely simulating a rolled-back box)"
else
  _fail "scenario C: test setup invalid — BUILD_ID was modified when it should have stayed untouched: $(cat "$DASHBOARD_DIR/.next/BUILD_ID" 2>/dev/null || echo MISSING)"
fi

if grep -q "commandCenterLastUpdateVerified" "$SANDBOX_STATE_CALLS" 2>/dev/null && grep -qi "false" "$SANDBOX_STATE_CALLS" 2>/dev/null; then
  _pass "scenario C: state_set stamped commandCenterLastUpdateVerified = false — the SSOT stamp does NOT lie about a rolled-back box (P1-07 fix-loop finding #1)"
else
  _fail "scenario C: state_set stamped verified=true (or was not called) on a box healthy-but-NOT-updated — this is exactly the bug the fix-loop judge found: $(cat "$SANDBOX_STATE_CALLS" 2>/dev/null)"
fi

if grep -q "GREEN on the PRIOR build (rolled back), the update did NOT take effect" "$LOG_FILE" 2>/dev/null; then
  _pass "scenario C: log line honestly distinguishes 'healthy on the old build' from 'update took effect'"
else
  _fail "scenario C: expected log line distinguishing rolled-back-but-healthy from a genuine fresh-verified update was not found: $(cat "$LOG_FILE" 2>/dev/null)"
fi

_section "SUMMARY"
echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
