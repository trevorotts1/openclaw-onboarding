#!/usr/bin/env bash
# cc-update-path-build-fresh.test.sh — class E: a verified Command Center update
# must not end "done-degraded" just because it went through update.sh.
#
# THE BUG: run-full-install.sh's FINAL check requires commandCenterBuildFresh ==
# true (fail-closed: an ABSENT key is degraded — cc-done-degraded-retry-gate.test.sh
# pins that). Only cc_ensure_fresh_build writes the key, and the update-only path
# (cc_route_update_through_canonical_path, tiers 1/2 = update.sh / atomic-deploy.sh)
# never calls it: it stamped only commandCenterLastUpdateVerified=true. So every
# verified update-only run reported "done-degraded: ccBuildFresh(6)".
#
# Runs the REAL function (extracted with _cc_mtime) against a stub update.sh
# that lands a fresh .next/BUILD_ID and a stub curl answering 200, then applies
# the REAL FINAL jq filter to the resulting state.
set -uo pipefail
P="[cc-update-path-build-fresh]"; PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RFI="$ROOT/32-command-center-setup/scripts/run-full-install.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
command -v jq >/dev/null 2>&1 || { echo "$P FATAL: jq not on PATH" >&2; exit 1; }

awk '/^_cc_mtime\(\)/{p=1} p{print} p&&/^}$/{exit}' "$RFI" > "$TMP/fn.sh"
awk '/^cc_route_update_through_canonical_path\(\)/{p=1} p{print} p&&/^}$/{exit}' "$RFI" >> "$TMP/fn.sh"
grep -q '^cc_route_update_through_canonical_path()' "$TMP/fn.sh" || { echo "$P FATAL: function not found" >&2; exit 1; }
FILTER="$(python3 - "$RFI" <<'PY'
import re, sys
m = re.search(r"DEGRADED_PHASES=\"\$\(jq -r '(.*?)' \"\$STATE_FILE\"", open(sys.argv[1]).read(), re.S)
sys.stdout.write(m.group(1) if m else "")
PY
)"
[[ -n "$FILTER" ]] || { echo "$P FATAL: FINAL jq filter not found" >&2; exit 1; }

mkdir -p "$TMP/bin" "$TMP/app"
printf '#!/bin/sh\nprintf %%s "${CURL_CODE:-200}"\n' > "$TMP/bin/curl"; chmod +x "$TMP/bin/curl"

run_update() { # run_update <update.sh body> -> prints the FINAL degraded list
  printf '#!/usr/bin/env bash\n%s\n' "$1" > "$TMP/app/update.sh"
  rm -rf "$TMP/app/.next"
  # Every OTHER required phase already true: only the update path's own keys vary.
  printf '%s' '{"commandCenterWorkspacesSeeded":true,"commandCenterDepartmentsSynced":true,"commandCenterMdContentSynced":true,"commandCenterDashboardContentSeeded":true,"commandCenterDeptRuntimeParity":true,"commandCenterTenantReady":true}' > "$TMP/state.json"
  PATH="$TMP/bin:$PATH" DASHBOARD_DIR="$TMP/app" DASHBOARD_PORT=1 STATE_FILE="$TMP/state.json" \
    LOG_FILE="$TMP/log" CC_PM2_NAME=x bash -c '
      log() { :; }
      state_set() { local t; t="$(mktemp)"; jq "$1" "$STATE_FILE" > "$t" && mv "$t" "$STATE_FILE"; }
      source "$1"; cc_route_update_through_canonical_path' _ "$TMP/fn.sh" >/dev/null 2>&1
  jq -r "$FILTER" "$TMP/state.json"
}

# Fresh build lands after the pull, health 200 -> verified -> must be "done".
out="$(run_update 'cd "$CC_APP_DIR"; sleep 1; mkdir -p .next; touch .next/BUILD_ID')"
[[ -z "$out" ]] && pass "verified update.sh run -> done (no degraded phases)" \
  || fail "verified update.sh run still degraded: '$out'"
[[ "$(jq -r '.commandCenterBuildFresh' "$TMP/state.json")" == "true" ]] \
  && pass "commandCenterBuildFresh=true stamped on the update path" \
  || fail "commandCenterBuildFresh not stamped: $(jq -c . "$TMP/state.json")"

# Rolled back (BUILD_ID not newer than the pull) -> still degraded, never "done".
out="$(run_update 'cd "$CC_APP_DIR"; mkdir -p .next; touch -t 202001010000 .next/BUILD_ID')"
[[ "$out" == *"ccBuildFresh(6)"* ]] && pass "rolled-back update stays degraded ($out)" \
  || fail "rolled-back update not flagged: '$out'"

echo "$P Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
