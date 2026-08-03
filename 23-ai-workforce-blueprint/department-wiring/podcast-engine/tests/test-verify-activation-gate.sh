#!/bin/bash
# test-verify-activation-gate.sh - hermetic behavioral tests for the activation-layer
# gate (check 8) in verify-podcast-engine-wiring.py. Builds a scratch repo tree from
# the real wiring inputs plus synthetic activation files, then asserts the gate's
# two-tier behavior: zero activation scripts on disk is reported as not installed and
# exits 0 (co-land tolerance); any partial, non-executable, or undocumented layer
# exits 7; a complete documented layer exits 0.
#
# Zero em dashes, no triple-backtick fences. Exits 0 when all checks pass.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIRING_DIR="$(cd "$HERE/.." && pwd)"
SRC="$(cd "$WIRING_DIR/../../.." && pwd)"
VERIFY="$WIRING_DIR/verify-podcast-engine-wiring.py"

T="$(mktemp -d /tmp/verify-activation-gate.XXXXXX)"
trap 'rm -rf "$T"' EXIT

mkdir -p "$T/23-ai-workforce-blueprint/department-wiring/podcast-engine" \
         "$T/23-ai-workforce-blueprint/templates/role-library" \
         "$T/project-prds/podcast-engine/design" \
         "$T/58-podcast-production-engine/scripts"
cp "$SRC/23-ai-workforce-blueprint/skill-department-map.json" "$T/23-ai-workforce-blueprint/"
cp "$SRC/23-ai-workforce-blueprint/department-naming-map.json" "$T/23-ai-workforce-blueprint/"
cp "$SRC/23-ai-workforce-blueprint/templates/role-library/_index.json" "$T/23-ai-workforce-blueprint/templates/role-library/"
cp "$SRC/project-prds/podcast-engine/design/dashboard-design.md" "$T/project-prds/podcast-engine/design/"
cp "$WIRING_DIR/wiring.json" "$T/23-ai-workforce-blueprint/department-wiring/podcast-engine/"
cp "$VERIFY" "$T/23-ai-workforce-blueprint/department-wiring/podcast-engine/"

V="$T/23-ai-workforce-blueprint/department-wiring/podcast-engine/verify-podcast-engine-wiring.py"
SCRIPTS="$T/58-podcast-production-engine/scripts"

skill_full() {
  cat > "$T/58-podcast-production-engine/SKILL.md" <<'SK'
# Podcast Production Engine (Skill 58)

## Activation layer (the production processor)

register-podcast-hook.sh installs the intake hook, podcast_controller.py
drives queued flows, install-podcast-department.sh installs the agent.

## Next section
SK
}

skill_no_head() {
  cat > "$T/58-podcast-production-engine/SKILL.md" <<'SK'
# Podcast Production Engine (Skill 58)

## Pipeline
no activation heading anywhere in this file.
SK
}

mk_scripts() {
  printf '#!/bin/bash\n' > "$SCRIPTS/register-podcast-hook.sh"
  printf '#!/bin/bash\n' > "$SCRIPTS/install-podcast-department.sh"
  printf '#!/usr/bin/env python3\n' > "$SCRIPTS/podcast_controller.py"
  chmod 755 "$SCRIPTS"/*
}

pass=0
fail=0
check_rc() { # name expected_rc
  local name="$1" want="$2" got out
  out="$(python3 "$V" 2>&1)" && got=$? || got=$?
  if [ "$got" -eq "$want" ]; then
    pass=$((pass + 1)); echo "PASS [$name] rc=$got"
  else
    fail=$((fail + 1)); echo "FAIL [$name] want rc=$want got rc=$got"
    echo "$out" | tail -12
  fi
}
check_note() { # name needle
  local name="$1" needle="$2" out
  out="$(python3 "$V" 2>&1 || true)"
  if echo "$out" | grep -q "$needle"; then
    pass=$((pass + 1)); echo "PASS [$name]"
  else
    fail=$((fail + 1)); echo "FAIL [$name] missing needle: $needle"
  fi
}

# A: complete layer (3 scripts, executable, documented) exits 0
mk_scripts; skill_full
check_rc "A complete layer exits 0" 0
check_note "A reports verified" "activation layer verified"

# B: partial layer (only the controller present) exits 7 with missing-script errors
rm -f "$SCRIPTS/register-podcast-hook.sh" "$SCRIPTS/install-podcast-department.sh"
check_rc "B partial layer exits 7" 7
check_note "B names missing hook script" "missing script 58-podcast-production-engine/scripts/register-podcast-hook.sh"
check_note "B names missing install script" "missing script 58-podcast-production-engine/scripts/install-podcast-department.sh"

# C: complete layer but one shell script not executable exits 7
mk_scripts; chmod 644 "$SCRIPTS/register-podcast-hook.sh"; skill_full
check_rc "C non-executable script exits 7" 7
check_note "C names the non-executable script" "register-podcast-hook.sh exists but is not executable"
chmod 755 "$SCRIPTS/register-podcast-hook.sh"

# D: complete scripts but SKILL.md has no activation heading exits 7
skill_no_head
check_rc "D no activation heading exits 7" 7
check_note "D names the missing heading" "SKILL.md has no activation section heading"

# E: activation heading present but the section body omits a script exits 7
cat > "$T/58-podcast-production-engine/SKILL.md" <<'SK'
## Activation
register-podcast-hook.sh and install-podcast-department.sh only.
SK
check_rc "E undocumented script exits 7" 7
check_note "E names the undocumented script" "activation section does not document podcast_controller.py"

# F: zero activation scripts on disk exits 0 and reports not installed (co-land tolerance)
rm -f "$SCRIPTS"/*
skill_full
check_rc "F zero scripts exits 0" 0
check_note "F reports not installed" "activation layer not installed"

echo "== $pass passed, $fail failed =="
[ "$fail" -eq 0 ]
