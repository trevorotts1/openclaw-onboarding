#!/usr/bin/env bash
# Issue 43: oc_gate_skill runs verify.sh for the launch family (no qc-*.sh).
# verify.sh exit 0 -> qc-passed; nonzero -> qc-failed; missing verify.sh -> fail closed;
# a skill NOT in OC_VERIFY_GATED_SKILLS keeps the old behaviour (no verify.sh run). Hermetic.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }
# one skills root per case (the stub CLI reports the tree path of the skill under test)
gate(){ # gate <case-dir-name> <verify-exit|none> <gated:yes|no> -> prints rc
  local d="$T/$1"; rm -rf "$d"; mkdir -p "$d/bin" "$d/h" "$d/oc" "$d/sk/78-x"
  printf -- '---\nname: x\nversion: 1.0.0\n---\n' > "$d/sk/78-x/SKILL.md"; printf '1.0.0\n' > "$d/sk/78-x/skill-version.txt"
  [ "$2" = none ] || printf '#!/bin/sh\nexit %s\n' "$2" > "$d/sk/78-x/verify.sh"
  printf '#!/bin/sh\ncat <<'"'"'OUT'"'"'\nx ✓ Ready\n\nDetails:\n  Source: openclaw-managed\n  Path: %s\n  Visible to model: yes\nOUT\nexit 0\n' "$d/sk/78-x/SKILL.md" > "$d/bin/openclaw"; chmod +x "$d/bin/openclaw"
  local list="78-x"; [ "$3" = yes ] || list=""
  HOME="$d/h" PATH="$d/bin:$PATH" OC_SKILLS_DIR="$d/sk" OPENCLAW_ROOT="$d/oc" OC_CONFIG="$d/oc" ONBOARDING_STATE_FILE="$d/oc/.onboarding-state.json" \
    bash -c 'source "$1" 2>/dev/null; OC_VERIFY_GATED_SKILLS="$2"; oc_gate_skill 78-x >/dev/null 2>&1; echo rc=$?' _ "$REPO/lib-onboarding-state.sh" "$list" 2>&1 | tail -1
}
[ "$(gate a 0 yes)" = "rc=0" ] && ok "verify.sh exit 0 -> gate passes" || bad "pass case: $(gate a 0 yes)"
[ "$(gate b 1 yes)" != "rc=0" ] && ok "verify.sh exit 1 -> gate fails" || bad "failing verify.sh passed"
[ "$(gate c none yes)" != "rc=0" ] && ok "listed skill with no verify.sh -> gate fails closed" || bad "missing verify.sh passed"
[ "$(gate d 1 no)" = "rc=0" ] && ok "unlisted skill's verify.sh is not run (old behaviour)" || bad "unlisted case: $(gate d 1 no)"
exit $fail
