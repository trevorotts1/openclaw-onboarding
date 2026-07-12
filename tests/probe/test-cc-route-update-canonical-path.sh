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
# run build ... )`; our fake npm exits 0 but writes NOTHING — so the file
# system after "build" looks like source changed but the build step itself
# did not actually refresh .next (a broken-build simulation). Force a source
# file newer than .next/BUILD_ID so cc_ensure_fresh_build decides a rebuild is
# needed and calls `npm run build`.
mkdir -p "$DASHBOARD_DIR/src"
sleep 1
touch "$DASHBOARD_DIR/src/marker.ts"

source "$UNIT"
PATH="$BOXB/bin:$PATH" cc_route_update_through_canonical_path
RC=$?

if [ "$RC" -ne 0 ]; then
  _pass "tier 3: function correctly reports non-zero when health check fails post-update"
else
  _fail "tier 3: function reported success (rc=0) despite a failing health check — regression of the P1-07 invariant"
fi

if [ -f "$DASHBOARD_DIR/.next/CANARY_MARKER_OLD" ]; then
  _pass "tier 3: .next was reverted to the pre-update snapshot (old marker file restored) — never left half-updated"
else
  _fail "tier 3: pre-update snapshot was NOT restored — the old marker file is missing, meaning the box could be left in a broken/half-updated state"
fi

if grep -q "commandCenterLastUpdateVerified" "$SANDBOX_STATE_CALLS" 2>/dev/null && grep -qi "false" "$SANDBOX_STATE_CALLS" 2>/dev/null; then
  _pass "tier 3: state_set stamped commandCenterLastUpdateVerified = false on the failed assertion"
else
  _fail "tier 3: state_set did not stamp verified=false on failure: $(cat "$SANDBOX_STATE_CALLS" 2>/dev/null)"
fi

_section "SUMMARY"
echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
