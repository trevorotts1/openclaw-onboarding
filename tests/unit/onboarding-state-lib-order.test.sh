#!/usr/bin/env bash
# tests/unit/onboarding-state-lib-order.test.sh
# Locks: the shim must source the lib BESIDE it (delivered by every roll) before
# "../lib-onboarding-state.sh" (a stale ~/.openclaw/lib-... copy on old boxes), and
# oc_skill_registered must pass --agent on multi-agent boxes. Hermetic (mktemp HOME).
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }

# Box layout: scripts/ beside-lib is fresh, parent lib is stale.
mkdir -p "$T/box/scripts"
cp "$REPO/scripts/onboarding-state.sh" "$T/box/scripts/"
cp "$REPO/lib-onboarding-state.sh" "$T/box/scripts/"
echo 'STALE_LIB_LOADED=1' > "$T/box/lib-onboarding-state.sh"
out="$(HOME="$T/h" bash -c 'source "$1" 2>/dev/null; echo "stale=${STALE_LIB_LOADED:-no}"; command -v oc_state_seed >/dev/null && echo fresh=yes' _ "$T/box/scripts/onboarding-state.sh")"
echo "$out" | grep -q 'stale=no' && echo "$out" | grep -q 'fresh=yes' && ok "beside-copy wins over stale ../lib" || bad "stale ../lib won: $out"

# Repo layout: lib only at ../ (repo root) still resolves.
mkdir -p "$T/repo/scripts"
cp "$REPO/scripts/onboarding-state.sh" "$T/repo/scripts/"; cp "$REPO/lib-onboarding-state.sh" "$T/repo/"
out="$(HOME="$T/h" bash -c 'source "$1" 2>/dev/null; command -v oc_state_seed >/dev/null && echo fresh=yes' _ "$T/repo/scripts/onboarding-state.sh")"
echo "$out" | grep -q 'fresh=yes' && ok "repo layout (../lib) still resolves" || bad "repo layout broken"

# oc_skill_registered passes --agent when the default agent resolves.
mkdir -p "$T/bin" "$T/sk/01-demo"
printf -- '---\nname: demo\n---\n' > "$T/sk/01-demo/SKILL.md"
printf '#!/bin/sh\necho "ARGS:$*" >> "%s/args"\necho "name: demo ready"\n' "$T" > "$T/bin/openclaw"; chmod +x "$T/bin/openclaw"
out="$(HOME="$T/h" PATH="$T/bin:$PATH" OPENCLAW_AGENT_ID=jill OC_SKILLS_DIR="$T/sk" bash -c 'source "$1" 2>/dev/null; oc_skill_registered 01-demo' _ "$T/box/scripts/onboarding-state.sh")"; rc=$?
grep -q 'skills info demo --agent jill' "$T/args" 2>/dev/null && ok "oc_skill_registered passes --agent" || bad "no --agent: $(cat "$T/args" 2>/dev/null)"
# R2: the updater refreshes (never creates) the stale parent copy.
grep -q '_OC_PARENT_LIB' "$REPO/update-skills.sh" && grep -q 'cmp -s "$_OC_PARENT_LIB"' "$REPO/update-skills.sh" && ok "updater refreshes stale parent lib" || bad "updater lacks stale-parent refresh"
exit $fail
