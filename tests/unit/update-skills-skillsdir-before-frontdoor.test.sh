#!/usr/bin/env bash
# tests/unit/update-skills-skillsdir-before-frontdoor.test.sh — v25.3.18 regression lock.
# v25.3.17 aborted every run with `SKILLS_DIR: unbound variable` right after
# "[lock] acquired": the front-door block expanded "$SKILLS_DIR" under
# `set -euo pipefail` before SKILLS_DIR was assigned. This test runs the REAL
# front-door lookup text out of update-skills.sh with SKILLS_DIR unset and
# asserts it reaches the installed shared-utils copy (not just "does not crash").
# Exit: 0 green; 1 regressed.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATE_SH="$REPO_ROOT/update-skills.sh"
W="$(mktemp -d "${TMPDIR:-/tmp}/skillsdir-frontdoor-XXXXXX")"
trap 'rm -rf "$W"' EXIT

mkdir -p "$W/skills/shared-utils" "$W/empty"
: > "$W/skills/shared-utils/lib-frontdoor.sh"
: > "$W/skills/shared-utils/oct4_frontdoor.py"

{
  echo 'set -euo pipefail'
  echo '_SCRIPT_DIR="$1"; ONBOARDING_ONLY=0; OC_SKILLS_DIR="$2"'
  sed -n '/^discover_skills_dir() {/,/^}/p' "$UPDATE_SH"
  echo 'main() {'
  # front-door header comment .. the lib/stage lookup loops (cut before the FATAL check)
  sed -n '/OCT4 issue #10 — ONE FRONT DOOR/,/if \[ -z "\$_FRONTDOOR_LIB" \]/p' "$UPDATE_SH" | sed '$d'
  echo '  fi'
  echo '  echo "LIB=$_FRONTDOOR_LIB"'
  echo '}'
  echo 'main'
} > "$W/harness.sh"

OUT="$(bash "$W/harness.sh" "$W/empty" "$W/skills" 2>&1)"
if [ "$OUT" = "LIB=$W/skills/shared-utils/lib-frontdoor.sh" ]; then
  echo "  PASS: front door resolves lib-frontdoor.sh via SKILLS_DIR under set -u"
else
  echo "  FAIL: front-door lookup did not resolve via SKILLS_DIR: $OUT" >&2
  exit 1
fi
