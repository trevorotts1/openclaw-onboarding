#!/usr/bin/env bash
# R11-R15 locks: SOP manifest absent = exit 0; skill 43 versions are X.Y.Z; gate skips qc-built-*;
# skill 06 lattice check skips off-repo; updater delivers lib-shared.sh. Hermetic.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }
# R11
mkdir -p "$T/h/.openclaw"; HOME="$T/h" OPENCLAW_ROOT="$T/oc" python3 "$REPO/23-ai-workforce-blueprint/scripts/author-missing-sops.py" >/dev/null 2>&1; [ $? -eq 0 ] && ok "R11 no manifest -> exit 0" || bad "R11 default"
python3 "$REPO/23-ai-workforce-blueprint/scripts/author-missing-sops.py" --sop-needed "$T/nope.json" >/dev/null 2>&1; [ $? -eq 1 ] && ok "R11 explicit missing path -> exit 1" || bad "R11 explicit"
# R12
v="$(tr -d '[:space:]' < "$REPO/43-graphify-knowledge-graph/skill-version.txt")"
fm="$(awk '/^version:/{print $2; exit}' "$REPO/43-graphify-knowledge-graph/SKILL.md")"
printf '%s' "$v" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$' && [ "$v" = "$fm" ] && ok "R12 skill 43 versions X.Y.Z and equal" || bad "R12 $v vs $fm"
# R13 (lib gate picks qc-convert-and-flow.sh, not qc-built-workflow.sh)
mkdir -p "$T/sk/44-x"; printf -- '---\nname: x\n---\n' > "$T/sk/44-x/SKILL.md"
printf '#!/bin/sh\nexit 0\n' > "$T/sk/44-x/qc-convert-and-flow.sh"; printf '#!/bin/sh\nexit 9\n' > "$T/sk/44-x/qc-built-workflow.sh"; chmod +x "$T/sk/44-x/"*.sh
mkdir -p "$T/bin"; printf '#!/bin/sh\necho "name: x ready"\n' > "$T/bin/openclaw"; chmod +x "$T/bin/openclaw"
out="$(HOME="$T/h" PATH="$T/bin:$PATH" OC_SKILLS_DIR="$T/sk" OPENCLAW_ROOT="$T/oc" bash -c 'source "$1" 2>/dev/null; oc_gate_skill 44-x >/dev/null 2>&1; echo rc=$?' _ "$REPO/lib-onboarding-state.sh" 2>&1)"
echo "$out" | grep -q 'rc=0' && ok "R13 gate used qc-convert-and-flow.sh (qc-built-workflow.sh would exit 9)" || bad "R13: $out"
# R14
grep -q 'SKIP: GK-27' "$REPO/06-ghl-install-pages/qc-ghl-install-pages.sh" && ok "R14 skill 06 lattice check skips off-repo" || bad "R14"
# R15
grep -q 'lib-shared.sh" "\$SKILLS_DIR/lib-shared.sh"' "$REPO/update-skills.sh" && ok "R15 updater delivers lib-shared.sh" || bad "R15"
exit $fail
