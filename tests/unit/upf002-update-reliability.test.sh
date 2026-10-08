#!/usr/bin/env bash
# tests/unit/upf002-update-reliability.test.sh
# UPF002 U1 (extensions survive cleanup), U2 (presentation entry co-location),
# U4 (verification gate survives the temp clone being deleted). Hermetic: temp dirs only.
# U3 lives in 70-lean-core-file-system/tests/test-wire.sh; U5 in ghl-mcp-assert-runtime.test.sh.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok()  { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT

echo "== U1: extensions staged before the temp clone is deleted =="
# Run the real staging lines, then the real cleanup, then read what the installer would read.
mkdir -p "$T/u1/clone/extensions/ceo-routing-doctrine" "$T/u1/cfg"
echo v4.3 > "$T/u1/clone/extensions/ceo-routing-doctrine/index.js"
ONBOARDING_DIR="$T/u1/clone" OC_CONFIG="$T/u1/cfg" bash -c "
  $(sed -n '/^  _OC_EXT_STAGE=/,/^  fi$/p' "$REPO/update-skills.sh")
  rm -rf '$T/u1/clone'
  [ -f \"\$_OC_EXT_STAGE/ceo-routing-doctrine/index.js\" ]"
[ $? -eq 0 ] && ok "extension present after cleanup" || bad "extension lost after cleanup"
s=$(grep -n '^  _OC_EXT_STAGE=' "$REPO/update-skills.sh" | head -1 | cut -d: -f1)
c=$(grep -n '^  # Cleanup$' "$REPO/update-skills.sh" | head -1 | cut -d: -f1)
[ -n "$s" ] && [ -n "$c" ] && [ "$s" -lt "$c" ] && ok "stage ($s) precedes cleanup ($c)" || bad "stage not before cleanup"
grep -q '_RD_SRC="${_OC_EXT_STAGE:-' "$REPO/update-skills.sh" && grep -q '_TE_SRC="${_OC_EXT_STAGE:-' "$REPO/update-skills.sh" \
  && ok "both plugin installers read the stage" || bad "installers still read the clone"

echo "== U2: co-location copies every file that exists in the repo =="
mkdir -p "$T/u2/skills/23-ai-workforce-blueprint/scripts" "$T/u2/ws/departments/Presentations/scripts"
cp "$REPO/23-ai-workforce-blueprint/scripts/presentation-canonical-entry.sh" "$T/u2/skills/23-ai-workforce-blueprint/scripts/"
out="$(SKILLS_DIR="$T/u2/skills" OC_WS_RESOLVED="$T/u2/ws" bash -c "
  oc_resolve_workspace_announced() { return 0; }
  $(sed -n '/^colocate_presentation_entry() {/,/^}/p' "$REPO/update-skills.sh")
  colocate_presentation_entry" 2>&1)"
[ -x "$T/u2/ws/departments/Presentations/scripts/presentation-canonical-entry.sh" ] && ! echo "$out" | grep -q partial \
  && ok "entry script copied, no 'partial' warning" || bad "co-location partial: $out"

echo "== U4: gate works after the temp clone (and its helper) is gone =="
H="$T/u4/home"; mkdir -p "$H/.openclaw/scripts" "$T/u4/clone/scripts" "$T/u4/skills/09-demo" "$T/u4/bin" "$T/u4/ws"
cp "$REPO/scripts/onboarding-state.sh" "$REPO/scripts/run-with-deadline.py" "$T/u4/clone/scripts/"
cp "$REPO/lib-onboarding-state.sh" "$T/u4/clone/" 2>/dev/null; cp "$REPO/scripts/run-with-deadline.py" "$H/.openclaw/scripts/"
printf -- '---\nname: demo\n---\n' > "$T/u4/skills/09-demo/SKILL.md"
printf '#!/bin/sh\nexit 0\n' > "$T/u4/skills/09-demo/qc-09-demo.sh"; chmod +x "$T/u4/skills/09-demo/qc-09-demo.sh"
printf '#!/bin/sh\necho "name: demo ready"\n' > "$T/u4/bin/openclaw"; chmod +x "$T/u4/bin/openclaw"
res="$(HOME="$H" PATH="$T/u4/bin:$PATH" OPENCLAW_AGENT_ID=main OPENCLAW_WORKSPACE="$T/u4/ws" bash -c "
  . '$T/u4/clone/scripts/onboarding-state.sh'
  rm -rf '$T/u4/clone'
  obs_verify_skill 09-demo '$T/u4/skills'; echo rc=\$?" 2>&1)"
echo "$res" | grep -q 'rc=0' && ! echo "$res" | grep -q 'NOT verified\|not-visible\|nonzero-exit' \
  && ok "visible, passing skill verified after clone deletion" || bad "gate still fails: $res"

echo "== $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ]
