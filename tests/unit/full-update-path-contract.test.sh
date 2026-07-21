#!/usr/bin/env bash
# Static integration contract tying the independently-tested update stages into
# one root-updater/Sunday-cron path. Functional behavior remains covered by the
# stage-specific suites this test names.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET_ROOT="${TARGET_ROOT_UNDER_TEST:-$REPO_ROOT}"
UPDATE_SH="$TARGET_ROOT/update-skills.sh"
RUN_FULL="$TARGET_ROOT/32-command-center-setup/scripts/run-full-install.sh"
CRON_SETUP="$TARGET_ROOT/scripts/setup-weekly-update.sh"
RUNNER="$TARGET_ROOT/shared-utils/fleet_refresh_runner.py"
PLATFORM_BOOTSTRAP="$TARGET_ROOT/platform/mac/bootstrap.sh"
PASS=0; FAIL=0
ok() { PASS=$((PASS + 1)); printf '  PASS: %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL: %s\n' "$1"; }
line_of() { grep -n -m1 -- "$1" "$2" 2>/dev/null | cut -d: -f1; }
before() {
  local label="$1" first="$2" second="$3" file="$4" a b
  a="$(line_of "$first" "$file")"; b="$(line_of "$second" "$file")"
  if [ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ]; then ok "$label"; else bad "$label (lines ${a:-missing}, ${b:-missing})"; fi
}

echo "=== full-update-path-contract.test.sh ==="

before "self-sync executes before platform bootstrap resolution" '^self_sync_guard$' '^_PLATFORM_BOOTSTRAP=' "$UPDATE_SH"
before "update mode is exported before platform bootstrap" '^export OPENCLAW_BOOTSTRAP_MODE=update' '^_PLATFORM_BOOTSTRAP=' "$UPDATE_SH"
grep -q 'pr_preflight_gate "$_PR_MODE"' "$PLATFORM_BOOTSTRAP" \
  && grep -q '\[ "$_PR_MODE" = "update" \]' "$PLATFORM_BOOTSTRAP" \
  && ok "FileVault/power gate is mode-aware and advisory on update" \
  || bad "FileVault update-advisory wiring missing"

before "full scripts tree lands before same-version content-clean exit" 'deliver_canonical_scripts_tree "$ONBOARDING_DIR/scripts"' 'if \[ "${_SAME_VERSION_RECHECK:-0}" -eq 1 \]' "$UPDATE_SH"
before "full scripts tree lands before version stamp" 'deliver_canonical_scripts_tree "$ONBOARDING_DIR/scripts"' 'echo "$ONBOARDING_VERSION" > "$SKILLS_DIR/.onboarding-version"' "$UPDATE_SH"
CURRENT_VERSION="$(tr -d '[:space:]' < "$TARGET_ROOT/version")"
grep -q "^ONBOARDING_VERSION=\"$CURRENT_VERSION\"$" "$UPDATE_SH" \
  && grep -q 'echo "$ONBOARDING_VERSION" > "$SKILLS_DIR/.onboarding-version"' "$UPDATE_SH" \
  && ok "success stamp records the repository's current version ($CURRENT_VERSION)" \
  || bad "success stamp version does not match the repository version ($CURRENT_VERSION)"
before "SOP V2 population runs before version stamp" 'Step U6c: SOP V2 library population check' 'echo "$ONBOARDING_VERSION" > "$SKILLS_DIR/.onboarding-version"' "$UPDATE_SH"
grep -q '_U6C_SOPLIB_FAIL' "$UPDATE_SH" && grep -q 'SOP V2 library (U6c' "$UPDATE_SH" \
  && ok "under-populated SOP library withholds the version stamp" \
  || bad "SOP library is not stamp-gating"

before "branding/departments reconciliation runs before version stamp" 'Step U6d: Command Center departments + branding population check' 'echo "$ONBOARDING_VERSION" > "$SKILLS_DIR/.onboarding-version"' "$UPDATE_SH"
grep -q '_U6D_CC_CONFIG_FAIL' "$UPDATE_SH" && grep -q 'Command Center runtime config (U6d' "$UPDATE_SH" \
  && ok "branding/departments failure withholds the version stamp" \
  || bad "branding/departments reconciliation is not stamp-gating"

# Every name below MUST stay in _PROVISIONING_HARD_CHECKS. Asserted per-name over
# the whole tuple block (which legitimately wraps across lines) rather than as one
# literal line, so a reformat cannot break the contract — but DROPPING a gate
# still fails it. ROLE-FLOOR is the disk-measured floor gate: DEPARTMENTS proves
# only that departments.json is a non-empty array, and that file lives in a
# different tree from the role folders it promises, so without ROLE-FLOOR a box
# could lose every role folder and still record a clean, completed roll.
_PHC_BLOCK="$(sed -n '/_PROVISIONING_HARD_CHECKS = (/,/)/p' "$RUNNER")"
_PHC_MISSING=""
for _phc in '"VERSION"' '"BRANDING"' '"DEPARTMENTS"' '"PERSONAS"' '"ROLE-FLOOR"'; do
  printf '%s' "$_PHC_BLOCK" | grep -qF -- "$_phc" || _PHC_MISSING="$_PHC_MISSING $_phc"
done
[ -n "$_PHC_BLOCK" ] && [ -z "$_PHC_MISSING" ] \
  && ok "fleet provisioning verdict hard-gates version, branding, departments, personas, and the on-disk role floor" \
  || bad "provisioning-completeness hard verdict missing:${_PHC_MISSING:- (tuple not found)}"
grep -q 'QC_COMPLETENESS_SCRIPT=.*qc-completeness.sh' "$UPDATE_SH" \
  && ok "root updater reaches post-update workforce completeness QC" \
  || bad "root updater does not invoke workforce completeness QC"

grep -q -- '--update-only --app-dir "$_CC_DIR"' "$UPDATE_SH" \
  && ok "root updater pins the exact validated Command Center checkout" \
  || bad "Command Center refresh is not pinned to the resolved checkout"
grep -q 'merge-base --is-ancestor "origin/$_CC_DEFAULT" HEAD' "$UPDATE_SH" \
  && ok "root updater independently asserts Command Center contains latest origin/main" \
  || bad "Command Center origin/main post-assertion missing"
grep -q 'canonical Command Center update failed' "$RUNNER" \
  && ! grep -q 'checkout", cc_tag' "$RUNNER" \
  && ok "fleet runner preserves main convergence instead of checking out a stale compatibility tag" \
  || bad "fleet runner can still detach/downgrade Command Center after the root update"
grep -q 'could not converge Command Center checkout onto the latest origin default branch' "$RUN_FULL" \
  && grep -q 'did not end GREEN on the fresh build' "$RUN_FULL" \
  && ok "Command Center branch or deploy rollback fails the update loudly" \
  || bad "Command Center convergence/deploy failures are still advisory"

grep -q 'main/update-skills.sh' "$CRON_SETUP" \
  && ! grep -q 'UPDATE_SCRIPT_URL=.*main/scripts/update-skills.sh' "$CRON_SETUP" \
  && ok "Sunday restart script downloads the root updater" \
  || bad "Sunday restart script points at the legacy updater"
grep -q '_UPDATE_RC=\$?' "$CRON_SETUP" \
  && grep -q 'exit "\$_UPDATE_RC"' "$CRON_SETUP" \
  && ok "Sunday wrapper propagates a failed complete update" \
  || bad "Sunday wrapper can swallow a failed updater exit"
grep -q 'LEGACY_UPDATER_PATH_FRAGMENT="main/scripts/update-skills.sh"' "$UPDATE_SH" \
  && grep -q 'heal_weekly_cron_updater' "$UPDATE_SH" \
  && ok "installed legacy Sunday scripts self-heal to the root updater" \
  || bad "weekly cron self-heal missing"

for suite in \
  tests/unit/sop-library-update-path-ingest.test.sh \
  tests/unit/update-command-center-runtime-config.test.sh \
  tests/unit/power-resilience-gate.test.sh \
  tests/unit/provisioning-completeness-gate.test.py \
  tests/unit/fleet-refresh-cc-main-convergence.test.py \
  tests/unit/update-skills-full-scripts-tree.test.sh; do
  [ -f "$TARGET_ROOT/$suite" ] && ok "stage has a regression suite: $suite" || bad "missing stage suite: $suite"
done

printf 'RESULT: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
