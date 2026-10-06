#!/usr/bin/env bash
# cc-status-from-live-health.test.sh — the daily update path must take
# commandCenterStatus from the Command Center that is ACTUALLY RUNNING, not from
# the outcome of this run's (possibly spare) rebuild.
#
# THE BUG: update-skills.sh -> run-full-install.sh --update-only -> phase 6 ->
# cc_route_update_through_canonical_path -> CC update.sh/atomic-deploy.sh. When
# that rebuild failed and rolled back, the function returned 1 and phase 6
# fail_install()ed -> commandCenterStatus=failed, even though the running CC was
# healthy, migrations current, and already serving the current code.
#
# Runs the REAL phase-6 call line (cc_route_update_through_canonical_path ||
# fail_install ...) with the REAL functions, a stub update.sh (the rebuild), a
# stub curl (the live /api/health) and a stub build-inventory.sh (served-build
# oracle), then applies the REAL FINAL jq filter.
set -uo pipefail
P="[cc-status-from-live-health]"; PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RFI="$ROOT/32-command-center-setup/scripts/run-full-install.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
command -v jq >/dev/null 2>&1 || { echo "$P FATAL: jq not on PATH" >&2; exit 1; }

for fn in fail_install _cc_mtime _cc_resolve_bash4 cc_route_update_through_canonical_path \
          cc_live_health_ok cc_served_build_current; do
  awk -v f="$fn" '$0 ~ "^"f"\\(\\)" {p=1} p{print} p&&/^}$/{exit}' "$RFI" >> "$TMP/fn.sh"
  grep -q "^$fn()" "$TMP/fn.sh" || { echo "$P FATAL: $fn not found in $RFI" >&2; exit 1; }
done
CALL="$(grep -A1 '^  cc_route_update_through_canonical_path || \\$' "$RFI")"
[[ -n "$CALL" ]] || { echo "$P FATAL: phase-6 call line not found" >&2; exit 1; }
FILTER="$(python3 - "$RFI" <<'PY'
import re, sys
m = re.search(r"DEGRADED_PHASES=\"\$\(jq -r '(.*?)' \"\$STATE_FILE\"", open(sys.argv[1]).read(), re.S)
sys.stdout.write(m.group(1) if m else "")
PY
)"
[[ -n "$FILTER" ]] || { echo "$P FATAL: FINAL jq filter not found" >&2; exit 1; }

mkdir -p "$TMP/bin" "$TMP/app/scripts/lib"
# Stub curl: `-w` form = the fresh-build probe (prints a code); otherwise the
# live /api/health body, or a curl -f failure (exit 22) when LIVE=down.
cat > "$TMP/bin/curl" <<'SH'
#!/bin/sh
case " $* " in *" -w "*) printf %s "${CURL_CODE:-200}"; exit 0 ;; esac
[ "${LIVE:-ok}" = down ] && exit 22
printf %s "${HEALTH_BODY:-}"
SH
chmod +x "$TMP/bin/curl"
printf '#!/usr/bin/env bash\nexit "${INV_RC:-0}"\n' > "$TMP/app/scripts/lib/build-inventory.sh"

OK_BODY='{"status":"ok","migrations":{"applied":["001"],"expected":["001"],"pending":[],"gap":0}}'
PENDING_BODY='{"status":"degraded","migrations":{"applied":["001"],"expected":["001","002"],"pending":["002"],"gap":1}}'
REBUILD_FAILS='echo "next/font: failed to fetch" >&2; exit 1'
REBUILD_FRESH='cd "$CC_APP_DIR"; sleep 1; mkdir -p .next; touch .next/BUILD_ID'

# run_case <update.sh body> [ENV=VAL ...] -> sets STATUS and DEGRADED
run_case() {
  printf '#!/usr/bin/env bash\n%s\n' "$1" > "$TMP/app/update.sh"; shift
  rm -rf "$TMP/app/.next"; mkdir -p "$TMP/app/.next"; touch -t 202001010000 "$TMP/app/.next/BUILD_ID"
  printf '%s' '{"commandCenterWorkspacesSeeded":true,"commandCenterDepartmentsSynced":true,"commandCenterMdContentSynced":true,"commandCenterDashboardContentSeeded":true,"commandCenterDeptRuntimeParity":true,"commandCenterTenantReady":true}' > "$TMP/state.json"
  env "$@" PATH="$TMP/bin:$PATH" DASHBOARD_DIR="$TMP/app" DASHBOARD_PORT=1 STATE_FILE="$TMP/state.json" \
    LOG_FILE="$TMP/log" CC_PM2_NAME=x bash -c '
      log() { :; }
      state_set() { local t; t="$(mktemp)"; jq "$1" "$STATE_FILE" > "$t" && mv "$t" "$STATE_FILE"; }
      state_set_arg() { local t; t="$(mktemp)"; jq --arg val "$2" "$1" "$STATE_FILE" > "$t" && mv "$t" "$STATE_FILE"; }
      source "$1"; eval "$2"' \
      _ "$TMP/fn.sh" "$CALL" >/dev/null 2>&1
  STATUS="$(jq -r '.commandCenterStatus // "not-failed"' "$TMP/state.json")"
  DEGRADED="$(jq -r "$FILTER" "$TMP/state.json")"
}

# 1. Spare rebuild fails, running CC healthy + serving current code -> NOT failed, done.
run_case "$REBUILD_FAILS" HEALTH_BODY="$OK_BODY" INV_RC=0
[[ "$STATUS" != failed && -z "$DEGRADED" ]] \
  && pass "rebuild fails + live healthy + served build current -> not failed, done" \
  || fail "rebuild fails + live healthy + current: status=$STATUS degraded='$DEGRADED'"

# 2. Rebuild fails, running CC healthy but served build unproven -> not failed, done-degraded.
run_case "$REBUILD_FAILS" HEALTH_BODY="$OK_BODY" INV_RC=1
[[ "$STATUS" != failed && "$DEGRADED" == *"ccBuildFresh(6)"* ]] \
  && pass "rebuild fails + live healthy + served build unproven -> not failed, degraded ($DEGRADED)" \
  || fail "rebuild fails + live healthy + unproven: status=$STATUS degraded='$DEGRADED'"

# 3. Running CC down -> failed (real failures are never masked).
run_case "$REBUILD_FAILS" LIVE=down INV_RC=0
[[ "$STATUS" == failed ]] && pass "live unhealthy (down) -> failed" \
  || fail "live down but status=$STATUS"

# 4. Running CC answers 200 but migrations pending -> failed.
run_case "$REBUILD_FAILS" HEALTH_BODY="$PENDING_BODY" INV_RC=0
[[ "$STATUS" == failed ]] && pass "live 200 with pending migrations -> failed" \
  || fail "pending migrations but status=$STATUS"

# 5. Regression: a fresh verified rebuild is still done.
run_case "$REBUILD_FRESH" HEALTH_BODY="$OK_BODY" CURL_CODE=200
[[ "$STATUS" != failed && -z "$DEGRADED" ]] && pass "fresh rebuild + healthy -> done" \
  || fail "fresh rebuild: status=$STATUS degraded='$DEGRADED'"

echo "$P Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
