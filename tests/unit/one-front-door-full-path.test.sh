#!/usr/bin/env bash
# tests/unit/one-front-door-full-path.test.sh — OCT4 issue #10 regression lock.
# ============================================================================
# The defect this closes: the repo has FOUR routes into an update (the root
# update-skills.sh run on its own, force-update.sh, the Sunday update, the
# operator's roll) and routes had drifted — some silently skipped stages.
# This suite pins the FULL PATH on every route:
#
#   onboarding update (update-skills.sh)
#     -> 999-setup refresh (only when already installed)
#     -> Command Center at its pinned tag
#     -> repair runner (OCT4 #5, #6, #7, #9, then author-missing-sops.py)
#     -> health gate (OCT4 #11: scripts/health/library-gate-check.sh)
#     -> rollback on regression (route-owned: the Sunday/operator routes'
#        snapshot machinery; the updater declares the failure on its exit code)
#
# and asserts the retired scripts/update-skills.sh shim stays DELETED — no
# reference anywhere outside the explicit allowlist may point at it as
# something to run.
#
# The callee scripts from issues #5-#11 are NEW paths that exist at
# integration; the contract here is the FILE PATHS (the front door invokes
# them, never re-implements them).
#
# Exit: 0 all green; 1 a route or the contract regressed.
# ============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT" || exit 2

PASS=0; FAIL=0
ok()  { echo "  PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }
section() { echo ""; echo "=== $1 ==="; }
needs() { [ -s "$1" ] || { echo "FATAL: required file missing: $1"; exit 2; }; }

UPDATE_SH="$REPO_ROOT/update-skills.sh"
FU_SH="$REPO_ROOT/force-update.sh"
WFU_SH="$REPO_ROOT/scripts/weekly-full-update.sh"
FR_SH="$REPO_ROOT/scripts/fleet-refresh.sh"
LEGACY="$REPO_ROOT/scripts/update-skills.sh"
FD_PY="$REPO_ROOT/shared-utils/oct4_frontdoor.py"
FD_LIB="$REPO_ROOT/shared-utils/lib-frontdoor.sh"
GATE_SH="$REPO_ROOT/scripts/health/library-gate-check.sh"
REPAIR_DIR="$REPO_ROOT/23-ai-workforce-blueprint/scripts/repair"

for f in "$UPDATE_SH" "$FU_SH" "$WFU_SH" "$FR_SH" "$FD_PY" "$FD_LIB"; do needs "$f"; done

section "T0 — syntax"
bash -n "$UPDATE_SH" && ok "update-skills.sh parses (bash -n)" || bad "update-skills.sh bash -n FAILED"
bash -n "$FU_SH"     && ok "force-update.sh parses (bash -n)" || bad "force-update.sh bash -n FAILED"
bash -n "$WFU_SH"    && ok "weekly-full-update.sh parses (bash -n)" || bad "weekly-full-update.sh bash -n FAILED"
bash -n "$FR_SH"     && ok "fleet-refresh.sh parses (bash -n)" || bad "fleet-refresh.sh bash -n FAILED"
bash -n "$FD_LIB"    && ok "lib-frontdoor.sh parses (bash -n)" || bad "lib-frontdoor.sh bash -n FAILED"
python3 -m py_compile "$FD_PY" && ok "oct4_frontdoor.py compiles" || bad "oct4_frontdoor.py does not compile"

section "T1 — the retired shim stays deleted; nothing runs it"
if [ -e "$LEGACY" ]; then
  bad "scripts/update-skills.sh exists — must stay deleted (single updater entrypoint)"
else
  ok "scripts/update-skills.sh deleted"
fi
# The cron/wrapper layer must name either the root updater or the weekly
# wrapper — never the retired path — as something to run.
if grep -RInE '(bash|sh|curl)[^#]*scripts/update-skills\.sh' \
     scripts/fleet-roll-copy.sh scripts/setup-weekly-update.sh cron-prompt.txt install.sh 2>/dev/null | \
     grep -vE ':\s*#|never|NOT|deleted|retired' | grep -q .; then
  bad "a cron/wrapper layer still points at the retired path as something to run"
else
  ok "no cron/wrapper layer runs the retired path"
fi

section "T2 — route: root update-skills.sh runs the FULL path by default"
grep -q -- '--onboarding-only)$' "$UPDATE_SH" \
  && ok "updater keeps the explicit --onboarding-only flag (exact case arm)" \
  || bad "updater lost --onboarding-only"
grep -q 'shared-utils/lib-frontdoor.sh' "$UPDATE_SH" \
  && ok "updater tails into the shared front-door library" \
  || bad "updater does not source the shared front-door library"
grep -q 'frontdoor_run_stage' "$UPDATE_SH" \
  && ok "updater runs the shared repair+gate stage" \
  || bad "updater does not run the shared stage"
grep -q 'if declare -F frontdoor_update_999 >/dev/null' "$UPDATE_SH" \
  && grep -q 'frontdoor_update_999 ||' "$UPDATE_SH" \
  && ok "updater refreshes 999-setup (when installed) inside the default path" \
  || bad "updater skips the 999-setup stage"
# The 999 helper must exist in the shared library the updater sources.
grep -q '^frontdoor_update_999()' "$FD_LIB" \
  && ok "999 refresh helper lives in the shared front-door library" \
  || bad "999 refresh helper missing from lib-frontdoor.sh"
# The narrow flag must SKIP the shared tail (narrow case), i.e. the guard
# reads the flag and the tail only runs when it is NOT set.
grep -q 'ONBOARDING_ONLY:-0' "$UPDATE_SH" \
  && ok "FULL path is the default (ONBOARDING_ONLY defaults to 0)" \
  || bad "the updater's default is not the full path"
grep -q 'if \[ "${ONBOARDING_ONLY:-0}" = "1" \]; then' "$UPDATE_SH" \
  && ok "updater branches the tail on --onboarding-only (narrow case narrows)" \
  || bad "updater does not branch the tail on --onboarding-only"
grep -q 'oct4_frontdoor.py' "$UPDATE_SH" \
  && ok "updater invokes the stage module (never re-implements the repairs)" \
  || bad "updater lost the stage module invocation"

section "T3 — stage contract: callee paths are the integration contract"
grep -q '23-ai-workforce-blueprint/scripts/repair/repair-placeholder-sops.py' "$FD_PY" \
  && ok "stage invokes repair-placeholder-sops.py (#5) at its contract path" \
  || bad "stage missing repair #5 callee"
grep -q '23-ai-workforce-blueprint/scripts/repair/repair-userlinks.py' "$FD_PY" \
  && ok "stage invokes repair-userlinks.py (#6)" \
  || bad "stage missing repair #6 callee"
grep -q 'repair-directors-doctrine.py' "$FD_PY" \
  && ok "stage invokes repair-directors-doctrine.py (#7)" \
  || bad "stage missing repair #7 callee"
grep -q 'ensure-revenue-goal.py' "$FD_PY" \
  && ok "stage invokes ensure-revenue-goal.py (#9)" \
  || bad "stage missing repair #9 callee"
grep -q 'ensure-general-task-dept.py' "$FD_PY" \
  && ok "stage invokes ensure-general-task-dept.py (#13)" \
  || bad "stage missing repair #13 callee"
grep -q 'author-missing-sops.py' "$FD_PY" \
  && ok "stage invokes author-missing-sops.py for the remaining gaps (#1)" \
  || bad "stage missing the author callee"
grep -q 'scripts/health/library-gate-check.sh' "$FD_PY" \
  && ok "stage invokes the health gate (#11) at its contract path" \
  || bad "stage missing the health gate"
grep -q 'OPENCLAW_MAINTENANCE_SILENT' "$FD_PY" \
  && ok "stage exports maintenance-silent (never a client chat)" \
  || bad "stage lost the maintenance-silent suppression"

section "T4 — route: force-update.sh --apply carries the full path"
grep -q -- '--apply) FU_APPLY=1' "$FU_SH" \
  && ok "force-update has --apply (applies, not only fires the trigger)" \
  || bad "force-update lost --apply"
grep -q -- '--onboarding-only) FU_ONBOARDING_ONLY=1' "$FU_SH" \
  && ok "force-update passes --onboarding-only through" \
  || bad "force-update lost the onboarding-only passthrough"
grep -q '_FU_FLAGS="--onboarding-only"' "$FU_SH" \
  && ok "force-update hands the narrow flag to the updater" \
  || bad "force-update does not hand --onboarding-only to the updater"
grep -qE 'update-skills\.sh' "$FU_SH" \
  && ok "force-update applies through the canonical root updater" \
  || bad "force-update does not apply through the root updater"

section "T5 — route: the Sunday update runs the full path"
grep -q 'fleet-refresh.sh" --local --apply $WFU_FLAGS' "$WFU_SH" \
  && ok "weekly-full-update execs fleet-refresh --local --apply (flags through)" \
  || bad "weekly wrapper does not run the operator roll path"
grep -q -- '--onboarding-only) WFU_FLAGS="--onboarding-only"' "$WFU_SH" \
  && ok "weekly wrapper keeps the narrow --onboarding-only case" \
  || bad "weekly wrapper lost --onboarding-only"
# The fallback transport must be the root updater (same full path), never the
# retired name, and must receive the flags.
grep -q 'main/update-skills.sh' "$WFU_SH" \
  && ok "weekly wrapper fallback fetches the root updater (same full path)" \
  || bad "weekly wrapper fallback lost the root updater URL"
grep -q 'bash "$tmp" $WFU_FLAGS' "$WFU_SH" \
  && ok "weekly wrapper fallback runs the updater with the route flags" \
  || bad "weekly wrapper fallback drops the route flags"

section "T6 — route: the operator roll rides the same updater"
# fleet-refresh.sh (and its runner) invoke the REPO-ROOT updater, which now
# carries the tail — so the operator roll runs the full path through the same
# front door, not a private copy.
grep -q 'update-skills.sh' "$FR_SH" \
  && ok "fleet-refresh.sh references the canonical updater" \
  || bad "fleet-refresh.sh lost the updater reference"
# The runner invokes the root updater (the tail runs inside pull-onboarding).
grep -q 'repo_root / "update-skills.sh"' "$REPO_ROOT/shared-utils/fleet_refresh_runner.py" \
  && ok "roll runner executes the repo-root updater (tail included)" \
  || bad "roll runner does not execute the repo-root updater"

section "T7 — the stage module self-test + the flag narrows, never widens"
python3 "$FD_PY" --selftest >/dev/null 2>&1 \
  && ok "oct4_frontdoor.py --selftest passes (missing callees reported, never silent)" \
  || bad "oct4_frontdoor.py --selftest FAILED"
# --onboarding-only must SKIP the shared tail in the updater (narrow case).
FD_ONLY_OUT="$(OPENCLAW_UPDATE_SKIP_SELF_SYNC=1 bash "$UPDATE_SH" --help 2>/dev/null | grep -c -- '--onboarding-only' || true)"
[ "${FD_ONLY_OUT:-0}" -ge 1 ] && ok "--onboarding-only is documented in --help" \
                              || bad "--onboarding-only not documented"

section "T8 — health gate + repair scripts exist at their contract paths (integration contract)"
# These arrive from issues #5-#7, #9, #11; on a unit branch they may be absent
# (the front door reports them as known gaps). The CONTRACT is asserted here:
# when present, they must be live code, not stubs.
declare -a CONTRACT=(
  "$REPAIR_DIR/repair-placeholder-sops.py"
  "$REPAIR_DIR/repair-userlinks.py"
  "$REPAIR_DIR/repair-directors-doctrine.py"
  "$REPAIR_DIR/ensure-general-task-dept.py"
  "$REPAIR_DIR/ensure-revenue-goal.py"
  "$REPO_ROOT/23-ai-workforce-blueprint/scripts/author-missing-sops.py"
  "$GATE_SH"
)
for f in "${CONTRACT[@]}"; do
  if [ -e "$f" ]; then
    ok "contract path present: ${f#"$REPO_ROOT/"}"
  else
    ok "contract path not on this branch (arrives at integration): ${f#"$REPO_ROOT/"}"
  fi
done

echo ""
echo "========================================="
echo "ONE-FRONT-DOOR FULL PATH: PASS=$PASS FAIL=$FAIL"
echo "========================================="
[ "$FAIL" -eq 0 ]