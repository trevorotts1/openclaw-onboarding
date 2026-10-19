#!/usr/bin/env bash
# tests/unit/frontdoor-verdict-after-install.test.sh — CAN006 regression lock (fleet roll 20261019).
# The defect: update-skills.sh ran the shared front-door tail (repair runner +
# health gate) BEFORE the content install and `exit`ed on a gate failure. A
# failing gate on the box's OLD tree therefore aborted the very update that
# ships the fix, so .onboarding-content-manifest.json + .onboarding-version
# stayed at the old release and the roll's role-library check failed with
# "content manifest is for v27.1.29, not v27.1.36".
# This runs the REAL front-door text out of update-skills.sh with a stage that
# fails, and asserts (1) the run still reaches the install, (2) the verdict is
# re-judged after the install: clean -> 0, still failing -> the early rc.
# Writes only under a mktemp dir (HOME + OPENCLAW_ROOT are pointed there).
# Exit: 0 green; 1 regressed.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATE_SH="$REPO_ROOT/update-skills.sh"
W="$(mktemp -d "${TMPDIR:-/tmp}/frontdoor-verdict-XXXXXX")"
trap 'rm -rf "$W"' EXIT
FAIL=0
ok()  { echo "  PASS: $1"; }
bad() { echo "  FAIL: $1" >&2; FAIL=1; }

mkdir -p "$W/repo/shared-utils" "$W/skills" "$W/home"
VER="v0.0.0-test"
printf '%s\n' "$VER" > "$W/repo/shared-utils/.frontdoor-fetched-version"
echo '# run_full_stage' > "$W/repo/shared-utils/oct4_frontdoor.py"
# Fake shared library: verdict comes from $FD_MODE_FILE (fail|pass), like the real
# frontdoor_run_stage contract (sets FRONTDOOR_STATUS/JSON, returns 0 only when clean).
cat > "$W/repo/shared-utils/lib-frontdoor.sh" <<'EOF'
frontdoor_run_stage() {
  FRONTDOOR_JSON=""
  if [ "$(cat "$FD_MODE_FILE")" = "pass" ]; then
    FRONTDOOR_STATUS="ok"; FRONTDOOR_JSON='{"frontdoor":{"status":"ok"}}'; return 0
  fi
  FRONTDOOR_STATUS="gate-failed"; return 1
}
EOF

run_harness() {  # $1 = verdict of the early (pre-install) stage, $2 = verdict after the install
  echo "$1" > "$W/mode"
  {
    echo 'set -uo pipefail'
    echo "_SCRIPT_DIR='$W/repo'; ONBOARDING_ONLY=0; ONBOARDING_VERSION='$VER'; OC_SKILLS_DIR='$W/skills'"
    echo "HOME='$W/home'; export OPENCLAW_ROOT='$W/home/.openclaw'; FD_MODE_FILE='$W/mode'"
    sed -n '/^discover_skills_dir() {/,/^}/p' "$UPDATE_SH"
    sed -n '/^frontdoor_final_verdict() {/,/^}/p' "$UPDATE_SH"
    echo 'main() {'
    # the real early front-door block, header comment .. the banner that opens the install
    sed -n '/OCT4 issue #10 — ONE FRONT DOOR/,/^  echo "============================================"$/p' "$UPDATE_SH"
    echo '  echo REACHED-INSTALL'
    echo "  echo '$2' > \"\$FD_MODE_FILE\""
    echo '  frontdoor_final_verdict; echo "FINAL-RC=$?"'
    echo '}'
    echo 'main'
  } > "$W/harness.sh"
  bash "$W/harness.sh" 2>&1
}

OUT="$(run_harness fail pass)"
if grep -q 'REACHED-INSTALL' <<<"$OUT"; then ok "failing gate on the old tree does not abort before the install"
else bad "update aborted at the front door before the install (stamp/manifest never refreshed): $(tail -3 <<<"$OUT")"; fi
if grep -q 'FINAL-RC=0' <<<"$OUT"; then ok "verdict re-judged after the install: clean tree -> rc 0"
else bad "post-install re-judge did not clear a gate that now passes: $(tail -3 <<<"$OUT")"; fi

OUT="$(run_harness fail fail)"
if grep -q 'FINAL-RC=2' <<<"$OUT"; then ok "still-failing gate after the install -> rc 2 (content current, infra needs attention)"
else bad "a gate that still fails after the install did not surface as rc 2: $(tail -3 <<<"$OUT")"; fi

OUT="$(run_harness pass pass)"
if grep -q 'REACHED-INSTALL' <<<"$OUT" && grep -q 'FINAL-RC=0' <<<"$OUT"; then ok "clean gate: no change in behaviour (rc 0)"
else bad "clean-gate path regressed: $(tail -3 <<<"$OUT")"; fi

# Both exit paths must re-judge: the end of main() and the content-current exit.
n="$(grep -c 'frontdoor_final_verdict' "$UPDATE_SH")"
[ "$n" -ge 4 ] && ok "frontdoor_final_verdict is wired at both exits ($n refs)" || bad "frontdoor_final_verdict not wired at both exits ($n refs)"

[ "$FAIL" -eq 0 ] && echo "frontdoor-verdict-after-install: PASS" || { echo "frontdoor-verdict-after-install: FAIL" >&2; exit 1; }
