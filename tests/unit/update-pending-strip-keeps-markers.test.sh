#!/usr/bin/env bash
# tests/unit/update-pending-strip-keeps-markers.test.sh
# THE DEFECT: _strip_update_pending_sections() removed a "## UPDATE PENDING"
# section from its header to the next "## " line. When a managed block such as
# "<!-- BEGIN SKILL38: SKILL38_RUNTIME_INVARIANTS -->" sat directly after the
# notice, the BEGIN comment was swallowed (BEGIN=0 / END=1) on every updater
# run, so the block's binding rules dropped out of the agent's bootstrap.
# METHOD: extract the REAL function verbatim from update-skills.sh, run it on a
# fixture in a throwaway dir, and assert on the resulting file. Also asserts the
# install.sh copy of the pattern stays identical to update-skills.sh's.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TD="$(mktemp -d)"; trap 'rm -rf "$TD"' EXIT
fail=0
src="$TD/fn.sh"
awk '/^_strip_update_pending_sections\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$ROOT/update-skills.sh" > "$src"
grep -q '^_strip_update_pending_sections() {' "$src" || { echo "FAIL: could not extract _strip_update_pending_sections"; exit 2; }
# shellcheck disable=SC1090
source "$src"

run_case() { # name marker
  local name="$1" marker="$2" f="$TD/$1/AGENTS.md"
  mkdir -p "$TD/$1"
  cat > "$f" <<EOF
# Agents

## Earlier Section
keep me

## UPDATE PENDING -- Skill Update to v1.0.0
- This section is removed AUTOMATICALLY by the next update-skills.sh run.

$marker
## Block Heading
1. rule one
<!-- END ${marker#<!-- BEGIN } 
EOF
  _strip_update_pending_sections "$f" >/dev/null 2>&1 || { echo "FAIL[$name]: strip refused (rc=$?)"; fail=1; return; }
  if grep -q 'UPDATE PENDING' "$f"; then echo "FAIL[$name]: notice not removed"; fail=1; fi
  if ! grep -qxF "$marker" "$f"; then echo "FAIL[$name]: BEGIN marker was deleted"; fail=1; fi
  if ! grep -q '^## Block Heading' "$f" || ! grep -q '^keep me' "$f"; then echo "FAIL[$name]: other content lost"; fail=1; fi
  [ "$fail" -eq 0 ] && echo "PASS[$name]: notice removed, BEGIN marker kept"
}
run_case skill38-namespace '<!-- BEGIN SKILL38: SKILL38_RUNTIME_INVARIANTS -->'
run_case skill-namespace   '<!-- BEGIN skill:38-conversational-ai-system:agents -->'

a="$(grep -F "(?!^##\\s)" "$ROOT/update-skills.sh" | sed 's/#.*//;s/[[:space:]]*$//;s/^[[:space:]]*//')"
b="$(grep -F "(?!^##\\s)" "$ROOT/install.sh" | sed 's/#.*//;s/[[:space:]]*$//;s/^[[:space:]]*//')"
if [ -n "$a" ] && [ "$a" = "$b" ]; then echo "PASS[lockstep]: install.sh pattern matches update-skills.sh"; else echo "FAIL[lockstep]: patterns differ"; fail=1; fi
exit $fail
