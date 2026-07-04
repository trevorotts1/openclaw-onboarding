#!/usr/bin/env bash
# tests/unit/cc-done-degraded-retry-gate.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Regression lock for AUDIT ISSUE #12 (P2) — "run-full-install marks phase state
# 'done' strings inconsistently ('script-missing' as terminal success-ish state)".
#
# Issue #12's EXACT fix asked for two things:
#   (1) fold the board-provisioning sub-phase keys (6b commandCenterWorkspacesSeeded
#       and 6c commandCenterDepartmentsSynced) into the fail-closed done-stamp
#       computation, and
#   (2) make the resume path re-invoke run-full-install until they reach true,
#       instead of leaving a "script-missing"/false sub-state as a terminal
#       success-ish state that never retries.
#
# Wave 2's Issue #6 fix implemented (1) in run-full-install.sh's FINAL block, and
# the resume re-run (2) is provided by (a) run-closeout.sh step 1 skipping ONLY on
# commandCenterStatus == "done" (so "done-degraded" re-invokes the installer) and
# (b) update-skills.sh's D5 block invoking run-full-install.sh --update-only
# unconditionally on every update. This test locks that behavior so the bug can
# never silently regress (there was NO test guarding the done-degraded computation
# before this file).
#
# It exercises the REAL jq filter EXTRACTED FROM run-full-install.sh (not a copy),
# so weakening the filter (e.g. dropping 6c, or folding 6f in) fails this test.
#
# Fully offline/hermetic (mktemp sandbox, jq only). Exit 0 = all pass, 1 = failure.
# bash 3.2-safe (macOS system bash): no assoc arrays, no mapfile, no ${x,,}.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RFI="$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh"
RUN_CLOSEOUT="$REPO_ROOT/37-zhc-closeout/scripts/run-closeout.sh"
UPDATE_SKILLS="$REPO_ROOT/update-skills.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== cc-done-degraded-retry-gate.test.sh (Issue #12) ==="

for f in "$RFI" "$RUN_CLOSEOUT" "$UPDATE_SKILLS"; do
  [ -f "$f" ] || { echo "  FAIL: required file not found: $f"; exit 1; }
done
command -v jq >/dev/null 2>&1 || { echo "  FAIL: jq not on PATH"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "  FAIL: python3 not on PATH"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
TMP_STATE="$WORK/state.json"

# ── Extract the REAL DEGRADED_PHASES jq filter straight out of the installer ──
# This is the exact filter run-full-install.sh's FINAL block runs against the
# build-state to decide done vs done-degraded (lines ~815-821). Extracting it
# means this test guards the shipping code, not a stale duplicate.
FILTER="$(python3 - "$RFI" <<'PY'
import re, sys
s = open(sys.argv[1]).read()
m = re.search(r"DEGRADED_PHASES=\"\$\(jq -r '(.*?)' \"\$STATE_FILE\"", s, re.S)
if not m:
    sys.stderr.write("could not extract DEGRADED_PHASES jq filter from run-full-install.sh\n")
    sys.exit(3)
sys.stdout.write(m.group(1))
PY
)"
if [ -z "$FILTER" ]; then
  fail "could not extract the FINAL-block jq filter from run-full-install.sh (structure changed?)"
  echo "";  echo "  RESULT: $PASS passed, $FAIL failed"; exit 1
fi
pass "extracted the live DEGRADED_PHASES jq filter from run-full-install.sh"

# final_status <state-json> [zheGateStatus] -> echoes "done" | "done-degraded"
# Faithfully mirrors run-full-install.sh FINAL block: required-key degradation via
# the extracted filter, then the zheGate(failed) append, then the done/degraded pick.
final_status() {
  local state_json="$1" zhe="${2:-}" dp
  printf '%s' "$state_json" > "$TMP_STATE"
  dp="$(jq -r "$FILTER" "$TMP_STATE" 2>/dev/null || echo "")"
  if [ "$zhe" = "failed" ]; then
    if [ -n "$dp" ]; then dp="$dp, zheGate(failed)"; else dp="zheGate(failed)"; fi
  fi
  if [ -n "$dp" ]; then echo "done-degraded"; else echo "done"; fi
}

expect() { # expect <label> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1 -> $3"; else fail "$1: expected '$2' got '$3'"; fi
}

ALL_TRUE='{"commandCenterWorkspacesSeeded":true,"commandCenterDepartmentsSynced":true,"commandCenterMdContentSynced":true,"commandCenterDashboardContentSeeded":true}'

# ── Fail-closed on the two Issue-#12-named keys (script-missing / false) ─────────
# The exact audit scenario: dashboard repo lacks the sync script -> 6c script-missing.
expect "6c=script-missing must NOT report done (fail-closed)" "done-degraded" \
  "$(final_status '{"commandCenterWorkspacesSeeded":true,"commandCenterDepartmentsSynced":"script-missing","commandCenterMdContentSynced":true,"commandCenterDashboardContentSeeded":true}')"
expect "6b=false must NOT report done (fail-closed)" "done-degraded" \
  "$(final_status '{"commandCenterWorkspacesSeeded":false,"commandCenterDepartmentsSynced":true,"commandCenterMdContentSynced":true,"commandCenterDashboardContentSeeded":true}')"
expect "6d=script-missing must NOT report done (fail-closed)" "done-degraded" \
  "$(final_status '{"commandCenterWorkspacesSeeded":true,"commandCenterDepartmentsSynced":true,"commandCenterMdContentSynced":"script-missing","commandCenterDashboardContentSeeded":true}')"
expect "6e=false must NOT report done (fail-closed)" "done-degraded" \
  "$(final_status '{"commandCenterWorkspacesSeeded":true,"commandCenterDepartmentsSynced":true,"commandCenterMdContentSynced":true,"commandCenterDashboardContentSeeded":false}')"

# ── Convergence: all required sub-phases true -> done (green box stays green) ────
expect "all required true -> done (converges)" "done" "$(final_status "$ALL_TRUE")"

# ── 6f (KPI rollup, WARN-by-design) is DELIBERATELY EXCLUDED ────────────────────
expect "only 6f missing must still report done (6f excluded)" "done" \
  "$(final_status '{"commandCenterWorkspacesSeeded":true,"commandCenterDepartmentsSynced":true,"commandCenterMdContentSynced":true,"commandCenterDashboardContentSeeded":true,"commandCenterKpiRollupWritten":"script-missing"}')"

# ── Older state (keys absent) must NOT be treated as a regression ───────────────
expect "absent keys (older state) -> done (no false-red)" "done" \
  "$(final_status '{"commandCenterStatus":"building"}')"

# ── ZHE gate failure (reachable only via ZHE_ENFORCE=0 escape hatch) ────────────
expect "zheGate failed -> done-degraded even when sub-phases green" "done-degraded" \
  "$(final_status "$ALL_TRUE" failed)"

# ── Retry-then-fail-closed loop simulation ──────────────────────────────────────
# Pass 1: transient failure (sync script not yet shipped) -> done-degraded, so the
#         resume path re-runs (status != "done"). Pass 2: transient cleared (dashboard
#         repo pulled, 6c now true) -> done. The gate converges when the transient
#         resolves and NEVER silently reports done while it persists.
p1="$(final_status '{"commandCenterWorkspacesSeeded":true,"commandCenterDepartmentsSynced":"script-missing","commandCenterMdContentSynced":true,"commandCenterDashboardContentSeeded":true}')"
p2="$(final_status "$ALL_TRUE")"
if [ "$p1" = "done-degraded" ] && [ "$p2" = "done" ]; then
  pass "retry loop: transient(6c=script-missing)->done-degraded, then cleared->done (converges)"
else
  fail "retry loop: expected done-degraded then done, got '$p1' then '$p2'"
fi
# Never-silent-pass: a persistently missing script can never yield "done".
persist_ok=1
for _i in 1 2 3 4 5; do
  [ "$(final_status '{"commandCenterWorkspacesSeeded":true,"commandCenterDepartmentsSynced":"script-missing","commandCenterMdContentSynced":true,"commandCenterDashboardContentSeeded":true}')" = "done-degraded" ] || persist_ok=0
done
[ "$persist_ok" = "1" ] && pass "persistent 6c=script-missing never silently passes (5/5 stayed done-degraded)" \
  || fail "persistent 6c=script-missing leaked a 'done' on some pass"

# ── Static wiring: the filter guards exactly the four required keys, not 6f ─────
for key in commandCenterWorkspacesSeeded commandCenterDepartmentsSynced \
           commandCenterMdContentSynced commandCenterDashboardContentSeeded; do
  case "$FILTER" in
    *"$key"*) pass "FINAL filter still includes required key $key" ;;
    *) fail "FINAL filter lost required key $key (Issue-#12/#6 regression)" ;;
  esac
done
case "$FILTER" in
  *commandCenterKpiRollupWritten*) fail "FINAL filter wrongly folded in 6f (commandCenterKpiRollupWritten) — WARN-by-design must not withhold done" ;;
  *) pass "FINAL filter correctly excludes 6f (commandCenterKpiRollupWritten)" ;;
esac
if grep -Fq 'FINAL_STATUS="done-degraded"' "$RFI" \
   && grep -Fq 'commandCenterStatus = \"done-degraded\"' "$RFI"; then
  pass "run-full-install.sh stamps commandCenterStatus=done-degraded (fail-closed)"
else
  fail "run-full-install.sh no longer stamps done-degraded"
fi

# ── Static wiring: the resume path re-invokes the installer on done-degraded ────
# run-closeout.sh step 1 must skip ONLY on the literal "done" (so done-degraded
# re-runs run-full-install.sh — the auto-repair path Issue #12 asked for).
if grep -Eq 'cc_status" == "done"' "$RUN_CLOSEOUT" || grep -Eq 'cc_status.*==.*"done"' "$RUN_CLOSEOUT"; then
  pass "run-closeout.sh step 1 skips only on commandCenterStatus==done (done-degraded re-runs installer)"
else
  fail "run-closeout.sh step 1 skip gate not found / changed — resume re-run for done-degraded unproven"
fi
if grep -Eq 'cc_status" == "done-degraded"|cc_status.*done-degraded' "$RUN_CLOSEOUT"; then
  fail "run-closeout.sh step 1 wrongly treats done-degraded as skip — installer would never re-run"
else
  pass "run-closeout.sh step 1 does NOT skip on done-degraded (auto-repair intact)"
fi
# update-skills.sh D5 must re-invoke run-full-install.sh --update-only (unconditional
# resume/refresh; the "until they're true" driver Issue #12 named).
if grep -Eq 'run-full-install|_CC_RUN_INSTALL' "$UPDATE_SKILLS" && grep -q -- '--update-only' "$UPDATE_SKILLS"; then
  pass "update-skills.sh re-invokes run-full-install.sh --update-only (resume re-run driver)"
else
  fail "update-skills.sh no longer re-invokes run-full-install.sh --update-only — no resume retry driver"
fi

echo ""
echo "  RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
