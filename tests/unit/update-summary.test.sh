#!/usr/bin/env bash
# scripts/update-summary.py: UPDATE PENDING "What changed" lists releases between old and new
# version, the JEV core callout, and changed skills; flag template carries it; CHANGELOG refresh wired.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }
mkdir -p "$T/b/74-x" "$T/b/75-y" "$T/l/74-x" "$T/l/75-y"
printf 'v2\n' > "$T/b/74-x/skill-version.txt"; printf 'v1\n' > "$T/l/74-x/skill-version.txt"
printf 'v1\n' > "$T/b/75-y/skill-version.txt"; printf 'v1\n' > "$T/l/75-y/skill-version.txt"
cat > "$T/CL.md" <<'CL'
## [v2.0.0]  -  2026-01-02  -  JEV intake routing lands
## [v1.5.0]  -  2026-01-01  -  Plain fix
## [v1.0.0]  -  2025-12-01  -  Old stuff
CL
out="$(python3 "$REPO/scripts/update-summary.py" v1.0.0 v2.0.0 "$T/CL.md" "$T/b" "$T/l")"
echo "$out" | grep -q 'v2.0.0: JEV intake routing lands' && echo "$out" | grep -q 'v1.5.0' && ! echo "$out" | grep -q 'v1.0.0:' && ok "range is (old,new]" || bad "range: $out"
echo "$out" | grep -q 'JEV decision engine.*routing-mode.sh status' && ok "core JEV callout" || bad "no JEV callout"
echo "$out" | grep -q '74-x (v1 -> v2)' && ! echo "$out" | grep -q '75-y' && ok "changed skills only" || bad "skills: $out"
grep -q 'UPDATE_SUMMARY_TEXT:-' "$REPO/update-skills.sh" && ok "flag template includes summary" || bad "flag lacks summary"
grep -q 'CHANGELOG.md" "\$HOME/Downloads/openclaw-master-files/CHANGELOG.md"' "$REPO/update-skills.sh" && ok "CHANGELOG refresh wired" || bad "no CHANGELOG refresh"
# R9: the V4.3 intake text names the JEV decision engine everywhere it is stamped.
for f in AGENTS.md shared-utils/ceo_execution_policy.py shared-utils/intake_classifier_policy.txt extensions/ceo-routing-doctrine/dist/index.js 23-ai-workforce-blueprint/master-orchestrator-dept/SOP-00-Owner-Task-Routing.md; do
  grep -q 'mc-route.sh is the JEV decision engine' "$REPO/$f" && ok "JEV named in $f" || bad "JEV missing in $f"
done
exit $fail
