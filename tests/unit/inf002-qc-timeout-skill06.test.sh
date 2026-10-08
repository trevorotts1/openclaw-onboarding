#!/usr/bin/env bash
# tests/unit/inf002-qc-timeout-skill06.test.sh
# INF002 E: Skill 06 (ghl-install-pages) QC gets 600 s ("give it 10 minutes"); every other
# skill keeps its limit (OBS_QC_TIMEOUT_SECONDS when set, else the 180 s default).
# Runs the REAL gate loop from update-skills.sh against a stub obs_verify_skill that echoes
# the deadline it was handed. Hermetic: temp dirs only.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok()  { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/skills/05-ghl-setup" "$T/skills/06-ghl-install-pages" "$T/skills/29-ghl-convert-and-flow"
LOOP="$(sed -n '/^    for _gskill in "\$SKILLS_DIR"\/\[0-9\]\*\/; do$/,/^    done$/p' "$REPO/update-skills.sh")"
[ -n "$LOOP" ] && ok "gate loop found in update-skills.sh" || { bad "gate loop not found"; echo "$PASS passed, $FAIL failed"; exit 1; }

# The gate prints $_greason only on failure, so the stub fails to surface the deadline it got.
run_fail() {
  SKILLS_DIR="$T/skills" PRESET="$1" bash -c '
    [ -n "$PRESET" ] && export OBS_QC_TIMEOUT_SECONDS="$PRESET"
    obs_verify_skill() { echo "deadline=${OBS_QC_TIMEOUT_SECONDS:-180}"; return 1; }
    '"$LOOP"'' 2>&1
}
out="$(run_fail '')"
echo "$out" | grep "06-ghl-install-pages" | grep -q "deadline=600" && ok "06 gets 600 s by default" || bad "06 did not get 600: $out"
echo "$out" | grep "05-ghl-setup" | grep -q "deadline=180" && ok "05 keeps the 180 s default" || bad "05 changed: $out"
echo "$out" | grep "29-ghl-convert-and-flow" | grep -q "deadline=180" && ok "29 keeps the 180 s default" || bad "29 changed: $out"
out="$(run_fail 240)"
echo "$out" | grep "06-ghl-install-pages" | grep -q "deadline=600" && ok "06 stays 600 s when the operator set 240" || bad "06 ignored: $out"
echo "$out" | grep "05-ghl-setup" | grep -q "deadline=240" && ok "05 keeps the operator's 240 s" || bad "05 override lost: $out"
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
