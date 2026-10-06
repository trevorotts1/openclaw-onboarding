#!/usr/bin/env bash
# frontdoor_update_999: a 9Router box with NO 999-setup checkout gets one cloned
# and the guarded skills-only path runs; a box with no 9Router signal gets nothing.
# Hermetic: fake origin via git insteadOf, HOME=mktemp.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }
O="$T/origin"; mkdir -p "$O/CONTROL" "$O/.claude/skills/nine-router-setup/scripts"
echo x > "$O/AGENT_INSTALL.md"; echo kaizen > "$O/CONTROL/bundled-skills.txt"
printf '#!/bin/bash\nmain() { :; }\nmain "$@"\n' > "$O/.claude/skills/nine-router-setup/scripts/setup-macos.sh"
git -C "$O" init -q && git -C "$O" add -A && git -C "$O" -c user.email=a@b -c user.name=t commit -qm i
run(){ HOME="$1" GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="url.$O.insteadOf" GIT_CONFIG_VALUE_0="https://github.com/trevorotts1/999-setup.git" \
  bash -c 'source "$1"; frontdoor_update_999' _ "$REPO/shared-utils/lib-frontdoor.sh" 2>&1; }
mkdir -p "$T/h1/.9router"; out="$(run "$T/h1")"
[ -d "$T/h1/999-setup/.git" ] && ok "9Router box: checkout cloned" || bad "no clone: $out"
echo "$out" | grep -q "skills-only\|predates" && ok "guarded skills-only path reached" || bad "guard not reached: $out"
mkdir -p "$T/h2"; out="$(run "$T/h2")"
[ ! -e "$T/h2/999-setup" ] && ok "no 9Router signal: nothing installed" || bad "installed without signal"
exit $fail
